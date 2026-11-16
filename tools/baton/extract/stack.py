"""Stack facts from build files, layout from stereotypes. Values are detected or `unknown`, never guessed."""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

from baton.extract.model import JavaFile, TypeDecl
from baton.extract.repos import UNKNOWN, Sources

_DATASTORE = {
    "mongodb": {
        "spring-boot-starter-data-mongodb",
        "spring-boot-starter-data-mongodb-reactive",
        "spring-data-mongodb",
        "mongodb-driver-sync",
        "mongodb-driver-reactivestreams",
    },
    "jpa": {"spring-boot-starter-data-jpa", "spring-data-jpa", "jakarta.persistence-api"},
    "jdbc": {"spring-boot-starter-jdbc", "spring-boot-starter-data-jdbc"},
}
_MESSAGING = {
    "kafka": {"spring-kafka", "kafka-clients"},
    "jms": {"spring-jms", "spring-boot-starter-artemis", "spring-boot-starter-activemq"},
    "amqp": {"spring-boot-starter-amqp", "spring-rabbit"},
}
_WEB = {
    "spring-mvc": {"spring-boot-starter-web", "spring-webmvc"},
    "spring-webflux": {"spring-boot-starter-webflux", "spring-webflux"},
}
_BATCH = {"spring-boot-starter-batch", "spring-batch-core"}
_UI = {"react": "react", "@angular/core": "angular", "vue": "vue"}
_VERSION_REF = re.compile(r"^\$\{(.+)\}$")


class _Build:
    """What a build file declares, whichever tool wrote it."""

    def __init__(self):
        self.main: set[str] = set()  # artifact ids outside test scope
        self.all: set[str] = set()  # also test scope and plugins
        self.java = UNKNOWN
        self.boot = UNKNOWN
        self.problems: list[str] = []
        self.catalog = False

    def add(self, artifact: str, test: bool = False) -> None:
        self.all.add(artifact)
        if not test:
            self.main.add(artifact)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(element, name: str) -> ET.Element | None:
    return next((c for c in element if _local(c.tag) == name), None)


def _text(element, name: str) -> str:
    child = _child(element, name) if element is not None else None
    return child.text.strip() if child is not None and child.text else ""


def _maven(paths: list[Path], root: Path, build: _Build) -> None:
    properties: dict[str, str] = {}
    trees = []
    for path in paths:
        try:
            trees.append(ET.parse(path).getroot())
        except ET.ParseError as exc:
            rel = path.relative_to(root).as_posix()
            build.problems.append(f"{rel}: {exc}")
            # Presence checks only, from the raw text: a broken pom still says what it names.
            text = re.sub(r"<!--.*?-->", "", path.read_text(encoding="utf-8", errors="replace"), flags=re.S)
            for artifact in re.findall(r"<artifactId>\s*([\w.-]+)\s*</artifactId>", text):
                build.all.add(artifact)
    for tree in trees:
        props = _child(tree, "properties")
        for item in props if props is not None else []:
            properties.setdefault(_local(item.tag), (item.text or "").strip())

    def value(text: str) -> str:
        match = _VERSION_REF.match(text)
        if match:
            return properties.get(match.group(1), UNKNOWN)
        return text or UNKNOWN

    for key in ("java.version", "maven.compiler.release", "maven.compiler.source", "maven.compiler.target"):
        if build.java == UNKNOWN and key in properties:
            build.java = value(properties[key])
    for tree in trees:
        parent = _child(tree, "parent")
        if parent is not None and _text(parent, "artifactId") == "spring-boot-starter-parent":
            build.boot = value(_text(parent, "version"))
        for element in tree.iter():
            tag = _local(element.tag)
            if tag not in ("dependency", "plugin"):
                continue
            artifact = _text(element, "artifactId")
            scope = _text(element, "scope")
            managed = _within(tree, element, "dependencyManagement")
            if artifact == "spring-boot-dependencies" and build.boot == UNKNOWN:
                build.boot = value(_text(element, "version"))
            if artifact == "spring-boot-maven-plugin" and build.boot == UNKNOWN and _text(element, "version"):
                build.boot = value(_text(element, "version"))
            if artifact and not managed:
                build.add(artifact, test=tag == "plugin" or scope == "test")
            if tag == "plugin" and artifact == "maven-compiler-plugin" and build.java == UNKNOWN:
                config = _child(element, "configuration")
                for key in ("release", "source"):
                    if build.java == UNKNOWN and _text(config, key):
                        build.java = value(_text(config, key))


