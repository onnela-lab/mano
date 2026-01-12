import itertools
import logging
import zipfile
from datetime import date, datetime, timedelta
from io import BytesIO
from os import fsync, remove as delete_file
from os.path import exists as file_exists, join as path_join
from pprint import pformat
from sys import stdout
from tempfile import NamedTemporaryFile
from time import perf_counter

import orjson
import requests
from dateutil.parser import parse as dateutil_parse, ParserError
from dateutil.tz import UTC
from requests.models import Response

from mano.constants import (ALL_DATA_STREAMS, API_TIME_FORMAT, BACKFILL_WINDOW,
    EARLIEST_POSSIBLE_DATA_DT, log, UnParsableTimeError, URL_COMPRESSED, URL_UNCOMPRESSED)
from mano.file_management import generate_registry_info, make_directories, save_archive
from mano.messages import (BACKFILL_LOCK_AND_PASSPHRASE_MSG, BACKFILL_START_DATE_FUTURE_MSG,
    BACKFILL_UNPARSABLE_DATE_MSG, COULD_NOT_PARSE_TIME_MSG, DOWNLOAD_COMMA_IN_PARTICIPANTS_WARNING,
    full_dt_format, INVALID_DATA_STREAMS_MSG, NO_TIME_MSG, NOT_200_OK_MSG,
    PICK_USER_PARTICIPANT_PLURAL_MSG, PICK_USER_PARTICIPANT_SINGLE_MSG, PROGRESS_DEPRECATION_MSG,
    SYNC_SAVE_DEPRECATION_MSG, TIME_NAIVE_MSG, TIME_NOT_UTC_MSG, TIME_PARSED_MSG, TIME_REQUIRED_MSG,
    USER_ID_KEYWORD_DEPRECATION_MSG, USER_IDS_DEPRECATION_MSG, X_IS_NOT_A_Y_MSG)


# historical namespace items
from mano.constants import APIError, DownloadError, ParseError, SaveError, WriteError;  # noqa


# very verbose type hint(s)
RequestPayload = dict[str, str | list[str] | dict[str, str]]

# todo: how exactly does the registry parameter work on the download function.
#TODO: implement registry file generation and other management tools.
#TODO: Aggressively hook in the registry? Aggressively regenerate the registry? Always regenerate it?
#TODO: does the spinner need to be intrinsically dependant on stdout?


