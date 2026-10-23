"""Genetic self-improvement loop: the platform breeds, trains and selects its own models.

Each individual has a genome (its architecture + learning habits) and a brain
(its weights). Every generation:
  1. every individual lives (trains) for a fixed time on your data,
  2. it is tested on held-out data (fitness = validation loss, lower is better),
  3. the fittest survive (elitism), the rest are replaced by children made by
     crossover + mutation of tournament-selected parents,
  4. a child whose architecture matches a parent inherits that parent's weights,
     so learned knowledge is passed down rather than relearned,
  5. the champion goes through the quality gate and, if better, becomes the live model.
State is saved after every generation so the loop can be stopped and resumed.
"""
import json
import math
import os
import random
import time

import torch

from .config import pick_device
from .refresh import refresh_data as refresh_folders
from .storage import load_checkpoint, promote, save_checkpoint
from .train import build_model, evaluate, load_data, quality_gate, train_loop

GENE_POOL = {
    "n_layer": [2, 3, 4, 6, 8],
    "n_embd": [128, 192, 256, 384],
    "n_head": [2, 4, 6, 8],
    "block_size": [128, 256],
    "dropout": [0.0, 0.05, 0.1, 0.2],
    "batch_size": [8, 16, 32],
}
LR_RANGE = (1e-4, 3e-3)
ARCH_GENES = ("n_layer", "n_embd", "n_head", "block_size")


def _repair(g):
    if g["n_embd"] % g["n_head"]:
        g["n_head"] = max(h for h in GENE_POOL["n_head"] if g["n_embd"] % h == 0)
    return g


def random_genome(rng):
    g = {k: rng.choice(v) for k, v in GENE_POOL.items()}
    g["lr"] = math.exp(rng.uniform(math.log(LR_RANGE[0]), math.log(LR_RANGE[1])))
    return _repair(g)


def crossover(a, b, rng):
    child = {k: (a if rng.random() < 0.5 else b)[k] for k in a}
    # Architecture tends to be inherited as a unit from one parent so weights can be passed down.
    if rng.random() < 0.7:
        child.update({k: a[k] for k in ARCH_GENES})
    return _repair(child)


def mutate(g, rng, rate=0.25):
    g = dict(g)
    for k, options in GENE_POOL.items():
        if rng.random() < rate:
            g[k] = rng.choice(options)
    if rng.random() < rate:
        g["lr"] = min(LR_RANGE[1], max(LR_RANGE[0], g["lr"] * math.exp(rng.gauss(0, 0.5))))
    return _repair(g)


def arch(g):
    return tuple(g[k] for k in ARCH_GENES)


def tournament(pop, rng, k=3):
    return min(rng.sample(pop, min(k, len(pop))), key=lambda ind: ind["fitness"])


def _state_path(ws):
    return ws.evolution / "state.json"


def load_state(ws):
    p = _state_path(ws)
    return json.loads(p.read_text()) if p.exists() else None


