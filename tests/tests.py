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


def test_download():
    """
    The data used in this test (cassette) are real, but they were captured on a
    test phone from a test deployment of beiwe-backend.
    """
    cassette = os.path.join(CASSETTES, 'download.v1.yaml')
    filter_params = [
        ('access_key', Keyring['ACCESS_KEY']),
        ('secret_key', Keyring['SECRET_KEY']),
        ('study_id', 'STUDY_ID'),
        ('user_ids', 'USER_ID')
    ]
    
    # urllib3 2.0.0+ causes the downloaded file to be 97,409 bytes instead of 443,610 bytes, and
    # ZipFile throws a BadZipFile exception. (Unable to find a valid end of central directory
    # structure). I don't even know how to begin debugging this, so I have to pin urllib3 to an
    # older version.
    
    with vcr.use_cassette(cassette, filter_post_data_parameters=filter_params):
        zf = mano.sync.download(Keyring,
                                study_id='STUDY_ID',
                                user_ids=['USER_ID'],
                                data_streams=['identifiers', 'gps'],
                                time_start='2018-06-15T00:00:00',
                                time_end='2018-06-17T00:00:00')
        ans = set()
        for zinfo in zf.infolist():
            ans.add((zinfo.filename, zinfo.CRC))
        assert ans == test_download.index


test_download.index = set([
    ('6y6s1w4g/identifiers/2018-06-15 16_00_00.csv', 4113954587),
    ('6y6s1w4g/gps/2018-06-15 22_00_00.csv', 3073924694),
    ('6y6s1w4g/gps/2018-06-15 17_00_00.csv', 4177290012),
    ('6y6s1w4g/gps/2018-06-15 20_00_00.csv', 3999192708),
    ('6y6s1w4g/gps/2018-06-15 18_00_00.csv', 4038997044),
    ('6y6s1w4g/gps/2018-06-15 21_00_00.csv', 2945081574),
    ('6y6s1w4g/gps/2018-06-15 19_00_00.csv', 4035326526),
    ('6y6s1w4g/gps/2018-06-15 16_00_00.csv', 427497446),
    ('6y6s1w4g/gps/2018-06-16 04_00_00.csv', 2574140219),
    ('6y6s1w4g/gps/2018-06-16 01_00_00.csv', 503869630),
    ('6y6s1w4g/gps/2018-06-16 03_00_00.csv', 1817118505),
    ('6y6s1w4g/gps/2018-06-16 00_00_00.csv', 963879171),
    ('6y6s1w4g/gps/2018-06-15 23_00_00.csv', 2924619047),
    ('6y6s1w4g/gps/2018-06-16 02_00_00.csv', 2868941135),
    ('6y6s1w4g/gps/2018-06-16 07_00_00.csv', 2619751600),
    ('6y6s1w4g/gps/2018-06-16 12_00_00.csv', 3738822868),
    ('6y6s1w4g/gps/2018-06-16 10_00_00.csv', 2382158563),
    ('6y6s1w4g/gps/2018-06-16 08_00_00.csv', 3580985466),
    ('6y6s1w4g/gps/2018-06-16 09_00_00.csv', 771315427),
    ('6y6s1w4g/gps/2018-06-16 11_00_00.csv', 1386915032),
    ('6y6s1w4g/gps/2018-06-16 14_00_00.csv', 641388715),
    ('6y6s1w4g/gps/2018-06-16 15_00_00.csv', 3728053865),
    ('6y6s1w4g/gps/2018-06-16 16_00_00.csv', 1258485774),
    ('6y6s1w4g/gps/2018-06-16 18_00_00.csv', 1597315532),
    ('6y6s1w4g/gps/2018-06-16 13_00_00.csv', 2905130265),
    ('6y6s1w4g/gps/2018-06-16 19_00_00.csv', 565983226),
    ('6y6s1w4g/gps/2018-06-16 17_00_00.csv', 2142570097),
    ('6y6s1w4g/gps/2018-06-16 06_00_00.csv', 3417900549),
    ('6y6s1w4g/gps/2018-06-16 20_00_00.csv', 1834664030),
    ('6y6s1w4g/gps/2018-06-16 05_00_00.csv', 3970320035),
    ('registry', 942145567)
])
