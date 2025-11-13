# allow for direct imports of the entities in the mano file to retain compatability

from mano.mano import (
    AmbiguousStudyIDError,
    APIError,
    DATA_STREAMS,
    device_settings,
    expand_study_id,
    interval,
    IntervalError,
    keyring_from_env,
    keyring,
    KeyringError,
    login,
    LoginError,
    ScrapeError,
    studies,
    studyid,
    StudyIDError,
    studyname,
    StudyNameError,
    StudySettingsError,
    TIME_FORMAT,
    users,
)

from mano import constants

# We have to bend over backwards to both preserve some of the imports that have historically existed
# in this codebase (so can't be abandoned), and fix one that is broken in the current structure.
# `from mano import sync` would fail even after `import mano`. An explicit `import mano.sync` here
# was required to resolve this.
import mano.sync as sync


__all__ = [
    "AmbiguousStudyIDError",
    "APIError",
    "constants",
    "DATA_STREAMS",
    "device_settings",
    "expand_study_id",
    "interval",
    "IntervalError",
    "keyring_from_env",
    "keyring",
    "KeyringError",
    "login",
    "LoginError",
    "ScrapeError",
    "studies",
    "studyid",
    "StudyIDError",
    "studyname",
    "StudyNameError",
    "StudySettingsError",
    "sync",
    "TIME_FORMAT",
    "users",
]
