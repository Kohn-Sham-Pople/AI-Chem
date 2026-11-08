# Step 1-3 local registration, effective execution and single-job pilot

No command in this document was executed on an actual scheduler by cloud Codex.
Real HPC pilot and Cron activation require **separate user authorization**. Cloud
and default suites use synthetic data/fake scheduler only. Do not upload actual
Input/POTCAR/config/DB/receipts, private scheduler dumps or environment values.

## Existing Step 1-2 compatibility

Read compatibility_map.md and synthetic_manifest_shape.json first. The base is
b510177725075ce549ef5d5fca8bcf050ab8ed03. All original source/schema/CLI/tests remain
byte-identical. The package-data extension installs the additive submission
subpackage schemas. Commands use **python -m ai_chem_input.submission**, sharing
state/preparations.sqlite3 and lock/controller.lock with preparation. This avoids
changing the preparation worker's no-qsub contract or creating competing writers.
No preparation row/status/schema_meta version or prepared payload is rewritten.

The adapter calls the existing verify_bundle and rechecks exact READY/manifest,
source snapshots, input-only validation, generated hashes and science identity.
The physical final directory must be under the registered output root and away
from protected/source roots. Original source drift does not trigger repairs or
invalidate a sealed bundle on its own. Extra runtime files, unmanifested CHGCAR,
additional scripts, symlinks or unknown payloads block a first submission.
A bundle is never reused, repaired or overwritten to force submission.

## 1. Preserve the code and provision only approved local tools

Use the existing isolated checkout; no worktree is needed. Transfer code and
synthetic fixtures only, then use the already provisioned Python 3.9.19 linked to
SQLite 3.46.1 on CentOS 6.9. Runtime has stdlib dependencies only. With approved
offline dev wheels, install requirements-dev.txt in a separate approved dev env.
Run the complete tests with -B. No OS or system library upgrade is part of this task.

```sh
PYTHONPATH=src:tests "$AI_CHEM_PY" -B -m pytest -q
PYTHONPATH=src "$AI_CHEM_PY" -B -m ai_chem_input.submission --help
```

Live real clients are independently gated on exact Python/linked SQLite/CentOS
runtime. The bounded runner cannot execute real SGE on the cloud's unmatched
runtime. Synthetic subprocess tests replace that check only for hand-authored
harmless clients under temporary runner directories, protected by execution spies.
This does not mark S13-16 target/cluster acceptance as run.

## 2. Private submission config and bundle reference registration

Use schemas/submission_v1/examples/config.draft.json as an incomplete shape.
Keep the completed config outside Git, sources, protected roots and prepared
bundles, in approved 0700 private configuration storage. Drafts deliberately
contain nulls and cannot validate. live_enabled starts **false**, with pause and
restore pause true. Do not clear either pause until the relevant local review.

Config has exactly schema_version=1, profile (complete SubmissionProfile), and
bundle_refs (alias -> absolute final output directory). The SubmitRequest contains
only bundle_ref, expected_manifest_sha256, labels/stage and profile{id,revision}.
A bundle_ref is a trusted local mapping, not a request-supplied source path.
Request stage must equal the bundle stage. calculation_id is a transport/display
alias; scientific/bundle identities come from actual verified data. A changed
request_id or label cannot allocate a second run for the same intent.

Complete profile fields from actual local records, not examples:

- id/revision/approval: exact reviewed positive revision and UTC reviewer metadata.
  First use pins its full content in submission_profiles. Same ID/revision with
  changed content is a conflict. Record a new explicit revision for policy changes.
- cluster_id/cluster_epoch: scheduler instance and reset epoch, not a hostname
  guess. state_epoch is a reviewer-provisioned 64-hex controller-store epoch, not a
  credential. Never change it to evade an outstanding intent/fence.
- expected_owner.uid/name: actual effective account. HOME must be the actual HOME;
  no temporary HOME or shell startup sourcing. SGE_ROOT/CELL must identify the
  confirmed cluster. Check common/act_qmaster against the registered qmaster_aliases
  group (canonical names/FQDNs). Failover within an approved alias group is not a new
  cluster; scheduler resets need an explicitly reviewed cluster_epoch.
- qsub_path/qstat_path/qacct_path: absolute executable non-symlink paths with those
  exact client basenames, actual client version and supported output dialect.
  Inventory read-only local help/manual outside imports; never test by submitting
  VASP, executing MPI, or adding generic executable hooks.
