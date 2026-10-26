"""PURE Tendermint-style state machine: handle(cs, ev) -> (cs, actions).

Branches commented with line numbers from Buchman, Kwon, Milosevic (2018).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum, auto
from typing import Any


class Step(Enum):
    PROPOSE = auto()
    PREVOTE = auto()
    PRECOMMIT = auto()


@dataclass(frozen=True, slots=True)
class ConsensusState:
    h: int
    r: int
    step: Step
    locked_value: bytes | None  # block hash
    locked_round: int
    valid_value: bytes | None
    valid_round: int
    # votes: map round -> type -> list of (validator_index, block_hash|None)
    votes: dict[int, dict[str, list[tuple[int, bytes | None]]]] = field(default_factory=dict)
    proposals: dict[int, Any] = field(default_factory=dict)
    validated: frozenset[bytes] = field(default_factory=frozenset)
    total_power: int = 4
    proposer_index: int = 0
    self_index: int = 0
    decided: bytes | None = None


class EventKind(Enum):
    START = auto()
    PROPOSAL_RECEIVED = auto()
    PROPOSAL_VALIDATED = auto()
    VOTE_RECEIVED = auto()
    TIMEOUT = auto()
    BLOCK_FETCHED = auto()


@dataclass(frozen=True, slots=True)
class Event:
    kind: EventKind
    height: int = 0
    round: int = 0
    step: str = ""
    block_hash: bytes | None = None
    ok: bool = False
    proposal: Any = None
    vote: Any = None
    pol_round: int = -1
    validator_index: int = 0
    vote_type: str = ""
    block: Any = None


class ActionKind(Enum):
    BROADCAST = auto()
    SIGN_AND_BROADCAST = auto()
    VALIDATE = auto()
    SCHEDULE_TIMEOUT = auto()
    COMMIT = auto()
    FETCH_BLOCK = auto()
    EMIT_EVIDENCE = auto()
    START_ROUND = auto()


@dataclass(frozen=True, slots=True)
class Action:
    kind: ActionKind
    payload: Any = None


def quorum(total: int) -> int:
    return total * 2 // 3 + 1


def skip_power(total: int) -> int:
    return total // 3 + 1


def timeout_propose(r: int) -> int:
    return 1000 + 500 * r


def timeout_prevote(r: int) -> int:
    return 500 + 250 * r


def timeout_precommit(r: int) -> int:
    return 500 + 250 * r


def _power_for(cs: ConsensusState, r: int, vtype: str, bh: bytes | None) -> int:
    votes = cs.votes.get(r, {}).get(vtype, [])
    # one vote per validator
    seen: dict[int, bytes | None] = {}
    for idx, hsh in votes:
        seen[idx] = hsh
    return sum(1 for hsh in seen.values() if hsh == bh)


def _any_power(cs: ConsensusState, r: int, vtype: str) -> int:
    votes = cs.votes.get(r, {}).get(vtype, [])
    return len({idx for idx, _ in votes})


def _add_vote(
    cs: ConsensusState, r: int, vtype: str, idx: int, bh: bytes | None
) -> tuple[ConsensusState, Any | None]:
    votes = {rr: {tt: list(vv) for tt, vv in m.items()} for rr, m in cs.votes.items()}
    bucket = votes.setdefault(r, {}).setdefault(vtype, [])
    evidence = None
    for i, (vi, vh) in enumerate(bucket):
        if vi == idx:
            if vh != bh:
                evidence = (idx, r, vtype, vh, bh)
            return cs, evidence
    bucket.append((idx, bh))
    return replace(cs, votes=votes), None


def handle(cs: ConsensusState, ev: Event) -> tuple[ConsensusState, list[Action]]:
    actions: list[Action] = []

    # Line 11: upon StartRound(round)
    if ev.kind == EventKind.START:
        return _start_round(cs, ev.round if ev.round else 0)

    # Skip-ahead: f+1 messages from higher round (paper L49)
    if ev.kind == EventKind.VOTE_RECEIVED and ev.height == cs.h and ev.round > cs.r:
        cs2, evid = _add_vote(cs, ev.round, ev.vote_type, ev.validator_index, ev.block_hash)
        if evid:
            actions.append(Action(ActionKind.EMIT_EVIDENCE, evid))
        if _any_power(cs2, ev.round, ev.vote_type) >= skip_power(cs2.total_power):
            cs3, acts = _start_round(cs2, ev.round)
            return cs3, actions + acts
        return cs2, actions

    if ev.height != cs.h and ev.kind != EventKind.BLOCK_FETCHED:
        return cs, actions

    # Vote received at current round
    if ev.kind == EventKind.VOTE_RECEIVED and ev.round == cs.r:
        cs, evid = _add_vote(cs, ev.round, ev.vote_type, ev.validator_index, ev.block_hash)
        if evid:
            actions.append(Action(ActionKind.EMIT_EVIDENCE, evid))
        actions.extend(_check_vote_rules(cs))
        # Re-read — _check_vote_rules returns actions but may need state updates
        cs2, acts2 = _apply_vote_rules(cs)
        return cs2, actions + acts2

    # Proposal received (paper L22–L36)
    if ev.kind == EventKind.PROPOSAL_RECEIVED and ev.round == cs.r and cs.step == Step.PROPOSE:
        props = dict(cs.proposals)
        props[ev.round] = ev.proposal
        cs = replace(cs, proposals=props)
        actions.append(Action(ActionKind.VALIDATE, ev.proposal))
        return cs, actions

    if ev.kind == EventKind.PROPOSAL_VALIDATED and ev.round == cs.r:
        validated = cs.validated
        if ev.ok and ev.block_hash is not None:
            validated = cs.validated | frozenset([ev.block_hash])
        cs = replace(cs, validated=validated)
        if cs.step != Step.PROPOSE:
            return cs, actions
        prop = cs.proposals.get(cs.r)
        pol = ev.pol_round
        bh = ev.block_hash if ev.ok else None
        # L22: proposal with pol_round == -1
        if pol == -1:
            if (
                ev.ok
                and bh is not None
                and (cs.locked_round == -1 or cs.locked_value == bh)
            ):
                vote_hash = bh
            else:
                vote_hash = None
            actions.append(
                Action(
                    ActionKind.SIGN_AND_BROADCAST,
                    {"type": "PREVOTE", "hash": vote_hash, "h": cs.h, "r": cs.r},
                )
            )
            return replace(cs, step=Step.PREVOTE), actions
        # L28: proposal with pol_round = vr
        if 0 <= pol < cs.r:
            if (
                ev.ok
                and bh is not None
                and _power_for(cs, pol, "PREVOTE", bh) >= quorum(cs.total_power)
                and (cs.locked_round <= pol or cs.locked_value == bh)
            ):
                vote_hash = bh
            else:
                vote_hash = None
            actions.append(
                Action(
                    ActionKind.SIGN_AND_BROADCAST,
                    {"type": "PREVOTE", "hash": vote_hash, "h": cs.h, "r": cs.r},
                )
            )
            return replace(cs, step=Step.PREVOTE), actions
        return cs, actions

    # Timeouts (paper L47–L48 area)
    if ev.kind == EventKind.TIMEOUT and ev.height == cs.h and ev.round == cs.r:
        if ev.step == "PROPOSE" and cs.step == Step.PROPOSE:
            actions.append(
                Action(
                    ActionKind.SIGN_AND_BROADCAST,
                    {"type": "PREVOTE", "hash": None, "h": cs.h, "r": cs.r},
                )
            )
            return replace(cs, step=Step.PREVOTE), actions
        if ev.step == "PREVOTE" and cs.step == Step.PREVOTE:
            actions.append(
                Action(
                    ActionKind.SIGN_AND_BROADCAST,
                    {"type": "PRECOMMIT", "hash": None, "h": cs.h, "r": cs.r},
                )
            )
            return replace(cs, step=Step.PRECOMMIT), actions
        if ev.step == "PRECOMMIT":
            return _start_round(cs, cs.r + 1)

    if ev.kind == EventKind.BLOCK_FETCHED and ev.block_hash is not None:
        actions.append(Action(ActionKind.COMMIT, {"hash": ev.block_hash, "block": ev.block}))
        return cs, actions

    return cs, actions


def _start_round(cs: ConsensusState, r: int) -> tuple[ConsensusState, list[Action]]:
    # Line 11–20 StartRound
    proposer = (cs.h + r) % cs.total_power
    cs2 = replace(cs, r=r, step=Step.PROPOSE, proposer_index=proposer)
    actions: list[Action] = []
    if proposer == cs.self_index:
        actions.append(
            Action(
                ActionKind.SIGN_AND_BROADCAST,
                {
                    "type": "PROPOSAL",
                    "h": cs2.h,
                    "r": r,
                    "pol_round": cs2.valid_round if cs2.valid_value else -1,
                    "value": cs2.valid_value,
                },
            )
        )
    else:
        actions.append(
            Action(
                ActionKind.SCHEDULE_TIMEOUT,
                {"step": "PROPOSE", "h": cs2.h, "r": r, "ms": timeout_propose(r)},
            )
        )
    actions.append(Action(ActionKind.START_ROUND, r))
    return cs2, actions


def _check_vote_rules(cs: ConsensusState) -> list[Action]:
    return []


def _apply_vote_rules(cs: ConsensusState) -> tuple[ConsensusState, list[Action]]:
    """Rules 4–8 from the paper for current round."""
    actions: list[Action] = []
    q = quorum(cs.total_power)
    r = cs.r

    # L34: first time ≥q prevotes of any kind while PREVOTE → schedule timeout_prevote
    if cs.step == Step.PREVOTE and _any_power(cs, r, "PREVOTE") >= q:
        actions.append(
            Action(
                ActionKind.SCHEDULE_TIMEOUT,
                {"step": "PREVOTE", "h": cs.h, "r": r, "ms": timeout_prevote(r)},
            )
        )

    # L36: valid proposal + ≥q prevotes for it
    # Find hash with quorum prevotes
    for bh in _distinct_hashes(cs, r, "PREVOTE"):
        if bh is None:
            continue
        if _power_for(cs, r, "PREVOTE", bh) >= q and bh in cs.validated:
            if cs.step == Step.PREVOTE:
                cs = replace(cs, locked_value=bh, locked_round=r, step=Step.PRECOMMIT)
                actions.append(
                    Action(
                        ActionKind.SIGN_AND_BROADCAST,
                        {"type": "PRECOMMIT", "hash": bh, "h": cs.h, "r": r},
                    )
                )
            cs = replace(cs, valid_value=bh, valid_round=r)
            break

    # L44: ≥q prevotes for nil while PREVOTE
    if cs.step == Step.PREVOTE and _power_for(cs, r, "PREVOTE", None) >= q:
        actions.append(
            Action(
                ActionKind.SIGN_AND_BROADCAST,
                {"type": "PRECOMMIT", "hash": None, "h": cs.h, "r": r},
            )
        )
        cs = replace(cs, step=Step.PRECOMMIT)

    # L47: ≥q precommits of any kind → schedule timeout_precommit
    if _any_power(cs, r, "PRECOMMIT") >= q:
        actions.append(
            Action(
                ActionKind.SCHEDULE_TIMEOUT,
                {"step": "PRECOMMIT", "h": cs.h, "r": r, "ms": timeout_precommit(r)},
            )
        )

    # L49-ish: ≥q precommits for block B in any round
    for rr, m in cs.votes.items():
        for bh in _distinct_hashes(cs, rr, "PRECOMMIT"):
            if bh is not None and _power_for(cs, rr, "PRECOMMIT", bh) >= q:
                if bh in cs.validated:
                    actions.append(Action(ActionKind.COMMIT, {"hash": bh, "round": rr}))
                else:
                    actions.append(Action(ActionKind.FETCH_BLOCK, bh))
                return cs, actions

    return cs, actions


def _distinct_hashes(
    cs: ConsensusState, r: int, vtype: str
) -> list[bytes | None]:
    votes = cs.votes.get(r, {}).get(vtype, [])
    out: list[bytes | None] = []
    seen: set[bytes | None] = set()
    for _, hsh in votes:
        if hsh not in seen:
            seen.add(hsh)
            out.append(hsh)
    return out
