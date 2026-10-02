"""Behavioural tests for Nemo v84 Atlas: Futures Desk + speed layer.

Expected values are computed independently here (explicit arithmetic, brute-force enumeration, hand-counted calendars),
not by calling the code under test. Uses the same harness as test_cortex83 (scripted fake provider, temp SQLite, fake Telegram).

    python -m unittest tests.test_atlas84 -v
"""
import datetime as dt
import itertools
import json
import math
import os
import sys
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import test_cortex83 as base                      # noqa: E402
from tests.test_cortex83 import CortexCase, answer_stage      # noqa: E402

m = None
NOW = dt.datetime(2026, 10, 2, 12, 0)        # Friday 2 Oct 2026 (a market holiday: Gandhi Jayanti)


def setUpModule():
    global m
    if base.m is None:
        base.setUpModule()
    m = base.m


class AtlasCase(CortexCase):
    def setUp(self):
        super().setUp()
        m._N84_SCHEMA['path'] = None
        for k in m._N84_STATS:
            m._N84_STATS[k] = 0
        p = mock.patch.object(m, '_n83_now', lambda: NOW)
        p.start()
        self.patches.append(p)

    def run_cmd(self, line, now=NOW, read_only=False):
        return m._n84_exec(self.cid, line, now, read_only)


# ---------------------------------------------------------------- number parsing / formatting
class TestParsing(AtlasCase):
    def test_amounts(self):
        for text, want in (('5L', 500000), ('1.5cr', 15000000), ('₹5,00,000', 500000), ('500k', 500000), ('1,25,000', 125000),
                           ('2 lakh', 200000), ('Rs. 750', 750), ('0', 0), ('24500.5', 24500.5)):
            self.assertEqual(m._n84_amount(text), want, text)

    def test_amount_rejects_garbage(self):
        for bad in ('-5', 'nan', 'inf', '1e5', '', None, 'five', '5 6', '1,2,x', '99999999999999999'):
            with self.assertRaises(ValueError, msg=repr(bad)):
                m._n84_amount(bad)

    def test_price_and_int_bounds(self):
        with self.assertRaises(ValueError):
            m._n84_price('0', 'p')
        with self.assertRaises(ValueError):
            m._n84_price('2e8', 'p')
        with self.assertRaises(ValueError):
            m._n84_int('2.5', 'lots')
        with self.assertRaises(ValueError):
            m._n84_int('0', 'lots')
        self.assertEqual(m._n84_int('3', 'lots'), 3)

    def test_probability_forms(self):
        for text in ('45', '45%', '0.45'):
            self.assertAlmostEqual(m._n84_prob(text, 'w'), 0.45)
        for bad in ('0', '100', '1', 'x', '-5'):
            with self.assertRaises(ValueError, msg=bad):
                m._n84_prob(bad, 'w')

    def test_inr_indian_grouping(self):
        self.assertEqual(m._n84_inr(1592500), '₹15,92,500')
        self.assertEqual(m._n84_inr(999), '₹999')
        self.assertEqual(m._n84_inr(100000), '₹1,00,000')
        self.assertEqual(m._n84_inr(-12345.678, 2), '-₹12,345.68')
        self.assertEqual(m._n84_inr(12345678), '₹1,23,45,678')

    def test_parse_command_line(self):
        sub, pos, kv = m._n84_parse('/fut84 journal add side=long note="gap up open" tag=b')
        self.assertEqual((sub, pos, kv), ('journal', ['add'], {'side': 'long', 'note': 'gap up open', 'tag': 'b'}))
        with self.assertRaises(ValueError):
            m._n84_parse('size entry=1 entry=2')

    def test_unknown_parameters_are_rejected_with_help(self):
        with self.assertRaises(ValueError) as ctx:
            self.run_cmd('size capital=5L entyr=24500 stop=24440 sym=NIFTY')
        self.assertIn('entyr', str(ctx.exception))
        self.assertIn('Allowed', str(ctx.exception))


# ---------------------------------------------------------------- expiry calendar
class TestExpiryCalendar(AtlasCase):
    D = dt.date

    def test_known_holiday_moves_expiry_back(self):
        # Nov 2026: last Tuesday is 24 Nov = Guru Nanak Jayanti (in the v81 holiday table) -> Monday 23 Nov
        row = m._n84_expiries(self.D(2026, 11, 1), 1, 'tue')[0]
        self.assertEqual(row['expiry'], self.D(2026, 11, 23))
        self.assertTrue(row['shifted'])
        self.assertEqual(row['holiday'], 'Guru Nanak Jayanti')
        # Mar 2026: last Tuesday 31 Mar = Mahavir Jayanti -> Monday 30 Mar
        self.assertEqual(m._n84_expiries(self.D(2026, 3, 1), 1, 'tue')[0]['expiry'], self.D(2026, 3, 30))

    def test_plain_months(self):
        self.assertEqual(m._n84_expiries(self.D(2026, 10, 2), 1, 'tue')[0]['expiry'], self.D(2026, 10, 27))
        self.assertEqual(m._n84_expiries(self.D(2026, 12, 1), 1, 'tue')[0]['expiry'], self.D(2026, 12, 29))

    def test_session_count_excludes_holidays_and_weekends(self):
        # hand count 3 Oct..27 Oct 2026: Oct 5-9 (5) + 12-16 (5) + 19-23 minus Dussehra Tue 20 Oct (4) + 26,27 (2) = 16
        row = m._n84_expiries(self.D(2026, 10, 2), 1, 'tue')[0]
        self.assertEqual(row['days'], 25)
        self.assertEqual(row['trading_days'], 16)

    def test_expiry_day_and_after(self):
        self.assertEqual(m._n84_expiries(self.D(2026, 12, 29), 1, 'tue')[0]['trading_days'], 0)       # expires today
        nxt = m._n84_expiries(self.D(2026, 12, 30), 1, 'tue')[0]                                       # Dec expiry passed
        self.assertEqual(nxt['expiry'], self.D(2027, 1, 26))
        self.assertFalse(nxt['calendar_known'])                                                         # 2027: holiday list unknown

    def test_count_and_weekday_setting(self):
        rows = m._n84_expiries(self.D(2026, 10, 2), 3, 'tue')
        self.assertEqual([r['month'] for r in rows], ['OCT 2026', 'NOV 2026', 'DEC 2026'])
        self.assertEqual(m._n84_expiries(self.D(2026, 10, 2), 1, 'thu')[0]['expiry'], self.D(2026, 10, 29))
        with self.assertRaises(ValueError):
            m._n84_expiries(self.D(2026, 10, 2), 1, 'sat')

    def test_adjust_skips_weekend_and_holiday(self):
        self.assertEqual(m._n84_adjust(self.D(2026, 10, 3))[0], self.D(2026, 10, 1))      # Sat -> Fri 2 Oct is a holiday -> Thu 1 Oct
        self.assertEqual(m._n84_adjust(self.D(2026, 10, 27))[1], False)

    def test_roll_window_and_symbol_hint(self):
        row = m._n84_expiries(self.D(2026, 10, 21), 1, 'tue', 5, 'nifty')[0]
        self.assertEqual(row['trading_days'], 4)                      # 22, 23, 26, 27 Oct
        self.assertTrue(row['in_roll_window'])
        self.assertEqual(row['hint'], 'NSE:NIFTY26OCTFUT')

    def test_command_text(self):
        out = self.run_cmd('expiry sym=NIFTY')
        self.assertIn('Today is a market holiday: Mahatma Gandhi Jayanti', out)
        self.assertIn('Tue 27 Oct 2026', out)
        self.assertIn('Mon 23 Nov 2026', out)
        self.assertIn('Guru Nanak Jayanti', out)
        self.assertIn('ESTIMATE', out)
        self.assertIn('NOT verified today', out)                       # built-in lot table is labelled unverified


