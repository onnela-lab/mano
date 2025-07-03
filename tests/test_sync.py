"""
Tests for mano.sync module download functionality.
"""
import zipfile

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

    # Get the list of files in the zip
    file_names = [zinfo.filename for zinfo in zf.infolist()]

    # Verify we have the expected total number of files
    # (29 GPS + 1 identifier + 1 registry = 31)
    assert len(file_names) == 31


def test_download_contains_expected_files(mock_download_api, keyring):
    """Test that download contains expected identifier and registry files."""
    # Call the download function
    zf = mano.sync.download(keyring,
                            study_id='STUDY_ID',
                            user_ids=['USER_ID'],
                            data_streams=['identifiers', 'gps'],
                            time_start='2018-06-15T00:00:00',
                            time_end='2018-06-17T00:00:00')

    # Get the list of files in the zip
    file_names = [zinfo.filename for zinfo in zf.infolist()]

    # Verify expected files are present
    expected_files = [
        '6y6s1w4g/identifiers/2018-06-15 16_00_00.csv',
        'registry'
    ]

    for expected_file in expected_files:
        assert expected_file in file_names


def test_download_gps_files(mock_download_api, keyring):
    """Test that download contains the expected GPS files."""
    # Call the download function
    zf = mano.sync.download(keyring,
                            study_id='STUDY_ID',
                            user_ids=['USER_ID'],
                            data_streams=['identifiers', 'gps'],
                            time_start='2018-06-15T00:00:00',
                            time_end='2018-06-17T00:00:00')

    # Get the list of files in the zip
    file_names = [zinfo.filename for zinfo in zf.infolist()]

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
    body = request.body.decode('utf-8')
    assert 'access_key=ACCESS_KEY' in body
    assert 'secret_key=SECRET_KEY' in body
    assert 'study_id=STUDY_ID' in body
    assert 'user_ids=USER_ID' in body
