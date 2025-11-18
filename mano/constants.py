import logging
import itertools
import json
import locale
import os
from datetime import datetime

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

# The logger
logger = logging.getLogger("mano")


# Exception Types - ensure all exception types have the work error in them for easy identification

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
