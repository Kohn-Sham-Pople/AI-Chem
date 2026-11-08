# AC13: typed-renderer registration (optional follow-up)

**For initial Golden Review use [preserve_source](ac13-preserve-source.md).**
This page describes the optional typed_renderer workflow only. Its node127-to-all.q,
new thread/library policies and machinefile rendering are not applied to preserved
scripts. Select a reviewed typed profile explicitly; the Golden tool then needs
--script-mode typed_renderer. No original script is automatically migrated.


This supplements the full [runbook](runbook.md). All recipes in this document
that read actual input are for **authorized HPC local execution only**. They were
not executed on research files by cloud Codex. Keep actual JSON, inventories,
source hashes/diffs and golden outputs private. Never commit them to this repo.
The paths supplied by the operator below identify runtime binaries; they do not
supply scientific parameters or permission to run the binaries.

## Status and unchanged boundaries

The operator reports AC12 **164/164 tests PASS on CentOS 6.9**, plus actual f/d
INCAR/POSCAR/KPOINTS/POTCAR parsing PASS. Historical cloud reports remain historical.
Run the newly expanded suite on HPC after installing this revision. AC13 still
needs human approval of actual JSON and independently reviewed golden results.
Scientific protocols, INCAR/POTCAR parsing, byte-copy/source guards, dry-run,
atomic preparation and restart trust rules are unchanged by this profile update.

No qsub, mpirun, VASP, initialization fragment, remote API or scheduler query is
executed by static validation or preparation. bash -n may parse rendered text;
it is not proof of MPI ABI, node placement, runtime libraries or convergence.

## 1. Explicit library policy and runtime tokens

`environment.ld_library_path_policy` is mandatory for new registration and
preparation. It has no default:

| Policy | library_dirs | Generated batch behavior after approved fragments |
|---|---|---|
| replace | Nonempty approved ordered absolute dirs | Set LD_LIBRARY_PATH to exactly these dirs; discard previous value |
| prepend | Nonempty approved ordered absolute dirs | Add these dirs ahead of the eventual batch value |
| preserve | Empty list | Leave the eventual batch variable unchanged (including leaving it unset) |
| unset | Empty list | Explicitly unset the eventual batch variable |

An empty list does **not** mean a missing library was discovered or is unnecessary
physically. It means no extra directory was approved for insertion. For the d
source script, lack of an explicit library assignment is insufficient to choose
between preserve and unset: the operator must review the actual batch environment
and approve one. f compiler/MKL paths and their load order must be inventoried
locally. Do not copy paths from examples or guess system library locations.

The generator never captures its own/Cron LD_LIBRARY_PATH. preserve/prepend refer
to the future **SGE batch environment after registered fragments**, not the
submission shell. The renderer does not add `#$ -V`. At batch time it refuses
set-empty values and empty/current/relative inherited directory entries (exit 94).
Unset inheritance is allowed. Even with lexical guards, inherited libraries and
compute-node availability/ABI need local review; static validation cannot attest
an unknown future environment. replace/unset are environment changes requiring
approval too, even if they make an eventual job fail early instead of running.

Safe launcher args for the operator-reported command are exactly:

```json
{
  "path": "/opt/mpi/intel-14.0.3/openmpi-1.10.7/bin/mpirun",
  "args": [
    "-np", {"token": "NSLOTS"},
    "-machinefile", {"token": "SGE_MACHINEFILE"},
    {"token": "EXECUTABLE"}
  ]
}
```

The VASP object is:

```json
{
  "version": "5.4.4",
  "path": "/opt/vasp/vasp.5.4.4/bin/vasp_ncl",
  "binary_name": "vasp_ncl"
}
```

SGE_MACHINEFILE is a dedicated token, not a string interpolation facility. It
renders **only** `"${TMPDIR}/machines"`, paired once with `-machinefile`.
The generated script checks JOB_ID, NSLOTS=32, nonempty absolute TMPDIR (exit 92),
and a readable regular machines file (exit 93) before the launcher. The generator
need not have TMPDIR/machines: these are future batch checks. Unknown token names,
extra token fields, raw `$TMPDIR/machines`, `$()`, backticks or newlines are rejected.
The command and runtime guards are text, never run during registration/preparation.

