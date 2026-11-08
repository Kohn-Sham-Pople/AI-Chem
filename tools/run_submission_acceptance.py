"""Run the full synthetic suite and record test IDs; never contact a scheduler.

Use the development pytest dependency. Local HPC acceptance remains NOT_RUN;
this tool cannot promote mock evidence into cluster or operational approval.
"""
import datetime
import hashlib
import json
import platform
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PREFIX = ROOT / 'docs/step_1_3/evidence/cloud_synthetic'
BASE = 'b510177725075ce549ef5d5fca8bcf050ab8ed03'
CHECKS = [
    ('S13-01', 'One dispatch and strict binding', ['test_s13_01_submit_once']),
    ('S13-02', 'Request redelivery and stable identity', ['test_s13_02_03', 'test_s13_02_science', 'test_restarted_client']),
    ('S13-03', 'Labels and physical/scientific aliases', ['test_s13_02_03', 'test_s13_03_']),
    ('S13-04', 'Bundle integrity and source immutability', ['test_s13_04_', 'test_s13_01_submit_once', 'test_preparation_rows']),
    ('S13-05', 'Accepted timeout/crash recovery', ['test_s13_05_', 'test_restarted_client']),
    ('S13-06', 'Fence-before-spawn crash', ['test_s13_06_07_fault_windows[fence', 'test_s13_13_fence_commit']),
    ('S13-07', 'Immutable receipt and DB crash recovery', ['test_s13_06_07_fault_windows', 'test_s13_07_', 'test_receipt_']),
    ('S13-08', 'Unknown/delayed observation never retries', ['test_s13_08_', 'test_s13_05_08_']),
    ('S13-09', 'Weak/multiple identity evidence', ['test_s13_08_09_', 'test_accounting_timestamp']),
    ('S13-10', 'Malformed acknowledgment and bounded clients', ['test_s13_10_', 'test_bounded_synthetic', 'test_independent_output', 'test_timeout_and_no_shell', 'test_definite_']),
    ('S13-11', 'User-wide 320-slot admission', ['test_s13_11_', 'test_live_gates_are_fail_closed']),
    ('S13-12', 'Reservation/PE row deduplication', ['test_s13_12_', 'test_hand_authored_sge']),
    ('S13-13', 'Concurrent writers and CAS/DB failures', ['test_s13_13_']),
    ('S13-14', 'Strict dry-run and side-effect-free help', ['test_s13_14_', 'test_help_is_']),
    ('S13-15', 'Actual SGE defaults/environment/CLI precedence', ['test_s13_15_', 'test_default_live_false', 'test_qmaster_change']),
    ('S13-16', 'Exact target runtime and benign local SGE pilot', []),
    ('S13-17', 'Actual approved verified-bundle submission', []),
    ('S13-18', 'Restore/epoch/orphan evidence blocking', ['test_s13_18_', 'test_restore_pause_']),
]
LOCAL = {
    'S13-15': 'Actual SGE defaults/JSV, -V inheritance, f node127 selection and Intel/MKL environment equivalence require private local evidence and explicit change approval.',
    'S13-16': 'Exact CentOS 6.9 / Python 3.9.19 / linked SQLite 3.46.1 and local SGE/RQS/dialect/storage are unverified; benign pilot requires separate user approval.',
    'S13-17': 'No actual private Input/POTCAR was accessed; actual single-job d/f pilot and Cron require separate authorization.',
}


class Evidence:
    def __init__(self):
        self.tests = {}

    def pytest_runtest_logreport(self, report):
        row = self.tests.setdefault(report.nodeid, dict(test_id=report.nodeid, outcome='PASS', duration_seconds=0))
        row['duration_seconds'] += report.duration
        if report.failed:
            row['outcome'] = 'FAIL'
        elif report.skipped and row['outcome'] != 'FAIL':
            row['outcome'] = 'NOT_RUN'


