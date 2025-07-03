# Test Data Directory

This directory contains static test data files used by the test suite.

## Files:

- `download.v1.zip`: Original API response from the download cassette (443KB)
  - Contains 31 files: 29 GPS data files, 1 identifiers file, 1 registry file
  - Used by `mock_zip_data` fixture in `conftest.py`
  - Extracted from `tests/cassettes/download.v1.yaml`

## Usage:

Test data files should be:
- Small and focused (avoid large files when possible)
- Versioned (e.g., v1, v2) when format changes
- Documented with purpose and source
- Committed to git for reproducible tests
