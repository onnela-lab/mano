from os.path import dirname, join as path_join
from pathlib import Path

import pytest
import pyzstd
import responses


"""
Pytest configuration and shared fixtures for mano tests.
"""


@pytest.fixture
def keyring() -> dict[str, str]:
    """Fixture providing test credentials for Beiwe API authentication."""
    return {
        'URL': 'https://studies.beiwe.org',
        'USERNAME': 'foobar',
        'PASSWORD': 'bizbat',
        'ACCESS_KEY': 'ACCESS_KEY',
        'SECRET_KEY': 'SECRET_KEY'
    }


@pytest.fixture
def mock_zip_data_uncompressed():
    """Create a mock zip file response using the original ZIP file.
    
    This fixture uses the extracted download.v1.zip to provide test data with
    the exact same content and CRC values as the original download,
    eliminating the need for VCR.py dependencies.
    """
    # Load the original ZIP file extracted from the cassette
    original_zip_file = path_join(dirname(__file__), 'data', 'download.v1.zip')
    
    with open(original_zip_file, 'rb') as f:
        return f.read()


@pytest.fixture
def mock_zip_data_compressed():
    original_zip_file = path_join(dirname(__file__), 'data', 'download.v2.zip')
    
    with open(original_zip_file, 'rb') as f:
        return f.read()


@pytest.fixture
def mock_download_v1_api(mock_zip_data_uncompressed: bytes):
    """Fixture that sets up the mock API endpoint for download testing."""
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.POST,
            'https://studies.beiwe.org/get-data/v1',
            body=mock_zip_data_uncompressed,
            status=200,
            content_type='application/zip'
        )
        yield rsps


@pytest.fixture
def mock_download_v2_api(mock_zip_data_compressed: bytes):
    """Fixture that sets up the mock API endpoint for download testing."""
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.POST,
            'https://studies.beiwe.org/get-data/v2',
            body=mock_zip_data_compressed,
            status=200,
            content_type='application/zip'
        )
        yield rsps


@pytest.fixture
def mock_download_v1_and_v2_api(mock_zip_data_compressed: bytes, mock_zip_data_uncompressed: bytes):
    """Fixture for mocking the comparison of download v1 and v2 endpoints must be its own thing."""
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.POST,
            'https://studies.beiwe.org/get-data/v1',
            body=mock_zip_data_uncompressed,
            status=200,
            content_type='application/zip'
        )
        rsps.add(
            responses.POST,
            'https://studies.beiwe.org/get-data/v2',
            body=mock_zip_data_compressed,
            status=200,
            content_type='application/zip'
        )
        yield rsps


@pytest.fixture
def expected_uncompressed_filenames() -> set[tuple[str, int]]:
    """Expected files and CRC values from the original download.
    
    These values represent what we expect the download function to return
    based on the original API response captured in the cassette.
    """
    return {
        ('6y6s1w4g/gps/2018-06-15 16_00_00.csv', 427497446),
        ('6y6s1w4g/gps/2018-06-15 17_00_00.csv', 4177290012),
        ('6y6s1w4g/gps/2018-06-15 18_00_00.csv', 4038997044),
        ('6y6s1w4g/gps/2018-06-15 19_00_00.csv', 4035326526),
        ('6y6s1w4g/gps/2018-06-15 20_00_00.csv', 3999192708),
        ('6y6s1w4g/gps/2018-06-15 21_00_00.csv', 2945081574),
        ('6y6s1w4g/gps/2018-06-15 22_00_00.csv', 3073924694),
        ('6y6s1w4g/gps/2018-06-15 23_00_00.csv', 2924619047),
        ('6y6s1w4g/gps/2018-06-16 00_00_00.csv', 963879171),
        ('6y6s1w4g/gps/2018-06-16 01_00_00.csv', 503869630),
        ('6y6s1w4g/gps/2018-06-16 02_00_00.csv', 2868941135),
        ('6y6s1w4g/gps/2018-06-16 03_00_00.csv', 1817118505),
        ('6y6s1w4g/gps/2018-06-16 04_00_00.csv', 2574140219),
        ('6y6s1w4g/gps/2018-06-16 05_00_00.csv', 3970320035),
        ('6y6s1w4g/gps/2018-06-16 06_00_00.csv', 3417900549),
        ('6y6s1w4g/gps/2018-06-16 07_00_00.csv', 2619751600),
        ('6y6s1w4g/gps/2018-06-16 08_00_00.csv', 3580985466),
        ('6y6s1w4g/gps/2018-06-16 09_00_00.csv', 771315427),
        ('6y6s1w4g/gps/2018-06-16 10_00_00.csv', 2382158563),
        ('6y6s1w4g/gps/2018-06-16 11_00_00.csv', 1386915032),
        ('6y6s1w4g/gps/2018-06-16 12_00_00.csv', 3738822868),
        ('6y6s1w4g/gps/2018-06-16 13_00_00.csv', 2905130265),
        ('6y6s1w4g/gps/2018-06-16 14_00_00.csv', 641388715),
        ('6y6s1w4g/gps/2018-06-16 15_00_00.csv', 3728053865),
        ('6y6s1w4g/gps/2018-06-16 16_00_00.csv', 1258485774),
        ('6y6s1w4g/gps/2018-06-16 17_00_00.csv', 2142570097),
        ('6y6s1w4g/gps/2018-06-16 18_00_00.csv', 1597315532),
        ('6y6s1w4g/gps/2018-06-16 19_00_00.csv', 565983226),
        ('6y6s1w4g/gps/2018-06-16 20_00_00.csv', 1834664030),
        ('6y6s1w4g/identifiers/2018-06-15 16_00_00.csv', 4113954587),
        ('registry', 942145567),
    }


