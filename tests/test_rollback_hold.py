from agents.orchestration import rollback_hold


def test_no_rollback_means_no_hold():
    assert not rollback_hold([{"role": "action_agent", "text": "TRANSMITTED seq 1"}])


def test_rollback_holds_next_step():
    lines = [{"role": "action_agent", "text": "ROLLBACK: attitude error grew."}]
    assert rollback_hold(lines)


def test_human_resume_clears_hold():
    lines = [
        {"role": "action_agent", "text": "ROLLBACK: attitude error grew."},
        {"role": "mission_director", "text": "Resume — continue sequence"},
    ]
    assert not rollback_hold(lines)


def test_agent_cannot_clear_its_own_hold():
    lines = [
        {"role": "action_agent", "text": "ROLLBACK: attitude error grew."},
        {"role": "action_agent", "text": "Resume"},
    ]
    assert rollback_hold(lines)


def test_already_said_detects_a_posted_confirmation():
    from agents.orchestration import _already_said

    assert _already_said(["CONFIRMED recovered. Attitude error 0.75 deg"], "CONFIRMED recovered")
    assert not _already_said(["TRANSMITTED seq 4"], "CONFIRMED recovered")
