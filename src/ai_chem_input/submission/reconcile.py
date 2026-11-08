import time
import uuid
from pathlib import Path
from .models import result
from .preflight import proof,verify_runtime_identity
from .receipts import read_outcome,publish
from .sge import command,parse_qstat,parse_detail,parse_accounting
from .admission import successful
from ..errors import require,InputError
from ..provenance import canonical
from ..config import loads


def outcome_state(receipt):
    if receipt['spawn_status']=='SPAWN_FAILED': return 'NOT_DISPATCHED'
    return 'SUBMITTED' if receipt['parsed_job_id'] else 'SUBMISSION_UNCERTAIN'


def strong_candidate(candidate,row,captured):
    record=loads(row['record_json'])
    if candidate.get('name')!='ac_'+row['token']: return False
    if candidate.get('owner')!=row['owner'] or candidate.get('pe')!='mpi_32' or candidate.get('slots')!=32: return False
    timestamp=candidate.get('qsub_time')
    if timestamp is None or not row['armed_at']-120<=timestamp<=captured+120: return False
    if not candidate.get('terminal'):
        if candidate.get('token')!=row['token'] or candidate.get('manifest')!=record['manifest_sha256'] or candidate.get('cwd')!=record['bundle_path']: return False
    return True


def reconcile_submission(store,row,runner,deadline=None):
    require(row['dispatch_fence']==1,'NOT_ARMED',exit_code=9)
    try: receipt=read_outcome(store,row)
    except (InputError,OSError,KeyError,ValueError,TypeError):
        updated=store.transition(row,'REVIEW_REQUIRED','RECEIPT_INVALID')
        return result('reconcile',state='REVIEW_REQUIRED',issues=['RECEIPT_INVALID'],row=updated,committed=True)
    if receipt and row['state']!='SUBMITTED':
        value,h=receipt; state=outcome_state(value)
        if state in ('SUBMITTED','NOT_DISPATCHED'):
            updated=store.transition(row,state,'DURABLE_RECEIPT',value['parsed_job_id'],h)
            return result('reconcile',state=state,row=updated,committed=True)
    if row['state'] in ('NOT_DISPATCHED','REVIEW_REQUIRED','IDENTITY_CONFLICT'):
        return result('reconcile',state=row['state'],row=row)
    p=store.profile; require(p['live_enabled'],'LIVE_DISABLED',exit_code=4)
    verify_runtime_identity(p)
    proof(p,'dialect_evidence','dialect')
    record=loads(row['record_json']); cwd=record['bundle_path']; candidates=[]; raw=[]; unknown=False
    try:
        output=runner.query(command(p,'qstat',cwd,['-xml','-u',row['owner']]),deadline); raw.append(('qstat.xml',output.stdout,output.stderr))
        require(successful(output),'OBSERVATION_UNKNOWN',exit_code=4)
        jobs=parse_qstat(output.stdout,row['owner'])
        relevant=[j for j in jobs if j['name']=='ac_'+row['token'] or j['name'].startswith('ac_'+row['token'][:12]) or j['job_id']==row.get('job_id')]
        require(len(relevant)+2<=p['max_queries'],'QUERY_LIMIT',exit_code=4)
        for job in relevant:
            detail=runner.query(command(p,'qstat',cwd,['-j',job['job_id']]),deadline); raw.append(('detail_'+job['job_id'],detail.stdout,detail.stderr))
            require(successful(detail),'OBSERVATION_UNKNOWN',exit_code=4)
            candidates.append(parse_detail(detail.stdout))
        # Also query accounting: a fast terminal job may never appear in qstat.
        accounted=runner.query(command(p,'qacct',cwd,['-o',row['owner'],'-j',row.get('job_id') or 'ac_'+row['token']]),deadline)
        raw.append(('qacct',accounted.stdout,accounted.stderr))
        require(successful(accounted),'OBSERVATION_UNKNOWN',exit_code=4)
        candidates.extend(parse_accounting(accounted.stdout))
    except (InputError,OSError,ValueError,KeyError): unknown=True
    captured=time.time(); strong={}; weak=False
    for candidate in candidates:
        if strong_candidate(candidate,row,captured):
            key=(candidate['job_id'],candidate['owner'],candidate['qsub_time'])
            # Prefer terminal evidence for repeated PE records/live+accounted overlap.
            if key not in strong or candidate['terminal']: strong[key]=candidate
        else: weak=True
    if len({c['job_id'] for c in strong.values()})>1 or len(strong)>1:
        state='IDENTITY_CONFLICT'; reason='MULTIPLE_SCHEDULER_IDENTITIES'; selected=None
    elif weak:
        state='REVIEW_REQUIRED'; reason='WEAK_IDENTITY'; selected=None
    elif len(strong)==1 and not unknown:
        selected=next(iter(strong.values())); state='SUBMITTED'; reason='EXACT_SCHEDULER_IDENTITY'
    else:
        selected=None; state='SUBMISSION_UNCERTAIN'; reason='OBSERVATION_UNKNOWN' if unknown else 'IDENTITY_NOT_OBSERVED'
    observations=store.connect()
    try: count=observations.execute('SELECT COUNT(*) FROM scheduler_observations WHERE intent_id=?',(row['intent_id'],)).fetchone()[0]
    finally: observations.close()
    if state=='SUBMISSION_UNCERTAIN' and (captured-row['armed_at']>=p['reconcile_grace_seconds'] or count+1>=p['reconcile_max_observations']):
        state='REVIEW_REQUIRED'; reason='RECONCILE_LIMIT'
    observation_id=uuid.uuid4().hex; directory=store.state/'submissions'/row['intent_id']/'observations'/observation_id
    for name,stdout,stderr in raw:
        publish(directory/(name+'.stdout'),stdout); publish(directory/(name+'.stderr'),stderr)
    h=publish(directory/'observation.json',canonical(dict(schema_version=1,captured_at=captured,state=state,reason=reason,candidates=candidates,unknown=unknown)))
    store.observation(row,'sge',reason,h)
    updated=store.transition(row,state,reason,selected['job_id'] if selected else None,
                             terminal=bool(selected and selected['terminal']),scheduler_time=selected['qsub_time'] if selected else None)
    return result('reconcile',state=state,issues=[] if state=='SUBMITTED' else [reason],row=updated,committed=True)
