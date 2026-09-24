from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from mano.constants import logger as log
from mano.file_management import iterate_beiwe_data_files_recursively
from mano.messages import NO_VALID_FILES_MSG
from tests.conftest import (COMPRESSED_BYTES, DECOMPRESSED_BYTES, generate_valid_compress_test_files,
    generate_valid_decompress_test_files)


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


def test_iterate_recursive_rejects_conflicting_flags():
    with pytest.raises(ValueError, match="cannot set both zst_only and include_zst set to True"):
        list(iterate_beiwe_data_files_recursively("irrelevant", zst_only=True, include_zst=True))


def test_iterate_logs_and_reraises_on_unexpected_walk_error(tmp_path: Path, mocker: MockerFixture):
    mocker.patch("mano.file_management.walk_directory", side_effect=OSError("permission denied"))
    with pytest.raises(OSError, match="permission denied"):
        list(iterate_beiwe_data_files_recursively(str(tmp_path)))
