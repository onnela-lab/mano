from pathlib import Path
from zipfile import ZipFile

import pytest
import pyzstd

from mano.constants import ParseError, SaveError
from mano.file_management import (decrypt_binary_data_to_bytes,
    determine_data_stream_from_internal_zip_filepath, find_duplicate_files, process_one_archive_file,
    save_archive)
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
