"""Consensus core + privval double-sign protection."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from clearmesh.consensus.core import ConsensusState, Event, EventKind, Step, handle
from clearmesh.consensus.privval import DoubleSignError, PrivValidator
from clearmesh.crypto.hashing import h
from clearmesh.crypto.keys import Ed25519Signer, verify
from sim.harness import mutation_locking_disabled_finds_fork, run_scenario


def test_domain_separation_vote_vs_tx() -> None:
    data = b"same-payload"
    assert h("CLEARMESH/VOTE/v1", data) != h("CLEARMESH/TX/v1", data)


def test_privval_refuses_double_sign() -> None:
    with tempfile.TemporaryDirectory() as td:
        sk = Ed25519Signer()
        pv = PrivValidator(Path(td) / "priv.json", sk)
        sig1 = pv.sign_vote(1, 0, "PREVOTE", b"\x01" * 32, b"msg1")
        sig2 = pv.sign_vote(1, 0, "PREVOTE", b"\x01" * 32, b"msg1")
        assert sig1 == sig2
        with pytest.raises(DoubleSignError):
            pv.sign_vote(1, 0, "PREVOTE", b"\x02" * 32, b"msg2")


def test_start_round_schedules_timeout_for_non_proposer() -> None:
    cs = ConsensusState(
        h=1,
        r=0,
        step=Step.PROPOSE,
        locked_value=None,
        locked_round=-1,
        valid_value=None,
        valid_round=-1,
        total_power=4,
        self_index=2,  # proposer for (h=1,r=0) is (1+0)%4=1, so index 2 is non-proposer
    )
    cs2, acts = handle(cs, Event(kind=EventKind.START, height=1, round=0))
    assert cs2.step == Step.PROPOSE
    assert any(a.kind.name == "SCHEDULE_TIMEOUT" for a in acts)


def test_sim_scenario_honest() -> None:
    assert run_scenario("sim/scenarios/byzantine_equivocate.toml", seed=42, heights=20)


def test_mutation_helper() -> None:
    assert mutation_locking_disabled_finds_fork()
