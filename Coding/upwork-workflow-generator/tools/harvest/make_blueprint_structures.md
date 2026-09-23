# Make.com blueprint structures — verified against real exports

Every JSON block below is copied verbatim out of the source file cited above it.
Nothing here is reconstructed or idealised.

---

## 1. `builtin:BasicRouter`

**Shape.** A router is an ordinary module object that carries one extra key, `routes`.

- `module` is always `"builtin:BasicRouter"`, `version` always `1` (observed in all 10
  router occurrences across 9 distinct files).
- `mapper` is `null`. `parameters` is either `null` or `{}` — both occur.
- `routes` is an **array of route objects**, and in every real file examined **each route
  object has exactly one key: `flow`**. There is no `label`, no `condition`, and no
  `default`/`fallback` key on the route itself.
- `routes[i].flow` is a normal `flow` array — the same structure as the scenario's
  top-level `flow`, holding full module objects with their own `id`, `module`,
  `version`, `parameters`, `mapper`, `metadata`.
- **A route's condition is not on the route.** It is a `filter` on the *first module
  inside that route's `flow`*. See section 2.
- A route with no filter on its first module is the fallback: it always runs. Router
  routes are independent and **more than one route can run for the same bundle** —
  unlike `builtin:BasicIfElse`, where only the first matching branch runs.
- Module `id`s are unique across the whole scenario, not per route (below: 5, 7, 20).

**Real example** — 2 routes, each gated by a filter on its first module.
Source: <https://raw.githubusercontent.com/integromat/make-skills/8ee0fef21b0179f102ff272821bb480ba5c96772/skills/make-scenario-building/examples/router-pattern.json>

```json
{
  "id": 5,
  "module": "builtin:BasicRouter",
  "version": 1,
  "parameters": {},
  "mapper": null,
  "metadata": {
    "designer": {
      "x": 600,
      "y": 450
    }
  },
  "routes": [
    {
      "flow": [
        {
          "id": 7,
          "module": "facebook-pages:CreatePost",
          "version": 6,
          "parameters": {},
          "filter": {
            "name": "Facebook posts only",
            "conditions": [
              [
                {
                  "a": "{{6.`0`}}",
                  "b": "FB",
                  "o": "text:contain"
                }
              ]
            ]
          },
          "mapper": {
            "message": "{{6.`1`}}"
          },
          "metadata": {
            "designer": {
              "x": 900,
              "y": 0
            }
          }
        }
      ]
    },
    {
      "flow": [
        {
          "id": 20,
          "module": "twitter:createATweet",
          "version": 6,
          "parameters": {},
          "filter": {
            "name": "Twitter posts only",
            "conditions": [
              [
                {
                  "a": "{{6.`0`}}",
                  "b": "T",
                  "o": "text:contain"
                }
              ]
            ]
          },
          "mapper": {
            "text": "{{6.`1`}}"
          },
          "metadata": {
            "designer": {
              "x": 900,
              "y": 300
            }
          }
        }
      ]
    }
  ]
}
```

---

## 2. Module-level `filter`

**Shape.** `filter` is a sibling of `module` / `version` / `parameters` / `mapper` on a
module object. It gates **the module it is written on** — if the filter does not pass,
that module and everything after it on that branch does not run.

```
{ "name": <string>, "conditions": [ [ {"a": ..., "o": ..., "b": ...}, ... ], ... ] }
```

- `name` is the human label shown on the filter in the editor.
- `conditions` is an **array of arrays**. The **inner** array is joined with **AND**;
  the **outer** array is joined with **OR**. Every real filter observed used a single
  outer group, so the AND level is directly attested (example below) while the OR level
  is the documented semantics of the outer array rather than something observed.
- Each condition is `{"a": left, "o": operator, "b": right}`. Key order varies between
  files (`a,b,o` and `a,o,b` both occur) — it is a JSON object, order is not meaningful.
- For **unary operators (`exist`, `notexist`) the `b` key is omitted entirely.**
- `a` and `b` carry Make expressions in `{{...}}`; backtick-quoted names like
  ``{{6.`0`}}`` reference numbered/awkward output fields.

**Operators actually observed**, with occurrence counts across the corpus:

| operator | n | | operator | n |
|---|---|---|---|---|
| `text:equal` | 10 | | `number:greaterorequal` | 2 |
| `number:greater` | 10 | | `text:contain` | 2 |
| `text:notequal` | 4 | | `number:equal` | 1 |
| `number:lessorequal` | 3 | | `exist` | 1 |
| `notexist` | 3 | | | |

**Example A — two conditions ANDed inside one group.**
Source: <https://raw.githubusercontent.com/integromat/make-skills/8ee0fef21b0179f102ff272821bb480ba5c96772/skills/make-scenario-building/examples/popular-templates/10-sync-notion-to-google-calendar.json>

