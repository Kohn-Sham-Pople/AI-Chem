import copy
import pytest
from support import setup
from ai_chem_input.prepare import build_plan
from ai_chem_input.incar import parse_incar
from ai_chem_input.script import validate_profile,safe_token
from ai_chem_input.validators import validate_inputs
from ai_chem_input.errors import InputError

@pytest.mark.parametrize('shell',['f','d'])
def test_protocol(tmp_path,shell):
    req,reg,entities=setup(tmp_path,shell); plan=build_plan((req,reg)); tags=parse_incar(dict(plan.generated)['INCAR']).tags
    assert tags['EDIFF']==('1E-04' if shell=='f' else '1E-06')
    assert tags['LMAXMIX']==('6' if shell=='f' else '4') and tags['ISTART']=='0'
    assert 'ICHARG' not in tags
    assert (tags.get('NELM')=='300') if shell=='f' else ('NELM' not in tags)
    assert tags['MAGMOM']=='1 -1'
    script=dict(plan.generated)['run.sh'].decode()
    assert script.count('#$ -q all.q')==1 and script.count('#$ -pe mpi_32 32')==1
    assert '"$NSLOTS"' in script and 'LD_LIBRARY_PATH=' in script

@pytest.mark.parametrize('value',['x\ny','$(id)','`id`',"a'b",''])
def test_script_injection(value):
    with pytest.raises(InputError): safe_token(value)

@pytest.mark.parametrize('edit',[lambda p:p.update(slots=64),lambda p:p['environment'].update(library_dirs=['.']),lambda p:p['launcher'].update(args=['-np']),lambda p:p['vasp'].update(path='/not/there')])
def test_profile(tmp_path,edit):
    _,_,entities=setup(tmp_path); p=copy.deepcopy(entities['profile']); edit(p)
    with pytest.raises(InputError): validate_profile(p)

@pytest.mark.parametrize('stage',['s02_e5','s03_e6'])
def test_restart_closed(tmp_path,stage):
    req,reg,_=setup(tmp_path); req['stage_id']=stage
    with pytest.raises(InputError) as e: build_plan((req,reg))
    assert e.value.exit_code==4 and not (tmp_path/'output').exists()


def test_unapproved_malicious_source_blocked(tmp_path):
    req,reg,e=setup(tmp_path)
    from pathlib import Path
    src=Path(e['template']['source_dir'])/'run.sh'
    src.write_bytes(b'#!/bin/bash\nqsub bad\nrm -rf bad\n')
    with pytest.raises(InputError) as exc: build_plan((req,reg))
    assert exc.value.code=='SOURCE_CHANGED' and not (tmp_path/'output').exists()