def download(
    Keyring: dict[str, str],                   # Your loaded credentials (see documentation).
    study_id: str,                             # The target Study ID.
    
    # Data Filters
    participant_ids: str | list[str] | None = None,  # List of participant IDs to target.
    data_streams: list[str] | None = None,     # List of data streams to target.
    time_start: str | datetime | None = None,  # Limit to only data AFTER this time.
    time_end: str | datetime | None = None,    # Limit to only data BEFORE this time.
    
    # Behavior
    registry: dict[str, str] | None = None,    # A special dictionary to avoid re-downloading files.
    compressed: bool = False,                  # Download compressed data. (DEFAULT WILL CHANGE.)
    
    # Deprecated
    # Deprecated parameters will be removed in future releases of Mano, they will emit warnings.
    progress: int = 0,                         # Show the progress every N bytes.
    user_ids: str | list[str] | None = None,         # alias of participant_ids.
) -> zipfile.ZipFile:
    """
    A simple function to download Beiwe Platform Study Data from the Beiwe Data Access API.
    :returns: A [standard library] ZipFile object containing the downloaded data.
    
    #
    # Required parameters
    #
    
    :param Keyring: Credentials dictionary - See documentation for details on how to safely store
        and load your Beiwe API credentials at https://github.com/onnela-lab/mano/
    
    :param study_id: The Study ID to download data from
        The Beiwe Data Access API requires that a data download request specify a Study ID.
        A Study ID is a 24 character long string that uniquely identifies your study.
        The Study ID can be found on your Beiwe Platform website directly on your Study's page.
    
    #
    # Recommended Parameters
    #
    
    :param compressed: A boolean to indicate whether to download compressed data.
        
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
    
    :param participant_ids: A list of participant ("user") IDs to download data for.
        None or an empty list means "all participants".
    
    :param data_streams: A list of data streams to download.
        None or an empty list means "all data streams".
    
    :param time_start: A datetime or string representing the earliest time to download data from.
        None string means "no start time filter".
        Notes about timezones:
        - Data on The Beiwe Platform is recorded and handled in UTC time.
        - Python datetime _objects_ with timezones WILL BE TIME-SHIFTED to UTC.
        - Timezone-Naive datetime objects (without tzinfo) will be treated as UTC.
        - Date/Time _strings_ provided to Mano will usually be interpreted as UTC times, but if they
            are parsed to include a timezone they will be time-shifted to UTC time.
    
    :param time_end: A datetime or string representing the latest time to download data from.
        None means "no end time filter".
        (please see detailed notes above about timezones)
    
    #
    # Other
    #
    
    :param progress: (DEPRECATED)
        Formerly: "Show a progress indicator every N bytes downloaded."
        This parameter is deprecated and will be ignored, use `debug_level` to control output instead.
        The spinner is shown at INFO and DEBUG levels.
        The spinner now advances (roughly) every time a component file is received from the server,
            depending on system, network, and server conditions.
    """
    
    # this function is just a wrapper to handle deprecated parameter names, and provide documentation
    # for usage of Mano's raison d'être functionality closer to the top of a file.
    
    # Deprecations - user_ids -> participant_ids, progress -> debug_level
    if user_ids:
        log.warning(USER_IDS_DEPRECATION_MSG)
        # raise type error early
        if not isinstance(user_ids, (list, type(None), str)):
            log.error(
                msg :=  # worst formatting ever...
                X_IS_NOT_A_Y_MSG("user_ids", "str, list[str], or None", user_ids, "download")
            )
            raise TypeError(msg)
    
    if user_ids and participant_ids:
        log.error(PICK_USER_PARTICIPANT_PLURAL_MSG)
        raise ValueError(PICK_USER_PARTICIPANT_PLURAL_MSG)
    if user_ids and not participant_ids:
        participant_ids = user_ids
    
    if progress:
        log.warning(PROGRESS_DEPRECATION_MSG)
    
    if not isinstance(Keyring, dict):
        log.error(msg := X_IS_NOT_A_Y_MSG("Keyring", dict, Keyring, "download"))
        raise TypeError(msg)
    if not isinstance(study_id, str):
        log.error(msg := X_IS_NOT_A_Y_MSG("study_id", str, study_id, "download"))
        raise TypeError(msg)
    if not isinstance(participant_ids, (list, type(None), str)):
        log.error(
            msg :=  # worst formatting ever...
            X_IS_NOT_A_Y_MSG("participant_ids", "list[str] or None", participant_ids, "download")
        )
        raise TypeError(msg)
    if not isinstance(time_start, (str, datetime, type(None))):
        log.error(
            msg := X_IS_NOT_A_Y_MSG("time_start", "str, datetime, or None", time_start, "download")
        )
        raise TypeError(msg)
    if not isinstance(time_end, (str, datetime, type(None))):
        log.error(
            msg := X_IS_NOT_A_Y_MSG("time_end", "str, datetime, or None", time_end, "download")
        )
        raise TypeError(msg)
    if not isinstance(data_streams, (list, type(None))):
        log.error(
            msg := X_IS_NOT_A_Y_MSG("data_streams", "list[str] or None", data_streams, "download")
        )
        raise TypeError(msg)
    if not isinstance(registry, (dict, type(None))):
        log.error(msg := X_IS_NOT_A_Y_MSG("registry", "dict or None", registry, "download"))
        raise TypeError(msg)
    if not isinstance(compressed, bool):
        log.error(msg := X_IS_NOT_A_Y_MSG("compressed", bool, compressed, "download"))
        raise TypeError(msg)
    if not isinstance(progress, int):
        log.error(msg := X_IS_NOT_A_Y_MSG("progress", int, progress, "download"))
        raise TypeError(msg)
    
    # handle participant_ids as str or list[str]
    if isinstance(participant_ids, str):
        if "," in participant_ids:
            # individually strip whitespace and ignore empty strings
            # (note: this exists only to support existing, known use-cases, do not document it in
            # the big documentation section above, this is not a recommended usage pattern.)
            participant_ids = [p_id.strip() for p_id in participant_ids.split(",") if p_id.strip()]
            log.warning(DOWNLOAD_COMMA_IN_PARTICIPANTS_WARNING)
        else:
            participant_ids = [participant_ids.strip()]
    
    # convert None to empty collections
    registry = registry or {}
    participant_ids = participant_ids or []
    data_streams = data_streams or []
    
    time_start = validate_datetime(time_start, "time_start")
    time_end = validate_datetime(time_end, "time_end")
    
    # sanity check start and end times
    if time_start and time_end and time_start > time_end:
        raise DownloadError(f"The provided start_time {time_start} is after end_time {time_end}")
    
    validate_data_streams(data_streams, "download - `data_streams`")
    
    return _download(
        Keyring, study_id, compressed, data_streams, registry, time_start, time_end, participant_ids
    )