def _within(tree, element, name: str) -> bool:
    for holder in tree.iter():
        if _local(holder.tag) == name and any(item is element for item in holder.iter()):
            return True
    return False


_GRADLE_DEP = re.compile(
    r"""\b(\w+)\s*\(?\s*(?:platform\s*\(\s*)?["']([\w.-]+):([\w.-]+)(?::([^"']*))?["']"""
)
_GRADLE_BOOT = re.compile(
    r"""id\s*\(?\s*["']org\.springframework\.boot["']\s*\)?\s*version\s*["']([^"']+)["']"""
)
_GRADLE_PLUGIN = re.compile(r"""\bid\s*\(?\s*["']([\w.-]+)["']""")
_GRADLE_JAVA = (
    re.compile(r"JavaLanguageVersion\.of\(\s*[\"']?(\d+)[\"']?\s*\)"),
    re.compile(r"languageVersion\s*=\s*(\d+)"),
    re.compile(
        r"(?:sourceCompatibility|targetCompatibility)\s*=?\s*[\"']?(?:JavaVersion\.VERSION_)?([\d_.]+)[\"']?"
    ),
)


def _catalog(root: Path) -> tuple[dict[str, tuple[str, str]], dict[str, tuple[str, str]]]:
    """gradle/libs.versions.toml: (libraries, plugins), each alias -> (artifact or plugin id, version).
    Aliases are normalised the way Gradle does: `-`, `_` and `.` are the same separator."""
    path = root / "gradle" / "libs.versions.toml"
    if not path.is_file():
        return {}, {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return {}, {}
    versions = data.get("versions") or {}

    def version(entry) -> str:
        if isinstance(entry, str):
            return entry.split(":")[-1] if entry.count(":") >= 1 else ""
        ref = entry.get("version")
        if isinstance(ref, dict):
            ref = ref.get("ref") and versions.get(ref["ref"]) or ref.get("strictly") or ref.get("require")
        elif ref is None and entry.get("version.ref"):
            ref = versions.get(entry["version.ref"])
        return str(ref or "")

    def key(alias: str) -> str:
        return re.sub(r"[-_.]", ".", alias).lower()

    libraries = {}
    for alias, entry in (data.get("libraries") or {}).items():
        if isinstance(entry, str):
            parts = entry.split(":")
            artifact = parts[1] if len(parts) > 1 else ""
        else:
            module = entry.get("module") or f"{entry.get('group', '')}:{entry.get('name', '')}"
            artifact = module.split(":")[-1]
        libraries[key(alias)] = (artifact, version(entry))
    plugins = {}
    for alias, entry in (data.get("plugins") or {}).items():
        plugin_id = entry.split(":")[0] if isinstance(entry, str) else entry.get("id", "")
        plugins[key(alias)] = (plugin_id, version(entry))
    return libraries, plugins


_CATALOG_DEP = re.compile(r"\b(\w+)\s*\(?\s*(?:platform\s*\(\s*)?libs\.([\w.]+)")
_CATALOG_PLUGIN = re.compile(r"\balias\s*\(\s*libs\.plugins\.([\w.]+)")


def _gradle(paths: list[Path], build: _Build, root: Path | None = None) -> None:
    libraries, plugins = _catalog(root) if root is not None else ({}, {})
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        text = re.sub(r"(?<!:)//[^\n]*|/\*.*?\*/", "", text, flags=re.S)
        for config, _group, artifact, _version in _GRADLE_DEP.findall(text):
            build.add(artifact, test=config.lower().startswith("test"))
        for plugin in _GRADLE_PLUGIN.findall(text):
            build.all.add(plugin)
        boot = _GRADLE_BOOT.search(text)
        if boot and build.boot == UNKNOWN:
            build.boot = boot.group(1)
        for pattern in _GRADLE_JAVA:
            match = pattern.search(text)
            if match and build.java == UNKNOWN:
                build.java = match.group(1).replace("1_", "").replace("_", ".")
        for config, alias in _CATALOG_DEP.findall(text):
            found = libraries.get(alias.lower())
            if found:
                build.add(found[0], test=config.lower().startswith("test"))
            elif not alias.startswith(("plugins.", "versions.", "bundles.")):
                build.catalog = True  # a catalog alias this file does not resolve
        for alias in _CATALOG_PLUGIN.findall(text):
            plugin_id, plugin_version = plugins.get(alias.lower(), ("", ""))
            if plugin_id:
                build.all.add(plugin_id)
                if plugin_id == "org.springframework.boot" and plugin_version and build.boot == UNKNOWN:
                    build.boot = plugin_version
            else:
                build.catalog = True
        if not libraries and not plugins:
            build.catalog = build.catalog or bool(re.search(r"\b\w+\(\s*libs\.", text))


def _names(table: dict[str, set[str]], artifacts: set[str]) -> str:
    found = [name for name, members in table.items() if members & artifacts]
    return ",".join(found) if found else UNKNOWN


def _sha256(paths: list[Path], root: Path) -> str:
    """One build file: its plain hash. Several: the hash of each path and content, in sorted order."""
    if not paths:
        return UNKNOWN
    if len(paths) == 1:
        return hashlib.sha256(paths[0].read_bytes()).hexdigest()
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _package_json(root: Path, row: dict, problems: list[str]) -> None:
    path = root / "package.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("top level is not an object")
    except (ValueError, UnicodeDecodeError) as exc:
        problems.append(f"package.json: {exc}")
        return
    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    ui = next((label for key, label in _UI.items() if key in deps), UNKNOWN)
    if row["ui"] == UNKNOWN:
        row["ui"] = ui
    if row["build"] == "npm":
        scripts = data.get("scripts", {})
        tool = (
            "pnpm"
            if (root / "pnpm-lock.yaml").is_file()
            else "yarn"
            if (root / "yarn.lock").is_file()
            else "npm"
        )
        if "build" in scripts:
            row["buildCmd"] = f"{tool} run build"
        if "test" in scripts:
            row["testCmd"] = f"{tool} test" if tool == "npm" else f"{tool} run test"


def detect_stack(sources: Sources) -> dict:
    """One schema row, plus `problems` and `testcontainers`, which the caller takes off before validating."""
    root = sources.repo.path
    poms = [root / m / "pom.xml" for m in sources.module_roots if (root / m / "pom.xml").is_file()]
    gradles = [
        root / m / name
        for m in sources.module_roots
        for name in ("build.gradle", "build.gradle.kts")
        if (root / m / name).is_file()
    ]
    has_npm = (root / "package.json").is_file()
    row = {
        "repo": sources.repo.name,
        "build": UNKNOWN,
        "buildCmd": UNKNOWN,
        "testCmd": UNKNOWN,
        "java": UNKNOWN,
        "springBoot": UNKNOWN,
        "batch": False,
        "datastore": UNKNOWN,
        "messaging": UNKNOWN,
        "web": UNKNOWN,
        "ui": UNKNOWN,
        "packageRoot": UNKNOWN,
        "archunit": "missing",
        "pitest": "missing",
        "buildFileSha256": UNKNOWN,
    }
    build = _Build()
    if poms:
        _maven(poms, root, build)
    if gradles:
        _gradle(gradles, build, root)
    if poms and gradles:
        build.problems.append("both Maven and Gradle build files at this repo: which one builds it?")
    elif poms:
        tool = "./mvnw" if (root / "mvnw").is_file() else "mvn"
        row.update(build="maven", buildCmd=f"{tool} -q verify", testCmd=f"{tool} -q test")
    elif gradles:
        tool = "./gradlew" if (root / "gradlew").is_file() else "gradle"
        row.update(build="gradle", buildCmd=f"{tool} build", testCmd=f"{tool} test")
    elif has_npm:
        row["build"] = "npm"
    row["buildFileSha256"] = _sha256(poms + gradles or ([root / "package.json"] if has_npm else []), root)
    if has_npm:
        _package_json(root, row, build.problems)
    row.update(
        java=build.java,
        springBoot=build.boot,
        batch=bool(_BATCH & build.main),
        datastore=_names(_DATASTORE, build.main),
        messaging=_names(_MESSAGING, build.main),
        web=_names(_WEB, build.main),
    )
    row["archunit"] = "installed" if any("archunit" in a for a in build.all) else "missing"
    row["pitest"] = "installed" if any("pitest" in a for a in build.all) else "missing"
    if build.catalog:
        build.problems.append("dependencies come through a version catalog (libs.*), which is not read")
    row["packageRoot"], layout, notes = detect_layout(sources.main)
    if sources.main:
        row["layout"] = layout
    build.problems += notes
    row["problems"] = build.problems
    row["testcontainers"] = any("testcontainers" in a for a in build.all)
    return row


def _stereotype(decl: TypeDecl) -> str | None:
    if decl.annotation("RestController", "Controller", "Repository", "FeignClient"):
        return "adapters"
    if decl.annotation("Service"):
        return "application"
    if decl.annotation("Document", "Entity"):
        return "domain"
    method_names = {a.name for m in decl.methods for a in m.annotations}
    if method_names & {"KafkaListener", "JmsListener", "RabbitListener"}:
        return "adapters"
    if decl.kind == "interface" and any(r.name.endswith("Repository") for r in decl.extends):
        return "adapters"
    builders = {c.new.value for c in decl.chains if c.new is not None}
    if builders & {"JobBuilder", "StepBuilder"}:
        return "adapters"
    return None


def _common_package(packages: list[str]) -> str:
    if not packages:
        return ""
    split = [p.split(".") for p in packages]
    common = []
    for parts in zip(*split, strict=False):
        if len(set(parts)) != 1:
            break
        common.append(parts[0])
    return ".".join(common)


def detect_layout(files: list[JavaFile]) -> tuple[str, dict, list[str]]:
    """(package root, layer map, notes). A layer is one package directly under the root that every class with
    that stereotype sits in. Split or shared packages are `unknown`, and the note says why."""
    mains = [f.package for f in files for t in f.types if t.annotation("SpringBootApplication")]
    root = (
        sorted(set(mains))[0]
        if len(set(mains)) == 1
        else _common_package([f.package for f in files if f.package])
    )
    layout = {"adapters": UNKNOWN, "application": UNKNOWN, "domain": UNKNOWN}
    notes: list[str] = []
    if not root:
        return UNKNOWN, layout, notes
    seats: dict[str, set[str]] = {layer: set() for layer in layout}
    for parsed in files:
        for decl in parsed.types:
            layer = _stereotype(decl)
            if layer is None:
                continue
            below = parsed.package[len(root) + 1 :] if parsed.package.startswith(root + ".") else ""
            seats[layer].add(below.split(".")[0] if below else "")
    for layer, segments in seats.items():
        if len(segments) == 1 and "" not in segments:
            layout[layer] = f"{root}.{next(iter(segments))}"
        elif segments:
            shown = ", ".join(sorted(s or "(package root)" for s in segments))
            notes.append(f"layout: {layer} classes are split across {shown}")
    values = [v for v in layout.values() if v != UNKNOWN]
    for layer, value in list(layout.items()):
        if value != UNKNOWN and values.count(value) > 1:
            notes.append(f"layout: {layer} shares {value} with another layer")
            layout[layer] = UNKNOWN
    return root, layout, notes
