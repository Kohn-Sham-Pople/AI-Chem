import os
import uuid
from dataclasses import asdict
from pathlib import Path
from .models import DispatchOutcome,checked
from .sge import parse_qsub,command_digest
from ..config import loads
from ..errors import require
from ..paths import private_dir,safe_path,read_small,write_new,fsync_dir
from ..provenance import canonical,sha256,digest


def publish(path,data):
    path=safe_path(path); private_dir(path.parent)
    if path.exists():
        require(read_small(path,8*1024*1024)==data,'RECEIPT_CONFLICT',exit_code=9)
        return sha256(data)
    temporary=path.parent/('.tmp_'+uuid.uuid4().hex)
    write_new(temporary,data)
    require(not path.exists(),'RECEIPT_CONFLICT',exit_code=9)
    os.rename(str(temporary),str(path)); fsync_dir(path.parent)
    return sha256(data)


def intent_files(store,row,spec):
    directory=store.state/'submissions'/row['intent_id']
    record=loads(row['record_json'])
    publish(directory/'intent.json',canonical(record))
    command=asdict(spec)
    publish(directory/'argv.json',canonical(command))
    return canonical(command).decode(),command_digest(spec)


def fence_file(store,row):
    data=canonical(dict(intent_id=row['intent_id'],request_digest=row['request_digest'],state_epoch=store.profile['state_epoch']))
    publish(store.ledger/(row['intent_id']+'.json'),data)


def persist_outcome(store,row,spec,outcome):
    directory=store.state/'submissions'/row['intent_id']; record=loads(row['record_json'])
    stdout_hash=publish(directory/'qsub.stdout',outcome.stdout)
    stderr_hash=publish(directory/'qsub.stderr',outcome.stderr)
    value=dict(schema_version=1,intent_id=row['intent_id'],run_instance_id=row['run_instance_id'],token=row['token'],
        cluster_id=row['cluster_id'],cluster_epoch=row['cluster_epoch'],owner=row['owner'],request_digest=row['request_digest'],intent_sha256=sha256(canonical(record)),
        command_digest=command_digest(spec),cwd_digest=digest('cwd-v1',spec.cwd),manifest_sha256=record['manifest_sha256'],
        started_at=str(outcome.started_at),finished_at=str(outcome.finished_at),spawn_status=outcome.spawn_status,returncode=outcome.returncode,
        signal=-outcome.returncode if outcome.returncode is not None and outcome.returncode<0 else None,
        timed_out=outcome.timed_out,output_overflow=outcome.output_overflow,
        stdout=dict(size_bytes=len(outcome.stdout),sha256=stdout_hash),stderr=dict(size_bytes=len(outcome.stderr),sha256=stderr_hash),parsed_job_id=parse_qsub(outcome))
    value_hash=publish(directory/'dispatch_result.json',canonical(value))
    return value,value_hash


def read_outcome(store,row):
    directory=store.state/'submissions'/row['intent_id']; path=directory/'dispatch_result.json'
    if not path.exists(): return None
    data=read_small(path); value=checked(loads(data),'dispatch_result'); attempt=store.attempt(row['intent_id']); record=loads(row['record_json'])
    required={'schema_version','intent_id','run_instance_id','token','cluster_id','cluster_epoch','owner','request_digest','intent_sha256','command_digest','cwd_digest','manifest_sha256','started_at','finished_at','spawn_status','returncode','signal','timed_out','output_overflow','stdout','stderr','parsed_job_id'}
    require(set(value)==required and value['schema_version']==1 and attempt is not None,'RECEIPT_INVALID',exit_code=9)
    require(all(value[k]==row[k] for k in ('intent_id','run_instance_id','token','cluster_id','cluster_epoch','owner','request_digest')),'RECEIPT_INVALID',exit_code=9)
    require(value['intent_sha256']==sha256(canonical(record)) and read_small(directory/'intent.json')==canonical(record) and read_small(directory/'argv.json')==attempt['command_json'].encode(),'RECEIPT_INVALID',exit_code=9)
    spec=loads(attempt['command_json'])
    require(value['command_digest']==attempt['command_digest'] and value['cwd_digest']==digest('cwd-v1',spec['cwd']) and value['manifest_sha256']==record['manifest_sha256'],'RECEIPT_INVALID',exit_code=9)
    require(value['spawn_status'] in ('PROCESS_STARTED','SPAWN_FAILED','SPAWN_UNKNOWN') and type(value['timed_out']) is bool and type(value['output_overflow']) is bool,'RECEIPT_INVALID',exit_code=9)
    require(value['returncode'] is None or type(value['returncode']) is int,'RECEIPT_INVALID',exit_code=9)
    require(float(value['started_at'])>=row['armed_at']-120 and float(value['finished_at'])>=float(value['started_at']),'RECEIPT_INVALID',exit_code=9)
    raw=[]
    for stream in ('stdout','stderr'):
        contents=read_small(directory/('qsub.'+stream),1024*1024)
        require(value[stream]==dict(size_bytes=len(contents),sha256=sha256(contents)),'RECEIPT_INVALID',exit_code=9); raw.append(contents)
    outcome=DispatchOutcome(value['spawn_status'],value['returncode'],value['timed_out'],value['output_overflow'],raw[0],raw[1],float(value['started_at']),float(value['finished_at']))
    require(parse_qsub(outcome)==value['parsed_job_id'],'RECEIPT_INVALID',exit_code=9)
    if attempt['receipt_sha256']: require(attempt['receipt_sha256']==sha256(data),'RECEIPT_INVALID',exit_code=9)
    return value,sha256(data)
