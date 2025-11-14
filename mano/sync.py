import io
import json
import locale
import logging
import os
import re
import sys
import zipfile
from datetime import datetime, timedelta
from os.path import dirname, exists as path_exists, join as path_join
from tempfile import NamedTemporaryFile
from time import sleep

import cryptease as crypt
import dateutil
import requests

import mano
from mano.constants import (BACKFILL_INTERVAL_SLEEP, BACKFILL_WINDOW, EARLIEST_POSSIBLE_DATA_DT,
    EARLIEST_POSSIBLE_DATA_STR, spinner, TIME_FORMAT, URL_COMPRESSED, URL_UNCOMPRESSED)
from mano.file_management import atomic_write, make_directories


logger = logging.getLogger(__name__)

# historical namespace items
from mano.constants import APIError, DownloadError, ParseError, SaveError, WriteError  # noqa


def backfill(
    Keyring: dict[str, str],
    study_id: str,
    user_id: str,
    output_dir: str,
    start_date: str = EARLIEST_POSSIBLE_DATA_STR,
    data_streams: list[str] | None = None,
    lock: list[str] | None = None,
    passphrase: str | None = None,
) -> None:
    """
    Backfill a user (participant)
    """
    
    encoding = locale.getpreferredencoding()
    
    if not data_streams:
        data_streams = mano.DATA_STREAMS
    
    if not path_exists(output_dir):
        make_directories(output_dir, umask=0o077)
    
    # backfill continuously until this function finally returns
    while True:
        # read backfill state from file
        user_dir = path_join(output_dir, user_id)
        if not path_exists(user_dir):
            make_directories(user_dir)
        backfill_file = path_join(user_dir, '.backfill')
        
        logger.info(f'reading backfill file {backfill_file}')
        
        with open(backfill_file, 'a+') as fo:
            fo.seek(0)
            timestamp = fo.read().strip()
        if timestamp:
            logger.debug(f'backfill file contains string: {timestamp}')
        
        # return immediately if backfill state file contains string COMPLETE
        if timestamp == 'COMPLETE':
            logger.debug('no backfill is necessary')
            return
        
        # if there is no backfill state, default to start_date
        if not timestamp:
            timestamp = start_date
            logger.debug(f'no backfill timestamp found, using: {timestamp}')
        
        # get download window and next resume point
        start, stop, resume = _window(timestamp, BACKFILL_WINDOW)
        logger.info(f'processing window is [{start}, {stop}]')
        
        # download window of data
        archive = download(
            Keyring,
            study_id,
            [user_id],
            data_streams,
            progress=3*1024,
            time_start=start,
            time_end=stop
        )
        
        # save data
        num_saved = save(archive, user_id, output_dir, lock, passphrase)
        logger.info(f'saved {num_saved} files')
        
        # wite the new resume point to the backfill file
        if resume:
            atomic_write(backfill_file, resume.encode(encoding))
            logger.debug('waiting for next backfill interval')
            sleep(BACKFILL_INTERVAL_SLEEP)
        else:
            atomic_write(backfill_file, 'COMPLETE'.encode(encoding))
            logger.info('backfill is complete')


