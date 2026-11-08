"""Independent durable fake scheduler and explicitly synthetic local approvals."""
import copy
import os
import pwd
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from support import setup
from ai_chem_input.discovery import inventory
from ai_chem_input.prepare import build_plan,materialize,verify_bundle
from ai_chem_input.provenance import canonical,sha256,digest
from ai_chem_input.config import loads
from ai_chem_input.submission.models import DispatchOutcome
from ai_chem_input.submission.runner import BoundedRunner
from ai_chem_input.submission.preflight import execution_report,profile_authorization_hash,build_submission_plan


class Crash(BaseException): pass


def make_case(root,live=True,shell='d',cluster_timezone='UTC'):
    request,reg,e=setup(root,shell)
    source=Path(e['template']['source_dir'])
    data=(Path('tests/fixtures/synthetic')/('preserve_'+shell+'.sh.txt')).read_bytes()
    (source/'run.sh').write_bytes(data)
    p=copy.deepcopy(e['profile']); p.update(revision=2,run_script_mode='preserve_source')
    for key in ('launcher','environment','execution_review'): p.pop(key)
    p['source_script_approval']=dict(source_run_sha256=sha256(data),approval=p['approval'])
    reg.register('profile',p,sha256(canonical(p)))
    t=copy.deepcopy(e['template']); t.update(revision=2,files=inventory(source)['files']); t['profile']['revision']=2
    reg.register('template',t,sha256(canonical(t)))
    request['template']['revision']=request['cluster_profile']['revision']=2
    plan=build_plan((request,reg)); materialize(plan)
    bundle=Path(plan.final_dir); verified=verify_bundle(bundle)
    clients=root/'sge_clients'; clients.mkdir()
    for kind in ('qsub','qstat','qacct'):
        path=clients/kind; path.write_bytes(b'SYNTHETIC TEST ONLY -- NEVER EXECUTE'); path.chmod(0o700)
    sge_root=root/'sge_root'; (sge_root/'default/common').mkdir(parents=True)
    (sge_root/'default/common/act_qmaster').write_text('synthetic-master\n')
    owner=pwd.getpwuid(os.geteuid()).pw_name
    profile=dict(schema_version=1,id='synthetic_submission',revision=1,approval=copy.deepcopy(p['approval']),
      cluster_id='synthetic_cluster',cluster_epoch='epoch1',state_epoch='a'*64,
      expected_owner=dict(uid=os.geteuid(),name=owner),qmaster_aliases=['synthetic-master'],cluster_timezone=cluster_timezone,
      qsub_path=str(clients/'qsub'),qstat_path=str(clients/'qstat'),qacct_path=str(clients/'qacct'),dialect='sge_xml_v1',
      sge_client_env=dict(SGE_ROOT=str(sge_root),SGE_CELL='default',PATH='/usr/bin:/bin',HOME=os.environ['HOME']),
      queue='all.q',pe='mpi_32',slots=32,user_quota_slots=320,scheduler_rqs_evidence=None,dialect_evidence=None,
      effective_execution_evidence=None,live_authorization=None,queue_pending_policy='single_job_pilot',
      max_outstanding_controller_runs=1,live_enabled=live,snapshot_max_age_seconds=5,qsub_timeout_seconds=1,
      query_timeout_seconds=1,reconcile_grace_seconds=300,reconcile_max_observations=10,
      worker_budget_seconds=45,max_new_submissions=1,max_queries=100,paused=False,paused_restore=False,roots=p['roots'])
    config=dict(schema_version=1,profile=profile,bundle_refs=dict(bundle=str(bundle),alias=str(bundle)))
    submit_req=dict(schema_version=1,request_id='submit1',calculation_id=request['calculation_id'],stage_id=request['stage_id'],
      bundle_ref='bundle',expected_manifest_sha256=verified['manifest_sha256'],submission_profile=dict(id=profile['id'],revision=1))
    config_path=root/'submission.json'
    def pin(field,kind,value):
        document=dict(schema_version=1,kind=kind,cluster_id=profile['cluster_id'],cluster_epoch=profile['cluster_epoch'],owner=owner,approval=copy.deepcopy(profile['approval']),**value)
        path=root/(field+'.json'); path.write_bytes(canonical(document)); profile[field]=dict(path=str(path),sha256=sha256(path.read_bytes()))
    pin('scheduler_rqs_evidence','rqs',dict(hard_cap=320,pending_included=True))
    pin('dialect_evidence','dialect',dict(dialect='sge_xml_v1',client_version='SYNTHETIC_TEST_ONLY',job_name_max_length=80,all_active_states=True,requested_upper_slots=True,full_name_accounting=True,
        cli_clear_supported=True,client_paths_sha256=digest('sge-paths-v1',{k:profile[k+'_path'] for k in ('qsub','qstat','qacct')}),qmaster_aliases=profile['qmaster_aliases']))
    config_path.write_bytes(canonical(config)); planned=build_submission_plan(submit_req,str(config_path))
    report=execution_report(planned.bundle,profile)
    pin('effective_execution_evidence','effective_execution',dict(script_sha256=report['script_sha256'],command_policy_sha256=report['command_policy_sha256'],
        client_env_sha256=report['client_env_sha256'],defaults_reviewed=True,local_precedence_pilot=True,runtime_environment_equivalent=True,
        approved_changes=report['changes'],evidence_digest='e'*64))
    pin('live_authorization','live_authorization',dict(mode='single_job_pilot',profile_sha256=profile_authorization_hash(profile)))
    config_path.write_bytes(canonical(config))
    return submit_req,config_path,config,bundle


