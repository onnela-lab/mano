from collections.abc import Generator
from datetime import datetime, timedelta
import getpass
import json
import locale
import logging
import os
import re

import cryptease as crypt
import lxml.html as html
import requests


logger = logging.getLogger(__name__)

DIR = os.path.dirname(__file__)

# read configuration file
Config = os.path.join(DIR, 'config.json')
with open(Config, 'rb') as fo:
    Config = json.load(fo)

DATA_STREAMS = Config['data_streams']
TIME_FORMAT = Config['time_format']
LOCALE = str(Config['locale'])

locale.setlocale(locale.LC_ALL, LOCALE)


class AmbiguousStudyIDError(Exception):
    pass


class APIError(Exception):
    pass


class KeyringError(Exception):
    pass


class IntervalError(Exception):
    pass


class LoginError(Exception):
    pass


class ScrapeError(Exception):
    pass


class StudyIDError(Exception):
    pass


class StudyNameError(Exception):
    pass


class StudySettingsError(Exception):
    pass


def interval(x: str) -> int:
    """
    Convert an interval e.g., 1d, 12h, into seconds
    """
    # validate and extract
    result = re.split("^([0-9]+)([smhd]$)", x)
    if len(result) != 4:
        raise IntervalError(f"invalid interval '{x}'")
    value, units = result[1], result[2]
    try:
        value = int(value)
    except ValueError as e:
        raise IntervalError(f"invalid interval '{x}': {e}")

    # convert to seconds using datetime
    now = datetime.now()
    if units == "d":
        offset = timedelta(days=value)
    elif units == "h":
        offset = timedelta(hours=value)
    elif units == "m":
        offset = timedelta(minutes=value)
    elif units == "s":
        offset = timedelta(seconds=value)

    return int(((now + offset) - now).total_seconds())


def studies(Keyring: dict[str, str]) -> Generator[tuple[str, str], None, None]:
    """
    Request a list of studies
    """
    # setup
    url = Keyring['URL'].rstrip('/') + '/get-studies/v1'
    payload = {'access_key': Keyring['ACCESS_KEY'], 'secret_key': Keyring['SECRET_KEY']}

    # request
    resp = requests.post(url, data=payload, stream=True)
    if resp.status_code != requests.codes.OK:
        raise APIError(f'response not ok ({resp.status_code}) {resp.url}')
    response: dict = json.loads(resp.content)

    # yield each study name and id
    for study_id, study_name in iter(response.items()):
        yield study_name, study_id


