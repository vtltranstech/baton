"""The code map: every class with its methods' line ranges, who calls what, and the resources each method
uses.

Built from the same AST as `baton extract` plus the repo's edges in the graph, so a diagram never names a
class, method or collection the code does not have. Cached at `.baton/code/<repo>.json` (git-ignored) and
rebuilt when a Java file or the repo's edges change. Agents read slices of it (`baton diagram context`)
instead of whole source files.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from baton.extract import ts_backend
from baton.extract.model import JavaFile, Method, TypeDecl
from baton.extract.repos import RepoRef, git_commit, load_sources
from baton.extract.resolve import TypeIndex, variable
from baton.graph.model import DOCUMENT_EXTRACTOR, Edge, node_name, node_prefix

CACHE_DIR = ".baton/code"
VERSION = 2
ENTRY_KINDS = ("EXPOSES", "CONSUMES", "RUNS_JOB")
_INJECT = {"Autowired", "Inject", "Resource", "Value"}
_SCHEDULED = {"Scheduled", "EventListener", "KafkaListener", "JmsListener", "RabbitListener", "SqsListener"}
_REPOSITORY_BASES = re.compile(r"(Mongo|Jpa|Crud|PagingAndSorting|Reactive\w*|ListCrud|R2dbc)Repository$")
_WRITE_VERBS = re.compile(r"^(save|insert|update|upsert|delete|remove|persist|merge|put|bulk|replace)")
_EXCEPTION = re.compile(r"(Exception|Error)$")


@dataclass
class Call:
    line: int
    target: str  # fqcn of the called class
    method: str  # "<init>" for `new T(..)`
    via: str  # field | self | static | param | local | new
    arity: int = -1  # arguments at the call site; -1 when unknown


@dataclass
class Use:
    kind: str  # an edge kind: READS_COLLECTION, PUBLISHES, EXPOSES, ...
    resource: str  # node id
    line: int


@dataclass
class FieldInfo:
    name: str
    type: str
    line: int
    injected: bool = False


@dataclass
class MethodInfo:
    name: str
    start: int
    end: int
    params: list[str] = field(default_factory=list)  # "String accountRef"
    returns: str = ""
    visibility: str = ""
    annotations: list[str] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)
    uses: list[Use] = field(default_factory=list)
    throws: list[str] = field(default_factory=list)

    def accepts(self, arity: int) -> bool:
        """Whether a call with this many arguments can land on this overload."""
        if arity < 0:
            return True
        if self.params and "..." in self.params[-1]:
            return arity >= len(self.params) - 1
        return arity == len(self.params)

    def signature(self, short: bool = False) -> str:
        params = ", ".join(p.split(" ")[-1] if short else p for p in self.params)
        tail = f": {self.returns}" if self.returns and self.returns != "void" else ""
        return f"{self.name}({params}){tail}"

    @property
    def entries(self) -> list[Use]:
        return [u for u in self.uses if u.kind in ENTRY_KINDS]

    def is_entry(self) -> bool:
        return bool(self.entries) or bool(_SCHEDULED & set(self.annotations))


@dataclass
class ClassInfo:
    fqcn: str
    name: str
    kind: str  # class | interface | enum | record | annotation | module (a TypeScript file)
    stereotype: str
    file: str
    start: int
    end: int
    repo: str = ""
    annotations: list[str] = field(default_factory=list)
    extends: list[str] = field(default_factory=list)  # fqcn when in the repo, else the simple name
    implements: list[str] = field(default_factory=list)
    fields: list[FieldInfo] = field(default_factory=list)
    methods: list[MethodInfo] = field(default_factory=list)
    uses: list[Use] = field(default_factory=list)  # edges at class level: spring-data, document, ...
    tests: list[str] = field(default_factory=list)  # test files that name this class
    doc: str = ""  # the collection this class is the shape of, if any

    @property
    def node(self) -> str:
        return f"class:{self.fqcn}"

    def method(self, name: str) -> list[MethodInfo]:
        return [m for m in self.methods if m.name == name]

    def is_value(self) -> bool:
        """Data carriers: never a lifeline in a sequence, never a box in a flow."""
        return self.stereotype in ("dto", "document", "value", "enum")


@dataclass
class CodeMap:
    repo: str
    commit: str
    fingerprint: str
    classes: dict[str, ClassInfo] = field(default_factory=dict)
    version: int = VERSION

    def __post_init__(self) -> None:
        self._reindex()

    def _reindex(self) -> None:
        self.by_name: dict[str, list[str]] = {}
        self.impls: dict[str, list[str]] = {}
        for fqcn in sorted(self.classes):
            info = self.classes[fqcn]
            self.by_name.setdefault(info.name, []).append(fqcn)
            for parent in info.implements + info.extends:
                if parent in self.classes:
                    self.impls.setdefault(parent, []).append(fqcn)

    def add(self, info: ClassInfo) -> None:
        self.classes[info.fqcn] = info
        self._reindex()

    def implementation(self, fqcn: str) -> str:
        """The one in-repo implementation of an interface, else the interface itself."""
        found = self.impls.get(fqcn, [])
        info = self.classes.get(fqcn)
        if info and info.kind == "interface" and len(found) == 1:
            return found[0]
        return fqcn

    def callers(self, fqcn: str, method: str | None = None) -> list[tuple[ClassInfo, MethodInfo, Call]]:
        """Calls into a class (or one of its methods), also through an interface it implements."""
        targets = {fqcn} | {
            parent for parent in self.classes.get(fqcn, ClassInfo(fqcn, "", "", "", "", 0, 0)).implements
        }
        out = []
        for info in self.classes.values():
            for m in info.methods:
                for call in m.calls:
                    if call.target in targets and (method is None or call.method == method):
                        out.append((info, m, call))
        return sorted(out, key=lambda item: (item[0].fqcn, item[2].line))

    def at(self, file: str, line: int) -> tuple[ClassInfo | None, MethodInfo | None]:
        """The innermost class and the method covering a line of a file."""
        best: ClassInfo | None = None
        for info in self.classes.values():
            if info.file == file and info.start <= line <= max(info.end, info.start):
                if best is None or info.start >= best.start:
                    best = info
        if best is None:
            return None, None
        for m in best.methods:
            if m.start <= line <= m.end:
                return best, m
        return best, None

    def to_json(self) -> str:
        data = {
            "version": self.version,
            "repo": self.repo,
            "commit": self.commit,
            "fingerprint": self.fingerprint,
            "classes": [asdict(self.classes[k]) for k in sorted(self.classes)],
        }
        return json.dumps(data, indent=1, sort_keys=True) + "\n"

    @classmethod
    def from_json(cls, text: str) -> CodeMap:
        data = json.loads(text)
        classes = {}
        for raw in data["classes"]:
            raw["fields"] = [FieldInfo(**f) for f in raw["fields"]]
            raw["uses"] = [Use(**u) for u in raw["uses"]]
            methods = []
            for m in raw["methods"]:
                m["calls"] = [Call(**c) for c in m["calls"]]
                m["uses"] = [Use(**u) for u in m["uses"]]
                methods.append(MethodInfo(**m))
            raw["methods"] = methods
            classes[raw["fqcn"]] = ClassInfo(**raw)
        return cls(data["repo"], data["commit"], data["fingerprint"], classes, data.get("version", 0))


# -- building ----------------------------------------------------------------------------------------------


def _names(annotations) -> list[str]:
    return [a.name for a in annotations]


def _start(method: Method) -> int:
    return min([method.line, *[a.line for a in method.annotations if a.line]])


def _stereotype(decl: TypeDecl, repository_like: bool) -> str:
    names = set(_names(decl.annotations))
    if names & {"RestController", "Controller"}:
        return "controller"
    if names & {"Document", "Entity", "Table"}:
        return "document"
    if "Configuration" in names:
        return "config"
    if "SpringBootApplication" in names:
        return "application"
    if "Repository" in names or repository_like:
        return "repository"
    if "Service" in names:
        return "service"
    if any(m_names & _SCHEDULED for m_names in (set(_names(m.annotations)) for m in decl.methods)):
        return "listener"
    if "Component" in names:
        lowered = decl.name.lower()
        for word, kind in (("client", "client"), ("publisher", "publisher"), ("store", "adapter")):
            if lowered.endswith(word):
                return kind
        return "component"
    if decl.kind == "enum":
        return "enum"
    if decl.kind == "record" or decl.name.endswith(("Dto", "DTO", "Request", "Response", "View")):
        return "dto"
    if decl.kind == "interface":
        return "interface"
    return "class"


def _resolve_type(name: str, decl: TypeDecl, index: TypeIndex) -> str | None:
    found = index.find(name, decl)
    return found.fqcn if found is not None else None


def _calls(decl: TypeDecl, index: TypeIndex, methods: dict[int, MethodInfo]) -> None:
    own = {m.name for m in decl.methods}
    for chain in decl.chains:
        if chain.method is None:
            continue
        info = methods.get(id(chain.method))
        if info is None:
            continue
        if chain.new is not None and chain.new.kind == "new":
            created = chain.new.value
            if _EXCEPTION.search(created):
                if created not in info.throws:
                    info.throws.append(created)
            else:
                target = _resolve_type(created, decl, index)
                if target:
                    info.calls.append(Call(chain.new_line or info.start, target, "<init>", "new"))
            continue
        if not chain.calls:
            continue
        first = chain.calls[0]
        if not chain.root:
            if first.name in own:
                info.calls.append(Call(first.line, decl.fqcn, first.name, "self", len(first.args)))
            continue
        head = chain.root.split(".", 1)[0]
        if "." in chain.root:
            continue  # a call on a field of a field: the AST cannot tell the type
        found = variable(head, decl, chain.method)
        if found is not None:
            var, _owner = found
            target = _resolve_type(var.type.name, decl, index)
            if target:
                kind = "field" if var in _owner.fields else "param" if var in chain.method.params else "local"
                info.calls.append(Call(first.line, target, first.name, kind, len(first.args)))
            continue
        target = _resolve_type(head, decl, index)
        if target:
            info.calls.append(Call(first.line, target, first.name, "static", len(first.args)))


def _class_info(decl: TypeDecl, parsed: JavaFile, index: TypeIndex, repo: str) -> ClassInfo:
    def ref(name: str) -> str:
        return _resolve_type(name, decl, index) or name

    extends = [ref(t.name) for t in decl.extends]
    repository_like = decl.kind == "interface" and any(_REPOSITORY_BASES.search(t.name) for t in decl.extends)
    info = ClassInfo(
        decl.fqcn,
        decl.name,
        decl.kind,
        _stereotype(decl, repository_like),
        parsed.path,
        decl.line,
        decl.end or decl.line,
        repo,
        _names(decl.annotations),
        extends,
        [ref(t.name) for t in decl.implements],
    )
    constructor_params = {p.name for m in decl.methods if m.name == decl.name for p in m.params}
    for var in decl.fields:
        injected = bool(_INJECT & set(_names(var.annotations))) or (
            var.final and var.init is None and (var.name in constructor_params or decl.kind != "record")
        )
        type_name = var.type.name + (f"<{', '.join(var.type.args)}>" if var.type.args else "")
        info.fields.append(FieldInfo(var.name, type_name, var.line, injected and decl.kind != "record"))
    by_id: dict[int, MethodInfo] = {}
    for method in decl.methods:
        params = [
            f"{p.type.name}{'<' + ', '.join(p.type.args) + '>' if p.type.args else ''} {p.name}"
            for p in method.params
        ]
        m = MethodInfo(
            method.name,
            _start(method),
            method.end or method.line,
            params,
            method.returns,
            method.visibility,
            _names(method.annotations),
        )
        info.methods.append(m)
        by_id[id(method)] = m
    _calls(decl, index, by_id)
    for m in info.methods:
        m.calls.sort(key=lambda c: (c.line, c.method))
    return info


def _attach(classes: dict[str, ClassInfo], edges: list[Edge], repo: str) -> None:
    """Each edge goes on the method covering its line, else on its class. A source the AST has no class for
    (a TypeScript module) becomes a class of kind `module`."""
    for edge in sorted(edges):
        if edge.repo != repo or node_prefix(edge.src) != "class":
            continue
        fqcn = node_name(edge.src)
        info = classes.get(fqcn)
        if info is None:
            short = fqcn.rsplit(".", 1)[-1]
            info = classes.setdefault(fqcn, ClassInfo(fqcn, short, "module", "ui", edge.file, 1, 1, repo))
        use = Use(edge.kind, edge.dst, edge.line)
        if edge.extractor == DOCUMENT_EXTRACTOR:
            info.doc = node_name(edge.dst)
            info.stereotype = "document"
            continue
        method = next((m for m in info.methods if m.start <= edge.line <= m.end), None)
        target = method.uses if method else info.uses
        if use not in target:
            target.append(use)


def _tests(classes: dict[str, ClassInfo], tests: list[JavaFile]) -> None:
    by_name: dict[str, list[ClassInfo]] = {}
    for info in classes.values():
        by_name.setdefault(info.name, []).append(info)
    for parsed in tests:
        tokens = set(re.findall(r"[A-Za-z_]\w*", parsed.source))
        for name in tokens & set(by_name):
            for info in by_name[name]:
                if parsed.path not in info.tests:
                    info.tests.append(parsed.path)
    for info in classes.values():
        info.tests.sort()


_IMPORT = re.compile(r"""^\s*import\s+(?!type\b)([^;'"]*?)\s+from\s+['"](\.{1,2}/[^'"]+)['"]""", re.M)
_TS_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", "/index.ts", "/index.tsx", "/index.js")


def _ts_stereotype(rel: str) -> str:
    stem = Path(rel).stem
    if stem.startswith("use") and stem[3:4].isupper():
        return "hook"
    if "/api/" in f"/{rel}" or stem.lower().endswith(("client", "api", "service")):
        return "client"
    if rel.endswith((".tsx", ".jsx")) and stem[:1].isupper():
        return "screen"
    return "ui"


def _typescript(repo: Path, name: str, classes: dict[str, ClassInfo]) -> None:
    """One `module` per TypeScript file; an imported name's first call is a call into that module."""
    root = repo.resolve()
    files = {p.resolve().relative_to(root).as_posix(): p for p in ts_backend.source_files(repo)}
    for rel in sorted(files):
        text = files[rel].read_text(encoding="utf-8", errors="replace")
        node = node_name(ts_backend.node_of(rel))
        lines = text.count("\n") + 1
        info = classes.setdefault(node, ClassInfo(node, Path(rel).stem, "module", "ui", rel, 1, lines, name))
        info.kind, info.stereotype, info.file, info.end = "module", _ts_stereotype(rel), rel, lines
        body = MethodInfo(Path(rel).stem, 1, lines)
        for match in _IMPORT.finditer(text):
            base = (Path(rel).parent / match.group(2)).as_posix()
            parts: list[str] = []
            for part in base.split("/"):
                if part == "..":
                    parts = parts[:-1]
                elif part not in (".", ""):
                    parts.append(part)
            base = "/".join(parts)
            target_rel = next((base + s for s in ("", *_TS_SUFFIXES) if base + s in files), None)
            if target_rel is None:
                continue
            target = node_name(ts_backend.node_of(target_rel))
            for imported in re.findall(r"[A-Za-z_$][\w$]*", match.group(1).replace(" as ", " ")):
                use = re.search(
                    rf"\b{re.escape(imported)}\s*\(|<{re.escape(imported)}\b", text[match.end() :]
                )
                if use:
                    line = text[: match.end() + use.start()].count("\n") + 1
                    body.calls.append(Call(line, target, imported, "import"))
        body.calls.sort(key=lambda c: (c.line, c.method))
        if body.calls or not info.methods:
            info.methods = [body]


def fingerprint(repo_path: Path, edges: list[Edge]) -> str:
    digest = hashlib.sha256(f"v{VERSION}".encode())
    sources = sorted(repo_path.rglob("*.java")) + ts_backend.source_files(repo_path)
    for path in sources:
        rel = path.relative_to(repo_path).as_posix()
        if any(part in ("target", "build", "node_modules") for part in rel.split("/")):
            continue
        stat = path.stat()
        digest.update(f"{rel}:{stat.st_size}:{stat.st_mtime_ns}\n".encode())
    for edge in sorted(edges):
        digest.update(repr(edge.to_dict()).encode())
    return digest.hexdigest()[:24]


def build(repo: RepoRef, edges: list[Edge]) -> CodeMap:
    sources = load_sources(repo)
    index = TypeIndex()
    for parsed in sources.main:
        index.add(parsed)
    classes: dict[str, ClassInfo] = {}
    for parsed in sources.main:
        for decl in parsed.types:
            classes[decl.fqcn] = _class_info(decl, parsed, index, repo.name)
    _typescript(repo.path, repo.name, classes)
    _attach(classes, edges, repo.name)
    _tests(classes, sources.test)
    commit, _ = git_commit(repo.path)
    return CodeMap(repo.name, commit, fingerprint(repo.path, edges), classes)


def load(central: Path, repo: RepoRef, edges: list[Edge]) -> CodeMap:
    """The cached map when it still matches the code and the edges, else a fresh one (written back)."""
    repo_edges = [e for e in edges if e.repo == repo.name]
    cache = central / CACHE_DIR / f"{repo.name}.json"
    current = fingerprint(repo.path, repo_edges)
    if cache.is_file():
        try:
            cached = CodeMap.from_json(cache.read_text(encoding="utf-8"))
            if cached.fingerprint == current and cached.version == VERSION:
                return cached
        except (ValueError, KeyError, TypeError):
            pass
    fresh = build(repo, repo_edges)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(fresh.to_json(), encoding="utf-8")
    return fresh


def read_write(info: ClassInfo, method: str) -> str | None:
    """For a call into a Spring Data repository, whether the named method reads or writes."""
    if info.stereotype != "repository":
        return None
    return "WRITES_COLLECTION" if _WRITE_VERBS.match(method) else "READS_COLLECTION"
