from .incar import number
from .errors import require


def validate_kpoints(data):
    lines=data.decode().splitlines(); require(len(lines)>=4,'KPOINTS_SYNTAX')
    require(lines[1].strip().isdigit(),'UNSUPPORTED_KPOINTS'); count=int(lines[1].strip()); mode=lines[2].strip().lower()
    if count==0:
        require(mode in ('gamma','g','monkhorst-pack','m') and len(lines) in (4,5),'UNSUPPORTED_KPOINTS')
        mesh=lines[3].split(); require(len(mesh)==3 and all(x.isdigit() and int(x)>0 for x in mesh),'KPOINTS_MESH')
        if len(lines)==5:
            shift=lines[4].split(); require(len(shift)==3,'KPOINTS_SHIFT'); tuple(number(x) for x in shift)
    else:
        require(count<=1000000 and mode in ('reciprocal','r','cartesian','c') and len(lines)==3+count,'UNSUPPORTED_KPOINTS')
        for line in lines[3:]:
            point=line.split(); require(len(point)==4,'KPOINTS_LIST'); values=tuple(number(x) for x in point); require(values[3]>=0,'KPOINTS_WEIGHT')
    return True
