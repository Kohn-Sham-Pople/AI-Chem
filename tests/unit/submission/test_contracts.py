import copy
import json
import time
from pathlib import Path
import pytest
from submission_support import make_case,FakeScheduler
from support import tree
from ai_chem_input.config import loads
from ai_chem_input.provenance import canonical
from ai_chem_input.errors import InputError
from ai_chem_input.submission.models import checked,DispatchOutcome,SchedulerSnapshot
from ai_chem_input.submission.sge import parse_qsub,parse_qstat,parse_detail,parse_accounting,upper_slots,build_qsub
from ai_chem_input.submission.admission import check_admission
from ai_chem_input.submission.preflight import build_submission_plan,execution_report
from ai_chem_input.submission.identity import derive_calculation_key
from ai_chem_input.submission.service import submit


@pytest.mark.parametrize('stdout,rc,expected',[(b'12345\n',0,'12345'),(b' \t12345\r\n',0,'12345'),(b'',0,None),(b'Job 12345 submitted',0,None),(b'1\n2',0,None),(b'12345.1-10:1',0,None),(b'12345',1,None),(b'-12',0,None),(b'0',0,None),(b'\xef\xbb\xbf12345',0,None),(b'12345\0',0,None),(b'\xff',0,None)])
def test_s13_10_strict_terse_parser(stdout,rc,expected):
    assert parse_qsub(DispatchOutcome('PROCESS_STARTED',rc,stdout=stdout,stderr=b'warning'))==expected


@pytest.mark.parametrize('raw',['{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}'])
def test_json_loader_is_strict(raw):
    with pytest.raises(InputError): loads(raw)


@pytest.mark.parametrize('change',[lambda r:r.update(unexpected=True),lambda r:r.update(request_id='../escape'),lambda r:r.update(schema_version=2),lambda r:r.update(bundle_ref='<LOCAL_VALUE>'),lambda r:r.update(submission_profile={'id':'profile','revision':0})])
def test_submit_request_schema_rejects_injection(tmp_path,change):
    req,_,_,_=make_case(tmp_path); change(req)
    with pytest.raises(InputError): checked(req,'request')


def test_s13_02_science_and_transport_keys(tmp_path):
    req,path,c,bundle=make_case(tmp_path)
    before=tree(tmp_path); original=build_submission_plan(req,str(path))
    alias=build_submission_plan(dict(req,request_id='redelivery',calculation_id='alias',bundle_ref='alias'),str(path))
    assert original.request_digest==alias.request_digest and original.calculation_key==alias.calculation_key
    assert original.bundle_key==alias.bundle_key and tree(tmp_path)==before
    for field in ('method_hash','configuration_hash','stage_input_hash'):
        manifest=loads(original.bundle.manifest_json); manifest['science_identity'][field]='f'*64
        from dataclasses import replace
        altered=replace(original.bundle,manifest_json=canonical(manifest))
        assert derive_calculation_key(altered)!=original.calculation_key


@pytest.mark.parametrize('shell,change',[('f','node_selection_removed'),('d','export_all_removed')])
def test_s13_15_effective_precedence_needs_explicit_local_approval(tmp_path,shell,change):
    req,path,c,_=make_case(tmp_path,shell=shell)
    plan=build_submission_plan(req,str(path)); report=execution_report(plan.bundle,c['profile'])
    assert change in report['changes'] and not report['blockers']
    c['profile']['effective_execution_evidence']=None; path.write_bytes(canonical(c))
    fake=FakeScheduler(c['profile'],tmp_path/'fake'); before=tree(tmp_path/'research')
    response=submit(req,str(path),runner=fake)
    assert response['state']=='ADMISSION_BLOCKED' and not fake.calls and not fake.jobs()
    assert tree(tmp_path/'research')==before
    # The supplied script keeps its original -V/node bytes; no compiler/MPI run.
    assert b'#$ -V' in (Path(plan.bundle.path)/'run.sh').read_bytes()
    assert not (Path(c['profile']['roots']['state'])/'submissions').exists()


def test_default_live_false_and_exact_command(tmp_path):
    req,path,c,bundle=make_case(tmp_path,live=False); c['profile'].pop('live_enabled'); path.write_bytes(canonical(c))
    result=submit(req,str(path)); assert result['issue_codes']==['LIVE_DISABLED']
    spec=build_qsub(c['profile'],str(bundle),req['expected_manifest_sha256'],'a'*32)
    assert list(spec.argv[1:5])==['-clear','-terse','-b','n']
    assert spec.argv[-1]=='./run.sh' and '-V' not in spec.argv and '-@' not in spec.argv
    assert spec.cwd==str(bundle) and dict(spec.env)['LC_ALL']=='C'
    assert 'LD_LIBRARY_PATH' not in dict(spec.env)


