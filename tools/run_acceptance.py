"""Synthetic evidence runner. Records actual outcomes, never upgrades local gates."""
import json
import platform
import sqlite3
from pathlib import Path
import pytest

PREFIXES={
 'AC01':['tests/integration/test_preparation.py::test_end_to_end','tests/integration/test_faults.py::test_copy_fault_preserves_source','tests/unit/test_t01.py'],
 'AC02':['tests/unit/test_t05_t07.py::test_protocol[f]','tests/unit/test_t12.py::test_independent_goldens'],
 'AC03a':['tests/unit/test_t05_t07.py::test_restart_closed'],
 'AC03b':['tests/unit/test_t06.py::test_restart_positive'],
 'AC03c':['tests/unit/test_t06.py::test_restart_negative','tests/unit/test_t06.py::test_revocation'],
 'AC04':['tests/unit/test_t05_t07.py::test_protocol[d]'],
 'AC05a':['tests/unit/test_validation_matrix.py::test_mapping_failures'],
 'AC05b':['tests/unit/test_validation_matrix.py::test_mapping_failures'],
 'AC05c':['tests/unit/test_validation_matrix.py::test_mapping_failures'],
 'AC06a':['tests/unit/test_validation_matrix.py::test_generated_magmom'],
 'AC06b':['tests/unit/test_validation_matrix.py::test_noncollinear'],
 'AC06c':['tests/unit/test_validation_matrix.py::test_generated_magmom'],
 'AC07':['tests/unit/test_t05_t07.py::test_profile','tests/unit/test_t05_t07.py::test_script_injection','tests/unit/test_t12.py::test_independent_goldens'],
 'AC08':['tests/integration/test_faults.py::test_verify_tampering'],
 'AC09':['tests/integration/test_cli_worker.py::test_cli_dry','tests/integration/test_preparation.py::test_end_to_end'],
 'AC10a':['tests/integration/test_preparation.py::test_end_to_end'],
 'AC10b':['tests/integration/test_preparation.py::test_identity_conflict'],
 'AC10c':['tests/integration/test_preparation.py::test_crash_reconciliation','tests/integration/test_preparation.py::test_two_process_writers'],
 'AC11':['tests/integration/test_preparation.py::test_end_to_end','tests/unit/test_t12.py::test_repo_synthetic_only'],
 'AC14':['tests/unit/test_t12.py::test_repo_synthetic_only'],
}

class Evidence:
    def __init__(self): self.outcomes={}
    def pytest_runtest_logreport(self,report):
        if report.when=='call' or report.failed:
            self.outcomes[report.nodeid]=report.outcome


def main():
    evidence=Evidence(); status=pytest.main(['-q','--tb=short','tests'],plugins=[evidence])
    matrix={}
    for key,prefixes in PREFIXES.items():
        tests={k:v for k,v in evidence.outcomes.items() if any(k.startswith(p) for p in prefixes)}
        matrix[key]=dict(status='passed' if tests and all(v=='passed' for v in tests.values()) else 'failed_or_unrun',tests=tests)
    matrix['AC12']=dict(status='not_run_exact_target',reason='Cloud Python 3.9.19 verified; linked SQLite 3.46.0, not CentOS 6.9')
    matrix['AC13']=dict(status='not_run',reason='Approved actual f/d bytes, private registry and reviewer golden evidence required on HPC only')
    folder=Path('docs/evidence'); folder.mkdir(exist_ok=True)
    (folder/'acceptance-matrix.json').write_text(json.dumps(dict(schema_version=1,scope='synthetic tests only; selected evidence is not an exhaustive proof of all DD cases',pytest_exit=status,checks=matrix),indent=2)+'\n')
    counts={k:sum(v==k for v in evidence.outcomes.values()) for k in ('passed','failed','skipped')}
    (folder/'environment-report.json').write_text(json.dumps(dict(python=platform.python_version(),linked_sqlite=sqlite3.sqlite_version,platform=platform.platform(),counts=counts,exact_target=False),indent=2)+'\n')
    return status

if __name__=='__main__': raise SystemExit(main())
