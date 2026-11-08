# Outstanding external gates and supported boundaries

- S13-15 actual SGE option/default/-V/node equivalence, S13-16 exact target/local
  scheduler-only pilot/RQS and S13-17 actual verified d/f submission are NOT_RUN.
  No user authorization for any actual pilot or Cron activation was supplied.
- Only fixture dialect sge_xml_v1 is tested. Unknown local SGE versions, textual
  timestamps without timezone, namespaces/states, unconfirmed pending/held coverage,
  unhandled serial/PE details or arrays block before dispatch. Do not certify a
  local distribution from an internet manual or a passing mock. A reviewed adapter
  extension may be needed after private local capability inventory.
- Real f/d run.sh/Input/POTCAR, actual SGE paths/versions/SGE_ROOT/CELL/qmaster,
  owner, hard quota, defaults/JSV, local environment comparison and local storage
  were not accessed by cloud Codex. No real private profile/proof is embedded.
- The fixed -clear/-q all.q command may change preserve_source execution behavior.
  Missing source/script/command/env-bound proof or explicit change approval is a
  live blocker. Unknown site directives do not get silently overridden.
- Source/preparation files are unchanged. verify_bundle is reused and requires a
  supported Step1-2 schema. Extra runtime files block a *new* use; existing submitted
  identity lookup does not claim current runtime outputs are scientifically valid.
- State/receipt storage must be complete, durable, master-local and operated by
  cooperating single-lock writers. Same-account malicious edits, total loss of DB
  plus independent ledger/registration history, NFS and active-active are outside
  the correctness guarantee. Restore is an operational pause/review contract.
- Receipt/SGE identity evidence is not a scientific validator. qacct exit status,
  a disappeared job or elapsed grace never produces scientific success or retry.
- Admission checks all known user-wide reservations/queues and requires hard RQS
  evidence, but cannot atomically coordinate unrelated manual submitters; the
  scheduler's native hard cap remains essential. Pilot outstanding cap stays one.
- This Step adds no scheduling/backfill, monitoring loop, stage generation/advance,
  retry recipe, cancellation, VASP/MPI execution, SSH/HTTP client or notifications.
- RQS/defaults/precedence evidence is trusted local operator attestation, not a
  cryptographic defense against its editor. Site changes require revocation/new
  reviewed profiles. Hashes are integrity links and do not supply missing approval.

- Invoke strict dry-run with Python -B or PYTHONDONTWRITEBYTECODE=1 as documented.
  Interpreter startup/import cache writes before application code are outside the
  planner's control; the verified invocation suppresses bytecode caches too.
