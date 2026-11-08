import os
import subprocess
from pathlib import Path
import pytest

@pytest.fixture(autouse=True)
def no_real_scheduler(monkeypatch):
    original=subprocess.Popen
    def guarded(args,*pos,**kw):
        executable=str(args[0] if isinstance(args,(list,tuple)) else args)
        if os.path.basename(executable) in ('qsub','qstat','qacct','mpirun','vasp_ncl') and '/runner/' not in executable:
            raise AssertionError('Real scheduler/MPI/VASP execution forbidden in synthetic tests')
        if os.path.basename(executable) in ('qsub','qstat','qacct') and Path(executable).exists():
            assert b'SYNTHETIC TEST ONLY' in Path(executable).read_bytes()[:512]
        return original(args,*pos,**kw)
    monkeypatch.setattr(subprocess,'Popen',guarded)
