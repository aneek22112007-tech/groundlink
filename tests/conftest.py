from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

from agents.common.db import create_all

T0 = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
AOS = T0 + timedelta(minutes=40)
LOS = AOS + timedelta(minutes=12)


@pytest.fixture()
def factory() -> sessionmaker[Session]:
    return create_all("sqlite://")
