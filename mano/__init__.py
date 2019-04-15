import os
import io
import re
import sys
import json
import time
import locale
import logging
import zipfile
import requests
import getpass as gp
import datetime as dt
import tempfile as tf
import lxml.html as html
import cryptease as crypt
import pkg_resources as res

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

def interval(x):
    '''
    Convert an interval e.g., 1d, 12h, into seconds

    :param x: Interval string
    :type x: str
    :returns: Interval in seconds
    :rtype: int
    '''
    result = re.split("^([0-9]+)([smhd]$)", x)
    if len(result) != 4:
        raise IntervalError("invalid interval '%s'" % x)
    value,units = result[1],result[2]
    try:
        value = int(value)
    except ValueError as e:
        raise IntervalError("invalid interval '%s': %s" % (x, e))
    now = dt.datetime.now()
    if units == "d":
        offset = dt.timedelta(days=value)
    elif units == "h":
        offset = dt.timedelta(hours=value)
    elif units == "m":
        offset = dt.timedelta(minutes=value)
    elif units == "s":
        offset = dt.timedelta(seconds=value)

    return ((now + offset) - now).total_seconds()

class IntervalError(Exception):
    pass

def studies(Keyring):
    '''
    Request a list of studies

    :param Keyring: Keyring dictionary
    :type Keyring: dict
    :returns: Generator of (study_name, study_id)
    :rtype: generator
    '''
    url = Keyring['URL'].rstrip('/') + '/get-studies/v1'
    payload = {
        'access_key': Keyring['ACCESS_KEY'],
        'secret_key': Keyring['SECRET_KEY']
    }
    resp = requests.post(url, data=payload, stream=True)
    if resp.status_code != requests.codes.OK:
        raise APIError('response not ok ({0}) {1}'.format(resp.status_code, resp.url))
    response = json.loads(resp.content)
    for study_id,study_name in iter(response.items()):
        yield study_name,study_id

class APIError(Exception):
    pass

def keyring(deployment, keyring_file='~/.nrg-keyring.enc', passphrase=None):
    '''
    Get keyring for deployment

    :param deployment: Deployment name
    :type deployment: str
    :param keyring_file: Keyring file
    :type keyring_file: str
    :param passphrase: Passphrase to decrypt keyring
    :type passphrase: str
    :returns: Deployment keyring
    :rtype: dict
    '''
    if deployment == None:
        return keyring_from_env()
    if passphrase == None:
        if 'NRG_KEYRING_PASS' in os.environ:
            passphrase = os.environ['NRG_KEYRING_PASS']
        else:
            passphrase = gp.getpass('enter keyring passphrase: ')
    keyring_file = os.path.expanduser(keyring_file)
    with open(keyring_file, 'rb') as fo:
        key = crypt.key_from_file(fo, passphrase)
        content = b''
        for chunk in crypt.decrypt(fo, key):
            content += chunk
    try:
        js = json.loads(content)
    except ValueError as e:
        raise KeyringError('could not decrypt file {0} (wrong passphrase perhaps?)'.format(keyring_file))
    return js[deployment]

def keyring_from_env():
    '''
    Construct keyring from environment variables

    :returns: Keyring
    :rtype: dict
    '''
    Keyring = dict()
    try:
        Keyring['URL'] = os.environ['BEIWE_URL']
        Keyring['USERNAME'] = os.environ['BEIWE_USERNAME']
        Keyring['PASSWORD'] = os.environ['BEIWE_PASSWORD']
        Keyring['ACCESS_KEY'] = os.environ['BEIWE_ACCESS_KEY']
        Keyring['SECRET_KEY'] = os.environ['BEIWE_SECRET_KEY']
    except KeyError as e:
        raise KeyringError('environment variable not found: {0}'.format(e))
    return Keyring

class KeyringError(Exception):
    pass

