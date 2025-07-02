"""
Tests for mano.sync module download functionality.
"""
import zipfile

import responses

import mano.sync


# Test data - same as used in other tests
Keyring = {
    'URL': 'https://studies.beiwe.org',
    'USERNAME': 'foobar',
    'PASSWORD': 'bizbat',
    'ACCESS_KEY': 'ACCESS_KEY',
    'SECRET_KEY': 'SECRET_KEY'
}


@responses.activate
def test_download(mock_zip_data):
    """
    Test the download function using responses library instead of VCR.
    This test mocks the HTTP response with a zip file containing expected data.
    """
    # Mock the API endpoint
    responses.add(
        responses.POST,
        'https://studies.beiwe.org/get-data/v1',
        body=mock_zip_data,
        status=200,
        content_type='application/zip'
    )
    
    # Call the download function
    zf = mano.sync.download(Keyring,
                            study_id='STUDY_ID',
                            user_ids=['USER_ID'],
                            data_streams=['identifiers', 'gps'],
                            time_start='2018-06-15T00:00:00',
                            time_end='2018-06-17T00:00:00')
    
    # Check that we got a ZipFile object
    assert isinstance(zf, zipfile.ZipFile)
    
    # Get the list of files in the zip
    file_names = [zinfo.filename for zinfo in zf.infolist()]
    
    # Verify we have the expected total number of files
    # (29 GPS + 1 identifier + 1 registry = 31)
    assert len(file_names) == 31
    
    # Verify expected files are present
    expected_files = [
        '6y6s1w4g/identifiers/2018-06-15 16_00_00.csv',
        'registry'
    ]
    
    for expected_file in expected_files:
        assert expected_file in file_names
    
    # Verify GPS files are present - should have 29 GPS files
    gps_files = [f for f in file_names if 'gps' in f]
    assert len(gps_files) == 29
    
    # Verify date range coverage (June 15-16, 2018)
    assert any('2018-06-15' in f for f in gps_files)
    assert any('2018-06-16' in f for f in gps_files)
    
    # Verify the API was called correctly
    assert len(responses.calls) == 1
    request = responses.calls[0].request
    
    # Check that the request contains expected parameters
    assert 'access_key=ACCESS_KEY' in request.body
    assert 'secret_key=SECRET_KEY' in request.body
    assert 'study_id=STUDY_ID' in request.body
    assert 'user_ids=USER_ID' in request.body
