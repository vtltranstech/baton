"""baton.progress: step lines, counters with and without a total, and BATON_QUIET."""

from __future__ import annotations

import io

from baton.progress import Progress, silent


def test_steps_counters_and_ticks_go_to_the_stream(monkeypatch):
    monkeypatch.delenv("BATON_QUIET", raising=False)
    out = io.StringIO()
    progress = Progress("context build", steps=2, stream=out, every=0)
    progress.step("reading the repos")
    for _ in range(3):
        progress.tick("svc: Java main", 1, "files found")
    progress.tick("svc: done", 3, "files found", final=True)
    list(progress.each(["a", "b"], "svc"))
    progress.done()
    text = out.getvalue()
    assert "context build [1/2] reading the repos (0:00)" in text
    assert "  svc: Java main: 1 files found (0:00)" in text
    assert "  svc: done: 3 files found (0:00)" in text
    assert "  svc: 2/2 files (0:00)" in text
    assert text.endswith("context build complete (0:00)\n")


def test_quiet_and_silent_print_nothing(monkeypatch):
    out = io.StringIO()
    monkeypatch.setenv("BATON_QUIET", "1")
    Progress("x", stream=out).tick("svc", 1, final=True)
    quiet = silent()
    quiet.stream = out
    quiet.step("nothing")
    assert out.getvalue() == ""


def test_repo_walk_never_opens_node_modules(tmp_path, monkeypatch):
    import os

    from baton.context.product import _walk_ts

    (tmp_path / "src" / "app").mkdir(parents=True)
    (tmp_path / "src" / "app" / "Screen.tsx").write_text("export {}\n")
    (tmp_path / "src" / "node_modules" / "lib").mkdir(parents=True)
    (tmp_path / "src" / "node_modules" / "lib" / "x.ts").write_text("export {}\n")
    (tmp_path / "src" / "types.d.ts").write_text("export {}\n")
    opened = []
    real = os.walk

    def walk(top, *args, **kwargs):
        for current, dirs, files in real(top, *args, **kwargs):
            opened.append(current)
            yield current, dirs, files

    monkeypatch.setattr(os, "walk", walk)
    assert [p.name for p in _walk_ts(tmp_path)] == ["Screen.tsx"]
    assert not any("node_modules" in o for o in opened)
