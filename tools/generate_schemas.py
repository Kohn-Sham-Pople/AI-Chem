import json
from pathlib import Path
S={'type':'string','minLength':1}; I={'type':'integer','minimum':1}; B={'type':'boolean'}
ID=dict(S,pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'); H=dict(S,pattern=r'^[0-9a-f]{64}$'); D=dict(S,pattern=r'^-?(0|[1-9][0-9]*)(\.[0-9]*[1-9])?$',format='canonical-decimal'); P=dict(S,pattern=r'^/[^\n\r]*$')
def obj(**p): return {'type':'object','properties':p,'required':list(p),'additionalProperties':False}
def arr(s,n=1): return {'type':'array','items':s,'minItems':n}
def nullable(s): return {'anyOf':[s,{'type':'null'}]}
def enum(*v): return dict(S,enum=list(v))
def mapping(s): return {'type':'object','additionalProperties':s}
ref=obj(id=ID,revision=I); file=obj(size_bytes=I,sha256=H,source_relative_name=S)
approval=obj(reviewer=ID,approved_at=dict(S,pattern=r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$'),note=S)
def entity(**p): return obj(schema_version={'const':1},id=ID,revision=I,approval=approval,**p)
roots=obj(source=arr(P),protected=arr(P),output=P,registry=P,state=P,lock=P)
profile=entity(roots=roots,queue={'const':'all.q'},pe={'const':'mpi_32'},slots={'const':32},user_quota_slots={'const':320},vasp=obj(version={'const':'5.4.4'},path=P,binary_name={'const':'vasp_ncl'}),launcher=obj(path=P,args=arr({'anyOf':[S,obj(token=enum('NSLOTS','EXECUTABLE','SGE_MACHINEFILE'))]})),environment=obj(fragments=arr(obj(id=ID,path=P,sha256=H),0),library_dirs=arr(P,0),thread_vars=obj(OMP_NUM_THREADS=I,MKL_NUM_THREADS=I)),runtime=obj(python_path=P,bash_path={'const':'/bin/bash'},walltime=nullable(dict(S,pattern=r'^[0-9]{1,4}:[0-5][0-9]:[0-5][0-9]$'))),preparation=obj(max_requests={'const':1},budget_seconds=I,copy_chunk_bytes=I,max_source_bytes=I,min_free_bytes=I),discovery=obj(max_depth={'type':'integer','minimum':0,'maximum':3},max_candidates={'type':'integer','minimum':1,'maximum':100},recursive=B))
# Optional at decode time so historical immutable bundle snapshots remain readable.
# New registration/preparation requires both fields via validate_profile.
profile['properties']['environment']['properties']['ld_library_path_policy']=enum('replace','prepend','preserve','unset')
profile['properties']['execution_review']=obj(source_run_sha256=H,source_node_selection=enum('all_q','node127'),target_node_selection={'const':'all_q'},approved_changes=arr(enum('sge_machinefile','ld_library_path_replace','ld_library_path_prepend','ld_library_path_preserve','ld_library_path_unset','node127_to_all_q')),approval=approval)
block=obj(block_id=ID,element=dict(S,pattern=r'^[A-Z][a-z]?$'),count=I,potential_variant=S,dataset_sha256=H)
configuration=obj(configuration_id=ID,structure_id=ID,structure_sha256=H,spin_mode=enum('collinear','noncollinear'),soc=B,saxis=nullable(arr(D)),magmom_by_atom=arr({'anyOf':[obj(atom_index=I,moment=D),obj(atom_index=I,vector=arr(D))]}))
material=entity(formula=S,species_blocks=arr(block),structures=arr(obj(structure_id=ID,sha256=H)),configurations=arr(configuration),u_sets=arr(obj(u_set_id=ID,ldau=B,ldautype=I,by_block=mapping(obj(l={'type':'integer','minimum':-1,'maximum':3},u_eV=D,j_eV=D)))),method=obj(incar_tags=mapping(S),kpoints_sha256=H,potcar_sha256=H,approved_u_set_ids=arr(ID)))
template=entity(material_id=ID,shell_class=enum('f','d'),source_dir=P,files=obj(**{k:file for k in ['INCAR','POSCAR','POTCAR','KPOINTS','run.sh']}),profile=ref,protocol=ref)
protocol=entity(shell_class=enum('f','d'),recipe=enum('open_f_v1','open_d_v1'))
request=obj(schema_version={'const':1},request_id=ID,calculation_id=ID,template=ref,material=ref,cluster_profile=ref,protocol=ref,structure_id=ID,configuration_id=ID,u_set_id=ID,stage_id=ID,restart_evidence_id=nullable(ID))
catalog={'profile':profile,'material':material,'template':template,'protocol':protocol,'request':request,'operator':obj(schema_version={'const':1},registry=P,profile=ref)}
catalog['evidence']=obj(schema_version={'const':1},evidence_id=ID,issuer=ID,issuer_version=S,validation_status={'const':'VALIDATED'},producer_manifest_sha256=H,issued_at=S,result_evidence_refs=arr(H),rule=obj(id=ID,version=S,ediff_pass={'const':True},rmsc_pass={'const':True}),producer_ediff=S,compatibility=obj(shell_class={'const':'f'},calculation_id=ID,stage_id=enum('s01_e4','s02_e5'),method_hash=H,configuration_hash=H,structure_sha256=H,potcar_sha256=H,u_set_id=ID,lmaxmix={'const':6},lcharg={'const':True}),chgcar=obj(path=P,size_bytes=I,sha256=H))
file_meta=obj(size_bytes={'type':'integer','minimum':0},sha256=H)
source_meta=obj(size_bytes=I,sha256=H,source_alias=S,snapshot_relative_path=S)
identity=obj(request_id=ID,calculation_id=ID,stage_id=ID,protocol=ref)
refs=obj(template=ref,material=ref,cluster_profile=ref,protocol=ref,structure_id=ID,configuration_id=ID,u_set_id=ID)
restart_ref=obj(path=P,size_bytes=I,sha256=H,evidence_id=ID,evidence_hash=H)
catalog['ready']=obj(schema_version={'const':1},calculation_id=ID,stage_id=ID,request_digest=H,manifest_sha256=H)
catalog['manifest']=obj(schema_version={'const':1},hash_schema_version={'const':1},generator_version=S,identity=identity,resolved_refs=refs,
 source_files=obj(**{k:source_meta for k in ['INCAR','POSCAR','POTCAR','KPOINTS','run.sh']}),generated_files=mapping(file_meta),payload_files=mapping(file_meta),
 resource_request=obj(queue={'const':'all.q'},pe={'const':'mpi_32'},slots={'const':32},quota_static={'const':320},live_checked={'const':False}),
 science_identity=obj(method_hash=H,configuration_hash=H,stage_input_hash=H),restart=nullable(restart_ref),
 validation=obj(result={'const':'INPUT_VALIDATED'},input_only={'const':True},issues=arr(obj(code=ID),0)),
 generation=obj(created_at=S,actor=ID,request_digest=H,bundle_payload_hash=H))
catalog['result']=obj(schema_version={'const':1},request_id=nullable(ID),calculation_id=nullable(ID),stage_id=nullable(ID),result=S,committed=B,issue_codes=arr(ID,0),request_digest=nullable(H),bundle_path=nullable(P))
for folder in [Path('schemas'),Path('src/ai_chem_input/schemas')]:
 folder.mkdir(exist_ok=True)
 for name,s in catalog.items(): (folder/(name+'.json')).write_text(json.dumps(dict(s,**{'$schema':'https://json-schema.org/draft/2020-12/schema','$id':'ai-chem-v1-'+name}),indent=2)+'\n')
# Drafts are documentation and are deliberately never accepted by prepare.
def draft(schema):
    out=dict(schema)
    if 'properties' in out: out['properties']={k:draft(v) for k,v in out['properties'].items()}
    if 'items' in out: out['items']=draft(out['items'])
    return {'anyOf':[out,{'type':'null'}]}
for name in ('profile','material','template','protocol'):
    Path('schemas',name+'.draft.schema.json').write_text(json.dumps(draft(catalog[name]),indent=2)+'\n')
