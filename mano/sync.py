import itertools
import locale
import logging
import zipfile
from datetime import datetime, timedelta
from io import BytesIO
from os import fsync
from os.path import exists as path_exists, join as path_join
from pprint import pformat
from sys import stdout
from tempfile import NamedTemporaryFile
from time import perf_counter, sleep

import dateutil
import requests
from dateutil.tz import UTC
from requests.models import Response

import mano
from mano.constants import (ALL_DATA_STREAMS, BACKFILL_INTERVAL_SLEEP, BACKFILL_WINDOW,
    BadTimezoneError, EARLIEST_POSSIBLE_DATA_STR, log, TIME_FORMAT, URL_COMPRESSED,
    URL_UNCOMPRESSED)
from mano.file_management import atomic_write, make_directories, save_encrypted
from mano.messages import (NO_TIME_MSG, NOT_200_OK_MSG, PICK_USER_PARTICIPANT_MSG,
    PROGRESS_DEPRECATION_MSG, SYNC_SAVE_DEPRECATION_MSG, TIME_NAIVE_MSG, TIME_NOT_UTC_MSG,
    TIME_PARSED_MSG, USER_IDS_DEPRECATION_MSG)


# historical namespace items
from mano.constants import APIError, DownloadError, ParseError, SaveError, WriteError;  # noqa


# very verbose type hint(s)
RequestPayload = dict[str, str | list[str] | dict[str, str]]


#TODO: make sure the time validation logic matches the documentation below.
#TODO: implement registry file generation and other management tools.
#TODO: implement warnings for deprecated parameters.
#TODO: Fix tests, something has changed from the data download refactor.
#TODO: Aggressively hook in the registry? Aggressively regenerate the registry? Always regenerate it?
#TODO: does the spinner need to be intrinsicly dependant on stdout?
#TODO: Backfill.


