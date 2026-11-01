# Baseline configuration

The shared configuration set most fixtures start from (`setup.config.base: baseline`). Fixtures add or replace artifacts in `setup.config.artifacts`.

| Artifact | Purpose |
|---|---|
| `org@1` | Policy bundle: instructions, default fallback, `pii`/`phi` sensitivity policies |
| `assistant@1` | Persona with tools `lookup@1` (read) and `update_record@1` (mutating, non-idempotent); primary `scripted-a/model-a`, fallback `scripted-b/model-b` |
| `default@1` | Buffered profile with explicit TTLs, step limit 8, token budget, retries |
| `streamed@1` | Same, with `streamed` delivery |
| `test@1` | Deployment: two scripted providers, in-memory ports, retention |

`tools/validate.py` validates these artifacts against the configuration schemas (`Tool` artifacts once the Area 4 schema lands).
