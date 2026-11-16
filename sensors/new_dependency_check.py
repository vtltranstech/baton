#!/usr/bin/env python3
"""New-dependency sensor: lists dependencies declared in a repo's build files but not at the base ref.

Usage: new_dependency_check.py --repo <path> --base <ref>
Reads pom.xml, build.gradle(.kts) and package.json at every depth, skipping generated directories.
Exit 0 none new; 1 new dependency, one `REMEDIATION:` line per finding; 2 not a git repo or bad ref. Stdlib only.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

BUILD_FILES = ("pom.xml", "build.gradle", "build.gradle.kts", "package.json")
SKIP_DIRS = {"node_modules", "target", "build", ".git", ".gradle"}
GRADLE_DEP = re.compile(
    r"""\b(?:implementation|api|compileOnly|runtimeOnly|annotationProcessor|developmentOnly|
    testImplementation|testCompileOnly|testRuntimeOnly|testAnnotationProcessor)\b
    \s*\(?\s*["']([^:"']+:[^:"']+)""",
    re.VERBOSE,
)


def maven_deps(text):
    root = ET.fromstring(text)
    found = set()
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "dependency":
            continue
        parts = {child.tag.rsplit("}", 1)[-1]: (child.text or "").strip() for child in element}
        if parts.get("groupId") and parts.get("artifactId"):
            found.add(f"{parts['groupId']}:{parts['artifactId']}")
    return found


def npm_deps(text):
    data = json.loads(text)
    found = set()
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        found.update(data.get(key, {}))
    return found


def declared(name, text):
    if name == "pom.xml":
        return maven_deps(text)
    if name == "package.json":
        return npm_deps(text)
    return set(GRADLE_DEP.findall(text))


def build_files(repo):
    for path in sorted(repo.rglob("*")):
        relative = path.relative_to(repo)
        if path.name in BUILD_FILES and path.is_file() and not SKIP_DIRS.intersection(relative.parts):
            yield relative


def git(repo, *args):
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=env)


def at_ref(repo, ref, relative):
    done = git(repo, "show", f"{ref}:{relative.as_posix()}")
    return done.stdout if done.returncode == 0 else None


def findings(repo, base):
    for relative in build_files(repo):
        current = declared(relative.name, (repo / relative).read_text())
        old_text = at_ref(repo, base, relative)
        old = declared(relative.name, old_text) if old_text is not None else set()
        for dep in sorted(current - old):
            yield relative.as_posix(), dep


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base", required=True, help="git ref to compare against, e.g. main")
    args = parser.parse_args(argv)
    repo = Path(args.repo)
    check = git(repo, "rev-parse", "--verify", f"{args.base}^{{commit}}")
    if check.returncode:
        print(f"new-dependency: cannot resolve {args.base} in {repo}", file=sys.stderr)
        return 2
    found = list(findings(repo, args.base))
    for file, dep in found:
        print(f"{file}: new dependency {dep}. REMEDIATION: remove it, or record why it is needed in the design note "
              "and have the Tech Lead accept it (a new dependency caps confidence at 70)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
