import os
import time
import uuid
from .preflight import load_config
from .models import checked,result
from .store import SubmissionStore
from .service import submit,reconcile
from .receipts import publish
from ..config import loads
from ..errors import InputError,require
from ..paths import private_dir,read_small,fsync_dir
from ..state import global_lock
from ..worker import bounded_items
from ..provenance import canonical,sha256


def once(config_path,max_new_submissions=1,runner=None):
    require(max_new_submissions==1,'PILOT_LIMIT',exit_code=2)
    config,_=load_config(config_path); p=config['profile']; store=SubmissionStore(p)
    if not p['live_enabled']: return result('worker',state='ADMISSION_BLOCKED',issues=['LIVE_DISABLED'])
    deadline=time.monotonic()+p['worker_budget_seconds']
    with global_lock(p['roots']['lock']):
        store.guard()
        pending=[r for r in store.all_intents() if r['dispatch_fence'] and r['state'] in ('DISPATCH_ARMED','SUBMISSION_UNCERTAIN')]
        if pending: return reconcile(pending[0]['intent_id'],config_path,runner,deadline,_locked=True)
        unarmed=[r for r in store.all_intents() if not r['dispatch_fence'] and r['state']=='SUBMIT_PENDING']
        if unarmed: return submit(loads(unarmed[0]['record_json'])['request'],config_path,runner=runner,deadline=deadline,_locked=True)
        base=private_dir(store.state/'submission_inbox'); claimed=private_dir(store.state/'submission_processing')
        items=bounded_items(claimed,True)[:1] or bounded_items(base,True)[:1]
        if not items: return result('worker',state='EXISTING')
        source=items[0]
        target=claimed/(uuid.uuid4().hex+'.json') if source.parent==base else source
        if source!=target:
            os.rename(str(source),str(target)); fsync_dir(base); fsync_dir(claimed)
        try: data=read_small(target); request=checked(loads(data),'request')
        except (InputError,OSError,ValueError): data=None; request=None
        response=submit(request,config_path,runner=runner,deadline=deadline,_locked=True) if request else result('worker',state='INVALID_REQUEST',issues=['INVALID_REQUEST'])
        archive=private_dir(store.state/'submission_archive'/uuid.uuid4().hex)
        publish(archive/'result.json',canonical(dict(response,transport_sha256=sha256(data) if data else None)))
        os.rename(str(target),str(archive/'request.json')); fsync_dir(archive); fsync_dir(claimed)
        return response
