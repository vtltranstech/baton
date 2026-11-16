"""W6 test setup. Build-driven tests are marked `slow` and skip unless BATON_SLOW=1."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

# A pre-commit hook exports GIT_DIR and GIT_INDEX_FILE. Left in place, the temp repos these tests create
# would write to the real repository instead: `git init` flips core.bare and `git add -A` rewrites the index.
for name in [key for key in os.environ if key.startswith("GIT_")]:
    del os.environ[name]


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: drives Maven, Gradle or npm; runs only with BATON_SLOW=1")


def pytest_collection_modifyitems(config, items):
    if os.environ.get("BATON_SLOW") == "1":
        return
    skip = pytest.mark.skip(reason="build-driven test: set BATON_SLOW=1 to run it")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)
