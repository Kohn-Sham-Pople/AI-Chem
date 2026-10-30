"""Streaming metadata only; never include licensed content in diagnostics."""
import hashlib
import re
from dataclasses import dataclass
from .errors import require
from .incar import number
from .paths import deadline_check

@dataclass(frozen=True)
class PotentialDataset:
    element: str
    variant: str
    sha256: str
    lexch: str
    zval: str


def inspect_potcar(source,deadline=None):
    result=[]; h=hashlib.sha256(); size=0; metadata={}
    while True:
        deadline_check(deadline)
        line=source.readline(1024*1024+1)
        if not line: break
        require(len(line)<=1024*1024,'POTCAR_FORMAT')
        h.update(line); size+=len(line)
        # Decode only bounded metadata lines; data lines are never retained.
        for key in ('TITEL','VRHFIN','LEXCH','ZVAL'):
            if re.search(rb'\b'+key.encode()+rb'\s*=',line):
                require(key not in metadata,'POTCAR_METADATA')
                value=re.search(rb'\b'+key.encode()+rb'\s*=\s*([^;\r\n]*)',line).group(1).strip()
                require(len(value)<256,'POTCAR_METADATA'); metadata[key]=value.decode('ascii',errors='strict')
        if line.strip()==b'End of Dataset':
            require(set(metadata)=={'TITEL','VRHFIN','LEXCH','ZVAL'},'POTCAR_METADATA')
            title=metadata['TITEL'].split(); require(len(title)>=2,'POTCAR_METADATA')
            element=metadata['VRHFIN'].split(':')[0].strip(); variant=title[1]
            require(re.fullmatch(r'[A-Z][a-z]?',element) and re.fullmatch(r'[A-Za-z0-9_]+',variant),'POTCAR_METADATA')
            number(metadata['ZVAL'])
            result.append(PotentialDataset(element,variant,h.hexdigest(),metadata['LEXCH'],metadata['ZVAL']))
            h=hashlib.sha256(); metadata={}; size=0
    require(size==0 and result,'POTCAR_TRUNCATED')
    return tuple(result)