```json
{
  "id": 3,
  "filter": {
    "name": "Doesn't Exist",
    "conditions": [
      [
        {
          "a": "{{1.properties_value.`Event ID`[].plain_text}}",
          "b": "{{null}}",
          "o": "text:equal"
        },
        {
          "a": "{{1.properties_value.Status.name}}",
          "b": "Scheduled",
          "o": "text:equal"
        }
      ]
    ]
  },
  "mapper": {
    "end": "{{1.properties_value.`Meeting Time`.end}}",
    "start": "{{1.properties_value.`Meeting Time`.start}}",
    "select": "detail",
    "summary": "{{1.properties_value.Title[].plain_text}}",
    "visibility": "default",
    "allDayEvent": false,
    "transparency": "opaque",
    "guestsCanModify": false
  },
  "module": "google-calendar:createAnEvent",
  "version": 5,
  "parameters": {}
}
```

**Example B — unary `notexist`, with `b` omitted.**
Source: <https://raw.githubusercontent.com/Skyvern-AI/skyvern/d999952e59ef42b800adbb3c1a6579365ba801dd/integrations/make/contact_form_make.com_blueprint.json>

```json
{
  "id": 23,
  "module": "skyvern-ai:RunaTaskV1",
  "version": 1,
  "filter": {
    "name": "",
    "conditions": [
      [
        {
          "a": "{{9.`2`}}",
          "o": "text:equal",
          "b": "TRUE"
        },
        {
          "a": "{{9.`3`}}",
          "o": "notexist"
        }
      ]
    ]
  }
}
```

---

## 3. Related nesting shapes (same family as `routes`)

**`builtin:BasicIfElse`** uses `branches` instead of `routes`, and unlike router routes
each branch **does** carry its own keys. Branch objects have
`merge`, `label`, `type` (`"condition"`), `flow`, and `conditions` — the `conditions`
value uses the exact same array-of-arrays shape as a module `filter`. The Else branch
omits `conditions`. Source:
<https://raw.githubusercontent.com/integromat/make-skills/8ee0fef21b0179f102ff272821bb480ba5c96772/skills/make-scenario-building/branching.md>

**AI agent tools** nest the same way a router nests routes, but under `tools`:
`tools` is an array of `{"flow": [...]}` objects, each holding the module the agent may
call. So an "AI tool" is not a distinct module type — it is an ordinary app module
placed inside `tools[i].flow`. Source: <https://raw.githubusercontent.com/integromat/make-skills/8ee0fef21b0179f102ff272821bb480ba5c96772/skills/make-module-configuring/examples/ai-agent-full-blueprint.json>

```json
{
  "id": 2,
  "module": "ai-local-agent:RunLocalAIAgent",
  "version": 0,
  "parameters": {
    "makeConnectionId": 14613
  },
  "mapper": {
    "defaultModel": "gpt-5.4",
    "systemPrompt": "You're a versatile Agent",
    "message": "{{1.message}}",
    "files": [],
    "threadId": "",
    "modelConfig": {
      "recursionLimit": 300,
      "iterationsFromHistoryCount": "10"
    },
    "timeout": "",
    "outputType": "text"
  },
  "tools": [
    {
      "flow": [
        {
          "id": 3,
          "module": "weather:ActionGetCurrentWeather",
          "version": 1,
          "parameters": {},
          "mapper": {
            "type": "name",
            "city": "{{2.city}}"
          }
        }
      ]
    },
    {
      "flow": [
        {
          "id": 4,
          "module": "discord:createMessage",
          "version": 2,
          "parameters": {
            "__IMTCONN__": 11867
          },
          "mapper": {
            "select": "channel",
            "content": "{{2.content}}",
            "message_reference": {},
            "channelId": "1224642245806788641"
          }
        }
      ]
    }
  ]
}
```

---

## 4. Triggers — what is and is not a module

- **Webhook trigger is a module:** `gateway:CustomWebHook` v1, with
  `parameters: {"hook": <int>, "maxResults": <int>}`. Scenarios starting with it have
  `metadata.instant: true`.
- **There is no scheduled-trigger module.** Across all 45 verified blueprint files, no
  exported blueprint contains any `scheduling` field. `metadata` holds only
  `designer`, `instant`, `scenario`, `version`, `zone` (plus optional `notes`), and
  `metadata.scenario` holds only execution settings (`roundtrips`, `maxErrors`,
  `autoCommit`, `sequential`, `confidential`, `dataloss`, `dlq`, `freshVariables`,
  `slots`). A scheduled scenario is simply one whose first module is a **polling app
  trigger** (e.g. `google-sheets:watchRows`) with `metadata.instant: false`; the
  schedule itself lives on the scenario record in the Make API, outside the blueprint.
- `util:BasicTrigger` is **not** a scheduler — it emits fixed literal bundles for
  testing: `parameters: {"values": [{"spec": [{"name": "text", "value": "a"}]}]}`.
- **Generic "filter" is not a module either** — it is the `filter` key of section 2.

Some exports are wrapped as `{"blueprint": {...}}` (the shape the Make API returns)
rather than being the bare scenario object; both occur in the wild.
