"""Additive tables in the preparation DB; never modify preparation records."""
import os
import secrets
import sqlite3
import time
import uuid
from pathlib import Path
from .models import DispatchPermit
from ..config import loads
from ..errors import InputError,require
from ..paths import safe_path,private_dir,read_small,write_new,fsync_dir
from ..provenance import canonical,digest
from ..state import StateStore

SQL='''
CREATE TABLE IF NOT EXISTS submission_schema_meta(version INTEGER PRIMARY KEY,cluster_id TEXT,cluster_epoch TEXT,state_epoch TEXT,owner TEXT,applied_at REAL,implementation_revision TEXT);
CREATE TABLE IF NOT EXISTS submission_profiles(id TEXT,revision INTEGER,sha256 TEXT NOT NULL,PRIMARY KEY(id,revision));
CREATE TABLE IF NOT EXISTS submission_intents(
 intent_id TEXT PRIMARY KEY,cluster_id TEXT NOT NULL,cluster_epoch TEXT NOT NULL,owner TEXT NOT NULL,
 calculation_id TEXT NOT NULL,stage_id TEXT NOT NULL,calculation_key TEXT NOT NULL,bundle_key TEXT NOT NULL,
 request_digest TEXT NOT NULL,run_instance_id TEXT UNIQUE NOT NULL,token TEXT UNIQUE NOT NULL,
 state TEXT NOT NULL,dispatch_fence INTEGER NOT NULL CHECK(dispatch_fence IN (0,1)),version INTEGER NOT NULL,
 created_at REAL NOT NULL,armed_at REAL,updated_at REAL NOT NULL,slots INTEGER NOT NULL,
 terminal_observed INTEGER NOT NULL DEFAULT 0,record_json TEXT NOT NULL,
 UNIQUE(cluster_id,cluster_epoch,calculation_key),UNIQUE(cluster_id,cluster_epoch,bundle_key));
CREATE TABLE IF NOT EXISTS submission_requests(request_id TEXT PRIMARY KEY,request_digest TEXT NOT NULL,
 intent_id TEXT NOT NULL REFERENCES submission_intents(intent_id),label TEXT,stage_id TEXT,received_at REAL);
CREATE TABLE IF NOT EXISTS submission_attempts(intent_id TEXT PRIMARY KEY REFERENCES submission_intents(intent_id),
 ordinal INTEGER NOT NULL CHECK(ordinal=1),command_digest TEXT NOT NULL,command_json TEXT NOT NULL,
 started_at REAL,finished_at REAL,receipt_sha256 TEXT);
CREATE TABLE IF NOT EXISTS scheduler_bindings(intent_id TEXT PRIMARY KEY REFERENCES submission_intents(intent_id),
 cluster_id TEXT,cluster_epoch TEXT,job_id TEXT NOT NULL,owner TEXT,qsub_time REAL,evidence_sha256 TEXT);
CREATE TABLE IF NOT EXISTS scheduler_observations(observation_id TEXT PRIMARY KEY,intent_id TEXT REFERENCES submission_intents(intent_id),
 captured_at REAL,source TEXT,match_result TEXT,evidence_sha256 TEXT);
CREATE TABLE IF NOT EXISTS submission_events(event_id INTEGER PRIMARY KEY,intent_id TEXT REFERENCES submission_intents(intent_id),
 prior_state TEXT,new_state TEXT,reason TEXT,created_at REAL);
CREATE TABLE IF NOT EXISTS admission_records(admission_id TEXT PRIMARY KEY,intent_id TEXT REFERENCES submission_intents(intent_id),record_json TEXT NOT NULL);
'''


