"""SiLA 2 feature for the SainSmart relay - routes a signal to one of N channels."""

import typing
from dataclasses import dataclass

from unitelabs.cdk import sila
from unitelabs.cdk.sila import constraints

from ..io import ChannelOutOfRange, RelayCommunicationError, SainsmartRelay, SimulatedRelay
from ..metrics import RelayMetrics

# 16-channel device. The bound is encoded in the SiLA Feature Definition and validated
# cross-language on the wire (hardcoded, not the configurable num_channels).
Channel = typing.Annotated[int, constraints.MinimalInclusive(0), constraints.MaximalInclusive(15)]


@dataclass
class ChannelState:
    """State of a single relay channel."""

    channel: Channel
    closed: bool


@dataclass
class ActiveChannel:
    """The currently-routed channel (avoids a -1 sentinel)."""

    channel: int
    has_active: bool


class RelayControlFeature(sila.Feature):
    """Control a SainSmart 16-channel relay: route the signal to one channel at a time."""

    def __init__(self, controller: SainsmartRelay | SimulatedRelay, metrics: RelayMetrics) -> None:
        super().__init__(originator="ca.accelerationconsortium", category="switches")
        self._relay = controller
        self._metrics = metrics

    def _active(self) -> ActiveChannel:
        ch = self._relay.active_channel
        return ActiveChannel(channel=ch, has_active=ch >= 0)

    @sila.UnobservableCommand(errors=[RelayCommunicationError, ChannelOutOfRange])
    async def switch_to_channel(self, channel: Channel) -> ActiveChannel:
        """
        Deactivate the currently-active channel and activate `channel` (no-op if already active).

        This is the core operation - it guarantees only one channel is ever closed.
        """
        with self._metrics.time_command("switch"):
            await self._relay.switch_to_channel(channel)
        self._metrics.on_switch(channel, self._relay.channel_states())
        return self._active()

    @sila.UnobservableCommand(errors=[RelayCommunicationError, ChannelOutOfRange])
    async def set_channel(self, channel: Channel, closed: bool) -> ChannelState:
        """Set a single channel open/closed directly (does not deactivate others)."""
        with self._metrics.time_command("set"):
            await self._relay.set_channel(channel, closed)
        self._metrics.on_set(self._relay.channel_states())
        return ChannelState(channel=channel, closed=closed)

    @sila.UnobservableCommand(errors=[RelayCommunicationError])
    async def deactivate_all(self) -> None:
        """Open every channel (no signal routed)."""
        with self._metrics.time_command("deactivate_all"):
            await self._relay.deactivate_all()
        self._metrics.on_set(self._relay.channel_states())

    @sila.UnobservableCommand(errors=[RelayCommunicationError])
    async def get_channel_states(self) -> list[ChannelState]:
        """Return the state of every channel (connector-tracked; authoritative - sole owner)."""
        return [ChannelState(channel=i, closed=on) for i, on in enumerate(self._relay.channel_states())]

    @sila.UnobservableProperty()
    async def active_channel(self) -> ActiveChannel:
        """Return the channel the signal is currently routed to (has_active=false if none)."""
        return self._active()

    @sila.UnobservableProperty()
    async def channel_count(self) -> int:
        """Return the number of relay channels on this device."""
        return self._relay.num_channels
