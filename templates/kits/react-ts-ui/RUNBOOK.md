# <app name>: runbook

## Start
`<deployment step; the build output is dist/, served by <web server or platform>>`

## Stop
`<how to take it down or roll back to the previous build>`

## Health
<the URL to check and what a healthy page shows; the backend health URL it depends on>

## Logs
<where browser errors and server access logs go, how to search them>

## Config
| Variable | Meaning | Where it is set |
| --- | --- | --- |
| `VITE_API_BASE_URL` | backend base URL, fixed at build time | <build config> |
| `<NAME>` | <meaning> | <where> |

## Alerts
| Alert | Fires when | First action |
| --- | --- | --- |
| <alert name> | <condition> | <action> |

## Owners
<team, channel, escalation>
