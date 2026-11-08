import copy
import multiprocessing
import sqlite3
import subprocess
import time
from dataclasses import replace
from pathlib import Path
import pytest
from submission_support import make_case,FakeScheduler,Crash
from support import tree
from ai_chem_input.config import loads
from ai_chem_input.provenance import canonical
from ai_chem_input.errors import InputError
from ai_chem_input.state import global_lock
from ai_chem_input.submission.models import checked
from ai_chem_input.submission.preflight import build_submission_plan
from ai_chem_input.submission.service import submit,reconcile
from ai_chem_input.submission.store import SubmissionStore
from ai_chem_input.submission.receipts import publish
from ai_chem_input.submission.cli import main
from ai_chem_input.submission.worker import once


def test_s13_14_strict_dry_run_no_writes_queries_tokens_or_lock(tmp_path,monkeypatch,capsys):
    req,path,c,bundle=make_case(tmp_path,live=False)
    # Include an entirely missing submission/preparation DB: planning never creates it.
    db=tmp_path/'state/preparations.sqlite3'; db.unlink()
    request_path=tmp_path/'request.json'; request_path.write_bytes(canonical(req))
    before=tree(tmp_path)
    def forbidden(*args,**kwargs): raise AssertionError('write/process/token/SQLite forbidden')
    monkeypatch.setattr(subprocess,'Popen',forbidden)
    monkeypatch.setattr(sqlite3,'connect',forbidden)
    import ai_chem_input.submission.store as module
    monkeypatch.setattr(module.secrets,'token_hex',forbidden)
    monkeypatch.setattr(module.uuid,'uuid4',forbidden)
    import ai_chem_input.submission.service as svc
    monkeypatch.setattr(svc,'global_lock',forbidden)
    response=submit(req,str(path),dry_run=True)
    assert response['state']=='DRY_RUN_VALID',response
    assert not response['committed'] and not response['dispatched_this_call'] and not response['dispatch_allowed']
    assert response['live_admission']=='NOT_CHECKED'
    checked(response,'result')
    assert main(['submit','--config',str(path),'--request',str(request_path),'--dry-run'])==0
    assert loads(capsys.readouterr().out)['state']=='DRY_RUN_VALID'
    assert tree(tmp_path)==before


@pytest.mark.parametrize('bad',['tamper','used','unmanifested_chgcar','symlink','manifest'])
def test_s13_04_integrity_used_directory_no_dispatch(tmp_path,bad):
    req,path,c,bundle=make_case(tmp_path); fake=FakeScheduler(c['profile'],tmp_path/'fake')
    if bad=='tamper': (bundle/'INCAR').write_bytes((bundle/'INCAR').read_bytes()+b'! altered\n')
    elif bad=='used': (bundle/'OUTCAR').write_bytes(b'SYNTHETIC TEST ONLY')
    elif bad=='unmanifested_chgcar': (bundle/'CHGCAR').write_bytes(b'SYNTHETIC TEST ONLY')
    elif bad=='symlink': (bundle/'extra').symlink_to(tmp_path/'request')
    else: req['expected_manifest_sha256']='f'*64
    before=tree(tmp_path/'research'); response=submit(req,str(path),runner=fake)
    assert response['state']=='INPUT_REJECTED',response
    assert not fake.calls and not fake.jobs() and tree(tmp_path/'research')==before
    assert not (tmp_path/'state/submissions').exists()


@pytest.mark.parametrize('gate',['rqs','dialect','effective','authorization','paused','restore','owner'])
def test_live_gates_are_fail_closed(tmp_path,gate):
    req,path,c,_=make_case(tmp_path)
    fields={'rqs':'scheduler_rqs_evidence','dialect':'dialect_evidence','effective':'effective_execution_evidence','authorization':'live_authorization'}
    if gate in fields: c['profile'][fields[gate]]=None
    elif gate=='paused': c['profile']['paused']=True
    elif gate=='restore': c['profile']['paused_restore']=True
    else: c['profile']['expected_owner']['uid']+=1
    path.write_bytes(canonical(c)); fake=FakeScheduler(c['profile'],tmp_path/'fake')
    response=submit(req,str(path),runner=fake)
    assert response['state'] in ('ADMISSION_BLOCKED','REVIEW_REQUIRED'),response
    assert not fake.calls and not fake.jobs()
    assert not (tmp_path/'state/submissions').exists()


