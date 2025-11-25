from pathlib import Path
from unittest.mock import MagicMock

import pytest
import responses
from pytest_mock import MockerFixture
from pyzstd import decompress

import mano
from mano import mano_cli
from mano.constants import logger as log, VALID_EXTENSIONS_MESSAGE
from mano.file_management import (compress_as_backend, compress_general, compress_one_zst_file,
    compress_to_zst_files, decompress_one_zst_file, decompress_zst_files,
    iterate_beiwe_data_files_recursively)
from tests.conftest import (generate_compressed_zst_files, generate_uncompressed_zst_files,
    generate_valid_compress_test_files, generate_valid_decompress_test_files)


@responses.activate
def test_users(keyring: dict[str, str], mock_users_response: str):
    expected_users = set(["tgsidhm", "lholbc5", "yxzxtwr"])
    responses.post(
        keyring['URL'] + '/get-users/v1',
        body=mock_users_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    users = set[str]()
    for user in mano.users(keyring, 'STUDY_ID'):
        users.add(user)
    assert users == expected_users


def test_device_settings():
    # The device_settings function is implemented by programmatically logging
    # into the Beiwe frontend (which any user can do) and scraping the Study
    # app settings page. This type of function is brittle and I'm choosing not
    # to spend any time dealing with it.
    #
    # It's worth noting that this function also needs the user to pass in a
    # Study ID that is different from the usual Study ID expected by other API
    # endpoints. This was not always the case and this alternate Study ID is
    # not returned by get-studies/v1 or anywhere else that I can think of.
    #
    # At the moment, Beiwe does have an export_study_settings_file API endpoint
    # but it's only accessible to users with site administration privileges.
    """
    Keyring = {
        'URL': 'https://studies.beiwe.org',
        'USERNAME': 'foobar',
        'PASSWORD': 'bizbat',
        'ACCESS_KEY': 'ACCESS_KEY',
        'SECRET_KEY': 'SECRET_KEY'
    }
    cassette = os.path.join(DIR, 'cassettes', 'device_settings.yaml')
    filter_params = [
        ('access_key', Keyring['ACCESS_KEY']),
        ('secret_key', Keyring['SECRET_KEY']),
        ('username', Keyring['USERNAME']),
        ('password', Keyring['PASSWORD']),
        ('study_id', 'STUDY_ID')
    ]
    device_settings = set([
        ('accelerometer_off_duration_seconds', '10'),
        ('accelerometer_on_duration_seconds', '10')
    ])
    with vcr.use_cassette(cassette, decode_compressed_response=True,
                          filter_post_data_parameters=filter_params):
        ans = set()
        for setting in mano.device_settings(Keyring, '123'):
            ans.add(setting)
        assert ans == device_settings
    """


def test_interval():
    assert mano.interval("10s") == 10
    assert mano.interval("5m") == 300
    assert mano.interval("2h") == 7200
    assert mano.interval("1d") == 86400
    assert mano.interval("0s") == 0
    assert mano.interval("0h") == 0
    assert mano.interval("0H") == 0
    assert mano.interval("0m") == 0
    assert mano.interval("0d") == 0
    assert mano.interval("000000000000m") == 0
    
    with pytest.raises(mano.IntervalError, match="invalid interval 'y'"):
        mano.interval("y")
    
    # there's a regex that catches it first
    # with pytest.raises(mano.IntervalError, match="invalid interval unit '10x'"):
    with pytest.raises(mano.IntervalError, match="invalid interval '10x'"):
        mano.interval("10x")
    
    with pytest.raises(mano.IntervalError, match="invalid interval 'abc'"):
        mano.interval("abc")
    
    with pytest.raises(mano.IntervalError, match="invalid interval ''"):
        mano.interval("")
    
    with pytest.raises(mano.IntervalError, match="invalid interval ''"):
        mano.interval("")


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


# (tmp_path is a built-in pytest fixture, it creates a temporary directory for the test)
# test compress


def test_compress_one_zst_file_defaults(tmp_path: Path):
    uncompressed_path, compressed_path, original_bytes = generate_uncompressed_zst_files(tmp_path)
    compress_one_zst_file(str(uncompressed_path))
    assert compressed_path.exists()
    assert uncompressed_path.exists()
    assert original_bytes == decompress(compressed_bytes:=compressed_path.read_bytes())
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


def tesst_compress_one_zst_file_custom_level(tmp_path: Path):
    uncompressed_path, compressed_path, original_bytes = generate_uncompressed_zst_files(tmp_path)
    compress_one_zst_file(str(uncompressed_path), compression_level=19)  # take it slow
    assert compressed_path.exists()
    assert uncompressed_path.exists()
    assert original_bytes == decompress(compressed_bytes:=compressed_path.read_bytes())
    assert len(compressed_bytes) < len(original_bytes)


# test decompress


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


# test file iteration


def test_iterate_valid_data_files(tmp_path: Path):
    # create some valid and invalid files
    valid_files = ["data1.csv", "audio.wav"]
    invalid_files = ["document.txt", "image.jpg", "archive.zip", "script.py"]
    
    # make them exist
    for filename in valid_files + invalid_files:
        (tmp_path / filename).write_text("test content")
    
    found_files = set[str]()
    for file_path in iterate_beiwe_data_files_recursively(str(tmp_path)):
        found_files.add(Path(file_path).name)
    
    assert found_files == set(valid_files)


def test_iterate_no_such_folder():
    with pytest.raises(FileNotFoundError, match="No such directory: `this/path/does/not/exist`"):
        for fp in iterate_beiwe_data_files_recursively("this/path/does/not/exist"):
            log.error(f"Unexpected file found while running test 1: {fp}")  # debugging helper
    
    with pytest.raises(FileNotFoundError, match="No such directory: `this/path/does/not/exist`"):
        for fp in iterate_beiwe_data_files_recursively("this/path/does/not/exist", zst_only=True):
            log.error(f"Unexpected file found while running test 2: {fp}")  # debugging helper


def test_empty_folder(tmp_path: Path):
    restricted_dir = tmp_path / "restricted"
    restricted_dir.mkdir()
    
    # this is the error for when it had nothing with the right extensions
    with pytest.raises(FileNotFoundError, match=f"{VALID_EXTENSIONS_MESSAGE}: `{str(tmp_path)}`"):
        for fp in iterate_beiwe_data_files_recursively(str(tmp_path)):
            log.error(f"Unexpected file found while running test 3: {fp}")  # debugging helper
    
    msg2 =f"No `.zst` files found in directory `{str(tmp_path)}` or its subdirectories."
    with pytest.raises(FileNotFoundError, match=msg2):
        for fp in iterate_beiwe_data_files_recursively(str(tmp_path), zst_only=True):
            log.error(f"Unexpected file found while running test 4: {fp}")  # debugging helper


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


# full compress/decompress tests


def test_full_decompress_decompresses(tmp_path: Path):
    zst_files, non_zst_files, uncompressed_bytes = generate_valid_decompress_test_files(tmp_path)
    decompress_zst_files(str(tmp_path), delete_zsts=False, overwrite=False)
    common_full_decompress(tmp_path, uncompressed_bytes, zst_files, non_zst_files)


def test_full_decompress_multithread_works(tmp_path: Path):
    # as above, but with multithreading
    zst_files, non_zst_files, uncompressed_bytes = generate_valid_decompress_test_files(tmp_path)
    decompress_zst_files(str(tmp_path), delete_zsts=False, overwrite=False, multithread_count=4)
    common_full_decompress(tmp_path, uncompressed_bytes, zst_files, non_zst_files)


def common_full_decompress(
    tmp_path: Path, uncompressed_bytes: bytes, zst_files: list[Path], non_zst_files: list[Path]
):
    correct_uncompressed_file_paths = {str(path).rsplit(".zst")[0] for path in zst_files}
    
    for path in non_zst_files:  # add the valid never-were-compressed files too (iterate picks them up)
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


def test_full_compress_compresses(tmp_path: Path):
    compressable_files, _uncompressable_files, original_bytes = generate_valid_compress_test_files(tmp_path)
    compress_to_zst_files(str(tmp_path), delete_original=False, overwrite=False)
    common_full_compress(tmp_path, original_bytes, compressable_files)


def test_full_compress_multithread_works(tmp_path: Path):
    # as above, but with multithreading
    compressable_files, _uncompressable_files, original_bytes = generate_valid_compress_test_files(tmp_path)
    compress_to_zst_files(str(tmp_path), delete_original=False, overwrite=False, multithread_count=4)
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
    # create dummy .zst files to be overwritten
    for path in compressable_files:
        (path.parent / (path.name + ".zst")).write_bytes(b"super secret data")
    
    compress_to_zst_files(str(tmp_path), delete_original=False, overwrite=True)
    for path in compressable_files:
        compressed_path = path.parent / (path.name + ".zst")
        assert compressed_path.exists()
        assert decompress(compressed_path.read_bytes()) == decompressed_data


def test_full_decompress_overwrites(tmp_path: Path):
    zst_files, _non_zst_files, decompressed_data = generate_valid_decompress_test_files(tmp_path)
    # create dummy uncompressed files to be overwritten
    for path in zst_files:
        Path(str(path).rsplit(".zst")[0]).write_bytes(b"super secret data")
    
    decompress_zst_files(str(tmp_path), delete_zsts=False, overwrite=True)
    for path in zst_files:
        uncompressed_path = path.parent / path.name.rsplit(".zst")[0]
        assert uncompressed_path.exists()
        assert uncompressed_path.read_bytes() == decompressed_data


def test_full_compress_raises_an_error_during_real_execution_1_thread(tmp_path: Path, mocker: MockerFixture):
    # simulate an error during compression
    _compressable_files, _uncompressable_files, _ = generate_valid_compress_test_files(tmp_path)
    mocker.patch("mano.file_management.compress_one_zst_file", side_effect=Exception("Simulated compression error"))
    with pytest.raises(Exception, match="Simulated compression error"):
        compress_to_zst_files(str(tmp_path), delete_original=False, overwrite=False, multithread_count=1)


def test_full_compress_raises_an_error_during_real_execution_2_threads(tmp_path: Path, mocker: MockerFixture):
    # simulate an error during compression
    _compressable_files, _uncompressable_files, _ = generate_valid_compress_test_files(tmp_path)
    mocker.patch("mano.file_management.compress_one_zst_file", side_effect=Exception("Simulated compression error"))
    with pytest.raises(Exception, match="Simulated compression error"):
        compress_to_zst_files(str(tmp_path), delete_original=False, overwrite=False, multithread_count=2)


def test_full_decompress_raises_an_error_during_real_execution_1_thread(tmp_path: Path, mocker: MockerFixture):
    # simulate an error during decompression
    _zst_files, _non_zst_files, _ = generate_valid_decompress_test_files(tmp_path)
    mocker.patch("mano.file_management.decompress_one_zst_file", side_effect=Exception("Simulated decompression error"))
    with pytest.raises(Exception, match="Simulated decompression error"):
        decompress_zst_files(str(tmp_path), delete_zsts=False, overwrite=False, multithread_count=1)


def test_full_decompress_raises_an_error_during_real_execution_2_threads(tmp_path: Path, mocker: MockerFixture):
    # simulate an error during decompression
    _zst_files, _non_zst_files, _ = generate_valid_decompress_test_files(tmp_path)
    mocker.patch("mano.file_management.decompress_one_zst_file", side_effect=Exception("Simulated decompression error"))
    with pytest.raises(Exception, match="Simulated decompression error"):
        decompress_zst_files(str(tmp_path), delete_zsts=False, overwrite=False, multithread_count=2)

#
# test mano CLI commands
#


def _setup_mock_compress(mocker: MockerFixture, tmp_path: Path) -> MagicMock:
    # mocks the function call and sets up `input` to let us run the function without breaking
    _, _, _ = generate_uncompressed_zst_files(tmp_path)
    mock_input = mocker.patch("mano.mano_cli.input")
    mock_input.return_value = "y"
    return mocker.patch("mano.mano_cli.compress_to_zst_files")


def _setup_mock_decompress(mocker: MockerFixture, tmp_path: Path) -> MagicMock:
    # mocks the function call and sets up `input` to let us run the function without breaking
    _, _, _ = generate_compressed_zst_files(tmp_path)
    mock_input = mocker.patch("mano.mano_cli.input")
    mock_input.return_value = "y"
    return mocker.patch("mano.mano_cli.decompress_zst_files")


#
# compress tests
#


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

#
# decompress tests
#

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


# test cli helpers


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
