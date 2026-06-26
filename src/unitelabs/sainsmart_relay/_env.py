"""
Environment-variable overrides for the connector config.

``unitelabs.cdk.run(create_app)`` validates the config from defaults only (it does
not read a config file), so the frozen ``relay-connector.exe`` would otherwise
always run with defaults (simulator). Nomad ``raw_exec`` configures processes via
env vars - the same pattern the BLE forwarder uses - so we apply a small set of
``RELAY_*`` / ``LOG_LEVEL`` overrides onto the full default config object. This
deep-merges by construction (only named fields are touched), so the connector's
name/type/version on ``sila_server`` are preserved while ``uuid`` etc. are pinned.

With no env vars set (e.g. local dev, the CI smoke test) the defaults stand and
the connector boots the simulator.
"""

import logging
import os

logger = logging.getLogger(__name__)

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def _as_bool(value: str) -> bool:
    v = value.strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    msg = f"Expected a boolean (true/false), got {value!r}."
    raise ValueError(msg)


def apply_env_overrides(config: object) -> object:
    """Mutate `config` in place from RELAY_*/LOG_LEVEL env vars and return it."""
    env = os.environ

    if "RELAY_USE_SIMULATOR" in env:
        config.use_simulator = _as_bool(env["RELAY_USE_SIMULATOR"])
    if "RELAY_SERIAL_PORT" in env:
        # An empty value means "auto-detect" (None), so a deploy can clear a pin.
        config.serial_port = env["RELAY_SERIAL_PORT"] or None
    if "RELAY_USB_VID_PID" in env:
        config.usb_vid_pid = env["RELAY_USB_VID_PID"]
    if "RELAY_USB_SERIAL_NUMBER" in env:
        config.usb_serial_number = env["RELAY_USB_SERIAL_NUMBER"] or None
    if "RELAY_NUM_CHANNELS" in env:
        config.num_channels = int(env["RELAY_NUM_CHANNELS"])
    if "RELAY_METRICS_ENABLED" in env:
        config.metrics_enabled = _as_bool(env["RELAY_METRICS_ENABLED"])
    if "RELAY_METRICS_PORT" in env:
        config.metrics_port = int(env["RELAY_METRICS_PORT"])

    # SiLA server identity / bind - pinned per deployment.
    if env.get("RELAY_UUID"):
        config.sila_server.uuid = env["RELAY_UUID"]
    if "RELAY_SILA_PORT" in env:
        config.sila_server.port = int(env["RELAY_SILA_PORT"])
    if "RELAY_SILA_HOSTNAME" in env:
        config.sila_server.hostname = env["RELAY_SILA_HOSTNAME"]

    return config


def configure_log_level() -> None:
    """Apply the LOG_LEVEL env var (DEBUG/INFO/WARNING/ERROR) to the root logger."""
    level = os.environ.get("LOG_LEVEL")
    if not level:
        return
    resolved = logging.getLevelName(level.strip().upper())
    if isinstance(resolved, int):
        logging.getLogger().setLevel(resolved)
    else:
        logger.warning("Ignoring invalid LOG_LEVEL=%r", level)
