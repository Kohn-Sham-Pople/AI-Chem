import argparse
import json
import sqlite3
import sys
from pathlib import Path
from .config import checked,load
from .errors import InputError,result,require
from .registry import Registry
from .prepare import build_plan,materialize,verify_bundle
from .worker import operator,once
from .discovery import discover_templates
from .provenance import canonical,sha256
from .paths import read_small,safe_path

class Parser(argparse.ArgumentParser):
    def error(self,message): raise InputError('CLI_USAGE',exit_code=2)


def parser():
    p=Parser(prog='ai-chem-input'); sub=p.add_subparsers(dest='command',required=True)
    for name in ('plan','prepare'):
        q=sub.add_parser(name); q.add_argument('--config',required=True); q.add_argument('--request',required=True)
        if name=='prepare': q.add_argument('--dry-run',action='store_true')
    q=sub.add_parser('discover'); q.add_argument('--config',required=True)
    q=sub.add_parser('verify'); q.add_argument('--bundle',required=True)
    q=sub.add_parser('worker'); q.add_argument('--config',required=True); q.add_argument('--once',required=True,action='store_true'); q.add_argument('--max-requests',type=int,default=1)
    q=sub.add_parser('registry'); s=q.add_subparsers(dest='action',required=True)
    for name in ('check','register'):
        r=s.add_parser(name); r.add_argument('--registry',required=True)
        if name=='register':
            r.add_argument('--kind',choices=('profile','template','material','protocol'),required=True)
            r.add_argument('--entity',required=True); r.add_argument('--approved-sha256',required=True)
    return p


def main(argv=None):
    request=None
    try:
        args=parser().parse_args(argv)
        if args.command in ('plan','prepare'):
            _,reg,profile=operator(args.config); request=checked(load(args.request),'request')
            require(request['cluster_profile']['id']==profile['id'] and request['cluster_profile']['revision']==profile['revision'],'REGISTRY_LINK')
            plan=build_plan((request,reg))
            if args.command=='plan' or args.dry_run:
                response=result(request,'PLAN_VALIDATED',digest=plan.request_digest)
                from .config import loads
                response.update(stage_plan=dict(stage_id=request['stage_id'],input_only=True),semantic_changes=[{k:v for k,v in change.items() if k not in ('old','new')} for change in loads(plan.semantic_json)])
                # Raw old/new values are private: stdout is only for approved HPC/synthetic use.
            else: response=materialize(plan)
        elif args.command=='verify':
            try: verified=verify_bundle(Path(args.bundle))
            except (OSError,InputError,KeyError,ValueError,TypeError):
                raise InputError('PACKAGE_TAMPERED',exit_code=5) from None
            m=verified['manifest']
            response=result(m['identity'],'VERIFIED',digest=verified['request_digest'],bundle=args.bundle)
            response['manifest_sha256']=verified['manifest_sha256']
        elif args.command=='discover':
            _,_,profile=operator(args.config); candidates=discover_templates(profile)
            # Full inventory is local-private; no file bytes or raw shell body.
            response=dict(result(None,'DISCOVERED'),candidates=candidates)
        elif args.command=='worker':
            responses=once(args.config,args.max_requests)
            response=responses[0] if responses else result(None,'INBOX_EMPTY')
        elif args.action=='register':
            reg=Registry(args.registry); entity=load(args.entity)
            reg.register(args.kind,entity,args.approved_sha256); response=result(None,'REGISTERED')
        else:
            reg=Registry(args.registry); count=0
            for kind in ('profile','template','material','protocol'):
                directory=reg.root/kind
                if not directory.exists(): continue
                for name in sorted(directory.iterdir()):
                    safe_path(name); require(name.is_dir(),'REGISTRY_IDENTITY')
                    for path in sorted(name.iterdir()):
                        safe_path(path); require(path.suffix=='.json' and path.stem.isdigit(),'REGISTRY_IDENTITY')
                        reg.resolve(kind,dict(id=name.name,revision=int(path.stem))); count+=1
            require(count>0,'REGISTRY_EMPTY',exit_code=2); response=dict(result(None,'REGISTRY_VALID'),entity_count=count)
        print(json.dumps(response,sort_keys=True))
        return {'REJECTED':2,'BLOCKED_RESTART':4,'FAILED_SAFE':5,'BUSY':6,'IDENTITY_CONFLICT':7}.get(response['result'],0)
    except InputError as exc:
        status={4:'BLOCKED_RESTART',5:'FAILED_SAFE',6:'BUSY',7:'IDENTITY_CONFLICT'}.get(exc.exit_code,'REJECTED')
        print(json.dumps(result(request,status,[exc.code]))); return exc.exit_code
    except (OSError,sqlite3.Error):
        print(json.dumps(result(request,'FAILED_SAFE',['LOCAL_IO']))); return 5
    except (ValueError,KeyError,TypeError,UnicodeError):
        print(json.dumps(result(request,'REJECTED',['INVALID_DATA']))); return 2
