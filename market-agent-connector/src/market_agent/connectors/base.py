"""Base connector interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseConnector(ABC):
    name: str

    @abstractmethod
    async def health(self) -> dict[str, Any]:
        """Return connector status and auth state."""

    @abstractmethod
    async def close(self) -> None:
        """Release HTTP resources."""
