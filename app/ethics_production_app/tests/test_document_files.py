import io
import unittest
import zipfile

from app.ethics_production_app.utils.document_files import (
    UploadValidationError,
    decode_legacy_binary,
    detect_document_type,
    read_validated_upload,
    response_document_metadata,
)


class Upload:
    def __init__(self, filename, data):
        self.filename = filename
        self._stream = io.BytesIO(data)

    def read(self, size=-1):
        return self._stream.read(size)


def make_docx():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("[Content_Types].xml", "types")
        archive.writestr("word/document.xml", "document")
    return stream.getvalue()


class DocumentFileTests(unittest.TestCase):
    def test_decodes_legacy_postgres_hex(self):
        self.assertEqual(decode_legacy_binary(r"\x255044462d312e37"), b"%PDF-1.7")
        self.assertEqual(decode_legacy_binary(b"\\x504b0304"), b"PK\x03\x04")

    def test_accepts_docx_content_with_pdf_name_and_corrects_extension(self):
        data, filename = read_validated_upload(
            Upload("incorrect.pdf", make_docx()), 1024 * 1024
        )
        self.assertEqual(detect_document_type(data), "docx")
        self.assertEqual(filename, "incorrect.docx")

    def test_accepts_legacy_word_document(self):
        legacy_doc = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1legacy-word-data"
        data, filename = read_validated_upload(
            Upload("letter.doc", legacy_doc), 1024 * 1024
        )
        self.assertEqual(data, legacy_doc)
        self.assertEqual(filename, "letter.doc")

    def test_repairs_existing_mislabeled_document_response(self):
        mimetype, filename, as_attachment = response_document_metadata(
            make_docx(), "incorrect.pdf", "document"
        )
        self.assertEqual(detect_document_type(make_docx()), "docx")
        self.assertTrue(mimetype.endswith("wordprocessingml.document"))
        self.assertEqual(filename, "incorrect.docx")
        self.assertTrue(as_attachment)

    def test_accepts_pdf_with_matching_name(self):
        data, filename = read_validated_upload(
            Upload("report.pdf", b"%PDF-1.7\ncontent"), 1024 * 1024
        )
        self.assertTrue(data.startswith(b"%PDF-"))
        self.assertEqual(filename, "report.pdf")


if __name__ == "__main__":
    unittest.main()
