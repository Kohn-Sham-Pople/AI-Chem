"""Flat VASP 5 syntax with exact character spans and conservative patching."""
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from .errors import require, InputError

NUMERIC = set('EDIFF NELM AMIX AMIX_MAG BMIX BMIX_MAG LMAXMIX ICHARG ISTART ISPIN SAXIS MAGMOM LDAUTYPE LDAUL LDAUU LDAUJ NSW IBRION ENCUT NBANDS ISYM NPAR KPAR NCORE ISMEAR SIGMA'.split())
BOOL = set('LDAU LCHARG LWAVE LSORBIT LNONCOLLINEAR LHFCALC LASPH'.split())
NUM = re.compile(r'^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eEdD][+-]?\d+)?$')


def number(raw):
    require(isinstance(raw,str) and NUM.fullmatch(raw) is not None,'INCAR_NUMBER')
    try: value=Decimal(raw.replace('D','E').replace('d','e'))
    except InvalidOperation: raise InputError('INCAR_NUMBER') from None
    require(value.is_finite(),'INCAR_NUMBER'); return value


def boolean(raw):
    r=raw.upper(); require(r in ('.TRUE.','.FALSE.','T','F','TRUE','FALSE'),'INCAR_BOOLEAN')
    return r in ('.TRUE.','T','TRUE')


def array(raw,limit=1000000):
    out=[]
    for token in raw.split():
        if '*' in token:
            parts=token.split('*'); require(len(parts)==2 and parts[0].isdigit(),'INCAR_ARRAY')
            count=int(parts[0]); value=number(parts[1])
        else: count=1; value=number(token)
        require(0<count<=limit-len(out),'INCAR_ARRAY_LIMIT'); out.extend([value]*count)
    require(out,'INCAR_ARRAY'); return tuple(out)


def normalize(raw):
    return re.sub(r'\\[ \t]*\r?\n',' ',raw).strip()


@dataclass(frozen=True)
class Assignment:
    tag: str
    raw: str
    start: int
    end: int


@dataclass(frozen=True)
class IncarDocument:
    data: bytes
    assignments: tuple
    @property
    def tags(self): return {a.tag:normalize(a.raw) for a in self.assignments}


@dataclass(frozen=True)
class Patch:
    tag: str
    value: object = None
    action: str = 'SET'


def parse_incar(data):
    try: text=data.decode('utf-8')
    except UnicodeError: raise InputError('INCAR_SYNTAX') from None
    entries=[]; seen=set(); start=0; i=0; quote=None
    def statement(a,b):
        raw=text[a:b]; stripped=raw.strip()
        if not stripped: return
        require(not any(c in stripped for c in '{}[]'),'UNSUPPORTED_INCAR_SYNTAX')
        if '=' not in stripped: return  # preserved plain heading
        m=re.fullmatch(r'\s*([A-Za-z][A-Za-z0-9_]*)\s*=([\s\S]*)',raw)
        require(m is not None,'INCAR_SYNTAX'); tag=m[1].upper(); value=normalize(m[2])
        require(value and ('=' not in value or (value[0] in "'\"" and value[-1]==value[0])),'INCAR_SYNTAX')
        require(tag not in seen,'INCAR_DUPLICATE',tag); seen.add(tag)
        if tag in NUMERIC:
            parsed=array(value)
            if tag not in {'MAGMOM','SAXIS','LDAUL','LDAUU','LDAUJ'}:
                require(len(parsed)==1,'INCAR_NUMBER')
            if tag in {'NELM','LMAXMIX','ICHARG','ISTART','ISPIN','LDAUTYPE','NSW','IBRION','NBANDS','ISYM','NPAR','KPAR','NCORE','ISMEAR','LDAUL'}:
                require(all(x==x.to_integral_value() for x in parsed),'INCAR_NUMBER')
        if tag in BOOL: boolean(value)
        # Exclude surrounding whitespace from edit spans, preserving separators/comments.
        left=a+len(raw)-len(raw.lstrip()); right=b-len(raw)+len(raw.rstrip())
        entries.append(Assignment(tag,m[2],left,right))
    while i<len(text):
        c=text[i]
        if quote:
            require(c not in '\r\n','UNSUPPORTED_INCAR_SYNTAX')
            if c==quote: quote=None
            i+=1; continue
        if c in "'\"": quote=c; i+=1; continue
        if c=='\\':
            m=re.match(r'\\[ \t]*\r?\n',text[i:]); require(m is not None,'INCAR_CONTINUATION')
            require(text[i+len(m[0]):].strip(),'INCAR_CONTINUATION'); i+=len(m[0]); continue
        if c in '#!':
            statement(start,i)
            end=text.find('\n',i)
            if end<0: i=len(text); start=i; break
            i=end+1; start=i; continue
        if c in ';\r\n':
            statement(start,i); start=i+1
        i+=1
    require(quote is None,'UNSUPPORTED_INCAR_SYNTAX'); statement(start,len(text))
    return IncarDocument(data,tuple(entries))


def patch_incar(doc,patches):
    text=doc.data.decode(); edits=[]; append=[]; tags=doc.tags; used=set()
    for patch in patches:
        tag=patch.tag.upper(); require(tag not in used,'INCAR_DUPLICATE'); used.add(tag)
        require(tag in NUMERIC|BOOL|{'SYSTEM'},'OVERRIDE_FORBIDDEN',tag)
        require(patch.action in ('SET','REMOVE'),'INCAR_PATCH')
        val=None if patch.action=='REMOVE' else str(patch.value)
        if val is not None:
            require(not any(c in val for c in '\n\r;#!'),'INCAR_PATCH')
        assignment=next((a for a in doc.assignments if a.tag==tag),None)
        if assignment:
            if val is not None and tags[tag]==val: continue
            edits.append((assignment.start,assignment.end,'' if val is None else tag+' = '+val))
        elif val is not None: append.append(tag+' = '+val)
    for a,b,value in sorted(edits,reverse=True): text=text[:a]+value+text[b:]
    if append:
        newline='\r\n' if b'\r\n' in doc.data else '\n'
        if text and not text.endswith('\n'): text+=newline
        text+=newline.join(append)+newline
    output=text.encode(); parsed=parse_incar(output)
    for patch in patches:
        if patch.action=='REMOVE': require(patch.tag.upper() not in parsed.tags,'INCAR_PATCH')
        else: require(parsed.tags[patch.tag.upper()]==str(patch.value),'INCAR_PATCH')
    return output
