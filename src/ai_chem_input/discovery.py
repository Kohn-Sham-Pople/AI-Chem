from pathlib import Path
from .paths import safe_path, inspect, open_read, read_small
from .errors import require
FILES=('INCAR','POSCAR','POTCAR','KPOINTS','run.sh')

def inventory(directory):
    directory=safe_path(directory); require(directory.is_dir(),'TEMPLATE_NOT_FOUND'); files={}
    for name in FILES:
        require((directory/name).exists(),'TEMPLATE_NOT_FOUND',name)
        files[name]=dict(inspect(directory/name),source_relative_name=name)
        require(files[name]['size_bytes']>0,'TEMPLATE_NOT_FOUND',name)
    from .incar import parse_incar
    from .poscar import parse_poscar
    from .potcar import inspect_potcar
    from .kpoints import validate_kpoints
    parse_incar(read_small(directory/'INCAR'))
    with open_read(directory/'POTCAR') as f: potentials=inspect_potcar(f)
    parse_poscar(read_small(directory/'POSCAR'),[p.element for p in potentials]); validate_kpoints(read_small(directory/'KPOINTS'))
    extras=[]
    for entry in directory.iterdir():
        if entry.name not in FILES: extras.append(entry.name)
        require(len(extras)<=1000,'DISCOVERY_LIMIT')
    return dict(files=files,parse_status='PARSED_NOT_APPROVED',ignored_extra_names=sorted(extras))

def discover_templates(profile):
    policy=profile['discovery']; candidates=[]
    def walk(root,depth):
        safe_path(root)
        for p in sorted(root.iterdir()):
            require(not p.is_symlink(),'SOURCE_SYMLINK')
            if p.is_dir():
                if p.name in ('f','d'):
                    candidates.append(dict(shell_class=p.name,source_dir=str(p),**inventory(p)))
                    require(len(candidates)<=policy['max_candidates'],'DISCOVERY_LIMIT')
                elif policy['recursive']:
                    require(depth<policy['max_depth'],'DISCOVERY_LIMIT'); walk(p,depth+1)
    for root in profile['roots']['source']: walk(Path(root),0)
    return candidates

def select_candidate(candidates,shell_class,explicit_path=None):
    matches=[c for c in candidates if c['shell_class']==shell_class and (explicit_path is None or c['source_dir']==str(explicit_path))]
    require(len(matches)==1,'AMBIGUOUS_TEMPLATE' if matches else 'TEMPLATE_NOT_FOUND'); return matches[0]
