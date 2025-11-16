import pytest
from sla_engine import safe_get, escalate_sla_breach
from database import get_conn


def test_safe_get():
    row = {"a": 10}
    assert safe_get(row, "a") == 10
    assert safe_get(row, "missing", default="x") == "x"


