# SainSmart Relay

A SiLA 2 connector for the SainSmart 16-channel USB relay (CH340, Modbus ASCII),
built on the [UniteLabs CDK](https://gitlab.com/unitelabs/cdk). It exposes the
relay over a SiLA 2 gRPC interface and serves Prometheus metrics, so the relay
can be driven from any SiLA client and observed in the existing Grafana stack.

The on-the-wire serial framing is byte-for-byte identical to the original
`sdl1chem` driver (`tests/test_command_bytes.py` locks the golden frames), so the
physical relay behavior is unchanged.

## What it exposes

`RelayControlFeature` (SiLA feature, originator `ca.accelerationconsortium`,
category `switches`):

| Command / Property      | Description |
| ----------------------- | ----------- |
| `switch_to_channel(ch)` | Deactivate the active channel and activate `ch`. Guarantees only one channel is ever closed. |
| `set_channel(ch, closed)` | Set a single channel open/closed directly. |
| `deactivate_all()`      | Open every channel (no signal routed). |
| `get_channel_states()`  | State of every channel (connector-tracked; authoritative). |
| `active_channel`        | The currently-routed channel (`has_active=false` if none). |
| `channel_count`         | Number of channels on the board. |

The connector is the **sole owner** of the relay: it resets all channels open on
start (`reset_on_start`), so its tracked state is authoritative by construction.

## Ports

- SiLA gRPC server binds `0.0.0.0:50051`.
- Prometheus `/metrics` binds `0.0.0.0:9110`.

Both bind all interfaces so a containerized consumer (e.g. `echem-uos`, Prometheus)
can reach this native host process at `host.docker.internal:<port>`.

## Configuration

`SainsmartRelaySilaConfig` keys (set via `config.json`/`config.yaml` or env vars):

| Key | Default | Notes |
| --- | ------- | ----- |
| `use_simulator` | `true` | In-memory simulator; set `false` for real hardware. |
| `serial_port` | `null` | Pin the port (e.g. `COM11`). `null` = auto-detect by VID:PID. |
| `usb_vid_pid` | `1A86:7523` | CH340 VID:PID for auto-detect. |
| `usb_serial_number` | `null` | Disambiguate when multiple CH340 devices are present. |
| `num_channels` | `16` | Channels on the board. |
| `reset_on_start` | `true` | Open all channels on startup (sole-owner state model). |
| `metrics_enabled` | `true` | Expose Prometheus `/metrics`. |
| `metrics_port` | `9110` | Metrics port. |

With no config file present the connector boots with these defaults
(`use_simulator=true`) - this is exactly what the CI simulator-boot smoke test
exercises against the frozen `.exe`.

### Metrics

`relay_active_channel`, `relay_channel_state{channel}`, `relay_switches_total{channel}`,
`relay_command_errors_total{op,reason}`, `relay_command_duration_seconds{op}`,
`relay_last_switch_timestamp_seconds`, and `sila_server_info{uuid,name,type,version,vendor_url}`
(the SiLA server identity from the CDK).

## Deployment

The connector ships as a single Windows `relay-connector.exe` (PyInstaller, built
and smoke-tested in CI, published to a versioned GitHub release with its
`sha256`) and runs on the Windows host under **Nomad `raw_exec`** - the same
pattern as the BLE forwarder. The exe opens the relay's COM port directly, so no
WSL2/usbipd attach or Docker device passthrough is needed.

## Getting Started (development)

### Prerequisites

Python 3.10 or newer, and [uv](https://docs.astral.sh/uv/) for packaging.

### Install from source

This is a private repository; install it from a clone rather than an index:

```sh
git clone https://github.com/AccelerationConsortium/sainsmart-relay-sila.git
cd sainsmart-relay-sila
uv sync --all-extras
```

All runtime dependencies (`unitelabs-cdk`, `pyserial`, `prometheus-client`) are
public on PyPI - no index credentials are required.

Run the connector in simulator mode:

```sh
uv run python -m unitelabs.sainsmart_relay
```

If you are on a Windows machine, you may wish to set `UNITELABS_CDK_APP` to the
connector's entry point so the CLI commands below don't need `--app` each time:

```sh
set UNITELABS_CDK_APP=unitelabs.sainsmart_relay:create_app
```

#### Configure the Connector

To get information about the configuration values for the connector simply run:

- On **Windows**:

  ```sh
  config show --app unitelabs.sainsmart_relay:create_app
  ```

- On **macOS**/**Linux**:

  ```sh
  config show
  ```

To create a configuration file for our connector we run:

- On **Windows**:

  ```sh
  config create --app unitelabs.sainsmart_relay:create_app
  ```

- On **macOS**/**Linux**:

  ```sh
  config create
  ```

Used as such this command will create a `config.json` in the current working directory. If you prefer to use yaml for your config file or would like to save the file to a different location, simply add the `--path` argument:

- On **Windows**:

  ```sh
  config create --app unitelabs.sainsmart_relay:create_app  --path <path to config>
  ```

- On **macOS**/**Linux**:

  ```sh
  config create --path <path to config>
  ```

The file that is created will be populated with default configuration values that you may now edit.

Note: The `cloud_server_endpoint` values are only necessary if you want to use the connector with the UniteLabs platform.

#### Verify the Installation

After installation, you can verify that everything works by starting the connector using the CLI tool included in the dependencies:

Note: This must be done in the activated environment setup in Step 1.

```sh
connector start --app unitelabs.sainsmart_relay:create_app -vvv
```

If you decided to create your configuration file at a non-default location, you can specify it with the `--config-path` or `-cfg` argument:

```sh
connector start --app unitelabs.sainsmart_relay:create_app -cfg <path to config> -vvv
```

In this way one can have multiple configurations for the same connector.

## Usage

To interact with the running connector, we recommend using the [SiLA Browser](https://gitlab.com/unitelabs/sila2/sila-browser).

### Encryption

To secure communication between the connector and its clients, you can enable TLS encryption. Start by installing the optional `cryptography` package for generating TLS certificates:

```sh
python -m pip install cryptography
```

To generate a pair of public and private keys, use the following command:

```sh
certificate generate
```

Without any arguments this command uses the default config location to get the connector's UUID and host name, required to generate TLS certificates. It will prompt you as to whether or not you want to update your config file to enable TLS encryption on your connector. This prompt can be suppressed with the use of the `--non-interactive` or `-y` flag, which will update the config file with paths to the locally created files without prompting, or with `--embed` or `-e` flag to write the file contents into the config file directly.

You can adjust your config file's host to reflect the machine's hostname, or set it to `localhost` if the connector should only be accessible locally.

If your config file was created at a non-default path, you can provide it with the `--config-path` or `-cfg` option:

```sh
certificate generate -cfg <path to config>
```

By default the generate command creates the `cert.pem` and `key.pem` files in your current working directory. You can customize the output directory with the `--target` argument.

If you choose not to update your config file with the paths to your certificates using `--non-interactive` or `-y` or to have the file contents saved directly in your config file with `--embed` or `-e` flag, you will have to modify the config file yourself to set the following values under `sila_server`:
 
- `certificate_chain` - the path to the `cert.pem` file
- `private_key` - the path to the `key.pem` file
- `tls` - a boolean that toggles on/off TLS encryption for the SiLA server

With your updated config file you can once again run:

```sh
connector start --app unitelabs.sainsmart_relay:create_app -vvv
```

> **Important:** Never share the `key.pem` file with anyone. Only the `cert.pem` is required for clients to connect to encrypted servers.

## Contribute

We welcome contributions to improve our connectors. Follow the steps below to set up your development environment.

### Development Environment

We use [uv][] for Python packaging.

#### Set Up the Environment

Install and configure `uv`:

```sh
pipx install uv
```

Note: requires `uv>=0.6.8`.

#### Install the Package

Clone the repository:

```sh
git clone https://github.com/AccelerationConsortium/sainsmart-relay-sila.git
```

Set up the development environment and start the connector:

```sh
uv sync --all-extras
uv run connector start -vvv
```

Note: By default, uv will sync all dependencies with every call to `uv run CMD`. To prevent this use `uv run --frozen CMD` or set the environment variable `UV_FROZEN=true`.

#### Install pre-commit Hooks

Set up `pre-commit` hooks to ensure code quality:

```sh
uv run pre-commit install
```

#### Running Tests

To run the test suite:

```sh
uv run pytest
```

To run tests with a specific version of python, e.g. Python 3.12:

```sh
uv run --python 3.12 --all-extras pytest
```

#### Dev-Mode

To improve the development experience, we recommend running the connector in developer mode. This will automatically reload the connector whenever changes to the source code are saved.

```sh
uv run connector dev --app unitelabs.sainsmart_relay:create_app
```

## Contact

If you found a bug, please use the [issue tracker][issue-tracker].

[issue-tracker]: https://github.com/AccelerationConsortium/sainsmart-relay-sila/issues
[uv]: https://docs.astral.sh/uv/
