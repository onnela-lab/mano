from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

import pytest
import pyzstd
from pytest_mock import MockerFixture
from pyzstd import decompress

from mano.constants import EncryptionKeyUnavailable, GlobalSettings, ParseError, SaveError, WriteError, logger as log
from mano.file_management import (atomic_write, bytes_to_human_filesize, check_hash_cache_match,
    compress_as_backend, compress_general, compress_one_zst_file, compress_to_zst_files,
    decompress_one_zst_file, decompress_zst_files, decrypt_binary_data_to_bytes,
    determine_data_stream_from_internal_zip_filepath, do_encrypted_write, find_duplicate_files,
    get_possible_real_paths, get_thread_count, iterate_beiwe_data_files_recursively,
    normalize_path_for_registry, process_one_archive_file, save_archive, validate_exists_at_all,
    validate_is_a_folder_or_valid_beiwe_data_file, validate_is_a_folder_or_zst_file)
from mano.messages import NO_VALID_FILES_MSG
from tests.conftest import (COMPRESSED_BYTES, DATA_STREAM_FILE, DATA_STREAM_FILE_ISO,
    DECOMPRESSED_BYTES, FILE_CONTENT_UNCOMPRESSED, PARTICIPANT_ID, PASSPHRASE_STRING, STUDY_ID,
    generate_compressed_zst_files, generate_uncompressed_zst_files,
    generate_valid_compress_test_files, generate_valid_decompress_test_files)


def test_compress_as_backend():
    original_bytes = b'This is some test data to be compressed using the backend compression settings.' * 10
    compressed_bytes = compress_as_backend(original_bytes)
    assert decompress(compressed_bytes) == original_bytes
    assert len(compressed_bytes) < len(original_bytes)


def test_compress_general():
    original_bytes = b'This is some test data to be compressed using the general compression settings.' * 10
    compressed_bytes = compress_general(original_bytes, level=19)  # take it slow
    assert decompress(compressed_bytes) == original_bytes
    assert len(compressed_bytes) < len(original_bytes)


def test_compress_one_zst_file_defaults(tmp_path: Path):
    uncompressed_path, compressed_path, original_bytes = generate_uncompressed_zst_files(tmp_path)
    compress_one_zst_file(str(uncompressed_path))
    assert compressed_path.exists()
    assert uncompressed_path.exists()
    assert original_bytes == decompress(compressed_bytes := compressed_path.read_bytes())
    assert len(compressed_bytes) < len(original_bytes)


def test_compress_one_zst_file_overwrite_fail(tmp_path: Path):
    uncompressed_path, compressed_path, _original_bytes = generate_uncompressed_zst_files(tmp_path)
    compressed_path.write_bytes(b"super secret data")
    compress_one_zst_file(str(uncompressed_path), overwrite=False)
    assert compressed_path.read_bytes() == b"super secret data"


def test_compress_one_zst_file_overwrite_success(tmp_path: Path):
    uncompressed_path, compressed_path, original_bytes = generate_uncompressed_zst_files(tmp_path)
    compressed_path.write_bytes(b"super secret data")
    compress_one_zst_file(str(uncompressed_path), overwrite=True)
    assert original_bytes == decompress(compressed_path.read_bytes())


def test_compress_one_zst_file_delete_original(tmp_path: Path):
    uncompressed_path, compressed_path, original_bytes = generate_uncompressed_zst_files(tmp_path)
    compress_one_zst_file(str(uncompressed_path), delete_original=True)
    assert not uncompressed_path.exists()
    assert compressed_path.exists()
    assert original_bytes == decompress(compressed_path.read_bytes())


def test_compress_one_zst_file_custom_level(tmp_path: Path):
    uncompressed_path, compressed_path, original_bytes = generate_uncompressed_zst_files(tmp_path)
    compress_one_zst_file(str(uncompressed_path), compression_level=19)  # take it slow
    assert compressed_path.exists()
    assert uncompressed_path.exists()
    assert original_bytes == decompress(compressed_bytes := compressed_path.read_bytes())
    assert len(compressed_bytes) < len(original_bytes)


def test_decompress_one_zst_file_defaults(tmp_path: Path):
    uncompressed_path, compressed_path, original_bytes = generate_compressed_zst_files(tmp_path)
    decompress_one_zst_file(str(compressed_path))
    assert uncompressed_path.exists()
    assert compressed_path.exists()
    assert original_bytes == uncompressed_path.read_bytes()