def test_s13_13_fence_commit_unknown_never_returns_second_permit(tmp_path,monkeypatch):
    req,path,c,_=make_case(tmp_path); fake=FakeScheduler(c['profile'],tmp_path/'fake')
    original=SubmissionStore.arm_dispatch
    def ambiguous(self,*args,**kwargs):
        original(self,*args,**kwargs)
        raise sqlite3.OperationalError('synthetic lost commit acknowledgment')
    monkeypatch.setattr(SubmissionStore,'arm_dispatch',ambiguous)
    response=submit(req,str(path),runner=fake)
    assert response['state']=='SUBMISSION_UNCERTAIN',response
    assert not fake.jobs() and fake.calls.count('qsub')==0
    monkeypatch.setattr(SubmissionStore,'arm_dispatch',original)
    for _ in range(2): assert submit(req,str(path),runner=fake)['state']=='SUBMISSION_UNCERTAIN'
    assert not fake.jobs() and fake.calls.count('qsub')==0


def test_s13_07_receipt_recovers_after_db_bind_failure(tmp_path,monkeypatch):
    req,path,c,_=make_case(tmp_path); fake=FakeScheduler(c['profile'],tmp_path/'fake')
    original=SubmissionStore.transition
    def fail(*args,**kwargs): raise sqlite3.OperationalError('synthetic DB unavailable')
    monkeypatch.setattr(SubmissionStore,'transition',fail)
    response=submit(req,str(path),runner=fake)
    assert response['state']=='SUBMISSION_UNCERTAIN'
    monkeypatch.setattr(SubmissionStore,'transition',original)
    recovered=reconcile(response['intent_id'],str(path),runner=fake)
    assert recovered['state']=='SUBMITTED' and fake.calls.count('qsub')==1


def test_s13_13_two_process_writers_and_common_lock(tmp_path):
    req,path,c,_=make_case(tmp_path); server=tmp_path/'fake'; server.mkdir()
    ctx=multiprocessing.get_context('fork'); barrier=ctx.Barrier(2); queue=ctx.Queue()
    def writer():
        barrier.wait(); queue.put(submit(req,str(path),runner=FakeScheduler(c['profile'],server)))
    workers=[ctx.Process(target=writer) for _ in range(2)]
    for p in workers: p.start()
    for p in workers: p.join(15); assert p.exitcode==0
    responses=[queue.get(timeout=2) for _ in workers]
    assert any(r['state']=='SUBMITTED' for r in responses),responses
    assert len(FakeScheduler(c['profile'],server).jobs())==1
    with global_lock(c['profile']['roots']['lock']):
        assert submit(req,str(path),runner=FakeScheduler(c['profile'],server))['state']=='BUSY'


def test_s13_18_restore_orphan_and_epoch_block(tmp_path):
    req,path,c,_=make_case(tmp_path); fake=FakeScheduler(c['profile'],tmp_path/'fake')
    first=submit(req,str(path),runner=fake); assert first['state']=='SUBMITTED'
    rogue=tmp_path/'state/submissions/orphan'; rogue.mkdir()
    assert submit(req,str(path),runner=fake)['state']=='REVIEW_REQUIRED'
    rogue.rmdir()
    c['profile']['cluster_epoch']='epoch2'; path.write_bytes(canonical(c))
    assert submit(dict(req,request_id='new_request'),str(path),runner=fake)['state']=='REVIEW_REQUIRED'
    c['profile']['cluster_epoch']='epoch1'; path.write_bytes(canonical(c))
    # Restore a pre-fence DB while durable dispatch ledger/receipt still exist.
    db=sqlite3.connect(str(tmp_path/'state/preparations.sqlite3'))
    db.execute('UPDATE submission_intents SET dispatch_fence=0'); db.commit(); db.close()
    assert submit(req,str(path),runner=fake)['state']=='REVIEW_REQUIRED'
    assert len(fake.jobs())==1 and fake.calls.count('qsub')==1


def test_s13_18_db_removed_with_external_anchor_cannot_reinitialize(tmp_path):
    req,path,c,_=make_case(tmp_path); fake=FakeScheduler(c['profile'],tmp_path/'fake')
    submit(req,str(path),runner=fake)
    (tmp_path/'state/preparations.sqlite3').unlink()
    result=submit(dict(req,request_id='other'),str(path),runner=fake)
    assert result['state']=='REVIEW_REQUIRED' and len(fake.jobs())==1
    assert not (tmp_path/'state/preparations.sqlite3').exists()


