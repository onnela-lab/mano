from pathlib import Path

import pytest
from pytest_mock import MockerFixture
from pyzstd import decompress

from mano.file_management import (compress_as_backend, compress_general, compress_one_zst_file,
    compress_to_zst_files, decompress_one_zst_file, decompress_zst_files,
    iterate_beiwe_data_files_recursively)
from tests.conftest import (generate_compressed_zst_files, generate_uncompressed_zst_files,
    generate_valid_compress_test_files, generate_valid_decompress_test_files)


def test_compress_as_backend():
    original_bytes = b'This is some test data to be compressed using the backend compression settings.' * 10
    compressed_bytes = compress_as_backend(original_bytes)
    assert decompress(compressed_bytes) == original_bytes
    assert len(compressed_bytes) < len(original_bytes)


def test_compress_general():
    original_bytes = b'This is some test data to be compressed using the general compression settings.' * 10
    compressed_bytes = compress_general(original_bytes, level=19)  # take it slow
    assert decompress(compressed_bytes) == original_bytes
    assert len(compressed_bytes) < len(original_bytes)


def test_compress_one_zst_file_defaults(tmp_path: Path):
    uncompressed_path, compressed_path, original_bytes = generate_uncompressed_zst_files(tmp_path)
    compress_one_zst_file(str(uncompressed_path))
    assert compressed_path.exists()
    assert uncompressed_path.exists()
    assert original_bytes == decompress(compressed_bytes := compressed_path.read_bytes())
    assert len(compressed_bytes) < len(original_bytes)


def test_compress_one_zst_file_overwrite_fail(tmp_path: Path):
    uncompressed_path, compressed_path, _original_bytes = generate_uncompressed_zst_files(tmp_path)
    compressed_path.write_bytes(b"super secret data")
    compress_one_zst_file(str(uncompressed_path), overwrite=False)
    assert compressed_path.read_bytes() == b"super secret data"


def test_compress_one_zst_file_overwrite_success(tmp_path: Path):
    uncompressed_path, compressed_path, original_bytes = generate_uncompressed_zst_files(tmp_path)
    compressed_path.write_bytes(b"super secret data")
    compress_one_zst_file(str(uncompressed_path), overwrite=True)
    assert original_bytes == decompress(compressed_path.read_bytes())


def test_compress_one_zst_file_delete_original(tmp_path: Path):
    uncompressed_path, compressed_path, original_bytes = generate_uncompressed_zst_files(tmp_path)
    compress_one_zst_file(str(uncompressed_path), delete_original=True)
    assert not uncompressed_path.exists()
    assert compressed_path.exists()
    assert original_bytes == decompress(compressed_path.read_bytes())


def test_compress_one_zst_file_custom_level(tmp_path: Path):
    uncompressed_path, compressed_path, original_bytes = generate_uncompressed_zst_files(tmp_path)
    compress_one_zst_file(str(uncompressed_path), compression_level=19)  # take it slow
    assert compressed_path.exists()
    assert uncompressed_path.exists()
    assert original_bytes == decompress(compressed_bytes := compressed_path.read_bytes())
    assert len(compressed_bytes) < len(original_bytes)


def test_decompress_one_zst_file_defaults(tmp_path: Path):
    uncompressed_path, compressed_path, original_bytes = generate_compressed_zst_files(tmp_path)
    decompress_one_zst_file(str(compressed_path))
    assert uncompressed_path.exists()
    assert compressed_path.exists()
    assert original_bytes == uncompressed_path.read_bytes()


def test_decompress_one_zst_file_overwrite_fail(tmp_path: Path):
    uncompressed_path, compressed_path, _original_bytes = generate_compressed_zst_files(tmp_path)
    uncompressed_path.write_bytes(b"super secret data")
    decompress_one_zst_file(str(compressed_path), overwrite=False)
    assert uncompressed_path.read_bytes() == b"super secret data"


def test_decompress_one_zst_file_overwrite_success(tmp_path: Path):
    uncompressed_path, compressed_path, original_bytes = generate_compressed_zst_files(tmp_path)
    uncompressed_path.write_bytes(b"super secret data")
    decompress_one_zst_file(str(compressed_path), overwrite=True)
    assert original_bytes == uncompressed_path.read_bytes()


def test_decompress_one_zst_file_delete_zst(tmp_path: Path):
    uncompressed_path, compressed_path, original_bytes = generate_compressed_zst_files(tmp_path)
    decompress_one_zst_file(str(compressed_path), delete_zsts=True)
    assert not compressed_path.exists()
    assert uncompressed_path.exists()
    assert original_bytes == uncompressed_path.read_bytes()


def test_decompress_zst_files_single_file_mode(tmp_path: Path):
    uncompressed_path, compressed_path, original_bytes = generate_compressed_zst_files(tmp_path)
    decompress_zst_files(str(compressed_path))
    assert uncompressed_path.read_bytes() == original_bytes