## 2. Source-bound execution approval, including node127 removal

Each new active profile needs `execution_review` with these exact fields:

```json
{
  "source_run_sha256": null,
  "source_node_selection": null,
  "target_node_selection": "all_q",
  "approved_changes": [],
  "approval": {"reviewer": null, "approved_at": null, "note": null}
}
```

Nulls/empty approvals are draft-only and must be completed by a reviewer. The
profile's top-level approval is also required. Both records use UTC timestamps
`YYYY-MM-DDTHH:MM:SSZ`; do not fill them automatically as a substitute for review.

- source_run_sha256: exact original run.sh hash from read-only inventory. It must
  match the selected template's run.sh hash at registration and request resolution.
- source_node_selection: `node127` for the operator-reported pinned f script;
  `all_q` only if local review confirms the source has no node127 restriction.
  The renderer does not infer this claim by trying to interpret arbitrary shell.
- target_node_selection: `all_q`, corresponding to queue `all.q` without a host pin.
- approved_changes: **exactly** one `ld_library_path_POLICY` entry, plus
  `sge_machinefile` when that token is used, plus `node127_to_all_q` when the source
  selection is node127. Duplicates, missing or contradictory entries block.

For example, if a reviewer chooses f replace, the required list is
`["ld_library_path_replace","sge_machinefile","node127_to_all_q"]`.
If a reviewer chooses d preserve after reviewing the original unpinned script,
it is `["ld_library_path_preserve","sge_machinefile"]`.
These examples explain the contract; **they do not approve either policy**.
Record the specific reason and comparison of original/generated execution behavior
in approval.note. In particular node127 removal is an execution-environment change,
not a whitespace-only run.sh rewrite. It is blocked without that explicit approval.

Queue/PE/slots/quota remain all.q/mpi_32/32/320. No host placement or live quota
claim is made. Source scripts and library files are never edited, chmodded or run.

## 3. Choose private paths and create incomplete local drafts

Use the code checkout under approved code storage. Configure an existing private
configuration directory outside every protected research root and outside Git.
The variables below must be set by the operator to actual approved absolute paths;
no directory defaults are supplied or created by this recipe.

```sh
: "${AI_CHEM_PY:?set approved Python 3.9.19 absolute executable}"
: "${AI_CHEM_CONFIG:?set existing private configuration directory}"
: "${AI_CHEM_REGISTRY:?set approved private registry absolute root}"
export AI_CHEM_CONFIG AI_CHEM_REGISTRY
umask 077
test -d "$AI_CHEM_CONFIG"
```

From the code root, write schema-shaped drafts exclusively (never overwrite):

```sh
PYTHONPATH=src "$AI_CHEM_PY" -B - <<'PY'
import json, os
from pathlib import Path
from ai_chem_input.config import schema_for

def draft(s):
    if 'const' in s: return s['const']
    if s.get('type') == 'object':
        return {k: draft(v) for k, v in s.get('properties', {}).items()}
    if s.get('type') == 'array': return []
    return None

root = Path(os.environ['AI_CHEM_CONFIG'])
for shell in ('f', 'd'):
    for kind in ('profile', 'material', 'protocol', 'template'):
        path = root / (kind + '_' + shell + '.json')
        with path.open('x') as f:
            value = draft(schema_for(kind))
            if kind == 'profile':
                value.pop('source_script_approval')
                value['run_script_mode'] = 'typed_renderer'
            json.dump(value, f, indent=2)
            f.write('\n')
PY
```

This deliberately writes no science defaults and no approval. Complete files
locally using an editor. Fresh registries can use revision 1; existing entities
need a new explicitly chosen positive revision. Never overwrite/edit a registered
revision, select `latest`, or silently patch old saved configs.

Recommended **distinct identifiers**, not a change to Registry layout:

