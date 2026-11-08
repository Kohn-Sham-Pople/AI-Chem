# Initial AC13 Golden Review: preserve_source

Use this mode for both f/d **initial** Golden Template Registry registration.
It copies the existing locally approved run.sh bytes without interpreting or
regenerating the script. All recipes that read actual files below are for the
approved HPC local environment only. Cloud Codex did not read those files.
No actual script/Input/config/diff/output belongs in Git or an upload.

## Contract and trust boundary

- Preserve exactly the original `#$ -V`, Queue/PE/node directives, machinefile
  arguments, Intel/MKL/LD_LIBRARY_PATH assignments, commands, quotes, comments,
  line endings and final newline state. No cd, guard, resource directive, thread
  assignment, environment normalization or node127 removal is inserted.
- This mode has no launcher/environment/execution_review objects. Reject those
  fields instead of silently ignoring a supposedly applied renderer policy.
  No new library paths, OMP/MKL settings or target node selection are inferred.
- The script is opaque executable configuration, approved by exact SHA-256 and
  reviewer metadata. Copying does not source/execute it or prove arbitrary shell
  safe. JobRequest cannot inject a body/path or bypass the registered hash.
- Source/protected/output/registry/state/lock separation, descriptor read-only
  access, stat/hash pins, new revisions, no-overwrite and cooperative deadlines
  stay in effect. Source bytes/mode/mtime are not modified. Output uses the
  existing private independent-copy permissions (run.sh 0700); it is not a link.
- Profile queue/PE/slots/quota and VASP metadata remain declared information for
  the Input contract. This mode does not inspect/execute runtime binaries,
  compiler/MKL fragments or assert source directives match that declaration.
  The reviewer must check all actual source resources and working-directory
  behavior. Manifest explicitly uses resource_validation=profile_declared_only.
  INPUT_READY is not permission to submit or proof of cluster/runtime readiness.
- Typed renderer remains unchanged in behavior for existing profiles (an omitted
  mode still means typed_renderer). It remains available for a separately approved
  later transformation. There is no automatic mode switch for old revisions.

## 1. Inventory current local f/d sources and review the changed d script

Use the private-path/root rules in [the main runbook](runbook.md), and the
read-only inventory recipe in section 4 of the [registration supplement](ac13-registration.md).
Do not scan for first/newest templates or alter original files to match a registry.
Retain complete current hashes/sizes for INCAR, POSCAR, POTCAR, KPOINTS and run.sh.

The operator reports the **already locally modified d/run.sh** SHA-256:

```text
c9324f17ec9e1701a05722400812b741acc5f59e3139f807c75216b8b889aee0
```

This is user-supplied metadata, not a hash verified by cloud and not a code default,
fixture or automatic approval. Do not reconstruct bytes from it, reuse an old d
revision, or modify local bytes to satisfy it. On HPC, compare a fresh read-only
hash with this supplied value, review what changed locally, then approve a new
profile/template revision. If the actual hash differs, stop and reinventory/review.
The f hash must also be inventoried locally; none is assumed here.

One local-only check (set AI_CHEM_D_EXPECTED_SHA to the reviewed value above):

```sh
: "${AI_CHEM_PY:?set approved Python absolute path}"
: "${AI_CHEM_D_SOURCE:?set approved explicit d source}"
: "${AI_CHEM_D_EXPECTED_SHA:?set operator-reviewed expected hash}"
export AI_CHEM_D_SOURCE AI_CHEM_D_EXPECTED_SHA
PYTHONPATH=src "$AI_CHEM_PY" -B - <<'PY'
import os
from pathlib import Path
from ai_chem_input.paths import inspect
actual = inspect(Path(os.environ['AI_CHEM_D_SOURCE']) / 'run.sh')['sha256']
if actual != os.environ['AI_CHEM_D_EXPECTED_SHA']:
    raise SystemExit('SOURCE_CHANGED: reinventory and local review required')
print('D_RUN_HASH_MATCHED: approval still required')
PY
```

Do not upload its actual bytes or private inventory. The new hash is not embedded
in runtime code; the same general source checks apply to every template.

## 2. Build new incomplete preservation profiles privately

A minimal draft is in schemas/examples/profile-preserve-source.draft.json.
Complete common id/revision/approval, roots, declared queue/PE/slots/quota, VASP
metadata, controller runtime, preparation and discovery fields from approved local
configuration. Retain known values rather than inventing new runtime paths.
VASP.version still participates in scientific method identity; copying run.sh does
not relax material/method validation. Binary paths in this mode are metadata, not
claims that executables or their ABI were validated.

Select explicit positive **new** f/d profile revisions (e.g. separate cluster_f
and cluster_d IDs, each with the next reviewer-chosen revision), and set:

```json
{
  "run_script_mode": "preserve_source",
  "source_script_approval": {
    "source_run_sha256": null,
    "approval": {"reviewer": null, "approved_at": null, "note": null}
  }
}
```

These are fields to merge into a complete private profile, not a complete active
profile or approved data. Fill source_run_sha256 from the current inventory. Fill
reviewer/UTC approved_at/note only after actual human review. Top-level approval
must also be renewed for the new revision. Note must identify byte preservation,
actual -V/queue/node/MPI/library/working-directory behavior and the local d change.
Do not carry over an approval for a previous script/hash or renderer transformation.

Remove launcher, environment and execution_review entirely (not null, not empty
maps). Thus no thread variables or library/node policy are required. Node127, if
present in the original f script, is **preserved**, not automatically replaced.
The earlier node127_to_all_q approval requirement is for typed transformations
only; it does not apply when the bytes are unchanged.

