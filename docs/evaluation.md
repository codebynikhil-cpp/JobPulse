# Evaluation

Phase 1 has no jobs, profiles or matcher. No matching evaluation has been run, and no precision/recall/F1 claims are made. The labeled dataset and evaluation script will be implemented in the applicable later phase defined by `docs/spec.md`.

Phase 5 adds ten hand-authored synthetic acceptance examples in
`backend/app/matching/examples.py` and deterministic unit verification. These are
correctness checks, not the labeled 100-200 real-posting evaluation dataset; no
precision/recall/F1 claim is made. Scoring weights and threshold are configurable
for future evaluation without editing matcher business logic.
