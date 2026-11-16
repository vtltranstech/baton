"""Seeds a human confirms: aggregates (plan section 3 row 4) and risk zones (row 11). Never authoritative."""

from __future__ import annotations

import re

from baton.extract.model import JavaFile, TypeDecl
from baton.extract.resolve import TypeIndex

CAP = 50
_MONEY = re.compile(r"\b(BigDecimal|Decimal128)\b")
_AUTH = re.compile(
    r"\b(SecurityFilterChain|PreAuthorize|PostAuthorize|Secured|RolesAllowed|EnableWebSecurity)\b"
    r"|org \. springframework \. security"
)
_AUTH_PATH = re.compile(r"(^|/)(security|auth)(/|$)|Entitlement", re.I)
_MIGRATION = re.compile(r"\b(ChangeUnit|ChangeLog|ChangeSet|Flyway|Liquibase)\b")
_MIGRATION_DIRS = ("db/migration", "db/changelog", "liquibase", "mongock")
_SUFFIX = re.compile(r"(Document|Doc|Entity)$")
_ID_FIELD = re.compile(r"^(.+?)(Ids?|Refs?)$")
_REFERENCE_ANNOTATIONS = {"DBRef", "DocumentReference"}
ZONE_REASONS = {
    "money": "money fields (BigDecimal or Decimal128)",
    "outbound-file": "writes a file another system consumes",
    "auth": "authentication or entitlement code",
    "migration": "schema migrations",
}


def aggregate_name(decl: TypeDecl) -> str:
    return _SUFFIX.sub("", decl.name) or decl.name


def seed_aggregates(documents: list[tuple[TypeDecl, str]], index: TypeIndex) -> list[dict]:
    """One aggregate per @Document class. `references`: another document by @DBRef or an `<other>Id` or
    `<other>Ref` field. `members`: repo classes a document embeds. Unknown names give nothing."""
    names = {aggregate_name(decl).lower(): aggregate_name(decl) for decl, _ in documents}
    roots = {decl.fqcn for decl, _ in documents}
    out = []
    for decl, collection in documents:
        own = aggregate_name(decl)
        references, members = set(), set()
        for var in decl.fields:
            match = _ID_FIELD.match(var.name)
            if match and match.group(1).lower() in names and names[match.group(1).lower()] != own:
                references.add(names[match.group(1).lower()])
            for type_name in [var.type.name, *var.type.args]:
                target = index.find(type_name, decl)
                if target is None or target.fqcn == decl.fqcn:
                    continue
                if target.fqcn in roots:
                    if any(a.name in _REFERENCE_ANNOTATIONS for a in var.annotations):
                        references.add(aggregate_name(target))
                elif target.kind in ("class", "record"):
                    members.add(f"class:{target.fqcn}")
        out.append(
            {
                "name": own,
                "root": f"class:{decl.fqcn}",
                "collection": collection,
                "members": sorted(members),
                "references": sorted(references),
                "confirmed": False,
            }
        )
    return sorted(out, key=lambda a: (a["name"], a["root"]))


def risk_files(files: list[JavaFile], edges: list[dict], resources: list[str]) -> dict[str, list[str]]:
    """zone name -> repo-relative paths. Matches read code, comments and string contents excluded."""
    zones: dict[str, set[str]] = {name: set() for name in ZONE_REASONS}
    for parsed in files:
        text = parsed.source
        if _MONEY.search(_without_strings(text)):
            zones["money"].add(parsed.path)
        if _AUTH.search(_without_strings(text)) or _AUTH_PATH.search(parsed.path):
            zones["auth"].add(parsed.path)
        if _MIGRATION.search(_without_strings(text)):
            zones["migration"].add(parsed.path)
    for edge in edges:
        if edge["kind"] == "WRITES_FILE":
            zones["outbound-file"].add(edge["provenance"]["file"])
    for path in resources:
        if any(f"/{part}/" in f"/{path}" for part in _MIGRATION_DIRS):
            zones["migration"].add(path)
    return {name: sorted(paths) for name, paths in zones.items() if paths}


def _without_strings(text: str) -> str:
    return re.sub(r'"(?:\\.|[^"\\])*"', '""', text)


def zone_entries(by_name: dict[str, list[str]]) -> list[dict]:
    return [
        {"name": name, "paths": paths, "reason": ZONE_REASONS[name], "cap": CAP, "confirmed": False}
        for name, paths in sorted(by_name.items())
    ]


def merge_reviewed(existing: list[dict], seeds: list[dict], key: str, replaced_keys: set[str]) -> list[dict]:
    """A human's work survives: only entries still marked `confirmed: false` are ever replaced or dropped.
    `replaced_keys`: unconfirmed entries with these keys are this run's to refresh; others stay."""
    kept = [e for e in existing if e.get("confirmed") is not False or e.get(key) not in replaced_keys]
    held = {e.get(key) for e in kept}
    merged = kept + [s for s in seeds if s[key] not in held]
    return sorted(merged, key=lambda e: (str(e.get("name")), str(e.get(key))))
