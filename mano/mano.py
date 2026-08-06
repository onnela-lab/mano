import getpass
import json
import os
import re
from datetime import timedelta

import cryptease as crypt
import requests

from mano.beiwe_api import fetch_accessible_studies, fetch_study_settings_test, fetch_users_in_study
from mano.beiwe_api import fetch_interventions  # noqa: F401  (unused here, re-exported for backward compatibility)
from mano.beiwe_api import fetch_participant_table_data  # noqa: F401
from mano.beiwe_api import fetch_participant_table_data_csv  # noqa: F401
from mano.beiwe_api import fetch_study_settings  # noqa: F401
from mano.beiwe_api import fetch_summary_statistics  # noqa: F401
from mano.beiwe_api import fetch_survey_history  # noqa: F401
from mano.constants import (ACCESS_KEY, AmbiguousStudyIDError, BEIWE_ACCESS_KEY, BEIWE_PASSWORD,
    BEIWE_SECRET_KEY, BEIWE_URL, BEIWE_USERNAME, Config, DATA_STREAMS, IntervalError, KeyringError,
    LOCALE, logger as log, LoginError, NRG_KEYRING_PASS, PASSWORD, SECRET_KEY, StudyIDError,
    StudyNameError, TIME_FORMAT, URL, USERNAME)
from mano.constants import APIError  # noqa: F401  (unused here, re-exported for backward compatibility)
from mano.constants import ScrapeError  # noqa: F401
from mano.constants import StudySettingsError  # noqa: F401


# TODO: remove username and password from the keyring, display a deprecation warning if they are present
ENV_KEYS = [BEIWE_URL, BEIWE_USERNAME, BEIWE_PASSWORD, BEIWE_ACCESS_KEY, BEIWE_SECRET_KEY]
KEYRING_KEYS = [USERNAME, PASSWORD, URL, ACCESS_KEY, SECRET_KEY]

# fetch_accessible_studies, fetch_interventions, fetch_participant_table_data,
# fetch_participant_table_data_csv, fetch_study_settings, fetch_study_settings_test,
# fetch_summary_statistics, fetch_survey_history, and fetch_users_in_study live in
# mano/beiwe_api.py now; imported above so `from mano.mano import fetch_...` still works.


#
## Keyring
#
def load_keyring(
    deployment: str | None,
    keyring_file: str = "~/.nrg-keyring.enc",
    passphrase: str | None = None
) -> dict[str, str]:
    """
    Get keyring for deployment
    :param deployment: Deployment name
    :param keyring_file: Keyring file location
    :param passphrase: Passphrase to decrypt keyring
    :returns: Deployment keyring
    """
    # if no deployment string was provided, get keyring from environment
    if deployment is None:
        return keyring_from_env()

    # if no passphrase was provided, get it from the environment or prompt
    if passphrase is None:
        if NRG_KEYRING_PASS in os.environ:
            passphrase = os.environ[NRG_KEYRING_PASS]
        else:
            passphrase = getpass.getpass("enter keyring passphrase: ")

    # get keyring file using cryptease
    keyring_file = os.path.expanduser(keyring_file)

    with open(keyring_file, "rb") as fo:
        key = crypt.key_from_file(fo, passphrase)
        content = b""

        # crypt.decrypt cannot be None
        for chunk in crypt.decrypt(fo, key):  # type: ignore
            content += chunk

    # load, return
    try:
        js = json.loads(content)
    except (ValueError, KeyError) as e:
        msg = f"could not decrypt file `{keyring_file}` (wrong passphrase, perhaps?)"
        log.error(msg)
        raise KeyringError(msg) from e
    return js[deployment]


def keyring_from_env() -> dict[str, str]:
    """
    Construct keyring from environment variables
    :returns: Keyring
    """
    keyring = dict[str, str]()
    try:
        keyring[URL] = os.environ[BEIWE_URL]
        keyring[USERNAME] = os.environ[BEIWE_USERNAME]  # TODO: need to finish removing this...
        keyring[PASSWORD] = os.environ[BEIWE_PASSWORD]
        keyring[ACCESS_KEY] = os.environ[BEIWE_ACCESS_KEY]
        keyring["SECRET_KEY"] = os.environ[BEIWE_SECRET_KEY]
    except KeyError:
        missing_keys = [k for k in ENV_KEYS if k not in os.environ]
        for k in missing_keys:
            log.error(f"environment variable `{k}` is not set")
        raise KeyringError(f"environment variable(s) not found: {', '.join(missing_keys)}") from None

    # strings
    empty_keys = [k for k in KEYRING_KEYS if k in keyring and not keyring[k]]
    if empty_keys:
        raise KeyringError(f"the environment variable(s) `{'`, `'.join(empty_keys)}` are present but empty.")

    return keyring


