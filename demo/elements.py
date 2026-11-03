"""Kestrel-7 elements chosen so Bengaluru's next pass opens about 40 minutes after epoch."""

from __future__ import annotations

import math
from datetime import UTC, datetime

from core.types import GroundStation, OrbitalElements


def epoch() -> datetime:
    return datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


KESTREL_ELEMENTS = OrbitalElements(
    altitude_km=550.0,
    inclination_rad=math.radians(97.6),
    raan_rad=math.radians(21.0),
    true_anomaly_rad=math.radians(0.0),
    epoch=epoch(),
)

KESTREL_STATION = GroundStation(
    id="blr",
    name="Bengaluru",
    lat_deg=13.03,
    lon_deg=77.51,
    alt_km=0.92,
    min_elevation_deg=5.0,
)
