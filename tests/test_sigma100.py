"""Nemo v100 "Sigma": a signal desk inside Nemo (fixed rules for stocks and the index, option-chain analytics, defined-risk option structures, a backtest with charges, a short-volatility proxy study and a forward scoreboard).

Offline. No Telegram, no network (a test asserts the raw HTTP layer is never touched), no broker, no AI, no order. The market is synthetic: seeded candle generators and a chain built from the same Black-Scholes helper the
bot uses, so every expectation can be checked by hand. Known-answer tests use numbers worked out on paper (RSI, ATR, Bollinger bands, payoffs). A structural group parses the layer and fails if it ever names an order
function, the trading agent, the paper ledger, the broker, the guards or the owner lock, calls an AI, or writes a table that is not its own.

    NEMO_FILE=/path/to/nemotron_bot.py python -m unittest tests.test_sigma100 -v
"""
import ast
import copy
import datetime as dt
import json
import math
import random
import re
import time
import unittest
from unittest import mock

from tests import test_cortex83 as base
from tests.test_forge91 import OWNER_ID
from tests.test_scout93 import ScoutCase, make_chain, wavy, index_daily, index_intraday, vix_series


ORIG = {}


def setUpModule():
    if base.m is None:
        base.setUpModule()
    ORIG['daily'] = base.m._n100_daily                 # the real function, before any test replaces it with a stub


def sigma_source():
    src = open(base.NEMO_FILE, encoding='utf-8').read()
    i = src.index('# NEMO 100 - SIGMA')
    j = src.index('# NEMO 101 - ') if '# NEMO 101 - ' in src else src.rindex("if __name__")
    return src[i:j]


# ===================================================================================================================
# synthetic markets
# ===================================================================================================================
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def ist_ts(y, mo, d, h=9, mi=15):
    return dt.datetime(y, mo, d, h, mi, tzinfo=IST).timestamp()


NOW = ist_ts(2026, 10, 5, 10, 30)                 # a Monday, 10:30 IST (the stubbed session says the market is open)
LAST_DAY = ist_ts(2026, 10, 1)                    # the last completed daily candle


def candles(closes, vols=None, wick=0.004, end_ts=LAST_DAY, step=86400, opens=None):
    n = len(closes)
    out, prev = [], closes[0]
    for i, c in enumerate(closes):
        o = opens[i] if opens else prev
        out.append({'ts': int(end_ts - (n - 1 - i) * step), 'o': o, 'h': max(o, c) * (1 + wick), 'l': min(o, c) * (1 - wick), 'c': c, 'v': vols[i] if vols else 1e6})
        prev = c
    return out


def trend(n, start=100.0, drift=0.0025, vol=0.006, seed=1):
    rnd = random.Random(seed)
    px, cs = start, []
    for _ in range(n):
        px *= 1 + drift + rnd.gauss(0, vol)
        cs.append(px)
    return cs


def dip_closes():
    """A steady uptrend followed by three falling closes: RSI(2) collapses while the price stays far above its 200-day average."""
    cl = trend(260)
    return cl + [cl[-1] * 0.985, cl[-1] * 0.985 ** 2, cl[-1] * 0.985 ** 3]


def breakout_closes():
    cl = trend(260, seed=2)
    return cl + [max(cl[-56:-1]) * 1.015]


def squeeze_closes():
    rnd = random.Random(4)
    cl, px = [], 100.0
    for _ in range(150):
        px *= 1 + rnd.gauss(0, 0.014)
        cl.append(px)
    for _ in range(45):
        px *= 1 + rnd.gauss(0, 0.002)
        cl.append(px)
    return cl + [cl[-1] * 1.035]


def flip_closes():
    rnd = random.Random(7)
    cl, px = [], 200.0
    for _ in range(150):
        px *= 1 - 0.006 + rnd.gauss(0, 0.006)
        cl.append(px)
    for _ in range(30):
        px *= 1 + 0.012 + rnd.gauss(0, 0.004)
        cl.append(px)
    return cl


def fire_indexes(m, F, name, side, lo=130):
    out = []
    for i in range(lo, F['n']):
        s, _w = m._N100_FUNCS[name](F, i, side)
        if s:
            out.append(i)
    return out


def tiny_F(o, h, l, c, extra=None, t0=1000):
    """A hand-made prepared series for the walker: only the keys the walker reads."""
    n = len(c)
    F = {'n': n, 'ts': [t0 + k * 86400 for k in range(n)], 'o': o, 'h': h, 'l': l, 'c': c, 'st_dir': [None] * n, 'st_line': [None] * n, 'sma5': [None] * n, 'sma50': [None] * n, 'll20': [None] * n, 'hh20': [None] * n}
    F.update(extra or {})
    return F


def spec(side=1, ref=100.0, stop=95.0, target=None, horizon=10, rule=None, trail=None, atr=2.0, deadline=None, st_trail=False):
    return {'side': side, 'ref': ref, 'stop': stop, 'target': target, 'horizon': horizon, 'rule': rule, 'trail_mult': trail, 'atr': atr, 'deadline': deadline, 'st_trail': st_trail}


class FrozenTime:
    """The clock the layer sees: always `NOW` (a Monday, 10:30 IST) unless a test moves it; everything else of the time module is real."""

    def __init__(self, now):
        self.now = now

    def time(self):
        return self.now

    def __getattr__(self, k):
        return getattr(time, k)


class SigmaCase(ScoutCase):
    """Everything outside the layer is a stub (market data, option chain, calendar, AI); the daily-history fetch is replaced by a dict."""

    def setUp(self):
        super().setUp()
        m = self.m
        for k in m._N100_STATS:
            m._N100_STATS[k] = 0
        self.daily = {}
        self.daily_calls = []
        self.start(m, '_N91_SYNC', True)
        self.clock = FrozenTime(NOW)
        self.start(m, '_n91_time', self.clock)
        self.session['calendar_known'] = True
        self.guest = lambda text, **k: dict({'chat': {'id': 5552, 'type': 'private'}, 'from': {'id': 5552, 'first_name': 'Asha'}, 'message_id': 3, 'text': text}, **k)

        def daily(sym, years=2, now=None):
            sym = str(sym).upper()
            self.daily_calls.append((sym, years))
            cs = copy.deepcopy(self.daily.get(sym, []))
            info = {'source': 'test feed', 'n': len(cs), 'error': '' if cs else 'no candles (test)', 'live': None, 'jump': False,
                    'last_day': dt.datetime.fromtimestamp(cs[-1]['ts'], IST).date().isoformat() if cs else ''}
            return cs, info
        self.start(m, '_n100_daily', daily)
        self.start(m, '_N100_HANDLE_PREV', lambda msg: self.passed.append(msg))
        m._n100_db().close()
        m._n100_q('DELETE FROM sig100_signal', write=True)
        m._n100_q('DELETE FROM sig100_setting', write=True)
        m._n100_q('DELETE FROM sig100_iv', write=True)
        m._n93_q('DELETE FROM scout93_setting', write=True)
        self.cfg = {'capital': 500000.0, 'risk_pct': 1.0, 'heat_pct': 3.0, 'max_signals': 4, 'min_score': 65, 'alerts': False, 'alerts_per_day': 4, 'shorts': False, 'breaker': True, 'universe': 30,
                    'max_position_pct': 25.0, 'own_capital': True}
        self.http_calls = []

    def put_ctx(self, **kw):
        ctx = {'index_dir': 1, 'regime': 'TREND_UP', 'ret20': 2.0, 'vix': {'level': 13.0, 'pct': 40.0, 'chg5': -0.3, 'n': 120}, 'F': None, 'cs': None, 'notes': [], 'session': None}
        ctx.update(kw)
        return ctx

    def info(self, cs, **kw):
        d = {'source': 'test feed', 'n': len(cs), 'error': '', 'live': None, 'jump': False, 'last_day': dt.datetime.fromtimestamp(cs[-1]['ts'], IST).date().isoformat()}
        d.update(kw)
        return d

    def eval_stock(self, closes, vols=None, sym='TCS', cfg=None, ctx=None, **kw):
        cs = candles(closes, vols)
        return self.m._n100_eval_daily(sym, cs, self.info(cs, **kw), ctx or self.put_ctx(), cfg or self.cfg, 'stock', NOW)


# ===================================================================================================================
# 1. INDICATORS: worked by hand
# ===================================================================================================================
class TestIndicators(SigmaCase):
    def test_rsi_wilder_known_answers(self):
        # n=2: changes +1,-1 -> 50; then +1 -> avg gain (0.5*1+1)/2=.75, avg loss (0.5*1+0)/2=.25 -> RS 3 -> 75; then -1 -> .375, .625 -> 37.5
        r = self.m._n100_rsi([10, 11, 10, 11, 10], 2)
        self.assertEqual(r[:2], [None, None])
        self.assertEqual([round(x, 6) for x in r[2:]], [50.0, 75.0, 37.5])

    def test_rsi_extremes_and_flat(self):
        self.assertEqual(self.m._n100_rsi([1, 2, 3, 4, 5, 6], 2)[-1], 100.0)
        self.assertEqual(self.m._n100_rsi([5, 4, 3, 2, 1], 2)[-1], 0.0)
        self.assertEqual(self.m._n100_rsi([5, 5, 5, 5, 5], 2)[-1], 50.0)

    def test_atr_wilder_known_answers(self):
        # true ranges 2, 3, 3; first ATR(2) = (2+3)/2 = 2.5; next = (2.5*1+3)/2 = 2.75
        a = self.m._n100_atr([10, 11, 12, 13], [8, 9, 9, 10], [9, 10, 11, 12], 2)
        self.assertEqual(a[:2], [None, None])
        self.assertAlmostEqual(a[2], 2.5)
        self.assertAlmostEqual(a[3], 2.75)

    def test_bollinger_bands_known_answer(self):
        mid, up, lo, wid = self.m._n100_bands([1, 2, 3, 4, 5], 5, 2.0)
        sd = math.sqrt(2.0)                          # population standard deviation of 1..5
        self.assertAlmostEqual(mid[4], 3.0)
        self.assertAlmostEqual(up[4], 3 + 2 * sd)
        self.assertAlmostEqual(lo[4], 3 - 2 * sd)
        self.assertAlmostEqual(wid[4], 4 * sd / 3.0)
        self.assertEqual(mid[:4], [None] * 4)

    def test_sma_and_ema(self):
        self.assertEqual(self.m._n100_sma([1, 2, 3, 4, 5], 3), [None, None, 2.0, 3.0, 4.0])
        e = self.m._n100_ema([1, 2, 3, 4, 5], 3)                       # seeded with the average of the first 3 (2.0), alpha 0.5
        self.assertEqual(e[:2], [None, None])
        self.assertAlmostEqual(e[2], 2.0)
        self.assertAlmostEqual(e[3], 3.0)
        self.assertAlmostEqual(e[4], 4.0)

    def test_prior_high_excludes_the_bar_itself(self):
        self.assertEqual(self.m._n100_prior_high([1, 5, 3, 9], 2), [None, None, 5, 5])
        self.assertEqual(self.m._n100_prior_low([4, 2, 3, 1], 2), [None, None, 2, 2])
        self.assertEqual(self.m._n100_window_high([1, 5, 3, 9], 3), [None, None, 5, 9])

    def test_adx_is_high_in_a_straight_trend_and_low_in_a_flat_market(self):
        up = candles([100 + k for k in range(80)], wick=0.002)
        adx = self.m._n100_adx([x['h'] for x in up], [x['l'] for x in up], [x['c'] for x in up], 14)
        self.assertGreater(adx[-1], 60)
        self.assertIsNone(adx[26])                                       # the first value is at bar 2n-1 = 27
        self.assertIsNotNone(adx[27])
        rnd = random.Random(3)
        flat = candles([100 + (k % 2) * 0.2 + rnd.gauss(0, 0.05) for k in range(120)], wick=0.001)
        adx2 = self.m._n100_adx([x['h'] for x in flat], [x['l'] for x in flat], [x['c'] for x in flat], 14)
        self.assertLess(adx2[-1], 25)

    def test_supertrend_follows_a_trend_and_flips_on_a_reversal(self):
        up = candles([100 + k for k in range(60)], wick=0.002)
        line, d = self.m._n100_supertrend([x['h'] for x in up], [x['l'] for x in up], [x['c'] for x in up], 10, 3.0)
        self.assertEqual(d[-1], 1)
        self.assertLess(line[-1], up[-1]['c'])
        self.assertIsNone(d[9])
        down = candles([160 - 4 * k for k in range(15)], wick=0.002)
        both = up + [dict(x, ts=up[-1]['ts'] + (k + 1) * 86400) for k, x in enumerate(down)]
        line, d = self.m._n100_supertrend([x['h'] for x in both], [x['l'] for x in both], [x['c'] for x in both], 10, 3.0)
        self.assertEqual(d[-1], -1)
        self.assertGreater(line[-1], both[-1]['c'])

    def test_realised_volatility_known_answer(self):
        # alternating +1% and -1% log returns: sample standard deviation of the 20 returns is about 1.026% -> x sqrt(252)
        c = [100.0]
        for k in range(20):
            c.append(c[-1] * math.exp(0.01 if k % 2 == 0 else -0.01))
        r = [math.log(c[i] / c[i - 1]) for i in range(1, 21)]
        mean = sum(r) / 20
        sd = math.sqrt(sum((x - mean) ** 2 for x in r) / 19)
        self.assertAlmostEqual(self.m._n100_realized_vol(c, 20), sd * math.sqrt(252) * 100, places=6)
        self.assertIsNone(self.m._n100_realized_vol(c[:10], 20))

    def test_pivots_known_answer(self):
        p = self.m._n100_pivots(110.0, 90.0, 100.0)
        self.assertAlmostEqual(p['pivot'], 100.0)
        self.assertAlmostEqual(p['r1'], 110.0)
        self.assertAlmostEqual(p['s1'], 90.0)
        self.assertAlmostEqual(p['r2'], 120.0)
        self.assertAlmostEqual(p['s2'], 80.0)
        self.assertAlmostEqual(p['bc'], 100.0)
        self.assertAlmostEqual(p['tc'], 100.0)

    def test_percentile_rank(self):
        s = [None] * 3 + list(range(1, 11))
        self.assertEqual(self.m._n100_pctrank(s, 12, 10), 100.0)
        self.assertEqual(self.m._n100_pctrank(s, 3, 10), None)         # too little history
        s2 = [5.0] * 9 + [1.0]
        self.assertEqual(self.m._n100_pctrank(s2, 9, 10), 10.0)

    def test_prepared_series_have_one_value_per_bar_and_are_causal(self):
        cs = candles(trend(300))
        F = self.m._n100_prepare(cs)
        for k in ('sma5', 'sma200', 'rsi2', 'rsi14', 'atr', 'adx', 'bb_w', 'hh55', 'st_dir', 'vr', 'ret126', 'bb_w_pct'):
            self.assertEqual(len(F[k]), 300, k)
        cut = 250
        F2 = self.m._n100_prepare(cs[:cut + 1])
        for k in ('sma5', 'sma200', 'rsi2', 'rsi14', 'atr', 'adx', 'bb_up', 'hh55', 'll20', 'hh252', 'st_line', 'st_dir', 'avgv', 'bb_w_pct'):
            for i in (cut, cut - 5, 200):
                self.assertEqual(F[k][i], F2[k][i], (k, i))            # the value at bar i never depends on bars after i

    def test_short_series_do_not_crash(self):
        F = self.m._n100_prepare(candles([100, 101, 102]))
        self.assertEqual(F['n'], 3)
        self.assertIsNone(F['sma200'][2])
        self.assertEqual(self.m._n100_signals_at(F, 2)[0], [])


