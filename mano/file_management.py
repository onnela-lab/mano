import hashlib
import re
from base64 import encodebytes as base64_encodebytes
from collections import defaultdict
from collections.abc import Callable, Generator, Iterable
from datetime import datetime
from io import BytesIO
from multiprocessing.pool import ThreadPool
from os import (chmod, cpu_count, makedirs as _make_directories, remove as delete_file,
    replace as replace_file, walk as walk_directory)
from os.path import dirname, exists as path_exists, expanduser, isdir, join as path_join
from tempfile import NamedTemporaryFile
from typing import Any
from zipfile import ZipFile

import pyzstd
from cryptease import decrypt_to_stream, encrypt, kdf as key_derivation_function, key_from_file
from mypy.types import T
from pyzstd import decompress

from mano.constants import (BACKEND_PYZSTD_PARAMS, BEIWE_EXTENSIONS_MESSAGE, BEIWE_FILE_EXTENSIONS,
    EncryptionKeyUnavailable, GlobalSettings, log, ParseError, SaveError, WriteError)
from mano.messages import (CANNOT_ENCRYPT_MSG, CANNOT_HASH_MSG, DATA_STREAM_FOLDER_MSG,
    DATA_STREAM_NOT_PARTICIPANT_MSG, DATA_STREAM_REGISTRY_MSG, PARSE_ERROR_NO_MATCH_MSG,
    PARSE_ERROR_TOO_MANY_MATCHES_MSG)


def make_directories(path: str):
    """ Run create directories with exists defaulting to True """
    _make_directories(path, exist_ok=True)


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
    
    # TODO: the value of mimicking the cyptease.encrypt permissions is questionable.
    chmod(tmp.name, permissions)
    # on wandows rename will fail if target exists with a FileExistsError if we use os.rename
    replace_file(tmp.name, filename)
    log.debug(f"wrote file: `{filename}`, {len(content)} bytes.")


def iterate_beiwe_data_files_recursively(
    directory_path: str,
    zst_only: bool = False,
    include_zst: bool = False,
    suppress_empty: bool = False
) -> Generator[str, None, None]:
    """
    Generator that yields full paths for all file paths in a directory tree that are valid Beiwe
    data files.  constants.BEIWE_FILE_EXTENSIONS for valid extensions.
    The zst_only flag will switch to only yielding .zst files.
    """
    any_valid_files = False  # two error cases we want to have separate messages for
    anything_at_all = False
    try:
        for root, _, files in walk_directory(directory_path):
            anything_at_all = True
            
            for file_path in files:
                is_valid = False
                
                is_locked = file_path.endswith('.lock')  # ".lock" is always at the end
                if is_locked:
                    file_path = file_path[:-5]
                
                if zst_only:
                    is_valid = file_path.endswith('.zst') and check_is_valid_beiwe_data_file(file_path[:-4])
                elif include_zst:
                    if file_path.endswith('.zst') and check_is_valid_beiwe_data_file(file_path[:-4]):
                        is_valid = True
                    elif check_is_valid_beiwe_data_file(file_path):
                        is_valid = True
                else:
                    is_valid = check_is_valid_beiwe_data_file(file_path)
                
                if is_valid:
                    any_valid_files = True
                    if is_locked:
                        file_path += '.lock'
                    yield path_join(root, file_path)
    
    except Exception as e:
        # All other file system related errors seem to subclass OSError, we'll be broader.
        log.error(f"There was an issue accessing files in: `{directory_path}`: {e}")
        raise
    
    if suppress_empty:  # don't check for errors if caller doesn't care
        return
    
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