class SubmissionStore:
    def __init__(self,profile):
        self.profile=profile; self.path=Path(profile['roots']['state'])/'preparations.sqlite3'
        self.state=Path(profile['roots']['state']); self.ledger=Path(profile['roots']['lock'])/'dispatch_fences'
        self.anchor=Path(profile['roots']['lock'])/'submission_store.json'
    def connect(self,write=False):
        if not self.path.exists() and not write: return None
        if write:
            con=StateStore(self.state).connect(True)
        else:
            safe_path(self.path); con=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True,timeout=5)
            con.row_factory=sqlite3.Row; con.execute('PRAGMA foreign_keys=ON'); con.execute('PRAGMA busy_timeout=5000')
        return con
    def initialized(self):
        con=self.connect()
        if con is None: return False
        try: return con.execute("SELECT 1 FROM sqlite_master WHERE name='submission_schema_meta'").fetchone() is not None
        finally: con.close()
    def guard(self,allow_paused=False):
        p=self.profile
        if self.path.exists():
            existing=StateStore(self.state).connect(False)
            existing.close()
        require(allow_paused or (not p['paused_restore'] and not p['paused'] and not any((self.state/name).exists() for name in ('submission.pause','paused_restore'))),'RESTORE_PAUSED',exit_code=9)
        initialized=self.initialized()
        if not initialized:
            require(not self.anchor.exists() and not (self.state/'submissions').exists() and not self.ledger.exists(),'RESTORE_OR_ORPHAN',exit_code=9)
            return
        require(self.anchor.exists(),'RESTORE_OR_ORPHAN',exit_code=9)
        anchor=loads(read_small(self.anchor))
        expected={k:p[k] for k in ('cluster_id','cluster_epoch','state_epoch')}
        require(anchor==expected,'STORE_EPOCH_MISMATCH',exit_code=9)
        con=self.connect()
        try:
            require(con.execute('PRAGMA quick_check').fetchone()[0]=='ok','DB_INTEGRITY',exit_code=5)
            meta=con.execute('SELECT * FROM submission_schema_meta').fetchall()
            require(len(meta)==1 and meta[0]['version']==1 and all(meta[0][k]==p[k] for k in expected)
                    and meta[0]['owner']==p['expected_owner']['name'],'STORE_EPOCH_MISMATCH',exit_code=9)
            registered=con.execute('SELECT sha256 FROM submission_profiles WHERE id=? AND revision=?',(p['id'],p['revision'])).fetchone()
            require(allow_paused or registered is None or registered[0]==digest('submission-profile-v1',p),'PROFILE_REVISION_CONFLICT',exit_code=9)
            rows={r['intent_id']:dict(r) for r in con.execute('SELECT * FROM submission_intents')}
        finally: con.close()
        base=self.state/'submissions'
        if base.exists():
            entries=list(base.iterdir()); require(len(entries)<=1000,'STATE_INVENTORY_LIMIT',exit_code=9)
            for directory in entries:
                safe_path(directory); require(directory.is_dir() and directory.name in rows,'RESTORE_OR_ORPHAN',exit_code=9)
                if (directory/'dispatch_result.json').exists(): require(rows[directory.name]['dispatch_fence']==1,'RESTORE_OR_ORPHAN',exit_code=9)
        if self.ledger.exists():
            files=list(self.ledger.iterdir()); require(len(files)<=1000,'STATE_INVENTORY_LIMIT',exit_code=9)
            for path in files:
                safe_path(path)
                require(path.suffix=='.json' and path.stem in rows and rows[path.stem]['dispatch_fence']==1,'RESTORE_OR_ORPHAN',exit_code=9)
                record=loads(read_small(path))
                require(record==dict(intent_id=path.stem,request_digest=rows[path.stem]['request_digest'],state_epoch=p['state_epoch']),'RESTORE_OR_ORPHAN',exit_code=9)
    def initialize(self):
        if self.initialized(): return
        self.guard()
        private_dir(self.profile['roots']['lock'])
        write_new(self.anchor,canonical({k:self.profile[k] for k in ('cluster_id','cluster_epoch','state_epoch')}))
        fsync_dir(self.anchor.parent)
        con=self.connect(True)
        try:
            con.executescript(SQL)
            with con:
                p=self.profile
                con.execute('INSERT INTO submission_schema_meta VALUES (1,?,?,?,?,?,?)',(p['cluster_id'],p['cluster_epoch'],p['state_epoch'],p['expected_owner']['name'],time.time(),'step1_3_v1'))
        finally: con.close()
    def lookup(self,request_id=None,intent_id=None):
        if not self.initialized(): return None
        con=self.connect()
        try:
            if request_id:
                row=con.execute('SELECT i.*,b.job_id,r.request_digest AS alias_digest FROM submission_requests r JOIN submission_intents i ON r.intent_id=i.intent_id LEFT JOIN scheduler_bindings b ON b.intent_id=i.intent_id WHERE r.request_id=?',(request_id,)).fetchone()
            else:
                row=con.execute('SELECT i.*,b.job_id FROM submission_intents i LEFT JOIN scheduler_bindings b ON b.intent_id=i.intent_id WHERE i.intent_id=?',(intent_id,)).fetchone()
            return dict(row) if row else None
        finally: con.close()
    def find(self,plan):
        if not self.initialized(): return None
        request=loads(plan.request_json); con=self.connect()
        try:
            row=con.execute('SELECT i.*,b.job_id FROM submission_intents i LEFT JOIN scheduler_bindings b ON b.intent_id=i.intent_id WHERE i.cluster_id=? AND i.cluster_epoch=? AND (i.calculation_key=? OR i.bundle_key=? OR (i.calculation_id=? AND i.stage_id=?) OR i.intent_id IN (SELECT intent_id FROM submission_requests WHERE label=? AND stage_id=?))',
              (self.profile['cluster_id'],self.profile['cluster_epoch'],plan.calculation_key,plan.bundle_key,request['calculation_id'],request['stage_id'],request['calculation_id'],request['stage_id'])).fetchall()
            require(len({r['intent_id'] for r in row})<=1,'IDENTITY_CONFLICT',exit_code=7)
            return dict(row[0]) if row else None
        finally: con.close()
    def all_intents(self):
        if not self.initialized(): return []
        con=self.connect()
        try: return [dict(r) for r in con.execute('SELECT i.*,b.job_id FROM submission_intents i LEFT JOIN scheduler_bindings b ON b.intent_id=i.intent_id ORDER BY i.created_at')]
        finally: con.close()
    def alias(self,request,row):
        con=self.connect(True)
        try:
            with con:
                existing=con.execute('SELECT * FROM submission_requests WHERE request_id=?',(request['request_id'],)).fetchone()
                if existing:
                    require(existing['request_digest']==row['request_digest'],'REQUEST_ID_CONFLICT',exit_code=7); return False
                con.execute('INSERT INTO submission_requests VALUES (?,?,?,?,?,?)',(request['request_id'],row['request_digest'],row['intent_id'],request['calculation_id'],request['stage_id'],time.time()))
                return True
        finally: con.close()
    def create_or_get_intent(self,plan):
        self.initialize(); request=loads(plan.request_json)
        existing=self.lookup(request_id=request['request_id']) or self.find(plan)
        if existing:
            require(existing['request_digest']==plan.request_digest,'IDENTITY_CONFLICT',exit_code=7)
            self.alias(request,existing); return existing
        intent_id=uuid.uuid4().hex; run_id=str(uuid.uuid4()); token=secrets.token_hex(16); now=time.time()
        bundle=loads(plan.bundle.manifest_json); p=self.profile
        record=dict(schema_version=1,intent_id=intent_id,run_instance_id=run_id,token=token,cluster_id=p['cluster_id'],cluster_epoch=p['cluster_epoch'],owner=p['expected_owner']['name'],
                    request_digest=plan.request_digest,manifest_sha256=plan.bundle.manifest_sha256,bundle_path=plan.bundle.path,calculation_key=plan.calculation_key,bundle_key=plan.bundle_key,
                    config_sha256=plan.config_sha256,profile=p,execution_report=loads(plan.execution_json),created_at=now,request=request)
        con=self.connect(True)
        try:
            with con:
                con.execute('INSERT OR IGNORE INTO submission_profiles VALUES (?,?,?)',(p['id'],p['revision'],digest('submission-profile-v1',p)))
                registered=con.execute('SELECT sha256 FROM submission_profiles WHERE id=? AND revision=?',(p['id'],p['revision'])).fetchone()
                require(registered[0]==digest('submission-profile-v1',p),'PROFILE_REVISION_CONFLICT',exit_code=9)
                con.execute('INSERT INTO submission_intents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                 (intent_id,p['cluster_id'],p['cluster_epoch'],p['expected_owner']['name'],bundle['identity']['calculation_id'],request['stage_id'],plan.calculation_key,plan.bundle_key,plan.request_digest,run_id,token,'SUBMIT_PENDING',0,0,now,None,now,32,0,canonical(record).decode()))
                con.execute('INSERT INTO submission_requests VALUES (?,?,?,?,?,?)',(request['request_id'],plan.request_digest,intent_id,request['calculation_id'],request['stage_id'],now))
                con.execute('INSERT INTO submission_events VALUES (NULL,?,?,?,?,?)',(intent_id,None,'SUBMIT_PENDING','INTENT',now))
        except sqlite3.IntegrityError:
            raise InputError('IDENTITY_COLLISION',exit_code=7) from None
        finally: con.close()
        return self.lookup(intent_id=intent_id)
    def arm_dispatch(self,intent_id,expected_version,command_json,command_digest,admission):
        con=self.connect(True); now=time.time()
        try:
            with con:
                changed=con.execute("UPDATE submission_intents SET state='DISPATCH_ARMED',dispatch_fence=1,version=version+1,armed_at=?,updated_at=? WHERE intent_id=? AND state='SUBMIT_PENDING' AND dispatch_fence=0 AND version=?",(now,now,intent_id,expected_version)).rowcount
                require(changed==1,'FENCE_CAS_FAILED',exit_code=9)
                con.execute('INSERT INTO submission_attempts VALUES (?,1,?,?,?,NULL,NULL)',(intent_id,command_digest,command_json,now))
                con.execute('INSERT INTO admission_records VALUES (?,?,?)',(uuid.uuid4().hex,intent_id,canonical(admission).decode()))
                con.execute('INSERT INTO submission_events VALUES (NULL,?,?,?,?,?)',(intent_id,'SUBMIT_PENDING','DISPATCH_ARMED','FENCE',now))
        finally: con.close()
        # Only this post-commit call stack receives the capability.
        return DispatchPermit(intent_id,command_digest=command_digest)
    def attempt(self,intent_id):
        con=self.connect()
        try:
            row=con.execute('SELECT * FROM submission_attempts WHERE intent_id=?',(intent_id,)).fetchone(); return dict(row) if row else None
        finally: con.close()
    def transition(self,row,state,reason,job=None,evidence=None,terminal=False,scheduler_time=None):
        con=self.connect(True); now=time.time()
        try:
            with con:
                changed=con.execute('UPDATE submission_intents SET state=?,version=version+1,updated_at=?,terminal_observed=? WHERE intent_id=? AND version=?',
                    (state,now,int(terminal or row['terminal_observed']),row['intent_id'],row['version'])).rowcount
                require(changed==1,'STATE_CAS_FAILED',exit_code=9)
                if job:
                    old=con.execute('SELECT job_id FROM scheduler_bindings WHERE intent_id=?',(row['intent_id'],)).fetchone()
                    require(old is None or old[0]==job,'IDENTITY_CONFLICT',exit_code=7)
                    con.execute('INSERT OR IGNORE INTO scheduler_bindings VALUES (?,?,?,?,?,?,?)',(row['intent_id'],row['cluster_id'],row['cluster_epoch'],job,row['owner'],scheduler_time if scheduler_time is not None else row['armed_at'],evidence))
                con.execute('INSERT INTO submission_events VALUES (NULL,?,?,?,?,?)',(row['intent_id'],row['state'],state,reason,now))
                if evidence and reason in ('QSUB_OUTCOME','DURABLE_RECEIPT'): con.execute('UPDATE submission_attempts SET receipt_sha256=?,finished_at=? WHERE intent_id=?',(evidence,now,row['intent_id']))
        finally: con.close()
        return self.lookup(intent_id=row['intent_id'])
    def observation(self,row,source,match,evidence):
        con=self.connect(True)
        try:
            with con: con.execute('INSERT INTO scheduler_observations VALUES (?,?,?,?,?,?)',(uuid.uuid4().hex,row['intent_id'],time.time(),source,match,evidence))
        finally: con.close()
