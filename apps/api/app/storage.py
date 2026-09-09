"""Photo storage for complaint attachments.

The build plan targets Supabase Storage. Without a Supabase project the
equivalent, and the only honest option that is not fake, is to store the
bytes on the API host and serve them from a mounted static route — the
backend still owns the write, the frontend still gets back a URL it does
nothing special with, and swapping in a Supabase/S3 upload later means
replacing one function body.

What matters more than where the bytes land is that we never trusted the
client about them (plan phase 16, "insecure file uploads"):

- The declared content type is ignored; the format is decided by magic
  bytes, and anything that is not a real JPEG/PNG/GIF/WebP is rejected.
  A `.jpg` that is actually an HTML document or a script never gets stored.
- The filename is generated, never taken from the upload. There is no path
  the client controls, so there is no path traversal to defend against.
- Size is capped before decode (base64 inflates ~33%, so the encoded length
  is checked first) and again after.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from pathlib import Path

from app.config import get_settings

# magic-byte prefix -> (extension, mime type). This is the allowlist: a
# payload whose first bytes match nothing here is not an image we accept.
_SIGNATURES: list[tuple[bytes, str, str]] = [
    (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
    (b"\xff\xd8\xff", "jpg", "image/jpeg"),
    (b"GIF87a", "gif", "image/gif"),
    (b"GIF89a", "gif", "image/gif"),
]


class InvalidPhotoError(ValueError):
    """The supplied photo was missing, malformed, oversized or not an image."""


def _sniff(data: bytes) -> tuple[str, str]:
    for prefix, extension, mime in _SIGNATURES:
        if data.startswith(prefix):
            return extension, mime
    # WebP needs a two-part check: "RIFF" .... "WEBP".
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    raise InvalidPhotoError(
        "attachment is not a recognized image (expected JPEG, PNG, GIF or WebP)"
    )


def decode_photo(photo_base64: str | None) -> tuple[bytes, str, str] | None:
    """Decode and validate a (possibly data-URL-prefixed) base64 photo.

    Returns `(raw_bytes, extension, mime_type)`, or `None` when no photo was
    supplied. Raises `InvalidPhotoError` for anything supplied but unusable,
    so the caller can return a 422 that tells the student what was wrong
    instead of silently dropping their evidence.
    """
    if not photo_base64:
        return None

    settings = get_settings()
    encoded = photo_base64.split(",", 1)[1] if "," in photo_base64 else photo_base64

    # base64 is ~4/3 the size of the bytes it encodes. Checking the encoded
    # length first means a 500 MB payload is rejected without allocating a
    # 375 MB bytes object to find that out.
    if len(encoded) > settings.max_upload_bytes * 4 // 3 + 8:
        raise InvalidPhotoError(
            f"photo is larger than the {settings.max_upload_bytes // (1024 * 1024)} MB limit"
        )

    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise InvalidPhotoError("photo is not valid base64") from exc

    if not data:
        raise InvalidPhotoError("photo payload was empty")
    if len(data) > settings.max_upload_bytes:
        raise InvalidPhotoError(
            f"photo is larger than the {settings.max_upload_bytes // (1024 * 1024)} MB limit"
        )

    extension, mime = _sniff(data)
    return data, extension, mime


def save_photo(data: bytes, extension: str) -> str:
    """Write `data` to the upload directory and return its public URL path.

    The returned value is a root-relative path (`/uploads/<uuid>.<ext>`)
    rather than an absolute URL, so the same stored row works whether the
    API is reached on localhost, a LAN IP, or a tunnel during the demo.
    """
    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid.uuid4().hex}.{extension}"
    (upload_dir / filename).write_bytes(data)
    return f"/uploads/{filename}"
