"""Additive submission-only schemas. Does not regenerate Step 1-2 contracts."""
import json
from pathlib import Path
S={'type':'string','minLength':1}; B={'type':'boolean'}; I={'type':'integer','minimum':1}
ID=dict(S,pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'); H=dict(S,pattern=r'^[0-9a-f]{64}$'); P=dict(S,pattern=r'^/[^\r\n]*$')
def obj(**p): return dict(type='object',properties=p,required=list(p),additionalProperties=False)
def arr(s,n=0): return dict(type='array',items=s,minItems=n,maxItems=1000)
def enum(*v): return dict(S,enum=list(v))
def null(s): return {'anyOf':[s,{'type':'null'}]}
def mapping(s): return dict(type='object',additionalProperties=s)
ref=obj(id=ID,revision=I); pin=obj(path=P,sha256=H)
approval=obj(reviewer=ID,approved_at=S,note=S)
roots=obj(source=arr(P,1),protected=arr(P,1),output=P,registry=P,state=P,lock=P)
request=obj(schema_version={'const':1},request_id=ID,calculation_id=ID,stage_id=ID,bundle_ref=ID,expected_manifest_sha256=H,submission_profile=ref)
env=obj(SGE_ROOT=P,SGE_CELL=ID,PATH=P,HOME=P)
# Ports are explicit optional typed values; no general environment/extra-args map.
for name in ('SGE_QMASTER_PORT','SGE_EXECD_PORT'): env['properties'][name]=dict(S,pattern=r'^[0-9]{1,5}$')
profile=obj(schema_version={'const':1},id=ID,revision=I,approval=approval,cluster_id=ID,cluster_epoch=ID,state_epoch=H,
 expected_owner=obj(uid={'type':'integer','minimum':0},name=ID),qmaster_aliases=arr(dict(S,pattern=r'^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$'),1),cluster_timezone=enum('UTC','Asia/Seoul'),
 qsub_path=P,qstat_path=P,qacct_path=P,dialect={'const':'sge_xml_v1'},sge_client_env=env,
 queue={'const':'all.q'},pe={'const':'mpi_32'},slots={'const':32},user_quota_slots={'const':320},
 scheduler_rqs_evidence=null(pin),dialect_evidence=null(pin),effective_execution_evidence=null(pin),live_authorization=null(pin),
 queue_pending_policy=enum('single_job_pilot','unknown'),max_outstanding_controller_runs={'const':1},live_enabled=B,
 snapshot_max_age_seconds={'type':'integer','minimum':1,'maximum':5},qsub_timeout_seconds={'type':'integer','minimum':1,'maximum':15},query_timeout_seconds={'type':'integer','minimum':1,'maximum':5},
 reconcile_grace_seconds=I,reconcile_max_observations=I,worker_budget_seconds={'type':'integer','minimum':20,'maximum':300},max_new_submissions={'const':1},max_queries={'type':'integer','minimum':1,'maximum':1000},paused=B,paused_restore=B,roots=roots)
profile['properties']['site_options']=obj(project=null(ID),account=null(ID),walltime=null(dict(S,pattern=r'^[0-9]{1,4}:[0-5][0-9]:[0-5][0-9]$')))
profile['properties']['live_enabled']['default']=False
profile['required'].remove('live_enabled')  # Loader default is false, never true.
config=obj(schema_version={'const':1},profile=profile,bundle_refs=mapping(P))
proof_base=dict(schema_version={'const':1},cluster_id=ID,cluster_epoch=ID,owner=ID,approval=approval)
rqs=obj(**dict(proof_base,kind={'const':'rqs'},hard_cap={'const':320},pending_included={'const':True}))
dialect=obj(**dict(proof_base,kind={'const':'dialect'},dialect={'const':'sge_xml_v1'},client_version=S,job_name_max_length={'type':'integer','minimum':35,'maximum':1024},all_active_states={'const':True},requested_upper_slots={'const':True},full_name_accounting={'const':True},cli_clear_supported={'const':True},client_paths_sha256=H,qmaster_aliases=arr(dict(S,pattern=r'^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$'),1)))
effective=obj(**dict(proof_base,kind={'const':'effective_execution'},script_sha256=H,command_policy_sha256=H,client_env_sha256=H,
 defaults_reviewed={'const':True},local_precedence_pilot={'const':True},runtime_environment_equivalent={'const':True},approved_changes=arr(enum('export_all_removed','node_selection_removed','queue_overridden','name_overridden','shell_overridden','cwd_overridden','rerun_overridden','stdout_overridden','join_overridden')),evidence_digest=H))
authorization=obj(**dict(proof_base,kind={'const':'live_authorization'},mode={'const':'single_job_pilot'},profile_sha256=H))
result=obj(schema_version={'const':1},operation=S,request_id=null(ID),calculation_id=null(ID),calculation_key=null(H),stage_id=null(ID),intent_id=null(ID),run_instance_id=null(S),state=S,committed=B,dispatched_this_call=B,dispatch_allowed=B,scheduler_job_id=null(dict(S,pattern=r'^[1-9][0-9]*$')),live_admission=S,issue_codes=arr(ID),review_required=B)
result['properties']['planned_argv']=arr(S); result['properties']['execution_blockers']=arr(ID); result['properties']['execution_changes']=arr(ID)
stream=obj(size_bytes={'type':'integer','minimum':0,'maximum':1048576},sha256=H)
receipt=obj(schema_version={'const':1},intent_id=ID,run_instance_id=S,token=dict(S,pattern=r'^[0-9a-f]{32}$'),cluster_id=ID,cluster_epoch=ID,owner=ID,request_digest=H,intent_sha256=H,command_digest=H,cwd_digest=H,manifest_sha256=H,
 started_at=dict(S,pattern=r'^[0-9]+(?:\.[0-9]+)?$'),finished_at=dict(S,pattern=r'^[0-9]+(?:\.[0-9]+)?$'),spawn_status=enum('SPAWN_FAILED','PROCESS_STARTED','SPAWN_UNKNOWN'),returncode=null({'type':'integer'}),signal=null(I),timed_out=B,output_overflow=B,stdout=stream,stderr=stream,parsed_job_id=null(dict(S,pattern=r'^[1-9][0-9]*$')))
catalog=dict(dispatch_result=receipt,request=request,profile=profile,config=config,rqs=rqs,dialect=dialect,effective_execution=effective,live_authorization=authorization,result=result)
for folder in (Path('schemas/submission_v1'),Path('src/ai_chem_input/submission/schemas')):
 folder.mkdir(parents=True,exist_ok=True)
 for name,value in catalog.items():
  (folder/(name+'.json')).write_text(json.dumps(dict(value,**{'$schema':'https://json-schema.org/draft/2020-12/schema'}),indent=2)+'\n')
