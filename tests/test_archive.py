import logging
from pathlib import Path
from zipfile import ZipFile

import pytest
from pytest_mock import MockerFixture

from mano import file_management
from mano.constants import log, ParseError, SaveError, zstd
from mano.file_management import (decrypt_binary_data_to_bytes,
    determine_data_stream_from_internal_zip_filepath, find_duplicate_files, parse_duplicate_files,
    process_one_archive_file, save_archive)
from mano.messages import DECOMPRESS_NOT_ZST_WARNING
from tests.conftest import FILE_CONTENT_UNCOMPRESSED, PARTICIPANT_ID, PASSPHRASE_STRING


# Different files must never be reported as duplicates, or the user would be told to clean up unique data.
def test_find_duplicate_files_no_duplicates_when_files_differ(tmp_path: Path):
    folder = tmp_path / PARTICIPANT_ID / "gps"
    folder.mkdir(parents=True)
    (folder / "one.csv").write_bytes(FILE_CONTENT_UNCOMPRESSED)
    (folder / "two.csv").write_bytes(b"different content entirely")

    duplicates, hashes = find_duplicate_files(str(tmp_path), PARTICIPANT_ID)

    assert duplicates == {}
    assert hashes == {}


# Saving with no downloaded zip would silently do nothing; the user gets a clear error instead.
def test_save_archive_raises_without_zipfile():
    with pytest.raises(SaveError, match="requires you provide a ZipFile object"):
        save_archive(None, PARTICIPANT_ID, "irrelevant")


# Asking to encrypt without a passphrase must fail loudly rather than write the data unencrypted.
def test_save_archive_raises_when_lock_without_passphrase(tmp_path: Path):
    archive_path = tmp_path / "empty.zip"
    with ZipFile(archive_path, "w"):
        pass
    with ZipFile(archive_path) as archive:
        with pytest.raises(SaveError, match="Encrypting data requires a passphrase"):
            save_archive(archive, PARTICIPANT_ID, str(tmp_path), lock=["gps"])


def _write_one_member_archive(tmp_path: Path, member_name: str, content: bytes) -> Path:
    """ zip containing a single file, return  path. """
    archive_path = tmp_path / "archive.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr(member_name, content)
    return archive_path


# Decompress mode must not corrupt or drop files that were never compressed.
def test_process_one_archive_file_non_zst_member_saved_unchanged_when_decompress_requested(
    tmp_path: Path,
):
    original_bytes = b"plain data, not zstd"
    member = f"{PARTICIPANT_ID}/gps/data.csv"
    archive_path = _write_one_member_archive(tmp_path, member, original_bytes)

    with ZipFile(archive_path) as archive:
        saved = process_one_archive_file(
            member, str(tmp_path), archive, PARTICIPANT_ID, None, [], True, {},
        )

    assert saved is True
    assert (tmp_path / PARTICIPANT_ID / "gps" / "data.csv").read_bytes() == original_bytes


# The user asked for decompression, so a file that cannot be decompressed should be called out.
def test_process_one_archive_file_non_zst_member_logs_warning_when_decompress_requested(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
):
    member = f"{PARTICIPANT_ID}/gps/data.csv"
    archive_path = _write_one_member_archive(tmp_path, member, b"plain data")

    with caplog.at_level(logging.WARNING, logger=log.name), ZipFile(archive_path) as archive:
        process_one_archive_file(member, str(tmp_path), archive, PARTICIPANT_ID, None, [], True, {})

    assert DECOMPRESS_NOT_ZST_WARNING(member) in caplog.text


# Plain files are normal when not decompressing; a warning there would be noise on every save.
def test_process_one_archive_file_non_zst_member_no_warning_when_decompress_not_requested(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
):
    member = f"{PARTICIPANT_ID}/gps/data.csv"
    archive_path = _write_one_member_archive(tmp_path, member, b"plain data")

    with caplog.at_level(logging.WARNING, logger=log.name), ZipFile(archive_path) as archive:
        process_one_archive_file(member, str(tmp_path), archive, PARTICIPANT_ID, None, [], False, {})

    assert "is not a .zst file" not in caplog.text


# Guards the decompress option: users get the readable file, not a leftover .zst.
def test_process_one_archive_file_zst_member_is_decompressed_and_renamed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
):
    original_bytes = b"decompress me please"
    member = f"{PARTICIPANT_ID}/gps/data.csv.zst"
    archive_path = _write_one_member_archive(tmp_path, member, zstd.compress(original_bytes))

    with caplog.at_level(logging.WARNING, logger=log.name), ZipFile(archive_path) as archive:
        saved = process_one_archive_file(
            member, str(tmp_path), archive, PARTICIPANT_ID, None, [], True, {},
        )

    assert saved is True
    assert (tmp_path / PARTICIPANT_ID / "gps" / "data.csv").read_bytes() == original_bytes
    assert not (tmp_path / PARTICIPANT_ID / "gps" / "data.csv.zst").exists()
    assert "is not a .zst file" not in caplog.text


