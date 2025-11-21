import os
from os import chmod, makedirs as _make_directories, rename
from os.path import dirname, exists as path_exists, expanduser, join as path_join
from tempfile import NamedTemporaryFile

import pyzstd
from pyzstd import decompress

from mano.constants import (BACKEND_PYZSTD_PARAMS, logger as log, VALID_BEIWE_FILE_EXTENSIONS,
    VALID_EXTENSIONS_MESSAGE, WriteError)


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


def iterate_beiwe_data_files_recursively(directory_path: str):
    """
    Generator for all file paths in a directory tree
    """
    any_valid_files = False  # two error cases we want to have separate messages for
    anything_at_all = False
    try:
        for root, _, files in os.walk(directory_path):
            anything_at_all = True
            for file in files:
                if any(file.endswith(ext) for ext in VALID_BEIWE_FILE_EXTENSIONS):
                    any_valid_files = True
                    yield path_join(root, file)
    
    except Exception as e:
        # All other file system related errors seem to subclass OSError, we'll be broader.
        log.error(f"There was an issue accessing files in: `{directory_path}`: {e}")
        raise
    
    if not anything_at_all:
        log.error(msg:= f"No such directory: `{directory_path}`")
        raise FileNotFoundError(msg)
    
    if not any_valid_files:
        log.error(msg:= f"{VALID_EXTENSIONS_MESSAGE}: `{directory_path}`")
        raise FileNotFoundError(msg)


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
    
    # bytes don't have fractions
    if index == 0:
        return f"{int(count)}{suffixes[index]}"
    
    return f"{count:.2f}{suffixes[index]}"


def decompress_zstd_files(directory_path: str, delete_zsts: bool = False, overwrite: bool = False):
    """ Decompress all .zst files in a directory. """
    # todo: multithread this using physical core count
    
    for full_path in iterate_beiwe_data_files_recursively(directory_path):
        if not full_path.endswith('.zst'):
            continue
        decompress_one_zstd_file(full_path, delete_zst=delete_zsts, overwrite=overwrite)


def decompress_one_zstd_file(full_path: str, delete_zst: bool = False, overwrite: bool = False):
    """ Decompress a single .zst file. """
    decompressed_path = full_path[:-4]
    
    it_exists = path_exists(decompressed_path)
    if not overwrite and it_exists:
        log.warning(f"Skipping: `{full_path}`, file already exists.")
        return
    
    with open(full_path, 'rb') as fo:
        compressed_bytes = fo.read()
    
    # decompression speed should be over 1GB/s on anything remotely modern as of 2025
    decompressed_bytes = decompress(compressed_bytes)
    size_compressed = bytes_to_human_filesize(compressed_bytes)
    size_decompressed = bytes_to_human_filesize(decompressed_bytes)
    
    label = "Overwrote:" if it_exists else "Created:::"  # ensure same length prefix
    _log = log.warning if it_exists else log.info
    _log(f"{label} `{decompressed_path}` ({size_compressed} -> {size_decompressed}).")
    
    with open(decompressed_path, 'wb') as fo:
        fo.write(decompressed_bytes)
    
    if delete_zst:
        os.remove(full_path)


def compress_zstd_files(
    directory_path: str, delete_original: bool = False, overwrite: bool = False
):
    """ Compress all files in a directory to .zst """
    # todo: multithread this using physical core count
    for full_path in iterate_beiwe_data_files_recursively(directory_path):
        if full_path.endswith('.zst'):
            continue
        compress_one_zstd_file(full_path, delete_original=delete_original, overwrite=overwrite)


def compress_one_zstd_file(
    full_path: str,
    delete_original: bool = False,
    overwrite: bool = False,
    compression_level: int = 2
):
    """ Compress a single file to .zst """
    
    compressed_path = full_path + '.zst'
    
    it_exists = path_exists(compressed_path)
    if not overwrite and it_exists:
        log.warning(f"Skipping: `{compressed_path}`, file already exists.")
        return
    
    with open(full_path, 'rb') as fo:
        original_bytes = fo.read()
    
    if compression_level == 2:
        compressed_bytes = compress_as_backend(original_bytes)
    else:
        compressed_bytes = compress_general(original_bytes, level=compression_level)
    
    size_original = bytes_to_human_filesize(original_bytes)
    size_compressed = bytes_to_human_filesize(compressed_bytes)
    
    label = "Overwrote:" if it_exists else "Created:::"  # ensure same length prefix
    _log = log.warning if it_exists else log.info
    _log(f"{label} `{compressed_path}` ({size_original} -> {size_compressed}).")
    
    with open(compressed_path, 'wb') as fo:
        fo.write(compressed_bytes)
    
    if delete_original:
        os.remove(full_path)


def compress_as_backend(b: bytes) -> bytes:
    """
    This function matches the exact compression parameters used by the Beiwe backend. These
    parameters were tested and found to be fairly ideal, achieving 18-19% original size at hundreds
    of MB/s. Less aggressive compression may be _slower_, as well as worse. More aggressive
    parameters will drop speed _significantly_, down to single digit MB/s by level 18, with maximum
    compression raised to around 14-15%.  Decompression speed is always extremely fast (~2GB/s).
    (Your speeds will differ, compression ratios are stable.)
    """
    return pyzstd.compress(b, BACKEND_PYZSTD_PARAMS)  # type: ignore


def compress_general(b: bytes, level: int) -> bytes:
    return pyzstd.compress(b, {pyzstd.CParameter.compressionLevel: level}) # type: ignore
