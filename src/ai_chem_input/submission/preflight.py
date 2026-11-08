import datetime
import os
import pwd
import re
import shlex
from pathlib import Path
from .models import checked,VerifiedBundle,SubmissionPlan
from .identity import derive_calculation_key,derive_bundle_key,request_digest
from .sge import command_policy,client_env
from ..config import load,loads
from ..errors import require,InputError
from ..paths import safe_path,under,guard_roots,read_small,inspect
from ..prepare import verify_bundle
from ..provenance import canonical,sha256,digest


def load_config(path):
    data=read_small(safe_path(path)); value=checked(loads(data),'config')
    value['profile'].setdefault('live_enabled',False)
    for key in ('SGE_QMASTER_PORT','SGE_EXECD_PORT'):
        if key in value['profile']['sge_client_env']:
            require(1<=int(value['profile']['sge_client_env'][key])<=65535,'CLIENT_PORT_INVALID',exit_code=2)
    return value,sha256(data)


def verify_prepared_bundle(ref,expected_manifest,profile,deadline=None):
    path=under(ref,[profile['roots']['output']])
    try: verified=verify_bundle(path,deadline)
    except (InputError,OSError,ValueError,KeyError): raise InputError('BUNDLE_INVALID',exit_code=3) from None
    m=verified['manifest']; require(verified['manifest_sha256']==expected_manifest,'MANIFEST_MISMATCH',exit_code=3)
    require(m['schema_version']==1 and m['hash_schema_version']==1,'BUNDLE_SCHEMA',exit_code=3)
    require(m['resource_request']==dict(queue='all.q',pe='mpi_32',slots=32,quota_static=320,live_checked=False),'RESOURCE_MISMATCH',exit_code=3)
    resolved=read_small(path/'provenance/resolved_config.json'); c=loads(resolved)
    for key in ('output','state','lock'):
        require(profile['roots'][key]==c['profile']['roots'][key],'ROOT_MISMATCH',exit_code=3)
    require(profile['roots']['protected']==c['profile']['roots']['protected'],'ROOT_MISMATCH',exit_code=3)
    return VerifiedBundle(str(path),expected_manifest,canonical(m),resolved)


def reject_used(bundle):
    m=loads(bundle.manifest_json)
    allowed=set(m['payload_files'])|{'READY.json','provenance/manifest.json'}
    expected_dirs={str(Path(p).parent) for p in allowed}
    expected_dirs|={'provenance','provenance/source','.'}
    count=0
    for p in Path(bundle.path).rglob('*'):
        count+=1; require(count<=1000,'DIR_INVENTORY_LIMIT',exit_code=3)
        safe_path(p); rel=str(p.relative_to(bundle.path))
        require((p.is_dir() and rel in expected_dirs) or (p.is_file() and rel in allowed),'DIR_ALREADY_USED',exit_code=3)


def profile_authorization_hash(profile):
    return digest('live-authorization-v1',{k:v for k,v in profile.items() if k not in ('live_authorization','live_enabled')})


def proof(profile,field,kind):
    pin=profile[field]; require(pin is not None,kind.upper()+'_UNVERIFIED',exit_code=4)
    data=read_small(safe_path(pin['path']))
    require(sha256(data)==pin['sha256'],'EVIDENCE_CHANGED',exit_code=4)
    value=checked(loads(data),kind)
    require(all(value[k]==profile[k] for k in ('cluster_id','cluster_epoch')) and value['owner']==profile['expected_owner']['name'],'EVIDENCE_SCOPE',exit_code=4)
    try: datetime.datetime.strptime(value['approval']['approved_at'],'%Y-%m-%dT%H:%M:%SZ')
    except ValueError: raise InputError('EVIDENCE_APPROVAL',exit_code=4) from None
    return value


def execution_report(bundle,profile):
    """Conservative potential differences, not a shell interpreter or site proof."""
    data=read_small(Path(bundle.path)/'run.sh'); directives=[]; source={}; blockers=[]; changes=set()
    try: text=data.decode('utf-8')
    except UnicodeError:
        text=''; blockers.append('SCRIPT_ENCODING_UNVERIFIED')
    for line in text.splitlines():
        if line.lstrip().startswith('#$'):
            try: words=shlex.split(line.lstrip()[2:])
            except ValueError:
                blockers.append('SCRIPT_DIRECTIVE_UNVERIFIED'); continue
            directives.append(words)
            if not words: continue
            flag=words[0]
            if flag in source: blockers.append('SCRIPT_DIRECTIVE_UNVERIFIED')
            source[flag]=words[1:]
            if flag not in ('-S','-V','-cwd','-q','-pe','-N','-j','-o','-r','-l','-P','-A'):
                blockers.append('SCRIPT_DIRECTIVE_UNVERIFIED')
    if '-V' in source: changes.add('export_all_removed')
    queue=source.get('-q',[])
    if queue and queue!=['all.q']:
        changes.add('node_selection_removed' if queue==['all.q@node127'] else 'queue_overridden')
    if source.get('-pe',['mpi_32','32'])!=['mpi_32','32']: blockers.append('SCRIPT_RESOURCE_MISMATCH')
    for flag,expected,label in [('-S',['/bin/bash'],'shell_overridden'),('-r',['n'],'rerun_overridden'),('-j',['y'],'join_overridden'),('-o',['vasp.stdout'],'stdout_overridden')]:
        if flag in source and source[flag]!=expected: changes.add(label)
    if '-N' in source: changes.add('name_overridden')
    if '-cwd' not in source: changes.add('cwd_overridden')
    site=profile.get('site_options',{})
    for flag,key in (('-P','project'),('-A','account')):
        if flag in source and source[flag]!=[site.get(key)]: blockers.append('SITE_RESOURCE_OPTIONS_UNVERIFIED')
    if '-l' in source and (not site.get('walltime') or source['-l']!=['h_rt='+site['walltime']]):
        blockers.append('SITE_RESOURCE_OPTIONS_UNVERIFIED')
    m=loads(bundle.manifest_json)
    report=dict(script_sha256=m['generated_files']['run.sh']['sha256'],command_policy_sha256=command_policy(profile,bundle),
                client_env_sha256=digest('client-env-v1',client_env(profile)),changes=sorted(changes),directives=directives,blockers=blockers)
    try:
        evidence=proof(profile,'effective_execution_evidence','effective_execution')
        require(all(evidence[k]==report[k] for k in ('script_sha256','command_policy_sha256','client_env_sha256')),'EXECUTION_EVIDENCE_MISMATCH',exit_code=4)
        require(set(evidence['approved_changes'])==changes and len(evidence['approved_changes'])==len(changes),'EXECUTION_CHANGE_UNAPPROVED',exit_code=4)
    except (InputError,OSError,ValueError,KeyError):
        report['blockers'].append('EXECUTION_EQUIVALENCE_UNVERIFIED')
    report['blockers']=sorted(set(report['blockers']))
    return report