- sge_client_env: only SGE_ROOT, SGE_CELL, PATH, actual HOME, optional numeric
  SGE_QMASTER_PORT/SGE_EXECD_PORT (1..65535). Client LANG/LC_ALL are fixed to C.
  No inherited shell/Cron environment, BASH_ENV, arbitrary env map or secret dump.
  Environment inheritance in the **job** is a different issue requiring section 3.
- roots: all Step 1-2 source/protected/output/registry/state/lock roots. Output/state/
  lock and protected list must agree with the bundle's pinned config. State/lock/
  receipts are master-local POSIX storage, not NFS or active-active/shared masters.
  No writable root overlaps a research root. Use account-owned 0700 roots.
- queue/pe/slots/user_quota_slots: all.q/mpi_32/32/320. single_job_pilot pending
  policy and max_outstanding_controller_runs=1; max_new_submissions=1. Never expand
  the pilot automatically to ten jobs/nodes. Set explicit bounded timeouts/budgets:
  snapshot<=5s, qsub<=15s, query<=5s, worker typically45s, grace300s/observations10.
  Blocking I/O cannot be interrupted at an exact budget boundary.
- site_options, when needed: typed project/account IDs and optional HH:MM:SS
  walltime only. The builder replays -P/-A/-l h_rt explicitly. Unknown resource/site
  options or a source directive mismatch block. No free extra_args, priority,
  array/hold/sync/now/-@ or arbitrary -l bypass exists. Mandatory JSV/RQS must remain.
- evidence pins: scheduler_rqs_evidence, dialect_evidence,
  effective_execution_evidence, live_authorization each null until approved, then
  {path:absolute_private_JSON,sha256:exact_bytes_hash}. All are strict typed JSON,
  bound to cluster/epoch/owner and explicit approval. Copy no secrets into them.

Evidence schemas and deliberately incomplete draft shapes are checked in. Boolean
confirmation fields in proof drafts are null, not automatically certified true.
The profile may plan with missing evidence, but cannot dispatch.

## 3. Critical preserve_source / -clear / -V / node selection gate

The original f script has all.q@node127; d has all.q. Both retain -V, existing
Intel/MKL statements and mpi_32 32/machinefile command. Step 1-2 preserve_source
approval proves their **bytes**, not equivalence to different qsub options.
This controller does not edit original/generated run.sh to make them match.

The fixed command policy is -clear -terse -b n -S /bin/bash -r n -cwd -hard
-q all.q -pe mpi_32 32 -N ac_FULLTOKEN -j y -o vasp.stdout -v the two identity
variables, reviewed site options, ./run.sh. No -V is added silently. In particular:

- -clear/default-request precedence can remove -V job environment inheritance.
- -q all.q can remove f's node127 host restriction.
- name, cwd, shell, rerun, stdout/join, site defaults may also be overridden.
- Script-body Intel/MKL assignments remain byte-identical, but the inherited value
  they extend or the libraries/hosts they reach may differ. Equal script bytes do
  not establish equal effective job environment or ABI.

Static parsing is intentionally narrow, not a shell evaluator. It reports potential
changed-environment codes. Unknown/duplicate directives, mismatched PE/resources or
unhandled site options block. Missing local equivalence evidence blocks with
EXECUTION_EQUIVALENCE_UNVERIFIED **before pending/fence/qsub**. Source -V and node
changes must be explicit entries (export_all_removed, node_selection_removed) in
approved_changes; unrelated/missing approval entries fail closed. No confirmation
is inferred from a Step 1-2 review, hashes alone or a timeout.

Inspect the policy read-only, with no scheduler calls or writes:

```sh
PYTHONPATH=src "$AI_CHEM_PY" -B - "$SUBMIT_CONFIG" "$SUBMIT_REQUEST" <<'PY'
import json, sys
from ai_chem_input.config import load, loads
from ai_chem_input.submission.preflight import build_submission_plan
plan = build_submission_plan(load(sys.argv[2]), sys.argv[1])
report = loads(plan.execution_json)
print(json.dumps({k:report[k] for k in ('script_sha256','command_policy_sha256','client_env_sha256','changes','blockers')}, indent=2))
PY
```

Store actual output only in HPC-private review records. command_policy_sha256 uses
the fixed 32-zero symbolic token, actual manifest and final cwd; it is not a run
instance. Actual dispatch replaces the token once after durable intent creation.
The policy hash is not a test that the site implements those flags.

## 4. Local evidence and separately authorized benign equivalence pilot

No pilot is authorized by this implementation. First collect actual local client
version, help/man behavior, current default request files (site/user/cwd), JSV/site
mandatory options, owner and qmaster alias, clock/timezone and storage properties.
Do not install/modify RQS, scheduler config or crontab. RQS evidence must establish
an actual hard user-wide 320-slot cap including pending jobs; qstat is not that cap.

