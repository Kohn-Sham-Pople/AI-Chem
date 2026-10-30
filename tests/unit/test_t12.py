import ast
from pathlib import Path
from support import setup
from ai_chem_input.prepare import build_plan
from ai_chem_input.provenance import sha256,digest


def test_independent_goldens(tmp_path):
    req,reg,_=setup(tmp_path); plan=build_plan((req,reg)); fixture=Path('tests/fixtures/synthetic')
    assert dict(plan.generated)['INCAR']==(fixture/'expected_f_INCAR').read_bytes()
    expected=(fixture/'expected_run.sh.txt').read_text().replace('@ROOT@',str(tmp_path)).replace('@DIGEST24@',plan.request_digest[:24])
    assert dict(plan.generated)['run.sh'].decode()==expected


def test_repo_synthetic_only():
    # The only potential bodies in the repository must be hand-authored mocks.
    for p in Path('.').rglob('POTCAR'):
        assert 'tests/fixtures/synthetic' in str(p)
        assert p.read_bytes().startswith(b'SYNTHETIC TEST ONLY\n')
    for p in Path('src/ai_chem_input').glob('*.py'):
        tree=ast.parse(p.read_text())
        imports=[node.names[0].name for node in ast.walk(tree) if isinstance(node,ast.Import)]
        assert not set(imports)&{'subprocess','socket','urllib','http','requests','paramiko'}


def test_raw_hash_distinct():
    assert sha256(b'EDIFF=1D-6\r\n')!=sha256(b'EDIFF=1E-06\n')


def test_hash_domains_and_volatile_roots(tmp_path):
    import copy
    from ai_chem_input.config import loads
    from ai_chem_input.provenance import canonical
    from ai_chem_input.validators import semantic_tag_value
    from ai_chem_input.registry import Registry
    req,reg,e=setup(tmp_path/'one'); first=build_plan((req,reg))
    req2,reg2,e2=setup(tmp_path/'two'); second=build_plan((req2,reg2))
    assert loads(first.science_json)==loads(second.science_json)
    assert first.request_digest!=second.request_digest  # profile execution locations differ
    assert semantic_tag_value('ENCUT','400')==semantic_tag_value('ENCUT','4D2')
    assert semantic_tag_value('MAGMOM','2*1.0')==semantic_tag_value('MAGMOM','1 1')
    m=copy.deepcopy(e['material']); m['revision']=2; m['u_sets'][0]['by_block']['b0']['u_eV']='5'
    reg.register('material',m,sha256(canonical(m))); req['material']['revision']=2
    third=build_plan((req,reg))
    assert loads(first.science_json)['method_hash']!=loads(third.science_json)['method_hash']
    assert loads(first.science_json)['stage_input_hash']!=loads(third.science_json)['stage_input_hash']
