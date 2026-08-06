# allow for direct imports of the entities in the mano file to retain compatability

# We have to bend over backwards to both preserve some of the imports that have historically existed
# in this codebase (so can't be abandoned), and fix one that is broken in the current structure.
# `from mano import sync` would fail even after `import mano`. An explicit `import mano.sync` here
# was required to resolve this.
import mano.sync as sync
from mano import constants, mano_cli
from mano.beiwe_api import (fetch_accessible_studies, fetch_interventions,
    fetch_participant_table_data, fetch_participant_table_data_csv, fetch_study_settings,
    fetch_study_settings_test, fetch_summary_statistics, fetch_survey_history, fetch_users_in_study)
from mano.mano import (AmbiguousStudyIDError, APIError, Config, DATA_STREAMS, device_settings,
    expand_study_id, interval, IntervalError, Keyring, keyring_from_env, KeyringError, load_keyring,
    LOCALE, login, LoginError, ScrapeError, studies, studyid, StudyIDError, studyname,
    StudyNameError, StudySettingsError, TIME_FORMAT, users)


__all__ = [
    "AmbiguousStudyIDError",
    "APIError",
    "constants",
    "DATA_STREAMS",
    "expand_study_id",
    "interval",
    "IntervalError",
    "keyring_from_env",
    "KeyringError",
    "load_keyring",
    "login",
    "LoginError",
    "mano_cli",
    "ScrapeError",
    "studyid",
    "StudyIDError",
    "studyname",
    "StudyNameError",
    "StudySettingsError",
    "sync",
    "TIME_FORMAT",

    "fetch_accessible_studies",
    "fetch_interventions",
    "fetch_participant_table_data",
    "fetch_participant_table_data_csv",
    "fetch_study_settings",
    "fetch_study_settings_test",
    "fetch_summary_statistics",
    "fetch_survey_history",
    "fetch_users_in_study",

    "studies",
    "users",
    "Keyring",
    "device_settings",
    "Config",
    "LOCALE",
]
