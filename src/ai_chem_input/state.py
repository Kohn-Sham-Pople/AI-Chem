import fcntl
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from .errors import require, InputError
from .paths import private_dir, safe_path

SQL='''
CREATE TABLE IF NOT EXISTS schema_meta(schema_version INTEGER PRIMARY KEY,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS preparations(
 calculation_id TEXT NOT NULL,stage_id TEXT NOT NULL,request_id TEXT NOT NULL,
 request_digest TEXT NOT NULL,state TEXT NOT NULL,final_relpath TEXT NOT NULL,
 manifest_sha256 TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
 PRIMARY KEY(calculation_id,stage_id));
CREATE TABLE IF NOT EXISTS attempts(
 attempt_id TEXT PRIMARY KEY,calculation_id TEXT NOT NULL,stage_id TEXT NOT NULL,
 staging_relpath TEXT NOT NULL,start TEXT NOT NULL,end TEXT,error_code TEXT,
 FOREIGN KEY(calculation_id,stage_id) REFERENCES preparations(calculation_id,stage_id));
CREATE TABLE IF NOT EXISTS preparation_events(
 event_id INTEGER PRIMARY KEY,calculation_id TEXT NOT NULL,stage_id TEXT NOT NULL,
 previous_state TEXT,new_state TEXT NOT NULL,timestamp TEXT NOT NULL,actor TEXT NOT NULL,
 issue_code TEXT,detail_digest TEXT,
 FOREIGN KEY(calculation_id,stage_id) REFERENCES preparations(calculation_id,stage_id));
'''


@contextmanager
def global_lock(root):
    root=private_dir(root); path=safe_path(root/'controller.lock')
    fd=os.open(str(path),os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise InputError('BUSY',exit_code=6) from None
        yield
    finally: os.close(fd)


class StateStore:
    def __init__(self,root): self.root=Path(root); self.path=self.root/'preparations.sqlite3'
    def connect(self,write=False):
        if write: private_dir(self.root)
        safe_path(self.path)
        if not write and not self.path.exists(): return None
        con=sqlite3.connect(str(self.path) if write else self.path.as_uri()+'?mode=ro',uri=not write,timeout=5)
        con.row_factory=sqlite3.Row
        con.execute('PRAGMA foreign_keys=ON'); con.execute('PRAGMA busy_timeout=5000')
        if write:
            con.execute('PRAGMA synchronous=FULL'); con.execute('PRAGMA journal_mode=DELETE')
            con.executescript(SQL)
            con.execute("INSERT OR IGNORE INTO schema_meta VALUES (1,datetime('now'))"); con.commit()
            os.chmod(self.path,0o600)
        try:
            require([r[0] for r in con.execute('SELECT schema_version FROM schema_meta')]==[1],'DB_SCHEMA',exit_code=5)
        except BaseException:
            con.close(); raise
        return con
    def lookup(self,request):
        con=self.connect()
        if con is None: return None
        try:
            require(con.execute('PRAGMA quick_check').fetchone()[0]=='ok','DB_INTEGRITY',exit_code=5)
            return con.execute('SELECT * FROM preparations WHERE calculation_id=? AND stage_id=?',(request['calculation_id'],request['stage_id'])).fetchone()
        finally: con.close()
    def intent(self,request,digest,attempt):
        con=self.connect(True); key=(request['calculation_id'],request['stage_id']); now=str(time.time())
        try:
            with con:
                row=con.execute('SELECT * FROM preparations WHERE calculation_id=? AND stage_id=?',key).fetchone()
                require(row is None or row['request_digest']==digest,'IDENTITY_CONFLICT',exit_code=7)
                old=row['state'] if row else None
                if row:
                    con.execute('UPDATE attempts SET end=?,error_code=? WHERE calculation_id=? AND stage_id=? AND end IS NULL',
                                (now,'ABANDONED')+key)
                if row: con.execute('UPDATE preparations SET state=?,updated_at=? WHERE calculation_id=? AND stage_id=?',('PREPARING',now)+key)
                else: con.execute('INSERT INTO preparations VALUES (?,?,?,?,?,?,?,?,?)',key+(request['request_id'],digest,'PREPARING','/'.join(key),None,now,now))
                con.execute('INSERT INTO attempts VALUES (?,?,?,?,?,?,?)',(attempt,)+key+('.staging/'+attempt,now,None,None))
                con.execute('INSERT INTO preparation_events VALUES (NULL,?,?,?,?,?,?,?,?)',key+(old,'PREPARING',now,'local',None,digest))
        finally: con.close()
    def ready(self,request,manifest_hash,attempt=None):
        con=self.connect(True); key=(request['calculation_id'],request['stage_id']); now=str(time.time())
        try:
            with con:
                old=con.execute('SELECT state FROM preparations WHERE calculation_id=? AND stage_id=?',key).fetchone()
                require(old is not None,'DB_INTEGRITY',exit_code=5)
                con.execute('UPDATE preparations SET state=?,manifest_sha256=?,updated_at=? WHERE calculation_id=? AND stage_id=?',('INPUT_READY',manifest_hash,now)+key)
                if attempt: con.execute('UPDATE attempts SET end=? WHERE attempt_id=?',(now,attempt))
                con.execute('INSERT INTO preparation_events VALUES (NULL,?,?,?,?,?,?,?,?)',key+(old[0],'INPUT_READY',now,'local',None,None))
        finally: con.close()

    def quarantine(self,request,code):
        con=self.connect(True); key=(request['calculation_id'],request['stage_id']); now=str(time.time())
        try:
            with con:
                old=con.execute('SELECT state FROM preparations WHERE calculation_id=? AND stage_id=?',key).fetchone()
                if old:
                    con.execute('UPDATE preparations SET state=?,updated_at=? WHERE calculation_id=? AND stage_id=?',('QUARANTINED',now)+key)
                    con.execute('INSERT INTO preparation_events VALUES (NULL,?,?,?,?,?,?,?,?)',key+(old[0],'QUARANTINED',now,'local',code,None))
        finally: con.close()
