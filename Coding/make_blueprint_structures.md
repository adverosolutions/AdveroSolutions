# Make.com blueprint structures — verified against real exports

Every JSON block below is copied verbatim from the source cited above it.

**How sources were trusted.** Module ids were accepted only if they appear in the
official `integromat/make-skills` repo, OR in blueprints from **two independent
repositories**, OR in a single file carrying exporter bookkeeping (`__IMTCONN__`
connection ids / the `metadata.parameters` field-spec dump) with no template
placeholders. That test rejected 28 of 586 harvested ids — including
`slack:createMessage` (wrong case for `slack:CreateMessage`), `gmail:sendEmail`
(Gmail's real namespace is `google-email`), `whatsapp-business:sendTextMessage`
(real namespace is `whatsapp-business-cloud`), `openai:CreateChatCompletion`
(real namespace is `openai-gpt-3`), and a fabricated `builtin:BasicScheduler`.
Those are exactly the plausible-but-wrong ids that Make's importer rejects.

---

## 1. `builtin:BasicRouter`

**Shape.** A router is an ordinary module object carrying one extra key, `routes`.

- `module` is always `"builtin:BasicRouter"`. `version` is `1` where present.
- `mapper` is `null`; `parameters` is `null` or `{}`.
- `routes` is an **array of route objects**. Each route object holds a `flow` array —
  a normal flow of full module objects, exactly like the scenario's top-level `flow`.
- **In 606 of 612 route objects observed, `flow` is the only key.** The condition for a
  route is normally not on the route: it is a `filter` on the **first module inside**
  that route's `flow` (section 2). A route whose first module has no filter always runs.
- Router routes are independent and **more than one route may run for the same bundle** —
  unlike `builtin:BasicIfElse`, where only the first matching branch runs.
- Module `id`s are unique across the whole scenario, not per route.

**Real example — 2 routes, each gated by a filter on its first module.**
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

### 1a. Route objects can carry more than `flow`

The single-key form is overwhelmingly the common case, but not a rule. Across the corpus
three other route key sets occur: `{"disabled","flow"}` (3),
`{"filter","flow","label"}` (2), and `{"filter","flow"}` (1). When a route carries its own `filter`, that filter sits on
the **route**, not on a module — so both placements are legal and a parser must handle both.

Source: <https://gist.githubusercontent.com/arielrgualtieri-cloud/34461de7300a8d87d1161bfb0c830ad6/raw/>

```json
{
  "module": "builtin:BasicRouter",
  "version": 1,
  "routes": [
    {
      "label": "🔥 Prioridad ALTA",
      "filter": {
        "name": "🔥 Prioridad ALTA",
        "conditions": [
          [
            {
              "a": "{{parseJSON(2.choices[].message.content).prioridad}}",
              "b": "ALTA",
              "o": "text:equal"
            }
          ]
        ]
      },
      "flow": [
        {
          "id": 4,
          "module": "google-sheets:updateRow",
          "version": 2,
          "parameters": {
            "__IMTCONN__": {
              "data": {
                "scoped": "true",
                "connection": "google"
              },
              "label": "Google — Stratos Mobility"
            },
            "spreadsheetId": "REEMPLAZAR_CON_TU_SPREADSHEET_ID",
            "sheetId": "Leads",
            "rowNumber": "{{1.__IMTROWIDX__}}"
          },
          "mapper": {
            "prioridad": "ALTA",
            "score_ia": "{{parseJSON(2.choices[].message.content).score}}",
            "motivo_ia": "{{parseJSON(2.choices[].message.content).motivo}}",
            "estado": "Listo para contacto comercial",
            "fecha_clasificacion": "{{formatDate(now; \"YYYY-MM-DD HH:mm:ss\")}}"
          }
        },
        {
          "id": 5,
          "module": "gmail:ActionSendEmail",
          "version": 1,
          "parameters": {
            "__IMTCONN__": {
              "data": {
                "scoped": "true",
                "connection": "google"
              },
              "label": "Google — Stratos Mobility"
            }
          },
          "mapper": {
            "to": "ventas@stratosmobility.com",
            "subject": "🔥 Lead ALTA: {{1.nombre}} ({{1.empresa}}) — Score {{parseJSON(2.choices[].message.content).score}}/10",
            "content": "<div style=\"font-family:Arial,sans-serif;max-width:600px\">\n  <h2 style=\"color:#c0392b\">🔥 Lead de ALTA prioridad — acción inmediata</h2>\n  <table style=\"border-collapse:collapse;width:100%\">\n    <tr><td style=\"padding:6px;font-weight:bold;width:120px\">Nombre</td><td style=\"padding:6px\">{{1.nombre}}</td></tr>\n    <tr style=\"background:#f9f9f9\"><td s
```

A route may also be switched off with `"disabled": true`
(<https://raw.githubusercontent.com/michael-cannon/make-goggles/main/UTIL8686IG%20%23errors-automation%20Notice.json>).

### 1b. Routers nest

Routers **do** appear inside other routers' routes — 74 nested occurrences across the
corpus (243 routers across 167 files), up to three levels deep. A nested router is just a router module placed in a
`routes[i].flow`. Below, module ids only (parameters elided) to show the nesting.
Source: <https://raw.githubusercontent.com/nateshelly/make-ai-automation-agents-blueprints/main/Gmail_and_Email_Automation/Inbound%20SDR%20Agent>

```json
{
  "id": 33,
  "module": "builtin:BasicRouter",
  "version": 1,
  "routes": [
    {
      "flow": [
        {
          "id": 12,
          "module": "airtable:ActionSearchRecords",
          "version": 3,
          "filter": {
            "name": "Email is NOT from <mailer-daemon@googlemail.com>",
            "conditions": [
              [
                {
                  "a": "{{27.result}}",
                  "b": "2",
                  "o": "number:equal"
                }
              ]
            ]
          }
        },
        {
          "id": 17,
          "module": "openai-gpt-3:CreateCompletion",
          "version": 1
        },
        {
          "id": 39,
          "module": "regexp:Parser",
          "version": 1
        },
        {
          "id": 18,
          "module": "builtin:BasicRouter",
          "version": 1,
          "routes": [
            {
              "flow": [
                {
                  "id": 58,
                  "module": "airtable:ActionCreateRecord",
                  "version": 3,
                  "filter": {
                    "name": "1️⃣ AI Reply (Confident Match)",
                    "conditions": [
                      [
                        {
                          "a": "{{39.`$1`}}",
                          "b": "1",
                          "o": "number:equal"
                        },
                        {
                          "a": "{{39.`$2`}}",
                          "b": "40",
                          "o": "number:greater"
                        }
                      ]
                    ]
                  }
                },
                {
                  "id": 2,
                  "module": "openai-gpt-3:CreateCompletion",
                  "version": 1
                },
                {
                  "id": 52,
                  "module": "builtin:BasicRouter",
                  "version": 1,
                  "routes": [
                    {
          
```

Disconnected modules are not lost on export — they are parked under
`metadata.designer.orphans`, which is an array of module arrays and can itself contain
routers with full `routes` trees.

---

## 2. Module-level `filter`

**Shape.** `filter` is a sibling of `module` / `version` / `parameters` / `mapper` on the
module object it gates. If it does not pass, that module and everything downstream of it
on that branch does not run.

```
{ "name": <string>, "conditions": [ [ {"a": ..., "o": ..., "b": ...}, ... ], ... ] }
```

- `conditions` is an **array of arrays**: the **inner** array is ANDed, the **outer**
  array is ORed. Both levels are attested below.
- Each condition is `{"a": left, "o": operator, "b": right}`. Key order varies between
  files (`a,b,o` and `a,o,b` both occur); it is a JSON object, so order is not meaningful.
- For **unary operators (`exist`, `notexist`) the `b` key is omitted entirely**.
- `a`/`b` hold Make expressions in `{{...}}`; backticks quote awkward field names,
  e.g. ``{{6.`0`}}``.

**Operators observed in trusted sources.** The `:ci` suffix is case-insensitive.
Operator strings appearing only in files that failed the trust test
(`number:greaterEqual`, `text:contains`, `number:lessThan`, `string:equal`) are excluded
— they look hand-typed and are probably invalid.

| operator | occurrences | files |
|---|---|---|
| `text:equal` | 262 | 96 |
| `text:contain:ci` | 86 | 12 |
| `exist` | 79 | 47 |
| `notexist` | 59 | 30 |
| `text:contain` | 53 | 21 |
| `text:notequal` | 44 | 23 |
| `text:equal:ci` | 31 | 15 |
| `number:greater` | 30 | 19 |
| `number:equal` | 18 | 11 |
| `number:greaterorequal` | 16 | 11 |
| `text:notcontain` | 14 | 11 |
| `array:contain` | 12 | 6 |
| `text:notcontain:ci` | 8 | 8 |
| `number:notequal` | 6 | 5 |
| `text:pattern:ci` | 6 | 1 |
| `array:notequal` | 5 | 3 |
| `array:notcontain` | 5 | 2 |
| `text:notpattern:ci` | 5 | 2 |
| `number:lessorequal` | 5 | 4 |
| `date:lessorequal` | 4 | 3 |
| `date:less` | 4 | 3 |
| `boolean:equal` | 3 | 3 |
| `date:greaterorequal` | 3 | 3 |
| `date:greater` | 3 | 3 |
| `number:less` | 2 | 2 |
| `array:equal` | 2 | 2 |
| `text:notequal:ci` | 2 | 2 |
| `array:greaterorequal` | 1 | 1 |
| `time:lessorequal` | 1 | 1 |
| `array:greater` | 1 | 1 |
| `text:endwith:ci` | 1 | 1 |
| `array:contain:ci` | 1 | 1 |
| `boolean:notequal` | 1 | 1 |
| `text:startwith:ci` | 1 | 1 |
| `text:pattern` | 1 | 1 |
| `text:startwith` | 1 | 1 |



**Example A — two conditions ANDed (one inner group).**
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

**Example B — two groups ORed (outer array length 2).**
Source: <https://gist.githubusercontent.com/AME22654/60d04c7457401ee51f57efb88b95dceb/raw/>

```json
{
  "name": "Sort",
  "conditions": [
    [
      {
        "a": "{{3.Sort}}",
        "b": "Likes",
        "o": "text:equal"
      }
    ],
    [
      {
        "a": "{{3.Sort}}",
        "b": "Comments",
        "o": "text:equal"
      }
    ]
  ]
}
```

**Example C — unary `notexist`, `b` omitted.**
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

## 3. Triggers, and where scheduling actually lives

- **Webhook trigger is a module:** `gateway:CustomWebHook` v1 with
  `parameters: {"hook": <int>, "maxResults": <int>}`. Mail equivalent:
  `gateway:CustomMailHook` v1. Scenarios starting with one have `metadata.instant: true`.
- **There is no scheduled-trigger module.** A scheduled scenario is one whose first
  module is a **polling app trigger** (e.g. `google-sheets:watchRows`) with
  `metadata.instant: false`.
- **Scheduling is an envelope field, and which envelope matters.** A plain
  *scenario blueprint* export (`{name, flow, metadata}`) contains no scheduling at all —
  `metadata` holds only `designer`, `instant`, `scenario`, `version`, `zone` (+ optional
  `notes`). A **template** export uses a different, larger envelope that *does* carry it:

Source: <https://raw.githubusercontent.com/integromat/make-skills/8ee0fef21b0179f102ff272821bb480ba5c96772/skills/make-scenario-building/examples/popular-templates/01-chatgpt-completions-from-google-sheets.json>

```json
{
  "blueprint": {
    "name": null,
    "flow": "…3 modules…",
    "metadata": {
      "instant": false,
      "version": 1,
      "designer": {
        "orphans": []
      },
      "scenario": {
        "dlq": false,
        "slots": null,
        "dataloss": false,
        "maxErrors": 3,
        "autoCommit": true,
        "roundtrips": 1,
        "sequential": false,
        "confidential": false,
        "freshVariables": false,
        "autoCommitTriggerLast": true
      }
    }
  },
  "controller": {
    "name": "Generate ChatGPT Completions from Google Sheets Rows",
    "description": "Effortlessly enhance your content creation process by integrating ChatGPT with Google Sheets. This powerful template allows you to automatically generate relevant completions, ranging from SEO keywords to custom responses, boosting productivity and content quality with ease."
  },
  "scheduling": {
    "type": "indefinitely",
    "interval": 900
  },
  "language": "en",
  "metadata": {
    "templateUrl": "10570-create-new-completions-with-openai-chatgpt-from-new-rows-in-google-sheets",
    "usage": 107031
  }
}
```

  `scheduling.type` values observed: `"indefinitely"` (with `interval` in seconds) and
  `"immediately"`. Note the scenario itself is nested under `blueprint` here — importers
  must handle both the bare and the wrapped shape.
- `util:BasicTrigger` is **not** a scheduler: it emits fixed literal bundles for testing,
  `parameters: {"values": [{"spec": [{"name": "text", "value": "a"}]}]}`.
- **A generic "filter" is not a module** — it is the `filter` key of section 2.

---

## 4. Related nesting shapes

**`builtin:BasicIfElse`** uses `branches` rather than `routes`, and its branch objects
*do* carry their own keys: `merge`, `label`, `type` (`"condition"`), `flow`, and
`conditions` — where `conditions` uses the identical array-of-arrays shape as a module
`filter`. The Else branch omits `conditions`. It is emitted as two consecutive top-level
modules: `builtin:BasicIfElse` immediately followed by `builtin:BasicMerge`. Source:
<https://raw.githubusercontent.com/integromat/make-skills/8ee0fef21b0179f102ff272821bb480ba5c96772/skills/make-scenario-building/branching.md>

**AI agent tools** nest like router routes but under `tools`: an array of
`{"flow": [...]}` objects. So an "AI tool" is not a distinct module type — it is an
ordinary app module placed inside `tools[i].flow`. Source: <https://raw.githubusercontent.com/integromat/make-skills/8ee0fef21b0179f102ff272821bb480ba5c96772/skills/make-module-configuring/examples/ai-agent-full-blueprint.json>

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
          "version": 1
        }
      ]
    },
    {
      "flow": [
        {
          "id": 4,
          "module": "discord:createMessage",
          "version": 2
        }
      ]
    }
  ]
}
```