#
## Utility Functions
#
def expand_study_id(keyring: dict[str, str], segment: str) -> tuple[str, str] | None:
    """
    Expand a Study ID segment to the full Study ID

    :param Keyring: Keyring dictionary
    :param segment: First characters from a Study ID
    :returns: Complete Study name and ID
    """
    ids = list[tuple[str, str]]()
    for study_name, study_id in fetch_accessible_studies(keyring):
        if study_id.startswith(segment):
            ids.append((study_name, study_id))

    if not ids:
        log.warning(f"no study was found for study id segment {segment}")
        return None
    elif len(ids) == 1:
        return ids[0]
    else:
        raise AmbiguousStudyIDError(f"study id is not unique enough {segment}")


def studyid(keyring: dict[str, str], name: str) -> str:
    """
    Get the Study ID for a given Study Name

    :param Keyring: Keyring dictionary
    :param name: Study name
    :returns: Study ID
    """
    for study_name, study_id in fetch_accessible_studies(keyring):
        if name == study_name:
            return study_id
    raise StudyIDError(f"study not found {name}")


def studyname(keyring: dict[str, str], sid: str) -> str:
    """
    Get the Study Name for a given Study ID

    :param Keyring: Keyring dictionary
    :param sid: Study ID
    :returns: Study Name
    """
    for study_name, study_id in fetch_accessible_studies(keyring):
        if sid == study_id:
            return study_name
    raise StudyNameError(f"study not found {sid}")


def interval(x: str) -> int:
    """
    Convert an interval e.g., 1d, 12h, into seconds
    """
    x = x.lower()

    # validate and extract - any number of digits followed by single character s m h d
    result = re.split("^([0-9]+)([smhd]$)", x)
    if len(result) != 4:
        raise IntervalError(f"invalid interval '{x}'")

    value, units = result[1], result[2]
    try:
        value = int(value)
    except ValueError as e:
        raise IntervalError(f"invalid interval '{x}': {e}") from None

    # convert to seconds using datetime
    if units == "d":
        offset = timedelta(days=value)
    elif units == "h":
        offset = timedelta(hours=value)
    elif units == "m":
        offset = timedelta(minutes=value)
    elif units == "s":
        offset = timedelta(seconds=value)
    else:
        raise IntervalError(f"invalid interval unit '{units}'")

    return int(offset.total_seconds())


#
## Old to-be-rewritten functionality, replace with API calls
#
# FIXME: this function is the login to the beiwe website, a detail we want to drop entirely
def login(keyring: dict[str, str]) -> requests.cookies.RequestsCookieJar:
    """
    Programmatic login to the Beiwe website (returns cookies)

    :param Keyring: Keyring namespace
    :returns: Cookies
    """
    # setup
    url = keyring["URL"].rstrip("/") + "/validate_login"
    payload = {"username": keyring["USERNAME"], "password": keyring["PASSWORD"]}
    # request
    resp = requests.post(url, data=payload)
    if resp.status_code != requests.codes.OK:
        raise LoginError(f"response not ok ({resp.status_code}) for {resp.url}")
    # there is a redirect after login
    return resp.history[0].cookies


#
##  Old function aliases and variables we need to keep in the namespace for backward compatibility
#
studies = fetch_accessible_studies             # noqa
users = fetch_users_in_study                   # noqa
keyring = load_keyring                         # noqa
Keyring = load_keyring                         # noqa
device_settings = fetch_study_settings_test    # noqa
Config = Config                                # noqa
DATA_STREAMS = DATA_STREAMS                    # noqa
LOCALE = LOCALE                                # noqa
TIME_FORMAT = TIME_FORMAT                      # noqa
