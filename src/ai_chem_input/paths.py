"""Descriptor-relative read-only access. Never chmod or write source objects."""
import hashlib
import os
import stat
import time
from pathlib import Path
from .errors import require, InputError


def safe_path(path):
    p = Path(path)
    require(p.is_absolute() and '..' not in p.parts, 'PATH_UNSAFE')
    cur = Path(p.anchor)
    for part in p.parts[1:]:
        cur /= part
        if cur.exists() or cur.is_symlink():
            require(not cur.is_symlink(), 'SOURCE_SYMLINK')
    return p


def overlaps(a, b):
    a, b = Path(a), Path(b)
    return a == b or a in b.parents or b in a.parents


def guard_roots(roots):
    for name in ('source', 'protected'):
        require(isinstance(roots[name], list) and roots[name], 'PATH_UNSAFE', name)
    protected = [safe_path(p) for p in roots['protected']]
    sources = [safe_path(p) for p in roots['source']]
    for p in sources:
        require(any(p == q or q in p.parents for q in protected), 'PATH_UNSAFE', 'source')
    dests = [safe_path(roots[k]) for k in ('output', 'registry', 'state', 'lock')]
    for p in dests:
        require(not any(overlaps(p, q) for q in protected), 'PATH_UNSAFE')
    for i, p in enumerate(dests):
        require(not any(overlaps(p, q) for q in dests[i + 1:]), 'PATH_UNSAFE')
    return roots


def under(path, roots):
    p = safe_path(path)
    require(any(p == Path(r) or Path(r) in p.parents for r in roots), 'PATH_UNSAFE')
    return p


def open_read(path):
    """O_NOFOLLOW on every directory component, not just the leaf."""
    p = safe_path(path)
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in p.parts[1:-1]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        leaf = os.open(p.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            require(stat.S_ISREG(os.fstat(leaf).st_mode), 'SOURCE_NOT_REGULAR')
            return os.fdopen(leaf, 'rb')
        except BaseException:
            os.close(leaf)
            raise
    finally:
        os.close(fd)


def pin(st):
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_mode


def deadline_check(deadline):
    require(deadline is None or time.monotonic() < deadline, 'DEADLINE', exit_code=5)


def inspect(path, expected=None, dest=None, limit=2 ** 40, chunk=1024 * 1024, deadline=None):
    h, size = hashlib.sha256(), 0
    with open_read(path) as f:
        before = pin(os.fstat(f.fileno()))
        while True:
            deadline_check(deadline)
            data = f.read(chunk)
            if not data:
                break
            size += len(data)
            require(size <= limit, 'SOURCE_LIMIT')
            h.update(data)
            if dest is not None:
                require(os.fstat(dest.fileno()).st_ino != before[1] or
                        os.fstat(dest.fileno()).st_dev != before[0], 'PATH_UNSAFE')
                dest.write(data)
        require(before == pin(os.fstat(f.fileno())), 'SOURCE_CHANGED')
    value = dict(size_bytes=size, sha256=h.hexdigest())
    if expected is not None:
        require(value == {k: expected[k] for k in value}, 'SOURCE_CHANGED')
    return value


def read_small(path, limit=4 * 1024 * 1024):
    with open_read(path) as f:
        before = pin(os.fstat(f.fileno()))
        require(before[2] <= limit, 'SOURCE_LIMIT')
        data = f.read(limit + 1)
        require(len(data) <= limit and before == pin(os.fstat(f.fileno())), 'SOURCE_CHANGED')
        return data


def private_dir(path):
    p = safe_path(path)
    missing=[]; current=p
    while not current.exists():
        missing.append(current); current=current.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
    st = p.stat()
    require(st.st_uid == os.getuid() and st.st_mode & 0o077 == 0, 'PATH_OWNERSHIP')
    return p


def write_new(path, data=None, source=None, expected=None, executable=False, **kwargs):
    p = safe_path(path)
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o700 if executable else 0o600)
    with os.fdopen(fd, 'wb') as f:
        if source is not None:
            inspect(source, expected, f, **kwargs)
        else:
            f.write(data)
        f.flush()
        os.fsync(f.fileno())


def fsync_dir(path):
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
