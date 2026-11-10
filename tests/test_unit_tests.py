import re
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
def test_fetch_participants_in_study_empty_list_returns_nothing(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-participant-ids/v1', body='[]', status=200)
    assert fetch_participants_in_study(keyring, 'STUDY_ID') == []


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


# This is a parametrized test: pytest runs it once for each case listed in the decorator below,
# passing that case's values in as the test function's arguments.
# Checks that interval() converts a "<number><unit>" string into seconds.
# This test runs once per row. Each row is: (interval string, expected seconds)
@pytest.mark.parametrize(
    ("value", "seconds"),
    [
        # one of each unit: s = seconds, m = minutes, h = hours, d = days
        ("10s", 10),
        ("5m", 300),
        ("2h", 7200),
        ("1d", 86400),
        # zero is valid for every unit
        ("0s", 0),
        ("0m", 0),
        ("0h", 0),
        ("0H", 0),              # uppercase unit (see test_interval_uppercase_all_units for the rest)
        ("0d", 0),
        ("000000000000m", 0),   # leading zeros are allowed
    ],
)
def test_interval(value: str, seconds: int):
    assert interval(value) == seconds


# This is a parametrized test: pytest runs it once for each case listed in the decorator below,
# passing that case's values in as the test function's arguments.
# Checks that a malformed interval string raises IntervalError, and that the error message
# quotes the bad value back to the user. This test runs once per value in the list.
@pytest.mark.parametrize(
    "value",
    [
        "y",      # unknown unit, no number
        "10x",    # number with an unknown unit
        "abc",    # not an interval at all
        "",       # empty string
    ],
)
def test_interval_invalid_raises_error_with_value_in_message(value: str):
    with pytest.raises(IntervalError, match=re.escape(f"invalid interval '{value}'")):
        interval(value)


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
def test_fetch_study_settings_empty_returns_nothing(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-study-settings/v1', body='{}', status=200)
    assert fetch_study_settings(keyring, 'STUDY_ID') == []


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
def test_fetch_participant_table_data_csv_empty_response_writes_empty_file(keyring: dict[str, str], tmp_path: Path):
    responses.post(keyring['URL'] + '/get-participant-table-data/v1', body='', status=200)
    file_path = tmp_path / "participants.csv"
    fetch_participant_table_data_csv(keyring, 'STUDY_ID', str(file_path))
    assert file_path.read_bytes() == b''


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


# The summary-statistics endpoint splits its parameters: the credentials and study_id go in the
# POST body, and every filter goes in the URL query string. The server ignores filters in the body.
# Source: beiwe-backend libs/endpoint_helpers/summary_statistic_helpers.py (ApiQueryForm on request.GET).


@responses.activate
def test_fetch_summary_statistics_sends_study_id_in_body(
    keyring: dict[str, str], mock_summary_statistics_response: str
):
    responses.post(keyring['URL'] + '/get-summary-statistics/v1', body=mock_summary_statistics_response, status=200)
    list(fetch_summary_statistics(keyring, 'MY_STUDY_ID'))
    assert 'study_id=MY_STUDY_ID' in str(responses.calls[0].request.body)
    assert 'study_id' not in responses.calls[0].request.url


@responses.activate
def test_fetch_summary_statistics_sends_filters_in_query_string_not_body(
    keyring: dict[str, str], mock_summary_statistics_response: str
):
    responses.post(keyring['URL'] + '/get-summary-statistics/v1', body=mock_summary_statistics_response, status=200)
    fetch_summary_statistics(keyring, 'STUDY_ID', start_date='2024-01-01', end_date='2024-01-31', fields='beiwe_id')
    query = parse_qs(urlparse(responses.calls[0].request.url).query)
    assert query == {'start_date': ['2024-01-01'], 'end_date': ['2024-01-31'], 'fields': ['beiwe_id']}
    # the old bug: filters sent in the POST body, where the server never reads them
    body = str(responses.calls[0].request.body)
    assert 'start_date' not in body
    assert 'end_date' not in body
    assert 'fields' not in body


@responses.activate
def test_fetch_summary_statistics_omits_none_params(keyring: dict[str, str], mock_summary_statistics_response: str):
    responses.post(keyring['URL'] + '/get-summary-statistics/v1', body=mock_summary_statistics_response, status=200)
    list(fetch_summary_statistics(keyring, 'STUDY_ID'))
    # no filters given, so nothing in the query string and only credentials + study_id in the body
    assert urlparse(responses.calls[0].request.url).query == ''
    body = parse_qs(responses.calls[0].request.body)
    assert set(body) == {'access_key', 'secret_key', 'study_id'}


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


#
# participant history fetchers
#
# These five functions all work the same way: they POST `participant_id` plus the keyring's
# credentials to their own endpoint, and return the parsed JSON response. So every test in this
# section runs once for each function, using the table below.
#
# Each row is: (fetch function, endpoint path, empty response body, what that empty body parses to)
# Notification history returns a dict of surveys; the other four return a list.
PARTICIPANT_HISTORY_FETCHERS = [
    pytest.param(
        fetch_participant_version_history, '/get-participant-version-history/v1', '[]', [],
        id='version_history',
    ),
    pytest.param(
        fetch_participant_heartbeat_history, '/get-participant-heartbeat-history/v1', '[]', [],
        id='heartbeat_history',
    ),
    pytest.param(
        fetch_participant_upload_history, '/get-participant-upload-history/v1', '[]', [],
        id='upload_history',
    ),
    pytest.param(
        fetch_participant_notification_history, '/get-participant-notification-history/v1', '{}', {},
        id='notification_history',
    ),
    pytest.param(
        _fetch_participant_device_status_history, '/get-participant-device-status-history/v1', '[]', [],
        id='device_status_history',
    ),
]
PARTICIPANT_HISTORY_COLUMNS = ("fetch", "endpoint", "empty_body", "empty_result")


# This is a parametrized test: pytest runs it once for each case listed in the decorator below,
# passing that case's values in as the test function's arguments.
# Checks that each fetcher returns the server's JSON unchanged, including tricky values (nulls,
# zeros, nested objects, empty lists) and list order. Each row is:
#   (fetch function, endpoint path, JSON data the mock server sends back)
@pytest.mark.parametrize(
    ("fetch", "endpoint", "data"),
    [
        # version history: one normal entry
        pytest.param(
            fetch_participant_version_history, '/get-participant-version-history/v1',
            [{'app_version_code': '250', 'app_version_name': '2.5.0', 'os_version': '17.0',
              'created_on': '2024-01-01T12:00:00Z'}],
            id='version_history',
        ),
        # version history: null fields are kept, and entries keep their order
        pytest.param(
            fetch_participant_version_history, '/get-participant-version-history/v1',
            [{'app_version_code': None, 'app_version_name': None, 'os_version': None,
              'created_on': '2024-01-01T12:00:00Z'},
             {'app_version_code': '250', 'app_version_name': '2.5.0', 'os_version': '17.0',
              'created_on': '2024-01-02T12:00:00Z'}],
            id='version_history_nulls_and_order',
        ),
        # heartbeat history: two timestamps
        pytest.param(
            fetch_participant_heartbeat_history, '/get-participant-heartbeat-history/v1',
            [{'timestamp': '2024-01-01T12:00:00Z'}, {'timestamp': '2024-01-01T13:00:00Z'}],
            id='heartbeat_history',
        ),
        # upload history: one normal entry
        pytest.param(
            fetch_participant_upload_history, '/get-participant-upload-history/v1',
            [{'file_size': 128, 'timestamp': '2024-01-01T12:00:00Z', 'file_name': 'gps/1704110400.csv'}],
            id='upload_history',
        ),
        # upload history: a file size of 0 is kept, and entries keep their order
        pytest.param(
            fetch_participant_upload_history, '/get-participant-upload-history/v1',
            [{'file_size': 0, 'timestamp': '2024-01-01T12:00:00Z', 'file_name': 'gps/1704110400.csv'},
             {'file_size': 128, 'timestamp': '2024-01-01T13:00:00Z', 'file_name': 'gps/1704114000.csv'}],
            id='upload_history_zero_size_and_order',
        ),
        # notification history: one survey with one notification
        pytest.param(
            fetch_participant_notification_history, '/get-participant-notification-history/v1',
            {'survey1': [{'timestamp': '2024-01-01T12:00:00Z', 'type': 'absolute',
                          'scheduled_time': '2024-01-01T12:00:00Z', 'confirmed_received': False,
                          'uuid': 'notification1', 'resend': False, 'push_rejected': False}]},
            id='notification_history',
        ),
        # notification history: null uuid, timezone offsets, and a survey with no notifications
        pytest.param(
            fetch_participant_notification_history, '/get-participant-notification-history/v1',
            {'survey1': [{'timestamp': '2024-01-01T07:00:00-05:00', 'type': 'absolute',
                          'scheduled_time': '2024-01-01T07:00:00-05:00',
                          'confirmed_received': '2024-01-01T07:00:01-05:00',
                          'uuid': None, 'resend': True, 'push_rejected': False}],
             'survey2': []},
            id='notification_history_nulls_and_empty_survey',
        ),
        # device status history: one normal entry
        pytest.param(
            _fetch_participant_device_status_history, '/get-participant-device-status-history/v1',
            [{'created_on': '2024-01-01T12:00:00Z', 'endpoint': 'upload', 'app_os': 'ios',
              'os_version': '17.0', 'app_version': '2.5.0', 'device_status': {'battery_level': 0.8}}],
            id='device_status_history',
        ),
        # device status history: empty and deeply nested device_status objects are kept
        pytest.param(
            _fetch_participant_device_status_history, '/get-participant-device-status-history/v1',
            [{'created_on': '2024-01-01T12:00:00Z', 'device_status': {}},
             {'created_on': '2024-01-02T12:00:00Z',
              'device_status': {'battery_level': 0, 'charging': False, 'events': [{'value': None}]}}],
            id='device_status_history_nested_data',
        ),
    ],
)
@responses.activate
def test_fetch_participant_history_returns_data(keyring: dict[str, str], fetch, endpoint: str, data):
    responses.post(keyring['URL'] + endpoint, json=data, status=200)
    assert fetch(keyring, 'PARTICIPANT_ID') == data


# This is a parametrized test: pytest runs it once for each case listed in the decorator below,
# passing that case's values in as the test function's arguments.
# Checks that an empty response comes back as an empty list (or empty dict for notification
# history). Rows come from PARTICIPANT_HISTORY_FETCHERS above.
@pytest.mark.parametrize(PARTICIPANT_HISTORY_COLUMNS, PARTICIPANT_HISTORY_FETCHERS)
@responses.activate
def test_fetch_participant_history_empty_returns_nothing(
    keyring: dict[str, str], fetch, endpoint: str, empty_body: str, empty_result
):
    responses.post(keyring['URL'] + endpoint, body=empty_body, status=200)
    assert fetch(keyring, 'PARTICIPANT_ID') == empty_result


# This is a parametrized test: pytest runs it once for each case listed in the decorator below,
# passing that case's values in as the test function's arguments.
# Checks that the participant ID and both credentials are sent in the POST body.
# Rows come from PARTICIPANT_HISTORY_FETCHERS above.
@pytest.mark.parametrize(PARTICIPANT_HISTORY_COLUMNS, PARTICIPANT_HISTORY_FETCHERS)
@responses.activate
def test_fetch_participant_history_sends_participant_id_and_credentials(
    keyring: dict[str, str], fetch, endpoint: str, empty_body: str, empty_result
):
    responses.post(keyring['URL'] + endpoint, body=empty_body, status=200)
    fetch(keyring, 'MY_PARTICIPANT_ID')
    body = str(responses.calls[0].request.body)
    assert 'participant_id=MY_PARTICIPANT_ID' in body
    assert f"access_key={keyring['ACCESS_KEY']}" in body
    assert f"secret_key={keyring['SECRET_KEY']}" in body


# This is a parametrized test: pytest runs it once for each case listed in the decorator below,
# passing that case's values in as the test function's arguments.
# Checks that values containing URL-special characters (+, &, =) are encoded properly, so the
# server decodes exactly the values we sent. Rows come from PARTICIPANT_HISTORY_FETCHERS above.
@pytest.mark.parametrize(PARTICIPANT_HISTORY_COLUMNS, PARTICIPANT_HISTORY_FETCHERS)
@responses.activate
def test_fetch_participant_history_encodes_participant_id_and_credentials(
    keyring: dict[str, str], fetch, endpoint: str, empty_body: str, empty_result
):
    keyring['ACCESS_KEY'] = 'access+key&value'
    keyring['SECRET_KEY'] = 'secret=key+value'
    responses.post(keyring['URL'] + endpoint, body=empty_body, status=200)
    fetch(keyring, 'participant+id&value')
    body = parse_qs(responses.calls[0].request.body)
    assert body['participant_id'] == ['participant+id&value']
    assert body['access_key'] == [keyring['ACCESS_KEY']]
    assert body['secret_key'] == [keyring['SECRET_KEY']]


# This is a parametrized test: pytest runs it once for each case listed in the decorator below,
# passing that case's values in as the test function's arguments.
# Checks that a keyring URL ending in "/" doesn't produce a double slash in the endpoint URL.
# The mock is registered without the double slash, so a wrong URL fails with a ConnectionError.
# Rows come from PARTICIPANT_HISTORY_FETCHERS above.
@pytest.mark.parametrize(PARTICIPANT_HISTORY_COLUMNS, PARTICIPANT_HISTORY_FETCHERS)
@responses.activate
def test_fetch_participant_history_handles_trailing_slash(
    keyring: dict[str, str], fetch, endpoint: str, empty_body: str, empty_result
):
    responses.post(keyring['URL'] + endpoint, body=empty_body, status=200)
    keyring['URL'] += '/'
    assert fetch(keyring, 'PARTICIPANT_ID') == empty_result


# This is a parametrized test: pytest runs it once for each case listed in the decorators below,
# passing that case's values in as the test function's arguments. With two decorators, it runs
# once for every combination: each fetcher (PARTICIPANT_HISTORY_FETCHERS) x each status code.
# Checks that any non-200 response raises APIError naming the status code.
@pytest.mark.parametrize("status_code", [400, 403, 404, 500])
@pytest.mark.parametrize(PARTICIPANT_HISTORY_COLUMNS, PARTICIPANT_HISTORY_FETCHERS)
@responses.activate
def test_fetch_participant_history_http_error_raises_api_error(
    keyring: dict[str, str], fetch, endpoint: str, empty_body: str, empty_result, status_code: int
):
    responses.post(keyring['URL'] + endpoint, body='error', status=status_code)
    with pytest.raises(APIError, match=str(status_code)):
        fetch(keyring, 'PARTICIPANT_ID')


# This is a parametrized test: pytest runs it once for each case listed in the decorators below,
# passing that case's values in as the test function's arguments. With two decorators, it runs
# once for every combination: each fetcher (PARTICIPANT_HISTORY_FETCHERS) x each bad body.
# Checks that a 200 response whose body isn't valid JSON raises orjson.JSONDecodeError.
@pytest.mark.parametrize(
    "bad_body",
    [
        "not json",         # plain text
        "",                 # empty body
        '{"incomplete":',   # JSON cut off part way through
    ],
)
@pytest.mark.parametrize(PARTICIPANT_HISTORY_COLUMNS, PARTICIPANT_HISTORY_FETCHERS)
@responses.activate
def test_fetch_participant_history_invalid_json_raises(
    keyring: dict[str, str], fetch, endpoint: str, empty_body: str, empty_result, bad_body: str
):
    responses.post(keyring['URL'] + endpoint, body=bad_body, status=200)
    with pytest.raises(orjson.JSONDecodeError):
        fetch(keyring, 'PARTICIPANT_ID')


# This is a parametrized test: pytest runs it once for each case listed in the decorators below,
# passing that case's values in as the test function's arguments. With two decorators, it runs
# once for every combination: each fetcher (PARTICIPANT_HISTORY_FETCHERS) x each network error.
# Checks that network errors are not caught or retried: they reach the caller unchanged.
@pytest.mark.parametrize("error", [requests.exceptions.ConnectionError, requests.exceptions.Timeout])
@pytest.mark.parametrize(PARTICIPANT_HISTORY_COLUMNS, PARTICIPANT_HISTORY_FETCHERS)
@responses.activate
def test_fetch_participant_history_request_error_propagates(
    keyring: dict[str, str], fetch, endpoint: str, empty_body: str, empty_result, error
):
    responses.post(keyring['URL'] + endpoint, body=error('request failed'))
    with pytest.raises(error, match="request failed"):
        fetch(keyring, 'PARTICIPANT_ID')


#
# fetch_sycamore_analysis_output tests
#
# Unlike the other fetchers, this endpoint returns a zip file (raw bytes), not JSON.
# Source: beiwe-backend libs/utils/forest_utils.py, forest_task_runtime_output_file_handler.
#

SYCAMORE_ENDPOINT = '/get-sycamore-analysis-output/v1'


def _mock_sycamore_zip_response(url: str, zip_bytes: bytes) -> None:
    """ Mock a successful sycamore response the way the backend sends it: zip bytes as an attachment. """
    responses.post(
        url + SYCAMORE_ENDPOINT,
        body=zip_bytes,
        status=200,
        content_type='zip',
        headers={'Content-Disposition': 'attachment; filename=report.zip'},
    )


@responses.activate
def test_fetch_sycamore_analysis_output_returns_zip(keyring: dict[str, str], mock_zip_data_uncompressed: bytes):
    # mock_zip_data_uncompressed is the real zip file tests/data/download.v1.zip
    _mock_sycamore_zip_response(keyring['URL'], mock_zip_data_uncompressed)
    result = fetch_sycamore_analysis_output(keyring, 'STUDY_ID')
    # the bytes come back untouched, and still open as the same zip file
    assert result == mock_zip_data_uncompressed
    with ZipFile(BytesIO(result)) as returned, ZipFile(BytesIO(mock_zip_data_uncompressed)) as original:
        assert returned.namelist() == original.namelist()


@responses.activate
def test_fetch_sycamore_analysis_output_sends_study_id_and_credentials(
    keyring: dict[str, str], mock_zip_data_uncompressed: bytes
):
    _mock_sycamore_zip_response(keyring['URL'], mock_zip_data_uncompressed)
    fetch_sycamore_analysis_output(keyring, 'MY_STUDY_ID')
    body = str(responses.calls[0].request.body)
    assert 'study_id=MY_STUDY_ID' in body
    assert f"access_key={keyring['ACCESS_KEY']}" in body
    assert f"secret_key={keyring['SECRET_KEY']}" in body


@responses.activate
def test_fetch_sycamore_analysis_output_handles_trailing_slash(
    keyring: dict[str, str], mock_zip_data_uncompressed: bytes
):
    # the mock is registered without a double slash, so a wrong URL fails with a ConnectionError
    _mock_sycamore_zip_response(keyring['URL'], mock_zip_data_uncompressed)
    keyring['URL'] += '/'
    assert fetch_sycamore_analysis_output(keyring, 'STUDY_ID') == mock_zip_data_uncompressed


# This is a parametrized test: pytest runs it once for each case listed in the decorator below,
# passing that case's values in as the test function's arguments.
# Checks that any non-200 response raises APIError naming the status code. The two 404 rows use
# the exact messages the backend sends. Each row is: (HTTP status code, response body)
@pytest.mark.parametrize(
    ("status_code", "body"),
    [
        (400, 'error'),
        (403, 'error'),
        (500, 'error'),
        (404, 'No forest tasks found for this study.'),   # study has never run a forest task
        (404, 'Unable to access report file.'),           # task exists but its output file is missing
    ],
    ids=["400", "403", "500", "404_no_forest_tasks", "404_missing_report_file"],
)
@responses.activate
def test_fetch_sycamore_analysis_output_http_error_raises_api_error(
    keyring: dict[str, str], status_code: int, body: str
):
    responses.post(keyring['URL'] + SYCAMORE_ENDPOINT, body=body, status=status_code)
    with pytest.raises(APIError, match=str(status_code)):
        fetch_sycamore_analysis_output(keyring, 'STUDY_ID')


# This is a parametrized test: pytest runs it once for each case listed in the decorator below,
# passing that case's values in as the test function's arguments.
# Checks that network errors are not caught or retried: they reach the caller unchanged.
@pytest.mark.parametrize("error", [requests.exceptions.ConnectionError, requests.exceptions.Timeout])
@responses.activate
def test_fetch_sycamore_analysis_output_request_error_propagates(keyring: dict[str, str], error):
    responses.post(keyring['URL'] + SYCAMORE_ENDPOINT, body=error('request failed'))
    with pytest.raises(error, match="request failed"):
        fetch_sycamore_analysis_output(keyring, 'STUDY_ID')


#
# fetch_summary_statistics participant filter tests
#
# The backend reads summary-statistics filters from the URL query string, and the participant
# filter is named `participant_ids` (plural, comma-separated). Credentials stay in the POST body.
# Source: beiwe-backend libs/endpoint_helpers/summary_statistic_helpers.py (ApiQueryForm on request.GET).
#


@responses.activate
def test_fetch_summary_statistics_sends_participant_id(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-summary-statistics/v1', body='[]', status=200)
    fetch_summary_statistics(keyring, 'STUDY_ID', participant_id='MY_PARTICIPANT_ID')
    query = parse_qs(urlparse(responses.calls[0].request.url).query)
    assert query.get('participant_ids') == ['MY_PARTICIPANT_ID']
    # the old bug: a singular `participant_id` sent in the POST body, which the server ignores
    assert 'participant_id' not in str(responses.calls[0].request.body)


@responses.activate
def test_fetch_summary_statistics_omits_none_participant_id(keyring: dict[str, str]):
    responses.post(keyring['URL'] + '/get-summary-statistics/v1', body='[]', status=200)
    fetch_summary_statistics(keyring, 'STUDY_ID', participant_id=None)
    assert 'participant_id' not in str(responses.calls[0].request.body)
    assert 'participant_id' not in responses.calls[0].request.url
    assert 'participant_ids' not in str(responses.calls[0].request.body)


# This is a parametrized test: pytest runs it once for each case listed in the decorator below,
# passing that case's values in as the test function's arguments.
# Checks that the participant filter and the other filters are all sent together in the URL
# query string. Each value is the extra filter keyword arguments passed to fetch_summary_statistics.
@pytest.mark.parametrize(
    "filters",
    [
        {'start_date': '2024-01-01'},                                                       # start only
        {'end_date': '2024-01-31'},                                                         # end only
        {'fields': 'date,beiwe_id'},                                                        # fields only
        {'start_date': '2024-01-01', 'end_date': '2024-01-31', 'fields': 'date,beiwe_id'},  # all three
    ],
)
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


# This is a parametrized test: pytest runs it once for each case listed in the decorator below,
# passing that case's values in as the test function's arguments.
# Checks that a non-200 response raises APIError naming the status code when filtering by participant.
@pytest.mark.parametrize("status_code", [400, 403, 404, 500])
@responses.activate
def test_fetch_summary_statistics_participant_filter_http_error_raises_api_error(
    keyring: dict[str, str], status_code: int
):
    responses.post(keyring['URL'] + '/get-summary-statistics/v1', body='error', status=status_code)
    with pytest.raises(APIError, match=str(status_code)):
        fetch_summary_statistics(keyring, 'STUDY_ID', participant_id='PARTICIPANT_ID')


# This is a parametrized test: pytest runs it once for each case listed in the decorator below,
# passing that case's values in as the test function's arguments.
# Checks that a 200 response whose body isn't valid JSON raises orjson.JSONDecodeError.
@pytest.mark.parametrize(
    "body",
    [
        "not json",         # plain text
        "",                 # empty body
        '{"incomplete":',   # JSON cut off part way through
    ],
)
@responses.activate
def test_fetch_summary_statistics_participant_filter_invalid_json_raises(keyring: dict[str, str], body: str):
    responses.post(keyring['URL'] + '/get-summary-statistics/v1', body=body, status=200)
    with pytest.raises(orjson.JSONDecodeError):
        fetch_summary_statistics(keyring, 'STUDY_ID', participant_id='PARTICIPANT_ID')


# This is a parametrized test: pytest runs it once for each case listed in the decorator below,
# passing that case's values in as the test function's arguments.
# Checks that network errors are not caught or retried: they reach the caller unchanged.
@pytest.mark.parametrize("error", [requests.exceptions.ConnectionError, requests.exceptions.Timeout])
@responses.activate
def test_fetch_summary_statistics_participant_filter_request_error_propagates(keyring: dict[str, str], error):
    responses.post(keyring['URL'] + '/get-summary-statistics/v1', body=error('request failed'))
    with pytest.raises(error, match="request failed"):
        fetch_summary_statistics(keyring, 'STUDY_ID', participant_id='PARTICIPANT_ID')