def test_decompress_one_zst_file_overwrite_fail(tmp_path: Path):
    uncompressed_path, compressed_path, _original_bytes = generate_compressed_zst_files(tmp_path)
    uncompressed_path.write_bytes(b"super secret data")
    decompress_one_zst_file(str(compressed_path), overwrite=False)
    assert uncompressed_path.read_bytes() == b"super secret data"


def test_decompress_one_zst_file_overwrite_success(tmp_path: Path):
    uncompressed_path, compressed_path, original_bytes = generate_compressed_zst_files(tmp_path)
    uncompressed_path.write_bytes(b"super secret data")
    decompress_one_zst_file(str(compressed_path), overwrite=True)
    assert original_bytes == uncompressed_path.read_bytes()


def test_decompress_one_zst_file_delete_zst(tmp_path: Path):
    uncompressed_path, compressed_path, original_bytes = generate_compressed_zst_files(tmp_path)
    decompress_one_zst_file(str(compressed_path), delete_zsts=True)
    assert not compressed_path.exists()
    assert uncompressed_path.exists()
    assert original_bytes == uncompressed_path.read_bytes()


def test_iterate_valid_data_files(tmp_path: Path):
    valid_files = ["data1.csv", "audio.wav"]
    invalid_files = ["document.txt", "image.jpg", "archive.zip", "script.py"]

    for filename in valid_files + invalid_files:
        (tmp_path / filename).write_text("test content")

    found_files = set[str]()
    for file_path in iterate_beiwe_data_files_recursively(str(tmp_path)):
        found_files.add(Path(file_path).name)

    assert found_files == set(valid_files)


def test_iterate_no_such_folder():
    with pytest.raises(FileNotFoundError, match="No such directory: `this/path/does/not/exist`"):
        for fp in iterate_beiwe_data_files_recursively("this/path/does/not/exist"):
            log.error(f"Unexpected file found while running test 1: {fp}")

    with pytest.raises(FileNotFoundError, match="No such directory: `this/path/does/not/exist`"):
        for fp in iterate_beiwe_data_files_recursively("this/path/does/not/exist", zst_only=True):
            log.error(f"Unexpected file found while running test 2: {fp}")


def test_empty_folder(tmp_path: Path):
    restricted_dir = tmp_path / "restricted"
    restricted_dir.mkdir()

    base_path_str = str(tmp_path)
    rgx_compat_path = base_path_str.replace("\\", "\\\\")

    with pytest.raises(FileNotFoundError, match=NO_VALID_FILES_MSG(rgx_compat_path, False)):
        for fp in iterate_beiwe_data_files_recursively(str(tmp_path)):
            log.error(f"TEST: Unexpected file found while running test 3: {fp}")

    with pytest.raises(FileNotFoundError, match=NO_VALID_FILES_MSG(rgx_compat_path, True)):
        for fp in iterate_beiwe_data_files_recursively(str(tmp_path), zst_only=True):
            log.error(f"TEST: Unexpected file found while running test 4: {fp}")


def test_iterate_recursive(tmp_path: Path):
    valid_files, _invalid_files, _bytes = generate_valid_compress_test_files(tmp_path)
    found_files = {*iterate_beiwe_data_files_recursively(str(tmp_path))}
    expected_valid_filenames = {str(f) for f in valid_files}
    assert found_files == expected_valid_filenames


def test_iterate_recursive_zst_only(tmp_path: Path):
    zst_files, _non_zst_files, _uncompressed_bytes = generate_valid_decompress_test_files(tmp_path)
    found_files = {*iterate_beiwe_data_files_recursively(str(tmp_path), zst_only=True)}
    expected_zst_filenames = {str(f) for f in zst_files}
    assert found_files == expected_zst_filenames


def test_iterate_lock_files(tmp_path: Path):
    lock_files = [
        tmp_path / "data2.csv.lock",
        tmp_path / "subdir2" / "audio2.wav.lock",
        tmp_path / "data2.csv.zst.lock",
        tmp_path / "subdir2" / "audio2.wav.zst.lock",
    ]
    (tmp_path / "subdir2").mkdir()

    for filepath in lock_files:
        if ".zst" in filepath.name:
            filepath.write_bytes(COMPRESSED_BYTES)
        else:
            filepath.write_bytes(DECOMPRESSED_BYTES)

    zst_only_true = {*iterate_beiwe_data_files_recursively(str(tmp_path), zst_only=True)}
    assert zst_only_true == {str(f) for f in lock_files if ".zst" in str(f)}
    zst_only_false = {*iterate_beiwe_data_files_recursively(str(tmp_path), zst_only=False)}
    assert zst_only_false == {str(f) for f in lock_files if ".zst" not in str(f)}
    both = {*iterate_beiwe_data_files_recursively(str(tmp_path), include_zst=True)}
    assert both == {str(f) for f in lock_files}


