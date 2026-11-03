from __future__ import annotations

from agents.common.audit import append_event, load_chain, verify_chain
from tests.conftest import T0


def test_chain_verifies_and_detects_tampering(factory) -> None:  # type: ignore[no-untyped-def]
    session = factory()
    append_event(session, "m1", "mission.opened", {"sat": "kestrel-7"}, ts=T0)
    second = append_event(session, "m1", "diagnosis.posted", {"severity": "crit"}, ts=T0)
    session.commit()
    rows = load_chain(session)
    ok, detail = verify_chain(rows)
    assert ok is True
    assert detail == "chain intact"
    assert rows[1].prev_hash == rows[0].row_hash
    assert second.row_hash != rows[0].row_hash
    rows[1].payload_json = '{"severity":"nominal"}'
    broken, reason = verify_chain(rows)
    assert broken is False
    assert "break" in reason
    session.close()