def backfill(
    # Required parameters:
    Keyring: dict[str, str],                        # Your loaded credentials (see documentation).
    study_id: str,                                  # The target Study ID.
    participant_id: str,                            # The target participant's ID.
    output_dir: str,                                # Directory to save downloaded data.
    
    # Optional parameters:
    start_date: str | datetime | date = EARLIEST_POSSIBLE_DATA_DT,   # Date/time to start backfill from.
    end_date: str | datetime | date | None = None,  # Date/time to stop backfill at.
    data_streams: list[str] | None = None,          # List of data streams to backfill.
    lock: list[str] | None = None,                  # List of files to lock during backfill.
    passphrase: str | None = None,                  # Passphrase for encryption.
    compressed: bool = False,                       # Compress downloaded data.
    
    # Deprecated
    user_id: str | None = None,                     # DEPRECATED alias of participant_id.
) -> None:
    """
    Backfill is a somewhat more robust data download mechanism than the simple download function,
    and we encourage users to try it out.
    
    Backfill downloads data in smaller chunks for a participant, starting from a specified date.
    By splitting up the requests we can address some common real-world difficulties:
    - Data on the Beiwe platform may be uploaded late for any number of real-world reasons.
      Backfill automates the built-in "registry" feature of the Beiwe Data Access API to avoid
      re-downloading data you already have.
    - The quantity of data produced by participants may be large and take time, so they may be
      interrupted. For instance [and Onnela Lab has confirmed a few cases where] downloads can get
      cut off by overenthusiastic campus firewalls or intrusion detection systems, perfect wifi is
      a myth, rural internet is always problematic, etc.
    
    This function helps to "backfill" data that arrives late.
    
    #
    # Required parameters
    #
    
    :param Keyring: Credentials dictionary - See documentation for details on how to safely store
        and load your Beiwe API credentials at https://github.com/onnela-lab/mano/
    
    :param study_id: The Study ID to download data from
        The Beiwe Data Access API requires that a data download request specify a Study ID.
        A Study ID is a 24 character long string that uniquely identifies your study.
        The Study ID can be found on your Beiwe Platform website directly on your Study's page.
    
    :param participant_id: The participant on your study to run backfill for.
        A participant ID is an 8 character string that identifies a participant in your study.
    
    :param output_dir: the folder in which to save downloaded data.
        A subfolder with the participant ID will be created if it does not already exist.
        
    :param start_date: The date from which to start backfilling data.
        This can be a date, datetime, or string parseable by dateutil.parser (but we recommend
        the ISO-8601 format, e.g. "2023-06-15" or "2023-06-15T00:00:00Z" to avoid ambiguity).
        Dates are interpreted as start of day (midnight, 12:00 AM).
        The default value is September 1, 2015, the earliest possible date for any data that
          any Beiwe study could possibly have.
        If the provided start date is in the future, backfill will exit without doing anything.
        Be aware that the Beiwe platform expects all times to be in the UTC timezone.
    
    #
    # Optional parameters
    #
    :param end_date: The date at which to stop backfilling data - defaults to start of day tomorrow.
        Type and formatting expectations are the same as `start_date`, except this isoptional.
    
    :param data_streams: A list of the data streams to download.
        If None or an empty list is provided all data streams will be downloaded.
    
    :param lock: A list of data streams to "lock" (encrypt) during backfill.
        If None or an empty list is provided no data streams will be encrypted.
    
    :param passphrase: The encryption key _for your Keyring_ to then access the decryption keys.
        If None is provided no encryption will be performed.
        Must be paired with a non-empty `lock` parameter.
    
    :param user_id: (DEPRECATED) An alias of `participant_id`.
    """
    # do all the user_id -> participant_id handling first, including its type checking
    if user_id is not None:
        log.warning(USER_ID_KEYWORD_DEPRECATION_MSG)
        if not isinstance(user_id, str):
            raise TypeError(X_IS_NOT_A_Y_MSG("user_id", str, user_id, "backfill"))
    
    if user_id and participant_id:
        log.error(PICK_USER_PARTICIPANT_SINGLE_MSG)
        raise ValueError(PICK_USER_PARTICIPANT_SINGLE_MSG)
    if user_id and not participant_id:
        participant_id = user_id
    
    # Type checking messages
    if not isinstance(Keyring, dict):
        log.error(msg := X_IS_NOT_A_Y_MSG("Keyring", dict, Keyring, "backfill"))
        raise TypeError(msg)
    if not isinstance(study_id, str):
        log.error(msg := X_IS_NOT_A_Y_MSG("study_id", str, study_id, "backfill"))
        raise TypeError(msg)
    if not isinstance(participant_id, (str, type(None))):
        log.error(msg := X_IS_NOT_A_Y_MSG("participant_id", "str or None", participant_id, "backfill"))
        raise TypeError(msg)
    if not isinstance(output_dir, str):
        log.error(msg := X_IS_NOT_A_Y_MSG("output_dir", str, output_dir, "backfill"))
        raise TypeError(msg)
    if not isinstance(start_date, (str, datetime, date)):
        log.error(msg := X_IS_NOT_A_Y_MSG("start_date", "str, datetime, or date", start_date, "backfill"))
        raise TypeError(msg)
    if not isinstance(end_date, (str, datetime, date, type(None))):
        log.error(msg := X_IS_NOT_A_Y_MSG("end_date", "str, datetime, date, or None", end_date, "backfill"))
        raise TypeError(msg)
    if not isinstance(data_streams, (type(None), list)):
        log.error(msg := X_IS_NOT_A_Y_MSG("data_streams", "list of strings or None", data_streams, "backfill"))
        raise TypeError(msg)
    if not isinstance(lock, (type(None), list)):
        log.error(msg := X_IS_NOT_A_Y_MSG("lock", "list of strings or None", lock, "backfill"))
        raise TypeError(msg)
    if not isinstance(compressed, bool):
        log.error(msg := X_IS_NOT_A_Y_MSG("compressed", bool, compressed, "backfill"))
        raise TypeError(msg)
    if not isinstance(passphrase, (type(None), str)):
        log.error(msg := X_IS_NOT_A_Y_MSG("passphrase", "str or None", passphrase, "backfill"))
        raise TypeError(msg)
    
    # and then if they are still None convert them to empty lists
    data_streams = data_streams or []
    lock = lock or []
    passphrase = passphrase or None  # normalize empty string to None
    
    # require both lock and passphrase if either is provided
    if int(bool(lock)) + int(bool(passphrase)) == 1:
        if not lock:
            log.error(msg := BACKFILL_LOCK_AND_PASSPHRASE_MSG("lock", "passphrase"))
            raise ValueError(msg)
        if not passphrase:
            log.error(msg := BACKFILL_LOCK_AND_PASSPHRASE_MSG("passphrase", "lock"))
            raise ValueError(msg)
    
    # more type checking of list contents
    if data_streams:
        for ds in data_streams:
            if not isinstance(ds, str):
                log.error(msg := X_IS_NOT_A_Y_MSG("data_streams item", str, ds, "backfill"))
                raise TypeError(msg)
        validate_data_streams(data_streams, "backfill - `data_streams`")
    
    if lock:
        for lk in lock:
            if not isinstance(lk, str):
                log.error(msg := X_IS_NOT_A_Y_MSG("lock item", str, lk, "backfill"))
                raise TypeError(msg)
        validate_data_streams(lock, "backfill - `lock`")
    
    # start date cannot be an empty string
    if start_date == "" or end_date == "":
        raise ValueError("Backfill's `start_date` and `end_date` parameters cannot be empty strings.")
    
    # ensure start_date is a datetime, remove the tzinfo
    try:
        start_date = validate_required_datetime(start_date, "backfill - start_date")
        start_date = start_date.replace(tzinfo=None)
    except ParserError:
        log.error(msg := BACKFILL_UNPARSABLE_DATE_MSG(start_date))
        raise ValueError(msg)
    
    if end_date is not None:
        try:
            # (type checker complains if we use validate_datetime because return could be None.)
            end_date = validate_required_datetime(end_date, "backfill - end_date")
            end_date = end_date.replace(tzinfo=None)
        except ParserError:
            log.error(msg := BACKFILL_UNPARSABLE_DATE_MSG(end_date))
            raise ValueError(msg)
    
    # time is in the future - this is valid _behavior_ so we don't raise an exception
    if start_date > datetime.now():
        log.warning(BACKFILL_START_DATE_FUTURE_MSG(start_date))  # just a warning
        return
    
    # required setup
    make_directories(path_join(output_dir, participant_id))
    
    # this is just a this wrapper to provide documentation for usage of Mano's backfill functionality
    _backfill_participant(
        Keyring,
        study_id,
        participant_id,
        output_dir,
        start_date,
        data_streams,
        compressed,
        lock,
        passphrase,
        backfill_end=end_date,
    )


