from datetime import datetime

from mano.file_management import check_hash_cache_match, get_possible_real_paths, normalize_path_for_registry
from tests.conftest import DATA_STREAM_FILE, DATA_STREAM_FILE_ISO, PARTICIPANT_ID, STUDY_ID


def test_normalize_path_for_registry_survey_timings_returns_three_variants():
    path = f"survey_timings/{DATA_STREAM_FILE}"
    paths = normalize_path_for_registry(path, STUDY_ID, PARTICIPANT_ID)
    assert paths == [
        f"{STUDY_ID}/{PARTICIPANT_ID}/survey_timings/{DATA_STREAM_FILE_ISO}",
        f"{STUDY_ID}/{PARTICIPANT_ID}/survey_timings/{DATA_STREAM_FILE_ISO}",
        f"{STUDY_ID}/{PARTICIPANT_ID}/surveyTimings/{DATA_STREAM_FILE_ISO}",
    ]


def test_normalize_path_for_registry_audio_recordings_uses_special_case():
    path = f"audio_recordings/{DATA_STREAM_FILE}"
    paths = normalize_path_for_registry(path, STUDY_ID, PARTICIPANT_ID)
    t = datetime.fromisoformat(f"{DATA_STREAM_FILE_ISO.removesuffix('.csv')}Z").timestamp()
    assert paths == [
        f"{STUDY_ID}/{PARTICIPANT_ID}/voiceRecording/{int(t * 1000)}.csv",
        f"{STUDY_ID}/{PARTICIPANT_ID}/voiceRecording/{int(t)}.csv",
    ]


def test_check_hash_cache_match_returns_false_when_not_in_cache():
    real_path = f"{STUDY_ID}/{PARTICIPANT_ID}/gps/file.csv"
    assert check_hash_cache_match(real_path, PARTICIPANT_ID, b"data", {}, False) is False


def test_get_possible_real_paths():
    bare, zst, lock, lock_zst = get_possible_real_paths("folder/file.csv")
    assert bare == "folder/file.csv"
    assert zst == "folder/file.csv.zst"
    assert lock == "folder/file.csv.lock"
    assert lock_zst == "folder/file.csv.zst.lock"
