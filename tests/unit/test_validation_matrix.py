import copy
from pathlib import Path
import pytest
from support import setup
from ai_chem_input.provenance import canonical,sha256
from ai_chem_input.prepare import build_plan
from ai_chem_input.validators import validate_inputs
from ai_chem_input.potcar import inspect_potcar
from ai_chem_input.incar import parse_incar,patch_incar,Patch
from ai_chem_input.errors import InputError


def revise(reg,request,kind,value):
    value=copy.deepcopy(value); value['revision']=2
    reg.register(kind,value,sha256(canonical(value)))
    request[{'profile':'cluster_profile'}.get(kind,kind)]['revision']=2
    return value

@pytest.mark.parametrize('edit,code',[
    (lambda m:m['species_blocks'][0].update(count=2),'SPECIES_MISMATCH'),
    (lambda m:m['species_blocks'][0].update(element='Cu'),'SPECIES_MISMATCH'),
    (lambda m:m['species_blocks'][0].update(potential_variant='Eu_frozen'),'POTENTIAL_MISMATCH'),
    (lambda m:m['species_blocks'][0].update(dataset_sha256='f'*64),'POTENTIAL_MISMATCH'),
    (lambda m:m['species_blocks'][1].update(block_id='b0'),'SPECIES_MISMATCH'),
    (lambda m:m['u_sets'][0]['by_block'].pop('b0'),'LDAU_MAPPING_INVALID'),
    (lambda m:m['u_sets'][0]['by_block'].update(extra=dict(l=-1,u_eV='0',j_eV='0')),'LDAU_MAPPING_INVALID'),
    (lambda m:m['u_sets'][0]['by_block']['b0'].update(l=2),'LDAU_MAPPING_INVALID'),
    (lambda m:m['u_sets'][0].update(ldautype=3),'LDAU_MAPPING_INVALID'),
    (lambda m:m['configurations'][0]['magmom_by_atom'].pop(),'MAGMOM_COUNT'),
    (lambda m:m['configurations'][0]['magmom_by_atom'][1].update(atom_index=1),'MAGMOM_COUNT'),
    (lambda m:m['configurations'][0].update(spin_mode='noncollinear'),'MAGMOM_COUNT'),
    (lambda m:m['configurations'][0].update(soc=True),'SPIN_MODE_CONFLICT'),
    (lambda m:m['method'].update(kpoints_sha256='f'*64),'KPOINTS_MISMATCH')])
def test_mapping_failures(tmp_path,edit,code):
    req,reg,e=setup(tmp_path); m=copy.deepcopy(e['material']); edit(m); revise(reg,req,'material',m)
    before={str(p):p.read_bytes() for p in (tmp_path/'research').rglob('*') if p.is_file()}
    with pytest.raises(InputError) as exc: build_plan((req,reg))
    assert exc.value.code==code
    assert not (tmp_path/'output').exists() and not (tmp_path/'state').exists()
    assert before=={str(p):p.read_bytes() for p in (tmp_path/'research').rglob('*') if p.is_file()}

@pytest.mark.parametrize('value,code',[('1','MAGMOM_COUNT'),('1 -1 0','MAGMOM_COUNT'),('-1 1','MAGMOM_MAPPING')])
def test_generated_magmom(tmp_path,value,code):
    req,reg,e=setup(tmp_path); p=build_plan((req,reg)); inputs=dict(p.generated)
    inputs['INCAR']=patch_incar(parse_incar(inputs['INCAR']),[Patch('MAGMOM',value)])
    with (Path(e['template']['source_dir'])/'POTCAR').open('rb') as f: potentials=inspect_potcar(f)
    with pytest.raises(InputError) as exc: validate_inputs(dict(e,request=req,potentials=potentials),inputs)
    assert exc.value.code==code


def test_schema_and_runtime_identical():
    from ai_chem_input.config import checked,loads
    for path in Path('schemas').glob('*.json'):
        if '.draft.' in path.name: continue
        assert path.read_bytes()==(Path('src/ai_chem_input/schemas')/path.name).read_bytes()
    # all runtime modules parse using the Python 3.9 grammar
    import ast
    for path in Path('src').rglob('*.py'): ast.parse(path.read_text(),feature_version=(3,9))


def test_noncollinear_soc_positive_and_scalar_rejection(tmp_path):
    from ai_chem_input.paths import inspect
    from ai_chem_input.discovery import inventory
    req,reg,e=setup(tmp_path)
    source=Path(e['template']['source_dir']); incar=source/'INCAR'
    incar.write_bytes(incar.read_bytes()+b'LNONCOLLINEAR = .TRUE.\nLSORBIT = .TRUE.\nSAXIS = 0 0 1\n')
    m=copy.deepcopy(e['material']); m['method']['incar_tags'].update(LNONCOLLINEAR='.TRUE.',LSORBIT='.TRUE.',SAXIS='0 0 1')
    c=m['configurations'][0]; c.update(spin_mode='noncollinear',soc=True,saxis=['0','0','1'],magmom_by_atom=[dict(atom_index=1,vector=['0','0','1']),dict(atom_index=2,vector=['0','0','-1'])])
    revise(reg,req,'material',m)
    t=copy.deepcopy(e['template']); t['files']=inventory(source)['files']; revise(reg,req,'template',t)
    plan=build_plan((req,reg)); assert parse_incar(dict(plan.generated)['INCAR']).tags['MAGMOM']=='0 0 1 0 0 -1'
    inputs=dict(plan.generated); inputs['INCAR']=patch_incar(parse_incar(inputs['INCAR']),[Patch('MAGMOM','1 -1')])
    with (source/'POTCAR').open('rb') as f: potentials=inspect_potcar(f)
    with pytest.raises(InputError) as exc: validate_inputs(dict(e,material=m,template=t,request=req,potentials=potentials),inputs)
    assert exc.value.code=='MAGMOM_COUNT'


def test_static_calculation_not_silently_repaired(tmp_path):
    from ai_chem_input.discovery import inventory
    req,reg,e=setup(tmp_path); source=Path(e['template']['source_dir']); incar=source/'INCAR'
    incar.write_bytes(incar.read_bytes().replace(b'NSW = 0',b'NSW = 5'))
    m=copy.deepcopy(e['material']); m['method']['incar_tags']['NSW']='5'; revise(reg,req,'material',m)
    t=copy.deepcopy(e['template']); t['files']=inventory(source)['files']; revise(reg,req,'template',t)
    with pytest.raises(InputError) as exc: build_plan((req,reg))
    assert exc.value.code=='UNSUPPORTED_CALCULATION'