def download(
    Keyring: dict[str, str],                   # Your loaded credentials (see documentation).
    study_id: str,                             # The target Study ID.
    
    # Data Filters
    participant_ids: list[str] | None = None,  # List of participant IDs to target.
    data_streams: list[str] | None = None,     # List of data streams to target.
    time_start: str | datetime | None = None,  # Limit to only data AFTER this time.
    time_end: str | datetime | None = None,    # Limit to only data BEFORE this time.
    
    # Behavior
    registry: dict[str, str] | None = None,    # A special dictionary to avoid re-downloading files.
    compressed: bool = False,                  # Download compressed data. (DEFAULT WILL CHANGE.)
    
    # Deprecated
    # Deprecated parameters will be removed in future releases of Mano, they will emit warnings.
    progress: int = 0,                         # Show the progress every N bytes.
    user_ids: list[str] | None = None,         # alias of participant_ids.
) -> zipfile.ZipFile:
    """
    Download Beiwe Platform Study Data from the Data Access API.
    :returns: A [standard library] ZipFile object containing the downloaded data.
    
    #
    # Required parameters
    #
    
    :param `Keyring`: Credentials dictionary - See documentation for details on how to safely store
        and load your Beiwe API credentials.
    
    :param `study_id`: The Study ID to download data from - The API requires that a data download
        request specify a Study ID.
    
    #
    # Recommended Parameters
    #
    
    :param `compressed`: A boolean to indicate whether to download compressed data.
        
        We highly recommend downloading compressed data.
        
        Compressed data uses ZSTD ("zee-standard"), which has virtually no downsides.
            At the settings we use is roughly 1/5th the size of uncompressed data.
            It downloads faster.
            It helps us out with server load and bandwidth costs.
            ZSTD is FAST. At our settings hundreds of MB/s, even on hardware from ~2013.
        
        Mano includes tools (including a Command Line Interface) for managing compressed data.
            Type `mano` on the command line (make sure to activate the Python environment first)
            (Graphical tools and OSes are catching up, adding ZSTD support all the time.)
        
            The API is unchanged, it still encapsulates files (now ending in ".zst") in a Zip file.
        
        Other Notes:
            Servers running old versions of The Beiwe Platform may not support compressed downloads.
            The default value of this parameter WILL CHANGE TO TRUE in a future release of Mano.
    
    :param registry: A dictionary mapping Beiwe file identifiers to file content hashes.
        (A hash is a small "fingerprint" that can be calculated from the binary content of a file.)
        
        We highly recommend including a registry file
        
        This "registry" file is provided by Mano and The Beiwe Platform, it serves a few purposes.
            You can provide it in the request, and the backend will inspect it.
            It will then only provide you with files that have non-matching (updated) hashes.
                E.g. only download data that is new or updated.
            You can use the hash information to validate that your downloaded files are correct.
            Even if you delete your registry, you can easily generate a registry file from  your
                current downloaded data - even on compressed data this process is quick.
            (We use an SHA1 hash, which is extremely fast and sufficiently collision-resistant)
    
    #
    # Data Filters
    #
    
    :param participant_ids: A list of participant ("user") IDs to limit data to.
        None means "all participants".
    
    :param data_streams: A list of data streams to limit data to. None means "all data streams".
    
    :param time_start: A datetime or string representing the earliest time to download data from.
        None means "no start time filter".
        
        -Data on The Beiwe Platform is recorded in UTC time.
        -Date/Time _strings_ provided to Mano will be interpreted as UTC times.
        -Python datetime _objects_ with non-UTC timezones will be converted to UTC via the
            `datetime.astimezone(UTC)` datetime standard library function.
        -Timezone-Naive datetime objects (those lacking a tzinfo attribute) will be treated as UTC.
    
    :param time_end: A datetime or string representing the latest time to download data from.
        None means "no end time filter".
        (see detailed notes above for the `time_start` parameter)
    
    #
    # Other
    #
    
    :param progress: (DEPRECATED)
        Formerly: "Show a progress indicator every N bytes downloaded."
        This parameter may be ignored.
        This parameter is deprecated, use `debug_level` to control output instead.
        The spinner is shown at INFO and DEBUG levels.
        The spinner now advances (roughly) every time a component file is received from the server,
            depending on system, network, and server conditions.
    """
    
    # this function is just a wrapper to handle deprecated parameter names, and provide documentation
    # for usage of Mano's raison d'être functionality closer to the top of a file.
    
    # handle deprecated parameter `user_ids`
    if user_ids:
        log.warning(USER_IDS_DEPRECATION_MSG)
    if user_ids and participant_ids:
        log.error(PICK_USER_PARTICIPANT_MSG)
        raise ValueError(PICK_USER_PARTICIPANT_MSG)
    if user_ids and not participant_ids:
        participant_ids = user_ids
    
    # handle deprecated parameter `progress`
    if progress:
        log.warning(PROGRESS_DEPRECATION_MSG)
    
    return _download(
        Keyring,
        study_id,
        compressed=compressed,
        data_streams=data_streams,
        registry=registry,
        time_end=time_end,
        time_start=time_start,
        participant_ids=participant_ids,
    )


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
        
        log.info(f'reading backfill file {backfill_file}')
        
        with open(backfill_file, 'a+') as fo:
            fo.seek(0)
            timestamp = fo.read().strip()
        if timestamp:
            log.debug(f'backfill file contains string: {timestamp}')
        
        # return immediately if backfill state file contains string COMPLETE
        if timestamp == 'COMPLETE':
            log.debug('no backfill is necessary')
            return
        
        # if there is no backfill state, default to start_date
        if not timestamp:
            timestamp = start_date
            log.debug(f'no backfill timestamp found, using: {timestamp}')
        
        # get download window and next resume point
        start, stop, resume = _window(timestamp, BACKFILL_WINDOW)
        log.info(f'processing window is [{start}, {stop}]')
        
        # download window of data
        archive = download(
            Keyring,
            study_id,
            [user_id],
            data_streams,
            time_start=start,
            time_end=stop
        )
        
        # save data
        num_saved = save(archive, user_id, output_dir, lock, passphrase)
        log.info(f'saved {num_saved} files')
        
        # wite the new resume point to the backfill file
        if resume:
            atomic_write(backfill_file, resume.encode(encoding))
            log.debug('waiting for next backfill interval')
            sleep(BACKFILL_INTERVAL_SLEEP)
        else:
            atomic_write(backfill_file, 'COMPLETE'.encode(encoding))
            log.info('backfill is complete')


def _download(
    Keyring: dict[str, str],
    study_id: str,
    compressed: bool = False,
    data_streams: list[str] | None = None,
    registry: dict[str, str] | None = None,
    time_end: str | datetime | None = None,
    time_start: str | datetime | None = None,
    participant_ids: list[str] | None = None,
) -> zipfile.ZipFile:
    """
    Internal function to handle download logic, do not call directly.
    """
    
    registry = registry or dict[str, str]()  # (shorthand to convert Nones to containers)
    participant_ids = participant_ids or list[str]()
    data_streams = data_streams or list[str]()
    
    # base url for beiwe instance
    url = normalize_url(Keyring['URL']) + (URL_COMPRESSED if compressed else URL_UNCOMPRESSED)
    
    time_start = handle_one_time_input(time_start, "time_start")
    time_end = handle_one_time_input(time_end, "time_end")
    
    # sanity check start and end times
    if time_start and time_end and time_start > time_end:
        raise DownloadError(f"The provided start_time {time_start} is after end_time {time_end}")
    
    validate_data_streams(data_streams)
    
    # setup request payload
    payload: RequestPayload = {
        "access_key": Keyring["ACCESS_KEY"],
        "secret_key": Keyring["SECRET_KEY"],
        "study_id": study_id,  # required
    }
    if data_streams:
        payload["data_streams"] = data_streams
    if participant_ids:
        payload["user_ids"] = participant_ids
    if time_start:
        payload["time_start"] = time_start.strftime(TIME_FORMAT)
    if time_end:
        payload["time_end"] = time_end.strftime(TIME_FORMAT)
    if registry:
        payload["registry"] = registry
    
    # don't log sensitive information
    dummy_payload = {k: v for k, v in payload.items() if k not in ("access_key", "secret_key")}
    log.debug(f"download parameters: {pformat(dummy_payload, width=20000)}")
    
    return _do_download(url, payload)