def test_full_decompress_decompresses(tmp_path: Path):
    zst_files, non_zst_files, uncompressed_bytes = generate_valid_decompress_test_files(tmp_path)
    decompress_zst_files(str(tmp_path), delete_zsts=False, overwrite=False)
    common_full_decompress(tmp_path, uncompressed_bytes, zst_files, non_zst_files)


def common_full_decompress(
    tmp_path: Path, uncompressed_bytes: bytes, zst_files: list[Path], non_zst_files: list[Path]
):
    correct_uncompressed_file_paths = {str(path).rsplit(".zst")[0] for path in zst_files}

    for path in non_zst_files:
        if path.suffix in [".csv", ".wav"]:
            correct_uncompressed_file_paths.add(str(path))

    new_valid_file_paths = set[str]()
    for file in iterate_beiwe_data_files_recursively(str(tmp_path), zst_only=False):
        path = Path(file)
        new_valid_file_paths.add(str(path))
        assert path.exists()
        assert path.suffix != ".zst"
        assert path.read_bytes() == uncompressed_bytes

    assert set(new_valid_file_paths) == correct_uncompressed_file_paths


def test_full_compress_multithread_works(tmp_path: Path):
    compressable_files, _uncompressable_files, original_bytes = generate_valid_compress_test_files(tmp_path)
    compress_to_zst_files(str(tmp_path), delete_original=False, overwrite=False)
    common_full_compress(tmp_path, original_bytes, compressable_files)


def common_full_compress(tmp_path: Path, original_bytes: bytes, compressable_files: list[Path]):
    correct_compressed_file_paths = {str(path)+".zst" for path in compressable_files}

    new_valid_file_paths = set[str]()
    for fp in iterate_beiwe_data_files_recursively(str(tmp_path), zst_only=True):
        path = Path(fp)
        new_valid_file_paths.add(str(path))
        assert path.suffix == ".zst"
        assert path.exists()
        assert decompress(path.read_bytes()) == original_bytes

    assert new_valid_file_paths == correct_compressed_file_paths


def test_full_decompress_delete_zst_deletes_zsts(tmp_path: Path):
    zst_files, non_zst_files, _ = generate_valid_decompress_test_files(tmp_path)
    decompress_zst_files(str(tmp_path), delete_zsts=True, overwrite=False)
    for path in zst_files:
        assert not path.exists()
    for path in non_zst_files:
        assert path.exists()


def test_full_compress_delete_original_deletes_originals(tmp_path: Path):
    compressable_files, uncompressable_files, _ = generate_valid_compress_test_files(tmp_path)
    compress_to_zst_files(str(tmp_path), delete_original=True, overwrite=False)
    for path in compressable_files:
        assert not path.exists()
    for path in uncompressable_files:
        assert path.exists()


def test_full_compress_overwrites(tmp_path: Path):
    compressable_files, _uncompressable_files, decompressed_data = generate_valid_compress_test_files(tmp_path)
    for path in compressable_files:
        (path.parent / (path.name + ".zst")).write_bytes(b"super secret data")

    compress_to_zst_files(str(tmp_path), delete_original=False, overwrite=True)
    for path in compressable_files:
        compressed_path = path.parent / (path.name + ".zst")
        assert compressed_path.exists()
        assert decompress(compressed_path.read_bytes()) == decompressed_data


def test_full_decompress_overwrites(tmp_path: Path):
    zst_files, _non_zst_files, decompressed_data = generate_valid_decompress_test_files(tmp_path)
    for path in zst_files:
        Path(str(path).rsplit(".zst")[0]).write_bytes(b"super secret data")

    decompress_zst_files(str(tmp_path), delete_zsts=False, overwrite=True)
    for path in zst_files:
        uncompressed_path = path.parent / path.name.rsplit(".zst")[0]
        assert uncompressed_path.exists()
        assert uncompressed_path.read_bytes() == decompressed_data


def test_full_compress_raises_an_error_during_real_execution_1_thread(tmp_path: Path, mocker: MockerFixture):
    _compressable_files, _uncompressable_files, _ = generate_valid_compress_test_files(tmp_path)
    mocker.patch("mano.file_management.compress_one_zst_file", side_effect=Exception("Simulated compression error"))
    with pytest.raises(Exception, match="Simulated compression error"):
        compress_to_zst_files(str(tmp_path), delete_original=False, overwrite=False)


