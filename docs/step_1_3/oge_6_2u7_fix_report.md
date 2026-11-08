# OGE 6.2u7 parser repair evidence

Baseline: `782e17921fc198e0ca9d50a62a9146324e526ff7`.
Branch: `codex/step1-3-submission`.

## Changes

- sge.py: Accounting's whitespace delimiter no longer swallows the date's colon.
  Valid compound qstat keys remain supported. Duplicate/invalid keys, required
  fields and bounded input checks remain strict. C/English dates use an explicit
  UTC/Asia/Seoul profile timezone and stdlib ZoneInfo; malformed dates, missing
  zone data, unknown zones and DST gaps/folds fail closed. Unix epoch and aware
  ISO timestamps remain supported. OGE's absent pe_taskid master rule is retained.
- admission.py and reconcile.py: pass the pinned profile timezone into detail and
  Accounting parsers. No implicit host timezone or nine-hour guess is used.
- Submission conftest fixtures: remove and restore inherited SGE_ROOT/SGE_CELL only
  for synthetic tests. Production mismatch checks are unchanged. make_case accepts
  an explicit test profile timezone; old calls retain UTC.
- Two hand-authored synthetic OGE fixture files; three new regression test files;
  read-only local runbook, limits, acceptance traceability and full test evidence.
  No schema, profile registry, scientific code or Input payload is changed.

## Executed verification

**490 PASS, 0 FAIL, 0 skipped**: all original 402 test IDs are present and PASS,
plus **88 new regression cases**. The new cases comprise 73 parser/date/record
cases, 12 service/admission/identity/environment cases and 3 executions of the
documented read-only command (approved evidence, missing evidence, bad date).

The final run deliberately inherited conflicting synthetic HPC variables:

```sh
SGE_ROOT=/SYNTHETIC/inherited_hpc_root SGE_CELL=synthetic_inherited_cell \
  PYTHONPATH=src:tests "$AI_CHEM_PY" -B tools/run_submission_acceptance.py
```

Cloud runtime: Python 3.9.19 / linked SQLite 3.46.0. Target CentOS 6.9 / Python
3.9.19 / linked SQLite 3.46.1 revalidation of this patch remains **NOT_RUN** here.
The user's earlier successful target run and two scheduler pilots are recorded
as user-reported history, not newly executed evidence for this repair.

[Full per-test results](evidence/cloud_synthetic.json),
[test log](evidence/cloud_synthetic.log) and
[acceptance matrix](acceptance_matrix.md) include exact test IDs and source digest.
S13-01 through S13-14 and S13-18 remain automated PASS; S13-15/16/17 actual local
gates remain NOT_RUN by cloud. Local evidence must not be replaced with mocks.

Exact baseline byte comparison confirmed store.py, service.py, runner.py,
receipts.py and preflight.py are unchanged. AST comparisons confirmed fixed qsub
argv/client environment, qsub acknowledgment parsing, XML/qstat parsing, strong
identity matching and slot-admission policy are unchanged. Scientific parsers,
preparation source and all schemas are untouched. Existing test functions were
not edited or removed; fixture isolation is the required test-only change.

Privacy inventory/credential-pattern scan found no real input/POTCAR/CHGCAR,
credential file, raw private scheduler dump or token/key credential addition.
Public OGE captures use job 1001 and explicitly synthetic owner/node/cwd/token.
No real qsub, MPI or VASP command was executed; only existing fake schedulers and
the original guarded harmless subprocess tests ran.

## Local revalidation and remaining blockers

Follow [the exact read-only local commands](oge_6_2u7_parser_acceptance.md) for
both already completed pilots. They read private captures/config/evidence only,
invoke no process, create no DB/lock/receipt and print no private raw values.
Verify local IANA Asia/Seoul data and the exact target runtime. If ended jobs no
longer have retained qstat detail, mark that portion NOT_RUN; do not submit again.

This compatible text-format fix stays inside sge_xml_v1 so registered/armed
intents keep their immutable profile and original run/token. Preserve approved
cluster/epoch/owner/client version/path/alias evidence and exact hashes locally.
No evidence, profile content, approval or fence is automatically rewritten.

Actual -V/node127/default/JSV/library equivalence, hard RQS/pending policy, verified
bundle pilot and Cron remain separate gates. The two reported scheduler pilots
alone do not authorize those operations. live_enabled defaults false, and an
armed/uncertain intent is never automatically resubmitted after timeout/crash.

## Changed paths

Production changes: src/ai_chem_input/submission/{sge,admission,reconcile}.py.

Test/support changes: tests/submission_support.py,
tests/unit/submission/conftest.py, tests/integration/submission/conftest.py;
new tests/unit/submission/test_oge62.py,
tests/unit/submission/test_oge62_runbook.py,
tests/integration/submission/test_oge62_service.py; new synthetic fixtures
tests/fixtures/sge_synthetic/oge_6_2u7_{qstat_detail,qacct_single}.txt.

Evidence/docs changes: tools/run_submission_acceptance.py;
docs/step_1_3/{runbook,known_limits,acceptance_matrix}.md,
docs/step_1_3/acceptance_matrix.json,
docs/step_1_3/evidence/cloud_synthetic.{json,log}; new
docs/step_1_3/oge_6_2u7_parser_acceptance.md and this report.
