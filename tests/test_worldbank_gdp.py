"""OUTLOOK GDP는 중앙 DB 읽기 경로만 사용한다."""
import unittest
from unittest.mock import patch
import pandas as pd
from extract.worldbank_gdp import load_gdp


class GDPReaderTests(unittest.TestCase):
    def test_uses_shared_readonly_database_and_bound_filters(self):
        expected = pd.DataFrame({"value": [None, 0, -1.2]})
        with patch("extract.worldbank_gdp.db.query", return_value=expected) as query:
            result = load_gdp(economies=["kor", "EMU"], metrics=["gdp_growth"], start=2024, end=2024)
        self.assertIs(result, expected)
        sql, params = query.call_args.args
        self.assertTrue(sql.lstrip().startswith("SELECT"))
        self.assertEqual(params["codes"], ["KOR", "EMU"])
        self.assertEqual(params["metrics"], ["gdp_growth"])

    def test_invalid_filters_never_open_database(self):
        with patch("extract.worldbank_gdp.db.query") as query:
            for arguments in ({"economies": ["KOR;delete"]}, {"metrics": ["forecast"]}, {"start": 2025, "end": 2024}):
                with self.assertRaises(ValueError):
                    load_gdp(**arguments)
            query.assert_not_called()


if __name__ == "__main__":
    unittest.main()
