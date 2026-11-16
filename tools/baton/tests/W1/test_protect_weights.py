"""protect_weights: direct and indirect reads are refused; ordinary project reads are not."""

import pytest

W = "profile/confidence-weights.yaml"


@pytest.fixture
def central(tmp_path):
    root = tmp_path / "central"
    (root / "profile").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "profile" / "project.md").write_text("x\n")
    (root / W).write_text("secret\n")
    (root / "docs" / "a.md").write_text("x\n")
    (tmp_path / "svc").mkdir()
    return root


def bash(run_hook, central, command, cwd=None):
    return run_hook("protect_weights", "Bash", {"command": command}, cwd or central, project=central)


BLOCKED_BASH = [
    f"cat {W}",
    f"head -5 {W}",
    f"tail {W}",
    f"less {W}",
    f"grep mutation {W}",
    f"sed -n 1p {W}",
    f"awk 1 {W}",
    f"xxd {W}",
    f"base64 {W}",
    f"cp {W} /tmp/x",
    f"ln -s {W} x",
    f"dd if={W}",
    f"cat < {W}",
    f"python3 -c 'print(open(\"{W}\").read())'",
    'python3 -c \'print(open("profile/confidence-" + "weights.yaml").read())\'',
    "python3 -c 'import glob;print(glob.glob(\"profile/*\"))'",
    "python3 <<EOF\nprint(open('profile/conf' + 'idence-w' + 'eights.yaml').read())\nEOF",
    'node -e \'require("fs").readFileSync("profile/conf"+"idence")\'',
    'ruby -e \'puts File.read("profile/" + "x")\'',
    "perl -ne 'print' profile/conf*",
    "cat profile/confidence-*",
    "cat profile/*",
    "cat profile/*.yaml",
    "cat profile/conf*",
    "cat profile/c?nfidence-weights.yaml",
    "cat pro*/*",
    "cat */*.yaml",
    "cat profile/{project.md,confidence-weights.yaml}",
    "cd profile && cat *",
    "cd profile; cat conf*",
    "(cd profile && head *)",
    "f=profile/confidence-we; cat ${f}ights.yaml",
    "cat profile/confidence\\-weights.yaml",
    "cat 'profile/confidence'-weights.yaml",
    "cat PROFILE/CONFIDENCE-WEIGHTS.YAML",
    "cat $'profile/\\x63onfidence-weights.yaml'",
    "cat profile/$NAME",
    "git show HEAD:profile/confidence-weights.yaml",
    "bash -c 'cat profile/confidence-weights.yaml'",
    "eval 'cat profile/*'",
    "grep -r mutation_full .",
    "grep -rn mutation_full profile",
    "grep -R x profile/",
    "grep -r x",
    "rg mutation_full",
    "rg mutation_full .",
    "rg x profile",
    "ag x",
    "tar czf /tmp/x.tgz profile",
    "tar czf /tmp/x.tgz .",
    "zip -r /tmp/x.zip profile",
    "cp -r profile /tmp/p",
    "rsync -a profile /tmp/p",
    "find . -name '*.yaml' -exec cat {} ';'",
    "find profile -type f -exec cat {} +",
    "find . -name '*.yaml' | xargs cat",
    "git grep mutation_full",
    "git archive HEAD",
    "cat s | bash",
    "cat 'unterminated",
]


@pytest.mark.parametrize("command", BLOCKED_BASH)
def test_bash_read_blocked(run_hook, central, command):
    result = bash(run_hook, central, command)
    assert result.returncode == 2, f"not blocked: {command!r}"
    assert "refused" in result.stderr


def test_the_refusal_says_who_owns_it(run_hook, central):
    assert "owned by the Senior Engineer" in bash(run_hook, central, f"cat {W}").stderr


