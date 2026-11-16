"""Names from the products the framework was first used on; core files must never hold them.

The list itself is not in the repo: one regex per line in `project-words.local.txt` beside this file
(git-ignored), or in the file named by BATON_PROJECT_WORDS. Without either, the word tests skip.
A line starting `core: ` is a domain word, checked only in the core (CORE_WORDS); the rest are names,
checked everywhere (PROJECT_WORDS).
"""

import os
import re
from pathlib import Path

LOCAL = Path(__file__).with_name("project-words.local.txt")


def load(core: bool = False, path: Path | None = None) -> re.Pattern | None:
    path = path or Path(os.environ.get("BATON_PROJECT_WORDS") or LOCAL)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    words = []
    for line in (line.strip() for line in lines):
        if line.startswith("core: "):
            line = line[len("core: "):].strip() if core else ""
        if line and not line.startswith("#"):
            words.append(line)
    return re.compile("|".join(f"(?:{w})" for w in words), re.I) if words else None


PROJECT_WORDS = load()
CORE_WORDS = load(core=True)
