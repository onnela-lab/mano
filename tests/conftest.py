from io import BytesIO
from os.path import dirname, join as path_join
from pathlib import Path

import pytest
import pyzstd
import responses
from cryptease import encrypt_to_stream, kdf as key_derivation_function


"""
Pytest configuration and shared fixtures for mano tests.
"""

# TODO: move these constants and helpers to a common test utils file
STUDY_ID = "abcdefghijklmnopqrstuvwx"  # 24 chars
PARTICIPANT_ID = "12345678"
DATA_STREAM_FOLDER = "accelerometer"
DATA_STREAM_FILE = "2024-02-16 09_00_00+00_00.csv"
DATA_STREAM_FILE_ISO = "2024-02-16T09:00:00.csv"
NORMALIZED_FILE_PATH = f"{STUDY_ID}/{PARTICIPANT_ID}/{DATA_STREAM_FOLDER}/{DATA_STREAM_FILE_ISO}"
LOCAL_PATH_REFERENCE = f"{DATA_STREAM_FOLDER}/{DATA_STREAM_FILE}"
FILE_CONTENT_UNCOMPRESSED = b"timestamp,x,y,z\n2024-02-16 09:00:00+00:00,0.1,0.2,0.3\n"
FILE_CONTENT_COMPRESSED = pyzstd.compress(FILE_CONTENT_UNCOMPRESSED)

# the encrypted files and passphrase differ on every run due to the salt and iv
PASSPHRASE_STRING = "test_passphrase"
salt = b'JOoKmNv31b1kLVJnwPAtCorhTSRb0In77k8xw5AVDjc='  # make the key static across all test runs
PASSPHRASE_OBJECT = key_derivation_function(PASSPHRASE_STRING, salt)  # slow, make global

# these files look weird, they start with a ~json-like header with information about the key
FILE_CONTENT_ENCRYPTED_UNCOMPRESSED = b"".join(
    encrypt_to_stream(BytesIO(FILE_CONTENT_UNCOMPRESSED), PASSPHRASE_OBJECT)
)
FILE_CONTENT_ENCRYPTED_COMPRESSED = b"".join(
    encrypt_to_stream(BytesIO(FILE_CONTENT_COMPRESSED), PASSPHRASE_OBJECT)
)

# FILE_SHA1_HASH_BYTES = base64.b64encode(hashlib.sha1(FILE_CONTENT_UNCOMPRESSED).digest())
FILE_SHA1_HASH_BYTES = b"mJfbbHQygEaa6euqwUnye9vYulM="  # hardcode this to make it unambiguous
FILE_SHA1_HASH_STRING = FILE_SHA1_HASH_BYTES.decode()



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

def generate_uncompressed_zst_files(tmp_path: Path) -> tuple[Path, Path, bytes]:
    """
    Basic setup so running compress doesn't error and compresses something.
    """
    uncompressed_path = tmp_path / "testzstd.csv"
    original_bytes = b"Sample data for compression test." * 20
    uncompressed_path.write_bytes(original_bytes)
    compressed_path = tmp_path / "testzstd.csv.zst"
    return uncompressed_path, compressed_path, original_bytes


def generate_compressed_zst_files(tmp_path: Path) -> tuple[Path, Path, bytes]:
    uncompressed_path = tmp_path / "testzstd.csv"
    compressed_path = tmp_path / "testzstd.csv.zst"
    original_bytes = b"Sample data for compression test." * 20
    compressed_bytes = pyzstd.compress(original_bytes, 2)  # type: ignore
    compressed_path.write_bytes(compressed_bytes)
    return uncompressed_path, compressed_path, original_bytes


DECOMPRESSED_BYTES = b"test content"
COMPRESSED_BYTES: bytes = pyzstd.compress(DECOMPRESSED_BYTES, 2)  # type: ignore


def generate_valid_compress_test_files(tmp_path: Path) -> tuple[list[Path], list[Path], bytes]:
    # create some valid and invalid files in subdirectories
    (tmp_path / "subdir1").mkdir()
    (tmp_path / "subdir2").mkdir()
    
    compressable_files = [
        tmp_path / "data1.csv",
        tmp_path / "subdir1" / "audio.wav",
    ]
    uncompressable_files = [
        tmp_path / "document.txt",
        tmp_path / "subdir1" / "image.jpg",
        tmp_path / "subdir2" / "archive.zip",
        tmp_path / "subdir1" / "script.py"
    ]
    # make them exist
    for filepath in compressable_files + uncompressable_files:
        filepath.write_bytes(DECOMPRESSED_BYTES)
    
    return compressable_files, uncompressable_files, DECOMPRESSED_BYTES


def generate_valid_decompress_test_files(tmp_path: Path) -> tuple[list[Path], list[Path], bytes]:
    # create some valid and invalid files in subdirectories
    (tmp_path / "subdir1").mkdir()
    (tmp_path / "subdir2").mkdir()
    
    zst_files = [
        tmp_path / "data1.csv.zst",
        tmp_path / "subdir1" / "audio.wav.zst",
    ]
    
    non_zst_files = [
        tmp_path / "document.txt",
        tmp_path / "subdir1" / "image.jpg",
        tmp_path / "subdir2" / "archive.zstd",
        tmp_path / "subdir1" / "script.py",
        tmp_path / "data3.csv"
    ]
    
    # make them exist
    for filepath in zst_files:
        filepath.write_bytes(COMPRESSED_BYTES)
    
    for filepath in non_zst_files:
        filepath.write_bytes(DECOMPRESSED_BYTES)
    
    return zst_files, non_zst_files, DECOMPRESSED_BYTES
