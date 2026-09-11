import unittest
from datetime import datetime

import pandas as pd

from src.analysis.hk_market_liquidity import (
    HK_MARKET_LIQUIDITY_INDICES,
    build_hk_market_liquidity_profile,
    calculate_weighted_heat_ratio,
    classify_heat_level,
    format_hk_market_liquidity_prompt,
    infer_cross_index_state,
)


class TestHkMarketLiquidity(unittest.TestCase):
    def test_calculates_raw_and_weighted_ratios(self):
        now = datetime(2026, 8, 19, 17, 0)
        dates = pd.bdate_range(end=now.date(), periods=181)
        history = pd.DataFrame(
            {
                "time_key": dates,
                "turnover": [100.0] * 180 + [150.0],
            }
        )
        snapshots = {
            code: {
                "code": code,
                "data_date": "2026-08-19",
                "turnover": 150.0,
            }
            for code in HK_MARKET_LIQUIDITY_INDICES
        }
        profile = build_hk_market_liquidity_profile(
            snapshots=snapshots,
            klines_by_code={code: history for code in HK_MARKET_LIQUIDITY_INDICES},
            now_dt=now,
        )

        hsi = profile["indices"]["HK.800000"]
        self.assertEqual(hsi["ratios"], {"5": 1.5, "30": 1.5, "90": 1.5, "180": 1.5})
        self.assertEqual(hsi["weighted_heat_ratio"], 1.5)
        self.assertEqual(hsi["heat_level"], "明显放量")
        self.assertEqual(profile["cross_index_state"], "全面共振升温")

    def test_weighted_ratio_uses_documented_weights(self):
        result = calculate_weighted_heat_ratio(
            {5: 2.0, 30: 1.5, 90: 1.0, 180: 0.5}
        )

        self.assertEqual(result, 1.5)

    def test_weighted_ratio_renormalizes_missing_long_window(self):
        result = calculate_weighted_heat_ratio(
            {5: 2.0, 30: 1.0, 90: 0.5, 180: None}
        )

        self.assertAlmostEqual(result, 1.3333, places=4)

    def test_weighted_ratio_requires_5_and_30_day_windows(self):
        self.assertIsNone(
            calculate_weighted_heat_ratio({5: None, 30: 1.0, 90: 1.0, 180: 1.0})
        )
        self.assertIsNone(
            calculate_weighted_heat_ratio({5: 1.0, 30: None, 90: 1.0, 180: 1.0})
        )

    def test_classification_boundaries(self):
        cases = [
            (0.49, "流动性低迷"),
            (0.50, "明显缩量"),
            (0.80, "常态成交"),
            (1.30, "明显放量"),
            (1.80, "极度活跃"),
        ]
        for ratio, expected in cases:
            with self.subTest(ratio=ratio):
                self.assertEqual(classify_heat_level(ratio), expected)

    def test_three_normal_indices_are_not_marked_as_divergent(self):
        indices = {
            code: {"weighted_heat_ratio": ratio}
            for code, ratio in zip(HK_MARKET_LIQUIDITY_INDICES, (0.93, 0.90, 0.99))
        }

        self.assertEqual(infer_cross_index_state(indices), "整体常态")

    def test_before_1500_uses_previous_completed_day(self):
        now = datetime(2026, 8, 19, 14, 0)
        dates = pd.bdate_range(end=now.date(), periods=182)
        history = pd.DataFrame(
            {
                "time_key": dates,
                "turnover": [100.0] * 181 + [20.0],
            }
        )
        snapshots = {
            code: {
                "code": code,
                "data_date": "2026-08-19",
                "turnover": 20.0,
            }
            for code in HK_MARKET_LIQUIDITY_INDICES
        }

        profile = build_hk_market_liquidity_profile(
            snapshots=snapshots,
            klines_by_code={code: history for code in HK_MARKET_LIQUIDITY_INDICES},
            now_dt=now,
        )

        hsi = profile["indices"]["HK.800000"]
        self.assertEqual(hsi["current_turnover"], 20.0)
        self.assertEqual(hsi["comparable_turnover"], 100.0)
        self.assertEqual(hsi["comparison_mode"], "PREVIOUS_COMPLETED_DAY")
        self.assertEqual(hsi["weighted_heat_ratio"], 1.0)

    def test_after_1500_uses_same_day_cumulative_without_projection(self):
        now = datetime(2026, 8, 19, 15, 30)
        dates = pd.bdate_range(end=now.date(), periods=181)
        history = pd.DataFrame(
            {
                "time_key": dates,
                "turnover": [100.0] * 180 + [75.0],
            }
        )
        snapshots = {
            code: {
                "code": code,
                "data_date": "2026-08-19",
                "turnover": 75.0,
            }
            for code in HK_MARKET_LIQUIDITY_INDICES
        }

        profile = build_hk_market_liquidity_profile(
            snapshots=snapshots,
            klines_by_code={code: history for code in HK_MARKET_LIQUIDITY_INDICES},
            now_dt=now,
        )

        hsi = profile["indices"]["HK.800000"]
        self.assertEqual(hsi["comparable_turnover"], 75.0)
        self.assertEqual(hsi["comparison_mode"], "TODAY_CUMULATIVE_AFTER_1500")
        self.assertEqual(hsi["weighted_heat_ratio"], 0.75)

    def test_prompt_keeps_raw_ratios_and_explains_weighting(self):
        profile = {
            "weight_formula": "5日×40% + 30日×30% + 90日×20% + 180日×10%",
            "thresholds": "test thresholds",
            "cross_index_state": "明显分化",
            "summary": "test summary",
            "indices": {
                code: {
                    "current_turnover": 100_000_000,
                    "ratios": {"5": 1.1, "30": 1.2, "90": 1.3, "180": 1.4},
                    "weighted_heat_ratio": 1.2,
                    "heat_level": "常态成交",
                    "comparison_mode": "CLOSED",
                    "confidence": "NORMAL",
                }
                for code in HK_MARKET_LIQUIDITY_INDICES
            },
        }

        text = format_hk_market_liquidity_prompt(profile)

        self.assertIn("5日×40% + 30日×30% + 90日×20% + 180日×10%", text)
        self.assertIn("5/30/90/180日比值=1.10/1.20/1.30/1.40", text)
        self.assertIn("加权热度=1.20（常态成交）", text)


if __name__ == "__main__":
    unittest.main()
