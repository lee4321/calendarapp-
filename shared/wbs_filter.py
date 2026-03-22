"""
WBS filtering utilities.

Filter syntax:
- Comma-separated tokens.
- "!" prefix excludes matches.
- Segments are separated by "." and compared case-insensitively.
- "*" matches any single segment.
- "**" matches zero or more segments.

If a token does not include "**", it is treated as a prefix match by
implicitly appending "**".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


def _normalize_segments(value: str) -> list[str]:
    return [seg.strip().upper() for seg in value.split(".") if seg.strip()]


def _compile_pattern(token: str) -> list[str]:
    segments = _normalize_segments(token)
    if not segments:
        return []
    if "**" not in segments:
        segments.append("**")
    return segments


def _match_pattern(pattern: list[str], wbs_segments: list[str]) -> bool:
    def rec(pi: int, wi: int) -> bool:
        while pi < len(pattern):
            token = pattern[pi]
            if token == "**":
                if pi == len(pattern) - 1:
                    return True
                for skip in range(wi, len(wbs_segments) + 1):
                    if rec(pi + 1, skip):
                        return True
                return False
            if wi >= len(wbs_segments):
                return False
            if token != "*" and token != wbs_segments[wi]:
                return False
            pi += 1
            wi += 1
        return wi == len(wbs_segments)

    return rec(0, 0)


@dataclass(frozen=True)
class WBSFilter:
    include: list[list[str]]
    exclude: list[list[str]]

    @classmethod
    def parse(cls, value: str | None) -> "WBSFilter | None":
        if not value:
            return None

        include: list[list[str]] = []
        exclude: list[list[str]] = []
        tokens = [t.strip() for t in value.split(",") if t.strip()]
        for token in tokens:
            is_exclude = token.startswith("!")
            raw = token[1:].strip() if is_exclude else token
            pattern = _compile_pattern(raw)
            if not pattern:
                continue
            if is_exclude:
                exclude.append(pattern)
            else:
                include.append(pattern)

        if not include and not exclude:
            return None

        return cls(include=include, exclude=exclude)

    def matches(self, wbs: str | None) -> bool:
        if not wbs:
            return True

        segments = _normalize_segments(wbs)
        if not segments:
            return True

        for pattern in self.exclude:
            if _match_pattern(pattern, segments):
                return False

        if self.include:
            return any(_match_pattern(pattern, segments) for pattern in self.include)

        return True


def filter_events(
    events: Iterable[dict],
    filter_value: str | None,
    field: str = "WBS",
) -> list[dict]:
    compiled = WBSFilter.parse(filter_value)
    if not compiled:
        return list(events)
    return [e for e in events if compiled.matches(e.get(field))]