def verify_runtime_identity(p):
    require(p['expected_owner']==dict(uid=os.geteuid(),name=pwd.getpwuid(os.geteuid()).pw_name) and os.getuid()==os.geteuid(),'OWNER_MISMATCH',exit_code=4)
    require(p['sge_client_env']['HOME']==os.environ.get('HOME'),'HOME_MISMATCH',exit_code=4)
    for name in ('SGE_ROOT','SGE_CELL'):
        require(name not in os.environ or os.environ[name]==p['sge_client_env'][name],'CLUSTER_MISMATCH',exit_code=4)
    qmaster=Path(p['sge_client_env']['SGE_ROOT'])/p['sge_client_env']['SGE_CELL']/'common/act_qmaster'
    try: current=read_small(qmaster,4096).decode('ascii').strip()
    except (OSError,UnicodeError,InputError): raise InputError('QMASTER_IDENTITY_UNKNOWN',exit_code=4) from None
    require(current in p['qmaster_aliases'],'QMASTER_IDENTITY_MISMATCH',exit_code=4)


def live_gates(plan):
    c=loads(plan.config_json); p=c['profile']; guard_roots(p['roots'])
    require(p['live_enabled'],'LIVE_DISABLED',exit_code=4)
    require(not p['paused'] and not p['paused_restore'],'RESTORE_PAUSED',exit_code=9)
    require(not any((Path(p['roots']['state'])/name).exists() for name in ('submission.pause','paused_restore')),'RESTORE_PAUSED',exit_code=9)
    verify_runtime_identity(p)
    require(p['queue_pending_policy']=='single_job_pilot','ADMISSION_POLICY_UNVERIFIED',exit_code=4)
    for kind in ('qsub','qstat','qacct'):
        path=safe_path(p[kind+'_path']); require(path.name==kind and path.is_file() and os.access(str(path),os.R_OK|os.X_OK),'CLIENT_UNAVAILABLE',exit_code=4)
    proof(p,'scheduler_rqs_evidence','rqs')
    dialect=proof(p,'dialect_evidence','dialect')
    require(dialect['client_paths_sha256']==digest('sge-paths-v1',{k:p[k+'_path'] for k in ('qsub','qstat','qacct')}) and dialect['qmaster_aliases']==p['qmaster_aliases'],'DIALECT_UNVERIFIED',exit_code=4)
    authorization=proof(p,'live_authorization','live_authorization')
    require(authorization['profile_sha256']==profile_authorization_hash(p),'LIVE_AUTHORIZATION_UNVERIFIED',exit_code=4)
    report=execution_report(plan.bundle,p)
    require(not report['blockers'],report['blockers'][0] if report['blockers'] else 'EXECUTION_EQUIVALENCE_UNVERIFIED',exit_code=4)
    return p


def build_submission_plan(request,config_path,deadline=None):
    checked(request,'request'); c,pin=load_config(config_path); p=c['profile']; guard_roots(p['roots'])
    require(request['submission_profile']=={k:p[k] for k in ('id','revision')},'PROFILE_REF',exit_code=2)
    require(request['bundle_ref'] in c['bundle_refs'],'BUNDLE_REF',exit_code=2)
    bundle=verify_prepared_bundle(c['bundle_refs'][request['bundle_ref']],request['expected_manifest_sha256'],p,deadline)
    require(request['stage_id']==loads(bundle.manifest_json)['identity']['stage_id'],'PREPARATION_IDENTITY',exit_code=3)
    calculation=derive_calculation_key(bundle); location=derive_bundle_key(bundle,p)
    return SubmissionPlan(canonical(request),canonical(c),str(safe_path(config_path)),pin,bundle,calculation,location,
                          request_digest(bundle,p,calculation,location),canonical(execution_report(bundle,p)))


def refresh(plan,deadline=None):
    require(inspect(plan.config_path)['sha256']==plan.config_sha256,'CONFIG_CHANGED',exit_code=3)
    c=loads(plan.config_json)
    fresh=verify_prepared_bundle(plan.bundle.path,plan.bundle.manifest_sha256,c['profile'],deadline)
    require(fresh==plan.bundle,'BUNDLE_CHANGED',exit_code=3)
    reject_used(fresh)
    return fresh