def decompress_zst_files(target_path: str, delete_zsts: bool = False, overwrite: bool = False):
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
    """
    kwargs = dict(delete_zsts=delete_zsts, overwrite=overwrite)
    
    if target_path.endswith('.zst'):  # single file (not a directory)
        return decompress_one_zst_file(target_path, **kwargs)
    
    paths = iterate_beiwe_data_files_recursively(target_path, zst_only=True)
    easy_threaded_iterate(decompress_one_zst_file, "decompression", paths, **kwargs)


def decompress_one_zst_file(
    full_path: str,
    delete_zsts: bool = False,
    overwrite: bool = False,
):
    """ Decompress a single .zst file. """
    decompressed_path = full_path[:-4]
    
    it_exists = path_exists(decompressed_path)
    if not overwrite and it_exists:
        log.debug(f"Skipping: `{full_path}`, file already exists.")
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
            2 will compress to 18-19% original size at hundreds of MB/s on most computers.
            Higher values provide additional gains, up to around 14-15% of the original size,
            but are much slower, often down to single digit MB/s at the maximum level.
    """
    
    kwargs = dict[str, Any](  # (type-checking does not like it when you wrap kwargs like this)
        delete_original=delete_original,
        overwrite=overwrite,
        compression_level=compression_level,
    )
    
    if check_is_valid_beiwe_data_file(target_path):  # single file (not a directory)
        return compress_one_zst_file(target_path, **kwargs)
    
    easy_threaded_iterate(
        compress_one_zst_file,
        "compression",
        iterate_beiwe_data_files_recursively(target_path),
        **kwargs,
    )


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
        log.debug(f"Skipping: `{full_path}`, .zst file already exists.")
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


#
# File Encryption
#

#TODO: actually review what this does and confirm this rename is correct
#TODO: document this
def save_archive(
    archive: ZipFile,
    participant_id: str,
    output_dir: str,
    lock: list[str] | None = None,
    passphrase: str | None = None,
    decompress_zst: bool = False,
    hash_lookup: dict[str, bytes] | None = None,
) -> int:
    """
    The order of operations here is important to ensure the ability to reach a state of consistency:
        1. Save the file
        2. Update the local registry
    """
    
    if archive is None or not isinstance(archive, ZipFile):
        raise SaveError('Saving output data requires you provide a ZipFile object')
    
    lock = lock or []
    if lock and not passphrase:
        raise SaveError('Encrypting data requires a passphrase.')
    
    # probably cannot multithread due to "file-io" in the backing memory of the ZipFile object
    num_saved = 0
    for member in archive.namelist():
        if process_one_archive_file(
            member,
            output_dir,
            archive,
            participant_id,
            passphrase,
            lock,
            decompress_zst,
            hash_lookup=hash_lookup or {},
        ):
            num_saved += 1
    
    return num_saved


def process_one_archive_file(
    filename_in_zip: str,
    output_dir: str,
    archive: ZipFile,
    participant_id: str,
    passphrase: str | None,
    lock: list[str],
    decompress_zst: bool,
    hash_lookup: dict[str, bytes],
) -> bool:
    """
    Handle one file from inside a ZipFile Archive
    Lock is a list of data streams, if provided, those data streams will be encrypted.
    """
    
    # skip the registry files and directories - (not sure how fast/slow getinfo is)
    if filename_in_zip == 'registry' or archive.getinfo(filename_in_zip).is_dir():
        log.debug(f'skipping archive file: `{filename_in_zip}`')
        return False
    
    # parse the data type determine if it should be encrypted
    do_encrypt = determine_data_stream_from_internal_zip_filepath(filename_in_zip, participant_id) in lock
    
    # prepend folder, append .lock if encrypting (even works on wandows, cool)
    output_name = f'{filename_in_zip}.lock' if do_encrypt else filename_in_zip
    output_name = path_join(output_dir, output_name)
    
    # read archive file content, decompress if we have a hash to check or just need to decompress,
    # tracking if we decompressed for hash checking (start false only if it is a zst file)
    
    binary_data: bytes = archive.read(filename_in_zip)
    if decompress_zst:
        if not filename_in_zip.endswith('.zst'):
            f"decompress_zst set to True but file is not .zst: `{filename_in_zip}`"
        binary_data = decompress(binary_data)
        output_name = output_name.replace(".zst", "")  # works even on uncompressed ~mp4s
        was_decompressed = True
    else:
        was_decompressed = False
    
    # bare_path, zst_path, lock_path, lock_zst_path = get_possible_real_paths(filename_in_zip)
    
    # detect if target exists, create the directory
    if path_exists(output_name):
        # if we have a local hash lookup, check if the file already matches and skip it
        if hash_lookup and check_hash_cache_match(
            output_name, participant_id, binary_data, hash_lookup, was_decompressed
        ):
            log.debug(f"skipping existing file with matching hash at: `{output_name}`")
            return False
        
        log.debug(f"clearing existing file at: `{output_name}`")
        delete_file(output_name)
    
    if not path_exists(target_dir := dirname(output_name)):
        log.debug(f"creating directory at: `{target_dir}`")
        make_directories(target_dir)
    
    # encrypt if necessary
    if do_encrypt:
        do_encrypted_write(binary_data, output_name, passphrase)
    else:
        # write content to persistent storage
        atomic_write(output_name, binary_data)
    
    return True


