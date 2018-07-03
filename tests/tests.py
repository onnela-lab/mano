import os
import vcr
import mano
import pytest

DIR = os.path.dirname(__file__)
CASSETTES = os.path.join(DIR, 'cassettes')

Keyring = {
    'URL': 'https://studies.beiwe.org',
    'USERNAME': 'foobar',
    'PASSWORD': 'bizbat',
    'ACCESS_KEY': 'ACCESS_KEY',
    'SECRET_KEY': 'SECRET_KEY'
}

def test_keyring():
    os.environ['NRG_KEYRING_PASS'] = 'foobar'
    f = os.path.join(DIR, 'keyring.enc')
    ans = mano.keyring('beiwe.onnela', keyring_file=f)
    assert ans == Keyring

def test_keyring_wrong_password():
    os.environ['NRG_KEYRING_PASS'] = 'wrong'
    f = os.path.join(DIR, 'keyring.enc')
    with pytest.raises(mano.KeyringError):
        _ = mano.keyring('beiwe.onnela', keyring_file=f)

def test_keyring_missing_file():
    with pytest.raises(IOError):
        _ = mano.keyring('beiwe.onnela', keyring_file='no-file.enc')

def test_studies():
    cassette = os.path.join(CASSETTES, 'studies.yaml')
    filter_params = [
        ('access_key', 'ACCESS_KEY'),
        ('secret_key', 'SECRET_KEY')
    ]
    studies = set([
        ('Project A', '12abcdef34567g8hi90123ab'),
        ('Project B', '92abcdef34567g8hi90123ac')
    ])
    ans = set()
    with vcr.use_cassette(cassette, decode_compressed_response=True, 
                          filter_post_data_parameters=filter_params) as cass:
        for study in mano.studies(Keyring):
            ans.add(study)
    assert ans == studies

