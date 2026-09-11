import unittest

from src.analysis.hk_single_stock_indicator import hk_basic_finance_data


class TestHkBasicFinanceData(unittest.TestCase):
    def test_formats_dividend_yields_from_snapshot(self):
        result = hk_basic_finance_data(
            {
                "dividend_ratio_ttm": 4.567,
                "dividend_lfy_ratio": 3.214,
            }
        )

        self.assertEqual(result["dividend_ratio_ttm"], "4.57%")
        self.assertEqual(result["dividend_lfy_ratio"], "3.21%")

    def test_marks_missing_dividend_yields_as_unavailable(self):
        result = hk_basic_finance_data({})

        self.assertEqual(result["dividend_ratio_ttm"], "无数据")
        self.assertEqual(result["dividend_lfy_ratio"], "无数据")


if __name__ == "__main__":
    unittest.main()
