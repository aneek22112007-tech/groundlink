from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class OrbitalElements:
    altitude_km: float
    inclination_rad: float
    raan_rad: float
    true_anomaly_rad: float
    epoch: datetime


@dataclass(frozen=True)
class GroundStation:
    id: str
    name: str
    lat_deg: float
    lon_deg: float
    alt_km: float
    min_elevation_deg: float


@dataclass(frozen=True)
class PassWindow:
    station_id: str
    station_name: str
    aos: datetime
    los: datetime
    max_elevation_deg: float

    def contains(self, moment: datetime) -> bool:
        return self.aos <= moment <= self.los

    @property
    def duration_s(self) -> float:
        return (self.los - self.aos).total_seconds()


@dataclass(frozen=True)
class Sample:
    ts: datetime
    bus_voltage: float
    battery_soc: float
    attitude_err_deg: float
    wheel_rpm: float
    temp_c: float
    comms_status: str
    fuel_kg: float
    in_eclipse: bool
    load_w: float


@dataclass(frozen=True)
class Finding:
    subsystem: str
    severity: str
    detail: str


@dataclass(frozen=True)
class Diagnosis:
    findings: tuple[Finding, ...]
    started_at: datetime
    still_works: tuple[str, ...]
    severity: str


@dataclass(frozen=True)
class Reversibility:
    reversible: bool
    tag: str
    reason: str


@dataclass(frozen=True)
class SimResult:
    min_voltage: float
    end_voltage: float
    end_soc: float
    end_attitude_deg: float
    end_fuel_kg: float
    service_loss_h: float
    power_cost_wh: float
    survived: bool


@dataclass(frozen=True)
class OptionSpec:
    key: str
    name: str
    version: int
    success_prob: float
    power_cost_wh: float
    fuel_cost_kg: float
    fuel_reserve_pct: float
    service_loss_h: float
    reversible: bool
    reversibility_reason: str
    rationale: str
    kind: str
    pass_number: int
