import os

import pytest
import vcr

import mano
import mano.sync


DIR = os.path.dirname(__file__)
CASSETTES = os.path.join(DIR, 'cassettes')

NRG_KEYRING_PASS = 'foobar'

Keyring = {
    'URL': 'https://studies.beiwe.org',
    'USERNAME': 'foobar',
    'PASSWORD': 'bizbat',
    'ACCESS_KEY': 'ACCESS_KEY',
    'SECRET_KEY': 'SECRET_KEY'
}


def test_keyring():
    _environ = dict(os.environ)
    try:
        os.environ['NRG_KEYRING_PASS'] = NRG_KEYRING_PASS
        f = os.path.join(DIR, 'keyring.enc')
        ans = mano.keyring('beiwe.onnela', keyring_file=f)
        assert ans == Keyring
    finally:
        os.environ.clear()
        os.environ.update(_environ)


def test_keyring_wrong_password():
    _environ = dict(os.environ)
    try:
        os.environ['NRG_KEYRING_PASS'] = '**wrong**'
        f = os.path.join(DIR, 'keyring.enc')
        with pytest.raises(mano.KeyringError):
            _ = mano.keyring('beiwe.onnela', keyring_file=f)
    finally:
        os.environ.clear()
        os.environ.update(_environ)


def test_keyring_missing_file():
    _environ = dict(os.environ)
    try:
        os.environ['NRG_KEYRING_PASS'] = NRG_KEYRING_PASS
        f = os.path.join(DIR, 'no-such-file.enc')
        with pytest.raises(IOError):
            _ = mano.keyring('beiwe.onnela', keyring_file=f)
    finally:
        os.environ.clear()
        os.environ.update(_environ)


def test_keyring_from_env():
    _environ = dict(os.environ)
    try:
        os.environ['BEIWE_URL'] = Keyring['URL']
        os.environ['BEIWE_USERNAME'] = Keyring['USERNAME']
        os.environ['BEIWE_PASSWORD'] = Keyring['PASSWORD']
        os.environ['BEIWE_ACCESS_KEY'] = Keyring['ACCESS_KEY']
        os.environ['BEIWE_SECRET_KEY'] = Keyring['SECRET_KEY']
        ans = mano.keyring(None)
        assert ans == Keyring
    finally:
        os.environ.clear()
        os.environ.update(_environ)


def test_keyring_from_env_missing():
    _environ = dict(os.environ)  
    try:
        os.environ['BEIWE_USERNAME'] = Keyring['USERNAME']
        os.environ['BEIWE_PASSWORD'] = Keyring['PASSWORD']
        os.environ['BEIWE_ACCESS_KEY'] = Keyring['ACCESS_KEY']
        os.environ['BEIWE_SECRET_KEY'] = Keyring['SECRET_KEY']
        with pytest.raises(mano.KeyringError):
            _ = mano.keyring(None)
    finally:
        os.environ.clear()
        os.environ.update(_environ)


def test_studies():
    cassette = os.path.join(CASSETTES, 'studies.v1.yaml')
    filter_params = [
        ('access_key', Keyring['ACCESS_KEY']),
        ('secret_key', Keyring['SECRET_KEY'])
    ]
    studies = set([
        ('Project A', '123lrVdb0g6tf3PeJr5ZtZC8'),
        ('Project B', '123U93wwgS18aLDIwdYXTXsr')
    ])
    ans = set()
    with vcr.use_cassette(cassette, decode_compressed_response=True, 
                          filter_post_data_parameters=filter_params):
        for study in mano.studies(Keyring):
            ans.add(study)
    assert ans == studies


def test_users():
    cassette = os.path.join(CASSETTES, 'users.v1.yaml')
    filter_params = [
        ('access_key', Keyring['ACCESS_KEY']),
        ('secret_key', Keyring['SECRET_KEY']),
        ('study_id', 'STUDY_ID')
    ]
    users = set(["tgsidhm", "lholbc5", "yxzxtwr"])
    ans = set()
    with vcr.use_cassette(cassette, decode_compressed_response=True, 
                          filter_post_data_parameters=filter_params):
        for user in mano.users(Keyring, 'STUDY_ID'):
            ans.add(user)
    assert ans == users


def test_expand_study_id():
    cassette = os.path.join(CASSETTES, 'studies.v1.yaml')
    filter_params = [
        ('access_key', Keyring['ACCESS_KEY']),
        ('secret_key', Keyring['SECRET_KEY']),
        ('study_id', 'STUDY_ID')
    ]
    with vcr.use_cassette(cassette, decode_compressed_response=True, 
                          filter_post_data_parameters=filter_params):
        study = ('Project A', '123lrVdb0g6tf3PeJr5ZtZC8')
        ans = mano.expand_study_id(Keyring, '123lrVdb0g6tf3PeJr5ZtZC8')
        assert ans == study


