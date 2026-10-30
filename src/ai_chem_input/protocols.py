from .incar import Patch
from .errors import require
CONTROLLED=set('EDIFF NELM AMIX AMIX_MAG LMAXMIX ICHARG ISTART LCHARG'.split())
MATERIAL_TAGS=set('LDAU LDAUTYPE LDAUL LDAUU LDAUJ MAGMOM'.split())
STAGES={'f':('s01_e4','s02_e5','s03_e6'),'d':('s01_e6',)}


def stage_values(shell,stage):
    require(shell in STAGES and stage in STAGES[shell],'STAGE_INVALID',exit_code=2)
    if shell=='f':
        n=STAGES[shell].index(stage)
        return dict(EDIFF=('1E-04','1E-05','1E-06')[n],NELM='300',AMIX='0.1',AMIX_MAG='0.1',LMAXMIX='6',ICHARG=None if n==0 else '1',ISTART='0',LCHARG='.TRUE.')
    return dict(EDIFF='1E-06',NELM=None,AMIX='0.2',AMIX_MAG='0.4',LMAXMIX='4',ICHARG=None,ISTART='0')


def protocol_patches(shell,stage):
    return [Patch(k,v,'REMOVE' if v is None else 'SET') for k,v in stage_values(shell,stage).items()]
