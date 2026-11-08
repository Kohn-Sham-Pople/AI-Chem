"""Pure immutable plan, revalidation, private staging and single-writer publication."""
import os
import shutil
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path, PurePosixPath
from .config import checked, loads
from .errors import require, InputError, result
from .paths import (inspect, read_small, open_read, safe_path, write_new, private_dir,
                    fsync_dir, deadline_check)
from .discovery import FILES
from .incar import parse_incar, patch_incar
from .poscar import parse_poscar
from .potcar import inspect_potcar
from .provenance import canonical, sha256, digest, text_diff
from .protocols import protocol_patches, CONTROLLED, MATERIAL_TAGS
from .validators import material_mapping, validate_inputs, check_method, check_spin, semantic_tag_value
from .restart import RestartEvidenceProvider, consume
from .registry import resolve_request
from .script import prepare_run_script, run_script_mode, validate_profile
from .state import StateStore, global_lock


@dataclass(frozen=True)
class CopyDescriptor:
    name: str
    path: str
    size_bytes: int
    sha256: str
    @property
    def expected(self): return dict(size_bytes=self.size_bytes,sha256=self.sha256)


@dataclass(frozen=True)
class PreparationPlan:
    request_json: bytes
    config_json: bytes
    config_pins: tuple
    sources: tuple
    generated: tuple
    restart: object
    semantic_json: bytes
    science_json: bytes
    request_digest: str
    final_dir: str
    evidence_provider: object = None
    issues: tuple = ()


def build_plan(context,provider=None,deadline=None):
    # context is (request, Registry), so resolution cannot be skipped by CLI callers.
    request,registry=context
    entities,pins=resolve_request(request,registry)
    t,m,p=entities['template'],entities['material'],entities['profile']
    validate_profile(p)
    for root_name in ('output','registry','state','lock'):
        rp=Path(p['roots'][root_name])
        if rp.exists():
            require(rp.is_dir() and rp.stat().st_uid==os.getuid() and rp.stat().st_mode & 0o077==0,'PATH_OWNERSHIP')
    limits=p['preparation']; source=Path(t['source_dir']); descriptors=[]; small={}
    for name in FILES:
        deadline_check(deadline)
        meta=inspect(source/name,t['files'][name],limit=limits['max_source_bytes'],deadline=deadline)
        descriptors.append(CopyDescriptor(name,str(source/name),**meta))
        if name!='POTCAR':
            small[name]=read_small(source/name)
            require(sha256(small[name])==meta['sha256'],'SOURCE_CHANGED')
    with open_read(source/'POTCAR') as f: potentials=inspect_potcar(f,deadline)
    # Source hash after metadata parsing prevents mixed source snapshots.
    inspect(source/'POTCAR',t['files']['POTCAR'],deadline=deadline)
    require(t['files']['POTCAR']['sha256']==m['method']['potcar_sha256'],'POTENTIAL_MISMATCH')
    structure=parse_poscar(small['POSCAR'],[b['element'] for b in m['species_blocks']])
    config,uset,patches=material_mapping(m,request,structure,potentials)
    doc=parse_incar(small['INCAR']); check_method(m,doc.tags); check_spin(config,doc.tags)
    patches+=protocol_patches(t['shell_class'],request['stage_id'])
    small['INCAR']=patch_incar(doc,patches)
    validation_context=dict(entities,request=request,potentials=potentials)
    validate_inputs(validation_context,small)
    method_spec=dict(m['method'],incar_tags={k:semantic_tag_value(k,v) for k,v in m['method']['incar_tags'].items()})
    method_hash=digest('method',dict(method=method_spec,potentials=[asdict(v) for v in potentials],u_set=uset,
                                    spin={k:config[k] for k in ('spin_mode','soc','saxis')},vasp=p['vasp']['version']))
    config_hash=digest('configuration',dict(configuration=config,blocks=m['species_blocks'],material_revision=m['revision']))
    compatibility=dict(shell_class=t['shell_class'],method_hash=method_hash,configuration_hash=config_hash,
                       structure_sha256=config['structure_sha256'],potcar_sha256=m['method']['potcar_sha256'],u_set_id=uset['u_set_id'])
    restart=consume(provider or RestartEvidenceProvider(),request,compatibility,structure,p['roots']['protected'])
    intent={k:v for k,v in request.items() if k!='request_id'}
    request_digest=digest('request',dict(request=intent,entities=entities,restart=asdict(restart) if restart else None))
    final=Path(p['roots']['output'])/request['calculation_id']/request['stage_id']
    small['run.sh']=prepare_run_script(p,small['run.sh'],final,request_digest)
    changes=[]
    after=parse_incar(small['INCAR']).tags
    for tag in sorted(set(doc.tags)|set(after)):
        if doc.tags.get(tag)!=after.get(tag):
            changes.append(dict(tag=tag,old=doc.tags.get(tag),new=after.get(tag),action='REMOVE' if tag not in after else 'SET',
                                layer='protocol' if tag in CONTROLLED else 'material',reason='registered stage rule' if tag in CONTROLLED else 'approved atom/block mapping'))
    science=dict(method_hash=method_hash,configuration_hash=config_hash,
                 stage_input_hash=digest('stage',dict(files={k:sha256(v) for k,v in small.items() if k!='run.sh'},potcar=m['method']['potcar_sha256'],
                                                      protocol=request['protocol'],stage=request['stage_id'],restart=asdict(restart) if restart else None)))
    return PreparationPlan(canonical(request),canonical(entities),pins,tuple(descriptors),tuple(sorted(small.items())),restart,
                           canonical(changes),canonical(science),request_digest,str(final),provider if restart else None)


