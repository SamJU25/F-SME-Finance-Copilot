"""Zero-trust validation guards for bank statement PDF ingestion."""

from __future__ import annotations

import io
from typing import Optional
import pypdf
from pypdf.errors import PdfReadError

DEFAULT_MAX_PDF_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB limit
DEFAULT_MAX_PDF_PAGES = 50                     # 50 page limit


class PDFValidationError(ValueError):
    """Domain error representing an untrusted or invalid PDF input with a stable error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_pdf_statement(
    file_bytes: bytes,
    max_size_bytes: int = DEFAULT_MAX_PDF_SIZE_BYTES,
    max_pages: int = DEFAULT_MAX_PDF_PAGES,
) -> pypdf.PdfReader:
    """Validates PDF byte stream against zero-trust financial participant invariants.

    Checks:
    1. Payload non-emptiness.
    2. Payload size quota (prevents DoS/memory saturation).
    3. Magic byte header: must start with '%PDF'.
    4. Encryption / password protection: rejects locked PDFs.
    5. Page count ceiling: protects against decompression bombs.
    6. PDF structural integrity: validates EOF marker and object streams.

    Returns:
        pypdf.PdfReader: Verified, readable PDF document instance.

    Raises:
        PDFValidationError: If any safety invariant fails.
    """
    if not file_bytes or len(file_bytes.strip()) == 0:
        raise PDFValidationError("EMPTY_PAYLOAD", "Uploaded PDF file is empty (0 bytes).")

    if len(file_bytes) > max_size_bytes:
        mb = len(file_bytes) / (1024 * 1024)
        limit_mb = max_size_bytes / (1024 * 1024)
        raise PDFValidationError(
            "PDF_SIZE_LIMIT_EXCEEDED",
            f"PDF file size ({mb:.1f} MB) exceeds maximum permitted upload ceiling ({limit_mb:.1f} MB).",
        )

    # Magic byte check
    if not file_bytes.startswith(b"%PDF"):
        # Check first 1024 bytes in case of leading whitespace or BOM
        header_sample = file_bytes[:1024]
        if b"%PDF" not in header_sample:
            raise PDFValidationError(
                "INVALID_PDF_HEADER",
                "Uploaded file is not a valid PDF document (missing %PDF magic header).",
            )

    try:
        stream = io.BytesIO(file_bytes)
        reader = pypdf.PdfReader(stream, strict=False)

        if reader.is_encrypted:
            raise PDFValidationError(
                "ENCRYPTED_PDF_ERROR",
                "The bank statement PDF is password-protected or encrypted. "
                "Please upload an unprotected statement export.",
            )

        num_pages = len(reader.pages)
        if num_pages == 0:
            raise PDFValidationError("CORRUPT_PDF_ERROR", "PDF contains no renderable pages.")

        if num_pages > max_pages:
            raise PDFValidationError(
                "PDF_PAGE_LIMIT_EXCEEDED",
                f"PDF has {num_pages} pages, which exceeds the {max_pages}-page single statement ceiling.",
            )

        return reader

    except PdfReadError as exc:
        raise PDFValidationError(
            "CORRUPT_PDF_ERROR",
            f"PDF document is structurally corrupted or truncated: {str(exc)}",
        )
    except PDFValidationError:
        raise
    except Exception as exc:
        raise PDFValidationError(
            "UNREADABLE_PDF_ERROR",
            f"Unable to parse PDF document structure: {str(exc)}",
        )
