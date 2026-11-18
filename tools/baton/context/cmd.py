"""Measure the product's context per layer, per story and per feature; ingest | build | score | brief |
understand | questions | answer | check S|F | gaps | trend

baton context ingest [--from P] Confluence, Word, PowerPoint, Excel, text -> docs/context/sources/*.md
baton context build            branch points -> profile/branch-points.yaml, drafts -> profile/domain-drafts.md
baton context score            coverage per layer -> docs/context/context-map.json and .md
baton context brief AREA       what an explorer must explain about one area (`system`: for the integrator)
baton context understand       grade the explorers' notes, flows and landscape -> docs/context/understanding/
baton context questions        open questions by person, with their age -> docs/context/questions.md
baton context answer REF Q3 "words" --by PO   a human's answer, verbatim under the question (C3: resolved)
baton context check S-010      is the context enough for this story? exit 2 on a blocking gap
baton context check F-001      is the system understood well enough to accept this feature? exit 2 if not
                               (--track light|full|spike; default full)
baton context gaps [--layer L] the gap list, worst module first
baton context trend            the domain score per checked story

No model call and no network anywhere (contracts/context-map.md). Run from the central repo.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from baton.context import domain as dm
from baton.context.product import MAP_JSON, MAP_MD, load_points, load_repos, load_settings
from baton.extract.repos import MissingInput

EXIT_OK, EXIT_FAILED, EXIT_REFUSED = 0, 1, 2
ACTIONS = ("ingest", "build", "score", "brief", "understand", "questions", "answer", "check", "gaps", "trend")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action", choices=ACTIONS)
    parser.add_argument(
        "story",
        nargs="?",
        help="check: a story id (S-010) or feature id (F-001); brief: an area or `system`; answer: an area, "
        "`landscape` or `flow:<name>`",
    )
    parser.add_argument("words", nargs="*", help='answer: the item (Q3 or C1), then "the answer"')
    parser.add_argument("--by", choices=("PO", "TL"), help="answer: who answered")
    parser.add_argument(
        "--track",
        choices=("light", "full", "spike"),
        default="full",
        help="check F-x: the track (default full)",
    )
    parser.add_argument(
        "--layer",
        choices=("structural", "behavioural", "domain", "operational", "intent"),
        help="gaps: only this layer",
    )
    parser.add_argument(
        "--from",
        dest="sources",
        action="append",
        metavar="PATH",
        help="ingest: a file, folder or glob to read (repeatable); default: doc-sources in context.yaml",
    )
    parser.add_argument(
        "--no-write", action="store_true", help="check: print only; write neither the manifest nor the story"
    )


def _out(args: argparse.Namespace, data, text: str) -> None:
    print(json.dumps(data, indent=1) if args.json else text)


def _score(central: Path, repos, domain, settings) -> dict | None:
    from baton.context import score

    points = load_points(central)
    if points is None or any("status" not in p or "module" not in p for p in points):
        return None  # never built: a hand-written file holds only the human mappings
    return score.compute(central, repos, domain, points, settings)


def _understanding(args: argparse.Namespace, central: Path, repos, domain, points) -> int:
    from baton.context import understanding as us

    status = us.grade_all(central, repos, domain, points)
    if args.action == "brief":
        if not args.story:
            print("baton context brief: name an area (repo/module) or `system`", file=sys.stderr)
            return EXIT_REFUSED
        if args.story == "system":
            brief = us.brief_system(repos, status)
        else:
            brief = us.brief_area(central, repos, domain, points, args.story, status)
        _out(args, brief, us.brief_text(brief))
        return EXIT_OK
    wrote = us.write(central, status)
    settings = load_settings(central)
    today = date.today().isoformat()
    (central / us.QUESTIONS_MD).write_text(
        us.questions_page(status, settings.question_ttl_days, today), encoding="utf-8"
    )
    wrote.append(us.QUESTIONS_MD)
    if args.action == "questions":
        _out(
            args,
            status["openQuestions"] + status["openContradictions"],
            us.questions_page(status, settings.question_ttl_days, today) + f"Wrote {', '.join(wrote)}.",
        )
        return EXIT_OK
    counts = status["counts"]
    lines = [
        ", ".join(f"{counts[s]} {s}" for s in us.STATES) + f"; landscape {status['landscape']['status']}; "
        f"{sum(1 for f in status['flows'] if f['valid'])}/{len(status['flows'])} flows valid; "
        f"{sum(1 for q in status['openQuestions'] if q['blocking'])} blocking questions open."
    ]
    lines += [f"  {key}: {area['status']}" for key, area in status["areas"].items()]
    lines.append("System understood." if status["understood"] else "Not understood yet: see " + us.STATUS_MD)
    lines.append(f"Wrote {', '.join(wrote)}.")
    _out(args, status, "\n".join(lines))
    return EXIT_OK


def state_check_gate_off(central: Path) -> str | None:
    from baton.state_check import gate_off

    return gate_off(central)


def run(args: argparse.Namespace) -> int:
    from baton.context import build, check, score, understanding

    central = Path(args.central).resolve()
    try:
        settings = load_settings(central)
        domain = dm.load(central)
        if args.action == "trend":
            path = central / MAP_JSON
            if not path.is_file():
                print(f"baton context: {MAP_JSON} is missing; run baton context score", file=sys.stderr)
                return EXIT_REFUSED
            trend = json.loads(path.read_text(encoding="utf-8")).get("trend") or []
            text = (
                "\n".join(
                    f"{t['story']:<10} domain {t['domain']}  clarifications {t.get('clarifications', 0)}"
                    for t in trend
                )
                or "no story checked yet"
            )
            _out(args, trend, text)
            return EXIT_OK
        if args.action == "ingest":
            from baton.context import ingest

            patterns = args.sources or settings.doc_sources
            if not patterns:
                print(
                    "baton context ingest: nothing to read; pass --from <folder or file> or set doc-sources "
                    "in profile/context.yaml",
                    file=sys.stderr,
                )
                return EXIT_REFUSED
            from baton.progress import Progress

            progress = Progress("context ingest", steps=1)
            summary = ingest.run_ingest(central, patterns, ingest.options_from(settings), progress=progress)
            progress.done()
            lines = [
                f"{summary['written']} written, {summary['unchanged']} unchanged, {len(summary['skipped'])} "
                f"skipped; {summary['documents']} documents in {ingest.INDEX_JSON}."
            ]
            lines += [f"  skipped {s['source']}: {s['reason']}" for s in summary["skipped"]]
            lines += [
                f"  {source}: {w}" for source, warnings in summary["warnings"].items() for w in warnings
            ]
            lines.append("OCR: " + summary["ocr"])
            lines.append("Next: baton context build (mines them into profile/domain-drafts.md), then score.")
            _out(args, summary, "\n".join(lines))
            return EXIT_OK
        if args.action == "answer":
            from baton.context import understanding as us

            if not args.story or len(args.words) < 2 or not args.by:
                print(
                    "baton context answer: write baton context answer <area | landscape | flow:name> Q<n> "
                    '"<the answer>" --by PO|TL',
                    file=sys.stderr,
                )
                return EXIT_REFUSED
            try:
                where = us.record(
                    central,
                    args.story,
                    args.words[0],
                    " ".join(args.words[1:]),
                    args.by,
                    date.today().isoformat(),
                )
            except (FileNotFoundError, ValueError) as exc:
                print(f"baton context answer: {exc}", file=sys.stderr)
                return EXIT_REFUSED
            print(f"Wrote the answer under {args.words[0]} in {where}. Grading again:")
            args.action = "understand"
        off = state_check_gate_off(central) if args.action == "check" and args.story else None
        if off:
            _out(
                args,
                {"story": args.story, "blocking": 0, "gateOff": off},
                f"{args.story}: gate 0 is off for the product: {off}; nothing checked - accepted",
            )
            return EXIT_OK
        if args.action == "build":
            from baton.progress import Progress

            progress = Progress("context build", steps=5)
            progress.step("reading the repos in profile/project.md")
            repos = load_repos(central, progress)
            summary = build.run_build(central, repos, domain, settings, progress=progress)
            progress.done()
        else:
            repos = load_repos(central)
        if args.action == "build":
            ext = ", ".join(f"{k} {v}" for k, v in sorted(summary["extractors"].items())) or "none"
            _out(
                args,
                summary,
                f"{summary['branchPoints']} branch points: {summary['mapped']} mapped, "
                f"{summary['undocumented']} undocumented, {summary['contested']} contested ({ext}); "
                f"{summary['drafts']} drafts. Wrote {', '.join(summary['wrote'])}.",
            )
            return EXIT_OK
        data = _score(central, repos, domain, settings)
        if data is None:
            print(
                "baton context: profile/branch-points.yaml is missing or not built; run baton context build",
                file=sys.stderr,
            )
            return EXIT_REFUSED
        points = load_points(central) or []
        if args.action in ("brief", "understand", "questions"):
            return _understanding(args, central, repos, domain, points)
        if args.action == "score":
            if (central / understanding.FOLDER).is_dir():
                data["understanding"] = understanding.summary(
                    understanding.grade_all(central, repos, domain, points)
                )
            score.write(central, data, points)
            layers = data["layers"]
            lines = [f"{name:<12} {layers[name]['score']}" for name in score.LAYERS]
            _out(
                args,
                data,
                "\n".join(score.statements(data) + [""] + lines + ["", f"Wrote {MAP_JSON}, {MAP_MD}."]),
            )
            return EXIT_OK
        if args.action == "gaps":
            gaps = [g for g in data["gaps"] if args.layer in (None, g["layer"])]
            order = {m: i for i, m in enumerate(data["interviewOrder"])}
            gaps.sort(key=lambda g: (order.get(g["module"], len(order)), g["layer"], g["module"]))
            text = "\n".join(
                f"[{g['layer']}] {g['module']}: {score.ASK[g['ask']]}: {g['text']}"
                + (f" ({g['file']}:{g['line']})" if g.get("file") else "")
                for g in gaps
            )
            _out(args, {"interviewOrder": data["interviewOrder"], "gaps": gaps}, text or "no gaps")
            return EXIT_OK
        if not args.story:
            print("baton context check: name the story, e.g. baton context check S-010", file=sys.stderr)
            return EXIT_REFUSED
        status = understanding.grade_all(central, repos, domain, points)
        if not args.no_write:
            understanding.write(central, status)  # the state gate reads it
        if check.FEATURE_ID.match(args.story):
            result = check.check_feature(
                central, args.story, repos, domain, points, args.track, settings.light_open_questions, status
            )
            if not args.no_write:
                result["wrote"] = check.write_feature(central, result)
            lines = [
                f"{result['feature']} ({result['track']}): {result['blocking']} blocking gap"
                f"{'s' if result['blocking'] != 1 else ''}"
                f"; changes {', '.join(result['changed']) or '(none found)'}"
                + (" - accepted for story drafting" if not result["blocking"] else " - not accepted yet")
            ]
            lines += [
                f"  {'BLOCKING' if g['blocking'] else 'open'} {score.ASK[g['ask']]}: {g['question']}"
                for g in result["gaps"]
            ]
            _out(args, result, "\n".join(lines))
            return EXIT_REFUSED if result["blocking"] else EXIT_OK
        result = check.check(central, args.story, repos, domain, points, settings, status)
        if not args.no_write:
            result["wrote"] = check.write(central, result, data["layers"]["domain"]["score"])
        lines = [
            f"{result['story']} ({result['track']}): {result['blocking']} blocking gap"
            f"{'s' if result['blocking'] != 1 else ''}, {len(result['gaps'])} in all; scope "
            f"{', '.join(result['scope']) or '(none)'}"
        ]
        lines += [
            f"  {'BLOCKING' if g['blocking'] else 'open'} {score.ASK[g['ask']]}: {g['question']}"
            for g in result["gaps"]
        ]
        _out(args, result, "\n".join(lines))
        return EXIT_REFUSED if result["blocking"] else EXIT_OK
    except (MissingInput, FileNotFoundError) as exc:
        print(f"baton context: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except ValueError as exc:
        print(f"baton context: {exc}", file=sys.stderr)
        return EXIT_FAILED
