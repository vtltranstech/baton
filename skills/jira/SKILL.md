---
name: jira
description: Jira field and status mapping and the CLI commands agents use once Jira is connected; project key and site come from profile/project.md. Use as /jira to print it.
---
# Jira mapping (used when a Jira tool/MCP is connected; otherwise humans sync from docs/jira-sync-pending.md)

## Issue fields <-> story header
| Jira | Story file |
| --- | --- |
| Issue type | Jira-Type |
| Labels | Labels |
| Key | Jira-Key |
| Summary | title line |
| Description | the Story paragraph + a link to docs/stories/<F>/<S>.md |
| Epic / parent | Feature |

## State <-> Jira transition
| Story State | Jira status |
| --- | --- |
| Draft, Needs Clarification | Backlog |
| Ready | Selected for Development |
| Designed, Design Approved, Design Changes Requested | In Design |
| In Review, QA Pass, QA Fail | In Progress |
| Approved | In Review |
| Documented, Done | Done |
| Blocked | Blocked (add the open question as a comment) |

## Who writes what
- story-drafter creates the issue (type, labels, summary, description).
- release transitions to Done and comments the PR link.
- Humans change type/labels in Jira; the next agent run re-reads them and re-derives the Track. The story header mirrors Jira, never the other way round, once connected.

## Commands (Atlassian acli, when approved for use; the Atlassian Rovo MCP is the alternative)
- Create: `acli jira workitem create --project <KEY> --type <Jira-Type> --summary "<title>" --description-file <story.md> --label <labels> [--parent <epic key>]`; a Bug also sets `--priority` (P0 Highest, P1 High, P2 Medium, P3 Low).
- Transition: `acli jira workitem transition <key> --status "<status from the table above>"` - status never moves by edit.
- Comment the PR: `acli jira workitem comment create <key> --body "PR: <url>"`.
- Read: `acli jira workitem view <key> --json --fields key,issuetype,summary,status,labels,parent`.
- Setup once: `acli jira auth login --web --site <site>`; the project needs an "In Design" and an "In Review" status (team-managed: board column; company-managed: a Jira admin adds it to the workflow).

## One-way mirror (Git to Jira)
- **State:** every State change in Git is mirrored to Jira by the transition above; nothing in Jira moves a story's State. Without a connector the change goes to `docs/jira-sync-pending.md`.
- **Gate decisions:** gates 1, 2 and 3 add a comment with the decision and the deciding human (`Gate 2: Approved by TL, 2026-11-15, confidence 86%`); a gate 0 override adds its recorded reason.
- **Evidence:** at release, `docs/qa/<F>/<S>-evidence.md` is posted as a comment beside the PR links.
- **Ticket as input:** `/stories <KEY>` pulls the issue text into `docs/features/F-xxx.md` with a `jira: <KEY>` header; ACs and rules authored in Jira are input to the drafter, never final until the PO sets Ready in Git.
- **Later, a webhook:** on an issue created with the opt-in label, run `/stories <KEY>`. Not built: it needs an automation outside Claude Code.
