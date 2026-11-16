"""Helpers shared by the W6 tests (pytest's importlib mode cannot import from conftest)."""
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
JAVA_FIXTURE = ROOT / "fixtures" / "sample-java-repo"
REACT_FIXTURE = ROOT / "fixtures" / "sample-react-repo"
GIT_IDENTITY = ["-c", "user.name=fixture", "-c", "user.email=fixture@example.com",
                "-c", "commit.gpgsign=false"]


def git(repo, *args):
    done = subprocess.run(["git", "-C", str(repo), *GIT_IDENTITY, *args], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout


def copy_fixture(source, target, ignore=("target", "build", ".gradle", "node_modules")):
    """A temp copy of a fixture as its own git repo: the clean tree on main."""
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(*ignore), symlinks=True)
    git(target, "init", "-q", "-b", "main")
    git(target, "add", "-A")
    git(target, "commit", "-q", "-m", "clean fixture")
    return target


def java_home(version):
    return subprocess.run(["/usr/libexec/java_home", "-v", str(version)],
                          capture_output=True, text=True, check=True).stdout.strip()
