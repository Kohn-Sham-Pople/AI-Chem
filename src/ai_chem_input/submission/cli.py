import argparse
import json
import sqlite3
import sys
from .models import EXIT,checked,result
from .preflight import load_config
from .service import submit,reconcile,error_result
from .store import SubmissionStore
from .worker import once
from ..config import load,identifier
from ..errors import InputError

class Parser(argparse.ArgumentParser):
    def error(self,message): raise InputError('CLI_USAGE',exit_code=2)


def main(argv=None):
    try:
        parser=Parser(prog='ai-chem-input submission'); sub=parser.add_subparsers(dest='operation',required=True)
        q=sub.add_parser('submit'); q.add_argument('--config',required=True); q.add_argument('--request',required=True); q.add_argument('--dry-run',action='store_true')
        q=sub.add_parser('show'); q.add_argument('--config',required=True); q.add_argument('--request-id',required=True)
        q=sub.add_parser('reconcile'); q.add_argument('--config',required=True); q.add_argument('--intent-id',required=True)
        q=sub.add_parser('worker'); q.add_argument('--config',required=True); q.add_argument('--once',action='store_true',required=True); q.add_argument('--max-new-submissions',type=int,default=1)
        args=parser.parse_args(argv)
        if args.operation=='submit': response=submit(checked(load(args.request),'request'),args.config,args.dry_run)
        elif args.operation=='reconcile': response=reconcile(identifier(args.intent_id),args.config)
        elif args.operation=='worker': response=once(args.config,args.max_new_submissions)
        else:
            config,_=load_config(args.config); store=SubmissionStore(config['profile'])
            row=store.lookup(request_id=identifier(args.request_id))
            response=result('show',dict(request_id=args.request_id),state=row['state'] if row else 'INVALID_REQUEST',row=row,issues=[] if row else ['REQUEST_NOT_FOUND'])
    except (InputError,OSError,sqlite3.Error,ValueError,KeyError,TypeError) as error:
        response=error_result('cli',None,error)
    print(json.dumps(response,sort_keys=True))
    return EXIT.get(response['state'],0 if response['operation']=='show' else 9)
