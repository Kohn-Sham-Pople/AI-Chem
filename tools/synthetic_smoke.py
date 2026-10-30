"""Run with the target interpreter. Does not change OS or install anything."""
import argparse
import json
import platform
import sqlite3
import sys
from pathlib import Path


def main():
    p=argparse.ArgumentParser(); p.add_argument('--require-target',action='store_true'); args=p.parse_args()
    report=dict(python=platform.python_version(),linked_sqlite=sqlite3.sqlite_version,platform=platform.platform())
    target=(sys.version_info[:3]==(3,9,19) and sqlite3.sqlite_version=='3.46.1')
    osrelease=Path('/etc/centos-release')
    target=target and osrelease.exists() and '6.9' in osrelease.read_text()
    report['exact_target']=bool(target); print(json.dumps(report,sort_keys=True))
    if args.require_target and not target: return 2
    import pytest
    return pytest.main(['-q','-p','no:cacheprovider','tests'])

if __name__=='__main__': raise SystemExit(main())
