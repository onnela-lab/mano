from pathlib import Path
from zipfile import ZipFile

import pytest
import pyzstd
from pytest_mock import MockerFixture

from mano import file_management
from mano.constants import ParseError, SaveError
from mano.file_management import (decrypt_binary_data_to_bytes,
    determine_data_stream_from_internal_zip_filepath, find_duplicate_files, parse_duplicate_files,
    process_one_archive_file, save_archive)
from tests.conftest import FILE_CONTENT_UNCOMPRESSED, PARTICIPANT_ID, PASSPHRASE_STRING


def test_find_duplicate_files_no_duplicates_when_files_differ(tmp_path: Path):
    folder = tmp_path / PARTICIPANT_ID / "gps"
    folder.mkdir(parents=True)
    (folder / "one.csv").write_bytes(FILE_CONTENT_UNCOMPRESSED)
    (folder / "two.csv").write_bytes(b"different content entirely")

    duplicates, hashes = find_duplicate_files(str(tmp_path), PARTICIPANT_ID)

    assert duplicates == {}
    assert hashes == {}


def test_save_archive_raises_without_zipfile():
    with pytest.raises(SaveError, match="requires you provide a ZipFile object"):
        save_archive(None, PARTICIPANT_ID, "irrelevant")


def test_save_archive_raises_when_lock_without_passphrase(tmp_path: Path):
    archive_path = tmp_path / "empty.zip"
    with ZipFile(archive_path, "w"):
        pass
    with ZipFile(archive_path) as archive:
        with pytest.raises(SaveError, match="Encrypting data requires a passphrase"):
            save_archive(archive, PARTICIPANT_ID, str(tmp_path), lock=["gps"])


def test_process_one_archive_file_decompresses_non_zst_named_member(tmp_path: Path):
    archive_path = tmp_path / "archive.zip"
    original_bytes = b"decompress me please"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr(f"{PARTICIPANT_ID}/gps/data.csv", pyzstd.compress(original_bytes))

    with ZipFile(archive_path) as archive:
        saved = process_one_archive_file(
            f"{PARTICIPANT_ID}/gps/data.csv", str(tmp_path), archive, PARTICIPANT_ID,
            None, [], True, {},
        )

    assert saved is True
    assert (tmp_path / PARTICIPANT_ID / "gps" / "data.csv").read_bytes() == original_bytes


def test_process_one_archive_file_encrypts_locked_streams(tmp_path: Path):
    archive_path = tmp_path / "archive.zip"
    original_bytes = b"secret gps data"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr(f"{PARTICIPANT_ID}/gps/data.csv", original_bytes)

    with ZipFile(archive_path) as archive:
        saved = process_one_archive_file(
            f"{PARTICIPANT_ID}/gps/data.csv", str(tmp_path), archive, PARTICIPANT_ID,
            PASSPHRASE_STRING, ["gps"], False, {},
        )

    assert saved is True
    output_path = tmp_path / PARTICIPANT_ID / "gps" / "data.csv.lock"
    assert output_path.exists()
    decrypted = decrypt_binary_data_to_bytes(output_path.read_bytes(), PASSPHRASE_STRING, str(output_path))
    assert decrypted == original_bytes


def test_determine_data_stream_from_internal_zip_filepath_rejects_folder_paths():
    with pytest.raises(ParseError, match="provide only file paths"):
        determine_data_stream_from_internal_zip_filepath(f"{PARTICIPANT_ID}/gps/", PARTICIPANT_ID)


def test_determine_data_stream_from_internal_zip_filepath_rejects_registry_paths():
    with pytest.raises(ParseError, match="which is not a data stream"):
        determine_data_stream_from_internal_zip_filepath("registry", PARTICIPANT_ID)


def test_determine_data_stream_from_internal_zip_filepath_rejects_other_participant():
    with pytest.raises(ParseError, match="does not start with the"):
        determine_data_stream_from_internal_zip_filepath("someone_else/gps/file.csv", PARTICIPANT_ID)


def test_determine_data_stream_from_internal_zip_filepath_rejects_unparsable_path():
    with pytest.raises(ParseError, match="Did not find a data type"):
        determine_data_stream_from_internal_zip_filepath(PARTICIPANT_ID, PARTICIPANT_ID)


# NOTE: the regex used in determine_data_stream_from_internal_zip_filepath has exactly one capture
# group, so `numgroups != 1` can never actually happen - the code even says "(this will never
# happen)" right above it. We force it here by stubbing re.search to return a fake match with 2
# groups, purely to exercise the dead branch; this isn't behavior that can occur for real.
def test_determine_data_stream_from_internal_zip_filepath_dead_too_many_matches_branch(mocker: MockerFixture):
    fake_match = mocker.MagicMock()
    fake_match.groups.return_value = ("gps", "extra")
    mocker.patch.object(file_management.re, "search", return_value=fake_match)
    with pytest.raises(ParseError, match="expected 1 match, found 2"):
        determine_data_stream_from_internal_zip_filepath(f"{PARTICIPANT_ID}/gps/file.csv", PARTICIPANT_ID)


# NOTE: parse_duplicate_files()/find_duplicate_files() have a pre-existing bug when actual
# duplicates are found: find_duplicate_files's `real_to_hash` filter checks `k in duplicates`
# (duplicates is keyed by *base* path), instead of checking membership in the real per-file paths
# that were found to be duplicated. This makes the returned hash lookup always empty whenever any
# duplicates exist, so calling the real find_duplicate_files() would immediately raise KeyError.
# The tests below mock find_duplicate_files with correctly-shaped return data so we can exercise
# parse_duplicate_files's own (correct) logic in isolation from that upstream bug.
def test_parse_duplicate_files_no_duplicates_returns_empty_dicts(tmp_path: Path):
    folder = tmp_path / PARTICIPANT_ID / "gps"
    folder.mkdir(parents=True)
    (folder / "one.csv").write_bytes(FILE_CONTENT_UNCOMPRESSED)

    cannot_resolve, no_conflicts = parse_duplicate_files(str(tmp_path), PARTICIPANT_ID)

    assert cannot_resolve == {}
    assert no_conflicts == {}


def test_parse_duplicate_files_no_conflict_when_hashes_match(mocker: MockerFixture):
    fake_duplicates = {"gps/data.csv": ["/a/data.csv", "/a/data.csv.zst"]}
    fake_hashes = {"/a/data.csv": b"samehash", "/a/data.csv.zst": b"samehash"}
    mocker.patch.object(file_management, "find_duplicate_files", return_value=(fake_duplicates, fake_hashes))

    cannot_resolve, no_conflicts = parse_duplicate_files("irrelevant/folder", PARTICIPANT_ID)

    assert cannot_resolve == {}
    assert no_conflicts == {"gps/data.csv": ["/a/data.csv", "/a/data.csv.zst"]}


def test_parse_duplicate_files_cannot_resolve_when_hashes_differ(mocker: MockerFixture):
    fake_duplicates = {"gps/data.csv": ["/a/data.csv", "/a/data.csv.zst"]}
    fake_hashes = {"/a/data.csv": b"hash1", "/a/data.csv.zst": b"hash2"}
    mocker.patch.object(file_management, "find_duplicate_files", return_value=(fake_duplicates, fake_hashes))

    cannot_resolve, no_conflicts = parse_duplicate_files("irrelevant/folder", PARTICIPANT_ID)

    assert no_conflicts == {}
    assert cannot_resolve == {"gps/data.csv": ["/a/data.csv", "/a/data.csv.zst"]}
