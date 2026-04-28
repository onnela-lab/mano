from datetime import date, datetime, timedelta
from io import BytesIO
from os import listdir, makedirs, remove as delete_file
from pathlib import Path
from time import sleep
from zipfile import ZipFile

import pytest
import requests
import responses
from pytest_mock import MockerFixture
from pyzstd import decompress
from responses import RequestsMock

from mano import sync
from mano.constants import APIError, UnParsableTimeError, UTC
from mano.messages import NOT_200_OK_ERROR
from tests.conftest import (DATA_STREAM_FILE, DATA_STREAM_FOLDER, FILE_CONTENT_COMPRESSED,
    FILE_CONTENT_ENCRYPTED_COMPRESSED, FILE_CONTENT_ENCRYPTED_UNCOMPRESSED,
    FILE_CONTENT_UNCOMPRESSED, FILE_SHA1_HASH_BYTES, FILE_SHA1_HASH_STRING, LOCAL_PATH_REFERENCE,
    NORMALIZED_FILE_PATH, PARTICIPANT_ID, PASSPHRASE_STRING, STUDY_ID)


#
# test download function
#


def test_download_returns_zipfile(mock_download_v1_api: RequestsMock, keyring: dict[str, str]):
    """ Test that download function returns a ZipFile object. """
    # Call the download function
    zf = sync.download(
        keyring,
        study_id='STUDY_ID',
        participant_ids=['USER_ID'],
        data_streams=['identifiers', 'gps'],
        time_start='2018-06-15T00:00:00',
        time_end='2018-06-17T00:00:00'
    )
    
    # Check that we got a ZipFile object
    assert isinstance(zf, ZipFile)


def test_download_user_ids_alias(mock_download_v1_api: RequestsMock, keyring: dict[str, str]):
    """ Ensure the deprecated user_ids alias works as expected. """
    # Just test that it doesn't crash, if we later have further infrastructure duplicate a separate test
    sync.download(
        keyring,
        study_id='STUDY_ID',
        user_ids=['USER_ID'],
        data_streams=['identifiers', 'gps'],
        time_start='2018-06-15T00:00:00',
        time_end='2018-06-17T00:00:00'
    )


def test_download_file_count(mock_download_v1_api: RequestsMock, keyring: dict[str, str]):
    """Test that download returns the expected number of files."""
    # Call the download function
    zf = sync.download(
        keyring,
        study_id='STUDY_ID',
        participant_ids=['USER_ID'],
        data_streams=['identifiers', 'gps'],
        time_start='2018-06-15T00:00:00',
        time_end='2018-06-17T00:00:00'
    )
    
    # Get the list of files in the zip (excluding directory entries)
    assert isinstance(zf, ZipFile)
    file_names = [zinfo.filename for zinfo in zf.infolist() if not zinfo.filename.endswith('/')]
    
    # Verify we have the expected total number of files
    # (29 GPS + 1 identifier + 1 registry = 31)
    assert len(file_names) == 31


def test_download_v1_contains_expected_files_with_correct_crcs(
    mock_download_v1_api: RequestsMock,
    keyring: dict[str, str],
    expected_uncompressed_filenames: set[tuple[str, int]],
):
    """Test download contains expected files with correct CRC values from original data."""
    # Call the download function
    zf = sync.download(
        keyring,
        study_id='STUDY_ID',
        participant_ids=['USER_ID'],
        data_streams=['identifiers', 'gps'],
        time_start='2018-06-15T00:00:00',
        time_end='2018-06-17T00:00:00'
    )
    
    # Get the actual files and their CRC values from the zip
    assert isinstance(zf, ZipFile)
    actual_files = {(zinfo.filename, zinfo.CRC) for zinfo in zf.infolist()}
    
    # Filter actual files to only include expected ones (excludes directories)
    filtered_actual_files = {
        (filename, crc) for filename, crc in actual_files
        if filename in {f for f, _ in expected_uncompressed_filenames}
    }
    
    # Verify that the CRC values match exactly
    assert filtered_actual_files == expected_uncompressed_filenames


def test_download_v2_contains_expected_files_with_correct_crcs(
    mock_download_v2_api: RequestsMock,
    keyring: dict[str, str],
    expected_compressed_filenames: set[tuple[str, int]],
):
    """Test download contains expected files with correct CRC values from original data."""
    # Call the download function
    zf = sync.download(
        keyring,
        study_id='STUDY_ID',
        participant_ids=['USER_ID'],
        data_streams=['identifiers', 'gps'],
        time_start='2018-06-15T00:00:00',
        time_end='2018-06-17T00:00:00',
        compressed=True,
    )
    
    # Get the actual files and their CRC values from the zip
    assert isinstance(zf, ZipFile)
    actual_files = {(zinfo.filename, zinfo.CRC) for zinfo in zf.infolist()}
    
    # Filter actual files to only include expected ones (excludes directories)
    filtered_actual_files = {
        (filename, crc) for filename, crc in actual_files
        if filename in {f for f, _ in expected_compressed_filenames}
    }
    
    # Verify that the CRC values match exactly
    assert filtered_actual_files == expected_compressed_filenames


