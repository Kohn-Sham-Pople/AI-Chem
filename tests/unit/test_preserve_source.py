"""Exact script preservation with hand-authored synthetic source only."""
import copy
import importlib.util
import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from support import setup, tree
from ai_chem_input.cli import main
from ai_chem_input.config import checked, loads
from ai_chem_input.discovery import inventory
from ai_chem_input.errors import InputError
from ai_chem_input.prepare import build_plan, materialize, verify_bundle
from ai_chem_input.provenance import canonical, digest, sha256
from ai_chem_input.script import prepare_run_script, render_script, validate_profile


def preserved(root, shell='f', data=None):
    request, registry, entities = setup(root, shell)
    if data is None:
        data = (Path('tests/fixtures/synthetic') / ('preserve_' + shell + '.sh.txt')).read_bytes()
    source = Path(entities['template']['source_dir']) / 'run.sh'
    source.write_bytes(data)
    profile = copy.deepcopy(entities['profile'])
    profile.update(revision=2, run_script_mode='preserve_source')
    for key in ('launcher', 'environment', 'execution_review'):
        profile.pop(key)
    profile['source_script_approval'] = dict(source_run_sha256=sha256(data), approval=dict(
        reviewer='synthetic', approved_at='2026-11-08T00:00:00Z',
        note='SYNTHETIC TEST ONLY: review exact source without environment changes'))
    registry.register('profile', profile, sha256(canonical(profile)))
    template = copy.deepcopy(entities['template'])
    template.update(revision=2, files=inventory(source.parent)['files'])
    template['profile']['revision'] = 2
    registry.register('template', template, sha256(canonical(template)))
    request['template']['revision'] = request['cluster_profile']['revision'] = 2
    entities.update(profile=profile, template=template)
    return request, registry, entities, data


@pytest.mark.parametrize('shell', ['f', 'd'])
@pytest.mark.parametrize('newline', [b'\n', b'\r\n'])
@pytest.mark.parametrize('trailing', [True, False])
def test_exact_source_bytes_snapshots_manifest_and_dry_run(tmp_path, monkeypatch, shell, newline, trailing):
    data = (Path('tests/fixtures/synthetic') / ('preserve_' + shell + '.sh.txt')).read_bytes()
    data = data.replace(b'\n', newline)
    if not trailing:
        data = data[:-len(newline)]
    request, registry, entities, data = preserved(tmp_path, shell, data)
    def forbidden(*args, **kwargs):
        raise AssertionError('Source script, command or network must not execute')
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(socket, 'socket', forbidden)
    before = tree(tmp_path)
    plan = build_plan((request, registry))
    assert tree(tmp_path) == before
    assert dict(plan.generated)['run.sh'] == data
    assert b'#$ -V' in data and b'-machinefile $TMPDIR/machines' in data
    assert b'OMP_NUM_THREADS' not in data and b'MKL_NUM_THREADS' not in data
    assert (b'all.q@node127' in data) == (shell == 'f')
    source_before = tree(tmp_path / 'research')
    response = materialize(plan)
    final = Path(plan.final_dir)
    assert response['result'] == 'INPUT_READY'
    assert (final / 'run.sh').read_bytes() == data
    assert (final / 'provenance/source/run.sh').read_bytes() == data
    assert (final / 'run.sh').stat().st_ino != (Path(entities['template']['source_dir']) / 'run.sh').stat().st_ino
    assert tree(tmp_path / 'research') == source_before
    verified = verify_bundle(final)
    m = verified['manifest']
    assert m['run_script'] == dict(mode='preserve_source', source_sha256=sha256(data),
        generated_sha256=sha256(data), byte_identical=True, resource_validation='profile_declared_only')
    assert m['source_files']['run.sh']['sha256'] == m['generated_files']['run.sh']['sha256'] == sha256(data)
    diff = (final / 'provenance/input.diff').read_text()
    assert 'run.sh SAME=true mode=preserve_source' in diff and '--- source/run.sh' not in diff
    before = tree(tmp_path)
    assert materialize(plan)['result'] == 'IDEMPOTENT_EXISTING'
    assert tree(tmp_path) == before


def test_opaque_non_utf8_comment_and_no_new_thread_or_host_settings(tmp_path):
    data = b'#!/bin/bash\r\n# SYNTHETIC TEST ONLY \xff\r\n#$ -V\r\nexport OMP_NUM_THREADS=8\r\n'
    request, registry, _, _ = preserved(tmp_path, data=data)
    plan = build_plan((request, registry))
    materialize(plan)
    assert (Path(plan.final_dir) / 'run.sh').read_bytes() == data
    assert verify_bundle(Path(plan.final_dir))


@pytest.mark.parametrize('field', ['launcher', 'environment', 'execution_review'])
def test_renderer_fields_are_rejected_in_preserve_profile(tmp_path, field):
    _, _, original = setup(tmp_path / 'typed')
    _, registry, entities, _ = preserved(tmp_path / 'copy')
    p = copy.deepcopy(entities['profile'])
    p['revision'] = 3
    p[field] = original['profile'][field]
    before = tree(tmp_path)
    with pytest.raises(InputError) as exc:
        registry.register('profile', p, sha256(canonical(p)))
    assert exc.value.code == 'SCRIPT_MODE_CONFLICT'
    assert tree(tmp_path) == before