def source_digest():
    entries = []
    for directory in ('src', 'tests', 'schemas', 'tools'):
        for path in sorted((ROOT / directory).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc' and not any(part.endswith('.egg-info') for part in path.parts):
                entries.append((str(path.relative_to(ROOT)), hashlib.sha256(path.read_bytes()).hexdigest()))
    entries.append(('pyproject.toml', hashlib.sha256((ROOT / 'pyproject.toml').read_bytes()).hexdigest()))
    return hashlib.sha256(json.dumps(entries, separators=(',', ':')).encode()).hexdigest()


def main():
    if Path.cwd() != ROOT:
        raise SystemExit('Run from the repository root.')
    plugin = Evidence()
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    code = pytest.main(['-q', '--tb=short'], plugins=[plugin])
    tests = sorted(plugin.tests.values(), key=lambda row: row['test_id'])
    for row in tests:
        row['duration_seconds'] = round(row['duration_seconds'], 6)
    matrix = []
    for check, title, selectors in CHECKS:
        matched = [r for r in tests if '/submission/' in r['test_id'] and any(s in r['test_id'] for s in selectors)]
        automated = ('FAIL' if any(r['outcome'] == 'FAIL' for r in matched) else
                     'PASS' if matched and all(r['outcome'] == 'PASS' for r in matched) else 'NOT_RUN')
        matrix.append(dict(id=check, title=title, status='NOT_RUN' if check in LOCAL else automated,
                           automated_status=automated, test_ids=[r['test_id'] for r in matched],
                           local_blocker=LOCAL.get(check)))
    report = dict(schema_version=1, scope='CLOUD_SYNTHETIC_ONLY', base_commit=BASE,
                  started_at=started, python=platform.python_version(), linked_sqlite=sqlite3.sqlite_version,
                  system=platform.system(), machine=platform.machine(), implementation_tree_sha256=source_digest(),
                  pytest_exit_code=int(code), test_count=len(tests),
                  step_1_2_count=sum('/submission/' not in r['test_id'] for r in tests),
                  step_1_3_count=sum('/submission/' in r['test_id'] for r in tests),
                  outcomes={state: sum(r['outcome'] == state for r in tests) for state in ('PASS','FAIL','NOT_RUN')},
                  tests=tests)
    PREFIX.parent.mkdir(parents=True, exist_ok=True)
    PREFIX.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
    PREFIX.with_suffix('.log').write_text('CLOUD_SYNTHETIC_ONLY\n' + '\n'.join(r['outcome'] + ' ' + r['test_id'] for r in tests) + '\n')
    (PREFIX.parent.parent / 'acceptance_matrix.json').write_text(json.dumps(matrix, indent=2) + '\n')
    lines = ['# S13 acceptance matrix', '',
             'Evidence: [per-test results](evidence/cloud_synthetic.json), [test log](evidence/cloud_synthetic.log).', '',
             'PASS means automated synthetic evidence. Actual cluster checks remain NOT_RUN; no scheduler/VASP pilot or Cron was executed.', '',
             '| Acceptance | Scope | Status | Automated cases |', '|---|---|---|---|']
    lines += ['| {id} | {title} | {status} | {count} ({automated_status}) |'.format(count=len(r['test_ids']), **r) for r in matrix]
    lines += ['', 'Full parameterized test IDs and local blockers are in acceptance_matrix.json.', '',
              'Full suite: {} passed, {} failed, {} not run; Step 1-2 {}, Step 1-3 {}.'.format(
                  report['outcomes']['PASS'], report['outcomes']['FAIL'], report['outcomes']['NOT_RUN'], report['step_1_2_count'], report['step_1_3_count']), '',
              'Cloud Python {} / linked SQLite {} is test evidence, not exact HPC acceptance.'.format(report['python'], report['linked_sqlite']), '',
              'Reproduce from the repository root with the approved development dependencies:', '',
              '```sh', 'PYTHONPATH=src:tests "$AI_CHEM_PY" -B tools/run_submission_acceptance.py', '```', '',
              'This writes public synthetic evidence only; do not use it to publish private HPC outputs.', '']
    (PREFIX.parent.parent / 'acceptance_matrix.md').write_text('\n'.join(lines))
    return int(code) or int(any(r['status'] == 'FAIL' for r in matrix))


if __name__ == '__main__':
    sys.exit(main())
