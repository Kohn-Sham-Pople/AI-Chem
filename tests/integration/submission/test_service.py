import copy
from pathlib import Path
import pytest
from submission_support import make_case,FakeScheduler,Crash
from support import tree
from ai_chem_input.config import loads
from ai_chem_input.provenance import canonical
from ai_chem_input.submission.service import submit,reconcile
from ai_chem_input.submission.store import SubmissionStore


def test_s13_01_submit_once(tmp_path):
    req,path,config,bundle=make_case(tmp_path); fake=FakeScheduler(config['profile'],tmp_path/'fake')
    protected=tree(tmp_path/'research'); payload=tree(bundle)
    result=submit(req,str(path),runner=fake)
    assert result['state']=='SUBMITTED',result
    assert result['scheduler_job_id']=='1001' and result['dispatched_this_call']
    assert len(fake.jobs())==1 and fake.calls.count('qsub')==1
    assert tree(bundle)==payload and tree(tmp_path/'research')==protected
    row=SubmissionStore(config['profile']).lookup(request_id=req['request_id'])
    assert row['dispatch_fence']==1 and row['state']=='SUBMITTED'
    from ai_chem_input.provenance import sha256
    receipt=loads((tmp_path/'state/submissions'/row['intent_id']/'dispatch_result.json').read_bytes())
    assert receipt['intent_sha256']==sha256(row['record_json'].encode())


def test_s13_02_03_aliases_and_conflicts(tmp_path):
    req,path,c,_=make_case(tmp_path); fake=FakeScheduler(c['profile'],tmp_path/'fake')
    first=submit(req,str(path),runner=fake); assert first['state']=='SUBMITTED',first
    assert submit(req,str(path),runner=fake)['state']=='EXISTING'
    alias=dict(req,request_id='again',calculation_id='label_alias',bundle_ref='alias')
    again=submit(alias,str(path),runner=fake)
    assert again['state']=='EXISTING' and again['intent_id']==first['intent_id']
    assert len(fake.jobs())==1 and fake.calls.count('qsub')==1
    conflict=dict(req,expected_manifest_sha256='f'*64)
    assert submit(conflict,str(path),runner=fake)['state']=='IDENTITY_CONFLICT'


@pytest.mark.parametrize('point',['before_pending','pending','intent_files','fence','fence_receipt','outcome','receipt','bound'])
def test_s13_06_07_fault_windows(tmp_path,point):
    req,path,c,_=make_case(tmp_path); fake=FakeScheduler(c['profile'],tmp_path/'fake')
    def crash(name):
        if name==point: raise Crash(name)
    with pytest.raises(Crash): submit(req,str(path),runner=fake,fault=crash)
    store=SubmissionStore(c['profile']); row=store.lookup(request_id=req['request_id'])
    if point in ('before_pending','pending','intent_files'):
        assert len(fake.jobs())==0
        response=submit(req,str(path),runner=fake)
        assert response['state']=='SUBMITTED',response
    else:
        before=len(fake.jobs()); response=submit(req,str(path),runner=fake)
        assert len(fake.jobs())==before
        if row and row['state']!='SUBMITTED':
            recovered=reconcile(row['intent_id'],str(path),runner=fake)
            assert recovered['state']==('SUBMISSION_UNCERTAIN' if point in ('fence','fence_receipt') else 'SUBMITTED'),recovered
    assert len(fake.jobs())<=1 and fake.calls.count('qsub')<=1


@pytest.mark.parametrize('accounted',[False,True])
def test_s13_05_08_timeout_acceptance_recovery(tmp_path,accounted):
    req,path,c,_=make_case(tmp_path); fake=FakeScheduler(c['profile'],tmp_path/'fake')
    fake.timeout=True; fake.stdout=b''
    initial=submit(req,str(path),runner=fake)
    assert initial['state']=='SUBMISSION_UNCERTAIN',initial
    fake.mode='accounted' if accounted else 'live'
    recovered=reconcile(initial['intent_id'],str(path),runner=fake)
    assert recovered['state']=='SUBMITTED',recovered
    assert recovered['scheduler_job_id']=='1001'
    assert len(fake.jobs())==1 and fake.calls.count('qsub')==1
    row=SubmissionStore(c['profile']).lookup(intent_id=initial['intent_id'])
    assert bool(row['terminal_observed'])==accounted