def test_s13_08_grace_expiry_is_not_nonacceptance(tmp_path):
    req,path,c,_=make_case(tmp_path); fake=FakeScheduler(c['profile'],tmp_path/'fake'); fake.timeout=True; fake.stdout=b''
    response=submit(req,str(path),runner=fake); fake.mode='delay'
    db=sqlite3.connect(str(tmp_path/'state/preparations.sqlite3'))
    db.execute('UPDATE submission_intents SET armed_at=?',(time.time()-400,)); db.commit(); db.close()
    # Receipt's timestamp still passes the conservative armed-time comparison.
    response=reconcile(response['intent_id'],str(path),runner=fake)
    assert response['state']=='REVIEW_REQUIRED' and fake.calls.count('qsub')==1
    assert submit(req,str(path),runner=fake)['state']=='REVIEW_REQUIRED'


def test_receipt_exclusive_same_content_and_conflict(tmp_path):
    path=tmp_path/'private/receipt.json'
    first=publish(path,b'one'); before=tree(tmp_path)
    assert publish(path,b'one')==first and tree(tmp_path)==before
    with pytest.raises(InputError): publish(path,b'two')
    assert path.read_bytes()==b'one'


def test_preparation_rows_never_change(tmp_path):
    req,path,c,_=make_case(tmp_path); fake=FakeScheduler(c['profile'],tmp_path/'fake')
    database=tmp_path/'state/preparations.sqlite3'
    def rows():
        con=sqlite3.connect(str(database))
        try: return {t:con.execute('SELECT * FROM '+t).fetchall() for t in ('schema_meta','preparations','attempts','preparation_events')}
        finally: con.close()
    before=rows(); submit(req,str(path),runner=fake)
    assert rows()==before


def test_worker_recovery_precedes_new_inbox_and_preserves_malformed(tmp_path):
    req,path,c,_=make_case(tmp_path); fake=FakeScheduler(c['profile'],tmp_path/'fake')
    state=tmp_path/'state'; inbox=state/'submission_inbox'; inbox.mkdir(mode=0o700)
    (inbox/'01.json').write_bytes(b'{')
    (inbox/'02.json').write_bytes(canonical(req))
    assert once(str(path),runner=fake)['state']=='INVALID_REQUEST'
    assert once(str(path),runner=fake)['state']=='SUBMITTED'
    assert fake.calls.count('qsub')==1 and len(list((state/'submission_archive').glob('*/request.json')))==2
    assert (inbox/'02.json').exists() is False


def test_s13_03_scientific_duplicate_in_new_physical_bundle_is_blocked(tmp_path):
    from ai_chem_input.registry import Registry
    from ai_chem_input.prepare import build_plan,materialize,verify_bundle
    req,path,c,bundle=make_case(tmp_path); fake=FakeScheduler(c['profile'],tmp_path/'fake')
    assert submit(req,str(path),runner=fake)['state']=='SUBMITTED'
    preparation=loads((bundle/'provenance/resolved_request.json').read_bytes())
    preparation.update(request_id='new_preparation',calculation_id='new_label')
    plan=build_plan((preparation,Registry(c['profile']['roots']['registry'])))
    materialize(plan); other=Path(plan.final_dir)
    c['bundle_refs']['second']=str(other); path.write_bytes(canonical(c))
    changed=dict(req,request_id='second_submit',calculation_id='new_label',bundle_ref='second',expected_manifest_sha256=verify_bundle(other)['manifest_sha256'])
    response=submit(changed,str(path),runner=fake)
    assert response['state']=='IDENTITY_CONFLICT',response
    assert fake.calls.count('qsub')==1 and len(fake.jobs())==1


def test_s13_03_same_physical_bundle_cannot_get_a_new_manifest_run(tmp_path):
    from ai_chem_input.provenance import sha256
    req,path,c,bundle=make_case(tmp_path); fake=FakeScheduler(c['profile'],tmp_path/'fake')
    submit(req,str(path),runner=fake)
    manifest_path=bundle/'provenance/manifest.json'; manifest=loads(manifest_path.read_bytes()); manifest['generation']['created_at']='changed'
    manifest_path.write_bytes(canonical(manifest)); ready=loads((bundle/'READY.json').read_bytes())
    ready['manifest_sha256']=sha256(manifest_path.read_bytes()); (bundle/'READY.json').write_bytes(canonical(ready))
    changed=dict(req,request_id='new_transport',expected_manifest_sha256=ready['manifest_sha256'])
    assert submit(changed,str(path),runner=fake)['state']=='IDENTITY_CONFLICT'
    assert fake.calls.count('qsub')==1


