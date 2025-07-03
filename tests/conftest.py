"""
Pytest configuration and shared fixtures for mano tests.
"""
import io
import json
import os
import zipfile

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
    """Create a mock zip file response using original file contents.
    
    This fixture uses the extracted download.v1.json to create test data with
    the exact same content and CRC values as the original download,
    eliminating the need for VCR.py dependencies.
    """
    zip_buffer = io.BytesIO()
    
    # Load the original file contents extracted from the cassette
    original_contents_file = os.path.join(
        os.path.dirname(__file__), 'download.v1.json'
    )
    
    with open(original_contents_file, 'r') as f:
        original_contents = json.load(f)
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Add each file with its original content
        for filename, file_info in original_contents.items():
            zip_file.writestr(filename, file_info['content'])
    
    zip_buffer.seek(0)
    return zip_buffer.getvalue()


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
