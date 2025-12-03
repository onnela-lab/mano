import json
import locale
import re
import zipfile
from multiprocessing.pool import ThreadPool
from os import (chmod, makedirs as _make_directories, remove as delete_file, rename,
    umask as get_umask, walk as walk_directory)
from os.path import dirname, exists as path_exists, expanduser, isdir, join as path_join
from tempfile import NamedTemporaryFile
from typing import Any

import cryptease as crypt
import pyzstd
from pyzstd import decompress

from mano.constants import (BACKEND_PYZSTD_PARAMS, ParseError, SaveError, log, BEIWE_FILE_EXTENSIONS,
    BEIWE_EXTENSIONS_MESSAGE, WriteError)


def make_directories(path: str, umask: int | None = None, exist_ok: bool = True):
    """
    Create directories recursively with a temporary umask
    """
    
    old_umask = None
    if umask is not None:
        old_umask = get_umask(umask)
    try:
        _make_directories(path, exist_ok=exist_ok)
    finally:
        if old_umask is not None:
            get_umask(old_umask)


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


def iterate_beiwe_data_files_recursively(directory_path: str, zst_only: bool = False):
    """
    Generator for all file paths in a directory tree
    """
    any_valid_files = False  # two error cases we want to have separate messages for
    anything_at_all = False
    try:
        for root, _, files in walk_directory(directory_path):
            anything_at_all = True
            
            for file_path in files:
                
                if zst_only:
                    is_valid = file_path.endswith('.zst')
                else:
                    is_valid = check_is_valid_beiwe_data_file(file_path)
                
                if is_valid:
                    any_valid_files = True
                    yield path_join(root, file_path)
    
    except Exception as e:
        # All other file system related errors seem to subclass OSError, we'll be broader.
        log.error(f"There was an issue accessing files in: `{directory_path}`: {e}")
        raise
    
    if not anything_at_all:  # walk doesn't error on empty dirs.
        log.error(msg := f"No such directory: `{directory_path}`")
        raise FileNotFoundError(msg)
    
    if not any_valid_files:
        # there were files, but not of the correct type
        if zst_only:
            msg = f"No `.zst` files found in directory `{directory_path}` or its subdirectories."
        else:
            msg = f"{BEIWE_EXTENSIONS_MESSAGE}: `{directory_path}` or its subdirectories."
        log.error(msg)
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


def decompress_zst_files(
    target_path: str,
    delete_zsts: bool = False,
    overwrite: bool = False,
    multithread_count: int = 1,
):
    """
    Decompresses all .zst files in a directory and its subdirectories, also works on single files.
    
    Args:
        target_path:
            Path to a directory containing .zst files, or a single .zst file.
            For the current working directory provide "."
        delete_zsts:
            Delete the original .zst files after decompression. Defaults to False.
        overwrite:
            Overwrite existing decompressed files, otherwise skip it. Defaults to False.
        multithread_count:
            Number of files to decompress concurrently. Defaults to 1.
            (ZSTD decompression is extremely fast, test before assuming this will provide benefits.)
    """
    kwargs = dict(delete_zsts=delete_zsts, overwrite=overwrite)
    
    if target_path.endswith('.zst'):  # single file (not a directory)
        return decompress_one_zst_file(target_path, **kwargs)
    
    pool = setup_threadpool(multithread_count, "decompression")
    try:
        # imap_unordered returns results as they complete, not in order of submission.
        for _ in pool.imap_unordered(
            lambda fp: decompress_one_zst_file(fp, **kwargs),  # just hands it the file path
            iterate_beiwe_data_files_recursively(target_path, zst_only=True)
        ):
            pass
    
    finally:
        pool.close()
        pool.join()
        pool.terminate()


def decompress_one_zst_file(
    full_path: str,
    delete_zsts: bool = False,
    overwrite: bool = False,
):
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
    
    with open(decompressed_path, 'wb') as fo:
        fo.write(decompressed_bytes)
    
    if delete_zsts:
        delete_file(full_path)
    
    label = "Overwrote:" if it_exists else "Created:  "  # ensure same length prefix
    log_func = log.warning if it_exists else log.info
    log_func(f"{label} `{decompressed_path}` ({size_compressed} -> {size_decompressed}).")


