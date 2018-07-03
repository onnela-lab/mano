import os
import vcr
import mano
import pytest

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
    os.environ['NRG_KEYRING_PASS'] = NRG_KEYRING_PASS
    f = os.path.join(DIR, 'keyring.enc')
    ans = mano.keyring('beiwe.onnela', keyring_file=f)
    assert ans == Keyring

def test_keyring_wrong_password():
    os.environ['NRG_KEYRING_PASS'] = '**wrong**'
    f = os.path.join(DIR, 'keyring.enc')
    with pytest.raises(mano.KeyringError):
        _ = mano.keyring('beiwe.onnela', keyring_file=f)

def test_keyring_missing_file():
    with pytest.raises(IOError):
        _ = mano.keyring('beiwe.onnela', keyring_file='no-such-file.enc')

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
        ('access_key', 'ACCESS_KEY'),
        ('secret_key', 'SECRET_KEY')
    ]
    studies = set([
        ('Project A', '123lrVdb0g6tf3PeJr5ZtZC8'),
        ('Project B', '123U93wwgS18aLDIwdYXTXsr')
    ])
    ans = set()
    with vcr.use_cassette(cassette, decode_compressed_response=True, 
                          filter_post_data_parameters=filter_params) as cass:
        for study in mano.studies(Keyring):
            ans.add(study)
    assert ans == studies

def test_users():
    cassette = os.path.join(CASSETTES, 'users.v1.yaml')
    filter_params = [
        ('access_key', 'ACCESS_KEY'),
        ('secret_key', 'SECRET_KEY'),
        ('study_id', 'STUDY_ID')
    ]
    users = set(["tgsidhm", "lholbc5", "yxzxtwr"])
    ans = set()
    with vcr.use_cassette(cassette, decode_compressed_response=True, 
                          filter_post_data_parameters=filter_params) as cass:
        for user in mano.users(Keyring, 'STUDY_ID'):
            ans.add(user)
    assert ans == users

def test_expand_study_id():
    cassette = os.path.join(CASSETTES, 'studies.v1.yaml')
    filter_params = [
        ('access_key', 'ACCESS_KEY'),
        ('secret_key', 'SECRET_KEY'),
        ('study_id', 'STUDY_ID')
    ]
    with vcr.use_cassette(cassette, decode_compressed_response=True, 
                          filter_post_data_parameters=filter_params) as cass:
        study = ('Project A', '123lrVdb0g6tf3PeJr5ZtZC8')
        ans = mano.expand_study_id(Keyring, '123lrVdb0g6tf3PeJr5ZtZC8')
        assert ans == study

def test_expand_study_id_conflict():
    cassette = os.path.join(CASSETTES, 'studies.v1.yaml')
    filter_params = [
        ('access_key', 'ACCESS_KEY'),
        ('secret_key', 'SECRET_KEY'),
        ('study_id', 'STUDY_ID')
    ]
    with vcr.use_cassette(cassette, decode_compressed_response=True, 
                          filter_post_data_parameters=filter_params) as cass:
        with pytest.raises(mano.AmbiguousStudyIDError):       
            _ = mano.expand_study_id(Keyring, '123')

def test_expand_study_id_nomatch():
    cassette = os.path.join(CASSETTES, 'studies.v1.yaml')
    filter_params = [
        ('access_key', 'ACCESS_KEY'),
        ('secret_key', 'SECRET_KEY'),
        ('study_id', 'STUDY_ID')
    ]
    with vcr.use_cassette(cassette, decode_compressed_response=True, 
                          filter_post_data_parameters=filter_params) as cass:
        ans = mano.expand_study_id(Keyring, '321')
        assert ans == None