def _do_download(url: str, payload: RequestPayload) -> zipfile.ZipFile:
    """ Internal function to handle download logic, do not call directly. """
    
    show_progress = log.getEffectiveLevel() >= logging.INFO
    content = BytesIO()  # temporary (RAM) storage for response content, required to use ZipFile
    
    # submit download request
    resp = requests.post(url, data=payload, stream=True)
    if resp.status_code != requests.codes.OK:
        log.error(err_msg := NOT_200_OK_MSG(resp.status_code, resp.url))
        raise APIError(err_msg)
    
    log.info('Server responded, reading zip data... ')
    size, t_start, t_end = iterate_with_spinner(resp, content, show_progress)
    log.info('Download finished.')
    MBps = (size / 1024 / 1024) / (t_end - t_start)
    log.info(f'Download took {t_end - t_start:.2f} seconds (average of {MBps:.2f} MB/s)')
    
    # load response content into a zipfile object
    try:
        return zipfile.ZipFile(content)
    except zipfile.BadZipfile as e:
        # TODO: stick in a helper
        with NamedTemporaryFile(dir='.', prefix='beiwe', suffix='.zip', delete=False) as fo:
            content.seek(0)
            fo.write(content.read())
            fo.flush()
            fsync(fo.fileno())
            log.warning(f'A bad zip file written to `{fo.name}` for debugging')
        raise DownloadError(f'bad zip file written to {fo.name}') from e


def iterate_with_spinner(
    resp: Response, bytesio: BytesIO, show_progress: bool
) -> tuple[int, float, float]:
    spinner = itertools.cycle(['-', '/', '|', '\\'])
    
    t_start = perf_counter()  # hard to disentangle log statements from time measurement...
    
    # chunk_size of None reads in the existing buffer, of whatever size buffer was as determined by
    # the IO system (or implementation detail of the requests library). This should tend to
    # correlate with individual _files as they are sent by the server, which pulls in data as it
    # arrives, file by file. (TCP and OS details probably also influence this.)
    threshold = 1024 * 1024 * 2  # 2 MB chunks
    loop_progress = 0
    size = 0
    
    # download loop, get the bytes
    for chunk in resp.iter_content(chunk_size=None):
        bytesio.write(chunk)
        size += len(chunk)
        loop_progress += len(chunk)
        
        # rotate spinner
        if show_progress and loop_progress >= threshold:
            out = f"{next(spinner)} ({(size / 1024 / 1024):.2f} MB)"
            stdout.write(out)
            stdout.flush()
            stdout.write('\b' * len(out))  # backspaces, not flushed
            loop_progress = 0
    
    # spinner cleanup
    if show_progress:
        stdout.write("\r\n")
        stdout.flush()
    
    t_end = perf_counter()
    return size, t_start, t_end


def save(
    archive: zipfile.ZipFile | None,
    user_id: str,
    output_dir: str,
    lock: list[str] | None = None,
    passphrase: str | None = None,
) -> int:
    log.warning(SYNC_SAVE_DEPRECATION_MSG)
    return save_encrypted(archive, user_id, output_dir, lock, passphrase)


#
# Helper functions
#


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


def normalize_url(url: str) -> str:
    """ Ensure URL is https and has no trailing slashes. """
    url = url.strip()
    
    if url == '':
        raise ValueError('An empty URL provided')
    
    if url.startswith('http://'):  # force https
        url = 'https://' + url[7:]
    
    if not url.startswith('https://'):  # add https
        url = 'https://' + url
    
    return url.rstrip('/')  # strip [any number of] trailing slashes


def handle_one_time_input(
    dt: str | datetime | None, name: str, ignore_tz: bool = True
) -> datetime | None:
    """ Process one time input parameter - a returned value of None indicates no time filter. """
    
    # empty string and None
    if dt is None or not dt:
        log.debug(NO_TIME_MSG(name))
        return None
    
    # string input
    if isinstance(dt, str):
        time_str = dt
        dt = dateutil.parser.parse(dt)
        log.debug(TIME_PARSED_MSG(name, time_str, dt))
    
    # naive datetime
    if dt.tzinfo is None:
        log.debug(TIME_NAIVE_MSG(name))
        dt = dt.astimezone(UTC)
    
    # non-UTC timezone
    if dt.tzinfo != UTC:
        if not ignore_tz:
            raise BadTimezoneError(TIME_NOT_UTC_MSG(name, dt, "is invalid."))
        
        dt = dt.astimezone(UTC)
        log.warning(TIME_NOT_UTC_MSG(name, dt, "has been converted to UTC."))
    
    return dt


def validate_data_streams(data_streams: list[str]) -> None:
    """ Validate data streams against known Beiwe data streams. """
    invalid_streams = sorted([ds for ds in data_streams if ds not in ALL_DATA_STREAMS])
    
    for stream in invalid_streams:
        log.error(f'Invalid data stream: {stream}')
    
    if invalid_streams:
        raise ValueError(f'invalid data streams: {", ".join(invalid_streams)}')
