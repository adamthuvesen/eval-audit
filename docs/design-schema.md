# Schema design rules

Validation lives in [eval_audit/schema](../eval_audit/schema): `StudySpec`
([study.py](../eval_audit/schema/study.py)), `RunRecord`
([run_record.py](../eval_audit/schema/run_record.py)), and the audit summary
shapes. The two declared inputs are documented field-by-field in
[STUDY_SCHEMA.md](STUDY_SCHEMA.md) and [INPUT_CONTRACT.md](INPUT_CONTRACT.md);
both are pinned to the code by doc-parity tests under `tests/docs/`.

- Prefer strict Pydantic models with `extra="forbid"`.
- Validate declarations at the boundary. Bad study specs should fail loudly
  before analysis.
- Keep schema declarations aligned with engine behavior. Never accept a field
  that the engine ignores in a decision-relevant way.
- When expanding v0 scope, update schema, analysis, report rendering,
  snapshots, CLI behavior, and docs together, including the parity-checked
  field reference docs.

Canonical `RunRecord` boolean, numeric, and datetime values use strict physical types.
Finite numeric constraints reject NaN and infinity before Polars computes statistics.
Enum strings remain accepted canonical encodings. Token structs may contain null padding from Polars.

`StudySpec` rejects duplicate agent IDs, empty cost metrics, and unsafe study IDs.
Evidence preparation revalidates a defensive study copy because nested declarations remain mutable.
The prepared frames and study copy remain mutable too. Consumers must treat them as owned, read-only evidence.
