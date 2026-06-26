"""PyInstaller entry point for the SainSmart relay SiLA connector executable.

Bundled into ``relay-connector.exe`` (Windows) so the host needs no Python or
deps - the Nomad ``raw_exec`` task runs this exe directly. It runs exactly the
same connector as ``python -m unitelabs.sainsmart_relay``: ``unitelabs.cdk.run``
loads config from ``./config.json`` (or env vars) if present, otherwise falls
back to the ``SainsmartRelaySilaConfig`` defaults (``use_simulator=true``), which
is what the CI simulator-boot smoke test relies on.
"""

import asyncio

from unitelabs.cdk import run

from unitelabs.sainsmart_relay import create_app


def main() -> None:
    """Run the relay connector until terminated."""
    asyncio.run(run(create_app))


if __name__ == "__main__":
    main()
