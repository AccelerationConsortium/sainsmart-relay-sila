"""
SainSmart 16-channel USB relay (CH340, Modbus ASCII) - serial controller.

Reproduces the exact command framing, checksum, and timing of the original
sdl1chem driver (`src/echem_uos/drivers/sainsmart_relay.py`) so the bytes on the
wire - and therefore the physical behavior - are identical.

The board is write-only (it echoes a response we ignore). State is therefore
connector-tracked: this connector is the sole owner of the relay and resets to a
known baseline on start (`reset_on_start`), so `active_channel` is authoritative.
pyserial is blocking, so blocking I/O runs in a thread and a lock serializes the
port (one command at a time).
"""

from __future__ import annotations

import asyncio
import logging

import serial
from serial.tools import list_ports

from ._errors import ChannelOutOfRange, RelayCommunicationError

logger = logging.getLogger(__name__)

# Protocol constants - verbatim from the legacy SainsmartRelayHAL.
_HEADER = 0xFE
_CMD_WRITE_COIL = 0x05
_ADDR = 0x00
_VALUE_LOW = 0x00
_ON = 0xFF
_OFF = 0x00

CONNECT_SETTLE_S = 2.0
COMMAND_READ_WAIT_S = 0.1
DEACTIVATE_ALL_GAP_S = 0.05


def build_command(channel: int, state: bool) -> bytes:
    r"""
    Build the Modbus-ASCII Write-Single-Coil frame (identical to the legacy driver).

    e.g. channel 0 ON -> b':FE050000FF00FE\r\n'.
    """
    value_high = _ON if state else _OFF
    checksum = (256 - ((_HEADER + _CMD_WRITE_COIL + _ADDR + channel + value_high + _VALUE_LOW) % 256)) % 256
    frame = f":FE{_CMD_WRITE_COIL:02X}{_ADDR:02X}{channel:02X}{value_high:02X}{_VALUE_LOW:02X}{checksum:02X}\r\n"
    return frame.encode("ascii")


def resolve_port(
    serial_port: str | None,
    usb_vid_pid: str = "1A86:7523",
    usb_serial_number: str | None = None,
) -> str:
    """
    Resolve the serial port: an explicit pin wins, else auto-detect by USB VID:PID.

    Raises RelayCommunicationError (listing the ports seen) if zero or >1 candidates
    match, so the operator knows to pin `serial_port`.
    """
    if serial_port:
        return serial_port

    target = usb_vid_pid.lower().replace(":", "")
    ports = list(list_ports.comports())
    matches = []
    for p in ports:
        ident = f"{p.vid:04x}{p.pid:04x}" if p.vid is not None and p.pid is not None else ""
        if ident == target or target in (p.hwid or "").lower().replace(":", ""):
            if usb_serial_number and (p.serial_number or "") != usb_serial_number:
                continue
            matches.append(p.device)

    if len(matches) == 1:
        return matches[0]
    seen = ", ".join(f"{p.device} [{p.hwid}]" for p in ports) or "(none)"
    if not matches:
        msg = f"No relay with USB VID:PID {usb_vid_pid} found. Ports seen: {seen}. Set serial_port to pin one."
        raise RelayCommunicationError(msg)
    msg = f"Multiple devices match VID:PID {usb_vid_pid}: {matches}. Set serial_port or usb_serial_number."
    raise RelayCommunicationError(msg)


class SainsmartRelay:
    """Async controller for the SainSmart 16-channel relay over serial."""

    def __init__(
        self,
        *,
        serial_port: str | None = None,
        baudrate: int = 9600,
        timeout: float = 1.0,
        num_channels: int = 16,
        usb_vid_pid: str = "1A86:7523",
        usb_serial_number: str | None = None,
        reset_on_start: bool = True,
    ) -> None:
        self.num_channels = num_channels
        self.reset_on_start = reset_on_start
        self._serial_port = serial_port
        self._baudrate = baudrate
        self._timeout = timeout
        self._usb_vid_pid = usb_vid_pid
        self._usb_serial_number = usb_serial_number
        self._serial: serial.Serial | None = None
        self._lock = asyncio.Lock()
        self._states = [False] * num_channels

    @property
    def connected(self) -> bool:
        """Whether the serial port is open."""
        return self._serial is not None and self._serial.is_open

    @property
    def active_channel(self) -> int:
        """The single active channel, or -1 if none (or, defensively, more than one)."""
        active = [i for i, on in enumerate(self._states) if on]
        return active[0] if len(active) == 1 else -1

    def channel_states(self) -> list[bool]:
        """Return a snapshot of every channel's coil state (True = closed)."""
        return list(self._states)

    def _validate(self, channel: int) -> None:
        if not (0 <= channel < self.num_channels):
            msg = f"Channel {channel} out of range (0..{self.num_channels - 1})."
            raise ChannelOutOfRange(msg)

    async def open(self) -> None:
        """Resolve and open the serial port, settle, and apply reset_on_start."""
        port = resolve_port(self._serial_port, self._usb_vid_pid, self._usb_serial_number)
        try:
            self._serial = await asyncio.to_thread(serial.Serial, port, self._baudrate, timeout=self._timeout)
        except serial.SerialException as exc:
            msg = f"Could not open relay on {port}: {exc}"
            raise RelayCommunicationError(msg) from exc
        await asyncio.sleep(CONNECT_SETTLE_S)
        logger.info("Relay connected on %s @ %d baud", port, self._baudrate)
        if self.reset_on_start:
            await self.deactivate_all()

    async def _write(self, channel: int, state: bool) -> None:
        if not self.connected:
            msg = "Relay is not connected."
            raise RelayCommunicationError(msg)
        frame = build_command(channel, state)
        async with self._lock:
            try:
                await asyncio.to_thread(self._serial.write, frame)
                await asyncio.sleep(COMMAND_READ_WAIT_S)
                await asyncio.to_thread(self._serial.readline)  # response is echoed but unused
            except serial.SerialException as exc:
                msg = f"Relay write failed (ch {channel}): {exc}"
                raise RelayCommunicationError(msg) from exc
        self._states[channel] = state

    async def set_channel(self, channel: int, closed: bool) -> None:
        """Set a single channel open/closed; validates the channel index first."""
        self._validate(channel)
        await self._write(channel, closed)

    async def deactivate_all(self) -> None:
        """Open every channel in turn (no signal routed)."""
        for channel in range(self.num_channels):
            await self._write(channel, False)
            await asyncio.sleep(DEACTIVATE_ALL_GAP_S)

    async def switch_to_channel(self, channel: int) -> int:
        """
        Deactivate the currently-active channel and activate `channel` (no-op if already active).

        If the prior active channel is unknown (-1: none or, defensively, multiple), deactivate
        all first so we can never leave two channels closed at once.
        """
        self._validate(channel)
        prev = self.active_channel
        if prev == channel:
            return channel
        if prev == -1:
            await self.deactivate_all()
        else:
            await self._write(prev, False)
        await self._write(channel, True)
        return channel

    async def close(self) -> None:
        """
        Close the port WITHOUT deactivating (preserve the latched routing).

        The next `open()` re-establishes a known baseline when reset_on_start is set.
        """
        if self._serial is not None:
            await asyncio.to_thread(self._serial.close)
            self._serial = None