def test_download_v1_and_v2_have_same_underlying_data(
    mock_download_v1_and_v2_api: RequestsMock,
    keyring: dict[str, str],
    expected_compressed_filenames: set[tuple[str, int]],
    expected_uncompressed_filenames: set[tuple[str, int]],
):
    compressed_filenames = {n[:-4] for n, _ in expected_compressed_filenames}
    compressed_filenames.remove("regi")
    compressed_filenames.add("registry")
    uncompressed_filenames = {n for n, _ in expected_uncompressed_filenames}
    assert compressed_filenames == uncompressed_filenames
    names = compressed_filenames
    
    
    zf1 = sync.download(
        keyring,
        study_id='STUDY_ID',
        participant_ids=['USER_ID'],
        data_streams=['identifiers', 'gps'],
        time_start='2018-06-15T00:00:00',
        time_end='2018-06-17T00:00:00'
    )
    zf2 = sync.download(
        keyring,
        study_id='STUDY_ID',
        participant_ids=['USER_ID'],
        data_streams=['identifiers', 'gps'],
        time_start='2018-06-15T00:00:00',
        time_end='2018-06-17T00:00:00',
        compressed=True,
    )
    
    assert isinstance(zf1, ZipFile)
    assert isinstance(zf2, ZipFile)
    
    names.remove("registry")
    for name in names:
        
        data1 = zf1.read(name)
        data2 = decompress(zf2.read(name+".zst"))
        assert data1 == data2
    
    assert zf1.read("registry") == zf2.read("registry")


def test_download_gps_files(mock_download_v1_api: RequestsMock, keyring: dict[str, str]):
    """Test that download contains the expected GPS files."""
    # Call the download function
    zf = sync.download(
        keyring,
        study_id='STUDY_ID',
        participant_ids=['USER_ID'],
        data_streams=['identifiers', 'gps'],
        time_start='2018-06-15T00:00:00',
        time_end='2018-06-17T00:00:00'
    )
    
    # Get the list of files in the zip (excluding directory entries)
    assert isinstance(zf, ZipFile)
    file_names = [zinfo.filename for zinfo in zf.infolist() if not zinfo.filename.endswith('/')]
    
    # Verify GPS files are present - should have 29 GPS files
    gps_files = [f for f in file_names if 'gps' in f]
    assert len(gps_files) == 29
    
    # Verify date range coverage (June 15-16, 2018)
    assert any('2018-06-15' in f for f in gps_files)
    assert any('2018-06-16' in f for f in gps_files)


def test_download_v1_api_request(mock_download_v1_api: RequestsMock, keyring: dict[str, str]):
    """Test that download makes the correct API request."""
    # Call the download function
    sync.download(
        keyring,
        study_id='STUDY_ID',
        participant_ids=['USER_ID'],
        data_streams=['identifiers', 'gps'],
        time_start='2018-06-15T00:00:00',
        time_end='2018-06-17T00:00:00'
    )
    
    # Verify the API was called correctly
    assert len(mock_download_v1_api.calls) == 1
    request = mock_download_v1_api.calls[0].request
    
    # Check that the request contains expected parameters
    assert isinstance(request.body, str)
    assert 'access_key=ACCESS_KEY' in request.body
    assert 'secret_key=SECRET_KEY' in request.body
    assert 'study_id=STUDY_ID' in request.body
    # the api's user_ids parameter is misnamed, it has been changed to participant_ids in newer
    # backends, but user_ids will not be deprecated on the backend for compatibility.
    assert 'user_ids=USER_ID' in request.body


def test_download_v2_api_request(mock_download_v2_api: RequestsMock, keyring: dict[str, str]):
    """Test that download makes the correct API request."""
    # Call the download function
    sync.download(
        keyring,
        study_id='STUDY_ID',
        participant_ids=['USER_ID'],
        data_streams=['identifiers', 'gps'],
        time_start='2018-06-15T00:00:00',
        time_end='2018-06-17T00:00:00',
        compressed=True,
    )
    
    # Verify the API was called correctly
    assert len(mock_download_v2_api.calls) == 1
    request = mock_download_v2_api.calls[0].request
    
    # Check that the request contains expected parameters
    assert isinstance(request.body, str)
    assert 'access_key=ACCESS_KEY' in request.body
    assert 'secret_key=SECRET_KEY' in request.body
    assert 'study_id=STUDY_ID' in request.body
    # the api's user_ids parameter is misnamed, it has been changed to participant_ids in newer
    # backends, but user_ids will not be deprecated on the backend for compatibility.
    assert 'user_ids=USER_ID' in request.body


def test_download_network_error_during_streaming(keyring: dict[str, str]):
    """Test that download handles network errors during response streaming."""
    with responses.RequestsMock() as rsps:
        # responses library can directly mock connection errors
        rsps.add(
            responses.POST,
            'https://studies.beiwe.org/get-data/v1',
            body=requests.exceptions.ConnectionError("Network connection lost")
        )
        
        with pytest.raises(requests.exceptions.ConnectionError, match="Network connection lost"):
            sync.download(
                keyring,
                study_id='STUDY_ID',
                participant_ids=['USER_ID'],
                data_streams=['identifiers', 'gps'],
                time_start='2018-06-15T00:00:00',
                time_end='2018-06-17T00:00:00'
            )


def test_download_timeout_error(keyring: dict[str, str]):
    """Test that download handles timeout errors."""
    with responses.RequestsMock() as rsps:
        # responses can directly mock timeout exceptions
        rsps.add(
            responses.POST,
            'https://studies.beiwe.org/get-data/v1',
            body=requests.exceptions.Timeout("Request timed out")
        )
        
        with pytest.raises(requests.exceptions.Timeout, match="Request timed out"):
            sync.download(
                keyring,
                study_id='STUDY_ID',
                participant_ids=['USER_ID'],
                data_streams=['identifiers', 'gps'],
                time_start='2018-06-15T00:00:00',
                time_end='2018-06-17T00:00:00'
            )