class FakeScheduler(BoundedRunner):
    def __init__(self,profile,root):
        super().__init__(profile); self.root=Path(root); self.root.mkdir(exist_ok=True)
        self.profile=profile; self.mode='live'; self.rc=0; self.stdout=None; self.stderr=b''
        self.timeout=False; self.overflow=False; self.spawn='PROCESS_STARTED'; self.crash_accept=False; self.calls=[]; self.manual=[]
    def jobs(self):
        path=self.root/'accepted.json'; return loads(path.read_bytes()) if path.exists() else []
    def write_jobs(self,jobs): (self.root/'accepted.json').write_bytes(canonical(jobs))
    def _run(self,spec,deadline=None):
        self.calls.append(spec.kind); now=time.time(); args=list(spec.argv)
        if spec.kind=='qsub':
            if self.spawn=='SPAWN_FAILED': return DispatchOutcome(self.spawn,None,started_at=now,finished_at=now)
            jobs=self.jobs(); job_id=str(1001+len(jobs)); variables=dict(x.split('=',1) for x in args[args.index('-v')+1].split(','))
            job=dict(job_id=job_id,name=args[args.index('-N')+1],owner=self.profile['expected_owner']['name'],cwd=spec.cwd,
                token=variables['AI_CHEM_RUN_TOKEN'],manifest=variables['AI_CHEM_MANIFEST_SHA256'],pe='mpi_32',slots=32,qsub_time=now)
            jobs.append(job); self.write_jobs(jobs)
            if self.crash_accept: raise Crash('synthetic server accepted before client response')
            return DispatchOutcome(self.spawn,self.rc,self.timeout,self.overflow,
                self.stdout if self.stdout is not None else (job_id+'\n').encode(),self.stderr,now,time.time())
        if self.mode=='fail': return DispatchOutcome('PROCESS_STARTED',1,stderr=b'SYNTHETIC permission failure',started_at=now,finished_at=now)
        jobs=copy.deepcopy(self.jobs()+self.manual)
        if self.mode=='weak':
            for j in jobs: j['name']=j['name'][:20]
        if self.mode=='wrong_manifest':
            for j in jobs: j['manifest']='f'*64
        if self.mode=='multiple' and jobs:
            duplicate=copy.deepcopy(jobs[0]); duplicate['job_id']='9999'; jobs.append(duplicate)
        output=b''
        if spec.kind=='qstat' and '-xml' in args:
            xml=ET.Element('job_info'); group=ET.SubElement(xml,'queue_info')
            if self.mode not in ('delay','accounted'):
                for j in jobs:
                    node=ET.SubElement(group,'job_list',state='running')
                    for key,value in dict(JB_job_number=j['job_id'],JB_name=j['name'],JB_owner=j['owner'],state='r',slots=str(j['slots']),pe_range=str(j['slots'])).items():
                        ET.SubElement(node,key).text=value
            output=ET.tostring(xml)
        elif spec.kind=='qstat':
            matches=[j for j in jobs if j['job_id']==args[-1]]
            if matches:
                j=matches[0]
                output=('job_number: {job_id}\njob_name: {name}\nowner: {owner}\nsge_o_workdir: {cwd}\nsubmission_time: {qsub_time}\nparallel environment: {pe} range: {slots}\n'.format(**j)+
                    'env_list: AI_CHEM_RUN_TOKEN='+j['token']+',AI_CHEM_MANIFEST_SHA256='+j['manifest']+'\n').encode()
        elif spec.kind=='qacct' and self.mode in ('accounted','weak','multiple'):
            rows=[]
            for j in jobs:
                base='jobnumber {job_id}\njobname {name}\nowner {owner}\nqsub_time {qsub_time}\ngranted_pe {pe}\nslots {slots}\n'.format(**j)
                rows.append('====\n'+base+'pe_taskid NONE\ntaskid undefined\n')
                if self.mode=='accounted': rows.append('====\n'+base.replace('slots 32','slots 1')+'pe_taskid 1\ntaskid undefined\n')
            output=''.join(rows).encode()
        return DispatchOutcome('PROCESS_STARTED',0,stdout=output,started_at=now,finished_at=time.time())
