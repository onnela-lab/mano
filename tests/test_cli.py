import importlib
import os
import runpy
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from mano import mano_cli
from mano.constants import GlobalSettings, InternalError
from tests.conftest import generate_compressed_zst_files, generate_uncompressed_zst_files


def _run_main(monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture, argv: list[str]):
    """ Keep sys.argv and mano_cli's `command_line_args` alias pointed at the same list. """
    monkeypatch.setattr(sys, "argv", argv)
    mocker.patch.object(mano_cli, "command_line_args", argv)
    mano_cli.main()


def _setup_mock_compress(mocker: MockerFixture, tmp_path: Path) -> MagicMock:
    _, _, _ = generate_uncompressed_zst_files(tmp_path)
    mock_input = mocker.patch("mano.mano_cli.input")
    mock_input.return_value = "y"
    return mocker.patch("mano.mano_cli.compress_to_zst_files")


def _setup_mock_decompress(mocker: MockerFixture, tmp_path: Path) -> MagicMock:
    _, _, _ = generate_compressed_zst_files(tmp_path)
    mock_input = mocker.patch("mano.mano_cli.input")
    mock_input.return_value = "y"
    return mocker.patch("mano.mano_cli.decompress_zst_files")


def test_mano_cli_compress_all(tmp_path: Path, mocker: MockerFixture):
    mock_compress_to_zst_files = _setup_mock_compress(mocker, tmp_path)
    mano_cli.compress([str(tmp_path), "--delete-original", "--overwrite"])
    mock_compress_to_zst_files.assert_called_once_with(
        str(tmp_path), delete_original=True, overwrite=True, compression_level=2
    )


def test_mano_cli_compress_no_delete_no_overwrite(tmp_path: Path, mocker: MockerFixture):
    mock_compress_to_zst_files = _setup_mock_compress(mocker, tmp_path)
    mano_cli.compress([str(tmp_path)])
    mock_compress_to_zst_files.assert_called_once_with(
        str(tmp_path), delete_original=False, compression_level=2, overwrite=False
    )


def test_mano_cli_compress_only_delete(tmp_path: Path, mocker: MockerFixture):
    mock_compress_to_zst_files = _setup_mock_compress(mocker, tmp_path)
    mano_cli.compress([str(tmp_path), "--delete-original"])
    mock_compress_to_zst_files.assert_called_once_with(
        str(tmp_path), delete_original=True, overwrite=False, compression_level=2
    )


def test_mano_cli_compress_only_overwrite(tmp_path: Path, mocker: MockerFixture):
    mock_compress_to_zst_files = _setup_mock_compress(mocker, tmp_path)
    mano_cli.compress([str(tmp_path), "--overwrite"])
    mock_compress_to_zst_files.assert_called_once_with(
        str(tmp_path), delete_original=False, overwrite=True, compression_level=2
    )


def test_compress_with_custom_level(tmp_path: Path, mocker: MockerFixture):
    mock_compress_to_zst_files = _setup_mock_compress(mocker, tmp_path)
    mano_cli.compress([str(tmp_path), "-19"])
    mock_compress_to_zst_files.assert_called_once_with(
        str(tmp_path), delete_original=False, overwrite=False, compression_level=19
    )


def test_mano_cli_decompress_all(tmp_path: Path, mocker: MockerFixture):
    mock_decompress_zst_files = _setup_mock_decompress(mocker, tmp_path)
    mano_cli.decompress([str(tmp_path), "--delete-zst", "--overwrite"])
    mock_decompress_zst_files.assert_called_once_with(
        str(tmp_path), delete_zsts=True, overwrite=True
    )


def test_mano_cli_decompress_no_delete_no_overwrite(tmp_path: Path, mocker: MockerFixture):
    mock_decompress_zst_files = _setup_mock_decompress(mocker, tmp_path)
    mano_cli.decompress([
        str(tmp_path),
    ])
    mock_decompress_zst_files.assert_called_once_with(
        str(tmp_path), delete_zsts=False, overwrite=False
    )


def test_mano_cli_decompress_only_delete(tmp_path: Path, mocker: MockerFixture):
    mock_decompress_zst_files = _setup_mock_decompress(mocker, tmp_path)
    mano_cli.decompress([str(tmp_path), "--delete-zst"])
    mock_decompress_zst_files.assert_called_once_with(
        str(tmp_path), delete_zsts=True, overwrite=False
    )


def test_mano_cli_decompress_only_overwrite(tmp_path: Path, mocker: MockerFixture):
    mock_decompress_zst_files = _setup_mock_decompress(mocker, tmp_path)
    mano_cli.decompress([str(tmp_path), "--overwrite"])
    mock_decompress_zst_files.assert_called_once_with(
        str(tmp_path), delete_zsts=False, overwrite=True
    )


