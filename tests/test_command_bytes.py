"""Byte-exact protocol tests.

These lock the on-the-wire framing to the original sdl1chem driver
(`src/echem_uos/drivers/sainsmart_relay.py::_build_command_packet`). If any of
these change, the physical relay behavior changes - so they are golden vectors.
"""

import pytest

from unitelabs.sainsmart_relay.io import build_command

# Golden frames computed from the legacy driver's algorithm. Channels are 0-indexed
# on the wire (the legacy logs show 1-indexed, but the byte is channel_zero_indexed).
GOLDEN = {
    (0, True): b":FE050000FF00FE\r\n",
    (0, False): b":FE0500000000FD\r\n",
    (1, True): b":FE050001FF00FD\r\n",
    (15, True): b":FE05000FFF00EF\r\n",
    (15, False): b":FE05000F0000EE\r\n",
}


@pytest.mark.parametrize(("channel", "state", "expected"), [(c, s, e) for (c, s), e in GOLDEN.items()])
def test_build_command_golden(channel, state, expected):
    assert build_command(channel, state) == expected


def test_frame_structure():
    frame = build_command(3, True)
    assert frame.startswith(b":FE05")  # ':' + header FE + write-single-coil cmd 05
    assert frame.endswith(b"\r\n")
    assert frame[1:-2].decode("ascii").isalnum()  # only ASCII hex between ':' and CRLF


@pytest.mark.parametrize("channel", range(16))
@pytest.mark.parametrize("state", [True, False])
def test_checksum_invariant(channel, state):
    """The checksum is the two's-complement LRC: the six value bytes + checksum == 0 mod 256."""
    frame = build_command(channel, state)
    body = frame[1:-2]  # strip ':' and CRLF -> 14 hex chars = 7 bytes
    values = [int(body[i : i + 2], 16) for i in range(0, len(body), 2)]
    assert len(values) == 7
    assert sum(values) % 256 == 0


def test_on_off_differ_only_in_value_and_checksum():
    on = build_command(4, True)
    off = build_command(4, False)
    # positions: :FE 05 00 <ch> <vh> <vl> <cs>; value-high byte is chars 9:11
    assert on[:9] == off[:9]
    assert on[9:11] == b"FF"
    assert off[9:11] == b"00"
