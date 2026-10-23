"""Source plugin interface and registry."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from ..config import Settings
from ..fetch.http import HttpClient
from ..models import RawArticle

REGISTRY: dict[str, type["Source"]] = {}


def register(cls: type["Source"]) -> type["Source"]:
    REGISTRY[cls.name] = cls
    return cls


class Source(ABC):
    name: ClassVar[str]

    def __init__(self, http: HttpClient, settings: Settings):
        self.http = http
        self.settings = settings

    def is_configured(self) -> tuple[bool, str]:
        """Sources that need extra setup (API keys, contact headers) override this."""
        return True, ""

    @abstractmethod
    def fetch(self, tickers: list[str]) -> list[RawArticle]:
        """Fetch recent items. Per-ticker failures should be collected, not raised, so one bad ticker
        doesn't sink the whole source; raise only when the source as a whole is broken."""
