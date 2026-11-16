"""Runs PIT on changed classes and reduces its XML report to mutation.json. Stdlib only.

The score counts only mutants on lines the diff added or changed, and skips logging lines, as Google's
diff-based mutation testing does (Petrovic et al., TSE 2021): whole-class scores mostly measure code the
story did not touch. PIT runs on several threads and keeps its history, so a fix loop reruns faster.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

GIT = "git"
MAIN_MARKER = "src/main/java/"
TEST_MARKER = "src/test/java/"
KILLED = {"KILLED", "TIMED_OUT", "MEMORY_ERROR"}
LOG_TAIL_LINES = 15
GENERATED_DIRS = {"node_modules", ".git"}
# "arid" lines: a mutant there says nothing about the tests (logging, printing)
ARID = re.compile(
    r"^\s*(?:log|logger|LOG|LOGGER|log\w*)\.(?:trace|debug|info|warn|error)\(|^\s*System\.(?:out|err)\."
)
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


class DiffError(Exception):
    """The repo or the ref cannot be read."""


def classes_from_paths(paths: list[str]) -> list[str]:
    classes = set()
    for path in paths:
        if MAIN_MARKER not in path or not path.endswith(".java"):
            continue
        relative = path.split(MAIN_MARKER, 1)[1].removesuffix(".java")
        if relative.rsplit("/", 1)[-1] in ("package-info", "module-info"):
            continue
        classes.add(relative.replace("/", "."))
    return sorted(classes)


def _clean_env() -> dict[str, str]:
    """Without GIT_*: under a git hook they would point these commands at the wrong repository."""
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def changed_classes(repo: Path, diff_ref: str) -> list[str]:
    done = subprocess.run([GIT, "-C", str(repo), "diff", "--name-only", "--diff-filter=d", diff_ref, "--"],
                          capture_output=True, text=True, env=_clean_env())
    if done.returncode:
        raise DiffError(done.stderr.strip() or f"git diff {diff_ref} failed")
    return classes_from_paths(done.stdout.splitlines())


def changed_lines(repo: Path, diff_ref: str) -> dict[str, set[int]]:
    """Repo-relative path of each changed main Java file -> the line numbers the diff added or changed."""
    done = subprocess.run([GIT, "-C", str(repo), "diff", "-U0", "--diff-filter=d", diff_ref, "--", "*.java"],
                          capture_output=True, text=True, env=_clean_env())
    if done.returncode:
        raise DiffError(done.stderr.strip() or f"git diff {diff_ref} failed")
    lines: dict[str, set[int]] = {}
    current = None
    for line in done.stdout.splitlines():
        if line.startswith("+++ "):
            path = line[4:].removeprefix("b/")
            current = path if MAIN_MARKER in path else None
            if current:
                lines.setdefault(current, set())
        elif current and (hunk := _HUNK.match(line)):
            start, count = int(hunk.group(1)), int(hunk.group(2) or 1)
            lines[current].update(range(start, start + count))
    return lines


def _source_path(mutated: str, changed: dict[str, set[int]]) -> str | None:
    """The changed file a mutated class lives in: `a.b.Fee$Inner` is in .../src/main/java/a/b/Fee.java."""
    suffix = MAIN_MARKER + mutated.split("$", 1)[0].replace(".", "/") + ".java"
    return next((path for path in changed if path.endswith(suffix)), None)


def _is_changed(mutated: str, changed: set[str]) -> bool:
    return mutated.split("$", 1)[0] in changed


def count_mutations(
    reports: list[Path],
    changed: list[str],
    lines: dict[str, set[int]] | None = None,
    repo: Path | None = None,
) -> dict[str, int]:
    """Counts only changed classes: a build whose config ignores targetClasses cannot widen the score.

    With `lines`, only mutants on a changed line count, and a mutant on an arid line of `repo` is skipped.
    """
    wanted = set(changed)
    counts = {"killed": 0, "survived": 0, "noCoverage": 0}
    sources: dict[str, list[str]] = {}
    for report in reports:
        for mutation in ET.parse(report).getroot().iter("mutation"):
            mutated = mutation.findtext("mutatedClass", "")
            if not _is_changed(mutated, wanted):
                continue
            if lines is not None:
                path = _source_path(mutated, lines)
                number = int(mutation.findtext("lineNumber", "0") or 0)
                if path is None or number not in lines[path]:
                    continue
                if repo is not None:
                    if path not in sources:
                        file = repo / path
                        text = file.read_text(errors="replace") if file.is_file() else ""
                        sources[path] = text.splitlines()
                    text = sources[path][number - 1] if 0 < number <= len(sources[path]) else ""
                    if ARID.match(text):
                        continue
            status = mutation.get("status", "")
            if status in KILLED:
                counts["killed"] += 1
            elif status == "SURVIVED":
                counts["survived"] += 1
            elif status == "NO_COVERAGE":
                counts["noCoverage"] += 1
    return counts


def score(counts: dict[str, int]) -> float | None:
    """PIT's own definition: detected / all viable mutants, so uncovered mutants lower the score."""
    total = counts["killed"] + counts["survived"] + counts["noCoverage"]
    return round(counts["killed"] / total, 4) if total else None


