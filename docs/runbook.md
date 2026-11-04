# HPC local inventory, registration and acceptance

## Data and trust boundary

Transfer only this source code, schemas, docs and synthetic tests into approved
HPC code storage. Never upload research Input, POTCAR, CHGCAR, private configs,
absolute research paths, manifests or diffs to cloud/Git/API. `.gitignore` is
only a convenience; operator policy and storage separation are required.
The package contains no transport client. Run discovery and preparation only in
an environment already authorized to read and retain the actual local files.

Source directories are read-only by application API, not mounted read-only by
this package. Mount-level read-only controls can add protection. Reading may
change atime; bytes/hash/mode/mtime must remain unchanged. Source writers must
not race preparation; descriptor/hash checks do not provide a hostile filesystem
sandbox. Never chmod, repair, reorder or edit originals to satisfy a validator.

## 1. Verify the machine and storage

Run `python3.9 -B tools/synthetic_smoke.py --require-target` with
`PYTHONPATH=src:tests` and approved dev dependencies. It reports Python's linked
SQLite, not the sqlite3 CLI version. Required local target is Python 3.9.19,
SQLite 3.46.1, CentOS 6.9. Do not upgrade the OS/system libraries in this task.

Operator must establish source/protected absolute roots and four mutually
separate application roots: output, registry, state, lock. No writable root may
be ancestor or descendant of any protected root; source must be contained in
protected. Symlinks in research/config paths and special files are rejected.
The fixed `/bin/bash` system interpreter is the sole permitted platform alias.
Writable application roots must be account-owned and private (0700). State and
lock must be on a **master-local POSIX filesystem**, not NFS. Verify flock,
same-filesystem rename and fsync semantics locally; mount locality cannot be
proved portably by this code. No other writer may modify output directories.

## 2. Fill and approve the profile

Copy `schemas/examples/*.draft.json` outside the code checkout into private
configuration storage. Drafts are incomplete documents and are never prepare
inputs. Complete profile fields using the source run.sh and local inventory:
VASP 5.4.4 `vasp_ncl`, absolute approved MPI launcher, literal argument tokens
and the `NSLOTS`/`EXECUTABLE`/`SGE_MACHINEFILE` token objects; explicitly approved library policy and ordered directories;
hash-pinned approved initialization fragments; thread settings; Python and bash
paths; explicit walltime or null. There is no free-form environment map or
executable hook. Queue/PE/slots/quota are all.q/mpi_32/32/320; quota is static.

Do not guess compiler/MPI/MKL paths, launcher flags, library order or thread
counts. Fragment approval is approval of executable future compute-node config;
a hash is not proof that an unreviewed script is safe. The generator never
sources fragments or executes VASP/MPI. Manually review the source run.sh and
bind its exact five-file template hash to this profile revision; a malicious or
unreviewed script must not receive approval. Reviewers are the trust authority,
not an arbitrary-shell static scanner.

Set discovery recursive=false, max_depth=3, max_candidates=100 if those bounded
policies are desired; do not use roots beyond the approved research subtree.
Set preparation max_requests=1, budget_seconds=45 and explicit positive chunk,
size/free-space policy. The cooperative budget checks chunk loops; blocked I/O
cannot be forcibly interrupted. Approved large CHGCAR policy may need a longer
budget, without changing resources or science.

Each active entity has schema_version=1, id, revision>0 and
approval {reviewer, approved_at UTC `YYYY-MM-DDTHH:MM:SSZ`, note}. Calculate the
reviewed canonical entity digest locally:

```sh
PYTHONPATH=src python3.9 -B -c 'import sys; from ai_chem_input.config import load; from ai_chem_input.provenance import canonical,sha256; print(sha256(canonical(load(sys.argv[1]))))' /private/profile.json
PYTHONPATH=src python3.9 -B -m ai_chem_input registry register --registry /private/registry --kind profile --entity /private/profile.json --approved-sha256 REVIEWED_DIGEST
```