The implemented sge_xml_v1 fixture dialect is a versioned tested contract, not a
claim that the unknown installed SGE matches it. It accepts known namespace-free
XML states, complete requested ranges, colon job detail fields and accounting with
UTC epoch or explicit-offset ISO time. Old textual timestamps, unknown namespaces/
versions, unrecognized states/arrays or incomplete serial/PE detail **block**; add
a separately reviewed dialect adapter using approved local fixtures if necessary.
Never loosen number parsing, drop -clear or guess missing resources to get a pass.

After a **separate user approval** for a scheduler-only single-job probe:

1. Create separate benign scripts in approved private probe storage. Never source
   the original run.sh, which would execute MPI/VASP. A reviewer may manually
   transcribe only necessary initialization statements into an init-only probe;
   it must contain no MPI/VASP, external API or research-file writes.
2. Compare baseline source-equivalent SGE directives and the candidate CLI policy
   using the same reviewed init-only probe, one job at a time under site quota.
   Record the intentional probe-script/cwd substitution; the production command
   still accepts only verified Step 1-2 bundles. No benign-script exception is
   added to the production submit API.
3. Query **effective** queue/host selection, PE/slots, full token/env/cwd, defaults,
   -V inheritance and rerun/stdout/walltime behavior from local scheduler detail.
   Confirm all active held/error/suspended/deleting states and upper requested
   slots are represented. Verify accounting preserves full name and groups PE
   tasks; actual qacct nonrecord/error distinctions must be confirmed locally.
4. Compare names/presence and approved per-variable hashes for relevant compiler,
   MKL, LD_LIBRARY_PATH, PATH, thread settings and machinefile metadata. Do not
   dump the entire environment or credentials. Keep the detailed comparison private;
   hashes alone do not prove library ABI, and variable differences require review.
5. If -V removal or host selection changes have not been shown equivalent and
   explicitly approved, leave runtime_environment_equivalent unset/false and
   live disabled. In particular do not automatically approve general all.q for f.
6. Record exact local findings in the strict effective_execution evidence, binding
   actual run.sh hash, production policy hash, client-env hash, actual changed
   fields, local precedence pilot confirmation and a digest of the private report.
   Include reviewer/time/reason. Reissue evidence if any pinned component changes.
7. dialect evidence binds actual client version, exact paths digest and approved
   qmaster aliases plus required capabilities and the confirmed full job-name limit
   (at least 35 characters; token truncation is never accepted). The implementation never manufactures
   a successful local dialect/pilot record. Sample proof data are synthetic only.

Only after those prerequisites and another explicit user authorization may a
live_authorization record permit the **single_job_pilot**. Its profile_sha256 is
computed over the complete normalized profile except live_authorization and
live_enabled (avoids a self-hash cycle); the profile remains immutable once used:

```sh
PYTHONPATH=src "$AI_CHEM_PY" -B - "$SUBMIT_CONFIG" <<'PY'
import sys
from ai_chem_input.submission.preflight import load_config, profile_authorization_hash
config, _ = load_config(sys.argv[1])
print(profile_authorization_hash(config['profile']))
PY
```

A hash does not grant approval; the actual authorization record requires the user's
instruction and operator reviewer metadata. Default live_enabled=false is retained
until then. No proof files are supplied for the real cluster by cloud Codex.

## 5. Dry-run then separately approved actual d-shell pilot

```sh
PYTHONPATH=src "$AI_CHEM_PY" -B -m ai_chem_input.submission submit \
  --config "$SUBMIT_CONFIG" --request "$SUBMIT_REQUEST" --dry-run
```

Dry-run has scheduler/process/write/lock/inbox allocation **zero**, no random token
or new DB. It may open an existing DB read-only. Missing DB is not created. Results
state live_admission=NOT_CHECKED, dispatch_allowed=false, committed=false. Planned
argv uses a symbolic token and executable alias; do not treat it as permission.
Keep local stdout private. A zero dry-run exit does not pass live gates.

After **separate actual-VASP pilot authorization**, registered proofs and exact
runtime checks, choose one approved initial d bundle and explicitly enable a new
reviewed live profile. Do not use a source directory as cwd. Submit once:

```sh
PYTHONPATH=src "$AI_CHEM_PY" -B -m ai_chem_input.submission submit \
  --config "$SUBMIT_CONFIG" --request "$SUBMIT_REQUEST"
PYTHONPATH=src "$AI_CHEM_PY" -B -m ai_chem_input.submission show \
  --config "$SUBMIT_CONFIG" --request-id "$SUBMIT_REQUEST_ID"
```

