from __future__ import annotations

from abc import ABC, abstractmethod


class BaseProvider(ABC):
    provider_name: str

    @abstractmethod
    def healthcheck(self) -> bool:
        raise NotImplementedError
