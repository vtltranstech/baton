"""Why a page fails, as a list of reasons. An empty list is the only thing that earns `verified: true`."""

from __future__ import annotations

from baton.extract.repos import UNKNOWN
from baton.wiki.facts import CATEGORIES, RepoFacts
from baton.wiki.page import Page, PageError, body_problems, parse, schema_problems


def repo_reasons(facts: RepoFacts, head: str, head_reason: str, dirty: bool) -> list[str]:
    """Why no page of this repo can pass right now. `unknown` never matches, not even `unknown`."""
    reasons = []
    if facts.commit == UNKNOWN or not facts.commit:
        reasons.append(
            f"dependencies.yaml says commit: unknown for {facts.repo.name} "
            f"({head_reason or 'not recorded'}): "
            "there is no commit to check claims at; give the repo its own git history and run baton extract"
        )
    elif head != facts.commit:
        reasons.append(
            f"dependencies.yaml is at {facts.commit} but the repo is at {head}: run baton extract, then "
            "baton wiki"
        )
    if dirty and head != UNKNOWN:
        reasons.append(f"the repo has uncommitted changes: claims cannot be checked at commit {head}")
    for edge in facts.unassigned:
        reasons.append(f"dependencies.yaml has an edge outside any module: {edge.get('to')}")
    return reasons


def _elsewhere(value: str, category: str, facts: RepoFacts, own: str) -> str:
    holders = sorted(n for n in facts.modules if n != own and value in facts.claims(n)[category])
    return f" (it belongs to {', '.join(holders)})" if holders else ""


def claim_reasons(page: Page, name: str, facts: RepoFacts) -> list[str]:
    claims = page.front.get("claims")
    if not isinstance(claims, dict):
        return []
    reasons = [
        f"claims.{key}: the extractors have no such category, so this claim cannot be checked"
        for key in sorted(set(claims) - set(CATEGORIES))
    ]
    actual = facts.claims(name)
    for category in CATEGORIES:
        value = claims.get(category, [])
        stated = {v for v in value if isinstance(v, str)} if isinstance(value, list) else set()
        for item in sorted(stated - set(actual[category])):
            reasons.append(
                f"claims.{category}: {item!r} is not in dependencies.yaml for module {name}"
                + _elsewhere(item, category, facts, name)
            )
        for item in sorted(set(actual[category]) - stated):
            reasons.append(
                f"claims.{category}: {item!r} is in dependencies.yaml for module {name} but not claimed"
            )
    return reasons


def page_reasons(text: str, stem: str, facts: RepoFacts, shared: list[str]) -> tuple[list[str], Page | None]:
    try:
        page = parse(text)
    except PageError as exc:
        return [f"frontmatter: {exc}", *shared], None
    reasons = schema_problems(page.front)
    if page.front.get("repo") not in (None, facts.repo.name):
        reasons.append(f"frontmatter: repo is {page.front['repo']!r}, this is {facts.repo.name}")
    if page.front.get("module") not in (None, stem):
        reasons.append(f"frontmatter: module is {page.front['module']!r} in the page for {stem}")
    if stem not in facts.modules:
        reasons.append(f"no such module in {facts.repo.name}: {stem}")
    generated = page.front.get("generatedFrom")
    if generated == UNKNOWN:
        reasons.append("generatedFrom is commit: unknown, which never matches any commit")
    elif "generatedFrom" in page.front and generated != facts.commit:
        reasons.append(
            f"stale: page generatedFrom {generated}, dependencies.yaml is at {facts.commit}: run baton wiki"
        )
    reasons += body_problems(page)
    reasons += claim_reasons(page, stem, facts)
    return reasons + shared, page
