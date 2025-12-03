# Some user messages get too fiddly to format inline with the code, and make it hard to read.
# Place that code here.

from datetime import datetime

from mano.constants import FULL_DT_FORMAT


# helpers22
def full_dt_format(dt: datetime) -> str:
    return dt.strftime(FULL_DT_FORMAT)


# formatting functions

def NO_TIME_MSG(name: str):
    return f"{name} - no time was provided, filter will not be applied."


def TIME_PARSED_MSG(name: str, time_str: str, dt: datetime):
    return f"{name} - parsed time string `{time_str}` as `{full_dt_format(dt)}`"


def TIME_NAIVE_MSG(name: str):
    return f"{name} - Mano received a timezone-naive datetime, proceeding assuming UTC"


def TIME_NOT_UTC_MSG(name: str, dt: datetime, ending: str):
    dt_str = full_dt_format(dt)
    return f"{name} - The Beiwe platform expects times to be in the UTC timezone `{dt_str}` {ending}"


def NOT_200_OK_MSG(status_code: int, url: str):
    return f"Did not receive HTTP 200 OK. Received status code: `{status_code}` - {url}"


# Deprecation warnings


PROGRESS_DEPRECATION_MSG = \
    "The `progress` parameter is deprecated and will be removed in a future release, use `debug_level` instead"

USER_IDS_DEPRECATION_MSG = \
    "`user_ids` is a deprecated alias of `participant_ids` and will be removed in a future " \
    "release, use `participant_ids` instead."

PICK_USER_PARTICIPANT_MSG = \
    "`user_ids` is a deprecated alias of `participant_ids`, you cannot provide both."

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
