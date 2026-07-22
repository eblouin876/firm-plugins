"""Tests for the input-validation drop-in. No real user data — every value
is a synthetic fixture or an obviously-fake attack payload."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from validation import (
    ExampleHardenedInput,
    SafeIdentifier,
    Slug,
    StrictModel,
    check_max_bytes,
    check_max_length,
    no_control_chars,
    safe_filename,
)


# --- StrictModel: extra="forbid" (mass-assignment defense) --------------


class _Widget(StrictModel):
    name: str


def test_strict_model_accepts_declared_fields():
    widget = _Widget(name="gadget")
    assert widget.name == "gadget"


def test_strict_model_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        _Widget(name="gadget", is_admin=True)  # mass-assignment attempt


def test_strict_model_strips_whitespace():
    widget = _Widget(name="  gadget  ")
    assert widget.name == "gadget"


def test_strict_model_revalidates_on_assignment():
    widget = _Widget(name="gadget")
    with pytest.raises(ValidationError):
        widget.name = 12345  # not a str -- must fail post-construction too


# --- no_control_chars ----------------------------------------------------


def test_no_control_chars_accepts_normal_text():
    assert no_control_chars("hello world") == "hello world"


@pytest.mark.parametrize(
    "attack",
    [
        "hello\x00world",  # null byte
        "hello\x1bworld",  # ESC -- terminal escape injection
        "line1\nline2\rinjected",  # CR/LF log injection
        "\x07bell",
    ],
)
def test_no_control_chars_rejects_control_characters(attack):
    with pytest.raises(ValueError, match="control character"):
        no_control_chars(attack)


# --- safe_filename: the path-traversal attack shapes ---------------------


def test_safe_filename_accepts_plain_name():
    assert safe_filename("report.pdf") == "report.pdf"


@pytest.mark.parametrize(
    "attack",
    [
        "../../etc/passwd",
        "..",
        "../secrets.env",
        "subdir/file.txt",
        "..\\..\\windows\\system32\\config",
        "a\\b.txt",
        ".hidden",
        ".",
        "",
        "with\x00null.txt",
        "with\x1bescape.txt",
    ],
)
def test_safe_filename_rejects_attack_shapes(attack):
    with pytest.raises(ValueError):
        safe_filename(attack)


def test_safe_filename_rejects_oversize_name():
    with pytest.raises(ValidationError):
        ExampleHardenedInput(
            username="alice",
            slug="my-post",
            bio="hello",
            filename="a" * 300 + ".txt",
        )


# --- SafeIdentifier / Slug patterns ---------------------------------------


class _IdModel(StrictModel):
    ident: SafeIdentifier


class _SlugModel(StrictModel):
    slug: Slug


@pytest.mark.parametrize("value", ["valid_id", "_leading_underscore", "Camel1"])
def test_safe_identifier_accepts_valid_shapes(value):
    assert _IdModel(ident=value).ident == value


@pytest.mark.parametrize(
    "value",
    ["1starts-with-digit", "has space", "has-hyphen", "has.dot", "semi;colon", ""],
)
def test_safe_identifier_rejects_invalid_shapes(value):
    with pytest.raises(ValidationError):
        _IdModel(ident=value)


@pytest.mark.parametrize("value", ["my-post", "post2", "a-b-c-123"])
def test_slug_accepts_valid_shapes(value):
    assert _SlugModel(slug=value).slug == value


@pytest.mark.parametrize(
    "value",
    ["My-Post", "-leading-hyphen", "trailing-hyphen-", "double--hyphen", "has space", ""],
)
def test_slug_rejects_invalid_shapes(value):
    with pytest.raises(ValidationError):
        _SlugModel(slug=value)


# --- size / limit helpers -------------------------------------------------


def test_check_max_bytes_accepts_within_limit():
    payload = b"x" * 100
    assert check_max_bytes(payload, max_bytes=1024) == payload


def test_check_max_bytes_rejects_oversize_payload():
    payload = b"x" * (10 * 1024 * 1024 + 1)  # 10 MiB + 1 byte
    with pytest.raises(ValueError, match="exceeds"):
        check_max_bytes(payload, max_bytes=10 * 1024 * 1024, label="upload")


def test_check_max_length_rejects_oversize_string():
    with pytest.raises(ValueError, match="exceeds"):
        check_max_length("x" * 1000, max_length=100, label="comment")


# --- composed model: the whole hardened shape together --------------------


def test_example_hardened_input_accepts_well_formed_data():
    model = ExampleHardenedInput(
        username="alice_01",
        slug="hello-world",
        bio="A short, safe bio.",
        filename="avatar.png",
    )
    assert model.username == "alice_01"
    assert model.filename == "avatar.png"


def test_example_hardened_input_rejects_control_char_in_bio():
    with pytest.raises(ValidationError):
        ExampleHardenedInput(
            username="alice",
            slug="hello-world",
            bio="malicious\x00payload",
            filename="avatar.png",
        )


def test_example_hardened_input_rejects_traversal_filename():
    with pytest.raises(ValidationError):
        ExampleHardenedInput(
            username="alice",
            slug="hello-world",
            bio="fine",
            filename="../../etc/passwd",
        )


def test_example_hardened_input_rejects_unknown_field():
    with pytest.raises(ValidationError):
        ExampleHardenedInput(
            username="alice",
            slug="hello-world",
            bio="fine",
            filename="avatar.png",
            is_admin=True,  # mass-assignment attempt
        )