| Entity | f | d |
|---|---|---|
| profile | cluster_f | cluster_d |
| material | eu2bacuo5 | cacu_seo3_2 |
| protocol | open_f_v1 | open_d_v1 |
| template | eu_f_template | cu_d_template |

A template has its own exact `profile:{id,revision}`; a request must select the
same exact ref. The existing Registry already isolates ID+revision. One f profile
revision does not change d or auto-update a template. Both profiles can use the
same protected/source/writable roots and the same global master-local lock/state,
provided the original root separation/ownership rules are satisfied.

Fill both profile roots and the reported queue/launcher/VASP values above. Enter
actual Python/bash paths, fragments, ordered libraries, thread settings, walltime
(or null), copy/space/budget policy and bounded discovery settings. Thread settings
are not inferred from pure-MPI conventions. d library_dirs may be `[]` only with
an explicitly approved preserve/unset policy. f paths remain unresolved until
local compiler/MKL inventory and review are complete. Paths must be canonical,
non-symlink paths under the existing safety contract (fixed /bin/bash alias excepted).
If a supplied /opt path traverses a symlink, do not silently rewrite it: obtain
read-only canonical-path/identity confirmation and approve the exact profile path.

## 4. Read-only actual inventory on HPC, never cloud

Set AI_CHEM_F_SOURCE and AI_CHEM_D_SOURCE to the explicitly chosen f/d directories.
Do not scan a research tree looking for a first/newest match. Keep the outputs in
AI_CHEM_CONFIG. This recipe reads the five approved files and emits metadata only;
it does not source run.sh, print POTCAR bodies or create anything in the sources.

```sh
: "${AI_CHEM_F_SOURCE:?set explicit approved f source}"
: "${AI_CHEM_D_SOURCE:?set explicit approved d source}"
export AI_CHEM_F_SOURCE AI_CHEM_D_SOURCE
PYTHONPATH=src "$AI_CHEM_PY" -B - <<'PY'
import json, os
from dataclasses import asdict
from pathlib import Path
from ai_chem_input.discovery import inventory
from ai_chem_input.paths import open_read, read_small
from ai_chem_input.potcar import inspect_potcar
from ai_chem_input.poscar import parse_poscar
from ai_chem_input.incar import parse_incar
from ai_chem_input.protocols import CONTROLLED, MATERIAL_TAGS

out = Path(os.environ['AI_CHEM_CONFIG'])
for shell in ('f', 'd'):
    source = Path(os.environ['AI_CHEM_' + shell.upper() + '_SOURCE'])
    info = inventory(source)
    with open_read(source / 'POTCAR') as f:
        potentials = inspect_potcar(f)
    structure = parse_poscar(read_small(source / 'POSCAR'), [p.element for p in potentials])
    tags = parse_incar(read_small(source / 'INCAR')).tags
    report = dict(source_dir=str(source), **info,
                  species=list(structure.species), counts=list(structure.counts),
                  nions=structure.nions, potentials=[asdict(p) for p in potentials],
                  preserved_incar_tags={k:v for k,v in tags.items() if k not in CONTROLLED | MATERIAL_TAGS})
    with (out / ('inventory_' + shell + '.json')).open('x') as f:
        json.dump(report, f, indent=2)
        f.write('\n')
PY
```

This data is **not scientific approval**. VASP4 hints from dataset metadata in
this report still need the material registry/POTCAR/source three-way review.
Never use the formula as the cell count/order, and never upload this private output.

## 5. Complete material/protocol/template JSON without guessing

Fill material's common id/revision/approval and the following exact catalog fields
using inventory plus independently approved local science:

- formula: f `Eu2BaCuO5`, d `CaCu(SeO3)2` (informational, not a cell template).
- species_blocks: ordered entries `{block_id,element,count,potential_variant,dataset_sha256}`.
  Use actual counts/order/variant/hash. Repeat elements only with distinct block_id.
