# Phase 5 files

New:
- `backend/app/matching/__init__.py`: standalone package boundary.
- `backend/app/matching/config.py`: validated scoring weights and default threshold.
- `backend/app/matching/text.py`: deterministic normalization, phrase/skill evidence, small seed.
- `backend/app/matching/experience.py`: conservative parser and experience provenance.
- `backend/app/matching/matcher.py`: pure input/result contracts, Matcher protocol and implementation.
- `backend/app/matching/examples.py`: ten asserted synthetic acceptance examples.
- `tests/unit/test_matching.py`: parser, matcher, configuration, boundary and dependency tests.
- `docs/matching.md`: precedence, required skills, unknown semantics, scoring and limitations.
- `docs/phase-5-files.md`: this inventory.
- `docs/phase-5-validation.md`: executed verification results.

Updated: `docs/architecture.md`, `docs/product-decisions.md`, `docs/spec.md` and
`docs/evaluation.md` to record the approved contract and evaluation limits.

No canonical schema, models, migrations, existing API/UI, dependencies or lockfiles
changed. No match persistence, scheduler or notification implementation.