def test_download_partial_content_then_error(keyring: dict[str, str]):
    """Test download with ChunkedEncodingError."""
    with responses.RequestsMock() as rsps:
        # responses can mock ChunkedEncodingError directly
        rsps.add(
            responses.POST,
            'https://studies.beiwe.org/get-data/v1',
            body=requests.exceptions.ChunkedEncodingError("Connection broken: Invalid chunk encoding")
        )
        
        with pytest.raises(requests.exceptions.ChunkedEncodingError, match="Connection broken"):
            sync.download(
                keyring,
                study_id='STUDY_ID',
                participant_ids=['USER_ID'],
                data_streams=['identifiers', 'gps'],
                time_start='2018-06-15T00:00:00',
                time_end='2018-06-17T00:00:00'
            )


def test_download_http_error(keyring: dict[str, str]):
    """Test download with HTTP error responses."""
    with responses.RequestsMock() as rsps:
        # Test 500 Internal Server Error
        rsps.add(
            responses.POST,
            url := 'https://studies.beiwe.org/get-data/v1',
            status=500,
            body="Internal Server Error"
        )
        
        with pytest.raises(APIError, match=str(NOT_200_OK_ERROR(500, url))):
            sync.download(
                keyring,
                study_id='STUDY_ID',
                participant_ids=['USER_ID'],
                data_streams=['identifiers', 'gps'],
                time_start='2018-06-15T00:00:00',
                time_end='2018-06-17T00:00:00'
            )


def test_download_connection_error(keyring: dict[str, str]):
    """Test download with various connection errors."""
    with responses.RequestsMock() as rsps:
        # Test different types of connection errors
        rsps.add(
            responses.POST,
            'https://studies.beiwe.org/get-data/v1',
            body=requests.exceptions.ConnectionError("Connection refused")
        )
        
        with pytest.raises(requests.exceptions.ConnectionError, match="Connection refused"):
            sync.download(
                keyring,
                study_id='STUDY_ID',
                participant_ids=['USER_ID'],
                data_streams=['identifiers', 'gps'],
                time_start='2018-06-15T00:00:00',
                time_end='2018-06-17T00:00:00'
            )


#
# test backfill function
#

# these helpers make the test code legible....
def default_backfill_kwargs(tmp_path: Path, keyring: dict[str, str]) -> dict:
    return dict(
        compressed=False,
        data_streams=['gps'],
        keyring=keyring,
        lock=[],
        output_dir=str(tmp_path),
        participant_id='6y6s1w4g',
        passphrase=None,
        study_id='STUDY_ID',
        end_date=None,
    )


def default_backfill_download_kwargs(start: datetime, end: datetime) -> dict:
    return {
        "study_id": "STUDY_ID",
        "participant_ids": ["6y6s1w4g"],
        "data_streams": ["gps"],
        "time_start": start,
        "time_end": end,
        "compressed": True,
        "registry": {},
    }


def test_backfill_calls_download(
    mocker: MockerFixture,
    keyring: dict[str, str],
    tmp_path: Path,
    mock_zip_data_compressed: bytes,
):
    """ Test that backfill_participant calls download with correct parameters. """
    mock_download = mocker.patch(
        'mano.sync.download', return_value=ZipFile(BytesIO(mock_zip_data_compressed))
    )
    
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterdt = today - timedelta(days=1)
    
    # one call to yesterday, so the next call will be the default backfill time plus 20 days, so
    # into the future, which should trigger the finish logic
    sync.backfill(
        start_date=yesterdt.date().isoformat(), **default_backfill_kwargs(tmp_path, keyring)
    )
    mock_download.assert_called_once_with(
        keyring,
        **default_backfill_download_kwargs(yesterdt, yesterdt+timedelta(days=20))
    )


def test_backfill_UTC_timezone_stripped_and_no_time_shifting(
    mocker: MockerFixture,
    keyring: dict[str, str],
    tmp_path: Path,
    mock_zip_data_compressed: bytes,
):
    mock_download = mocker.patch(
        'mano.sync.download', return_value=ZipFile(BytesIO(mock_zip_data_compressed))
    )
    
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterdt_utc = today.replace(tzinfo=UTC) - timedelta(days=1)
    yesterdt_no_utc = today - timedelta(days=1)
    
    sync.backfill(
        start_date=yesterdt_utc,
        **default_backfill_kwargs(tmp_path, keyring)
    )
    mock_download.assert_called_once_with(
        keyring,
        **default_backfill_download_kwargs(yesterdt_no_utc, yesterdt_no_utc+timedelta(days=20))
    )


def test_backfill_called_twice(
    mocker: MockerFixture,
    keyring: dict[str, str],
    tmp_path: Path,
    mock_zip_data_compressed: bytes,
):
    """ Test that backfill_participant calls download twice when needed. """
    mock_download = mocker.patch(
        'mano.sync.download', return_value=ZipFile(BytesIO(mock_zip_data_compressed))
    )
    
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    twenty_days_ago_dt = today - timedelta(days=20)
    
    # set it to 5 days ago so two calls are needed to catch up to today
    # backfill_file.write_text(five_days_ago_dt.date().isoformat())
    
    sync.backfill(
        start_date=twenty_days_ago_dt.date().isoformat(),
        **default_backfill_kwargs(tmp_path, keyring)
    )
    
    # assert hits to download look good
    assert mock_download.call_count == 2
    mock_download.assert_any_call(
        keyring,
        **default_backfill_download_kwargs(twenty_days_ago_dt, twenty_days_ago_dt+timedelta(days=20))
    )
    mock_download.assert_any_call(
        keyring,
        **default_backfill_download_kwargs(twenty_days_ago_dt+timedelta(days=20), twenty_days_ago_dt+timedelta(days=40))
    )
    
    # we removed the backfill tracking, it may be replaced by querying the server for data.
    # backfill_file = tmp_path / '6y6s1w4g' / '.backfill'
    # assert backfill_file.read_text() == "COMPLETE"


