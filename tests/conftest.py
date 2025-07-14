"""
Pytest configuration and shared fixtures for mano tests.
"""
import os

import pytest
import responses


@pytest.fixture
def keyring():
    """Fixture providing test credentials for Beiwe API authentication."""
    return {
        'URL': 'https://studies.beiwe.org',
        'USERNAME': 'foobar',
        'PASSWORD': 'bizbat',
        'ACCESS_KEY': 'ACCESS_KEY',
        'SECRET_KEY': 'SECRET_KEY'
    }


@pytest.fixture
def mock_zip_data():
    """Create a mock zip file response using the original ZIP file.

    This fixture uses the extracted download.v1.zip to provide test data with
    the exact same content and CRC values as the original download,
    eliminating the need for VCR.py dependencies.
    """
    # Load the original ZIP file extracted from the cassette
    original_zip_file = os.path.join(
        os.path.dirname(__file__), 'data', 'download.v1.zip'
    )

    with open(original_zip_file, 'rb') as f:
        return f.read()


@pytest.fixture
def mock_download_api(mock_zip_data):
    """Fixture that sets up the mock API endpoint for download testing."""
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.POST,
            'https://studies.beiwe.org/get-data/v1',
            body=mock_zip_data,
            status=200,
            content_type='application/zip'
        )
        yield rsps


@pytest.fixture
def expected_download_files():
    """Expected files and CRC values from the original download.

    These values represent what we expect the download function to return
    based on the original API response captured in the cassette.
    """
    return {
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
