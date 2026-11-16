# <job name>: runbook

## Start
`<scheduler entry or command, e.g. java -jar target/<job name>.jar>`. Schedule: <when it runs>. A rerun is safe: <why>.

## Stop
<how to stop a running execution, and how to restart it from the failed step>

## Health
<how to tell the last run succeeded: exit code, BATCH_JOB_EXECUTION status, the listener's count line>

## Logs
<where the logs go, how to search them; the `step=... read=... written=...` line per step>

## Config
| Variable | Meaning | Where it is set |
| --- | --- | --- |
| `ITEMS_INBOUND_FILE` | input file | <where> |
| `ITEMS_OUTBOUND_FILE` | output file | <where> |
| `JOB_REPOSITORY_URL` | job repository database | <secret store or deployment config> |

## Alerts
| Alert | Fires when | First action |
| --- | --- | --- |
| <job failed> | <exit code not 0> | <action> |
| <job late> | <not finished by time> | <action> |

## Owners
<team, channel, escalation>