def test_backfill_makes_no_download_calls_when_up_to_date(
    mocker: MockerFixture,
    keyring: dict[str, str],
    tmp_path: Path,
):
    """ Test that backfill_participant makes no download calls when up to date. """
    mock_download = mocker.patch('mano.sync.download')  # intentionally missing a return_value so it errors.
    tomorrow = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    
    # set it to today so no calls are needed
    sync.backfill(
        start_date=tomorrow.date().isoformat(), **default_backfill_kwargs(tmp_path, keyring)
    )
    mock_download.assert_not_called()
    
    backfill_file = tmp_path / '6y6s1w4g' / '.backfill'
    assert not backfill_file.exists()


def test_junk_backfill_file_is_deleted(
    mocker: MockerFixture,
    keyring: dict[str, str],
    tmp_path: Path,
    mock_zip_data_compressed: bytes,
):
    """ Test that backfill_participant works when there is a bad .backfill file. """
    mock_download = mocker.patch(
        'mano.sync.download', return_value=ZipFile(BytesIO(mock_zip_data_compressed))
    )
    yesterdt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    
    # real old-style backfill files would have nothing useful in them
    backfill_file = tmp_path / '6y6s1w4g' / '.backfill'
    makedirs(backfill_file.parent, exist_ok=True)
    backfill_file.write_text('some invalid date')
    
    # no backfill file, so it should use the start_date parameter
    sync.backfill(
        start_date=yesterdt.date().isoformat(), **default_backfill_kwargs(tmp_path, keyring)
    )
    mock_download.assert_called_once_with(
        keyring,
        **default_backfill_download_kwargs(yesterdt, yesterdt+timedelta(days=20)),
    )
    assert not backfill_file.exists()  # confirm we deleted


def test_old_style_backfill_file_is_ignored(
    mocker: MockerFixture,
    keyring: dict[str, str],
    tmp_path: Path,
    mock_zip_data_compressed: bytes,
):
    """ tests that we ignore the old deprecated backfill file. """
    mock_download = mocker.patch(
        'mano.sync.download', return_value=ZipFile(BytesIO(mock_zip_data_compressed))
    )
    
    # this is from the test that tested whether a backfill file was parsed / overridden
    backfill_file = tmp_path / '6y6s1w4g' / '.backfill'
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    seven_days_ago = today - timedelta(days=7)
    
    makedirs(backfill_file.parent, exist_ok=True)
    backfill_file.write_text(yesterday.isoformat())  # this date results in only one call to download
    
    # set it to today so no calls are needed
    sync.backfill(
        start_date=seven_days_ago.date().isoformat(),  # should be ignored
        **default_backfill_kwargs(tmp_path, keyring)
    )
    mock_download.assert_called_once_with(
        keyring,
        **default_backfill_download_kwargs(seven_days_ago, seven_days_ago+timedelta(days=20)),
    )
    
    assert not backfill_file.exists()  # confirm we deleted


def test_backfill_does_not_overwrite_matching_files_compressed_compressed(
    mocker: MockerFixture,
    keyring: dict[str, str],
    tmp_path: Path,
    mock_zip_data_compressed: bytes,
    mock_zip_data_uncompressed: bytes,
):
    """ The backfill function needs to download _and compare hashes_ if there are file overwrites.
    This test tests when there is a mismatch between whether the files to be extracted from the zip
    file are supposed to come out as compressed (.zst), and  the existing files are compressed. """
    _test_backfill_does_not_overwrite(
        mocker, keyring, tmp_path, mock_zip_data_compressed, mock_zip_data_compressed, True
    )


def test_backfill_does_not_overwrite_matching_files_uncompressed_uncompressed(
    mocker: MockerFixture,
    keyring: dict[str, str],
    tmp_path: Path,
    mock_zip_data_compressed: bytes,
    mock_zip_data_uncompressed: bytes,
):
    """ as test_backfill_does_not_overwrite_matching_files_compressed_compressed, but flip the
    initial data to uncompressed files, and the download with compressed=False to decompress files.
    (Note that backfill always downloads the compressed version.) """
    _test_backfill_does_not_overwrite(
        mocker, keyring, tmp_path, mock_zip_data_uncompressed, mock_zip_data_compressed, False
    )


