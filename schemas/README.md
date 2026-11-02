# Schemas

Normative JSON Schemas (draft 2020-12), authored in YAML and published as JSON (ADR-0001).

## Layout

```
schemas/<area>/v<major>/<name>.yaml
```

| Path | Contents |
|---|---|
| `common/v1/defs.yaml` | Shared definitions: identifiers, timestamps, labels, provenance, usage, enums |
| `core/v1/error.yaml` | The error shape (CORE-190) |
| `core/v1/content.yaml` | Messages, content parts, blob references, tool results (Area 1 §7–8) |
| `core/v1/event.yaml` | Event envelope and every event payload (Area 1 §9, as amended) |
| `config/v1/artifact.yaml` | Artifact envelope (CFG-001–003) and the merge-annotation vocabulary |
| `config/v1/defs.yaml` | Shared configuration blocks: `model`, `context`, sensitivity policies, reviewer rules, durations, CEL, secret references |
| `config/v1/policy-bundle.yaml`, `persona.yaml`, `harness-profile.yaml` | Behavioural kinds (CFG-070, 080, 090, as amended) |
| `config/v1/deployment.yaml` | Deployment (CFG-110, as amended); no merge annotations |
| `config/v1/tool.yaml` | Tool (TOOL-001–004, bindings per Area 4 §4 as amended by Area 7); not a behavioural layer, so no merge annotations |

The `Hook` artifact schema arrives with Area 5 (until then, fixtures use the interim names in `conformance/shared/NAMES.md`); Areas 6–11 add theirs in later Phase 4 pull requests.

## Conventions

- **`$id`**: `https://alphega.io/agentry/schemas/<area>/<name>/v<major>.json`. References between schemas use these IDs.
- **Unions** use a constant `type` field with `if`/`then` per variant, so validators report the specific variant that failed.
- **Closed objects**: core objects use `additionalProperties: false` (or `unevaluatedProperties: false` with composition). Vendor or adapter data goes only in `extensions`.
- **Versioning**: every top-level document carries `schemaVersion`. The schema path's major version changes only with a major contract release (ADR-0002).
- **Merge annotations**: configuration schemas (Areas 2–3) annotate each field with `x-agentry-merge`, each `stricter` field with `x-agentry-order` (strictest first), and secret fields with `x-agentry-secret: true` (CFG-030, CFG-031, CFG-061). `tools/validate.py` checks this, that `override` appears only on the allowlisted display and generation-parameter fields (CFG-033), and that the non-layered kinds (`Deployment`, `Tool`) carry no merge annotations.

## Validating

```
pip install -r tools/requirements.txt
python tools/validate.py
```
