"""The twelve contract extractors (contracts/artefacts.md section 2), over the parser-independent model."""

from __future__ import annotations

from dataclasses import dataclass, field

from baton.extract.config import Config
from baton.extract.model import Annotation, Chain, Expr, JavaFile, TypeDecl
from baton.extract.resolve import Resolver, TypeIndex, variable

_MAPPINGS = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "DeleteMapping": "DELETE",
    "PatchMapping": "PATCH",
}
_MONGO_REPOSITORIES = {
    "MongoRepository",
    "ReactiveMongoRepository",
    "CrudRepository",
    "ListCrudRepository",
    "PagingAndSortingRepository",
    "ListPagingAndSortingRepository",
    "ReactiveCrudRepository",
    "Repository",
    "ReactiveSortingRepository",
}
_MONGO_TEMPLATES = {"MongoTemplate", "MongoOperations", "ReactiveMongoTemplate", "ReactiveMongoOperations"}
_MONGO_READS = {
    "find",
    "findOne",
    "findById",
    "findAll",
    "findDistinct",
    "exists",
    "count",
    "estimatedCount",
    "aggregate",
    "aggregateStream",
    "stream",
    "scroll",
}
_MONGO_WRITES = {
    "insert",
    "insertAll",
    "save",
    "remove",
    "updateFirst",
    "updateMulti",
    "upsert",
    "findAndModify",
    "findAndRemove",
    "findAndReplace",
    "findAllAndRemove",
    "bulkOps",
    "dropCollection",
    "createCollection",
    "replace",
}
_HTTP_VERBS = {"get", "post", "put", "patch", "delete", "head", "options"}
_REST_TEMPLATE = {
    "getForObject": "GET",
    "getForEntity": "GET",
    "postForObject": "POST",
    "postForEntity": "POST",
    "postForLocation": "POST",
    "put": "PUT",
    "delete": "DELETE",
    "patchForObject": "PATCH",
    "headForHeaders": "HEAD",
    "optionsForAllow": "OPTIONS",
}
_FLAT_FILES = {
    "FlatFileItemReaderBuilder": ("READS_FILE", "flatfile-reader"),
    "FlatFileItemWriterBuilder": ("WRITES_FILE", "flatfile-writer"),
    "FlatFileItemReader": ("READS_FILE", "flatfile-reader"),
    "FlatFileItemWriter": ("WRITES_FILE", "flatfile-writer"),
}
_RESOURCE_TYPES = {"FileSystemResource", "ClassPathResource", "UrlResource", "PathResource"}
_JMS_SEND = {"send", "convertAndSend", "sendAndReceive", "convertSendAndReceive"}
_JMS_RECEIVE = {"receive", "receiveAndConvert", "receiveSelected", "receiveSelectedAndConvert"}
_KAFKA_SEND = {"send"}


def decapitalize(name: str) -> str:
    return name[:1].lower() + name[1:]


