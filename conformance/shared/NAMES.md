# Names adopted from interim fixtures

Fixtures in Areas 1–4 used `Tool` and `Hook` artifacts before their schemas existed. Both schemas adopted the interim names unchanged, so these tables are now for reference only; the schemas are normative.

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

Credentials a `native` or `langchain` binding needs are given in `credentials`, a map of names to secret references (`secret://<provider>/<name>`), never inline. Other binding kinds take no `credentials`: `mcp` and `http` bindings use their deployment server's or endpoint's credentials; `agent` and `retrieval` bindings take none.

## Hook `source` — now normative

`Hook` names are normative in [`schemas/config/v1/hook.yaml`](../../schemas/config/v1/hook.yaml), which adopted the names below unchanged; `tools/validate.py` validates every `Hook` artifact against that schema. `credentials` (secret references) is allowed only on a `native` source; a `remote` source uses its deployment endpoint's credentials.

| Kind | Fields |
|---|---|
| `rule` | `when` — CEL expression; `then` — `{ result: annotate, labels: [...] }`, `{ result: block, reasonCode }`, or `{ result: escalate, reasonCode }` (HOOK-090) |
| `native` | `handler` |
| `remote` | `endpoint` — a remote hook ID from the deployment's `remoteHooks` |
| `model` | `model` — `{provider, name, params}`; `instructions`; `maxTokens` |