def determine_data_stream_from_internal_zip_filepath(file_path: str, participant_id: str):
    """ Parse data type from a Beiwe archive member name. """
    debug_funcname = "zipped_file_path_to_data_stream"
    
    # special error messages for common mistakes
    if file_path.endswith('/') or file_path.endswith('\\'):
        log.error(msg := DATA_STREAM_FOLDER_MSG(debug_funcname, file_path))
        raise ParseError(msg)
    if "registry" in file_path:
        log.error(msg := DATA_STREAM_REGISTRY_MSG(debug_funcname, file_path))
        raise ParseError(msg)
    if not file_path.startswith(participant_id):
        log.error(msg := DATA_STREAM_NOT_PARTICIPANT_MSG(debug_funcname, file_path, participant_id))
        raise ParseError(msg)
    
    regexpr = f'^{participant_id}/([a-zA-Z_]+)/.*$'  # (the curly braces are not part of the regex)
    match = re.search(regexpr, file_path)
    
    if not match:
        log.error(msg := PARSE_ERROR_NO_MATCH_MSG(regexpr, file_path))
        raise ParseError(msg)
    
    # (this will never happen)
    numgroups = len(match.groups())
    if numgroups != 1:
        log.error(msg := PARSE_ERROR_TOO_MANY_MATCHES_MSG(regexpr, file_path, numgroups))
        raise ParseError(msg)
    
    return match.group(1)


#
# File Hashing
#


