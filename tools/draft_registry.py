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
    Path('schemas/examples',kind+'.draft.json').write_text(json.dumps(skeleton(schema),indent=2)+'\n')
