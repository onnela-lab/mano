import os
from os import chmod, makedirs as _make_directories, rename
from os.path import dirname, exists as path_exists, expanduser
from tempfile import NamedTemporaryFile

from mano.constants import WriteError


def make_directories(path: str, umask: int | None = None, exist_ok: bool = True):
    """
    Create directories recursively with a temporary umask
    """
    
    old_umask = None
    if umask is not None:
        old_umask = os.umask(umask)
    try:
        _make_directories(path, exist_ok=exist_ok)
    finally:
        if old_umask is not None:
            os.umask(old_umask)


def atomic_write(filename: str, content: bytes, overwrite: bool = True, permissions: int = 0o0644):
    """
    Write a file by first saving the content to a temporary file first, then
    renaming the file. Overwrites silently by default o_o
    """
    
    filename = expanduser(filename)
    folder_name = dirname(filename)
    
    if not overwrite and path_exists(filename):
        raise WriteError(f"file already exists: {filename}")
    
    with NamedTemporaryFile(dir=folder_name, prefix='.', delete=False) as tmp:
        tmp.write(content)
    
    chmod(tmp.name, permissions)
    rename(tmp.name, filename)
