"""Byzantine strategies: equivocate, conflicting proposals, silence, stale replay."""

from __future__ import annotations

from enum import Enum, auto


class Strategy(Enum):
    HONEST = auto()
    SILENCE = auto()
    EQUIVOCATE = auto()
    CONFLICTING_PROPOSALS = auto()
    STALE_REPLAY = auto()


def should_drop_outbound(strategy: Strategy) -> bool:
    return strategy == Strategy.SILENCE


def should_equivocate(strategy: Strategy) -> bool:
    return strategy == Strategy.EQUIVOCATE


def should_double_propose(strategy: Strategy) -> bool:
    return strategy == Strategy.CONFLICTING_PROPOSALS
