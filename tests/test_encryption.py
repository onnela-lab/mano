from pathlib import Path

import pytest

from mano.constants import EncryptionKeyUnavailable
from mano.file_management import decrypt_binary_data_to_bytes, do_encrypted_write
from tests.conftest import FILE_CONTENT_UNCOMPRESSED, PASSPHRASE_STRING


# Decrypting without a passphrase must raise a clear error rather than return garbage.
def test_decrypt_binary_data_to_bytes_raises_without_passphrase():
    with pytest.raises(EncryptionKeyUnavailable):
        decrypt_binary_data_to_bytes(b"irrelevant", None, "some/path.lock")


# Encrypted writes without a passphrase must fail instead of silently writing plaintext.
def test_do_encrypted_write_raises_without_passphrase():
    with pytest.raises(EncryptionKeyUnavailable):
        do_encrypted_write(b"irrelevant", "some/path.csv", None)


# Encrypted output must be recoverable with the passphrase, or locked data would be lost.
def test_do_encrypted_write_writes_encrypted_file(tmp_path: Path):
    filename = str(tmp_path / "output.csv")
    do_encrypted_write(FILE_CONTENT_UNCOMPRESSED, filename, PASSPHRASE_STRING)
    encrypted_bytes = Path(filename).read_bytes()
    assert decrypt_binary_data_to_bytes(encrypted_bytes, PASSPHRASE_STRING, filename) == FILE_CONTENT_UNCOMPRESSED