def revalidate(plan,deadline=None):
    entities=loads(plan.config_json); validate_profile(entities['profile'])
    for path,hash_value in plan.config_pins:
        require(inspect(path,deadline=deadline)['sha256']==hash_value,'CONFIG_CHANGED')
    for source in plan.sources: inspect(source.path,source.expected,deadline=deadline)
    if plan.restart:
        inspect(plan.restart.path,asdict(plan.restart),deadline=deadline)
        require(plan.evidence_provider is not None,'RESTART_UNTRUSTED',exit_code=4)
        record=plan.evidence_provider.get(plan.restart.evidence_id)
        require(digest('evidence',record)==plan.restart.evidence_hash,'RESTART_UNTRUSTED',exit_code=4)
    return entities


def safe_relative(value):
    require(isinstance(value,str) and value and '\\' not in value,'PACKAGE_TAMPERED')
    p=PurePosixPath(value)
    require(not p.is_absolute() and '..' not in p.parts and '.' not in p.parts and str(p)==value,'PACKAGE_TAMPERED')
    return p


REQUIRED_METADATA=('provenance/resolved_request.json','provenance/resolved_config.json','provenance/input.diff',
                   'provenance/parameter_changes.json','provenance/validation.json')


def verify_bundle(bundle_dir,deadline=None):
    root=safe_path(bundle_dir)
    ready=checked(loads(read_small(root/'READY.json')),'ready')
    require(set(ready)=={'schema_version','calculation_id','stage_id','request_digest','manifest_sha256'} and ready['schema_version']==1,'PACKAGE_TAMPERED')
    manifest_bytes=read_small(root/'provenance/manifest.json'); require(sha256(manifest_bytes)==ready['manifest_sha256'],'PACKAGE_TAMPERED')
    m=checked(loads(manifest_bytes),'manifest')
    require(m['schema_version']==1 and m['validation']['result']=='INPUT_VALIDATED' and m['validation']['input_only'] is True,'PACKAGE_TAMPERED')
    for key in ('calculation_id','stage_id'): require(m['identity'][key]==ready[key],'PACKAGE_TAMPERED')
    require(m['generation']['request_digest']==ready['request_digest'],'PACKAGE_TAMPERED')
    require(m['resource_request']==dict(queue='all.q',pe='mpi_32',slots=32,quota_static=320,live_checked=False),'PACKAGE_TAMPERED')
    payload=m['payload_files']; required=set(FILES)|{'provenance/source/'+n for n in FILES}|set(REQUIRED_METADATA)
    if m['restart'] is not None: required.add('CHGCAR')
    require(required==set(payload),'PACKAGE_TAMPERED')
    for relative,expected in payload.items():
        safe_relative(relative); require(relative not in ('READY.json','provenance/manifest.json'),'PACKAGE_TAMPERED')
        require(inspect(root/relative,deadline=deadline)==expected,'PACKAGE_TAMPERED')
    require(digest('payload',payload)==m['generation']['bundle_payload_hash'],'PACKAGE_TAMPERED')
    require(set(m['generated_files'])==set(FILES)|({'CHGCAR'} if m['restart'] else set()),'PACKAGE_TAMPERED')
    for name,meta in m['generated_files'].items(): require(payload[name]==meta,'PACKAGE_TAMPERED')
    for name,meta in m['source_files'].items():
        require(name in FILES and meta['snapshot_relative_path']=='provenance/source/'+name,'PACKAGE_TAMPERED')
        require(payload['provenance/source/'+name]=={k:meta[k] for k in ('size_bytes','sha256')},'PACKAGE_TAMPERED')
    request=checked(loads(read_small(root/'provenance/resolved_request.json')),'request')
    entities=loads(read_small(root/'provenance/resolved_config.json'))
    for kind in ('template','material','profile','protocol'): checked(entities[kind],kind)
    require(set(m['source_files'])==set(FILES),'PACKAGE_TAMPERED')
    for name in FILES:
        meta=entities['template']['files'][name]
        require(payload['provenance/source/'+name]=={k:meta[k] for k in ('size_bytes','sha256')},'PACKAGE_TAMPERED')
    for name in ('POSCAR','POTCAR','KPOINTS'):
        require(payload[name]==payload['provenance/source/'+name],'PACKAGE_TAMPERED')
    script_mode=run_script_mode(entities['profile'])
    source_sha=payload['provenance/source/run.sh']['sha256']
    generated_sha=payload['run.sh']['sha256']
    expected_script=dict(mode=script_mode,source_sha256=source_sha,generated_sha256=generated_sha,
                         byte_identical=source_sha==generated_sha,
                         resource_validation='profile_declared_only' if script_mode=='preserve_source' else 'typed_static')
    if 'run_script' in m:
        require(m['run_script']==expected_script,'PACKAGE_TAMPERED')
    if script_mode=='preserve_source':
        from .registry import validate_template_profile
        validate_template_profile(entities['template'],entities['profile'])
        require(m.get('run_script')==expected_script and source_sha==generated_sha,'PACKAGE_TAMPERED')
    require(request['calculation_id']==ready['calculation_id'] and request['stage_id']==ready['stage_id'],'PACKAGE_TAMPERED')
    intent={k:v for k,v in request.items() if k!='request_id'}
    require(digest('request',dict(request=intent,entities=entities,restart=m['restart']))==ready['request_digest'],'PACKAGE_TAMPERED')
    expected_stage=digest('stage',dict(files={n:payload[n]['sha256'] for n in ('INCAR','POSCAR','KPOINTS')},potcar=payload['POTCAR']['sha256'],
                                      protocol=request['protocol'],stage=request['stage_id'],restart=m['restart']))
    require(m['science_identity']['stage_input_hash']==expected_stage,'PACKAGE_TAMPERED')
    # Verify scientific file consistency without dereferencing original source paths.
    with open_read(root/'POTCAR') as f: potentials=inspect_potcar(f,deadline)
    validate_inputs(dict(entities,request=request,potentials=potentials),{n:read_small(root/n) for n in FILES if n!='POTCAR'})
    return dict(manifest_sha256=ready['manifest_sha256'],request_digest=ready['request_digest'],
                manifest=m,run_script=expected_script)


