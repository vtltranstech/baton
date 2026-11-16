---
name: ship
description: Run documentation -> release for one Approved story (/ship S-010); with a feature id, archive a finished feature (/ship F-002).
---
Run the post-approval chain for one story: $ARGUMENTS (a story id such as S-010). A feature id (F-002) means: archive that feature, section Archive below.

Read the workflow skill first. Refuse unless the story's State is Approved. Switch to `story/<feature-id>-<story-id>` first. Then run, as subagents in the foreground, each with its model from `baton models <story-id>`, and wait for its report before the next step, in order:
1. documentation. Then commit the change note, ADRs, `docs/architecture/*` (workspace, CHANGELOG, diagrams), `docs/wiki/`, `docs/context/codebase-map.md`, the generated `profile/` files, the story and `docs/status.md`: `<story-id>: change note; promote architecture (+a elements, +r relationships, ~c changed)`, with the counts `baton c4 --story` printed.
2. release. It pushes this branch and opens the central-repo PR too.
Then run `baton trace <feature-id> --story <story-id>` (the story's folder under docs/stories/ is the feature id; `backlog` stories have none, skip it) so `docs/trace/<feature-id>.html` shows the merged story. Commit the trace page, the story (PR lines, Done), `docs/status.md`, `docs/metrics.md` and any `docs/jira-sync-pending.md`: `<story-id>: trace regenerated; PR <central-repo PR url>`, and push the branch again so the PR shows it.
Finish by printing the PR URL(s), the links to `-evidence.md`, `-confidence.json` and the trace page, and the new docs/status.md row.
If every other story of this feature is Done, this was its last one: say "After the Tech Lead merges this story's PRs, run /ship <feature-id> to archive the feature."

## Archive a finished feature (/ship F-002; contracts/versioning.md section 5)
Run it once every story of the feature is Done and its docs PR is merged into the default branch. It cannot run inside the last story's /ship: that branch does not hold the other stories' merged files, and agents never merge the default branch into it.
1. `git fetch origin`, then `git switch -c archive/<feature-id> origin/<default>` (`workflow` skill: default branch).
2. Every story under `docs/stories/<feature-id>/` must say `State: Done`. If one does not, or a story the feature's trace lists is missing on this branch (its PR is not merged), stop and say which.
3. For each of `stories`, `design`, `qa`, `changes` that has a `docs/<kind>/<feature-id>/` folder: `git mv docs/<kind>/<feature-id> docs/archive/<feature-id>/<kind>`.
4. `baton trace <feature-id>`: it reads the archive, so the page's links now point there.
5. Commit the moves and the trace page: `<feature-id>: archived (<n> stories)`. Push the branch and open its PR, `<feature-id>: archive`. The Tech Lead merges it and runs `baton tag <feature-id>` on the default branch.
Agents never read `docs/archive/`; `/retro` does.
