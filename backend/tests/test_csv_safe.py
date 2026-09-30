"""CSV 公式注入（审计 BUG-20 回归）"""
import csv
import io

from backend.utils.csv_safe import neutralize_csv_value, safe_csv_row


def test_dangerous_prefixes_neutralized():
    for bad in ("=HYPERLINK(\"http://evil\",\"x\")", "+1+1", "-2+3", "@SUM(A1)", "\tcmd", "\r=1"):
        assert neutralize_csv_value(bad).startswith("'")


def test_safe_values_untouched():
    for ok in ("普通标题", "https://a.example", "-1.5", "+3", "1e5", "", None, 42):
        assert neutralize_csv_value(ok) == ok


def test_export_row_roundtrip():
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["title", "url"])
    w.writeheader()
    w.writerow(safe_csv_row({"title": "=cmd|' /C calc'!A0", "url": "https://x"}))
    assert "'=cmd" in buf.getvalue()
