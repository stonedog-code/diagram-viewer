def test_deliberately_failing_probe():
    """Planted to prove branch protection blocks a red PR. Never merged."""
    assert 1 == 2, "planted failure — this branch must not be mergeable"
