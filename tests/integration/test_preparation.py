import os
import copy
import socket
import subprocess
import pytest
from support import setup
from ai_chem_input.prepare import *
from ai_chem_input.state import StateStore,global_lock
from ai_chem_input.errors import InputError


def tree(root):
    return {str(p.relative_to(root)):(p.read_bytes(),p.stat().st_mode,p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}

@pytest.mark.parametrize('shell',['f','d'])
def test_end_to_end(tmp_path,shell,monkeypatch):
    request,registry,entities=setup(tmp_path,shell)
    def forbidden(*a,**kw): raise AssertionError('external invocation forbidden')
    monkeypatch.setattr(subprocess,'Popen',forbidden); monkeypatch.setattr(socket,'socket',forbidden)
    before=tree(tmp_path); plan=build_plan((request,registry)); assert tree(tmp_path)==before
    source=tree(tmp_path/'research'); response=materialize(plan); assert response['result']=='INPUT_READY'
    final=Path(plan.final_dir); assert verify_bundle(final)['request_digest']==plan.request_digest
    assert tree(tmp_path/'research')==source
    for name in FILES:
        assert (final/'provenance/source'/name).read_bytes()==(tmp_path/'research'/shell/name).read_bytes()
        assert (final/name).stat().st_ino!=(tmp_path/'research'/shell/name).stat().st_ino
    before=tree(tmp_path)
    request['request_id']='redelivery'; again=build_plan((request,registry)); assert again.request_digest==plan.request_digest
    assert materialize(again)['result']=='IDEMPOTENT_EXISTING'; assert tree(tmp_path)==before
    (final/'INCAR').write_bytes((final/'INCAR').read_bytes()+b'! tampered\n')
    with pytest.raises(InputError): materialize(plan)

@pytest.mark.parametrize('point',['intent','snapshot:POTCAR','before_manifest','before_ready','ready','before_rename','renamed','db_success'])
def test_crash_reconciliation(tmp_path,point):
    request,registry,_=setup(tmp_path); plan=build_plan((request,registry)); before=tree(tmp_path/'research')
    def crash(name):
        if name==point: raise OSError('synthetic crash')
    with pytest.raises(OSError): materialize(plan,fault=crash)
    if point in ('renamed','db_success'): assert Path(plan.final_dir).exists()
    else: assert not Path(plan.final_dir).exists()
    assert materialize(plan)['result'] in ('INPUT_READY','IDEMPOTENT_EXISTING')
    assert tree(tmp_path/'research')==before


def test_stale_source_config_and_busy(tmp_path):
    request,reg,e=setup(tmp_path); plan=build_plan((request,reg))
    with global_lock(e['profile']['roots']['lock']):
        with pytest.raises(InputError) as exc: materialize(plan)
        assert exc.value.exit_code==6
    source=Path(e['template']['source_dir'])/'INCAR'; source.write_bytes(source.read_bytes()+b'\n')
    with pytest.raises(InputError): materialize(plan)
    assert not (tmp_path/'output').exists() and not (tmp_path/'state').exists()


def test_identity_conflict(tmp_path):
    request,reg,e=setup(tmp_path); plan=build_plan((request,reg)); materialize(plan)
    value=copy.deepcopy(e['material']); value['revision']=2; value['u_sets'][0]['by_block']['b0']['u_eV']='5'
    reg.register('material',value,sha256(canonical(value)))
    request['material']['revision']=2; other=build_plan((request,reg))
    with pytest.raises(InputError) as exc: materialize(other)
    assert exc.value.exit_code==7


def test_two_process_writers(tmp_path):
    import multiprocessing
    req,reg,_=setup(tmp_path); plan=build_plan((req,reg))
    context=multiprocessing.get_context('fork'); barrier=context.Barrier(2); q=context.Queue()
    def writer():
        barrier.wait()
        try: q.put(materialize(plan)['result'])
        except InputError as exc: q.put(exc.code)
    procs=[context.Process(target=writer) for _ in range(2)]
    for p in procs: p.start()
    for p in procs:
        p.join(10); assert p.exitcode==0
    outcomes=[q.get(timeout=2) for _ in procs]
    assert outcomes.count('INPUT_READY')==1
    assert set(outcomes)<= {'INPUT_READY','IDEMPOTENT_EXISTING','BUSY'}
    assert verify_bundle(Path(plan.final_dir))
