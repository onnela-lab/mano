from datetime import date, datetime
from typing import Any

from mano.constants import (APIError, BASE_24HR_TIME_FORMAT, BEIWE_EXTENSIONS_ORED, log,
    UnParsableTimeError)


"""
Some user messages get too fiddly to format inline with the code, and make it hard to read.
Place that code here.
"""

#
# helpers
#


def full_dt_format(dt: datetime) -> str:
    # if the time zone is not a _name_, just an offset, %Z will be empty, then we use %z.
    tz_str = dt.strftime("%Z")
    if not tz_str:
        tz_str = dt.strftime("%z")
    dt_str = dt.strftime(BASE_24HR_TIME_FORMAT)
    if tz_str:
        return f"{dt_str} ({tz_str})"
    return dt_str


#
# Mostly these are formatting functions used for log statements and error messages.
#


# Error functions that always raise an exception should log and return an exception.

def X_IS_NOT_A_Y_ERROR(x: str, T: type | str, the_object: Any, source_name: str) -> TypeError:
    """ This one raises a TypeError and logs to the error log. """
    
    if isinstance(T, type):  # T for type or title...
        T = T.__name__
    
    found_type = type(the_object)
    msg = f"The `{x}` parameter passed to {source_name} must be a `{T}`, encountered `{found_type}`."
    
    log.error(msg)
    return TypeError(msg)


def BACKFILL_UNPARSABLE_DATE_ERROR(start_date: str | datetime | date) -> ValueError:
    msg = f'Backfill received the value "{start_date}" for `start_date`, which it could not parse.'
    log.error(msg)
    return ValueError(msg)


def BACKFILL_LOCK_AND_PASSPHRASE_ERROR(parameter_a: str, parameter_b: str) -> ValueError:
    msg = f"Backfill's `{parameter_a}` parameter cannot be empty if `{parameter_b}` is provided."
    log.error(msg)
    return ValueError(msg)


def NOT_200_OK_ERROR(status_code: int, url: str) -> APIError:
    msg = f"Did not receive HTTP 200 OK. Received status code: `{status_code}` - {url}"
    log.error(msg)
    return APIError(msg)


def TIME_REQUIRED_ERROR(prefix: str) -> ValueError:
    msg = f"{prefix} - a required date-time parameter was not provided."
    log.error(msg)
    return ValueError(msg)


def COULD_NOT_PARSE_TIME_ERROR(prefix: str, dt: datetime | str | None) -> ValueError:
    msg = f"{prefix} - could not parse time string `{dt}`"
    log.error(msg)
    return UnParsableTimeError(msg)


# General string formatting functions

def NO_VALID_FILES_MSG(directory_path: str, zst_only: bool):
    if zst_only:
        return f"No `.zst` files found in directory `{directory_path}` or its subdirectories."
    
    return f"No files with {BEIWE_EXTENSIONS_ORED} found in directory " \
            f"`{directory_path}` or its subdirectories."


def NO_TIME_MSG(prefix: str):
    return f"{prefix} - no datetime was provided, filter will not be applied."


def TIME_PARSED_MSG(prefix: str, time_str: str, dt: datetime):
    dt_str = full_dt_format(dt)
    return f"{prefix} - parsed time string `{time_str}` as `{dt_str}`"


def TIME_NAIVE_MSG(prefix: str):
    return f"{prefix} - Mano received a timezone-naive datetime, proceeding assuming UTC"


def TIME_NOT_UTC_MSG(prefix: str, dt: datetime, ending: str):
    dt_str = full_dt_format(dt)
    return f"{prefix} - The Beiwe platform expects times to be in the UTC timezone `{dt_str}` {ending}"


def TIME_IS_TOO_EARLY_MSG(prefix: str, dt: datetime):
    dt_str = full_dt_format(dt)
    return f"{prefix} - The provided datetime `{dt_str}` is before the earliest possible " \
            "time for any Beiwe data."


def TIME_IS_TOO_LATE_MSG(prefix: str, dt: datetime):
    dt_str = full_dt_format(dt)
    return f"{prefix} - The provided datetime `{dt_str}` is too far in the future. " \
            "This input can only send junk queries to the Beiwe Data Access API."

# SPECIFIC formatting functions


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


def INVALID_DATA_STREAMS_MSG(invalid_streams: list[str], prefix: str):
    return f'{prefix} - invalid data streams: {", ".join(invalid_streams)}'


def BACKFILL_START_DATE_FUTURE_MSG(start_date: datetime):
    return f'Backfill received the value "{start_date}" for `start_date`, which is in the future.'


def BACKFILL_FILE_EXISTS_MSG(file_path: str):
    return f'A backfill timestamp file already exists at `{file_path}`, it will be overwritten.'


def BACKFILL_RESTARTING_WARNING(participant_id: str):
    return f"The backfill tracking file for participant `{participant_id}` indicates a prior " \
        "backfill operation did not complete. Backfill will resume from the last recorded timestamp."


def CANNOT_HASH_MSG(path: str):
    return f"Mano encountered an encrypted file ({path}) " \
           "but cannot produce a hash because no decryption key was provided."


def CANNOT_ENCRYPT_MSG(path: str):
    return f"Mano encountered a request to encrypt a file ({path}) " \
           "but cannot do so because no passphrase was provided."


TOO_MANY_MULTITHREAD_ARGS = \
    "Multiple multithreading parameters (strting with `--mt`) were provided, please provide only one."


def BAD_MULTITHREADING_ERROR(arg: str) -> str:
    return f"An invalid multithreading parameter `{arg}` was provided. " \
            "Please provide a value like `--mt4` or `--mt10`."

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

DOWNLOAD_COMMA_IN_PARTICIPANTS_WARNING = \
    "`participant_ids` was provided as a comma-separated string. This usage has been deprecated."

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
