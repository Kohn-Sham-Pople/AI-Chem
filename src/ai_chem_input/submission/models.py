import os
from dataclasses import dataclass,field
from pathlib import Path
from ..config import loads,validate
from ..errors import InputError


def checked(value,kind):
    schema=loads((Path(__file__).parent/'schemas'/(kind+'.json')).read_bytes())
    validate(value,schema)
    return value


@dataclass(frozen=True)
class VerifiedBundle:
    path: str
    manifest_sha256: str
    manifest_json: bytes
    resolved_json: bytes


@dataclass(frozen=True)
class SubmissionPlan:
    request_json: bytes
    config_json: bytes
    config_path: str
    config_sha256: str
    bundle: VerifiedBundle
    calculation_key: str
    bundle_key: str
    request_digest: str
    execution_json: bytes


@dataclass(frozen=True)
class CommandSpec:
    kind: str
    executable: str
    argv: tuple
    cwd: str
    env: tuple
    timeout: float
    output_limit: int


@dataclass(frozen=True)
class DispatchOutcome:
    spawn_status: str
    returncode: object
    timed_out: bool=False
    output_overflow: bool=False
    stdout: bytes=b''
    stderr: bytes=b''
    started_at: float=0
    finished_at: float=0


@dataclass(frozen=True)
class SchedulerSnapshot:
    cluster_id: str
    cluster_epoch: str
    owner: str
    captured_at: float
    complete: bool
    jobs: tuple
    raw: tuple = ()


@dataclass
class DispatchPermit:
    intent_id: str
    command_digest: str=''
    pid: int=field(default_factory=os.getpid)
    used: bool=False
    def consume(self):
        if self.pid!=os.getpid() or self.used:
            raise InputError('DISPATCH_PERMIT_USED',exit_code=9)
        self.used=True


def result(operation,request=None,state='INVALID_REQUEST',issues=(),row=None,committed=False,dispatched=False,admission='NOT_CHECKED'):
    request=request or {}; row=dict(row or {})
    return dict(schema_version=1,operation=operation,request_id=request.get('request_id'),
        calculation_id=request.get('calculation_id',row.get('calculation_id')),calculation_key=row.get('calculation_key'),
        stage_id=request.get('stage_id',row.get('stage_id')),intent_id=row.get('intent_id'),run_instance_id=row.get('run_instance_id'),
        state=state,committed=committed,dispatched_this_call=dispatched,dispatch_allowed=False,
        scheduler_job_id=row.get('job_id'),live_admission=admission,issue_codes=list(issues),
        review_required=state in ('REVIEW_REQUIRED','IDENTITY_CONFLICT','SUBMISSION_UNCERTAIN'))

EXIT={'SUBMITTED':0,'EXISTING':0,'DRY_RUN_VALID':0,'INVALID_REQUEST':2,'INPUT_REJECTED':3,'ADMISSION_BLOCKED':4,
 'LOCAL_STATE_ERROR':5,'BUSY':6,'IDENTITY_CONFLICT':7,'SUBMISSION_UNCERTAIN':8,'REVIEW_REQUIRED':9,'NOT_DISPATCHED':10}
