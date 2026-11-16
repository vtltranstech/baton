"""The change spec: what a story adds or changes, in a few lines the architect writes instead of diagrams.

`docs/design/<feature>/<story>-change.yaml` (YAML subset per baton/miniyaml.py):

    story: S-010
    title: Apply a loyalty discount to orders
    changed:
      - OrderService#place               # a method (Class#method; the class by simple name or FQCN)
      - OrderDoc.total                    # a field
      - collection:orders                 # a resource whose shape or meaning changes
    new:
      - class: com.example.orders.application.service.LoyaltyDiscountPolicy
        stereotype: service               # controller | service | component | repository | adapter |
                                          # client | ...
        implements: [DiscountPolicyPort]
        uses: [OrderHistoryPort]          # injected collaborators
      - method: LoyaltyDiscountPolicy#discountFor
        signature: "discountFor(String customerRef, BigDecimal total): BigDecimal"
        calledFrom: OrderService#place    # where the new call goes ...
        before: PriceCalculator#calculateTotal  # ... and before which existing call (optional)
        calls: [OrderHistoryPort#countForCustomer]
        reads: [collection:loyalty_tiers] # reads | writes | publishes | consumes | exposes | callsEndpoint
      - field: OrderDoc.discount
        type: BigDecimal
    removed:
      - OrderSummary.legacyTotal          # breaking for every reader: the impact walk carries it
    useCases:                             # optional; derived from the entry points otherwise
      - name: Place an order
        actor: Customer
        entry: "endpoint:POST /api/v1/orders"
        includes: [Apply loyalty discount]

Every name is checked against the code map: an existing element must exist, a new one must not.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path

from baton import miniyaml
from baton.graph.model import NODE_KINDS, node_prefix

RESOURCE_PREFIXES = ("collection", "topic", "queue", "endpoint", "file", "job")
USE_KEYS = {
    "reads": "READS_COLLECTION",
    "writes": "WRITES_COLLECTION",
    "publishes": "PUBLISHES",
    "consumes": "CONSUMES",
    "exposes": "EXPOSES",
    "callsEndpoint": "CALLS_ENDPOINT",
    "readsFile": "READS_FILE",
    "writesFile": "WRITES_FILE",
}
_NEW_KEYS = {
    "class": {"class", "repo", "stereotype", "implements", "extends", "uses", "fields", "why"},
    "method": {"method", "signature", "calledFrom", "before", "calls", "why", *USE_KEYS},
    "field": {"field", "type", "why"},
}
_SIGNATURE = re.compile(r"^\s*(\w+)\s*\((.*)\)\s*(?::\s*(.+?))?\s*$")


class SpecError(Exception):
    """Exit 1: the spec names something the code does not have, or is not a spec."""

    def __init__(self, problems: list[str]):
        super().__init__("\n".join(problems))
        self.problems = problems


@dataclass
class Ref:
    """A name in the spec, as written, and what kind of thing it names."""

    text: str
    kind: str  # method | field | class | resource
    owner: str = ""  # class part as written
    member: str = ""


@dataclass
class NewClass:
    name: str  # as written: FQCN or simple
    repo: str = ""
    stereotype: str = "component"
    implements: list[str] = field(default_factory=list)
    extends: list[str] = field(default_factory=list)
    uses: list[str] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)


@dataclass
class NewMethod:
    ref: Ref
    name: str
    params: list[str] = field(default_factory=list)
    returns: str = ""
    called_from: list[Ref] = field(default_factory=list)
    before: Ref | None = None
    calls: list[Ref] = field(default_factory=list)
    uses: list[tuple[str, str]] = field(default_factory=list)  # (edge kind, resource id)


@dataclass
class NewField:
    ref: Ref
    type: str = ""


@dataclass
class ChangedMethod:
    ref: Ref
    calls: list[Ref] = field(default_factory=list)
    uses: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class UseCaseSpec:
    name: str
    actor: str = ""
    entry: str = ""
    includes: list[str] = field(default_factory=list)


@dataclass
class Spec:
    story: str
    title: str = ""
    path: str = ""
    repo: str = ""
    entries: list[str] = field(default_factory=list)
    changed: list[Ref] = field(default_factory=list)
    changed_methods: list[ChangedMethod] = field(default_factory=list)
    new_classes: list[NewClass] = field(default_factory=list)
    new_methods: list[NewMethod] = field(default_factory=list)
    new_fields: list[NewField] = field(default_factory=list)
    removed: list[Ref] = field(default_factory=list)
    use_cases: list[UseCaseSpec] = field(default_factory=list)


def parse_ref(text: str) -> Ref:
    text = str(text).strip()
    if node_prefix(text) in NODE_KINDS or node_prefix(text) in RESOURCE_PREFIXES:
        return Ref(text, "resource")
    if "#" in text:
        owner, _, member = text.partition("#")
        return Ref(text, "method", owner.strip(), member.strip().rstrip("()"))
    head, _, tail = text.rpartition(".")
    if head and tail[:1].islower():
        return Ref(text, "field", head, tail)
    return Ref(text, "class", text)


def parse_signature(text: str, fallback: str) -> tuple[str, list[str], str]:
    match = _SIGNATURE.match(text or "")
    if not match:
        return fallback, [], ""
    params = [p.strip() for p in _split_params(match.group(2)) if p.strip()]
    return match.group(1), params, (match.group(3) or "").strip()


def _split_params(text: str) -> list[str]:
    out, depth, current = [], 0, ""
    for ch in text:
        if ch in "<([":
            depth += 1
        elif ch in ">)]":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(current)
            current = ""
        else:
            current += ch
    out.append(current)
    return out


def _listify(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _uses(item: dict, problems: list[str], where: str) -> list[tuple[str, str]]:
    out = []
    for key, kind in USE_KEYS.items():
        for resource in _listify(item.get(key)):
            resource = str(resource)
            if node_prefix(resource) not in RESOURCE_PREFIXES:
                problems.append(
                    f"{where}: {key} needs node ids such as collection:<name>, topic:<name>, "
                    f"endpoint:<METHOD> <path>; got {resource!r}"
                )
                continue
            out.append((kind, resource))
    return out


def load(path: Path) -> Spec:
    try:
        data = miniyaml.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SpecError([f"{path}: {exc}"]) from exc
    if not isinstance(data, dict) or not data.get("story"):
        raise SpecError([f"{path}: not a change spec (needs a `story:` line)"])
    problems: list[str] = []
    known = {"story", "title", "repo", "entries", "changed", "new", "removed", "useCases"}
    for key in sorted(set(data) - known):
        problems.append(f"{path.name}: unknown key {key!r}; expected one of {', '.join(sorted(known))}")
    spec = Spec(str(data["story"]), str(data.get("title") or ""), str(path), str(data.get("repo") or ""))
    spec.entries = [str(e) for e in _listify(data.get("entries"))]
    for item in _listify(data.get("changed")):
        if isinstance(item, dict):
            text = item.get("method") or item.get("class") or item.get("field") or item.get("resource")
            if not text:
                problems.append(f"changed: an item needs method:, class:, field: or resource: ({item})")
                continue
            ref = parse_ref(str(text))
            spec.changed.append(ref)
            if ref.kind == "method":
                spec.changed_methods.append(
                    ChangedMethod(
                        ref,
                        [parse_ref(c) for c in _listify(item.get("calls"))],
                        _uses(item, problems, f"changed {text}"),
                    )
                )
        else:
            spec.changed.append(parse_ref(str(item)))
    for item in _listify(data.get("new")):
        if not isinstance(item, dict):
            problems.append(
                f"new: {item!r} needs a kind: `- class: ...`, `- method: Class#name` or `- field: Class.name`"
            )
            continue
        kinds = [k for k in ("class", "method", "field") if k in item]
        if len(kinds) != 1:
            problems.append(f"new: each item is exactly one of class:, method:, field: ({item})")
            continue
        kind = kinds[0]
        for key in sorted(set(item) - _NEW_KEYS[kind]):
            problems.append(f"new {kind} {item[kind]}: unknown key {key!r}")
        if kind == "class":
            spec.new_classes.append(
                NewClass(
                    str(item["class"]),
                    str(item.get("repo") or ""),
                    str(item.get("stereotype") or "component"),
                    [str(x) for x in _listify(item.get("implements"))],
                    [str(x) for x in _listify(item.get("extends"))],
                    [str(x) for x in _listify(item.get("uses"))],
                    [str(x) for x in _listify(item.get("fields"))],
                )
            )
        elif kind == "method":
            ref = parse_ref(str(item["method"]))
            if ref.kind != "method":
                problems.append(f"new method {item['method']}: write it as Class#method")
                continue
            name, params, returns = parse_signature(str(item.get("signature") or ""), ref.member)
            if item.get("signature") and name != ref.member:
                problems.append(f"new method {ref.text}: signature names {name}, not {ref.member}")
            before = item.get("before")
            spec.new_methods.append(
                NewMethod(
                    ref,
                    ref.member,
                    params,
                    returns,
                    [parse_ref(x) for x in _listify(item.get("calledFrom"))],
                    parse_ref(str(before)) if before else None,
                    [parse_ref(x) for x in _listify(item.get("calls"))],
                    _uses(item, problems, f"new method {ref.text}"),
                )
            )
        else:
            ref = parse_ref(str(item["field"]))
            if ref.kind != "field":
                problems.append(f"new field {item['field']}: write it as Class.field")
                continue
            spec.new_fields.append(NewField(ref, str(item.get("type") or "")))
    spec.removed = [parse_ref(str(x)) for x in _listify(data.get("removed"))]
    for item in _listify(data.get("useCases")):
        if not isinstance(item, dict) or not item.get("name"):
            problems.append(f"useCases: each item needs name: ({item})")
            continue
        spec.use_cases.append(
            UseCaseSpec(
                str(item["name"]),
                str(item.get("actor") or ""),
                str(item.get("entry") or ""),
                [str(x) for x in _listify(item.get("includes"))],
            )
        )
    if problems:
        raise SpecError(problems)
    return spec


def suggest(name: str, candidates) -> str:
    close = difflib.get_close_matches(name, sorted(set(candidates)), n=3, cutoff=0.6)
    return f"; did you mean {' or '.join(close)}?" if close else ""