Use actual local arguments; REVIEWED_DIGEST is not accepted as an approval hash.
An existing revision cannot be replaced. Use separate exact f/d profile references and operator configs; see the
[AC13 registration supplement](ac13-registration.md). Operator config is strict JSON:
`{"schema_version":1,"registry":"/private/registry","profile":{"id":"cluster_local","revision":1}}`.
Keep this file and all active registry content private.

## 3. Inventory explicitly

Run `discover --config ABS_OPERATOR_JSON` locally. Default search is only direct
f/d children of allowed source roots. Recursive mode is opt-in and bounded;
limits fail rather than silently truncating. Inventory gives hashes/sizes,
parse status and extra filenames. It does not register or pick a first/newest
candidate. With multiple candidates, the reviewer explicitly chooses one
canonical `source_dir` in the template entity. Extra files (including source
CHGCAR/WAVECAR) are never implicitly copied.

Inventory must confirm exactly INCAR, POSCAR, POTCAR, KPOINTS and run.sh. Record
ordered POSCAR blocks/counts, full structure hash, each potential variant and
dataset hash. Repeated element blocks require distinct block_id values.
POTCAR is copied whole; no dataset download/assembly/reordering is provided.
Unsupported metadata/format is a blocker, not a reason to loosen checks.

## 4. Complete material, template and protocol revisions

Material species_blocks must come from reviewed actual files. Register structures
and complete atom-index mappings, including explicit zero moments; no formula
unit multiplication or sparse site defaults. Record approved spin mode/SOC/SAXIS.
Provide each U set's LDAU, LDAUTYPE and exact per-block l/u_eV/j_eV (including
explicit inactive-species values). Quantities use canonical decimal strings,
not floats, NaN, implicit J=0, or an automatically expanded Ueff.

`method.incar_tags` is the **complete** preserved tag map excluding controlled
protocol tags EDIFF/NELM/AMIX/AMIX_MAG/LMAXMIX/ICHARG/ISTART/LCHARG and material
tags LDAU/LDAUTYPE/LDAUL/LDAUU/LDAUJ/MAGMOM. Include unknown approved tags verbatim.
Include registered KPOINTS/POTCAR whole hashes and approved U-set IDs.
Static pilot only: NSW absent/0, IBRION absent/-1; unsupported advanced methods
block. There are no arbitrary request overrides.

The material IDs are operator-chosen; formulas must be exactly Eu2BaCuO5 for f,
CaCu(SeO3)2 for d. Protocol recipe is open_f_v1/open_d_v1 respectively. Template
binds exact material_id, shell class, source directory, five size/hash/name
entries, exact profile and protocol refs. Register material/protocol/template
with the same reviewed-digest procedure; check the full registry. Registering
is not scientific approval generated by a parser: reviewer metadata must reflect
an actual review. A source hash change always needs a new explicit revision.

## 5. Dry-run and independent local golden gate (AC13)

Build JobRequests from registered IDs only (request schema documents all fields).
Choose initial f s01_e4 or d s01_e6, restart_evidence_id=null. Run plan and
prepare --dry-run with `-B`. Snapshot source/config/output/state/lock/inbox trees
before and after to establish no writes; stdout redirection is the operator's
shell action, not the dry-run API. No database or lock is opened for writing.

Review the expected changes independently. f A sets EDIFF=1E-04, NELM=300,
AMIX/AMIX_MAG=0.1, LMAXMIX=6, ISTART=0, LCHARG=true, removes ICHARG. d D sets
EDIFF=1E-06, AMIX=0.2, AMIX_MAG=0.4, LMAXMIX=4, ISTART=0, removes NELM/ICHARG,
preserves approved LCHARG. Both serialize only the chosen approved U/moment
mapping. No initial CHGCAR/WAVECAR is included.

Author a private independent expected JSON with reviewer, approved_at,
source_sha256 (five names), generated_sha256 (five names), and exact
semantic_changes (tag/old/new/action/layer/reason). Do not derive the expectation
by blindly accepting generator output. run.sh hash must match the reviewed
profile and final working directory. Then run:

