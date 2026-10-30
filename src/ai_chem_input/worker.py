"""One-shot local inbox consumer; no scheduler, shell or network clients."""
import os
import sqlite3
import time
import uuid
from pathlib import Path
from .config import checked, load, loads, identifier
from .errors import InputError, result, require
from .paths import private_dir, safe_path, read_small, write_new, fsync_dir, deadline_check
from .provenance import canonical,sha256
from .registry import Registry
from .prepare import build_plan,materialize
from .state import global_lock


def operator(config_path):
    safe_path(config_path); conf=checked(load(config_path),'operator'); reg=Registry(conf['registry'])
    profile,_=reg.resolve('profile',conf['profile'])
    from .paths import guard_roots
    guard_roots(profile['roots'])
    require(conf['registry']==profile['roots']['registry'],'REGISTRY_LINK')
    return conf,reg,profile


def bounded_items(directory,json_only=False):
    entries=[]
    for item in directory.iterdir():
        require(len(entries)<100,'INBOX_LIMIT',exit_code=2)
        entries.append(item)
    return sorted(p for p in entries if not json_only or p.suffix=='.json')


def once(config_path,max_requests=1):
    require(max_requests==1,'SCHEMA',exit_code=2)
    conf,registry,profile=operator(config_path); deadline=time.monotonic()+profile['preparation']['budget_seconds']
    with global_lock(profile['roots']['lock']):
        state=private_dir(profile['roots']['state']); inbox=private_dir(state/'inbox')
        processing=private_dir(state/'processing'); reports=[]
        # Resume a previously claimed request first; identity reconciliation is in materialize.
        pending=bounded_items(processing,True)
        items=pending[:1] if pending else bounded_items(inbox,True)[:1]
        for item in items:
            deadline_check(deadline); request=None; data=None
            claim=processing/(uuid.uuid4().hex+'.json')
            if item.parent==inbox:
                os.rename(str(item),str(claim)); fsync_dir(inbox); fsync_dir(processing)
            else: claim=item
            try:
                data=read_small(claim); request=checked(loads(data),'request')
                plan=build_plan((request,registry),deadline=deadline)
                response=materialize(plan,locked=True,deadline=deadline)
            except InputError as exc:
                response=result(request,'BUSY' if exc.exit_code==6 else 'BLOCKED_RESTART' if exc.exit_code==4 else 'IDENTITY_CONFLICT' if exc.exit_code==7 else 'REJECTED',codes=[exc.code])
            except (OSError,sqlite3.Error,ValueError,KeyError):
                response=result(request,'FAILED_SAFE',codes=['LOCAL_IO'])
            archive=private_dir(state/('processed' if response['result'] in ('INPUT_READY','IDEMPOTENT_EXISTING') else 'rejected'))
            folder=archive/uuid.uuid4().hex; folder.mkdir(mode=0o700)
            # Move even malformed/symlink input as an opaque rejected artifact, never follow it.
            write_new(folder/'result.json',canonical(dict(response,transport_sha256=sha256(data) if data is not None else None)))
            fsync_dir(folder)
            os.rename(str(claim),str(folder/'request.json'))
            fsync_dir(folder); fsync_dir(processing); reports.append(response)
        return reports
