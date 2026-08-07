import unittest

from src.analysis.hk_single_stock_indicator import hk_basic_finance_data


class TestHkBasicFinanceData(unittest.TestCase):
    def test_formats_ttm_dividend_yield_from_snapshot(self):
        result = hk_basic_finance_data({"dividend_ratio_ttm": 4.567})

        self.assertEqual(result["dividend_ratio_ttm"], "4.57%")

    def test_marks_missing_ttm_dividend_yield_as_unavailable(self):
        result = hk_basic_finance_data({})

        self.assertEqual(result["dividend_ratio_ttm"], "无数据")


if __name__ == "__main__":
    unittest.main()
