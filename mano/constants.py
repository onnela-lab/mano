import itertools
import json
import locale
import os


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
EARLIEST_POSSIBLE_DATA_DATE = '2015-9-01T00:00:00'

BACKFILL_WINDOW = 5
BACKFILL_INTERVAL_SLEEP = 3
BACKFILL_LOCK_EXT = '.lock'
