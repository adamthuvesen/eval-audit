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
  snapshots, CLI behavior, and docs together — including the parity-checked
  field reference docs.
