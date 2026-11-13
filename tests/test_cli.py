import importlib, logging, os, runpy, sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from mano import mano_cli
from mano.constants import GlobalSettings, InternalError
from mano.messages import NO_COMMAND_ERROR, UNKNOWN_COMMAND_ERROR
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


# A flag that is parsed but not passed on could make a user delete or overwrite files unexpectedly.
# This is a parametrized test: pytest runs it once for each case listed in the decorator below,
# passing that case's values in as the test function's arguments.
# Checks that each `mano compress` command-line flag is passed through to compress_to_zst_files.
# This test runs once per row. Each row is:
#   (extra CLI flags, expected delete_original, expected overwrite, expected compression_level)
# Compression level defaults to 2 unless a `-N` flag is given.
@pytest.mark.parametrize(
    ("flags", "delete_original", "overwrite", "compression_level"),
    [
        (["--delete-original", "--overwrite"], True, True, 2),   # both flags on
        ([], False, False, 2),                                   # no flags: everything off
        (["--delete-original"], True, False, 2),                 # only delete
        (["--overwrite"], False, True, 2),                       # only overwrite
        (["-19"], False, False, 19),                             # custom compression level
    ],
    ids=["all", "no_delete_no_overwrite", "only_delete", "only_overwrite", "custom_level"],
)
def test_mano_cli_compress_flags(
    tmp_path: Path,
    mocker: MockerFixture,
    flags: list[str],
    delete_original: bool,
    overwrite: bool,
    compression_level: int,
):
    mock_compress_to_zst_files = _setup_mock_compress(mocker, tmp_path)
    mano_cli.compress([str(tmp_path), *flags])
    mock_compress_to_zst_files.assert_called_once_with(
        str(tmp_path), delete_original=delete_original, overwrite=overwrite, compression_level=compression_level
    )


# A flag that is parsed but not passed on could make a user delete or overwrite files unexpectedly.
# This is a parametrized test: pytest runs it once for each case listed in the decorator below,
# passing that case's values in as the test function's arguments.
# Checks that each `mano decompress` command-line flag is passed through to decompress_zst_files.
# This test runs once per row. Each row is:
#   (extra CLI flags, expected delete_zsts, expected overwrite)
@pytest.mark.parametrize(
    ("flags", "delete_zsts", "overwrite"),
    [
        (["--delete-zst", "--overwrite"], True, True),   # both flags on
        ([], False, False),                              # no flags: everything off
        (["--delete-zst"], True, False),                 # only delete
        (["--overwrite"], False, True),                  # only overwrite
    ],
    ids=["all", "no_delete_no_overwrite", "only_delete", "only_overwrite"],
)
def test_mano_cli_decompress_flags(
    tmp_path: Path, mocker: MockerFixture, flags: list[str], delete_zsts: bool, overwrite: bool
):
    mock_decompress_zst_files = _setup_mock_decompress(mocker, tmp_path)
    mano_cli.decompress([str(tmp_path), *flags])
    mock_decompress_zst_files.assert_called_once_with(
        str(tmp_path), delete_zsts=delete_zsts, overwrite=overwrite
    )


# Scripts that pass -y must never hang on a prompt, while interactive users must still be asked.
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


# Non-string arguments are a programming mistake, and should fail at once rather than print a
# garbled prompt.
def test_confirm_command_rejects_non_string_args(mocker: MockerFixture):
    mocker.patch("mano.mano_cli.GlobalSettings").skip_user_interaction = False
    with pytest.raises(InternalError, match="only accepts string arguments"):
        mano_cli.confirm_command("fine", 123)  # type: ignore


# Saying no to the prompt must stop the command before it touches any files.
def test_confirm_command_exits_when_user_declines(mocker: MockerFixture):
    mocker.patch("mano.mano_cli.GlobalSettings").skip_user_interaction = False
    mocker.patch("mano.mano_cli.input", return_value="n")
    with pytest.raises(SystemExit) as exc_info:
        mano_cli.confirm_command("do the thing")
    assert exc_info.value.code == 0


#
# extract_multithread_args tests
#