# ---------------------------------------------------------------- pricing maths
class TestPricing(AtlasCase):
    def test_basis_matches_independent_formula(self):
        b = m._n84_basis(24500, 24590, 26, 6.5, 0, 0.1)
        fair = 24500 * math.exp(0.065 * 26 / 365)
        self.assertAlmostEqual(b['fair'], fair, places=9)
        self.assertAlmostEqual(b['fair'], 24613.7, places=1)           # hand-checked
        self.assertAlmostEqual(b['premium_pct'], (24590 / 24500 - 1) * 100, places=9)
        self.assertAlmostEqual(b['annualised_pct'], 90 / 24500 * 365 / 26 * 100, places=9)
        self.assertAlmostEqual(b['implied_rate_pct'], math.log(24590 / 24500) * 365 / 26 * 100, places=9)
        self.assertEqual(b['verdict'], 'near fair value')              # |-0.097%| <= 0.10%

    def test_rich_cheap_backwardation_and_dividend(self):
        self.assertEqual(m._n84_basis(24500, 24700, 26, 6.5, 0, 0.1)['verdict'], 'RICH vs fair')
        self.assertEqual(m._n84_basis(24500, 24550, 26, 6.5, 0, 0.1)['verdict'], 'CHEAP vs fair')
        self.assertIn('backwardation', m._n84_basis(24500, 24450, 26, 6.5, 0, 0.1)['structure'])
        with_div = m._n84_basis(24500, 24590, 26, 6.5, 1.2, 0.1)
        self.assertAlmostEqual(with_div['fair'], 24500 * math.exp((0.065 - 0.012) * 26 / 365), places=9)
        self.assertLess(with_div['fair'], m._n84_basis(24500, 24590, 26, 6.5, 0, 0.1)['fair'])

    def test_basis_expiry_day_is_rejected(self):
        with self.assertRaises(ValueError):
            m._n84_basis(24500, 24510, 0, 6.5, 0, 0.1)

    def test_basis_command_uses_nearest_expiry_for_symbol(self):
        out = self.run_cmd('basis spot=24500 fut=24590 sym=NIFTY')
        self.assertIn('25 days to the estimated OCT 2026 expiry 2026-10-27', out)

    def test_roll_cost(self):
        r = m._n84_roll(24590, 24680, 27, 65, 2, 6.5, 0)
        self.assertAlmostEqual(r['total'], 90 * 65 * 2)
        self.assertAlmostEqual(r['fair_spread'], 24590 * (math.exp(0.065 * 27 / 365) - 1), places=9)
        self.assertAlmostEqual(r['annualised_pct'], 90 / 24590 * 365 / 27 * 100, places=9)
        neg = m._n84_roll(24680, 24590, 27, 65, 1, 6.5, 0)
        self.assertAlmostEqual(neg['spread'], -90)

    def test_roll_command_derives_days_between_expiries(self):
        out = self.run_cmd('roll near=24590 next=24680 sym=NIFTY lots=2')
        self.assertIn('27 days apart', out)                           # 27 Oct -> 23 Nov
        self.assertIn('₹11,700', out)
        self.assertIn('BELOW fair', out)


# ---------------------------------------------------------------- sizing / pnl / check
class TestSizingPnlCheck(AtlasCase):
    def test_size_by_risk(self):
        s = m._n84_size(2000000, 20000, 24500, 24440, 65, 0, None, 50)
        self.assertEqual(s['risk_per_lot'], 60 * 65)                  # 3,900
        self.assertEqual(s['lots'], 5)                                # floor(20000/3900)=5
        self.assertAlmostEqual(s['risk_total'], 19500)
        self.assertAlmostEqual(s['risk_pct'], 0.975)
        self.assertEqual(s['side'], 'long')

    def test_slippage_widens_risk(self):
        s = m._n84_size(2000000, 20000, 24500, 24440, 65, 2, None, 50)
        self.assertEqual(s['risk_per_lot'], 62 * 65)                  # 4,030
        self.assertEqual(s['lots'], 4)                                # floor(20000/4030)=4

    def test_margin_cap_can_bind(self):
        s = m._n84_size(500000, 50000, 24500, 24440, 65, 0, 191100, 50)
        self.assertEqual(s['lots_by_risk'], 12)
        self.assertEqual(s['lots_by_margin'], 1)                      # floor(250000/191100)
        self.assertEqual((s['lots'], s['binding']), (1, 'margin cap'))

    def test_zero_lots_and_short_side_inference(self):
        s = m._n84_size(500000, 3000, 24500, 24440, 65, 0, None, 50)
        self.assertEqual(s['lots'], 0)
        short = m._n84_size(500000, 5000, 24500, 24560, 65, 0, None, 50, target=24380)
        self.assertEqual(short['side'], 'short')
        self.assertAlmostEqual(short['rr'], 2.0)
        self.assertAlmostEqual(short['breakeven_winrate_pct'], 100 / 3.0)

    def test_inconsistent_inputs_rejected(self):
        for kwargs in (dict(stop=24440, side='short'), dict(stop=24500), dict(stop=24440, target=24400)):
            args = dict(capital=500000, risk_amount=5000, entry=24500, stop=24440, lot=65, slip=0, margin_per_lot=None, max_margin_util_pct=50)
            args.update(kwargs)
            with self.assertRaises(ValueError, msg=str(kwargs)):
                m._n84_size(**args)

    def test_size_command_full_example(self):
        out = self.run_cmd('size capital=5L risk=1% entry=24500 stop=24440 sym=NIFTY target=24650 margin=12%')
        for want in ('LONG', '₹3,900', '1 lot(s) by risk', '₹1,91,100', '2.50R', '29%', '₹15,92,500', 'NOT verified today'):
            self.assertIn(want, out)

    def test_size_without_margin_says_cap_not_applied(self):
        self.assertIn('margin cap is NOT applied', self.run_cmd('size capital=5L risk=5000 entry=24500 stop=24440 lot=65'))

    def test_size_uses_saved_capital(self):
        self.run_cmd('config capital=10L')
        out = self.run_cmd('size entry=24500 stop=24440 lot=65')          # risk defaults to max_risk_pct (1%) of saved capital
        self.assertIn('₹10,000 (1.00% of ₹10,00,000)', out)
        self.assertIn('2 lot(s) by risk', out)                              # floor(10000/3900)

    def test_pnl_gross(self):
        p = m._n84_pnl('long', 24500, 24580, 2, 65, {})
        self.assertEqual((p['points'], p['gross'], p['configured']), (80, 10400, False))
        s = m._n84_pnl('short', 24500, 24580, 2, 65, {})
        self.assertEqual((s['points'], s['gross']), (-80, -10400))

    def test_pnl_charges_match_hand_calculation(self):
        cfg = dict(brokerage=20, stt_sell_pct=0.02, exch_pct=0.002, sebi_per_cr=10, stamp_buy_pct=0.002, gst_pct=18)
        p = m._n84_pnl('long', 24500, 24580, 2, 65, cfg)
        qty = 130
        buy, sell = 24500 * qty, 24580 * qty
        brokerage = 2 * 20
        stt = sell * 0.02 / 100
        exch = (buy + sell) * 0.002 / 100
        sebi = (buy + sell) * 10 / 1e7
        stamp = buy * 0.002 / 100
        gst = (brokerage + exch + sebi) * 0.18
        want = brokerage + stt + exch + sebi + stamp + gst
        self.assertAlmostEqual(p['charges'], want, places=6)
        self.assertAlmostEqual(p['net'], 10400 - want, places=6)
        self.assertAlmostEqual(p['breakeven_points'], want / qty, places=9)
        # short: STT applies to the (higher-priced) sell leg being the ENTRY
        sp = m._n84_pnl('short', 24580, 24500, 2, 65, cfg)
        self.assertAlmostEqual(sp['charge_parts']['stt'], 24580 * qty * 0.02 / 100, places=6)

    def test_pnl_command_says_gross_when_unconfigured(self):
        out = self.run_cmd('pnl side=long entry=24500 exit=24580 lots=2 sym=NIFTY')
        self.assertIn('GROSS', out)
        self.assertIn('₹10,400', out)
        self.run_cmd('config brokerage=20')
        self.assertIn('Charges (your configured rates)', self.run_cmd('pnl side=long entry=24500 exit=24580 lots=2 sym=NIFTY'))

    def test_pnl_open_position_ltp(self):
        self.assertIn('ltp 24580', self.run_cmd('pnl side=long entry=24500 ltp=24580 lots=1 lot=65'))

    def test_check_verdicts(self):
        base_args = 'side=long entry=24500 stop=24440 target=24650 sym=NIFTY capital=5L margin=12%'
        ok = self.run_cmd('check ' + base_args + ' lots=1', now=dt.datetime(2026, 10, 6, 10, 0))
        self.assertIn('verdict: CLEAR', ok)
        two = self.run_cmd('check ' + base_args + ' lots=2', now=dt.datetime(2026, 10, 6, 10, 0))
        self.assertIn('verdict: CAUTION', two)
        self.assertIn('exceeds your limit ₹5,000: 1 lot(s) would fit', two)
        self.assertIn('Margin use 76% exceeds your 50% cap', two)
        big = self.run_cmd('check ' + base_args + ' lots=3', now=dt.datetime(2026, 10, 6, 10, 0))
        self.assertIn('verdict: BLOCK (advisory)', big)               # 11,700 > 2 x 5,000

    def test_check_expiry_and_session_flags(self):
        args = 'side=long entry=24500 stop=24440 lots=1 sym=NIFTY capital=5L margin=12%'
        exp_day = self.run_cmd('check ' + args, now=dt.datetime(2026, 10, 27, 10, 0))
        self.assertIn('expires TODAY', exp_day)
        self.assertIn('BLOCK', exp_day)
        near = self.run_cmd('check ' + args, now=dt.datetime(2026, 10, 26, 10, 0))
        self.assertIn('Only 1 session(s) to expiry', near)
        closed = self.run_cmd('check ' + args, now=NOW)               # holiday
        self.assertIn('Market is not open now (CLOSED_HOLIDAY', closed)

    def test_check_atr_and_rr_flags(self):
        out = self.run_cmd('check side=long entry=24500 stop=24490 target=24505 lots=1 lot=65 capital=5L atr=95', now=dt.datetime(2026, 10, 6, 10, 0))
        self.assertIn('inside normal noise', out)
        self.assertIn('below 1', out)
        self.assertIn('No margin supplied', out)

    def test_check_never_claims_to_trade(self):
        out = self.run_cmd('check side=long entry=24500 stop=24440 lots=1 lot=65 capital=5L')
        self.assertIn('does not place futures orders', out)


