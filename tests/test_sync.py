"""
Tests for mano.sync module download functionality.
"""
import zipfile

import pytest
import requests
import responses

import mano.sync


def test_download_returns_zipfile(mock_download_api, keyring):
    """Test that download function returns a ZipFile object."""
    # Call the download function
    zf = mano.sync.download(keyring,
                            study_id='STUDY_ID',
                            user_ids=['USER_ID'],
                            data_streams=['identifiers', 'gps'],
                            time_start='2018-06-15T00:00:00',
                            time_end='2018-06-17T00:00:00')

    # Check that we got a ZipFile object
    assert isinstance(zf, zipfile.ZipFile)


def test_download_file_count(mock_download_api, keyring):
    """Test that download returns the expected number of files."""
    # Call the download function
    zf = mano.sync.download(keyring,
                            study_id='STUDY_ID',
                            user_ids=['USER_ID'],
                            data_streams=['identifiers', 'gps'],
                            time_start='2018-06-15T00:00:00',
                            time_end='2018-06-17T00:00:00')

    # Get the list of files in the zip (excluding directory entries)
    file_names = [zinfo.filename for zinfo in zf.infolist()
                  if not zinfo.filename.endswith('/')]

    # Verify we have the expected total number of files
    # (29 GPS + 1 identifier + 1 registry = 31)
    assert len(file_names) == 31


def test_download_contains_expected_files_with_correct_crcs(
        mock_download_api, keyring, expected_download_files):
    """Test download contains expected files with correct CRC values from
    original data."""
    # Call the download function
    zf = mano.sync.download(keyring,
                            study_id='STUDY_ID',
                            user_ids=['USER_ID'],
                            data_streams=['identifiers', 'gps'],
                            time_start='2018-06-15T00:00:00',
                            time_end='2018-06-17T00:00:00')

    # Get the actual files and their CRC values from the zip
    actual_files = {(zinfo.filename, zinfo.CRC) for zinfo in zf.infolist()}

    # Filter actual files to only include expected ones (excludes directories)
    filtered_actual_files = {
        (filename, crc) for filename, crc in actual_files
        if filename in {f for f, _ in expected_download_files}
    }

    # Verify that the CRC values match exactly
    assert filtered_actual_files == expected_download_files


def test_download_gps_files(mock_download_api, keyring):
    """Test that download contains the expected GPS files."""
    # Call the download function
    zf = mano.sync.download(keyring,
                            study_id='STUDY_ID',
                            user_ids=['USER_ID'],
                            data_streams=['identifiers', 'gps'],
                            time_start='2018-06-15T00:00:00',
                            time_end='2018-06-17T00:00:00')

    # Get the list of files in the zip (excluding directory entries)
    file_names = [zinfo.filename for zinfo in zf.infolist()
                  if not zinfo.filename.endswith('/')]

    # Verify GPS files are present - should have 29 GPS files
    gps_files = [f for f in file_names if 'gps' in f]
    assert len(gps_files) == 29

    # Verify date range coverage (June 15-16, 2018)
    assert any('2018-06-15' in f for f in gps_files)
    assert any('2018-06-16' in f for f in gps_files)


def test_download_api_request(mock_download_api, keyring):
    """Test that download makes the correct API request."""
    # Call the download function
    mano.sync.download(keyring,
                       study_id='STUDY_ID',
                       user_ids=['USER_ID'],
                       data_streams=['identifiers', 'gps'],
                       time_start='2018-06-15T00:00:00',
                       time_end='2018-06-17T00:00:00')

    # Verify the API was called correctly
    assert len(mock_download_api.calls) == 1
    request = mock_download_api.calls[0].request

    # Check that the request contains expected parameters
    assert 'access_key=ACCESS_KEY' in request.body
    assert 'secret_key=SECRET_KEY' in request.body
    assert 'study_id=STUDY_ID' in request.body
    assert 'user_ids=USER_ID' in request.body


def test_download_network_error_during_streaming(keyring):
    """Test that download handles network errors during response streaming."""
    with responses.RequestsMock() as rsps:
        # responses library can directly mock connection errors
        rsps.add(
            responses.POST,
            'https://studies.beiwe.org/get-data/v1',
            body=requests.exceptions.ConnectionError("Network connection lost")
        )

        with pytest.raises(requests.exceptions.ConnectionError,
                           match="Network connection lost"):
            mano.sync.download(keyring,
                               study_id='STUDY_ID',
                               user_ids=['USER_ID'],
                               data_streams=['identifiers', 'gps'],
                               time_start='2018-06-15T00:00:00',
                               time_end='2018-06-17T00:00:00')


def test_download_timeout_error(keyring):
    """Test that download handles timeout errors."""
    with responses.RequestsMock() as rsps:
        # responses can directly mock timeout exceptions
        rsps.add(
            responses.POST,
            'https://studies.beiwe.org/get-data/v1',
            body=requests.exceptions.Timeout("Request timed out")
        )

        with pytest.raises(requests.exceptions.Timeout,
                           match="Request timed out"):
            mano.sync.download(
                keyring,
                study_id='STUDY_ID',
                user_ids=['USER_ID'],
                data_streams=['identifiers', 'gps'],
                time_start='2018-06-15T00:00:00',
                time_end='2018-06-17T00:00:00'
            )


def test_download_partial_content_then_error(keyring):
    """Test download with ChunkedEncodingError."""
    with responses.RequestsMock() as rsps:
        # responses can mock ChunkedEncodingError directly
        rsps.add(
            responses.POST,
            'https://studies.beiwe.org/get-data/v1',
            body=requests.exceptions.ChunkedEncodingError(
                "Connection broken: Invalid chunk encoding"
            )
        )

        with pytest.raises(requests.exceptions.ChunkedEncodingError,
                           match="Connection broken"):
            mano.sync.download(
                keyring,
                study_id='STUDY_ID',
                user_ids=['USER_ID'],
                data_streams=['identifiers', 'gps'],
                time_start='2018-06-15T00:00:00',
                time_end='2018-06-17T00:00:00'
            )


def test_download_http_error(keyring):
    """Test download with HTTP error responses."""
    with responses.RequestsMock() as rsps:
        # Test 500 Internal Server Error
        rsps.add(
            responses.POST,
            'https://studies.beiwe.org/get-data/v1',
            status=500,
            body="Internal Server Error"
        )

        with pytest.raises(mano.sync.APIError,
                           match="response not ok \\(500\\)"):
            mano.sync.download(
                keyring,
                study_id='STUDY_ID',
                user_ids=['USER_ID'],
                data_streams=['identifiers', 'gps'],
                time_start='2018-06-15T00:00:00',
                time_end='2018-06-17T00:00:00'
            )


def test_download_connection_error(keyring):
    """Test download with various connection errors."""
    with responses.RequestsMock() as rsps:
        # Test different types of connection errors
        rsps.add(
            responses.POST,
            'https://studies.beiwe.org/get-data/v1',
            body=requests.exceptions.ConnectionError("Connection refused")
        )

        with pytest.raises(requests.exceptions.ConnectionError,
                           match="Connection refused"):
            mano.sync.download(
                keyring,
                study_id='STUDY_ID',
                user_ids=['USER_ID'],
                data_streams=['identifiers', 'gps'],
                time_start='2018-06-15T00:00:00',
                time_end='2018-06-17T00:00:00'
            )
