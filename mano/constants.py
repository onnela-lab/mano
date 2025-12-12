import json
import locale
import logging
import os
from datetime import datetime

import coloredlogs
import pyzstd
from dateutil.tz import UTC


# URL endpoints
URL_UNCOMPRESSED = '/get-data/v1'
URL_COMPRESSED = '/get-data/v2'

# read configuration file
# TODO: document the config file / configuration options (at all).
Config = os.path.join(os.path.dirname(__file__), 'config.json')
with open(Config, 'rb') as fo:
    Config = json.load(fo)


# TODO: source this locale from the system
LOCALE = str(Config['locale'])
locale.setlocale(locale.LC_ALL, LOCALE)

DATA_STREAMS = Config['data_streams']  # Warning, historical variable name, cannot/do not change
ALL_DATA_STREAMS = {
    "accelerometer",
    "audio_recordings",
    "app_log",
    "bluetooth",
    "calls",
    "devicemotion",
    "gps",
    "gyro",
    "identifiers",
    "ios_log",
    "magnetometer",
    "power_state",
    "proximity",
    "reachability",
    "survey_answers",
    "survey_timings",
    "texts",
    "wifi",
}

#
# Anything Related to Time
#

BASE_24HR_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"  # isoformat but with space instead of T
FULL_DT_FORMAT = "%Y-%m-%d %H:%M:%S (%Z)"  # with timezone _name_
FULL_DT_FORMAT_NO_TZ = "%Y-%m-%d %H:%M:%S"

TIME_FORMAT = Config['time_format']  # This will probably get removed because we always want isoformat
API_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"  # isoformat without timezone, YYYY-MM-DDThh:mm:ss

# this is the earliest possible date for data out of any Beiwe study
EARLIEST_POSSIBLE_DATA_STR = '2015-9-01T00:00:00'
EARLIEST_POSSIBLE_DATA_DT = datetime(2015, 9, 1, tzinfo=UTC)

BACKFILL_WINDOW = 5
BACKFILL_INTERVAL_SLEEP = 3

# pyzstd custom parameters
# Note - Beiwe does not produce files large enough to benefit from multiple threads (at this level)
BACKEND_PYZSTD_PARAMS = {
    pyzstd.CParameter.compressionLevel: 2,
    pyzstd.CParameter.nbWorkers: -1,
    pyzstd.CParameter.strategy: pyzstd.Strategy.dfast,
}

#
# Valid Beiwe data file extensions
#
# We provide a tool that de/compresses/deletes files, JSON and MP4 files are likely to exist on
# users' devices, so we need to at the very least default to skipping them.
#TODO: add more protections and "intelligence" to determine if a file is a beiwe data file.
BEIWE_FILE_EXTENSIONS = [
    '.csv',
    '.wav',
    # '.json',  # The platform provides some json data, but it is too dangerous to include.
    # '.mp4',   # Mp4 files are already compressed... that's their gorram purpose.
]
# Yeah we COULD just type out these two-item lists, but instead we will dynamically generate them.
BEIWE_EXTENSIONS_ANDED = f'{", ".join(BEIWE_FILE_EXTENSIONS[:-1])}, and {BEIWE_FILE_EXTENSIONS[-1]}'
BEIWE_EXTENSIONS_ORED = f'{", ".join(BEIWE_FILE_EXTENSIONS[:-1])}, or {BEIWE_FILE_EXTENSIONS[-1]}'
BEIWE_EXTENSIONS_MESSAGE = f"No files ending in {BEIWE_EXTENSIONS_ORED} found in directory"


#
# Exception Types - ensure all exception types have the work error in them for easy identification
#
# General Errors
class InternalError(Exception): pass  # noqa

# originally in mano/sync.py
class APIError(Exception): pass  # noqa
class DownloadError(Exception): pass  # noqa
class ParseError(Exception): pass  # noqa
class SaveError(Exception): pass  # noqa
class WriteError(Exception): pass  # noqa

# originally in mano/mano.py
class AmbiguousStudyIDError(Exception): pass  # noqa
class IntervalError(Exception): pass  # noqa
class KeyringError(Exception): pass  # noqa
class LoginError(Exception): pass  # noqa
class ScrapeError(Exception): pass  # noqa
class StudyIDError(Exception): pass  # noqa
class StudyNameError(Exception): pass  # noqa
class StudySettingsError(Exception): pass  # noqa

# new!
class UnParsableTimeError(ValueError): pass  # noqa


# configure colored logging - currently this is our best spot for this
coloredlogs.install(
    fmt="%(asctime)s %(name)s: %(message)s",
    programname="mano",
    level=logging.INFO,  # our default is going to be info (blue label, regular text color message)
    datefmt="%H:%M:%S",  # cutting out the date for brevity
)

# The logger
log = logger = logging.getLogger("mano")