def materialize(plan,state=None,locked=False,fault=None,deadline=None):
    entities=revalidate(plan,deadline); p=entities['profile']; request=loads(plan.request_json)
    if not locked:
        with global_lock(p['roots']['lock']):
            return materialize(plan,state,True,fault,deadline)
    state=state or StateStore(p['roots']['state']); final=Path(plan.final_dir)
    row=state.lookup(request)
    require(row is None or row['request_digest']==plan.request_digest,'IDENTITY_CONFLICT',exit_code=7)
    if final.exists():
        require(row is None or row['state']!='QUARANTINED','PACKAGE_TAMPERED',exit_code=5)
        try: verified=verify_bundle(final)
        except (OSError,KeyError,ValueError,InputError):
            if row: state.quarantine(request,'PACKAGE_TAMPERED')
            raise InputError('PACKAGE_TAMPERED',exit_code=5) from None
        require(verified['request_digest']==plan.request_digest,'IDENTITY_CONFLICT',exit_code=7)
        if row is not None and row['state']=='INPUT_READY' and row['manifest_sha256']!=verified['manifest_sha256']:
            state.quarantine(request,'PACKAGE_TAMPERED')
            raise InputError('PACKAGE_TAMPERED',exit_code=5)
        require(row is not None,'ORPHAN_FINAL',exit_code=5)
        if row['state']!='INPUT_READY': state.ready(request,verified['manifest_sha256'])
        return result(request,'IDEMPOTENT_EXISTING',digest=plan.request_digest,bundle=final)
    if row is not None and row['state'] in ('INPUT_READY','QUARANTINED'):
        state.quarantine(request,'PACKAGE_TAMPERED')
        raise InputError('PACKAGE_TAMPERED',exit_code=5)
    out=private_dir(p['roots']['output']); private_dir(final.parent)
    needed=sum(s.size_bytes*2 for s in plan.sources)+(plan.restart.size_bytes if plan.restart else 0)+1024*1024
    require(shutil.disk_usage(out).free>=needed+p['preparation']['min_free_bytes'],'DISK_FULL',exit_code=5)
    attempt=uuid.uuid4().hex; state.intent(request,plan.request_digest,attempt)
    def point(name):
        deadline_check(deadline)
        if fault: fault(name)
    point('intent')
    staging_root=private_dir(out/'.staging'); staging=staging_root/attempt; staging.mkdir(mode=0o700)
    private_dir(staging/'provenance/source')
    limits=p['preparation']; copy_kw=dict(limit=limits['max_source_bytes'],chunk=limits['copy_chunk_bytes'],deadline=deadline)
    for source in plan.sources:
        write_new(staging/'provenance/source'/source.name,source=source.path,expected=source.expected,**copy_kw)
        point('snapshot:'+source.name)
    generated=dict(plan.generated)
    for name in FILES:
        if name in generated: write_new(staging/name,generated[name],executable=name=='run.sh')
        else:
            source=next(s for s in plan.sources if s.name==name)
            write_new(staging/name,source=source.path,expected=source.expected,**copy_kw)
        point('input:'+name)
    if plan.restart: write_new(staging/'CHGCAR',source=plan.restart.path,expected=asdict(plan.restart),**copy_kw)
    diff=''
    for name in ('INCAR','run.sh'):
        if name=='run.sh' and run_script_mode(p)=='preserve_source':
            source=next(s for s in plan.sources if s.name==name)
            diff+='run.sh SAME=true mode=preserve_source sha256='+source.sha256+'\n'
        else:
            diff+=text_diff(name,read_small(staging/'provenance/source'/name),generated[name])
    for name in ('POSCAR','POTCAR','KPOINTS'):
        source=next(s for s in plan.sources if s.name==name); diff+=name+' SAME=true sha256='+source.sha256+'\n'
    metadata={'provenance/resolved_request.json':plan.request_json,'provenance/resolved_config.json':plan.config_json,
              'provenance/input.diff':diff.encode(),'provenance/parameter_changes.json':plan.semantic_json,
              'provenance/validation.json':canonical(dict(result='INPUT_VALIDATED',input_only=True,issues=[]))}
    for relative,data in metadata.items(): write_new(staging/relative,data); point(relative)
    revalidate(plan,deadline)
    with open_read(staging/'POTCAR') as f: potentials=inspect_potcar(f,deadline)
    validate_inputs(dict(entities,request=request,potentials=potentials),{n:read_small(staging/n) for n in FILES if n!='POTCAR'})
    names=set(FILES)|set(metadata)|{'provenance/source/'+n for n in FILES}
    if plan.restart: names.add('CHGCAR')
    payload={n:inspect(staging/n,deadline=deadline) for n in sorted(names)}
    for source in plan.sources:
        require(payload['provenance/source/'+source.name]==source.expected,'SOURCE_CHANGED')
    for name,data in generated.items():
        require(payload[name]==dict(size_bytes=len(data),sha256=sha256(data)),'PACKAGE_TAMPERED')
    require(payload['POTCAR']==next(s.expected for s in plan.sources if s.name=='POTCAR'),'POTENTIAL_MISMATCH')
    if plan.restart:
        require(payload['CHGCAR']==dict(size_bytes=plan.restart.size_bytes,sha256=plan.restart.sha256),'RESTART_INCOMPATIBLE',exit_code=4)
    manifest=dict(schema_version=1,hash_schema_version=1,generator_version='0.1.0',
                  identity={k:request[k] for k in ('request_id','calculation_id','stage_id','protocol')},
                  resolved_refs={k:request[k] for k in ('template','material','cluster_profile','protocol','structure_id','configuration_id','u_set_id')},
                  source_files={s.name:dict(s.expected,source_alias=s.name,snapshot_relative_path='provenance/source/'+s.name) for s in plan.sources},
                  generated_files={n:payload[n] for n in FILES+ (('CHGCAR',) if plan.restart else ())},payload_files=payload,
                  resource_request=dict(queue='all.q',pe='mpi_32',slots=32,quota_static=320,live_checked=False),
                  science_identity=loads(plan.science_json),restart=asdict(plan.restart) if plan.restart else None,
                  validation=dict(result='INPUT_VALIDATED',input_only=True,issues=[]),
                  generation=dict(created_at=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),actor='local',request_digest=plan.request_digest,bundle_payload_hash=digest('payload',payload)))
    source_sha=payload['provenance/source/run.sh']['sha256']
    generated_sha=payload['run.sh']['sha256']
    mode=run_script_mode(p)
    manifest['run_script']=dict(mode=mode,source_sha256=source_sha,generated_sha256=generated_sha,
                                byte_identical=source_sha==generated_sha,
                                resource_validation='profile_declared_only' if mode=='preserve_source' else 'typed_static')
    manifest_bytes=canonical(manifest); mh=sha256(manifest_bytes)
    point('before_manifest'); write_new(staging/'provenance/manifest.json',manifest_bytes)
    point('before_ready'); write_new(staging/'READY.json',canonical(dict(schema_version=1,calculation_id=request['calculation_id'],stage_id=request['stage_id'],request_digest=plan.request_digest,manifest_sha256=mh)))
    verify_bundle(staging,deadline)
    for folder in ('provenance/source','provenance',''): fsync_dir(staging/folder)
    point('ready'); revalidate(plan,deadline)
    require(not final.exists(),'IDENTITY_CONFLICT',exit_code=7)
    point('before_rename'); os.rename(str(staging),str(final)); fsync_dir(final.parent); point('renamed')
    state.ready(request,mh,attempt); point('db_success')
    return result(request,'INPUT_READY',digest=plan.request_digest,bundle=final,committed=True)
