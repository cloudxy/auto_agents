"""H2：metrics.yaml 六元组齐全。"""
from pathlib import Path

import yaml

REQUIRED = {"id", "name", "formula", "window", "unit", "source"}


def test_metrics_yaml_six_tuple():
    path = Path(__file__).resolve().parents[2] / "config" / "metrics.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    rows = data["metrics"]
    assert len(rows) >= 4
    for row in rows:
        assert REQUIRED <= set(row)