def _test_backfill_does_not_overwrite(
    mocker: MockerFixture,
    keyring: dict[str, str],
    tmp_path: Path,
    data_to_decompress: bytes,
    mock_zip_data_compressed: bytes,
    compression_parameter: bool
):
    """ WOW FUN FACT - WANDOWS CAN'T DO FILE CREATION TIME PROPERLY SO THIS TEST GETS SLEEP STATEMENTS """
    
    target_folder = tmp_path / "target_folder"
    gps_path = target_folder / "6y6s1w4g" / "gps"
    identifiers_path = target_folder / "6y6s1w4g" / "identifiers"
    
    with ZipFile(BytesIO(data_to_decompress)) as zf:
        zf.extractall(target_folder)
    delete_file(target_folder / "registry")  # we don't want it in this current implementation
    
    # inserting sleeps for 0.02 seconds either side so that fs timestamps differ enough to be detected
    sleep(1/50)
    between_creation_and_potential_update = datetime.now().timestamp()
    sleep(1/50)
    
    # (tmp_path / "registry").
    _ = mocker.patch('mano.sync.download', return_value=ZipFile(BytesIO(mock_zip_data_compressed)))
    
    gps_list = listdir(gps_path)
    identifiers_list = listdir(identifiers_path)
    
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    sync.backfill(
        start_date=yesterday.date().isoformat(),
        **{
            **default_backfill_kwargs(tmp_path, keyring),
            "output_dir": str(target_folder),
            "compressed": compression_parameter,
        },
    )
    
    # file list in this case should be unchanged
    assert gps_list == listdir(gps_path)
    assert identifiers_list == listdir(identifiers_path)
    
    # This is how you test files were not modified or overwritten:
    # ctime is creation time, mtime is modified time
    for a_path in gps_list + identifiers_list:
        p = (gps_path / a_path)
        ctime = p.stat().st_ctime
        mtime = p.stat().st_mtime
        assert ctime <= between_creation_and_potential_update
        assert mtime <= between_creation_and_potential_update


#
# Test Type Validation for download
#

# keyring: dict[str, str]
# study_id: str
# participant_ids: list[str] | None = None
# data_streams: list[str] | None = None
# time_start: str | datetime | None = None
# time_end: str | datetime | None = None
# registry: dict[str, str] | None = None
# compressed: bool = False
# progress: int = 0
# user_ids: list[str] | None = None


def test_download_type_validation_raises_on_bad_types(
    keyring: dict[str, str], mocker: MockerFixture
):
    mocker.patch('mano.sync._download')  # prevent actual download
    
    with pytest.raises(TypeError, match=".*keyring.*dict.*"):
        sync.download(
            keyring='not a dict',  # type: ignore
            study_id='STUDY_ID',
        )
    with pytest.raises(TypeError, match=".*study_id.*str.*"):
        sync.download(
            keyring=keyring,
            study_id=12345,  # type: ignore
        )
    with pytest.raises(TypeError, match=".*participant_ids.*list.*"):
        sync.download(
            keyring=keyring,
            study_id='STUDY_ID',
            participant_ids=12345,  # type: ignore
        )
    with pytest.raises(TypeError, match=".*data_streams.*list.*"):
        sync.download(
            keyring=keyring,
            study_id='STUDY_ID',
            data_streams='not a list',  # type: ignore
        )
    with pytest.raises(TypeError, match=".*time_start.*datetime.*"):
        sync.download(
            keyring=keyring,
            study_id='STUDY_ID',
            time_start=12345,  # type: ignore
        )
    with pytest.raises(TypeError, match=".*time_end.*datetime.*"):
        sync.download(
            keyring=keyring,
            study_id='STUDY_ID',
            time_end=12345,  # type: ignore
        )
    with pytest.raises(TypeError, match=".*registry.*dict.*"):
        sync.download(
            keyring=keyring,
            study_id='STUDY_ID',
            registry='not a dict',  # type: ignore
        )
    with pytest.raises(TypeError, match=".*compressed.*bool.*"):
        sync.download(
            keyring=keyring,
            study_id='STUDY_ID',
            compressed='not a bool',  # type: ignore
        )
    with pytest.raises(TypeError, match=".*progress.*int.*"):
        sync.download(
            keyring=keyring,
            study_id='STUDY_ID',
            progress='not an int',  # type: ignore
        )
    with pytest.raises(TypeError, match=".*user_ids.*list.*"):
        sync.download(
            keyring=keyring,
            study_id='STUDY_ID',
            user_ids=12345,  # type: ignore
        )


def test_download_type_validation_passes_on_good_types(keyring: dict[str, str], mocker: MockerFixture):
    mocker.patch('mano.sync._download')  # prevent actual download
    
    # should not raise
    sync.download(
        keyring=keyring,
        study_id='STUDY_ID',
        participant_ids=['USER_ID'],
        data_streams=['gps'],
        time_start='2018-06-15T00:00:00',
        time_end='2018-06-17T00:00:00',
        registry={'some_file': 'some_hash'},
        compressed=True,
        progress=1,
        # user_ids=['USER_ID'],
    )
    # can't have both participant_ids and user_ids
    sync.download(
        keyring=keyring,
        study_id='STUDY_ID',
        # participant_ids=['USER_ID'],
        data_streams=['gps'],
        time_start='2018-06-15T00:00:00',
        time_end='2018-06-17T00:00:00',
        registry={'some_file': 'some_hash'},
        compressed=True,
        progress=1,
        user_ids=['USER_ID'],
    )


def test_download_single_user_string_works(keyring: dict[str, str], mocker: MockerFixture):
    """Test that download works when a single participant ID string is provided."""
    dl = mocker.patch("mano.sync._download")
    # Call the download function with a single string participant ID
    time_start = datetime(2018, 6, 15, 0, 0, 0, tzinfo=UTC)
    time_end = datetime(2018, 6, 17, 0, 0, 0, tzinfo=UTC)
    _zf = sync.download(
        keyring,
        study_id='STUDY_ID',
        participant_ids='USER_ID',
        data_streams=['identifiers', 'gps'],
        time_start=time_start,
        time_end=time_end,
    )
    
    dl.assert_called_once_with(
        keyring, 'STUDY_ID', False, ['identifiers', 'gps'], {}, time_start, time_end, ['USER_ID']
    )