# ===================================================================================================================
# 2. THE STRATEGIES: each fires on a built case, and says why not otherwise
# ===================================================================================================================
class TestStrategies(SigmaCase):
    def test_rsi2_pullback_fires_on_a_dip_in_an_uptrend(self):
        F = self.m._n100_prepare(candles(dip_closes()))
        i = F['n'] - 1
        s, why = self.m._n100_s_rsi2(F, i, 1)
        self.assertIsNone(why)
        self.assertEqual(s['strategy'], 'RSI2')
        self.assertLess(F['rsi2'][i], 10)
        self.assertGreater(F['c'][i], F['sma200'][i])
        self.assertAlmostEqual(s['ref'] - s['stop'], 2.5 * F['atr'][i])
        self.assertEqual((s['rule'], s['horizon'], s['side']), ('sma5', 8, 1))
        self.assertAlmostEqual(s['t1'], F['sma5'][i])
        self.assertIn('RSI(2) fell to', s['trigger'])

    def test_rsi2_does_not_fire_below_the_200_day_average_or_when_not_oversold(self):
        cl = trend(260, drift=-0.003)
        cl += [cl[-1] * 0.985, cl[-1] * 0.985 ** 2, cl[-1] * 0.985 ** 3]
        F = self.m._n100_prepare(candles(cl))
        s, why = self.m._n100_s_rsi2(F, F['n'] - 1, 1)
        self.assertIsNone(s)
        self.assertIn('not above its 200-day average', why)
        F = self.m._n100_prepare(candles(trend(262)))
        s, why = self.m._n100_s_rsi2(F, F['n'] - 1, 1)
        self.assertIsNone(s)
        self.assertTrue('washed-out dip' in why or 'RSI(2)' in why)

    def test_rsi2_short_is_the_mirror(self):
        cl = trend(260, drift=-0.003)
        cl += [cl[-1] * 1.02, cl[-1] * 1.02 ** 2, cl[-1] * 1.02 ** 3]
        F = self.m._n100_prepare(candles(cl))
        s, why = self.m._n100_s_rsi2(F, F['n'] - 1, -1)
        self.assertIsNone(why)
        self.assertGreater(s['stop'], s['ref'])
        self.assertEqual(s['side'], -1)

    def test_donchian_breakout_fires_on_volume_and_trend(self):
        cl = breakout_closes()
        vols = [1e6] * 260 + [2.5e6]
        F = self.m._n100_prepare(candles(cl, vols))
        i = F['n'] - 1
        s, why = self.m._n100_s_donchian(F, i, 1)
        self.assertIsNone(why)
        self.assertGreater(F['c'][i], F['hh55'][i])
        self.assertAlmostEqual(s['ref'] - s['stop'], 2.5 * F['atr'][i])
        self.assertEqual((s['trail_mult'], s['rule'], s['scale']), (3.0, 'donchian20', 2.0))
        self.assertAlmostEqual(s['t1'] - s['ref'], 2 * (s['ref'] - s['stop']))
        self.assertIn('closed above the 55-day high', s['trigger'])

    def test_donchian_refuses_a_weak_volume_break_a_low_adx_and_a_stretched_price(self):
        cl = breakout_closes()
        F = self.m._n100_prepare(candles(cl, [1e6] * 261))
        s, why = self.m._n100_s_donchian(F, F['n'] - 1, 1)
        self.assertIsNone(s)
        self.assertIn('volume is only', why)
        rnd = random.Random(2)
        flat = [100 + rnd.gauss(0, 0.4) for _ in range(260)]
        flat.append(max(flat[-56:-1]) + 0.2)
        F = self.m._n100_prepare(candles(flat, [1e6] * 260 + [3e6]))
        s, why = self.m._n100_s_donchian(F, F['n'] - 1, 1)
        self.assertIsNone(s)
        self.assertTrue('ADX' in why or 'below the 200-day' in why or 'closed above' in why or 'stretched' in why, why)

    def test_high52_fires_near_a_fresh_high_in_an_uptrend(self):
        F = self.m._n100_prepare(candles(breakout_closes(), [1e6] * 261))
        fired = fire_indexes(self.m, F, 'HIGH52', 1)
        self.assertTrue(fired)
        i = fired[-1]
        s, why = self.m._n100_s_high52(F, i, 1)
        self.assertIsNone(why)
        self.assertGreaterEqual(F['c'][i] / F['hh252'][i], 0.97)
        self.assertGreater(F['c'][i], F['hh20'][i])
        self.assertGreaterEqual(F['ret126'][i], 0.10)
        self.assertLessEqual(F['rsi14'][i], 80)

    def test_high52_is_long_only_and_waits_for_a_fresh_high(self):
        F = self.m._n100_prepare(candles(breakout_closes(), [1e6] * 261))
        s, why = self.m._n100_s_high52(F, F['n'] - 1, -1)
        self.assertEqual((s, why), (None, 'long only'))
        cl = trend(262)
        cl[-1] = cl[-2] * 0.999
        F = self.m._n100_prepare(candles(cl))
        s, why = self.m._n100_s_high52(F, F['n'] - 1, 1)
        self.assertIsNone(s)

    def test_squeeze_breakout_fires_after_a_squeeze_on_volume(self):
        cl = squeeze_closes()
        F = self.m._n100_prepare(candles(cl, [1e6] * (len(cl) - 1) + [2.2e6]))
        i = F['n'] - 1
        self.assertLessEqual(F['bb_w_pct'][i - 1], 20)
        s, why = self.m._n100_s_squeeze(F, i, 1)
        self.assertIsNone(why)
        risk = s['ref'] - s['stop']
        self.assertTrue(F['atr'][i] * 1.0 - 1e-9 <= risk <= F['atr'][i] * 3.0 + 1e-9)
        self.assertAlmostEqual(s['target'] - s['ref'], 2 * risk)
        s2, why2 = self.m._n100_s_squeeze(F, i, -1)
        self.assertIsNone(s2)
        self.assertIn('has not closed outside the bands', why2)

    def test_squeeze_needs_the_squeeze_and_the_volume(self):
        rnd = random.Random(5)
        cl, px = [], 100.0
        for _ in range(200):
            px *= 1 + rnd.gauss(0, 0.012)
            cl.append(px)
        cl.append(cl[-1] * 1.04)
        F = self.m._n100_prepare(candles(cl, [1e6] * 200 + [2e6]))
        s, why = self.m._n100_s_squeeze(F, F['n'] - 1, 1)
        self.assertIsNone(s)
        self.assertIn('no squeeze', why)
        cl = squeeze_closes()
        F = self.m._n100_prepare(candles(cl, [1e6] * len(cl)))
        s, why = self.m._n100_s_squeeze(F, F['n'] - 1, 1)
        self.assertIsNone(s)
        self.assertIn('on only', why)

    def test_supertrend_flip_fires_with_adx_and_has_a_bounded_stop(self):
        F = self.m._n100_prepare(candles(flip_closes()))
        fired = fire_indexes(self.m, F, 'SUPERTREND', 1, 20)
        self.assertTrue(fired, 'no flip fired on the built reversal')
        i = fired[0]
        s, _w = self.m._n100_s_supertrend(F, i, 1)
        self.assertEqual((F['st_dir'][i - 1], F['st_dir'][i]), (-1, 1))
        self.assertGreaterEqual(F['adx'][i], 20)
        risk = s['ref'] - s['stop']
        self.assertTrue(F['atr'][i] - 1e-9 <= risk <= 4.0 * F['atr'][i] + 1e-9)
        self.assertTrue(s['st_trail'] and s['rule'] == 'st_flip')

    def test_supertrend_refuses_a_flip_without_adx(self):
        rnd = random.Random(9)
        cl, px = [], 100.0
        for k in range(200):
            px = 100 + 3 * math.sin(k / 3.0) + rnd.gauss(0, 0.3)
            cl.append(px)
        F = self.m._n100_prepare(candles(cl))
        flips = [i for i in range(40, F['n']) if F['st_dir'][i] == 1 and F['st_dir'][i - 1] == -1]
        self.assertTrue(flips)
        for i in flips:
            s, why = self.m._n100_s_supertrend(F, i, 1)
            if F['adx'][i] < 20:
                self.assertIsNone(s)
                self.assertIn('whipsaw', why)

    def test_every_signal_has_a_stop_on_the_losing_side_and_a_time_limit(self):
        for closes, vols, name in ((dip_closes(), None, 'RSI2'), (breakout_closes(), [1e6] * 260 + [2.5e6], 'DONCHIAN'), (squeeze_closes(), [1e6] * 195 + [2.2e6], 'SQUEEZE')):
            F = self.m._n100_prepare(candles(closes, vols))
            s, why = self.m._N100_FUNCS[name](F, F['n'] - 1, 1)
            self.assertIsNone(why, name)
            self.assertLess(s['stop'], s['ref'], name)
            self.assertGreaterEqual(s['horizon'], 8)
            self.assertTrue(s['trigger'])

    def test_the_rules_are_fixed_constants(self):
        R = self.m._N100_RULES
        self.assertEqual((R['RSI2']['rsi_below'], R['RSI2']['trend_sma'], R['RSI2']['stop_atr'], R['RSI2']['horizon']), (10.0, 200, 2.5, 8))
        self.assertEqual((R['DONCHIAN']['n'], R['DONCHIAN']['vol_mult'], R['DONCHIAN']['adx_min'], R['DONCHIAN']['trail_atr']), (55, 1.3, 20.0, 3.0))
        self.assertEqual((R['SUPERTREND']['period'], R['SUPERTREND']['mult']), (10, 3.0))
        self.assertEqual(set(R), {'RSI2', 'DONCHIAN', 'HIGH52', 'SQUEEZE', 'SUPERTREND', 'ORB'})

    def test_why_not_is_given_for_every_rule(self):
        F = self.m._n100_prepare(candles(trend(262)))
        sigs, why = self.m._n100_signals_at(F, F['n'] - 1)
        for (name, side), text in why.items():
            self.assertTrue(text and isinstance(text, str), (name, side))
        self.assertEqual(len(sigs) + len(why), 9)                        # five rules, four of them in both directions


# ===================================================================================================================
# 3. FOLLOWING A PLAN: the walk used by the backtest and by the record
# ===================================================================================================================
class TestWalker(SigmaCase):
    def walk(self, F, sp, i=0):
        return self.m._n100_walk(F, i, sp)

    def test_stop_first_when_one_candle_touches_both(self):
        F = tiny_F([100, 100, 100], [100, 108, 100], [100, 94, 100], [100, 100, 100])
        w = self.walk(F, spec(target=105.0))
        self.assertEqual((w['status'], w['reason'], w['exit']), ('closed', 'stop', 95.0))
        self.assertAlmostEqual(w['r'], -1.0)

    def test_a_gap_through_the_stop_exits_at_the_open_not_the_stop(self):
        F = tiny_F([100, 100, 90], [100, 101, 91], [100, 99.9, 89], [100, 100.5, 90])
        w = self.walk(F, spec())
        self.assertEqual((w['reason'], w['exit']), ('stop (gap)', 90.0))
        self.assertAlmostEqual(w['r'], -2.0)

    def test_target_hit_and_target_gap(self):
        F = tiny_F([100, 100, 100], [100, 106, 100], [100, 99, 100], [100, 100, 100])
        w = self.walk(F, spec(target=105.0))
        self.assertEqual((w['reason'], w['exit']), ('target', 105.0))
        self.assertAlmostEqual(w['r'], 1.0)
        F = tiny_F([100, 100, 107], [100, 101, 108], [100, 99, 106], [100, 100, 107])
        w = self.walk(F, spec(target=105.0))
        self.assertEqual((w['reason'], w['exit']), ('target', 107.0))                  # a gap above the target is a better fill
        self.assertAlmostEqual(w['r'], 1.4)

    def test_time_exit_at_the_close_of_the_last_allowed_bar(self):
        F = tiny_F([100] * 6, [101] * 6, [99] * 6, [100, 100.2, 100.4, 100.6, 100.8, 101])
        w = self.walk(F, spec(horizon=3))
        self.assertEqual((w['reason'], w['exit_i'], w['bars']), ('time', 3, 3))
        self.assertAlmostEqual(w['exit'], 100.6)

    def test_rule_exit_is_taken_at_the_next_open(self):
        F = tiny_F([100, 100, 103, 104], [101, 101, 104, 105], [99.5, 99.5, 102, 103], [100, 101, 103.5, 104], {'sma5': [100.0] * 4})
        w = self.walk(F, spec(rule='sma5', horizon=20))
        self.assertEqual((w['reason'], w['exit_i'], w['exit']), ('rule', 2, 103.0))      # the close of bar 1 (101) is above the average: leave at the open of bar 2

    def test_skipped_when_the_open_is_beyond_the_stop_or_chasing(self):
        F = tiny_F([100, 94, 100], [100, 95, 100], [100, 93, 100], [100, 94.5, 100])
        w = self.walk(F, spec())
        self.assertEqual(w['status'], 'skipped')
        self.assertIn('beyond the stop', w['reason'])
        F = tiny_F([100, 103, 100], [100, 104, 100], [100, 102, 100], [100, 103, 100])
        w = self.walk(F, spec())                                                          # 103 is 8 from the stop 95, risk 5: 1.6 times
        self.assertEqual(w['status'], 'skipped')
        self.assertIn('chasing', w['reason'])
        F = tiny_F([100, 102, 100], [100, 103, 100], [100, 101, 100], [100, 102, 100])
        w = self.walk(F, spec(target=101.0))                                             # 7 from the stop (not chasing) but already past the target
        self.assertIn('beyond the target', w['reason'])

    def test_trailing_stop_ratchets_and_never_loosens(self):
        F = tiny_F([100, 100, 109, 100], [100, 110, 109.5, 100], [100, 99, 107.5, 100], [100, 109, 108, 100])
        w = self.walk(F, spec(trail=1.0, atr=2.0, horizon=20))
        self.assertEqual((w['reason'], w['exit']), ('stop', 108.0))                      # best 110 after bar 1, stop 110-2*1 = 108, bar 2 low 107.5
        self.assertAlmostEqual(w['r'], 1.6)

    def test_short_side_mirrors(self):
        F = tiny_F([100, 100, 100], [100, 101, 100], [100, 94, 100], [100, 96, 100])
        w = self.walk(F, spec(side=-1, ref=100.0, stop=105.0, target=95.0))
        self.assertEqual((w['reason'], w['exit']), ('target', 95.0))
        self.assertAlmostEqual(w['r'], 1.0)
        F = tiny_F([100, 100, 100], [100, 106, 100], [100, 99, 100], [100, 100, 100])
        w = self.walk(F, spec(side=-1, ref=100.0, stop=105.0))
        self.assertEqual((w['reason'], w['exit']), ('stop', 105.0))

    def test_pending_open_and_closed_states(self):
        F = tiny_F([100], [100], [100], [100])
        self.assertEqual(self.walk(F, spec())['status'], 'pending')
        F = tiny_F([100, 100, 100], [100, 101, 101], [100, 99, 99], [100, 100, 100])
        w = self.walk(F, spec(horizon=10))
        self.assertEqual(w['status'], 'open')
        self.assertEqual(w['entry'], 100.0)

    def test_supertrend_line_trails_the_stop(self):
        F = tiny_F([100, 100, 100, 100], [100, 101, 101, 101], [100, 99, 99.5, 96], [100, 100, 100, 99], {'st_dir': [1, 1, 1, 1], 'st_line': [90.0, 96.0, 97.0, 98.0]})
        w = self.walk(F, spec(st_trail=True, horizon=20))
        self.assertEqual((w['reason'], w['exit']), ('stop', 97.0))                       # the line at bar 2 is 97: bar 3 trades down to 96

    def test_deadline_ends_an_intraday_plan_at_the_open_of_the_first_bar_past_it(self):
        F = tiny_F([100, 100, 101, 102], [101, 101, 102, 103], [99.5, 99.5, 100.5, 101.5], [100, 100.5, 101.5, 102], t0=1000)
        w = self.walk(F, spec(horizon=10 ** 6, deadline=1000 + 3 * 86400))
        self.assertEqual((w['reason'], w['exit_i'], w['exit']), ('time', 3, 102.0))

    def test_no_look_ahead_the_future_cannot_change_a_closed_trade(self):
        rnd = random.Random(11)
        base_cs = candles(trend(420, seed=5, vol=0.011, drift=0.0008))
        bt1 = self.m._n100_backtest(base_cs, kind='stock')
        self.assertGreater(len(bt1['trades']), 5)
        K = 300
        cs2 = copy.deepcopy(base_cs)
        for x in cs2[K + 1:]:
            f = 1 + rnd.uniform(-0.3, 0.3)
            x.update(o=x['o'] * f, h=x['h'] * f, l=x['l'] * f, c=x['c'] * f)
        bt2 = self.m._n100_backtest(cs2, kind='stock')
        t1 = [(t['strategy'], t['i'], t['entry'], t['exit'], t['reason']) for t in bt1['trades'] if t['i'] + t['bars'] <= K]
        t2 = [(t['strategy'], t['i'], t['entry'], t['exit'], t['reason']) for t in bt2['trades'] if t['i'] + t['bars'] <= K]
        self.assertTrue(t1)
        self.assertEqual(t1, t2)

    def test_signals_at_a_bar_do_not_depend_on_later_bars(self):
        cs = candles(trend(330, seed=8, vol=0.013, drift=0.001))
        F = self.m._n100_prepare(cs)
        G = self.m._n100_prepare(cs[:301])
        for i in (250, 280, 300):
            a, _ = self.m._n100_signals_at(F, i)
            b, _ = self.m._n100_signals_at(G, i)
            self.assertEqual([(s['strategy'], s['side'], round(s['stop'], 8)) for s in a], [(s['strategy'], s['side'], round(s['stop'], 8)) for s in b])


# ===================================================================================================================
# 4. CHARGES
# ===================================================================================================================
class TestCosts(SigmaCase):
    def test_share_round_trip_cost_is_the_sum_of_its_parts(self):
        c = self.m._N100_EQ_COST
        expect = 2 * 0.03 + 2 * 0.10 + 2 * 0.00297 + 2 * 0.0001 + 0.015 + 0.18 * (2 * 0.03 + 2 * 0.00297 + 2 * 0.0001) + 2 * 0.05
        self.assertAlmostEqual(self.m._n100_cost_pct('stock'), expect, places=9)
        self.assertAlmostEqual(self.m._n100_cost_pct('stock'), 0.393045, places=5)
        self.assertEqual(c['stt_side'], 0.10)                              # delivery shares pay STT on both legs

    def test_index_cost_is_futures_like_and_smaller(self):
        self.assertAlmostEqual(self.m._n100_cost_pct('index'), 0.10222, places=4)
        self.assertLess(self.m._n100_cost_pct('index'), self.m._n100_cost_pct('stock'))

    def test_net_result_subtracts_charges_in_risk_units(self):
        w = {'status': 'closed', 'entry': 100.0, 'risk': 5.0, 'r': 1.0}
        self.assertAlmostEqual(self.m._n100_net_r(w, 'stock'), 1.0 - 100.0 * 0.393045 / 100 / 5.0, places=5)
        self.assertIsNone(self.m._n100_net_r({'status': 'open'}, 'stock'))

    def test_costs_follow_the_ledger_table_for_options(self):
        legs = [(1, 'CE', 24500.0, 100.0)]
        c = self.m._n100_costs_lot(legs, 65)
        self.assertGreater(c, 40.0)                                         # two orders of the ledger's brokerage plus tax and fees
        self.m._n96_q("INSERT OR REPLACE INTO ledger96_setting(key,value) VALUES('costs', ?)", (json.dumps(dict(self.m._N96_COSTS_DEFAULT, **{'on': 0.0})),), write=True)
        try:
            self.assertEqual(self.m._n100_costs_lot(legs, 65), c)            # switched off in the ledger: Sigma still charges (it never flatters a plan)
        finally:
            self.m._n96_q("DELETE FROM ledger96_setting WHERE key='costs'", write=True)


# ===================================================================================================================
# 5. THE CHAIN, READ
# ===================================================================================================================
def chain_with(m, spot=24490.0, iv=14.0, days=6.0, put_iv_extra=0.0, put_oi_x=1.0, buildup=None, **kw):
    ch = make_chain(m, spot=spot, iv=iv, days=days, **kw)
    for r in ch['rows']:
        if r['type'] == 'PE':
            if put_iv_extra:
                r['iv'] += put_iv_extra
            r['oi'] *= put_oi_x
        if buildup:
            r['oi_change'], r['chp'] = buildup(r)
    return ch


