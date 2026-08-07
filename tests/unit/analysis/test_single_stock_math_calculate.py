from datetime import datetime, timedelta
import unittest

import numpy as np
import pandas as pd

from src.analysis.single_stock_math_calculate import calculate_ema_derivatives


class TestCalculateEmaDerivatives(unittest.TestCase):
    @staticmethod
    def _expected_derivatives(close: pd.Series) -> tuple[float, float, float]:
        ema5 = close.ewm(span=5, adjust=False).mean()
        ema20 = close.ewm(span=20, adjust=False).mean()
        v5 = ema5.pct_change() * 100.0
        v20 = ema20.pct_change() * 100.0
        a5 = v5.diff()
        return round(v5.iloc[-1], 2), round(v20.iloc[-1], 2), round(a5.iloc[-1], 2)

    def test_replaces_existing_current_day_close_instead_of_appending(self):
        today = datetime.now().date()
        dates = pd.date_range(end=today, periods=30, freq="D")
        close = pd.Series(np.linspace(90.0, 120.0, 30))
        df = pd.DataFrame({"time_key": dates, "close": close})
        current_price = 118.0

        result = calculate_ema_derivatives(df, current_price)

        expected_close = close.copy()
        expected_close.iloc[-1] = current_price
        expected_v5, expected_v20, expected_a5 = self._expected_derivatives(expected_close)
        self.assertEqual(result["v5"], expected_v5)
        self.assertEqual(result["v20"], expected_v20)
        self.assertEqual(result["a5"], expected_a5)

    def test_appends_current_price_when_latest_row_is_historical(self):
        yesterday = datetime.now().date() - timedelta(days=1)
        dates = pd.date_range(end=yesterday, periods=30, freq="D")
        close = pd.Series(np.linspace(90.0, 120.0, 30))
        df = pd.DataFrame({"time_key": dates, "close": close})
        current_price = 118.0

        result = calculate_ema_derivatives(df, current_price)

        expected_close = pd.concat(
            [close, pd.Series([current_price])],
            ignore_index=True,
        )
        expected_v5, expected_v20, expected_a5 = self._expected_derivatives(expected_close)
        self.assertEqual(result["v5"], expected_v5)
        self.assertEqual(result["v20"], expected_v20)
        self.assertEqual(result["a5"], expected_a5)

    def test_daily_drop_is_reflected_when_ema_trend_remains_positive(self):
        yesterday = datetime.now().date() - timedelta(days=1)
        dates = pd.date_range(end=yesterday, periods=30, freq="D")
        df = pd.DataFrame(
            {
                "time_key": dates,
                "close": np.linspace(90.0, 120.0, 30),
            }
        )

        result = calculate_ema_derivatives(
            df,
            current_price=118.0,
            current_change_rate=-1.67,
        )

        self.assertGreater(result["v5"], 0)
        self.assertGreater(result["v20"], 0)
        self.assertIn("上升趋势回调", result["tag_combined"])
        self.assertIn("当日价格下跌", result["tag_combined"])

    def test_daily_drop_marks_short_term_recovery_as_blocked(self):
        yesterday = datetime.now().date() - timedelta(days=1)
        close = np.concatenate(
            [
                np.linspace(120.0, 90.0, 25),
                np.array([91.0, 93.0, 95.0, 97.0, 99.0]),
            ]
        )
        df = pd.DataFrame(
            {
                "time_key": pd.date_range(end=yesterday, periods=len(close), freq="D"),
                "close": close,
            }
        )

        result = calculate_ema_derivatives(
            df,
            current_price=98.0,
            current_change_rate=-1.01,
        )

        self.assertGreater(result["v5"], 0)
        self.assertLess(result["v20"], 0)
        self.assertIn("短期修复受阻", result["tag_combined"])

    def test_daily_rise_marks_short_term_weakness_as_rebound(self):
        yesterday = datetime.now().date() - timedelta(days=1)
        close = np.concatenate(
            [
                np.linspace(90.0, 120.0, 25),
                np.array([119.0, 117.0, 115.0, 113.0, 111.0]),
            ]
        )
        df = pd.DataFrame(
            {
                "time_key": pd.date_range(end=yesterday, periods=len(close), freq="D"),
                "close": close,
            }
        )

        result = calculate_ema_derivatives(
            df,
            current_price=112.0,
            current_change_rate=0.9,
        )

        self.assertLess(result["v5"], 0)
        self.assertGreater(result["v20"], 0)
        self.assertIn("短期转弱中的反弹", result["tag_combined"])


if __name__ == "__main__":
    unittest.main()