@pytest.fixture
def expected_compressed_filenames() -> set[tuple[str, int]]:
    return {
        ('6y6s1w4g/gps/2018-06-15 16_00_00.csv.zst', 1706328344),
        ('6y6s1w4g/gps/2018-06-15 17_00_00.csv.zst', 976572207),
        ('6y6s1w4g/gps/2018-06-15 18_00_00.csv.zst', 1804195275),
        ('6y6s1w4g/gps/2018-06-15 19_00_00.csv.zst', 4251078412),
        ('6y6s1w4g/gps/2018-06-15 20_00_00.csv.zst', 1367354287),
        ('6y6s1w4g/gps/2018-06-15 21_00_00.csv.zst', 1899806299),
        ('6y6s1w4g/gps/2018-06-15 22_00_00.csv.zst', 1220964178),
        ('6y6s1w4g/gps/2018-06-15 23_00_00.csv.zst', 4068865129),
        ('6y6s1w4g/gps/2018-06-16 00_00_00.csv.zst', 2656704980),
        ('6y6s1w4g/gps/2018-06-16 01_00_00.csv.zst', 2657586866),
        ('6y6s1w4g/gps/2018-06-16 02_00_00.csv.zst', 1718996254),
        ('6y6s1w4g/gps/2018-06-16 03_00_00.csv.zst', 1422106514),
        ('6y6s1w4g/gps/2018-06-16 04_00_00.csv.zst', 1111613011),
        ('6y6s1w4g/gps/2018-06-16 05_00_00.csv.zst', 2608945488),
        ('6y6s1w4g/gps/2018-06-16 06_00_00.csv.zst', 2454933779),
        ('6y6s1w4g/gps/2018-06-16 07_00_00.csv.zst', 493462176),
        ('6y6s1w4g/gps/2018-06-16 08_00_00.csv.zst', 321395430),
        ('6y6s1w4g/gps/2018-06-16 09_00_00.csv.zst', 3697804579),
        ('6y6s1w4g/gps/2018-06-16 10_00_00.csv.zst', 2768111514),
        ('6y6s1w4g/gps/2018-06-16 11_00_00.csv.zst', 2903824137),
        ('6y6s1w4g/gps/2018-06-16 12_00_00.csv.zst', 85290479),
        ('6y6s1w4g/gps/2018-06-16 13_00_00.csv.zst', 2815825291),
        ('6y6s1w4g/gps/2018-06-16 14_00_00.csv.zst', 643966221),
        ('6y6s1w4g/gps/2018-06-16 15_00_00.csv.zst', 2621553271),
        ('6y6s1w4g/gps/2018-06-16 16_00_00.csv.zst', 2585072462),
        ('6y6s1w4g/gps/2018-06-16 17_00_00.csv.zst', 136510382),
        ('6y6s1w4g/gps/2018-06-16 18_00_00.csv.zst', 394448715),
        ('6y6s1w4g/gps/2018-06-16 19_00_00.csv.zst', 1660357250),
        ('6y6s1w4g/gps/2018-06-16 20_00_00.csv.zst', 3428101130),
        ('6y6s1w4g/identifiers/2018-06-15 16_00_00.csv.zst', 133130875),
        ('registry', 942145567)
    }


@pytest.fixture
def mock_studies_response():
    """Mock API response for get-studies/v1 endpoint"""
    return  '{"123lrVdb0g6tf3PeJr5ZtZC8": "Project A", "123U93wwgS18aLDIwdYXTXsr": "Project B"}'


@pytest.fixture
def mock_users_response():
    """Mock API response for get-users/v1 endpoint"""
    return '["tgsidhm", "lholbc5", "yxzxtwr"]'


#
# Helper functions for zstd compression tests - require the test uses the tmp_path fixture and pass it in
#

def generate_uncompressed_zstd_files(tmp_path: Path) -> tuple[Path, Path, bytes]:
    """
    Basic setup so running compress doesn't error and compresses something.
    """
    uncompressed_path = tmp_path / "testzstd.csv"
    original_bytes = b"Sample data for compression test." * 20
    uncompressed_path.write_bytes(original_bytes)
    compressed_path = tmp_path / "testzstd.csv.zst"
    return uncompressed_path, compressed_path, original_bytes


def generate_compressed_zstd_file(tmp_path: Path) -> tuple[Path, Path, bytes]:
    uncompressed_path = tmp_path / "testzstd.csv"
    compressed_path = tmp_path / "testzstd.csv.zst"
    original_bytes = b"Sample data for compression test." * 20
    compressed_bytes = pyzstd.compress(original_bytes, 2)  # type: ignore
    compressed_path.write_bytes(compressed_bytes)
    return uncompressed_path, compressed_path, original_bytes
