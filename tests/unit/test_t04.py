import io
import pytest
from ai_chem_input.poscar import parse_poscar
from ai_chem_input.potcar import inspect_potcar
from ai_chem_input.kpoints import validate_kpoints
from ai_chem_input.errors import InputError
POS=b'SYNTHETIC TEST ONLY\n1\n1 0 0\n0 1 0\n0 0 1\nCu Cu\n1 1\nDirect\n2 0 0\n0 0 0\n'
POT=b'SYNTHETIC TEST ONLY\nTITEL = PAW Cu_fake\nVRHFIN = Cu: fake\nLEXCH = PE\nZVAL = 1\nFAKE DATA\nEnd of Dataset\n'

def test_parse():
    assert parse_poscar(POS).nions==2
    assert parse_poscar(POS.replace(b'Cu Cu\n',b''),['Cu','Cu']).species==('Cu','Cu')
    assert parse_poscar(POS.replace(b'\n1\n',b'\n-10\n',1)).scale==-10
    assert inspect_potcar(io.BytesIO(POT*2))[1].variant=='Cu_fake'
    assert validate_kpoints(b'fake\n0\nGamma\n1 1 1\n0 0 0\n')

@pytest.mark.parametrize('data',[POS+b'0 0 0\n',POS.replace(b'1 0 0',b'0 0 0'),POS[:-8],POS.replace(b'\n1\n',b'\n1 1 1\n',1)])
def test_bad_pos(data):
    with pytest.raises(InputError): parse_poscar(data)

@pytest.mark.parametrize('data',[POT[:-10],POT.replace(b'LEXCH',b'OTHER'),POT.replace(b'ZVAL = 1',b'ZVAL = nan')])
def test_bad_pot(data):
    with pytest.raises(InputError): inspect_potcar(io.BytesIO(data))

@pytest.mark.parametrize('data',[
    b'fake\n0\nGamma\n0 1 1\n',b'fake\n2\nReciprocal\n0 0 0 1\n',
    b'fake\n0\nLine-mode\n1 1 1\n',b'fake\n0\nGamma\n1 1 1\nNaN 0 0\n'])
def test_bad_kpoints(data):
    with pytest.raises(InputError): validate_kpoints(data)


def test_selective_and_scale_geometry():
    from ai_chem_input.poscar import same_geometry
    a=parse_poscar(POS)
    b=parse_poscar(POS.replace(b'\nDirect\n',b'\nSelective dynamics\nDirect\n').replace(b'2 0 0\n',b'2 0 0 T T F\n').replace(b'0 0 0\n',b'0 0 0 F F F\n'))
    assert same_geometry(a,b)
    assert same_geometry(a,parse_poscar(POS.replace(b'\n1\n',b'\n-1\n',1)))