def save(
    archive: zipfile.ZipFile,
    participant_id: str,
    output_dir: str,
    lock: list[str] | None = None,
    passphrase: str | None = None,
    user_id: str | None = None,
) -> int:
    log.warning(SYNC_SAVE_DEPRECATION_MSG)
    
    if user_id:
        log.warning(USER_ID_KEYWORD_DEPRECATION_MSG)
    
    if user_id and participant_id:
        log.error(PICK_USER_PARTICIPANT_SINGLE_MSG)
        raise ValueError(PICK_USER_PARTICIPANT_SINGLE_MSG)
    
    if user_id and not participant_id:
        participant_id = user_id
    
    return save_archive(archive, participant_id, output_dir, lock, passphrase)


#
# Implementation
#


def _download(
    Keyring: dict[str, str],
    study_id: str,
    compressed: bool,
    data_streams: list[str],
    registry: dict[str, str],
    time_start: datetime | None,
    time_end: datetime | None,
    participant_ids: list[str],
) -> zipfile.ZipFile:
    """
    Internal function to handle download logic, do not call directly.
    """
    # base url for beiwe instance
    url = normalize_url(Keyring['URL']) + (URL_COMPRESSED if compressed else URL_UNCOMPRESSED)
    log.debug(f'download URL: {url}')
    
    # setup request payload
    payload: RequestPayload = {
        "access_key": Keyring["ACCESS_KEY"],
        "secret_key": Keyring["SECRET_KEY"],
        "study_id": study_id,  # required
    }
    if data_streams:
        payload["data_streams"] = data_streams
    if participant_ids:
        # changed to participant_ids in newer backends, user_ids is backwards compatible but misnamed
        payload["user_ids"] = participant_ids
    if time_start:
        payload["time_start"] = time_start.strftime(API_TIME_FORMAT)
    if time_end:
        payload["time_end"] = time_end.strftime(API_TIME_FORMAT)
    if registry:
        payload["registry"] = orjson.dumps(registry).decode()
    
    # don't log sensitive information, registry may be huuge
    dummy_payload = {k: v for k, v in payload.items() if k not in ("access_key", "secret_key", "registry")}
    if registry:
        dummy_payload["registry"] = "<omitted>"
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
    
    log.info('Server responded, downloading zip data... ')
    MB, t_start, t_end = iterate_with_spinner(resp, content, show_progress)
    
    MBps = MB / (t_end - t_start)
    if f"{t_end - t_start:.2f}" == "0.00":
        log.info(f'Download took {t_end - t_start:.2f} seconds, no data was downloaded.')
    else:
        log.info(f'Download took {t_end - t_start:.2f} seconds (average of {MBps:.2f} MB/s) for {MB:.2f} MB.')
    
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


