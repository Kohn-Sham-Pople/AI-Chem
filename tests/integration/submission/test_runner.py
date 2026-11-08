import os
import time
from pathlib import Path
import pytest
from ai_chem_input.submission.models import CommandSpec,DispatchPermit
from ai_chem_input.submission.runner import BoundedRunner
from ai_chem_input.submission.sge import parse_qsub,command_digest
from ai_chem_input.errors import InputError


@pytest.fixture(autouse=True)
def synthetic_client_runtime_only(monkeypatch):
    import ai_chem_input.submission.runner as module
    monkeypatch.setattr(module,'validate_target_runtime',lambda:None)


def fixture_runner(tmp_path,body,kind='qsub',limit=1024,timeout=1):
    folder=tmp_path/'runner'; folder.mkdir()
    executable=folder/kind
    # Use an installed interpreter only to execute a hand-authored synthetic client.
    import sys
    executable.write_text('#!'+sys.executable+'\n# SYNTHETIC TEST ONLY\n'+body); executable.chmod(0o700)
    profile={k+'_path':str(folder/k) for k in ('qsub','qstat','qacct')}
    runner=BoundedRunner(profile)
    spec=CommandSpec(kind,str(executable),(str(executable),),str(tmp_path),(('PATH','/usr/bin:/bin'),),timeout,limit)
    return runner,spec


@pytest.mark.parametrize('body,expected',[
    ("import sys\nsys.stdout.buffer.write(b'12345\\n')\nsys.stderr.buffer.write(b'warning')\n",'12345'),
    ("import sys\nsys.stdout.buffer.write(b'\\xff')\n",None),
    ("import os,signal\nos.kill(os.getpid(),signal.SIGTERM)\n",None),
])
def test_bounded_synthetic_process_and_protocol(tmp_path,body,expected):
    runner,spec=fixture_runner(tmp_path,body)
    permit=DispatchPermit('synthetic',command_digest=command_digest(spec))
    outcome=runner.dispatch(permit,spec)
    assert parse_qsub(outcome)==expected
    assert outcome.spawn_status=='PROCESS_STARTED'
    with pytest.raises(InputError): runner.dispatch(permit,spec)


@pytest.mark.parametrize('stream',['stdout','stderr','both'])
def test_independent_output_caps_do_not_deadlock_or_buffer_without_limit(tmp_path,stream):
    body="import os\n"
    if stream=='both': body+="for _ in range(1000):\n os.write(1,b'x'*4096)\n os.write(2,b'y'*4096)\n"
    else: body+="for _ in range(1000): os.write("+('1' if stream=='stdout' else '2')+",b'x'*4096)\n"
    runner,spec=fixture_runner(tmp_path,body)
    outcome=runner.dispatch(DispatchPermit('synthetic',command_digest=command_digest(spec)),spec)
    assert outcome.output_overflow and len(outcome.stdout)<=1024 and len(outcome.stderr)<=1024


def test_timeout_and_no_shell_interpolation(tmp_path):
    runner,spec=fixture_runner(tmp_path,'import time\ntime.sleep(30)\n',timeout=0.1)
    outcome=runner.dispatch(DispatchPermit('synthetic',command_digest=command_digest(spec)),spec)
    assert outcome.timed_out and parse_qsub(outcome) is None
    from dataclasses import replace
    executable=Path(spec.executable)
    executable.write_text('#!'+__import__('sys').executable+'\n# SYNTHETIC TEST ONLY\nimport sys\nprint(sys.argv[1])\n')
    spec=replace(spec,argv=(str(executable),'$(touch should-not-exist)'),timeout=1)
    outcome=runner.dispatch(DispatchPermit('second',command_digest=command_digest(spec)),spec)
    assert b'$(touch should-not-exist)' in outcome.stdout and not (tmp_path/'should-not-exist').exists()


def test_definite_missing_exec_and_query_cannot_dispatch(tmp_path):
    runner,spec=fixture_runner(tmp_path,'print(12345)\n')
    Path(spec.executable).unlink()
    outcome=runner.dispatch(DispatchPermit('synthetic',command_digest=command_digest(spec)),spec)
    assert outcome.spawn_status=='SPAWN_FAILED'
    with pytest.raises(InputError): runner.query(spec)
