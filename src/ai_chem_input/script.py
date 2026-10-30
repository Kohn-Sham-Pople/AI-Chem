import os
import re
import shlex
from pathlib import Path
from .errors import require
from .paths import safe_path, inspect
from .config import checked


def safe_token(value):
    require(isinstance(value,str) and value and re.fullmatch(r'[A-Za-z0-9_./:=,+-]+',value),'SCRIPT_PROFILE_INVALID')
    return shlex.quote(value)


def validate_profile(profile):
    checked(profile,'profile')
    from .paths import guard_roots
    guard_roots(profile['roots'])
    require(profile['slots']<=profile['user_quota_slots'],'SCRIPT_PROFILE_INVALID')
    for field in [profile['vasp']['path'],profile['launcher']['path'],profile['runtime']['python_path'],profile['runtime']['bash_path']]:
        safe_token(field); path=Path(field) if field=='/bin/bash' else safe_path(field)
        require(path.is_file() and os.access(str(path),os.R_OK|os.X_OK),'SCRIPT_PROFILE_INVALID')
    require(Path(profile['vasp']['path']).name==profile['vasp']['binary_name'],'SCRIPT_PROFILE_INVALID')
    for directory in profile['environment']['library_dirs']:
        safe_token(directory); path=safe_path(directory)
        require(path.is_dir() and os.access(str(path),os.R_OK|os.X_OK),'SCRIPT_PROFILE_INVALID')
        require(any(p.is_file() and not p.is_symlink() for p in path.iterdir()),'SCRIPT_PROFILE_INVALID')
    for fragment in profile['environment']['fragments']:
        safe_token(fragment['path']); require(inspect(fragment['path'])['sha256']==fragment['sha256'],'SCRIPT_PROFILE_INVALID')
    tokens=[]
    for arg in profile['launcher']['args']:
        if isinstance(arg,dict): tokens.append(arg['token'])
        else: safe_token(arg)
    require(tokens.count('EXECUTABLE')==1 and tokens.count('NSLOTS')==1,'SCRIPT_PROFILE_INVALID')


def render_script(profile,final_dir,request_digest):
    validate_profile(profile); safe_token(str(final_dir))
    lines=['#!/bin/bash','#$ -S /bin/bash','#$ -cwd','#$ -q all.q','#$ -pe mpi_32 32','#$ -N ac_'+request_digest[:24],'#$ -j y','#$ -o vasp.stdout']
    if profile['runtime']['walltime']: lines.append('#$ -l h_rt='+profile['runtime']['walltime'])
    lines+=['set -e','set -o pipefail','umask 077','test -n "${JOB_ID:-}" || exit 90','test "${NSLOTS:-0}" = 32 || exit 91','cd -- '+shlex.quote(str(final_dir))]
    for fragment in profile['environment']['fragments']: lines.append('. '+safe_token(fragment['path']))
    lines.append('export LD_LIBRARY_PATH='+shlex.quote(':'.join(profile['environment']['library_dirs'])))
    for k,v in sorted(profile['environment']['thread_vars'].items()): lines.append('export '+k+'='+str(v))
    args=[safe_token(profile['launcher']['path'])]
    for arg in profile['launcher']['args']:
        if isinstance(arg,dict): args.append('"$NSLOTS"' if arg['token']=='NSLOTS' else safe_token(profile['vasp']['path']))
        else: args.append(safe_token(arg))
    lines.append('exec '+' '.join(args))
    return ('\n'.join(lines)+'\n').encode()