def test_ancestor_and_sibling_paths(run_hook, central, tmp_path):
    assert bash(run_hook, central, "grep -r x ..", central / "docs").returncode == 2
    assert bash(run_hook, central, "grep -r x ../central", tmp_path / "svc").returncode == 2
    assert bash(run_hook, central, "grep -r x .", tmp_path / "svc").returncode == 0
    assert bash(run_hook, central, "cat ../central/profile/*", tmp_path / "svc").returncode == 2


ALLOWED_BASH = [
    "ls",
    "ls profile",
    "cat profile/project.md",
    "cat profile/project.*",
    "cat docs/*",
    "cat docs/*.md",
    "grep -r x docs",
    "grep -rn x docs/",
    "grep -r --include=*.md x .",
    "rg x docs",
    "rg x -g '*.md'",
    "grep x docs/a.md",
    "find . -name '*.md'",
    "find . -name '*.md' -exec cat {} ';'",
    "find docs -type f -exec cat {} +",
    "python3 tools/baton/cli.py confidence S-010",
    "python3 -c 'print(1+1)'",
    "cp docs/a.md /tmp/a.md",
    "tar czf /tmp/x.tgz docs",
    "git status",
    "git log -1",
    "git grep x docs",
]


@pytest.mark.parametrize("command", ALLOWED_BASH)
def test_bash_allowed(run_hook, central, command):
    result = bash(run_hook, central, command)
    assert result.returncode == 0, f"false positive: {command!r}: {result.stderr}"


def test_read_tool(run_hook, central):
    def read(path):
        return run_hook("protect_weights", "Read", {"file_path": str(path)}, central, project=central)

    assert read(central / W).returncode == 2
    assert read(W).returncode == 2
    assert read("profile/../profile/confidence-weights.yaml").returncode == 2
    assert read(str(central / W).upper()).returncode == 2
    assert read(central / "profile/project.md").returncode == 0
    link = central / "docs" / "innocent.txt"
    link.symlink_to(central / W)
    assert read(link).returncode == 2


def test_edit_and_write_tools_refused(run_hook, central):
    for tool, payload in (
        ("Write", {"file_path": W, "content": "x"}),
        ("Edit", {"file_path": W, "old_string": "a", "new_string": "b"}),
        ("MultiEdit", {"edits": [{"file_path": W, "old_string": "a", "new_string": "b"}]}),
    ):
        assert run_hook("protect_weights", tool, payload, central, project=central).returncode == 2


GREP_CASES = [
    ({"pattern": "x", "path": W}, 2),
    ({"pattern": "x", "path": "profile"}, 2),
    ({"pattern": "x", "path": "."}, 2),
    ({"pattern": "x"}, 2),
    ({"pattern": "x", "glob": "*.yaml"}, 2),
    ({"pattern": "x", "glob": "confidence-*"}, 2),
    ({"pattern": "x", "glob": "**/*.{yaml,md}"}, 2),
    ({"pattern": "x", "type": "yaml"}, 2),
    ({"pattern": "x", "path": "docs"}, 0),
    ({"pattern": "x", "path": "profile/project.md"}, 0),
    ({"pattern": "x", "glob": "*.md"}, 0),
    ({"pattern": "x", "type": "java"}, 0),
]


@pytest.mark.parametrize("tool_input,expected", GREP_CASES)
def test_grep_tool(run_hook, central, tool_input, expected):
    assert run_hook("protect_weights", "Grep", tool_input, central, project=central).returncode == expected


def test_glob_tool_only_lists_names(run_hook, central):
    assert (
        run_hook("protect_weights", "Glob", {"pattern": "profile/*"}, central, project=central).returncode
        == 0
    )


@pytest.mark.parametrize(
    "stdin", ["", "nope", '{"tool_name":"Read","tool_input":{}}', '{"tool_name":"Bash","tool_input":{}}']
)
def test_bad_input_fails_closed(stdin):
    import subprocess
    import sys
    from pathlib import Path

    hook = Path(__file__).resolve().parents[4] / "hooks" / "protect_weights.py"
    assert (
        subprocess.run([sys.executable, str(hook)], input=stdin, capture_output=True, text=True).returncode
        == 2
    )
