"""
Pytest configuration and shared fixtures for mano tests.
"""
import io
import zipfile

import pytest


@pytest.fixture
def mock_zip_data():
    """Create a mock zip file response for download testing"""
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Add identifier file
        identifier_content = (
            "timestamp,UTC time,patient_id,MAC,phone_number,"
            "device_id,device_os,os_version,product,brand,"
            "hardware_id,manufacturer,model,beiwe_version\n"
            "1529078972000,2018-06-15T16:09:32.000,6y6s1w4g,"
            "FvdQruBocshHVKRW,+1234567890,device123,Android,"
            "8.0.0,Product,Brand,hw123,Manufacturer,Model,"
            "2.0.0\n"
        )
        zip_file.writestr('6y6s1w4g/identifiers/2018-06-15 16_00_00.csv',
                          identifier_content)
        
        # Add all GPS files from the original test_download.index
        gps_files = [
            '2018-06-15 16_00_00.csv', '2018-06-15 17_00_00.csv',
            '2018-06-15 18_00_00.csv', '2018-06-15 19_00_00.csv',
            '2018-06-15 20_00_00.csv', '2018-06-15 21_00_00.csv',
            '2018-06-15 22_00_00.csv', '2018-06-15 23_00_00.csv',
            '2018-06-16 00_00_00.csv', '2018-06-16 01_00_00.csv',
            '2018-06-16 02_00_00.csv', '2018-06-16 03_00_00.csv',
            '2018-06-16 04_00_00.csv', '2018-06-16 05_00_00.csv',
            '2018-06-16 06_00_00.csv', '2018-06-16 07_00_00.csv',
            '2018-06-16 08_00_00.csv', '2018-06-16 09_00_00.csv',
            '2018-06-16 10_00_00.csv', '2018-06-16 11_00_00.csv',
            '2018-06-16 12_00_00.csv', '2018-06-16 13_00_00.csv',
            '2018-06-16 14_00_00.csv', '2018-06-16 15_00_00.csv',
            '2018-06-16 16_00_00.csv', '2018-06-16 17_00_00.csv',
            '2018-06-16 18_00_00.csv', '2018-06-16 19_00_00.csv',
            '2018-06-16 20_00_00.csv'
        ]
        
        gps_content = (
            "timestamp,UTC time,latitude,longitude,altitude,"
            "accuracy\n"
            "1529100313864,2018-06-15T22:05:13.864,42.3805588,"
            "-71.1149213,0.0,19.521\n"
        )
        
        for gps_file in gps_files:
            zip_file.writestr(f'6y6s1w4g/gps/{gps_file}', gps_content)
        
        # Add registry file with more realistic content
        registry_content = (
            '{"CHUNKED_DATA/fiaKUCTtfqH5oQ4tz8V6LWiF/6y6s1w4g/'
            'gps/2018-06-15T16:00:00.csv": "Kpcasj7yQdfQu07emmg7mg'
            '==\\n", "version": "1.0"}'
        )
        zip_file.writestr('registry', registry_content)
    
    zip_buffer.seek(0)
    return zip_buffer.getvalue()
