# allow for direct imports of the entities in the mano file to retain compatability

from mano.mano import (
    AmbiguousStudyIDError,
    APIError,
    KeyringError,
    IntervalError,
    LoginError,
    ScrapeError,
    StudyIDError,
    StudyNameError,
    StudySettingsError,
    DATA_STREAMS,
    TIME_FORMAT,
    interval,
    studies,
    keyring,
    keyring_from_env,
    expand_study_id,
    login,
    device_settings,
    users,
    studyid,
    studyname,
)

# We have to bend over backwards to both preserve some of the imports that have historically existed
# in this codebase (so can't be abandoned), and fix one that is broken in the current structure.
# `from mano import sync` would fail even after `import mano`. An explicit `import mano.sync` here
# is required to resolve this.
import mano.sync as sync


__all__ = [
    "AmbiguousStudyIDError",
    "APIError",
    "KeyringError",
    "IntervalError",
    "LoginError",
    "ScrapeError",
    "StudyIDError",
    "StudyNameError",
    "StudySettingsError",
    "DATA_STREAMS",
    "TIME_FORMAT",
    "interval",
    "studies",
    "keyring",
    "keyring_from_env",
    "expand_study_id",
    "login",
    "device_settings",
    "users",
    "studyid",
    "studyname",
    "sync",
]