def test_expand_study_id_conflict():
    cassette = os.path.join(CASSETTES, 'studies.v1.yaml')
    filter_params = [
        ('access_key', Keyring['ACCESS_KEY']),
        ('secret_key', Keyring['SECRET_KEY']),
        ('study_id', 'STUDY_ID')
    ]
    with vcr.use_cassette(cassette, decode_compressed_response=True, 
                          filter_post_data_parameters=filter_params):
        with pytest.raises(mano.AmbiguousStudyIDError):       
            _ = mano.expand_study_id(Keyring, '123')


def test_expand_study_id_nomatch():
    cassette = os.path.join(CASSETTES, 'studies.v1.yaml')
    filter_params = [
        ('access_key', Keyring['ACCESS_KEY']),
        ('secret_key', Keyring['SECRET_KEY']),
        ('study_id', 'STUDY_ID')
    ]
    with vcr.use_cassette(cassette, decode_compressed_response=True, 
                          filter_post_data_parameters=filter_params):
        ans = mano.expand_study_id(Keyring, '321')
        assert ans is None


def test_studyid():
    cassette = os.path.join(CASSETTES, 'studies.v1.yaml')
    filter_params = [
        ('access_key', Keyring['ACCESS_KEY']),
        ('secret_key', Keyring['SECRET_KEY']),
        ('study_id', 'STUDY_ID')
    ]
    studyid = '123lrVdb0g6tf3PeJr5ZtZC8'
    with vcr.use_cassette(cassette, decode_compressed_response=True,
                          filter_post_data_parameters=filter_params):
        ans = mano.studyid(Keyring, 'Project A')
        assert ans == studyid


def test_studyid_not_found():
    cassette = os.path.join(CASSETTES, 'studies.v1.yaml')
    filter_params = [
        ('access_key', Keyring['ACCESS_KEY']),
        ('secret_key', Keyring['SECRET_KEY']),
        ('study_id', 'STUDY_ID')
    ]
    with vcr.use_cassette(cassette, decode_compressed_response=True,
                          filter_post_data_parameters=filter_params):
        with pytest.raises(mano.StudyIDError):
            _ = mano.studyid(Keyring, 'Project X')


def test_studyname():
    cassette = os.path.join(CASSETTES, 'studies.v1.yaml')
    filter_params = [
        ('access_key', Keyring['ACCESS_KEY']),
        ('secret_key', Keyring['SECRET_KEY']),
        ('study_id', 'STUDY_ID')
    ]
    studyname = 'Project A'
    with vcr.use_cassette(cassette, decode_compressed_response=True,
                          filter_post_data_parameters=filter_params):
        ans = mano.studyname(Keyring, '123lrVdb0g6tf3PeJr5ZtZC8')
        assert ans == studyname


def test_studyname_not_found():
    cassette = os.path.join(CASSETTES, 'studies.v1.yaml')
    filter_params = [
        ('access_key', Keyring['ACCESS_KEY']),
        ('secret_key', Keyring['SECRET_KEY']),
        ('study_id', 'STUDY_ID')
    ]
    # studyname = 'Project X'
    with vcr.use_cassette(cassette, decode_compressed_response=True,
                          filter_post_data_parameters=filter_params):
        with pytest.raises(mano.StudyNameError):
            _ = mano.studyname(Keyring, 'x')


def test_device_settings():
    # The device_settings function is implemented by programmatically logging
    # into the Beiwe frontend (which any user can do) and scraping the Study
    # app settings page. This type of function is brittle and I'm choosing not
    # to spend any time dealing with it.
    #
    # It's worth noting that this function also needs the user to pass in a
    # Study ID that is different from the usual Study ID expected by other API
    # endpoints. This was not always the case and this alternate Study ID is
    # not returned by get-studies/v1 or anywhere else that I can think of.
    #
    # At the moment, Beiwe does have an export_study_settings_file API endpoint,
    # but it's only accessible to users with site administration privileges.
    """
    cassette = os.path.join(CASSETTES, 'device_settings.yaml')
    filter_params = [
        ('access_key', Keyring['ACCESS_KEY']),
        ('secret_key', Keyring['SECRET_KEY']),
        ('username', Keyring['USERNAME']),
        ('password', Keyring['PASSWORD']),
        ('study_id', 'STUDY_ID')
    ]
    device_settings = set([
        ('accelerometer_off_duration_seconds', '10'),
        ('accelerometer_on_duration_seconds', '10')
    ])
    with vcr.use_cassette(cassette, decode_compressed_response=True,
                          filter_post_data_parameters=filter_params):
        ans = set()
        for setting in mano.device_settings(Keyring, '123'):
            ans.add(setting)
        assert ans == device_settings
    """


