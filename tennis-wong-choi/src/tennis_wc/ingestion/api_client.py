from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ApiResult:
    endpoint: str
    params: dict[str, Any]
    status_code: int
    body: dict | list