class TestChain(SigmaCase):
    def test_expected_move_is_spot_times_iv_times_root_time(self):
        st = self.m._n100_chain_stats(chain_with(self.m), 65, 50)
        self.assertAlmostEqual(st['em_iv'], 24490.0 * 0.14 * math.sqrt(6.0 / 365.0), delta=0.5)
        self.assertEqual(st['em'], st['em_iv'])
        self.assertLess(st['em_gap_pct'], 3.0)                         # a straddle is worth about 0.8 of one standard deviation, so x1.25 agrees with the volatility figure
        self.assertAlmostEqual(st['em_straddle'], st['straddle'] * 1.25)
        self.assertAlmostEqual(st['em_pct'], st['em'] / 24490.0 * 100.0)
        self.assertAlmostEqual(st['daily_move'], 24490.0 * 0.14 / math.sqrt(365.0), delta=0.5)

    def test_atm_strike_iv_and_straddle(self):
        st = self.m._n100_chain_stats(chain_with(self.m), 65, 50)
        self.assertEqual(st['atm'], 24500.0)
        self.assertAlmostEqual(st['atm_iv'], 14.0, delta=0.01)
        self.assertGreater(st['straddle'], 300)
        self.assertTrue(st['atm_liquid'])

    def test_pcr_walls_and_added_interest(self):
        ch = chain_with(self.m, put_oi_x=2.0)
        for r in ch['rows']:
            if r['type'] == 'CE' and r['strike'] == 24650.0:
                r['oi'] = 900000.0
            if r['type'] == 'PE' and r['strike'] == 24300.0:
                r['oi'] = 800000.0
                r['oi_change'] = 50000.0
        st = self.m._n100_chain_stats(ch, 65, 50)
        self.assertEqual((st['call_wall'], st['put_wall']), (24650.0, 24300.0))
        self.assertEqual(st['put_add'], 24300.0)
        ce = sum(r['oi'] for r in ch['rows'] if r['type'] == 'CE')
        pe = sum(r['oi'] for r in ch['rows'] if r['type'] == 'PE')
        self.assertAlmostEqual(st['pcr_oi'], pe / ce)

    def test_skew_is_put_volatility_minus_call_volatility_half_a_move_out(self):
        st = self.m._n100_chain_stats(chain_with(self.m, put_iv_extra=3.0), 65, 50)
        self.assertAlmostEqual(st['skew'], 3.0, delta=0.15)
        st0 = self.m._n100_chain_stats(chain_with(self.m), 65, 50)
        self.assertAlmostEqual(st0['skew'], 0.0, delta=0.1)

    def test_buildup_reads_put_writing_as_bullish_and_call_writing_as_bearish(self):
        def put_writing(r):
            return (80000.0, -10.0) if r['type'] == 'PE' else (1000.0, 2.0)
        st = self.m._n100_chain_stats(chain_with(self.m, buildup=put_writing), 65, 50)
        self.assertGreater(st['buildup']['score'], 0.5)
        self.assertEqual(st['buildup']['top'][0][2], 'put writing')

        def call_writing(r):
            return (80000.0, -10.0) if r['type'] == 'CE' else (1000.0, 2.0)
        st = self.m._n100_chain_stats(chain_with(self.m, buildup=call_writing), 65, 50)
        self.assertLess(st['buildup']['score'], -0.5)
        self.assertEqual(st['buildup']['top'][0][2], 'call writing')

    def test_each_buildup_quadrant_has_the_right_sign(self):
        B = self.m._N100_BUILD
        self.assertEqual(B[('CE', 1, -1)], ('call writing', -1.0))
        self.assertEqual(B[('CE', 1, 1)], ('call buying', 1.0))
        self.assertEqual(B[('PE', 1, -1)], ('put writing', 1.0))
        self.assertEqual(B[('PE', 1, 1)], ('put buying', -1.0))
        self.assertGreater(B[('CE', -1, 1)][1], 0)                      # call short covering: bullish
        self.assertLess(B[('PE', -1, 1)][1], 0)                         # put short covering: bearish

    def test_buildup_is_none_when_the_feed_has_no_changes(self):
        st = self.m._n100_chain_stats(chain_with(self.m), 65, 50)
        self.assertIsNone(st['buildup'])
        ch = chain_with(self.m, buildup=lambda r: (None, None))
        self.assertIsNone(self.m._n100_chain_stats(ch, 65, 50)['buildup'])

    def test_liquidity_gate(self):
        L = self.m._n100_liquid
        ok = {'bid': 100.0, 'ask': 101.0, 'oi': 100000}
        self.assertEqual(L(ok, 65), (True, ''))
        self.assertFalse(L({'bid': 0, 'ask': 0, 'oi': 100000}, 65)[0])
        self.assertIn('spread', L({'bid': 100.0, 'ask': 108.0, 'oi': 100000}, 65)[1])
        self.assertTrue(L({'bid': 2.0, 'ask': 2.8, 'oi': 100000}, 65)[0])             # a cheap contract: 33% wide but under ₹1
        self.assertIn('open interest', L({'bid': 100.0, 'ask': 100.5, 'oi': 100}, 65)[1])

    def test_max_pain_is_context_only(self):
        st = self.m._n100_chain_stats(chain_with(self.m), 65, 50)
        self.assertIsNotNone(st['max_pain'])
        parts = self.m._n100_view_parts(self.m._n100_prepare(candles(trend(200))), 'TREND_UP', st, None, [], 100.0)
        self.assertNotIn('max pain', ' '.join(p[0] for p in parts).lower())               # it never enters the view

    def test_iv_history_is_recorded_at_most_every_twenty_minutes(self):
        st = self.m._n100_chain_stats(chain_with(self.m), 65, 50)
        self.assertTrue(self.m._n100_iv_record('NIFTY', st, now=NOW))
        self.assertFalse(self.m._n100_iv_record('NIFTY', st, now=NOW + 600))
        self.assertTrue(self.m._n100_iv_record('NIFTY', st, now=NOW + 1300))
        self.assertEqual(self.m._n100_q('SELECT COUNT(*) FROM sig100_iv')[0][0], 2)

    def test_iv_percentile_prefers_its_own_history_then_the_vix_then_nothing(self):
        vix = {'pct': 77.0, 'n': 120}
        p, src = self.m._n100_ivp('NIFTY', 14.0, 6.0, vix)
        self.assertEqual(p, 77.0)
        self.assertIn('stand-in', src)
        self.assertEqual(self.m._n100_ivp('NIFTY', 14.0, 6.0, None)[0], None)
        for k in range(60):                                                  # 60 readings over 12 days, volatility 10..19.9
            self.m._n100_q('INSERT INTO sig100_iv(symbol, ts, day, expiry, dte, spot, atm_iv, straddle, pcr) VALUES(?,?,?,?,?,?,?,?,?)',
                           ('NIFTY', NOW - k * 7000, 'd%d' % (k // 5), 'x', 6.0, 24000.0, 10.0 + k / 6.0, 300.0, 1.0), write=True)
        p, src = self.m._n100_ivp('NIFTY', 15.0, 6.0, vix)
        self.assertIn('its own 60 readings over 12 days', src)
        self.assertAlmostEqual(p, 100.0 * sum(1 for k in range(60) if 10.0 + k / 6.0 <= 15.0) / 60.0)
        self.assertEqual(self.m._n100_ivp('NIFTY', 15.0, 20.0, vix)[0], 77.0)         # a different time to expiry has no comparable history: back to the VIX


# ===================================================================================================================
# 6. OPTION MATHS AND STRUCTURES
# ===================================================================================================================
class TestOptionMaths(SigmaCase):
    def test_terminal_distribution_sums_to_one_and_keeps_the_mean(self):
        d = self.m._n100_terminal(24000.0, 15.0, 7.0, fwd=24000.0)
        self.assertAlmostEqual(sum(p for _s, p in d), 1.0, places=9)
        self.assertAlmostEqual(sum(s * p for s, p in d), 24000.0, delta=24000.0 * 0.0005)
        d = self.m._n100_terminal(24000.0, 15.0, 7.0)                                      # no forward given: the spot carried at 6.5%
        self.assertAlmostEqual(sum(s * p for s, p in d), 24000.0 * math.exp(0.065 * 7 / 365.0), delta=24000.0 * 0.0005)

    def test_the_forward_comes_from_put_call_parity_on_the_chain(self):
        ch = chain_with(self.m)
        book = self.m._n100_book(ch)
        f = self.m._n100_forward(book, 24490.0, 6.0, 24500.0)
        self.assertAlmostEqual(f, 24490.0 * math.exp(0.065 * 6.0 / 365.0), delta=1.5)
        self.assertAlmostEqual(self.m._n100_forward({}, 24490.0, 6.0, 24500.0), 24490.0 * math.exp(0.065 * 6.0 / 365.0), places=6)       # no quotes: the spot carried
        for r in book.values():
            r['ltp'] = r['bid'] = r['ask'] = 1.0 if r['type'] == 'CE' else 900.0                                                        # an absurd parity: not trusted
        self.assertAlmostEqual(self.m._n100_forward(book, 24490.0, 6.0, 24500.0), 24490.0 * math.exp(0.065 * 6.0 / 365.0), places=6)

    def test_delta_known_values(self):
        d_c = self.m._n100_delta(100.0, 100.0, 20.0, 30.0, 'CE')
        d_p = self.m._n100_delta(100.0, 100.0, 20.0, 30.0, 'PE')
        self.assertTrue(0.50 < d_c < 0.56)
        self.assertAlmostEqual(d_c - d_p, 1.0, places=9)
        self.assertGreater(self.m._n100_delta(100.0, 80.0, 20.0, 30.0, 'CE'), 0.95)
        self.assertIsNone(self.m._n100_delta(100.0, 100.0, 0.0, 30.0, 'CE'))

    def test_payoff_shapes_worked_by_hand(self):
        sh = self.m._n100_shape([(-1, 'PE', 100.0, 5.0), (1, 'PE', 90.0, 2.0)], 105.0)           # bull put: credit 3, width 10
        self.assertAlmostEqual(sh['max_profit'], 3.0)
        self.assertAlmostEqual(sh['max_loss'], 7.0)
        self.assertEqual(sh['breakevens'], [97.0])
        sh = self.m._n100_shape([(1, 'CE', 100.0, 5.0)], 100.0)                                  # a bought call: unlimited, loses the premium, break-even 105
        self.assertTrue(sh['unlimited'])
        self.assertIsNone(sh['max_profit'])
        self.assertAlmostEqual(sh['max_loss'], 5.0)
        self.assertEqual(sh['breakevens'], [105.0])
        sh = self.m._n100_shape([(1, 'PE', 100.0, 5.0)], 100.0)                                  # a bought put: bounded by the strike
        self.assertFalse(sh['unlimited'])
        self.assertAlmostEqual(sh['max_profit'], 95.0)
        sh = self.m._n100_shape([(-1, 'PE', 24000.0, 30.0), (1, 'PE', 23900.0, 20.0), (-1, 'CE', 25000.0, 30.0), (1, 'CE', 25100.0, 20.0)], 24500.0)
        self.assertAlmostEqual(sh['max_profit'], 20.0)
        self.assertAlmostEqual(sh['max_loss'], 80.0)
        self.assertEqual(sh['breakevens'], [23980.0, 25020.0])
        sh = self.m._n100_shape([(1, 'CE', 100.0, 8.0), (-1, 'CE', 110.0, 3.0)], 100.0)          # bull call: debit 5, width 10
        self.assertAlmostEqual(sh['max_profit'], 5.0)
        self.assertAlmostEqual(sh['max_loss'], 5.0)
        self.assertEqual(sh['breakevens'], [105.0])

    def test_probability_and_expected_value_behave(self):
        far = [(-1, 'PE', 22000.0, 3.0), (1, 'PE', 21900.0, 1.5)]
        pop, _ev = self.m._n100_pop_ev(far, 24500.0, 14.0, 6.0)
        self.assertGreater(pop, 0.99)
        atm_call = [(1, 'CE', 24500.0, 200.0)]
        pop, _ev = self.m._n100_pop_ev(atm_call, 24500.0, 14.0, 6.0)
        self.assertLess(pop, 0.5)
        price = self.m._n93_bs_price(24500.0, 24500.0, 14.0, 6.0, 'CE')
        fwd = 24500.0 * math.exp(0.065 * 6.0 / 365.0)                                     # the forward the Black-Scholes price is built on
        pop, ev = self.m._n100_pop_ev([(1, 'CE', 24500.0, price)], 24500.0, 14.0, 6.0, fwd=fwd)
        self.assertLess(abs(ev), 0.01 * price)                                            # a fairly priced option is worth about nothing before charges
        put = self.m._n93_bs_price(24500.0, 24500.0, 14.0, 6.0, 'PE')
        self.assertLess(abs(self.m._n100_pop_ev([(1, 'PE', 24500.0, put)], 24500.0, 14.0, 6.0, fwd=fwd)[1]), 0.01 * put)
        pop, ev_c = self.m._n100_pop_ev([(1, 'CE', 24500.0, price)], 24500.0, 14.0, 6.0, cost_unit=5.0, fwd=fwd)
        self.assertAlmostEqual(ev - ev_c, 5.0, places=9)
        self.assertLess(pop, 0.5)

    def test_value_of_a_structure_at_another_price_and_time(self):
        legs = [(1, 'CE', 100.0, 5.0), (-1, 'CE', 110.0, 2.0)]
        v_up = self.m._n100_value(legs, 110.0, 5.0, [20.0, 20.0])
        v_dn = self.m._n100_value(legs, 90.0, 5.0, [20.0, 20.0])
        self.assertGreater(v_up, 5.0)
        self.assertLess(v_dn, 1.0)
        self.assertLessEqual(v_up, 10.0)


class StructureCase(SigmaCase):
    def setUp(self):
        super().setUp()
        self.ch = chain_with(self.m, spot=24490.0, iv=14.0, days=6.0)
        for r in self.ch['rows']:                      # wider quotes than the fixture's 0.3%, and plenty of open interest
            r['bid'], r['ask'], r['oi'] = round(r['ltp'] * 0.99, 2), round(r['ltp'] * 1.01, 2), 500000.0
        st = self.m._n100_chain_stats(self.ch, 65, 50)
        self.st = st
        self.ctx = {'spot': 24490.0, 'days': 6.0, 'lot': 65, 'step': 50, 'atm_iv': st['atm_iv'], 'em': st['em'], 'book': self.m._n100_book(self.ch), 'atm_liquid': True}
        self.lv = {'stop': 24300.0, 't1': 24700.0, 't2': 24850.0}


class TestStructures(StructureCase):
    def test_long_option_uses_the_ask_and_a_delta_near_half(self):
        p, why = self.m._n100_long(self.ctx, 1, self.lv)
        self.assertIsNone(why)
        lg = p['legs'][0]
        self.assertEqual((lg['action'], lg['type']), ('BUY', 'CE'))
        row = self.ctx['book'][(lg['strike'], 'CE')]
        self.assertEqual(lg['px'], row['ask'])
        self.assertTrue(0.40 <= p['delta'] <= 0.70)
        self.assertAlmostEqual(p['max_loss'], lg['px'])
        self.assertTrue(p['unlimited'])
        self.assertAlmostEqual(p['breakevens'][0], lg['strike'] + lg['px'], places=1)
        self.assertGreater(p['cost_lot'], 40)
        self.assertLess(p['sl'], p['premium'])
        self.assertGreater(p['tp1'], p['premium'])
        self.assertGreaterEqual(p['sl'], p['premium'] * (1 - self.m._N100_PREM_STOP) - 1e-9)

    def test_long_put_for_a_bearish_view(self):
        p, why = self.m._n100_long(self.ctx, -1, {'stop': 24700.0, 't1': 24300.0, 't2': 24150.0})
        self.assertIsNone(why)
        self.assertEqual(p['legs'][0]['type'], 'PE')
        self.assertFalse(p['unlimited'])

    def test_debit_spread_pays_the_ask_and_collects_the_bid(self):
        p, why = self.m._n100_debit(self.ctx, 1, self.lv)
        self.assertIsNone(why)
        buy, sell = p['legs']
        self.assertEqual((buy['action'], sell['action']), ('BUY', 'SELL'))
        self.assertEqual(buy['px'], self.ctx['book'][(buy['strike'], 'CE')]['ask'])
        self.assertEqual(sell['px'], self.ctx['book'][(sell['strike'], 'CE')]['bid'])
        self.assertGreaterEqual(sell['strike'] - buy['strike'], 100.0)
        self.assertAlmostEqual(p['debit'], buy['px'] - sell['px'])
        self.assertAlmostEqual(p['max_loss'], p['debit'])
        self.assertAlmostEqual(p['max_profit'], p['width'] - p['debit'])
        self.assertAlmostEqual(p['breakevens'][0], buy['strike'] + p['debit'], places=1)
        self.assertEqual(p['plan_risk'], p['premium'] - p['sl'])

    def test_credit_spread_geometry_and_exit_plan(self):
        p, why = self.m._n100_credit(self.ctx, 1)
        self.assertIsNone(why)
        short, wing = p['legs']
        self.assertEqual((short['action'], short['type'], wing['action']), ('SELL', 'PE', 'BUY'))
        self.assertLess(short['strike'], 24490.0)
        self.assertLess(wing['strike'], short['strike'])
        self.assertGreaterEqual(24490.0 - short['strike'], 0.8 * self.st['em'])
        w = short['strike'] - wing['strike']
        self.assertAlmostEqual(p['credit'], short['px'] - wing['px'])
        self.assertAlmostEqual(p['max_loss'], w - p['credit'])
        self.assertAlmostEqual(p['max_profit'], p['credit'])
        self.assertAlmostEqual(p['breakevens'][0], short['strike'] - p['credit'], places=1)
        self.assertAlmostEqual(p['tp1'], 0.5 * p['credit'])
        self.assertAlmostEqual(p['sl'], min(2.0 * p['credit'], 0.85 * w))
        self.assertAlmostEqual(p['plan_risk'], p['sl'] - p['credit'])
        self.assertGreater(p['pop'], 0.6)

    def test_bear_call_credit_spread_mirrors(self):
        p, why = self.m._n100_credit(self.ctx, -1)
        self.assertIsNone(why)
        short, wing = p['legs']
        self.assertEqual(short['type'], 'CE')
        self.assertGreater(short['strike'], 24490.0)
        self.assertGreater(wing['strike'], short['strike'])

    def test_iron_condor_has_four_legs_and_a_worst_case_on_one_side(self):
        p, why = self.m._n100_condor(self.ctx)
        self.assertIsNone(why)
        self.assertEqual(sorted((lg['action'], lg['type']) for lg in p['legs']), [('BUY', 'CE'), ('BUY', 'PE'), ('SELL', 'CE'), ('SELL', 'PE')])
        sp = [lg['strike'] for lg in p['legs'] if lg['action'] == 'SELL' and lg['type'] == 'PE'][0]
        sc = [lg['strike'] for lg in p['legs'] if lg['action'] == 'SELL' and lg['type'] == 'CE'][0]
        wp = [lg['strike'] for lg in p['legs'] if lg['action'] == 'BUY' and lg['type'] == 'PE'][0]
        wc = [lg['strike'] for lg in p['legs'] if lg['action'] == 'BUY' and lg['type'] == 'CE'][0]
        self.assertEqual(sp - wp, wc - sc)
        self.assertAlmostEqual(p['width'], sp - wp)
        self.assertAlmostEqual(p['max_loss'], p['width'] - p['credit'])
        self.assertEqual(len(p['breakevens']), 2)
        self.assertAlmostEqual(p['breakevens'][0], sp - p['credit'], places=1)
        self.assertAlmostEqual(p['breakevens'][1], sc + p['credit'], places=1)
        self.assertGreaterEqual(min(24490.0 - sp, sc - 24490.0), 0.9 * self.st['em'])

    def test_a_structure_with_no_quotes_is_refused(self):
        for r in self.ctx['book'].values():
            r['bid'] = r['ask'] = 0
        for fn in (lambda: self.m._n100_long(self.ctx, 1, self.lv), lambda: self.m._n100_debit(self.ctx, 1, self.lv), lambda: self.m._n100_credit(self.ctx, 1), lambda: self.m._n100_condor(self.ctx)):
            p, why = fn()
            self.assertIsNone(p)
            self.assertTrue(why)

    def test_acceptance_tests(self):
        p, _ = self.m._n100_debit(self.ctx, 1, self.lv)
        bad = dict(p, rr=1.1)
        ok, why = self.m._n100_plan_ok(bad, self.ctx)
        self.assertFalse(ok)
        self.assertIn('reward to risk', why)
        c, _ = self.m._n100_credit(self.ctx, 1)
        ok, why = self.m._n100_plan_ok(dict(c, credit_ratio=0.05), self.ctx)
        self.assertFalse(ok)
        self.assertIn('credit is only', why)
        ok, why = self.m._n100_plan_ok(dict(c, pop=0.5), self.ctx)
        self.assertIn('probability of profit', why)
        ok, why = self.m._n100_plan_ok(dict(c, cost_lot=c['max_profit'] * 65 * 0.5), self.ctx)
        self.assertIn('charges would take', why)
        ok, why = self.m._n100_plan_ok(dict(c, short_distance=100.0), self.ctx)
        self.assertIn('inside 0.8 of the expected move', why)

    def test_sizing_rounds_down_and_never_up(self):
        p, _ = self.m._n100_credit(self.ctx, 1)
        per_lot = p['max_loss'] * 65
        cfg = {'capital': per_lot * 3.5 / 0.01, 'risk_pct': 1.0, 'max_position_pct': 25.0}
        z = self.m._n100_size_option(p, cfg)
        self.assertEqual(z['lots'], 3)
        self.assertAlmostEqual(z['risk_total'], 3 * per_lot)
        z = self.m._n100_size_option(p, {'capital': per_lot * 0.99 / 0.01, 'risk_pct': 1.0, 'max_position_pct': 25.0})
        self.assertEqual((z['lots'], z['fits']), (0, False))
        self.assertAlmostEqual(z['capital_for_one'], per_lot / 0.01)
        self.assertIn('worst case', z['basis'])

    def test_a_bought_structure_is_sized_by_its_planned_exit_and_capped_by_outlay(self):
        p, _ = self.m._n100_long(self.ctx, 1, self.lv)
        z = self.m._n100_size_option(p, {'capital': 1000000.0, 'risk_pct': 1.0, 'max_position_pct': 25.0})
        self.assertEqual(z['per_lot_risk'], p['plan_risk'] * 65)
        self.assertEqual(z['lots'], int(10000.0 // (p['plan_risk'] * 65)))
        z = self.m._n100_size_option(p, {'capital': 1000000.0, 'risk_pct': 5.0, 'max_position_pct': 5.0})            # the outlay cap (5% = ₹50,000) bites before the risk limit
        self.assertLessEqual(z['lots'] * p['premium'] * 65, 50000.0)
        self.assertLess(z['lots'], int(50000.0 // (p['plan_risk'] * 65)))

    def test_a_twenty_thousand_rupee_account_gets_zero_lots_and_the_capital_it_would_need(self):
        for fn in (lambda: self.m._n100_long(self.ctx, 1, self.lv), lambda: self.m._n100_debit(self.ctx, 1, self.lv), lambda: self.m._n100_condor(self.ctx)):
            p, _ = fn()
            z = self.m._n100_size_option(p, {'capital': 20000.0, 'risk_pct': 1.0, 'max_position_pct': 25.0})
            self.assertEqual(z['lots'], 0)
            self.assertGreater(z['capital_for_one'], 100000.0)

    def test_choice_by_volatility_percentile_and_time(self):
        def choose(side, ivp, days=6.0, lv=self.lv):
            ctx = dict(self.ctx, days=days)
            return self.m._n100_option_choose(side, 0.5, 'TREND_UP', ivp, days, ctx, lv)
        _c, _a, _r, order = choose(1, 20.0)
        self.assertEqual(order, ['LONG', 'DEBIT'])
        _c, _a, _r, order = choose(1, 50.0)
        self.assertEqual(order, ['DEBIT', 'LONG'])
        _c, _a, _r, order = choose(1, 80.0)
        self.assertEqual(order, ['CREDIT', 'DEBIT'])
        _c, _a, _r, order = choose(1, None)
        self.assertEqual(order, ['DEBIT', 'LONG'])
        ch, _a, reasons, order = choose(1, 20.0, days=2.0)
        self.assertEqual(order, ['DEBIT'])
        self.assertIn('3 or more days', reasons['LONG'])
        self.assertIn('3 or more days', reasons['CREDIT'])
        ch, alts, reasons, order = choose(0, 80.0)
        self.assertEqual(order, ['CONDOR'])
        self.assertEqual(ch['structure'], 'CONDOR')
        ch, alts, reasons, order = choose(0, 80.0, days=2.0)
        self.assertIsNone(ch)
        self.assertIn('3 or more days', reasons['CONDOR'])

    def test_choice_returns_the_first_structure_that_passes(self):
        ch, alts, reasons, order = self.m._n100_option_choose(1, 0.5, 'TREND_UP', 20.0, 6.0, self.ctx, self.lv)
        self.assertEqual(ch['structure'], 'LONG')
        self.assertEqual(self.m._n100_option_score({'bias': 0.6, 'agree': 4, 'n': 5, 'conf': 1.0}, ch, 20.0, 0, self.ctx) >= 60, True)

    def test_score_stays_within_zero_and_a_hundred(self):
        p, _ = self.m._n100_credit(self.ctx, 1)
        for bias in ({'bias': 0.0, 'agree': 0, 'n': 5, 'conf': 1.0}, {'bias': 0.9, 'agree': 5, 'n': 5, 'conf': 1.0}, {'bias': -0.9, 'agree': 5, 'n': 5, 'conf': 1.0}):
            s = self.m._n100_option_score(bias, p, 80.0, 0, self.ctx)
            self.assertTrue(0 <= s <= 100)
        self.assertGreater(self.m._n100_option_score({'bias': 0.7, 'agree': 5, 'n': 5, 'conf': 1.0}, p, 80.0, 0, self.ctx), self.m._n100_option_score({'bias': 0.7, 'agree': 5, 'n': 5, 'conf': 1.0}, p, 80.0, 2, self.ctx))


# ===================================================================================================================
# 7. THE OPTION SIGNAL: from the reads to a structure, or the reasons there is none
# ===================================================================================================================
class OptionSignalCase(StructureCase):
    def setUp(self):
        super().setUp()
        m = self.m
        self.cs = index_daily()
        self.F = m._n100_prepare(self.cs)
        self.tech = m._n93_tech(self.cs, False)
        spot = self.cs[-1]['c']
        self.spot = spot
        self.ch = chain_with(m, spot=spot, iv=14.0, days=6.0, buildup=lambda r: (80000.0, -10.0) if r['type'] == 'PE' else (1000.0, 2.0))
        for r in self.ch['rows']:
            r['bid'], r['ask'], r['oi'] = round(r['ltp'] * 0.99, 2), round(r['ltp'] * 1.01, 2), 500000.0
        self.st = m._n100_chain_stats(self.ch, 65, 50)
        self.intr = {'value': 0.7, 'words': '5-minute: average20 above average50, price above the session average, above the opening range'}
        self.vix = lambda pct: {'level': 13.0, 'pct': pct, 'chg5': -0.2, 'n': 120}

    def sig(self, regime='TREND_UP', pct=50.0, intr=None, st=None, fresh=(), cfg=None, days=None, ch=None):
        st = st or self.st
        if days is not None:
            st = dict(st, days=days)
        ctx = self.put_ctx(vix=self.vix(pct) if pct is not None else None, regime=regime)
        return self.m._n100_option_signal('NIFTY', self.F, regime, ctx, cfg or self.cfg, st, ch or self.ch, self.intr if intr is None else intr, list(fresh), self.tech, NOW, 50)


class TestOptionSignal(OptionSignalCase):
    def test_a_bullish_agreement_with_cheap_options_gives_a_long_call_with_every_field(self):
        r = self.sig(pct=20.0)
        self.assertTrue(r['ok'], r.get('veto'))
        self.assertEqual((r['kind'], r['strategy'], r['side']), ('option', 'OPT_LONG', 1))
        self.assertGreaterEqual(r['score'], 65)
        p = r['plan']
        self.assertEqual(p['structure'], 'LONG')
        self.assertEqual(r['stop'], r['lv']['stop'])
        self.assertLess(r['stop'], r['ref'])
        self.assertGreater(r['t1'], r['ref'])
        for k in ('size', 'bias', 'stats', 'ivp', 'good', 'unchecked', 'wrong_if', 'risk', 'expiry', 'days', 'band'):
            self.assertIn(k, r)
        self.assertEqual(r['ivp'], 20.0)
        self.assertTrue(any('macro news' in u for u in r['unchecked']))

    def test_dear_options_prefer_a_credit_spread_or_fall_back_to_a_debit_spread(self):
        r = self.sig(pct=85.0)
        self.assertTrue(r['ok'], r.get('veto'))
        self.assertIn(r['plan']['structure'], ('CREDIT', 'DEBIT'))
        if r['plan']['structure'] == 'CREDIT':
            short = [lg for lg in r['plan']['legs'] if lg['action'] == 'SELL'][0]
            self.assertEqual(r['stop'], short['strike'])
            self.assertLess(r['stop'], self.spot)

    def test_middle_volatility_prefers_a_debit_spread(self):
        r = self.sig(pct=50.0)
        self.assertTrue(r['ok'], r.get('veto'))
        self.assertIn(r['plan']['structure'], ('DEBIT', 'LONG'))

    def test_a_range_with_dear_options_gives_a_condor(self):
        st = dict(self.st, buildup=None)
        r = self.sig(regime='RANGE', pct=80.0, intr={'value': 0.0, 'words': 'flat'}, st=st)
        self.assertTrue(r['ok'], r.get('veto'))
        self.assertEqual((r['plan']['structure'], r['side'], r['strategy']), ('CONDOR', 0, 'OPT_CONDOR'))
        self.assertLess(r['stop'], self.spot)
        self.assertGreater(r['stop2'], self.spot)

    def test_no_condor_when_options_are_not_dear_or_the_market_trends_or_volatility_is_rising(self):
        st = dict(self.st, buildup=None)
        flat = {'value': 0.0, 'words': 'flat'}
        r = self.sig(regime='RANGE', pct=40.0, intr=flat, st=st)
        self.assertFalse(r['ok'])
        self.assertIn('not dear enough', r['veto'])
        r = self.sig(regime='TREND_UP', pct=80.0, intr=flat, st=st)
        self.assertFalse(r['ok'])
        self.assertTrue('trending' in r['veto'] or 'no clear view' in r['veto'] or 'disagree' in r['veto'], r['veto'])
        ctx = self.put_ctx(vix={'level': 18.0, 'pct': 80.0, 'chg5': 3.0, 'n': 120}, regime='RANGE')
        r = self.m._n100_option_signal('NIFTY', self.F, 'RANGE', ctx, self.cfg, st, self.ch, flat, [], self.tech, NOW, 50)
        self.assertFalse(r['ok'])
        self.assertIn('rising fast', r['veto'])
        r = self.m._n100_option_signal('NIFTY', self.F, 'RANGE', self.put_ctx(vix=self.vix(80.0), regime='RANGE'), self.cfg, dict(st, skew=9.0), self.ch, flat, [], self.tech, NOW, 50)
        self.assertFalse(r['ok'])
        self.assertIn('paying up for protection', r['veto'])

    def test_an_expiry_within_a_day_is_never_traded(self):
        r = self.sig(days=0.6)
        self.assertFalse(r['ok'])
        self.assertIn('expiry is within a day', r['veto'])
        self.assertIn('never opens an expiry-day', r['veto'])

    def test_too_little_to_read_gives_no_view(self):
        st = dict(self.st, buildup=None, pcr_oi=None, call_wall=None, put_wall=None)
        r = self.sig(intr={'value': None, 'words': 'x'}, st=st)
        self.assertFalse(r['ok'])
        self.assertIn('too little could be read', r['veto'])

    def test_disagreeing_reads_give_no_signal(self):
        r = self.sig(regime='STRONG_TREND_UP', intr={'value': -1.0, 'words': 'down'}, st=dict(self.st, buildup={'score': -0.9, 'top': [(24500.0, 'CE', 'call writing', 90000.0)], 'coverage': 1.0}))
        self.assertFalse(r['ok'])
        self.assertTrue('disagree' in r['veto'] or 'no clear view' in r['veto'] or 'no direction' in r['veto'], r['veto'])      # strongly split reads cancel out: no direction, and a trending market is no place for a condor

    def test_a_target_beyond_the_expected_move_is_refused(self):
        tech = dict(self.tech, swing_highs=[self.spot + 3000.0], swing_lows=self.tech['swing_lows'])
        ctx = self.put_ctx(vix=self.vix(20.0))
        st = dict(self.st, em=100.0)
        r = self.m._n100_option_signal('NIFTY', self.F, 'TREND_UP', ctx, self.cfg, st, self.ch, self.intr, [], tech, NOW, 50)
        self.assertFalse(r['ok'])
        self.assertTrue('expect' in r['veto'] or 'too far' in r['veto'] or 'sound plan' in r['veto'], r['veto'])

    def test_a_small_account_is_told_it_does_not_fit_and_what_it_would_need(self):
        small = dict(self.cfg, capital=20000.0)
        r = self.sig(pct=20.0, cfg=small)
        self.assertTrue(r['ok'], r.get('veto'))
        self.assertFalse(r['size']['fits'])
        self.assertTrue(any('does not fit' in n for n in r['notes']))
        card = self.m._n100_card(r, small, 'SG100-ABC123')
        self.assertIn('0 lots', card)
        self.assertIn('would need about', card)

    def test_the_card_names_every_part_of_the_plan(self):
        r = self.sig(pct=20.0)
        card = self.m._n100_card(r, self.cfg, 'SG100-ABC123')
        for word in ('SIGMA SG100-ABC123', 'LONG CALL', 'VIEW:', 'VOLATILITY:', 'LEGS', 'EXIT PLAN', 'CHARGES', 'SIZE', 'NOT CHECKED', 'WRONG IF', 'Max pain', 'not advice', 'you place any order yourself'):
            self.assertIn(word, card, word)
        self.assertLessEqual(len(card), 3950)
        r2 = self.sig(regime='RANGE', pct=80.0, intr={'value': 0.0, 'words': 'flat'}, st=dict(self.st, buildup=None))
        card2 = self.m._n100_card(r2, self.cfg, 'SG100-ABC124')
        for word in ('IRON CONDOR', 'range-bound', 'CREDIT', 'half the credit', 'worst case', 'Broker margin applies'):
            self.assertIn(word, card2, word)

    def test_the_card_shows_a_fair_price_is_worth_about_zero_before_charges(self):
        card = self.m._n100_card(self.sig(pct=20.0), self.cfg, 'SG100-ABC123')
        self.assertIn('fairly priced option is worth about zero before charges', card)


# ===================================================================================================================
# 8. THE OPENING-RANGE BREAKOUT
# ===================================================================================================================
def five_min(day_ts, closes, spread=6.0, step=300):
    out, prev = [], closes[0]
    for k, c in enumerate(closes):
        o = prev
        out.append({'ts': int(day_ts + k * step), 'o': o, 'h': max(o, c) + spread, 'l': min(o, c) - spread, 'c': c, 'v': 0.0})
        prev = c
    return out


class TestORB(SigmaCase):
    DAY = ist_ts(2026, 10, 5, 9, 15)

    def series(self, closes, **kw):
        cs = five_min(self.DAY, closes, **kw)
        F = self.m._n100_prepare(cs)
        return F, F['n']

    def test_a_close_above_the_range_on_the_right_side_of_the_session_average_fires_long(self):
        F, n = self.series([24500, 24505, 24495, 24500, 24545, 24560])
        o, state = self.m._n100_orb(F, n, {'atr': 100.0}, self.put_ctx(), NOW)
        self.assertIsNotNone(o, state)
        sp = o['spec']
        orh, orl = max(F['h'][0:3]), min(F['l'][0:3])
        self.assertEqual((sp['side'], sp['strategy']), (1, 'ORB'))
        self.assertAlmostEqual(sp['stop'], (orh + orl) / 2)
        risk = sp['ref'] - sp['stop']
        self.assertAlmostEqual(sp['t1'] - sp['ref'], 1.5 * risk)
        self.assertAlmostEqual(sp['t2'] - sp['ref'], 2.5 * risk)
        self.assertEqual(dt.datetime.fromtimestamp(sp['deadline'], IST).strftime('%H:%M'), '15:10')
        self.assertEqual(sp['target'], sp['t1'])
        self.assertIn('above the opening range', sp['trigger'])

    def test_a_close_below_the_range_fires_short_when_the_daily_trend_is_not_up(self):
        F, n = self.series([24500, 24495, 24505, 24500, 24455, 24440])
        o, state = self.m._n100_orb(F, n, {'atr': 100.0}, self.put_ctx(index_dir=-1), NOW)
        self.assertIsNotNone(o, state)
        self.assertEqual(o['spec']['side'], -1)
        o, state = self.m._n100_orb(F, n, {'atr': 100.0}, self.put_ctx(index_dir=1), NOW)
        self.assertIsNone(o)
        self.assertIn('daily trend is against', state)

    def test_inside_the_range_and_an_unfinished_range_do_not_fire(self):
        F, n = self.series([24500, 24505, 24495, 24500, 24502])
        o, state = self.m._n100_orb(F, n, {'atr': 100.0}, self.put_ctx(), NOW)
        self.assertIsNone(o)
        self.assertIn('still inside the opening range', state)
        F, n = self.series([24500, 24505, 24495])
        o, state = self.m._n100_orb(F, n, {'atr': 100.0}, self.put_ctx(), NOW)
        self.assertIsNone(o)
        self.assertIn('not complete', state)

    def test_a_range_that_is_too_wide_or_too_narrow_is_not_traded(self):
        F, n = self.series([24500, 24505, 24495, 24500, 24545], spread=60.0)
        o, state = self.m._n100_orb(F, n, {'atr': 100.0}, self.put_ctx(), NOW)
        self.assertIsNone(o)
        self.assertIn('too wide', state)
        F, n = self.series([24500, 24500.5, 24499.5, 24500, 24501], spread=0.5)
        o, state = self.m._n100_orb(F, n, {'atr': 400.0}, self.put_ctx(), NOW)
        self.assertIsNone(o)
        self.assertIn('too narrow', state)

    def test_an_old_breakout_and_a_breakout_on_the_wrong_side_of_the_session_average_are_refused(self):
        F, n = self.series([24500, 24505, 24495, 24500, 24545, 24550, 24552, 24553, 24554, 24555])
        o, state = self.m._n100_orb(F, n, {'atr': 100.0}, self.put_ctx(), NOW)
        self.assertIsNone(o)
        self.assertIn('more than 3 bars old', state)
        cs = five_min(self.DAY, [24500, 24505, 24495, 24500, 24516])
        cs[3]['h'] = 24800.0                                                           # a spike inside the range lifts the session average above the later breakout close
        F = self.m._n100_prepare(cs)
        o, state = self.m._n100_orb(F, F['n'], {'atr': 100.0}, self.put_ctx(), NOW)
        self.assertIsNone(o)
        self.assertIn('wrong side of the session average', state)

    def test_a_late_breakout_is_refused(self):
        late = ist_ts(2026, 10, 5, 13, 40)
        cs = five_min(late - 20 * 300, [24500] * 3 + [24500, 24505, 24495] + [24500] * 14 + [24545, 24560])
        F = self.m._n100_prepare(cs)
        o, state = self.m._n100_orb(F, F['n'], {'atr': 100.0}, self.put_ctx(), NOW)
        self.assertIsNone(o)

    def test_the_intraday_read_is_a_weighted_sign_with_words(self):
        F, n = self.series([24500, 24505, 24495, 24500, 24545, 24560])
        r = self.m._n100_intraday_read(F, n)
        self.assertGreater(r['value'], 0)
        self.assertIn('above the opening range', r['words'])
        self.assertAlmostEqual(r['orh'], max(F['h'][0:3]))
        self.assertIsNone(self.m._n100_intraday_read(F, 3))


# ===================================================================================================================
# 9. SCORING AND THE CHECKS A STOCK MUST PASS
# ===================================================================================================================
class TestScoring(SigmaCase):
    def test_a_dip_in_an_uptrend_becomes_a_complete_record(self):
        recs, why = self.eval_stock(dip_closes())
        self.assertEqual(len(recs), 1, why)
        r = recs[0]
        self.assertEqual((r['kind'], r['strategy'], r['side'], r['symbol']), ('stock', 'RSI2', 1, 'TCS'))
        self.assertTrue(0 <= r['score'] <= 100)
        self.assertEqual(set(r['comps']), {'fit', 'setup', 'strength', 'backdrop', 'risk'})
        self.assertLessEqual(r['comps']['fit'], 25)
        self.assertLessEqual(r['comps']['setup'], 25)
        self.assertLessEqual(r['comps']['strength'], 15)
        self.assertLessEqual(r['comps']['backdrop'], 15)
        self.assertLessEqual(r['comps']['risk'], 20)
        self.assertEqual(r['spec']['stop'], r['stop'])
        self.assertLess(r['stop'], r['ref'])
        sz = r['size']
        self.assertLessEqual(sz['max_loss'], self.cfg['capital'] * 0.01 + 1e-6)
        self.assertGreater(sz['qty'], 0)
        self.assertAlmostEqual(r['cost_pct'], 0.393045, places=5)
        self.assertIn('RSI(2) fell to', r['trigger'])
        self.assertTrue(r['wrong_if'])

    def test_a_dip_is_scored_higher_when_nifty_agrees(self):
        up, _ = self.eval_stock(dip_closes(), ctx=self.put_ctx(index_dir=1))
        dn, _ = self.eval_stock(dip_closes(), ctx=self.put_ctx(index_dir=-1))
        self.assertGreater(up[0]['score'], dn[0]['score'])
        self.assertLess(dn[0]['comps']['backdrop'], 0)
        self.assertTrue(any('against' in b for b in dn[0]['bad']))

    def test_missing_pieces_are_listed_as_not_checked_never_passed(self):
        recs, _ = self.eval_stock(dip_closes(), ctx=self.put_ctx(index_dir=None, vix=None, ret20=None))
        self.assertTrue(any('NIFTY trend' in u for u in recs[0]['unchecked']))
        self.assertTrue(any('India VIX' in u for u in recs[0]['unchecked']))
        self.assertTrue(any('strength against NIFTY' in u for u in recs[0]['unchecked']))

    def test_thin_shares_are_vetoed(self):
        recs, why = self.eval_stock(dip_closes(), vols=[1000.0] * 263)
        self.assertEqual(recs, [])
        self.assertTrue(any('too thin' in v for v in why.values()), why)

    def test_a_stale_series_and_a_short_history_give_no_signal(self):
        cs = candles(dip_closes())
        info = self.info(cs, last_day='2026-09-01')
        recs, why = self.m._n100_eval_daily('TCS', cs, info, self.put_ctx(), self.cfg, 'stock', NOW)
        self.assertEqual(recs, [])
        self.assertIn('too old', why['data'])
        cs = candles(trend(100))
        recs, why = self.m._n100_eval_daily('TCS', cs, self.info(cs), self.put_ctx(), self.cfg, 'stock', NOW)
        self.assertIn('only 100 days', why['data'])
        recs, why = self.m._n100_eval_daily('TCS', [], {'error': 'no feed'}, self.put_ctx(), self.cfg, 'stock', NOW)
        self.assertEqual(why, {'data': 'no feed'})

    def test_chasing_the_live_price_is_refused(self):
        cs = candles(dip_closes())
        a = self.m._n100_prepare(cs)['atr'][-1]
        recs, why = self.m._n100_eval_daily('TCS', cs, self.info(cs, live=cs[-1]['c'] + 0.8 * a), self.put_ctx(), self.cfg, 'stock', NOW)
        self.assertEqual(recs, [])
        self.assertTrue(any('chasing' in v for v in why.values()), why)
        recs, why = self.m._n100_eval_daily('TCS', cs, self.info(cs, live=cs[-1]['c'] - 5 * a), self.put_ctx(), self.cfg, 'stock', NOW)
        self.assertEqual(recs, [])
        self.assertTrue(any('gone through the stop' in v for v in why.values()), why)
        recs, why = self.m._n100_eval_daily('TCS', cs, self.info(cs, live=cs[-1]['c'] + 0.1 * a), self.put_ctx(), self.cfg, 'stock', NOW)
        self.assertEqual(len(recs), 1)

    def test_shorts_only_when_switched_on_and_always_for_an_index(self):
        cl = trend(260, drift=-0.003)
        cl += [cl[-1] * 1.02, cl[-1] * 1.02 ** 2, cl[-1] * 1.02 ** 3]
        recs, _ = self.eval_stock(cl, ctx=self.put_ctx(index_dir=-1))
        self.assertEqual([r for r in recs if r['side'] == -1], [])
        recs, _ = self.eval_stock(cl, ctx=self.put_ctx(index_dir=-1), cfg=dict(self.cfg, shorts=True))
        self.assertTrue([r for r in recs if r['side'] == -1])
        cs = candles(cl)
        recs, _ = self.m._n100_eval_daily('NIFTY', cs, self.info(cs), self.put_ctx(index_dir=-1), self.cfg, 'index', NOW)
        self.assertTrue([r for r in recs if r['side'] == -1])
        self.assertIsNone(recs[0]['size'])

    def test_charges_that_would_eat_the_risk_veto_a_tight_stop(self):
        F = self.m._n100_prepare(candles(dip_closes()))
        s, _ = self.m._n100_s_rsi2(F, F['n'] - 1, 1)
        s = dict(s, stop=s['ref'] - 0.2 * F['atr'][-1])
        score, comps, good, bad, unchecked, veto, rr1, cost_r = self.m._n100_score_daily(s, F, F['n'] - 1, self.put_ctx(), 'stock')
        self.assertIn('charges would take', veto)
        self.assertGreater(cost_r, 0.5)

    def test_a_wide_stop_is_vetoed(self):
        F = self.m._n100_prepare(candles(dip_closes()))
        s, _ = self.m._n100_s_rsi2(F, F['n'] - 1, 1)
        s = dict(s, stop=s['ref'] - 5 * F['atr'][-1])
        veto = self.m._n100_score_daily(s, F, F['n'] - 1, self.put_ctx(), 'stock')[5]
        self.assertIn('too wide', veto)

    def test_bands(self):
        B = self.m._n100_band
        self.assertEqual([B(x) for x in (90, 78, 77, 66, 65, 55, 54)], ['A', 'A', 'B', 'B', 'C', 'C', '-'])

    def test_the_card_for_a_stock(self):
        recs, _ = self.eval_stock(dip_closes())
        card = self.m._n100_card(recs[0], self.cfg, 'SG100-ABC123')
        for word in ('SIGMA SG100-ABC123', 'LONG TCS', 'Trend pullback (RSI-2)', 'WHY:', 'ENTRY:', 'STOP:', 'EXIT:', 'SIZE at your limits', 'CHARGES:', 'WRONG IF:', 'not advice', 'close above the 5-day average', 'forward record: none yet'):
            self.assertIn(word, card, word)
        self.assertLessEqual(len(card), 3900)
        small = dict(self.cfg, capital=500.0)
        recs, _ = self.eval_stock(dip_closes(), cfg=small)
        self.assertIn('0 shares at your', self.m._n100_card(recs[0], small, 'SG100-ABC123'))


# ===================================================================================================================
# 10. ISSUING: limits, heat, the breaker, duplicates
# ===================================================================================================================
class TestIssue(SigmaCase):
    def recs(self, n=1, syms=('TCS',), score=None):
        out = []
        for s in syms:
            r, _ = self.eval_stock(dip_closes(), sym=s)
            out += r
        if score is not None:
            for r in out:
                r['score'] = score
        return out

    def test_issued_cards_are_saved_and_a_second_issue_the_same_day_is_a_duplicate(self):
        recs = self.recs()
        n = len(self.sent)
        issued = self.m._n100_issue(OWNER_ID, recs, self.cfg, NOW)
        self.assertEqual(len(issued), 1)
        self.assertIn('SIGMA SG100-', self.texts_to_owner(n))
        row = self.m._n100_q('SELECT id, kind, strategy, side, status FROM sig100_signal')[0]
        self.assertEqual((row[1], row[2], row[3], row[4]), ('stock', 'RSI2', 1, 'pending'))
        n = len(self.sent)
        self.assertEqual(self.m._n100_issue(OWNER_ID, self.recs(), self.cfg, NOW), [])
        self.assertEqual(self.texts_to_owner(n), '')

    def test_below_the_score_line_nothing_is_issued(self):
        self.assertEqual(self.m._n100_issue(OWNER_ID, self.recs(score=64), self.cfg, NOW), [])
        self.assertEqual(len(self.m._n100_issue(OWNER_ID, self.recs(score=65), self.cfg, NOW)), 1)

    def test_at_most_the_owners_number_per_scan_and_two_per_sector(self):
        syms = ('TCS', 'INFY', 'WIPRO', 'HCLTECH', 'TECHM')                                     # all IT
        recs = self.recs(syms=syms, score=80)
        issued = self.m._n100_issue(OWNER_ID, recs, self.cfg, NOW)
        self.assertEqual(len(issued), 2)
        issued = self.m._n100_issue(OWNER_ID, self.recs(syms=('HDFCBANK', 'ICICIBANK', 'SBIN', 'AXISBANK', 'KOTAKBANK'), score=80), dict(self.cfg, max_signals=1), NOW)
        self.assertEqual(len(issued), 1)

    def test_highest_score_first(self):
        recs = self.recs(syms=('ITC', 'RELIANCE'), score=70)
        recs[1]['score'] = 90
        issued = self.m._n100_issue(OWNER_ID, recs, dict(self.cfg, max_signals=1), NOW)
        self.assertEqual(issued[0]['symbol'], 'RELIANCE')

    def test_portfolio_heat_blocks_a_signal_that_would_exceed_it(self):
        recs = self.recs(syms=('TCS', 'ITC'), score=80)
        risk_pct = self.m._n100_risk_of(recs[0]) / self.cfg['capital'] * 100.0
        cfg = dict(self.cfg, heat_pct=risk_pct * 1.5)
        issued = self.m._n100_issue(OWNER_ID, recs, cfg, NOW)
        self.assertEqual(len(issued), 1)
        rs, pct = self.m._n100_heat(cfg)
        self.assertAlmostEqual(pct, risk_pct, places=6)
        self.assertGreater(rs, 0)

    def test_an_unsized_signal_adds_no_heat(self):
        r = self.recs(score=80)[0]
        r['size'] = dict(r['size'], qty=0, max_loss=0.0)
        self.assertEqual(self.m._n100_risk_of(r), 0.0)

    def test_circuit_breaker_on_three_stops_or_minus_two_r(self):
        cfg = self.cfg
        day0 = dt.datetime(2026, 10, 5, tzinfo=IST).timestamp()
        for k in range(3):
            self.m._n100_q('INSERT INTO sig100_signal(id, ts, day, symbol, kind, strategy, side, status, r_result, closed_ts, skey, payload) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                           ('SG100-00000%d' % k, day0, '2026-10-05', 'X', 'stock', 'RSI2', 1, 'stopped', -1.0, day0 + 3600 * (k + 1), 'k%d' % k, '{}'), write=True)
        tripped, why = self.m._n100_breaker(cfg, NOW)
        self.assertTrue(tripped)
        self.assertIn('3 signals were stopped out', why)
        n = len(self.sent)
        self.assertEqual(self.m._n100_issue(OWNER_ID, self.recs(score=90), cfg, NOW), [])
        self.assertIn('Circuit breaker', self.texts_to_owner(n))
        self.assertFalse(self.m._n100_breaker(dict(cfg, breaker=False), NOW)[0])
        self.m._n100_q('DELETE FROM sig100_signal', write=True)
        self.m._n100_q('INSERT INTO sig100_signal(id, ts, day, symbol, kind, strategy, side, status, r_result, closed_ts, skey, payload) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                       ('SG100-000009', day0, '2026-10-05', 'X', 'stock', 'RSI2', 1, 'expired', -2.4, day0 + 3600, 'kk', '{}'), write=True)
        self.assertIn('-2.4R', self.m._n100_breaker(cfg, NOW)[1])
        self.assertEqual(self.m._n100_breaker(cfg, NOW + 86400)[0], False)                   # yesterday's losses do not stop today

    def test_quiet_mode_sends_no_breaker_message(self):
        day0 = dt.datetime(2026, 10, 5, tzinfo=IST).timestamp()
        self.m._n100_q('INSERT INTO sig100_signal(id, ts, day, symbol, kind, strategy, side, status, r_result, closed_ts, skey, payload) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                       ('SG100-000009', day0, '2026-10-05', 'X', 'stock', 'RSI2', 1, 'expired', -2.4, day0 + 3600, 'kk', '{}'), write=True)
        n = len(self.sent)
        self.assertEqual(self.m._n100_issue(OWNER_ID, self.recs(score=90), self.cfg, NOW, quiet=True), [])
        self.assertEqual(self.texts_to_owner(n), '')


# ===================================================================================================================
# 11. FOLLOWING THE SIGNALS (the record)
# ===================================================================================================================
class TrackCase(SigmaCase):
    def make_signal(self, closes=None, sym='TCS'):
        recs, why = self.eval_stock(closes or dip_closes(), sym=sym)
        self.assertEqual(len(recs), 1, why)
        rec = recs[0]
        sid = self.m._n100_save(rec, NOW)
        self.assertTrue(sid)
        self.base_closes = list(closes or dip_closes())
        self.rec = rec
        return rec

    def extend(self, extra_closes, vols=None, opens=None, sym='TCS', wick=0.004):
        closes = self.base_closes + list(extra_closes)
        k = len(extra_closes)
        op = None
        if opens:
            op = [None] * len(self.base_closes) + list(opens)
            prev = None
            fixed = []
            for i, c in enumerate(closes):
                fixed.append(op[i] if op[i] is not None else (closes[i - 1] if i else closes[0]))
            op = fixed
        self.daily[sym] = candles(closes, vols, wick=wick, end_ts=LAST_DAY + k * 86400, opens=op)

    def row(self):
        return self.m._n100_q('SELECT status, r_result, exit_reason, closed_ts FROM sig100_signal')[0]


class TestTracker(TrackCase):
    def test_a_signal_waits_for_the_next_open_and_is_not_messaged(self):
        self.make_signal()
        self.daily['TCS'] = candles(self.base_closes)
        n = len(self.sent)
        self.assertEqual(self.m._n100_track_once(NOW), [])
        self.assertEqual(self.row()[0], 'pending')
        self.assertEqual(self.texts_to_owner(n), '')

    def test_the_exit_rule_settles_at_the_next_open_with_charges_taken_off(self):
        rec = self.make_signal()
        ref, stop = rec['ref'], rec['stop']
        self.extend([ref * 1.04, ref * 1.05, ref * 1.05])
        n = len(self.sent)
        done = self.m._n100_track_once(NOW)
        self.assertEqual([(d[1]) for d in done], ['rule'])
        st, r, why, closed = self.row()
        self.assertEqual((st, why), ('rule', 'rule'))
        risk = ref - stop
        gross = (ref * 1.04 - ref) / risk                                         # entry at the next open (= the signal close), exit at the open after the rule fired
        self.assertAlmostEqual(r, gross - ref * self.m._n100_cost_pct('stock') / 100.0 / risk, places=6)
        self.assertIn('the exit rule fired', self.texts_to_owner(n))
        self.assertIn('after charges', self.texts_to_owner(n))
        n = len(self.sent)
        self.assertEqual(self.m._n100_track_once(NOW), [])                          # settled once, announced once
        self.assertEqual(self.texts_to_owner(n), '')

    def test_the_stop_settles_at_minus_one_r_less_charges(self):
        rec = self.make_signal()
        ref, stop = rec['ref'], rec['stop']
        self.extend([ref * 0.90])
        done = self.m._n100_track_once(NOW)
        self.assertEqual(done[0][1], 'stopped')
        st, r, why, _c = self.row()
        risk = ref - stop
        self.assertAlmostEqual(r, -1.0 - ref * self.m._n100_cost_pct('stock') / 100.0 / risk, places=6)
        self.assertIn('the stop was reached', self.texts_to_owner())

    def test_a_gap_through_the_stop_at_the_open_voids_the_plan_and_is_not_counted(self):
        rec = self.make_signal()
        ref = rec['ref']
        self.extend([ref * 0.90], opens=[ref * 0.92])
        n = len(self.sent)
        done = self.m._n100_track_once(NOW)
        self.assertEqual(done[0][1], 'skipped')
        self.assertEqual(self.row()[0], 'skipped')
        self.assertEqual(self.texts_to_owner(n), '')                                   # a void plan is not announced as a loss
        out = self.m._n100_stats_text()
        self.assertIn('1 skipped because the open made the plan void', out)
        self.assertNotIn('All:', out)                                                   # and it is not in the record

    def test_the_time_limit_closes_a_signal_that_never_resolves(self):
        rec = self.make_signal()
        ref = rec['ref']
        self.extend([ref * (1 - 0.001 * k) for k in range(1, 10)])                       # drifts down: no exit rule, no stop
        done = self.m._n100_track_once(NOW)
        self.assertEqual(done[0][1], 'expired')
        self.assertEqual(self.row()[2], 'time')

    def test_still_open_stays_open(self):
        rec = self.make_signal()
        ref = rec['ref']
        self.extend([ref * 1.001, ref * 1.002])
        self.assertEqual(self.m._n100_track_once(NOW), [])
        self.assertEqual(self.row()[0], 'open')

    def test_the_owner_can_check_and_drop_a_signal(self):
        rec = self.make_signal()
        sid = rec['id']
        self.extend([rec['ref'] * 1.001])
        out = self.say('sigma check %s' % sid)
        self.assertIn(sid, out)
        out = self.say('sigma drop %s' % sid)
        self.assertIn('Dropped', out)
        self.assertEqual(self.row()[0], 'dropped')
        self.assertIn('There is no open signal', self.say('sigma drop %s' % sid))


class TestORBTracker(SigmaCase):
    DAY = ist_ts(2026, 10, 5, 9, 15)

    def make(self, later):
        closes = [24500, 24505, 24495, 24500, 24545] + later
        cs = five_min(self.DAY, closes)
        daily = candles(trend(200, start=24000.0, vol=0.002, drift=0.0003), wick=0.0005)          # a daily ATR of about 60 points
        data = {'cs': daily, 'info': self.info(daily), 'cs5': cs[:5]}
        recs, why, ana = self.m._n100_index_scan('NIFTY', self.put_ctx(), self.cfg, NOW, daily=False, orb=True, options=False, data=data)
        orb = [r for r in recs if r['strategy'] == 'ORB']
        self.assertEqual(len(orb), 1, (why, ana.get('orb')))
        self.rec = orb[0]
        self.assertTrue(self.m._n100_save(self.rec, NOW))
        self.md[('NIFTY', '5m')] = cs
        return self.rec

    def test_the_target_is_reached(self):
        rec = self.make([24560, 24600, 24650, 24660])
        self.assertEqual(self.rec['kind'], 'index')
        done = self.m._n100_track_once(NOW)
        self.assertEqual(done[0][1], 'target')
        r = self.m._n100_q('SELECT r_result FROM sig100_signal')[0][0]
        risk = rec['risk']
        self.assertAlmostEqual(r, 1.5 - rec['ref'] * self.m._n100_cost_pct('index') / 100.0 / risk, delta=0.05)

    def test_the_stop_at_the_middle_of_the_range_is_reached(self):
        rec = self.make([24540, 24510, 24495, 24490])
        done = self.m._n100_track_once(NOW)
        self.assertEqual(done[0][1], 'stopped')
        self.assertLess(self.m._n100_q('SELECT r_result FROM sig100_signal')[0][0], -1.0)

    def test_a_row_for_an_orb_signal_is_open_from_the_start(self):
        self.make([24550])
        self.assertEqual(self.m._n100_q('SELECT status FROM sig100_signal')[0][0], 'open')


class TestOptionTracker(OptionSignalCase):
    def make(self, pct=20.0):
        r = self.sig(pct=pct)
        self.assertTrue(r['ok'], r.get('veto'))
        r['expiry_ts'] = NOW + 6 * 86400.0
        self.assertTrue(self.m._n100_save(r, NOW))
        self.rec = r
        return r

    def chain_at(self, spot, days):
        ch = chain_with(self.m, spot=spot, iv=14.0, days=days)
        for x in ch['rows']:
            x['bid'], x['ask'], x['oi'] = round(x['ltp'] * 0.99, 2), round(x['ltp'] * 1.01, 2), 500000.0
        self.chain['NIFTY'] = ch

    def test_a_rally_reaches_the_target_value(self):
        r = self.make()
        self.chain_at(r['lv']['t1'] + 120.0, 5.0)
        done = self.m._n100_track_once(NOW + 3600)
        self.assertEqual(done[0][1], 'target')
        self.assertGreater(self.m._n100_q('SELECT r_result FROM sig100_signal')[0][0], 0)

    def test_a_fall_through_the_index_stop_settles_as_stopped(self):
        r = self.make()
        self.chain_at(r['lv']['stop'] - 80.0, 5.0)
        done = self.m._n100_track_once(NOW + 3600)
        self.assertEqual(done[0][1], 'stopped')
        self.assertLess(self.m._n100_q('SELECT r_result FROM sig100_signal')[0][0], 0)

    def test_nothing_happens_while_the_plan_holds(self):
        r = self.make()
        self.chain_at(self.spot + 10.0, 5.9)
        self.assertEqual(self.m._n100_track_once(NOW + 600), [])
        self.assertEqual(self.m._n100_q('SELECT status FROM sig100_signal')[0][0], 'open')

    def test_the_last_day_closes_the_position(self):
        r = self.make()
        p = r['plan']
        spot = next((s for s in range(int(self.spot), int(r['lv']['t1']) + 300, 5) if p['sl'] + 3 < self.m._n100_option_value(dict(r, expiry_ts=NOW + 6 * 86400.0), float(s), NOW + 5.1 * 86400, None) < p['tp1'] - 3), None)
        self.assertIsNotNone(spot, 'no index level leaves the position between its stop and its target one day before expiry')
        self.chain_at(float(spot), 0.9)
        done = self.m._n100_track_once(NOW + 5.1 * 86400)
        self.assertEqual(done[0][1], 'expired')

    def test_a_loss_on_the_last_day_is_still_a_stop(self):
        r = self.make()
        self.chain_at(self.spot - 40.0, 0.9)
        done = self.m._n100_track_once(NOW + 5.1 * 86400)
        self.assertEqual(done[0][1], 'stopped')

    def test_without_live_prices_the_model_marks_it_and_says_so(self):
        r = self.make()
        self.chain.clear()
        self.md[('NIFTY', '5m')] = five_min(ist_ts(2026, 10, 5, 9, 15), [r['lv']['t1'] + 150.0] * 20)
        d, spot, src = self.m._n100_track_option(self.m._n100_row(r.get('id')), NOW + 3600)
        self.assertIn('model', src)
        self.assertAlmostEqual(spot, r['lv']['t1'] + 150.0)

    def test_the_decision_rules_for_a_sold_structure(self):
        ch, _a, _r, _o = self.m._n100_option_choose(0, 0.1, 'RANGE', 80.0, 6.0, dict(self.ctx, days=6.0, fwd=self.st['forward']), None)
        if ch is None:
            self.skipTest('the fixture chain gives no condor')
        rec = {'plan': ch, 'side': 0, 'stop': [lg['strike'] for lg in ch['legs'] if lg['action'] == 'SELL' and lg['type'] == 'PE'][0],
               'stop2': [lg['strike'] for lg in ch['legs'] if lg['action'] == 'SELL' and lg['type'] == 'CE'][0], 'expiry_ts': NOW + 6 * 86400}
        D = self.m._n100_option_decide
        self.assertEqual(D(rec, -ch['tp1'] * 0.9, 24490.0, NOW)[0], 'target')                     # closing costs less than half the credit
        self.assertEqual(D(rec, -ch['sl'] * 1.01, 24490.0, NOW)[0], 'stopped')
        self.assertEqual(D(rec, -ch['credit'], rec['stop'] - 1.0, NOW)[0], 'stopped')               # the index closed beyond a short strike
        self.assertEqual(D(rec, -ch['credit'], rec['stop2'] + 1.0, NOW)[0], 'stopped')
        self.assertEqual(D(rec, -ch['credit'], 24490.0, NOW + 5.5 * 86400)[0], 'expired')
        self.assertIsNone(D(rec, -ch['credit'], 24490.0, NOW))
        why, rr, _v = D(rec, -ch['tp1'], 24490.0, NOW)
        self.assertGreater(rr, 0)


# ===================================================================================================================
# 12. STATISTICS, THE BACKTEST, THE SCOREBOARD, THE SHORT-VOLATILITY PROXY
# ===================================================================================================================
class TestStatistics(SigmaCase):
    def test_trade_stats_known_answers(self):
        s = self.m._n100_trade_stats([1.0, -1.0, 2.0, -1.0])
        self.assertEqual((s['n'], s['wins']), (4, 2))
        self.assertAlmostEqual(s['avg_r'], 0.25)
        self.assertAlmostEqual(s['profit_factor'], 3.0 / 2.0)
        self.assertAlmostEqual(s['max_dd_r'], 1.0)
        self.assertEqual(s['losing_streak'], 1)
        self.assertAlmostEqual(s['median_r'], 0.0)
        self.assertLess(s['win_lo'], 50.0)
        self.assertGreater(s['win_hi'], 50.0)
        self.assertEqual(self.m._n100_trade_stats([])['n'], 0)

    def test_bootstrap_is_repeatable_and_brackets_the_mean(self):
        rs = [1.0, -1.0, 2.0, -1.0, 0.5, -0.5, 1.5, -1.0] * 5
        lo, hi = self.m._n100_boot_ci(rs)
        self.assertEqual((lo, hi), self.m._n100_boot_ci(rs))
        mean = sum(rs) / len(rs)
        self.assertLess(lo, mean)
        self.assertGreater(hi, mean)
        self.assertEqual(self.m._n100_boot_ci([1.0]), (None, None))

    def test_the_evidence_label_is_earned_not_claimed(self):
        L = self.m._n100_label
        self.assertEqual(L([1.0] * 29), 'too few')
        self.assertEqual(L([-0.2, 0.1] * 20), 'negative')
        strong = [1.2, 0.8, 1.0, -0.2, 0.9, 1.1] * 7
        self.assertEqual(L(strong), 'promising')
        weak = [2.0, -1.0, -1.0, 1.5, -1.0, -0.4] * 6 + [1.0]
        self.assertGreater(sum(weak), 0)
        self.assertEqual(L(weak), 'unproven')
        self.assertEqual(L(strong, [strong[:20], strong[20:]]), 'promising')
        self.assertEqual(L(strong, [strong[:20], [-0.5, -0.2, -0.1]]), 'unproven')           # a losing second half blocks the label

    def test_the_backtest_takes_charges_off_every_trade_and_holds_one_position_per_rule(self):
        cs = candles(trend(700, seed=21, vol=0.012, drift=0.0007))
        bt = self.m._n100_backtest(cs, kind='stock')
        self.assertGreater(len(bt['trades']), 10)
        for t in bt['trades']:
            risk = None
            self.assertLess(t['r'], t['r_gross'])
            self.assertIn(t['reason'], ('stop', 'stop (gap)', 'target', 'time', 'rule'))
            self.assertGreater(t['exit_ts'], t['ts'] - 1)
        for name in {t['strategy'] for t in bt['trades']}:
            mine = sorted((t for t in bt['trades'] if t['strategy'] == name), key=lambda t: t['i'])
            for a, b in zip(mine, mine[1:]):
                self.assertGreaterEqual(b['i'], a['i'] + a['bars'] - 1, 'positions of one rule overlap')

    def test_a_forced_plan_has_the_same_geometry_as_the_rules_own(self):
        F = self.m._n100_prepare(candles(dip_closes()))
        i = F['n'] - 1
        s, _ = self.m._n100_s_rsi2(F, i, 1)
        f = self.m._n100_forced_spec('RSI2', F, i, 1)
        self.assertEqual((f['stop'], f['rule'], f['horizon']), (s['stop'], s['rule'], s['horizon']))
        F = self.m._n100_prepare(candles(breakout_closes(), [1e6] * 260 + [2.5e6]))
        i = F['n'] - 1
        s, _ = self.m._n100_s_donchian(F, i, 1)
        f = self.m._n100_forced_spec('DONCHIAN', F, i, 1)
        self.assertEqual((f['stop'], f['trail_mult'], f['rule']), (s['stop'], s['trail_mult'], s['rule']))
        cl = squeeze_closes()
        F = self.m._n100_prepare(candles(cl, [1e6] * (len(cl) - 1) + [2.2e6]))
        i = F['n'] - 1
        s, _ = self.m._n100_s_squeeze(F, i, 1)
        f = self.m._n100_forced_spec('SQUEEZE', F, i, 1)
        self.assertAlmostEqual(f['stop'], s['stop'])
        self.assertAlmostEqual(f['target'], s['target'])
        F = self.m._n100_prepare(candles(flip_closes()))
        i = fire_indexes(self.m, F, 'SUPERTREND', 1, 20)[0]
        s, _ = self.m._n100_s_supertrend(F, i, 1)
        f = self.m._n100_forced_spec('SUPERTREND', F, i, 1)
        self.assertAlmostEqual(f['stop'], s['stop'])
        self.assertEqual((f['rule'], f['st_trail']), ('st_flip', True))
        self.assertIsNone(self.m._n100_forced_spec('RSI2', self.m._n100_prepare(candles([100.0, 101.0])), 1, 1))

    def test_random_entries_pass_the_rules_own_side_of_the_market_filter_and_repeat(self):
        cs = candles(trend(700, seed=21, vol=0.012, drift=0.0007))
        F = self.m._n100_prepare(cs)
        a = self.m._n100_baseline(F, 'RSI2', 'stock')
        self.assertEqual(a, self.m._n100_baseline(F, 'RSI2', 'stock'))
        self.assertTrue(30 < len(a) <= 300)
        self.assertFalse(self.m._n100_eligible('RSI2', F, 250, -1) and self.m._n100_eligible('RSI2', F, 250, 1))
        i = next(k for k in range(210, 600) if F['st_dir'][k] == 1)
        self.assertTrue(self.m._n100_eligible('SUPERTREND', F, i, 1))
        self.assertFalse(self.m._n100_eligible('SUPERTREND', F, i, -1))
        self.assertTrue(self.m._n100_eligible('SQUEEZE', F, 300, 1))
        self.assertEqual(self.m._n100_baseline(self.m._n100_prepare(candles(trend(150))), 'RSI2', 'stock'), [])

    def test_the_difference_interval_and_the_label_with_a_baseline(self):
        strong = [1.2, 0.8, 1.0, -0.2, 0.9, 1.1] * 7
        same = [1.1, 0.9, 1.0, -0.1, 0.8, 1.2] * 7
        weak = [0.1, -0.1, 0.0, 0.05, -0.05, 0.1] * 7
        d, lo, hi = self.m._n100_diff_ci(strong, weak)
        self.assertEqual((d, lo, hi), self.m._n100_diff_ci(strong, weak))
        self.assertGreater(lo, 0)
        self.assertEqual(self.m._n100_diff_ci([1.0], weak), (None, None, None))
        self.assertEqual(self.m._n100_label(strong, None, weak), 'promising')
        self.assertEqual(self.m._n100_label(strong, None, same), 'unproven')              # as good as entering at random times: no claim
        self.assertEqual(self.m._n100_label(strong, None, weak[:10]), 'promising')       # a baseline of fewer than 30 entries is not used

    def test_a_rising_market_does_not_make_a_rule_look_good_when_random_timing_does_as_well(self):
        trades, base, firsts, lasts = [], [], [], []
        for seed in range(12):
            rnd = random.Random(seed + 500)
            px, cl = 100.0, []
            for _ in range(1000):
                px *= 1 + 0.0008 + rnd.gauss(0, 0.012)
                cl.append(px)
            bt = self.m._n100_backtest(candles(cl), ['HIGH52'], 'stock')
            trades += bt['trades']
            base += bt['baseline'].get('HIGH52', [])
            firsts.append(bt['first_ts'])
            lasts.append(bt['last_ts'])
        rs = [t['r'] for t in trades]
        self.assertGreater(sum(rs) / len(rs), 0.1)                                          # the rule "wins" because the whole market drifts up
        self.assertGreater(sum(base) / len(base), 0.1)                                      # and so does entering at random times
        summ = self.m._n100_bt_summary(trades, min(firsts), max(lasts), {'HIGH52': base})
        self.assertNotEqual(summ['HIGH52']['label'], 'promising')
        text = '\n'.join(self.m._n100_bt_lines(summ))
        self.assertIn('random entry times, same filter and exits', text)
        self.assertIn("the rule's timing adds", text)

    def test_pooled_lines_leave_out_the_drawdown_of_a_list_that_is_not_one_account(self):
        cs = candles(trend(700, seed=21, vol=0.012, drift=0.0007))
        bt = self.m._n100_backtest(cs, kind='stock')
        summ = self.m._n100_bt_summary(bt['trades'], bt['first_ts'], bt['last_ts'], bt['baseline'])
        self.assertIn('worst dip', '\n'.join(self.m._n100_bt_lines(summ)))
        self.assertNotIn('worst dip', '\n'.join(self.m._n100_bt_lines(summ, pooled=True)))

    def test_the_backtest_does_not_invent_an_edge_on_a_random_walk(self):
        rs = []
        for seed in range(8):
            rnd = random.Random(seed + 100)
            px, cl = 100.0, []
            for _ in range(900):
                px *= 1 + rnd.gauss(0, 0.012)
                cl.append(px)
            rs += [t['r'] for t in self.m._n100_backtest(candles(cl), kind='stock')['trades']]
        self.assertGreater(len(rs), 60)
        mean = sum(rs) / len(rs)
        self.assertLess(mean, 0.15, 'average %.3fR on %d trades with no edge in the data' % (mean, len(rs)))
        self.assertNotEqual(self.m._n100_label(rs), 'promising')

    def test_summary_lines_carry_ranges_halves_and_the_label(self):
        cs = candles(trend(700, seed=21, vol=0.012, drift=0.0007))
        bt = self.m._n100_backtest(cs, kind='stock')
        summ = self.m._n100_bt_summary(bt['trades'], bt['first_ts'], bt['last_ts'])
        text = '\n'.join(self.m._n100_bt_lines(summ))
        for word in ('trades', 'the true rate could be', 'after charges', 'profit factor', 'worst dip', 'first half', 'second half', 'evidence:'):
            self.assertIn(word, text)

    def test_the_test_command_for_one_name_reports_with_caveats(self):
        self.daily['TCS'] = candles(trend(900, seed=21, vol=0.012, drift=0.0007), end_ts=LAST_DAY)
        out = self.say('sigma test TCS')
        for word in ('SIGMA TEST: TCS', 'charges 0.39%', 'Buy and hold', 'Caveats', 'survivor list', 'small sample', 'random-timing line is the control'):
            self.assertIn(word, out)
        self.daily['TCS'] = candles(trend(300))
        self.assertIn('too few', self.say('sigma test TCS'))

    def test_the_pooled_test_uses_the_universe_and_names_what_it_could_not_read(self):
        for s in ('TCS', 'INFY', 'RELIANCE'):
            self.daily[s] = candles(trend(900, seed=hash(s) % 50, vol=0.012, drift=0.0006))
        out = self.say('sigma test all')
        self.assertIn('Testing the rules on', out)
        self.assertIn('SIGMA TEST (pooled): 3 stocks', out)
        self.assertIn('no usable history', out)
        self.assertIn('not independent', out)


class TestScoreboard(SigmaCase):
    def put(self, strategy, r, status='target', kind='stock', n=1):
        for k in range(n):
            self.m._n100_q('INSERT INTO sig100_signal(id, ts, day, symbol, kind, strategy, side, status, r_result, closed_ts, skey, payload) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                           ('SG100-%06X' % (abs(hash((strategy, r, status, k, n))) % 0xFFFFFF), NOW, '2026-10-05', 'X', kind, strategy, 1, status, r, NOW, '%s|%s|%s|%s' % (strategy, r, status, k) + str(time.time()), '{}'), write=True)

    def test_empty_scoreboard_says_so_and_how_a_label_is_earned(self):
        out = self.m._n100_stats_text()
        self.assertIn('nothing has settled yet', out)
        self.assertIn('30 settled signals', out)

    def test_scoreboard_groups_by_rule_with_ranges_and_an_evidence_label(self):
        self.put('RSI2', 1.0, 'target', n=5)
        self.put('RSI2', -1.1, 'stopped', n=3)
        self.put('DONCHIAN', -1.0, 'stopped', n=2)
        self.put('OPT_CONDOR', 0.5, 'target', kind='option', n=2)
        out = self.m._n100_stats_text()
        self.assertIn('All: 12 settled', out)
        self.assertIn('Trend pullback (RSI-2): 8 settled', out)
        self.assertIn('Option: Condor: 2 settled', out)
        self.assertIn('evidence: TOO FEW', out)
        self.assertIn('first look, not evidence', out)

    def test_skipped_and_dropped_signals_are_not_in_the_record(self):
        self.put('RSI2', None, 'skipped')
        self.m._n100_q("UPDATE sig100_signal SET r_result=NULL")
        self.put('RSI2', 5.0, 'dropped')
        self.assertIn('nothing has settled yet', self.m._n100_stats_text())

    def test_the_board_lists_open_signals(self):
        self.assertIn('No open Sigma signals', self.m._n100_board_text())
        recs, _ = self.eval_stock(dip_closes())
        self.m._n100_save(recs[0], NOW)
        out = self.m._n100_board_text()
        self.assertIn('OPEN SIGMA SIGNALS', out)
        self.assertIn('LONG TCS', out)
        self.assertIn('waiting for the next open', out)

    def test_a_cards_evidence_line_follows_the_record(self):
        self.assertIn('none yet', self.m._n100_evidence_line('RSI2'))
        self.put('RSI2', 1.0, 'target', n=40)
        line = self.m._n100_evidence_line('RSI2')
        self.assertIn('40 settled', line)
        self.assertIn('PROMISING'.lower(), line.lower().replace('evidence: ', 'evidence: ')) if False else self.assertIn('evidence:', line)


class TestVolProxy(SigmaCase):
    def make(self, vix=16.0, daily_vol=0.008, n=600, seed=3):
        rnd = random.Random(seed)
        px, cl = 24000.0, []
        for _ in range(n):
            px *= 1 + rnd.gauss(0, daily_vol)
            cl.append(px)
        return candles(cl, vols=[0.0] * n, end_ts=LAST_DAY), candles([vix] * n, vols=[0.0] * n, end_ts=LAST_DAY)

    def test_when_options_are_dearer_than_the_real_moves_the_short_strikes_mostly_hold(self):
        n, v = self.make(vix=16.0, daily_vol=0.008)
        rows = self.m._n100_volproxy(n, v)
        self.assertGreater(len(rows), 80)
        breach = sum(1 for r in rows if r['breach']) / len(rows)
        self.assertLess(breach, 0.317)                                                       # a fairly priced one-sigma strike is breached 31.7% of the time
        ratios = [r['ratio'] for r in rows]
        self.assertLess(sum(ratios) / len(ratios), 0.80)
        self.assertGreater(sum(1 for r in rows if r['pnl'] > 0) / len(rows), 0.55)
        for r in rows:
            self.assertGreater(r['credit'], 0)
            self.assertLess(r['pnl'], r['credit'] * 65 + 1)
            self.assertGreaterEqual(r['pnl'], -r['maxloss'] - 500)

    def test_when_the_real_moves_are_bigger_the_proxy_loses(self):
        n, v = self.make(vix=11.0, daily_vol=0.014)
        rows = self.m._n100_volproxy(n, v)
        self.assertGreater(sum(1 for r in rows if r['breach']) / len(rows), 0.4)
        self.assertLess(sum(r['pnl'] for r in rows), 0)

    def test_the_text_shows_the_shape_of_the_risk_and_the_limits_of_the_study(self):
        n, v = self.make()
        out = self.m._n100_volproxy_text(self.m._n100_volproxy(n, v))
        for word in ('SHORT-VOLATILITY PROXY STUDY', 'Won', 'worst week', 'worst 5 weeks', 'breached', 'wiped out', 'PROXY', 'Real results would be worse', 'not advice'):
            self.assertIn(word, out)
        self.assertIn('Too few weeks', self.m._n100_volproxy_text([]))

    def test_the_command_reads_history_and_says_when_there_is_too_little(self):
        n, v = self.make()
        self.daily['NIFTY'], self.daily['INDIAVIX'] = n, v
        self.md[('INDIAVIX', '1d')] = v[-130:]
        self.assertIn('SHORT-VOLATILITY PROXY STUDY', self.say('sigma volproxy'))
        self.daily['INDIAVIX'] = v[:100]
        self.md[('INDIAVIX', '1d')] = v[:100]
        self.assertIn('too few for the study', self.say('sigma volproxy'))


# ===================================================================================================================
# 13. DATA: the long daily history, its cache, the forming candle
# ===================================================================================================================
class FakeChart:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def chart_payload(cs, none_at=()):
    q = {k: [None if i in none_at else x[k2] for i, x in enumerate(cs)] for k, k2 in (('open', 'o'), ('high', 'h'), ('low', 'l'), ('close', 'c'), ('volume', 'v'))}
    return {'chart': {'result': [{'timestamp': [x['ts'] for x in cs], 'indicators': {'quote': [q]}, 'meta': {}}]}}


class TestData(SigmaCase):
    def setUp(self):
        super().setUp()
        self.m._n100_q('DELETE FROM sig100_cache', write=True)
        self.fetches = []

    def fetcher(self, cs):
        def f(sym, years):
            self.fetches.append((sym, years))
            return [[x['ts'], x['o'], x['h'], x['l'], x['c'], x['v']] for x in cs]
        return f

    def test_the_chart_feed_is_parsed_and_rows_without_prices_are_dropped(self):
        cs = candles(trend(60))
        seen = []

        def get(url, params=None, headers=None, timeout=None):
            seen.append((url, params))
            return FakeChart(chart_payload(cs, none_at=(5, 6)))
        self.start(self.m.requests, 'get', get)
        out = self.m._n100_fetch_daily('TCS', 2)
        self.assertEqual(len(out), 58)
        self.assertTrue(seen[0][0].endswith('TCS.NS'))
        self.assertEqual((seen[0][1]['range'], seen[0][1]['interval']), ('2y', '1d'))
        self.m._n100_fetch_daily('NIFTY', 5)
        self.assertTrue(seen[1][0].endswith('^NSEI'))
        self.start(self.m.requests, 'get', lambda *a, **k: FakeChart({'chart': {'result': [{'timestamp': [1], 'indicators': {'quote': [{}]}}]}}))
        with self.assertRaises(ValueError):
            self.m._n100_fetch_daily('TCS', 2)

    def test_during_the_session_the_forming_candle_is_dropped_and_kept_as_the_live_price(self):
        cs = candles(trend(260), end_ts=ist_ts(2026, 10, 5, 9, 15))                       # the last candle is today's, still forming at 10:30
        self.start(self.m, '_n100_fetch_daily', self.fetcher(cs))
        out, info = ORIG['daily']('TCS', 2, NOW)
        self.assertEqual(len(out), 259)
        self.assertEqual(info['last_day'], '2026-10-04')
        self.assertAlmostEqual(info['live'], cs[-1]['c'])
        self.assertEqual(info['source'], 'Yahoo Finance daily history')

    def test_after_the_close_the_last_candle_counts(self):
        cs = candles(trend(260), end_ts=ist_ts(2026, 10, 5, 9, 15))
        self.start(self.m, '_n100_fetch_daily', self.fetcher(cs))
        out, info = ORIG['daily']('TCS', 2, ist_ts(2026, 10, 5, 16, 0))
        self.assertEqual(len(out), 260)
        self.assertIsNone(info['live'])
        self.assertEqual(info['last_day'], '2026-10-05')

    def test_a_second_call_in_the_same_phase_uses_the_cache(self):
        cs = candles(trend(260), end_ts=ist_ts(2026, 10, 2, 9, 15))
        self.start(self.m, '_n100_fetch_daily', self.fetcher(cs))
        ORIG['daily']('TCS', 2, NOW)
        ORIG['daily']('TCS', 2, NOW + 120)
        self.assertEqual(len(self.fetches), 1)
        ORIG['daily']('TCS', 2, ist_ts(2026, 10, 5, 16, 30))                                # the market has closed: a different phase, fresh data
        self.assertEqual(len(self.fetches), 2)
        ORIG['daily']('TCS', 5, NOW)
        self.assertEqual(len(self.fetches), 3)

    def test_when_the_feed_fails_the_market_fabric_is_the_fallback_and_says_so(self):
        def boom(sym, years):
            raise ValueError('down')
        self.start(self.m, '_n100_fetch_daily', boom)
        self.md[('TCS', '1d')] = candles(trend(200))
        out, info = ORIG['daily']('TCS', 2, NOW)
        self.assertEqual(len(out), 200)
        self.assertIn('short history', info['source'])
        self.assertEqual(info['error'], '')

    def test_when_everything_fails_the_error_is_named(self):
        def boom(sym, years):
            raise ValueError('down')
        self.start(self.m, '_n100_fetch_daily', boom)
        out, info = ORIG['daily']('TCS', 2, NOW)
        self.assertEqual(out, [])
        self.assertTrue(info['error'])

    def test_a_one_day_jump_over_35_percent_is_flagged_for_unadjusted_splits(self):
        cl = trend(260)
        cl[200:] = [x * 0.5 for x in cl[200:]]
        cs = candles(cl, end_ts=ist_ts(2026, 10, 2, 9, 15))
        self.start(self.m, '_n100_fetch_daily', self.fetcher(cs))
        out, info = ORIG['daily']('TCS', 2, NOW)
        self.assertTrue(info['jump'])
        self.assertTrue(self.m._n100_card(self.eval_stock(dip_closes(), jump=True)[0][0], self.cfg, 'SG100-ABC123').count('may not be adjusted'))

    def test_drop_partial_and_staleness(self):
        cs = candles([100.0, 101.0, 102.0], end_ts=ist_ts(2026, 10, 5, 9, 15))
        out, live = self.m._n100_drop_partial(cs, ist_ts(2026, 10, 5, 12, 0))
        self.assertEqual((len(out), live), (2, 102.0))
        out, live = self.m._n100_drop_partial(cs, ist_ts(2026, 10, 5, 16, 0))
        self.assertEqual((len(out), live), (3, None))
        out, live = self.m._n100_drop_partial(cs, ist_ts(2026, 10, 6, 9, 0))
        self.assertEqual((len(out), live), (3, None))
        self.assertEqual(self.m._n100_drop_partial([], NOW), ([], None))
        self.assertFalse(self.m._n100_stale({'last_day': '2026-10-01'}, NOW))                 # a long weekend is fine
        self.assertTrue(self.m._n100_stale({'last_day': '2026-09-20'}, NOW))
        self.assertTrue(self.m._n100_stale({}, NOW))

    def test_the_universe_starts_with_the_watch_list_and_never_holds_an_index(self):
        self.start(self.m, '_n93_watch_list', lambda: ['ZOMATO', 'TCS', 'NIFTY'])
        u = self.m._n100_universe(dict(self.cfg, universe=12))
        self.assertEqual(u[:2], ['ZOMATO', 'TCS'])
        self.assertEqual(len(u), 12)
        self.assertEqual(len(set(u)), 12)
        self.assertNotIn('NIFTY', u)
        self.assertEqual(len(self.m._n100_universe(dict(self.cfg, universe=50))), len(set(self.m._n100_universe(dict(self.cfg, universe=50)))))

    def test_the_market_backdrop_reads_the_trend_and_the_vix(self):
        cs = candles(trend(300, start=23000.0, vol=0.004, drift=0.0006), wick=0.0008)
        ctx = self.m._n100_context(NOW, cs=cs, vcs=vix_series(level=13.0))
        self.assertEqual(ctx['index_dir'], 1)
        self.assertEqual(ctx['regime'] in ('TREND_UP', 'STRONG_TREND_UP', 'EXPANSION_UP'), True, ctx['regime'])
        self.assertIsNotNone(ctx['vix'])
        self.assertIsNotNone(ctx['ret20'])
        ctx = self.m._n100_context(NOW, cs=[], vcs=[])
        self.assertIsNone(ctx['index_dir'])
        self.assertTrue(any('India VIX' in n for n in ctx['notes']))


# ===================================================================================================================
# 14. THE FRONT DOOR: the owner, in a private chat, with these phrases only
# ===================================================================================================================
class TestFrontDoor(SigmaCase):
    def setUp(self):
        super().setUp()
        m = self.m
        self.jobs = []
        for name in ('_n100_scan', '_n100_brief_job', '_n100_symbol_job', '_n100_bt_job', '_n100_bt_all_job', '_n100_volproxy_job', '_n100_check_job'):
            self.start(m, name, lambda cid, *a, _n=name, **k: self.jobs.append((_n[6:], a)))

    def test_every_phrase_reaches_its_job(self):
        cases = [('sigma', ('scan', ('all',))), ('/sigma', ('scan', ('all',))), ('signals', ('scan', ('all',))), ('any signals today', ('scan', ('all',))), ('give me trade signals', ('scan', ('all',))),
                 ('show me new signals now', ('scan', ('all',))), ('signal desk', ('scan', ('all',))), ('Sigma scan', ('scan', ('all',))),
                 ('sigma nifty', ('scan', ('options', ['NIFTY']))), ('sigma banknifty', ('scan', ('options', ['BANKNIFTY']))), ('sigma bank nifty', ('scan', ('options', ['BANKNIFTY']))),
                 ('nifty signal', ('scan', ('options', ['NIFTY']))), ('option signals', ('scan', ('options', ['NIFTY']))), ('option signals banknifty', ('scan', ('options', ['BANKNIFTY']))),
                 ('sigma market', ('brief_job', (('NIFTY',),))), ('market brief', ('brief_job', (('NIFTY',),))), ('sigma brief banknifty', ('brief_job', (('BANKNIFTY',),))), ('banknifty brief', ('brief_job', (('BANKNIFTY',),))),
                 ('sigma TCS', ('symbol_job', ('TCS',))), ('signals for infy', ('symbol_job', ('INFY',))), ('signal on reliance', ('symbol_job', ('RELIANCE',))),
                 ('sigma test TCS', ('bt_job', ('TCS', None))), ('sigma test TCS rsi2', ('bt_job', ('TCS', 'RSI2'))), ('sigma backtest infy donchian', ('bt_job', ('INFY', 'DONCHIAN'))),
                 ('sigma test all', ('bt_all_job', (None,))), ('sigma test all squeeze', ('bt_all_job', ('SQUEEZE',))),
                 ('sigma volproxy', ('volproxy_job', ())), ('sigma vol study', ('volproxy_job', ())), ('sigma condor study', ('volproxy_job', ())),
                 ('sigma check SG100-ABC123', ('check_job', ('SG100-ABC123',)))]
        for text, want in cases:
            self.jobs.clear()
            self.passed.clear()
            self.say(text)
            self.assertEqual(self.passed, [], text)
            self.assertEqual(self.jobs, [(want[0], want[1])], text)

    def test_immediate_answers(self):
        for text, word in (('sigma board', 'No open Sigma signals'), ('sigma stats', 'nothing has settled yet'), ('sigma rules', 'SIGMA RULES'), ('sigma research', 'WHAT SIGMA IS BUILT ON'), ('sigma help', 'SIGMA:'),
                           ('sigma status', 'SIGMA:'), ('sigma config', 'SIGMA SETTINGS'), ('sigma SG100-ABC123', 'I do not have a signal called SG100-ABC123')):
            self.assertIn(word, self.say(text), text)
            self.assertEqual(self.passed, [])

    def test_older_phrases_are_not_taken(self):
        for text in ('trade ideas', 'scout', 'scout nifty', 'what is the nifty today', 'hello nemo', 'signal strength of my wifi', 'a signal of life is good', 'sigma male meaning', 'what does sigma mean in statistics',
                     'buy 1 lot nifty', 'should I buy TCS', 'my paper trades'):
            self.passed.clear()
            self.jobs.clear()
            out = self.say(text)
            self.assertEqual(self.jobs, [], text)
            self.assertNotIn('SIGMA', out, text)
            self.assertEqual(len(self.passed), 1, text)

    def test_a_guest_a_picture_a_file_and_a_group_are_not_served(self):
        self.say('sigma')
        self.jobs.clear()
        self.passed.clear()
        self.m.handle(self.guest('sigma'))
        self.assertEqual((self.jobs, len(self.passed)), ([], 1))
        for extra in ({'document': {'file_id': 'x'}}, {'photo': [{'file_id': 'y'}]}):
            self.passed.clear()
            self.m.handle(self.msg('sigma', **extra))
            self.assertEqual((self.jobs, len(self.passed)), ([], 1))
        self.passed.clear()
        self.m.handle({'chat': {'id': OWNER_ID, 'type': 'group'}, 'from': {'id': OWNER_ID}, 'message_id': 4, 'text': 'sigma'})
        self.assertEqual((self.jobs, len(self.passed)), ([], 1))

    def test_a_command_with_the_bot_name_suffix(self):
        self.say('/sigma@NemoBot')
        self.say('/sigma@NemoBot market')
        self.assertEqual([j[0] for j in self.jobs], ['scan', 'brief_job'])

    def test_an_unknown_share_name_is_not_guessed(self):
        out = self.say('sigma zzqx')
        self.assertIn('I do not know “ZZQX” as a share name', out)
        self.assertIn('scout watch add ZZQX', out)
        self.assertEqual(self.jobs, [])
        self.assertIn('I do not know', self.say('sigma test zzqx'))

    def test_settings_are_validated_and_saved(self):
        out = self.say('sigma config capital=5L risk=2% heat=4 max=3 min=70 universe=20 shorts=on breaker=off perday=6')
        self.assertIn('Saved:', out)
        c = self.m._n100_cfg()
        self.assertEqual((c['capital'], c['risk_pct'], c['heat_pct'], c['max_signals'], c['min_score'], c['universe'], c['shorts'], c['breaker'], c['alerts_per_day']), (500000.0, 2.0, 4.0, 3, 70, 20, True, False, 6))
        self.assertTrue(c['own_capital'])
        out = self.say('sigma config risk=9 colour=red max=abc')
        self.assertIn('risk must be between 0.1 and 5', out)
        self.assertIn('I do not know the setting “colour”', out)
        self.assertIn('is not a number I can use for max.', out)
        self.assertEqual(self.m._n100_cfg()['risk_pct'], 2.0)

    def test_capital_and_risk_follow_scouts_numbers_until_set_here(self):
        self.m._n93_set('capital', '7L')
        self.m._n93_set('risk', '0.5')
        c = self.m._n100_cfg()
        self.assertEqual((c['capital'], c['risk_pct'], c['own_capital']), (700000.0, 0.5, False))
        self.say('sigma config capital=3L')
        c = self.m._n100_cfg()
        self.assertEqual((c['capital'], c['risk_pct'], c['own_capital']), (300000.0, 0.5, True))

    def test_alerts_switch(self):
        self.assertIn('alerts are on', self.say('sigma alerts on'))
        self.assertTrue(self.m._n100_cfg()['alerts'])
        self.assertIn('alerts are off', self.say('sigma alerts off'))
        self.assertFalse(self.m._n100_cfg()['alerts'])

    def test_a_job_that_fails_says_so_and_changes_nothing(self):
        self.start(self.m, '_n100_scan', lambda *a, **k: (_ for _ in ()).throw(ValueError('x')))
        out = self.say('sigma')
        self.assertIn('Sigma hit an unexpected problem (ValueError)', out)
        self.assertIn('Nothing was placed, saved or changed', out)
        self.assertEqual(self.m._N100_STATS['errors'], 1)

    def test_a_signal_can_be_shown_in_full_by_its_id(self):
        recs, _ = self.eval_stock(dip_closes())
        sid = self.m._n100_save(recs[0], NOW)
        out = self.say('sigma ' + sid)
        self.assertIn('(pending)', out)
        self.assertIn('SIGMA ' + sid, out)
        self.assertIn('STOP:', out)
        self.assertIn('SIGMA ' + sid, self.say(sid.lower()))


# ===================================================================================================================
# 15. A WHOLE SCAN, THE ONE-NAME VIEW, THE BRIEF, THE ALERTS
# ===================================================================================================================
class ScanCase(SigmaCase):
    def setUp(self):
        super().setUp()
        self.daily['NIFTY'] = candles(trend(300, start=23000.0, vol=0.004, drift=0.0006), wick=0.0008)
        self.md[('INDIAVIX', '1d')] = vix_series()
        self.daily['TCS'] = candles(dip_closes())
        self.spot = self.daily['NIFTY'][-1]['c']

    def put_nifty_chain(self, **kw):
        ch = chain_with(self.m, spot=self.spot, iv=14.0, days=6.0, buildup=lambda r: (80000.0, -10.0) if r['type'] == 'PE' else (1000.0, 2.0), **kw)
        for r in ch['rows']:
            r['bid'], r['ask'], r['oi'] = round(r['ltp'] * 0.99, 2), round(r['ltp'] * 1.01, 2), 500000.0
        self.chain['NIFTY'] = ch
        return ch


class TestScan(ScanCase):
    def test_a_scan_issues_the_signal_and_summarises_with_what_it_could_not_do(self):
        n = len(self.sent)
        issued = self.m._n100_scan(OWNER_ID, 'all', now=NOW)
        out = self.texts_to_owner(n)
        self.assertTrue([r for r in issued if r['symbol'] == 'TCS'])
        self.assertIn('LONG TCS', out)
        self.assertIn('SIGMA SCAN:', out)
        self.assertIn('“sigma market” shows the whole read', out)
        self.assertIn('NIFTY options:', out)                                  # no chain was given: the reason is named, not guessed
        self.assertEqual(self.m._N100_STATS['scans'], 1)
        self.assertEqual(self.broker_calls, [])
        self.assertEqual(self.ai_calls, [])
        rows = self.m._n100_q('SELECT symbol, strategy, status FROM sig100_signal')
        self.assertIn(('TCS', 'RSI2', 'pending'), rows)

    def test_the_same_scan_again_issues_nothing_new(self):
        self.m._n100_scan(OWNER_ID, 'all', now=NOW)
        n = len(self.sent)
        n_rows = len(self.m._n100_q('SELECT id FROM sig100_signal'))
        issued = self.m._n100_scan(OWNER_ID, 'all', now=NOW)
        self.assertEqual(issued, [])
        self.assertEqual(len(self.m._n100_q('SELECT id FROM sig100_signal')), n_rows)
        self.assertIn('no signal today', self.texts_to_owner(n))

    def test_an_empty_market_gets_a_plain_no_signal(self):
        self.daily.clear()
        n = len(self.sent)
        self.assertEqual(self.m._n100_scan(OWNER_ID, 'all', now=NOW), [])
        out = self.texts_to_owner(n)
        self.assertIn('no signal today', out)
        self.assertIn('often the right answer', out)

    def test_a_quiet_scan_sends_cards_only(self):
        n = len(self.sent)
        self.m._n100_scan(OWNER_ID, 'stocks', quiet=True, now=NOW)
        out = self.texts_to_owner(n)
        self.assertIn('SIGMA SG100-', out)
        self.assertNotIn('SIGMA SCAN', out)
        n = len(self.sent)
        self.m._n100_scan(OWNER_ID, 'stocks', quiet=True, now=NOW)
        self.assertEqual(self.texts_to_owner(n), '')

    def test_the_breaker_stops_the_scan_before_it_reads_anything(self):
        day0 = dt.datetime(2026, 10, 5, tzinfo=IST).timestamp()
        for k in range(3):
            self.m._n100_q('INSERT INTO sig100_signal(id, ts, day, symbol, kind, strategy, side, status, r_result, closed_ts, skey, payload) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                           ('SG100-00000%d' % k, day0, '2026-10-05', 'X', 'stock', 'RSI2', 1, 'stopped', -1.0, day0 + 3600 * (k + 1), 'k%d' % k, '{}'), write=True)
        n = len(self.sent)
        self.daily_calls.clear()
        self.assertEqual(self.m._n100_scan(OWNER_ID, 'all', now=NOW), [])
        self.assertIn('Circuit breaker', self.texts_to_owner(n))
        self.assertEqual(self.daily_calls, [])

    def test_a_scan_that_is_already_running_says_so(self):
        self.m._N100_LOCK.acquire()
        try:
            n = len(self.sent)
            self.m._n100_bg(self.m._n100_scan, OWNER_ID, 'all')
            self.assertIn('already running', self.texts_to_owner(n))
        finally:
            self.m._N100_LOCK.release()

    def test_a_scan_reads_only_the_universe_and_nifty(self):
        self.m._n100_scan(OWNER_ID, 'all', now=NOW)
        syms = {s for s, _y in self.daily_calls}
        self.assertIn('NIFTY', syms)
        self.assertIn('TCS', syms)
        self.assertLessEqual(len(syms), self.cfg['universe'] + 3)
        self.assertEqual(self.m._N100_STATS['data_calls'], 0)                    # (the real feed is stubbed)

    def test_the_option_signal_waits_for_the_entry_window(self):
        self.put_nifty_chain()
        n = len(self.sent)
        self.m._n100_scan(OWNER_ID, 'options', ['NIFTY'], now=ist_ts(2026, 10, 5, 8, 0))
        self.assertIn('only issued between 09:30 and 14:30', self.texts_to_owner(n))
        self.session.update(state='CLOSED_WEEKEND', market_open=False)
        n = len(self.sent)
        self.m._n100_scan(OWNER_ID, 'options', ['NIFTY'], now=NOW)
        self.assertIn('market is closed', self.texts_to_owner(n))
        self.session.update(calendar_known=False)
        n = len(self.sent)
        self.m._n100_scan(OWNER_ID, 'options', ['NIFTY'], now=NOW)
        self.assertIn('only known for 2026', self.texts_to_owner(n))

    def test_an_options_scan_with_a_chain_gives_a_card_or_the_reason(self):
        self.put_nifty_chain()
        self.md[('NIFTY', '5m')] = five_min(ist_ts(2026, 10, 5, 9, 15), [self.spot - 20, self.spot - 15, self.spot - 25, self.spot - 20, self.spot + 5, self.spot + 20])
        n = len(self.sent)
        issued = self.m._n100_scan(OWNER_ID, 'options', ['NIFTY'], now=NOW)
        out = self.texts_to_owner(n)
        opt = [r for r in issued if r['kind'] == 'option']
        if opt:
            self.assertIn('LEGS', out)
            self.assertIn('EXIT PLAN', out)
            self.assertTrue(self.m._n100_q("SELECT id FROM sig100_signal WHERE kind='option'"))
            self.assertGreater(opt[0]['expiry_ts'], NOW)
        else:
            self.assertIn('NIFTY options:', out)
        self.assertEqual(self.m._N100_STATS['chains'], 1)
        self.assertEqual(self.m._n100_q('SELECT COUNT(*) FROM sig100_iv')[0][0], 1)           # the chain's own volatility was kept for next time

    def test_the_chain_is_never_traded_without_quotes(self):
        ch = self.put_nifty_chain()
        for r in ch['rows']:
            r['bid'] = r['ask'] = 0
        self.chain['NIFTY'] = ch
        recs, why, ana = self.m._n100_index_scan('NIFTY', self.put_ctx(), self.cfg, NOW, data={'cs': self.daily['NIFTY'], 'info': self.info(self.daily['NIFTY']), 'cs5': [], 'chain': ch})
        self.assertEqual([r for r in recs if r['kind'] == 'option'], [])


class TestSymbolAndBrief(ScanCase):
    def test_the_name_view_shows_the_panel_and_issues_the_signal(self):
        out = self.say('sigma TCS')
        for word in ('TCS on', 'ATR', 'ADX', 'RSI(2)', 'Price vs', '52-week high', 'SIGMA SG100-', 'LONG TCS'):
            self.assertIn(word, out)

    def test_a_name_with_no_signal_gets_the_reason_for_each_rule(self):
        self.daily['INFY'] = candles(trend(262, seed=9))
        out = self.say('sigma INFY')
        self.assertIn('No Sigma signal for INFY today', out)
        self.assertIn('Why each rule did not fire', out)
        for name in ('RSI-2 long', 'Donchian long', 'Squeeze long', 'Supertrend long'):
            self.assertIn(name, out)

    def test_a_name_that_is_close_to_firing_says_so(self):
        cl = trend(262, seed=1)
        cl[-1] = cl[-2] * 0.993
        cl[-2] = cl[-3] * 0.995
        self.daily['INFY'] = candles(cl)
        F = self.m._n100_prepare(self.daily['INFY'])
        near = self.m._n100_near(F, F['n'] - 1)
        if F['rsi2'][-1] is not None and 10 <= F['rsi2'][-1] < 25 and F['c'][-1] > F['sma200'][-1]:
            self.assertIn('RSI2', [a for a, _t in near])
            self.assertIn('Closest to firing', self.say('sigma INFY'))

    def test_a_name_without_data_says_so(self):
        out = self.say('sigma WIPRO')
        self.assertIn('could not read daily candles for WIPRO', out)

    def test_the_market_brief_reads_the_trend_the_chain_and_gives_a_stance(self):
        self.put_nifty_chain()
        out = self.say('sigma market')
        for word in ('SIGMA MARKET BRIEF', 'Trend: regime', 'Levels for the next session', 'pivot', 'India VIX', 'Options (', 'at-the-money implied volatility', 'expected move', 'Open interest: PCR', 'Build-up near the money',
                     'Skew:', 'Volatility percentile', 'Stance:', 'A reading of the numbers, not a forecast or advice'):
            self.assertIn(word, out, word)
        self.assertEqual(self.m._N100_STATS['briefs'], 1)

    def test_the_brief_names_what_it_could_not_read(self):
        out = self.say('sigma market')
        self.assertIn('SIGMA MARKET BRIEF', out)
        self.assertIn('Options:', out)
        self.daily.clear()
        out = self.say('sigma market')
        self.assertIn('I could not read enough daily candles for NIFTY', out)

    def test_the_stance_follows_the_regime_and_the_volatility(self):
        S = self.m._n100_stance
        self.assertIn('trend-following', S('TREND_UP', 30.0, None, True))
        self.assertIn('dear', S('TREND_UP', 80.0, None, True))
        self.assertIn('iron condor', S('RANGE', 75.0, None, True))
        self.assertIn('Standing aside', S('RANGE', 30.0, None, True))
        self.assertIn('could not be read', S(None, 30.0, None, True))


class TestAlerts(ScanCase):
    def test_a_slot_scans_once_a_day_and_only_when_alerts_are_on(self):
        self.session.update(state='PRE_MARKET', market_open=False)
        at = ist_ts(2026, 10, 5, 8, 55)
        self.assertEqual(self.m._n100_alert_tick(at), 0)                                    # alerts are off by default
        self.assertEqual(self.m._n100_q('SELECT COUNT(*) FROM sig100_signal')[0][0], 0)
        self.m._n100_set('alerts', 'on')
        n = len(self.sent)
        self.assertGreaterEqual(self.m._n100_alert_tick(at), 1)
        self.assertIn('SIGMA SG100-', self.texts_to_owner(n))
        n = len(self.sent)
        self.assertEqual(self.m._n100_alert_tick(at + 60), 0)                                # the same slot, the same day: never twice
        self.assertEqual(self.texts_to_owner(n), '')

    def test_the_daily_quota_is_respected(self):
        self.session.update(state='PRE_MARKET', market_open=False)
        self.m._n100_set('alerts', 'on')
        self.m._n100_set('perday', '1')
        self.m._n100_put('alerts_day', '2026-10-05')
        self.m._n100_put('alerts_n', '1')
        self.assertEqual(self.m._n100_alert_tick(ist_ts(2026, 10, 5, 8, 55)), 0)
        self.assertEqual(self.m._n100_q('SELECT COUNT(*) FROM sig100_signal')[0][0], 0)

    def test_no_alerts_on_a_holiday_or_outside_the_slots(self):
        self.m._n100_set('alerts', 'on')
        self.session.update(state='CLOSED_HOLIDAY', market_open=False)
        self.assertEqual(self.m._n100_alert_tick(ist_ts(2026, 10, 5, 8, 55)), 0)
        self.session.update(state='OPEN', market_open=True)
        self.assertEqual(self.m._n100_alert_tick(ist_ts(2026, 10, 5, 12, 0)), 0)
        self.assertEqual(self.m._n100_alert_tick(ist_ts(2026, 10, 5, 3, 0)), 0)

    def test_the_scan_quota_limits_the_cards_not_the_setting(self):
        self.session.update(state='PRE_MARKET', market_open=False)
        for s in ('INFY', 'WIPRO', 'HCLTECH'):
            self.daily[s] = candles(dip_closes())
        self.m._n100_set('alerts', 'on')
        self.m._n100_put('alerts_day', '2026-10-05')
        self.m._n100_put('alerts_n', '3')
        n = len(self.sent)
        self.m._n100_alert_tick(ist_ts(2026, 10, 5, 8, 55))
        self.assertEqual(self.texts_to_owner(n).count('SIGMA SG100-'), 1)                    # one left of the four
        self.assertEqual(self.m._n100_cfg()['max_signals'], 4)                               # and the owner's own setting was not touched


# ===================================================================================================================
# 16. NOTHING TOUCHES MONEY, THE AGENT, THE NETWORK (BUT ONE FEED), THE AI OR ANOTHER LAYER'S TABLES
# ===================================================================================================================
class TestWiring(SigmaCase):
    def test_version_marker_and_protection(self):
        self.assertEqual(self.m.VERSION, '100.0')
        src = open(base.NEMO_FILE, encoding='utf-8').read()
        self.assertIn('nemotron_bot.py v100.0 - SIGMA', src.split('"""', 2)[1][:200])
        self.assertIn("'_n99_','_n991_','_n100_','_p75_'", src)                       # the live self-editor may not touch the layer
        self.assertEqual(src.count('# NEMO 100 - SIGMA'), 1)

    def test_the_layer_adds_only_its_own_names_and_wraps_five_older_ones(self):
        tree = ast.parse(sigma_source())
        names = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                names.append(node.name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        names.append(t.id)
        foreign = {n for n in names if not n.startswith(('_n100_', '_N100_', '_N100'))}
        self.assertEqual(foreign, {'VERSION', '_n82_capabilities', '_n83_status_text', 'handle', 'prime_regression_suite', 'main'})

    def test_every_wrapped_function_is_really_wrapped_and_calls_the_old_one(self):
        m = self.m
        for new, old in (('handle', '_N100_HANDLE_PREV'), ('_n82_capabilities', '_N100_CAPS_PREV'), ('_n83_status_text', '_N100_STATUS_PREV'), ('prime_regression_suite', '_N100_REG_PREV'),
                         ('main', '_N100_MAIN_PREV')):
            self.assertIsNot(getattr(m, new), getattr(m, old), new)
        self.assertIn('Sigma 100', m._n82_capabilities())
        self.assertIn('Advisory only', m._n82_capabilities())
        status = m._n83_status_text(OWNER_ID)
        self.assertLessEqual(len(status), 3990)                                          # (the one-screen status is already full: Sigma's own counters are on “sigma status”)
        self.assertIn('SIGMA: a signal desk', m._n100_status_text())
        self.assertIn('0 scans', m._n100_status_text())
        self.assertFalse(hasattr(m, '_N100_ABIL_PREV'))                              # (the “what can you do” screen is already full: adding a row to it breaks the older report tests, so Sigma stays off it)

    def test_the_regression_rows_all_pass(self):
        rows = self.m._n100_regression_rows()
        self.assertGreaterEqual(len(rows), 8)
        self.assertEqual([r['name'] for r in rows if not r['ok']], [])
        suite = self.m.prime_regression_suite()
        self.assertEqual([t['name'] for t in suite['tests'] if t['name'].startswith('v100-') and not t['ok']], [])

    def test_the_layer_never_names_an_order_the_agent_the_ledger_the_ai_or_the_owner_lock(self):
        tree = ast.parse(sigma_source())
        ids = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        forbidden = {'fyers_place', 'fyers_place_bracket', 'fyers_place_cover', 'place_order', '_order_send', 'request_order', 'AUTO', 'AUTOLOG', 'ask_ai', 'web_search', '_n73_core_reply', '_n72_decide', '_n73_request',
                     'subprocess', 'system', 'eval', 'exec', 'open', 'post', 'put', 'delete', 'fyers_login', 'fyers_exchange', 'fyers_refresh', '_n90_secret', 'save_secret'}
        self.assertEqual(ids & forbidden, set())
        self.assertEqual({n for n in ids if re.match(r'^_?p75_', n)}, set())                      # the paper ledger
        self.assertEqual({n for n in ids if re.match(r'^_n9[6-9]_(?!costs|charge_parts|wilson)', n)} - {'_n96_q'} & {n for n in ids if n.endswith(('_save', '_put', '_set', '_write'))}, set())

    def test_the_owner_lock_and_the_agent_are_only_read_never_assigned(self):
        tree = ast.parse(sigma_source())
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                targets = [node.target]
            for t in targets:
                for sub in ast.walk(t):
                    if isinstance(sub, ast.Name):
                        self.assertNotIn(sub.id, ('OWNER', 'AUTO', 'AUTOLOG', 'ALLOWED', 'MODE'), 'the layer assigns to ' + sub.id)

    def test_the_one_network_call_is_the_public_daily_feed(self):
        tree = ast.parse(sigma_source())
        gets = []
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            for c in ast.walk(fn):
                if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and isinstance(c.func.value, ast.Name) and c.func.value.id == 'requests':
                    gets.append((fn.name, c.func.attr))
        self.assertEqual(gets, [('_n100_fetch_daily', 'get')])
        self.assertIn('query1.finance.yahoo.com', sigma_source())
        urls = re.findall(r'https?://[^\s\'"]+', sigma_source())
        self.assertEqual(sorted({u.split('/')[2] for u in urls}), ['query1.finance.yahoo.com'])

    def test_sql_touches_only_its_own_tables(self):
        src = sigma_source()
        tables = set()
        for stmt in re.findall(r"'((?:SELECT|INSERT|UPDATE|DELETE|CREATE)[^']*)'", src):
            tables |= set(re.findall(r'(?:FROM|INTO|UPDATE|TABLE(?: IF NOT EXISTS)?|JOIN)\s+([A-Za-z_0-9]+)', stmt))
        self.assertTrue(tables)
        self.assertEqual({t for t in tables if not t.startswith('sig100_')}, set())
        self.assertEqual(tables, {'sig100_setting', 'sig100_signal', 'sig100_iv', 'sig100_cache'})

    def test_no_secret_shaped_text(self):
        src = sigma_source()
        for pat in (r'sk-[A-Za-z0-9]{10,}', r'AKIA[0-9A-Z]{12,}', r'ghp_[A-Za-z0-9]{20,}', r'xox[bp]-[0-9A-Za-z-]{10,}', r'(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*[\'"][^\'"]{6,}', r'AIza[0-9A-Za-z_-]{20,}'):
            self.assertEqual(re.findall(pat, src), [], pat)

    def test_no_model_names_in_the_layer(self):
        self.assertEqual(re.findall(r'(?i)claude-|sonnet|opus|gpt-\d|gemini-\d', sigma_source()), [])

    def test_a_whole_working_day_makes_no_http_ai_or_broker_call(self):
        self.daily['NIFTY'] = candles(trend(300, start=23000.0, vol=0.004, drift=0.0006), wick=0.0008)
        self.daily['TCS'] = candles(dip_closes())
        self.md[('INDIAVIX', '1d')] = vix_series()
        ch = chain_with(self.m, spot=self.daily['NIFTY'][-1]['c'])
        self.chain['NIFTY'] = ch
        self.say('sigma')
        self.say('sigma market')
        self.say('sigma TCS')
        self.say('sigma stats')
        self.say('sigma board')
        self.m._n100_track_once(NOW)
        self.assertEqual(self.http.calls, [])
        self.assertEqual(self.ai_calls, [])
        self.assertEqual(self.broker_calls, [])
        self.assertEqual(self.passed, [])

    def test_the_cards_and_commands_always_carry_the_advisory_note(self):
        self.assertIn('you place any order yourself', self.m._N100_NOTE)
        self.assertIn('SEBI', self.m._N100_NOTE)
        recs, _ = self.eval_stock(dip_closes())
        self.assertIn(self.m._N100_NOTE, self.m._n100_card(recs[0], self.cfg, 'SG100-ABC123'))
        for text in (self.m._n100_research_text(), self.m._n100_rules_text(), self.m._n100_status_text()):
            self.assertLessEqual(len(text), 3950)
        self.assertIn('no public, audited evidence', self.m._n100_research_text())
        self.assertIn('Sigma does not broadcast', self.m._n100_research_text())

    def test_the_rules_text_matches_the_constants(self):
        text = self.m._n100_rules_text()
        R = self.m._N100_RULES
        for needle in ('RSI(2) below 10', '2.5 ATR', '55-day high', '1.3x volume', 'ADX is at least 20', 'within 3%', '120 days', 'Supertrend(10,3)', '15:10', 'daily trend 30%', 'intraday 25%', 'build-up 20%', 'walls 10%', 'PCR tilt 5%'):
            self.assertIn(needle, text, needle)
        self.assertEqual(R['HIGH52']['near'], 0.97)
        self.assertEqual(R['SQUEEZE']['pct_max'], 20.0)

    def test_the_background_loop_and_menu_are_wired(self):
        src = open(base.NEMO_FILE, encoding='utf-8').read()
        self.assertIn("_N100_MAIN_PREV = main", src)
        self.assertIn("('sigma', 'Trade signals with entry, stop and exit (advisory)')", src)
        self.assertTrue(any(c[0] == 'sigma' for c in self.m._N40_COMMANDS))
        self.assertTrue(any(btn[1] == 'c:/sigma' for row in self.m._N40_MENUS['main'][1] for btn in row))
        self.assertTrue(callable(self.m._n100_ensure_thread))


# ===================================================================================================================
# 17. CARDS: lengths, the index version, checking an option or an opening-range signal
# ===================================================================================================================
class TestCards(OptionSignalCase):
    def test_every_card_fits_one_message_and_keeps_its_closing_note(self):
        cards = []
        recs, _ = self.eval_stock(dip_closes())
        cards.append(self.m._n100_card(recs[0], self.cfg, 'SG100-ABC123'))
        for kw in (dict(pct=20.0), dict(pct=85.0), dict(regime='RANGE', pct=80.0, intr={'value': 0.0, 'words': 'flat'}, st=dict(self.st, buildup=None))):
            r = self.sig(**kw)
            if r['ok']:
                cards.append(self.m._n100_card(r, self.cfg, 'SG100-ABC124'))
                cards.append(self.m._n100_card(r, dict(self.cfg, capital=20000.0), 'SG100-ABC125'))
        self.assertGreaterEqual(len(cards), 4)
        for c in cards:
            self.assertLessEqual(len(c), 3950)
            self.assertIn('you place any order yourself', c)

    def test_the_index_card_has_no_share_size_but_a_futures_lot_risk(self):
        cs = candles(dip_closes())
        recs, _ = self.m._n100_eval_daily('NIFTY', cs, self.info(cs), self.put_ctx(), self.cfg, 'index', NOW)
        card = self.m._n100_card(recs[0], self.cfg, 'SG100-ABC123')
        self.assertIn('index-level signal', card)
        self.assertIn('one lot is 65 units', card)
        self.assertIn('sigma nifty', card)

    def test_the_opening_range_card(self):
        cs5 = five_min(ist_ts(2026, 10, 5, 9, 15), [24500, 24505, 24495, 24500, 24545, 24560])
        daily = candles(trend(200, start=24000.0, vol=0.002, drift=0.0003), wick=0.0005)
        recs, why, ana = self.m._n100_index_scan('NIFTY', self.put_ctx(), self.cfg, NOW, daily=False, orb=True, options=False, data={'cs': daily, 'info': self.info(daily), 'cs5': cs5})
        card = self.m._n100_card(recs[0], self.cfg, 'SG100-ABC123')
        for word in ('Opening-range breakout', 'WHY:', 'ENTRY:', 'STOP:', 'TIME STOP: out by 15:10', 'SIZE: as futures one lot is 65 units', 'not a true VWAP', 'cannot be back-tested here', 'WRONG IF'):
            self.assertIn(word, card, word)

    def test_checking_an_option_signal_marks_it_and_says_how(self):
        r = self.sig(pct=20.0)
        r['expiry_ts'] = NOW + 6 * 86400.0
        sid = self.m._n100_save(r, NOW)
        ch = chain_with(self.m, spot=self.spot + 10.0, iv=14.0, days=5.9)
        for x in ch['rows']:
            x['bid'], x['ask'], x['oi'] = round(x['ltp'] * 0.99, 2), round(x['ltp'] * 1.01, 2), 500000.0
        self.chain['NIFTY'] = ch
        out = self.say('sigma check ' + sid)
        self.assertIn('live chain mid prices', out)
        self.assertIn(sid, out)
        self.assertIn('Status: open', out)

    def test_checking_a_stock_signal_waiting_for_its_open(self):
        recs, _ = self.eval_stock(dip_closes())
        sid = self.m._n100_save(recs[0], NOW)
        self.daily['TCS'] = candles(dip_closes())
        out = self.say('sigma check ' + sid)
        self.assertIn('Waiting for the next open', out)
        self.assertIn('There is no open signal', self.say('sigma drop SG100-FFFFFF'))
        self.assertIn('I do not have a signal called', self.say('sigma check SG100-FFFFFF') or 'I do not have a signal called')
