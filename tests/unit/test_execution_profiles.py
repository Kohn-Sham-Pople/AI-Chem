"""Execution profile regressions using synthetic executables and source files only."""
import copy
import json
import socket
import subprocess
from pathlib import Path

import pytest

from support import setup, tree
from ai_chem_input.cli import main
from ai_chem_input.config import checked, loads
from ai_chem_input.errors import InputError
from ai_chem_input.prepare import build_plan, materialize, verify_bundle
from ai_chem_input.provenance import canonical, sha256
from ai_chem_input.script import render_script, validate_profile


def reviewed(profile, policy='preserve', machinefile=True, node='all_q'):
    """Test-only approval builder, never an operator auto-approval mechanism."""
    profile = copy.deepcopy(profile)
    env = profile['environment']
    env['ld_library_path_policy'] = policy
    if policy in ('preserve', 'unset'):
        env['library_dirs'] = []
    if machinefile:
        profile['launcher']['args'] = ['-np', {'token': 'NSLOTS'}, '-machinefile',
                                       {'token': 'SGE_MACHINEFILE'}, {'token': 'EXECUTABLE'}]
    review = profile['execution_review']
    review['source_node_selection'] = node
    review['approved_changes'] = ['ld_library_path_' + policy]
    if machinefile:
        review['approved_changes'].append('sge_machinefile')
    if node == 'node127':
        review['approved_changes'].append('node127_to_all_q')
    review['approval']['note'] = 'SYNTHETIC TEST ONLY: explicit execution review'
    return profile


