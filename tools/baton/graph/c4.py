"""C4 projection to Structurizr DSL (contracts/graph.md): sorted, no counters, no timestamps."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from baton.graph.model import DOCUMENT_EXTRACTOR, Edge, node_name, node_prefix
from baton.graph.profile_files import Profile, known

_STEREOTYPES = {
    "request-mapping": "Spring @RestController",
    "spring-data-generic": "Spring Data",
    "mongo-template-literal": "Spring @Component",
    "rest-client-base-url": "Spring @Component",
    "kafka-listener": "Spring @KafkaListener",
    "kafka-template": "Spring @Component",
    "jms-listener": "Spring @JmsListener",
    "jms-template": "Spring @Component",
    "flatfile-reader": "Spring Batch ItemReader",
    "flatfile-writer": "Spring Batch ItemWriter",
    "job-builder": "Spring @Configuration",
}
_DIRECTION = {
    "READS_COLLECTION": "read",
    "WRITES_COLLECTION": "write",
    "PUBLISHES": "publish",
    "CONSUMES": "consume",
}
_RESERVED = frozenset(
    "workspace model views styles person softwaresystem container component deploymentenvironment "
    "deploymentnode group element relationship include exclude animation dynamic this properties "
    "perspectives tags tag url description theme themes branding terminology configuration".split()
)
_QUEUE_BROKERS = ("jms", "mq", "activemq", "artemis", "rabbit")


def lower_camel(name: str) -> str:
    """lowerCamel of a name; word boundaries are non-alphanumerics and existing camel humps."""
    words: list[str] = []
    for chunk in re.split(r"[^0-9A-Za-z]+", name):
        words += re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+", chunk)
    if not words:
        return "unnamed"
    text = words[0].lower() + "".join(word.capitalize() for word in words[1:])
    if text[0].isdigit():
        text = "n" + text
    return text


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


@dataclass
class _Component:
    node: str
    repo: str
    name: str
    technology: str
    identifier: str = ""


@dataclass
class _Model:
    ids: dict = field(default_factory=dict)
    used: set = field(default_factory=set)

    def claim(self, key, *candidates: str) -> str:
        """First free candidate; derived from names only, so independent of run order."""
        for candidate in candidates:
            if candidate.lower() not in self.used and candidate.lower() not in _RESERVED:
                self.used.add(candidate.lower())
                self.ids[key] = candidate
                return candidate
        raise ValueError(f"identifier collision for {key}: {candidates}")


def _first_token(value: str | None) -> str | None:
    if not known(value):
        return None
    return re.split(r"[,;/ ]+", value.strip())[0]


def _datastore_of(collection: str, edges: list[Edge], profile: Profile) -> str:
    repos = sorted({e.repo for e in edges if e.dst == collection})
    for repo in repos:
        token = _first_token(profile.stack.get(repo, {}).get("datastore"))
        if token:
            return token
    return "datastore"


def _broker_of(resource: str, edges: list[Edge], profile: Profile) -> str:
    repos = sorted({e.repo for e in edges if e.dst == resource})
    tokens: list[str] = []
    for repo in repos:
        value = profile.stack.get(repo, {}).get("messaging")
        if known(value):
            tokens += [t for t in re.split(r"[,;/ ]+", value.strip()) if t]
    if node_prefix(resource) == "queue":
        for token in tokens:
            if token.lower().startswith(_QUEUE_BROKERS):
                return token
    else:
        for token in tokens:
            if token.lower().startswith("kafka"):
                return token
    return tokens[0] if tokens else "broker"


def _display_technology(name: str) -> str:
    return {"mongodb": "MongoDB", "kafka": "Kafka", "jms": "JMS"}.get(name.lower(), name)


def _repo_type(repo: str, profile: Profile) -> tuple[str, str]:
    row = profile.stack.get(repo, {})
    if known(row.get("ui")):
        return "ui", "React"
    if known(row.get("batch")):
        return "batch", "Spring Batch"
    return "service", "Spring Boot"


def _components(edges: list[Edge]) -> dict[tuple[str, str], _Component]:
    found: dict[tuple[str, str], _Component] = {}
    for edge in sorted(edges):
        if edge.kind == "OWNED_BY":
            continue
        if node_prefix(edge.src) == "class" and edge.extractor != DOCUMENT_EXTRACTOR:
            technology = _STEREOTYPES.get(edge.extractor, "Spring @Component")
            found.setdefault(
                (edge.repo, edge.src),
                _Component(edge.src, edge.repo, node_name(edge.src).rsplit(".", 1)[-1], technology),
            )
        if edge.kind == "RUNS_JOB":
            found.setdefault(
                (edge.repo, edge.dst),
                _Component(edge.dst, edge.repo, node_name(edge.dst), "Spring Batch Job"),
            )
    return found


def _assign_component_ids(components, model: _Model) -> None:
    by_camel: dict[str, list[_Component]] = {}
    for comp in components.values():
        by_camel.setdefault(lower_camel(comp.name), []).append(comp)
    for camel in sorted(by_camel):
        group = sorted(by_camel[camel], key=lambda c: (c.repo, c.node))
        clash = len(group) > 1
        for comp in group:
            qualified = lower_camel(f"{comp.repo} {comp.name}")
            full = lower_camel(f"{comp.repo} {node_name(comp.node)}")
            options = (qualified, full) if clash else (camel, qualified, full)
            comp.identifier = model.claim(("component", comp.repo, comp.node), *options)


def _unknown_externals(edges: list[Edge]) -> dict[str, str]:
    """Unknown edge endpoints that become ExternalSystems, keyed by "<role> <resource>".

    A collection or an exposed endpoint with one side stays inside its own datastore or service container.
    """
    kinds_by_resource: dict[str, set[str]] = {}
    for edge in edges:
        kinds_by_resource.setdefault(edge.dst, set()).add(edge.kind)
    out: dict[str, str] = {}
    for resource in sorted(kinds_by_resource):
        kinds = kinds_by_resource[resource]
        prefix = node_prefix(resource)
        if prefix == "endpoint" and "CALLS_ENDPOINT" in kinds and "EXPOSES" not in kinds:
            out[resource] = f"Unknown provider of {resource}"
        elif prefix in ("topic", "queue"):
            if "PUBLISHES" in kinds and "CONSUMES" not in kinds:
                out[resource] = f"Unknown consumer of {resource}"
            elif "CONSUMES" in kinds and "PUBLISHES" not in kinds:
                out[resource] = f"Unknown publisher of {resource}"
        elif prefix == "file":
            if "WRITES_FILE" in kinds and "READS_FILE" not in kinds:
                out[resource] = f"Unknown reader of {resource}"
            elif "READS_FILE" in kinds and "WRITES_FILE" not in kinds:
                out[resource] = f"Unknown writer of {resource}"
    return out


def render(edges: list[Edge], profile: Profile, dynamic_views: list[str] | None = None) -> str:
    edges = sorted(e for e in edges if e.kind != "OWNED_BY")
    repos = sorted({e.repo for e in edges} | set(profile.repos))
    model = _Model()
    user = model.claim("user", "user") if profile.personas else None
    product = model.claim("product", "product", "productSystem")

    datastores: dict[str, list[str]] = {}
    brokers: dict[str, list[str]] = {}
    store_of: dict[str, str] = {}
    for resource in sorted({e.dst for e in edges}):
        prefix = node_prefix(resource)
        if prefix == "collection":
            name = _datastore_of(resource, edges, profile)
            store_of[resource] = name
            datastores.setdefault(name, []).append(node_name(resource))
        elif prefix in ("topic", "queue"):
            name = _broker_of(resource, edges, profile)
            store_of[resource] = name
            brokers.setdefault(name, []).append(node_name(resource))

    for repo in repos:
        model.claim(("repo", repo), lower_camel(repo), lower_camel(f"{repo} service"))
    for name in sorted(set(datastores) | set(brokers)):
        model.claim(("infra", name), lower_camel(name), lower_camel(f"{name} container"))
    externals = sorted(profile.externals)
    for name, _ in externals:
        model.claim(("external", name), lower_camel(name), lower_camel(f"{name} system"))
    unknown = _unknown_externals(edges)
    for resource, label in unknown.items():
        model.claim(("unknown", resource), lower_camel(label))
    components = _components(edges)
    _assign_component_ids(components, model)

    relationships = _relationships(edges, components, model, store_of, unknown, profile)
    lines = [
        "// docs/architecture/workspace.dsl: generated by `baton c4`. Do not rename identifiers.",
        f"workspace {_quote(profile.name)} {_quote(profile.one_liner)} {{",
        "",
        "    model {",
    ]
    if user:
        lines.append(f'        {user} = person {_quote(profile.personas[0])} "Uses the product"')
    for name, description in externals:
        lines += _external(model.ids[("external", name)], name, description)
    for resource, label in unknown.items():
        lines += _external(
            model.ids[("unknown", resource)], label, "Other side not in the graph", tags="External,Unknown"
        )
    lines += ["", f"        {product} = softwareSystem {_quote(profile.name)} {_quote(profile.one_liner)} {{"]
    for repo in repos:
        lines += _repo_container(repo, model, components, profile)
    for name in sorted(datastores):
        collections = ", ".join(datastores[name])
        lines.append(
            f"            {model.ids[('infra', name)]} = container {_quote(name)} "
            f"{_quote('collections: ' + collections)} {_quote(_display_technology(name))} {{"
        )
        lines += ['                tags "Database"', "            }"]
    for name in sorted(brokers):
        names = ", ".join(brokers[name])
        lines.append(
            f"            {model.ids[('infra', name)]} = container {_quote(name)} "
            f"{_quote('topics and queues: ' + names)} {_quote(_display_technology(name))}"
        )
    lines += ["        }", ""]
    if user:
        for repo in repos:
            if _repo_type(repo, profile)[0] == "ui":
                lines.append(f'        {user} -> {model.ids[("repo", repo)]} "uses"')
    for (src, dst, label), technologies in sorted(relationships.items()):
        lines.append(f"        {src} -> {dst} {_quote(label)} {_quote(', '.join(sorted(technologies)))}")
    lines += ["    }", "", "    views {"]
    lines += _view("systemContext", product, "Context")
    lines += _view("container", product, "Containers")
    for repo in repos:
        if any(comp.repo == repo for comp in components.values()):
            identifier = model.ids[("repo", repo)]
            lines += _view("component", identifier, f"{identifier}Components")
    for view in sorted(dynamic_views or [], key=_dynamic_key):
        lines += ["        " + line if line.strip() else "" for line in view.splitlines()]
    lines += [
        "        styles {",
        *_style("External", "background #9aa3b2", "color #ffffff"),
        *_style("Database", "shape Cylinder"),
        *_style("New", "background #1f5fa8", "color #ffffff"),
        *_style("Changed", "background #d9731a", "color #ffffff"),
        "        }",
        "    }",
        "}",
        "",
    ]
    return "\n".join(lines)


def _style(tag: str, *rules: str) -> list[str]:
    # structurizr-cli rejects `element "x" { ... }` on one line, so each rule gets its own line.
    return [
        f"            element {_quote(tag)} {{",
        *[f"                {rule}" for rule in rules],
        "            }",
    ]


def _external(identifier: str, name: str, description: str, tags: str = "External") -> list[str]:
    return [
        f"        {identifier} = softwareSystem {_quote(name)} {_quote(description)} {{",
        f"            tags {_quote(tags)}",
        "        }",
    ]


def _repo_container(repo: str, model: _Model, components, profile: Profile) -> list[str]:
    info = profile.repos.get(repo)
    purpose = info.purpose if info else ""
    technology = _repo_type(repo, profile)[1]
    identifier = model.ids[("repo", repo)]
    head = f"            {identifier} = container {_quote(repo)} {_quote(purpose)} {_quote(technology)}"
    own = sorted((c for c in components.values() if c.repo == repo), key=lambda c: c.identifier)
    if not own:
        return [head]
    out = [head + " {"]
    for comp in own:
        out.append(
            f'                {comp.identifier} = component {_quote(comp.name)} "" {_quote(comp.technology)}'
        )
    out.append("            }")
    return out


def _view(kind: str, scope: str, key: str) -> list[str]:
    return [
        f"        {kind} {scope} {_quote(key)} {{",
        "            include *",
        "            autoLayout lr",
        "        }",
    ]


def _relationships(edges, components, model, store_of, unknown, profile) -> dict:
    rel: dict[tuple[str, str, str], set[str]] = {}

    def add(src: str, dst: str, label: str, technology: str) -> None:
        if src != dst:
            rel.setdefault((src, dst, label), set()).add(technology)

    def comp_id(edge: Edge, node: str | None = None) -> str | None:
        comp = components.get((edge.repo, node or edge.src))
        return comp.identifier if comp else None

    by_resource: dict[tuple[str, str], list[Edge]] = {}
    for edge in edges:
        by_resource.setdefault((edge.kind, edge.dst), []).append(edge)

    for edge in edges:
        source = comp_id(edge)
        label = node_name(edge.dst)
        if edge.kind == "RUNS_JOB":
            target = comp_id(edge, edge.dst)
            if source and target:
                add(source, target, label, "Spring Batch")
        if source is None:
            continue
        if edge.kind in ("READS_COLLECTION", "WRITES_COLLECTION", "PUBLISHES", "CONSUMES"):
            infra_name = store_of[edge.dst]
            infra = model.ids[("infra", infra_name)]
            technology = f"{_display_technology(infra_name)} {_DIRECTION[edge.kind]}"
            if edge.kind == "CONSUMES":
                add(infra, source, label, technology)
                if unknown.get(edge.dst):
                    add(model.ids[("unknown", edge.dst)], infra, label, technology)
            else:
                add(source, infra, label, technology)
                if edge.kind == "PUBLISHES" and unknown.get(edge.dst):
                    add(infra, model.ids[("unknown", edge.dst)], label, technology)
        elif edge.kind == "CALLS_ENDPOINT":
            providers = by_resource.get(("EXPOSES", edge.dst), [])
            for provider in providers:
                target = comp_id(provider)
                if target:
                    add(source, target, label, "REST/JSON")
            if edge.dst in unknown:
                add(source, model.ids[("unknown", edge.dst)], label, "REST/JSON")
        elif edge.kind == "WRITES_FILE":
            for reader in by_resource.get(("READS_FILE", edge.dst), []):
                target = comp_id(reader)
                if target:
                    add(source, target, label, "file")
            if edge.dst in unknown:
                add(source, model.ids[("unknown", edge.dst)], label, "file")
        elif edge.kind == "READS_FILE" and edge.dst in unknown:
            add(model.ids[("unknown", edge.dst)], source, label, "file")
    return rel


# --- existing workspace handling ---


def _mask_noncode(text: str, keep_strings: bool = False) -> str:
    """Same length as `text`, comments (and strings) blanked, so brace-matching offsets stay valid."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            j = i + 1
            while j < n and text[j] != '"' and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            if not keep_strings:
                for k in range(i, min(j + 1, n)):
                    out[k] = " "
            i = j + 1
        elif (
            text.startswith("//", i)
            or (ch == "#" and text[i + 1 : i + 2] in (" ", "\n", ""))
            or (ch == "#" and not text[text.rfind("\n", 0, i) + 1 : i].strip())
        ):
            while i < n and text[i] != "\n":
                out[i] = " "
                i += 1
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = n if end < 0 else end + 2
            for k in range(i, end):
                if text[k] != "\n":
                    out[k] = " "
            i = end
        else:
            i += 1
    return "".join(out)