# TODO: build a higher level function with a name like consolidate that handles cleaning up
#   messy folders with mixes of files.
def parse_duplicate_files(
    folder_path: str,
    participant_id: str,
    passphrase: str | None = None,
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """
    Identify duplicates that do not conflict and duplicates that do conflict out of the possibilties
    of files with no extra extensions, and those .lock .zst, and .zst.lock.
    """
    cannot_resolve = dict[str, list[str]]()
    no_conflicts = dict[str, list[str]]()
    duplicates, paths_to_hashes = find_duplicate_files(folder_path, participant_id, passphrase)
    
    # we don't need base path, its just the normalized path that has duplicate sources
    for base_path, real_paths in duplicates.items():
        assert len(real_paths) > 1, "fundamental logic error in duplicate detection"
        
        real_paths.sort()
        hash_set = {paths_to_hashes[path] for path in real_paths}
        if len(hash_set) > 1:
            cannot_resolve[base_path] = real_paths
        else:
            no_conflicts[base_path] = real_paths
    return cannot_resolve, no_conflicts


def find_duplicate_files(
    folder_path: str, participant_id: str, passphrase: str | None = None
) -> tuple[dict[str, list[str]], dict[str, bytes]]:
    
    paths = iterate_beiwe_data_files_recursively(folder_path, include_zst=True, suppress_empty=True)
    paths_and_hashes = easy_threaded_iterate(
        _threadable_hash_and_path, "generating hashes", paths, participant_id, passphrase
    )
    
    base_to_real: defaultdict[str, list[str]] = defaultdict(list[str])
    real_to_hash = dict[str, bytes]()
    for real_local_path, base_path, hash_val in paths_and_hashes:
        base_to_real[base_path].append(real_local_path)
        real_to_hash[real_local_path] = hash_val
    
    duplicates = {k: v for k, v in base_to_real.items() if len(v) > 1}  # any multiple matches
    real_to_hash = {k: v for k, v in real_to_hash.items() if k in duplicates}  # and their hashes
    return duplicates, real_to_hash


def _threadable_hash_and_path(
    real_local_path: str, participant_id: str, passphrase: str | None,
) -> tuple[str, str, bytes]:
    return (
        real_local_path,
        get_base_path(real_local_path, participant_id),
        get_sha1_file_hash(real_local_path, passphrase),
    )


# todo: make this handle locked files.
def generate_registry_info(
    folder_path: str, study_id: str, participant_id: str, passphrase: str | None = None
) -> tuple[dict[str, str], dict[str, bytes]]:
    """
    Reads and computes sha1 hashes for all Beiwe data files in a folder.
    Returns two dictionaries, the first for use to be passed into the registry on the download API,
    the second to provide local hash lookups for file integrity checking later so the hashes do not
    have to be recomputed.
    """
    remote_hashes = dict[str, str]()
    local_hashes = dict[str, bytes]()
    log.info(f'Computing file hashes for Beiwe Platform data in folder: `{folder_path}`')
    
    paths = iterate_beiwe_data_files_recursively(folder_path, include_zst=True, suppress_empty=True)
    
    easy_threaded_iterate(
        _threadable_generate_registry_info,
        "generating registry info",
        paths,
        study_id,  # lambda params start
        participant_id,
        passphrase,
        remote_hashes,
        local_hashes,
    )
    return remote_hashes, local_hashes


def _threadable_generate_registry_info(
    real_local_path: str,
    study_id: str,
    participant_id: str,
    passphrase: str | None,
    remote_hashes: dict[str, str],
    local_hashes: dict[str, bytes],
):
    # base path is the file with no .lock or .zst extensions, zst path is with .zst
    hash_val = get_sha1_file_hash(real_local_path, passphrase)
    base_path = get_base_path(real_local_path, participant_id)
    local_hashes[base_path] = hash_val
    
    # sometimes we need generate one of several possible remote paths
    for new_path in normalize_path_for_registry(base_path, study_id, participant_id):
        remote_hashes[new_path] = hash_val.decode()


def get_sha1_file_hash(path: str, passphrase: str | None) -> bytes:
    """ Generate the SHA1 hash of a regular, .zst, .lock, or .zst.lock file. """
    
    log.debug(f'generating sha1 hash for file: `{path}`')
    
    with open(path, 'rb') as fo:
        data = fo.read()
    
    if path.endswith(".lock"):
        # may be slow due to PBKDF2 key derivation
        data = decrypt_binary_data_to_bytes(data, passphrase, path)
    
    if path.endswith('.zst') or path.endswith('.zst.lock'):
        data = decompress(data)
    
    return generate_base64_sha1_hash(data)


def generate_base64_sha1_hash(data: bytes) -> bytes:
    # (for some reason this has a new line at the end)
    return base64_encodebytes(hashlib.sha1(data).digest()).strip()


#
# Encryption Operations
#


def decrypt_binary_data_to_bytes(binary_data: bytes, passphrase: str | None, path: str) -> bytes:
    """
    Decrypt a (.lock) file's binary data using cryptease.
    - Cryptease embeds the salt and iv in the file, it prepends a human readable header into the file binary.
    - Decryption requires using the password and the encrypted file itself to derive a final key.
    - For this purpose it provides a `key_from_file` function
    - Somewhere in there I'm pretty sure it uses PBKDF2 with sha256, so this is probably slow(ish).
    """
    if passphrase is None:
        raise EncryptionKeyUnavailable(CANNOT_HASH_MSG(path))
    
    encryption_key_obj = key_from_file(BytesIO(binary_data), passphrase)
    return b"".join(decrypt_to_stream(BytesIO(binary_data), encryption_key_obj))


def do_encrypted_write(binary_data: bytes, filename: str, passphrase: str | None):
    """ Using cryptease, generate an encryption key, and encrypt the binary data to the file. """
    if passphrase is None:
        raise EncryptionKeyUnavailable(CANNOT_ENCRYPT_MSG(filename))
    
    encryption_key = key_derivation_function(passphrase)  # may be slow
    encrypt(BytesIO(binary_data), encryption_key, filename=filename, permissions=0o0644)


#
# Path details for hashing
#


def get_base_path(path: str, participant_id: str) -> str:
    """ returns a normalized "base" path stripped of .zst/.lock and leading folders. """
    # convert wandows paths to slashes that aren't fake, remove .zst, remove lock
    path = path.replace("\\", "/").replace(".lock", "").replace(".zst", "")
    path = path.split(participant_id)[-1]    # we only care about the part after participant id
    return path.lstrip("/")                  # clear leading slash


def get_possible_real_paths(real_file_path: str) -> tuple[str, str, str, str]:
    bare_path = real_file_path.replace(".lock", "").replace(".zst", "")
    zst_path = bare_path + ".zst"
    lock_path = bare_path + ".lock"
    lock_zst_path = bare_path + ".zst.lock"
    return bare_path, zst_path, lock_path, lock_zst_path


def normalize_path_for_registry(path: str, study_id: str, participant_id: str) -> list[str]:
    """
    Normalize a file path to the format used in the registry.
    
    The backend needs some very specific file names, for the future we want to query for hashes,
    test those hashes and missing files, then download files that need to be updated.
    
    Returns a list of possible normalized paths (some files require multiple valid names for
    historical reasons).
    """
    folder, file_name = path.rsplit("/", 1)  # stream folder or survey+id folder
    
    # normalize the file's datetime format to true isoformat
    file_name = file_name.replace(" ", "T").replace("+00_00", "").replace("_", ":")
    if "audio_recordings" in folder or "survey_answers" in folder:
        return _normalize_surveys_special_case(file_name, folder, study_id, participant_id)
    
    # we need to provide 3 possible paths for timings because there is a ~bug on the backend
    # where it doesn't separate timings into their own files every time.
    if "survey_timings" in folder:
        return [
            f"{study_id}/{participant_id}/{folder}/{file_name}",
            f"{study_id}/{participant_id}/survey_timings/{file_name}",
            f"{study_id}/{participant_id}/surveyTimings/{file_name}",  # this one is probably wrong
        ]
    
    return [f"{study_id}/{participant_id}/{folder}/{file_name}"]


def _normalize_surveys_special_case(
    file_name: str, folder: str, study_id: str, participant_id: str
) -> list[str]:
    file_name, file_extension = file_name.rsplit(".", 1)
    # add a Z to the end to make it ISO8601 _UTC_
    t = datetime.fromisoformat(file_name + "Z").timestamp()
    unix_timestamp_1 = int(t * 1000)
    unix_timestamp_2 = int(t)
    file_name_1 = f"{unix_timestamp_1}.{file_extension}"
    file_name_2 = f"{unix_timestamp_2}.{file_extension}"
    folder = folder.replace("audio_recordings", "voiceRecording")  # just do both
    folder = folder.replace("survey_answers", "surveyAnswers")
    return [
        f"{study_id}/{participant_id}/{folder}/{file_name_1}",
        f"{study_id}/{participant_id}/{folder}/{file_name_2}"
    ]


def check_hash_cache_match(
    real_path: str, participant_id: str, file_content: bytes, hash_cache: dict[str, bytes], is_decompressed: bool
) -> bool:
    """
    If the file matches a hash in the local hash lookup return True, otherwise return False.
    The hash cache is expected to be the second value returned by generate_registry_info.
    This does not take files from the user's drive, it takes downloaded files so can't be locked.
    """
    sha1 = hash_cache.get(get_base_path(real_path, participant_id))
    if sha1 is None:
        return False
    
    if real_path.endswith('.zst') and not is_decompressed:
        file_content = decompress(file_content)
    
    return generate_base64_sha1_hash(file_content) == sha1


#
# Threadpool Helpers
#

def get_thread_count() -> int:
    """ Usually the detail we are multithreading is i/o bound, but fast SSDs are becoming more
    common virtually universal. Based on some testing on a _Very_ fast SSD our rate limit is more
    usually _the speed at which python can emit tasks_ - which is quite silly. Observed behavior is
    that at some point you hit a limit where adding more threads neither helps nor hurts. """
    if GlobalSettings.multithreading_count == 0:
        count = cpu_count() or 1  # unlikely but possibly None
        return max(1, count)
    return GlobalSettings.multithreading_count


def setup_threadpool(multithread_count: int, name: str) -> ThreadPool:
    """ Setup a thread pool with logging. """
    multithread_count = max(1, multithread_count)  # just ignore 0 and negatives
    if multithread_count > 1:
        log.info(f"Using {multithread_count} threads for {name}.")
    return ThreadPool(multithread_count)


def easy_threaded_iterate(
    func: Callable[..., T],
    name: str,
    iterable: Iterable[Any],
    *lambda_args: Any,
    **lambda_kwargs: Any,
) -> list[T]:
    """ Simple threaded iterator wrapper with logging. """
    pool = setup_threadpool(get_thread_count(), name or "easy_threaded_iterator")
    items = list(iterable)  # iterating on file names like this can save 10% overall time
    try:
        return list(
            pool.imap_unordered(
                lambda iterated: func(iterated, *lambda_args, **lambda_kwargs), items
            )
        )
    finally:
        pool.close()
        pool.join()
        pool.terminate()


# todo: add test that we decompress (don't decompress??) .mp4 files correctly