# Commands without a threads flag must keep the default and leave their arguments alone.
def test_extract_multithread_args_no_args_is_noop():
    original = GlobalSettings.multithreading_count
    try:
        args = ["compress", "some/path"]
        mano_cli.extract_multithread_args(args)
        assert args == ["compress", "some/path"]
        assert GlobalSettings.multithreading_count == original
    finally:
        GlobalSettings.multithreading_count = original


# The flag must set the thread count and be removed so later argument checks do not reject it.
def test_extract_multithread_args_sets_thread_count():
    original = GlobalSettings.multithreading_count
    try:
        args = ["compress", "some/path", "--mt4"]
        mano_cli.extract_multithread_args(args)
        assert args == ["compress", "some/path"]
        assert GlobalSettings.multithreading_count == 4
    finally:
        GlobalSettings.multithreading_count = original


# Two thread flags are ambiguous, so the user should get an error instead of one silently winning.
def test_extract_multithread_args_multiple_raises():
    with pytest.raises(SystemExit) as exc_info:
        mano_cli.extract_multithread_args(["compress", "--mt2", "--mt4"])
    assert exc_info.value.code == 1


# A mistyped thread count must stop with a clear error rather than run with a wrong value.
def test_extract_multithread_args_invalid_value_raises():
    with pytest.raises(SystemExit) as exc_info:
        mano_cli.extract_multithread_args(["compress", "--mtX"])
    assert exc_info.value.code == 1


#
# main() dispatch tests
#


# Running plain `mano` is how new users find out what it does, so it must show help and not crash.
def test_main_no_args_prints_help(monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture):
    mocker.patch.object(mano_cli, "GlobalSettings", MagicMock())
    _run_main(monkeypatch, mocker, ["mano"])  # no return value, no SystemExit raised


# Users expect --help to work and not to fail as an unknown command.
def test_main_help_flag_prints_help(monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture):
    mocker.patch.object(mano_cli, "GlobalSettings", MagicMock())
    _run_main(monkeypatch, mocker, ["mano", "--help"])


# Scripts need a non-zero exit code when a command name is wrong.
def test_main_unknown_command_exits_1(monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture):
    mocker.patch.object(mano_cli, "GlobalSettings", MagicMock())
    with pytest.raises(SystemExit) as exc_info:
        _run_main(monkeypatch, mocker, ["mano", "frobnicate"])
    assert exc_info.value.code == 1


# The user needs to see which command name was rejected, so typos are easy to spot.
def test_main_unknown_command_error_names_the_command(
    monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture, caplog: pytest.LogCaptureFixture,
):
    mocker.patch.object(mano_cli, "GlobalSettings", MagicMock())
    with pytest.raises(SystemExit):
        _run_main(monkeypatch, mocker, ["mano", "frobnicate", "some/path"])
    assert UNKNOWN_COMMAND_ERROR("frobnicate") in caplog.text
    # the debug line echoing argv also holds the path, so look only at error records
    error_messages = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert error_messages == [UNKNOWN_COMMAND_ERROR("frobnicate")]  # not the leftover args


# Flags alone are not a command, and users should be told that instead of getting silence.
# Checks that main exits 1 with a clear error when no command is given.
# Column: argv = the full sys.argv list (program name first).
@pytest.mark.parametrize("argv", [
    ["mano", "-y"],  # only the global yes flag
    ["mano", "--yes"],  # only the long yes flag
    ["mano", "--mt4"],  # only a multithreading flag
])
def test_main_no_command_logs_error_and_exits_1(
    monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture, caplog: pytest.LogCaptureFixture,
    argv: list[str],
):
    mocker.patch.object(mano_cli, "GlobalSettings", MagicMock())
    with pytest.raises(SystemExit) as exc_info:
        _run_main(monkeypatch, mocker, argv)
    assert exc_info.value.code == 1
    assert NO_COMMAND_ERROR in caplog.text


# The command name must reach the right handler with the remaining arguments, and exit 0 on success.
def test_main_dispatches_to_decompress(monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture):
    mocker.patch.object(mano_cli, "GlobalSettings", MagicMock())
    mock_decompress = mocker.patch.object(mano_cli, "decompress")
    with pytest.raises(SystemExit) as exc_info:
        _run_main(monkeypatch, mocker, ["mano", "decompress", "some/path"])
    assert exc_info.value.code == 0
    mock_decompress.assert_called_once_with(["some/path"])


