"""Versioned SGE fixture dialect. Unconfirmed local dialects cannot dispatch."""
import datetime
import re
import xml.etree.ElementTree as ET
from .models import CommandSpec
from ..errors import require,InputError
from ..provenance import canonical,digest

ACTIVE={'qw','r','hqw','Eqw','dr','dt','t','s','S','T','Rr','Rq','hRqw','d','h','E'}


def client_env(profile):
    return dict(profile['sge_client_env'],LC_ALL='C',LANG='C')


def command(profile,kind,cwd,arguments):
    require(kind in ('qsub','qstat','qacct'),'COMMAND_FORBIDDEN',exit_code=2)
    exe=profile[kind+'_path']
    return CommandSpec(kind,exe,tuple([exe]+list(arguments)),str(cwd),tuple(sorted(client_env(profile).items())),
                       profile['qsub_timeout_seconds'] if kind=='qsub' else profile['query_timeout_seconds'],
                       1024*1024 if kind=='qsub' else 8*1024*1024)


def build_qsub(profile,bundle_path,manifest_sha,token):
    require(re.fullmatch(r'[0-9a-f]{32}',token) is not None,'TOKEN_INVALID',exit_code=2)
    require(re.fullmatch(r'[0-9a-f]{64}',manifest_sha) is not None,'MANIFEST_INVALID',exit_code=2)
    args=['-clear','-terse','-b','n','-S','/bin/bash','-r','n','-cwd','-hard','-q','all.q','-pe','mpi_32','32',
          '-N','ac_'+token,'-j','y','-o','vasp.stdout','-v','AI_CHEM_RUN_TOKEN='+token+',AI_CHEM_MANIFEST_SHA256='+manifest_sha,'./run.sh']
    site=profile.get('site_options',{})
    extra=[]
    for key,flag in (('project','-P'),('account','-A')):
        if site.get(key): extra.extend([flag,site[key]])
    if site.get('walltime'): extra.extend(['-l','h_rt='+site['walltime']])
    args[-1:-1]=extra
    return command(profile,'qsub',bundle_path,args)


def command_digest(spec):
    return digest('command-v1',dict(argv=spec.argv,cwd=spec.cwd,env=spec.env))


def command_policy(profile,bundle):
    return command_digest(build_qsub(profile,bundle.path,bundle.manifest_sha256,'0'*32))


def parse_qsub(outcome):
    if outcome.spawn_status!='PROCESS_STARTED' or outcome.returncode!=0 or outcome.timed_out or outcome.output_overflow:
        return None
    data=outcome.stdout.strip(b' \t\r\n')
    return data.decode('ascii') if re.fullmatch(rb'[1-9][0-9]*',data) else None


def xml_root(data):
    require(len(data)<=8*1024*1024 and b'\x00' not in data and not re.search(rb'<!\s*(?:DOCTYPE|ENTITY)',data,re.I),'SGE_XML_UNSAFE',exit_code=4)
    try:
        data.decode('utf-8')
        parser=ET.XMLPullParser(events=('start','end')); root=None; depth=-1; count=0
        for offset in range(0,len(data),4096):
            parser.feed(data[offset:offset+4096])
            for event,node in parser.read_events():
                if event=='start':
                    depth+=1; count+=1
                    require(depth<=16 and count<=100000 and isinstance(node.tag,str) and '{' not in node.tag,'SGE_XML_UNSAFE',exit_code=4)
                    if root is None: root=node
                else: depth-=1
        parser.close()
    except (ET.ParseError,ValueError,UnicodeError): raise InputError('SGE_XML_INVALID',exit_code=4) from None
    require(root is not None and depth==-1,'SGE_XML_INVALID',exit_code=4)
    require(root.tag=='job_info' and (not root.attrib or root.attrib=={'version':'sge_xml_v1'}),'SGE_DIALECT_UNKNOWN',exit_code=4)
    return root


def upper_slots(raw):
    require(isinstance(raw,str) and re.fullmatch(r'[1-9][0-9]*(?:-[1-9][0-9]*)?',raw) is not None,'RESOURCE_UNKNOWN',exit_code=4)
    parts=[int(x) for x in raw.split('-')]
    require(parts[-1]>=parts[0] and parts[-1]<=1000000,'RESOURCE_UNKNOWN',exit_code=4)
    return parts[-1]


