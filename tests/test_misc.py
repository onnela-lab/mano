import os

import pytest
import responses

import mano


DIR = os.path.dirname(__file__)


@responses.activate
def test_users(keyring, mock_users_response):
    expected_users = set(["tgsidhm", "lholbc5", "yxzxtwr"])
    responses.post(
        keyring['URL'] + '/get-users/v1',
        body=mock_users_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    users = set()
    for user in mano.users(keyring, 'STUDY_ID'):
        users.add(user)
    assert users == expected_users


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
    # At the moment, Beiwe does have an export_study_settings_file API endpoint
    # but it's only accessible to users with site administration privileges.
    """
    Keyring = {
        'URL': 'https://studies.beiwe.org',
        'USERNAME': 'foobar',
        'PASSWORD': 'bizbat',
        'ACCESS_KEY': 'ACCESS_KEY',
        'SECRET_KEY': 'SECRET_KEY'
    }
    cassette = os.path.join(DIR, 'cassettes', 'device_settings.yaml')
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


def test_interval():
    assert mano.interval("10s") == 10
    assert mano.interval("5m") == 300
    assert mano.interval("2h") == 7200
    assert mano.interval("1d") == 86400
    assert mano.interval("0s") == 0
    assert mano.interval("0h") == 0
    assert mano.interval("0H") == 0
    assert mano.interval("0m") == 0
    assert mano.interval("0d") == 0
    assert mano.interval("000000000000m") == 0
    
    with pytest.raises(mano.IntervalError, match="invalid interval 'y'"):
        mano.interval("y")
    
    # there's a regex that catches it first
    # with pytest.raises(mano.IntervalError, match="invalid interval unit '10x'"):
    with pytest.raises(mano.IntervalError, match="invalid interval '10x'"):
        mano.interval("10x")
    
    with pytest.raises(mano.IntervalError, match="invalid interval 'abc'"):
        mano.interval("abc")
    
    with pytest.raises(mano.IntervalError, match="invalid interval ''"):
        mano.interval("")
    
    with pytest.raises(mano.IntervalError, match="invalid interval ''"):
        mano.interval("")
