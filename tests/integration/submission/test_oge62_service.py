"""Exercise the approved profile timezone through real service call paths."""
import datetime
import os
import re
from dataclasses import replace
from zoneinfo import ZoneInfo

import pytest

from submission_support import make_case,FakeScheduler
from ai_chem_input.submission.admission import snapshot
from ai_chem_input.submission.service import submit,reconcile
from ai_chem_input.submission.store import SubmissionStore
from ai_chem_input.submission.reconcile import strong_candidate
from ai_chem_input.config import loads


class OgeScheduler(FakeScheduler):
    def _run(self,spec,deadline=None):
        outcome=super()._run(spec,deadline)
        if spec.kind=='qstat' and '-j' in spec.argv:
            pattern=rb'(submission_time: )([0-9.]+)'
        elif spec.kind=='qacct':
            pattern=rb'(qsub_time )([0-9.]+)'
        else: return outcome
        def date(match):
            # datetime.ctime has fixed English tokens; independent of our parser.
            text=datetime.datetime.fromtimestamp(float(match[2]),ZoneInfo('Asia/Seoul')).ctime()
            return match[1]+text.encode('ascii')
        output=re.sub(pattern,date,outcome.stdout)
        if spec.kind=='qacct' and output:
            # A single OGE summary record: taskid=undefined, no pe_taskid.
            output=b'====\n'+output.split(b'====\n')[1].replace(b'pe_taskid NONE\n',b'')
        return replace(outcome,stdout=output)


@pytest.mark.parametrize('accounted',[False,True])
def test_oge_timeout_recovery_uses_pinned_kst_and_never_resubmits(tmp_path,accounted):
    req,path,c,bundle=make_case(tmp_path,cluster_timezone='Asia/Seoul')
    fake=OgeScheduler(c['profile'],tmp_path/'fake'); fake.timeout=True; fake.stdout=b''
    initial=submit(req,str(path),runner=fake)
    assert initial['state']=='SUBMISSION_UNCERTAIN',initial
    store=SubmissionStore(c['profile']); original=store.lookup(intent_id=initial['intent_id'])
    fake.mode='accounted' if accounted else 'live'
    recovered=reconcile(initial['intent_id'],str(path),runner=fake)
    assert recovered['state']=='SUBMITTED',recovered
    row=store.lookup(intent_id=initial['intent_id'])
    assert row['token']==original['token'] and row['run_instance_id']==original['run_instance_id']
    assert row['dispatch_fence']==1 and bool(row['terminal_observed'])==accounted
    assert recovered['scheduler_job_id']=='1001'
    assert submit(req,str(path),runner=fake)['state']=='EXISTING'
    assert fake.calls.count('qsub')==1 and len(fake.jobs())==1


def test_oge_admission_snapshot_uses_cluster_timezone(tmp_path):
    req,path,c,bundle=make_case(tmp_path,cluster_timezone='Asia/Seoul')
    fake=OgeScheduler(c['profile'],tmp_path/'fake')
    # Use the synthetic service once; then query that durable fake job, read-only.
    submitted=submit(req,str(path),runner=fake)
    assert submitted['state']=='SUBMITTED',submitted
    observed=snapshot(c['profile'],fake,str(bundle))
    assert len(observed.jobs)==1 and observed.jobs[0]['slots']==32
    assert observed.jobs[0]['qsub_time']==int(fake.jobs()[0]['qsub_time'])


@pytest.mark.parametrize('variable',['SGE_ROOT','SGE_CELL'])
def test_hpc_variable_isolation_does_not_relax_production_cluster_gate(tmp_path,monkeypatch,variable):
    assert 'SGE_ROOT' not in os.environ and 'SGE_CELL' not in os.environ
    req,path,c,_=make_case(tmp_path)
    fake=FakeScheduler(c['profile'],tmp_path/'fake')
    monkeypatch.setenv(variable,'unapproved-cluster')
    result=submit(req,str(path),runner=fake)
    assert result['state']=='ADMISSION_BLOCKED' and result['issue_codes']==['CLUSTER_MISMATCH']
    assert not fake.calls


@pytest.mark.parametrize('changed,value',[
    ('owner','other_owner'),('name','ac_'+'f'*32),('pe','other_pe'),('slots',1),
    ('qsub_time',1794153000.0),('manifest','f'*64),('cwd','/SYNTHETIC/wrong'),
])
def test_oge_dates_do_not_bypass_identity_postfilters(tmp_path,changed,value):
    from pathlib import Path
    from ai_chem_input.submission.sge import parse_detail
    from ai_chem_input.submission.preflight import build_submission_plan
    req,path,c,_=make_case(tmp_path,cluster_timezone='Asia/Seoul')
    store=SubmissionStore(c['profile']); row=store.create_or_get_intent(build_submission_plan(req,str(path)))
    row['armed_at']=1794153162.0
    record=loads(row['record_json'])
    candidate=parse_detail(Path('tests/fixtures/sge_synthetic/oge_6_2u7_qstat_detail.txt').read_bytes(),'Asia/Seoul')
    candidate.update(owner=row['owner'],name='ac_'+row['token'],token=row['token'],manifest=record['manifest_sha256'],cwd=record['bundle_path'])
    assert strong_candidate(candidate,row,1794153163.0)
    candidate[changed]=value
    assert not strong_candidate(candidate,row,1794153163.0)
