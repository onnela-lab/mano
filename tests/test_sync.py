from datetime import datetime, timedelta
from io import BytesIO
from os import makedirs
from pathlib import Path
from zipfile import ZipFile

import pytest
import requests
import responses
from pytest_mock import MockerFixture
from pyzstd import decompress
from responses import RequestsMock

from mano import sync
from mano.constants import APIError
from mano.messages import NOT_200_OK_MSG


def test_download_returns_zipfile(mock_download_v1_api: RequestsMock, keyring: dict[str, str]):
    """Test that download function returns a ZipFile object."""
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
    # Just test that it doesn't crash, if we later have further infratructure duplicate a separate test
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
        
        with pytest.raises(APIError, match=NOT_200_OK_MSG(500, url)):
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


def test_backfill_calls_download(
    mocker: MockerFixture,
    keyring: dict[str, str],
    tmp_path: Path,
    mock_zip_data_uncompressed: bytes,
):
    """ Test that backfill_participant calls download with correct paraeters. """
    backfill_file = tmp_path / '.backfill'
    mock_download = mocker.patch(
        'mano.sync.download', return_value=ZipFile(BytesIO(mock_zip_data_uncompressed))
    )
    _ = mocker.patch('mano.sync.sleep')  # otherwise there is a sleep
    
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterdt = today - timedelta(days=1)
    
    # one call to yesterday, so the next call will be the default backfill time plus five days, so
    # into the future, which should trigger the finish logic
    backfill_file.write_text(today.date().isoformat())
    sync.backfill(
        Keyring=keyring,
        study_id='STUDY_ID',
        participant_id='6y6s1w4g',
        output_dir=str(tmp_path),
        start_date=yesterdt.date().isoformat(),
        data_streams=['gps'],
        lock=[],
        passphrase=None,
    )
    mock_download.assert_called_once_with(
        keyring,
        'STUDY_ID',
        ['6y6s1w4g'],
        ['gps'],
        time_start=yesterdt.isoformat(),
        time_end=(yesterdt+timedelta(days=5)).isoformat(),
    )


def test_backfill_called_twice(
    mocker: MockerFixture,
    keyring: dict[str, str],
    tmp_path: Path,
    mock_zip_data_uncompressed: bytes,
):
    """ Test that backfill_participant calls download twice when needed. """
    mock_download = mocker.patch(
        'mano.sync.download', return_value=ZipFile(BytesIO(mock_zip_data_uncompressed))
    )
    _ = mocker.patch('mano.sync.sleep')  # otherwise there is a sleep
    
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    five_days_ago_dt = today - timedelta(days=5)
    
    # set it to 5 days ago so two calls are needed to catch up to today
    # backfill_file.write_text(five_days_ago_dt.date().isoformat())
    
    sync.backfill(
        Keyring=keyring,
        study_id='STUDY_ID',
        participant_id='6y6s1w4g',
        output_dir=str(tmp_path),
        start_date=five_days_ago_dt.date().isoformat(),
        data_streams=['gps'],
        lock=[],
        passphrase=None,
    )
    
    # assert hits to download look good
    assert mock_download.call_count == 2
    mock_download.assert_any_call(
        keyring,
        'STUDY_ID',
        ['6y6s1w4g'],
        ['gps'],
        time_start=five_days_ago_dt.isoformat(),
        time_end=(five_days_ago_dt + timedelta(days=5)).isoformat(),
    )
    mock_download.assert_any_call(
        keyring,
        'STUDY_ID',
        ['6y6s1w4g'],
        ['gps'],
        time_start=(five_days_ago_dt+timedelta(days=5)).isoformat(),
        time_end=(five_days_ago_dt+timedelta(days=10)).isoformat(),
    )
    
    backfill_file = tmp_path / '6y6s1w4g' / '.backfill'
    assert backfill_file.read_text() == "COMPLETE"


def test_backfill_makes_no_download_calls_when_up_to_date(
    mocker: MockerFixture,
    keyring: dict[str, str],
    tmp_path: Path,
):
    """ Test that backfill_participant makes no download calls when up to date. """
    backfill_file = tmp_path / '6y6s1w4g' / '.backfill'
    mock_download = mocker.patch('mano.sync.download')  # intentionally missing a return_value so it errors.
    _ = mocker.patch('mano.sync.sleep')  # otherwise there is a sleep
    tomorrow = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    
    # set it to today so no calls are needed
    sync.backfill(
        Keyring=keyring,
        study_id='STUDY_ID',
        participant_id='6y6s1w4g',
        output_dir=str(tmp_path),
        start_date=tomorrow.date().isoformat(),
        data_streams=['gps'],
        lock=[],
        passphrase=None,
    )
    mock_download.assert_not_called()
    assert not backfill_file.exists()


def test_backfill_does_not_crash_when_there_is_a_backfill_file(
    mocker: MockerFixture,
    keyring: dict[str, str],
    tmp_path: Path,
    mock_zip_data_uncompressed: bytes,
):
    """ Test that backfill_participant works when there is no .backfill file. """
    mock_download = mocker.patch(
        'mano.sync.download', return_value=ZipFile(BytesIO(mock_zip_data_uncompressed))
    )
    _ = mocker.patch('mano.sync.sleep')  # otherwise there is a sleep
    yesterdt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    
    backfill_file = tmp_path / '6y6s1w4g' / '.backfill'
    makedirs(backfill_file.parent, exist_ok=True)
    backfill_file.write_text('some invalid date')
    
    # no backfill file, so it should use the start_date parameter
    sync.backfill(
        Keyring=keyring,
        study_id='STUDY_ID',
        participant_id='6y6s1w4g',
        output_dir=str(tmp_path),
        start_date=yesterdt.date().isoformat(),
        data_streams=['gps'],
        lock=[],
        passphrase=None,
    )
    mock_download.assert_called_once_with(
        keyring,
        'STUDY_ID',
        ['6y6s1w4g'],
        ['gps'],
        time_start=yesterdt.isoformat(),
        time_end=(yesterdt+timedelta(days=5)).isoformat(),
    )
    assert backfill_file.read_text() == "COMPLETE"
