import collections.abc
import dataclasses
import logging
from importlib.metadata import version

from unitelabs.cdk import Connector, ConnectorBaseConfig, SiLAServerConfig

from ._env import apply_env_overrides, configure_log_level
from .features import RelayControlFeature
from .io import SainsmartRelay, SimulatedRelay
from .metrics import RelayMetrics, start_metrics_server

__version__ = version("unitelabs-sainsmart-relay-sila")

log = logging.getLogger(__name__)


@dataclasses.dataclass
class SainsmartRelaySilaConfig(ConnectorBaseConfig):
    """Configuration for the SainSmart Relay connector."""

    use_simulator: bool = True
    """Use the in-memory simulator instead of real serial hardware."""

    serial_port: str | None = None
    """Pin the serial port (e.g. ``COM11`` / ``/dev/ttyUSB0``). ``None`` = auto-detect by VID:PID."""

    usb_vid_pid: str = "1A86:7523"
    """USB VID:PID used for auto-detect when ``serial_port`` is unset (CH340)."""

    usb_serial_number: str | None = None
    """Optional USB serial number to disambiguate when multiple CH340 devices are present."""

    baudrate: int = 9600
    """Serial baud rate (SainSmart relay is fixed at 9600)."""

    num_channels: int = 16
    """Number of relay channels on the board."""

    reset_on_start: bool = True
    """Open all channels on startup so connector-tracked state is authoritative (sole owner)."""

    metrics_enabled: bool = True
    """Expose Prometheus metrics on ``metrics_port``."""

    metrics_port: int = 9110
    """Port for the Prometheus exposition endpoint (bound on 0.0.0.0)."""

    sila_server: SiLAServerConfig = dataclasses.field(
        default_factory=lambda: SiLAServerConfig(
            hostname="0.0.0.0",
            port=50051,
            name="SainSmart Relay",
            type="Switch",
            description="SiLA 2 connector for a SainSmart 16-channel USB relay (CH340, Modbus ASCII).",
            version=str(__version__),
            vendor_url="https://accelerationconsortium.ca/",
        )
    )


async def create_app(
    config: SainsmartRelaySilaConfig,
) -> collections.abc.AsyncGenerator[Connector, None]:
    """Create the connector application: wire the relay controller + SiLA feature + metrics."""
    configure_log_level()
    apply_env_overrides(config)  # RELAY_*/LOG_LEVEL overrides for Nomad raw_exec deploys
    log.info(
        "Starting SainSmart Relay connector v%s (simulator=%s, port=%s, channels=%d)",
        __version__,
        config.use_simulator,
        config.serial_port or "auto",
        config.num_channels,
    )

    if config.use_simulator:
        relay = SimulatedRelay(num_channels=config.num_channels, reset_on_start=config.reset_on_start)
    else:
        relay = SainsmartRelay(
            serial_port=config.serial_port,
            baudrate=config.baudrate,
            num_channels=config.num_channels,
            usb_vid_pid=config.usb_vid_pid,
            usb_serial_number=config.usb_serial_number,
            reset_on_start=config.reset_on_start,
        )

    metrics = RelayMetrics()
    srv = config.sila_server
    metrics.set_server_info(
        uuid=srv.uuid, name=srv.name, server_type=srv.type, version=str(srv.version), vendor_url=srv.vendor_url
    )
    if config.metrics_enabled:
        start_metrics_server(config.metrics_port)

    await relay.open()

    app = Connector(config)
    app.register(RelayControlFeature(relay, metrics))

    yield app

    await relay.close()
