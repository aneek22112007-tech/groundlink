"""Two-body pass geometry on a spherical Earth.

The model is intentionally small: a circular orbit, Keplerian mean motion,
and a spherical station. It is deterministic and fast enough to sample a
day of visibility inside a request. It is not an operational propagator.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from core.constants import EARTH_RADIUS_KM, MU_KM3_S2
from core.types import GroundStation, OrbitalElements, PassWindow

J2000 = datetime(2000, 1, 1, 12, tzinfo=UTC)
_Vec = tuple[float, float, float]


def orbital_period_s(altitude_km: float) -> float:
    radius = EARTH_RADIUS_KM + altitude_km
    return 2.0 * math.pi * math.sqrt(radius**3 / MU_KM3_S2)


def mean_motion_rad_s(altitude_km: float) -> float:
    radius = EARTH_RADIUS_KM + altitude_km
    return math.sqrt(MU_KM3_S2 / radius**3)


def gmst_rad(moment: datetime) -> float:
    if moment.tzinfo is None:
        raise ValueError("moment must be timezone-aware")
    days = (moment.astimezone(UTC) - J2000).total_seconds() / 86400.0
    degrees = (280.46061837 + 360.98564736629 * days) % 360.0
    return math.radians(degrees)


def _norm(v: _Vec) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _dot(a: _Vec, b: _Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def geodetic_to_ecef(lat_deg: float, lon_deg: float, alt_km: float) -> _Vec:
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    radius = EARTH_RADIUS_KM + alt_km
    cos_lat = math.cos(lat)
    return (
        radius * cos_lat * math.cos(lon),
        radius * cos_lat * math.sin(lon),
        radius * math.sin(lat),
    )


def sat_eci(elements: OrbitalElements, moment: datetime) -> _Vec:
    if moment.tzinfo is None or elements.epoch.tzinfo is None:
        raise ValueError("times must be timezone-aware")
    dt = (moment.astimezone(UTC) - elements.epoch.astimezone(UTC)).total_seconds()
    radius = EARTH_RADIUS_KM + elements.altitude_km
    theta = elements.true_anomaly_rad + mean_motion_rad_s(elements.altitude_km) * dt
    x_pf = radius * math.cos(theta)
    y_pf = radius * math.sin(theta)
    c_o, s_o = math.cos(elements.raan_rad), math.sin(elements.raan_rad)
    c_i, s_i = math.cos(elements.inclination_rad), math.sin(elements.inclination_rad)
    return (
        c_o * x_pf - s_o * c_i * y_pf,
        s_o * x_pf + c_o * c_i * y_pf,
        s_i * y_pf,
    )


def eci_to_ecef(eci: _Vec, moment: datetime) -> _Vec:
    g = gmst_rad(moment)
    c_g, s_g = math.cos(g), math.sin(g)
    return (c_g * eci[0] + s_g * eci[1], -s_g * eci[0] + c_g * eci[1], eci[2])


def elevation_deg(sat_ecef: _Vec, station_ecef: _Vec) -> float:
    rho = (
        sat_ecef[0] - station_ecef[0],
        sat_ecef[1] - station_ecef[1],
        sat_ecef[2] - station_ecef[2],
    )
    up_n = _norm(station_ecef)
    rho_n = _norm(rho)
    if up_n == 0.0 or rho_n == 0.0:
        return -90.0
    sin_el = max(-1.0, min(1.0, _dot(station_ecef, rho) / (up_n * rho_n)))
    return math.degrees(math.asin(sin_el))


def elevation_at(elements: OrbitalElements, station: GroundStation, moment: datetime) -> float:
    sat = eci_to_ecef(sat_eci(elements, moment), moment)
    sta = geodetic_to_ecef(station.lat_deg, station.lon_deg, station.alt_km)
    return elevation_deg(sat, sta)


def pass_windows(
    elements: OrbitalElements,
    stations: list[GroundStation],
    start: datetime,
    horizon_s: float,
    step_s: float = 15.0,
) -> list[PassWindow]:
    """Return every visibility interval that opens inside the horizon."""
    if step_s <= 0:
        raise ValueError("step_s must be positive")
    windows: list[PassWindow] = []
    steps = int(horizon_s / step_s)
    for station in stations:
        open_at: datetime | None = None
        peak = -90.0
        prev_el = elevation_at(elements, station, start)
        for i in range(1, steps + 1):
            moment = start + timedelta(seconds=i * step_s)
            el = elevation_at(elements, station, moment)
            if open_at is None and prev_el < station.min_elevation_deg <= el:
                open_at = moment
                peak = el
            elif open_at is not None:
                peak = max(peak, el)
                if el < station.min_elevation_deg:
                    windows.append(
                        PassWindow(
                            station_id=station.id,
                            station_name=station.name,
                            aos=open_at,
                            los=moment,
                            max_elevation_deg=round(peak, 2),
                        )
                    )
                    open_at = None
                    peak = -90.0
            prev_el = el
    windows.sort(key=lambda item: item.aos)
    return windows


def next_pass(
    elements: OrbitalElements,
    stations: list[GroundStation],
    moment: datetime,
    horizon_s: float = 36 * 3600,
) -> PassWindow | None:
    """The pass in progress, or the next one to open."""
    windows = pass_windows(elements, stations, moment - timedelta(minutes=20), horizon_s)
    for window in windows:
        if window.los >= moment:
            return window
    return None


def countdown_s(window: PassWindow | None, moment: datetime) -> float | None:
    if window is None:
        return None
    if window.contains(moment):
        return 0.0
    if moment < window.aos:
        return (window.aos - moment).total_seconds()
    return None
