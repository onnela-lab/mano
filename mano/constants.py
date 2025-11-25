import itertools
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
Config = os.path.join(os.path.dirname(__file__), 'config.json')
with open(Config, 'rb') as fo:
    Config = json.load(fo)

DATA_STREAMS = Config['data_streams']
TIME_FORMAT = Config['time_format']
LOCALE = str(Config['locale'])

locale.setlocale(locale.LC_ALL, LOCALE)

spinner = itertools.cycle(['-', '/', '|', '\\'])

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
# valid Beiwe data file extensions
#
_VBDTE = VALID_BEIWE_FILE_EXTENSIONS = [
    '.csv',
    # '.json',  # this is too broad
    '.wav',
    # '.mp4',  # these should not be double compressed
]

VALID_EXTENSIONS_ANDED = ", ".join(_VBDTE[:-1]) + f", and {_VBDTE[-1]}"
VALID_EXTENSIONS_ORED = ", ".join(_VBDTE[:-1]) + f", or {_VBDTE[-1]}"
VALID_EXTENSIONS_MESSAGE = f"No files ending in {VALID_EXTENSIONS_ORED} found in directory"


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



# configure colored logging
# coloredlogs.install(fmt="%(levelname)s %(name)s: %(message)s")
coloredlogs.install(fmt="%(message)s")
coloredlogs.auto_install()
# The logger
logger = logging.getLogger("mano")
