import sqlite3
import time
from contextlib import nullcontext
from pathlib import Path
from .models import checked,result
from .preflight import build_submission_plan,load_config,live_gates,refresh,reject_used
from .store import SubmissionStore
from .sge import build_qsub
from .runner import BoundedRunner,execute_qsub_once,validate_target_runtime
from .admission import snapshot,check_admission
from .receipts import intent_files,fence_file,persist_outcome,publish
from .reconcile import reconcile_submission,outcome_state
from ..config import loads
from ..errors import InputError,require
from ..paths import safe_path
from ..provenance import canonical
import uuid
from ..state import global_lock


def error_result(operation,request,error,row=None,armed=False,dispatched=False):
    if armed:
        return result(operation,request,'SUBMISSION_UNCERTAIN',[getattr(error,'code','POST_FENCE_LOCAL_FAILURE')],row,committed=bool(row and row.get('dispatch_fence')),dispatched=dispatched)
    code=getattr(error,'code','LOCAL_STATE_ERROR'); number=getattr(error,'exit_code',5)
    state={2:'INVALID_REQUEST',3:'INPUT_REJECTED',4:'ADMISSION_BLOCKED',5:'LOCAL_STATE_ERROR',6:'BUSY',7:'IDENTITY_CONFLICT',9:'REVIEW_REQUIRED'}.get(number,'LOCAL_STATE_ERROR')
    return result(operation,request,state,[code],row)


def existing_result(request,row,committed=False):
    state=row['state']
    if state in ('DISPATCH_ARMED','SUBMISSION_UNCERTAIN'): state='SUBMISSION_UNCERTAIN'
    elif state=='SUBMITTED': state='EXISTING'
    return result('submit',request,state,row=row,committed=committed)


def _known_request(request,config,store):
    row=store.lookup(request_id=request['request_id'])
    if not row: return None
    record=loads(row['record_json']); p=config['profile']
    require(request['expected_manifest_sha256']==record['manifest_sha256'] and request['stage_id']==row['stage_id']
            and request['submission_profile']=={k:p[k] for k in ('id','revision')}
            and request['bundle_ref'] in config['bundle_refs']
            and str(safe_path(config['bundle_refs'][request['bundle_ref']]))==record['bundle_path']
            and p==record['profile'],'REQUEST_ID_CONFLICT',exit_code=7)
    return row


