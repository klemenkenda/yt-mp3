import pytest

from yt_mp3.util import MAX_NAME_LEN, sanitize_filename


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Hello World", "Hello World"),
        ('AC/DC: "Back in Black" <HQ>?', "AC_DC_ _Back in Black_ _HQ__"),
        ("trailing dots...", "trailing dots"),
        ("   spaced   out   ", "spaced out"),
        ("", "untitled"),
        ("...", "untitled"),
        ("CON", "_CON"),
        ("nul.txt", "_nul.txt"),
        ("Console", "Console"),
        ("tab\there", "tab_here"),
        ("Čeština – ünïcode 🎵", "Čeština – ünïcode 🎵"),
    ],
)
def test_sanitize(raw, expected):
    assert sanitize_filename(raw) == expected


def test_sanitize_length():
    assert len(sanitize_filename("a" * 500)) == MAX_NAME_LEN