- structures: entries `{structure_id,sha256}` using exact POSCAR bytes.
- configurations: entries `{configuration_id,structure_id,structure_sha256,spin_mode,soc,saxis,magmom_by_atom}`.
  spin_mode is collinear/noncollinear. saxis is null only when approved unspecified;
  otherwise a complete registered three-vector. Atom entries are exactly
  `{atom_index,moment}` or `{atom_index,vector}`. Cover every 1..N atom once; no
  sparse defaults. Moments/vectors come from the reviewed configuration, not a
  formula or this document. Quantities are canonical decimal strings.
- u_sets: `{u_set_id,ldau,ldautype,by_block}` with each block_id mapped to
  `{l,u_eV,j_eV}`. Record raw J and approved LDAUTYPE explicitly; no Ueff expansion.
- method: `{incar_tags,kpoints_sha256,potcar_sha256,approved_u_set_ids}`. The complete
  preserved_incar_tags in the inventory must be reviewed and bound to the method;
  unknown tags are preserved, not new editable overrides. Register approved U-set
  IDs, actual whole-file hashes and actual static-method/spin/parallel settings.

Profiles contain no material U/J/MAGMOM. Requests contain only selected IDs.
For protocols, complete common metadata plus shell_class f/d and recipe
open_f_v1/open_d_v1 respectively. No extra stage dictionaries or arbitrary INCAR
fields are supported. Built-in protocol constants remain unchanged.

For template JSON use common id/revision/approval and exactly:
`material_id`, `shell_class`, `source_dir`, `files`, `profile`, `protocol`.
Copy source_dir and the entire five-key files object from that shell's **reviewed**
inventory (each entry size_bytes, sha256, source_relative_name). Set material_id to
that shell's material ID. Set profile/protocol to exact `{id,revision}` selections.
Copy the run.sh file hash to the associated profile.execution_review.source_run_sha256.
Do not edit original files to make hashes match. Any drift needs renewed inventory
and a new explicitly approved revision. No material/profile link is inferred from
file timestamps, directory discovery order or a shared ID.

## 6. No-execution validation and exact registration commands

Before registration, validate each candidate profile using read-only metadata
checks. These inspect paths/readability, resources, approved fragment hashes,
policy and token structure. They do not invoke the launcher or VASP, qsub, ldd,
`--version`, a fragment or a network client:

```sh
for shell in f d; do
  PYTHONPATH=src "$AI_CHEM_PY" -B - "$AI_CHEM_CONFIG/profile_$shell.json" <<'PY'
import sys
from ai_chem_input.config import checked, load
from ai_chem_input.script import validate_profile
validate_profile(checked(load(sys.argv[1]), 'profile'))
print('PROFILE_STATIC_VALIDATED')
PY
done
```

Missing paths, empty replace/prepend dirs, unapproved policies/transitions or
mismatched script hashes must be resolved locally and reviewed, not waived.
The validator cannot verify the truth of a human claim about arbitrary source
shell semantics, a future LD_LIBRARY_PATH, actual PE allocation or runtime ABI.

After all local reviews are complete, register explicit files with independently
reviewed contents. The digest below binds reviewed contents; computing a digest
is not approval in itself. Stop on any error; never force or overwrite:

```sh
set -e
register_entity() {
  kind="$1"
  entity_path="$2"
  reviewed_digest=$(PYTHONPATH=src "$AI_CHEM_PY" -B - "$entity_path" <<'PY'
import sys
from ai_chem_input.config import load
from ai_chem_input.provenance import canonical, sha256
print(sha256(canonical(load(sys.argv[1]))))
PY
)
  PYTHONPATH=src "$AI_CHEM_PY" -B -m ai_chem_input registry register \
    --registry "$AI_CHEM_REGISTRY" --kind "$kind" --entity "$entity_path" \
    --approved-sha256 "$reviewed_digest"
}
for shell in f d; do
  register_entity profile "$AI_CHEM_CONFIG/profile_$shell.json"
  register_entity material "$AI_CHEM_CONFIG/material_$shell.json"
  register_entity protocol "$AI_CHEM_CONFIG/protocol_$shell.json"
  register_entity template "$AI_CHEM_CONFIG/template_$shell.json"
done
PYTHONPATH=src "$AI_CHEM_PY" -B -m ai_chem_input registry check --registry "$AI_CHEM_REGISTRY"
```

