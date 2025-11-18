import os
from os import chmod, makedirs as _make_directories, rename
from os.path import dirname, exists as path_exists, expanduser, join as path_join
from tempfile import NamedTemporaryFile

from pyzstd import decompress

from mano.constants import logger as log, WriteError

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


def iterate_all_files(directory_path: str):
    """
    Generator that yields all file paths in a directory tree
    """
    for root, _, files in os.walk(directory_path):
        for file in files:
            yield path_join(root, file)


def bytes_to_human_filesize(b: bytes) -> str:
    """
    Convert byte count to human readable string
    """
    suffixes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    index = 0
    count = float(len(b))
    
    while count >= 1024 and index < len(suffixes) - 1:
        count /= 1024
        index += 1
    
    return f"{count:.2f}{suffixes[index]}"


def decompress_zstd_files(directory_path: str, delete_zsts: bool = False, overwrite: bool = False):
    """ Decompress all .zst files in a directory. """
    # todo: multithread this using physical core count
    
    for full_path in iterate_all_files(directory_path):
        if not full_path.endswith('.zst'):
            continue
        decompress_one_zstd_file(full_path, delete_zst=delete_zsts, overwrite=overwrite)


def decompress_one_zstd_file(full_path: str, delete_zst: bool = False, overwrite: bool = False):
    """ Decompress a single .zst file. """
    decompressed_path = full_path[:-4]
    
    it_exists = path_exists(decompressed_path)
    if not overwrite and it_exists:
        log.warning(f"Skipping: `{decompressed_path}`, file already exists.")
        return
    
    with open(full_path, 'rb') as fo:
        compressed_bytes = fo.read()
    
    decompressed_bytes = decompress(compressed_bytes)
    size_compressed = bytes_to_human_filesize(compressed_bytes)
    size_decompressed = bytes_to_human_filesize(decompressed_bytes)
    
    if it_exists:
        log.info(f"Overwriting: `{decompressed_path}` ({size_compressed} -> {size_decompressed}).")
    else:
        log.info(f"Creating:::: `{decompressed_path}` ({size_compressed} -> {size_decompressed}).")
    
    with open(decompressed_path, 'wb') as fo:
        fo.write(decompressed_bytes)
    
    if delete_zst:
        os.remove(full_path)


def compress_zstd_files(directory_path: str, delete_original: bool = False, overwrite: bool = False):
    """ Compress all files in a directory to .zst """
    
    for full_path in iterate_all_files(directory_path):
        if full_path.endswith('.zst'):
            continue
        compress_one_zstd_file(full_path, delete_original=delete_original, overwrite=overwrite)


def compress_one_zstd_file(full_path: str, delete_original: bool = False, overwrite: bool = False):
    """ Compress a single file to .zst """
    
    compressed_path = full_path + '.zst'
    
    it_exists = path_exists(compressed_path)
    if not overwrite and it_exists:
        log.warning(f"Skipping: `{compressed_path}`, file already exists.")
        return
    
    with open(full_path, 'rb') as fo:
        original_bytes = fo.read()
    
    compressed_bytes = decompress(original_bytes)
    size_original = bytes_to_human_filesize(original_bytes)
    size_compressed = bytes_to_human_filesize(compressed_bytes)
    
    if it_exists:
        # Log info this one because it is the default behavior to overwrite
        log.info(f"Overwriting: `{compressed_path}` ({size_original} -> {size_compressed}).")
    else:
        log.info(f"Creating:::: `{compressed_path}` ({size_original} -> {size_compressed}).")
    
    with open(compressed_path, 'wb') as fo:
        fo.write(compressed_bytes)
    
    if delete_original:
        os.remove(full_path)
