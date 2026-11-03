"""SQLite tables. Events are append-only and hash-chained."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Satellite(Base):
    __tablename__ = "satellites"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    altitude_km: Mapped[float] = mapped_column(Float)
    inclination_deg: Mapped[float] = mapped_column(Float)
    raan_deg: Mapped[float] = mapped_column(Float)
    true_anomaly_deg: Mapped[float] = mapped_column(Float)
    epoch: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fuel_capacity_kg: Mapped[float] = mapped_column(Float)
    wet_mass_kg: Mapped[float] = mapped_column(Float)


class Telemetry(Base):
    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sat_id: Mapped[str] = mapped_column(String(64), index=True)
    bus_voltage: Mapped[float] = mapped_column(Float)
    battery_soc: Mapped[float] = mapped_column(Float)
    attitude_err_deg: Mapped[float] = mapped_column(Float)
    wheel_rpm: Mapped[float] = mapped_column(Float)
    temp_c: Mapped[float] = mapped_column(Float)
    comms_status: Mapped[str] = mapped_column(String(32))
    fuel_kg: Mapped[float] = mapped_column(Float, default=0.0)
    in_eclipse: Mapped[bool] = mapped_column(Boolean, default=False)
    load_w: Mapped[float] = mapped_column(Float, default=0.0)
    mission_id: Mapped[str] = mapped_column(String(64), default="", index=True)


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sat_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(256))
    opened: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str] = mapped_column(Text)
    subsystem: Mapped[str] = mapped_column(String(64))


class Mission(Base):
    __tablename__ = "missions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sat_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="open")
    opened: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str] = mapped_column(Text, default="")
    pass_number: Mapped[int] = mapped_column(Integer, default=3)
    option_version: Mapped[int] = mapped_column(Integer, default=1)
    persistence: Mapped[bool] = mapped_column(Boolean, default=True)
    variant: Mapped[str] = mapped_column(String(32), default="")
    generation: Mapped[int] = mapped_column(Integer, default=1)


class Option(Base):
    __tablename__ = "options"
    __table_args__ = (UniqueConstraint("mission_id", "key", "version", name="uq_option_version"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    mission_id: Mapped[str] = mapped_column(String(64), index=True)
    key: Mapped[str] = mapped_column(String(8))
    version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(256))
    success_prob: Mapped[float] = mapped_column(Float)
    power_cost: Mapped[float] = mapped_column(Float)
    fuel_cost_kg: Mapped[float] = mapped_column(Float)
    fuel_reserve_pct: Mapped[float] = mapped_column(Float)
    service_loss_h: Mapped[float] = mapped_column(Float)
    reversible: Mapped[bool] = mapped_column(Boolean)
    rationale: Mapped[str] = mapped_column(Text)
    reversibility_reason: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(32))
    pass_number: Mapped[int] = mapped_column(Integer, default=0)


class Command(Base):
    __tablename__ = "commands"
    __table_args__ = (UniqueConstraint("mission_id", "seq", name="uq_command_seq"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer)
    mission_id: Mapped[str] = mapped_column(String(64), index=True)
    option_id: Mapped[str] = mapped_column(String(64))
    step: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="queued")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mission_id: Mapped[str] = mapped_column(String(64), index=True)
    option_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(32))
    approver: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(64))
    message_id: Mapped[str] = mapped_column(String(128))
    statement: Mapped[str] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    option_version: Mapped[int] = mapped_column(Integer)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("prev_hash", name="uq_event_prev_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mission_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload_json: Mapped[str] = mapped_column(Text)
    prev_hash: Mapped[str] = mapped_column(String(64))
    row_hash: Mapped[str] = mapped_column(String(64))


class Operator(Base):
    __tablename__ = "operators"

    username: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(64))


class SimClock(Base):
    __tablename__ = "sim_clock"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sim_now: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    time_scale: Mapped[float] = mapped_column(Float, default=30.0)
    seed: Mapped[int] = mapped_column(Integer, default=7)