# The command name must reach the right handler with the remaining arguments, and exit 0 on success.
def test_main_dispatches_to_compress(monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture):
    mocker.patch.object(mano_cli, "GlobalSettings", MagicMock())
    mock_compress = mocker.patch.object(mano_cli, "compress")
    with pytest.raises(SystemExit) as exc_info:
        _run_main(monkeypatch, mocker, ["mano", "compress", "some/path"])
    assert exc_info.value.code == 0
    mock_compress.assert_called_once_with(["some/path"])


# -y is what lets scripts run without prompts, and it must not leak into the command's own
# arguments.
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


# Users can pass one file instead of a folder, and that path must be handed on as given.
def test_decompress_single_zst_file(tmp_path: Path, mocker: MockerFixture):
    zst_file = tmp_path / "data.csv.zst"
    zst_file.write_bytes(b"irrelevant")
    mocker.patch("mano.mano_cli.input", return_value="y")
    mock_decompress = mocker.patch("mano.mano_cli.decompress_zst_files")
    mano_cli.decompress([str(zst_file)])
    mock_decompress.assert_called_once_with(str(zst_file), delete_zsts=False, overwrite=False)


# A failure inside decompression should end with a clear error and exit code 2, not a raw traceback.
def test_decompress_exception_logs_and_exits(tmp_path: Path, mocker: MockerFixture):
    _, _, _ = generate_compressed_zst_files(tmp_path)
    mocker.patch("mano.mano_cli.input", return_value="y")
    mocker.patch("mano.mano_cli.decompress_zst_files", side_effect=RuntimeError("boom"))
    with pytest.raises(SystemExit) as exc_info:
        mano_cli.decompress([str(tmp_path)])
    assert exc_info.value.code == 2


# Users can pass one file instead of a folder, and the default options must apply.
def test_compress_single_valid_beiwe_file(tmp_path: Path, mocker: MockerFixture):
    data_file = tmp_path / "data.csv"
    data_file.write_bytes(b"irrelevant")
    mocker.patch("mano.mano_cli.input", return_value="y")
    mock_compress = mocker.patch("mano.mano_cli.compress_to_zst_files")
    mano_cli.compress([str(data_file)])
    mock_compress.assert_called_once_with(
        str(data_file), delete_original=False, overwrite=False, compression_level=2
    )


# A failure inside compression should end with a clear error and exit code 2, not a raw traceback.
def test_compress_exception_logs_and_exits(tmp_path: Path, mocker: MockerFixture):
    _, _, _ = generate_uncompressed_zst_files(tmp_path)
    mocker.patch("mano.mano_cli.input", return_value="y")
    mocker.patch("mano.mano_cli.compress_to_zst_files", side_effect=RuntimeError("boom"))
    with pytest.raises(SystemExit) as exc_info:
        mano_cli.compress([str(tmp_path)])
    assert exc_info.value.code == 2


# zstd only accepts a limited range of levels, so a bad level should stop with an error before any
# work starts.
def test_extract_compression_level_out_of_range_exits(tmp_path: Path):
    with pytest.raises(SystemExit) as exc_info:
        mano_cli.extract_compression_level(["-99"])
    assert exc_info.value.code == 1


#
# argument validation helper tests
#


# A command run without its required path should stop with a usage error.
def test_ensure_minimum_number_of_args_raises_when_too_few():
    with pytest.raises(SystemExit) as exc_info:
        mano_cli.ensure_minimum_number_of_args("decompress", [], 1)
    assert exc_info.value.code == 1


# The check must not block correct usage.
def test_ensure_minimum_number_of_args_passes_when_enough():
    mano_cli.ensure_minimum_number_of_args("decompress", ["some/path"], 1)  # no exception


# A mistyped flag must be rejected, or the user may think a safety option like --delete-zst was
# applied.
def test_ensure_only_allowed_parameters_raises_on_unknown():
    with pytest.raises(SystemExit) as exc_info:
        mano_cli.ensure_only_allowed_parameters(
            "decompress", ["some/path", "--bogus"], [mano_cli.DELETE_ZST, mano_cli.OVERWRITE], "some/path"
        )
    assert exc_info.value.code == 1


# The check must not block correct usage.
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


# `python -m mano` must start the CLI, and this is the only test that runs __main__.py.
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
