# Interim names for Hook artifacts

Fixtures in Areas 1–4 need `Hook` artifacts before their schema exists (Area 5). They use these names, which the Area 5 schema **must adopt**.

## Tool `binding` — now normative

`Tool` names are normative in [`schemas/config/v1/tool.yaml`](../../schemas/config/v1/tool.yaml), which adopted the interim names below unchanged; `tools/validate.py` validates every `Tool` artifact against that schema. The table is kept for reference.

| Kind | Fields |
|---|---|
| `native` | `handler` — the registered handler name |
| `mcp` | `server` — an MCP server ID from the deployment; `tool` — the tool's name on that server |
| `http` | `endpoint` — an HTTP endpoint ID from the deployment; `operation` — operation ID |
| `agent` | `persona` — `id@version` |
| `retrieval` | `source` — a vector store source ID |
| `langchain` | `tool` — the LangChain tool name |

Credentials a binding needs are given in `credentials`, a map of names to secret references (`secret://<provider>/<name>`), never inline.

## Hook `source` — interim

| Kind | Fields |
|---|---|
| `rule` | `when` — CEL expression; `then` — `{ result: annotate, labels: [...] }`, `{ result: block, reasonCode }`, or `{ result: escalate, reasonCode }` (HOOK-090) |
| `native` | `handler` |
| `remote` | `endpoint` — a remote hook ID from the deployment's `remoteHooks` |
| `model` | `model` — `{provider, name, params}`; `instructions`; `maxTokens` |