def extract_dynamic_views(text: str) -> list[str]:
    """The `dynamic ... { ... }` blocks of a workspace, verbatim but dedented."""
    masked = _mask_noncode(text)
    views: list[str] = []
    for match in re.finditer(r"(?m)^[ \t]*dynamic\b", masked):
        depth, i, opened = 0, match.start(), False
        while i < len(masked):
            if masked[i] == "{":
                depth, opened = depth + 1, True
            elif masked[i] == "}":
                depth -= 1
                if opened and depth == 0:
                    break
            i += 1
        block = text[match.start() : i + 1]
        views.append(_dedent(block))
    return sorted(views, key=_dynamic_key)


def _dedent(block: str) -> str:
    lines = block.splitlines()
    first_indent = len(lines[0]) - len(lines[0].lstrip())
    return "\n".join(
        line[first_indent:] if line[:first_indent].isspace() else line.lstrip() for line in lines
    )


def _dynamic_key(view: str) -> str:
    match = re.search(r'"([^"]*)"', view)
    return match.group(1) if match else view


def _declared_elements(generated: str) -> dict[str, str | None]:
    """identifier -> parent identifier, from the brace structure of the generated DSL."""
    parents: dict[str, str | None] = {}
    stack: list[str | None] = []
    declaration = re.compile(r"^\s*(\w+)\s*=\s*(?:person|softwareSystem|container|component)\b")
    for raw in _mask_noncode(generated, keep_strings=False).splitlines():
        match = declaration.match(raw)
        if match:
            enclosing = [item for item in stack if item]
            parents[match.group(1)] = enclosing[-1] if enclosing else None
        if raw.count("{") > raw.count("}"):
            stack.append(match.group(1) if match else None)
        elif raw.count("}") > raw.count("{"):
            stack.pop()
    return parents