# ---------------------------------------------------------------- edge / kelly / streaks
class TestEdge(AtlasCase):
    def test_kelly_and_expectancy(self):
        e = m._n84_edge(0.5, 2.0)
        self.assertAlmostEqual(e['kelly'], 0.25)
        self.assertAlmostEqual(e['expectancy_r'], 0.5)
        n = m._n84_edge(0.3, 1.0)
        self.assertFalse(n['has_edge'])
        self.assertLess(n['kelly'], 0)
        self.assertEqual(n['half_kelly'], 0)

    def test_streak_probability_equals_brute_force(self):
        def brute(q, n, k):
            total = 0.0
            for seq in itertools.product('WL', repeat=n):
                p = 1.0
                for x in seq:
                    p *= q if x == 'L' else 1 - q
                if 'L' * k in ''.join(seq):
                    total += p
            return total
        for q in (0.5, 0.3, 0.55, 0.9):
            for n in range(1, 13):
                for k in range(1, 7):
                    self.assertAlmostEqual(m._n84_streak_prob(q, n, k), brute(q, n, k), places=12, msg=(q, n, k))

    def test_streak_probability_equals_closed_recurrence_at_scale(self):
        q, n, k = 0.55, 100, 6
        a = [1.0] * k + [1 - q ** k]
        for i in range(k + 1, n + 1):
            a.append(a[i - 1] - (1 - q) * q ** k * a[i - k - 1])
        self.assertAlmostEqual(m._n84_streak_prob(q, n, k), 1 - a[n], places=10)

    def test_command_text(self):
        out = self.run_cmd('edge win=45% payoff=1.8 n=100 streak=6 risk=1%')
        self.assertIn('+0.260R', out)
        self.assertIn('Kelly fraction 14.4%', out)
        self.assertIn('72.9%', out)
        self.assertIn('5.9% of capital', out)                           # 1-(0.99)^6
        self.assertIn('NO edge', self.run_cmd('edge win=30% payoff=1'))


