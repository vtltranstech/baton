"""A wiki page as text: frontmatter the tools own, a body whose structure the tools own.

The model's answer only fills the two prose sections, as text; nothing it returns reaches the frontmatter.
`bodySha256` is additive to schemas/wiki-page.json (which allows it): it makes an edit after generation
detectable without trusting the file's own `verified`.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from baton import miniyaml
from baton.extract import yamlio
from baton.wiki.facts import CATEGORIES

REQUIRED_SECTIONS = (
    "Purpose",
    "Entry points",
    "Reads / Writes",
    "Calls / Called by",
    "Invariants observed in tests",
    "Known pitfalls",
    "Last verified",
)
LAST_VERIFIED = "\n## Last verified\n"
NOT_VERIFIED = "Not verified."
VERIFIED_LINE = "Verified by baton verify at commit {commit}."
_LAST_VERIFIED_BODY = re.compile(r"\A(?:Not verified\.|Verified by baton verify at commit \S+\.)\n\Z")


class PageError(Exception):
    """The file is not a readable page."""


@dataclass
class Page:
    front: dict
    front_text: str
    body: str


def parse(text: str) -> Page:
    if not text.startswith("---\n"):
        raise PageError("no frontmatter: the page must start with a --- block")
    end = text.find("\n---\n", 3)
    if end < 0:
        raise PageError("frontmatter is not closed by a --- line")
    front_text = text[4 : end + 1]
    try:
        front = miniyaml.loads(front_text)
    except ValueError as exc:
        raise PageError(f"frontmatter cannot be read as YAML: {exc}") from exc
    if not isinstance(front, dict):
        raise PageError("frontmatter is not a mapping")
    return Page(front, front_text, text[end + 5 :])


def schema_problems(front: dict) -> list[str]:
    """schemas/wiki-page.json, checked with the stdlib (a test compares this with jsonschema)."""
    problems = []
    for key in ("repo", "module", "generatedFrom"):
        if key not in front:
            problems.append(f"frontmatter: {key} is missing")
        elif not isinstance(front[key], str):
            problems.append(f"frontmatter: {key} must be a string")
    if "verified" not in front:
        problems.append("frontmatter: verified is missing")
    elif not isinstance(front["verified"], bool):
        problems.append("frontmatter: verified must be true or false")
    if "claims" not in front:
        problems.append("frontmatter: claims is missing")
    elif not isinstance(front["claims"], dict):
        problems.append("frontmatter: claims must be a mapping")
    else:
        for key, value in front["claims"].items():
            if key in CATEGORIES and not (isinstance(value, list) and all(isinstance(v, str) for v in value)):
                problems.append(f"claims.{key} must be a list of strings")
    return problems


def split_last_verified(body: str) -> tuple[str, str] | None:
    """(what the digest covers, the Last verified text), or None unless the section appears exactly once."""
    if body.count(LAST_VERIFIED) != 1:
        return None
    head, tail = body.split(LAST_VERIFIED)
    return head, tail


def digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def body_problems(page: Page) -> list[str]:
    parts = split_last_verified(page.body)
    if parts is None:
        return ["body: the Last verified section must appear exactly once"]
    head, tail = parts
    problems = [
        f"body: section {section!r} is missing"
        for section in REQUIRED_SECTIONS[:-1]
        if f"\n## {section}\n" not in "\n" + head
    ]
    if digest(head) != page.front.get("bodySha256"):
        problems.append("body: edited after generation (bodySha256 differs): regenerate with baton wiki")
    if not _LAST_VERIFIED_BODY.match(tail):
        problems.append("body: the Last verified section holds other text: regenerate with baton wiki")
    return problems


def render(repo: str, module: str, commit: str, claims: dict[str, list[str]], content: str) -> str:
    """`content` is the body before Last verified. Every frontmatter value comes from the caller."""
    front = yamlio.dumps(
        {
            "repo": repo,
            "module": module,
            "generatedFrom": commit,
            "bodySha256": digest(content),
            "claims": {category: list(claims.get(category, [])) for category in CATEGORIES},
            "verified": False,
        }
    )
    return f"---\n{front}---\n{content}{LAST_VERIFIED}{NOT_VERIFIED}\n"


_VERIFIED_KEY = re.compile(r"^verified:.*$", re.M)
_COMMIT_KEY = re.compile(r"^generatedFrom:.*$", re.M)


def with_state(text: str, verified: bool, commit: str | None = None, new_commit: str | None = None) -> str:
    """The same page with `verified` and the Last verified line set; everything else stays byte for byte."""
    page = parse(text)
    front = _VERIFIED_KEY.sub(f"verified: {'true' if verified else 'false'}", page.front_text)
    if new_commit is not None:
        rendered = yamlio.dumps({"generatedFrom": new_commit}).strip()
        front = _COMMIT_KEY.sub(lambda _m: rendered, front)
    body = page.body
    parts = split_last_verified(body)
    if parts is not None:
        line = VERIFIED_LINE.format(commit=commit) if verified else NOT_VERIFIED
        body = f"{parts[0]}{LAST_VERIFIED}{line}\n"
    return f"---\n{front}---\n{body}"


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        out.write(text)
    os.replace(temp, path)