def expand_study_id(Keyring, segment):
    '''
    Expand a Study ID segment to the full Study ID

    :param Keyring: Keyring dictionary
    :type Keyring: dict
    :param segment: First characters from a Study ID
    :type segment: str
    :returns: Complete Study name and ID
    :rtype: tuple
    '''
    ids = list()
    for study_name,study_id in studies(Keyring):
        if study_id.startswith(segment):
            ids.append((study_name, study_id))
    if not ids:
        logger.warn('no study was found for study id segment {0}'.format(segment))
        return None
    elif len(ids) == 1:
        return ids[0]
    elif len(ids) > 1:
        raise AmbiguousStudyIDError('study id is not unique enough {0}'.format(segment))

class AmbiguousStudyIDError(Exception):
    pass

def login(Keyring):
    '''
    Programmatic login to the Beiwe website (returns cookies)

    :param Keyring: Keyring namespace
    :returns: Cookies
    :rtype: dict
    '''
    url = Keyring['URL'].rstrip('/') + '/validate_login'
    payload = {
        'username': Keyring['USERNAME'],
        'password': Keyring['PASSWORD']
    }
    resp = requests.post(url, data=payload)
    if resp.status_code != requests.codes.OK:
        raise LoginError('response not ok ({0}) for {1}'.format(resp.status_code, resp.url))
    # there is a redirect after login
    return resp.history[0].cookies

class LoginError(Exception):
    pass

def device_settings(Keyring, study_id):
    '''
    Get device settings for a Study

    :param Keyring: Keyring namespace
    :param study_id: Study ID
    :returns: Generator of sensor (name, setting)
    :rtype: generator
    '''
    # get login cookies
    cookies = login(Keyring)
    # request choose_study html page
    url = Keyring['URL'].rstrip('/') + '/device_settings/{0}'.format(study_id)
    resp = requests.get(url, cookies=cookies)
    if resp.status_code != requests.codes.OK:
        raise StudySettingsError('response not ok ({0}) for url={1}'.format(resp.status_code, resp.url))
    # parse html page
    tree = html.fromstring(resp.content)
    # run xpath expression to get study list
    expr = "//div[@class='form-group']/div/input[@class='form-control']"
    elements = tree.xpath(expr)
    if not elements:
        raise ScrapeError('zero anchor elements returned from expression: {0}'.format(expr))
    # yield each setting name and value
    for e in elements:
        if "name" not in e.attrib:
            raise ScrapeError('input element is missing "name" attribute')
        if "value" not in e.attrib:
            raise ScrapeError('input element is missing "value" attribute')
        yield e.name,e.value

class StudySettingsError(Exception):
    pass

class ScrapeError(Exception):
    pass

def users(Keyring, study_id):
    '''
    Request a list of users within a study

    :param Keyring: Keyring dictionary
    :type Keyring: dict
    :param study_id: Study ID
    :type study_id: str
    :returns: Generator of (study_name, study_id)
    :rtype: generator
    '''
    url = Keyring['URL'].rstrip('/') + '/get-users/v1'
    payload = {
        'access_key': Keyring['ACCESS_KEY'],
        'secret_key': Keyring['SECRET_KEY'],
        'study_id': study_id
    }
    resp = requests.post(url, data=payload, stream=True)
    if resp.status_code != requests.codes.OK:
        raise APIError('response not ok ({0}) {1}'.format(resp.status_code, resp.url))
    response = json.loads(resp.content)
    for uid in response:
        yield uid

def studyid(Keyring, name):
    '''
    Get the Study ID for a given Study Name
    
    :param Keyring: Keyring dictionary
    :type Keyring: dict
    :param name: Study name
    :type name: str
    :returns: Study ID
    :rtype: str
    '''
    for study_name,study_id in studies(Keyring):
        if name == study_name:
            return study_id
    raise StudyIDError('study not found {0}'.format(name))

class StudyIDError(Exception):
    pass

def studyname(Keyring, sid):
    '''
    Get the Study Name for a given Study ID
    
    :param Keyring: Keyring dictionary
    :type Keyring: dict
    :param sid: Study ID
    :type sid: str
    :returns: Study Name
    :rtype: str
    '''
    for study_name,study_id in studies(Keyring):
        if sid == study_id:
            return study_name
    raise StudyNameError('study not found {0}'.format(sid))

class StudyNameError(Exception):
    pass