def _ancestors(identifier: str, parents: dict[str, str | None]) -> set[str]:
    out = {identifier}
    while parents.get(identifier):
        identifier = parents[identifier]
        out.add(identifier)
    return out


def dynamic_view_problems(generated: str, dynamic_views: list[str]) -> list[str]:
    """What structurizr-cli would reject in a kept view: unknown identifiers, steps with no relationship.

    A step is backed by a relationship between the same elements or, since the DSL creates implied
    relationships upwards, between their descendants.
    """
    parents = _declared_elements(generated)
    backed: set[tuple[str, str]] = set()
    arrow = re.compile(r"([\w-]+)\s*->\s*([\w-]+)")
    model_text = _mask_noncode(generated).split("\n    views {", 1)[0]
    for src, dst in arrow.findall(model_text):
        if src in parents and dst in parents:
            backed |= {(a, b) for a in _ancestors(src, parents) for b in _ancestors(dst, parents)}
    problems: list[str] = []
    for view in dynamic_views:
        key = _dynamic_key(view)
        masked = _mask_noncode(view)
        scope = re.match(r"\s*dynamic\s+([\w*-]+)", masked)
        names = {scope.group(1)} - {"*"} if scope else set()
        steps = arrow.findall(masked)
        names |= {name for step in steps for name in step}
        for name in sorted(names - set(parents)):
            problems.append(f"dynamic view {key} references undeclared identifier {name}")
        for src, dst in sorted(set(steps)):
            if src in parents and dst in parents and (src, dst) not in backed:
                problems.append(f"dynamic view {key} step {src} -> {dst} has no relationship in the model")
    return problems


def _normalise(text: str) -> list[str]:
    return [line.strip() for line in _mask_noncode(text, keep_strings=True).splitlines() if line.strip()]


def drift(existing: str, generated: str) -> list[str]:
    """Unified diff (comments and whitespace ignored) from the recorded workspace to the projection."""
    return list(
        difflib.unified_diff(
            _normalise(existing),
            _normalise(generated),
            "docs/architecture/workspace.dsl",
            "baton c4",
            lineterm="",
            n=1,
        )
    )