@pytest.mark.parametrize('change', [
    lambda p: p.pop('source_script_approval'),
    lambda p: p['source_script_approval']['approval'].update(reviewer=''),
    lambda p: p['source_script_approval'].update(source_run_sha256='not-a-hash'),
    lambda p: p.update(run_script_mode='copy-anything'),
])
def test_missing_approval_or_unknown_mode_is_not_auto_approved(tmp_path, change):
    _, registry, entities, _ = preserved(tmp_path)
    p = copy.deepcopy(entities['profile'])
    p['revision'] = 3
    change(p)
    before = tree(tmp_path)
    with pytest.raises(InputError):
        registry.register('profile', p, sha256(canonical(p)))
    assert tree(tmp_path) == before


def test_wrong_approved_hash_cannot_register_template_or_copy(tmp_path):
    _, registry, entities, data = preserved(tmp_path)
    p = copy.deepcopy(entities['profile'])
    p['revision'] = 3
    p['source_script_approval']['source_run_sha256'] = 'f' * 64
    registry.register('profile', p, sha256(canonical(p)))
    template = copy.deepcopy(entities['template'])
    template['revision'] = 3
    template['profile']['revision'] = 3
    before = tree(tmp_path)
    with pytest.raises(InputError) as exc:
        registry.register('template', template, sha256(canonical(template)))
    assert exc.value.code == 'PROFILE_SOURCE_MISMATCH'
    with pytest.raises(InputError):
        prepare_run_script(p, data, tmp_path / 'unused', 'a' * 64)
    assert tree(tmp_path) == before


@pytest.mark.parametrize('stale', ['source', 'config', 'symlink'])
def test_stale_pins_and_symlinks_block_before_output_or_lock(tmp_path, stale):
    request, registry, entities, data = preserved(tmp_path)
    plan = build_plan((request, registry))
    source = Path(entities['template']['source_dir']) / 'run.sh'
    if stale == 'source':
        source.write_bytes(data + b'# changed\n')
    elif stale == 'config':
        path = registry.path('profile', entities['profile'])
        path.write_bytes(path.read_bytes() + b' ')
    else:
        other = tmp_path / 'synthetic-other.sh'
        other.write_bytes(data)
        source.unlink()
        source.symlink_to(other)
    with pytest.raises(InputError):
        materialize(plan)
    for name in ('output', 'state', 'lock'):
        assert not (tmp_path / name).exists()


def reseal(final, manifest):
    path = final / 'provenance/manifest.json'
    path.write_bytes(canonical(manifest))
    ready = loads((final / 'READY.json').read_bytes())
    ready['manifest_sha256'] = sha256(path.read_bytes())
    (final / 'READY.json').write_bytes(canonical(ready))


@pytest.mark.parametrize('tamper', ['run_bytes', 'metadata', 'missing_mode', 'rehashed_changed_run'])
def test_verify_rejects_script_bytes_and_resealed_mode_inconsistency(tmp_path, tamper):
    request, registry, _, _ = preserved(tmp_path)
    plan = build_plan((request, registry))
    materialize(plan)
    final = Path(plan.final_dir)
    m = loads((final / 'provenance/manifest.json').read_bytes())
    if tamper == 'run_bytes':
        (final / 'run.sh').write_bytes(b'# SYNTHETIC TEST ONLY -- tampered')
    elif tamper == 'metadata':
        m['run_script']['mode'] = 'typed_renderer'
        reseal(final, m)
    elif tamper == 'missing_mode':
        m.pop('run_script')
        reseal(final, m)
    else:
        data = (final / 'run.sh').read_bytes() + b'\n# changed\n'
        (final / 'run.sh').write_bytes(data)
        metadata = dict(size_bytes=len(data), sha256=sha256(data))
        m['payload_files']['run.sh'] = m['generated_files']['run.sh'] = metadata
        m['run_script'].update(generated_sha256=sha256(data), byte_identical=False)
        m['generation']['bundle_payload_hash'] = digest('payload', m['payload_files'])
        reseal(final, m)
    with pytest.raises(InputError):
        verify_bundle(final)


def test_legacy_typed_manifest_stays_readable_and_renderer_is_not_repurposed(tmp_path):
    req, registry, entities = setup(tmp_path / 'typed')
    plan = build_plan((req, registry))
    materialize(plan)
    final = Path(plan.final_dir)
    m = loads((final / 'provenance/manifest.json').read_bytes())
    m.pop('run_script')
    reseal(final, m)
    assert verify_bundle(final)['run_script']['mode'] == 'typed_renderer'
    _, _, preserved_entities, _ = preserved(tmp_path / 'preserved')
    with pytest.raises(InputError) as exc:
        render_script(preserved_entities['profile'], tmp_path / 'unused', 'a' * 64)
    assert exc.value.code == 'SCRIPT_MODE_CONFLICT'
    assert render_script(entities['profile'], Path(plan.final_dir), plan.request_digest) == dict(plan.generated)['run.sh']


