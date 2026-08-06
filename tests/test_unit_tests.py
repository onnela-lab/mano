from datetime import datetime
from pathlib import Path

import pytest
import responses
from dateutil.tz import gettz

from mano import APIError, interval, IntervalError
from mano.beiwe_api import (fetch_interventions, fetch_participant_table_data,
    fetch_participant_table_data_csv, fetch_study_settings, fetch_study_settings_test,
    fetch_summary_statistics, fetch_survey_history, fetch_users_in_study)
from mano.constants import UTC
from mano.messages import TIME_REQUIRED_ERROR
from mano.sync import validate_datetime, validate_required_datetime


#
# fetch_users_in_study tests
#


@responses.activate
def test_fetch_users_in_study_returns_users(keyring: dict[str, str], mock_users_response: str):
    responses.post(
        keyring['URL'] + '/get-participants/v1',
        body=mock_users_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    users = list(fetch_users_in_study(keyring, 'STUDY_ID'))
    assert set(users) == {"tgsidhm", "lholbc5", "yxzxtwr"}


@responses.activate
def test_fetch_users_in_study_http_error_raises_api_error(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-participants/v1',
        body='Internal Server Error',
        status=500,
    )
    with pytest.raises(APIError, match="500"):
        list(fetch_users_in_study(keyring, 'STUDY_ID'))


@responses.activate
def test_fetch_users_in_study_sends_study_id(keyring: dict[str, str], mock_users_response: str):
    responses.post(
        keyring['URL'] + '/get-participants/v1',
        body=mock_users_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    list(fetch_users_in_study(keyring, 'MY_STUDY_ID'))
    request_body = responses.calls[0].request.body
    assert request_body is not None
    assert 'study_id=MY_STUDY_ID' in str(request_body)


@responses.activate
def test_fetch_users_in_study_server_returns_dict_yields_keys(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-participants/v1',
        body='{"error": "no users"}',
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises((ValueError, APIError)):
        list(fetch_users_in_study(keyring, 'STUDY_ID'))


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
    assert interval("10s") == 10
    assert interval("5m") == 300
    assert interval("2h") == 7200
    assert interval("1d") == 86400
    assert interval("0s") == 0
    assert interval("0h") == 0
    assert interval("0H") == 0
    assert interval("0m") == 0
    assert interval("0d") == 0
    assert interval("000000000000m") == 0

    with pytest.raises(IntervalError, match="invalid interval 'y'"):
        interval("y")

    with pytest.raises(IntervalError, match="invalid interval '10x'"):
        interval("10x")

    with pytest.raises(IntervalError, match="invalid interval 'abc'"):
        interval("abc")

    with pytest.raises(IntervalError, match="invalid interval ''"):
        interval("")

    with pytest.raises(IntervalError, match="invalid interval ''"):
        interval("")


def test_interval_negative_raises_error():
    with pytest.raises(IntervalError):
        interval("-5m")
    with pytest.raises(IntervalError):
        interval("-1h")


def test_interval_with_spaces_raises_error():
    with pytest.raises(IntervalError):
        interval(" 5m")
    with pytest.raises(IntervalError):
        interval("5m ")
    with pytest.raises(IntervalError):
        interval("5 m")


def test_interval_unit_only_raises_error():
    with pytest.raises(IntervalError):
        interval("m")
    with pytest.raises(IntervalError):
        interval("s")
    with pytest.raises(IntervalError):
        interval("h")
    with pytest.raises(IntervalError):
        interval("d")


def test_interval_float_raises_error():
    with pytest.raises(IntervalError):
        interval("1.5h")
    with pytest.raises(IntervalError):
        interval("0.5m")


def test_interval_whitespace_only_raises_error():
    with pytest.raises(IntervalError):
        interval(" ")


def test_interval_multiple_units_raises_error():
    with pytest.raises(IntervalError):
        interval("1h30m")
    with pytest.raises(IntervalError):
        interval("1hh")


def test_interval_uppercase_all_units():
    assert interval("10S") == 10
    assert interval("5M") == 300
    assert interval("2H") == 7200
    assert interval("1D") == 86400


@responses.activate
def test_fetch_interventions_returns_data(keyring: dict[str, str], mock_interventions_response: str):
    responses.post(keyring['URL'] + '/get-interventions/v1', body=mock_interventions_response, status=200)
    result = dict(fetch_interventions(keyring, 'STUDY_ID'))
    assert "participant1" in result
    assert "participant2" in result


@responses.activate
def test_fetch_interventions_empty_returns_nothing(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-interventions/v1', body='{}', status=200)
    result = list(fetch_interventions(keyring, 'STUDY_ID'))
    assert result == []


@responses.activate
def test_fetch_survey_history_returns_data(keyring: dict[str, str], mock_survey_history_response: str):
    responses.post(keyring['URL'] + '/get-survey-history/v1', body=mock_survey_history_response, status=200)
    result = dict(fetch_survey_history(keyring, 'STUDY_ID'))
    assert "abc123survey" in result


@responses.activate
def test_fetch_survey_history_empty_returns_nothing(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-survey-history/v1', body='{}', status=200)
    result = list(fetch_survey_history(keyring, 'STUDY_ID'))
    assert result == []


@responses.activate
def test_fetch_study_settings_returns_all_keys(keyring: dict[str, str], mock_study_settings_response: str):
    responses.post(keyring['URL'] + '/get-study-settings/v1', body=mock_study_settings_response, status=200)
    result = dict(fetch_study_settings(keyring, 'STUDY_ID'))
    assert "surveys" in result
    assert "device_settings" in result
    assert "interventions" in result


@responses.activate
def test_fetch_participant_table_data_returns_rows(keyring: dict[str, str], mock_participant_table_response: str):
    responses.post(keyring['URL'] + '/get-participant-table-data/v1', body=mock_participant_table_response, status=200)
    result = list(fetch_participant_table_data(keyring, 'STUDY_ID'))
    assert len(result) == 1
    assert result[0]['Patient ID'] == 'abc123'


@responses.activate
def test_fetch_participant_table_data_empty_returns_nothing(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-participant-table-data/v1', body='[]', status=200)
    result = list(fetch_participant_table_data(keyring, 'STUDY_ID'))
    assert result == []


@responses.activate
def test_fetch_participant_table_data_non_list_raises(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-participant-table-data/v1', body='{}', status=200)
    with pytest.raises(ValueError, match="expected a list"):
        list(fetch_participant_table_data(keyring, 'STUDY_ID'))


#
# fetch_participant_table_data_csv tests
#


@responses.activate
def test_fetch_participant_table_data_csv_writes_file(
    keyring: dict[str, str], tmp_path: Path, mock_participant_table_csv_response: str
):
    responses.post(
        keyring['URL'] + '/get-participant-table-data/v1', body=mock_participant_table_csv_response, status=200
    )
    file_path = tmp_path / "participants.csv"
    fetch_participant_table_data_csv(keyring, 'STUDY_ID', str(file_path))
    assert file_path.read_bytes() == mock_participant_table_csv_response.encode()


@responses.activate
def test_fetch_participant_table_data_csv_creates_missing_directories(
    keyring: dict[str, str], tmp_path: Path, mock_participant_table_csv_response: str
):
    responses.post(
        keyring['URL'] + '/get-participant-table-data/v1', body=mock_participant_table_csv_response, status=200
    )
    file_path = tmp_path / "subdir" / "nested" / "participants.csv"
    fetch_participant_table_data_csv(keyring, 'STUDY_ID', str(file_path))
    assert file_path.read_bytes() == mock_participant_table_csv_response.encode()


@responses.activate
def test_fetch_participant_table_data_csv_raises_on_error(keyring: dict[str, str], tmp_path: Path):
    responses.post(keyring['URL'] + '/get-participant-table-data/v1', body='error', status=500)
    file_path = tmp_path / "participants.csv"
    with pytest.raises(APIError, match="500"):
        fetch_participant_table_data_csv(keyring, 'STUDY_ID', str(file_path))
    assert not file_path.exists()


@responses.activate
def test_fetch_study_settings_test_returns_settings(keyring: dict[str, str], mock_study_settings_response: str):
    responses.post(
        keyring['URL'] + '/get-study-settings/v1',
        body=mock_study_settings_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    result = dict(fetch_study_settings_test(keyring, '0eb8ZGulAYf6c8smypun87PM'))
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
    with pytest.raises(APIError, match="500"):
        list(fetch_study_settings_test(keyring, 'STUDY_ID'))


@responses.activate
def test_fetch_study_settings_test_400_raises_api_error(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-study-settings/v1',
        body='Bad Request',
        status=400,
    )
    with pytest.raises(APIError, match="400"):
        list(fetch_study_settings_test(keyring, 'STUDY_ID'))


@responses.activate
def test_fetch_study_settings_test_empty_returns_nothing(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-study-settings/v1',
        body='{"device_settings": {}}',
        status=200,
        content_type='text/html; charset=utf-8'
    )
    result = list(fetch_study_settings_test(keyring, 'STUDY_ID'))
    assert result == []


#
# fetch_summary_statistics tests
#


@responses.activate
def test_fetch_summary_statistics_returns_data(keyring: dict[str, str], mock_summary_statistics_response: str):
    responses.post(keyring['URL'] + '/get-summary-statistics/v1', body=mock_summary_statistics_response, status=200)
    result = list(fetch_summary_statistics(keyring, 'STUDY_ID'))
    assert len(result) == 2
    assert result[0]['participant_id'] == 'abc123'


@responses.activate
def test_fetch_summary_statistics_empty_returns_nothing(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-summary-statistics/v1', body='[]', status=200)
    result = list(fetch_summary_statistics(keyring, 'STUDY_ID'))
    assert result == []


@responses.activate
def test_fetch_summary_statistics_http_error_raises_api_error(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-summary-statistics/v1', body='Internal Server Error', status=500)
    with pytest.raises(APIError, match="500"):
        list(fetch_summary_statistics(keyring, 'STUDY_ID'))


@responses.activate
def test_fetch_summary_statistics_sends_study_id(keyring: dict[str, str], mock_summary_statistics_response: str):
    responses.post(keyring['URL'] + '/get-summary-statistics/v1', body=mock_summary_statistics_response, status=200)
    list(fetch_summary_statistics(keyring, 'MY_STUDY_ID'))
    assert 'study_id=MY_STUDY_ID' in str(responses.calls[0].request.body)


@responses.activate
def test_fetch_summary_statistics_sends_optional_params(keyring: dict[str, str], mock_summary_statistics_response: str):
    responses.post(keyring['URL'] + '/get-summary-statistics/v1', body=mock_summary_statistics_response, status=200)
    fetch_summary_statistics(keyring, 'STUDY_ID', start_date='2024-01-01', end_date='2024-01-31', fields='beiwe_id')
    body = str(responses.calls[0].request.body)
    assert 'start_date=2024-01-01' in body
    assert 'end_date=2024-01-31' in body
    assert 'fields=beiwe_id' in body


@responses.activate
def test_fetch_summary_statistics_omits_none_params(keyring: dict[str, str], mock_summary_statistics_response: str):
    responses.post(keyring['URL'] + '/get-summary-statistics/v1', body=mock_summary_statistics_response, status=200)
    list(fetch_summary_statistics(keyring, 'STUDY_ID'))
    body = str(responses.calls[0].request.body)
    assert 'start_date' not in body
    assert 'end_date' not in body
    assert 'fields' not in body
