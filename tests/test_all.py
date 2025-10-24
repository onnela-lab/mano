import os

import pytest
import responses
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


@responses.activate
def test_studies(keyring, mock_studies_response):
    expected_studies = set([
        ('Project A', '123lrVdb0g6tf3PeJr5ZtZC8'),
        ('Project B', '123U93wwgS18aLDIwdYXTXsr')
    ])
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    studies = set()
    for study in mano.studies(keyring):
        studies.add(study)

    assert studies == expected_studies


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


@responses.activate
def test_expand_study_id(keyring, mock_studies_response):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    expected_study = ('Project A', '123lrVdb0g6tf3PeJr5ZtZC8')
    study = mano.expand_study_id(keyring, '123lrVdb0g6tf3PeJr5ZtZC8')
    assert study == expected_study


@responses.activate
def test_expand_study_id_conflict(keyring, mock_studies_response):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises(mano.AmbiguousStudyIDError):
        _ = mano.expand_study_id(keyring, '123')


@responses.activate
def test_expand_study_id_nomatch(keyring, mock_studies_response):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    study = mano.expand_study_id(keyring, '321')
    assert study is None


@responses.activate
def test_studyid(keyring, mock_studies_response):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    expected_studyid = '123lrVdb0g6tf3PeJr5ZtZC8'
    study_id = mano.studyid(keyring, 'Project A')
    assert study_id == expected_studyid


@responses.activate
def test_studyid_not_found(keyring, mock_studies_response):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises(mano.StudyIDError):
        _ = mano.studyid(keyring, 'Project X')


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


