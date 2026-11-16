"""The one call to the model: headless `claude -p`, no tools, outside every repo, answer parsed as prose."""

from __future__ import annotations

import os
import re
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path

CLAUDE_BIN_VAR = "BATON_CLAUDE_BIN"
_PROMPT_FILE = Path(__file__).with_name("prompt.md")
_FIELD = re.compile(r"\{\{(REPO|MODULE|NONCE|EDGES|SOURCES|TESTS)\}\}")
# `## Purpose`, `### purpose:`, `**Purpose**`: models vary the heading, and the answer is no worse for it.
_HEADING = re.compile(r"^[ \t]{0,3}(?:#{1,4}[ \t]+|\*\*)(.+?)(?:\*\*)?[ \t]*:?[ \t]*$", re.M)
_QUOTA = re.compile(
    r"\b429\b|quota|rate[ _-]?limit|resource[ _]?exhausted|too many requests|overloaded", re.I
)
_FRONTMATTER_KEY = re.compile(r"^\s*(verified|claims|generatedFrom|bodySha256)\s*:", re.M)
SECTIONS = ("Purpose", "Invariants observed in tests")
SOURCE_LIMIT = 80_000


class ModelError(Exception):
    """The call failed, or its answer cannot be used. No page is written from it."""


class QuotaError(ModelError):
    """The model's quota or rate limit was hit: every further call would fail the same way."""


def claude_bin() -> str | None:
    names = (CLAUDE_BIN_VAR, "POD_CLAUDE_BIN", "HARNESS_CLAUDE_BIN")  # the last two: older names
    return shutil.which(next((os.environ[n] for n in names if os.environ.get(n)), "claude"))


def _bundle(paths: list[Path], base: Path) -> str:
    chunks, used = [], 0
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        if used + len(text) > SOURCE_LIMIT:
            chunks.append(f"(further files left out at the size limit, starting at {path.name})")
            break
        used += len(text)
        chunks.append(f"--- file: {path.relative_to(base).as_posix()}\n{text}")
    return "\n".join(chunks) if chunks else "(none)"


def build_prompt(
    repo: str, module: str, edges: str, sources: list[Path], tests: list[Path], base: Path
) -> str:
    """One pass over the template, so text inside a source can never be taken for a field. The nonce is drawn
    per call, so a source cannot write the line that closes its own data block."""
    if not _PROMPT_FILE.is_file():
        raise ModelError(f"{_PROMPT_FILE} is missing from this install")
    values = {
        "REPO": repo,
        "MODULE": module,
        "NONCE": secrets.token_hex(8),
        "EDGES": edges or "(none)",
        "SOURCES": _bundle(sources, base),
        "TESTS": _bundle(tests, base),
    }
    return _FIELD.sub(lambda m: values[m.group(1)], _PROMPT_FILE.read_text(encoding="utf-8"))


def ask(prompt: str, timeout: int) -> str:
    binary = claude_bin()
    if binary is None:
        raise ModelError("claude executable not found")
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    with tempfile.TemporaryDirectory(prefix="baton-wiki-") as empty:
        try:
            done = subprocess.run(
                [binary, "-p", "--tools", ""],
                input=prompt,
                capture_output=True,
                text=True,
                cwd=empty,
                env=env,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise ModelError(f"claude -p did not answer in {timeout}s") from exc
        except OSError as exc:
            raise ModelError(f"claude -p could not start: {exc}") from exc
    said = f"{done.stderr}\n{done.stdout}"
    if _QUOTA.search(said) and (done.returncode != 0 or not _HEADING.search(done.stdout)):
        raise QuotaError(f"quota or rate limit: {said.strip()[:300]}")
    if done.returncode != 0:
        raise ModelError(f"claude -p exited {done.returncode}: {(done.stderr or done.stdout).strip()[:300]}")
    return done.stdout


def parse_answer(answer: str) -> dict[str, str]:
    """Only the text under the two prose headings is kept. Anything else, frontmatter included, is never read.
    A kept section that holds a frontmatter key, or a heading given twice, rejects the answer."""
    marks = list(_HEADING.finditer(answer))
    found: dict[str, str] = {}
    canonical = {title.casefold(): title for title in SECTIONS}
    for index, mark in enumerate(marks):
        title = canonical.get(mark.group(1).strip().strip("*").strip().casefold())
        if title is None:
            continue
        if title in found:
            raise ModelError(f"answer has the section {title!r} twice")
        end = marks[index + 1].start() if index + 1 < len(marks) else len(answer)
        found[title] = answer[mark.end() : end].strip()
    for title in SECTIONS:
        if not found.get(title):
            raise ModelError(f"answer has no text under {title!r}")
        if _FRONTMATTER_KEY.search(found[title]):
            raise ModelError(f"answer has frontmatter keys inside {title!r}")
    return found
