"""Connectors: outside data, pinned well enough to prove later.

    weather     Open-Meteo (ERA5) and NASA POWER monthly weather
    soilgrids   ISRIC SoilGrids 2.0 soil prior
    stac        Sentinel-1/2 scene availability from a STAC catalogue
    sensors     field water-level loggers, and radar validation against them
    registry    registry CSV exports reconciled against our ledger

Every network call goes through a `Transport`, so the same code runs live,
records, or replays pinned responses with no network at all.
"""

from .base import (
    ConnectorUnavailable, RecordingTransport, ReplayTransport, Snapshot,
    UrllibTransport, default_transport, pin, request_key,
)

__all__ = [
    "ConnectorUnavailable", "RecordingTransport", "ReplayTransport", "Snapshot",
    "UrllibTransport", "default_transport", "pin", "request_key",
]
