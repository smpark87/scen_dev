"""OUTLOOK JODI-Gas 조회는 중앙 DB의 허용 범위만 읽는다."""
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from extract.jodi_gas import load_jodi_gas


def test_uses_shared_readonly_database_and_bound_filters():
    expected = pd.DataFrame({"value": [0.0, 42.5]})
    with patch("extract.jodi_gas.db.query", return_value=expected) as query:
        result = load_jodi_gas(
            countries=["kr", "JP"], flows=["implng", "TOTDEMO"],
            units=["million_m3"], assessments=[1, 2],
            start=date(2024, 1, 1), end=date(2024, 12, 31))
    assert result is expected
    sql, params = query.call_args.args
    assert sql.lstrip().startswith("SELECT")
    assert params["countries"] == ["JP", "KR"]
    assert params["flows"] == ["IMPLNG", "TOTDEMO"]
    assert params["units"] == ["million_m3"]
    assert params["assessments"] == [1, 2]


@pytest.mark.parametrize("arguments", [
    {"countries": ["KOR"]}, {"countries": []}, {"flows": ["BILATERAL"]},
    {"units": ["bcf"]}, {"assessments": [0]}, {"assessments": []},
    {"start": date(2025, 1, 1), "end": date(2024, 1, 1)}, {"start": "2009-01-01"},
])
def test_invalid_filters_never_open_database(arguments):
    with patch("extract.jodi_gas.db.query") as query:
        with pytest.raises(ValueError):
            load_jodi_gas(**arguments)
        query.assert_not_called()