If starting with a private editable copy of a previous profile, make those changes
in a new candidate file outside the immutable registry. Never edit registered JSON.
The schema intentionally still decodes historical typed snapshots; active profile
validation enforces the chosen mode's requirements and rejects mixed fields.

Validate each candidate without execution or writes:

```sh
for shell in f d; do
  PYTHONPATH=src "$AI_CHEM_PY" -B - "$AI_CHEM_CONFIG/profile_${shell}_preserve.json" <<'PY'
import sys
from ai_chem_input.config import checked, load
from ai_chem_input.script import validate_profile
validate_profile(checked(load(sys.argv[1]), 'profile'))
print('PRESERVATION_PROFILE_VALIDATED: declared resources and approval only')
PY
done
```

This checks schema, root safety and explicit approval metadata. It does not
implicitly verify script semantics or launch/read new compiler/MPI/VASP settings.

## 3. Register exact profile/material/protocol/template revisions

Use the reviewed-digest register_entity function and exact registration commands
in section 6 of [the registration supplement](ac13-registration.md). For initial
AC13, pass the preservation profile file rather than a typed candidate:

```sh
for shell in f d; do
  register_entity profile "$AI_CHEM_CONFIG/profile_${shell}_preserve.json"
  register_entity material "$AI_CHEM_CONFIG/material_${shell}.json"
  register_entity protocol "$AI_CHEM_CONFIG/protocol_${shell}.json"
  register_entity template "$AI_CHEM_CONFIG/template_${shell}_preserve.json"
done
```

For an existing registry, **do not re-register an existing material/protocol
revision**. Check/resolve the exact already approved immutable record and retain
its ref when science is unchanged. Only register material/protocol files above
when registering genuinely new approved revisions in a fresh or updated catalog.
No U/J/MAGMOM, species/count/order or scientific protocol is changed to accommodate
the script. Existing approved scientific refs remain exact, never `latest`.

Each new template must contain the full current five-file inventory, its actual
source_dir, the unchanged correct material/protocol refs and the new exact
preservation profile {id,revision}. Template.files['run.sh'].sha256 must equal
profile.source_script_approval.source_run_sha256. Registration and request
resolution enforce that binding; file drift remains blocked by actual byte hashes.
A new d script requires a new template/profile approval even when other four files
are unchanged. Any other file changes need their own review, not an assumption.

Create separate operator_f/operator_d configs selecting those exact profile refs.
Update each JobRequest's template and cluster_profile refs to match the newly
registered revisions. Retain the appropriate approved structure/configuration/U-set,
material/protocol and initial stage (f s01_e4, d s01_e6, restart_evidence_id=null).
Use new calculation IDs if an existing final identity refers to an older intent;
never overwrite an existing bundle or reuse a conflicting ID.

## 4. Dry-run, byte equality and initial Golden gate

Run plan and prepare --dry-run with each exact operator/request pair as in the
main runbook, with -B and private stdout handling. Compare complete before/after
source/config/output/state/lock/inbox trees: no output/SQLite/lock/inbox/log writes
are allowed during dry-run. An invalid hash/revision does not authorize repair.

Prepare independently reviewed expected source/generated hashes and INCAR
semantic changes as usual. For **run.sh**, expected generated SHA-256 must equal
the independently approved source SHA-256; do not accept a renderer-derived diff.
POSCAR/POTCAR/KPOINTS remain byte copies; existing scientific INCAR protocol patches
and approved material mappings are the only intended scientific changes.

```sh
for shell in f d; do
  PYTHONPATH=src "$AI_CHEM_PY" -B tools/local_golden.py \
    --config "$AI_CHEM_CONFIG/operator_$shell.json" \
    --request "$AI_CHEM_CONFIG/request_$shell.json" \
    --expected "$AI_CHEM_CONFIG/expected_$shell.json"
done
```

The tool **defaults to preserve_source** and rejects a typed profile with
GOLDEN_SCRIPT_MODE before preparation. The flag does not override a profile:
--script-mode typed_renderer is an explicit opt-in to a separate typed review,
which still requires the existing typed execution/environment approvals.

After preparation, verify the complete bundle with the existing verify command.
For preservation mode, manifest.run_script contains mode, source_sha256,
generated_sha256, byte_identical=true and resource_validation=profile_declared_only.
Source/generated file metadata and independent source snapshot must all match.
The run.sh diff summary is SAME=true with the hash; no text decoding/normalization
is applied, including to CRLF/non-UTF8 comments. Full source bytes remain only in
the private source snapshot and output. READY still hashes the complete manifest.
Verification rejects missing/mismatched mode metadata or a changed copied script,
even when payload checksums were recomputed. Local Golden evidence records the mode
and hashes alongside existing material/configuration and source immutability checks.

Copying keeps existing cd commands and SGE -cwd/-V semantics. Review any absolute
research-directory references before any future execution; this mode does not
silently rewrite them into the new output directory or authorize future source
writes. No qsub/VASP/monitor/API invocation or execution approval is part of AC13.

## Required remaining local approval

Review current f/d raw scripts (including locally modified d bytes), exact hashes,
retained environment inheritance/library/node/launcher/working-directory behavior,
new profile/template refs, all unchanged scientific mappings, and independently
expected actual Golden outputs. Run the expanded regression suite on the target
HPC runtime and retain actual private Golden evidence there. Cloud tests are
synthetic only and do not establish that the reported d hash matches local bytes.
