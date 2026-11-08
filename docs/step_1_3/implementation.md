# Step 1-3 implementation and handoff

Base: `b510177725075ce549ef5d5fca8bcf050ab8ed03`, branch
`codex/step1-2-handoff`. Work branch: `codex/step1-3-submission`.
The attached Detailed Design and Task Specification supplied the design criteria;
the user's additional preservation, effective-SGE and operational-approval
requirements govern this implementation. No prior conversation was used as an
operational approval.

Start with [compatibility_map.md](compatibility_map.md), the captured actual
synthetic [manifest shape](synthetic_manifest_shape.json), and the
[local runbook](runbook.md). The [acceptance matrix](acceptance_matrix.md) links
individual test IDs and exact automated evidence; [known_limits.md](known_limits.md)
lists the unverified boundaries.

| Task | Implemented responsibility | Evidence |
|---|---|---|
| T13-01 | Actual Step 1-2 API/manifest/state/root audit and read-only adapter | compatibility map; original suite; integrity tests |
| T13-02 | Strict schemas, separate science/location/request identity and immutable token/run | models.py, identity.py; contracts and alias tests |
| T13-03 | Typed fixed argv, strict terse/SGE XML/detail/accounting fixture dialect | sge.py; synthetic fixture/parser tests |
| T13-04 | Concurrent bounded pipes, timeout/output caps, explicit env and process permit | runner.py; harmless subprocess integration tests |
| T13-05 | Verified bundle and effective execution gates, complete fresh owner-wide admission | preflight.py, admission.py; slot/integrity/gate tests |
| T13-06 | Additive existing DB tables, common lock, uniqueness/CAS, independent restore ledger | store.py; concurrency, rollback and epoch tests |
| T13-07 | Immutable private intent/argv/result/raw/observation evidence with fsync | receipts.py; conflict, fsync, ENOSPC and DB recovery tests |
| T13-08 | Safe pending resume, one fenced dispatch, explicit accepted/uncertain states | service.py; fault windows and durable fake server |
| T13-09 | Receipt-first exact identity reconciliation; weak/multiple/no match never resubmits | reconcile.py; live/accounted/repeated recovery tests |
| T13-10 | Additive CLI, strict no-write dry-run, one-shot pilot worker and private archives | cli.py, worker.py; spies, help and worker tests |
| T13-11 | Independent durable accepted-job fake, fault injection and per-test acceptance logs | tests/submission_support.py; run_submission_acceptance.py |
| T13-12 | Private registration/proof drafts, equivalence review and separately approved pilot procedure | runbook.md; incomplete draft schemas; actual gates NOT_RUN |

All original Step 1-2 source, schemas, fixtures and 267 regression tests are
preserved. The only edited pre-existing file is pyproject.toml, adding the new
subpackage's schema package-data entry. No old CLI or preparation worker is
silently repurposed. The new CLI is:

```sh
python -B -m ai_chem_input.submission --help
```

It operates in the same preparations.sqlite3 and controller.lock as Step 1-2.
No preparation row/schema version or input bundle is mutated by submission.
Only explicit approved live submission may use the local SGE clients. Defaults
and incomplete public config drafts cannot dispatch. Real clients independently
require the exact target runtime; fake tests do not supply real approval.

The CAS transaction commits before any qsub. Only the current process receives
a command-bound single-use permit. The separate durable fence ledger is written
before spawning. A crash in that window can strand an unsubmitted intent, which
is an intentional safety outcome: no fence reset or automatic retry is provided.
Receipts and scheduler observations retain separate evidence hashes. Acknowledged
acceptance establishes identity, not VASP execution or scientific success.

Reconciliation does not implement continuous monitoring. An explicit call can
record terminal scheduler evidence to release a reservation; no disappearance,
grace expiry or qacct exit status is scientific validation. The worker prioritizes
uncertain/pending recovery and handles at most one new request per invocation.

Cloud evidence contains public synthetic fixtures only. No scheduler/VASP/MPI
command, HPC pilot, Cron installation, actual Input/POTCAR read, scientific
parameter adjustment or research-file write was performed. Main and the base
branch are not modified by the handoff push.
