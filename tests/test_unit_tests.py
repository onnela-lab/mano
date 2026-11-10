from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zipfile import ZipFile

import orjson, pytest, requests, responses
from dateutil.tz import gettz

from mano import APIError, interval, IntervalError
from mano.beiwe_api import (_fetch_participant_device_status_history, fetch_interventions,
    fetch_participant_heartbeat_history, fetch_participant_notification_history,
    fetch_participant_table_data, fetch_participant_table_data_csv, fetch_participant_upload_history,
    fetch_participant_version_history, fetch_participants_in_study, fetch_study_device_settings,
    fetch_study_settings, fetch_summary_statistics, fetch_survey_history, fetch_sycamore_analysis_output)
from mano.constants import UTC
from mano.mano import login, LoginError
from mano.messages import (API_400_ERROR, API_403_ERROR, API_404_ERROR, BACKFILL_FILE_EXISTS_MSG,
    BACKFILL_RESTARTING_WARNING, BACKFILL_UNPARSABLE_DATE_ERROR, BAD_MULTITHREADING_ERROR,
    PARSE_ERROR_TOO_MANY_MATCHES_MSG, TIME_REQUIRED_ERROR)
from mano.sync import validate_datetime, validate_required_datetime


#
# fetch_participants_in_study tests
#