# ---------------------------------------------------------------- journal + stats
class TestJournal(AtlasCase):
    def add_three(self):
        self.run_cmd('journal add side=long sym=NIFTY entry=24500 exit=24580 lots=2 stop=24440 tag=breakout date=2026-09-28')
        self.run_cmd('journal add side=long sym=NIFTY entry=24600 exit=24550 lots=1 stop=24540 tag=breakout date=2026-09-29')
        self.run_cmd('journal add side=short sym=NIFTY entry=24500 exit=24450 lots=3 stop=24540 tag=fade date=2026-10-01')

    def test_stats_match_hand_calculation(self):
        self.add_three()
        # pnl: +80*130 = 10,400 ; -50*65 = -3,250 ; +50*195 = 9,750 ; R: 80/60, -50/60, 50/40
        st = m._n84_trade_stats(m._n84_trades(self.cid))
        self.assertEqual((st['n'], st['wins'], st['losses']), (3, 2, 1))
        self.assertAlmostEqual(st['total'], 16900)
        self.assertAlmostEqual(st['win_rate'], 200 / 3.0)
        self.assertAlmostEqual(st['avg_win'], 10075)
        self.assertAlmostEqual(st['avg_loss'], -3250)
        self.assertAlmostEqual(st['payoff'], 10075 / 3250)
        self.assertAlmostEqual(st['profit_factor'], 20150 / 3250)
        self.assertAlmostEqual(st['expectancy'], 16900 / 3)
        self.assertAlmostEqual(st['max_drawdown'], 3250)
        self.assertEqual(st['longest_loss_streak'], 1)
        self.assertAlmostEqual(st['avg_r'], (80 / 60 - 50 / 60 + 50 / 40) / 3)

    def test_stats_command_filters_and_tags(self):
        self.add_three()
        all_ = self.run_cmd('stats')
        self.assertIn('3 trades', all_)
        self.assertIn('₹16,900', all_)
        self.assertIn('breakout 2 trades ₹7,150', all_)
        self.assertIn('Only 3 trades', all_)
        self.assertIn('2 trades', self.run_cmd('stats tag=breakout'))
        self.assertIn('1 trades', self.run_cmd('stats tag=fade'))
        recent = self.run_cmd('stats days=2')                              # today is 2 Oct: 30 Sep onwards -> only the 1 Oct trade
        self.assertIn('1 trades', recent)
        self.assertIn('No journalled trades', self.run_cmd('stats tag=nothing'))

    def test_drawdown_peak_to_trough(self):
        pnls = [100, -300, 50, 400, -100, -100, 20]
        st = m._n84_trade_stats([{'pnl': p, 'ts': i, 'r': None} for i, p in enumerate(pnls)])
        # equity: 100, -200, -150, 250, 150, 50, 70 -> peak 250 then trough 50 = 200 ; start->(-200) from peak 100 = 300
        self.assertEqual(st['max_drawdown'], 300)
        self.assertEqual(st['longest_loss_streak'], 2)

    def test_empty_stats(self):
        self.assertEqual(m._n84_trade_stats([]), {'n': 0})
        self.assertIn('empty', self.run_cmd('journal list'))

    def test_add_validations(self):
        bad = ['journal add side=long entry=24500 exit=24580 lots=1',                                   # no lot / sym
               'journal add side=up sym=NIFTY entry=1 exit=2 lots=1',
               'journal add side=long sym=NIFTY entry=24500 exit=24580 lots=1 stop=24500',            # stop == entry
               'journal add side=long sym=NIFTY entry=24500 exit=24580 lots=1 date=2027-01-01',       # future
               'journal add side=long sym=NIFTY entry=24500 exit=24580 lots=1 bogus=1',
               'journal add side=long sym=NIFTY entry=0 exit=24580 lots=1',
               'journal frobnicate']
        for line in bad:
            with self.assertRaises(ValueError, msg=line):
                self.run_cmd(line)
        self.assertEqual(m._n84_trades(self.cid), [])

    def test_fees_override_and_configured_charges(self):
        self.run_cmd('journal add side=long sym=NIFTY entry=24500 exit=24580 lots=2 fees=500')
        self.assertAlmostEqual(m._n84_trades(self.cid)[0]['pnl'], 10400 - 500)
        self.run_cmd('config brokerage=20')
        self.run_cmd('journal add side=long sym=NIFTY entry=24500 exit=24580 lots=1')
        self.assertAlmostEqual(m._n84_trades(self.cid)[1]['pnl'], 80 * 65 - 40)

    def test_delete_list_and_isolation(self):
        out = self.run_cmd('journal add side=long sym=NIFTY entry=24500 exit=24580 lots=1 tag=t')
        tid = out.split()[2].rstrip(':')
        self.assertRegex(tid, r'^FD-[0-9A-F]{6}$')
        self.assertIn(tid, self.run_cmd('journal list'))
        self.assertEqual(m._n84_trades(999), [])                         # another chat sees nothing
        self.assertIn('No such trade', m._n84_exec(999, 'journal del ' + tid, NOW))
        self.assertIn('Deleted', self.run_cmd('journal del ' + tid))
        with self.assertRaises(ValueError):
            self.run_cmd('journal del not-an-id')

    def test_owner_reported_label(self):
        self.assertIn('Nemo did not place or verify this trade', self.run_cmd('journal add side=long sym=NIFTY entry=24500 exit=24580 lots=1'))


# ---------------------------------------------------------------- settings
class TestConfig(AtlasCase):
    def test_set_view_and_validation(self):
        self.assertIn('capital = ₹5,00,000', self.run_cmd('config capital=5L'))
        view = self.run_cmd('config')
        self.assertIn('capital = ₹5,00,000', view)
        self.assertIn('defaults are placeholders', view)
        for bad in ('config max_risk_pct=50', 'config capital=10', 'config expiry_weekday=sat', 'config nonsense=1', 'config roll_days=0', 'config rate=-1'):
            with self.assertRaises(ValueError, msg=bad):
                self.run_cmd(bad)
        self.assertEqual(m._n84_cfg(self.cid)['capital'], 500000)

    def test_expiry_weekday_setting_changes_calendar(self):
        self.run_cmd('config expiry_weekday=thu')
        self.assertIn('Thu 29 Oct 2026', self.run_cmd('expiry'))

    def test_charges_default_to_zero_never_invented(self):
        cfg = m._n84_cfg(self.cid)
        for k in ('brokerage', 'stt_sell_pct', 'exch_pct', 'sebi_per_cr', 'stamp_buy_pct', 'gst_pct', 'slip_pts'):
            self.assertEqual(cfg[k], 0.0, k)


# ---------------------------------------------------------------- dispatch + read-only facade
class TestDispatch(AtlasCase):
    def test_commands_are_instant_and_use_no_model(self):
        self.assertTrue(m._n84_dispatch(self.msg('/fut84 expiry sym=NIFTY')))
        self.assertIn('FUTURES EXPIRIES', self.sent[-1][1])
        self.assertEqual(self.fake.calls, [])
        self.assertTrue(m._n84_dispatch(self.msg('/fut84@nemo_bot help')))
        self.assertIn('NEMO FUTURES DESK', self.sent[-1][1])
        self.assertTrue(m._n84_dispatch(self.msg('/fut84')))

    def test_errors_are_friendly_with_an_example(self):
        m._n84_dispatch(self.msg('/fut84 size capital=5L'))
        self.assertTrue(self.sent[-1][1].startswith('❌'))
        self.assertIn('Example: /fut84 size', self.sent[-1][1])
        m._n84_dispatch(self.msg('/fut84 nonsense'))
        self.assertIn('unknown subcommand', self.sent[-1][1])

    def test_unexpected_exception_is_contained(self):
        with mock.patch.object(m, '_n84_exec', mock.Mock(side_effect=RuntimeError('boom'))):
            self.assertTrue(m._n84_dispatch(self.msg('/fut84 expiry')))
        self.assertIn('Nothing was changed', self.sent[-1][1])
        self.assertEqual(m._N84_STATS['errors'], 1)

    def test_owner_only(self):
        stranger = {'chat': {'id': 999, 'type': 'private'}, 'from': {'id': 999}, 'text': '/fut84 journal list'}
        self.assertFalse(m._n84_dispatch(stranger))
        group = {'chat': {'id': self.cid, 'type': 'group'}, 'from': {'id': self.cid}, 'text': '/fut84 help'}
        self.assertFalse(m._n84_dispatch(group))
        self.assertEqual(self.sent, [])

    def test_tool_facade_is_read_only(self):
        for line in ('journal add side=long sym=NIFTY entry=1 exit=2 lots=1', 'journal list', 'config capital=5L', 'alerts on', 'help', 'bogus'):
            with self.assertRaises(ValueError, msg=line):
                self.run_cmd(line, read_only=True)
        self.assertEqual(m._n84_trades(self.cid), [])
        self.assertIn('1 lot(s)', self.run_cmd('size capital=5L risk=5000 entry=24500 stop=24440 lot=65', read_only=True))

    def test_alert_setting_via_command(self):
        self.assertIn('OFF', self.run_cmd('alerts'))
        self.assertIn('ON', self.run_cmd('alerts on'))
        self.assertTrue(m._n84_alert_get(self.cid)[0])
        self.run_cmd('alerts off')
        self.assertFalse(m._n84_alert_get(self.cid)[0])


