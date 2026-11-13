# Test Data Directory

Static files used by the test suite. They are real Beiwe download responses, committed so that
tests are reproducible.

## Files

- `download.v1.zip` (445,692 bytes, 34 entries): response of `/get-data/v1`, uncompressed.
  - 29 gps files, 1 identifiers file, 1 `registry` file, plus 3 directory entries.
  - Served by the `mock_zip_data_uncompressed` fixture in `conftest.py` (used by
    `mock_download_v1_api` and `mock_download_v1_and_v2_api`).
- `download.v2.zip` (98,248 bytes, 34 entries): response of `/get-data/v2`, the same data with
  each file compressed with zstd (`.zst`).
  - Same layout as v1, file names end in `.zst`.
  - Served by the `mock_zip_data_compressed` fixture in `conftest.py` (used by
    `mock_download_v2_api` and `mock_download_v1_and_v2_api`).

When the download format changes, add a new versioned file rather than editing these.
