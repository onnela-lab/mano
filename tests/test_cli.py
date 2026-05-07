from pathlib import Path
from unittest.mock import MagicMock

from pytest_mock import MockerFixture

from mano import mano_cli
from tests.conftest import generate_compressed_zst_files, generate_uncompressed_zst_files


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