def submit(request,config_path,dry_run=False,runner=None,fault=None,deadline=None,_locked=False):
    row=None; armed=False; dispatched=False
    try:
        checked(request,'request'); config,_=load_config(config_path); p=config['profile']; store=SubmissionStore(p)
        deadline=min(deadline or float('inf'),time.monotonic()+p['worker_budget_seconds'])
        existing=_known_request(request,config,store)
        if existing and existing['dispatch_fence'] and not dry_run:
            with (nullcontext() if _locked else global_lock(p['roots']['lock'])):
                store.guard(); return existing_result(request,store.lookup(intent_id=existing['intent_id']))
        plan=build_submission_plan(request,config_path,deadline)
        existing=existing or store.find(plan)
        if existing: require(existing['request_digest']==plan.request_digest,'IDENTITY_CONFLICT',exit_code=7)
        else: reject_used(plan.bundle)
        if dry_run:
            response=result('submit',request,'DRY_RUN_VALID',row=dict(calculation_key=plan.calculation_key))
            report=loads(plan.execution_json)
            response.update(execution_blockers=report['blockers'],execution_changes=report['changes'],planned_argv=['QSUB']+list(build_qsub(p,plan.bundle.path,plan.bundle.manifest_sha256,'0'*32).argv[1:]))
            return response
        require(p['live_enabled'],'LIVE_DISABLED',exit_code=4)
        with (nullcontext() if _locked else global_lock(p['roots']['lock'])):
            store.guard()
            row=store.lookup(request_id=request['request_id']) or store.find(plan)
            if row:
                require(row['request_digest']==plan.request_digest,'IDENTITY_CONFLICT',exit_code=7)
                alias_changed=store.alias(request,row)
                if row['dispatch_fence']: return existing_result(request,row,alias_changed)
                require(row['state']=='SUBMIT_PENDING','PENDING_STATE_INVALID',exit_code=9)
            live_gates(plan); refresh(plan,deadline)
            if runner is None: validate_target_runtime()
            actual_runner=runner or BoundedRunner(p)
            admission=check_admission(snapshot(p,actual_runner,plan.bundle.path,deadline),store.all_intents(),p,row['intent_id'] if row else None)
            if fault: fault('before_pending')
            if row is None: row=store.create_or_get_intent(plan)
            if fault: fault('pending')
            spec=build_qsub(p,plan.bundle.path,plan.bundle.manifest_sha256,row['token'])
            command_json,command_hash=intent_files(store,row,spec)
            if fault: fault('intent_files')
            # Rehash before the final fresh user-wide snapshot, not after it ages out.
            refresh(plan,deadline); live_gates(plan)
            latest=snapshot(p,actual_runner,plan.bundle.path,deadline)
            admission=check_admission(latest,store.all_intents(),p,row['intent_id'])
            evidence_dir=store.state/'submissions'/row['intent_id']/'admission'/uuid.uuid4().hex
            for name,stdout,stderr in latest.raw:
                publish(evidence_dir/(name+'.stdout'),stdout); publish(evidence_dir/(name+'.stderr'),stderr)
            admission['snapshot_sha256']=publish(evidence_dir/'snapshot.json',canonical(dict(cluster_id=latest.cluster_id,cluster_epoch=latest.cluster_epoch,owner=latest.owner,captured_at=latest.captured_at,complete=latest.complete,jobs=latest.jobs)))
            admission['rqs_evidence_sha256']=p['scheduler_rqs_evidence']['sha256']
            admission['profile']={k:p[k] for k in ('id','revision')}
            require(0<=time.time()-latest.captured_at<=p['snapshot_max_age_seconds'],'SNAPSHOT_STALE',exit_code=4)
            require(deadline-time.monotonic()>=p['qsub_timeout_seconds']+2,'BUDGET_EXHAUSTED',exit_code=4)
            armed=True
            permit=store.arm_dispatch(row['intent_id'],row['version'],command_json,command_hash,admission)
            row=store.lookup(intent_id=row['intent_id'])
            if fault: fault('fence')
            fence_file(store,row)
            if fault: fault('fence_receipt')
            require(0<=time.time()-latest.captured_at<=p['snapshot_max_age_seconds'],'SNAPSHOT_STALE',exit_code=4)
            dispatched=True  # attempted; reset only on a definite no-process outcome
            outcome=execute_qsub_once(permit,spec,actual_runner,deadline)
            dispatched=outcome.spawn_status!='SPAWN_FAILED'
            if fault: fault('outcome')
            receipt,h=persist_outcome(store,row,spec,outcome)
            if fault: fault('receipt')
            state=outcome_state(receipt)
            row=store.transition(row,state,'QSUB_OUTCOME',receipt['parsed_job_id'],h)
            if fault: fault('bound')
            return result('submit',request,state,row=row,committed=True,dispatched=dispatched,admission='PERMITTED')
    except (InputError,OSError,sqlite3.Error,ValueError,KeyError,TypeError) as exc:
        return error_result('submit',request,exc,row,armed,dispatched)


def reconcile(intent_id,config_path,runner=None,deadline=None,_locked=False):
    row=None
    try:
        config,_=load_config(config_path); p=config['profile']; store=SubmissionStore(p)
        deadline=min(deadline or float('inf'),time.monotonic()+p['worker_budget_seconds'])
        with (nullcontext() if _locked else global_lock(p['roots']['lock'])):
            store.guard(allow_paused=True); row=store.lookup(intent_id=intent_id)
            require(row is not None,'INTENT_NOT_FOUND',exit_code=2)
            operational={'live_enabled','paused','paused_restore'}
            require({k:v for k,v in loads(row['record_json'])['profile'].items() if k not in operational}=={k:v for k,v in p.items() if k not in operational},'PROFILE_CHANGED',exit_code=9)
            return reconcile_submission(store,row,runner or BoundedRunner(p),deadline)
    except (InputError,OSError,sqlite3.Error,ValueError,KeyError,TypeError) as exc:
        return error_result('reconcile',None,exc,row)
