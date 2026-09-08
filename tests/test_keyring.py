import os

import pytest
from pytest_mock import MockerFixture

from mano import load_keyring
from mano.mano import ENV_KEYS, KeyringError

DIR = os.path.dirname(__file__)



def test_keyring(keyring: dict[str, str]):
    _environ = dict(os.environ)
    try:
        os.environ["NRG_KEYRING_PASS"] = "foobar"
        f = os.path.join(DIR, "keyring.enc")
        ans = load_keyring("beiwe.onnela", keyring_file=f)
        assert ans == keyring
    finally:
        os.environ.clear()
        os.environ.update(_environ)


def test_keyring_empty_environment():
    _environ = dict(os.environ)
    try:
        for k in ENV_KEYS:
            if k in os.environ:
                del os.environ[k]
        with pytest.raises(KeyringError, match=r".*environment variable\(s\) not found:.*"):
            _ = load_keyring(None)
    finally:
        os.environ.clear()
        os.environ.update(_environ)


def test_keyring_empty_string_environment_all():
    _environ = dict(os.environ)
    try:
        for k in ENV_KEYS:
            os.environ[k] = ""
        with pytest.raises(KeyringError, match=".*are present but empty.$"):
            _ = load_keyring(None)
    finally:
        os.environ.clear()
        os.environ.update(_environ)


def test_keyring_empty_string_environment_one_by_one():
    _environ = dict(os.environ)
    try:
        for k in ENV_KEYS:
            os.environ[k] = "x"
        for k in ENV_KEYS:
            os.environ[k] = ""
            with pytest.raises(KeyringError):
                _ = load_keyring(None)
            os.environ[k] = "x"
    finally:
        os.environ.clear()
        os.environ.update(_environ)


def test_keyring_wrong_password():
    _environ = dict(os.environ)
    try:
        os.environ["NRG_KEYRING_PASS"] = "**wrong**"
        f = os.path.join(DIR, "keyring.enc")
        with pytest.raises(KeyringError):
            _ = load_keyring("beiwe.onnela", keyring_file=f)
    finally:
        os.environ.clear()
        os.environ.update(_environ)


def test_keyring_missing_file():
    _environ = dict(os.environ)
    try:
        os.environ["NRG_KEYRING_PASS"] = "foobar"
        f = os.path.join(DIR, "no-such-file.enc")
        with pytest.raises(IOError):
            _ = load_keyring("beiwe.onnela", keyring_file=f)
    finally:
        os.environ.clear()
        os.environ.update(_environ)


def test_keyring_from_env(keyring: dict[str, str]):
    _environ = dict(os.environ)
    try:
        os.environ["BEIWE_URL"] = keyring["URL"]
        os.environ["BEIWE_USERNAME"] = keyring["USERNAME"]
        os.environ["BEIWE_PASSWORD"] = keyring["PASSWORD"]
        os.environ["BEIWE_ACCESS_KEY"] = keyring["ACCESS_KEY"]
        os.environ["BEIWE_SECRET_KEY"] = keyring["SECRET_KEY"]
        ans = load_keyring(None)
        assert ans == keyring
    finally:
        os.environ.clear()
        os.environ.update(_environ)


def test_keyring_prompts_for_passphrase_when_not_provided(mocker: MockerFixture, keyring: dict[str, str]):
    """ When no passphrase is given and NRG_KEYRING_PASS isn't set, fall back to an interactive prompt. """
    _environ = dict(os.environ)
    try:
        os.environ.pop("NRG_KEYRING_PASS", None)
        mock_getpass = mocker.patch("mano.mano.getpass.getpass", return_value="foobar")
        f = os.path.join(DIR, "keyring.enc")
        ans = load_keyring("beiwe.onnela", keyring_file=f)
        assert ans == keyring
        mock_getpass.assert_called_once_with("enter keyring passphrase: ")
    finally:
        os.environ.clear()
        os.environ.update(_environ)


def test_keyring_from_env_missing(keyring: dict[str, str]):
    _environ = dict(os.environ)
    try:
        os.environ["BEIWE_USERNAME"] = keyring["USERNAME"]
        os.environ["BEIWE_PASSWORD"] = keyring["PASSWORD"]
        os.environ["BEIWE_ACCESS_KEY"] = keyring["ACCESS_KEY"]
        os.environ["BEIWE_SECRET_KEY"] = keyring["SECRET_KEY"]
        with pytest.raises(KeyringError):
            _ = load_keyring(None)
    finally:
        os.environ.clear()
        os.environ.update(_environ)
