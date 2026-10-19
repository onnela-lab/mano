from os.path import dirname

import orjson, requests

from mano.constants import ACCESS_KEY, APIError, SECRET_KEY
from mano.file_management import make_directories
from mano.sync import normalize_url


#
## API Endpoints
#
def _json_api_post(keyring: dict[str, str], endpoint: str, params: dict[str, str] | None = None):
    url = keyring["URL"].rstrip("/") + endpoint
    url = normalize_url(url)
    payload = {"access_key": keyring[ACCESS_KEY], "secret_key": keyring[SECRET_KEY]}
    if params:
        payload.update(params)
    resp = requests.post(url, data=payload, stream=True)
    if resp.status_code != requests.codes.OK:
        raise APIError(f"response not ok ({resp.status_code}) {resp.url}")
    return orjson.loads(resp.content)


def fetch_accessible_studies(keyring: dict[str, str]) -> list[tuple[str, str]]:
    """
    Request the name and study ID of all studies that the provided keyring has access to.
    """
    return [(study_name, study_id) for study_id, study_name in _json_api_post(keyring, "/get-studies/v1").items()]


def fetch_participants_in_study(keyring: dict[str, str], study_id: str) -> list[str]:
    """
    Request a list of participant IDs within a study

    :param keyring: Keyring dictionary
    :param study_id: Study ID
    :returns: List of participant IDs
    """
    # get-users was deprecated, using get-participants
    result = _json_api_post(keyring, "/get-participant-ids/v1", {"study_id": study_id})
    if not isinstance(result, list):
        raise ValueError(f"expected a list of participant IDs, got {type(result).__name__}")
    return result


fetch_users_in_study = fetch_participants_in_study  # the old name for backward compatibility


def fetch_interventions(keyring: dict[str, str], study_id: str) -> list[tuple[str, str]]:
    """
    Get intervention data for all participants in a study.

    :param keyring: Keyring dictionary
    :param study_id: Study ID
    :returns: List of (participant_id, intervention_data)
    """
    return list(_json_api_post(keyring, "/get-interventions/v1", {"study_id": study_id}).items())


def fetch_survey_history(keyring: dict[str, str], study_id: str) -> list[tuple[str, str]]:
    """
    Get the edit history of all surveys in a study.

    :param keyring: Keyring dictionary
    :param study_id: Study ID
    :returns: List of (survey_id, survey_history_data)
    """
    result = _json_api_post(keyring, "/get-survey-history/v1", {"study_id": study_id})
    if not isinstance(result, dict):
        raise ValueError(f"expected a dict of survey history data, got {type(result).__name__}")
    return list(result.items())


def fetch_study_settings(keyring: dict[str, str], study_id: str) -> list[tuple[str, str]]:
    """
    Get the settings for a study.

    :param keyring: Keyring dictionary
    :param study_id: Study ID
    :returns: List of (key, value) — keys are surveys, device_settings, interventions
    """
    return list(_json_api_post(keyring, "/get-study-settings/v1", {"study_id": study_id}).items())


def fetch_study_device_settings(keyring: dict[str, str], study_id: str) -> list[tuple[str, str]]:
    """
    Get device settings for a Study via the API

    :param keyring: Keyring dictionary
    :param study_id: Study ID
    :returns: List of (name, setting)
    """
    return list(_json_api_post(keyring, "/get-study-settings/v1", {"study_id": study_id})["device_settings"].items())


def fetch_participant_table_data(keyring: dict[str, str], study_id: str) -> list[dict]:
    """
    Get participant table data for a study as JSON.

    :param keyring: Keyring dictionary
    :param study_id: Study ID
    :returns: List of participant row dicts
    """
    result = _json_api_post(keyring, "/get-participant-table-data/v1", {"study_id": study_id, "data_format": "json"})
    if not isinstance(result, list):
        raise ValueError(f"expected a list of participant rows, got {type(result).__name__}")
    return result


