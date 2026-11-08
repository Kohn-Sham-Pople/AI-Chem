# OGE 6.2u7 parser compatibility and read-only local acceptance

Patch baseline: `782e17921fc198e0ca9d50a62a9146324e526ff7` on
`codex/step1-3-submission`. The operator reports CentOS 6.9, OGE 6.2u7,
Python 3.9.19, linked SQLite 3.46.1, Asia/Seoul, two completed scheduler pilots,
and 402 passing original tests. These are user-reported local results; cloud did
not access the cluster or the private observations. Acceptance of this patch on
the actual HPC is **NOT_RUN** until the operator reruns the checks below.

## Scope and compatibility

- `fields()` recognizes simple identifier keys with colon or horizontal whitespace
  delimiters, and compound colon keys made of identifier words, including
  `parallel environment:`, `hard resource_list:` and `scheduling info:`.
  Colons within Accounting date values remain values. Invalid/control-character
  keys, ambiguous compound keys and duplicate keys fail closed. Required detail
  and Accounting fields remain required.
- `timestamp(raw, cluster_timezone=None)`, `parse_detail(data, cluster_timezone=None)`
  and `parse_accounting(data, cluster_timezone=None)` keep existing absolute Unix
  epoch and timezone-aware ISO inputs. C/English dates such as
  `Mon Nov  9 00:52:42 2026` require an explicitly supplied approved profile zone.
  Admission and reconciliation pass `profile['cluster_timezone']` on every path.
  A missing zone never means process-local time or an assumed UTC.
- English weekday/month tokens are parsed without locale-sensitive strptime or
  changing process locale. The actual calendar date and weekday must agree.
  The existing supported zones remain UTC and Asia/Seoul. Asia/Seoul uses Python
  3.9's stdlib ZoneInfo and local IANA data, not a guessed fixed offset. Missing
  timezone data, invalid dates, historical DST gaps/folds and unknown zones block.
  No extra Python dependency or timezone download is introduced.
- A single OGE summary with `taskid=undefined` and absent `pe_taskid` uses the
  existing master-record rule. Explicit PE task rows still need a consistent
  master. Array tasks, missing fields and conflicting masters remain errors.
  No identity, full token, owner, cwd, manifest, PE/slots or plausible-time
  postfilter is weakened. Receipts, fencing, storage and qsub argv are unchanged.

This is a compatible text-parser correction within **sge_xml_v1**, not a new XML
wire format or a schema migration. No new dialect is needed: parse_qstat/XML and
the profile schema are unchanged, and existing armed intents can keep their
original immutable profile, run and token. English dates are accepted only with
the already explicit, approved profile timezone. The current profile-bound
`dialect_evidence` still requires approved cluster/epoch/owner, client version,
paths/alias group and capabilities. This patch does not manufacture that evidence.

Do not edit a registered profile/proof in place, delete state, change epochs or
reset a fence to install this fix. If a *new* profile revision or new evidence pin
is necessary, follow the existing registration/review process before new dispatch.
Existing uncertain intents retain their original identity and pinned profile.

## 1. Local synthetic regressions with inherited HPC variables

From the repository root, use the approved Python and development dependencies:

```sh
PYTHONPATH=src:tests "$AI_CHEM_PY" -B -m pytest -q
PYTHONPATH=src:tests "$AI_CHEM_PY" -B -m pytest -q \
  tests/unit/submission/test_oge62.py \
  tests/integration/submission/test_oge62_service.py
```

Leave the real parent SGE_ROOT/SGE_CELL alone. Autouse submission fixtures remove
them only inside each synthetic test and restore them afterwards, including in
forked worker tests. Production still refuses mismatched inherited variables.
No real scheduler, MPI or VASP is run by these tests. The new integration cases
use the existing independent durable fake scheduler only.

The two fixture files under tests/fixtures/sge_synthetic/oge_6_2u7_* are entirely
hand-authored: job 1001, synthetic owner/node/path and artificial token/hash. No
real pilot output, real job identity or private environment was copied into Git.

## 2. Read-only parser acceptance on existing private pilot captures

Use existing approved private capture files. Do not submit another probe or VASP
job for this check. Since the pilots have ended, qstat -j may no longer return
their detail; use the locally retained detail capture. If no such capture exists,
mark that portion NOT_RUN instead of inventing it or submitting a replacement.
Do not upload captures or the completed config/proof files.

Set the following shell variables to already existing local files outside Git:
SUBMIT_CONFIG, PILOT_QSTAT_XML, PILOT_DETAIL, PILOT_QACCT. The qacct file must be
the single-record capture for the same pilot as PILOT_DETAIL. Run separately for
each of the two pilots. The approved profile must explicitly say Asia/Seoul.

This command reads files only, opens no DB, acquires no lock, writes no receipts
and invokes no scheduler/process. It prints only sanitized counts/status codes.
An unregistered evidence pin is explicitly NOT_RUN, never automatic approval.

