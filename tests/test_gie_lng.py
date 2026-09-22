"""OUTLOOK GIE LNG 조회는 중앙 DB의 한 발행본과 허용된 필터만 읽는다."""
from unittest.mock import patch

import pandas as pd
import pytest

from extract.gie_lng import load_gie_lng_assets


def test_uses_latest_release_and_bound_filters():
    expected = pd.DataFrame({"asset_name": ["Zeebrugge"]})
    with patch("extract.gie_lng.db.query", return_value=expected) as query:
        result = load_gie_lng_assets(
            countries=[" France ", "Belgium"], statuses=["OPERATING", "construction"],
            startup_from=2020, startup_to=2030)
    assert result is expected
    sql, params = query.call_args.args
    assert sql.lstrip().startswith("WITH chosen")
    assert "ORDER BY release_date DESC, collected_at DESC, id DESC" in sql
    assert params == {"source": "gie_lng_database", "release_id": None,
                      "countries": ["Belgium", "France"],
                      "statuses": ["construction", "operating"],
                      "startup_from": 2020, "startup_to": 2030}


def test_specific_release_is_bound_not_interpolated():
    with patch("extract.gie_lng.db.query", return_value=pd.DataFrame()) as query:
        load_gie_lng_assets(release_id=17)
    sql, params = query.call_args.args
    assert "17" not in sql
    assert params["release_id"] == 17


@pytest.mark.parametrize("arguments", [
    {"countries": []}, {"countries": [" "]}, {"statuses": []},
    {"statuses": ["commissioning"]}, {"startup_from": 1899},
    {"startup_to": "2030"}, {"startup_from": 2030, "startup_to": 2020},
    {"release_id": 0}, {"release_id": True},
])
def test_invalid_filters_never_open_database(arguments):
    with patch("extract.gie_lng.db.query") as query:
        with pytest.raises(ValueError):
            load_gie_lng_assets(**arguments)
        query.assert_not_called()