def test_download_two_user_string_works(keyring: dict[str, str], mocker: MockerFixture):
    """Test that download works when a single participant ID string is provided."""
    dl = mocker.patch("mano.sync._download")
    # Call the download function with a single string participant ID
    time_start = datetime(2018, 6, 15, 0, 0, 0, tzinfo=UTC)
    time_end = datetime(2018, 6, 17, 0, 0, 0, tzinfo=UTC)
    _zf = sync.download(
        keyring,
        study_id='STUDY_ID',
        participant_ids='USER_ID,user_id',
        data_streams=['identifiers', 'gps'],
        time_start=time_start,
        time_end=time_end
    )
    dl.assert_called_once_with(
        keyring,
        'STUDY_ID',
        False,
        ['identifiers', 'gps'],
        {},
        time_start,
        time_end,
        ['USER_ID', 'user_id'],
    )


def test_download_non_type_error_validation(keyring: dict[str, str]):
    
    # can't have both participant_ids and user_ids
    with pytest.raises(ValueError, match=".*you cannot provide both\\.$"):
        sync.download(
            keyring=keyring,
            study_id='STUDY_ID',
            participant_ids=['USER_ID'],
            user_ids=['USER_ID'],
        )
    
    # bad data stream
    with pytest.raises(ValueError, match=".*invalid.*random_stream.*"):
        sync.download(
            keyring=keyring,
            study_id='STUDY_ID',
            participant_ids=['USER_ID'],
            data_streams=['gps', 'random_stream'],
        )
    
    # end time before start time
    with pytest.raises(sync.DownloadError, match=".*is after end_time.*"):
        sync.download(
            keyring=keyring,
            study_id='STUDY_ID',
            participant_ids=['USER_ID'],
            time_start='2018-06-17T00:00:00',
            time_end='2018-06-15T00:00:00',
        )
    
    # unparsable time_start
    with pytest.raises(UnParsableTimeError, match=".*could not parse time string.*"):
        sync.download(
            keyring=keyring,
            study_id='STUDY_ID',
            participant_ids=['USER_ID'],
            time_start='not a date',
        )
    # unparsable time_end
    with pytest.raises(UnParsableTimeError, match=".*could not parse time string.*"):
        sync.download(
            keyring=keyring,
            study_id='STUDY_ID',
            participant_ids=['USER_ID'],
            time_end='not a date',
        )


# keyring: dict[str, str]
# study_id: str
# participant_id: str
# output_dir: str
# start_date: str | datetime = EARLIEST_POSSIBLE_DATA_DT
# data_streams: list[str] | None = None
# lock: list[str] | None = None
# passphrase: str | None = None
# user_id: str | None = None


def test_backfill_type_validation_raises_on_bad_types(mocker: MockerFixture):
    mocker.patch('mano.sync._download')  # prevent actual download
    start_date = datetime(2024, 7, 30)
    
    with pytest.raises(TypeError, match=".*keyring.*dict.*"):
        sync.backfill(
            keyring="not a dict",  # type: ignore
            study_id="STUDY_ID",
            participant_id="USER_ID",
            output_dir="/tmp",
            start_date=start_date,
        )
    with pytest.raises(TypeError, match=".*study_id.*str.*"):
        sync.backfill(
            keyring={},
            study_id=12345,  # type: ignore
            participant_id="USER_ID",
            output_dir="/tmp",
            start_date=start_date,
        )
    with pytest.raises(TypeError, match=".*participant_id.*str.*"):
        sync.backfill(
            keyring={},
            study_id="STUDY_ID",
            participant_id=12345,  # type: ignore
            output_dir="/tmp",
            start_date=start_date,
        )
    with pytest.raises(TypeError, match=".*output_dir.*str.*"):
        sync.backfill(
            keyring={},
            study_id="STUDY_ID",
            participant_id="USER_ID",
            output_dir=12345,  # type: ignore
            start_date=start_date,
        )
    with pytest.raises(TypeError, match=".*start_date.*datetime.*"):
        sync.backfill(
            keyring={},
            study_id="STUDY_ID",
            participant_id="USER_ID",
            output_dir="/tmp",
            start_date=12345,  # type: ignore
        )
    with pytest.raises(TypeError, match=".*data_streams.*list.*"):
        sync.backfill(
            keyring={},
            study_id="STUDY_ID",
            participant_id="USER_ID",
            output_dir="/tmp",
            data_streams="not a list",  # type: ignore
            start_date=start_date,
        )
    with pytest.raises(TypeError, match=".*lock.*list.*"):
        sync.backfill(
            keyring={},
            study_id="STUDY_ID",
            participant_id="USER_ID",
            output_dir="/tmp",
            start_date=start_date,
            lock="not a list",  # type: ignore
            passphrase="aoeustaoeu"  # passphrase is required if lock is used
        )
    with pytest.raises(TypeError, match=".*passphrase.*str.*"):
        sync.backfill(
            keyring={},
            study_id="STUDY_ID",
            participant_id="USER_ID",
            output_dir="/tmp",
            start_date=start_date,
            passphrase=12345,  # type: ignore
            lock=["gps"]  # lock is required if passphrase is used
        )
    with pytest.raises(TypeError, match=".*user_id.*str.*"):
        sync.backfill(
            keyring={},
            study_id="STUDY_ID",
            participant_id="USER_ID",
            output_dir="/tmp",
            user_id=12345,  # type: ignore
            start_date=start_date,
        )