def test_token_collision_is_a_blocker_not_a_token_retry(tmp_path,monkeypatch):
    from ai_chem_input.submission.preflight import build_submission_plan
    import ai_chem_input.submission.store as module
    req,path,c,_=make_case(tmp_path); store=SubmissionStore(c['profile'])
    calls=[]
    def collision(_): calls.append(1); return 'c'*32
    monkeypatch.setattr(module.secrets,'token_hex',collision)
    first=build_submission_plan(req,str(path)); store.create_or_get_intent(first)
    other_request=dict(req,request_id='other',calculation_id='other_label')
    other=replace(first,request_json=canonical(other_request),calculation_key='b'*64,bundle_key='d'*64,request_digest='e'*64)
    with pytest.raises(InputError) as exc: store.create_or_get_intent(other)
    assert exc.value.code=='IDENTITY_COLLISION' and len(calls)==2
    assert len(store.all_intents())==1


def test_s13_13_cas_rollback_and_command_bound_permit(tmp_path):
    from dataclasses import asdict
    from ai_chem_input.submission.preflight import build_submission_plan
    from ai_chem_input.submission.sge import build_qsub,command_digest
    req,path,c,_=make_case(tmp_path); store=SubmissionStore(c['profile'])
    plan=build_submission_plan(req,str(path)); row=store.create_or_get_intent(plan)
    command=build_qsub(c['profile'],plan.bundle.path,plan.bundle.manifest_sha256,row['token'])
    with pytest.raises(InputError): store.arm_dispatch(row['intent_id'],999,canonical(asdict(command)).decode(),command_digest(command),{})
    assert store.lookup(intent_id=row['intent_id'])['dispatch_fence']==0 and store.attempt(row['intent_id']) is None
    permit=store.arm_dispatch(row['intent_id'],0,canonical(asdict(command)).decode(),command_digest(command),{})
    fake=FakeScheduler(c['profile'],tmp_path/'fake')
    with pytest.raises(InputError): fake.dispatch(permit,replace(command,cwd=str(tmp_path)))
    assert not fake.jobs()
    fake.dispatch(permit,command)
    with pytest.raises(InputError): fake.dispatch(permit,command)
    assert len(fake.jobs())==1


def test_s13_07_receipt_write_failure_still_never_resubmits(tmp_path,monkeypatch):
    import ai_chem_input.submission.service as svc
    req,path,c,_=make_case(tmp_path); fake=FakeScheduler(c['profile'],tmp_path/'fake')
    def disk_full(*a,**kw): raise OSError(28,'SYNTHETIC ENOSPC')
    monkeypatch.setattr(svc,'persist_outcome',disk_full)
    response=submit(req,str(path),runner=fake)
    assert response['state']=='SUBMISSION_UNCERTAIN'
    assert reconcile(response['intent_id'],str(path),runner=fake)['state']=='SUBMITTED'
    assert submit(req,str(path),runner=fake)['state']=='EXISTING'
    assert fake.calls.count('qsub')==1


def test_receipt_tampering_requires_review_not_loose_job_id_recovery(tmp_path):
    req,path,c,_=make_case(tmp_path); fake=FakeScheduler(c['profile'],tmp_path/'fake'); fake.timeout=True; fake.stdout=b''
    response=submit(req,str(path),runner=fake)
    receipt=tmp_path/'state/submissions'/response['intent_id']/'dispatch_result.json'
    value=loads(receipt.read_bytes()); value['parsed_job_id']='1001'; receipt.write_bytes(canonical(value))
    assert reconcile(response['intent_id'],str(path),runner=fake)['state']=='REVIEW_REQUIRED'
    assert fake.calls.count('qsub')==1


def test_worker_unarmed_pending_resumes_same_token(tmp_path):
    req,path,c,_=make_case(tmp_path); fake=FakeScheduler(c['profile'],tmp_path/'fake')
    def crash(point):
        if point=='pending': raise Crash(point)
    with pytest.raises(Crash): submit(req,str(path),runner=fake,fault=crash)
    before=SubmissionStore(c['profile']).lookup(request_id=req['request_id'])
    response=once(str(path),runner=fake)
    assert response['state']=='SUBMITTED' and response['intent_id']==before['intent_id']
    assert SubmissionStore(c['profile']).lookup(request_id=req['request_id'])['token']==before['token']
    assert fake.calls.count('qsub')==1


