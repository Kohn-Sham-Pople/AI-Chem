# Validation performed

Final synthetic acceptance: **131 passed, 0 failed, 0 skipped** under Python
**3.9.19**, Python-linked SQLite **3.46.0**, cloud Linux. AC12 exact SQLite
3.46.1/CentOS 6.9 and AC13 actual-template golden review remain NOT RUN.

Commands executed from the checkout:

```sh
PYTHONPATH=/tmp/ai-chem-py39-test-deps:src:tests PYTHONDONTWRITEBYTECODE=1 /tmp/ai-chem-python/cpython-3.9.19-linux-x86_64-gnu/bin/python3.9 tools/run_acceptance.py
PYTHONPATH=/tmp/ai-chem-py39-test-deps:src:tests PYTHONDONTWRITEBYTECODE=1 /tmp/ai-chem-python/cpython-3.9.19-linux-x86_64-gnu/bin/python3.9 tools/synthetic_smoke.py
```

These /tmp locations are cloud tooling paths, not proposed HPC locations.
Dev-only dependencies were installed from requirements-dev.txt. uv's managed
Python 3.9.19 distribution was installed with default verification retained;
system Python/libraries were not replaced. The final package was built/installed
with uv into /tmp/ai-chem-installed using Python 3.9.19 and --no-deps. Installed
CLI --help and packaged profile/manifest schema loading passed from /tmp.

Synthetic f A output: EDIFF=1E-04, NELM=300, AMIX/AMIX_MAG=0.1, LMAXMIX=6,
ISTART=0, LCHARG=true, no ICHARG. Synthetic d D: EDIFF=1E-06, AMIX=0.2,
AMIX_MAG=0.4, LMAXMIX=4, ISTART=0, no NELM/ICHARG. The test-only moments 1/-1
and mock U/geometry/potential data carry no actual material approval. Initial
stages contain neither CHGCAR nor WAVECAR.

Dry-run tree comparison, source bytes/mode/mtime preservation, different copy
inodes, stale config/source, partial-write/ENOSPC/rename failures, two-process
writers, crash reconciliation, hash/manifest tampering, production restart
blocking and test-only positive restart copying were exercised. Detailed node
IDs/outcomes are in acceptance-matrix.json. No VASP/MPI/fragment was executed.
No commit/push, real-file upload, scheduler/API call, actual HPC execution or
cloud environment publication was performed.
