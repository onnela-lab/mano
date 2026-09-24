import json
import locale
import logging
import os
from datetime import datetime

import coloredlogs
import pyzstd
import requests
from dateutil.tz import UTC


# Global settings object
# the main() function sets these values appropriately during CLI usage.
class GlobalSettings:
    skip_user_interaction: bool = True   # main() in CLI sets this to False when appropriate.
    multithreading_count: int = 0        # zero or negative means use the number of CPU cores.

    backfill_window = 20
    download_retry_attempts = 3
    # Requests reads this as (connect timeout, read inactivity timeout), in seconds.
    download_timeout = (10, 60)


NON_RETRYABLE_DOWNLOAD_EXCEPTIONS = (
    requests.exceptions.ProxyError,
    requests.exceptions.SSLError,
)
RETRYABLE_DOWNLOAD_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
    requests.exceptions.ContentDecodingError,
)


#
# The Beiwe Data Streams
#

class DataStreams:
    ACCELEROMETER = "accelerometer"
    AUDIO_RECORDING = "audio_recordings"
    ANDROID_LOG_FILE = "app_log"
    BLUETOOTH = "bluetooth"
    CALL_LOG = "calls"
    DEVICEMOTION = "devicemotion"
    GPS = "gps"
    GYRO = "gyro"
    IDENTIFIERS = "identifiers"
    IOS_LOG_FILE = "ios_log"
    MAGNETOMETER = "magnetometer"
    POWER_STATE = "power_state"
    PROXIMITY = "proximity"
    REACHABILITY = "reachability"
    SURVEY_ANSWERS = "survey_answers"
    SURVEY_TIMINGS = "survey_timings"
    TEXTS_LOG = "texts"
    WIFI = "wifi"


ALL_DATA_STREAMS = [
    DataStreams.ACCELEROMETER,
    DataStreams.AUDIO_RECORDING,
    DataStreams.ANDROID_LOG_FILE,
    DataStreams.BLUETOOTH,
    DataStreams.CALL_LOG,
    DataStreams.DEVICEMOTION,
    DataStreams.GPS,
    DataStreams.GYRO,
    DataStreams.IDENTIFIERS,
    DataStreams.IOS_LOG_FILE,
    DataStreams.MAGNETOMETER,
    DataStreams.POWER_STATE,
    DataStreams.PROXIMITY,
    DataStreams.REACHABILITY,
    DataStreams.SURVEY_ANSWERS,
    DataStreams.SURVEY_TIMINGS,
    DataStreams.TEXTS_LOG,
    DataStreams.WIFI,
]


class QuantityStats:
    # Informational Fields
    date = "date"
    participant_id = "participant_id"
    study_id = "study_id"
    timezone = "timezone"
    
    # Data Quantity Fields
    accelerometer_bytes = "accelerometer_bytes"
    app_log_bytes = "app_log_bytes"
    bluetooth_bytes = "bluetooth_bytes"
    calls_bytes = "calls_bytes"
    devicemotion_bytes = "devicemotion_bytes"
    gps_bytes = "gps_bytes"
    gyro_bytes = "gyro_bytes"
    identifiers_bytes = "identifiers_bytes"
    ios_log_bytes = "ios_log_bytes"
    magnetometer_bytes = "magnetometer_bytes"
    power_state_bytes = "power_state_bytes"
    proximity_bytes = "proximity_bytes"
    reachability_bytes = "reachability_bytes"
    survey_answers_bytes = "survey_answers_bytes"
    survey_timings_bytes = "survey_timings_bytes"
    texts_bytes = "texts_bytes"
    audio_recordings_bytes = "audio_recordings_bytes"
    wifi_bytes = "wifi_bytes"


class ForestStats:
    # Forest Output Fields
    jasmine_distance_diameter = "jasmine_distance_diameter"
    jasmine_distance_from_home = "jasmine_distance_from_home"
    jasmine_distance_traveled = "jasmine_distance_traveled"
    jasmine_flight_distance_average = "jasmine_flight_distance_average"
    jasmine_flight_distance_stddev = "jasmine_flight_distance_stddev"
    jasmine_flight_duration_average = "jasmine_flight_duration_average"
    jasmine_flight_duration_stddev = "jasmine_flight_duration_stddev"
    jasmine_home_duration = "jasmine_home_duration"
    jasmine_gyration_radius = "jasmine_gyration_radius"
    jasmine_significant_location_count = "jasmine_significant_location_count"
    jasmine_significant_location_entropy = "jasmine_significant_location_entropy"
    jasmine_pause_time = "jasmine_pause_time"
    jasmine_obs_duration = "jasmine_obs_duration"
    jasmine_obs_day = "jasmine_obs_day"
    jasmine_obs_night = "jasmine_obs_night"
    jasmine_total_flight_time = "jasmine_total_flight_time"
    jasmine_av_pause_duration = "jasmine_av_pause_duration"
    jasmine_sd_pause_duration = "jasmine_sd_pause_duration"
    jasmine_physical_circadian_rhythm = "jasmine_physical_circadian_rhythm"
    jasmine_physical_circadian_rhythm_stratified = "jasmine_physical_circadian_rhythm_stratified"
    willow_incoming_text_count = "willow_incoming_text_count"
    willow_incoming_text_degree = "willow_incoming_text_degree"
    willow_incoming_text_length = "willow_incoming_text_length"
    willow_outgoing_text_count = "willow_outgoing_text_count"
    willow_outgoing_text_degree = "willow_outgoing_text_degree"
    willow_outgoing_text_length = "willow_outgoing_text_length"
    willow_incoming_text_reciprocity = "willow_incoming_text_reciprocity"
    willow_outgoing_text_reciprocity = "willow_outgoing_text_reciprocity"
    willow_outgoing_MMS_count = "willow_outgoing_MMS_count"
    willow_incoming_MMS_count = "willow_incoming_MMS_count"
    willow_mean_responsiveness_text = "willow_mean_responsiveness_text"
    willow_incoming_call_count = "willow_incoming_call_count"
    willow_incoming_call_degree = "willow_incoming_call_degree"
    willow_incoming_call_duration = "willow_incoming_call_duration"
    willow_outgoing_call_count = "willow_outgoing_call_count"
    willow_outgoing_call_degree = "willow_outgoing_call_degree"
    willow_outgoing_call_duration = "willow_outgoing_call_duration"
    willow_missed_call_count = "willow_missed_call_count"
    willow_missed_callers = "willow_missed_callers"
    willow_mean_responsiveness_call = "willow_mean_responsiveness_call"
    willow_call_reciprocity = "willow_call_reciprocity"
    willow_uniq_individual_call_or_text_count = "willow_uniq_individual_call_or_text_count"
    oak_walking_time = "oak_walking_time"
    oak_steps = "oak_steps"
    oak_cadence = "oak_cadence"


