"""In-memory relay with the same async API as SainsmartRelay (use_simulator=true)."""

from __future__ import annotations

import asyncio
import logging

from ._errors import ChannelOutOfRange
from .relay import build_command  # exercised so the byte builder stays covered in sim too

logger = logging.getLogger(__name__)


class SimulatedRelay:
    """Drop-in stand-in for SainsmartRelay - no hardware, in-memory channel state."""

    def __init__(self, *, num_channels: int = 16, reset_on_start: bool = True, **_: object) -> None:
        self.num_channels = num_channels
        self.reset_on_start = reset_on_start
        self._states = [False] * num_channels

    @property
    def connected(self) -> bool:
        """Always True - the simulator has no port to open."""
        return True

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
        """Start the simulator and apply reset_on_start (open all channels)."""
        logger.info("Relay simulator started (%d channels)", self.num_channels)
        if self.reset_on_start:
            await self.deactivate_all()

    async def set_channel(self, channel: int, closed: bool) -> None:
        """Set a single channel open/closed (validates the index, builds the real frame)."""
        self._validate(channel)
        _ = build_command(channel, closed)  # keep the real framing on the sim path
        await asyncio.sleep(0)
        self._states[channel] = closed

    async def deactivate_all(self) -> None:
        """Open every channel (no signal routed)."""
        for channel in range(self.num_channels):
            self._states[channel] = False
        await asyncio.sleep(0)

    async def switch_to_channel(self, channel: int) -> int:
        """Deactivate the active channel and activate `channel` (single-active guarantee)."""
        self._validate(channel)
        prev = self.active_channel
        if prev == channel:
            return channel
        if prev == -1:
            await self.deactivate_all()
        else:
            self._states[prev] = False
        self._states[channel] = True
        return channel

    async def close(self) -> None:
        """No-op: the simulator has no resources to release."""
        await asyncio.sleep(0)
