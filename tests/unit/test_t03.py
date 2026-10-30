import pytest
from ai_chem_input.incar import *
from ai_chem_input.errors import InputError

@pytest.mark.parametrize('text',['A=1; a=1','EDIFF=nan','MAGMOM=1000000000*0','EDIFF=1 \\','SYSTEM="bad','EDIFF==1','X={x}'])
def test_bad(text):
    with pytest.raises(InputError): parse_incar(text.encode())

def test_spans():
    data=b'ediff = 1d-4 ; NELM = 450 ! old template value\r\n# ICHARG = 1\r\nAMIX = 0.2\r\nMAGMOM = 2*7.0 \\\r\n 1*0 1*1.0 5*0.0\r\nSYSTEM = "quote # ; !"\r\n'
    doc=parse_incar(data); assert number(doc.tags['EDIFF'])==Decimal('0.0001')
    p=[Patch('NELM',action='REMOVE'),Patch('ICHARG',action='REMOVE'),Patch('EDIFF','1E-04')]
    new=patch_incar(doc,p)
    assert b'! old template value' in new and b'# ICHARG = 1' in new
    assert 'NELM' not in parse_incar(new).tags
    assert patch_incar(parse_incar(new),p)==new
    assert array('2*-1 1D-4')==(Decimal('-1'),Decimal('-1'),Decimal('.0001'))

@pytest.mark.parametrize('text',[
    b'ICHARG=1; NELM=300 ! hi\n',b'NELM=300; ICHARG=1 ! hi\n',b'ICHARG=1; NELM=300; ENCUT=400\n'])
def test_remove_semicolon_edges(text):
    new=patch_incar(parse_incar(text),[Patch('ICHARG',action='REMOVE')])
    tags=parse_incar(new).tags
    assert 'ICHARG' not in tags and tags['NELM']=='300'
    if b'! hi' in text: assert b'! hi' in new