def keyring(
        deployment: str | None,
        keyring_file: str = '~/.nrg-keyring.enc',
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
        if 'NRG_KEYRING_PASS' in os.environ:
            passphrase = os.environ['NRG_KEYRING_PASS']
        else:
            passphrase = getpass.getpass('enter keyring passphrase: ')

    # get keyring file using cryptease
    keyring_file = os.path.expanduser(keyring_file)
    with open(keyring_file, 'rb') as fo:
        key = crypt.key_from_file(fo, passphrase)
        content = b''
        for chunk in crypt.decrypt(fo, key):
            content += chunk

    # load, return
    try:
        js = json.loads(content)
    except ValueError:
        raise KeyringError(f'could not decrypt file {keyring_file} (wrong passphrase perhaps?)')
    return js[deployment]


def keyring_from_env() -> dict[str, str]:
    """
    Construct keyring from environment variables
    :returns: Keyring
    """
    Keyring = dict()
    try:
        Keyring['URL'] = os.environ['BEIWE_URL']
        Keyring['USERNAME'] = os.environ['BEIWE_USERNAME']
        Keyring['PASSWORD'] = os.environ['BEIWE_PASSWORD']
        Keyring['ACCESS_KEY'] = os.environ['BEIWE_ACCESS_KEY']
        Keyring['SECRET_KEY'] = os.environ['BEIWE_SECRET_KEY']
    except KeyError as e:
        raise KeyringError(f'environment variable not found: {e}')
    return Keyring


def expand_study_id(Keyring: dict[str, str], segment: str) -> tuple[str, str] | None:
    """
    Expand a Study ID segment to the full Study ID

    :param Keyring: Keyring dictionary
    :param segment: First characters from a Study ID
    :returns: Complete Study name and ID
    """
    ids = list()
    for study_name, study_id in studies(Keyring):
        if study_id.startswith(segment):
            ids.append((study_name, study_id))
    if not ids:
        logger.warning(f'no study was found for study id segment {segment}')
        return None
    elif len(ids) == 1:
        return ids[0]
    elif len(ids) > 1:
        raise AmbiguousStudyIDError(f'study id is not unique enough {segment}')


def login(Keyring: dict[str, str]) -> dict:
    """
    Programmatic login to the Beiwe website (returns cookies)

    :param Keyring: Keyring namespace
    :returns: Cookies
    """
    # setup
    url = Keyring['URL'].rstrip('/') + '/validate_login'
    payload = {'username': Keyring['USERNAME'], 'password': Keyring['PASSWORD']}
    # request
    resp = requests.post(url, data=payload)
    if resp.status_code != requests.codes.OK:
        raise LoginError(f'response not ok ({resp.status_code}) for {resp.url}')
    # there is a redirect after login
    return resp.history[0].cookies


# FIXME: this function depends on the HTML structure of the Beiwe website, AND the content of the
# page may not accurately represent the state of data collected by the study. beiwe-backend now has
# an issue for this, #320
def device_settings(Keyring: dict[str, str], study_id: str) -> Generator[tuple[str, str], None, None]:
    """
    Get device settings for a Study

    :param Keyring: Keyring namespace
    :param study_id: Study ID
    :returns: Generator of sensor (name, setting)
    """
    # get login cookies
    cookies = login(Keyring)
    # request choose_study html page
    url = Keyring['URL'].rstrip('/') + f'/device_settings/{study_id}'
    resp = requests.get(url, cookies=cookies)
    if resp.status_code != requests.codes.OK:
        raise StudySettingsError(f'response not ok ({resp.status_code}) for url={resp.url}')
    # parse html page
    tree = html.fromstring(resp.content)
    # run xpath expression to get study list
    expr = "//div[@class='form-group']/div/input[@class='form-control']"
    elements = tree.xpath(expr)
    if not elements:
        raise ScrapeError(f'zero anchor elements returned from expression: {expr}')
    # yield each setting name and value
    for e in elements:
        if "name" not in e.attrib:
            raise ScrapeError('input element is missing "name" attribute')
        if "value" not in e.attrib:
            raise ScrapeError('input element is missing "value" attribute')
        yield e.name, e.value


def users(Keyring: dict[str, str], study_id: str) -> Generator[str, None, None]:
    """
    Request a list of users within a study

    :param Keyring: Keyring dictionary
    :param study_id: Study ID
    :returns: Generator of (study_name, study_id)
    :rtype: generator
    """
    url = Keyring['URL'].rstrip('/') + '/get-users/v1'
    payload = {
        'access_key': Keyring['ACCESS_KEY'],
        'secret_key': Keyring['SECRET_KEY'],
        'study_id': study_id
    }
    resp = requests.post(url, data=payload, stream=True)
    if resp.status_code != requests.codes.OK:
        raise APIError(f'response not ok ({resp.status_code}) {resp.url}')
    yield from json.loads(resp.content)


def studyid(Keyring: dict[str, str], name: str) -> str:
    """
    Get the Study ID for a given Study Name

    :param Keyring: Keyring dictionary
    :param name: Study name
    :returns: Study ID
    """
    for study_name, study_id in studies(Keyring):
        if name == study_name:
            return study_id
    raise StudyIDError(f'study not found {name}')


def studyname(Keyring: dict[str, str], sid: str) -> str:
    """
    Get the Study Name for a given Study ID

    :param Keyring: Keyring dictionary
    :param sid: Study ID
    :returns: Study Name
    """
    for study_name, study_id in studies(Keyring):
        if sid == study_id:
            return study_name
    raise StudyNameError(f'study not found {sid}')
