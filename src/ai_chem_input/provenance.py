import hashlib
import json
import difflib

def sha256(data): return hashlib.sha256(data).hexdigest()
def canonical(value): return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
def digest(label,value): return sha256(b'ai-chem:hash-v1:'+label.encode('ascii')+b':'+canonical(value))
def text_diff(name,before,after): return ''.join(difflib.unified_diff(before.decode().splitlines(True),after.decode().splitlines(True),fromfile='source/'+name,tofile='generated/'+name))
