"""Validation and response metadata for user-uploaded documents."""

from __future__ import annotations

import io
import os
import zipfile

from werkzeug.utils import secure_filename


class UploadValidationError(ValueError):
    """Raised when an uploaded document is unsafe or does not match its name."""


DOCUMENT_TYPES = {
    "pdf": (".pdf", "application/pdf"),
    "docx": (
        ".docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    "doc": (".doc", "application/msword"),
    "zip": (".zip", "application/zip"),
    "png": (".png", "image/png"),
    "jpeg": (".jpg", "image/jpeg"),
}


def decode_legacy_binary(value):
    """Return stored document content as bytes, decoding PostgreSQL hex text."""
    if isinstance(value, memoryview):
        value = value.tobytes()

    if isinstance(value, str):
        if value.startswith("\\x"):
            try:
                return bytes.fromhex(value[2:])
            except ValueError:
                pass
        return value.encode("latin-1", errors="ignore")

    if isinstance(value, bytes) and value.startswith(b"\\x"):
        try:
            return bytes.fromhex(value[2:].decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            pass

    if isinstance(value, bytes):
        return value
    if hasattr(value, "read"):
        return value.read()
    return bytes(value)


def detect_document_type(data: bytes) -> str | None:
    """Identify supported document types from bytes instead of the filename."""
    if data.startswith(b"%PDF-") or b"%PDF-" in data[:1024]:
        return "pdf"
    if data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "doc"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
                if "[Content_Types].xml" in names and any(
                    name.startswith("word/") for name in names
                ):
                    return "docx"
        except (OSError, zipfile.BadZipFile):
            return None
        return "zip"
    return None


def read_validated_upload(file_storage, max_bytes: int):
    """Read and validate a PDF/Word upload, returning bytes and a safe name."""
    if not file_storage or not file_storage.filename:
        return None, None

    filename = secure_filename(file_storage.filename)
    extension = os.path.splitext(filename)[1].lower()
    if extension not in {".pdf", ".docx", ".doc"}:
        raise UploadValidationError(
            f"{filename or 'The selected file'} must be a PDF, DOCX, or DOC document."
        )

    data = file_storage.read(max_bytes + 1)
    if not data:
        raise UploadValidationError(f"{filename} is empty.")
    if len(data) > max_bytes:
        limit_mb = max_bytes // (1024 * 1024)
        raise UploadValidationError(
            f"{filename} exceeds the {limit_mb} MB per-file limit."
        )

    detected = detect_document_type(data)
    if detected not in {"pdf", "docx", "doc"}:
        actual = (detected or "unknown").upper()
        raise UploadValidationError(
            f"{filename} contains unsupported {actual} data. "
            "Upload a genuine PDF, DOCX, or DOC document."
        )

    # Some legacy uploads have a Word payload with a .pdf name. Accept the
    # supported content but correct the saved name so browsers open it safely.
    correct_extension = DOCUMENT_TYPES[detected][0]
    if extension != correct_extension:
        filename = os.path.splitext(filename)[0] + correct_extension
    return data, filename


def response_document_metadata(data: bytes, filename: str | None, fallback: str):
    """Choose response metadata from actual bytes and repair a wrong extension."""
    kind = detect_document_type(data)
    safe_name = secure_filename(filename or fallback) or fallback
    if not kind:
        return "application/octet-stream", safe_name, True

    extension, mimetype = DOCUMENT_TYPES[kind]
    current_extension = os.path.splitext(safe_name)[1].lower()
    compatible = current_extension == extension or (
        kind == "jpeg" and current_extension in {".jpg", ".jpeg"}
    )
    if not compatible:
        safe_name = os.path.splitext(safe_name)[0] + extension

    # Browsers can render PDFs and common images. Office/ZIP files should download.
    return mimetype, safe_name, kind not in {"pdf", "png", "jpeg"}