def _backfill_participant(
    Keyring: dict[str, str],
    study_id: str,
    participant_id: str,
    output_dir: str,
    backfill_start: datetime,
    data_streams: list[str],
    compressed: bool,
    lock: list[str],
    passphrase: str | None = None,
    backfill_end: datetime | None = None,
) -> None:
    """
    Business logic for backfilling a participant's data.
    Do not call this function directly, use `backfill(...)`
    """
    
    assert backfill_start.tzinfo is None, "start_time must be timezone-naive"
    
    participant_path = path_join(output_dir, participant_id)
    if file_exists(backfill_file := path_join(participant_path, '.backfill')):
        log.warning("found old backfill tracking file, deleteing it.")
        delete_file(backfill_file)
    
    log.info(f'Starting backfill, initial timestamp: {backfill_start}')
    next_timestamp = backfill_start
    
    backfill_end = backfill_end or \
        datetime.today().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    
    particpant_registry, local_hash_lookup = generate_registry_info(
        participant_path, study_id, participant_id
    )
    
    while True:
        # get [next] download window and resume point, and download
        start, end = _get_next_backfill_window_strings(next_timestamp)
        log.info(f'Checking for backfill window {start} - {end}...')
        
        archive = download(
            Keyring,
            study_id=study_id,
            participant_ids=[participant_id],
            data_streams=data_streams,
            time_start=start,
            time_end=end,
            compressed=True,
            registry=particpant_registry
        )
        
        # save data
        log.info('Download complete, checking data...')
        num_saved = save_archive(
            archive,
            participant_id,
            output_dir,
            lock,
            passphrase,
            decompress_zst=not compressed,  # compressed is true when we do not want decompression
            hash_lookup=local_hash_lookup,
        )
        log_func = log.warning if num_saved == 0 else log.info
        log_func(f'download complete, created or updated {num_saved} files.')
        
        # stop condition
        if end > backfill_end:
            log.info(f'Backfill operations are complete for participant `{participant_id}`')
            return
        
        # proceed to next windo
        log.debug(f'next backfill for participant `{participant_id}` will resume from `{end}`')
        log.info("")
        next_timestamp = end  # advance the window