def test_machinefile_typed_render_and_bash_syntax(tmp_path):
    _, _, entities = setup(tmp_path, 'd')
    profile = reviewed(entities['profile'])
    script = render_script(profile, tmp_path / 'final', 'a' * 64)
    text = script.decode()
    expected = ('exec ' + profile['launcher']['path'] + ' -np "$NSLOTS" '
                '-machinefile "${TMPDIR}/machines" ' + profile['vasp']['path'] + '\n')
    assert text.endswith(expected)
    assert 'test -n "${TMPDIR:-}" || exit 92' in text
    assert 'case "$TMPDIR" in /*) ;; *) exit 92 ;; esac' in text
    assert 'test -f "${TMPDIR}/machines" && test -r "${TMPDIR}/machines" || exit 93' in text
    assert text.count('#$ -q all.q') == text.count('#$ -pe mpi_32 32') == 1
    assert '#$ -V' not in text and 'node127' not in text
    # Parse only: never run the generated script, MPI/VASP or a fragment.
    result = subprocess.run(['/bin/bash', '--noprofile', '--norc', '-n'], input=script,
                            env={'PATH': '/usr/bin:/bin'}, capture_output=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('argument', [
    '$TMPDIR/machines', '$(touch bad)', '`id`', 'x\ny',
    {'token': 'TMPDIR'}, {'token': 'SGE_MACHINEFILE', 'path': '/unapproved'},
    {'token': 'SGE_MACHINEFILE;id'},
])
def test_machinefile_rejects_untyped_interpolation_and_injection(tmp_path, argument):
    _, _, entities = setup(tmp_path)
    profile = reviewed(entities['profile'])
    profile['launcher']['args'][3] = argument
    with pytest.raises(InputError):
        validate_profile(profile)


@pytest.mark.parametrize('args', [
    ['-np', {'token': 'NSLOTS'}, {'token': 'SGE_MACHINEFILE'}, {'token': 'EXECUTABLE'}],
    ['-machinefile', {'token': 'SGE_MACHINEFILE'}, '-machinefile', {'token': 'SGE_MACHINEFILE'},
     '-np', {'token': 'NSLOTS'}, {'token': 'EXECUTABLE'}],
    ['-machinefile', {'token': 'SGE_MACHINEFILE'}, '-machinefile', '/other',
     '-np', {'token': 'NSLOTS'}, {'token': 'EXECUTABLE'}],
])
def test_machinefile_requires_one_paired_flag_and_token(tmp_path, args):
    _, _, entities = setup(tmp_path)
    profile = reviewed(entities['profile'])
    profile['launcher']['args'] = args
    with pytest.raises(InputError):
        validate_profile(profile)


@pytest.mark.parametrize('policy', ['replace', 'prepend', 'preserve', 'unset'])
def test_explicit_library_policies_and_no_generator_environment_capture(tmp_path, monkeypatch, policy):
    _, _, entities = setup(tmp_path)
    profile = reviewed(entities['profile'], policy)
    monkeypatch.setenv('LD_LIBRARY_PATH', '/cron-only/do-not-copy')
    first = render_script(profile, tmp_path / 'final', 'a' * 64)
    monkeypatch.delenv('LD_LIBRARY_PATH')
    assert first == render_script(profile, tmp_path / 'final', 'a' * 64)
    text = first.decode()
    assert '/cron-only/do-not-copy' not in text
    if policy == 'preserve':
        assert 'export LD_LIBRARY_PATH=' not in text and 'unset LD_LIBRARY_PATH' not in text
        assert 'case ":${LD_LIBRARY_PATH}:" in' in text
    elif policy == 'unset':
        assert 'unset LD_LIBRARY_PATH\n' in text and 'export LD_LIBRARY_PATH=' not in text
    else:
        directories = ':'.join(profile['environment']['library_dirs'])
        assert 'export LD_LIBRARY_PATH=' + directories in text
        if policy == 'prepend':
            assert '"${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"' in text
            assert '*::*|*:.:*|*:[!/:]*) exit 94 ;;' in text
    parsed = subprocess.run(['/bin/bash', '--noprofile', '--norc', '-n'], input=first,
                            env={'PATH': '/usr/bin:/bin'}, capture_output=True)
    assert parsed.returncode == 0, parsed.stderr


@pytest.mark.parametrize('policy,empty', [('replace', True), ('prepend', True),
                                        ('preserve', False), ('unset', False)])
def test_library_policy_directory_contradictions_are_not_guessed(tmp_path, policy, empty):
    _, _, entities = setup(tmp_path)
    profile = reviewed(entities['profile'], policy)
    profile['environment']['library_dirs'] = [] if empty else entities['profile']['environment']['library_dirs']
    with pytest.raises(InputError):
        validate_profile(profile)


@pytest.mark.parametrize('change', [
    lambda p: p['environment'].pop('ld_library_path_policy'),
    lambda p: p.pop('execution_review'),
    lambda p: p['execution_review'].update(approved_changes=[]),
    lambda p: p['execution_review']['approved_changes'].append('ld_library_path_preserve'),
    lambda p: p['execution_review']['approval'].update(reviewer=''),
    lambda p: p['execution_review'].update(target_node_selection='node127'),
    lambda p: p['environment'].update(ld_library_path_policy='automatic'),
])
def test_missing_or_contradictory_review_blocks_new_revision_without_writes(tmp_path, change):
    _, registry, entities = setup(tmp_path)
    profile = reviewed(entities['profile'])
    profile['revision'] = 2
    change(profile)
    before = tree(tmp_path)
    with pytest.raises(InputError):
        registry.register('profile', profile, sha256(canonical(profile)))
    assert tree(tmp_path) == before


def test_node127_removal_needs_explicit_approval(tmp_path):
    _, _, entities = setup(tmp_path)
    profile = reviewed(entities['profile'], 'replace', node='node127')
    validate_profile(profile)
    text = render_script(profile, tmp_path / 'final', 'a' * 64).decode()
    assert '#$ -q all.q\n' in text
    assert all('node127' not in line for line in text.splitlines() if line.startswith('#$'))
    profile['execution_review']['approved_changes'].remove('node127_to_all_q')
    with pytest.raises(InputError) as exc:
        validate_profile(profile)
    assert exc.value.code == 'PROFILE_APPROVAL_REQUIRED'


def test_legacy_snapshots_decode_but_cannot_silently_prepare(tmp_path):
    _, _, entities = setup(tmp_path)
    legacy = copy.deepcopy(entities['profile'])
    legacy.pop('execution_review')
    legacy['environment'].pop('ld_library_path_policy')
    checked(legacy, 'profile')  # historical bundle integrity remains readable
    with pytest.raises(InputError) as exc:
        validate_profile(legacy)
    assert exc.value.code == 'PROFILE_APPROVAL_REQUIRED'


@pytest.mark.parametrize('change', [
    lambda p: p.update(queue='all.q@node127'),
    lambda p: p.update(pe='mpi_64'),
    lambda p: p.update(slots=64),
    lambda p: p.update(user_quota_slots=64),
    lambda p: p['launcher'].update(path='/missing/synthetic/mpi'),
    lambda p: p['vasp'].update(binary_name='vasp_std'),
])
def test_static_profile_validation_blocks_wrong_resources_and_paths(tmp_path, change):
    _, _, entities = setup(tmp_path)
    profile = reviewed(entities['profile'])
    change(profile)
    with pytest.raises(InputError):
        validate_profile(profile)


def test_colon_is_not_a_registered_library_directory(tmp_path):
    _, _, entities = setup(tmp_path)
    profile = reviewed(entities['profile'], 'replace')
    directory = tmp_path / 'bad:.'
    directory.mkdir()
    (directory / 'fake.so').write_bytes(b'SYNTHETIC TEST ONLY')
    profile['environment']['library_dirs'] = [str(directory)]
    with pytest.raises(InputError):
        validate_profile(profile)


def test_static_check_never_executes_executables_fragments_or_network(tmp_path, monkeypatch, capsys):
    _, registry, entities = setup(tmp_path)
    profile = reviewed(entities['profile'])
    fragment = tmp_path / 'approved_fragment.sh'
    fragment.write_bytes(b'# SYNTHETIC TEST ONLY\nexit 99\n')
    profile['environment']['fragments'] = [dict(id='synthetic', path=str(fragment),
                                              sha256=sha256(fragment.read_bytes()))]
    profile['revision'] = 2
    before = tree(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError('External execution/network forbidden')
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(socket, 'socket', forbidden)
    validate_profile(profile)
    assert tree(tmp_path) == before
    registry.register('profile', profile, sha256(canonical(profile)))
    assert main(['registry', 'check', '--registry', str(registry.root)]) == 0
    assert json.loads(capsys.readouterr().out)['result'] == 'REGISTRY_VALID'
    fragment.write_bytes(b'# SYNTHETIC TEST ONLY -- drift\n')
    with pytest.raises(InputError):
        validate_profile(profile)


def test_execution_review_is_bound_to_exact_source_run_hash(tmp_path):
    request, registry, entities = setup(tmp_path)
    profile = reviewed(entities['profile'])
    profile['revision'] = 2
    profile['execution_review']['source_run_sha256'] = 'f' * 64
    registry.register('profile', profile, sha256(canonical(profile)))
    template = copy.deepcopy(entities['template'])
    template['revision'] = 2
    template['profile']['revision'] = 2
    before = tree(tmp_path)
    with pytest.raises(InputError) as exc:
        registry.register('template', template, sha256(canonical(template)))
    assert exc.value.code == 'PROFILE_SOURCE_MISMATCH'
    assert tree(tmp_path) == before


def test_profile_change_keeps_science_and_dry_run_source_invariants(tmp_path):
    request, registry, entities = setup(tmp_path, 'd')
    old_plan = build_plan((request, registry))
    profile = reviewed(entities['profile'])
    profile['revision'] = 2
    registry.register('profile', profile, sha256(canonical(profile)))
    template = copy.deepcopy(entities['template'])
    template['revision'] = 2
    template['profile']['revision'] = 2
    registry.register('template', template, sha256(canonical(template)))
    request['template']['revision'] = request['cluster_profile']['revision'] = 2
    before = tree(tmp_path)
    plan = build_plan((request, registry))
    assert tree(tmp_path) == before
    assert plan.science_json == old_plan.science_json
    assert plan.request_digest != old_plan.request_digest
    assert dict(plan.generated)['INCAR'] == dict(old_plan.generated)['INCAR']
    assert dict(plan.generated)['run.sh'] != dict(old_plan.generated)['run.sh']
    source_before = tree(tmp_path / 'research')
    materialize(plan)
    assert verify_bundle(Path(plan.final_dir))
    assert tree(tmp_path / 'research') == source_before
    resolved = loads((Path(plan.final_dir) / 'provenance/resolved_config.json').read_bytes())
    assert resolved['profile']['environment']['library_dirs'] == []
    assert resolved['profile']['execution_review'] == profile['execution_review']


def test_f_d_profiles_and_revisions_are_independently_selected(tmp_path, capsys):
    import shutil
    request_f, registry, f = setup(tmp_path / 'shared', 'f')
    request_d, _, d = setup(tmp_path / 'seed_d', 'd')
    shared_source = Path(f['template']['source_dir']).parent
    shutil.copytree(Path(d['template']['source_dir']), shared_source / 'd')
    profile_f = reviewed(f['profile'], 'replace', node='node127')
    profile_f['id'] = 'cluster_f'
    profile_d = reviewed(f['profile'], 'preserve')
    profile_d['id'] = 'cluster_d'
    profile_d['execution_review']['source_run_sha256'] = sha256((shared_source / 'd/run.sh').read_bytes())
    for profile in (profile_f, profile_d):
        registry.register('profile', profile, sha256(canonical(profile)))
    protocol_d = copy.deepcopy(d['protocol'])
    protocol_d['id'] = 'protocol_d'
    registry.register('protocol', protocol_d, sha256(canonical(protocol_d)))
    material_d = copy.deepcopy(d['material'])
    material_d['id'] = 'material_d'
    registry.register('material', material_d, sha256(canonical(material_d)))
    template_f = copy.deepcopy(f['template'])
    template_f.update(revision=2, profile=dict(id='cluster_f', revision=1))
    template_d = copy.deepcopy(d['template'])
    template_d.update(id='template_d', material_id='material_d', source_dir=str(shared_source / 'd'),
                      profile=dict(id='cluster_d', revision=1), protocol=dict(id='protocol_d', revision=1))
    for template in (template_f, template_d):
        registry.register('template', template, sha256(canonical(template)))
    request_f.update(calculation_id='calc_f', template=dict(id='template', revision=2),
                     cluster_profile=dict(id='cluster_f', revision=1))
    request_d.update(calculation_id='calc_d', template=dict(id='template_d', revision=1),
                     cluster_profile=dict(id='cluster_d', revision=1), material=dict(id='material_d', revision=1),
                     protocol=dict(id='protocol_d', revision=1))
    before = tree(tmp_path)
    plan_f = build_plan((request_f, registry))
    plan_d = build_plan((request_d, registry))
    assert tree(tmp_path) == before
    assert loads(plan_f.config_json)['profile']['id'] == 'cluster_f'
    assert loads(plan_d.config_json)['profile']['environment']['library_dirs'] == []
    assert 'export LD_LIBRARY_PATH=' not in dict(plan_d.generated)['run.sh'].decode()
    for suffix, request in [('f', request_f), ('d', request_d)]:
        operator = tmp_path / ('operator_' + suffix + '.json')
        req_path = tmp_path / ('request_' + suffix + '.json')
        operator.write_bytes(canonical(dict(schema_version=1, registry=str(registry.root),
                                            profile=request['cluster_profile'])))
        req_path.write_bytes(canonical(request))
        before = tree(tmp_path)
        assert main(['prepare', '--dry-run', '--config', str(operator), '--request', str(req_path)]) == 0
        assert json.loads(capsys.readouterr().out)['committed'] is False
        assert tree(tmp_path) == before
    # A new f revision has no effect on d or on the exact old f reference.
    updated = reviewed(profile_f, 'prepend', node='node127')
    updated['revision'] = 2
    registry.register('profile', updated, sha256(canonical(updated)))
    assert build_plan((request_f, registry)).request_digest == plan_f.request_digest
    assert build_plan((request_d, registry)).request_digest == plan_d.request_digest
    template_f.update(revision=3, profile=dict(id='cluster_f', revision=2))
    registry.register('template', template_f, sha256(canonical(template_f)))
    request_f.update(template=dict(id='template', revision=3), cluster_profile=dict(id='cluster_f', revision=2))
    assert loads(build_plan((request_f, registry)).config_json)['profile']['revision'] == 2
    wrong = copy.deepcopy(request_d)
    wrong['cluster_profile'] = dict(id='cluster_f', revision=2)
    with pytest.raises(InputError) as exc:
        build_plan((wrong, registry))
    assert exc.value.code == 'REGISTRY_LINK'