def compress_to_zst_files(
    target_path: str,
    delete_original: bool = False,
    overwrite: bool = False,
    compression_level: int = 2,
    multithread_count: int = 1,
):
    """
    Compress all files in a directory and its subdirectories to individual .zst files.
        Also works on single files.
    
    Args:
        target_path:
            Path to a directory containing Beiwe data files, or a single file.
            Compression is limited to the compressible data file types provided by The Beiwe
            Platform, .csv and .wav files.
            For the current working directory provide "."
        delete_original:
            Delete the original files after compression. Defaults to False.
        overwrite:
            Overwrite existing .zst files if present, otherwise skip it. Defaults to False.
        compression_level:
            ZSTD compression level to use, from 0 (fastest) to 22 (best).
            The default (2) matches the server and was tested and found to be fairly ideal.
            Default will achieve 18-19% original size at hundreds of MB/s on most computers.
            Higher values can provide additional compression gains up to about 14-15% original size,
            but are much slower, often down to single digit MB/s at the maximum level.
        multithread_count:
            Number of files to compress concurrently. Defaults to 1.
            ZSTD compression speed varies widely with compression level, test before assuming this
            will provide benefits. It is likely that higher compression levels will benefit more.
    """
    
    kwargs = dict[str, Any](  # (type-checking does not like it when you wrap kwargs like this)
        delete_original=delete_original,
        overwrite=overwrite,
        compression_level=compression_level,
    )
    
    if check_is_valid_beiwe_data_file(target_path):  # single file (not a directory)
        return compress_one_zst_file(target_path, **kwargs)
    
    pool = setup_threadpool(multithread_count, "compression")
    try:
        # imap_unordered returns results as they complete, not in order of submission.
        for _ in pool.imap_unordered(
            lambda fp: compress_one_zst_file(fp, **kwargs),  # just hands it a file path
            iterate_beiwe_data_files_recursively(target_path)
        ):
            pass
    finally:
        pool.close()
        pool.join()
        pool.terminate()


def compress_one_zst_file(
    full_path: str,
    delete_original: bool = False,
    overwrite: bool = False,
    compression_level: int = 2,
):
    """ Compress a single file to .zst """
    compressed_path = full_path + '.zst'
    
    it_exists = path_exists(compressed_path)
    if not overwrite and it_exists:
        log.warning(f"Skipping: `{full_path}`, .zst file already exists.")
        return
    
    with open(full_path, 'rb') as fo:
        original_bytes = fo.read()
    
    if compression_level == 2:
        compressed_bytes = compress_as_backend(original_bytes)
    else:
        compressed_bytes = compress_general(original_bytes, level=compression_level)
    
    size_original = bytes_to_human_filesize(original_bytes)
    size_compressed = bytes_to_human_filesize(compressed_bytes)
    
    with open(compressed_path, 'wb') as fo:
        fo.write(compressed_bytes)
    
    if delete_original:
        delete_file(full_path)
    
    label = "Overwrote:" if it_exists else "Created:  "  # ensure same length prefix
    log_func = log.warning if it_exists else log.info
    log_func(f"{label} `{compressed_path}` ({size_original} -> {size_compressed}).")


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
    return pyzstd.compress(b, {pyzstd.CParameter.compressionLevel: level})  # type: ignore


#
# File Validation
#


def validate_exists_at_all(path: str):
    """ Ensure a path exists. """
    if not path_exists(path):
        log.error(f"`{path}` does not exist.")
        exit(1)


def validate_is_a_folder_or_valid_beiwe_data_file(path: str):
    """ Ensure a path is either a directory or a valid Beiwe data file. """
    validate_exists_at_all(path)
    
    is_a_dir = isdir(path)
    is_a_beiwe = check_is_valid_beiwe_data_file(path)
    
    if is_a_dir or is_a_beiwe:
        return
    
    if not is_a_dir and not is_a_beiwe:
        log.error(f"`{path}` is neither a directory nor a valid Beiwe data file.")
        exit(1)
    if not is_a_dir:
        log.error(f"`{path}` is not a directory.")
        exit(1)
    if not is_a_beiwe:
        log.error(f"`{path}` is not a valid Beiwe data file.")
        exit(1)


def validate_is_a_folder_or_zst_file(path: str):
    """ Ensure a path is either a directory or a .zst file. """
    validate_exists_at_all(path)
    
    is_a_dir = isdir(path)
    is_a_zst = path.endswith('.zst')
    
    if is_a_dir or is_a_zst:
        return
    
    if not is_a_dir and not is_a_zst:
        log.error(f"`{path}` is neither a directory nor a .zst file.")
        exit(1)
    if not is_a_dir:
        log.error(f"`{path}` is not a directory.")
        exit(1)
    if not is_a_zst:
        log.error(f"`{path}` is not a .zst file.")
        exit(1)


