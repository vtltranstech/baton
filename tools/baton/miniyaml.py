"""A deliberately small YAML subset reader (stdlib only) for baton profile files.

Supports: nested maps by indentation, scalars (str/int/float/bool/null), lists of scalars
(`- item`) and lists of flat maps (`- key: value` + indented `key: value` lines), comments, and
single-line flow collections (`[a, "b"]`, `{file: a.java, line: 14}`), which the contracts use.
It does NOT support anchors or multi-line strings. A key needs `: ` or a trailing `:`, so
`class:com.x.A` is a scalar.
Profile files are written to this subset on purpose: a human must be able to read them.
"""
from __future__ import annotations

import re
from typing import Any

_SCALAR_INT = re.compile(r"^-?\d+$")
_SCALAR_FLOAT = re.compile(r"^-?\d+\.\d+$")
_KEY = re.compile(r"^([^\s:\[{][^:]*?)\s*:(?:\s+(.*))?$")


def _split_flow(body: str) -> list[str]:
    parts, current, depth, quote = [], [], 0, None
    for ch in body:
        if quote:
            quote = None if ch == quote else quote
        elif ch in ("'", '"'):
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(ch)
    if "".join(current).strip():
        parts.append("".join(current))
    return parts


def _key_split(text: str) -> tuple[str, str] | None:
    """Split `key: value` / `key:` outside quotes; None when the text is a plain scalar."""
    if text.startswith(("'", '"')):
        close = text.find(text[0], 1)
        rest = text[close + 1 :].lstrip() if close > 0 else ""
        if rest == ":" or rest.startswith(": "):
            return text[1:close], rest[1:].strip()
        return None
    match = _KEY.match(text)
    return (match.group(1).strip(), (match.group(2) or "").strip()) if match else None


def _scalar(raw: str) -> Any:
    s = raw.strip()
    if s == "" or s in ("null", "~"):
        return None
    if s.startswith("[") and s.endswith("]"):
        return [_scalar(part) for part in _split_flow(s[1:-1])]
    if s.startswith("{") and s.endswith("}"):
        result = {}
        for part in _split_flow(s[1:-1]):
            pair = _key_split(part.strip())
            if pair is None:
                raise ValueError(f"flow map entry without a key: {part.strip()}")
            result[pair[0]] = _scalar(pair[1])
        return result
    if s.lower() in ("true", "yes"):
        return True
    if s.lower() in ("false", "no"):
        return False
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    if _SCALAR_INT.match(s):
        return int(s)
    if _SCALAR_FLOAT.match(s):
        return float(s)
    return s


def _strip_comment(line: str) -> str:
    out, quote = [], None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


def loads(text: str) -> Any:
    lines = []
    for raw in text.splitlines():
        line = _strip_comment(raw)
        if line.strip() == "":
            continue
        indent = len(line) - len(line.lstrip(" "))
        lines.append((indent, line.strip()))
    value, _ = _parse_block(lines, 0, 0)
    return value


def _parse_block(lines, i, indent):
    if i >= len(lines):
        return None, i
    if lines[i][1].startswith("- ") or lines[i][1] == "-":
        return _parse_list(lines, i, lines[i][0])
    return _parse_map(lines, i, lines[i][0])


def _parse_map(lines, i, indent):
    result: dict = {}
    while i < len(lines):
        ind, text = lines[i]
        if ind < indent:
            break
        if ind > indent:
            raise ValueError(f"unexpected indent at line: {text}")
        if text.startswith("- "):
            break
        pair = _key_split(text)
        if pair is None:
            raise ValueError(f"expected `key: value` at line: {text}")
        key, rest = pair
        if rest == "":
            # nested block or empty
            if i + 1 < len(lines) and lines[i + 1][0] > ind:
                value, i = _parse_block(lines, i + 1, lines[i + 1][0])
            else:
                value, i = None, i + 1
        else:
            value, i = _scalar(rest), i + 1
        result[key] = value
    return result, i


def _parse_list(lines, i, indent):
    result: list = []
    while i < len(lines):
        ind, text = lines[i]
        if ind < indent or not text.startswith("- "):
            break
        item = text[2:].strip()
        pair = None if item.startswith(("[", "{")) else _key_split(item)
        if pair is not None:
            # list of maps: first key on the dash line, more keys indented below
            entry = {pair[0]: _scalar(pair[1])}
            i += 1
            while i < len(lines) and lines[i][0] > ind and not lines[i][1].startswith("- "):
                inner = _key_split(lines[i][1])
                if inner is None:
                    raise ValueError(f"expected `key: value` at line: {lines[i][1]}")
                k, r = inner
                if r == "" and i + 1 < len(lines) and lines[i + 1][0] > lines[i][0]:
                    v, i = _parse_block(lines, i + 1, lines[i + 1][0])
                    entry[k] = v
                else:
                    entry[k] = _scalar(r)
                    i += 1
            result.append(entry)
        else:
            result.append(_scalar(item))
            i += 1
    return result, i


def load_file(path: str) -> Any:
    with open(path, encoding="utf-8") as fh:
        return loads(fh.read())
