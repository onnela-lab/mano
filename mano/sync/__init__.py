import os
import re
import io
import sys
import mano
import time
import json
import errno
import locale
import zipfile
import logging
import requests
import itertools
import getpass as gp
import tempfile as tf
import datetime as dt
import dateutil.parser
import cryptease as crypt

BACKFILL_WINDOW = 5
BACKFILL_INTERVAL_SLEEP = 3
BACKFILL_START_DATE = '2015-10-01T00:00:00'
LOCK_EXT = '.lock'

logger = logging.getLogger(__name__)

spinner = itertools.cycle(['-', '/', '|', '\\'])

def backfill(Keyring, study_id, user_id, output_dir, start_date=BACKFILL_START_DATE,
             lock=None, passphrase=None):
    '''
    Backfill a user (participant)
    '''
    encoding = locale.getpreferredencoding()
    if not os.path.exists(output_dir):
        _makedirs(output_dir, umask=0o077)
    # backfill continuously until this function finally returns
    while True:
        # read backfill state from file
        backfill_file = os.path.join(output_dir, user_id, '.backfill')
        logger.debug('reading backfill file %s', backfill_file)
        with open(backfill_file, 'a+') as fo:
            fo.seek(0)
            timestamp = fo.read().strip()
        if timestamp:
            logger.debug('backfill file contains string: %s', timestamp)
        # return immediately if backfill state file contains string COMPLETE
        if timestamp == 'COMPLETE':
            logger.debug('no backfill is necessary')
            return
        # if there is no backfill state, default to start_date
        if not timestamp:
            timestamp = start_date
            logger.debug('no backfill timestamp found, using: %s', timestamp)
        # get download window and next resume point
        start,stop,resume = _window(timestamp, BACKFILL_WINDOW)
        logger.info('processing window is [%s, %s]', start, stop)
        # download window of data
        archive = download(Keyring,
                           study_id,
                           [user_id],
                           mano.DATA_STREAMS,
                           progress=3*1024,
                           time_start=start,
                           time_end=stop)
        # save data
        num_saved = save(Keyring, archive, user_id, output_dir, lock, passphrase)
        logger.info('saved %s files', num_saved)
        # wite the new resume point to the backfill file
        if resume:
            _atomic_write(backfill_file, resume.encode(encoding))
            logger.debug('waiting for next backfill interval')
            time.sleep(BACKFILL_INTERVAL_SLEEP)
        else:
            _atomic_write(backfill_file, 'COMPLETE'.encode(encoding))
            logger.info('backfill is complete')

def download(Keyring, study_id, user_ids, data_streams=None,
             time_start=None, time_end=None, registry=None,
             progress=False):
    '''
    Request data archive from Beiwe API
    
    :param Keyring: Keyring dictionary
    :type Keyring: dict
    :param study_id: Study ID
    :type study_id: str
    :param user_ids: Subject IDs
    :type user_id: list
    :param data_streams: Data streams
    :type data_streams: list
    :param time_start: Start time
    :type time_start: str
    :param time_end: End time
    :type time_end: str
    :param registry: Registry
    :type registry: dict
    :param progress: Progress indicator (in bytes)
    :type progress: int
    :returns: Zip archive object
    :rtype: zipfile.ZipFile
    '''
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
        time_start = dateutil.parser.parse(time_start)
    else:
        epoch = time.gmtime(0)
        time_start = dt.datetime(epoch.tm_year, 
                                 epoch.tm_mon,
                                 epoch.tm_mday)
    # process end_time
    if time_end:
        time_end = dateutil.parser.parse(time_end)
    else:
        time_end = dt.datetime.today()
    # sanity check start and end times
    if time_start > time_end:
        raise DownloadError('start time %s is after end time %s' % (time_start,
                                                                    time_end))
    # submit download request
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
    logger.debug('payload >\n%s', json.dumps(_masked_payload(payload), indent=2))
    resp = requests.post(url, data=payload, stream=True)
    if resp.status_code == requests.codes.NOT_FOUND:
        return None
    elif resp.status_code != requests.codes.OK:
        raise APIError('response not ok ({0}) {1}'.format(resp.status_code, resp.url))
    # read response in chunks
    if progress:
        sys.stdout.write('reading response data: ')
        sys.stdout.flush()
    meter = 0
    chunk_size = 1024
    content = io.BytesIO()
    for chunk in resp.iter_content(chunk_size=chunk_size):
        if progress and meter >= progress:
            sys.stdout.write(next(spinner)); sys.stdout.flush()
            sys.stdout.write('\b')
            meter = 0
        content.write(chunk)
        meter += chunk_size
    # shut down progress indicator
    if progress:
        sys.stdout.write('done.\n'); sys.stdout.flush()
    # load reponse content into a zipfile object
    try:
        zf = zipfile.ZipFile(content)
    except zipfile.BadZipfile:
        with tf.NamedTemporaryFile(dir='.', prefix='beiwe',
                                   suffix='.zip', delete=False) as fo:
                content.seek(0)
                fo.write(content.read())
        raise DownloadError('bad zip file written to {0}'.format(fo.name))
    return zf