qsub accepted does not mean VASP started, converged or scientifically succeeded.
Verify token/name/env/cwd/PE/slots and exact job ID locally. Re-deliver the exact
request/alias and restart the controller: same intent/run/job, no additional qsub.
A later f first-stage pilot needs separate approval; no B/C auto-advance exists.
Register distinct f/d submission profile IDs/revisions and script/command-bound
effective-execution proofs. One script-bound proof cannot approve both scripts.
Keep the same actual cluster/epochs/owner and shared state/lock; never change epochs
to bypass the common outstanding-one pilot limit.

Unknown/timeout/spawned rc!=0/invalid stdout after fence is uncertain, never an
automatic retry. Use explicit reconciliation, without modifying Input or receipts:

```sh
PYTHONPATH=src "$AI_CHEM_PY" -B -m ai_chem_input.submission reconcile \
  --config "$SUBMIT_CONFIG" --intent-id "$SUBMIT_INTENT_ID"
```

Durable strict qsub receipt is checked first; otherwise bounded owner-wide list,
exact full-token/ID detail and accounting postfilters are used. Empty observations,
permission failures, delay, grace expiry and missing PID never reset a fence.
Weak evidence requires review; multiple identities conflict. No qdel/qalter/qrls,
assume-not-submitted, force or reset-fence command exists. Terminal scheduler evidence
only releases a reservation; it is never SCF/energy/magnetic success.

## 6. Durability, restore and one-shot Cron (not activated)

Additive tables are in the existing preparations.sqlite3 with foreign_keys=ON,
DELETE journal, synchronous=FULL and busy_timeout=5000. Existing preparation rows
and schema_meta=1 stay untouched. submission_schema_meta records version1,
implementation revision and applied time. The app is a single master-local writer;
NFS, multiple masters and active-active are unsupported. Every submitting and
preparing writer uses the same controller.lock. No DB transaction spans SGE I/O.

Intent, argv, raw bounded stdout/stderr, dispatch_result, admission snapshots and
scheduler observations live under state/submissions/INTENT, **outside the bundle**.
Files use 0600/dirs0700, exclusive immutable targets, temp+fsync+rename under the
common lock. Return status distinguishes DB writes from this call's dispatch
attempt; an uncertain post-fence attempt is conservatively marked attempted.
The DB plus scheduler is not atomic and this is not exactly-once VASP execution.

Only the process that committed a 0→1 CAS fence obtains a single-use, PID- and
command-digest-bound in-memory permit. It writes a durable separate fence record
before any qsub attempt. Readers cannot recreate a permit from an armed DB row.
Pre-fence pending resumes use the original token/run, reconcile intent/argv bytes
and fresh gates. Armed/uncertain paths never dispatch again, even after definite
spawn failure, missing receipt, timeout or grace expiry.

The independent lock-root submission_store.json anchor and dispatch_fences ledger
plus receipt inventory detect missing/restored DB, orphan receipts and fence
rollback. A restore requires paused_restore=true (or the paused_restore marker),
no new dispatch, authoritative inventory and operator review. Do not delete the
DB/state/receipts/lock ledger or change epochs to "fix" an uncertain identity.
If all independent storage and registration history are lost, the application
cannot prove a fresh store was never used; authoritative admin evidence and a
paused manual recovery are mandatory. No automatic reinitialization/reset is safe.

The worker recovers receipt/armed/uncertain or existing unarmed pending intents
before new requests, processes at most one new request and keeps malformed bytes
in private archives. Producers publish complete unique .json files atomically into
state/submission_inbox. No research directory is scanned for work. Pause via profile
or approved state/submission.pause marker. Pause/restore markers block the worker
and new submission. Explicit reconciliation may persist identity evidence/bindings
while paused; it never dispatches. It still refuses orphan/epoch/rollback conflicts.
With live_enabled=false, a valid durable receipt can recover a binding, but real
scheduler queries remain disabled. Do not edit pinned non-operational profile fields
to bypass a restore gate.
Only the operator may activate Cron after separate authorization. Example **draft**:

```text
* * * * * cd /APPROVED/CODE/AI-Chem && env -i PATH=/usr/bin:/bin HOME=/ACTUAL/ACCOUNT/HOME PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /APPROVED/PYTHON39 -B -m ai_chem_input.submission worker --once --max-new-submissions 1 --config /PRIVATE/submission.json
```

Replace examples only with approved actual paths and retain the account's real
HOME, not a temporary home. This is not an installed crontab. Do not replace the
existing preparation Cron or enable live mode as part of a code installation.