Profile registration performs the same static checks. Template registration and
request resolution check that the profile review is bound to the exact source
run.sh hash. Register neither the f template with the d profile nor vice versa.
`registry check` is a schema/catalog integrity check; it does not execute files or
grants approval. Historical profile snapshots without the added fields can still
be decoded/verified, but new registration/preparation rejects them with
PROFILE_APPROVAL_REQUIRED. Migrate through a newly reviewed profile revision and
matching new template revision; never rewrite old JSON or existing bundles.

## 7. Separate operator config and requests, then golden review

Create **operator_f.json and operator_d.json** outside Git with exactly:

```json
{"schema_version":1,"registry":"/actual/private/registry","profile":{"id":"cluster_f","revision":1}}
```

For d, select cluster_d and its exact actual revision. The example revision 1
only applies to a fresh registry; replace it with the registered value. Both
operator registry and profile.roots.registry must identify the same root.
Each JobRequest's cluster_profile must equal both the operator-selected profile
and its template's pinned profile, otherwise it is rejected.

A request contains exactly: schema_version=1, operator-assigned request_id and
calculation_id, exact template/material/cluster_profile/protocol `{id,revision}`,
structure_id/configuration_id/u_set_id from that material's approved entries,
stage_id (`s01_e4` f, `s01_e6` d initially), restart_evidence_id=null. Do not guess
configuration names or magnetic parameters. For explicit shape see request.json
schema; do not copy synthetic IDs/scientific values into the actual request.

Run each exact pair, keeping stdout private:

```sh
for shell in f d; do
  PYTHONPATH=src "$AI_CHEM_PY" -B -m ai_chem_input plan \
    --config "$AI_CHEM_CONFIG/operator_$shell.json" --request "$AI_CHEM_CONFIG/request_$shell.json"
  PYTHONPATH=src "$AI_CHEM_PY" -B -m ai_chem_input prepare --dry-run \
    --config "$AI_CHEM_CONFIG/operator_$shell.json" --request "$AI_CHEM_CONFIG/request_$shell.json"
done
```

Compare source/config/output/state/lock/inbox tree snapshots before/after dry-run.
Review the **full local run.sh text diff** along with scientific diffs: machinefile
command, quote/guards, queue and removal of node127, exact fragment order,
LD_LIBRARY_PATH policy, thread vars and walltime. Do not approve unexpected changes.
Source snapshots, full resolved profile.execution_review and input.diff remain
inside the private bundle through the existing provenance implementation.

Author the independent expected hash/diff JSON as described in the main runbook,
then run tools/local_golden.py --script-mode typed_renderer separately for f/d
with those exact operator/request files. Reviewers must independently compare expected script bytes and hashes;
tests do not authorize a change to the actual source environment. No batch job is
submitted or run at this step. B/C still require a trusted restart issuer.

## AC13 approvals still required locally

1. Exact source f/d scripts and all five original file hashes; source block/count,
   potential/U/J/configuration and full method mapping approval.
2. Independent exact f and d profile ID/revision bindings, runtime paths and
   read/execute metadata; approved canonical-path confirmation if applicable.
3. f Intel/compiler/MKL paths, fragment hashes and load order, thread settings,
   walltime, and explicit replacement/preservation decision.
4. d empty-extra-library policy and actual future batch inheritance assessment;
   no invented directories or implicit clearing/prepending.
5. Explicit f node127-to-all.q removal and SGE_MACHINEFILE launcher change,
   including reviewer/time/reason bound to original run.sh bytes.
6. Local storage/lock/fsync semantics, private roots and disk/time policies,
   new expanded target test run and independently signed actual golden evidence.

Compute-node ABI, SGE allocation/placement and actual VASP execution are future
pilot gates. Passing static checks or AC13 Input preparation does not approve
those operations or establish convergence.
