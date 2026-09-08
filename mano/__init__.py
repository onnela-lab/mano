# allow for direct imports of the entities in the mano file to retain compatability

# We have to bend over backwards to both preserve some of the imports that have historically existed
# in this codebase (so can't be abandoned), and fix one that is broken in the current structure.
# `from mano import sync` would fail even after `import mano`. An explicit `import mano.sync` here
# was required to resolve this.
import mano.sync as sync
from mano import constants, mano_cli
from mano.beiwe_api import (fetch_accessible_studies, fetch_interventions,
    fetch_participant_table_data, fetch_participant_table_data_csv, fetch_study_device_settings,
    fetch_study_settings, fetch_summary_statistics, fetch_survey_history, fetch_users_in_study)
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
    "fetch_study_device_settings",
    "fetch_study_settings",
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


# README import audit — every `from mano...` / `import mano` line shown in README.md examples was
# checked against this file and the modules it re-exports from; all of them resolve to a real name:
#   from mano import ...                fetch_accessible_studies, fetch_study_device_settings,
#                                        fetch_summary_statistics, fetch_users_in_study, load_keyring,
#                                        sync                              (see __all__ above)
#   from mano.constants import ...      DataStreams, ALL_DATA_STREAMS, GlobalSettings
#   from mano.beiwe_api import ...      fetch_interventions, fetch_participant_table_data,
#                                        fetch_participant_table_data_csv, fetch_study_settings,
#                                        fetch_survey_history
#   from mano.sync import ...           backfill, download, save
#   from mano.file_management import .. compress_to_zst_files, decompress_zst_files, GlobalSettings
#                                        (re-exported here because file_management.py itself imports
#                                        it from mano.constants)
# None of the README examples currently import a name that doesn't exist.
