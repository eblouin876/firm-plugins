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


# --- StrictModel: strict=True (no lax-mode type coercion) ----------------


class _TypedModel(StrictModel):
    count: int
    active: bool


@pytest.mark.parametrize(
    "field, value",
    [
        ("count", "123"),  # numeric string -- lax mode would coerce to int
        ("active", 1),  # int -- lax mode would coerce to bool
        ("active", "yes"),  # string -- lax mode would coerce to bool
    ],
)
def test_strict_model_rejects_type_coercion(field, value):
    payload = {"count": 1, "active": True}
    payload[field] = value
    with pytest.raises(ValidationError):
        _TypedModel(**payload)


def test_strict_model_accepts_well_typed_values():
    model = _TypedModel(count=1, active=True)
    assert model.count == 1
    assert model.active is True


# --- no_control_chars ----------------------------------------------------


def test_no_control_chars_accepts_normal_text():
    assert no_control_chars("hello world") == "hello world"


@pytest.mark.parametrize(
    "text",
    [
        "café",  # accented Latin
        "中文",  # CJK
        "😀 emoji",  # emoji
        "Zürich, Москва, 東京",  # mixed scripts
    ],
)
def test_no_control_chars_accepts_legitimate_international_text(text):
    assert no_control_chars(text) == text


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


@pytest.mark.parametrize(
    "attack",
    [
        "safe\u202eevil",  # RLO -- Trojan-Source-style bidi override
        "safe\u202devil",  # LRO
        "safe\u2066evil",  # LRI bidi isolate
        "safe\u200bevil",  # ZWSP -- zero-width smuggling
        "safe\u200devil",  # ZWJ
        "safe\u200eevil",  # LRM
        "\ufeffsafe",  # BOM / zero-width no-break space
        "safe\xadevil",  # soft hyphen
    ],
)
def test_no_control_chars_rejects_bidi_and_format_controls(attack):
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


@pytest.mark.parametrize(
    "attack",
    [
        "CON",
        "con",
        "con.txt",
        "CON.TXT",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "com9.log",
        "LPT1",
        "lpt9.log",
    ],
)
def test_safe_filename_rejects_windows_reserved_names(attack):
    with pytest.raises(ValueError, match="reserved device name"):
        safe_filename(attack)


@pytest.mark.parametrize(
    "attack",
    [
        "report.txt.",  # trailing dot
        "report.txt ",  # trailing space
        "report:txt",  # colon -- NTFS ADS separator
    ],
)
def test_safe_filename_rejects_trailing_dot_space_and_colon(attack):
    with pytest.raises(ValueError):
        safe_filename(attack)


def test_safe_filename_accepts_name_that_merely_contains_reserved_substring():
    # "console.txt" is not the reserved name "CON" -- only an exact
    # base-name match (before the first dot) is rejected.
    assert safe_filename("console.txt") == "console.txt"


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
