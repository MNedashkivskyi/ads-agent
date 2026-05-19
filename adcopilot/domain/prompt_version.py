from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import NewType

PromptVersionId = NewType("PromptVersionId", int)


@dataclass(frozen=True)
class PromptVersion:
    id: PromptVersionId
    prompt_key: str
    version: int
    content: str
    created_at: datetime
