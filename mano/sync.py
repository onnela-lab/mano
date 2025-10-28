import errno
import io
import itertools
import json
import locale
import logging
import os
import re
import sys
import tempfile as tf
import time
import zipfile
from datetime import datetime, timedelta

import cryptease as crypt
import dateutil.parser
import requests

import mano


BACKFILL_WINDOW = 5
BACKFILL_INTERVAL_SLEEP = 3
# this is the earliest possible date for data out of any Beiwe study
BACKFILL_START_DATE = '2015-9-01T00:00:00'
LOCK_EXT = '.lock'

logger = logging.getLogger(__name__)

spinner = itertools.cycle(['-', '/', '|', '\\'])


class APIError(Exception):
    pass


class DownloadError(Exception):
    pass


class ParseError(Exception):
    pass


class SaveError(Exception):
    pass


class WriteError(Exception):
    pass


def backfill(
        Keyring: dict[str, str],
        study_id: str,
        user_id: str,
        output_dir: str,
        start_date: str = BACKFILL_START_DATE,
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
    if not os.path.exists(output_dir):
        _makedirs(output_dir, umask=0o077)

    # backfill continuously until this function finally returns
    while True:
        # read backfill state from file
        user_dir = os.path.join(output_dir, user_id)
        if not os.path.exists(user_dir):
            _makedirs(user_dir)
        backfill_file = os.path.join(user_dir, '.backfill')
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
        num_saved = save(Keyring, archive, user_id, output_dir, lock, passphrase)
        logger.info(f'saved {num_saved} files')

        # wite the new resume point to the backfill file
        if resume:
            _atomic_write(backfill_file, resume.encode(encoding))
            logger.debug('waiting for next backfill interval')
            time.sleep(BACKFILL_INTERVAL_SLEEP)
        else:
            _atomic_write(backfill_file, 'COMPLETE'.encode(encoding))
            logger.info('backfill is complete')


def download(Keyring: dict[str, str], study_id: str, user_ids: list[str],
             data_streams: list[str] | None = None,
             time_start: str | None = None,
             time_end: str | None = None,
             registry: dict[str, str] | None = None,
             progress: int = 0) -> zipfile.ZipFile:
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
        time_start: datetime = dateutil.parser.parse(time_start)
    else:
        epoch = time.gmtime(0)
        time_start: datetime = datetime(epoch.tm_year, epoch.tm_mon, epoch.tm_mday)

    # process end_time
    if time_end:
        time_end: datetime = dateutil.parser.parse(time_end)
    else:
        time_end: datetime = datetime.today()

    # sanity check start and end times
    if time_start > time_end:
        raise DownloadError(f'start time {time_start} is after end time {time_end}')

    # setup request payload
    url = url.rstrip('/') + '/get-data/v1'
    payload = {
        'access_key': Keyring['ACCESS_KEY'],
        'secret_key': Keyring['SECRET_KEY'],
        'study_id': study_id,
        'user_ids': user_ids,
        'data_streams': data_streams,
        'time_start': time_start.strftime(mano.TIME_FORMAT),
        'time_end': time_end.strftime(mano.TIME_FORMAT),
        'registry': registry
    }

    # logs
    logger.debug('payload contains')
    logger.debug(f'study_id={study_id}')
    logger.debug(f'user_ids={user_ids}')
    logger.debug(f'data_streams={data_streams}')
    logger.debug(f'time_start={time_start.strftime(mano.TIME_FORMAT)}')
    logger.debug(f'time_end={time_end.strftime(mano.TIME_FORMAT)}')

    # submit download request
    resp = requests.post(url, data=payload, stream=True)
    if resp.status_code == requests.codes.NOT_FOUND:
        return None
    elif resp.status_code != requests.codes.OK:
        raise APIError(f'response not ok ({resp.status_code}) {resp.url}')

    # read response in chunks
    if progress:
        sys.stdout.write('reading response data: ')
        sys.stdout.flush()
    meter = 0

    chunk_size = 1024 * 64
    content = io.BytesIO()  # temporary storage for response content, required to use ZipFile

    # chunk_size may not be respected, at least in more recent versions of requests.
    for chunk in resp.iter_content(chunk_size=chunk_size):
        if progress and meter >= progress:
            sys.stdout.write(next(spinner))
            sys.stdout.flush()
            # sys.stdout.write('\b')  # this code was here already, but it seems... clearly wrong?
            meter = 0
        content.write(chunk)
        meter += chunk_size

    # shut down progress indicator
    if progress:
        sys.stdout.write('done.\n')
        sys.stdout.flush()

    # load reponse content into a zipfile object
    try:
        zf = zipfile.ZipFile(content)
    except zipfile.BadZipfile:
        with tf.NamedTemporaryFile(dir='.', prefix='beiwe', suffix='.zip', delete=False) as fo:
            content.seek(0)
            fo.write(content.read())
            fo.flush()
            os.fsync(fo.fileno())
        raise DownloadError(f'bad zip file written to {fo.name}')
    return zf


def _window(timestamp: str, window: int | float) -> tuple[str, str, str]:
    """
    Generate a backfill window (start, stop, and resume)
    """
    # parse the input timestamp into a datetime object
    win_start = dateutil.parser.parse(timestamp)

    # by default, the download window will *stop* at `win_start` + `window`,
    # and the next *resume* point will be the same...
    win_stop = win_start + timedelta(days=window)
    resume = win_stop

    # ...unless the next projected window stop point extends into the future, in which case the
    # window stop point will be set to the present time, but and next resume time will be null
    now = datetime.today()
    if win_stop > now:
        win_stop = now
        resume = None

    # convert all timestamps to string representation before returning
    win_start = win_start.strftime(mano.TIME_FORMAT)
    win_stop = win_stop.strftime(mano.TIME_FORMAT)
    if resume:
        resume = resume.strftime(mano.TIME_FORMAT)

    return win_start, win_stop, resume


def save(Keyring: dict[str, str], archive: zipfile.ZipFile, user_id: str, output_dir: str,
         lock: list[str] | None = None, passphrase: str | None = None):
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

    lock_ext = LOCK_EXT.lstrip('.')
    # open registry file in downloaded archive
    logger.debug('reading registry file from beiwe archive')
    with archive.open('registry', 'r') as fo:
        registry = json.loads(fo.read().decode('utf-8'))

    # if archive registry contains any entries, process them
    if registry:
        # iterate over archive members
        for member in archive.namelist():
            # skip over the registry file
            if member == 'registry':
                continue

            # debugging get information about the current archive member
            # info = archive.getinfo(member)

            # parse the data type determine if it should be encrypted
            encrypt = _parse_datatype(member, user_id) in lock
            logger.debug(f'processing archive member: {member} (lock={encrypt})')
            # create target name
            target = member
            # add lock extension to target name if necessary
            if encrypt:
                target = f'{target}.{lock_ext}'

            # detect if target exists, create the directory
            target_abs = os.path.join(output_dir, target)
            target_dir = os.path.dirname(target_abs)
            if os.path.exists(target_abs):
                os.remove(target_abs)
            if not os.path.exists(target_dir):
                _makedirs(target_dir, umask=0o5022)

            # read archive member content and encrypt it if necessary
            content = archive.open(member)

            if encrypt:
                key = crypt.kdf(passphrase)
                crypt.encrypt(content, key, filename=target_abs, permissions=0o0644)
            else:
                # write content to persistent storage
                _atomic_write(target_abs, content.read())
            num_saved += 1

        # update local registry file to avoid re-downloading these files
        local_registry_file = os.path.join(output_dir, user_id, '.registry')
        local_registry = dict()
        if os.path.exists(local_registry_file):
            with open(local_registry_file) as fo:
                local_registry = json.load(fo)

        local_registry.update(registry)
        local_registry_str = json.dumps(local_registry, indent=2)
        _atomic_write(local_registry_file, local_registry_str.encode(encoding))

    # return the number of saved files
    return num_saved


def _makedirs(path: str, umask: int = None, exist_ok: bool = True):
    """
    Create directories recursively with a temporary umask
    """
    if umask is None:
        umask = os.umask(umask)
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno == errno.EEXIST and exist_ok:
            pass
        else:
            raise e
    if umask is None:
        os.umask(umask)


def _atomic_write(filename: str, content: bytes, overwrite=True, permissions=0o0644):
    """
    Write a file by first saving the content to a temporary file first, then
    renaming the file. Overwrites silently by default o_o
    """
    filename = os.path.expanduser(filename)
    if not overwrite and os.path.exists(filename):
        raise WriteError(f"file already exists: {filename}")
    dirname = os.path.dirname(filename)
    with tf.NamedTemporaryFile(dir=dirname, prefix='.', delete=False) as tmp:
        tmp.write(content)
    os.chmod(tmp.name, permissions)
    os.rename(tmp.name, filename)


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


# function unused
# def _masked_payload(p: Dict, masked_keys=['registry', 'secret_key', 'access_key']) -> Dict:
#     """
#     Copy and mask a request payload to safely print to console
#     """
#     _p = p.copy()
#     for k in masked_keys:
#         if k in _p and _p[k]:
#             _p[k] = "***"
#     return _p
