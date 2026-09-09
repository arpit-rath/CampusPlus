"""Photo upload validation.

These are security tests, not feature tests. Everything here is a case where
accepting the input would be the bug: a payload that claims to be an image
and is not, one large enough to be a denial-of-service, and one crafted to
control where a file lands on disk.
"""

from __future__ import annotations

import base64

import pytest

from app.config import get_settings
from app.storage import InvalidPhotoError, decode_photo, save_photo

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
GIF = b"GIF89a" + b"\x00" * 64
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 64


def _data_url(raw: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def test_no_photo_is_not_an_error():
    assert decode_photo(None) is None
    assert decode_photo("") is None


@pytest.mark.parametrize(
    ("raw", "expected_ext"),
    [(PNG, "png"), (JPEG, "jpg"), (GIF, "gif"), (WEBP, "webp")],
)
def test_accepts_each_supported_format(raw, expected_ext):
    data, extension, mime = decode_photo(_data_url(raw))
    assert data == raw
    assert extension == expected_ext
    assert mime.startswith("image/")


def test_accepts_bare_base64_without_a_data_url_prefix():
    data, extension, _ = decode_photo(base64.b64encode(PNG).decode())
    assert data == PNG
    assert extension == "png"


def test_rejects_a_non_image_masquerading_as_one():
    """The declared mime type is a lie; magic bytes decide.

    Without this check an HTML document or a script could be stored and then
    served back from our own origin by the /uploads mount.
    """
    html = b"<html><script>alert(1)</script></html>"
    with pytest.raises(InvalidPhotoError, match="not a recognized image"):
        decode_photo(_data_url(html, mime="image/png"))


def test_rejects_a_zip_or_executable_payload():
    with pytest.raises(InvalidPhotoError):
        decode_photo(_data_url(b"PK\x03\x04" + b"\x00" * 32))
    with pytest.raises(InvalidPhotoError):
        decode_photo(_data_url(b"MZ" + b"\x00" * 32))


def test_rejects_invalid_base64():
    with pytest.raises(InvalidPhotoError, match="not valid base64"):
        decode_photo("data:image/png;base64,!!!not base64 at all!!!")


def test_rejects_an_empty_payload():
    with pytest.raises(InvalidPhotoError, match="empty"):
        decode_photo("data:image/png;base64,")


def test_rejects_an_oversized_payload_without_decoding_it():
    settings = get_settings()
    # Comfortably over the cap once decoded, and rejected on the encoded
    # length so the huge bytes object is never allocated.
    oversized = "A" * (settings.max_upload_bytes * 2)
    with pytest.raises(InvalidPhotoError, match="larger than"):
        decode_photo(f"data:image/png;base64,{oversized}")


def test_saved_filename_is_generated_not_taken_from_the_client(tmp_path, monkeypatch):
    """There is no client-controlled component in the stored path.

    The upload API never accepts a filename at all, and this pins that: the
    name is a fresh uuid plus the sniffed extension, so `../../etc/passwd`
    has nowhere to enter.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "upload_dir", tmp_path)

    url = save_photo(PNG, "png")
    assert url.startswith("/uploads/")
    assert ".." not in url and "/" not in url[len("/uploads/") :]

    stored = tmp_path / url.rsplit("/", 1)[1]
    assert stored.read_bytes() == PNG

    # Two saves of identical bytes never collide.
    assert save_photo(PNG, "png") != url