def test_confirm_command_doesnt_block_when_it_shouldnt(mocker: MockerFixture):
    global_settings = mocker.patch("mano.mano_cli.GlobalSettings")
    global_settings.skip_user_interaction = False
    mock_input = mocker.patch("mano.mano_cli.input")
    mock_input.return_value = "y"
    mano_cli.confirm_command(*[""])
    mock_input.assert_called_once()
    mock_input = mocker.patch("mano.mano_cli.input")
    mock_input.return_value = "y"
    global_settings.skip_user_interaction = True
    mano_cli.confirm_command(*[""])
    mock_input.assert_not_called()


def test_confirm_command_rejects_non_string_args(mocker: MockerFixture):
    mocker.patch("mano.mano_cli.GlobalSettings").skip_user_interaction = False
    with pytest.raises(InternalError, match="only accepts string arguments"):
        mano_cli.confirm_command("fine", 123)  # type: ignore


def test_confirm_command_exits_when_user_declines(mocker: MockerFixture):
    mocker.patch("mano.mano_cli.GlobalSettings").skip_user_interaction = False
    mocker.patch("mano.mano_cli.input", return_value="n")
    with pytest.raises(SystemExit) as exc_info:
        mano_cli.confirm_command("do the thing")
    assert exc_info.value.code == 0


#
# extract_multithread_args tests
#


def test_extract_multithread_args_no_args_is_noop():
    original = GlobalSettings.multithreading_count
    try:
        args = ["compress", "some/path"]
        mano_cli.extract_multithread_args(args)
        assert args == ["compress", "some/path"]
        assert GlobalSettings.multithreading_count == original
    finally:
        GlobalSettings.multithreading_count = original


def test_extract_multithread_args_sets_thread_count():
    original = GlobalSettings.multithreading_count
    try:
        args = ["compress", "some/path", "--mt4"]
        mano_cli.extract_multithread_args(args)
        assert args == ["compress", "some/path"]
        assert GlobalSettings.multithreading_count == 4
    finally:
        GlobalSettings.multithreading_count = original


def test_extract_multithread_args_multiple_raises():
    with pytest.raises(SystemExit) as exc_info:
        mano_cli.extract_multithread_args(["compress", "--mt2", "--mt4"])
    assert exc_info.value.code == 1


def test_extract_multithread_args_invalid_value_raises():
    with pytest.raises(SystemExit) as exc_info:
        mano_cli.extract_multithread_args(["compress", "--mtX"])
    assert exc_info.value.code == 1


#
# main() dispatch tests
#


def test_main_no_args_prints_help(monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture):
    mocker.patch.object(mano_cli, "GlobalSettings", MagicMock())
    _run_main(monkeypatch, mocker, ["mano"])  # no return value, no SystemExit raised


def test_main_help_flag_prints_help(monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture):
    mocker.patch.object(mano_cli, "GlobalSettings", MagicMock())
    _run_main(monkeypatch, mocker, ["mano", "--help"])


def test_main_unknown_command_exits_1(monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture):
    mocker.patch.object(mano_cli, "GlobalSettings", MagicMock())
    with pytest.raises(SystemExit) as exc_info:
        _run_main(monkeypatch, mocker, ["mano", "frobnicate"])
    assert exc_info.value.code == 1


def test_main_dispatches_to_decompress(monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture):
    mocker.patch.object(mano_cli, "GlobalSettings", MagicMock())
    mock_decompress = mocker.patch.object(mano_cli, "decompress")
    with pytest.raises(SystemExit) as exc_info:
        _run_main(monkeypatch, mocker, ["mano", "decompress", "some/path"])
    assert exc_info.value.code == 0
    mock_decompress.assert_called_once_with(["some/path"])


def test_main_dispatches_to_compress(monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture):
    mocker.patch.object(mano_cli, "GlobalSettings", MagicMock())
    mock_compress = mocker.patch.object(mano_cli, "compress")
    with pytest.raises(SystemExit) as exc_info:
        _run_main(monkeypatch, mocker, ["mano", "compress", "some/path"])
    assert exc_info.value.code == 0
    mock_compress.assert_called_once_with(["some/path"])


def test_main_yes_flag_sets_skip_user_interaction(monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture):
    mock_decompress = mocker.patch.object(mano_cli, "decompress")
    original = GlobalSettings.skip_user_interaction
    try:
        with pytest.raises(SystemExit):
            _run_main(monkeypatch, mocker, ["mano", "decompress", "some/path", "-y"])
        assert GlobalSettings.skip_user_interaction is True
        # the -y flag must be stripped before dispatch
        mock_decompress.assert_called_once_with(["some/path"])
    finally:
        GlobalSettings.skip_user_interaction = original


#
# decompress()/compress() branch tests
#