@dataclass
class Found:
    edges: list[dict] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    collections: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class _Run:
    def __init__(self, files: list[JavaFile], index: TypeIndex, config_of):
        self.files, self.index, self.config_of = files, index, config_of
        self.found = Found()
        self.resolver: Resolver | None = None
        self.path = ""

    def edge(self, kind: str, decl: TypeDecl, target: str, line: int, extractor: str) -> None:
        self.found.edges.append(
            {
                "kind": kind,
                "from": f"class:{decl.fqcn}",
                "to": target,
                "provenance": {"file": self.path, "line": line, "extractor": extractor},
            }
        )

    def target(self, kind: str, decl: TypeDecl, prefix: str, text: str, ok: bool, line: int, extractor: str):
        node = f"{prefix}:{text}"
        self.edge(kind, decl, node, line, extractor)
        if not ok:
            self.found.unresolved.append(node)

    def values(self, expr: Expr, decl: TypeDecl, method, line: int) -> list[tuple[str, bool]]:
        items = expr.items if expr.kind == "array" else (expr,)
        return [self.resolver.value(item, decl, method, line) for item in items]

    def document_collection(self, decl: TypeDecl) -> tuple[str, bool] | None:
        """The collection of a @Document class. With no name Spring derives it from the class name."""
        annotation = decl.annotation("Document")
        if annotation is None:
            return None
        expr = annotation.args.get("collection", annotation.args.get("value"))
        if expr is None:
            return decapitalize(decl.name), True
        saved, self.resolver = (
            self.resolver,
            Resolver(self.index, self.config_of(self.index.file_of[decl.fqcn])),
        )
        try:
            return self.resolver.value(expr, decl, None, annotation.line)
        finally:
            self.resolver = saved

    def run(self) -> Found:
        for parsed in self.files:
            self.path = parsed.path
            self.resolver = Resolver(self.index, self.config_of(parsed))
            for decl in parsed.types:
                self.document(decl)
                self.repository_generic(decl)
                self.request_mappings(decl)
                self.listeners(decl)
                for chain in decl.chains:
                    self.chain(decl, chain)
        return self.found

    # -- collections --------------------------------------------------------------------------------------

    def document(self, decl: TypeDecl) -> None:
        annotation = decl.annotation("Document")
        if annotation is None:
            return
        text, ok = self.document_collection(decl)
        self.target("READS_COLLECTION", decl, "collection", text, ok, annotation.line, "document-annotation")
        indexes = []
        for item in decl.annotations:
            if item.name == "CompoundIndex" and "name" in item.args:
                indexes.append(self.resolver.value(item.args["name"], decl, None, item.line)[0])
            elif item.name == "CompoundIndexes" and "value" in item.args:
                indexes += [
                    self.resolver.value(sub, decl, None, item.line)[0]
                    for sub in item.args["value"].items
                    if sub.kind == "str"
                ]
        self.found.collections.append(
            {
                "name": text,
                "owner": f"class:{decl.fqcn}",
                "file": self.path,
                "line": annotation.line,
                "compoundIndexes": indexes,
            }
        )

    def _repository_argument(self, decl: TypeDecl, seen=frozenset()) -> str | None:
        """The domain type of a repository interface, through local base interfaces."""
        for ref in [*decl.extends]:
            if ref.name in _MONGO_REPOSITORIES and ref.args:
                return ref.args[0]
            base = self.index.find(ref.name, decl)
            if base is not None and base.fqcn not in seen and ref.args:
                if self._repository_argument(base, seen | {base.fqcn}) is not None:
                    return ref.args[0]
        return None

    def repository_generic(self, decl: TypeDecl) -> None:
        if decl.kind != "interface":
            return
        argument = self._repository_argument(decl)
        if argument is None:
            return
        domain = self.index.find(argument, decl)
        if domain is None:
            type_parameter = len(argument) == 1 or argument == "?"
            if (
                not type_parameter
            ):  # a domain type outside this repo: it may be a document; nothing says which
                self.target(
                    "READS_COLLECTION",
                    decl,
                    "collection",
                    f"<{decl.name}.{argument}>",
                    False,
                    decl.line,
                    "spring-data-generic",
                )
            return
        collection = self.document_collection(domain)
        if collection is None:  # not a Mongo document, e.g. a JPA entity
            self.found.notes.append(f"{self.path}: repository of {argument}, which has no @Document: no edge")
            return
        self.target("READS_COLLECTION", decl, "collection", *collection, decl.line, "spring-data-generic")

    def _template_target(self, decl, chain, call) -> tuple[str, bool]:
        """A string-valued argument names the collection; else a class's @Document; else it cannot be read."""
        strings = []
        for arg in call.args:
            if arg.kind == "str" or arg.kind == "concat":
                strings.append(arg)
            elif arg.kind == "name":
                found = variable(arg.value, decl, chain.method)
                if found is None or found[0].type.name == "String":
                    strings.append(arg)
        if strings:
            return self.resolver.value(strings[-1], decl, chain.method, call.line)
        for arg in call.args:
            if arg.kind == "cls":
                document = self.index.find(arg.value, decl)
                collection = self.document_collection(document) if document else None
                if collection:
                    return collection
        if call.args and call.args[0].kind == "name":  # save(entity): the variable's type says
            found = variable(call.args[0].value, decl, chain.method)
            document = self.index.find(found[0].type.name, decl) if found else None
            collection = self.document_collection(document) if document else None
            if collection:
                return collection
        return f"<{decl.name}:{call.line}>", False

    # -- REST ---------------------------------------------------------------------------------------------

    def _paths(self, annotation: Annotation, decl, method) -> list[tuple[str, bool]]:
        expr = annotation.args.get("path", annotation.args.get("value"))
        return self.values(expr, decl, method, annotation.line) if expr is not None else [("", True)]

    def _verbs(self, annotation: Annotation) -> list[str]:
        if annotation.name in _MAPPINGS:
            return [_MAPPINGS[annotation.name]]
        expr = annotation.args.get("method")
        if expr is None:
            return ["ANY"]
        items = expr.items if expr.kind == "array" else (expr,)
        return [item.value.rsplit(".", 1)[-1] if item.kind == "name" else "ANY" for item in items]

    def request_mappings(self, decl: TypeDecl) -> None:
        feign = decl.annotation("FeignClient")
        if decl.annotation("RestController", "Controller") is None and feign is None:
            return
        base_annotation = decl.annotation("RequestMapping")
        bases = self._paths(base_annotation, decl, None) if base_annotation else [("", True)]
        for method in decl.methods:
            for annotation in method.annotations:
                if annotation.name not in _MAPPINGS and annotation.name != "RequestMapping":
                    continue
                for base, base_ok in bases:
                    for path, path_ok in self._paths(annotation, decl, method):
                        full = _join(base, path) or "/"
                        ok = base_ok and path_ok
                        for verb in self._verbs(annotation):
                            if feign is not None:
                                self._feign(decl, feign, verb, full, ok, annotation.line)
                            else:
                                self.target(
                                    "EXPOSES",
                                    decl,
                                    "endpoint",
                                    f"{verb} {full}",
                                    ok,
                                    annotation.line,
                                    "request-mapping",
                                )

    def _feign(self, decl, feign, verb, path, path_ok, line) -> None:
        expr = feign.args.get("url")
        base, ok = self.resolver.value(expr, decl, None, line) if expr else (f"<{decl.name}.url>", False)
        self._call(decl, verb, _join_url(base, path), ok and path_ok, line)

    def _call(self, decl, verb: str, url: str, ok: bool, line: int) -> None:
        self.target(
            "CALLS_ENDPOINT",
            decl,
            "endpoint",
            f"{verb} {url}" if ok else url,
            ok,
            line,
            "rest-client-base-url",
        )

    def _base_url(self, decl: TypeDecl) -> tuple[str, bool]:
        """The one base URL this class configures. None or several: nothing says which, so it stays open."""
        found = []
        for chain in decl.chains:
            for call in chain.calls:
                static_create = chain.root in ("RestClient", "WebClient") and call.name == "create"
                if (call.name == "baseUrl" or static_create) and call.args:
                    found.append(self.resolver.value(call.args[0], decl, chain.method, call.line))
        distinct = sorted(set(found))
        if len(distinct) == 1:
            return distinct[0]
        return f"<{decl.name}.base-url>", False

    def _rest_chain(self, decl, chain, kind) -> None:
        if kind == "RestTemplate":
            call = chain.calls[0]
            verb = _REST_TEMPLATE.get(call.name)
            if call.name == "exchange" and len(call.args) >= 2 and call.args[1].kind == "name":
                verb = call.args[1].value.rsplit(".", 1)[-1]
            if verb is None or not call.args:
                return
            uri = call
        else:
            verb = None
            uri = None
            for call in chain.calls:
                if call.name in _HTTP_VERBS and verb is None:
                    verb = call.name.upper()
                elif call.name == "method" and call.args and call.args[0].kind == "name":
                    verb = call.args[0].value.rsplit(".", 1)[-1]
                elif call.name == "uri" and uri is None:
                    uri = call
            if uri is None or not uri.args:
                return
        path, path_ok = self.resolver.value(uri.args[0], decl, chain.method, uri.line)
        if path_ok and path.startswith(("http://", "https://")):
            self._call(decl, verb or "ANY", path, True, uri.line)
            return
        base, base_ok = self._base_url(decl)
        self._call(decl, verb or "ANY", _join_url(base, path), base_ok and path_ok, uri.line)

    # -- messaging ----------------------------------------------------------------------------------------

    def listeners(self, decl: TypeDecl) -> None:
        for annotation in decl.annotations:
            self._listener(decl, annotation, None)
        for method in decl.methods:
            for annotation in method.annotations:
                self._listener(decl, annotation, method)

    def _listener(self, decl, annotation, method) -> None:
        if annotation.name == "KafkaListener":
            exprs = [annotation.args[k] for k in ("topics", "value", "topicPattern") if k in annotation.args]
            if not exprs:
                self.target(
                    "CONSUMES",
                    decl,
                    "topic",
                    f"<{decl.name}:{annotation.line}>",
                    False,
                    annotation.line,
                    "kafka-listener",
                )
            for expr in exprs:
                for text, ok in self.values(expr, decl, method, annotation.line):
                    self.target("CONSUMES", decl, "topic", text, ok, annotation.line, "kafka-listener")
        elif annotation.name == "JmsListener" and "destination" in annotation.args:
            for text, ok in self.values(annotation.args["destination"], decl, method, annotation.line):
                self.target("CONSUMES", decl, "queue", text, ok, annotation.line, "jms-listener")

    def _destination(self, decl, chain, call) -> tuple[str, bool]:
        """The first argument, if it names a destination. A send with no name uses a default not seen here."""
        if len(call.args) >= 2 or (call.args and call.name.startswith("receive")):
            arg = call.args[0]
            if arg.kind in ("str", "concat"):
                return self.resolver.value(arg, decl, chain.method, call.line)
            if arg.kind == "name":
                found = variable(arg.value, decl, chain.method)
                if found is None or found[0].type.name == "String":
                    return self.resolver.value(arg, decl, chain.method, call.line)
        return f"<{decl.name}:{call.line}>", False

    # -- chains -------------------------------------------------------------------------------------------

    def chain(self, decl: TypeDecl, chain: Chain) -> None:
        if chain.new is not None:
            self._new(decl, chain)
            return
        if not chain.calls:
            return
        root_type = chain.root
        if chain.root and "." not in chain.root:
            found = variable(chain.root, decl, chain.method)
            root_type = found[0].type.name if found else chain.root
        first = chain.calls[0]
        if root_type in _MONGO_TEMPLATES:
            kind = (
                "READS_COLLECTION"
                if first.name in _MONGO_READS
                else "WRITES_COLLECTION"
                if first.name in _MONGO_WRITES
                else None
            )
            if kind:
                text, ok = self._template_target(decl, chain, first)
                self.target(kind, decl, "collection", text, ok, first.line, "mongo-template-literal")
        elif root_type in ("RestClient", "WebClient"):
            self._rest_chain(decl, chain, root_type)
        elif root_type == "RestTemplate":
            self._rest_chain(decl, chain, root_type)
        elif root_type == "KafkaTemplate" and first.name in _KAFKA_SEND:
            text, ok = self._destination(decl, chain, first)
            self.target("PUBLISHES", decl, "topic", text, ok, first.line, "kafka-template")
        elif root_type in ("JmsTemplate", "JmsMessagingTemplate"):
            if first.name in _JMS_SEND:
                text, ok = self._destination(decl, chain, first)
                self.target("PUBLISHES", decl, "queue", text, ok, first.line, "jms-template")
            elif first.name in _JMS_RECEIVE:
                text, ok = self._destination(decl, chain, first)
                self.target("CONSUMES", decl, "queue", text, ok, first.line, "jms-template")
        elif root_type == "JobBuilderFactory" and first.name == "get" and first.args:
            text, ok = self.resolver.value(first.args[0], decl, chain.method, first.line)
            self.target("RUNS_JOB", decl, "job", text, ok, first.line, "job-builder")
        self._flat_file_setter(decl, chain, root_type)

    def _new(self, decl: TypeDecl, chain: Chain) -> None:
        type_name = chain.new.value
        if type_name == "JobBuilder" and chain.new.items:
            text, ok = self.resolver.value(chain.new.items[0], decl, chain.method, chain.new_line)
            self.target("RUNS_JOB", decl, "job", text, ok, chain.new_line, "job-builder")
        if type_name in ("FlatFileItemReaderBuilder", "FlatFileItemWriterBuilder"):
            kind, extractor = _FLAT_FILES[type_name]
            resource = next((c for c in chain.calls if c.name == "resource" and c.args), None)
            text, ok = self._resource(decl, chain, resource.args[0] if resource else None, chain.new_line)
            self.target(kind, decl, "file", text, ok, chain.new_line, extractor)

    def _flat_file_setter(self, decl, chain, root_type) -> None:
        if root_type in ("FlatFileItemReader", "FlatFileItemWriter"):
            for call in chain.calls:
                if call.name == "setResource" and call.args:
                    kind, extractor = _FLAT_FILES[root_type]
                    text, ok = self._resource(decl, chain, call.args[0], call.line)
                    self.target(kind, decl, "file", text, ok, call.line, extractor)

    def _resource(self, decl, chain, expr, line) -> tuple[str, bool]:
        if expr is None:
            return f"<{decl.name}:{line}>", False
        if expr.kind == "new" and expr.value in _RESOURCE_TYPES and expr.items:
            text, ok = self.resolver.value(expr.items[0], decl, chain.method, line)
            return (f"classpath:{text}" if expr.value == "ClassPathResource" and ok else text), ok
        return self.resolver.value(expr, decl, chain.method, line)


