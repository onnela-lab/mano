import json
import os

import requests

from mano.constants import ACCESS_KEY, SECRET_KEY, APIError
from mano.file_management import make_directories


#
## API Endpoints
#
def _api_post(keyring: dict[str, str], endpoint: str, params: dict[str, str] | None = None):
    url = keyring["URL"].rstrip("/") + endpoint
    payload = {"access_key": keyring[ACCESS_KEY], "secret_key": keyring[SECRET_KEY]}
    if params:
        payload.update(params)
    resp = requests.post(url, data=payload, stream=True)
    if resp.status_code != requests.codes.OK:
        raise APIError(f"response not ok ({resp.status_code}) {resp.url}")
    return json.loads(resp.content)


def fetch_accessible_studies(keyring: dict[str, str]) -> list[tuple[str, str]]:
    """
    Request the name and study ID of all studies that the provided keyring has access to.
    """
    return [(study_name, study_id) for study_id, study_name in _api_post(keyring, "/get-studies/v1").items()]


def fetch_users_in_study(keyring: dict[str, str], study_id: str) -> list[str]:
    """
    Request a list of users within a study

    :param keyring: Keyring dictionary
    :param study_id: Study ID
    :returns: List of participant IDs
    """
    # get-users was deprecated, using get-participants
    result = _api_post(keyring, "/get-participants/v1", {"study_id": study_id})
    if not isinstance(result, list):
        raise ValueError(f"expected a list of participant IDs, got {type(result).__name__}")
    return result


def fetch_interventions(keyring: dict[str, str], study_id: str) -> list[tuple[str, str]]:
    """
    Get intervention data for all participants in a study.

    :param keyring: Keyring dictionary
    :param study_id: Study ID
    :returns: List of (participant_id, intervention_data)
    """
    return list(_api_post(keyring, "/get-interventions/v1", {"study_id": study_id}).items())


def fetch_survey_history(keyring: dict[str, str], study_id: str) -> list[tuple[str, str]]:
    """
    Get the edit history of all surveys in a study.

    :param keyring: Keyring dictionary
    :param study_id: Study ID
    :returns: List of (survey_id, survey_history_data)
    """
    result = _api_post(keyring, "/get-survey-history/v1", {"study_id": study_id})
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
    return list(_api_post(keyring, "/get-study-settings/v1", {"study_id": study_id}).items())


def fetch_study_settings_test(keyring: dict[str, str], study_id: str) -> list[tuple[str, str]]:
    """
    Get device settings for a Study via the API

    :param keyring: Keyring dictionary
    :param study_id: Study ID
    :returns: List of (name, setting)
    """
    return list(_api_post(keyring, "/get-study-settings/v1", {"study_id": study_id})["device_settings"].items())


def fetch_participant_table_data(keyring: dict[str, str], study_id: str) -> list[dict]:
    """
    Get participant table data for a study as JSON.

    :param keyring: Keyring dictionary
    :param study_id: Study ID
    :returns: List of participant row dicts
    """
    result = _api_post(keyring, "/get-participant-table-data/v1", {"study_id": study_id, "data_format": "json"})
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

    resp = requests.post(url, data=payload, stream=True)
    if resp.status_code != requests.codes.OK:
        raise APIError(f"response not ok ({resp.status_code}) {resp.url}")

    directory = os.path.dirname(file_path)
    if directory:
        make_directories(directory)

    with open(file_path, "wb") as fo:
        fo.write(resp.content)


def fetch_summary_statistics(
    keyring: dict[str, str],
    study_id: str,
    end_date: str | None = None,
    start_date: str | None = None,
    fields: str | None = None,
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
    return list(_api_post(keyring, "/get-summary-statistics/v1", params))
