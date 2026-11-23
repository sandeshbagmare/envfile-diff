"""Diff two ``.env`` files by key, masking values by default.

    >>> from envfile_diff import diff_env, parse_env, render
    >>> render(diff_env(parse_env("A=1\\nB=2\\n"), parse_env("B=3\\nC=4\\n")))
    '- A=***\\n~ B=*** (changed)\\n+ C=***'

Environments drift: a key is added in staging and never in production, or a value
changes in a file nobody read. Printing the files side by side leaks secrets into
terminals and CI logs, so values are masked unless you ask for them.

Standard library only, Python 3.9+.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "Change",
    "EnvDiff",
    "EnvParseError",
    "diff_env",
    "diff_files",
    "parse_env",
    "render",
]

__version__ = "0.1.0"

_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]*$")
_UNQUOTED_COMMENT = re.compile(r"\s+#")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "'": "'", "$": "$"}


class EnvParseError(ValueError):
    """A line that is not a ``KEY=VALUE`` assignment or a comment."""

    def __init__(self, line: int, message: str) -> None:
        super().__init__(f"line {line}: {message}")
        self.line = line


def _unquote_double(value: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(value):
        character = value[index]
        if character == "\\" and index + 1 < len(value):
            following = value[index + 1]
            out.append(_ESCAPES.get(following, "\\" + following))
            index += 2
            continue
        out.append(character)
        index += 1
    return "".join(out)


def parse_env(text: str) -> dict[str, str]:
    """Parse a dotenv document into an ordered ``dict``.

    Supports comments, a leading ``export``, single and double quotes, escapes inside
    double quotes, empty values and trailing comments after an unquoted value. A
    repeated key keeps its last value, as a shell would.
    """
    values: dict[str, str] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            raise EnvParseError(number, f"expected KEY=VALUE, got {raw.strip()!r}")
        key, _, value = line.partition("=")
        key = key.strip()
        if not _KEY.match(key):
            raise EnvParseError(number, f"{key!r} is not a valid key")
        value = value.strip()
        if value[:1] in ('"', "'"):
            quote = value[0]
            end = value.rfind(quote)
            if end <= 0:
                raise EnvParseError(number, f"unterminated {quote} quote")
            inner = value[1:end]
            values[key] = _unquote_double(inner) if quote == '"' else inner
            continue
        comment = _UNQUOTED_COMMENT.search(value)
        if comment:
            value = value[: comment.start()]
        values[key] = value.strip()
    return values


@dataclass(frozen=True)
class Change:
    """One key that differs between the two files."""

    key: str
    old: str | None
    new: str | None

    @property
    def kind(self) -> str:
        if self.old is None:
            return "added"
        if self.new is None:
            return "removed"
        return "changed"


@dataclass
class EnvDiff:
    """The differences between two dotenv files."""

    added: dict[str, str] = field(default_factory=dict)
    removed: dict[str, str] = field(default_factory=dict)
    changed: dict[str, tuple[str, str]] = field(default_factory=dict)
    unchanged: dict[str, str] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed)

    def changes(self) -> list[Change]:
        """Every change, sorted by key."""
        found = [Change(key, None, value) for key, value in self.added.items()]
        found += [Change(key, value, None) for key, value in self.removed.items()]
        found += [Change(key, old, new) for key, (old, new) in self.changed.items()]
        return sorted(found, key=lambda change: change.key)

    def keys(self) -> list[str]:
        return [change.key for change in self.changes()]


def diff_env(old: Mapping[str, str], new: Mapping[str, str]) -> EnvDiff:
    """Compare two parsed dotenv documents."""
    added = {key: value for key, value in new.items() if key not in old}
    removed = {key: value for key, value in old.items() if key not in new}
    changed = {key: (old[key], new[key]) for key in old if key in new and old[key] != new[key]}
    unchanged = {key: value for key, value in new.items() if key in old and old[key] == value}
    return EnvDiff(added=added, removed=removed, changed=changed, unchanged=unchanged)


def render(
    diff: EnvDiff,
    *,
    show_values: bool = False,
    mask: str = "***",
    include_unchanged: bool = False,
) -> str:
    """Render a diff as ``+``/``-``/``~`` lines, values masked unless asked for."""
    lines: list[str] = []

    def value(text: str | None) -> str:
        if text is None:  # pragma: no cover - a change always carries the side it has
            return ""
        return text if show_values else mask

    for change in diff.changes():
        if change.kind == "added":
            lines.append(f"+ {change.key}={value(change.new)}")
        elif change.kind == "removed":
            lines.append(f"- {change.key}={value(change.old)}")
        elif show_values:
            lines.append(f"~ {change.key}={value(change.old)} -> {value(change.new)}")
        else:
            # both values are hidden, so say plainly that the value changed
            lines.append(f"~ {change.key}={mask} (changed)")
    if include_unchanged:
        lines.extend(f"= {key}={value(text)}" for key, text in sorted(diff.unchanged.items()))
    return "\n".join(lines)


def diff_files(
    old: str | Path,
    new: str | Path,
    *,
    encoding: str = "utf-8",
) -> EnvDiff:
    """Parse and compare two files."""
    return diff_env(
        parse_env(Path(old).read_text(encoding=encoding)),
        parse_env(Path(new).read_text(encoding=encoding)),
    )
