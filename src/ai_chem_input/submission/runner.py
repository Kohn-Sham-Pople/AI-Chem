"""Bounded concurrent pipe pump; no shell, retry, scheduler cancellation or VASP."""
import errno
import os
import selectors
import subprocess
import time
import sys
import sqlite3
import re
from pathlib import Path
from .models import DispatchOutcome
from .sge import command_digest
from ..errors import require


def validate_target_runtime():
    release=Path('/etc/centos-release')
    require(sys.version_info[:3]==(3,9,19) and sqlite3.sqlite_version=='3.46.1'
            and release.is_file() and re.search(r'\b6\.9\b',release.read_text()) is not None,
            'TARGET_RUNTIME_UNVERIFIED',exit_code=4)


class BoundedRunner:
    def __init__(self,profile):
        self.executables={k:profile[k+'_path'] for k in ('qsub','qstat','qacct')}
    def query(self,command,deadline=None):
        require(command.kind in ('qstat','qacct'),'COMMAND_FORBIDDEN',exit_code=4)
        return self._run(command,deadline)
    def dispatch(self,permit,command,deadline=None):
        require(command.kind=='qsub','COMMAND_FORBIDDEN',exit_code=4)
        require(permit.command_digest==command_digest(command),'DISPATCH_COMMAND_MISMATCH',exit_code=9)
        permit.consume()
        return self._run(command,deadline)
    def _run(self,command,deadline=None):
        validate_target_runtime()
        require(command.kind in self.executables and command.executable==self.executables[command.kind]
                and command.argv[0]==command.executable,'COMMAND_FORBIDDEN',exit_code=4)
        start=time.time(); until=time.monotonic()+command.timeout
        if deadline is not None: until=min(until,deadline)
        require(until>time.monotonic(),'BUDGET_EXHAUSTED',exit_code=4)
        try:
            process=subprocess.Popen(command.argv,cwd=command.cwd,env=dict(command.env),shell=False,
                stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True,start_new_session=True)
        except OSError as exc:
            definite=exc.errno in (errno.ENOENT,errno.EACCES,errno.ENOEXEC,errno.ENOTDIR)
            return DispatchOutcome('SPAWN_FAILED' if definite else 'SPAWN_UNKNOWN',None,started_at=start,finished_at=time.time())
        output={'stdout':bytearray(),'stderr':bytearray()}; timeout=False; overflow=False
        selector=selectors.DefaultSelector()
        for stream,name in ((process.stdout,'stdout'),(process.stderr,'stderr')):
            os.set_blocking(stream.fileno(),False); selector.register(stream,selectors.EVENT_READ,name)
        try:
            while selector.get_map():
                remaining=until-time.monotonic()
                if remaining<=0: timeout=True; break
                for key,_ in selector.select(min(remaining,0.1)):
                    data=os.read(key.fileobj.fileno(),65536)
                    if not data: selector.unregister(key.fileobj); continue
                    target=output[key.data]; available=command.output_limit-len(target)
                    target.extend(data[:available])
                    if len(data)>available: overflow=True; break
                if overflow: break
            if timeout or overflow:
                # Kill only the local client; never qdel the potentially accepted job.
                process.kill()
            try: rc=process.wait(timeout=max(0.1,min(1.0,until-time.monotonic())))
            except subprocess.TimeoutExpired:
                timeout=True; process.kill(); rc=process.wait()
        finally:
            selector.close(); process.stdout.close(); process.stderr.close()
            if process.poll() is None: process.kill(); process.wait()
        return DispatchOutcome('PROCESS_STARTED',rc,timeout,overflow,bytes(output['stdout']),bytes(output['stderr']),start,time.time())


def execute_qsub_once(permit,command,runner,deadline=None):
    return runner.dispatch(permit,command,deadline)
