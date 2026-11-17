"""Compute the gate-3 confidence score from a story's artefacts (contracts/confidence.md).

Stdlib only. This tool is the only reader of profile/confidence-weights.yaml. A missing input scores 0
and is listed under `missing`; nothing is assumed. Refused (exit 2, no file): unusable weights, no story.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from baton import miniyaml, state_check
from baton.state_check import Story, section

SIGNALS = (
    "definition_of_ready",
    "design_review",
    "change_size",
    "sensors",
    "mutation",
    "acceptance_coverage",
    "independent_review",
    "conformance_fidelity",
    "blast_radius",
)
CAPS = ("risk_zone", "breaking_contract", "unprofiled_write", "unknown_edges", "new_dependency")
THRESHOLDS = {"change_size_files": 5, "mutation_full": 0.80, "mutation_half": 0.60, "sensors_loops_half": 2}
# The plan's point tables as fractions, so a recalibrated weight keeps the same shape.
DESIGN_AUTO, DESIGN_CHANGES = 8 / 10, 5 / 10
CHANGE_HALF, SENSORS_HALF, MUTATION_HALF = 5 / 10, 6 / 10, 5 / 10
REVIEW_MEDIUM, CONFORMANCE_DEVIATION, BLAST_NEAR = 10 / 15, 5 / 10, 8 / 15


class Refused(Exception):
    """The score cannot be computed honestly; the message must not reveal any weight."""


def _number(value: float) -> float | int:
    value = round(value, 2)
    return int(value) if value == int(value) else value


def load_weights(central: Path) -> dict:
    path = central / "profile" / "confidence-weights.yaml"
    if not path.is_file():
        raise Refused("profile/confidence-weights.yaml is missing; the Senior Engineer owns it")
    try:
        data = miniyaml.load_file(str(path))
    except (ValueError, OSError) as exc:
        raise Refused(f"profile/confidence-weights.yaml cannot be parsed ({type(exc).__name__})") from exc
    if not isinstance(data, dict):
        raise Refused("profile/confidence-weights.yaml is not a mapping")
    for key, kind in (
        ("version", int),
        ("signals", dict),
        ("caps", dict),
        ("policy", dict),
        ("thresholds", dict),
    ):
        if not isinstance(data.get(key), kind):
            raise Refused(f"profile/confidence-weights.yaml: `{key}` is missing or has the wrong type")
    signals = data["signals"]
    for name in SIGNALS:
        value = signals.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100:
            raise Refused(f"profile/confidence-weights.yaml: signal `{name}` is missing or not 0-100")
    if sum(signals[name] for name in SIGNALS) != 100 or set(signals) != set(SIGNALS):
        raise Refused("profile/confidence-weights.yaml: the signals must be exactly the nine and sum to 100")
    for name in CAPS:
        if not isinstance(data["caps"].get(name), int):
            raise Refused(f"profile/confidence-weights.yaml: cap `{name}` is missing")
    for name in ("fast_lane_min", "senior_min"):
        if not isinstance(data["policy"].get(name), int):
            raise Refused(f"profile/confidence-weights.yaml: policy `{name}` is missing")
    data["thresholds"] = {**THRESHOLDS, **data["thresholds"]}
    return data


def read_json(path: Path) -> tuple[dict | None, str | None]:
    """(document, None), or (None, why) for an absent or unreadable file."""
    if not path.is_file():
        return None, "not present"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None, "unreadable"
    return (document, None) if isinstance(document, dict) else (None, "unreadable")


def per_repo(story: Story, name: str) -> tuple[list[tuple[Path, dict]], list[str]]:
    """`-<name>.json` holds one repo; a multi-repo story adds `-<name>-<repo>.json`. (docs, unreadable)."""
    paths = [story.qa(f"{name}.json")] if story.qa(f"{name}.json").is_file() else []
    paths += sorted(story.qa("x").parent.glob(f"{story.story_id}-{name}-*.json"))
    documents, bad = [], []
    for path in paths:
        document, why = read_json(path)
        if document is None:
            bad.append(f"{path.name} ({why})")
        else:
            documents.append((path, document))
    return documents, bad


def project_value(central: Path, key: str) -> str | None:
    path = central / "profile" / "project.md"
    if not path.is_file():
        return None
    match = re.search(rf"^\|\s*{re.escape(key)}\s*\|\s*([^|]*?)\s*\|", path.read_text(encoding="utf-8"), re.M)
    return match.group(1) if match else None


def header_value(text: str, key: str) -> str | None:
    match = re.search(rf"^{re.escape(key)}:[ \t]*(.*?)[ \t]*$", text, re.M | re.I)
    return match.group(1) if match and match.group(1) else None


def glob_regex(pattern: str) -> re.Pattern:
    """Gitignore-style: `**` spans directories, `*` does not, a pattern with no slash matches any depth."""
    anchored = "/" in pattern.rstrip("/")
    pattern = pattern.lstrip("/")
    out, index = [], 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            out.append(r"(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            out.append(r".*")
            index += 2
        elif pattern[index] == "*":
            out.append(r"[^/]*")
            index += 1
        elif pattern[index] == "?":
            out.append(r"[^/]")
            index += 1
        else:
            out.append(re.escape(pattern[index]))
            index += 1
    body = "".join(out)
    if pattern.endswith("/"):
        body += ".*"
    return re.compile(("^" if anchored else r"^(?:.*/)?") + body + r"(?:/.*)?$")


def diff_files(diff: dict | None) -> list[tuple[str, str]]:
    """(repo, repo-relative path) for every file in -diff-shape.json."""
    if not diff:
        return []
    return [
        (repo.get("repo", ""), str(path))
        for repo in diff.get("repos") or []
        for path in repo.get("files") or []
    ]


def diff_lines(diff: dict) -> int:
    return sum(int(r.get("linesAdded", 0)) + int(r.get("linesDeleted", 0)) for r in diff.get("repos") or [])


def sensor_status(sensors: Path) -> dict[str, tuple[str, str]]:
    """Per tool present: (green|red, why). ArchUnit is always in the result, absent or not."""
    result = {}
    ok, why = state_check.archunit_status(sensors / "archunit.txt")
    result["archunit"] = ("green" if ok else "absent" if "not present" in why else "red", why)
    pmd = sensors / "pmd.xml"
    if pmd.is_file():
        count = pmd.read_text(errors="replace").count("<violation")
        result["pmd"] = ("green" if not count else "red", f"pmd.xml: {count} violations")
    style = sensors / "checkstyle.xml"
    if style.is_file():
        count = len(re.findall(r"<error\b", style.read_text(errors="replace")))
        result["checkstyle"] = ("green" if not count else "red", f"checkstyle.xml: {count} errors")
    axe = sensors / "axe.json"
    if axe.is_file():
        try:
            pages = json.loads(axe.read_text())
            pages = pages if isinstance(pages, list) else [pages]
            bad = sum(
                1
                for page in pages
                for v in (page or {}).get("violations") or []
                if (v or {}).get("impact") in ("serious", "critical")
            )
            result["axe"] = ("green" if not bad else "red", f"axe.json: {bad} serious or critical")
        except (ValueError, AttributeError, TypeError):
            result["axe"] = ("red", "axe.json is unreadable")
    eslint = sensors / "eslint.json"
    if eslint.is_file():
        try:
            count = sum(int(entry.get("errorCount", 0)) for entry in json.loads(eslint.read_text()))
            result["eslint"] = ("green" if not count else "red", f"eslint.json: {count} errors")
        except (ValueError, AttributeError, TypeError):
            result["eslint"] = ("red", "eslint.json is unreadable")
    return result


def triage_counts(text: str) -> dict[str, int] | None:
    """The `## Counts` block review-lenses writes: `HIGH: n`, `MEDIUM: n`, `LOW: n`. None when absent."""
    body = section(text, "Counts")
    if body is None:
        return None
    counts = {}
    for level in ("HIGH", "MEDIUM", "LOW"):
        match = re.search(rf"^\W*{level}\W+(\d+)\b", body, re.M | re.I)
        if not match:
            return None
        counts[level] = int(match.group(1))
    return counts


def ac_table(report: str) -> list[dict[str, str]]:
    rows, header = [], None
    for line in report.splitlines():
        if not line.lstrip().startswith("|"):
            header = None
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if header is None:
            header = [cell.casefold() for cell in cells]
            if not header or header[0] != "ac":
                header = []
            continue
        if not header or all(set(cell) <= set("-: ") for cell in cells):
            continue
        rows.append(dict(zip(header, cells, strict=False)))
    return rows


def story_acs(text: str) -> list[str]:
    body = section(text, "Acceptance criteria") or ""
    return re.findall(r"^\s*[-*]\s*\**(AC\d+)\b", body, re.M)


class _Scorer:
    def __init__(self, story: Story, text: str, weights: dict):
        self.story, self.text, self.weights = story, text, weights
        self.central = story.central
        self.signals: dict[str, dict] = {}
        self.caps: list[dict] = []
        self.missing: list[str] = []
        self.source = story.rel(story.path)
        self.diff, self.diff_why = read_json(story.qa("diff-shape.json"))
        self.diff_rel = story.rel(story.qa("diff-shape.json"))
        self.impact_blind = False
        self.impact_rel = story.rel(story.qa("impact.json"))
        self.report = self._text(story.qa("test-report.md"))
        self.report_rel = story.rel(story.qa("test-report.md"))

    @staticmethod
    def _text(path: Path) -> str | None:
        return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else None

    def _miss(self, name: str) -> None:
        if name not in self.missing:
            self.missing.append(name)

    def _score(self, name: str, fraction: float, evidence: str) -> None:
        maximum = self.weights["signals"][name]
        self.signals[name] = {"points": _number(maximum * fraction), "max": maximum, "evidence": evidence}

    def definition_of_ready(self) -> None:
        body = section(self.text, "Readiness")
        if body is None:
            self._miss("story ## Readiness")
            return self._score("definition_of_ready", 0, f"{self.source}: no ## Readiness section")
        ratio = re.search(r"score\W+(\d+)\s*/\s*(\d+)", body, re.I)
        decimal = re.search(r"score\W+(\d+(?:\.\d+)?)\s*(%?)", body, re.I)
        if ratio and int(ratio.group(2)):
            value, shown = int(ratio.group(1)) / int(ratio.group(2)), f"{ratio.group(1)}/{ratio.group(2)}"
        elif decimal:
            value = float(decimal.group(1)) / (100 if decimal.group(2) else 1)
            shown = decimal.group(1) + decimal.group(2)
        else:
            self._miss("story ## Readiness score")
            return self._score("definition_of_ready", 0, f"{self.source}: ## Readiness has no score")
        self._score("definition_of_ready", 1 if value == 1 else 0, f"{self.source}: Readiness {shown}")

    def design_review(self) -> None:
        body = section(self.text, "Design review")
        if body is None:
            self._miss("story ## Design review")
            return self._score("design_review", 0, f"{self.source}: no ## Design review section")
        if re.search(r"auto-passed", body):
            return self._score("design_review", DESIGN_AUTO, f"{self.source}: design review auto-passed")
        if re.search(r"(?<![Nn]ot )\bApproved\b", body):
            if re.search(r"changes requested", body, re.I):
                return self._score("design_review", DESIGN_CHANGES, f"{self.source}: approved after changes")
            return self._score("design_review", 1, f"{self.source}: approved first round")
        self._score("design_review", 0, f"{self.source}: design review not approved")

    def change_size(self) -> None:
        if self.diff is None:
            self._miss("diff-shape.json")
            return self._score("change_size", 0, f"{self.diff_rel}: {self.diff_why}")
        estimate = (header_value(self.text, "Estimate") or "").split(" ")[0].strip()
        limit = project_value(self.central, f"estimate.lines.{estimate}")
        if not limit or not limit.isdigit():
            self._miss(f"estimate.lines.{estimate or '?'} in profile/project.md")
            return self._score("change_size", 0, f"{self.source}: no line limit for estimate `{estimate}`")
        lines, files = diff_lines(self.diff), len(diff_files(self.diff))
        shown = f"{self.diff_rel}: {lines} lines against {limit} for {estimate}, {files} files"
        if lines > int(limit):
            return self._score("change_size", 0, shown)
        if files <= self.weights["thresholds"]["change_size_files"]:
            return self._score("change_size", 1, shown)
        self._score("change_size", CHANGE_HALF, shown)

    def sensors(self) -> None:
        folder = self.story.qa("sensors")
        rel = self.story.rel(folder)
        status = sensor_status(folder)
        state, why = status["archunit"]
        if state != "green":
            self.caps.append({"name": "archunit", "cap": 0, "evidence": f"{rel}/{why}"})
            if state == "absent":
                self._miss("sensors/archunit.txt")
            return self._score("sensors", 0, f"{rel}/{why}")
        others = [name for name in status if name != "archunit"]
        if not others:
            self._miss("sensors/pmd.xml or checkstyle.xml or eslint.json")
            return self._score("sensors", 0, f"{rel}: only archunit.txt present")
        red = [name for name, (value, _) in status.items() if value != "green"]
        if red:
            return self._score("sensors", 0, f"{rel}: red: {', '.join(red)}")
        loops = (self.diff or {}).get("sensorLoops")
        if not isinstance(loops, int) or isinstance(loops, bool):
            self._miss("sensorLoops in diff-shape.json")
            return self._score("sensors", 0, f"{rel}: all green, loops unknown ({self.diff_rel})")
        shown = f"{rel}: all green, {loops} loops ({self.diff_rel})"
        if loops == 0:
            return self._score("sensors", 1, shown)
        half = loops <= self.weights["thresholds"]["sensors_loops_half"]
        self._score("sensors", SENSORS_HALF if half else 0, shown)

    def mutation(self) -> None:
        rel = self.story.rel(self.story.qa("mutation.json"))
        documents, bad = per_repo(self.story, "mutation")
        if bad or not documents:
            self._miss("mutation.json")
            return self._score("mutation", 0, f"{rel}: {', '.join(bad) or 'not present'}")
        uncovered = self._repos_without(documents, "repo")
        if uncovered:
            self._miss(f"mutation.json for {', '.join(uncovered)}")
            return self._score("mutation", 0, f"{rel}: no mutation run for {', '.join(uncovered)}")
        lowest = None
        for path, document in documents:
            score = document.get("score")
            if document.get("notRun") or not isinstance(score, (int, float)) or isinstance(score, bool):
                reason = document.get("reason") or "no score"
                return self._score("mutation", 0, f"{self.story.rel(path)}: not run ({reason})")
            if lowest is None or score < lowest[0]:
                lowest = (score, path)
        score, path = lowest
        thresholds = self.weights["thresholds"]
        full, half = thresholds["mutation_full"], thresholds["mutation_half"]
        fraction = 1 if score >= full else MUTATION_HALF if score >= half else 0
        self._score("mutation", fraction, f"{self.story.rel(path)}: score {score:.2f}")

    def _repos_without(self, documents: list[tuple[Path, dict]], key: str) -> list[str]:
        """A multi-repo story needs a document per repo: one clean repo says nothing of the others."""
        repos = [r.get("repo") for r in (self.diff or {}).get("repos") or []]
        if len(repos) < 2:
            return []
        covered = {document.get(key) for _, document in documents}
        return [repo for repo in repos if repo not in covered]

    def acceptance_coverage(self) -> None:
        if self.report is None:
            self._miss("test-report.md")
            return self._score("acceptance_coverage", 0, f"{self.report_rel}: not present")
        rows = ac_table(self.report)
        if not rows:
            self._miss("AC table in test-report.md")
            return self._score("acceptance_coverage", 0, f"{self.report_rel}: no AC table")
        executed = {
            row["ac"].strip("* ")
            for row in rows
            if row.get("test", "").strip(" -—")
            and row.get("test", "").casefold() not in ("none", "n/a")
            and re.match(r"(?i)\W*(pass|fail)", row.get("result", ""))
        }
        wanted = story_acs(self.text) or [row["ac"].strip("* ") for row in rows]
        absent = [ac for ac in wanted if ac not in executed]
        if absent:
            shown = f"{self.report_rel}: no executing test for {', '.join(absent)}"
            return self._score("acceptance_coverage", 0, shown)
        self._score("acceptance_coverage", 1, f"{self.report_rel}: {len(wanted)}/{len(wanted)} ACs executed")

    def independent_review(self) -> None:
        path = self.story.qa("triage.md")
        rel = self.story.rel(path)
        text = self._text(path)
        if text is None:
            self._miss("triage.md")
            return self._score("independent_review", 0, f"{rel}: not present")
        counts = triage_counts(text)
        if counts is None:
            self._miss("## Counts in triage.md")
            return self._score("independent_review", 0, f"{rel}: no ## Counts block")
        shown = f"{rel}: HIGH {counts['HIGH']}, MEDIUM {counts['MEDIUM']}, LOW {counts['LOW']}"
        if counts["HIGH"]:
            return self._score("independent_review", 0, shown)
        self._score("independent_review", REVIEW_MEDIUM if counts["MEDIUM"] else 1, shown)

    def _domain_lens_skipped(self) -> bool:
        """True only when -risk.json says low and leaves the domain lens out, and the report says not run."""
        risk, _ = read_json(self.story.qa("risk.json"))
        if not risk or risk.get("tier") != "low" or "domain" in (risk.get("lenses") or []):
            return False
        return bool(re.search(r"^Domain fidelity:\s*not run", self.report or "", re.M | re.I))

    def conformance_fidelity(self) -> None:
        if self.report is None:
            self._miss("test-report.md")
            return self._score("conformance_fidelity", 0, f"{self.report_rel}: not present")
        conformance = header_value(self.report, "Conformance")
        fidelity = re.search(r"^Domain fidelity:.*?(\d+)\s+reinterpreted", self.report, re.M | re.I)
        if fidelity:
            reinterpreted = int(fidelity.group(1))
        elif conformance and self._domain_lens_skipped():
            reinterpreted = 0  # low risk and no rule touched: conformance alone decides
        else:
            reinterpreted = None
        if not conformance or "|" in conformance or reinterpreted is None:
            self._miss("Conformance / Domain fidelity in test-report.md")
            return self._score(
                "conformance_fidelity", 0, f"{self.report_rel}: conformance or fidelity not filled in"
            )
        verdict = re.sub(r"\s*\(.*$", "", conformance).strip().upper()
        shown = f"{self.report_rel}: {verdict}, {reinterpreted} reinterpreted"
        ui = self.story.qa("ui-verify.json")
        if ui.is_file():
            try:
                levels = {m.get("severity") for m in json.loads(ui.read_text()).get("mismatches") or []}
            except (ValueError, AttributeError, TypeError):
                levels = {"HIGH"}
            shown += f"; {self.story.rel(ui)}: " + (", ".join(sorted(levels)) or "conforms")
            if "HIGH" in levels:
                return self._score("conformance_fidelity", 0, shown)
            if "MEDIUM" in levels and verdict == "CONFORMS":
                return self._score("conformance_fidelity", CONFORMANCE_DEVIATION, shown)
        if verdict == "DEVIATES" or reinterpreted:
            return self._score("conformance_fidelity", 0, shown)
        if verdict == "CONFORMS":
            return self._score("conformance_fidelity", 1, shown)
        if "DEVIATION" in verdict:
            return self._score("conformance_fidelity", CONFORMANCE_DEVIATION, shown)
        self._score("conformance_fidelity", 0, shown)

    def blast_radius(self) -> None:
        documents, bad = per_repo(self.story, "impact")
        if bad or not documents:
            self._miss("impact.json")
            self.impact_blind = True
            return self._score("blast_radius", 0, f"{self.impact_rel}: {', '.join(bad) or 'not present'}")
        uncovered = self._repos_without(documents, "sourceRepo")
        if uncovered:
            self._miss(f"impact.json for {', '.join(uncovered)}")
            self.impact_blind = True
            return self._score(
                "blast_radius", 0, f"{self.impact_rel}: no impact run for {', '.join(uncovered)}"
            )
        impacted = []
        for path, document in documents:
            entries = document.get("impacted")
            if document.get("notRun") or not isinstance(entries, list):
                self.impact_blind = True
                return self._score("blast_radius", 0, f"{self.story.rel(path)}: not run")
            impacted += entries
        repos = {entry.get("repo") for entry in impacted if isinstance(entry, dict)}
        shown = f"{self.impact_rel}: {len(repos)} impacted repos"
        fraction = 1 if not repos else BLAST_NEAR if len(repos) <= 2 else 0
        self._score("blast_radius", fraction, shown)

    def _impacts(self) -> list[tuple[str, dict]]:
        return [(self.story.rel(path), doc) for path, doc in per_repo(self.story, "impact")[0]]

    def cap_risk_zones(self) -> None:
        path = self.central / "profile" / "risk-zones.yaml"
        if not path.is_file():
            return self._miss("risk-zones.yaml")
        try:
            zones = (miniyaml.load_file(str(path)) or {}).get("zones") or []
        except (ValueError, AttributeError):
            return self._miss("risk-zones.yaml (unreadable)")
        best = None
        for _, file in diff_files(self.diff):
            for zone in zones:
                if any(glob_regex(str(p)).match(file) for p in zone.get("paths") or []):
                    cap = zone.get("cap", self.weights["caps"]["risk_zone"])
                    if best is None or cap < best[0]:
                        best = (cap, f"{file} matches {zone.get('name')} (profile/risk-zones.yaml)")
        if best:
            self.caps.append({"name": "risk_zone", "cap": best[0], "evidence": best[1]})

    def cap_breaking(self) -> None:
        found = [str(item) for item in (self.diff or {}).get("breakingContract") or []]
        source = self.diff_rel
        for rel, impact in self._impacts():
            if found:
                break
            entries = impact.get("impacted") or []
            found = [str(e.get("via")) for e in entries if isinstance(e, dict) and e.get("breaking")]
            source = rel
        if found:
            cap = self.weights["caps"]["breaking_contract"]
            self.caps.append({"name": "breaking_contract", "cap": cap, "evidence": f"{found[0]} ({source})"})

    def collections_written(self) -> set[str]:
        written = {
            str(c).removeprefix("collection:") for c in (self.diff or {}).get("writesCollections") or []
        }
        path = self.central / "profile" / "dependencies.yaml"
        changed = set(diff_files(self.diff))
        if changed and path.is_file():
            try:
                graph = miniyaml.load_file(str(path)) or {}
            except ValueError:
                self._miss("dependencies.yaml (unreadable)")
                return written
            for repo in graph.get("repos") or []:
                for edge in repo.get("edges") or []:
                    file = (edge.get("provenance") or {}).get("file")
                    if edge.get("kind") == "WRITES_COLLECTION" and (repo.get("repo"), file) in changed:
                        written.add(str(edge.get("to")).removeprefix("collection:"))
        return written

    def cap_unprofiled(self) -> None:
        written = self.collections_written()
        if not written:
            return
        profiles: dict[str, bool] = {}
        for file in sorted((self.central / "docs" / "data-profile").glob("*.json")):
            document, _ = read_json(file)
            if document is not None:
                profiles[str(document.get("collection", file.stem))] = bool(document.get("unprofiled"))
        cap = self.weights["caps"]["unprofiled_write"]
        for name in sorted(written):
            if name not in profiles:
                evidence = f"writes {name}: no docs/data-profile/{name}.json"
            elif profiles[name]:
                evidence = f"writes {name}: docs/data-profile/{name}.json says unprofiled"
            else:
                continue
            self.caps.append({"name": "unprofiled_write", "cap": cap, "evidence": evidence})
            return

    def cap_unknown_edges(self) -> None:
        for rel, impact in self._impacts():
            edges = impact.get("unknownEdges") or []
            if edges:
                cap = self.weights["caps"]["unknown_edges"]
                self.caps.append({"name": "unknown_edges", "cap": cap, "evidence": f"{edges[0]} ({rel})"})
                return

    def cap_new_dependency(self) -> None:
        if self.diff is None:
            return
        found = self.diff.get("newDependencies")
        if found is None:
            return self._miss("newDependencies in diff-shape.json")
        if found:
            cap = self.weights["caps"]["new_dependency"]
            self.caps.append(
                {"name": "new_dependency", "cap": cap, "evidence": f"{found[0]} ({self.diff_rel})"}
            )


def lane_for(score: float, capped: bool, blind: list[str], track: str, policy: dict) -> tuple[str, str]:
    if capped:
        return "tech-lead", "a cap applies"
    if blind:
        return "tech-lead", "caps could not be evaluated without: " + ", ".join(blind)
    if score < policy["senior_min"]:
        return "tech-lead", f"score below {policy['senior_min']}"
    if score >= policy["fast_lane_min"] and track == "light":
        return "fast", f"track light, score at least {policy['fast_lane_min']}, no caps"
    return "senior", f"score at least {policy['senior_min']}, no caps, track {track}"


def compute(central: Path, story_id: str, now: str | None = None) -> tuple[Story, dict]:
    central = Path(central)
    weights = load_weights(central)
    try:
        story = state_check.find_story(central, story_id)
    except FileNotFoundError as exc:
        raise Refused(str(exc)) from exc
    text = story.path.read_text(encoding="utf-8")
    scorer = _Scorer(story, text, weights)
    for name in SIGNALS:
        getattr(scorer, name)()
    for step in (
        scorer.cap_risk_zones,
        scorer.cap_breaking,
        scorer.cap_unprofiled,
        scorer.cap_unknown_edges,
        scorer.cap_new_dependency,
    ):
        step()
    if not story.qa("security-report.md").is_file():
        scorer._miss("security-report.md")
    track = state_check.track_of(text)
    if track is None:
        scorer._miss("story Track")
    track = track or "full"
    raw = _number(sum(signal["points"] for signal in scorer.signals.values()))
    score = min([raw, *[cap["cap"] for cap in scorer.caps]])
    blind = [
        name
        for name, absent in (
            ("diff-shape.json", scorer.diff is None),
            ("risk-zones.yaml", any(m.startswith("risk-zones") for m in scorer.missing)),
            ("impact.json", scorer.impact_blind),
        )
        if absent
    ]
    lane, reason = lane_for(score, bool(scorer.caps), blind, track, weights["policy"])
    return story, {
        "story": story.story_id,
        "track": track,
        "computedAt": now or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "weightsVersion": weights["version"],
        "signals": scorer.signals,
        "raw": raw,
        "caps": scorer.caps,
        "score": score,
        "lane": lane,
        "laneReason": reason,
        "missing": scorer.missing,
    }


def add_arguments(parser) -> None:
    parser.add_argument("story_id", help="the story id, e.g. S-010")


def run(args) -> int:
    try:
        story, document = compute(Path(args.central), args.story_id)
    except Refused as exc:
        print(f"refused: {exc}. No confidence.json written.", file=sys.stderr)
        return 2
    path = story.qa("confidence.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(document, indent=2))
    else:
        print(f"{document['story']}: score {document['score']} lane {document['lane']} ({story.rel(path)})")
    return 0