@responses.activate
def test_fetch_participants_in_study_returns_users(keyring: dict[str, str], mock_users_response: str):
    responses.post(
        keyring['URL'] + '/get-participant-ids/v1',
        body=mock_users_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    users = list(fetch_participants_in_study(keyring, 'STUDY_ID'))
    assert set(users) == {"tgsidhm", "lholbc5", "yxzxtwr"}


@responses.activate
def test_fetch_participants_in_study_http_error_raises_api_error(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-participant-ids/v1',
        body='Internal Server Error',
        status=500,
    )
    with pytest.raises(APIError, match="500"):
        list(fetch_participants_in_study(keyring, 'STUDY_ID'))


@responses.activate
def test_fetch_participants_in_study_sends_study_id(keyring: dict[str, str], mock_users_response: str):
    responses.post(
        keyring['URL'] + '/get-participant-ids/v1',
        body=mock_users_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    list(fetch_participants_in_study(keyring, 'MY_STUDY_ID'))
    request_body = responses.calls[0].request.body
    assert request_body is not None
    assert 'study_id=MY_STUDY_ID' in str(request_body)


@responses.activate
def test_fetch_participants_in_study_server_returns_dict_raises_value_error(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-participant-ids/v1',
        body='{"error": "no users"}',
        status=200,
        content_type='text/html; charset=utf-8'
    )
    # A 200 response with an object still violates the endpoint's list response contract.
    with pytest.raises(ValueError, match="expected a list of participant IDs, got dict"):
        list(fetch_participants_in_study(keyring, 'STUDY_ID'))


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
def test_fetch_study_device_settings_returns_settings(keyring: dict[str, str], mock_study_settings_response: str):
    responses.post(
        keyring['URL'] + '/get-study-settings/v1',
        body=mock_study_settings_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    result = dict(fetch_study_device_settings(keyring, '0eb8ZGulAYf6c8smypun87PM'))
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
def test_fetch_study_device_settings_500_raises_api_error(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-study-settings/v1',
        body='Internal Server Error',
        status=500,
    )
    with pytest.raises(APIError, match="500"):
        list(fetch_study_device_settings(keyring, 'STUDY_ID'))


@responses.activate
def test_fetch_study_device_settings_400_raises_api_error(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-study-settings/v1',
        body='Bad Request',
        status=400,
    )
    with pytest.raises(APIError, match="400"):
        list(fetch_study_device_settings(keyring, 'STUDY_ID'))


@responses.activate
def test_fetch_study_device_settings_empty_returns_nothing(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-study-settings/v1',
        body='{"device_settings": {}}',
        status=200,
        content_type='text/html; charset=utf-8'
    )
    result = list(fetch_study_device_settings(keyring, 'STUDY_ID'))
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


#
# fetch_survey_history error handling
#


@responses.activate
def test_fetch_survey_history_non_dict_raises(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-survey-history/v1', body='[]', status=200)
    with pytest.raises(ValueError, match="expected a dict of survey history data"):
        fetch_survey_history(keyring, 'STUDY_ID')


#
# login() tests
#


@responses.activate
def test_login_returns_cookies_after_redirect(keyring: dict[str, str]):
    responses.add(
        responses.POST,
        keyring['URL'] + '/validate_login',
        status=302,
        headers={'Location': keyring['URL'] + '/dashboard', 'Set-Cookie': 'sessionid=abc123'},
    )
    responses.add(responses.GET, keyring['URL'] + '/dashboard', status=200, body='ok')

    cookies = login(keyring)
    assert cookies['sessionid'] == 'abc123'


@responses.activate
def test_login_sends_username_and_password(keyring: dict[str, str]):
    responses.add(
        responses.POST,
        keyring['URL'] + '/validate_login',
        status=302,
        headers={'Location': keyring['URL'] + '/dashboard', 'Set-Cookie': 'sessionid=abc123'},
    )
    responses.add(responses.GET, keyring['URL'] + '/dashboard', status=200, body='ok')

    login(keyring)
    body = str(responses.calls[0].request.body)
    assert f"username={keyring['USERNAME']}" in body
    assert f"password={keyring['PASSWORD']}" in body


@responses.activate
def test_login_http_error_raises_login_error(keyring: dict[str, str]):
    responses.add(
        responses.POST,
        keyring['URL'] + '/validate_login',
        status=500,
        body='Internal Server Error',
    )
    with pytest.raises(LoginError, match="500"):
        login(keyring)


#
# messages.py pure formatting function tests
#


def test_backfill_unparsable_date_error():
    err = BACKFILL_UNPARSABLE_DATE_ERROR("not-a-date")
    assert isinstance(err, ValueError)
    assert "not-a-date" in str(err)
    assert "could not parse" in str(err)


def test_parse_error_too_many_matches_msg():
    msg = PARSE_ERROR_TOO_MANY_MATCHES_MSG(r"^regex$", "some/path", 2)
    assert "expected 1 match, found 2" in msg
    assert "some/path" in msg


def test_backfill_file_exists_msg():
    msg = BACKFILL_FILE_EXISTS_MSG("/tmp/backfill.json")
    assert "/tmp/backfill.json" in msg
    assert "overwritten" in msg


def test_backfill_restarting_warning():
    msg = BACKFILL_RESTARTING_WARNING("USER_ID")
    assert "USER_ID" in msg
    assert "resume" in msg


def test_bad_multithreading_error():
    msg = BAD_MULTITHREADING_ERROR("--mtX")
    assert "--mtX" in msg
    assert "--mt4" in msg


def test_api_400_error():
    msg = API_400_ERROR(400, "https://studies.beiwe.org/get-studies/v1")
    assert "https://studies.beiwe.org/get-studies/v1" in msg
    assert "400" in msg


def test_api_404_error_variants():
    no_study = API_404_ERROR(404, "https://x/get-users/v1")
    assert "the provided data stream was not valid" in no_study

    with_study = API_404_ERROR(404, "https://x/get-users/v1", study_id="STUDY_ID")
    assert "study `STUDY_ID` does not exist" in with_study

    with_participant = API_404_ERROR(404, "https://x/get-users/v1", participation_id="PART_ID")
    assert "participant `PART_ID` does not exist" in with_participant


def test_api_403_error_with_study_id():
    msg = API_403_ERROR(403, "https://x/get-users/v1", study_id="STUDY_ID")
    assert "study `STUDY_ID`" in msg
    assert "may not exist" in msg


@responses.activate
def test_fetch_participant_version_history_returns_data(keyring: dict[str, str]):
    data = [{
        'app_version_code': '250',
        'app_version_name': '2.5.0',
        'os_version': '17.0',
        'created_on': '2024-01-01T12:00:00Z',
    }]
    responses.post(keyring['URL'] + '/get-participant-version-history/v1', json=data, status=200)
    result = fetch_participant_version_history(keyring, 'PARTICIPANT_ID')
    assert result == data


@responses.activate
def test_fetch_participant_version_history_empty_returns_nothing(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-participant-version-history/v1', body='[]', status=200)
    result = fetch_participant_version_history(keyring, 'PARTICIPANT_ID')
    assert result == []


@responses.activate
def test_fetch_participant_version_history_sends_participant_id_and_credentials(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-participant-version-history/v1', body='[]', status=200)
    fetch_participant_version_history(keyring, 'MY_PARTICIPANT_ID')
    body = str(responses.calls[0].request.body)
    assert 'participant_id=MY_PARTICIPANT_ID' in body
    assert f"access_key={keyring['ACCESS_KEY']}" in body
    assert f"secret_key={keyring['SECRET_KEY']}" in body


@pytest.mark.parametrize('status_code', [400, 403, 404, 500])
@responses.activate
def test_fetch_participant_version_history_http_error_raises_api_error(
    keyring: dict[str, str], status_code: int
):
    responses.post(keyring['URL'] + '/get-participant-version-history/v1', body='error', status=status_code)
    with pytest.raises(APIError, match=str(status_code)):
        fetch_participant_version_history(keyring, 'PARTICIPANT_ID')


@responses.activate
def test_fetch_participant_heartbeat_history_returns_data(keyring: dict[str, str]):
    data = [{'timestamp': '2024-01-01T12:00:00Z'}, {'timestamp': '2024-01-01T13:00:00Z'}]
    responses.post(keyring['URL'] + '/get-participant-heartbeat-history/v1', json=data, status=200)
    result = fetch_participant_heartbeat_history(keyring, 'PARTICIPANT_ID')
    assert result == data


@responses.activate
def test_fetch_participant_heartbeat_history_empty_returns_nothing(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-participant-heartbeat-history/v1', body='[]', status=200)
    result = fetch_participant_heartbeat_history(keyring, 'PARTICIPANT_ID')
    assert result == []


@responses.activate
def test_fetch_participant_heartbeat_history_sends_participant_id_and_credentials(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-participant-heartbeat-history/v1', body='[]', status=200)
    fetch_participant_heartbeat_history(keyring, 'MY_PARTICIPANT_ID')
    body = str(responses.calls[0].request.body)
    assert 'participant_id=MY_PARTICIPANT_ID' in body
    assert f"access_key={keyring['ACCESS_KEY']}" in body
    assert f"secret_key={keyring['SECRET_KEY']}" in body


@pytest.mark.parametrize('status_code', [400, 403, 404, 500])
@responses.activate
def test_fetch_participant_heartbeat_history_http_error_raises_api_error(
    keyring: dict[str, str], status_code: int
):
    responses.post(keyring['URL'] + '/get-participant-heartbeat-history/v1', body='error', status=status_code)
    with pytest.raises(APIError, match=str(status_code)):
        fetch_participant_heartbeat_history(keyring, 'PARTICIPANT_ID')


@responses.activate
def test_fetch_participant_upload_history_returns_data(keyring: dict[str, str]):
    data = [{
        'file_size': 128,
        'timestamp': '2024-01-01T12:00:00Z',
        'file_name': 'gps/1704110400.csv',
    }]
    responses.post(keyring['URL'] + '/get-participant-upload-history/v1', json=data, status=200)
    result = fetch_participant_upload_history(keyring, 'PARTICIPANT_ID')
    assert result == data


@responses.activate
def test_fetch_participant_upload_history_empty_returns_nothing(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-participant-upload-history/v1', body='[]', status=200)
    result = fetch_participant_upload_history(keyring, 'PARTICIPANT_ID')
    assert result == []


@responses.activate
def test_fetch_participant_upload_history_sends_participant_id_and_credentials(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-participant-upload-history/v1', body='[]', status=200)
    fetch_participant_upload_history(keyring, 'MY_PARTICIPANT_ID')
    body = str(responses.calls[0].request.body)
    assert 'participant_id=MY_PARTICIPANT_ID' in body
    assert f"access_key={keyring['ACCESS_KEY']}" in body
    assert f"secret_key={keyring['SECRET_KEY']}" in body


@pytest.mark.parametrize('status_code', [400, 403, 404, 500])
@responses.activate
def test_fetch_participant_upload_history_http_error_raises_api_error(
    keyring: dict[str, str], status_code: int
):
    responses.post(keyring['URL'] + '/get-participant-upload-history/v1', body='error', status=status_code)
    with pytest.raises(APIError, match=str(status_code)):
        fetch_participant_upload_history(keyring, 'PARTICIPANT_ID')


@responses.activate
def test_fetch_participant_notification_history_returns_data(keyring: dict[str, str]):
    data = {'survey1': [{
        'timestamp': '2024-01-01T12:00:00Z',
        'type': 'absolute',
        'scheduled_time': '2024-01-01T12:00:00Z',
        'confirmed_received': False,
        'uuid': 'notification1',
        'resend': False,
        'push_rejected': False,
    }]}
    responses.post(keyring['URL'] + '/get-participant-notification-history/v1', json=data, status=200)
    result = fetch_participant_notification_history(keyring, 'PARTICIPANT_ID')
    assert result == data


@responses.activate
def test_fetch_participant_notification_history_empty_returns_nothing(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-participant-notification-history/v1', body='{}', status=200)
    result = fetch_participant_notification_history(keyring, 'PARTICIPANT_ID')
    assert result == {}


@responses.activate
def test_fetch_participant_notification_history_sends_participant_id_and_credentials(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-participant-notification-history/v1', body='{}', status=200)
    fetch_participant_notification_history(keyring, 'MY_PARTICIPANT_ID')
    body = str(responses.calls[0].request.body)
    assert 'participant_id=MY_PARTICIPANT_ID' in body
    assert f"access_key={keyring['ACCESS_KEY']}" in body
    assert f"secret_key={keyring['SECRET_KEY']}" in body


@pytest.mark.parametrize('status_code', [400, 403, 404, 500])
@responses.activate
def test_fetch_participant_notification_history_http_error_raises_api_error(
    keyring: dict[str, str], status_code: int
):
    responses.post(keyring['URL'] + '/get-participant-notification-history/v1', body='error', status=status_code)
    with pytest.raises(APIError, match=str(status_code)):
        fetch_participant_notification_history(keyring, 'PARTICIPANT_ID')


@responses.activate
def test_fetch_participant_device_status_history_returns_data(keyring: dict[str, str]):
    data = [{
        'created_on': '2024-01-01T12:00:00Z',
        'endpoint': 'upload',
        'app_os': 'ios',
        'os_version': '17.0',
        'app_version': '2.5.0',
        'device_status': {'battery_level': 0.8},
    }]
    responses.post(keyring['URL'] + '/get-participant-device-status-history/v1', json=data, status=200)
    result = _fetch_participant_device_status_history(keyring, 'PARTICIPANT_ID')
    assert result == data


@responses.activate
def test_fetch_participant_device_status_history_empty_returns_nothing(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-participant-device-status-history/v1', body='[]', status=200)
    result = _fetch_participant_device_status_history(keyring, 'PARTICIPANT_ID')
    assert result == []


@responses.activate
def test_fetch_participant_device_status_history_sends_participant_id_and_credentials(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-participant-device-status-history/v1', body='[]', status=200)
    _fetch_participant_device_status_history(keyring, 'MY_PARTICIPANT_ID')
    body = str(responses.calls[0].request.body)
    assert 'participant_id=MY_PARTICIPANT_ID' in body
    assert f"access_key={keyring['ACCESS_KEY']}" in body
    assert f"secret_key={keyring['SECRET_KEY']}" in body


@pytest.mark.parametrize('status_code', [400, 403, 404, 500])
@responses.activate
def test_fetch_participant_device_status_history_http_error_raises_api_error(
    keyring: dict[str, str], status_code: int
):
    responses.post(keyring['URL'] + '/get-participant-device-status-history/v1', body='error', status=status_code)
    with pytest.raises(APIError, match=str(status_code)):
        _fetch_participant_device_status_history(keyring, 'PARTICIPANT_ID')


@responses.activate
def test_fetch_sycamore_analysis_output_returns_zip(keyring: dict[str, str]):
    archive = BytesIO()
    with ZipFile(archive, 'w') as output:
        output.writestr('report.csv', 'participant_id,value\nabc123,1\n')
    data = archive.getvalue()
    responses.post(
        keyring['URL'] + '/get-sycamore-analysis-output/v1',
        body=data,
        status=200,
        content_type='zip',
        headers={'Content-Disposition': 'attachment; filename=report.zip'},
    )
    result = fetch_sycamore_analysis_output(keyring, 'STUDY_ID')
    assert result == data


@responses.activate
def test_fetch_sycamore_analysis_output_sends_study_id_and_credentials(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-sycamore-analysis-output/v1',
        body='No forest tasks found for this study.',
        status=404,
    )
    with pytest.raises(APIError, match="404"):
        fetch_sycamore_analysis_output(keyring, 'MY_STUDY_ID')
    body = str(responses.calls[0].request.body)
    assert 'study_id=MY_STUDY_ID' in body
    assert f"access_key={keyring['ACCESS_KEY']}" in body
    assert f"secret_key={keyring['SECRET_KEY']}" in body


@responses.activate
def test_fetch_sycamore_analysis_output_no_tasks_raises_api_error(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-sycamore-analysis-output/v1',
        body='No forest tasks found for this study.',
        status=404,
    )
    with pytest.raises(APIError, match="404"):
        fetch_sycamore_analysis_output(keyring, 'STUDY_ID')


@responses.activate
def test_fetch_summary_statistics_sends_participant_id(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-summary-statistics/v1', body='[]', status=200)
    fetch_summary_statistics(keyring, 'STUDY_ID', participant_id='MY_PARTICIPANT_ID')
    query = parse_qs(urlparse(responses.calls[0].request.url).query)
    assert query.get('participant_ids') == ['MY_PARTICIPANT_ID']


@responses.activate
def test_fetch_summary_statistics_omits_none_participant_id(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-summary-statistics/v1', body='[]', status=200)
    fetch_summary_statistics(keyring, 'STUDY_ID', participant_id=None)
    assert 'participant_id' not in str(responses.calls[0].request.body)
    assert 'participant_id' not in responses.calls[0].request.url
    assert 'participant_ids' not in str(responses.calls[0].request.body)

@pytest.mark.parametrize('body', ['not json', '', '{"incomplete":'])
@responses.activate
def test_fetch_participant_version_history_invalid_json_raises(keyring: dict[str, str], body: str):
    responses.post(keyring['URL'] + '/get-participant-version-history/v1', body=body, status=200)
    with pytest.raises(orjson.JSONDecodeError):
        fetch_participant_version_history(keyring, 'PARTICIPANT_ID')


@pytest.mark.parametrize('error', [requests.exceptions.ConnectionError, requests.exceptions.Timeout])
@responses.activate
def test_fetch_participant_version_history_request_error_propagates(keyring: dict[str, str], error):
    responses.post(keyring['URL'] + '/get-participant-version-history/v1', body=error('request failed'))
    with pytest.raises(error, match="request failed"):
        fetch_participant_version_history(keyring, 'PARTICIPANT_ID')


@responses.activate
def test_fetch_participant_version_history_handles_trailing_slash(keyring: dict[str, str]):
    keyring['URL'] += '/'
    responses.post(keyring['URL'].rstrip('/') + '/get-participant-version-history/v1', body='[]', status=200)
    result = fetch_participant_version_history(keyring, 'PARTICIPANT_ID')
    assert result == []


@responses.activate
def test_fetch_participant_version_history_encodes_participant_id_and_credentials(keyring: dict[str, str]):
    keyring['ACCESS_KEY'] = 'access+key&value'
    keyring['SECRET_KEY'] = 'secret=key+value'
    responses.post(keyring['URL'] + '/get-participant-version-history/v1', body='[]', status=200)
    fetch_participant_version_history(keyring, 'participant+id&value')
    body = parse_qs(responses.calls[0].request.body)
    assert body['participant_id'] == ['participant+id&value']
    assert body['access_key'] == [keyring['ACCESS_KEY']]
    assert body['secret_key'] == [keyring['SECRET_KEY']]


@pytest.mark.parametrize('body', ['not json', '', '{"incomplete":'])
@responses.activate
def test_fetch_participant_heartbeat_history_invalid_json_raises(keyring: dict[str, str], body: str):
    responses.post(keyring['URL'] + '/get-participant-heartbeat-history/v1', body=body, status=200)
    with pytest.raises(orjson.JSONDecodeError):
        fetch_participant_heartbeat_history(keyring, 'PARTICIPANT_ID')


@pytest.mark.parametrize('error', [requests.exceptions.ConnectionError, requests.exceptions.Timeout])
@responses.activate
def test_fetch_participant_heartbeat_history_request_error_propagates(keyring: dict[str, str], error):
    responses.post(keyring['URL'] + '/get-participant-heartbeat-history/v1', body=error('request failed'))
    with pytest.raises(error, match="request failed"):
        fetch_participant_heartbeat_history(keyring, 'PARTICIPANT_ID')


@responses.activate
def test_fetch_participant_heartbeat_history_handles_trailing_slash(keyring: dict[str, str]):
    keyring['URL'] += '/'
    responses.post(keyring['URL'].rstrip('/') + '/get-participant-heartbeat-history/v1', body='[]', status=200)
    result = fetch_participant_heartbeat_history(keyring, 'PARTICIPANT_ID')
    assert result == []


@responses.activate
def test_fetch_participant_heartbeat_history_encodes_participant_id_and_credentials(keyring: dict[str, str]):
    keyring['ACCESS_KEY'] = 'access+key&value'
    keyring['SECRET_KEY'] = 'secret=key+value'
    responses.post(keyring['URL'] + '/get-participant-heartbeat-history/v1', body='[]', status=200)
    fetch_participant_heartbeat_history(keyring, 'participant+id&value')
    body = parse_qs(responses.calls[0].request.body)
    assert body['participant_id'] == ['participant+id&value']
    assert body['access_key'] == [keyring['ACCESS_KEY']]
    assert body['secret_key'] == [keyring['SECRET_KEY']]


@pytest.mark.parametrize('body', ['not json', '', '{"incomplete":'])
@responses.activate
def test_fetch_participant_upload_history_invalid_json_raises(keyring: dict[str, str], body: str):
    responses.post(keyring['URL'] + '/get-participant-upload-history/v1', body=body, status=200)
    with pytest.raises(orjson.JSONDecodeError):
        fetch_participant_upload_history(keyring, 'PARTICIPANT_ID')


@pytest.mark.parametrize('error', [requests.exceptions.ConnectionError, requests.exceptions.Timeout])
@responses.activate
def test_fetch_participant_upload_history_request_error_propagates(keyring: dict[str, str], error):
    responses.post(keyring['URL'] + '/get-participant-upload-history/v1', body=error('request failed'))
    with pytest.raises(error, match="request failed"):
        fetch_participant_upload_history(keyring, 'PARTICIPANT_ID')


@responses.activate
def test_fetch_participant_upload_history_handles_trailing_slash(keyring: dict[str, str]):
    keyring['URL'] += '/'
    responses.post(keyring['URL'].rstrip('/') + '/get-participant-upload-history/v1', body='[]', status=200)
    result = fetch_participant_upload_history(keyring, 'PARTICIPANT_ID')
    assert result == []


@responses.activate
def test_fetch_participant_upload_history_encodes_participant_id_and_credentials(keyring: dict[str, str]):
    keyring['ACCESS_KEY'] = 'access+key&value'
    keyring['SECRET_KEY'] = 'secret=key+value'
    responses.post(keyring['URL'] + '/get-participant-upload-history/v1', body='[]', status=200)
    fetch_participant_upload_history(keyring, 'participant+id&value')
    body = parse_qs(responses.calls[0].request.body)
    assert body['participant_id'] == ['participant+id&value']
    assert body['access_key'] == [keyring['ACCESS_KEY']]
    assert body['secret_key'] == [keyring['SECRET_KEY']]


@pytest.mark.parametrize('body', ['not json', '', '{"incomplete":'])
@responses.activate
def test_fetch_participant_notification_history_invalid_json_raises(keyring: dict[str, str], body: str):
    responses.post(keyring['URL'] + '/get-participant-notification-history/v1', body=body, status=200)
    with pytest.raises(orjson.JSONDecodeError):
        fetch_participant_notification_history(keyring, 'PARTICIPANT_ID')


@pytest.mark.parametrize('error', [requests.exceptions.ConnectionError, requests.exceptions.Timeout])
@responses.activate
def test_fetch_participant_notification_history_request_error_propagates(keyring: dict[str, str], error):
    responses.post(keyring['URL'] + '/get-participant-notification-history/v1', body=error('request failed'))
    with pytest.raises(error, match="request failed"):
        fetch_participant_notification_history(keyring, 'PARTICIPANT_ID')


@responses.activate
def test_fetch_participant_notification_history_handles_trailing_slash(keyring: dict[str, str]):
    keyring['URL'] += '/'
    responses.post(keyring['URL'].rstrip('/') + '/get-participant-notification-history/v1', body='{}', status=200)
    result = fetch_participant_notification_history(keyring, 'PARTICIPANT_ID')
    assert result == {}


@responses.activate
def test_fetch_participant_notification_history_encodes_participant_id_and_credentials(keyring: dict[str, str]):
    keyring['ACCESS_KEY'] = 'access+key&value'
    keyring['SECRET_KEY'] = 'secret=key+value'
    responses.post(keyring['URL'] + '/get-participant-notification-history/v1', body='{}', status=200)
    fetch_participant_notification_history(keyring, 'participant+id&value')
    body = parse_qs(responses.calls[0].request.body)
    assert body['participant_id'] == ['participant+id&value']
    assert body['access_key'] == [keyring['ACCESS_KEY']]
    assert body['secret_key'] == [keyring['SECRET_KEY']]


@pytest.mark.parametrize('body', ['not json', '', '{"incomplete":'])
@responses.activate
def test_fetch_participant_device_status_history_invalid_json_raises(keyring: dict[str, str], body: str):
    responses.post(keyring['URL'] + '/get-participant-device-status-history/v1', body=body, status=200)
    with pytest.raises(orjson.JSONDecodeError):
        _fetch_participant_device_status_history(keyring, 'PARTICIPANT_ID')


@pytest.mark.parametrize('error', [requests.exceptions.ConnectionError, requests.exceptions.Timeout])
@responses.activate
def test_fetch_participant_device_status_history_request_error_propagates(keyring: dict[str, str], error):
    responses.post(keyring['URL'] + '/get-participant-device-status-history/v1', body=error('request failed'))
    with pytest.raises(error, match="request failed"):
        _fetch_participant_device_status_history(keyring, 'PARTICIPANT_ID')


@responses.activate
def test_fetch_participant_device_status_history_handles_trailing_slash(keyring: dict[str, str]):
    keyring['URL'] += '/'
    responses.post(keyring['URL'].rstrip('/') + '/get-participant-device-status-history/v1', body='[]', status=200)
    result = _fetch_participant_device_status_history(keyring, 'PARTICIPANT_ID')
    assert result == []


@responses.activate
def test_fetch_participant_device_status_history_encodes_participant_id_and_credentials(keyring: dict[str, str]):
    keyring['ACCESS_KEY'] = 'access+key&value'
    keyring['SECRET_KEY'] = 'secret=key+value'
    responses.post(keyring['URL'] + '/get-participant-device-status-history/v1', body='[]', status=200)
    _fetch_participant_device_status_history(keyring, 'participant+id&value')
    body = parse_qs(responses.calls[0].request.body)
    assert body['participant_id'] == ['participant+id&value']
    assert body['access_key'] == [keyring['ACCESS_KEY']]
    assert body['secret_key'] == [keyring['SECRET_KEY']]


@pytest.mark.parametrize('status_code', [400, 403, 500])
@responses.activate
def test_fetch_sycamore_analysis_output_http_error_raises_api_error(
    keyring: dict[str, str], status_code: int
):
    responses.post(keyring['URL'] + '/get-sycamore-analysis-output/v1', body='error', status=status_code)
    with pytest.raises(APIError, match=str(status_code)):
        fetch_sycamore_analysis_output(keyring, 'STUDY_ID')


@responses.activate
def test_fetch_sycamore_analysis_output_missing_report_raises_api_error(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-sycamore-analysis-output/v1',
        body='Unable to access report file.',
        status=404,
    )
    with pytest.raises(APIError, match="404"):
        fetch_sycamore_analysis_output(keyring, 'STUDY_ID')


@pytest.mark.parametrize('error', [requests.exceptions.ConnectionError, requests.exceptions.Timeout])
@responses.activate
def test_fetch_sycamore_analysis_output_request_error_propagates(keyring: dict[str, str], error):
    responses.post(keyring['URL'] + '/get-sycamore-analysis-output/v1', body=error('request failed'))
    with pytest.raises(error, match="request failed"):
        fetch_sycamore_analysis_output(keyring, 'STUDY_ID')


@responses.activate
def test_fetch_sycamore_analysis_output_handles_trailing_slash(keyring: dict[str, str]):
    keyring['URL'] += '/'
    responses.post(
        keyring['URL'].rstrip('/') + '/get-sycamore-analysis-output/v1',
        body='No forest tasks found for this study.',
        status=404,
    )
    with pytest.raises(APIError, match="404"):
        fetch_sycamore_analysis_output(keyring, 'STUDY_ID')


@responses.activate
def test_fetch_participant_notification_history_preserves_surveys_and_null_values(keyring: dict[str, str]):
    data = {
        'survey1': [{
            'timestamp': '2024-01-01T07:00:00-05:00',
            'type': 'absolute',
            'scheduled_time': '2024-01-01T07:00:00-05:00',
            'confirmed_received': '2024-01-01T07:00:01-05:00',
            'uuid': None,
            'resend': True,
            'push_rejected': False,
        }],
        'survey2': [],
    }
    responses.post(keyring['URL'] + '/get-participant-notification-history/v1', json=data, status=200)
    result = fetch_participant_notification_history(keyring, 'PARTICIPANT_ID')
    assert result == data


@responses.activate
def test_fetch_participant_upload_history_preserves_order_and_zero_file_size(keyring: dict[str, str]):
    data = [
        {'file_size': 0, 'timestamp': '2024-01-01T12:00:00Z', 'file_name': 'gps/1704110400.csv'},
        {'file_size': 128, 'timestamp': '2024-01-01T13:00:00Z', 'file_name': 'gps/1704114000.csv'},
    ]
    responses.post(keyring['URL'] + '/get-participant-upload-history/v1', json=data, status=200)
    result = fetch_participant_upload_history(keyring, 'PARTICIPANT_ID')
    assert result == data


@responses.activate
def test_fetch_participant_version_history_preserves_order_and_null_values(keyring: dict[str, str]):
    data = [
        {'app_version_code': None, 'app_version_name': None, 'os_version': None,
         'created_on': '2024-01-01T12:00:00Z'},
        {'app_version_code': '250', 'app_version_name': '2.5.0', 'os_version': '17.0',
         'created_on': '2024-01-02T12:00:00Z'},
    ]
    responses.post(keyring['URL'] + '/get-participant-version-history/v1', json=data, status=200)
    result = fetch_participant_version_history(keyring, 'PARTICIPANT_ID')
    assert result == data


@responses.activate
def test_fetch_participant_device_status_history_preserves_nested_data(keyring: dict[str, str]):
    data = [
        {'created_on': '2024-01-01T12:00:00Z', 'device_status': {}},
        {'created_on': '2024-01-02T12:00:00Z', 'device_status': {
            'battery_level': 0,
            'charging': False,
            'events': [{'value': None}],
        }},
    ]
    responses.post(keyring['URL'] + '/get-participant-device-status-history/v1', json=data, status=200)
    result = _fetch_participant_device_status_history(keyring, 'PARTICIPANT_ID')
    assert result == data


@pytest.mark.parametrize('filters', [
    {'start_date': '2024-01-01'},
    {'end_date': '2024-01-31'},
    {'fields': 'date,beiwe_id'},
    {'start_date': '2024-01-01', 'end_date': '2024-01-31', 'fields': 'date,beiwe_id'},
])
@responses.activate
def test_fetch_summary_statistics_sends_participant_id_with_filters(keyring: dict[str, str], filters):
    responses.post(keyring['URL'] + '/get-summary-statistics/v1', body='[]', status=200)
    fetch_summary_statistics(keyring, 'STUDY_ID', participant_id='MY_PARTICIPANT_ID', **filters)
    query = parse_qs(urlparse(responses.calls[0].request.url).query)
    assert query.get('participant_ids') == ['MY_PARTICIPANT_ID']
    for name, value in filters.items():
        assert query.get(name) == [value]


@responses.activate
def test_fetch_summary_statistics_default_omits_participant_id(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-summary-statistics/v1', body='[]', status=200)
    fetch_summary_statistics(keyring, 'STUDY_ID')
    assert 'participant_id' not in str(responses.calls[0].request.body)
    assert 'participant_id' not in responses.calls[0].request.url


@pytest.mark.parametrize('status_code', [400, 403, 404, 500])
@responses.activate
def test_fetch_summary_statistics_participant_filter_http_error_raises_api_error(
    keyring: dict[str, str], status_code: int
):
    responses.post(keyring['URL'] + '/get-summary-statistics/v1', body='error', status=status_code)
    with pytest.raises(APIError, match=str(status_code)):
        fetch_summary_statistics(keyring, 'STUDY_ID', participant_id='PARTICIPANT_ID')


@pytest.mark.parametrize('body', ['not json', '', '{"incomplete":'])
@responses.activate
def test_fetch_summary_statistics_participant_filter_invalid_json_raises(keyring: dict[str, str], body: str):
    responses.post(keyring['URL'] + '/get-summary-statistics/v1', body=body, status=200)
    with pytest.raises(orjson.JSONDecodeError):
        fetch_summary_statistics(keyring, 'STUDY_ID', participant_id='PARTICIPANT_ID')


@pytest.mark.parametrize('error', [requests.exceptions.ConnectionError, requests.exceptions.Timeout])
@responses.activate
def test_fetch_summary_statistics_participant_filter_request_error_propagates(keyring: dict[str, str], error):
    responses.post(keyring['URL'] + '/get-summary-statistics/v1', body=error('request failed'))
    with pytest.raises(error, match="request failed"):
        fetch_summary_statistics(keyring, 'STUDY_ID', participant_id='PARTICIPANT_ID')
