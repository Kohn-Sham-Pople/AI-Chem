# Preservation, packaging and handoff audit

Base: b510177725075ce549ef5d5fca8bcf050ab8ed03. Only the new codex/step1-3-submission branch is the push target.

All 100 base-tracked paths were compared against exact Git object bytes. The 99 unchanged files include every original source/schema/fixture/test/document. pyproject.toml has one additive schema package-data entry; scientific/preparation code is untouched.

Full automated suite: **402 PASS = 267 unchanged Step 1-2 + 135 Step 1-3**, no failed/skipped tests. Python 3.9.19; linked SQLite 3.46.0. Actual CentOS 6.9/SQLite 3.46.1, scheduler precedence and pilots remain NOT_RUN. See acceptance_matrix.md/json and evidence/cloud_synthetic.json/log.

Isolated wheel smoke: PASS using Python 3.9.19/setuptools 70.3.0. Wheel integrity passed, all current submission source/schema bytes matched extracted installed files, all nine submission schemas were included, both old/new CLI --help commands passed, and the installed strict schema loader was exercised. Build/extraction was temporary outside the checkout; no distribution artifact is committed. No scheduler client was executed.

Privacy inventory: the only tracked POTCAR-named files are the two pre-existing tests/fixtures/synthetic f/d files, both containing SYNTHETIC markers. No new POTCAR/CHGCAR/INCAR/POSCAR/run.sh payload, private profile, raw private scheduler output, DB, credential file, archive, wheel or bytecode is included. New response fixtures are hand-authored synthetic data. Credential-pattern scan found no private-key, GitHub-token or AWS-access-key match in source/tests/schemas/docs/tools. Real research inputs were not accessed or transferred. This inventory and scan are bounded checks of this public checkout.

Runtime defaults remain live_enabled=false. Real environment equivalence, hard RQS/dialect/cluster/storage evidence, separate benign/actual single-job pilot approval and separate Cron approval remain operator gates. Public proof drafts are deliberately incomplete and do not approve anything.

## Changed paths

Modified existing path: pyproject.toml. Added public paths: 62.

```text
docs/step_1_3/acceptance_matrix.json
docs/step_1_3/acceptance_matrix.md
docs/step_1_3/compatibility_map.md
docs/step_1_3/evidence/cloud_synthetic.json
docs/step_1_3/evidence/cloud_synthetic.log
docs/step_1_3/handoff_audit.md
docs/step_1_3/implementation.md
docs/step_1_3/known_limits.md
docs/step_1_3/runbook.md
docs/step_1_3/synthetic_manifest_shape.json
schemas/submission_v1/config.json
schemas/submission_v1/dialect.json
schemas/submission_v1/dispatch_result.json
schemas/submission_v1/effective_execution.json
schemas/submission_v1/examples/config.draft.json
schemas/submission_v1/examples/dialect.draft.json
schemas/submission_v1/examples/effective_execution.draft.json
schemas/submission_v1/examples/live_authorization.draft.json
schemas/submission_v1/examples/request.draft.json
schemas/submission_v1/examples/rqs.draft.json
schemas/submission_v1/live_authorization.json
schemas/submission_v1/profile.json
schemas/submission_v1/request.json
schemas/submission_v1/result.json
schemas/submission_v1/rqs.json
src/ai_chem_input/submission/__init__.py
src/ai_chem_input/submission/__main__.py
src/ai_chem_input/submission/admission.py
src/ai_chem_input/submission/cli.py
src/ai_chem_input/submission/identity.py
src/ai_chem_input/submission/models.py
src/ai_chem_input/submission/preflight.py
src/ai_chem_input/submission/receipts.py
src/ai_chem_input/submission/reconcile.py
src/ai_chem_input/submission/runner.py
src/ai_chem_input/submission/schemas/config.json
src/ai_chem_input/submission/schemas/dialect.json
src/ai_chem_input/submission/schemas/dispatch_result.json
src/ai_chem_input/submission/schemas/effective_execution.json
src/ai_chem_input/submission/schemas/live_authorization.json
src/ai_chem_input/submission/schemas/profile.json
src/ai_chem_input/submission/schemas/request.json
src/ai_chem_input/submission/schemas/result.json
src/ai_chem_input/submission/schemas/rqs.json
src/ai_chem_input/submission/service.py
src/ai_chem_input/submission/sge.py
src/ai_chem_input/submission/store.py
src/ai_chem_input/submission/worker.py
tests/fixtures/sge_synthetic/qacct_pe_rows.txt
tests/fixtures/sge_synthetic/qstat_detail.txt
tests/fixtures/sge_synthetic/qstat_states.xml
tests/fixtures/sge_synthetic/qsub_cases.json
tests/integration/submission/conftest.py
tests/integration/submission/test_runner.py
tests/integration/submission/test_safety.py
tests/integration/submission/test_service.py
tests/submission_support.py
tests/unit/submission/conftest.py
tests/unit/submission/test_contracts.py
tools/draft_submission_config.py
tools/generate_submission_schemas.py
tools/run_submission_acceptance.py
```