def test_backfill_type_validation_passes_on_good_types(keyring: dict[str, str], mocker: MockerFixture, tmp_path: Path):
    mocker.patch("mano.sync._backfill_participant")  # prevent actual download
    
    # should not raise
    sync.backfill(
        keyring=keyring,
        study_id="STUDY_ID",
        participant_id="USER_ID",
        output_dir=str(tmp_path),
        start_date="2018-06-15T00:00:00",
        data_streams=["gps"],
        lock=["gps"],
        passphrase="some_passphrase",
        # user_id="USER_ID",
    )
    # cannot have both participant_id and user_id
    sync.backfill(
        keyring=keyring,
        study_id="STUDY_ID",
        participant_id=None,  # type: ignore #      have to set to None, it is a positional arg
        output_dir=str(tmp_path),
        start_date="2018-06-15T00:00:00",
        data_streams=["gps"],
        lock=["gps"],
        passphrase="some_passphrase",
        user_id="USER_ID",
    )


def test_backfill_allows_dates(keyring: dict[str, str], mocker: MockerFixture, tmp_path: Path):
    mocker.patch("mano.sync._backfill_participant")  # prevent actual download
    sync.backfill(
        keyring=keyring,
        study_id="STUDY_ID",
        participant_id="USER_ID",
        output_dir=str(tmp_path),
        start_date=date(2018, 6, 15),
        data_streams=["gps"],
        lock=["gps"],
        passphrase="some_passphrase",
    )
    
    # date-strings
    sync.backfill(
        keyring=keyring,
        study_id="STUDY_ID",
        participant_id="USER_ID",
        output_dir=str(tmp_path),
        start_date="2018-06-15",
        data_streams=["gps"],
        lock=["gps"],
        passphrase="some_passphrase",
        # user_id="USER_ID",
    )


def test_backfill_non_type_error_validation(keyring: dict[str, str], tmp_path: Path):
    start_date = datetime(2018, 6, 15)
    # cannot have both participant_id and user_id
    with pytest.raises(ValueError, match=".*you cannot provide both\\.$"):
        sync.backfill(
            keyring=keyring,
            study_id="STUDY_ID",
            start_date=start_date,
            participant_id="USER_ID",
            output_dir=str(tmp_path),
            user_id="USER_ID",
        )
    
    # passphrase without lock
    with pytest.raises(ValueError, match=".*parameter cannot be empty if `passphrase`.*"):
        sync.backfill(
            keyring=keyring,
            study_id="STUDY_ID",
            start_date=start_date,
            participant_id="USER_ID",
            output_dir=str(tmp_path),
            passphrase="some_passphrase",
        )
    
    # lock without passphrase
    with pytest.raises(ValueError, match=".*parameter cannot be empty if `lock`.*"):
        sync.backfill(
            keyring=keyring,
            study_id="STUDY_ID",
            start_date=start_date,
            participant_id="USER_ID",
            output_dir=str(tmp_path),
            lock=["gps"],
        )
    
    # invalid data stream in lock
    with pytest.raises(ValueError, match="backfill - `lock` - invalid data streams:.*random_stream.*"):
        sync.backfill(
            keyring=keyring,
            study_id="STUDY_ID",
            start_date=start_date,
            participant_id="USER_ID",
            output_dir=str(tmp_path),
            lock=["gps", "random_stream"],
            passphrase="some_passphrase",
        )
    
    # invalid data stream in data_streams
    with pytest.raises(ValueError, match="backfill - `data_streams` - invalid data streams:.*random_stream.*"):
        sync.backfill(
            keyring=keyring,
            study_id="STUDY_ID",
            start_date=start_date,
            participant_id="USER_ID",
            output_dir=str(tmp_path),
            data_streams=["gps", "random_stream"],
        )
    
    # empty start_date string
    with pytest.raises(ValueError, match=".*`start_date` and `end_date` parameters cannot be empty.*"):
        sync.backfill(
            keyring=keyring,
            study_id="STUDY_ID",
            participant_id="USER_ID",
            output_dir=str(tmp_path),
            start_date="",
        )


def test_backfill__future_does_not_call_backfill_participant(
    mocker: MockerFixture, tmp_path: Path, keyring: dict[str, str]
):
    """ Test that backfill_participant makes no download calls when start_date is in the future. """
    mock_backfill_participant = mocker.patch('mano.sync._backfill_participant')  # prevent actual download
    tomorrow = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=5)
    sync.backfill(
        keyring=keyring,
        study_id="STUDY_ID",
        participant_id="USER_ID",
        output_dir=str(tmp_path),
        start_date=tomorrow,
    )
    mock_backfill_participant.assert_not_called()


def test_backfill_end_date_before_start_date_raises(
    mocker: MockerFixture, tmp_path: Path, keyring: dict[str, str]
):
    """ Test that backfill raises when end_date is before start_date. """
    mock_backfill_participant = mocker.patch('mano.sync._backfill_participant')  # prevent actual download
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    with pytest.raises(ValueError, match=".*must come after.*"):
        sync.backfill(
            keyring=keyring,
            study_id="STUDY_ID",
            participant_id="USER_ID",
            output_dir=str(tmp_path),
            start_date=today,
            end_date=yesterday,
        )
    
    # and the equality case
    with pytest.raises(ValueError, match=".*must come after.*"):
        sync.backfill(
            keyring=keyring,
            study_id="STUDY_ID",
            participant_id="USER_ID",
            output_dir=str(tmp_path),
            start_date=today,
            end_date=today,
        )
    mock_backfill_participant.assert_not_called()

#
# test backfill hashing and file management components
#

# TODO: we need to support `2024-02-16 09_00_00+00_00.csv` and `2024-02-16 09_00_00.csv` file paths
#   but always convert to +00_00