# ---------------------------------------------------------------- alerts
class TestAlerts(AtlasCase):
    def at(self, y, mo, d, h=8, mi=50):
        return dt.datetime(y, mo, d, h, mi)

    def test_compose_cases(self):
        self.assertIn('Expiry day', m._n84_alert_compose(self.cid, dt.datetime(2026, 10, 27, 8, 50)))
        self.assertIn('expire in 1 session', m._n84_alert_compose(self.cid, dt.datetime(2026, 12, 28, 8, 50)))
        self.assertIn('Roll window open: 4 sessions to OCT 2026', m._n84_alert_compose(self.cid, dt.datetime(2026, 10, 21, 8, 50)))
        self.assertIn('Tomorrow (Tue 10 Nov 2026) is a market holiday', m._n84_alert_compose(self.cid, dt.datetime(2026, 11, 9, 8, 50)))

    def test_quiet_when_nothing_matters_and_on_non_session_days(self):
        self.assertEqual(m._n84_alert_compose(self.cid, dt.datetime(2026, 10, 5, 8, 50)), '')       # 15 sessions to expiry
        self.assertEqual(m._n84_alert_compose(self.cid, dt.datetime(2026, 10, 2, 8, 50)), '')       # holiday
        self.assertEqual(m._n84_alert_compose(self.cid, dt.datetime(2026, 10, 3, 8, 50)), '')       # Saturday

    def test_tick_sends_once_per_day_inside_the_window_only(self):
        m._n84_alert_set(self.cid, enabled=True)
        self.assertEqual(m._n84_alert_tick(dt.datetime(2026, 10, 27, 7, 0)), 0)                     # before the window
        self.assertEqual(m._n84_alert_tick(dt.datetime(2026, 10, 27, 9, 30)), 0)                    # after the window
        self.assertEqual(m._n84_alert_tick(dt.datetime(2026, 10, 27, 8, 50)), 1)
        self.assertEqual(m._n84_alert_tick(dt.datetime(2026, 10, 27, 8, 55)), 0)                    # already sent today
        self.assertEqual(len([t for _, t in self.sent if 'FUTURES DESK' in t]), 1)
        self.assertEqual(m._n84_alert_tick(dt.datetime(2026, 12, 29, 8, 50)), 1)                    # next day it works again

    def test_disabled_and_nothing_to_say(self):
        self.assertEqual(m._n84_alert_tick(dt.datetime(2026, 10, 27, 8, 50)), 0)                    # not enabled
        m._n84_alert_set(self.cid, enabled=True)
        self.assertEqual(m._n84_alert_tick(dt.datetime(2026, 10, 5, 8, 50)), 0)                     # nothing to say
        self.assertEqual(m._n84_alert_get(self.cid)[1], '2026-10-05')                               # but marked: no retry spam
        self.assertEqual(self.sent, [])

    def test_failed_send_is_not_retried(self):
        m._n84_alert_set(self.cid, enabled=True)
        with mock.patch.object(m, 'send_text', mock.Mock(side_effect=RuntimeError('net'))):
            with self.assertRaises(RuntimeError):
                m._n84_alert_tick(dt.datetime(2026, 10, 27, 8, 50))
        self.assertEqual(m._n84_alert_tick(dt.datetime(2026, 10, 27, 8, 51)), 0)


# ---------------------------------------------------------------- instant answers
class TestInstantAnswers(AtlasCase):
    def test_arithmetic(self):
        cases = {'what is 1250*18/100': '1250*18/100 = 225', '18% of 1250': '18% of 1250 = 225', '2+2': '2+2 = 4',
                 'calculate (1250 x 3) / 4': '(1250 x 3) / 4 = 937.5', '1,250 * 3': '1,250 * 3 = 3750', '2^10': '2^10 = 1024',
                 'what is 5% of 2,00,000?': '5% of 2,00,000 = 10000', '10 / 4 =': '10 / 4 = 2.5'}
        for text, want in cases.items():
            self.assertEqual(m._n84_instant_math(text), want, text)
        self.assertEqual(m._n84_instant_math('1250*140'), '1250*140 = 175000  (1,75,000)')
        self.assertEqual(m._n84_instant_math('what is 12/3'), '12/3 = 4')                    # an explicit prefix makes a bare fraction a question

    def test_not_arithmetic(self):
        for text in ('2026-10-02', '10-12-2026', 'call me at 98765-43210', '2026', 'hello', '12', '5 apples + 3', 'what is love', '1/0', '9**9**9',
                     '', '12-5', 'x', '1 +', 'tell me about 5% growth', '10/10/2026', '5/6', '12 / 3'):
            self.assertIsNone(m._n84_instant_math(text), repr(text))

    def test_dates(self):
        self.assertEqual(m._n84_instant_date('what day is 25 dec 2026'), 'Friday, 25 December 2026')
        self.assertTrue(m._n84_instant_date('what is the date today').startswith('Friday, 02 October 2026, 12:00 IST'))
        self.assertTrue(m._n84_instant_date('aaj ki date').startswith('Friday, 02 October 2026'))
        self.assertIn('84 days until Friday, 25 December 2026', m._n84_instant_date('days until 2026-12-25'))
        self.assertEqual(m._n84_instant_date('next monday'), 'Monday, 05 October 2026')
        self.assertEqual(m._n84_instant_date('today + 45 days'), 'Monday, 16 November 2026')
        for phrase in ('what date will it be in 45 days', 'which date is it 45 days from now', 'what is the date after 45 days', 'what date will it be 45 days later'):
            self.assertEqual(m._n84_instant_date(phrase + '?'), 'Monday, 16 November 2026', phrase)
        self.assertEqual(m._n84_instant_date('what date was it 10 days ago'), 'Tuesday, 22 September 2026')
        self.assertIn('84 days until Friday, 25 December 2026', m._n84_instant_date('how many days until 25 dec 2026'))
        self.assertIn('days since', m._n84_instant_date('how many days since 1 jan 2026'))

    def test_not_dates(self):
        for text in ('tomorrow', 'today', 'I will call you tomorrow', 'what is the date of the meeting', 'date', 'time', 'weekday of banana', 'in 5 minutes',
                     'what date will it be in a while', 'how many days do I have to wait for the parcel'):
            self.assertIsNone(m._n84_instant_date(text), repr(text))

    def test_dispatch_answers_with_zero_model_calls_and_records_history(self):
        self.assertTrue(m._n84_dispatch(self.msg('what is 18% of 1250')))
        self.assertEqual(self.sent[-1][1], '18% of 1250 = 225')
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(m.HISTORY[self.cid][-1]['content'], '18% of 1250 = 225')
        self.assertEqual(m._N84_STATS['instant'], 1)
        self.assertTrue(m._n84_dispatch(self.msg('futures expiry')))
        self.assertIn('FUTURES EXPIRIES', self.sent[-1][1])
        self.assertTrue(m._n84_dispatch(self.msg('nifty futures expiry')))
        self.assertIn('NSE:NIFTY26OCTFUT', self.sent[-1][1])

    def test_never_hijacks_a_pending_flow(self):
        m.HISTORY[self.cid] = [{'role': 'user', 'content': 'remind me'}, {'role': 'assistant', 'content': 'How many hours from now?'}]
        self.assertFalse(m._n84_dispatch(self.msg('2+2')))                       # the reply belongs to the question just asked
        m.HISTORY[self.cid] = []
        with mock.patch.object(m, '_n84_pending', lambda cid: True):
            self.assertFalse(m._n84_dispatch(self.msg('2+2')))
        self.assertEqual(self.sent, [])
        self.assertTrue(m._n84_dispatch(self.msg('2+2')))

    def test_switch_off(self):
        m._n83_set_flag(self.cid, 'instant', False)
        self.assertFalse(m._n84_dispatch(self.msg('2+2')))

    def test_awaiting_reply_detector(self):
        for last, want in (('Want a prep checklist?', True), ('Want a prep checklist? ', True), ('Done.', False), ('Is it "ok"?"', True)):
            m.HISTORY[self.cid] = [{'role': 'assistant', 'content': last}]
            self.assertEqual(m._n84_awaiting_reply(self.cid), want, last)
        m.HISTORY[self.cid] = []
        self.assertFalse(m._n84_awaiting_reply(self.cid))

    def test_flags_toggle_through_cortex_command(self):
        m._n83_dispatch(self.msg('/cortex83 fastpath off'))
        self.assertFalse(m._n83_flag(self.cid, 'fastpath'))
        m._n83_dispatch(self.msg('/cortex83 instant off'))
        self.assertFalse(m._n83_flag(self.cid, 'instant'))
        self.assertIn('Router fast-path', self.sent[-2][1])