def download(
    Keyring: dict[str, str],
    study_id: str,
    user_ids: list[str],
    data_streams: list[str] | None = None,
    time_start: str | datetime | None = None,
    time_end: str | datetime | None = None,
    registry: dict[str, str] | None = None,
    progress: int = 0,
    compressed: bool = False,
) -> zipfile.ZipFile | None:
    """
    Request data archive from Beiwe API
    
    :param progress: Progress indicator (in bytes)
    :type progress: int
    :returns: Zip archive object
    :rtype: zipfile.ZipFile
    """
    
    if not registry:
        registry = dict()
    if not user_ids:
        user_ids = list()
    if not data_streams:
        data_streams = list()
    
    # base url for beiwe instance
    url = Keyring['URL']
    
    # process start_time
    if time_start:
        if isinstance(time_start, str):
            time_start = dateutil.parser.parse(time_start)
    else:
        time_start = EARLIEST_POSSIBLE_DATA_DT
    
    # process end_time
    if time_end:
        if isinstance(time_end, str):
            time_end = dateutil.parser.parse(time_end)
    else:
        time_end = datetime.today()
    
    assert isinstance(time_start, datetime)  # mypy can get confused here
    assert isinstance(time_end, datetime)
    
    # sanity check start and end times
    if time_start > time_end:
        raise DownloadError(f'start time {time_start} is after end time {time_end}')
    
    # setup request payload
    url = url.rstrip('/') + (URL_COMPRESSED if compressed else URL_UNCOMPRESSED)
    payload = {
        'access_key': Keyring['ACCESS_KEY'],
        'secret_key': Keyring['SECRET_KEY'],
        'study_id': study_id,
        'user_ids': user_ids,
        'data_streams': data_streams,
        'time_start': time_start.strftime(TIME_FORMAT),
        'time_end': time_end.strftime(TIME_FORMAT),
        'registry': registry,
    }
    
    # logs
    logger.debug('payload contains')
    logger.debug(f'study_id={study_id}')
    logger.debug(f'user_ids={user_ids}')
    logger.debug(f'data_streams={data_streams}')
    logger.debug(f'time_start={time_start.strftime(TIME_FORMAT)}')
    logger.debug(f'time_end={time_end.strftime(TIME_FORMAT)}')
    
    # submit download request
    resp = requests.post(url, data=payload, stream=True)
    if resp.status_code == requests.codes.NOT_FOUND:
        return None
    elif resp.status_code != requests.codes.OK:
        raise APIError(f'response not ok ({resp.status_code}) {resp.url}')
    
    # read response in chunks
    if progress:
        print('reading response data: ', end='', flush=True)
    meter = 0
    
    chunk_size = 1024 * 64
    content = io.BytesIO()  # temporary storage for response content, required to use ZipFile
    
    # chunk_size may not be respected, at least in more recent versions of requests.
    for chunk in resp.iter_content(chunk_size=chunk_size):
        if progress and meter >= progress:
            sys.stdout.write(next(spinner))
            sys.stdout.flush()
            sys.stdout.write('\b')  # backspace, not flushed
            meter = 0
        content.write(chunk)
        meter += chunk_size
    
    # shut down progress indicator
    if progress:
        print('done.')
    
    # load response content into a zipfile object
    try:
        zf = zipfile.ZipFile(content)
    except zipfile.BadZipfile as e:
        with NamedTemporaryFile(dir='.', prefix='beiwe', suffix='.zip', delete=False) as fo:
            content.seek(0)
            fo.write(content.read())
            fo.flush()
            os.fsync(fo.fileno())
        raise DownloadError(f'bad zip file written to {fo.name}') from e
    return zf


def save(
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
    logger.debug('reading registry file from beiwe archive')
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
    """
    Handle one file from inside a ZipFile Archive
    """
    
    if file_name == 'registry':  # skip the registry file
        return False
    
    # info = archive.getinfo(member)  # debugging get information about the current archive member
    
    # parse the data type determine if it should be encrypted
    encrypt = _parse_datatype(file_name, user_id) in lock
    logger.debug(f'processing archive member: {file_name} (lock={encrypt})')
    
    output_filename = f'{file_name}.lock' if encrypt else file_name  # lock extension if we need it
    
    # detect if target exists, create the directory
    if path_exists(target_abs:= path_join(output_dir, output_filename)):
        os.remove(target_abs)
    if not path_exists(target_dir:= dirname(target_abs)):
        make_directories(target_dir, umask=0o5022)
    
    # read archive member content and encrypt it if necessary
    file_content = archive.open(file_name)
    
    if encrypt:
        key = crypt.kdf(passphrase)
        crypt.encrypt(file_content, key, filename=target_abs, permissions=0o0644)
    else:
        # write content to persistent storage
        atomic_write(target_abs, file_content.read())
    
    return True


## Helper functions


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


def _window(timestamp: str, window: int | float) -> tuple[str, str, str | None]:
    """
    Generate a backfill window (start, stop, and resume)
    """
    
    # parse the input timestamp into a datetime object
    win_start = dateutil.parser.parse(timestamp)
    
    # by default, the download window will *stop* at `win_start` + `window`,
    # and the next *resume* point will be the same...
    window_stop = win_start + timedelta(days=window)
    resume: datetime | None = window_stop  # mypy wants this explicit type hint
    
    # ...unless the next projected window stop point extends into the future, in which case the
    # window stop point will be set to the present time, but and next resume time will be null
    now = datetime.today()
    if window_stop > now:
        window_stop = now
        resume = None
    
    # convert all timestamps to string representation before returning
    win_start_str = win_start.strftime(TIME_FORMAT)
    win_stop_str = window_stop.strftime(TIME_FORMAT)
    resume_str = resume.strftime(TIME_FORMAT) if resume else None
    
    return win_start_str, win_stop_str, resume_str
