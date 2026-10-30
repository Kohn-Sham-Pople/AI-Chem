import datetime
from pathlib import Path
from .config import checked, identifier, loads
from .errors import require
from .paths import safe_path, read_small, write_new, private_dir
from .provenance import canonical, sha256
KINDS=('template','material','profile','protocol')

class Registry:
    def __init__(self,root): self.root=safe_path(root)
    def path(self,kind,ref):
        require(kind in KINDS,'SCHEMA',exit_code=2)
        identifier(ref['id'])
        require(type(ref['revision']) is int and ref['revision']>0,'SCHEMA',exit_code=2)
        return self.root/kind/ref['id']/(str(ref['revision'])+'.json')
    def resolve(self,kind,ref):
        path=self.path(kind,ref); data=read_small(path); value=checked(loads(data),kind)
        require(value['id']==ref['id'] and value['revision']==ref['revision'],'REGISTRY_IDENTITY')
        return value,(str(path),sha256(data))
    def register(self,kind,value,approved_sha256):
        checked(value,kind)
        require(sha256(canonical(value))==approved_sha256,'APPROVAL_HASH')
        datetime.datetime.strptime(value['approval']['approved_at'],'%Y-%m-%dT%H:%M:%SZ')
        if kind=='profile':
            from .paths import guard_roots
            guard_roots(value['roots'])
        if kind=='template':
            from .paths import overlaps
            require(not overlaps(self.root,safe_path(value['source_dir'])),'PATH_UNSAFE')
            from .discovery import inventory
            require(inventory(Path(value['source_dir']))['files']==value['files'],'SOURCE_CHANGED')
        path=self.path(kind,value); private_dir(path.parent); write_new(path,canonical(value)); return path

def resolve_request(request,registry):
    checked(request,'request'); entities={}; pins=[]
    for kind,field in [('template','template'),('material','material'),('profile','cluster_profile'),('protocol','protocol')]:
        entities[kind],pin=registry.resolve(kind,request[field]); pins.append(pin)
    t,m,p,protocol=(entities[x] for x in KINDS)
    require(t['material_id']==m['id'],'TEMPLATE_MATERIAL_MISMATCH')
    require(t['profile']==request['cluster_profile'] and t['protocol']==request['protocol'],'REGISTRY_LINK')
    require((t['shell_class'],m['formula'],protocol['recipe']) in [('f','Eu2BaCuO5','open_f_v1'),('d','CaCu(SeO3)2','open_d_v1')],'TEMPLATE_MATERIAL_MISMATCH')
    require(t['shell_class']==protocol['shell_class'],'REGISTRY_LINK')
    for name in t['files']: require(t['files'][name]['source_relative_name']==name,'PATH_UNSAFE')
    from .paths import guard_roots,under
    guard_roots(p['roots']); require(Path(p['roots']['registry'])==registry.root,'REGISTRY_LINK'); under(t['source_dir'],p['roots']['source'])
    return entities,tuple(pins)