def _reports(repo: Path, pattern: str) -> list[Path]:
    return [p for p in repo.rglob(pattern) if not GENERATED_DIRS.intersection(p.relative_to(repo).parts)]


def _read(path: Path) -> str:
    return path.read_text(errors="replace") if path.is_file() else ""


def _test_packages(repo: Path) -> str | None:
    """The longest package shared by the repo's tests: the group id need not match the package."""
    packages = []
    for path in repo.rglob("*.java"):
        posix = path.relative_to(repo).as_posix()
        if TEST_MARKER in posix and "/" in posix.split(TEST_MARKER, 1)[1]:
            packages.append(posix.split(TEST_MARKER, 1)[1].rsplit("/", 1)[0].split("/"))
    if not packages:
        return None
    common = os.path.commonprefix(packages)
    return ".".join(common) + ".*" if common else None


def _tool(repo: Path, wrapper: str, plain: str) -> str | None:
    if (repo / wrapper).is_file():
        return f"./{wrapper}"
    return shutil.which(plain)


def _targets(classes: list[str]) -> str:
    return ",".join(f"{name},{name}$*" for name in classes)


def _threads() -> int:
    """PIT runs on one thread unless told; leave one core for the machine."""
    return max(1, (os.cpu_count() or 2) - 1)


def plan(repo: Path, classes: list[str]) -> tuple[list[str] | None, str, str | None]:
    """Returns (command, report glob, reason it cannot run)."""
    gradle_file = next((f for f in ("build.gradle.kts", "build.gradle") if (repo / f).is_file()), None)
    tests = _test_packages(repo)
    if (repo / "pom.xml").is_file():
        report = "target/pit-reports/mutations.xml"
        if "pitest-maven" not in _read(repo / "pom.xml"):
            return None, report, "PIT is not installed: pom.xml has no pitest-maven plugin"
        tool = _tool(repo, "mvnw", "mvn")
        if tool is None:
            return None, report, "no build tool: neither ./mvnw nor mvn on PATH"
        command = [tool, "-B", "-q", "test-compile", "org.pitest:pitest-maven:mutationCoverage",
                   f"-DtargetClasses={_targets(classes)}", "-DoutputFormats=XML",
                   "-DtimestampedReports=false", "-DfailWhenNoMutations=false",
                   f"-Dthreads={_threads()}", "-DwithHistory=true"]
        return command + ([f"-DtargetTests={tests}"] if tests else []), report, None
    if gradle_file:
        report = "build/reports/pitest/mutations.xml"
        if "pitest" not in _read(repo / gradle_file):
            return None, report, f"PIT is not installed: {gradle_file} has no pitest plugin"
        tool = _tool(repo, "gradlew", "gradle")
        if tool is None:
            return None, report, "no build tool: neither ./gradlew nor gradle on PATH"
        targets = _targets(classes)
        # podTarget*, harnessTarget*: the property names build files installed before the renames still use
        command = [tool, "--no-daemon", "-q", "pitest"] + [f"-P{p}TargetClasses={targets}" for p in _PREFIXES]
        extra = [f"-P{p}TargetTests={tests}" for p in _PREFIXES] if tests else []
        return command + extra, report, None
    return None, "", "no pom.xml or build.gradle(.kts): PIT cannot run in this repo"


_PREFIXES = ("baton", "pod", "harness")


def _tail(text: str) -> str:
    return "\n".join(text.strip().splitlines()[-LOG_TAIL_LINES:])


def run_pit(repo: Path, classes: list[str], timeout: int) -> tuple[list[Path], str | None]:
    """Returns (reports, reason it did not run)."""
    command, report_glob, reason = plan(repo, classes)
    if command is None:
        return [], reason
    for stale in _reports(repo, report_glob):
        stale.unlink()
    try:
        done = subprocess.run(command, cwd=repo, capture_output=True, text=True, timeout=timeout,
                              env=_clean_env())
    except subprocess.TimeoutExpired:
        return [], f"build timed out after {timeout}s"
    if done.returncode:
        return [], f"build failed (exit {done.returncode}): {_tail(done.stdout + done.stderr)}"
    return _reports(repo, report_glob), None


def measure(repo: Path, repo_name: str, diff_ref: str, timeout: int) -> dict:
    classes = changed_classes(repo, diff_ref)
    result = {"repo": repo_name, "diffRef": diff_ref, "changedClasses": classes,
              "notRun": True, "reason": None}
    if not classes:
        result["reason"] = "no changed classes under src/main/java in this diff"
        return result
    reports, reason = run_pit(repo, classes, timeout)
    if reason:
        result["reason"] = reason
        return result
    whole = count_mutations(reports, classes)
    try:
        on_lines = count_mutations(reports, classes, changed_lines(repo, diff_ref), repo)
    except DiffError:
        on_lines = {"killed": 0, "survived": 0, "noCoverage": 0}
    # changed lines when PIT reported line numbers for them; else the changed classes, as before
    counts, scope = (on_lines, "changed lines") if score(on_lines) is not None else (whole, "changed classes")
    value = score(counts)
    if value is None:
        result["reason"] = "PIT ran but generated no mutations for the changed classes"
        return result
    return {**result, "score": value, **counts, "scope": scope, "classScore": score(whole), "notRun": False}
