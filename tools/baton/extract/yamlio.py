"""A YAML writer for baton.miniyaml's subset. Output always round-trips: `dumps` refuses otherwise."""

from __future__ import annotations

from baton import miniyaml


def _scalar(value, flow: bool = False) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    text = str(value)
    plain_unsafe = (
        text != text.strip()
        or (flow and any(c in text for c in ",{}[]:'\""))
        or text.startswith(("- ", "? ", "*", "&", "!", "|", ">", "%", "@", "`", "[", "{", "#"))
    )
    if not plain_unsafe and _reads_back(text):
        return text
    for quote in ('"', "'"):
        candidate = f"{quote}{text}{quote}"
        if quote not in text and _reads_back(candidate, text):
            return candidate
    raise ValueError(f"cannot write this value in the YAML subset: {text!r}")


def _reads_back(rendered: str, expected: str | None = None) -> bool:
    expected = rendered if expected is None else expected
    if "\n" in rendered:
        return False
    try:
        document = miniyaml.loads(f"k: {rendered}\nl:\n  - {rendered}\nm: {{a: {rendered}}}\n")
    except ValueError:
        return False
    return document == {"k": expected, "l": [expected], "m": {"a": expected}} or (
        document.get("k") == expected and document.get("l") == [expected]
    )


def _flow(value) -> str:
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k}: {_scalar(v, flow=True)}" for k, v in value.items()) + "}"
    return "[" + ", ".join(_scalar(v, flow=True) for v in value) + "]"


def _is_flat(value) -> bool:
    if isinstance(value, dict):
        return all(not isinstance(v, dict | list) for v in value.values())
    return isinstance(value, list) and all(not isinstance(v, dict | list) for v in value)


def _flowable(value) -> bool:
    try:
        _flow(value)
    except ValueError:
        return False
    return True


def _short_flat(value) -> bool:
    try:
        return _is_flat(value) and len(_flow(value)) <= 80
    except ValueError:
        return False


def _emit(value, indent: int, lines: list[str]) -> None:
    pad = " " * indent
    if isinstance(value, dict):
        for key, item in value.items():
            _emit_entry(f"{pad}{key}:", item, indent, lines)
    else:
        for item in value:
            if isinstance(item, dict):
                entries = list(item.items())
                first_key, first_value = entries[0]
                _emit_entry(f"{pad}- {first_key}:", first_value, indent + 2, lines)
                for key, sub in entries[1:]:
                    _emit_entry(f"{pad}  {key}:", sub, indent + 2, lines)
            else:
                lines.append(f"{pad}- {_scalar(item)}")


def _emit_entry(prefix: str, value, indent: int, lines: list[str]) -> None:
    if isinstance(value, dict | list):
        if not value:
            lines.append(f"{prefix} {'{}' if isinstance(value, dict) else '[]'}")
        elif (prefix.endswith("provenance:") and _flowable(value)) or (
            isinstance(value, list) and _short_flat(value)
        ):
            lines.append(f"{prefix} {_flow(value)}")
        else:
            lines.append(prefix)
            _emit(value, indent + 2, lines)
    else:
        lines.append(f"{prefix} {_scalar(value)}")


def dumps(document: dict, header: str = "") -> str:
    lines: list[str] = [f"# {line}" for line in header.splitlines()]
    _emit(document, 0, lines)
    text = "\n".join(lines) + "\n"
    if miniyaml.loads(text) != document:
        raise ValueError("generated YAML does not read back as what was written")
    return text
