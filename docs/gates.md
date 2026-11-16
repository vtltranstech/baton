# Gates and hooks

## Human gates
| Gate | Who | What |
| --- | --- | --- |
| 1 | Product Owner | sets `Ready`, through `/ready` after an AskUserQuestion answer |
| 2 | Senior Engineer reads, Tech Lead decides | design: Approve, Request changes, or Block. Light track at or above the auto-pass confidence, and hotfix, auto-pass and are recorded |
| 3 | per lane, see [confidence.md](confidence.md) | sets `Approved` |

A human merges every PR: each story's code PRs and its docs PR (`story/<F>-<S>`), all to the repo's default branch, in one sitting; then `baton tag <S>` on that branch marks the version. Agents never commit to the default branch.

## Hooks
All are PreToolUse, exit 2 with the reason on stderr, and are wired with `onFailure: "block"`, so a hook that cannot start blocks the call too.

| Hook | Matcher | Refuses |
| --- | --- | --- |
| `protect_main.py` | Bash | commit-like commands on main, master or the repo's default branch (`origin/HEAD`) in the target repo; push to them; any force push; push `--delete`, `--all`, `--mirror`, `--prune`; `git merge`; `git pull` without `--ff-only` or `--rebase`; `git branch -D`; `git tag -d`; moving main with `update-ref`, `checkout -B`, `branch -f`; `gh pr merge` |
| `protect_env.py` | Bash | datastore URI literals; database clients without the profile's variable, with another variable, or with a target override; write operations in mongosh |
| `commit_scope.py` | Bash | in the central repo on a `story/<F>-<S>` branch, a commit holding another story's or another feature's files (also what a `git add`, `mv` or removal in the same command would stage); shared files pass: `docs/status.md`, `docs/metrics.md`, `docs/architecture/*`, `profile/domain.md`, `profile/sensors/README.md` |
| `state_gate.py` | Bash, Write, Edit, MultiEdit | a story State the artefacts do not justify; removing the State line; conflicting State lines; Bash writes to a story file |
| `protect_weights.py` | Read, Grep, Glob, Bash, Write, Edit, MultiEdit, NotebookEdit | any read or write of `profile/confidence-weights.yaml`, direct or indirect |

The plan named `Read|Bash` for `protect_weights` and `Write|Edit` for `state_gate`. Both were widened because each has a direct bypass otherwise. Glob passes: it returns names, never content.

## Deliberate decisions on ambiguous commands
| Command | Decision | Why |
| --- | --- | --- |
| `git log --grep="git merge"`, `echo "git push origin main"` | allowed | the shell parser sees a string, not a command |
| `git commit -m "merge main"`, a commit message in a heredoc | allowed | same |
| `git push origin $BRANCH`, `git $SUB`, `cd $DIR && git commit` | refused | the target is only known at run time |
| `git merge --abort`, `git rebase --abort` | allowed | they only leave a state |
| `git pull` | refused unless `--ff-only` or `--rebase` | it can merge |
| `git branch -d done` | allowed | `-d` keeps unmerged work safe; `-D` is refused |
| `git push origin --delete feature/x` | refused | it cannot tell a branch from a tag |
| `echo "mongodb://"`, `grep -rn "jdbc:" src` | allowed | a bare scheme names no server; security reviews search for it |
| any scheme followed by a host, or `jdbc:<driver>`, anywhere including quotes, heredocs and comments | refused | a literal URI should not exist in a command at all |
| `which mongosh`, `grep mongosh README.md` | allowed | they do not run the client |
| `mongosh "$TEST_URI" -f script.js` | allowed after the hook reads the script and finds no write | a script it cannot read is refused |
| `cat s.js \| mongosh "$TEST_URI"` | refused | stdin cannot be checked |
| Any mention of `confidence-weights` in a Bash command, even in a message | refused | text matching fails closed here |
| `grep -r x .` or Grep with no path, in the central repo | refused | it would read `profile/`; pass `docs/`, `../<repo>`, or a file-type filter |
| `sed -i` or a redirect on a story file | refused | use Write or Edit so the gate can check; attachments are exempt |
| Unbalanced quotes | refused | the command cannot be checked |

Bad JSON, a missing field, or a crash inside any hook refuses the call. A missing profile refuses database clients only: nothing else depends on it.

## Story states
`contracts/states.md` is the table; `baton state-check <story-file> <new-state>` enforces it. Stricter readings than the literal text:
- `archunit.txt` is green only if every `Tests run:` line is clean and the total is above zero.
- `## Verdict: PASS` must be the whole line, so the unfilled template `## Verdict: PASS | FAIL` does not count.
- Unknown state names are refused, and the state line is matched in any case and with Markdown emphasis.

The hook judges the story as it will be after the edit, so one edit may add `## Dev summary` and the new State together.
