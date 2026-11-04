"""Hand-authored mock headers only; no licensed potential data."""
import hashlib
import io

import pytest

from ai_chem_input.errors import InputError
from ai_chem_input.potcar import inspect_potcar


SYNTHETIC_DATASET = (
    b'SYNTHETIC TEST ONLY\n'
    b'TITEL = PAW Cu_fake\n'
    b'VRHFIN = Cu: fake\n'
    b'LEXCH = PE\n'
    b'ZVAL = 1\n'
    b'FAKE DATA -- NOT LICENSED OR EXECUTABLE\n'
    b'End of Dataset\n'
)


def dataset(zval):
    return SYNTHETIC_DATASET.replace(b'ZVAL = 1', b'ZVAL = ' + zval)


@pytest.mark.parametrize('raw,expected', [
    (b'10.000', '10.000'),
    (b'10.000 mass and valenz', '10.000'),
    (b'1.000D+01 mass and valenz', '1.000D+01'),
    (b'1e1 mass and valenz', '1e1'),
    (b'+10.000 mass and valenz', '+10.000'),
    (b'.5 mass and valenz', '.5'),
    (b'10.000\tmass\tand\tvalenz', '10.000'),
    (b'  10.000   mass and valenz  ', '10.000'),
])
def test_zval_numeric_token_and_official_suffix(raw, expected):
    data = dataset(raw)
    stream = io.BytesIO(data)
    potential, = inspect_potcar(stream)
    assert potential.zval == expected
    assert (potential.element, potential.variant, potential.lexch) == ('Cu', 'Cu_fake', 'PE')
    assert potential.sha256 == hashlib.sha256(data).hexdigest()
    assert stream.getvalue() == data


@pytest.mark.parametrize('raw', [
    b'', b'mass and valenz', b'10.000 arbitrary',
    b'10.000 mass and valence', b'10.000 mass AND valenz',
    b'10.000 mass and valenz extra', b'10.000mass and valenz',
    b'10.000 mass and valenzfoo', b'10.000 mass and valenz #comment',
    b'10.000 20.000', b'10.000 20.000 mass and valenz',
    b'10.000foo mass and valenz', b'1.2.3 mass and valenz',
    b'1D+ mass and valenz', b'--10.000 mass and valenz',
    b'NaN', b'NaN mass and valenz', b'Infinity mass and valenz',
])
def test_zval_rejects_malformed_numbers_and_unknown_suffixes(raw):
    with pytest.raises(InputError):
        inspect_potcar(io.BytesIO(dataset(raw)))


def test_zval_on_shared_pomass_line_and_crlf():
    data = SYNTHETIC_DATASET.replace(
        b'ZVAL = 1', b'POMASS = 100.000; ZVAL = 10.000 mass and valenz'
    ).replace(b'\n', b'\r\n')
    potential, = inspect_potcar(io.BytesIO(data))
    assert potential.zval == '10.000'
    assert potential.sha256 == hashlib.sha256(data).hexdigest()


def test_zval_keeps_dataset_boundaries_and_exact_hashes():
    first = dataset(b'10.000 mass and valenz')
    second = dataset(b'2.000').replace(b'Cu_fake', b'O_fake').replace(b'Cu: fake', b'O: fake')
    potentials = inspect_potcar(io.BytesIO(first + second))
    assert [(p.element, p.variant, p.zval) for p in potentials] == [
        ('Cu', 'Cu_fake', '10.000'), ('O', 'O_fake', '2.000')
    ]
    assert [p.sha256 for p in potentials] == [
        hashlib.sha256(first).hexdigest(), hashlib.sha256(second).hexdigest()
    ]
    with pytest.raises(InputError) as exc:
        inspect_potcar(io.BytesIO(first + second.removesuffix(b'End of Dataset\n')))
    assert exc.value.code == 'POTCAR_TRUNCATED'


@pytest.mark.parametrize('corrupt', [
    lambda data: data.replace(b'TITEL = PAW Cu_fake\n', b''),
    lambda data: data.replace(b'VRHFIN = Cu: fake\n', b''),
    lambda data: data.replace(b'LEXCH = PE\n', b''),
    lambda data: data.replace(b'LEXCH = PE\n', b'LEXCH = PE\nLEXCH = PE\n'),
    lambda data: data.replace(b'ZVAL = 10.000 mass and valenz\n', b'ZVAL = 10.000 mass and valenz\nZVAL = 1\n'),
])
def test_official_zval_does_not_relax_metadata_checks(corrupt):
    with pytest.raises(InputError) as exc:
        inspect_potcar(io.BytesIO(corrupt(dataset(b'10.000 mass and valenz'))))
    assert exc.value.code == 'POTCAR_METADATA'