def test_compress_to_zst_files_single_file_mode(tmp_path: Path):
    uncompressed_path, compressed_path, original_bytes = generate_uncompressed_zst_files(tmp_path)
    compress_to_zst_files(str(uncompressed_path))
    assert decompress(compressed_path.read_bytes()) == original_bytes


def test_full_decompress_decompresses(tmp_path: Path):
    zst_files, non_zst_files, uncompressed_bytes = generate_valid_decompress_test_files(tmp_path)
    decompress_zst_files(str(tmp_path), delete_zsts=False, overwrite=False)
    common_full_decompress(tmp_path, uncompressed_bytes, zst_files, non_zst_files)


def common_full_decompress(
    tmp_path: Path, uncompressed_bytes: bytes, zst_files: list[Path], non_zst_files: list[Path]
):
    correct_uncompressed_file_paths = {str(path).rsplit(".zst")[0] for path in zst_files}

    for path in non_zst_files:
        if path.suffix in [".csv", ".wav"]:
            correct_uncompressed_file_paths.add(str(path))

    new_valid_file_paths = set[str]()
    for file in iterate_beiwe_data_files_recursively(str(tmp_path), zst_only=False):
        path = Path(file)
        new_valid_file_paths.add(str(path))
        assert path.exists()
        assert path.suffix != ".zst"
        assert path.read_bytes() == uncompressed_bytes

    assert set(new_valid_file_paths) == correct_uncompressed_file_paths


def test_full_compress_multithread_works(tmp_path: Path):
    compressable_files, _uncompressable_files, original_bytes = generate_valid_compress_test_files(tmp_path)
    compress_to_zst_files(str(tmp_path), delete_original=False, overwrite=False)
    common_full_compress(tmp_path, original_bytes, compressable_files)


def common_full_compress(tmp_path: Path, original_bytes: bytes, compressable_files: list[Path]):
    correct_compressed_file_paths = {str(path)+".zst" for path in compressable_files}

    new_valid_file_paths = set[str]()
    for fp in iterate_beiwe_data_files_recursively(str(tmp_path), zst_only=True):
        path = Path(fp)
        new_valid_file_paths.add(str(path))
        assert path.suffix == ".zst"
        assert path.exists()
        assert decompress(path.read_bytes()) == original_bytes

    assert new_valid_file_paths == correct_compressed_file_paths


def test_full_decompress_delete_zst_deletes_zsts(tmp_path: Path):
    zst_files, non_zst_files, _ = generate_valid_decompress_test_files(tmp_path)
    decompress_zst_files(str(tmp_path), delete_zsts=True, overwrite=False)
    for path in zst_files:
        assert not path.exists()
    for path in non_zst_files:
        assert path.exists()


def test_full_compress_delete_original_deletes_originals(tmp_path: Path):
    compressable_files, uncompressable_files, _ = generate_valid_compress_test_files(tmp_path)
    compress_to_zst_files(str(tmp_path), delete_original=True, overwrite=False)
    for path in compressable_files:
        assert not path.exists()
    for path in uncompressable_files:
        assert path.exists()


def test_full_compress_overwrites(tmp_path: Path):
    compressable_files, _uncompressable_files, decompressed_data = generate_valid_compress_test_files(tmp_path)
    for path in compressable_files:
        (path.parent / (path.name + ".zst")).write_bytes(b"super secret data")

    compress_to_zst_files(str(tmp_path), delete_original=False, overwrite=True)
    for path in compressable_files:
        compressed_path = path.parent / (path.name + ".zst")
        assert compressed_path.exists()
        assert decompress(compressed_path.read_bytes()) == decompressed_data


def test_full_decompress_overwrites(tmp_path: Path):
    zst_files, _non_zst_files, decompressed_data = generate_valid_decompress_test_files(tmp_path)
    for path in zst_files:
        Path(str(path).rsplit(".zst")[0]).write_bytes(b"super secret data")

    decompress_zst_files(str(tmp_path), delete_zsts=False, overwrite=True)
    for path in zst_files:
        uncompressed_path = path.parent / path.name.rsplit(".zst")[0]
        assert uncompressed_path.exists()
        assert uncompressed_path.read_bytes() == decompressed_data


def test_full_compress_raises_an_error_during_real_execution_1_thread(tmp_path: Path, mocker: MockerFixture):
    _compressable_files, _uncompressable_files, _ = generate_valid_compress_test_files(tmp_path)
    mocker.patch("mano.file_management.compress_one_zst_file", side_effect=Exception("Simulated compression error"))
    with pytest.raises(Exception, match="Simulated compression error"):
        compress_to_zst_files(str(tmp_path), delete_original=False, overwrite=False)


def test_full_decompress_raises_an_error_during_real_execution_1_thread(tmp_path: Path, mocker: MockerFixture):
    _zst_files, _non_zst_files, _ = generate_valid_decompress_test_files(tmp_path)
    mocker.patch("mano.file_management.decompress_one_zst_file", side_effect=Exception("Simulated decompression error"))
    with pytest.raises(Exception, match="Simulated decompression error"):
        decompress_zst_files(str(tmp_path), delete_zsts=False, overwrite=False)
