"""docs/context/codebase-map.md: a table row per page, from the frontmatter, honest about verification."""

from w4_helpers import ALL_MODULES, REPO, commit_all, page_path, run_cli

MAP = "docs/context/codebase-map.md"


def page_lines(central):
    return [ln for ln in (central / MAP).read_text().splitlines() if ln.startswith("| `docs/wiki/")]


def line_for(central, module):
    return next(ln for ln in page_lines(central) if f"/{module}.md`" in ln)


def test_one_line_per_page_and_marked_unverified_until_verify(generated):
    assert len(page_lines(generated)) == len(ALL_MODULES)
    assert all("UNVERIFIED" in ln for ln in page_lines(generated))
    assert run_cli("verify", REPO, "--central", str(generated)) == 0
    assert not any("UNVERIFIED" in ln for ln in page_lines(generated))
    line = line_for(generated, "adapters.repository")
    assert "| `fee_accruals`, `fee_schedules` |" in line


def test_failed_verify_shows_in_the_index(generated):
    assert run_cli("verify", REPO, "--central", str(generated)) == 0
    path = page_path(generated, "adapters.batch")
    path.write_text(path.read_text().replace("collections: []", "collections: [invented]"))
    assert run_cli("verify", REPO, "--central", str(generated)) == 1
    assert "UNVERIFIED" in line_for(generated, "adapters.batch")
    assert "UNVERIFIED" not in line_for(generated, "adapters.repository")


def test_a_stale_true_page_is_unverified_in_the_index(generated, repo, stub):
    assert run_cli("verify", REPO, "--central", str(generated)) == 0
    (repo / "README.md").write_text("moved\n")
    commit_all(repo)
    assert run_cli("extract", "--central", str(generated)) == 0
    assert run_cli("wiki", REPO, "--central", str(generated), "--module", "adapters.batch") == 0
    assert "UNVERIFIED" in line_for(generated, "adapters.repository")


def test_a_page_with_broken_frontmatter_is_listed_unverified(generated):
    page_path(generated, "adapters.batch").write_text("nothing\n")
    assert run_cli("verify", REPO, "--central", str(generated)) == 1
    assert "UNVERIFIED" in line_for(generated, "adapters.batch")


def test_regenerating_replaces_the_block_and_keeps_hand_written_lines(generated):
    path = generated / MAP
    path.write_text("# Old map\n- a hand-written line\n")
    assert run_cli("verify", REPO, "--central", str(generated)) == 0
    first = path.read_text()
    assert "a hand-written line" in first
    assert run_cli("verify", REPO, "--central", str(generated)) == 0
    assert path.read_text() == first
    assert first.count("<!-- wiki-index") == 1
