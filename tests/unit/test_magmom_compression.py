"""Synthetic serialization regressions; no approved real-material moments."""
import copy
from decimal import Decimal
from pathlib import Path

import pytest

from support import setup, tree
from ai_chem_input.cli import main
from ai_chem_input.config import loads
from ai_chem_input.discovery import inventory
from ai_chem_input.errors import InputError
from ai_chem_input.incar import array, parse_incar
from ai_chem_input.potcar import inspect_potcar
from ai_chem_input.prepare import build_plan, materialize, verify_bundle
from ai_chem_input.provenance import canonical, sha256
from ai_chem_input.validators import compress_magmom, validate_inputs, validate_magmom_line_lengths


def configured(root, moments, spin='collinear'):
    """Build an explicitly synthetic cell/configuration, never formula-derived."""
    request, registry, entities = setup(root)
    source = Path(entities['template']['source_dir'])
    count = len(moments)
    counts = [count // 2, count - count // 2]
    poscar = ('SYNTHETIC TEST ONLY -- formatting cell, not a material geometry\n'
              '1\n1 0 0\n0 1 0\n0 0 1\nEu Cu\n' + ' '.join(map(str, counts)) +
              '\nDirect\n' + '0 0 0\n' * count).encode()
    (source / 'POSCAR').write_bytes(poscar)
    scalar_moments = moments if spin == 'collinear' else [value for atom in moments for value in atom]
    incar = source / 'INCAR'
    incar.write_bytes(incar.read_bytes().replace(b'MAGMOM = 2*1',
        ('MAGMOM = ' + ' '.join(scalar_moments)).encode()))
    material = copy.deepcopy(entities['material'])
    material['revision'] = 2
    for block, value in zip(material['species_blocks'], counts):
        block['count'] = value
    material['structures'][0]['sha256'] = sha256(poscar)
    config = material['configurations'][0]
    config.update(structure_sha256=sha256(poscar), spin_mode=spin)
    if spin == 'collinear':
        config['magmom_by_atom'] = [dict(atom_index=i + 1, moment=value) for i, value in enumerate(moments)]
    else:
        config.update(soc=True, saxis=['0', '0', '1'])
        config['magmom_by_atom'] = [dict(atom_index=i + 1, vector=value) for i, value in enumerate(moments)]
        # Deliberately shuffle records: atom_index still specifies POSCAR order.
        config['magmom_by_atom'].reverse()
        tags = dict(LNONCOLLINEAR='.TRUE.', LSORBIT='.TRUE.', SAXIS='0 0 1')
        material['method']['incar_tags'].update(tags)
        with (source / 'INCAR').open('ab') as f:
            f.write(''.join(k + ' = ' + v + '\n' for k, v in tags.items()).encode())
    profile = copy.deepcopy(entities['profile'])
    profile.update(revision=2, run_script_mode='preserve_source')
    for key in ('launcher', 'environment', 'execution_review'):
        profile.pop(key)
    profile['source_script_approval'] = dict(source_run_sha256=sha256((source / 'run.sh').read_bytes()),
                                            approval=copy.deepcopy(profile['approval']))
    template = copy.deepcopy(entities['template'])
    template.update(revision=2, files=inventory(source)['files'])
    template['profile']['revision'] = 2
    for kind, value in [('profile', profile), ('material', material), ('template', template)]:
        registry.register(kind, value, sha256(canonical(value)))
    request['template']['revision'] = request['material']['revision'] = request['cluster_profile']['revision'] = 2
    entities.update(profile=profile, material=material, template=template)
    return request, registry, entities


@pytest.mark.parametrize('moments,expected', [
    (['6'] * 32 + ['0'] * 16 + ['1'] * 16 + ['0'] * 80, '32*6 16*0 16*1 80*0'),
    (['1', '0', '1'], '1 0 1'),
    (['-2', '-2', '2', '2', '-2'], '2*-2 2*2 -2'),
    (['1'], '1'),
    (['0'] * 144, '144*0'),
    (['6.0', '6D0', '6'], '3*6.0'),
    (['-0', '0', '0.0'], '3*-0'),
    (['1.0000000000000000000000000001', '1.0000000000000000000000000002'],
     '1.0000000000000000000000000001 1.0000000000000000000000000002'),
])
def test_only_adjacent_numerically_equal_components_are_compressed(moments, expected):
    before = list(moments)
    result = compress_magmom(moments)
    assert result == expected
    assert array(result) == tuple(Decimal(v.replace('D', 'E')) for v in moments)
    assert moments == before


@pytest.mark.parametrize('moments', [[], ['NaN'], ['Infinity'], ['bad'], ['2*1']])
def test_invalid_moments_are_never_silently_accepted(moments):
    with pytest.raises(InputError):
        compress_magmom(moments)


@pytest.mark.parametrize('fraction_digits,allowed', [(243, True), (244, True), (245, False)])
def test_full_assignment_255_byte_boundary(fraction_digits, allowed):
    value = '0.' + '1' * fraction_digits
    line = ('MAGMOM = ' + value).encode()
    if allowed:
        assert compress_magmom([value]) == value
        assert len(line) <= 255
    else:
        with pytest.raises(InputError) as exc:
            compress_magmom([value])
        assert exc.value.code == 'MAGMOM_LINE_TOO_LONG'
        assert len(line) == 256


@pytest.mark.parametrize('newline', [b'\n', b'\r\n'])
@pytest.mark.parametrize('prefix,suffix', [
    (b'', b' !'), (b'   ', b' #'), (b'ENCUT=400; ', b' !'), (b'', b'; EDIFF=1E-4 !')
])
def test_real_physical_line_counts_prefix_neighbors_comments_and_crlf(newline, prefix, suffix):
    base = prefix + b'MAGMOM = 1 -1' + suffix
    data = base + b'x' * (255 - len(base))
    assert len(data) == 255
    validate_magmom_line_lengths(parse_incar(data + newline))
    with pytest.raises(InputError) as exc:
        validate_magmom_line_lengths(parse_incar(data + b'x' + newline))
    assert exc.value.code == 'MAGMOM_LINE_TOO_LONG'


def test_utf8_comments_use_byte_limit_and_fake_commented_tags_do_not_count():
    data = 'MAGMOM = 1 -1 # ' + 'é' * 121
    assert len(data) < 255 and len(data.encode()) > 255
    with pytest.raises(InputError):
        validate_magmom_line_lengths(parse_incar(data.encode()))
    validate_magmom_line_lengths(parse_incar(b'# MAGMOM = ' + b'0 ' * 200))


def test_continuations_do_not_bypass_logical_assignment_limit():
    data = b'MAGMOM = ' + b' \\\n  '.join([b'1', b'-1'] * 62) + b'\n'
    assert all(len(line) < 255 for line in data.splitlines())
    with pytest.raises(InputError) as exc:
        validate_magmom_line_lengths(parse_incar(data))
    assert exc.value.code == 'MAGMOM_LINE_TOO_LONG'


def test_synthetic_144_atom_preparation_preserves_science_source_and_script(tmp_path):
    moments = ['6'] * 32 + ['0'] * 16 + ['1'] * 16 + ['0'] * 80
    assert len(('MAGMOM = ' + ' '.join(moments)).encode()) == 296
    request, registry, entities = configured(tmp_path, moments)
    before = tree(tmp_path)
    plan = build_plan((request, registry))
    assert tree(tmp_path) == before
    inputs = dict(plan.generated)
    doc = parse_incar(inputs['INCAR'])
    assert doc.tags['MAGMOM'] == '32*6 16*0 16*1 80*0'
    assert array(doc.tags['MAGMOM']) == tuple(Decimal(v) for v in moments)
    assert len(array(doc.tags['MAGMOM'])) == 144
    assert doc.tags['EDIFF'] == '1E-04' and doc.tags['NELM'] == '300'
    assert (doc.tags['LDAUU'], doc.tags['LDAUJ'], doc.tags['LDAUL']) == ('1 2', '0 0', '3 2')
    source = Path(entities['template']['source_dir'])
    assert inputs['run.sh'] == (source / 'run.sh').read_bytes()
    source_before = tree(tmp_path / 'research')
    materialize(plan)
    assert verify_bundle(Path(plan.final_dir))
    assert tree(tmp_path / 'research') == source_before
    assert (Path(plan.final_dir) / 'run.sh').read_bytes() == (source / 'run.sh').read_bytes()
    assert loads(plan.config_json)['material']['configurations'][0]['magmom_by_atom'] == entities['material']['configurations'][0]['magmom_by_atom']


def test_noncollinear_xyz_order_across_atom_boundaries_is_exact(tmp_path):
    vectors = [['0', '0', '1'], ['1', '1', '0'], ['0', '0', '-1'], ['-1', '-1', '-1']]
    request, registry, _ = configured(tmp_path, vectors, 'noncollinear')
    plan = build_plan((request, registry))
    raw = parse_incar(dict(plan.generated)['INCAR']).tags['MAGMOM']
    assert raw == '2*0 3*1 3*0 4*-1'
    assert array(raw) == tuple(Decimal(v) for atom in vectors for v in atom)
    assert len(array(raw)) == 12
    materialize(plan)
    assert verify_bundle(Path(plan.final_dir))


def test_uncompressible_144_atom_request_blocks_all_preparation_writes(tmp_path, capsys):
    request, registry, _ = configured(tmp_path, ['1', '-1'] * 72)
    operator = tmp_path / 'operator.json'
    req_path = tmp_path / 'request.json'
    operator.write_bytes(canonical(dict(schema_version=1, registry=str(registry.root), profile=request['cluster_profile'])))
    req_path.write_bytes(canonical(request))
    before = tree(tmp_path)
    with pytest.raises(InputError) as exc:
        build_plan((request, registry))
    assert exc.value.code == 'MAGMOM_LINE_TOO_LONG'
    assert main(['prepare', '--dry-run', '--config', str(operator), '--request', str(req_path)]) == 3
    assert loads(capsys.readouterr().out)['issue_codes'] == ['MAGMOM_LINE_TOO_LONG']
    assert tree(tmp_path) == before
    for root in ('output', 'state', 'lock'):
        assert not (tmp_path / root).exists()


def test_generated_inline_comment_overflow_is_rejected_before_writes(tmp_path):
    request, registry, entities = configured(tmp_path, ['1', '-1'])
    source = Path(entities['template']['source_dir'])
    data = (source / 'INCAR').read_bytes().replace(b'MAGMOM = 1 -1', b'MAGMOM = 1 -1 !' + b'x' * 250)
    (source / 'INCAR').write_bytes(data)
    template = copy.deepcopy(entities['template'])
    template.update(revision=3, files=inventory(source)['files'])
    registry.register('template', template, sha256(canonical(template)))
    request['template']['revision'] = 3
    before = tree(tmp_path)
    with pytest.raises(InputError) as exc:
        build_plan((request, registry))
    assert exc.value.code == 'MAGMOM_LINE_TOO_LONG'
    assert tree(tmp_path) == before


def test_final_input_validation_checks_actual_line_not_only_expected_compact_value(tmp_path):
    request, registry, entities = configured(tmp_path, ['1', '-1'])
    plan = build_plan((request, registry))
    inputs = dict(plan.generated)
    inputs['INCAR'] = inputs['INCAR'].replace(b'MAGMOM = 1 -1', b'MAGMOM = 1 -1 !' + b'x' * 250)
    source = Path(entities['template']['source_dir'])
    with (source / 'POTCAR').open('rb') as f:
        potentials = inspect_potcar(f)
    with pytest.raises(InputError) as exc:
        validate_inputs(dict(entities, request=request, potentials=potentials), inputs)
    assert exc.value.code == 'MAGMOM_LINE_TOO_LONG'
