import os
import pytest
from ai_chem_input.config import loads, validate
from ai_chem_input.paths import guard_roots, read_small, inspect, write_new
from ai_chem_input.errors import InputError

@pytest.mark.parametrize('data', ['{"a":1,"a":2}', '{"x":NaN}', '{"x":Infinity}'])
def test_strict_json(data):
    with pytest.raises(InputError): loads(data)

@pytest.mark.parametrize('value', [{'x':1}, {'a':'<LOCAL_VALUE>'}, {}])
def test_schema(value):
    with pytest.raises(InputError): validate(value, {'type':'object','required':['a'],'additionalProperties':False,'properties':{'a':{'type':'string'}}})

def test_paths(tmp_path):
    r = {k:str(tmp_path/k) for k in ['output','registry','state','lock']}
    r.update(source=[str(tmp_path/'research')],protected=[str(tmp_path/'research')])
    guard_roots(r)
    for path in [tmp_path, tmp_path/'research'/'out']:
        with pytest.raises(InputError): guard_roots(dict(r,output=str(path)))
    guard_roots(dict(r,output=str(tmp_path/'research2')))
    src=tmp_path/'file'; src.write_bytes(b'abc')
    link=tmp_path/'link'; link.symlink_to(src)
    with pytest.raises(InputError): read_small(link)
    fifo=tmp_path/'fifo'; os.mkfifo(fifo)
    with pytest.raises(InputError): read_small(fifo)
    before=src.stat(); dst=tmp_path/'copy'; write_new(dst,source=src,expected=inspect(src))
    assert dst.read_bytes()==b'abc' and dst.stat().st_ino != before.st_ino
    assert src.stat().st_mode==before.st_mode


def test_parent_symlink_hardlink_and_traversal(tmp_path):
    real=tmp_path/'real'; real.mkdir(); src=real/'file'; src.write_bytes(b'original')
    alias=tmp_path/'alias'; alias.symlink_to(real,target_is_directory=True)
    with pytest.raises(InputError): read_small(alias/'file')
    with pytest.raises(InputError): read_small(real/'..'/'real'/'file')
    hard=tmp_path/'hard'; os.link(src,hard)
    with pytest.raises(FileExistsError): write_new(hard,source=src)
    assert src.read_bytes()==b'original'
