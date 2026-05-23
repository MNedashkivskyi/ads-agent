"""AdCopyProposal domain entity — LLM-generated RSA variant."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AdCopyProposal:
    headlines: list[str]  # 3 items, each ≤ 30 chars
    descriptions: list[str]  # 2 items, each ≤ 90 chars
    final_url: str = ""
