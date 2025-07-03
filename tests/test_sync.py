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


def test_download_contains_expected_files_with_correct_crcs(
        mock_download_api, keyring):
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

    # Expected files and CRC values from the original download data
    # These values were extracted from the actual download and are stored in
    # tests/download.v1.json for VCR.py-independent testing
    expected_files_from_original = {
        ('6y6s1w4g/identifiers/2018-06-15 16_00_00.csv', 4113954587),
        ('6y6s1w4g/gps/2018-06-15 22_00_00.csv', 3073924694),
        ('6y6s1w4g/gps/2018-06-15 17_00_00.csv', 4177290012),
        ('6y6s1w4g/gps/2018-06-15 20_00_00.csv', 3999192708),
        ('6y6s1w4g/gps/2018-06-15 18_00_00.csv', 4038997044),
        ('6y6s1w4g/gps/2018-06-15 21_00_00.csv', 2945081574),
        ('6y6s1w4g/gps/2018-06-15 19_00_00.csv', 4035326526),
        ('6y6s1w4g/gps/2018-06-15 16_00_00.csv', 427497446),
        ('6y6s1w4g/gps/2018-06-16 04_00_00.csv', 2574140219),
        ('6y6s1w4g/gps/2018-06-16 01_00_00.csv', 503869630),
        ('6y6s1w4g/gps/2018-06-16 03_00_00.csv', 1817118505),
        ('6y6s1w4g/gps/2018-06-16 00_00_00.csv', 963879171),
        ('6y6s1w4g/gps/2018-06-15 23_00_00.csv', 2924619047),
        ('6y6s1w4g/gps/2018-06-16 02_00_00.csv', 2868941135),
        ('6y6s1w4g/gps/2018-06-16 07_00_00.csv', 2619751600),
        ('6y6s1w4g/gps/2018-06-16 12_00_00.csv', 3738822868),
        ('6y6s1w4g/gps/2018-06-16 10_00_00.csv', 2382158563),
        ('6y6s1w4g/gps/2018-06-16 08_00_00.csv', 3580985466),
        ('6y6s1w4g/gps/2018-06-16 09_00_00.csv', 771315427),
        ('6y6s1w4g/gps/2018-06-16 11_00_00.csv', 1386915032),
        ('6y6s1w4g/gps/2018-06-16 14_00_00.csv', 641388715),
        ('6y6s1w4g/gps/2018-06-16 15_00_00.csv', 3728053865),
        ('6y6s1w4g/gps/2018-06-16 16_00_00.csv', 1258485774),
        ('6y6s1w4g/gps/2018-06-16 18_00_00.csv', 1597315532),
        ('6y6s1w4g/gps/2018-06-16 13_00_00.csv', 2905130265),
        ('6y6s1w4g/gps/2018-06-16 19_00_00.csv', 565983226),
        ('6y6s1w4g/gps/2018-06-16 17_00_00.csv', 2142570097),
        ('6y6s1w4g/gps/2018-06-16 06_00_00.csv', 3417900549),
        ('6y6s1w4g/gps/2018-06-16 20_00_00.csv', 1834664030),
        ('6y6s1w4g/gps/2018-06-16 05_00_00.csv', 3970320035),
        ('registry', 942145567)
    }

    # Filter actual files to only include the ones we expect
    filtered_actual_files = {
        (filename, crc) for filename, crc in actual_files
        if filename in {f for f, _ in expected_files_from_original}
    }

    # Verify that the CRC values match exactly
    assert filtered_actual_files == expected_files_from_original, \
        f"CRC mismatch. Expected: {expected_files_from_original}, " \
        f"Got: {filtered_actual_files}"


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
    assert 'access_key=ACCESS_KEY' in request.body
    assert 'secret_key=SECRET_KEY' in request.body
    assert 'study_id=STUDY_ID' in request.body
    assert 'user_ids=USER_ID' in request.body
