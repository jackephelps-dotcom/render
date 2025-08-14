# ict_strategy.py
import pandas as pd
import numpy as np

class ICTStrategy:
    def __init__(self):
        self.min_score_for_medium = 2
        self.min_score_for_strong = 3

    def get_bias(self, df_h4, df_h1):
        """Determine overall bias from 4H and 1H charts."""
        h4_bias = "BULL" if df_h4['close'].iloc[-1] > df_h4['close'].iloc[-5] else "BEAR"
        h1_bias = "BULL" if df_h1['close'].iloc[-1] > df_h1['close'].iloc[-5] else "BEAR"
        if h4_bias == h1_bias:
            return h4_bias
        else:
            return "NEUTRAL"

    def detect_bos(self, df, bias):
        """Break of Structure detection."""
        if bias == "BULL":
            return df['high'].iloc[-1] > df['high'].iloc[-5]
        elif bias == "BEAR":
            return df['low'].iloc[-1] < df['low'].iloc[-5]
        return False

    def detect_fvg(self, df, bias):
        """Fair Value Gap detection."""
        if len(df) < 3:
            return False
        c1, c2, c3 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
        if bias == "BULL":
            return c1['high'] < c3['low']
        elif bias == "BEAR":
            return c1['low'] > c3['high']
        return False

    def detect_liquidity_sweep(self, df, bias):
        """Liquidity sweep detection."""
        recent_high = df['high'].iloc[-5]
        recent_low = df['low'].iloc[-5]
        if bias == "BULL" and df['low'].iloc[-1] < recent_low:
            return True
        elif bias == "BEAR" and df['high'].iloc[-1] > recent_high:
            return True
        return False

    def detect_smt_divergence(self, df_pair1, df_pair2, bias):
        """Simple SMT divergence check between correlated pairs."""
        if bias == "BULL":
            return (df_pair1['low'].iloc[-1] < df_pair1['low'].iloc[-5]) and \
                   (df_pair2['low'].iloc[-1] >= df_pair2['low'].iloc[-5])
        elif bias == "BEAR":
            return (df_pair1['high'].iloc[-1] > df_pair1['high'].iloc[-5]) and \
                   (df_pair2['high'].iloc[-1] <= df_pair2['high'].iloc[-5])
        return False

    def find_sl_tp(self, df, bias):
        """Find SL and TP based on liquidity pools."""
        if bias == "BULL":
            sl = df['low'].iloc[-1] - 0.0001
            tp = df['high'].max()
        elif bias == "BEAR":
            sl = df['high'].iloc[-1] + 0.0001
            tp = df['low'].min()
        else:
            sl = None
            tp = None
        return sl, tp

    def analyze(self, pair, df_h4, df_h1, df_m15, df_m5, correlated_df=None):
        """Main analysis combining all confluences."""
        bias = self.get_bias(df_h4, df_h1)
        if bias == "NEUTRAL":
            return None  # Skip if higher timeframes disagree

        confluences = []
        score = 0

        if self.detect_bos(df_m15, bias):
            confluences.append("BOS on 15M")
            score += 1
        if self.detect_fvg(df_m15, bias):
            confluences.append("FVG on 15M")
            score += 1
        if self.detect_liquidity_sweep(df_m15, bias):
            confluences.append("Liquidity Sweep on 15M")
            score += 1
        if correlated_df is not None and self.detect_smt_divergence(df_m5, correlated_df, bias):
            confluences.append("SMT divergence on 5M")
            score += 1

        if score >= self.min_score_for_medium:
            sl, tp = self.find_sl_tp(df_m5, bias)
            return {
                "pair": pair,
                "bias": bias,
                "score": score,
                "strength": "🔥 Strong" if score >= self.min_score_for_strong else "⚡ Medium",
                "confluences": confluences,
                "sl": sl,
                "tp": tp
            }
        return None
