"""OUTLOOK 금리는 중앙 DB의 허용 계열만 읽는다."""
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from extract.fed_rates import load_excel_policy_rate, load_fed_rates


def test_uses_shared_readonly_database_and_bound_filters():
    expected = pd.DataFrame({"value": [0.0, 5.33]})
    with patch("extract.fed_rates.db.query", return_value=expected) as query:
        result = load_fed_rates(metrics=["us_fed_target_lower", "us_effr_daily"],
                                start=date(2024, 1, 1), end=date(2024, 12, 31))
    assert result is expected
    sql, params = query.call_args.args
    assert sql.lstrip().startswith("SELECT")
    assert params["metrics"] == ["us_effr_daily", "us_fed_target_lower"]
    assert params["start"] == date(2024, 1, 1)


def test_excel_adapter_requests_only_monthly_effr():
    expected = pd.DataFrame({"value": [0.07]})
    with patch("extract.fed_rates.db.query", return_value=expected) as query:
        result = load_excel_policy_rate(start=date(2014, 1, 1), end=date(2014, 12, 31))
    assert result is expected
    assert query.call_args.args[1]["metrics"] == ["us_effr_monthly_avg"]


@pytest.mark.parametrize("arguments", [
    {"metrics": ["other_rate"]}, {"metrics": []},
    {"start": date(2025, 1, 1), "end": date(2024, 1, 1)},
    {"start": "2024-01-01"},
])
def test_invalid_filters_never_open_database(arguments):
    with patch("extract.fed_rates.db.query") as query:
        with pytest.raises(ValueError):
            load_fed_rates(**arguments)
        query.assert_not_called()