@pytest.mark.parametrize('slots,ok',[(288,True),(289,False),(320,False)])
def test_s13_11_user_wide_slot_boundary(tmp_path,slots,ok):
    _,_,c,_=make_case(tmp_path); p=c['profile']; now=time.time()
    snap=SchedulerSnapshot(p['cluster_id'],p['cluster_epoch'],p['expected_owner']['name'],now,True,
        (dict(job_id='1',owner=p['expected_owner']['name'],slots=slots,token=None),))
    if ok: assert check_admission(snap,[],p,now=now)['S_seen']==288
    else:
        with pytest.raises(InputError): check_admission(snap,[],p,now=now)


def test_s13_12_reservation_dedup_and_candidate_once(tmp_path):
    _,_,c,_=make_case(tmp_path); p=copy.deepcopy(c['profile']); p['max_outstanding_controller_runs']=2
    now=time.time(); job=dict(job_id='1',owner=p['expected_owner']['name'],slots=32,token='a'*32)
    snap=SchedulerSnapshot(p['cluster_id'],p['cluster_epoch'],p['expected_owner']['name'],now,True,(job,))
    reservation=dict(intent_id='old',state='SUBMITTED',token='a'*32,slots=32,terminal_observed=0)
    candidate=dict(intent_id='candidate',state='SUBMIT_PENDING',token='b'*32,slots=32,terminal_observed=0)
    decision=check_admission(snap,[reservation,candidate],p,'candidate',now)
    assert (decision['S_seen'],decision['S_unseen'],decision['requested'])==(32,0,32)
    reservation['token']='c'*32
    assert check_admission(snap,[reservation],p,now=now)['S_unseen']==32


@pytest.mark.parametrize('raw',[b'<job_info version="other"/>',b'<job_info xmlns="unknown"/>',b'<!DOCTYPE job_info [<!ENTITY x "bad">]><job_info/>',b'<job_info>'])
def test_unknown_or_unsafe_xml_is_not_an_empty_snapshot(raw):
    with pytest.raises(InputError): parse_qstat(raw,'owner')


@pytest.mark.parametrize('raw',['1-32','32'])
def test_requested_upper_bound(raw): assert upper_slots(raw)==32

@pytest.mark.parametrize('raw',['unknown','32-1','1-inf','0','1,4','1-32:2'])
def test_unsupported_slot_ranges_block(raw):
    with pytest.raises(InputError): upper_slots(raw)


def test_s13_12_accounting_pe_rows_group_one_job():
    data=b'====\njobnumber 12345\njobname ac_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\nowner owner\nqsub_time 1700000000\ngranted_pe mpi_32\nslots 32\npe_taskid NONE\n====\njobnumber 12345\njobname ac_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\nowner owner\nqsub_time 1700000000\ngranted_pe mpi_32\nslots 1\npe_taskid 1\n'
    records=parse_accounting(data)
    assert len(records)==1 and records[0]['slots']==32


def test_detail_fields_and_exact_identity_are_not_loose_number_search():
    data=b'job_number: 12345\njob_name: ac_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\nowner: owner\nsge_o_workdir: /synthetic/output\nenv_list: AI_CHEM_RUN_TOKEN=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,AI_CHEM_MANIFEST_SHA256='+b'b'*64+b'\nsubmission_time: 1700000000\nparallel environment: mpi_32 range: 1-32\n'
    record=parse_detail(data)
    assert record['slots']==32 and record['pe']=='mpi_32' and record['token']=='a'*32


def test_hand_authored_sge_fixtures():
    folder=Path('tests/fixtures/sge_synthetic')
    for case in loads((folder/'qsub_cases.json').read_bytes()):
        outcome=DispatchOutcome('PROCESS_STARTED',case['returncode'],stdout=case['stdout'].encode(),stderr=case['stderr'].encode())
        assert parse_qsub(outcome)==case['job_id'],case['name']
    jobs=parse_qstat((folder/'qstat_states.xml').read_bytes(),'synthetic_owner')
    assert len(jobs)==6 and next(j for j in jobs if j['job_id']=='2')['slots']==24
    assert parse_detail((folder/'qstat_detail.txt').read_bytes())['slots']==32
    assert len(parse_accounting((folder/'qacct_pe_rows.txt').read_bytes()))==1


