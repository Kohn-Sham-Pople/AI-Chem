import json
import os
import sqlite3
import pytest
from pathlib import Path
from support import setup,tree
from ai_chem_input.prepare import *
from ai_chem_input.state import StateStore
from ai_chem_input.errors import InputError

@pytest.mark.parametrize('point',['snapshot:INCAR','snapshot:POSCAR','snapshot:POTCAR','snapshot:KPOINTS','snapshot:run.sh','input:INCAR','input:POSCAR','input:POTCAR','input:KPOINTS','input:run.sh','provenance/resolved_config.json','provenance/validation.json'])
def test_copy_fault_preserves_source(tmp_path,point):
    req,reg,_=setup(tmp_path); plan=build_plan((req,reg)); before=tree(tmp_path/'research')
    def fail(name):
        if name==point: raise OSError(28,'synthetic ENOSPC')
    with pytest.raises(OSError): materialize(plan,fault=fail)
    assert not Path(plan.final_dir).exists() and tree(tmp_path/'research')==before


def test_changed_config(tmp_path):
    req,reg,_=setup(tmp_path); plan=build_plan((req,reg)); path=Path(plan.config_pins[0][0]); path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(InputError) as exc: materialize(plan)
    assert exc.value.code=='CONFIG_CHANGED' and not (tmp_path/'output').exists()


def test_sqlite_foreign_keys(tmp_path):
    store=StateStore(tmp_path/'state'); con=store.connect(True)
    with pytest.raises(sqlite3.IntegrityError):
        with con: con.execute('INSERT INTO attempts VALUES (?,?,?,?,?,?,?)',('x','no','no','stage','now',None,None))
    con.close()

@pytest.mark.parametrize('change',['missing_manifest','missing_ready','missing_potcar','manifest_traversal','omitted_payload','modified_snapshot','new_input'])
def test_verify_tampering(tmp_path,change):
    req,reg,_=setup(tmp_path); plan=build_plan((req,reg)); materialize(plan); final=Path(plan.final_dir)
    if change.startswith('missing_'):
        target={'missing_manifest':'provenance/manifest.json','missing_ready':'READY.json','missing_potcar':'POTCAR'}[change]; (final/target).unlink()
    elif change=='modified_snapshot': (final/'provenance/source/POSCAR').write_bytes(b'bad')
    elif change=='new_input':
        # Unknown extra VASP outputs are allowed but cannot replace a required input.
        (final/'OUTCAR').write_bytes(b'synthetic future output'); (final/'INCAR').unlink()
    else:
        mf=final/'provenance/manifest.json'; m=loads(mf.read_bytes())
        if change=='manifest_traversal': m['payload_files']['../unsafe']=m['payload_files']['INCAR']
        else: del m['payload_files']['POTCAR']
        mf.write_bytes(canonical(m)); ready=loads((final/'READY.json').read_bytes()); ready['manifest_sha256']=sha256(mf.read_bytes()); (final/'READY.json').write_bytes(canonical(ready))
    with pytest.raises((InputError,OSError)): verify_bundle(final)


def test_ready_db_but_missing_final(tmp_path):
    req,reg,_=setup(tmp_path); plan=build_plan((req,reg)); materialize(plan)
    Path(plan.final_dir).rename(Path(plan.final_dir+'-preserved'))
    with pytest.raises(InputError) as exc: materialize(plan)
    assert exc.value.exit_code==5


def test_deadline_no_writes(tmp_path):
    req,reg,_=setup(tmp_path); before=tree(tmp_path)
    with pytest.raises(InputError) as exc: build_plan((req,reg),deadline=0)
    assert exc.value.code=='DEADLINE' and tree(tmp_path)==before


def test_real_rename_failure_and_midcopy(tmp_path,monkeypatch):
    import ai_chem_input.prepare as prep
    req,reg,_=setup(tmp_path); plan=build_plan((req,reg)); before=tree(tmp_path/'research')
    original=prep.os.rename
    def fail(*args,**kwargs): raise OSError(28,'synthetic rename failure')
    monkeypatch.setattr(prep.os,'rename',fail)
    with pytest.raises(OSError): materialize(plan)
    assert not Path(plan.final_dir).exists() and tree(tmp_path/'research')==before
    monkeypatch.setattr(prep.os,'rename',original)
    import ai_chem_input.paths as paths
    inspect_original=paths.inspect
    def partial(path,expected=None,dest=None,**kw):
        if dest is not None:
            dest.write(b'partial synthetic bytes'); raise OSError(28,'synthetic partial write')
        return inspect_original(path,expected,dest,**kw)
    monkeypatch.setattr(paths,'inspect',partial)
    with pytest.raises(OSError): materialize(plan)
    assert not Path(plan.final_dir).exists() and tree(tmp_path/'research')==before


def test_unexpected_corruption_before_payload(tmp_path):
    req,reg,_=setup(tmp_path); plan=build_plan((req,reg))
    def corrupt(name):
        if name=='input:KPOINTS':
            staging=next((tmp_path/'output/.staging').iterdir()); incar=staging/'INCAR'
            incar.write_bytes(incar.read_bytes()+b'! silent extra comment\n')
    with pytest.raises(InputError): materialize(plan,fault=corrupt)
    assert not Path(plan.final_dir).exists()


def test_manifest_anchor_cannot_be_silently_replaced(tmp_path):
    req,reg,_=setup(tmp_path); plan=build_plan((req,reg)); materialize(plan); final=Path(plan.final_dir)
    path=final/'provenance/manifest.json'; m=loads(path.read_bytes()); m['generation']['created_at']='changed'
    path.write_bytes(canonical(m)); ready_path=final/'READY.json'; ready=loads(ready_path.read_bytes()); ready['manifest_sha256']=sha256(path.read_bytes()); ready_path.write_bytes(canonical(ready))
    # Standalone hash chain is internally consistent; the retained DB anchor detects replacement.
    assert verify_bundle(final)
    with pytest.raises(InputError) as exc: materialize(plan)
    assert exc.value.code=='PACKAGE_TAMPERED'
