from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class TraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class TraceSink(Protocol):
    def record(self, event: TraceEvent) -> None: ...


class NullTraceSink:
    def record(self, event: TraceEvent) -> None:
        del event


class JsonlTraceSink:
    """Append sanitized runtime events durably without provider reasoning or raw prompts."""

    def __init__(self, path: Path) -> None:
        if path.exists():
            raise FileExistsError(f"trace path already exists: {path}")
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def record(self, event: TraceEvent) -> None:
        line = event.model_dump_json(exclude_none=True) + "\n"
        with self._path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