def test_preservation_needs_no_new_library_thread_or_launcher_paths(tmp_path):
    request, registry, entities, data = preserved(tmp_path)
    for p in (tmp_path / 'bin').iterdir():
        p.unlink()
    for p in (tmp_path / 'lib').iterdir():
        p.unlink()
    validate_profile(entities['profile'])
    plan = build_plan((request, registry))
    assert dict(plan.generated)['run.sh'] == data


def test_preserve_dry_run_cli_is_zero_write(tmp_path, capsys):
    request, registry, entities, _ = preserved(tmp_path, 'd')
    operator = tmp_path / 'operator.json'
    req = tmp_path / 'request.json'
    operator.write_bytes(canonical(dict(schema_version=1, registry=str(registry.root), profile=request['cluster_profile'])))
    req.write_bytes(canonical(request))
    before = tree(tmp_path)
    assert main(['prepare', '--dry-run', '--config', str(operator), '--request', str(req)]) == 0
    assert json.loads(capsys.readouterr().out)['committed'] is False
    assert tree(tmp_path) == before


def golden_module():
    spec = importlib.util.spec_from_file_location('local_golden_test', 'tools/local_golden.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_initial_golden_rejects_typed_profile_by_default_without_writes(tmp_path, monkeypatch):
    _, registry, _ = setup(tmp_path)
    operator = tmp_path / 'operator.json'
    operator.write_bytes(canonical(dict(schema_version=1, registry=str(registry.root), profile=dict(id='cluster', revision=1))))
    monkeypatch.setattr(sys, 'argv', ['local_golden.py', '--config', str(operator), '--request', 'unused', '--expected', 'unused'])
    before = tree(tmp_path)
    with pytest.raises(InputError) as exc:
        golden_module().main()
    assert exc.value.code == 'GOLDEN_SCRIPT_MODE'
    assert tree(tmp_path) == before


@pytest.mark.parametrize('mode', ['preserve_source', 'typed_renderer'])
def test_golden_mode_routing_and_evidence(tmp_path, monkeypatch, mode):
    if mode == 'preserve_source':
        request, registry, entities, _ = preserved(tmp_path)
    else:
        request, registry, entities = setup(tmp_path)
    plan = build_plan((request, registry))
    operator = tmp_path / 'operator.json'
    req = tmp_path / 'request.json'
    expected = tmp_path / 'expected.json'
    operator.write_bytes(canonical(dict(schema_version=1, registry=str(registry.root), profile=request['cluster_profile'])))
    req.write_bytes(canonical(request))
    # This tests tool routing/evidence plumbing, not independent scientific approval.
    hashes = {k: sha256(v) for k, v in plan.generated}
    hashes['POTCAR'] = next(s.sha256 for s in plan.sources if s.name == 'POTCAR')
    expected.write_bytes(canonical(dict(reviewer='synthetic', approved_at='2026-11-08T00:00:00Z',
        source_sha256={s.name: s.sha256 for s in plan.sources}, generated_sha256=hashes,
        semantic_changes=loads(plan.semantic_json))))
    argv = ['local_golden.py', '--config', str(operator), '--request', str(req), '--expected', str(expected)]
    if mode == 'typed_renderer':
        argv += ['--script-mode', 'typed_renderer']
    monkeypatch.setattr(sys, 'argv', argv)
    golden_module().main()
    evidence = loads((tmp_path / 'state/golden/calc_s01_e4.json').read_bytes())
    assert evidence['run_script']['mode'] == mode
    assert evidence['run_script']['byte_identical'] == (mode == 'preserve_source')


@pytest.mark.parametrize('competitor', ['private', 'public', 'symlink'])
def test_concurrent_private_directory_creation_keeps_safety_checks(tmp_path, monkeypatch, competitor):
    from ai_chem_input.paths import private_dir
    target = tmp_path / 'contended'
    other = tmp_path / 'other'
    other.mkdir(mode=0o700)
    original = Path.mkdir
    def racing_mkdir(path, mode=0o777, parents=False, exist_ok=False):
        if path == target and not target.exists():
            if competitor == 'symlink':
                target.symlink_to(other, target_is_directory=True)
            else:
                original(target, mode=0o700 if competitor == 'private' else 0o755)
                if competitor == 'public':
                    target.chmod(0o755)  # simulate a different creator despite umask 077
        return original(path, mode=mode, parents=parents, exist_ok=exist_ok)
    monkeypatch.setattr(Path, 'mkdir', racing_mkdir)
    if competitor == 'private':
        assert private_dir(target) == target
        assert target.stat().st_mode & 0o777 == 0o700
    else:
        with pytest.raises(InputError) as exc:
            private_dir(target)
        assert exc.value.code == ('SOURCE_SYMLINK' if competitor == 'symlink' else 'PATH_OWNERSHIP')
        if competitor == 'public':
            assert target.stat().st_mode & 0o777 == 0o755  # never chmod another creator
    assert not list(other.iterdir())