class APIError(Exception):
    pass

class DownloadError(Exception):
    pass

def _window(timestamp, window):
    '''
    Generate a backfill window (start, stop, and resume)
    '''
    # parse the input timestamp into a datetime object
    win_start = dateutil.parser.parse(timestamp)
    # by default, the download window will *stop* at `win_start` + `window`, 
    # and the next *resume* point will be the same...
    win_stop = win_start + dt.timedelta(days=window)
    resume = win_stop
    # ...unless the next projected window stop point extends into the future, 
    # in which case the window stop point will be set to the present time, but 
    # and next resume time will be null
    now = dt.datetime.today()
    if win_stop > now:
        win_stop = now
        resume = None
    # convert all timestamps to string representation before returning
    win_start = win_start.strftime(mano.TIME_FORMAT)
    win_stop = win_stop.strftime(mano.TIME_FORMAT)
    if resume:
        resume = resume.strftime(mano.TIME_FORMAT)
    return win_start,win_stop,resume

def save(Keyring, archive, user_id, output_dir, lock=None, passphrase=None):
    '''
    The order of operations here is important to ensure the ability 
    to reach a state of consistency:

        1. Save the file
        2. Update the local registry
    '''
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
            # get information about the current archive member  
            info = archive.getinfo(member)
            # parse the data type name from the current archive member
            member_datatype = _parse_datatype(member, user_id)
            # check if data type should be encrypted
            encrypt = True if member_datatype in lock else False
            logger.debug('processing archive member: %s (lock=%s)', member, encrypt)
            # create target name
            target = member
            # add lock extension to target name if necessary
            if encrypt:
                target = '{0}.{1}'.format(target, lock_ext)
            target_abs = os.path.join(output_dir, target)
            target_dir = os.path.dirname(target_abs)
            # detect if target exists
            if os.path.exists(target_abs):
                os.remove(target_abs)
            # create target directory
            if not os.path.exists(target_dir):
                _makedirs(target_dir, umask=0o5022)
            # read archive member content and encrypt it if necessary
            content = archive.open(member)
            if encrypt:
                key = crypt.kdf(passphrase)
                crypt.encrypt(content, key, filename=target_abs)
            else:
                # write content to persistent storage
                _atomic_write(target_abs, content.read())
            num_saved += 1
        # update local registry file to avoid re-downloading these files
        local_registry_file = os.path.join(output_dir, user_id, '.registry')
        local_registry = dict()
        if os.path.exists(local_registry_file):
            with open(local_registry_file, 'r') as fo:
                local_registry = json.load(fo)
        local_registry.update(registry)
        local_registry_str = json.dumps(local_registry, indent=2)
        _atomic_write(local_registry_file, local_registry_str.encode(encoding))
    # return the number of saved files
    return num_saved

class SaveError(Exception):
    pass

def _makedirs(path, umask=None, exist_ok=True):
    '''
    Create directories recursively with a temporary umask
    '''
    if umask != None:
        umask = os.umask(umask)
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno == errno.EEXIST and exist_ok:
            pass
        else:
            raise e
    if umask != None:
        os.umask(umask)

def _masked_payload(p, keys=['secret_key', 'access_key']):
    '''
    Copy and mask a request payload to safely print to console

    :param p: Payload
    :type p: dict
    :param keys: Keys to mask
    :type keys: list
    :returns: Masked payload
    :rtype: dict
    '''
    _p = p.copy()
    for k in keys:
        if k in _p and _p[k]:
            _p[k] = "***"
    return _p

def _atomic_write(filename, content, overwrite=True, permissions=0o0644):
    '''
    Write a file by first saving the content to a temporary file first, then 
    renaming the file. Overwrites silently by default o_o
    '''
    filename = os.path.expanduser(filename)
    if not overwrite and os.path.exists(filename):
        raise WriteError("file already exists: %s" % filename)
    dirname = os.path.dirname(filename)
    with tf.NamedTemporaryFile(dir=dirname, prefix='.', delete=False) as tmp:
        tmp.write(content)
    os.chmod(tmp.name, permissions)
    os.rename(tmp.name, filename)

class WriteError(Exception):
    pass

def _parse_datatype(member, user_id):
    '''
    Parse data type from a Beiwe archive member name.
    '''
    expr = '^{USER}/([a-zA-Z_]+)/.*$'
    match = re.search(expr.format(USER=user_id), member)
    if not match:
        raise ParseError('no match: regex="%s", string="%s"' % (expr, member))
    numgroups = len(match.groups())
    if numgroups != 1:
        raise ParseError('expecting 1 capture group, found %s: regex="%s", string="%s"' % (numgroups, 
                         expr, member))
    return match.group(1)

class ParseError(Exception):
    pass

