from src.behavior_labels import assign_label


def test_default_label():
    p, _, _ = assign_label({'or_1m': '{}', 'or_5m': '{}', 'close_location': 0.5})
    assert p == 'Mixed / Watch Only'
