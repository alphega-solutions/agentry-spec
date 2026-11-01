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

Areas 2–11 add their schemas in later Phase 4 pull requests.

## Conventions

- **`$id`**: `https://alphega.io/agentry/schemas/<area>/<name>/v<major>.json`. References between schemas use these IDs.
- **Unions** use a constant `type` field with `if`/`then` per variant, so validators report the specific variant that failed.
- **Closed objects**: core objects use `additionalProperties: false` (or `unevaluatedProperties: false` with composition). Vendor or adapter data goes only in `extensions`.
- **Versioning**: every top-level document carries `schemaVersion`. The schema path's major version changes only with a major contract release (ADR-0002).
- **Merge annotations**: configuration schemas (Areas 2–3) annotate each field with `x-agentry-merge`, and secret fields with `x-agentry-secret: true` (CFG-030, CFG-061).

## Validating

```
pip install -r tools/requirements.txt
python tools/validate.py
```
