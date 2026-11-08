"""Emit incomplete documentation drafts, never active scientific defaults."""
import json
from pathlib import Path


def skeleton(s):
    if 'const' in s: return s['const']
    if s.get('type')=='object': return {k:skeleton(v) for k,v in s.get('properties',{}).items()}
    if s.get('type')=='array': return []
    return None

for kind in ('profile','template','material','protocol'):
    schema=json.loads(Path('schemas',kind+'.json').read_text())
    value=skeleton(schema)
    if kind=='profile':
        preserved=dict(value)
        for key in ('launcher','environment','execution_review'):
            preserved.pop(key)
        preserved['run_script_mode']='preserve_source'
        Path('schemas/examples/profile-preserve-source.draft.json').write_text(json.dumps(preserved,indent=2)+'\n')
        value.pop('source_script_approval')
        value['run_script_mode']='typed_renderer'
    Path('schemas/examples',kind+'.draft.json').write_text(json.dumps(value,indent=2)+'\n')
