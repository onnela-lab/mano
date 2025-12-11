# Some user messages get too fiddly to format inline with the code, and make it hard to read.
# Place that code here.

from datetime import datetime
from typing import Any

from mano.constants import FULL_DT_FORMAT


# helpers22
def full_dt_format(dt: datetime) -> str:
    return dt.strftime(FULL_DT_FORMAT)


#
# GENERIC formatting functions
#


def X_IS_NOT_A_Y_MSG(x: str, y: type | str, the_object: Any, source_name: str):
    if isinstance(y, type):
        y = y.__name__
    found = type(the_object)
    return f"The `{x}` parameter passed to {source_name} must be a `{y}`, encountered `{found}`."


def NO_TIME_MSG(prefix: str):
    return f"{prefix} - no datetime was provided, filter will not be applied."


def TIME_REQUIRED_MSG(prefix: str):
    return f"{prefix} - a required date and time parameter was not provided."


def TIME_PARSED_MSG(prefix: str, time_str: str, dt: datetime):
    return f"{prefix} - parsed time string `{time_str}` as `{full_dt_format(dt)}`"


def COULD_NOT_PARSE_TIME_MSG(prefix: str, dt: datetime | str | None):
    return f"{prefix} - could not parse time string `{dt}`"


def TIME_NAIVE_MSG(prefix: str):
    return f"{prefix} - Mano received a timezone-naive datetime, proceeding assuming UTC"


def TIME_NOT_UTC_MSG(prefix: str, dt: datetime, ending: str):
    dt_str = full_dt_format(dt)
    return f"{prefix} - The Beiwe platform expects times to be in the UTC timezone `{dt_str}` {ending}"


# SPECIFIC formatting functions


def NOT_200_OK_MSG(status_code: int, url: str):
    return f"Did not receive HTTP 200 OK. Received status code: `{status_code}` - {url}"


def PARSE_ERROR_NO_MATCH_MSG(expr: str, path: str):
    return f'Did not find a data type in zip archive file path: regex="{expr}", string="{path}"'


def PARSE_ERROR_TOO_MANY_MATCHES_MSG(regexpr: str, file_path: str, numgroups: int):
    return "Unexpectedly found the too many matches for the data type in a zip file path. " \
            f'(expected 1 match, found {numgroups}, regex="{regexpr}", string="{file_path})"'


def DATA_STREAM_FOLDER_MSG(funcname: str, folder_path: str):
    return f"{funcname} received a folder path: `{folder_path}`, provide only file paths."


def DATA_STREAM_REGISTRY_MSG(funcname: str, registry_path: str):
    return f"{funcname} received a registry file path: `{registry_path}`, which is not a data stream."


def DATA_STREAM_NOT_PARTICIPANT_MSG(funcname: str, file_path: str, participant_id: str):
    return f"{funcname} received the file path, `{file_path}`, which does not start with the " \
           f"specified participant id, `{participant_id}`. These paths are expected to start." \
           f"with the participant id."


def BACKFILL_START_DATE_FUTURE_MSG(start_date: datetime):
    return f'Backfill received the value "{start_date}" for `start_date`, which is in the future.'


def BACKFILL_UNPARSABLE_DATE_MSG(start_date: str | datetime):
    return f'Backfill received the value "{start_date}" for `start_date`, which it could not parse.'


def BACKFILL_FILE_EXISTS_MSG(file_path: str):
    return f'A backfill timestamp file already exists at `{file_path}`, it will be overwritten.'


def BACKFILL_RESTARTING_WARNING(participant_id: str):
    return f"The backfill tracking file for participant `{participant_id}` indicates a prior " \
        "backfill operation did not complete. Backfill will resume from the last recorded timestamp."


#
# Deprecation warnings
#


PROGRESS_DEPRECATION_MSG = \
    "The `progress` parameter is deprecated and will be removed in a future release, use `debug_level` instead"

USER_ID_KEYWORD_DEPRECATION_MSG = \
    "You provided `user_id` as a keyword argument. `user_id` is a deprecated alias of " \
    "`participant_id`, and will be removed in a future release. Use `participant_id` instead."

USER_IDS_DEPRECATION_MSG = \
    "`user_ids` is a deprecated alias of `participant_ids` and will be removed in a future " \
    "release, use `participant_ids` instead."

PICK_USER_PARTICIPANT_PLURAL_MSG = \
    "`user_ids` is a deprecated alias of `participant_ids`, you cannot provide both."

PICK_USER_PARTICIPANT_SINGLE_MSG = \
    "`user_id` is a deprecated alias of `participant_id`, you cannot provide both."

SYNC_SAVE_DEPRECATION_MSG = \
    "[mano.sync].save() is a deprecated alias of [mano.file_management].save_encrypted() and " \
    "will be removed in a future release, use mano.file_management.save_encrypted"


# TODO: finish documenting all the error codes for the data access API

"""
~Error Code Guide~

400 codes mean something about the request was malformed.
404 codes mean something provided could not be found.

404 codes include:
- The provided study ID does not exist.
- A provided participant ID was not found.
- A provided data stream was not valid.

400 codes:
- The user identified in by the API credentials is not authorized on the the study ID that was provided.
- A credential value provided was invalid (as in they are malformed, not just incorrect).
- A credential value was missing entirely.
- A study ID is malformed.
- The study ID was not provided.

403:
- the study id provided was not found
- the study id provided was not one the user is authorized on

"""
