# Local blockers and scope limits

No real template bytes, actual registry, research paths, source run.sh/library
recipe or HPC access were supplied or used. There are no inferred live values.
All checked-in POTCAR files are hand-authored `SYNTHETIC TEST ONLY` mocks; they
cannot run VASP. Synthetic pass is not actual-material/cluster acceptance.

Required unrun local gates:

- **AC12:** CentOS 6.9, Python 3.9.19, Python-linked SQLite **3.46.1**, approved
  offline dependencies, full synthetic suite/import/CLI/package installation.
  Cloud testing used Python 3.9.19 with SQLite 3.46.0 and separately host Python
  3.12.14 with SQLite 3.53.1. Neither is the exact target platform.
- **AC13:** private actual f/d inventory, reviewed exact original/generated five
  hashes, scientific parameter table, ordered species/U/J/MAGMOM mappings and
  independent INCAR/run.sh golden expectation. Run `tools/local_golden.py` twice
  on approved HPC storage and retain its evidence there only.
- Confirm master-local DB/lock filesystem, account-owned 0700 application roots,
  read access, disk policy, POSIX locks/rename/fsync and source sealing policy.
- Fill actual cell size/order, species block IDs, potential variants/dataset
  identities, raw U/J/LDAUTYPE, complete FM/AFM/site vector basis, preserved method,
  exact launcher/fragments/library paths/order, thread vars and walltime.

Runtime scope:

- Production CLI has no trusted restart issuer/store activation, so f B/C always
  fail closed. A read-only pinned local store adapter and provider interface are
  available for a future separately reviewed validator integration. Test-only
  providers are confined to tests. Hash/header checks do not validate a CHGCAR
  grid or scientific convergence.
- Supported flat VASP 5 INCAR only. Unsupported nested syntax blocks. Unknown
  approved flat tags are preserved, not writable through requests.
- POSCAR scalar scale/negative volume, VASP4 with approved hints and VASP5 are
  supported; three scales, velocities/predictor tails and advanced methods are
  blocked. KPOINTS mesh/explicit list only; no line-mode/tetrahedron/length mode.
- POTCAR parser requires unambiguous TITEL/VRHFIN/LEXCH/ZVAL and complete End of
  Dataset boundaries. Unknown legacy formats require a reviewed parser change;
  it never guesses or assembles datasets. Dataset hashes include exact bytes up
  to each End of Dataset line. Full-file hash is separately pinned.
- No qsub/qstat/qacct/mpirun/VASP invocation, HTTP/SSH/upload, automatic parameter
  tuning, stage advance, OUTCAR/rms(c) validation, live quota or compute-node
  ABI/PE placement checks. run.sh is rendered text for a later execution Step.
- Validation relies on independently approved registry contents and filesystem
  access policy. It is not cryptographic authentication against a malicious same
  Unix user who edits DB, configs and manifests. Hash chains are integrity checks,
  not signatures. A complete rewrite of bundle plus anchors requires external
  immutable records to detect.
- Non-cooperating external output writers are unsupported. Reconciliation is
  bounded to the explicitly requested identity; staging is retained, not globally
  scanned/repaired/deleted. Missing/corrupt finals are quarantined. DB and FS are
  not a single atomic transaction. Events are append-only at application API level.
- Budgets are cooperative; blocking filesystem calls cannot be interrupted at an
  exact wall-clock deadline. Library-directory presence does not prove ABI or
  compute-node visibility. Profile Python path presence does not prove its version;
  the target smoke gate performs the actual runtime version report.
- The referenced Phase 1 conversation and upstream PDF were not available through
  the supplied tools. Both attached v1.0 Markdown contracts were read; the explicit
  current user request governs this implementation. No claim is made to have
  verified inaccessible prior-conversation/PDF requirements.
