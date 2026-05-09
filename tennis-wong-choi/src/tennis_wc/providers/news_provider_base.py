from __future__ import annotations

from abc import abstractmethod

from .base import BaseProvider


class NewsProvider(BaseProvider):
    @abstractmethod
    def fetch_player_news(self, player_name: str, since_date: str | None = None) -> list[dict]:
        raise NotImplementedError