def test_s13_05_server_accept_then_controller_crash(tmp_path):
    req,path,c,_=make_case(tmp_path); fake=FakeScheduler(c['profile'],tmp_path/'fake'); fake.crash_accept=True
    with pytest.raises(Crash): submit(req,str(path),runner=fake)
    row=SubmissionStore(c['profile']).lookup(request_id=req['request_id'])
    fake.crash_accept=False
    assert reconcile(row['intent_id'],str(path),runner=fake)['state']=='SUBMITTED'
    assert submit(req,str(path),runner=fake)['state']=='EXISTING'
    assert len(fake.jobs())==1 and fake.calls.count('qsub')==1


@pytest.mark.parametrize('mode,expected',[('delay','SUBMISSION_UNCERTAIN'),('fail','SUBMISSION_UNCERTAIN'),('weak','REVIEW_REQUIRED'),('wrong_manifest','REVIEW_REQUIRED'),('multiple','IDENTITY_CONFLICT')])
def test_s13_08_09_observation_no_resubmission(tmp_path,mode,expected):
    req,path,c,_=make_case(tmp_path); fake=FakeScheduler(c['profile'],tmp_path/'fake'); fake.timeout=True; fake.stdout=b''
    initial=submit(req,str(path),runner=fake); assert initial['state']=='SUBMISSION_UNCERTAIN',initial
    fake.mode=mode
    result=reconcile(initial['intent_id'],str(path),runner=fake)
    assert result['state']==expected,result
    submit(dict(req,request_id='duplicate'),str(path),runner=fake)
    assert fake.calls.count('qsub')==1 and len(fake.jobs())==1


@pytest.mark.parametrize('rc,stdout',[(0,b''),(0,b'Job 12345 submitted'),(0,b'1\n2\n'),(0,b'123.1-5:1'),(1,b'1001\n'),(0,b'0'),(0,b'-12'),(0,b'\xff')])
def test_s13_10_malformed_ack(tmp_path,rc,stdout):
    req,path,c,_=make_case(tmp_path); fake=FakeScheduler(c['profile'],tmp_path/'fake'); fake.rc=rc; fake.stdout=stdout
    response=submit(req,str(path),runner=fake)
    assert response['state']=='SUBMISSION_UNCERTAIN',response
    assert submit(req,str(path),runner=fake)['state']=='SUBMISSION_UNCERTAIN'
    assert fake.calls.count('qsub')==1


def test_definite_spawn_failure_is_never_retried(tmp_path):
    req,path,c,_=make_case(tmp_path); fake=FakeScheduler(c['profile'],tmp_path/'fake'); fake.spawn='SPAWN_FAILED'
    response=submit(req,str(path),runner=fake)
    assert response['state']=='NOT_DISPATCHED',response
    assert not response['dispatched_this_call'] and not fake.jobs()
    submit(req,str(path),runner=fake)
    assert fake.calls.count('qsub')==1


@pytest.mark.parametrize('accounted',[False,True])
def test_s13_07_repeated_reconciliation_keeps_receipt_and_observation_hashes_separate(tmp_path,accounted):
    req,path,c,_=make_case(tmp_path); fake=FakeScheduler(c['profile'],tmp_path/'fake')
    fake.timeout=True; fake.stdout=b''
    first=submit(req,str(path),runner=fake)
    store=SubmissionStore(c['profile'])
    receipt_hash=store.attempt(first['intent_id'])['receipt_sha256']
    fake.mode='accounted' if accounted else 'live'
    for _ in range(3):
        recovered=reconcile(first['intent_id'],str(path),runner=fake)
        assert recovered['state']=='SUBMITTED',recovered
        assert store.attempt(first['intent_id'])['receipt_sha256']==receipt_hash
    assert len(fake.jobs())==1 and fake.calls.count('qsub')==1