# ---------------------------------------------------------------- router bypass
class TestRouterBypass(AtlasCase):
    PLAIN = ('should I hire another salesman for the showroom', 'I feel tired today', 'explain GST in simple words', 'thanks that helped a lot',
             'mera mood kharab hai', 'what do you think about my decision to wait a month', 'why is the sky blue')
    ACTION = ('remind me to call Rahul at 5', 'send this to Rahul', 'download this video', 'make me a pdf of this', 'research solar panels', 'should I buy nifty today',
              'plan my week', 'remember that my locker code changed', 'forget my old address', 'cancel the task', 'what is the status of my report', 'always reply in hindi',
              'rahul ko mail bhej do', 'play some music', 'create a project for the showroom', 'open google and find prices', 'check my vpn', 'whatsapp him',
              'https://example.com/a is this safe', 'mail me@example.com the notes', 'run `ls`', 'compare phone models', 'update yourself', 'show my portfolio')

    def test_plain_conversation_skips_router(self):
        for text in self.PLAIN:
            self.assertTrue(m._n84_plain_chat(self.cid, text), text)

    def test_action_words_always_go_to_the_router(self):
        for text in self.ACTION:
            self.assertFalse(m._n84_plain_chat(self.cid, text), text)

    def test_deny_list_does_not_swallow_ordinary_words(self):
        # regression: a stray "fort?" alternative once matched the word "for" and disabled the fast path
        for text in ('what is a good gift for my wife', 'I am looking for ideas', 'thanks for the help yesterday', 'is it fine for a beginner'):
            self.assertTrue(m._n84_plain_chat(self.cid, text), text)

    def test_help_strings_show_a_single_percent_sign(self):
        out = self.run_cmd('size capital=5L risk=5000 entry=24500 stop=24440 lot=65')
        self.assertIn('margin=<% of notional>', out)
        self.assertNotIn('%%', out)
        chk = self.run_cmd('check side=long entry=24500 stop=24440 lots=1 lot=65 capital=5L', now=dt.datetime(2026, 10, 6, 10, 0))
        self.assertIn('margin=<%>', chk)
        self.assertNotIn('%%', chk)
        for line in ('expiry sym=NIFTY', 'basis spot=24500 fut=24590 days=26', 'roll near=24590 next=24680 days=27', 'edge win=45% payoff=1.8 risk=1%', 'config', 'help'):
            self.assertNotIn('%%', self.run_cmd(line), line)

    def test_guards(self):
        self.assertFalse(m._n84_plain_chat(self.cid, 'x' * 301))
        self.assertFalse(m._n84_plain_chat(self.cid, '/help'))
        m.HISTORY[self.cid] = [{'role': 'assistant', 'content': 'Which showroom do you mean?'}]
        self.assertFalse(m._n84_plain_chat(self.cid, 'the one in Surat'))                   # answer to a clarification -> router resumes the goal
        m.HISTORY[self.cid] = []
        m._n83_set_flag(self.cid, 'fastpath', False)
        self.assertFalse(m._n84_plain_chat(self.cid, 'I feel tired today'))

    def test_decide_wrapper_skips_prev_for_plain_and_calls_it_for_actions(self):
        prev = mock.Mock(return_value={'route': 'legacy'})
        with mock.patch.object(m, '_N84_DECIDE_PREV', prev):
            self.assertEqual(m._n72_decide(self.cid, 'I feel tired today', ''), {'route': 'chat80'})
            prev.assert_not_called()
            self.assertEqual(m._n72_decide(self.cid, 'remind me to call Rahul', ''), {'route': 'legacy'})
            prev.assert_called_once()
        self.assertEqual(m._N84_STATS['router_skips'], 1)

    def test_smalltalk_stays_on_v83_fast_path_even_when_fastpath_off(self):
        m._n83_set_flag(self.cid, 'fastpath', False)
        with mock.patch.object(m, '_N83_DECIDE_PREV', mock.Mock(return_value={'route': 'legacy'})):
            self.assertEqual(m._n72_decide(self.cid, 'Hi Nemo!', ''), {'route': 'chat80'})
        self.assertEqual(m._N83_STATS['smalltalk_skips'], 1)

    def test_futures_questions_reach_cortex_but_orders_do_not(self):
        yes = ('how many lots of nifty futures can I take with 5L risking 1%', 'what is the basis on bank nifty futures', 'size a futures trade with stop 60 points',
               'when does the futures expiry roll window open', 'what is my p&l on nifty fut if it closes at 24580')
        no = ('buy 1 lot nifty futures', 'sell banknifty futures now', 'please place an order for nifty futures', 'my future plans are bright')
        prev = mock.Mock(return_value={'route': 'legacy'})
        with mock.patch.object(m, '_N84_DECIDE_PREV', prev):
            for text in yes:
                self.assertEqual(m._n72_decide(self.cid, text, ''), {'route': 'chat80'}, text)
            prev.assert_not_called()
            for text in no:
                self.assertEqual(m._n72_decide(self.cid, text, ''), {'route': 'legacy'}, text)

    def test_futures_routing_respects_tools_switch(self):
        m._n83_set_flag(self.cid, 'tools', False)
        prev = mock.Mock(return_value={'route': 'legacy'})
        with mock.patch.object(m, '_N84_DECIDE_PREV', prev):
            self.assertEqual(m._n72_decide(self.cid, 'how many lots of nifty futures can I take', ''), {'route': 'legacy'})

    def test_router_failure_never_blocks(self):
        with mock.patch.object(m, '_n84_plain_chat', mock.Mock(side_effect=RuntimeError('x'))), \
                mock.patch.object(m, '_N84_DECIDE_PREV', mock.Mock(return_value={'route': 'legacy'})):
            self.assertEqual(m._n72_decide(self.cid, 'I feel tired', ''), {'route': 'legacy'})