def parse_qstat(data,owner):
    root=xml_root(data); jobs={}
    require(len(root)>0 and all(group.tag in ('queue_info','job_info') and not group.attrib for group in root),'SGE_DIALECT_UNKNOWN',exit_code=4)
    require(all(node.tag=='job_list' for group in root for node in group),'SGE_DIALECT_UNKNOWN',exit_code=4)
    for node in (node for group in root for node in group):
        values={}
        for child in node:
            require(child.tag not in values,'SGE_XML_INVALID',exit_code=4)
            values[child.tag]=(child.text or '').strip()
        require(all(k in values for k in ('JB_job_number','JB_name','JB_owner','state','slots')),'RESOURCE_UNKNOWN',exit_code=4)
        require(re.fullmatch(r'[1-9][0-9]*',values['JB_job_number']) and values['JB_owner']==owner and values['state'] in ACTIVE,'RESOURCE_UNKNOWN',exit_code=4)
        require(not values.get('tasks'),'ARRAY_UNSUPPORTED',exit_code=4)
        slots=upper_slots(values.get('pe_range') or values['slots'])
        job=dict(job_id=values['JB_job_number'],name=values['JB_name'],owner=owner,state=values['state'],slots=slots,
                 token=values['JB_name'][3:] if re.fullmatch(r'ac_[0-9a-f]{32}',values['JB_name']) else None)
        if job['job_id'] in jobs:
            previous=jobs[job['job_id']]
            require(all(previous[k]==job[k] for k in ('name','owner')),'RESOURCE_UNKNOWN',exit_code=4)
        if job['job_id'] in jobs: job['slots']=max(job['slots'],jobs[job['job_id']]['slots'])
        jobs[job['job_id']]=job
    return tuple(jobs.values())


def timestamp(raw):
    if re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',raw): return float(raw)
    try:
        value=datetime.datetime.fromisoformat(raw.replace('Z','+00:00'))
        require(value.tzinfo is not None,'SGE_TIME_UNKNOWN',exit_code=4)
        return value.timestamp()
    except ValueError: raise InputError('SGE_TIME_UNKNOWN',exit_code=4) from None


def fields(data):
    require(len(data)<=8*1024*1024,'SGE_OUTPUT_LIMIT',exit_code=4)
    try: text=data.decode('utf-8')
    except UnicodeError: raise InputError('SGE_TEXT_INVALID',exit_code=4) from None
    result={}
    for line in text.splitlines():
        if not line.strip() or set(line.strip())=={'='}: continue
        match=(re.fullmatch(r'([A-Za-z_][A-Za-z0-9_ ]*):\s*(.*)',line.strip())
               or re.fullmatch(r'([A-Za-z_][A-Za-z0-9_]*)\s+(.*)',line.strip()))
        require(match is not None,'SGE_TEXT_INVALID',exit_code=4)
        key=match[1].strip(); require(key not in result,'SGE_TEXT_INVALID',exit_code=4); result[key]=match[2].strip()
    return result


def parse_detail(data):
    f=fields(data)
    required={'job_number','job_name','owner','sge_o_workdir','env_list','submission_time','parallel environment'}
    require(required<=set(f),'SGE_DETAIL_INCOMPLETE',exit_code=4)
    pe=re.fullmatch(r'(\S+)\s+range:\s*(\S+)',f['parallel environment'])
    require(pe is not None and re.fullmatch(r'[1-9][0-9]*',f['job_number']),'SGE_DETAIL_INCOMPLETE',exit_code=4)
    environment={}
    for pair in f['env_list'].split(','):
        require('=' in pair,'SGE_DETAIL_INCOMPLETE',exit_code=4)
        key,value=pair.split('=',1); require(key not in environment,'SGE_DETAIL_INCOMPLETE',exit_code=4); environment[key]=value
    return dict(job_id=f['job_number'],name=f['job_name'],owner=f['owner'],cwd=f['sge_o_workdir'],
        token=environment.get('AI_CHEM_RUN_TOKEN'),manifest=environment.get('AI_CHEM_MANIFEST_SHA256'),
        pe=pe[1],slots=upper_slots(pe[2]),qsub_time=timestamp(f['submission_time']),terminal=False)


def parse_accounting(data):
    if not data.strip(): return ()
    chunks=re.split(rb'(?m)^=+\s*$',data); jobs={}
    for chunk in chunks:
        if not chunk.strip(): continue
        f=fields(chunk)
        require({'jobnumber','jobname','owner','qsub_time','slots','granted_pe'}<=set(f),'SGE_ACCOUNTING_INCOMPLETE',exit_code=4)
        require(re.fullmatch(r'[1-9][0-9]*',f['jobnumber']),'SGE_ACCOUNTING_INCOMPLETE',exit_code=4)
        record=dict(job_id=f['jobnumber'],name=f['jobname'],owner=f['owner'],qsub_time=timestamp(f['qsub_time']),
                    slots=upper_slots(f['slots']),pe=f['granted_pe'],terminal=True)
        key=(record['job_id'],record['name'],record['owner'],record['qsub_time'])
        require(f.get('taskid','undefined') in ('undefined','NONE','0'),'ARRAY_UNSUPPORTED',exit_code=4)
        master=f.get('pe_taskid','NONE') in ('NONE','undefined','0')
        if key not in jobs: jobs[key]=[]
        jobs[key].append((master,record))
    result=[]
    for entries in jobs.values():
        masters=[record for master,record in entries if master]
        require(masters and all(record==masters[0] for record in masters),'SGE_ACCOUNTING_INCOMPLETE',exit_code=4)
        result.append(masters[0])
    return tuple(result)
