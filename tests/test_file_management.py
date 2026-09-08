from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from mano.constants import GlobalSettings, WriteError
from mano.file_management import (atomic_write, bytes_to_human_filesize, get_thread_count,
    validate_exists_at_all, validate_is_a_folder_or_valid_beiwe_data_file,
    validate_is_a_folder_or_zst_file)


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


def test_get_thread_count_uses_global_settings_override():
    original = GlobalSettings.multithreading_count
    GlobalSettings.multithreading_count = 4
    try:
        assert get_thread_count() == 4
    finally:
        GlobalSettings.multithreading_count = original


# NOTE: the two tests below exercise branches that are actually unreachable in real usage: by the
# time either function reaches its second/third `if`, the preceding `if is_a_dir or is_a_beiwe:
# return` has already ruled out every case except "neither" - so the first `exit(1)` (which we
# neutralize here by stubbing `exit`) always fires first in practice. These tests force execution
# past that point purely to exercise the dead code, they don't reflect real program behavior.
def test_validate_is_a_folder_or_valid_beiwe_data_file_dead_branches(tmp_path: Path, mocker: MockerFixture):
    mock_exit = mocker.patch("builtins.exit", MagicMock())
    bad_file = tmp_path / "notes.zzz"
    bad_file.write_text("hi")
    validate_is_a_folder_or_valid_beiwe_data_file(str(bad_file))
    assert mock_exit.call_count == 3


def test_validate_is_a_folder_or_zst_file_dead_branches(tmp_path: Path, mocker: MockerFixture):
    mock_exit = mocker.patch("builtins.exit", MagicMock())
    bad_file = tmp_path / "notes.zzz"
    bad_file.write_text("hi")
    validate_is_a_folder_or_zst_file(str(bad_file))
    assert mock_exit.call_count == 3
