"""A small POSIX-shell reader for the hooks (stdlib only).

It does not run anything. It turns a command line into the simple commands bash would run, so a hook
can reason about `cd x && git push`, `(git merge y)`, `"$(git commit)"`, `bash -c '...'` and heredocs
without being fooled by words that only appear inside a quoted string. What it cannot see (a script's
contents, a value computed at run time) is marked `dynamic` or `opaque`; each hook then fails closed.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

METACHARS = set(" \t\n;&|()<>")
RESERVED = {
    "if",
    "then",
    "elif",
    "else",
    "fi",
    "while",
    "until",
    "do",
    "done",
    "case",
    "esac",
    "in",
    "{",
    "}",
    "!",
    "time",
    "coproc",
    "function",
    "[[",
    "]]",
}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "ash"}
ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\+?=(.*)$", re.S)
ANSI = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "\\": "\\",
    "'": "'",
    '"': '"',
    "a": "\a",
    "b": "\b",
    "e": "\x1b",
    "f": "\f",
    "v": "\v",
}


class ShellParseError(ValueError):
    """The command is not valid shell as far as this reader can tell."""


@dataclass
class Word:
    text: str = ""
    raw: str = ""
    dynamic: bool = False  # contains an expansion or substitution whose value is unknown
    vars: list[str] = field(default_factory=list)  # variables expanded by the shell (not single-quoted)
    glob: bool = False  # unquoted glob or brace characters


@dataclass
class Command:
    argv: list[Word] = field(default_factory=list)
    env: dict[str, Word] = field(default_factory=dict)  # VAR=value prefixes
    redirects: list[tuple[str, Word]] = field(default_factory=list)
    heredocs: list[str] = field(default_factory=list)
    piped: Command | None = None  # the command whose stdout feeds this one
    opaque: str = ""  # non-empty: a shell reads code we cannot see

    @property
    def name(self) -> str:
        return os.path.basename(self.argv[0].text).lower() if self.argv else ""

    @property
    def args(self) -> list[Word]:
        return self.argv[1:]


OPEN, CLOSE = "(", ")"  # subshell markers in the flat item list; state inside must not leak out


class _Parser:
    def __init__(self, text: str, env: dict[str, str] | None = None, assigned: set[str] | None = None):
        self.s, self.i = text, 0
        self.env = env if env is not None else {}
        self.assigned = assigned if assigned is not None else set()
        self.pending: list[tuple[Command, str, bool]] = []  # heredocs waiting for the next newline

    def parse(self, closer: str | None = None) -> list:
        items: list = []
        current = Command()
        previous_pipe: Command | None = None
        started = False

        def finish(pipe: bool = False) -> None:
            nonlocal current, previous_pipe, started
            if started:
                current.piped = previous_pipe
                self._apply_assignments(current)
                items.append(current)
                previous_pipe = current if pipe else None
            elif not pipe:
                previous_pipe = None
            current, started = Command(), False

        while self.i < len(self.s):
            ch = self.s[self.i]
            if ch in " \t":
                self.i += 1
            elif ch == "\n":
                self.i += 1
                self._read_heredocs()
                finish()
            elif ch == "#":
                while self.i < len(self.s) and self.s[self.i] != "\n":
                    self.i += 1
            elif ch == ")":
                if closer != ")":
                    raise ShellParseError("unbalanced )")
                self.i += 1
                finish()
                return items
            elif ch == "(":
                self.i += 1
                inner = _Parser(self.s, dict(self.env), self.assigned)
                inner.i, inner.pending = self.i, self.pending
                body = inner.parse(")")
                self.i = inner.i
                finish()
                items += [OPEN, *body, CLOSE]
            elif self.s.startswith(("&&", "||", ";;"), self.i):
                self.i += 2
                finish()
            elif self.s.startswith(("|&",), self.i):
                self.i += 2
                finish(pipe=True)
            elif ch == "|":
                self.i += 1
                finish(pipe=True)
            elif ch == ";":
                self.i += 1
                finish()
            elif ch in "<>" or (ch == "&" and self.s[self.i + 1 : self.i + 2] == ">"):
                started = True
                items.extend(self._redirect(current))
            elif ch == "&":
                self.i += 1
                finish()
            else:
                word, subs = self._word()
                items.extend(subs)
                if self.i < len(self.s) and self.s[self.i] in "<>" and word.raw.isdigit():
                    continue  # file-descriptor prefix: 2>file
                started = True
                self._add_word(current, word)
        if closer:
            raise ShellParseError("unbalanced (")
        self._read_heredocs()
        finish()
        return items

    def _add_word(self, cmd: Command, word: Word) -> None:
        if not cmd.argv:
            match = ASSIGN.match(word.text)
            if match and ASSIGN.match(word.raw):
                cmd.env[match.group(1)] = Word(match.group(2), word.raw, word.dynamic, word.vars)
                return
            if word.text in RESERVED and word.raw == word.text:
                return
        cmd.argv.append(word)

    def _apply_assignments(self, cmd: Command) -> None:
        self.assigned.update(cmd.env)
        if not cmd.argv:
            for key, word in cmd.env.items():
                if word.dynamic:
                    self.env.pop(key, None)
                else:
                    self.env[key] = word.text
        elif cmd.name in ("export", "declare", "typeset", "readonly", "local"):
            for word in cmd.args:
                match = ASSIGN.match(word.text)
                if match:
                    self.assigned.add(match.group(1))
                    if word.dynamic:
                        self.env.pop(match.group(1), None)
                    else:
                        self.env[match.group(1)] = match.group(2)

    def _redirect(self, cmd: Command) -> list:
        s, subs = self.s, []
        if s.startswith("<<<", self.i):
            self.i += 3
            op = "<<<"
        elif s.startswith("<<", self.i):
            self.i += 2
            strip = s.startswith("-", self.i)
            if strip:
                self.i += 1
            self._skip_blank()
            word, _ = self._word()
            self.pending.append((cmd, word.text, strip))
            return []
        elif s.startswith(("<(", ">("), self.i):
            self.i += 2
            inner = _Parser(self.s, dict(self.env), self.assigned)
            inner.i, inner.pending = self.i, self.pending
            body = inner.parse(")")
            self.i = inner.i
            cmd.argv.append(Word("<process-substitution>", "<(...)", dynamic=True))
            return [OPEN, *body, CLOSE]
        else:
            match = re.match(r"&>>|&>|>>|>&|<&|>\||<>|>|<", s[self.i :])
            op = match.group(0)
            self.i += len(op)
        self._skip_blank()
        word, subs = self._word()
        cmd.redirects.append((op, word))
        return subs

    def _skip_blank(self) -> None:
        while self.i < len(self.s) and self.s[self.i] in " \t":
            self.i += 1

    def _read_heredocs(self) -> None:
        for cmd, delim, strip in self.pending:
            body = []
            while self.i < len(self.s):
                end = self.s.find("\n", self.i)
                end = len(self.s) if end < 0 else end
                line = self.s[self.i : end]
                self.i = min(end + 1, len(self.s))
                if (line.lstrip("\t") if strip else line) == delim:
                    break
                body.append(line)
            cmd.heredocs.append("\n".join(body))
        self.pending = []

    def _word(self) -> tuple[Word, list]:
        s, start = self.s, self.i
        word, subs = Word(), []
        while self.i < len(s):
            ch = s[self.i]
            if ch in METACHARS:
                break
            if ch == "\\":
                if s[self.i + 1 : self.i + 2] != "\n":
                    word.text += s[self.i + 1 : self.i + 2]
                self.i += 2
            elif ch == "'":
                end = s.find("'", self.i + 1)
                if end < 0:
                    raise ShellParseError("unterminated single quote")
                word.text += s[self.i + 1 : end]
                self.i = end + 1
            elif ch == "$" and s[self.i + 1 : self.i + 2] == "'":
                word.text += self._ansi()
            elif ch == '"':
                subs += self._double(word)
            elif ch == "$":
                subs += self._dollar(word)
            elif ch == "`":
                subs += self._backtick(word)
            else:
                if ch in "*?[{":
                    word.glob = True
                word.text += ch
                self.i += 1
        word.raw = s[start : self.i]
        return word, subs

    def _ansi(self) -> str:
        s, out = self.s, []
        self.i += 2
        while self.i < len(s) and s[self.i] != "'":
            ch = s[self.i]
            if ch != "\\":
                out.append(ch)
                self.i += 1
                continue
            nxt = s[self.i + 1 : self.i + 2]
            hexa = re.match(r"x([0-9a-fA-F]{1,2})|u([0-9a-fA-F]{1,4})|([0-7]{1,3})", s[self.i + 1 :])
            if hexa:
                if hexa.group(3):
                    out.append(chr(int(hexa.group(3), 8)))
                else:
                    out.append(chr(int(hexa.group(1) or hexa.group(2), 16)))
                self.i += 1 + len(hexa.group(0))
            else:
                out.append(ANSI.get(nxt, nxt))
                self.i += 2
        if self.i >= len(s):
            raise ShellParseError("unterminated $' quote")
        self.i += 1
        return "".join(out)

    def _double(self, word: Word) -> list:
        s, subs = self.s, []
        self.i += 1
        while True:
            if self.i >= len(s):
                raise ShellParseError("unterminated double quote")
            ch = s[self.i]
            if ch == '"':
                self.i += 1
                return subs
            if ch == "\\":
                nxt = s[self.i + 1 : self.i + 2]
                if nxt in ('"', "\\", "$", "`"):
                    word.text += nxt
                elif nxt != "\n":
                    word.text += "\\" + nxt
                self.i += 2
            elif ch == "$":
                subs += self._dollar(word)
            elif ch == "`":
                subs += self._backtick(word)
            else:
                word.text += ch
                self.i += 1

    def _dollar(self, word: Word) -> list:
        s = self.s
        if s.startswith("$((", self.i):
            end = s.find("))", self.i)
            if end < 0:
                raise ShellParseError("unterminated $((")
            word.text += s[self.i : end + 2]
            word.dynamic = True
            self.i = end + 2
            return []
        if s.startswith("$(", self.i):
            self.i += 2
            inner = _Parser(self.s, dict(self.env), self.assigned)
            inner.i = self.i
            body = inner.parse(")")
            self.i = inner.i
            word.text += "$(...)"
            word.dynamic = True
            return [OPEN, *body, CLOSE]
        if s.startswith("${", self.i):
            end = s.find("}", self.i)
            if end < 0:
                raise ShellParseError("unterminated ${")
            body = s[self.i + 2 : end]
            self.i = end + 1
            name = re.match(r"[#!]?([A-Za-z_][A-Za-z0-9_]*)", body)
            if name:
                word.vars.append(name.group(1))
            if name and name.group(0) == body and body in self.env:
                word.text += self.env[body]
            else:
                word.text += "${" + body + "}"
                word.dynamic = True
            return []
        match = re.match(r"\$([A-Za-z_][A-Za-z0-9_]*|[0-9@*#?$!-])", s[self.i :])
        if not match:
            word.text += "$"
            self.i += 1
            return []
        name = match.group(1)
        self.i += len(match.group(0))
        word.vars.append(name)
        if name in self.env:
            word.text += self.env[name]
        else:
            word.text += "$" + name
            word.dynamic = True
        return []

    def _backtick(self, word: Word) -> list:
        s = self.s
        end = self.i + 1
        while end < len(s) and s[end] != "`":
            end += 2 if s[end] == "\\" else 1
        if end >= len(s):
            raise ShellParseError("unterminated backtick")
        body = re.sub(r"\\([`\\$])", r"\1", s[self.i + 1 : end])
        self.i = end + 1
        word.text += "$(...)"
        word.dynamic = True
        return [OPEN, *_Parser(body, dict(self.env), self.assigned).parse(), CLOSE]


def _strip_wrappers(cmd: Command) -> Command:
    """Remove prefixes that only change how the real command starts (env, sudo, timeout, ...)."""
    argv, env = list(cmd.argv), dict(cmd.env)
    implicit = False
    while argv:
        name = os.path.basename(argv[0].text).lower()
        rest = argv[1:]
        if name == "env":
            while rest and (rest[0].text.startswith("-") or ASSIGN.match(rest[0].text)):
                word = rest.pop(0)
                match = ASSIGN.match(word.text)
                if match:
                    env[match.group(1)] = Word(match.group(2), word.raw, word.dynamic, word.vars)
                elif word.text in ("-u", "--unset", "-C", "--chdir", "-S", "--split-string") and rest:
                    rest.pop(0)
        elif name in ("sudo", "doas"):
            while rest and rest[0].text.startswith("-"):
                flag = rest.pop(0).text
                if flag in ("-u", "-g", "-h", "-p", "-U", "-C", "-T", "-r", "-t") and rest:
                    rest.pop(0)
        elif name in ("command", "builtin", "exec", "nohup", "setsid", "caffeinate", "unbuffer"):
            while rest and rest[0].text.startswith("-"):
                flag = rest.pop(0).text
                if flag in ("-v", "-V"):
                    return Command(piped=cmd.piped)  # `command -v git` only looks the name up
        elif name in ("nice", "ionice", "stdbuf", "chronic"):
            while rest and rest[0].text.startswith("-"):
                flag = rest.pop(0).text
                if flag in ("-n", "-c", "-i", "-o", "-e") and rest:
                    rest.pop(0)
        elif name in ("timeout", "gtimeout"):
            while rest and rest[0].text.startswith("-"):
                flag = rest.pop(0).text
                if flag in ("-k", "-s") and rest:
                    rest.pop(0)
            if rest:
                rest.pop(0)
        elif name in ("xargs", "parallel"):
            while rest and rest[0].text.startswith("-"):
                flag = rest.pop(0).text
                if flag in ("-I", "-n", "-P", "-L", "-d", "-E", "-s") and rest:
                    rest.pop(0)
            implicit = True
        else:
            break
        argv = rest
    result = Command(argv, env, cmd.redirects, cmd.heredocs, cmd.piped)
    if implicit:
        result.argv = argv + [Word("$XARGS", "$XARGS", dynamic=True)]
    return result


def _literal_stdin(cmd: Command | None) -> str | None:
    """The text an `echo`/`printf` pipes out, when it is fully known."""
    if cmd is None or cmd.name not in ("echo", "printf"):
        return None
    words = [w for w in cmd.args if not w.text.startswith("-")]
    if any(w.dynamic for w in words):
        return None
    return " ".join(w.text for w in words)


def flatten(text: str, env: dict[str, str] | None = None, assigned: set[str] | None = None) -> list:
    """Every simple command `text` can run, in order, with nested shells opened up."""
    env = env if env is not None else {}
    assigned = assigned if assigned is not None else set()
    out: list = []
    for item in _Parser(text, env, assigned).parse():
        if not isinstance(item, Command):
            out.append(item)
            continue
        cmd = _strip_wrappers(item)
        assigned.update(cmd.env)
        name = cmd.name
        if name == "eval":
            out += [OPEN, *_opaque_or(" ".join(w.text for w in cmd.args), cmd, env, assigned), CLOSE]
        elif name in SHELLS:
            out += _open_shell(cmd, env, assigned)
        elif name == "find":
            out.append(cmd)
            out += _find_exec(cmd, env, assigned)
        else:
            out.append(cmd)
    return out


def _opaque_or(code: str, cmd: Command, env, assigned) -> list:
    if any(w.dynamic for w in cmd.args):
        cmd.opaque = "eval of a value that is only known at run time"
        return [cmd]
    return flatten(code, dict(env), assigned)


def _open_shell(cmd: Command, env, assigned) -> list:
    args = cmd.args
    for index, word in enumerate(args):
        if word.text.startswith("-") and not word.text.startswith("--") and "c" in word.text:
            if index + 1 >= len(args):
                raise ShellParseError(f"{cmd.name} -c without a command")
            code = args[index + 1]
            if code.dynamic:
                cmd.opaque = f"{cmd.name} -c with a value only known at run time"
                return [cmd]
            return [OPEN, *flatten(code.text, dict(env), assigned), CLOSE]
    positional = [w for w in args if not w.text.startswith("-")]
    if positional:
        cmd.opaque = ""  # a script file: not parsed here; see docs/known-limitations.md
        return [cmd]
    if cmd.heredocs:
        return [OPEN, *flatten("\n".join(cmd.heredocs), dict(env), assigned), CLOSE]
    here = [w for op, w in cmd.redirects if op == "<<<"]
    if here and not here[0].dynamic:
        return [OPEN, *flatten(here[0].text, dict(env), assigned), CLOSE]
    literal = _literal_stdin(cmd.piped)
    if literal is not None:
        return [OPEN, *flatten(literal, dict(env), assigned), CLOSE]
    if cmd.piped is not None or any(op == "<" for op, _ in cmd.redirects):
        cmd.opaque = f"{cmd.name} reading code from stdin"
    return [cmd]


def _find_exec(cmd: Command, env, assigned) -> list:
    out, args = [], cmd.args
    index = 0
    while index < len(args):
        if args[index].text in ("-exec", "-execdir", "-ok", "-okdir"):
            end = index + 1
            while end < len(args) and args[end].text not in (";", "+"):
                end += 1
            inner = args[index + 1 : end]
            if inner:
                sub = _strip_wrappers(Command(argv=inner, redirects=[], heredocs=[]))
                if sub.name in SHELLS:
                    out += _open_shell(sub, env, assigned)
                else:
                    out.append(sub)
            index = end
        index += 1
    return out


def simple_commands(text: str) -> list[Command]:
    return [item for item in flatten(text) if isinstance(item, Command)]
