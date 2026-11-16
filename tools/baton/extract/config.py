"""Spring configuration values from application*.yml/properties, and `${...}` placeholder expansion.

A value counts only when it is what Spring would use with no profile active: the base files. Values that exist
only in a profile file, or that a profile overrides, are recorded so they can be asked about, never picked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from baton import miniyaml

_FILE = re.compile(r"^application(?:-(?P<profile>[\w.-]+))?\.(?:yml|yaml|properties)$")


def _canon(key: str) -> str:
    """Spring's relaxed binding: `a.fooBar`, `a.foo-bar` and `a.foo_bar` are one property."""
    return re.sub(r"[-_]", "", key).lower()


def _flatten(value, prefix: str, out: dict[str, str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _flatten(item, f"{prefix}.{key}" if prefix else str(key), out)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _flatten(item, f"{prefix}[{index}]", out)
    elif value is not None:
        out[prefix] = str(value).lower() if isinstance(value, bool) else str(value)


def _read_properties(text: str) -> dict[str, str]:
    out = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#!":
            continue
        match = re.match(r"([^=:\s]+)\s*[=:]\s*(.*)$", line)
        if match is None:
            raise ValueError(f"not a property: {line}")
        out[match.group(1)] = match.group(2).strip()
    return out


def _read_yaml(text: str) -> list[dict[str, str]]:
    documents = []
    for chunk in re.split(r"(?m)^---\s*$", text):
        if not chunk.strip():
            continue
        loaded = miniyaml.loads(chunk)
        if loaded is None:
            continue
        if not isinstance(loaded, dict):
            raise ValueError("top level is not a mapping")
        flat: dict[str, str] = {}
        _flatten(loaded, "", flat)
        documents.append(flat)
    return documents


@dataclass
class Config:
    base: dict[str, str] = field(default_factory=dict)  # canonical key -> value
    profiles: dict[str, dict[str, str]] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)  # repo-relative file -> reason
    files: list[str] = field(default_factory=list)
    keys: set[str] = field(default_factory=set)
    # canonical key -> what a profile says, for properties a target actually used
    used_overrides: dict[str, dict[str, str]] = field(default_factory=dict)
    used_only_in_profile: dict[str, dict[str, str]] = field(default_factory=dict)

    def add(self, flat: dict[str, str], profile: str | None) -> None:
        target = self.base if profile is None else self.profiles.setdefault(profile, {})
        for key, value in flat.items():
            target[_canon(key)] = value
            self.keys.add(key)

    def lookup(self, key: str) -> str | None:
        canon = _canon(key)
        others = {p: vals[canon] for p, vals in sorted(self.profiles.items()) if canon in vals}
        base = self.base.get(canon)
        if base is None:
            if others:
                self.used_only_in_profile[key] = others
            return None
        differing = {p: v for p, v in others.items() if v != base}
        if differing:
            self.used_overrides[key] = {"base": base, **differing}
        return base

    def expand(self, text: str, seen: frozenset[str] = frozenset()) -> tuple[str, bool]:
        """(text with placeholders replaced, whether all resolved). What cannot resolve stays literal."""
        out, ok, i = [], True, 0
        while i < len(text):
            start = text.find("${", i)
            if start < 0:
                out.append(text[i:])
                break
            out.append(text[i:start])
            end = _closing(text, start)
            if end < 0:
                out.append(text[start:])
                ok = False
                break
            literal = text[start : end + 1]
            value, good = self._placeholder(text[start + 2 : end], literal, seen)
            out.append(value)
            ok = ok and good
            i = end + 1
        return "".join(out), ok

    def _placeholder(self, body: str, literal: str, seen: frozenset[str]) -> tuple[str, bool]:
        key, sep, default = body.partition(":")
        if (
            self.errors or key in seen
        ):  # an unreadable config file may hold the real value: a default is a guess
            return literal, False
        value = self.lookup(key)
        if value is not None:
            expanded, ok = self.expand(value, seen | {key})
            return (expanded, True) if ok else (literal, False)
        if sep:
            expanded, ok = self.expand(default, seen | {key})
            return (expanded, True) if ok else (literal, False)
        return literal, False


def _closing(text: str, start: int) -> int:
    depth, i = 0, start
    while i < len(text):
        if text.startswith("${", i):
            depth += 1
            i += 2
            continue
        if text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def load_config(repo_root: Path, module: str) -> Config:
    config = Config()
    resources = repo_root / module / "src" / "main" / "resources"
    if not resources.is_dir():
        return config
    paths = [
        p
        for base in (resources, resources / "config")
        if base.is_dir()
        for p in sorted(base.iterdir())
        if p.is_file() and _FILE.match(p.name)
    ]
    # In one location Spring lets .properties win over .yml; loading them last gives that.
    paths.sort(key=lambda p: (p.parent != resources, p.suffix == ".properties", p.name))
    for path in paths:
        rel = path.relative_to(repo_root).as_posix()
        config.files.append(rel)
        file_profile = _FILE.match(path.name).group("profile")
        try:
            text = path.read_text(encoding="utf-8")
            if path.suffix == ".properties":
                config.add(_read_properties(text), file_profile)
                continue
            for flat in _read_yaml(text):
                doc_profile = flat.get("spring.config.activate.on-profile") or flat.get("spring.profiles")
                config.add(flat, doc_profile or file_profile)
        except (ValueError, UnicodeDecodeError, IndexError) as exc:
            config.errors[rel] = str(exc)
    return config
