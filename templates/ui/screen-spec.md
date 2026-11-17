# Screen: screen-id
persona: <a persona from profile/project.md>
task: <the decision this screen serves, as the persona would say it>
area: <the UI module>
route: /path/{param}
entry-points: <where the user comes from>
screen-of-record: new
files: <optional: repo:src/path/Screen.tsx, the built screen's files, else found from the route>

## Regions
| region | purpose | fields / actions | component |
| --- | --- | --- | --- |
| header | <why it is there> | fieldA, fieldB | <library component, app component, or New: Name (library: A, B)> |

## Fields
| field | label | source | format | rule |
| --- | --- | --- | --- | --- |
| fieldA | <glossary word> | GET /path/{id} -> fieldA | <format> | - |

## Actions
| action | label | target | permission |
| --- | --- | --- | --- |
| send | Send | POST /path/{id}/send | <permission> |

## States
| state | when | shows |
| --- | --- | --- |
| loading | request in flight | |
| empty | nothing to show | what to do next |
| error | 4xx or 5xx | message and retry |
| partial | part of the data is unresolved | |
| no-permission | 403 | explanation, no data |

## Validation and rules on screen
- <a rule the screen enforces, with its id (R<n>)>

## Accessibility notes
- <reading order, captions, keyboard paths>
