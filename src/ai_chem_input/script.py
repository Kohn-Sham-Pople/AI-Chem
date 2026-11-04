"""Typed, locally approved execution profiles; rendering never executes them."""
import datetime
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


def validate_execution_review(profile):
    environment=profile['environment']
    require('ld_library_path_policy' in environment and 'execution_review' in profile,
            'PROFILE_APPROVAL_REQUIRED')
    policy=environment['ld_library_path_policy']
    directories=environment['library_dirs']
    require(bool(directories)==(policy in ('replace','prepend')),'SCRIPT_PROFILE_INVALID')
    review=profile['execution_review']
    expected={'ld_library_path_'+policy}
    tokens=[arg['token'] for arg in profile['launcher']['args'] if isinstance(arg,dict)]
    if 'SGE_MACHINEFILE' in tokens:
        expected.add('sge_machinefile')
    if review['source_node_selection']=='node127':
        expected.add('node127_to_all_q')
    changes=review['approved_changes']
    require(len(changes)==len(set(changes)) and set(changes)==expected,'PROFILE_APPROVAL_REQUIRED')
    # Approval metadata is human-provided, never manufactured from a source scan.
    datetime.datetime.strptime(review['approval']['approved_at'],'%Y-%m-%dT%H:%M:%SZ')


def validate_profile(profile):
    checked(profile,'profile')
    validate_execution_review(profile)
    from .paths import guard_roots
    guard_roots(profile['roots'])
    require(profile['slots']<=profile['user_quota_slots'],'SCRIPT_PROFILE_INVALID')
    for field in [profile['vasp']['path'],profile['launcher']['path'],profile['runtime']['python_path'],profile['runtime']['bash_path']]:
        safe_token(field); path=Path(field) if field=='/bin/bash' else safe_path(field)
        require(path.is_file() and os.access(str(path),os.R_OK|os.X_OK),'SCRIPT_PROFILE_INVALID')
    require(Path(profile['vasp']['path']).name==profile['vasp']['binary_name'],'SCRIPT_PROFILE_INVALID')
    for directory in profile['environment']['library_dirs']:
        require(':' not in directory,'SCRIPT_PROFILE_INVALID')
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
    require(tokens.count('SGE_MACHINEFILE')<=1,'SCRIPT_PROFILE_INVALID')
    if 'SGE_MACHINEFILE' in tokens:
        args=profile['launcher']['args']
        index=args.index({'token':'SGE_MACHINEFILE'})
        require(index>0 and args[index-1]=='-machinefile' and args.count('-machinefile')==1,
                'SCRIPT_PROFILE_INVALID')


def library_lines(environment):
    policy=environment['ld_library_path_policy']
    directories=shlex.quote(':'.join(environment['library_dirs']))
    lines=[]
    if policy in ('preserve','prepend'):
        # Check the eventual batch environment, not the generator/Cron environment.
        # No empty/current/relative directory entries may be inherited.
        lines += ['if test "${LD_LIBRARY_PATH+x}" = x; then',
                  '    case ":${LD_LIBRARY_PATH}:" in',
                  '        *::*|*:.:*|*:[!/:]*) exit 94 ;;',
                  '    esac', 'fi']
    if policy=='replace':
        lines.append('export LD_LIBRARY_PATH='+directories)
    elif policy=='prepend':
        lines.append('export LD_LIBRARY_PATH='+directories+'"${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"')
    elif policy=='unset':
        lines.append('unset LD_LIBRARY_PATH')
    return lines


def render_script(profile,final_dir,request_digest):
    validate_profile(profile); safe_token(str(final_dir))
    lines=['#!/bin/bash','#$ -S /bin/bash','#$ -cwd','#$ -q all.q','#$ -pe mpi_32 32','#$ -N ac_'+request_digest[:24],'#$ -j y','#$ -o vasp.stdout']
    if profile['runtime']['walltime']: lines.append('#$ -l h_rt='+profile['runtime']['walltime'])
    lines+=['set -e','set -o pipefail','umask 077','test -n "${JOB_ID:-}" || exit 90','test "${NSLOTS:-0}" = 32 || exit 91','cd -- '+shlex.quote(str(final_dir))]
    for fragment in profile['environment']['fragments']: lines.append('. '+safe_token(fragment['path']))
    lines.extend(library_lines(profile['environment']))
    for k,v in sorted(profile['environment']['thread_vars'].items()): lines.append('export '+k+'='+str(v))
    has_machinefile=any(arg=={'token':'SGE_MACHINEFILE'} for arg in profile['launcher']['args'])
    if has_machinefile:
        lines+=['test -n "${TMPDIR:-}" || exit 92',
                'case "$TMPDIR" in /*) ;; *) exit 92 ;; esac',
                'test -f "${TMPDIR}/machines" && test -r "${TMPDIR}/machines" || exit 93']
    expansions={'NSLOTS':'"$NSLOTS"','EXECUTABLE':safe_token(profile['vasp']['path']),
                'SGE_MACHINEFILE':'"${TMPDIR}/machines"'}
    args=[safe_token(profile['launcher']['path'])]
    for arg in profile['launcher']['args']:
        args.append(expansions[arg['token']] if isinstance(arg,dict) else safe_token(arg))
    lines.append('exec '+' '.join(args))
    return ('\n'.join(lines)+'\n').encode()