def test_full_decompress_raises_an_error_during_real_execution_1_thread(tmp_path: Path, mocker: MockerFixture):
    _zst_files, _non_zst_files, _ = generate_valid_decompress_test_files(tmp_path)
    mocker.patch("mano.file_management.decompress_one_zst_file", side_effect=Exception("Simulated decompression error"))
    with pytest.raises(Exception, match="Simulated decompression error"):
        decompress_zst_files(str(tmp_path), delete_zsts=False, overwrite=False)


def test_find_duplicate_files_no_duplicates_when_files_differ(tmp_path: Path):
    folder = tmp_path / PARTICIPANT_ID / "gps"
    folder.mkdir(parents=True)
    (folder / "one.csv").write_bytes(FILE_CONTENT_UNCOMPRESSED)
    (folder / "two.csv").write_bytes(b"different content entirely")

    duplicates, hashes = find_duplicate_files(str(tmp_path), PARTICIPANT_ID)

    assert duplicates == {}
    assert hashes == {}


def test_get_possible_real_paths():
    bare, zst, lock, lock_zst = get_possible_real_paths("folder/file.csv")
    assert bare == "folder/file.csv"
    assert zst == "folder/file.csv.zst"
    assert lock == "folder/file.csv.lock"
    assert lock_zst == "folder/file.csv.zst.lock"


def test_atomic_write_raises_when_overwrite_false_and_file_exists(tmp_path: Path):
    target = tmp_path / "existing.txt"
    target.write_bytes(b"original")
    with pytest.raises(WriteError, match="file already exists"):
        atomic_write(str(target), b"new content", overwrite=False)
    assert target.read_bytes() == b"original"


def test_bytes_to_human_filesize_converts_larger_sizes():
    assert bytes_to_human_filesize(b"x" * 500) == "500B"
    assert bytes_to_human_filesize(b"x" * 2048) == "2.00KB"


def test_validate_exists_at_all_raises_when_missing():
    with pytest.raises(SystemExit):
        validate_exists_at_all("this/path/does/not/exist")


def test_validate_is_a_folder_or_valid_beiwe_data_file_raises_for_invalid_file(tmp_path: Path):
    bad_file = tmp_path / "notes.txt"
    bad_file.write_text("hi")
    with pytest.raises(SystemExit):
        validate_is_a_folder_or_valid_beiwe_data_file(str(bad_file))


def test_validate_is_a_folder_or_zst_file_raises_for_non_zst_file(tmp_path: Path):
    bad_file = tmp_path / "notes.txt"
    bad_file.write_text("hi")
    with pytest.raises(SystemExit):
        validate_is_a_folder_or_zst_file(str(bad_file))


def test_iterate_recursive_rejects_conflicting_flags():
    with pytest.raises(ValueError, match="cannot set both zst_only and include_zst set to True"):
        list(iterate_beiwe_data_files_recursively("irrelevant", zst_only=True, include_zst=True))


def test_decompress_zst_files_single_file_mode(tmp_path: Path):
    uncompressed_path, compressed_path, original_bytes = generate_compressed_zst_files(tmp_path)
    decompress_zst_files(str(compressed_path))
    assert uncompressed_path.read_bytes() == original_bytes


def test_compress_to_zst_files_single_file_mode(tmp_path: Path):
    uncompressed_path, compressed_path, original_bytes = generate_uncompressed_zst_files(tmp_path)
    compress_to_zst_files(str(uncompressed_path))
    assert decompress(compressed_path.read_bytes()) == original_bytes


def test_decrypt_binary_data_to_bytes_raises_without_passphrase():
    with pytest.raises(EncryptionKeyUnavailable):
        decrypt_binary_data_to_bytes(b"irrelevant", None, "some/path.lock")


def test_do_encrypted_write_raises_without_passphrase():
    with pytest.raises(EncryptionKeyUnavailable):
        do_encrypted_write(b"irrelevant", "some/path.csv", None)


def test_do_encrypted_write_writes_encrypted_file(tmp_path: Path):
    filename = str(tmp_path / "output.csv")
    do_encrypted_write(FILE_CONTENT_UNCOMPRESSED, filename, PASSPHRASE_STRING)
    encrypted_bytes = Path(filename).read_bytes()
    assert decrypt_binary_data_to_bytes(encrypted_bytes, PASSPHRASE_STRING, filename) == FILE_CONTENT_UNCOMPRESSED


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


def test_get_thread_count_uses_global_settings_override():
    original = GlobalSettings.multithreading_count
    GlobalSettings.multithreading_count = 4
    try:
        assert get_thread_count() == 4
    finally:
        GlobalSettings.multithreading_count = original


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
