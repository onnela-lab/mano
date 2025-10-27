import os

import pytest

import mano

DIR = os.path.dirname(__file__)
NRG_KEYRING_PASS = 'foobar'


def test_keyring(keyring):
    _environ = dict(os.environ)
    try:
        os.environ['NRG_KEYRING_PASS'] = NRG_KEYRING_PASS
        f = os.path.join(DIR, 'keyring.enc')
        ans = mano.keyring('beiwe.onnela', keyring_file=f)
        assert ans == keyring
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


def test_keyring_from_env(keyring):
    _environ = dict(os.environ)
    try:
        os.environ['BEIWE_URL'] = keyring['URL']
        os.environ['BEIWE_USERNAME'] = keyring['USERNAME']
        os.environ['BEIWE_PASSWORD'] = keyring['PASSWORD']
        os.environ['BEIWE_ACCESS_KEY'] = keyring['ACCESS_KEY']
        os.environ['BEIWE_SECRET_KEY'] = keyring['SECRET_KEY']
        ans = mano.keyring(None)
        assert ans == keyring
    finally:
        os.environ.clear()
        os.environ.update(_environ)


def test_keyring_from_env_missing(keyring):
    _environ = dict(os.environ)
    try:
        os.environ['BEIWE_USERNAME'] = keyring['USERNAME']
        os.environ['BEIWE_PASSWORD'] = keyring['PASSWORD']
        os.environ['BEIWE_ACCESS_KEY'] = keyring['ACCESS_KEY']
        os.environ['BEIWE_SECRET_KEY'] = keyring['SECRET_KEY']
        with pytest.raises(mano.KeyringError):
            _ = mano.keyring(None)
    finally:
        os.environ.clear()
        os.environ.update(_environ)
