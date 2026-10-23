import argparse
import json
from pathlib import Path

from .config import Workspace


def main():
    p = argparse.ArgumentParser(prog="hg", description="HomeGrok: your own AI, trained on your computer.")
    p.add_argument("--workspace", help="workspace folder (default: ./workspace)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("setup", help="choose which folders HomeGrok may learn from")
    s.add_argument("--folders", nargs="+", required=True)
    s.add_argument("--exclude", nargs="*", default=[], help="extra name patterns to never read")
    s.add_argument("--max-total-mb", type=float)

    sub.add_parser("collect", help="training path 1: collect text from your folders")
    sub.add_parser("clean", help="training path 2: clean, redact secrets, dedupe")
    t = sub.add_parser("tokenizer", help="train a tokenizer on your data")
    t.add_argument("--vocab", type=int, default=4096)
    sub.add_parser("index", help="build the document search index")

    tr = sub.add_parser("train", help="train -> test quality -> store a model")
    tr.add_argument("--minutes", type=float, default=10)
    tr.add_argument("--resume", action="store_true", help="continue training the live model")
    for k, typ in (("n_layer", int), ("n_head", int), ("n_embd", int), ("block_size", int),
                   ("batch_size", int), ("lr", float), ("dropout", float)):
        tr.add_argument("--" + k.replace("_", "-"), dest=k, type=typ)

    ev = sub.add_parser("evolve", help="genetic loop: breed, train and select models by itself")
    ev.add_argument("--generations", type=int, default=5)
    ev.add_argument("--population", type=int, default=6)
    ev.add_argument("--minutes-per", type=float, default=2.0, help="training minutes per individual per generation")
    ev.add_argument("--forever", action="store_true", help="keep evolving until stopped (Ctrl+C)")
    ev.add_argument("--refresh-data", action="store_true", help="re-read your folders every generation")
    ev.add_argument("--seed", type=int)

    pl = sub.add_parser("pipeline", help="setup-to-model in one go: collect, clean, tokenizer, index, train")
    pl.add_argument("--minutes", type=float, default=10)
    pl.add_argument("--vocab", type=int, default=4096)

    cl = sub.add_parser("claude", help="use your Claude subscription as HomeGrok's brain")
    onoff = cl.add_mutually_exclusive_group()
    onoff.add_argument("--enable", action="store_true")
    onoff.add_argument("--disable", action="store_true")
    cl.add_argument("--chat-model", help="model alias for chat, e.g. opus, sonnet, haiku ('' = Claude Code default)")
    cl.add_argument("--background-model", help="model alias for background learning ('' = Claude Code default)")
    cl.add_argument("--chat-effort", choices=["low", "medium", "high", "xhigh", "max"])
    cl.add_argument("--background-effort", choices=["low", "medium", "high", "xhigh", "max"])
    cl.add_argument("--background-calls-per-day", type=int, help="cap on Claude calls the autopilot makes per day")
    cl.add_argument("--test", action="store_true", help="send one short test message")

    le = sub.add_parser("learn", help="autopilot: learn from your files 24/7 (Claude memory + local training)")
    le.add_argument("--once", action="store_true", help="run a single cycle and exit")
    le.add_argument("--population", type=int, default=3)
    le.add_argument("--minutes-per", type=float, default=2.0)
    le.add_argument("--digests-per-cycle", type=int, default=5)
    le.add_argument("--train-on-battery", action="store_true", help="keep training the local model on battery")

    sub.add_parser("memory", help="show what HomeGrok has learned about you")
    sub.add_parser("watchdog", help="health check: restart frozen parts, trim logs (launchd runs this)")

    ap = sub.add_parser("apply", help="open a job application in Chrome and fill it in (you submit)")
    ap.add_argument("url")

    tk = sub.add_parser("tasks", help="list, start or stop background tasks")
    tk.add_argument("--start", nargs=2, metavar=("TITLE", "GOAL"))
    tk.add_argument("--stop", metavar="TITLE_OR_ID", help='stop matching tasks ("all" stops every task)')

    sv = sub.add_parser("serve", help="start the API gateway + web chat")
    sv.add_argument("--port", type=int, default=8000)
    sub.add_parser("chat", help="chat in the terminal")
    sub.add_parser("status", help="show what has been built so far")

    a = p.parse_args()
    ws = Workspace(a.workspace)

    if a.cmd == "setup":
        cfg = ws.load_config()
        cfg["folders"] = [str(Path(f).expanduser().resolve()) for f in a.folders]
        cfg["exclude"] = a.exclude
        if a.max_total_mb:
            cfg["max_total_mb"] = a.max_total_mb
        ws.save_config(cfg)
        print(f"HomeGrok will learn from: {', '.join(cfg['folders'])}")
        print(f"Config saved to {ws.config_path}")
    elif a.cmd == "collect":
        from .collect import collect
        collect(ws, ws.load_config())
    elif a.cmd == "clean":
        from .clean import clean
        clean(ws)
    elif a.cmd == "tokenizer":
        from .tokenizer import train_tokenizer
        train_tokenizer(ws, a.vocab)
    elif a.cmd == "index":
        from .vectordb import build_index
        build_index(ws)
    elif a.cmd == "train":
        from .train import train
        hp = {k: getattr(a, k) for k in ("n_layer", "n_head", "n_embd", "block_size", "batch_size", "lr", "dropout")
              if getattr(a, k) is not None}
        train(ws, a.minutes, hp, a.resume)
    elif a.cmd == "evolve":
        from .evolve import evolve
        evolve(ws, a.generations, a.population, a.minutes_per, forever=a.forever,
               refresh_data=a.refresh_data, seed=a.seed)
    elif a.cmd == "pipeline":
        from .clean import clean
        from .collect import collect
        from .tokenizer import train_tokenizer
        from .train import train
        from .vectordb import build_index
        print("[1/5] collect data"); collect(ws, ws.load_config())
        print("[2/5] clean data"); clean(ws)
        print("[3/5] tokenizer"); train_tokenizer(ws, a.vocab)
        print("[4/5] index documents"); build_index(ws)
        print("[5/5] train, test, store"); train(ws, a.minutes)
        print("\nDone. Start chatting with:  ./hg serve   (or ./hg chat)")
    elif a.cmd == "claude":
        from .brain import BrainUnavailable, ClaudeBrain, find_cli
        cfg = ws.load_config()
        claude = cfg.setdefault("claude", {})
        if a.enable:
            cli = find_cli(claude.get("cli"))
            if not cli:
                raise SystemExit("The claude command isn't installed. Install Claude Code first.")
            claude.update(enabled=True, cli=cli)
        if a.disable:
            claude["enabled"] = False
        for key in ("chat_model", "background_model", "chat_effort", "background_effort", "background_calls_per_day"):
            value = getattr(a, key)
            if value is not None:
                claude[key] = value or None
        ws.save_config(cfg)
        brain = ClaudeBrain(ws)
        print(json.dumps({"settings": brain.settings, "status": brain.status()}, indent=2))
        if a.test:
            try:
                reply = brain.ask("Say hello to the user in one short sentence.", "You are HomeGrok.", kind="chat")
                print(f"\nClaude ({reply['model']}): {reply['text']}")
            except BrainUnavailable as e:
                raise SystemExit(f"\nClaude is unavailable: {e}")
    elif a.cmd == "learn":
        from .learner import Autopilot
        Autopilot(ws, population=a.population, minutes_per=a.minutes_per, digests_per_cycle=a.digests_per_cycle,
                  train_on_battery=a.train_on_battery).run(once=a.once)
    elif a.cmd == "apply":
        from .apply import run, pause_auto_mode
        try:
            run(ws, a.url)
        except Exception:   # a crashed window must not be retried straight away by auto mode
            pause_auto_mode(ws)
            raise
    elif a.cmd == "watchdog":
        from .watchdog import check
        print(json.dumps(check(ws)))
    elif a.cmd == "memory":
        from .memory import Memory
        memory = Memory(ws)
        print(memory.note() or "Nothing learned yet. Enable Claude (./hg claude --enable) and run ./hg learn.")
        print(f"\n({len(memory.digests())} files digested, {len(memory.pending())} waiting)")
    elif a.cmd == "serve":
        from .server import serve
        serve(ws, a.port)
    elif a.cmd == "chat":
        import sys
        from .orchestrator import Orchestrator
        orch = Orchestrator(ws)
        brain = "Claude" if orch.brain.enabled else f"local model {orch.server.name or '(none yet)'}"
        print(f"HomeGrok ({brain}). Ctrl+D to quit.")
        while True:
            try:
                msg = input("\nyou> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not msg:
                continue
            print("\nhomegrok> ", end="", flush=True)
            streamed = []

            def show(piece):
                streamed.append(piece)
                sys.stdout.write(piece)
                sys.stdout.flush()

            r = orch.answer(msg, on_text=show)
            if not streamed or "[[" in "".join(streamed):
                print(("\n" if streamed else "") + r["reply"])
            else:
                print()
            for action in r.get("actions", []):
                print(f"   [{action['type']} task: {action['title']}]")
            if r.get("note"):
                print(f"   ({r['note']})")
            for s in r["sources"][:3]:
                print(f"   source: {s['path']}")
    elif a.cmd == "tasks":
        from .tasks import Tasks
        tasks = Tasks(ws)
        if a.start:
            t = tasks.start(a.start[0], a.start[1])
            print(f"Started {t['title']} ({t['id']}); results go to {t['folder']}")
        if a.stop:
            for t in tasks.stop(a.stop):
                print(f"Stopped {t['title']}")
        for t in tasks.all():
            latest = t["log"][-1]["summary"] if t["log"] else "no steps yet"
            print(f"{t['id']}  [{t['status']}]  {t['title']}: {t['steps']} steps, {len(t['files'])} files\n"
                  f"          {latest}\n          {t['folder']}")
    elif a.cmd == "status":
        from .evolve import load_state
        from .storage import read_registry
        cfg = ws.load_config()
        print(f"workspace : {ws.root}")
        print(f"folders   : {', '.join(cfg['folders']) or '(none — run ./hg setup)'}")
        for label, path in (("raw docs", ws.raw_docs), ("clean docs", ws.clean_docs)):
            n = sum(1 for _ in open(path)) if path.exists() else 0
            print(f"{label:<10}: {n}")
        print(f"tokenizer : {'yes' if ws.tokenizer.exists() else 'no'}")
        print(f"index     : {'yes' if ws.index.exists() else 'no'}")
        reg = read_registry(ws)
        if reg["current"]:
            info = reg["models"][reg["current"]]
            print(f"live model: {reg['current']}  {info['params'] / 1e6:.2f}M params  "
                  f"val loss {info['metrics']['val_loss']:.3f}")
        else:
            print("live model: none")
        st = load_state(ws)
        if st and st["history"]:
            print(f"evolution : generation {st['generation']}, best {st['history'][-1]['best']:.3f}")
            print(json.dumps(st["history"][-1]["genome"]))


if __name__ == "__main__":
    main()
