import pytest
from ai_chem_input.registry import Registry
from ai_chem_input.discovery import select_candidate,inventory
from ai_chem_input.provenance import canonical,sha256
from ai_chem_input.errors import InputError

def test_immutable(tmp_path):
    r=Registry(tmp_path/'reg'); v=dict(schema_version=1,id='f',revision=1,approval=dict(reviewer='test',approved_at='2026-10-30T00:00:00Z',note='synthetic'),shell_class='f',recipe='open_f_v1')
    h=sha256(canonical(v)); r.register('protocol',v,h)
    assert r.resolve('protocol',{'id':'f','revision':1})[0]==v
    with pytest.raises(FileExistsError): r.register('protocol',v,h)
    with pytest.raises(InputError): r.register('protocol',dict(v,extra=True),h)

def test_discovery(tmp_path):
    with pytest.raises(InputError): inventory(tmp_path)
    with pytest.raises(InputError): select_candidate([{'shell_class':'f','source_dir':'a'},{'shell_class':'f','source_dir':'b'}],'f')


def test_bounded_discovery_and_drift(tmp_path):
    import shutil
    from support import setup,tree
    from ai_chem_input.discovery import discover_templates
    from ai_chem_input.prepare import build_plan
    from pathlib import Path
    req,reg,e=setup(tmp_path); before=tree(tmp_path)
    assert len(discover_templates(e['profile']))==1 and tree(tmp_path)==before
    source=tmp_path/'research'; folder=source/'nested'; folder.mkdir()
    shutil.copytree(source/'f',folder/'f')
    profile=e['profile']; profile['discovery']['recursive']=True
    assert len(discover_templates(profile))==2
    profile['discovery']['max_candidates']=1
    with pytest.raises(InputError): discover_templates(profile)
    profile['discovery']['max_candidates']=100; profile['discovery']['max_depth']=0
    with pytest.raises(InputError): discover_templates(profile)
    (source/'f'/'run.sh').unlink()
    with pytest.raises(InputError): discover_templates(profile)
    assert not (tmp_path/'state').exists()
