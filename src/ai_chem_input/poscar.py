from dataclasses import dataclass
from decimal import Decimal
import re
from .incar import number
from .errors import require, InputError

@dataclass(frozen=True)
class StructureInfo:
    species: tuple
    counts: tuple
    lattice: tuple
    scale: Decimal
    mode: str
    coordinates: tuple
    selective: tuple
    @property
    def nions(self): return sum(self.counts)


def parse_poscar(data,species_hint=None):
    try: lines=data.decode().splitlines()
    except UnicodeError: raise InputError('POSCAR_SYNTAX') from None
    require(len(lines)>=8,'POSCAR_SYNTAX')
    s=lines[1].split(); require(len(s)==1,'UNSUPPORTED_POSCAR_SCALE'); scale=number(s[0]); require(scale!=0,'POSCAR_SCALE')
    lattice=[]
    for line in lines[2:5]:
        row=line.split(); require(len(row)==3,'POSCAR_LATTICE'); lattice.append(tuple(number(x) for x in row))
    a,b,c=lattice
    det=a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0])
    require(det!=0,'POSCAR_LATTICE')
    i=5; species=lines[i].split()
    if all(x.isdigit() for x in species):
        require(species_hint is not None,'POSCAR_SPECIES_HINT'); species=list(species_hint)
    else:
        require(all(re.fullmatch(r'[A-Z][a-z]?',x) for x in species),'POSCAR_SPECIES'); i+=1
    tokens=lines[i].split(); require(tokens and all(x.isdigit() and int(x)>0 for x in tokens),'POSCAR_COUNTS')
    counts=tuple(int(x) for x in tokens); require(len(species)==len(counts),'SPECIES_MISMATCH'); n=sum(counts)
    require(n<=1000000,'POSCAR_LIMIT'); i+=1
    selective=False
    if i<len(lines) and lines[i].strip().lower()=='selective dynamics': selective=True; i+=1
    require(i<len(lines),'POSCAR_COORDINATES'); mode=lines[i].strip().lower()
    require(mode in ('direct','cartesian','cart','d','c','k'),'POSCAR_MODE'); i+=1
    require(len(lines)>=i+n,'POSCAR_COORDINATES'); coords=[]; flags=[]
    for line in lines[i:i+n]:
        parts=line.split(); require(len(parts)==(6 if selective else 3),'POSCAR_COORDINATES')
        coords.append(tuple(number(x) for x in parts[:3]))
        if selective:
            require(all(x.upper() in ('T','F') for x in parts[3:]),'POSCAR_SELECTIVE'); flags.append(tuple(x.upper() for x in parts[3:]))
    require(not any(x.strip() for x in lines[i+n:]),'UNSUPPORTED_POSCAR_TAIL')
    return StructureInfo(tuple(species),counts,tuple(lattice),scale,mode,tuple(coords),tuple(flags))


def same_geometry(left,right):
    """Compare physical Cartesian geometry: abs/rel tolerance 1e-10."""
    import math
    if left.species!=right.species or left.counts!=right.counts: return False
    def physical(s):
        a,b,c=s.lattice
        det=a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0])
        factor=float(s.scale) if s.scale>0 else (float(-s.scale/abs(det)))**(1/3)
        lattice=[[float(v)*factor for v in row] for row in s.lattice]
        if s.mode.startswith('d'):
            coords=[[sum(float(row[k])*lattice[k][j] for k in range(3)) for j in range(3)] for row in s.coordinates]
        else: coords=[[float(v)*factor for v in row] for row in s.coordinates]
        return [v for row in lattice+coords for v in row]
    return all(math.isclose(a,b,abs_tol=1e-10,rel_tol=1e-10) for a,b in zip(physical(left),physical(right)))