class Evolution:
    def __init__(self, ws, population=6, minutes_per=2.0, elites=2, seed=None, log=print):
        self.ws, self.population, self.minutes_per, self.elites, self.log = ws, population, minutes_per, elites, log
        self.rng = random.Random(seed)
        self.device = pick_device()
        self.state = load_state(ws) or {"generation": 0, "next_id": 0, "population": [], "history": []}
        if not self.state["population"]:
            self.state["population"] = [self._new_individual(random_genome(self.rng)) for _ in range(population)]
            log(f"  created a population of {population} random individuals")
        self.reload_data()

    @property
    def generation(self):
        return self.state["generation"]

    def reload_data(self):
        self.tok, self.data = load_data(self.ws, self.log)

    def _new_individual(self, genome, parent=None):
        ind = {"id": self.state["next_id"], "genome": genome, "fitness": None, "parent": parent,
               "born": self.state["generation"], "steps": 0,
               "ckpt": str(self.ws.evolution / f"ind-{self.state['next_id']}.pt")}
        self.state["next_id"] += 1
        return ind

    def _live(self, ind):
        """Train one individual for its time slice and measure its fitness."""
        g = ind["genome"]
        model = build_model(self.tok, g)
        inherited = ""
        try:
            prev, _ = load_checkpoint(ind["ckpt"])
            model.load_state_dict(prev.state_dict())  # same architecture -> keep its brain
            inherited = " (inherited / continuing weights)"
        except (OSError, RuntimeError, KeyError):
            pass
        self.log(f"  #{ind['id']:<3} L{g['n_layer']} d{g['n_embd']} h{g['n_head']} ctx{g['block_size']} "
                 f"lr{g['lr']:.1e} bs{g['batch_size']} drop{g['dropout']}{inherited}")
        ind["steps"] += train_loop(model, self.data, g, self.device, self.minutes_per, log=self.log, log_every=0)
        ind["fitness"] = evaluate(model, self.data, self.device)["val_loss"]
        save_checkpoint(ind["ckpt"], model)
        self.log(f"       fitness (val loss) {ind['fitness']:.3f} after {ind['steps']} total steps")
        del model
        if self.device == "mps":
            torch.mps.empty_cache()

    def step(self, should_stop=lambda: False, on_individual=None):
        """Run one generation. Returns a summary, or None if should_stop() interrupted it."""
        gen = self.state["generation"]

        # 1-2. live and be tested
        for i, ind in enumerate(self.state["population"], 1):
            if should_stop():
                return None
            if on_individual:
                on_individual(ind, i, len(self.state["population"]))
            self._live(ind)

        # 3. selection
        pop = sorted(self.state["population"], key=lambda ind: ind["fitness"])
        champ = pop[0]
        self.state["history"].append({"generation": gen, "best": champ["fitness"],
                                      "mean": sum(i["fitness"] for i in pop) / len(pop),
                                      "champion": champ["id"], "genome": champ["genome"],
                                      "time": time.strftime("%Y-%m-%d %H:%M:%S")})
        self.log(f"  champion #{champ['id']} val loss {champ['fitness']:.3f}")

        # 5. champion -> quality gate -> model storage
        model, _ = load_checkpoint(champ["ckpt"], self.device)
        promoted, metrics = quality_gate(self.ws, model, self.data, self.device, self.log)
        if promoted:
            metrics.update({"steps": champ["steps"], "hp": champ["genome"], "generation": gen})
            promote(self.ws, f"evo-g{gen}-i{champ['id']}", champ["ckpt"], model, metrics, self.log)
        del model

        # 4. reproduction
        survivors = pop[:self.elites]
        children = []
        while len(survivors) + len(children) < self.population:
            a, b = tournament(pop, self.rng), tournament(pop, self.rng)
            child = self._new_individual(mutate(crossover(a["genome"], b["genome"], self.rng), self.rng),
                                         parent=a["id"])
            if arch(child["genome"]) == arch(a["genome"]):
                try:
                    parent_model, _ = load_checkpoint(a["ckpt"])
                    save_checkpoint(child["ckpt"], parent_model)   # inherit parent's weights
                    child["steps"] = a["steps"]
                except (OSError, RuntimeError):
                    pass
            children.append(child)
        for dead in pop[self.elites:]:
            try:
                os.remove(dead["ckpt"])
            except OSError:
                pass
        self.state["population"] = survivors + children
        self.state["generation"] += 1
        _state_path(self.ws).write_text(json.dumps(self.state, indent=2))
        return {"generation": gen, "best": champ["fitness"], "champion": champ["id"], "promoted": promoted}


def evolve(ws, generations=5, population=6, minutes_per=2.0, elites=2, forever=False,
           refresh_data=False, seed=None, log=print):
    evo = Evolution(ws, population, minutes_per, elites, seed, log)
    run = 0
    while forever or run < generations:
        if refresh_data and run > 0 and refresh_folders(ws, log):
            evo.reload_data()
        log(f"\n=== generation {evo.generation} ===")
        evo.step()
        run += 1
    log("\nevolution finished")
    return evo.state
