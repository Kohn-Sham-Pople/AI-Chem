import time
from .models import SchedulerSnapshot
from .sge import command,parse_qstat,parse_detail
from ..errors import require,InputError


def successful(outcome):
    return outcome.spawn_status=='PROCESS_STARTED' and outcome.returncode==0 and not outcome.timed_out and not outcome.output_overflow


def snapshot(profile,runner,cwd,deadline=None):
    started=time.time()
    outcome=runner.query(command(profile,'qstat',cwd,['-xml','-u',profile['expected_owner']['name']]),deadline)
    require(successful(outcome),'OBSERVATION_UNKNOWN',exit_code=4)
    raw=[('snapshot',outcome.stdout,outcome.stderr)]
    jobs=list(parse_qstat(outcome.stdout,profile['expected_owner']['name']))
    require(len(jobs)+1<=profile['max_queries'],'QUERY_LIMIT',exit_code=4)
    for job in jobs:
        detail=runner.query(command(profile,'qstat',cwd,['-j',job['job_id']]),deadline)
        require(successful(detail),'OBSERVATION_UNKNOWN',exit_code=4)
        raw.append(('detail_'+job['job_id'],detail.stdout,detail.stderr))
        info=parse_detail(detail.stdout,cluster_timezone=profile['cluster_timezone'])
        require(info['job_id']==job['job_id'] and info['owner']==job['owner'] and info['name']==job['name'],'RESOURCE_UNKNOWN',exit_code=4)
        job['slots']=max(job['slots'],info['slots'])
        # Identity dedup uses validated detail, not a truncated display name.
        job['token']=info['token']
        job['qsub_time']=info['qsub_time']
    return SchedulerSnapshot(profile['cluster_id'],profile['cluster_epoch'],profile['expected_owner']['name'],started,True,tuple(jobs),tuple(raw))


def check_admission(snapshot,reservations,profile,candidate_id=None,now=None):
    now=time.time() if now is None else now
    require(snapshot.complete and 0<=now-snapshot.captured_at<=profile['snapshot_max_age_seconds'],'SNAPSHOT_STALE',exit_code=4)
    require((snapshot.cluster_id,snapshot.cluster_epoch,snapshot.owner)==(profile['cluster_id'],profile['cluster_epoch'],profile['expected_owner']['name']),'SNAPSHOT_SCOPE',exit_code=4)
    jobs={}
    for job in snapshot.jobs:
        require(type(job.get('slots')) is int and job['slots']>0 and job['owner']==snapshot.owner,'RESOURCE_UNKNOWN',exit_code=4)
        if job['job_id'] in jobs: require(jobs[job['job_id']]==job,'RESOURCE_UNKNOWN',exit_code=4)
        jobs[job['job_id']]=job
    seen=sum(j['slots'] for j in jobs.values()); unseen=0; outstanding=0
    tokens={j.get('token') for j in jobs.values() if j.get('token')}
    for row in reservations:
        if row['intent_id']==candidate_id or row.get('terminal_observed') or row['state']=='NOT_DISPATCHED': continue
        outstanding+=1
        if row['token'] not in tokens: unseen+=row['slots']
    require(outstanding<profile['max_outstanding_controller_runs'],'PILOT_LIMIT',exit_code=4)
    require(seen+unseen+profile['slots']<=profile['user_quota_slots'],'QUOTA_EXCEEDED',exit_code=4)
    return dict(S_seen=seen,S_unseen=unseen,requested=profile['slots'],cap=profile['user_quota_slots'],snapshot_at=snapshot.captured_at,permitted=True)