def test_decompress_single_zst_file(tmp_path: Path, mocker: MockerFixture):
    zst_file = tmp_path / "data.csv.zst"
    zst_file.write_bytes(b"irrelevant")
    mocker.patch("mano.mano_cli.input", return_value="y")
    mock_decompress = mocker.patch("mano.mano_cli.decompress_zst_files")
    mano_cli.decompress([str(zst_file)])
    mock_decompress.assert_called_once_with(str(zst_file), delete_zsts=False, overwrite=False)


def test_decompress_exception_logs_and_exits(tmp_path: Path, mocker: MockerFixture):
    _, _, _ = generate_compressed_zst_files(tmp_path)
    mocker.patch("mano.mano_cli.input", return_value="y")
    mocker.patch("mano.mano_cli.decompress_zst_files", side_effect=RuntimeError("boom"))
    with pytest.raises(SystemExit) as exc_info:
        mano_cli.decompress([str(tmp_path)])
    assert exc_info.value.code == 2


def test_compress_single_valid_beiwe_file(tmp_path: Path, mocker: MockerFixture):
    data_file = tmp_path / "data.csv"
    data_file.write_bytes(b"irrelevant")
    mocker.patch("mano.mano_cli.input", return_value="y")
    mock_compress = mocker.patch("mano.mano_cli.compress_to_zst_files")
    mano_cli.compress([str(data_file)])
    mock_compress.assert_called_once_with(
        str(data_file), delete_original=False, overwrite=False, compression_level=2
    )


def test_compress_exception_logs_and_exits(tmp_path: Path, mocker: MockerFixture):
    _, _, _ = generate_uncompressed_zst_files(tmp_path)
    mocker.patch("mano.mano_cli.input", return_value="y")
    mocker.patch("mano.mano_cli.compress_to_zst_files", side_effect=RuntimeError("boom"))
    with pytest.raises(SystemExit) as exc_info:
        mano_cli.compress([str(tmp_path)])
    assert exc_info.value.code == 2


def test_extract_compression_level_out_of_range_exits(tmp_path: Path):
    with pytest.raises(SystemExit) as exc_info:
        mano_cli.extract_compression_level(["-99"])
    assert exc_info.value.code == 1


#
# argument validation helper tests
#


def test_ensure_minimum_number_of_args_raises_when_too_few():
    with pytest.raises(SystemExit) as exc_info:
        mano_cli.ensure_minimum_number_of_args("decompress", [], 1)
    assert exc_info.value.code == 1


def test_ensure_minimum_number_of_args_passes_when_enough():
    mano_cli.ensure_minimum_number_of_args("decompress", ["some/path"], 1)  # no exception


def test_ensure_only_allowed_parameters_raises_on_unknown():
    with pytest.raises(SystemExit) as exc_info:
        mano_cli.ensure_only_allowed_parameters(
            "decompress", ["some/path", "--bogus"], [mano_cli.DELETE_ZST, mano_cli.OVERWRITE], "some/path"
        )
    assert exc_info.value.code == 1


def test_ensure_only_allowed_parameters_passes_with_allowed_only():
    mano_cli.ensure_only_allowed_parameters(
        "decompress",
        ["some/path", mano_cli.DELETE_ZST, mano_cli.OVERWRITE],
        [mano_cli.DELETE_ZST, mano_cli.OVERWRITE],
        "some/path",
    )  # no exception


#
# mano/__main__.py tests
#
# __main__.py's logic is guarded by `if __name__ == "__main__":`, which never runs when pytest
# imports it as a regular module. runpy.run_module(..., run_name="__main__") executes it in-process
# with __name__ set to "__main__", so it exercises the real code (and is picked up by coverage)
# without needing an actual subprocess.
#


def test_dunder_main_invokes_cli_main(mocker: MockerFixture):
    mock_main = mocker.patch("mano.mano_cli.main")
    runpy.run_module("mano.__main__", run_name="__main__")
    mock_main.assert_called_once()


# NOTE: mano_cli.py's own bottom-of-file guard is written `from os import name` + `if name ==
# "__main__":`, which binds `name` to `os.name` (e.g. "nt"/"posix") instead of the module's
# `__name__`. That means this guard can never actually trigger - it's a latent bug, not a
# reachable safeguard. We force it here by patching `os.name` to "__main__" and reloading the
# module (which re-runs `from os import name` with the patched value), purely to exercise the dead
# branch; this isn't something that happens with a real interpreter's os.name.
def test_mano_cli_dunder_name_guard_is_actually_unreachable_dead_code():
    original_os_name = os.name
    os.name = "__main__"
    try:
        with pytest.raises(NotImplementedError, match="not meant to be run directly"):
            importlib.reload(mano_cli)
    finally:
        os.name = original_os_name
        importlib.reload(mano_cli)  # restore the module to its normal, working state
