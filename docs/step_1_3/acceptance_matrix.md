# S13 acceptance matrix

Evidence: [per-test results](evidence/cloud_synthetic.json), [test log](evidence/cloud_synthetic.log).

PASS means automated synthetic evidence. Actual cluster checks remain NOT_RUN; no scheduler/VASP pilot or Cron was executed.

| Acceptance | Scope | Status | Automated cases |
|---|---|---|---|
| S13-01 | One dispatch and strict binding | PASS | 1 (PASS) |
| S13-02 | Request redelivery and stable identity | PASS | 3 (PASS) |
| S13-03 | Labels and physical/scientific aliases | PASS | 3 (PASS) |
| S13-04 | Bundle integrity and source immutability | PASS | 7 (PASS) |
| S13-05 | Accepted timeout/crash recovery | PASS | 4 (PASS) |
| S13-06 | Fence-before-spawn crash | PASS | 3 (PASS) |
| S13-07 | Immutable receipt and DB crash recovery | PASS | 15 (PASS) |
| S13-08 | Unknown/delayed observation never retries | PASS | 8 (PASS) |
| S13-09 | Weak/multiple identity evidence | PASS | 6 (PASS) |
| S13-10 | Malformed acknowledgment and bounded clients | PASS | 29 (PASS) |
| S13-11 | User-wide 320-slot admission | PASS | 18 (PASS) |
| S13-12 | Reservation/PE row deduplication | PASS | 3 (PASS) |
| S13-13 | Concurrent writers and CAS/DB failures | PASS | 3 (PASS) |
| S13-14 | Strict dry-run and side-effect-free help | PASS | 2 (PASS) |
| S13-15 | Actual SGE defaults/environment/CLI precedence | NOT_RUN | 5 (PASS) |
| S13-16 | Exact target runtime and benign local SGE pilot | NOT_RUN | 0 (NOT_RUN) |
| S13-17 | Actual approved verified-bundle submission | NOT_RUN | 0 (NOT_RUN) |
| S13-18 | Restore/epoch/orphan evidence blocking | PASS | 4 (PASS) |

Full parameterized test IDs and local blockers are in acceptance_matrix.json.

Full suite: 402 passed, 0 failed, 0 not run; Step 1-2 267, Step 1-3 135.

Cloud Python 3.9.19 / linked SQLite 3.46.0 is test evidence, not exact HPC acceptance.

Reproduce from the repository root with the approved development dependencies:

```sh
PYTHONPATH=src:tests "$AI_CHEM_PY" -B tools/run_submission_acceptance.py
```

This writes public synthetic evidence only; do not use it to publish private HPC outputs.
