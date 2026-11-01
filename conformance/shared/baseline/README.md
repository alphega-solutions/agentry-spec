# Baseline configuration

The shared configuration set most fixtures start from (`setup.config.base: baseline`). Fixtures add or replace artifacts in `setup.config.artifacts`.

| Artifact | Purpose |
|---|---|
| `org@1` | Policy bundle: `policyInstructions`, default fallback, `pii`/`phi` sensitivity policies |
| `assistant@1` | Persona with tools `lookup@1` (read) and `update_record@1` (mutating, non-idempotent); primary `scripted-a/model-a`, fallback `scripted-b/model-b` |
| `lookup@1`, `update_record@1` | Tools bound `{ kind: native, handler: test.lookup }` and `{ kind: native, handler: test.update_record }` (interim names, `../NAMES.md`) |
| `default@1` | Buffered profile with explicit TTLs, step limit 8, token budget, retries |
| `streamed@1` | Same, with `streamed` delivery |
| `test@1` | Deployment: two scripted providers, in-memory ports, retention |

`tools/validate.py` validates these artifacts against the configuration schemas. Until the Area 4–5 schemas land, `Tool` and `Hook` artifacts are checked only against the interim binding and source names in `../NAMES.md`.

The policy bundle's instructions field is `policyInstructions` (merge `union`), separate from the persona's `instructions` (`locked`) (CFG-070 as amended 2026-11-01).