```sh
PYTHONPATH=src "$AI_CHEM_PY" -B - \
  "$SUBMIT_CONFIG" "$PILOT_QSTAT_XML" "$PILOT_DETAIL" "$PILOT_QACCT" <<'PY'
import json, re, sys
from ai_chem_input.errors import InputError, require
from ai_chem_input.paths import read_small
from ai_chem_input.provenance import digest
from ai_chem_input.submission.preflight import load_config, proof
from ai_chem_input.submission.sge import parse_qstat, parse_detail, parse_accounting, timestamp
try:
    config, _ = load_config(sys.argv[1])
    p = config['profile']
    require(p['cluster_timezone'] == 'Asia/Seoul', 'LOCAL_TIMEZONE_MISMATCH', exit_code=4)
    zone = p['cluster_timezone']
    # Independent absolute UTC oracles for the public example date strings.
    require(timestamp('Mon Nov  9 00:52:42 2026', zone) == 1794153162.0,
            'LOCAL_TIME_CONVERSION', exit_code=4)
    require(timestamp('Sat Nov  7 14:12:46 2026', zone) == 1794028366.0,
            'LOCAL_TIME_CONVERSION', exit_code=4)
    jobs = parse_qstat(read_small(sys.argv[2], 8*1024*1024), p['expected_owner']['name'])
    detail = parse_detail(read_small(sys.argv[3], 8*1024*1024), cluster_timezone=zone)
    records = parse_accounting(read_small(sys.argv[4], 8*1024*1024), cluster_timezone=zone)
    require(len(records) == 1, 'LOCAL_RECORD_COUNT', exit_code=4)
    accounted = records[0]
    require(detail['owner'] == p['expected_owner']['name'] and
            detail['pe'] == 'mpi_32' and detail['slots'] == 32,
            'LOCAL_PILOT_IDENTITY', exit_code=4)
    require(re.fullmatch(r'ac_[0-9a-f]{32}', detail['name']) is not None and
            detail['token'] == detail['name'][3:] and
            re.fullmatch(r'[0-9a-f]{64}', detail['manifest'] or '') is not None,
            'LOCAL_PILOT_IDENTITY', exit_code=4)
    require(all(detail[k] == accounted[k] for k in
                ('job_id', 'name', 'owner', 'pe', 'slots', 'qsub_time')),
            'LOCAL_PILOT_IDENTITY', exit_code=4)
    evidence = 'NOT_RUN'
    if p['dialect_evidence'] is not None:
        e = proof(p, 'dialect_evidence', 'dialect')
        require(e['dialect'] == p['dialect'] and '6.2u7' in e['client_version'] and
                e['client_paths_sha256'] == digest('sge-paths-v1',
                    {k:p[k+'_path'] for k in ('qsub','qstat','qacct')}) and
                e['qmaster_aliases'] == p['qmaster_aliases'],
                'DIALECT_UNVERIFIED', exit_code=4)
        evidence = 'PASS'
    print(json.dumps(dict(parser_acceptance='PASS', qstat='PASS', detail='PASS',
        accounting='PASS', qstat_job_count=len(jobs), accounting_records=len(records),
        dialect_evidence=evidence, dispatch_allowed=False)))
except (InputError, OSError, ValueError, KeyError, TypeError) as error:
    print(json.dumps(dict(parser_acceptance='FAIL',
        issue_code=getattr(error, 'code', 'LOCAL_PARSER_ERROR'), dispatch_allowed=False)))
    sys.exit(4)
PY
```

Keep this result and actual capture hashes/reviewer metadata private. Locally
compare the pilot cwd, full token/manifest and submit time to the pilot's original
records too; cross-matching two captures alone is not production authorization.
Empty qstat after completion is allowed by this parser check and never proves
non-submission. No accounting exit code is scientific success or retry evidence.

## Remaining acceptance and operational blockers

- Rerun the full suite and both actual private parser cases on CentOS 6.9 /
  Python 3.9.19 / linked SQLite 3.46.1; verify local Asia/Seoul IANA data availability.
  Cloud runs still use linked SQLite 3.46.0 and do not replace that target gate.
- Confirm client version, known active states/ranges, full token preservation and
  accounting master/task behavior against approved OGE 6.2u7 observations. Preserve
  reviewed private capability evidence and its exact hash pin. No auto-registration.
- The two reported successful scheduler pilots do not establish preserve_source
  -V/node127/default/JSV/Intel/MKL equivalence, hard RQS/pending-policy approval or
  actual verified-bundle/VASP pilot acceptance by themselves. Retain those gates.
- live_enabled stays false by default. Actual submission, an additional pilot or
  Cron activation is not authorized by this parser repair. Never reset an armed
  fence, retry a timed-out submit, or change scientific parameters to pass a test.