@pytest.mark.parametrize('xml',[
    b'<job_info>'+b'<nested>'*17+b'</nested>'*17+b'</job_info>',
    b'<job_info><queue_info><job_list><JB_job_number>1</JB_job_number></job_list></queue_info></job_info>',
    b'<job_info><queue_info><job_list><JB_job_number>1</JB_job_number><JB_name>array</JB_name><JB_owner>owner</JB_owner><state>qw</state><slots>1</slots><tasks>1-10</tasks></job_list></queue_info></job_info>'
])
def test_partial_deep_or_array_xml_blocks(xml):
    with pytest.raises(InputError): parse_qstat(xml,'owner')


@pytest.mark.parametrize('complete,age',[(False,0),(True,6),(True,-1)])
def test_s13_11_partial_stale_or_future_snapshot_blocks(tmp_path,complete,age):
    _,_,c,_=make_case(tmp_path); p=c['profile']; now=time.time()
    snap=SchedulerSnapshot(p['cluster_id'],p['cluster_epoch'],p['expected_owner']['name'],now-age,complete,())
    with pytest.raises(InputError): check_admission(snap,[],p,now=now)


def test_site_mandatory_options_are_typed_and_unknown_options_cannot_be_injected(tmp_path):
    req,path,c,bundle=make_case(tmp_path); p=c['profile']
    p['site_options']=dict(project='synthetic_project',account='synthetic_account',walltime='01:00:00')
    checked(p,'profile')
    argv=build_qsub(p,str(bundle),req['expected_manifest_sha256'],'a'*32).argv
    assert argv[-7:]==('-P','synthetic_project','-A','synthetic_account','-l','h_rt=01:00:00','./run.sh')
    p['site_options']['arbitrary']=['-V']
    with pytest.raises(InputError): checked(p,'profile')


@pytest.mark.parametrize('field',['template','generator','stage','potcar','kpoints','vasp'])
def test_identity_includes_versions_revisions_and_potential_structure_inputs(tmp_path,field):
    from dataclasses import replace
    req,path,_,_=make_case(tmp_path); plan=build_submission_plan(req,str(path))
    manifest=loads(plan.bundle.manifest_json); resolved=loads(plan.bundle.resolved_json)
    if field=='template': manifest['resolved_refs']['template']['revision']+=1
    elif field=='generator': manifest['generator_version']='different_generator'
    elif field=='stage': manifest['identity']['stage_id']='different_stage'
    elif field=='potcar': manifest['generated_files']['POTCAR']['sha256']='f'*64
    elif field=='kpoints': manifest['generated_files']['KPOINTS']['sha256']='f'*64
    else: resolved['profile']['vasp']['version']='different_version'
    changed=replace(plan.bundle,manifest_json=canonical(manifest),resolved_json=canonical(resolved))
    assert derive_calculation_key(changed)!=plan.calculation_key


def test_accounting_timestamp_and_live_env_mismatch_cannot_bind(tmp_path):
    from ai_chem_input.submission.reconcile import strong_candidate
    from ai_chem_input.submission.store import SubmissionStore
    req,path,c,_=make_case(tmp_path); plan=build_submission_plan(req,str(path))
    store=SubmissionStore(c['profile']); row=store.create_or_get_intent(plan); row['armed_at']=time.time()
    candidate=dict(job_id='1',name='ac_'+row['token'],owner=row['owner'],pe='mpi_32',slots=32,
        qsub_time=row['armed_at'],terminal=False,token=row['token'],manifest=req['expected_manifest_sha256'],cwd=plan.bundle.path)
    assert strong_candidate(candidate,row,time.time())
    for key,value in [('qsub_time',row['armed_at']-121),('owner','other'),('cwd','/SYNTHETIC/wrong'),('manifest','f'*64)]:
        altered=dict(candidate); altered[key]=value
        assert not strong_candidate(altered,row,time.time())


@pytest.mark.parametrize('raw',[
    b'<job_info/>',
    b'<job_info><error>permission denied</error></job_info>',
    b'<job_info><queue_info><error>partial result</error></queue_info></job_info>',
    '<!DOCTYPE job_info [<!ENTITY x "expanded">]><job_info><queue_info>&x;</queue_info></job_info>'.encode('utf-16'),
])
def test_s13_11_incomplete_or_alternate_encoding_xml_is_never_zero_usage(raw):
    with pytest.raises(InputError): parse_qstat(raw,'owner')


def test_s13_11_xml_element_count_is_bounded_during_parse():
    raw=b'<job_info><queue_info>'+b'<job_list/>'*100001+b'</queue_info></job_info>'
    with pytest.raises(InputError) as exc: parse_qstat(raw,'owner')
    assert exc.value.code=='SGE_XML_UNSAFE'
