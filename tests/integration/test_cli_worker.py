import io
import json
import os
from pathlib import Path
import pytest
from support import setup
from ai_chem_input.provenance import canonical
from ai_chem_input.paths import private_dir
from ai_chem_input.cli import main
from ai_chem_input.worker import once
from ai_chem_input.state import global_lock
from ai_chem_input.errors import InputError
from support import tree


def config(root):
    req,reg,entities=setup(root)
    conf=root/'operator.json'; conf.write_bytes(canonical(dict(schema_version=1,registry=str(reg.root),profile=dict(id='cluster',revision=1))))
    request=root/'request.json'; request.write_bytes(canonical(req))
    return req,reg,entities,conf,request


def test_cli_dry(tmp_path,capsys):
    req,reg,e,conf,request=config(tmp_path); before=tree(tmp_path)
    for cmd in ('plan','prepare'):
        args=[cmd,'--config',str(conf),'--request',str(request)]+(['--dry-run'] if cmd=='prepare' else [])
        assert main(args)==0; out=json.loads(capsys.readouterr().out); assert out['committed'] is False
        assert out['result']=='PLAN_VALIDATED' and tree(tmp_path)==before
    req['stage_id']='s02_e5'; request.write_bytes(canonical(req)); before=tree(tmp_path)
    assert main(['prepare','--dry-run','--config',str(conf),'--request',str(request)])==4
    assert tree(tmp_path)==before
    assert json.loads(capsys.readouterr().out)['result']=='BLOCKED_RESTART'
    assert main(['submit'])==2
    assert json.loads(capsys.readouterr().out)['issue_codes']==['CLI_USAGE']


def test_worker_minimal_and_archives(tmp_path,monkeypatch):
    req,reg,e,conf,request=config(tmp_path)
    monkeypatch.setenv('LD_LIBRARY_PATH','/inherited/unsafe')
    monkeypatch.setenv('PATH','/no/bin')
    assert once(str(conf))==[]
    inbox=Path(e['profile']['roots']['state'])/'inbox'
    (inbox/'01.json').write_bytes(b'{')
    (inbox/'02.json').write_bytes(canonical(req))
    assert once(str(conf))[0]['result']=='REJECTED'
    assert (inbox/'02.json').exists()
    assert once(str(conf))[0]['result']=='INPUT_READY'
    (inbox/'03.json').write_bytes(canonical(dict(req,request_id='req_again')))
    assert once(str(conf))[0]['result']=='IDEMPOTENT_EXISTING'
    assert len(list((inbox.parent/'rejected').glob('*/request.json')))==1
    (inbox/'04.json').symlink_to(request)
    assert once(str(conf))[0]['result']=='REJECTED'
    with global_lock(e['profile']['roots']['lock']):
        with pytest.raises(InputError) as exc: once(str(conf))
        assert exc.value.exit_code==6
    with pytest.raises(InputError): once(str(conf),2)


def test_cli_all_commands(tmp_path,capsys):
    req,reg,e,conf,request=config(tmp_path)
    assert main(['discover','--config',str(conf)])==0
    assert json.loads(capsys.readouterr().out)['candidates'][0]['shell_class']=='f'
    assert main(['registry','check','--registry',str(reg.root)])==0
    capsys.readouterr()
    assert main(['prepare','--config',str(conf),'--request',str(request)])==0
    out=json.loads(capsys.readouterr().out)
    assert main(['verify','--bundle',out['bundle_path']])==0
    assert json.loads(capsys.readouterr().out)['result']=='VERIFIED'


def test_inbox_limit_and_verify_exit(tmp_path,capsys):
    req,reg,e,conf,request=config(tmp_path)
    once(str(conf)); inbox=Path(e['profile']['roots']['state'])/'inbox'
    for i in range(101): (inbox/(str(i)+'.tmp')).write_bytes(b'incomplete')
    with pytest.raises(InputError) as exc: once(str(conf))
    assert exc.value.code=='INBOX_LIMIT' and len(list(inbox.iterdir()))==101
    assert main(['verify','--bundle',str(tmp_path/'missing')])==5
    assert json.loads(capsys.readouterr().out)['issue_codes']==['PACKAGE_TAMPERED']
