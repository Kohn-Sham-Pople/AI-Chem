"""Execute the documented file-only acceptance command with synthetic captures."""
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from submission_support import make_case
from support import tree
from ai_chem_input.config import loads
from ai_chem_input.provenance import canonical,sha256


@pytest.mark.parametrize('mode',['approved','missing_evidence','bad_date'])
def test_documented_oge_parser_acceptance_is_read_only_and_sanitized(tmp_path,monkeypatch,capsys,mode):
    req,config_path,c,_=make_case(tmp_path,live=False,cluster_timezone='Asia/Seoul')
    p=c['profile']
    if mode=='missing_evidence': p['dialect_evidence']=None
    else:
        pin=p['dialect_evidence']; path=Path(pin['path']); evidence=loads(path.read_bytes())
        evidence['client_version']='SYNTHETIC OGE 6.2u7'; path.write_bytes(canonical(evidence))
        pin['sha256']=sha256(path.read_bytes())
    config_path.write_bytes(canonical(c))
    fixtures=Path('tests/fixtures/sge_synthetic')
    detail=(fixtures/'oge_6_2u7_qstat_detail.txt').read_bytes().replace(b'synthetic_owner',p['expected_owner']['name'].encode())
    accounting=(fixtures/'oge_6_2u7_qacct_single.txt').read_bytes().replace(b'synthetic_owner',p['expected_owner']['name'].encode())
    if mode=='bad_date': detail=detail.replace(b'Mon Nov',b'Tue Nov')
    captures=[tmp_path/'qstat.xml',tmp_path/'detail.txt',tmp_path/'accounting.txt']
    for path,data in zip(captures,[b'<job_info><queue_info/></job_info>',detail,accounting]): path.write_bytes(data)
    command=Path('docs/step_1_3/oge_6_2u7_parser_acceptance.md').read_text().split("<<'PY'\n",1)[1].split('\nPY\n',1)[0]
    before=tree(tmp_path)
    def forbidden(*args,**kwargs): raise AssertionError('Parser-only command must not execute or open state')
    monkeypatch.setattr(subprocess,'Popen',forbidden)
    monkeypatch.setattr(sqlite3,'connect',forbidden)
    monkeypatch.setattr(sys,'argv',['parser-check',str(config_path)]+[str(path) for path in captures])
    if mode=='bad_date':
        with pytest.raises(SystemExit) as exc: exec(compile(command,'<documented-command>','exec'),{})
        assert exc.value.code==4
    else: exec(compile(command,'<documented-command>','exec'),{})
    output=capsys.readouterr().out; result=loads(output)
    assert result['parser_acceptance']==('FAIL' if mode=='bad_date' else 'PASS')
    assert result['dispatch_allowed'] is False
    if mode!='bad_date': assert result['dialect_evidence']==('NOT_RUN' if mode=='missing_evidence' else 'PASS')
    assert str(tmp_path) not in output and 'aaaaaaaa' not in output
    assert tree(tmp_path)==before