def _join(base: str, path: str) -> str:
    if not base:
        return path if not path or path.startswith(("/", "$", "<")) else f"/{path}"
    if not path:
        return base if base.startswith(("/", "$", "<")) else f"/{base}"
    joined = f"{base.rstrip('/')}/{path.lstrip('/')}"
    return joined if joined.startswith(("/", "$", "<")) else f"/{joined}"


def _join_url(base: str, path: str) -> str:
    if not path:
        return base
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def document_classes(files: list[JavaFile], index: TypeIndex, config_of) -> list[tuple[TypeDecl, str]]:
    """Every @Document class with its collection text, resolved or literal."""
    run = _Run(files, index, config_of)
    found = []
    for parsed in files:
        for decl in parsed.types:
            collection = run.document_collection(decl)
            if collection is not None:
                found.append((decl, collection[0]))
    return found


def extract(files: list[JavaFile], index: TypeIndex, config_of) -> Found:
    found = _Run(files, index, config_of).run()
    unique = {}
    for edge in found.edges:
        prov = edge["provenance"]
        unique[(edge["kind"], edge["from"], edge["to"], prov["file"], prov["line"], prov["extractor"])] = edge
    found.edges = [unique[key] for key in sorted(unique, key=lambda k: (k[3], k[4], k[0], k[1], k[2], k[5]))]
    found.unresolved = sorted(set(found.unresolved))
    found.collections.sort(key=lambda c: (c["name"], c["owner"]))
    return found


__all__ = ["Config", "Found", "extract"]
