"""Behavior tests for the relay controller, metrics, and SiLA feature wiring.

The SimulatedRelay holds the same single-active-channel logic as the hardware
controller, so exercising it here covers the connector's behavioral contract
without serial hardware.
"""

import prometheus_client
import pytest

from unitelabs.cdk import Connector
from unitelabs.sainsmart_relay import SainsmartRelaySilaConfig
from unitelabs.sainsmart_relay.features import RelayControlFeature
from unitelabs.sainsmart_relay.io import ChannelOutOfRange, SimulatedRelay
from unitelabs.sainsmart_relay.metrics import RelayMetrics


@pytest.fixture
async def relay():
    r = SimulatedRelay(num_channels=16)
    await r.open()  # reset_on_start defaults True -> all open
    return r


def fresh_metrics():
    # isolated registry so tests don't collide on global metric names
    return RelayMetrics(registry=prometheus_client.CollectorRegistry())


async def test_reset_on_start_opens_all(relay):
    assert relay.active_channel == -1
    assert not any(relay.channel_states())


async def test_set_channel(relay):
    await relay.set_channel(5, True)
    assert relay.channel_states()[5] is True
    assert relay.active_channel == 5
    await relay.set_channel(5, False)
    assert relay.active_channel == -1


async def test_switch_guarantees_single_active(relay):
    await relay.switch_to_channel(3)
    assert relay.active_channel == 3
    await relay.switch_to_channel(7)
    assert relay.active_channel == 7
    assert [i for i, on in enumerate(relay.channel_states()) if on] == [7]  # only one closed, ever


async def test_switch_to_same_channel_is_noop(relay):
    await relay.switch_to_channel(2)
    states_before = relay.channel_states()
    await relay.switch_to_channel(2)
    assert relay.channel_states() == states_before


async def test_deactivate_all(relay):
    await relay.switch_to_channel(9)
    await relay.deactivate_all()
    assert relay.active_channel == -1
    assert not any(relay.channel_states())


async def test_out_of_range_raises(relay):
    with pytest.raises(ChannelOutOfRange):
        await relay.set_channel(16, True)
    with pytest.raises(ChannelOutOfRange):
        await relay.switch_to_channel(-1)


def test_metrics_track_active_channel():
    m = fresh_metrics()
    states = [False] * 16
    states[4] = True
    m.on_switch(4, states)
    assert m.active_channel._value.get() == 4
    assert m.switches_total.labels(channel="4")._value.get() == 1
    assert m.channel_state.labels(channel="4")._value.get() == 1


def test_metrics_active_minus_one_when_multiple_or_none():
    m = fresh_metrics()
    m.on_set([False] * 16)
    assert m.active_channel._value.get() == -1
    multi = [False] * 16
    multi[1] = multi[2] = True
    m.on_set(multi)
    assert m.active_channel._value.get() == -1  # ambiguous -> -1


def test_metrics_time_command_records_errors():
    m = fresh_metrics()
    msg = "boom"
    with pytest.raises(ValueError, match="boom"), m.time_command("switch"):
        raise ValueError(msg)
    assert m.command_errors_total.labels(op="switch", reason="ValueError")._value.get() == 1


async def test_feature_registers_cleanly():
    cfg = SainsmartRelaySilaConfig(use_simulator=True)
    r = SimulatedRelay(num_channels=16)
    await r.open()
    app = Connector(cfg)
    # Exercises SiLA feature-definition generation (commands, properties, dataclass structures).
    app.register(RelayControlFeature(r, fresh_metrics()))