# Streams the user locked must land on disk encrypted and be recoverable with the passphrase.
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


# A folder entry is not a data file; it must be refused so it is never treated as a stream.
def test_determine_data_stream_from_internal_zip_filepath_rejects_folder_paths():
    with pytest.raises(ParseError, match="provide only file paths"):
        determine_data_stream_from_internal_zip_filepath(f"{PARTICIPANT_ID}/gps/", PARTICIPANT_ID)


# The registry entry is bookkeeping, not data, and must not be parsed as a data stream.
def test_determine_data_stream_from_internal_zip_filepath_rejects_registry_paths():
    with pytest.raises(ParseError, match="which is not a data stream"):
        determine_data_stream_from_internal_zip_filepath("registry", PARTICIPANT_ID)


# A zip entry for a different participant must be refused so data is never saved under the wrong person.
def test_determine_data_stream_from_internal_zip_filepath_rejects_other_participant():
    with pytest.raises(ParseError, match="does not start with the"):
        determine_data_stream_from_internal_zip_filepath("someone_else/gps/file.csv", PARTICIPANT_ID)


# A path with no stream name must raise a clear error instead of returning a wrong stream.
def test_determine_data_stream_from_internal_zip_filepath_rejects_unparsable_path():
    with pytest.raises(ParseError, match="Did not find a data type"):
        determine_data_stream_from_internal_zip_filepath(PARTICIPANT_ID, PARTICIPANT_ID)


# Covers a defensive branch that real paths cannot reach, so it still fails safely if the regex ever changes.
def test_determine_data_stream_from_internal_zip_filepath_dead_too_many_matches_branch(mocker: MockerFixture):
    fake_match = mocker.MagicMock()
    fake_match.groups.return_value = ("gps", "extra")
    mocker.patch.object(file_management.re, "search", return_value=fake_match)
    with pytest.raises(ParseError, match="expected 1 match, found 2"):
        determine_data_stream_from_internal_zip_filepath(f"{PARTICIPANT_ID}/gps/file.csv", PARTICIPANT_ID)


# A clean folder must report nothing to resolve.
def test_parse_duplicate_files_no_duplicates_returns_empty_dicts(tmp_path: Path):
    folder = tmp_path / PARTICIPANT_ID / "gps"
    folder.mkdir(parents=True)
    (folder / "one.csv").write_bytes(FILE_CONTENT_UNCOMPRESSED)

    cannot_resolve, no_conflicts = parse_duplicate_files(str(tmp_path), PARTICIPANT_ID)

    assert cannot_resolve == {}
    assert no_conflicts == {}


# Duplicates with identical content are safe to merge and must not be flagged as conflicts.
def test_parse_duplicate_files_no_conflict_when_hashes_match(mocker: MockerFixture):
    fake_duplicates = {"gps/data.csv": ["/a/data.csv", "/a/data.csv.zst"]}
    fake_hashes = {"/a/data.csv": b"samehash", "/a/data.csv.zst": b"samehash"}
    mocker.patch.object(file_management, "find_duplicate_files", return_value=(fake_duplicates, fake_hashes))

    cannot_resolve, no_conflicts = parse_duplicate_files("irrelevant/folder", PARTICIPANT_ID)

    assert cannot_resolve == {}
    assert no_conflicts == {"gps/data.csv": ["/a/data.csv", "/a/data.csv.zst"]}


# Duplicates with different content must be reported as unresolvable so no data is silently discarded.
def test_parse_duplicate_files_cannot_resolve_when_hashes_differ(mocker: MockerFixture):
    fake_duplicates = {"gps/data.csv": ["/a/data.csv", "/a/data.csv.zst"]}
    fake_hashes = {"/a/data.csv": b"hash1", "/a/data.csv.zst": b"hash2"}
    mocker.patch.object(file_management, "find_duplicate_files", return_value=(fake_duplicates, fake_hashes))

    cannot_resolve, no_conflicts = parse_duplicate_files("irrelevant/folder", PARTICIPANT_ID)

    assert no_conflicts == {}
    assert cannot_resolve == {"gps/data.csv": ["/a/data.csv", "/a/data.csv.zst"]}