def test_s13_18_profile_revision_drift_does_not_silently_redefine_intent(tmp_path):
    req,path,c,_=make_case(tmp_path); fake=FakeScheduler(c['profile'],tmp_path/'fake')
    submit(req,str(path),runner=fake)
    c['profile']['approval']['note']='different content in same immutable revision'
    path.write_bytes(canonical(c))
    assert submit(dict(req,request_id='again'),str(path),runner=fake)['state']=='IDENTITY_CONFLICT'
    assert fake.calls.count('qsub')==1


def test_restore_pause_allows_explicit_reconcile_but_never_new_dispatch(tmp_path):
    req,path,c,_=make_case(tmp_path); fake=FakeScheduler(c['profile'],tmp_path/'fake'); fake.timeout=True; fake.stdout=b''
    response=submit(req,str(path),runner=fake)
    (tmp_path/'state/paused_restore').write_bytes(b'operator pause')
    assert submit(req,str(path),runner=fake)['state']=='REVIEW_REQUIRED'
    recovered=reconcile(response['intent_id'],str(path),runner=fake)
    assert recovered['state']=='SUBMITTED'
    assert submit(req,str(path),runner=fake)['state']=='REVIEW_REQUIRED'
    assert fake.calls.count('qsub')==1


def test_restarted_client_object_uses_only_durable_server_state(tmp_path):
    req,path,c,_=make_case(tmp_path); server=tmp_path/'fake'; first=FakeScheduler(c['profile'],server); first.crash_accept=True
    with pytest.raises(Crash): submit(req,str(path),runner=first)
    row=SubmissionStore(c['profile']).lookup(request_id=req['request_id'])
    restarted=FakeScheduler(c['profile'],server)
    assert reconcile(row['intent_id'],str(path),runner=restarted)['state']=='SUBMITTED'
    assert len(restarted.jobs())==1 and restarted.calls.count('qsub')==0 and first.calls.count('qsub')==1


@pytest.mark.parametrize('operation',['submit','reconcile'])
def test_qmaster_change_blocks_client_execution(tmp_path,operation):
    req,path,c,_=make_case(tmp_path); fake=FakeScheduler(c['profile'],tmp_path/'fake')
    if operation=='reconcile':
        fake.timeout=True; fake.stdout=b''
        first=submit(req,str(path),runner=fake)
    master=Path(c['profile']['sge_client_env']['SGE_ROOT'])/'default/common/act_qmaster'
    master.write_text('other-cluster\n'); calls=list(fake.calls)
    response=submit(req,str(path),runner=fake) if operation=='submit' else reconcile(first['intent_id'],str(path),runner=fake)
    assert response['state']=='ADMISSION_BLOCKED'
    assert response['issue_codes']==['QMASTER_IDENTITY_MISMATCH']
    assert fake.calls==calls


def test_help_is_process_and_state_free(tmp_path,monkeypatch,capsys):
    def forbidden(*args,**kwargs): raise AssertionError('help must not execute/write')
    monkeypatch.setattr(subprocess,'Popen',forbidden)
    monkeypatch.setattr(sqlite3,'connect',forbidden)
    with pytest.raises(SystemExit) as exc: main(['--help'])
    assert exc.value.code==0
    assert 'submit' in capsys.readouterr().out
    assert not list(tmp_path.iterdir())


def test_s13_07_parent_fsync_failure_after_receipt_publish_is_recoverable(tmp_path,monkeypatch):
    req,path,c,_=make_case(tmp_path); fake=FakeScheduler(c['profile'],tmp_path/'fake')
    import ai_chem_input.submission.receipts as receipts
    original=receipts.fsync_dir
    def fail(path):
        if (Path(path)/'dispatch_result.json').exists():
            raise OSError('synthetic parent fsync failure')
        return original(path)
    monkeypatch.setattr(receipts,'fsync_dir',fail)
    first=submit(req,str(path),runner=fake)
    assert first['state']=='SUBMISSION_UNCERTAIN' and first['committed']
    monkeypatch.setattr(receipts,'fsync_dir',original)
    assert reconcile(first['intent_id'],str(path),runner=fake)['state']=='SUBMITTED'
    assert fake.calls.count('qsub')==1 and len(fake.jobs())==1
