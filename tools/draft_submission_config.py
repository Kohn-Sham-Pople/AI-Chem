"""Write incomplete public examples, with no live or execution approval."""
import json
from pathlib import Path


def draft(schema,proof=False):
    if 'const' in schema:
        return None if proof and type(schema['const']) is bool else schema['const']
    if schema.get('type')=='object': return {k:draft(v,proof) for k,v in schema.get('properties',{}).items()}
    if schema.get('type')=='array': return []
    return None

root=Path('schemas/submission_v1'); target=root/'examples'; target.mkdir(exist_ok=True)
for name in ('config','request','rqs','dialect','effective_execution','live_authorization'):
    value=draft(json.loads((root/(name+'.json')).read_text()),proof=name not in ('config','request'))
    if name=='config':
        value['profile']['live_enabled']=False
        value['profile']['paused']=True
        value['profile']['paused_restore']=True
    (target/(name+'.draft.json')).write_text(json.dumps(value,indent=2)+'\n')
