"""Evidence is consumed, never issued. Default production path is closed."""
from dataclasses import dataclass
from pathlib import Path
from .errors import require, InputError
from .paths import inspect, open_read, under, read_small
from .config import checked, identifier, load
from .provenance import digest
from .protocols import STAGES
from .poscar import parse_poscar, same_geometry

class RestartEvidenceProvider:
    def get(self,evidence_id):
        raise InputError('RESTART_UNTRUSTED',exit_code=4)


class TrustedLocalRecordStore(RestartEvidenceProvider):
    """Only instantiate in a locally audited integration; not from JobRequest.

    Trust in the issuer/store ownership is provisioned by the HPC operator,
    not inferred from a record's self-asserted validated flag.
    """
    def __init__(self,root,issuer,approved_records):
        self.root=Path(root); self.issuer=identifier(issuer)
        self.approved_records=dict(approved_records)
    def get(self,evidence_id):
        identifier(evidence_id)
        require(evidence_id in self.approved_records,'RESTART_UNTRUSTED',exit_code=4)
        path=self.root/(evidence_id+'.json')
        require(inspect(path)['sha256']==self.approved_records[evidence_id],'RESTART_UNTRUSTED',exit_code=4)
        record=load(path)
        require(record.get('issuer')==self.issuer,'RESTART_UNTRUSTED',exit_code=4)
        return record


@dataclass(frozen=True)
class RestartRef:
    path: str
    size_bytes: int
    sha256: str
    evidence_id: str
    evidence_hash: str


def consume(provider,request,compatibility,structure,protected_roots):
    shell=compatibility['shell_class']; stages=STAGES[shell]; i=stages.index(request['stage_id'])
    eid=request['restart_evidence_id']
    if i==0:
        require(eid is None,'RESTART_UNEXPECTED',exit_code=4); return None
    require(isinstance(eid,str) and eid,'BLOCKED_RESTART',exit_code=4)
    record=provider.get(eid)
    try: checked(record,'evidence')
    except InputError: raise InputError('RESTART_UNTRUSTED',exit_code=4) from None
    from .incar import number
    require(number(record['producer_ediff'])==number(('1E-04','1E-05')[i-1]),'RESTART_INCOMPATIBLE',exit_code=4)
    expected=dict(compatibility,calculation_id=request['calculation_id'],stage_id=stages[i-1],lmaxmix=6,lcharg=True)
    require(record.get('validation_status')=='VALIDATED' and record.get('evidence_id')==eid,'RESTART_UNTRUSTED',exit_code=4)
    require(record.get('compatibility')==expected,'RESTART_INCOMPATIBLE',exit_code=4)
    src=record.get('chgcar',{})
    require(set(src)=={'path','size_bytes','sha256'},'RESTART_UNTRUSTED',exit_code=4)
    try:
        path=under(src['path'],protected_roots)
        info=inspect(path,src)
        require(info['size_bytes']>0,'RESTART_TRUNCATED',exit_code=4)
        # CHGCAR header is POSCAR geometry followed by a blank and grid.
        with open_read(path) as f:
            lines=[]
            for _ in range(structure.nions+12):
                line=f.readline(4097); require(line and len(line)<=4096,'RESTART_HEADER',exit_code=4)
                if lines and line.strip()==b'': break
                lines.append(line)
        header=parse_poscar(b''.join(lines),list(structure.species))
        require(same_geometry(header,structure),'RESTART_HEADER',exit_code=4)
    except (OSError,InputError):
        raise InputError('RESTART_INCOMPATIBLE',exit_code=4) from None
    return RestartRef(str(path),info['size_bytes'],info['sha256'],eid,digest('evidence',record))
