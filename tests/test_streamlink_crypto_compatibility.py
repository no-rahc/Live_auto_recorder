"""Offline smoke coverage for Streamlink and its PyCryptodome backend."""
import unittest
from unittest.mock import patch

from streamlink import Streamlink
from streamlink.utils.crypto import AES, decrypt_openssl, encrypt_openssl, pad, unpad


class StreamlinkCryptoCompatibilityTests(unittest.TestCase):
    def test_aes_cbc_known_vector_through_streamlink_backend(self):
        # NIST SP 800-38A F.2.1, first AES-128 CBC block.
        key = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
        iv = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
        plain = bytes.fromhex("6bc1bee22e409f96e93d7e117393172a")
        encrypted = bytes.fromhex("7649abac8119b246cee98e9b12e9197d")
        self.assertEqual(AES.new(key, AES.MODE_CBC, iv).encrypt(plain), encrypted)
        self.assertEqual(AES.new(key, AES.MODE_CBC, iv).decrypt(encrypted), plain)

    def test_hls_padding_and_openssl_round_trip(self):
        payload = b"synthetic recording segment"
        self.assertEqual(unpad(pad(payload, AES.block_size), AES.block_size), payload)
        encrypted = encrypt_openssl(payload, b"synthetic-test-passphrase")
        self.assertEqual(decrypt_openssl(encrypted, b"synthetic-test-passphrase"), payload)

    def test_recording_plugins_resolve_without_network(self):
        session = Streamlink()
        self.addCleanup(session.http.close)
        with patch.object(session.http, "request", side_effect=AssertionError("No network allowed")):
            for expected, url in (
                ("chzzk", "https://chzzk.naver.com/live/00000000000000000000000000000000"),
                ("youtube", "https://www.youtube.com/watch?v=abcdefghijk"),
            ):
                with self.subTest(plugin=expected):
                    name, plugin, resolved_url = session.resolve_url(url, follow_redirect=False)
                    self.assertEqual(name, expected)
                    self.assertIsNotNone(plugin(session, resolved_url))


if __name__ == "__main__":
    unittest.main()