# ---------------------------------------------------------------- parallel tools, typing, timings
class TestSpeedMechanics(AtlasCase):
    def test_tools_of_a_round_run_in_parallel_and_keep_order(self):
        def slow_search(cid, q):
            time.sleep(0.3)
            return [{'title': q, 'url': 'https://x.example/' + q.split()[0], 'excerpt': 'e'}]
        needs = [{'tool': 'search', 'input': 'alpha topic'}, {'tool': 'search', 'input': 'beta topic'}, {'tool': 'search', 'input': 'gamma topic'}]
        with mock.patch.object(m, '_n83_tool_search', slow_search):
            t0 = time.monotonic()
            ev = m._n83_run_tools(self.cid, needs, True)
            elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 0.7)                                      # sequential would be >= 0.9 s
        self.assertEqual([e['input'] for e in ev], ['alpha topic', 'beta topic', 'gamma topic'])
        self.assertEqual(m._N84_STATS['parallel_rounds'], 1)

    def test_one_failing_tool_does_not_sink_the_round(self):
        needs = [{'tool': 'calculate', 'input': '2+2'}, {'tool': 'futures', 'input': 'size capital=5L'}, {'tool': 'date', 'input': 'today + 1 days'}]
        ev = m._n83_run_tools(self.cid, needs, True)
        self.assertEqual([e['ok'] for e in ev], [True, False, True])
        self.assertIn('ValueError', ev[1]['output'])

    def test_single_tool_round_is_not_threaded(self):
        m._n83_run_tools(self.cid, [{'tool': 'calculate', 'input': '1+1'}], True)
        self.assertEqual(m._N84_STATS['parallel_rounds'], 0)

    def test_typing_keepalive_pings_then_stops(self):
        pings = []
        with mock.patch.object(m, 'tg', lambda *a, **k: pings.append(time.monotonic())):
            with m._N84Typing(self.cid, interval=0.05):
                time.sleep(0.32)
            time.sleep(0.1)                                                    # let an in-flight ping land
            n = len(pings)
            time.sleep(0.25)
        self.assertGreaterEqual(n, 4)
        self.assertEqual(len(pings), n)                                     # nothing after the turn ended

    def test_chat_wrapper_keeps_typing_alive_during_the_turn(self):
        pings = []
        real = m._N84Typing

        def slow_core(msg):
            time.sleep(0.3)
            return {'ok': True, 'text': 'done'}
        with mock.patch.object(m, 'tg', lambda *a, **k: pings.append(1)), mock.patch.object(m, '_n83_chat_core', slow_core), \
                mock.patch.object(m, '_N84Typing', lambda cid: real(cid, 0.05)):
            out = m._n83_chat(self.msg('hello there friend'))
        self.assertEqual(out['text'], 'done')
        self.assertGreaterEqual(len(pings), 3)

    def test_stage_timings_are_recorded_and_shown(self):
        self.fake.when(lambda r, t: True, 'fine')
        m._n83_chat(self.msg('tell me a short joke about cats'))
        ms = m._N83_LAST[self.cid]['checks']['ms']
        for key in ('answer', 'verify', 'total'):
            self.assertIn(key, ms)
        self.assertRegex(m._n83_why_text(self.cid), r'Time: .*answer \d+\.\ds')
        status = m._n83_status_text(self.cid)
        self.assertIn('SPEED 84', status)
        self.assertRegex(status, r'p50 \d+\.\ds · p95 \d+\.\ds')
        self.assertIn('Futures Desk', status)


# ---------------------------------------------------------------- weekday / date audit
class TestDateAudit(AtlasCase):
    def test_wrong_weekday_is_found(self):
        bad = m._n84_date_audit('The expiry is Thursday, 29 October 2026.')               # 29 Oct 2026 is a Thursday -> fine
        self.assertEqual(bad, [])
        bad = m._n84_date_audit('Christmas is on Thursday, 25 December 2026.')           # it is a Friday
        self.assertEqual(len(bad), 1)
        self.assertEqual((bad[0]['stated'], bad[0]['correct'], bad[0]['expr']), ('Thursday', 'Friday', '25 December 2026'))

    def test_all_supported_shapes(self):
        wrong = ['Mon, 25 Dec 2026', 'Monday 25th December 2026', 'Monday, December 25, 2026', '25 December 2026 (Monday)', '2026-12-25 (Monday)']
        for text in wrong:
            self.assertEqual(len(m._n84_date_audit(text)), 1, text)
        right = ['Fri, 25 Dec 2026', 'Friday 25th December 2026', 'Friday, December 25, 2026', '25 December 2026 (Friday)', '2026-12-25 (Friday)',
                 'Mon 5 October 2026', 'Tuesday, 26 January 2027']
        for text in right:
            self.assertEqual(m._n84_date_audit(text), [], text)

    def test_ignores_what_it_cannot_judge(self):
        for text in ('Friday, 31 February 2026', 'Friday, 25 December', 'Friday the 25th', 'on Friday we meet', 'Friday, 25 Smarch 2026', ''):
            self.assertEqual(m._n84_date_audit(text), [], text)

    def test_duplicate_claims_flagged_once(self):
        self.assertEqual(len(m._n84_date_audit('Thursday, 25 December 2026 ... again Thursday, 25 December 2026')), 1)

    def test_cortex_repairs_a_wrong_weekday(self):
        self.fake.when(lambda r, t: 'check failed' in t, 'Christmas 2026 falls on Friday, 25 December 2026.')
        self.fake.when(lambda r, t: True, 'Christmas 2026 falls on Thursday, 25 December 2026.')
        out = m._n83_chat(self.msg('when is christmas this year'))
        self.assertIn('Friday, 25 December 2026', out['text'])
        self.assertEqual(m._N84_STATS['date_flagged'], 1)
        self.assertEqual(m._N83_STATS['arith_repaired'], 1)
        repair = self.fake.of('check failed')[0]['text']
        self.assertIn('"25 December 2026 is a Thursday" is wrong: it is a Friday', repair)

    def test_unrepaired_weekday_is_flagged_visibly(self):
        self.fake.when(lambda r, t: True, 'Christmas 2026 falls on Thursday, 25 December 2026.')
        out = m._n83_chat(self.msg('when is christmas this year'))
        self.assertIn('Date check: 25 December 2026 is a Friday (not Thursday)', out['text'])

    def test_arithmetic_and_dates_together(self):
        issues = m._n84_issue_note({'kind': 'weekday', 'expr': '25 December 2026', 'stated': 'Thursday', 'correct': 'Friday'})
        self.assertIn('is a Thursday', issues)
        self.assertIn('exact value is 225', m._n84_issue_note({'expr': '18% of 1250', 'stated': '250', 'correct': '225'}))


