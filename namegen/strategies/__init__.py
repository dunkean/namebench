"""Generation strategy protocol and registry."""

from __future__ import annotations

from typing import Optional, Protocol


class Strategy(Protocol):
    """Protocol for name generation strategies."""

    def generate(
        self,
        name_type: str,
        count: int,
        gender: Optional[str] = None,
    ) -> list[str]: ...
