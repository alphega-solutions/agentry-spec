# Interim names for Tool and Hook artifacts

Fixtures in Areas 1–3 need `Tool` and `Hook` artifacts before their schemas exist (Areas 4–5). They use these names, which the Area 4 and Area 5 schemas **must adopt**.

## Tool `binding`

| Kind | Fields |
|---|---|
| `native` | `handler` — the registered handler name |
| `mcp` | `server` — an MCP server ID from the deployment; `tool` — the tool's name on that server |
| `http` | `endpoint` — an HTTP endpoint ID from the deployment; `operation` — operation ID |
| `agent` | `persona` — `id@version` |
| `retrieval` | `source` — a vector store source ID |
| `langchain` | `tool` — the LangChain tool name |

Credentials a binding needs are given in `credentials`, a map of names to secret references (`secret://<provider>/<name>`), never inline.

## Hook `source`

| Kind | Fields |
|---|---|
| `rule` | `when` — CEL expression; `then` — `{ result: annotate, labels: [...] }`, `{ result: block, reasonCode }`, or `{ result: escalate, reasonCode }` (HOOK-090) |
| `native` | `handler` |
| `remote` | `endpoint` — a remote hook ID from the deployment's `remoteHooks` |
| `model` | `model` — `{provider, name, params}`; `instructions`; `maxTokens` |