def fetch_participant_table_data_csv(keyring: dict[str, str], study_id: str, file_path: str) -> None:
    """
    Get participant table data for a study as CSV and write it to a file.

    :param keyring: Keyring dictionary
    :param study_id: Study ID
    :param file_path: Path of the file to write the CSV data to
    """
    url = keyring["URL"].rstrip("/") + "/get-participant-table-data/v1"
    payload = {
        "access_key": keyring[ACCESS_KEY],
        "secret_key": keyring[SECRET_KEY],
        "study_id": study_id,
        "data_format": "csv",
    }

    url = normalize_url(url)
    resp = requests.post(url, data=payload, stream=True)
    if resp.status_code != requests.codes.OK:
        raise APIError(f"response not ok ({resp.status_code}) {resp.url}")
    
    if directory:=dirname(file_path):
        make_directories(directory)

    with open(file_path, "wb") as fo:
        fo.write(resp.content)


def fetch_participant_version_history(keyring: dict[str, str], participant_id: str) -> list[dict]:
    """
    Get the version history for a participant.

    :param keyring: Keyring dictionary
    :param participant_id: Participant ID
    :returns: List of version history dictionaries
    """
    params = {"participant_id": participant_id}
    return list(_json_api_post(keyring, "/get-participant-version-history/v1", params))



def fetch_participant_heartbeat_history(keyring: dict[str, str], participant_id: str) -> list[dict]:
    """
    Get the heartbeat history for a participant.

    :param keyring: Keyring dictionary
    :param participant_id: Participant ID
    :returns: List of heartbeat history dictionaries
    """
    params = {"participant_id": participant_id}
    return list(_json_api_post(keyring, "/get-participant-heartbeat-history/v1", params))


def fetch_participant_upload_history(keyring: dict[str, str], participant_id: str) -> list[dict]:
    """
    Get the upload history for a participant.

    :param keyring: Keyring dictionary
    :param participant_id: Participant ID
    :returns: List of upload history dictionaries
    """
    params = {"participant_id": participant_id}
    return list(_json_api_post(keyring, "/get-participant-upload-history/v1", params))


def fetch_participant_notification_history(keyring: dict[str, str], participant_id: str) -> dict:
    """
    Get the notification history for a participant.

    :param keyring: Keyring dictionary
    :param participant_id: Participant ID
    :returns: List of notification history dictionaries
    """
    params = {"participant_id": participant_id}
    # this one isn't a list, its a dictionary
    return _json_api_post(keyring, "/get-participant-notification-history/v1", params)


def fetch_sycamore_analysis_output(keyring: dict[str, str], study_id: str) -> list[dict]:
    """
    Get the Sycamore analysis output for a study.

    :param keyring: Keyring dictionary
    :param study_id: Study ID
    :returns: List of Sycamore analysis output dictionaries
    """
    params = {"study_id": study_id}
    return list(_json_api_post(keyring, "/get-sycamore-analysis-output/v1", params))


def fetch_summary_statistics(
    keyring: dict[str, str],
    study_id: str,
    end_date: str | None = None,
    start_date: str | None = None,
    fields: str | None = None,
    participant_id: str | None = None,
) -> list[dict]:
    """
    Get summary statistics for a study.

    :param keyring: Keyring dictionary
    :param study_id: Study ID
    :param end_date: Last date to include, format YYYY-MM-DD
    :param start_date: First date to include, format YYYY-MM-DD
    :param fields: Comma-separated list of fields to return
    :returns: List of summary statistic dictionaries
    """
    params = {'study_id': study_id}
    if end_date is not None:
        params["end_date"] = end_date
    if start_date is not None:
        params["start_date"] = start_date
    if fields is not None:
        params["fields"] = fields
    if participant_id is not None:
        params["participant_id"] = participant_id
    return list(_json_api_post(keyring, "/get-summary-statistics/v1", params))


def _fetch_participant_device_status_history(keyring: dict[str, str], participant_id: str) -> list[dict]:
    """
    Get the device status history for a participant -- this api is purely a development endpoint
    and will not return any data for normal participants, and may be removed at any time.

    :param keyring: Keyring dictionary
    :param participant_id: Participant ID
    :returns: List of device status history dictionaries
    """
    params = {"participant_id": participant_id}
    return list(_json_api_post(keyring, "/get-participant-device-status-history/v1", params))
