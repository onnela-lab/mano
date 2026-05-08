from datetime import datetime

import pytest
import responses
from dateutil.tz import gettz

import mano
from mano.constants import UTC
from mano.messages import TIME_REQUIRED_ERROR
from mano.sync import validate_datetime, validate_required_datetime


#
# fetch_users_in_study tests
#


@responses.activate
def test_fetch_users_in_study_returns_users(keyring: dict[str, str], mock_users_response: str):
    responses.post(
        keyring['URL'] + '/get-users/v1',
        body=mock_users_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    users = list(mano.fetch_users_in_study(keyring, 'STUDY_ID'))
    assert set(users) == {"tgsidhm", "lholbc5", "yxzxtwr"}


@responses.activate
def test_fetch_users_in_study_http_error_raises_api_error(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-users/v1',
        body='Internal Server Error',
        status=500,
    )
    with pytest.raises(mano.APIError, match="500"):
        list(mano.fetch_users_in_study(keyring, 'STUDY_ID'))


@responses.activate
def test_fetch_users_in_study_sends_study_id(keyring: dict[str, str], mock_users_response: str):
    responses.post(
        keyring['URL'] + '/get-users/v1',
        body=mock_users_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    list(mano.fetch_users_in_study(keyring, 'MY_STUDY_ID'))
    request_body = responses.calls[0].request.body
    assert request_body is not None
    assert 'study_id=MY_STUDY_ID' in str(request_body)


@responses.activate
def test_fetch_users_in_study_server_returns_dict_yields_keys(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-users/v1',
        body='{"error": "no users"}',
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises((ValueError, mano.APIError)):
        list(mano.fetch_users_in_study(keyring, 'STUDY_ID'))


#
# Beiwe platform specific datetime validation tests
#


def test_datetime_validation():
    assert validate_datetime("2023-01-01T00:00:00Z", "_") == datetime(2023, 1, 1, tzinfo=UTC)
    assert validate_datetime("2023-01-01 00:00:00Z", "_") == datetime(2023, 1, 1, tzinfo=UTC)
    assert validate_required_datetime("2023-01-01T00:00:00Z", "_") == datetime(2023, 1, 1, tzinfo=UTC)
    assert validate_required_datetime("2023-01-01 00:00:00Z", "_") == datetime(2023, 1, 1, tzinfo=UTC)


def test_require_datetime_errors_on_none():
    with pytest.raises(ValueError, match=str(TIME_REQUIRED_ERROR("_"))):
        validate_required_datetime(None, "_")
    with pytest.raises(ValueError, match=str(TIME_REQUIRED_ERROR("_"))):
        validate_required_datetime("", "_")


def test_validate_datetime_no_error_on_none():
    assert validate_datetime(None, "_") is None
    assert validate_datetime("", "_") is None


def test_validate_datetime_timezone_UTC_required():
    dt_wo_tz = datetime(2023, 1, 1, tzinfo=None)
    dt_w_utc = datetime(2023, 1, 1, tzinfo=UTC)
    assert validate_datetime(dt_wo_tz, "_") == dt_w_utc


def test_validate_datetime_with_timezone_timeshifts():
    dt_ny = datetime(2023, 1, 1, 0, 0, 0, tzinfo=gettz("America/New_York"))
    dt_expected = datetime(2023, 1, 1, 5, 0, 0, tzinfo=UTC)  # shifted to UTC
    dt_should_be_utc_0_0_0 = validate_datetime(dt_ny, "_")
    assert dt_should_be_utc_0_0_0 == dt_expected


def test_validate_datetime_string_with_timezone_timeshifts():
    dt_from_str = "2023-01-01T05:00:00+05:00"  # UTC-5
    dt_expected = datetime(2023, 1, 1, 0, 0, 0, tzinfo=UTC)  # shifted to UTC
    dt_should_be_utc_0_0_0 = validate_datetime(dt_from_str, "_")
    assert dt_should_be_utc_0_0_0 == dt_expected


def test_validate_datetime_too_something():
    with pytest.raises(ValueError, match=".*is before the earliest possible.*"):
        validate_datetime("2010-01-01T00:00:00Z", "_")
    with pytest.raises(ValueError, match=".*is too far in the future.*"):
        validate_datetime("2100-01-01T00:00:00Z", "_")


#
# interval tests
#


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

    with pytest.raises(mano.IntervalError, match="invalid interval '10x'"):
        mano.interval("10x")

    with pytest.raises(mano.IntervalError, match="invalid interval 'abc'"):
        mano.interval("abc")

    with pytest.raises(mano.IntervalError, match="invalid interval ''"):
        mano.interval("")

    with pytest.raises(mano.IntervalError, match="invalid interval ''"):
        mano.interval("")


def test_interval_negative_raises_error():
    with pytest.raises(mano.IntervalError):
        mano.interval("-5m")
    with pytest.raises(mano.IntervalError):
        mano.interval("-1h")


def test_interval_with_spaces_raises_error():
    with pytest.raises(mano.IntervalError):
        mano.interval(" 5m")
    with pytest.raises(mano.IntervalError):
        mano.interval("5m ")
    with pytest.raises(mano.IntervalError):
        mano.interval("5 m")


def test_interval_unit_only_raises_error():
    with pytest.raises(mano.IntervalError):
        mano.interval("m")
    with pytest.raises(mano.IntervalError):
        mano.interval("s")
    with pytest.raises(mano.IntervalError):
        mano.interval("h")
    with pytest.raises(mano.IntervalError):
        mano.interval("d")


def test_interval_float_raises_error():
    with pytest.raises(mano.IntervalError):
        mano.interval("1.5h")
    with pytest.raises(mano.IntervalError):
        mano.interval("0.5m")


def test_interval_whitespace_only_raises_error():
    with pytest.raises(mano.IntervalError):
        mano.interval(" ")


def test_interval_multiple_units_raises_error():
    with pytest.raises(mano.IntervalError):
        mano.interval("1h30m")
    with pytest.raises(mano.IntervalError):
        mano.interval("1hh")


def test_interval_uppercase_all_units():
    assert mano.interval("10S") == 10
    assert mano.interval("5M") == 300
    assert mano.interval("2H") == 7200
    assert mano.interval("1D") == 86400


@responses.activate
def test_fetch_study_settings_test_returns_settings(keyring: dict[str, str], mock_study_settings_response: str):
    responses.post(
        keyring['URL'] + '/get-study-settings/v1',
        body=mock_study_settings_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    result = dict(mano.fetch_study_settings_test(keyring, '0eb8ZGulAYf6c8smypun87PM'))
    assert result['gps'] is True
    assert result['bluetooth'] is False
    assert result['gps_on_duration_seconds'] == 60
    assert result['gps_off_duration_seconds'] == 600
    assert result['accelerometer_frequency'] == 10
    assert result['accelerometer_on_duration_seconds'] == 10
    assert result['accelerometer_off_duration_seconds'] == 10
    assert result['seconds_before_auto_logout'] == 600
    assert result['upload_data_files_frequency_seconds'] == 3600
    assert result['heartbeat_timer_minutes'] == 60


@responses.activate
def test_fetch_study_settings_test_500_raises_api_error(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-study-settings/v1',
        body='Internal Server Error',
        status=500,
    )
    with pytest.raises(mano.APIError, match="500"):
        list(mano.fetch_study_settings_test(keyring, 'STUDY_ID'))


@responses.activate
def test_fetch_study_settings_test_400_raises_api_error(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-study-settings/v1',
        body='Bad Request',
        status=400,
    )
    with pytest.raises(mano.APIError, match="400"):
        list(mano.fetch_study_settings_test(keyring, 'STUDY_ID'))


@responses.activate
def test_fetch_study_settings_test_empty_returns_nothing(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-study-settings/v1',
        body='{"device_settings": {}}',
        status=200,
        content_type='text/html; charset=utf-8'
    )
    result = list(mano.fetch_study_settings_test(keyring, 'STUDY_ID'))
    assert result == []