# URL endpoint extensions for the Beiwe data access API
URL_UNCOMPRESSED = '/get-data/v1'
URL_COMPRESSED = '/get-data/v2'

#
# Anything Related to Time
#

BASE_24HR_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"  # isoformat but with space instead of T
FULL_DT_FORMAT = "%Y-%m-%d %H:%M:%S (%Z)"  # with timezone _name_
FULL_DT_FORMAT_NO_TZ = "%Y-%m-%d %H:%M:%S"
API_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"  # isoformat without timezone, YYYY-MM-DDThh:mm:ss

# this is the earliest possible date for data out of any Beiwe study
EARLIEST_POSSIBLE_DATA_STR = '2015-9-01T00:00:00'
EARLIEST_POSSIBLE_DATA_DT = datetime(2015, 9, 1, tzinfo=UTC)

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
#TODO: how could we handle locked files? they would need to be decrypted-compress-encrypted
BEIWE_FILE_EXTENSIONS = [
    '.csv',  # micro-optimization to have this at thetop
    '.wav',
    '.json',  # The platform provides some json data, but it is too dangerous to include.
    '.mp4',   # Mp4 files are already compressed... that's their gorram purpose.
]
COMPRESSABLE_FILE_EXTENSIONS = ['.csv', '.wav']

# Yeah we COULD just type out these two-item lists, but instead we will dynamically generate them.
BEIWE_EXTENSIONS_ANDED = f'{", ".join(BEIWE_FILE_EXTENSIONS[:-1])}, and {BEIWE_FILE_EXTENSIONS[-1]}'
BEIWE_EXTENSIONS_ORED = f'{", ".join(BEIWE_FILE_EXTENSIONS[:-1])}, or {BEIWE_FILE_EXTENSIONS[-1]}'


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
class EncryptionKeyUnavailable(Exception): pass

_color_settings = coloredlogs.parse_encoded_styles(
    "debug=green;info=blue,bright;warning=yellow;success=green,bold;error=red;critical=background=red"
)

# configure colored logging - currently this is our best spot for this
coloredlogs.install(
    fmt="%(asctime)s %(name)s: %(message)s",
    programname="mano",
    level=logging.INFO,  # our default is going to be info (blue label, regular text color message)
    datefmt="%H:%M:%S",  # cutting out the date for brevity
    level_styles=_color_settings
)

# The logger
log = logger = logging.getLogger("mano")


# old configuration code

# TODO: document the config file / configuration options (at all).

# TODO: I don't think this is very useful.
# Read in the universal configuration file
Config = os.path.join(os.path.dirname(__file__), 'config.json')  # historical variable name
with open(Config, 'rb') as fo:
    Config = json.load(fo)

# TODO: source this locale from the system?
LOCALE = str(Config['locale'])  # historical variable name, cannot/do not change
locale.setlocale(locale.LC_ALL, LOCALE)

DATA_STREAMS = Config['data_streams']  # historical variable name, cannot/do not change
TIME_FORMAT = Config['time_format']  # This will probably get removed because we always want isoformat


## Keyring constants
BEIWE_URL = "BEIWE_URL"
BEIWE_USERNAME = "BEIWE_USERNAME"
BEIWE_PASSWORD = "BEIWE_PASSWORD"
BEIWE_ACCESS_KEY = "BEIWE_ACCESS_KEY"
BEIWE_SECRET_KEY = "BEIWE_SECRET_KEY"

USERNAME = "USERNAME"  # REMOVE
PASSWORD = "PASSWORD"  # REMOVE
URL = "URL"
ACCESS_KEY = "ACCESS_KEY"
SECRET_KEY = "SECRET_KEY"


NRG_KEYRING_PASS = "NRG_KEYRING_PASS"
