# AI Chem Step 1–2: VASP Input Discovery & Preparation

Local-only Input factory targeting **Python 3.9.19 / linked SQLite 3.46.1 /
CentOS 6.9**. Runtime dependencies are standard-library only. It does not
submit, monitor, run VASP/MPI, call APIs, issue restart evidence or change
scientific parameters in response to calculation results.

`f/` is restricted to Eu2BaCuO5 and `open_f_v1`; `d/` to CaCu(SeO3)2 and
`open_d_v1`. Formula labels never determine cell contents, species order,
U/J, moments, potential variants or runtime paths. All such values must be
explicitly registered and approved. The tiny test cells are **synthetic
parser fixtures**, not structures or parameter recommendations for those materials.

## Synthetic development

Use the existing isolated checkout; no worktree is necessary. All default tests
use `tests/fixtures/synthetic` copied to temporary directories. No real research
file is needed or allowed in cloud tests, Git or CI artifacts.

With an approved Python 3.9.19 and offline dev wheels:

```sh
python3.9 -B -m venv /tmp/ai-chem-dev
/tmp/ai-chem-dev/bin/python -B -m pip install --no-index --find-links /approved/wheels -r requirements-dev.txt
PYTHONPATH=src:tests /tmp/ai-chem-dev/bin/python -B tools/synthetic_smoke.py
PYTHONPATH=src /tmp/ai-chem-dev/bin/python -B -m ai_chem_input --help
```

The wheel directory above is an operator-supplied example, not a live HPC path.
`tools/synthetic_smoke.py --require-target` rejects a version/OS mismatch.
Do not replace system libraries to make it pass. Package metadata deliberately
requires Python >=3.9,<3.10. `PYTHONPATH=src` also supports source-checkout use.
Always invoke with `-B` / `PYTHONDONTWRITEBYTECODE=1` for strict no-write runs.

## Workflow

1. In an **approved HPC local execution environment only**, inventory the five
   files and register reviewed exact JSON revisions. Drafts in
   `schemas/examples/` contain nulls/empty lists and are intentionally unusable.
2. A JobRequest selects exact registered IDs/revisions; it cannot contain paths,
   arbitrary INCAR patches, shell bodies or CHGCAR bytes.
3. `plan` or `prepare --dry-run` resolves, hashes, parses and validates, returning
   a bounded summary without creating DB, locks, inbox, output or logs.
4. `prepare` revalidates source/config pins, locks a master-local controller,
   writes an intent, copies to private staging, reparses and verifies, writes
   READY last, fsyncs and renames once. Existing final output is never overwritten.
5. `verify` checks READY→manifest→all payload hashes and scientific mappings.
   Extra future result files such as OUTCAR may exist but are never treated as Input.

```sh
PYTHONPATH=src python3.9 -B -m ai_chem_input discover --config /local/operator.json
PYTHONPATH=src python3.9 -B -m ai_chem_input registry check --registry /local/registry
PYTHONPATH=src python3.9 -B -m ai_chem_input plan --config /local/operator.json --request /local/request.json
PYTHONPATH=src python3.9 -B -m ai_chem_input prepare --config /local/operator.json --request /local/request.json --dry-run
PYTHONPATH=src python3.9 -B -m ai_chem_input prepare --config /local/operator.json --request /local/request.json
PYTHONPATH=src python3.9 -B -m ai_chem_input verify --bundle /local/output/calculation/stage
```

These `/local` paths are explanatory; operators supply their own approved roots.
Never put actual source/config/diff/output or licensed POTCAR in this repository.
Discovery stdout and locally generated provenance are private HPC artifacts.

See [operator runbook](docs/runbook.md), [blockers and limitations](docs/known-limitations.md),
[implementation/evidence](docs/implementation.md), and the v1 contracts in `schemas/`.


Execution profiles now require an explicit LD_LIBRARY_PATH policy and an
execution review pinned to the source run.sh hash. Empty library lists are valid
for approved preserve/unset policies. SGE_MACHINEFILE expands only to the quoted
runtime ${TMPDIR}/machines path, with guards. Use independent exact profile refs
for f/d. See [AC13 local registration](docs/ac13-registration.md) for migration,
node127-to-all.q approval and complete private JSON/registration instructions.