# does not exit on failure, just returns a boolean
def check_is_valid_beiwe_data_file(path: str) -> bool:
    """ Check if a path is a valid Beiwe data file. """
    return any(path.endswith(ext) for ext in BEIWE_FILE_EXTENSIONS)


def setup_threadpool(multithread_count: int, name: str) -> ThreadPool:
    """ Setup a thread pool with logging. """
    multithread_count = max(1, multithread_count)  # just ignore 0 and negatives
    pool = ThreadPool(multithread_count)
    if multithread_count > 1:
        log.info(f"Using {multithread_count} threads for {name}.")
    return pool

#
# File Encryption
#

#TODO: actually review what this does and confirm this rename is correct
#TODO: document this
def save_encrypted(
    archive: zipfile.ZipFile | None,
    user_id: str,
    output_dir: str,
    lock: list[str] | None = None,
    passphrase: str | None = None,
) -> int:
    """
    The order of operations here is important to ensure the ability to reach a state of consistency:
        1. Save the file
        2. Update the local registry
    """
    
    num_saved = 0
    if not archive:
        return num_saved
    encoding = locale.getpreferredencoding()
    if not lock:
        lock = list()
    else:
        if not passphrase:
            raise SaveError('if you wish to lock a data type, you need a passphrase')
    
    # open registry file in downloaded archive
    log.debug('reading registry file from beiwe archive')
    with archive.open('registry', 'r') as fo:
        registry = json.loads(fo.read().decode('utf-8'))
    
    # if archive registry contains any entries, process them
    if registry:
        # iterate over archive members
        for member in archive.namelist():
            if process_one_archive_file(member, output_dir, archive, user_id, passphrase, lock):
                num_saved += 1
        
        # update local registry file to avoid re-downloading these files
        local_registry = dict[str, str]()
        local_registry_file = path_join(output_dir, user_id, '.registry')
        
        if path_exists(local_registry_file):
            with open(local_registry_file) as fo:
                local_registry = json.load(fo)
        
        local_registry.update(registry)
        local_registry_str = json.dumps(local_registry, indent=2)
        atomic_write(local_registry_file, local_registry_str.encode(encoding))
    
    # return the number of saved files
    return num_saved


def process_one_archive_file(
    file_name: str,
    output_dir: str,
    archive: zipfile.ZipFile,
    user_id: str,
    passphrase: str | None,
    lock: list[str],
) -> bool:
    """ Handle one file from inside a ZipFile Archive """
    
    if file_name == 'registry':  # skip the registry file
        return False
    
    # info = archive.getinfo(member)  # debugging, get information about the current archive member
    
    # parse the data type determine if it should be encrypted
    encrypt = _parse_datatype(file_name, user_id) in lock
    log.debug(f'processing archive member: {file_name} (lock={encrypt})')
    
    output_filename = f'{file_name}.lock' if encrypt else file_name  # lock extension if we need it
    
    # detect if target exists, create the directory
    if path_exists(target_abs := path_join(output_dir, output_filename)):
        delete_file(target_abs)
    if not path_exists(target_dir := dirname(target_abs)):
        make_directories(target_dir, umask=0o5022)
    
    # read archive member content and encrypt it if necessary
    file_content = archive.open(file_name)
    
    if encrypt:
        key = crypt.kdf(passphrase)  # type: ignore
        crypt.encrypt(file_content, key, filename=target_abs, permissions=0o0644)  # type: ignore
    else:
        # write content to persistent storage
        atomic_write(target_abs, file_content.read())
    
    return True


def _parse_datatype(member: str, user_id: str):
    """
    Parse data type from a Beiwe archive member name.
    """
    expr = f'^{user_id}/([a-zA-Z_]+)/.*$'  # (the curly braces are not part of the regex)
    match = re.search(expr, member)
    if not match:
        raise ParseError(f'no match: regex="{expr}", string="{member}"')
    numgroups = len(match.groups())
    if numgroups != 1:
        raise ParseError(
            f'expecting 1 capture group, found {numgroups}: regex="{expr}", string="{member}"'
        )
    return match.group(1)
