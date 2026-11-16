"""`baton wiki --changed-since`: regenerate only touched modules, and leave the rest verifiable."""

from w4_helpers import ALL_MODULES, REPO, commit_all, frontmatter, git, page_path, run_cli

BATCH_DIR = "src/main/java/com/example/sample/adapters/batch"
DOC_FILE = "src/main/java/com/example/sample/domain/document/FeeAccrualDoc.java"


def update(central, sha):
    assert run_cli("extract", "--central", str(central)) == 0
    return run_cli("wiki", REPO, "--central", str(central), "--changed-since", sha)


def test_only_the_touched_module_calls_the_model(generated, repo, stub):
    assert run_cli("verify", REPO, "--central", str(generated)) == 0
    start = git(repo, "rev-parse", "HEAD")
    (repo / BATCH_DIR / "Extra.java").write_text(
        "package com.example.sample.adapters.batch;\nclass Extra {}\n"
    )
    sha = commit_all(repo)
    before = len(stub())
    assert update(generated, start) == 0
    assert len(stub()) - before == 1
    assert "Extra" in stub()[-1]["prompt"]
    for module in ALL_MODULES:
        data = frontmatter(page_path(generated, module))
        assert data["generatedFrom"] == sha
        assert data["verified"] is False, "a moved page is not verified until verify says so"
    assert run_cli("verify", REPO, "--central", str(generated)) == 0


def test_a_change_with_no_java_regenerates_nothing_and_verify_passes(generated, repo, stub):
    start = git(repo, "rev-parse", "HEAD")
    (repo / "README.md").write_text("docs only\n")
    commit_all(repo)
    before = len(stub())
    assert update(generated, start) == 0
    assert len(stub()) == before
    assert run_cli("verify", REPO, "--central", str(generated)) == 0


def test_a_test_change_touches_its_module(generated, repo, stub):
    start = git(repo, "rev-parse", "HEAD")
    target = repo / "src/test/java/com/example/sample/application/service/FeeCalculatorTest.java"
    target.write_text(target.read_text() + "\n// changed\n")
    commit_all(repo)
    before = len(stub())
    assert update(generated, start) == 0
    assert len(stub()) - before == 1
    assert "FeeCalculator" in stub()[-1]["prompt"]


def test_changed_claims_regenerate_and_are_correct(generated, repo, stub):
    start = git(repo, "rev-parse", "HEAD")
    target = repo / DOC_FILE
    target.write_text(target.read_text().replace('"fee_accruals"', '"fee_accruals_v2"'))
    commit_all(repo)
    assert update(generated, start) == 0
    assert frontmatter(page_path(generated, "domain.document"))["claims"]["collections"] == [
        "fee_accruals_v2",
        "fee_schedules",
    ]
    assert run_cli("verify", REPO, "--central", str(generated)) == 0


def test_a_change_before_since_but_after_the_page_still_counts(generated, repo, stub):
    (repo / BATCH_DIR / "Extra.java").write_text(
        "package com.example.sample.adapters.batch;\nclass Extra {}\n"
    )
    commit_all(repo)
    (repo / "README.md").write_text("later\n")
    commit_all(repo, "later")
    since = git(repo, "rev-parse", "HEAD~1")
    before = len(stub())
    assert update(generated, since) == 0
    assert len(stub()) - before == 1
    assert "Extra" in stub()[-1]["prompt"]


def test_a_new_module_gets_a_page_and_a_removed_one_loses_it(generated, repo, stub):
    start = git(repo, "rev-parse", "HEAD")
    new_dir = repo / "src/main/java/com/example/sample/adapters/fresh"
    new_dir.mkdir()
    (new_dir / "Fresh.java").write_text("package com.example.sample.adapters.fresh;\nclass Fresh {}\n")
    commit_all(repo)
    assert update(generated, start) == 0
    assert page_path(generated, "adapters.fresh").exists()
    mid = git(repo, "rev-parse", "HEAD")
    (new_dir / "Fresh.java").unlink()
    commit_all(repo)
    assert update(generated, mid) == 0
    assert not page_path(generated, "adapters.fresh").exists()


def test_bad_sha_is_exit_2(generated, stub):
    assert run_cli("wiki", REPO, "--central", str(generated), "--changed-since", "nonsense") == 2


def test_a_revision_that_looks_like_an_option_never_reaches_git(generated, stub, tmp_path):
    written = tmp_path / "written-by-git"
    args = ("wiki", REPO, "--central", str(generated), f"--changed-since=--output={written}")
    assert run_cli(*args) == 2
    assert not written.exists()