#
# Helper functions
#


def _get_next_backfill_window_strings(timestamp: datetime) -> tuple[datetime, datetime]:
    """
    Given a timestamp return a time "window" (the start and end), and a boolean indicating whether
    """
    # strip down to the start of the day
    window_start = datetime(timestamp.year, timestamp.month, timestamp.day)
    window_stop = window_start + timedelta(days=BACKFILL_WINDOW)
    log.debug(f'calculated next backfill window from timestamp `{window_start}` as {window_stop}')
    return window_start, window_stop


def iterate_with_spinner(
    resp: Response, bytesio: BytesIO, show_progress: bool
) -> tuple[float, float, float]:
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
    return size / 1024 / 1024, t_start, t_end


#
# Validation
#

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


def validate_datetime(dt: str | datetime | date | None, msg_prefix: str) -> datetime | None:
    """ Process one time input parameter - a returned value of None indicates no time filter. """
    
    # empty string and None
    if dt is None or not dt:
        log.debug(NO_TIME_MSG(msg_prefix))
        return None
    
    if type(dt) is date:  # date subclasses datetime, this syntax to test the type is correct.
        dt = datetime(dt.year, dt.month, dt.day)
    
    # string input
    if isinstance(dt, str):
        time_str = dt
        try:
            dt = dateutil_parse(dt)
        except ParserError:
            log.error(msg := COULD_NOT_PARSE_TIME_MSG(msg_prefix, dt))
            raise UnParsableTimeError(msg)  # do not add "from e", the stack trace is not useful here
        log.debug(TIME_PARSED_MSG(msg_prefix, time_str, dt))
    
    assert type(dt) is datetime  # type checkers don't understand the date -> datetime conversion
    
    # naive datetime
    if dt.tzinfo is None:
        log.debug(TIME_NAIVE_MSG(msg_prefix))
        dt = dt.replace(tzinfo=UTC)
    
    # non-UTC timezone
    if dt.tzinfo != UTC:
        new_dt = dt.astimezone(UTC)
        log.warning(TIME_NOT_UTC_MSG(msg_prefix, dt, f"has been time-shifted to `{full_dt_format(new_dt)}`."))
        dt = new_dt
    
    return dt


def validate_required_datetime(dt: str | datetime | date | None, msg_prefix: str) -> datetime:
    """
    As handle_one_datetime_input, but raises ValueError on None/empty, and guarantees datetime return.
    """
    dt = validate_datetime(dt, msg_prefix)
    if dt is None or not dt:
        log.error(msg := TIME_REQUIRED_MSG(msg_prefix))
        raise ValueError(msg)
    return dt


def validate_data_streams(data_streams: list[str] | None, prefix_msg: str) -> None:
    """ Validate data streams against known Beiwe data streams. """
    if not data_streams:
        log.debug('(No data streams specified.)')
        return
    
    invalid_streams = []
    for ds in data_streams:
        if ds not in ALL_DATA_STREAMS:
            invalid_streams.append(ds)
    invalid_streams.sort()
    
    # raise error if any invalid streams found
    if invalid_streams:
        log.error(msg := INVALID_DATA_STREAMS_MSG(invalid_streams, prefix_msg))
        raise ValueError(msg)


def check_can_parse_to_datetime(dt_str: str) -> bool:
    try:
        dateutil_parse(dt_str)
        return True
    except ParserError:
        return False