def setup_file_paths_components(tmp_path: Path) -> tuple[Path, ...]:
    """ Sets up every folder path we might need for the tests. """
    study_path = tmp_path / STUDY_ID
    participant_path = study_path / PARTICIPANT_ID
    stream_path = participant_path / DATA_STREAM_FOLDER
    fp_uncompr = stream_path / DATA_STREAM_FILE
    fp_compr = stream_path / (DATA_STREAM_FILE + ".zst")
    fp_encr = stream_path / (DATA_STREAM_FILE + ".lock")
    fp_encr_compr = stream_path / (DATA_STREAM_FILE + ".zst.lock")
    # always make the folder exist...
    stream_path.mkdir(parents=True, exist_ok=True)
    
    return study_path, participant_path, stream_path, fp_uncompr, fp_compr, fp_encr, fp_encr_compr


def test_generate_registry_hashes_no_files(tmp_path: Path):
    study_path, participant_path, stream_path, fp_uncompr, fp_compr, fp_encr, fp_encr_compr = \
        setup_file_paths_components(tmp_path)
    remote_hashes, local_hashes = sync.generate_registry_info(
        str(tmp_path),
        study_id=STUDY_ID,
        participant_id=PARTICIPANT_ID,
        passphrase=None,
    )
    assert remote_hashes == {}
    assert local_hashes == {}


def test_generate_registry_hashes_uncompressed_unencrypted(tmp_path: Path):
    study_path, participant_path, stream_path, fp_uncompr, fp_compr, fp_encr, fp_encr_compr = \
        setup_file_paths_components(tmp_path)
    
    fp_uncompr.write_bytes(FILE_CONTENT_UNCOMPRESSED)
    remote_hashes, local_hashes = sync.generate_registry_info(
        str(tmp_path),
        study_id=STUDY_ID,
        participant_id=PARTICIPANT_ID,
        passphrase=None,
    )
    
    assert remote_hashes == {NORMALIZED_FILE_PATH: FILE_SHA1_HASH_STRING}
    assert local_hashes == {LOCAL_PATH_REFERENCE: FILE_SHA1_HASH_BYTES}


def test_generate_registry_hashes_compressed_unencrypted(tmp_path: Path):
    study_path, participant_path, stream_path, fp_uncompr, fp_compr, fp_encr, fp_encr_compr = \
        setup_file_paths_components(tmp_path)
    
    fp_compr.write_bytes(FILE_CONTENT_COMPRESSED)
    remote_hashes, local_hashes = sync.generate_registry_info(
        str(tmp_path),
        study_id=STUDY_ID,
        participant_id=PARTICIPANT_ID,
        passphrase=None,
    )
    
    assert remote_hashes == {NORMALIZED_FILE_PATH: FILE_SHA1_HASH_STRING}
    assert local_hashes == {LOCAL_PATH_REFERENCE: FILE_SHA1_HASH_BYTES}


def test_generate_registry_hashes_uncompressed_encrypted(tmp_path: Path):
    study_path, participant_path, stream_path, fp_uncompr, fp_compr, fp_encr, fp_encr_compr = \
        setup_file_paths_components(tmp_path)
    
    fp_encr.write_bytes(FILE_CONTENT_ENCRYPTED_UNCOMPRESSED)
    remote_hashes, local_hashes = sync.generate_registry_info(
        str(tmp_path),
        study_id=STUDY_ID,
        participant_id=PARTICIPANT_ID,
        passphrase=PASSPHRASE_STRING,
    )
    
    assert remote_hashes == {NORMALIZED_FILE_PATH: FILE_SHA1_HASH_STRING}
    assert local_hashes == {LOCAL_PATH_REFERENCE: FILE_SHA1_HASH_BYTES}


def test_generate_registry_hashes_compressed_encrypted(tmp_path: Path):
    study_path, participant_path, stream_path, fp_uncompr, fp_compr, fp_encr, fp_encr_compr = \
        setup_file_paths_components(tmp_path)
    
    fp_encr_compr.write_bytes(FILE_CONTENT_ENCRYPTED_COMPRESSED)
    remote_hashes, local_hashes = sync.generate_registry_info(
        str(tmp_path),
        study_id=STUDY_ID,
        participant_id=PARTICIPANT_ID,
        passphrase=PASSPHRASE_STRING,
    )
    
    assert remote_hashes == {NORMALIZED_FILE_PATH: FILE_SHA1_HASH_STRING}
    assert local_hashes == {LOCAL_PATH_REFERENCE: FILE_SHA1_HASH_BYTES}


def test_generate_registry_hashes_mixed_files(tmp_path: Path):
    study_path, participant_path, stream_path, fp_uncompr, fp_compr, fp_encr, fp_encr_compr = \
        setup_file_paths_components(tmp_path)
    fp_uncompr.write_bytes(FILE_CONTENT_UNCOMPRESSED)
    fp_compr.write_bytes(FILE_CONTENT_COMPRESSED)
    fp_encr.write_bytes(FILE_CONTENT_ENCRYPTED_UNCOMPRESSED)
    fp_encr_compr.write_bytes(FILE_CONTENT_ENCRYPTED_COMPRESSED)
    remote_hashes, local_hashes = sync.generate_registry_info(
        str(tmp_path),
        study_id=STUDY_ID,
        participant_id=PARTICIPANT_ID,
        passphrase=PASSPHRASE_STRING,
    )
    
    # TODO: this should probably detect this case and emit a warning rather than overwriting...
    assert remote_hashes == {NORMALIZED_FILE_PATH: FILE_SHA1_HASH_STRING}
    assert local_hashes == {LOCAL_PATH_REFERENCE: FILE_SHA1_HASH_BYTES}
