"""Tests for the RELAY_*/LOG_LEVEL env-var overrides applied at create_app time."""

import logging

import pytest

from unitelabs.sainsmart_relay import SainsmartRelaySilaConfig
from unitelabs.sainsmart_relay._env import apply_env_overrides, configure_log_level


def test_defaults_unchanged_without_env(monkeypatch):
    for k in list(__import__("os").environ):
        if k.startswith("RELAY_"):
            monkeypatch.delenv(k, raising=False)
    cfg = apply_env_overrides(SainsmartRelaySilaConfig())
    assert cfg.use_simulator is True
    assert cfg.serial_port is None
    assert cfg.sila_server.name == "SainSmart Relay"  # default factory identity preserved


def test_hardware_overrides(monkeypatch):
    monkeypatch.setenv("RELAY_USE_SIMULATOR", "false")
    monkeypatch.setenv("RELAY_SERIAL_PORT", "COM11")
    monkeypatch.setenv("RELAY_METRICS_PORT", "9131")
    cfg = apply_env_overrides(SainsmartRelaySilaConfig())
    assert cfg.use_simulator is False
    assert cfg.serial_port == "COM11"
    assert cfg.metrics_port == 9131


def test_empty_serial_port_means_auto(monkeypatch):
    monkeypatch.setenv("RELAY_SERIAL_PORT", "")
    cfg = apply_env_overrides(SainsmartRelaySilaConfig())
    assert cfg.serial_port is None


def test_uuid_pin_preserves_identity(monkeypatch):
    monkeypatch.setenv("RELAY_UUID", "11111111-2222-3333-4444-555555555555")
    monkeypatch.setenv("RELAY_SILA_PORT", "50055")
    cfg = apply_env_overrides(SainsmartRelaySilaConfig())
    assert cfg.sila_server.uuid == "11111111-2222-3333-4444-555555555555"
    assert cfg.sila_server.port == 50055
    # overriding uuid/port must NOT wipe the connector's name/type/version
    assert cfg.sila_server.name == "SainSmart Relay"
    assert cfg.sila_server.type == "Switch"


def test_invalid_bool_raises(monkeypatch):
    monkeypatch.setenv("RELAY_USE_SIMULATOR", "maybe")
    with pytest.raises(ValueError, match="boolean"):
        apply_env_overrides(SainsmartRelaySilaConfig())


def test_log_level_applies(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "warning")
    try:
        configure_log_level()
        assert logging.getLogger().level == logging.WARNING
    finally:
        logging.getLogger().setLevel(logging.WARNING)  # leave deterministic
