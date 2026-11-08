import os
import subprocess
import pytest

@pytest.fixture(autouse=True)
def no_real_scheduler(monkeypatch):
    original=subprocess.Popen
    def guarded(args,*pos,**kw):
        executable=str(args[0] if isinstance(args,(list,tuple)) else args)
        if os.path.basename(executable) in ('qsub','qstat','qacct','mpirun','vasp_ncl'):
            raise AssertionError('Real scheduler/MPI/VASP execution forbidden in synthetic tests')
        return original(args,*pos,**kw)
    monkeypatch.setattr(subprocess,'Popen',guarded)
