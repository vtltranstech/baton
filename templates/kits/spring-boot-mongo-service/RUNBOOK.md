# <service name>: runbook

## Start
`<start command, e.g. the deployment job or java -jar target/<service name>.jar>`

## Stop
`<stop command or deployment step>`

## Health
`GET <base url>/actuator/health` returns `{"status":"UP"}`. <what DOWN means and the first check>

## Logs
<where the logs go, how to search them, the correlation id field>

## Config
| Variable | Meaning | Where it is set |
| --- | --- | --- |
| `MONGODB_URI` | Mongo connection string | <secret store or deployment config> |
| `<NAME>` | <meaning> | <where> |

## Alerts
| Alert | Fires when | First action |
| --- | --- | --- |
| <alert name> | <condition> | <action> |

## Owners
<team, channel, escalation>