# ---------------------------------------------------------------- futures through Cortex
class TestFuturesThroughCortex(AtlasCase):
    def scout_with(self, line):
        def scout_reply(role, text, messages):
            return json.dumps({'need': []}) if 'Evidence so far' in text else json.dumps({'need': [{'tool': 'futures', 'input': line}]})
        self.fake.when(lambda r, t: 'tool scout' in t, scout_reply)

    def test_scout_tool_runs_calculator_and_answer_sees_exact_output(self):
        self.scout_with('size capital=5L risk=1% entry=24500 stop=24440 sym=NIFTY')
        self.fake.when(lambda r, t: True, 'You can take 1 lot.')
        out = m._n83_chat(self.msg('how many lots of nifty futures can I take with 5L risking 1%, entry 24500 stop 24440?'))
        self.assertTrue(out['ok'])
        final = next(c for c in self.fake.calls if answer_stage(c['messages']))
        joined = '\n'.join(str(x['content']) for x in final['messages'])                  # decoded text, not JSON-escaped
        self.assertIn('futures "size capital=5L risk=1% entry=24500 stop=24440 sym=NIFTY"', joined)
        self.assertIn('1 lot(s) by risk', joined)
        self.assertIn('futures "size', m._n83_why_text(self.cid))
        self.assertEqual(m._N84_STATS['futures_calls'], 1)

    def test_scout_cannot_use_write_subcommands_or_unknown_params(self):
        for line in ('journal add side=long sym=NIFTY entry=24500 exit=24580 lots=1', 'config capital=1', 'alerts on', 'size capital=5L evil=1', 'rm -rf /'):
            self.assertEqual(m._n83_validate_needs({'need': [{'tool': 'futures', 'input': line}]}), [], line)

    def test_even_if_validation_were_bypassed_the_runner_is_read_only(self):
        ev = m._n83_run_tools(self.cid, [{'tool': 'futures', 'input': 'journal add side=long sym=NIFTY entry=24500 exit=24580 lots=1'}], True)
        self.assertFalse(ev[0]['ok'])
        self.assertEqual(m._n84_trades(self.cid), [])

    def test_natural_language_futures_question_end_to_end(self):
        self.scout_with('size capital=5L risk=1% entry=24500 stop=24440 sym=NIFTY')
        self.fake.when(lambda r, t: 'intent router' in t, '{"route":"legacy"}')           # would be wrong: must never be asked
        self.fake.when(lambda r, t: True, 'One lot.')
        result = m._n72_task(self.msg('how many lots of nifty futures can I take with 5L risking 1%, entry 24500 stop 24440?'))
        self.assertEqual(result['text'], 'One lot.')
        self.assertEqual(self.fake.of('intent router'), [], 'router model call should have been skipped')
        self.assertTrue(self.fake.of('tool scout'))

    def test_tool_failure_becomes_visible_evidence(self):
        self.scout_with('size capital=5L')                                              # missing entry/stop
        self.fake.when(lambda r, t: True, 'I need your entry and stop.')
        m._n83_chat(self.msg('how many lots of nifty futures with 5L?'))
        final = next(c for c in self.fake.calls if answer_stage(c['messages']))
        self.assertIn('FAILED', json.dumps(final['messages']))

    def test_prompt_tells_the_model_not_to_invent_trading_facts(self):
        self.fake.when(lambda r, t: True, 'x')
        m._n83_chat(self.msg('tell me something kind'))
        system = next(c for c in self.fake.calls if answer_stage(c['messages']))['messages'][0]['content']
        self.assertIn('never invent live prices', system)
        self.assertIn('cannot place orders', system)


# ---------------------------------------------------------------- hooks, regression, safety
class TestAtlasIntegration(AtlasCase):
    def test_handle_wrapper_routes_commands_and_passes_the_rest(self):
        seen = []
        with mock.patch.object(m, '_N84_HANDLE_PREV', lambda msg: seen.append(msg['text'])):
            m.handle(self.msg('/fut84 help'))
            m.handle(self.msg('what is 2+2'))
            m.handle(self.msg('please remind me tomorrow'))
        self.assertEqual(seen, ['please remind me tomorrow'])
        self.assertEqual(len(self.sent), 2)

    def test_regression_rows_green_and_no_new_failures(self):
        with mock.patch.object(m, '_N35_DB', base.ORIG_DB):
            m._N83_SCHEMA['path'] = None
            m._N84_SCHEMA['path'] = None
            r = m.prime_regression_suite()
        v84 = [t for t in r['tests'] if t['name'].startswith('v84-')]
        self.assertGreaterEqual(len(v84), 20)
        self.assertEqual([t['name'] for t in v84 if not t['ok']], [])
        env_only = {'v36-daycard-render', 'v36-infographic-render', 'v39-toggle', 'v54-internet-contract', 'v58-eventbus'}
        failing = {t['name'] for t in r['tests'] if not t['ok']}
        self.assertLessEqual(failing, env_only, sorted(failing - env_only))
        self.assertEqual(r['version'], '84.0')

    def test_capabilities_text(self):
        self.assertIn('Futures Desk 84', m._n82_capabilities())
        self.assertIn('Cortex 83', m._n82_capabilities())

    def test_self_dev_editor_cannot_touch_atlas(self):
        for name in ('_n84_exec', '_n84_dispatch', '_n84_plain_chat'):
            self.assertFalse(m._n79_editable(name), name)

    def test_main_wrapper_bootstraps_and_survives_failure(self):
        ran = []
        with mock.patch.object(m, '_N84_MAIN_PREV', lambda: ran.append('main')), mock.patch.object(m, '_n84_ensure_alert_thread', lambda: ran.append('alerts')):
            m.main()
        self.assertEqual(ran, ['alerts', 'main'])
        ran.clear()
        with mock.patch.object(m, '_N84_MAIN_PREV', lambda: ran.append('main')), mock.patch.object(m, '_n84_bootstrap', mock.Mock(side_effect=RuntimeError('x'))):
            m.main()
        self.assertEqual(ran, ['main'])

    def test_version_and_update_gate(self):
        src = open(base.NEMO_FILE, encoding='utf-8').read()
        self.assertEqual(m._extract_version(src), '84.0')
        ok, err = m._compile_check(src)
        self.assertTrue(ok, err)


class TestAdvisoryOnlyGuarantee(unittest.TestCase):
    """The Futures Desk must never be able to place, modify or simulate an order or touch a broker, the network or a shell."""

    @staticmethod
    def block():
        src = open(base.NEMO_FILE, encoding='utf-8').read()
        return src[src.index('# NEMO 84 - ATLAS'):src.index("\nif __name__ == '__main__':")]

    def test_v84_block_has_no_order_broker_network_or_shell_identifiers(self):
        import ast
        tree = ast.parse(self.block())
        used = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                used.add(node.attr)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                used.update(a.name.split('.')[0] for a in node.names)
                if isinstance(node, ast.ImportFrom) and node.module:
                    used.add(node.module.split('.')[0])
        forbidden = {'fyers_place', 'fyers_login', 'fyers_ready', 'fyers_ltp', 'fyers_depth', 'fyers_quote_live', 'live_ltp', 'BROKER', 'TradeLab75',
                     'act_log', 'auto_trade_tick', 'requests', 'urllib', 'urlopen', 'subprocess', 'socket', 'system', 'popen', 'open', 'exec', 'eval',
                     '__import__', 'os', 'shutil'}
        self.assertEqual(sorted(used & forbidden), [], 'v84 block must stay advisory-only')

    def test_only_read_helpers_are_borrowed_from_trading_code(self):
        import re
        borrowed = set(re.findall(r'\b(lot_size|_n81_[A-Za-z_0-9]+|_N81_[A-Z_0-9]+|_p75_[a-z_0-9]+|_P75_[A-Z_0-9]+|_n75_[a-z_0-9]+)\b', self.block()))
        self.assertEqual(borrowed, {'lot_size', '_n81_session', '_N81_HOLIDAYS_2026'})


if __name__ == '__main__':
    unittest.main()
