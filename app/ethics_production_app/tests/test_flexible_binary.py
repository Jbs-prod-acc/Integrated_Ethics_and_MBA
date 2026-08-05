import unittest

from app.models.ethics_legacy import FlexibleBinary


class FlexibleBinaryTests(unittest.TestCase):
    def setUp(self):
        self.processor = FlexibleBinary().result_processor(None, None)

    def test_decodes_postgres_hex_text_to_pdf_bytes(self):
        self.assertEqual(self.processor(r"\x255044462d312e37"), b"%PDF-1.7")

    def test_decodes_postgres_hex_bytes_to_zip_bytes(self):
        self.assertEqual(self.processor(b"\\x504b0304"), b"PK\x03\x04")

    def test_preserves_regular_binary_data(self):
        data = b"%PDF-1.7\ncontent"
        self.assertEqual(self.processor(data), data)


if __name__ == "__main__":
    unittest.main()