```sh
PYTHONPATH=src python3.9 -B tools/local_golden.py --config ABS_OPERATOR_JSON --request ABS_REQUEST_JSON --expected ABS_EXPECTATION_JSON
```

The gate compares exact hashes/diffs, materializes separately, verifies the
bundle, rechecks sources and exclusively saves local evidence under state/golden.
Evidence includes exact species/U/configuration mappings and manifest hash.
Repeat for f and d. Never commit local-golden-review, input.diff or source snapshots.

## 6. Restart boundary

The production CLI deliberately uses a fail-closed provider. B/C cannot be
materialized through this CLI until a separately reviewed local validator/store
integration exists. No command issues a record or accepts a `validated` switch.
The Python read-only provider interface permits later integration. Trusted store
reader requires an independently provisioned issuer and exact record-hash map;
JobRequest cannot populate that map. Same-user ownership is an operational trust
boundary, not cryptographic security against that user.

Evidence v1 includes issuer/version, status VALIDATED, producer manifest hash,
result evidence refs, exact prior-stage EDIFF and passed versioned lab rules,
method/configuration/structure/potential/U identity, LMAXMIX=6 and LCHARG=true,
and CHGCAR path/size/hash. Preparation checks header geometry (abs/rel 1e-10),
bytes and record pin repeatedly; it does not validate charge grids/convergence.
Actual OUTCAR/rms(c) interpretation and evidence issuance remain a later Step.

## 7. One-shot Cron draft, recovery and handoff

No crontab is installed automatically. Operator may adapt:

```text
* * * * * cd /approved/code/AI-Chem && env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /approved/python3.9 -B -m ai_chem_input worker --once --max-requests 1 --config /private/operator.json
```

Paths are examples. Do not replace HOME. Use private local log redirection only
if approved; reports contain IDs/codes, not potential bodies or raw Input.
Producer writes a temporary request then atomic-renames a unique `.json` into
state/inbox. Worker takes the global lock, claims atomically, handles at most one
request, and retains processed/rejected bytes plus exact transport digest/result.
Partially written/malformed input is rejected and retained, never silently deleted.
A previously claimed request is retried first; duplicates use the preparation
identity guard. Archive result is durable before moving the request into archive.

DB uses DELETE journal, foreign_keys=ON, synchronous=FULL, busy_timeout=5000ms.
Do not assume a DB/FS distributed transaction. A PREPARING intent plus valid final
is rehashed before ready recovery; abandoned staging is retained and a fresh
attempt may be created. Missing/corrupt final for a completed identity is quarantined,
not regenerated. A final without matching DB intent is blocked for operator review.
Do not delete completed outputs, reset state or force overwrite to resolve conflict.
Events are append-only through the application, not tamper-proof against a DB editor.

Handoff to a future submission adapter is bundle_path, manifest_sha256,
calculation_id/stage_id and static resource_request. That adapter must reverify
Input and submit from the **final stage directory**. This implementation never
performs the handoff action or claims scheduler/ABI/convergence validation.

The worker rejects an inbox/processing directory with over 100 directory entries
before selecting an item; the cap bounds scanning as well as max_requests=1.
Move archived records using a separate operator maintenance policy, never delete
pending requests to evade a limit. Discovery extras inventory is capped at 1000
names per candidate and fails explicitly rather than truncating.


## 8. AC13 execution-profile compatibility update

The operator reports AC12 **164/164 PASS on actual CentOS 6.9 HPC**, plus actual
f/d Input parsing PASS after the ZVAL correction. This is operator-reported local
evidence; the historical cloud evidence files are retained unchanged. Run the
expanded suite on HPC again after deploying this execution-profile update.

Follow [the exact AC13 registration supplement](ac13-registration.md) for the
new explicit library policy, source-script-bound execution review, independent
f/d profiles, machinefile token and registration commands. No active profile or
scientific values are generated or approved in cloud. Old revisions stay immutable;
historical profile snapshots remain schema-readable, but a new preparation must
use an explicitly reviewed profile and matching template revision. A missing
policy/review fails with PROFILE_APPROVAL_REQUIRED; there is no implicit default.
