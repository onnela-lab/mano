from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import responses
from dateutil.tz import gettz
from pytest_mock import MockerFixture
from pyzstd import decompress

import mano
from mano import mano_cli
from mano.constants import logger as log, UTC
from mano.file_management import (compress_as_backend, compress_general, compress_one_zst_file,
    compress_to_zst_files, decompress_one_zst_file, decompress_zst_files,
    iterate_beiwe_data_files_recursively)
from mano.messages import NO_VALID_FILES_MSG, TIME_REQUIRED_ERROR
from mano.sync import validate_datetime, validate_required_datetime
from tests.conftest import (COMPRESSED_BYTES, DECOMPRESSED_BYTES, generate_compressed_zst_files,
    generate_uncompressed_zst_files, generate_valid_compress_test_files,
    generate_valid_decompress_test_files)

# run throught the test here, go through the test messages, check the message, check if there is duplication with other tests
# commit for the tests in test_studies, another for tests in test_misc. and then change to having a test_endpoints file that combines them
# Eli -- I want you to do this in seperate stages, commit, then push on my branch with the new tests, and then move them into one file as seperate commit.
@responses.activate
def test_fetch_users_in_study_returns_users(keyring: dict[str, str], mock_users_response: str):
    responses.post(
        keyring['URL'] + '/get-users/v1',
        body=mock_users_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    users = list(mano.fetch_users_in_study(keyring, 'STUDY_ID'))
    assert set(users) == {"tgsidhm", "lholbc5", "yxzxtwr"}


@responses.activate
def test_fetch_users_in_study_http_error_raises_api_error(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-users/v1',
        body='Internal Server Error',
        status=500,
    )
    with pytest.raises(mano.APIError, match="500"):
        list(mano.fetch_users_in_study(keyring, 'STUDY_ID'))


@responses.activate
def test_fetch_users_in_study_sends_study_id(keyring: dict[str, str], mock_users_response: str):
    responses.post(
        keyring['URL'] + '/get-users/v1',
        body=mock_users_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    list(mano.fetch_users_in_study(keyring, 'MY_STUDY_ID'))
    request_body = responses.calls[0].request.body
    assert request_body is not None
    assert 'study_id=MY_STUDY_ID' in str(request_body)


@responses.activate
def test_fetch_users_in_study_server_returns_dict_yields_keys(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-users/v1',
        body='{"error": "no users"}', 
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises((ValueError, mano.APIError)):
        list(mano.fetch_users_in_study(keyring, 'STUDY_ID'))


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
    for user in mano.fetch_users_in_study(keyring, 'STUDY_ID'):
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


#
# Beiwe platform specific datetime validation tests
#


def test_datetime_validation():
    assert validate_datetime("2023-01-01T00:00:00Z", "_") == datetime(2023, 1, 1, tzinfo=UTC)
    assert validate_datetime("2023-01-01 00:00:00Z", "_") == datetime(2023, 1, 1, tzinfo=UTC)
    assert validate_required_datetime("2023-01-01T00:00:00Z", "_") == datetime(2023, 1, 1, tzinfo=UTC)
    assert validate_required_datetime("2023-01-01 00:00:00Z", "_") == datetime(2023, 1, 1, tzinfo=UTC)


def test_require_datetime_errors_on_none():
    with pytest.raises(ValueError, match=str(TIME_REQUIRED_ERROR("_"))):
        validate_required_datetime(None, "_")
    with pytest.raises(ValueError, match=str(TIME_REQUIRED_ERROR("_"))):
        validate_required_datetime("", "_")


def test_validate_datetime_no_error_on_none():
    assert validate_datetime(None, "_") is None
    assert validate_datetime("", "_") is None


def test_validate_datetime_timezone_UTC_required():
    dt_wo_tz = datetime(2023, 1, 1, tzinfo=None)
    dt_w_utc = datetime(2023, 1, 1, tzinfo=UTC)
    assert validate_datetime(dt_wo_tz, "_") == dt_w_utc


def test_validate_datetime_with_timezone_timeshifts():
    dt_ny = datetime(2023, 1, 1, 0, 0, 0, tzinfo=gettz("America/New_York"))
    dt_expected = datetime(2023, 1, 1, 5, 0, 0, tzinfo=UTC)  # shifted to UTC
    dt_should_be_utc_0_0_0 = validate_datetime(dt_ny, "_")
    assert dt_should_be_utc_0_0_0 == dt_expected


def test_validate_datetime_string_with_timezone_timeshifts():
    dt_from_str = "2023-01-01T05:00:00+05:00"  # UTC-5
    dt_expected = datetime(2023, 1, 1, 0, 0, 0, tzinfo=UTC)  # shifted to UTC
    dt_should_be_utc_0_0_0 = validate_datetime(dt_from_str, "_")
    assert dt_should_be_utc_0_0_0 == dt_expected


def test_validate_datetime_too_something():
    with pytest.raises(ValueError, match=".*is before the earliest possible.*"):
        validate_datetime("2010-01-01T00:00:00Z", "_")
    with pytest.raises(ValueError, match=".*is too far in the future.*"):
        validate_datetime("2100-01-01T00:00:00Z", "_")


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


def test_full_compress_compresses(tmp_path: Path):
    compressable_files, _uncompressable_files, original_bytes = generate_valid_compress_test_files(tmp_path)
    compress_to_zst_files(str(tmp_path), delete_original=False, overwrite=False)
    common_full_compress(tmp_path, original_bytes, compressable_files)


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





def test_interval_negative_raises_error():
    with pytest.raises(mano.IntervalError):
        mano.interval("-5m")
    with pytest.raises(mano.IntervalError):
        mano.interval("-1h")


def test_interval_with_spaces_raises_error():
    with pytest.raises(mano.IntervalError):
        mano.interval(" 5m")  
    with pytest.raises(mano.IntervalError):
        mano.interval("5m ") 
    with pytest.raises(mano.IntervalError):
        mano.interval("5 m") 


def test_interval_unit_only_raises_error():
    with pytest.raises(mano.IntervalError):
        mano.interval("m")
    with pytest.raises(mano.IntervalError):
        mano.interval("s")
    with pytest.raises(mano.IntervalError):
        mano.interval("h")
    with pytest.raises(mano.IntervalError):
        mano.interval("d")


def test_interval_float_raises_error():
    with pytest.raises(mano.IntervalError):
        mano.interval("1.5h")
    with pytest.raises(mano.IntervalError):
        mano.interval("0.5m")


def test_interval_whitespace_only_raises_error():
    with pytest.raises(mano.IntervalError):
        mano.interval(" ")


def test_interval_multiple_units_raises_error():
    with pytest.raises(mano.IntervalError):
        mano.interval("1h30m")
    with pytest.raises(mano.IntervalError):
        mano.interval("1hh")


def test_interval_uppercase_all_units():
    assert mano.interval("10S") == 10
    assert mano.interval("5M") == 300
    assert mano.interval("2H") == 7200
    assert mano.interval("1D") == 86400


import pytest
import responses

import mano
from mano.constants import APIError


@responses.activate
def test_studies(keyring: dict[str, str], mock_studies_response: str):
    expected_studies = {
        ('Project A', '123lrVdb0g6tf3PeJr5ZtZC8'),
        ('Project B', '123U93wwgS18aLDIwdYXTXsr')
    }
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    studies = set[tuple[str, str]]()
    for study in mano.fetch_accessible_studies(keyring):
        studies.add(study)
    
    assert studies == expected_studies


@responses.activate
def test_expand_study_id(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    expected_study = ('Project A', '123lrVdb0g6tf3PeJr5ZtZC8')
    study = mano.expand_study_id(keyring, '123lrVdb0g6tf3PeJr5ZtZC8')
    assert study == expected_study


@responses.activate
def test_expand_study_id_conflict(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises(mano.AmbiguousStudyIDError):
        _ = mano.expand_study_id(keyring, '123')


@responses.activate
def test_expand_study_id_nomatch(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    study = mano.expand_study_id(keyring, '321')
    assert study is None


@responses.activate
def test_studyid(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    expected_studyid = '123lrVdb0g6tf3PeJr5ZtZC8'
    study_id = mano.studyid(keyring, 'Project A')
    assert study_id == expected_studyid


@responses.activate
def test_studyid_not_found(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises(mano.StudyIDError):
        _ = mano.studyid(keyring, 'Project X')


@responses.activate
def test_studyname(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    expected_study_name = 'Project A'
    study_name = mano.studyname(keyring, '123lrVdb0g6tf3PeJr5ZtZC8')
    assert study_name == expected_study_name


@responses.activate
def test_studyname_not_found(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises(mano.StudyNameError):
        _ = mano.studyname(keyring, 'x')


@responses.activate
def test_fetch_accessible_studies_empty_response(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body='{}',
        status=200,
        content_type='text/html; charset=utf-8'
    )
    results = list(mano.fetch_accessible_studies(keyring))
    assert results == []


@responses.activate
def test_fetch_accessible_studies_http_error_raises_api_error(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body='Internal Server Error',
        status=500,
    )
    with pytest.raises(APIError, match=r"^response not ok \(500\) https://studies.beiwe.org/get-studies/v1$"):
        list(mano.fetch_accessible_studies(keyring))


@responses.activate
def test_whether_credentials_are_passed(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body='{}',
        status=200,
        content_type='text/html; charset=utf-8'
    )
    list(mano.fetch_accessible_studies(keyring))

    request_body = responses.calls[0].request.body
    assert request_body is not None
    assert 'access_key=ACCESS_KEY' in str(request_body)
    assert 'secret_key=SECRET_KEY' in str(request_body)



@responses.activate
def test_studyid_case_sensitive(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises(mano.StudyIDError):
        mano.studyid(keyring, 'project a') 


@responses.activate
def test_studyname_case_sensitive(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises(mano.StudyNameError):
        mano.studyname(keyring, '123LRVDB0G6TF3PEJR5ZTZCB')


@responses.activate
def test_studyid_empty_string_raises_study_id_error(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises(mano.StudyIDError):
        mano.studyid(keyring, '')


@responses.activate
def test_studyname_empty_string_raises_study_name_error(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises(mano.StudyNameError):
        mano.studyname(keyring, '')


@responses.activate
def test_studyid_duplicate_study_names_returns_first_match(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body='{"id_first": "Same Name", "id_second": "Same Name"}',
        status=200,
        content_type='text/html; charset=utf-8'
    )
    with pytest.raises(mano.AmbiguousStudyIDError):
        mano.studyid(keyring, 'Same Name')


@responses.activate
def test_fetch_users_in_study_empty_list_yields_nothing(keyring: dict[str, str]):
    responses.post(
        keyring['URL'] + '/get-users/v1',
        body='[]',
        status=200,
        content_type='text/html; charset=utf-8'
    )
    results = list(mano.fetch_users_in_study(keyring, 'STUDY_ID'))
    assert results == []

# Test correctness, the way it corrently works.
@responses.activate 
def test_studyid_with_whitespace_name_not_found(keyring: dict[str, str], mock_studies_response: str):
    responses.post(
        keyring['URL'] + '/get-studies/v1',
        body=mock_studies_response,
        status=200,
        content_type='text/html; charset=utf-8'
    )
    result = mano.studyid(keyring, ' Project A ')
    assert result == '123lrVdb0g6tf3PeJr5ZtZC8'
