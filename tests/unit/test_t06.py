import copy
from pathlib import Path
import pytest
from support import setup
from ai_chem_input.config import loads
from ai_chem_input.provenance import digest,sha256
from ai_chem_input.prepare import build_plan,materialize,verify_bundle
from ai_chem_input.restart import RestartEvidenceProvider,TrustedLocalRecordStore
from ai_chem_input.paths import inspect
from ai_chem_input.errors import InputError

class TrustedSyntheticProvider(RestartEvidenceProvider):
    """Test-only issuer double; never imported by production."""
    def __init__(self,record): self.record=record
    def get(self,evidence_id): return self.record


def evidence(tmp_path,stage='s02_e5'):
    req,reg,entities=setup(tmp_path)
    a=build_plan((req,reg)); science=loads(a.science_json)
    src=Path(entities['template']['source_dir'])/'CHGCAR'
    src.write_bytes((src.parent/'POSCAR').read_bytes()+b'\n1 1 1\n1\n')
    compatibility=dict(shell_class='f',calculation_id=req['calculation_id'],stage_id='s01_e4' if stage=='s02_e5' else 's02_e5',
        method_hash=science['method_hash'],configuration_hash=science['configuration_hash'],structure_sha256=entities['material']['configurations'][0]['structure_sha256'],
        potcar_sha256=entities['material']['method']['potcar_sha256'],u_set_id='u',lmaxmix=6,lcharg=True)
    record=dict(schema_version=1,evidence_id='test_evidence',issuer='synthetic_validator',issuer_version='1',validation_status='VALIDATED',producer_manifest_sha256='a'*64,issued_at='2026-10-30T00:00:00Z',result_evidence_refs=['b'*64],rule=dict(id='lab_rule',version='1',ediff_pass=True,rmsc_pass=True),producer_ediff='1E-04' if stage=='s02_e5' else '1E-05',compatibility=compatibility,chgcar=dict(path=str(src),**inspect(src)))
    req.update(stage_id=stage,restart_evidence_id='test_evidence')
    return req,reg,record

@pytest.mark.parametrize('stage',['s02_e5','s03_e6'])
def test_restart_positive(tmp_path,stage):
    req,reg,record=evidence(tmp_path,stage); p=build_plan((req,reg),TrustedSyntheticProvider(record)); materialize(p)
    final=Path(p.final_dir)
    assert (final/'CHGCAR').read_bytes()==Path(record['chgcar']['path']).read_bytes()
    assert b'ICHARG = 1' in (final/'INCAR').read_bytes()
    assert verify_bundle(final)

@pytest.mark.parametrize('edit',[
    lambda r:r.update(validation_status='PENDING'),lambda r:r['compatibility'].update(lmaxmix=4),
    lambda r:r['compatibility'].update(lcharg=False),lambda r:r['compatibility'].update(u_set_id='other'),
    lambda r:r['compatibility'].update(configuration_hash='c'*64),lambda r:r['compatibility'].update(stage_id='s03_e6'),
    lambda r:r['chgcar'].update(sha256='c'*64),lambda r:r['chgcar'].update(path='/etc/passwd'),
    lambda r:r['rule'].update(rmsc_pass=False),lambda r:r.update(producer_ediff='1E-06'),
    lambda r:r.update(validated=True)])
def test_restart_negative(tmp_path,edit):
    req,reg,record=evidence(tmp_path); edit(record)
    with pytest.raises(InputError) as exc: build_plan((req,reg),TrustedSyntheticProvider(record))
    assert exc.value.exit_code==4 and not (tmp_path/'output').exists()


def test_revocation_and_header(tmp_path):
    req,reg,record=evidence(tmp_path); provider=TrustedSyntheticProvider(record); plan=build_plan((req,reg),provider)
    provider.record=dict(record,validation_status='REVOKED')
    with pytest.raises(InputError): materialize(plan)
    assert not (tmp_path/'output').exists()
    path=Path(record['chgcar']['path']); path.write_bytes(path.read_bytes().replace(b'0.5 0.5 0.5',b'0.4 0.5 0.5'))
    record['chgcar'].update(inspect(path))
    with pytest.raises(InputError): build_plan((req,reg),TrustedSyntheticProvider(record))


def test_store_untrusted(tmp_path):
    provider=TrustedLocalRecordStore(tmp_path,'issuer',{})
    with pytest.raises(InputError): provider.get('forged')
