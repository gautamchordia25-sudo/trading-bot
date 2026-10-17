"""Nemo v96 Ledger: the read-only record of what the stock-market agent has traded: charges, numbers, the plain-words ledger, one trade in full, CSV, chart, the explanation of the agent's logic,
the observer on the agent's tick, the day-end line, the front door and the guarantee that the layer never changes what the agent does.

Offline. The agent's own tick runs for real in one test (with the broker, quotes and calendar stubbed); no network, no broker, no order.

    NEMO_FILE=/path/to/nemotron_bot.py python -m unittest tests.test_ledger96 -v
"""
import ast
import copy
import csv
import datetime as dt
import io
import json
import os
import re
import time
import unittest
from unittest import mock

from tests import test_cortex83 as base
from tests.test_scout93 import ScoutCase
from tests.test_forge91 import OWNER_ID

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
SYM = 'NSE:NIFTY26O0622550PE'


def setUpModule():
    if base.m is None:
        base.setUpModule()


def v96_source():
    src = bot_source()
    i = src.index('# NEMO 96 - LEDGER')
    j = src.index('# NEMO 97 - DESK') if '# NEMO 97 - DESK' in src else src.rindex("if __name__")       # (the next layer is not part of this one)
    return src[i:j]


def bot_source():
    with open(base.NEMO_FILE, encoding='utf-8') as f:
        return f.read()


D0 = dt.date(2026, 10, 5)                                    # "today" in these tests: the day of the owner's screenshot (a Monday; the contract in it expires on the 6th)


def ist_ts(days_ago=0, hh=11, mm=0, today=None):
    d = (today or D0) - dt.timedelta(days=days_ago)
    return dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=IST).timestamp()


def trade(sym=SYM, entry=77.8, exit=122.7, qty=65, mode='shadow', reason='target', days_ago=0, hh=11, mm=0, why='AI NIFTY: strong trend (conf 7/10)', brain='ai'):
    return {'sym': sym, 'entry': entry, 'exit': exit, 'qty': qty, 'pnl': round((exit - entry) * qty, 1), 'why': why, 'exit_reason': reason, 'brain': brain, 'mode': mode, 't': ist_ts(days_ago, hh, mm), 'bracket': False}


class LedgerCase(ScoutCase):
    def setUp(self):
        super().setUp()
        m = self.m
        for table in ('ledger96_trade', 'ledger96_entry', 'ledger96_setting'):
            m._n96_q('DELETE FROM %s' % table, write=True)
        for k in m._N96_STATS:
            m._N96_STATS[k] = 0
        self.log = []
        self.start(m, 'AUTOLOG', self.log)
        self.start(m, 'send_mono', lambda cid, text: self.mono.append((cid, text)))
        self.mono = []
        self.files = []

        def doc(cid, path, name, mime):
            with open(path, 'rb') as f:
                self.files.append((cid, path, name, mime, f.read()))
            return True
        self.start(m, 'send_document', doc)
        self.images = []
        self.start(m, '_n90_send_image', lambda cid, raw, name, caption='', kb=None, force_file=False: self.images.append((cid, raw, name, caption)) or True)
        self.start(m, 'fyers_today', lambda: D0.isoformat())
        self.start(m, '_n96_now', lambda: ist_ts(0, 16, 0))
        self.guest = lambda text, **k: dict({'chat': {'id': 5552, 'type': 'private'}, 'from': {'id': 5552, 'first_name': 'Asha'}, 'message_id': 3, 'text': text}, **k)

    def add(self, *trades):
        self.log.extend(trades)
        return trades

    def load(self, mode=None):
        rows = self.m._n96_load()
        return [t for t in rows if not t['void'] and (mode is None or t['mode'] == mode)]


# ===================================================================================================================
# 1. CHARGES, MONEY, NUMBERS
# ===================================================================================================================
class TestCharges(LedgerCase):
    def test_the_screenshot_trade_costs_about_65_rupees_and_the_parts_add_up(self):
        p = self.m._n96_charge_parts(SYM, 65, 77.8, 122.7)
        self.assertAlmostEqual(p['brokerage'], 40.0, 2)
        self.assertAlmostEqual(p['stt'], 0.0015 * 122.7 * 65, 2)                       # 0.15% of the sell side
        self.assertAlmostEqual(p['exchange'], 0.0003503 * (77.8 + 122.7) * 65, 2)
        self.assertAlmostEqual(p['stamp'], 0.00003 * 77.8 * 65, 3)
        self.assertAlmostEqual(p['gst'], 0.18 * (p['brokerage'] + p['exchange'] + p['sebi']), 4)
        self.assertAlmostEqual(p['total'], p['brokerage'] + p['stt'] + p['exchange'] + p['sebi'] + p['stamp'] + p['gst'], 6)
        self.assertAlmostEqual(p['total'], 64.71, 1)

    def test_charges_can_be_switched_off_and_edited(self):
        c = dict(self.m._N96_COSTS_DEFAULT, on=0.0)
        self.assertEqual(self.m._n96_charge_parts(SYM, 65, 77.8, 122.7, c)['total'], 0.0)
        c = dict(self.m._N96_COSTS_DEFAULT, brokerage=0.0, stt_opt=0.0, exch_opt=0.0, sebi=0.0, stamp=0.0)
        self.assertEqual(self.m._n96_charge_parts(SYM, 65, 77.8, 122.7, c)['total'], 0.0)

    def test_shares_use_the_share_rates_and_the_percent_brokerage_cap(self):
        p = self.m._n96_charge_parts('NSE:SBIN-EQ', 10, 1000, 1010)
        self.assertAlmostEqual(p['brokerage'], 3.0 + 3.03, 2)                           # 0.03% of each side, below the Rs 20 flat fee
        self.assertAlmostEqual(p['stt'], 0.00025 * 10100, 3)
        big = self.m._n96_charge_parts('NSE:SBIN-EQ', 1000, 1000, 1010)
        self.assertAlmostEqual(big['brokerage'], 40.0, 2)

    def test_money_format_uses_indian_grouping_and_signs(self):
        f = self.m._n96_inr
        self.assertEqual(f(1234567, True), '+₹12,34,567')
        self.assertEqual(f(-2918), '-₹2,918')
        self.assertEqual(f(2918.5, True), '+₹2,918')
        self.assertEqual(f(0.2, True), '₹0')                                             # no "+₹0" / "-₹0"
        self.assertEqual(f(-0.2), '₹0')
        self.assertEqual(f(999), '₹999')
        self.assertEqual(f(None), 'n/a')

    def test_win_rate_range_known_values(self):
        w = self.m._n96_wilson
        lo, hi = w(1, 1)
        self.assertAlmostEqual(lo, 0.2065, 3)
        self.assertEqual(hi, 1.0)
        lo, hi = w(5, 10)
        self.assertAlmostEqual(lo, 0.2366, 3)
        self.assertAlmostEqual(hi, 0.7634, 3)
        self.assertEqual(w(0, 0), (0.0, 1.0))
        lo, hi = w(60, 100)
        self.assertTrue(0.50 < lo < 0.51 and 0.69 < hi < 0.70)

    def test_expiry_date_of_weekly_symbols(self):
        e = self.m._n96_expiry
        self.assertEqual(e('NSE:NIFTY26O0622550PE'), dt.date(2026, 10, 6))
        self.assertEqual(e('NSE:NIFTY2610622500CE'), dt.date(2026, 1, 6))                # month digit 1 = January
        self.assertEqual(e('BSE:SENSEX26N1081500CE'), dt.date(2026, 11, 10))
        self.assertEqual(e('NSE:NIFTY26D0122000PE'), dt.date(2026, 12, 1))
        self.assertIsNone(e('NSE:NIFTY26N3122550CE'))                                    # 31 November does not exist
        self.assertIsNone(e('NSE:NIFTY26OCT22550CE'))                                    # monthly: no exact day in the name
        self.assertIsNone(e('NSE:SBIN-EQ'))
        self.assertIsNone(e(''))

    def test_readable_contract_names(self):
        self.assertEqual(self.m._n96_pretty(SYM), 'NIFTY 22550 PE (expires Tue 06 Oct 2026)')
        self.assertEqual(self.m._n96_short(SYM), 'NIFTY 22550PE')
        self.assertEqual(self.m._n96_pretty('NSE:NIFTY26OCT22550CE'), 'NIFTY 22550 CE Oct 2026 (monthly)')
        self.assertEqual(self.m._n96_pretty('NSE:RELIANCE-EQ'), 'RELIANCE')
        self.assertEqual(self.m._n96_short('NSE:RELIANCE-EQ'), 'RELIANCE')

    def test_ist_clock_helpers(self):
        ts = ist_ts(0, 15, 45)
        self.assertEqual(self.m._n96_hm(ts), '15:45')
        self.assertEqual(self.m._n96_day(ts), '2026-10-05')
        self.assertEqual(self.m._n96_dm('2026-10-05'), '05 Oct')


# ===================================================================================================================
# 2. STORAGE: ARCHIVE, VOID ROWS, ENTRY NOTES
# ===================================================================================================================
class TestArchive(LedgerCase):
    def test_every_closed_trade_is_copied_once(self):
        self.add(trade(), trade(days_ago=1, entry=100, exit=70, reason='stop-loss'))
        self.assertEqual(self.m._n96_archive(), 2)
        self.assertEqual(self.m._n96_archive(), 0)                                       # idempotent
        self.add(trade(days_ago=2))
        self.assertEqual(self.m._n96_archive(), 1)
        self.assertEqual(len(self.load()), 3)

    def test_history_survives_the_agent_dropping_old_trades(self):
        self.add(trade(days_ago=3), trade(days_ago=2))
        self.m._n96_archive()
        del self.log[:]                                                                   # AUTOLOG keeps only the last 500: older ones disappear from memory
        self.add(trade(days_ago=0))
        self.assertEqual(len(self.load()), 3)

    def test_bookkeeping_rows_are_not_trades(self):
        self.add(trade(), dict(trade(entry=50, exit=50, reason='stale-shadow-reconciled'), pnl=0.0))
        rows = self.m._n96_load()
        self.assertEqual(len(rows), 2)
        real = [t for t in rows if not t['void']]
        self.assertEqual(len(real), 1)
        self.assertEqual(real[0]['no'], 1)
        s = self.m._n96_stats(real)
        self.assertEqual((s['n'], s['wins'], s['losses']), (1, 1, 0))                     # the old day-end card would have counted the reconciliation as a loss

    def test_broken_rows_are_skipped_not_fatal(self):
        self.add({'sym': '', 'entry': 1, 'exit': 2, 'qty': 1, 'pnl': 1, 't': 5}, {'sym': 'X', 'entry': 'abc', 'exit': 2, 'qty': 1, 'pnl': 1, 't': 5}, {'sym': 'X', 'entry': 1, 'exit': 2, 'qty': 1, 'pnl': 1, 't': 0},
                 {'sym': 'X', 'entry': float('nan'), 'exit': 2, 'qty': 1, 'pnl': 1, 't': 5}, 'not a dict', trade())
        self.assertEqual(self.m._n96_archive(), 1)

    def test_a_broken_database_never_raises(self):
        with mock.patch.object(self.m, '_n35_conn', side_effect=RuntimeError('disk')):
            self.assertEqual(self.m._n96_q('SELECT 1'), [])
            self.assertEqual(self.m._n96_q('DELETE FROM ledger96_trade', write=True), 0)
            self.assertEqual(self.m._n96_many('INSERT INTO ledger96_trade VALUES(1)', [(1,)]), 0)
        self.assertGreaterEqual(self.m._N96_STATS['errors'], 3)

    def test_the_observer_notes_an_opened_position_once(self):
        m = self.m
        self.start(m, 'AUTO', dict(m.AUTO, mode='shadow', brain='ai', pos={'symbol': SYM, 'entry': 77.8, 'sl': 54.5, 'target': 116.7, 'qty': 65, 'at': ist_ts(0, 10, 12), 'reason': 'AI NIFTY: breakout (conf 7/10)', 'bracket': False}))
        m._n96_observe()
        m._n96_observe()
        rows = m._n96_q('SELECT sym,mode,entry,sl,target,qty,reason FROM ledger96_entry')
        self.assertEqual(rows, [(SYM, 'shadow', 77.8, 54.5, 116.7, 65.0, 'AI NIFTY: breakout (conf 7/10)')])
        self.assertEqual(m._N96_STATS['entries_seen'], 1)

    def test_a_closed_trade_gets_its_entry_time_stop_target_and_hold_time(self):
        m = self.m
        self.start(m, 'AUTO', dict(m.AUTO, mode='shadow', pos={'symbol': SYM, 'entry': 77.8, 'sl': 54.5, 'target': 116.7, 'qty': 65, 'at': ist_ts(0, 10, 12), 'reason': 'AI NIFTY: breakout (conf 7/10)'}))
        m._n96_observe()
        self.add(trade(hh=11, mm=48, why=''))
        t = self.load()[0]
        self.assertEqual(m._n96_hm(t['entry_at']), '10:12')
        self.assertAlmostEqual(t['hold_min'], 96, 0)
        self.assertEqual((t['sl'], t['target']), (54.5, 116.7))
        self.assertEqual(t['why'], 'AI NIFTY: breakout (conf 7/10)')                      # the entry note fills in a missing reason
        self.assertEqual(t['dte'], 1)                                                      # bought the day before expiry (06 Oct) if today is 05 Oct

    def test_entry_notes_only_join_the_same_contract_price_and_mode(self):
        m = self.m
        m._n96_q("INSERT INTO ledger96_entry(key,sym,mode,entry,at,sl,target,qty,reason,brain,seen) VALUES('a',?,?,?,?,?,?,?,?,?,?)", (SYM, 'live', 77.8, ist_ts(0, 10, 12), 54.5, 116.7, 65, 'x', 'ai', 0), write=True)
        m._n96_q("INSERT INTO ledger96_entry(key,sym,mode,entry,at,sl,target,qty,reason,brain,seen) VALUES('b',?,?,?,?,?,?,?,?,?,?)", (SYM, 'shadow', 80.0, ist_ts(0, 10, 12), 56, 120, 65, 'x', 'ai', 0), write=True)
        m._n96_q("INSERT INTO ledger96_entry(key,sym,mode,entry,at,sl,target,qty,reason,brain,seen) VALUES('c',?,?,?,?,?,?,?,?,?,?)", (SYM, 'shadow', 77.8, ist_ts(0, 12, 30), 54.5, 116.7, 65, 'x', 'ai', 0), write=True)
        self.add(trade(hh=11, mm=48))
        t = self.load()[0]
        self.assertIsNone(t['entry_at'])                                                   # wrong mode, wrong price, and an "entry" later than the exit: none may join
        self.assertIsNone(t['hold_min'])

    def test_trade_numbers_run_per_mode_and_in_time_order(self):
        self.add(trade(days_ago=1, mode='live'), trade(days_ago=3), trade(days_ago=2), trade(days_ago=0))
        shadow = self.load('shadow')
        self.assertEqual([t['no'] for t in shadow], [1, 2, 3])
        self.assertEqual([t['no'] for t in self.load('live')], [1])
        self.assertEqual([t['day'] for t in shadow], sorted(t['day'] for t in shadow))


# ===================================================================================================================
# 3. THE NUMBERS
# ===================================================================================================================
class TestStats(LedgerCase):
    def setUp(self):
        super().setUp()
        self.start(self.m, '_n96_costs', lambda: dict(self.m._N96_COSTS_DEFAULT, on=0.0))      # charges off: round numbers

    def stats(self, *trades):
        self.add(*trades)
        return self.m._n96_stats(self.load())

    def test_known_set(self):
        s = self.stats(trade(entry=100, exit=150, qty=10, days_ago=4, reason='target'),       # +500
                       trade(entry=100, exit=70, qty=10, days_ago=3, reason='stop-loss'),      # -300
                       trade(entry=100, exit=70, qty=10, days_ago=2, reason='stop-loss'),      # -300
                       trade(entry=100, exit=160, qty=10, days_ago=1, reason='target'))        # +600
        self.assertEqual((s['n'], s['wins'], s['losses']), (4, 2, 2))
        self.assertAlmostEqual(s['net'], 500.0)
        self.assertAlmostEqual(s['win_rate'], 0.5)
        self.assertAlmostEqual(s['avg_win'], 550.0)
        self.assertAlmostEqual(s['avg_loss'], -300.0)
        self.assertAlmostEqual(s['breakeven'], 300 / 850.0)
        self.assertAlmostEqual(s['profit_factor'], 1100 / 600.0)
        self.assertAlmostEqual(s['per_trade'], 125.0)
        self.assertAlmostEqual(s['max_dd'], 600.0)                                          # +500 -> 200 -> -100: peak 500, trough -100
        self.assertEqual(s['loss_streak'], 2)
        self.assertEqual((s['up_days'], s['down_days']), (2, 2))
        self.assertEqual([round(d['run']) for d in s['days']], [500, 200, -100, 500])
        self.assertEqual(s['best_day']['net'], 600.0)

    def test_no_losses_means_no_break_even_and_no_profit_factor(self):
        s = self.stats(trade(), trade(days_ago=1))
        self.assertIsNone(s['breakeven'])
        self.assertIsNone(s['profit_factor'])
        self.assertIsNone(s['avg_loss'])
        self.assertEqual(s['max_dd'], 0.0)

    def test_current_dip_is_measured_from_the_high_point(self):
        s = self.stats(trade(entry=100, exit=200, qty=10, days_ago=2), trade(entry=100, exit=60, qty=10, days_ago=1), trade(entry=100, exit=90, qty=10))
        self.assertAlmostEqual(s['now_dd'], 500.0)
        self.assertAlmostEqual(s['max_dd'], 500.0)

    def test_result_after_charges_uses_the_costs(self):
        self.start(self.m, '_n96_costs', lambda: dict(self.m._N96_COSTS_DEFAULT))
        s = self.stats(trade())
        self.assertAlmostEqual(s['gross'], 2918.5, 1)
        self.assertAlmostEqual(s['charges'], 64.71, 1)
        self.assertAlmostEqual(s['net'], 2918.5 - s['charges'], 4)

    def test_a_trade_that_loses_only_because_of_charges_is_a_loss(self):
        self.start(self.m, '_n96_costs', lambda: dict(self.m._N96_COSTS_DEFAULT))
        s = self.stats(trade(entry=100, exit=100.2, qty=65))                                # +13 before charges, about -55 after
        self.assertEqual((s['wins'], s['losses']), (0, 1))

    def test_groups_by_distance_to_expiry_call_put_exit_and_brain(self):
        today = D0
        # contracts expiring today, tomorrow and in five days
        def weekly(delta, kind):
            d = today + dt.timedelta(days=delta)
            return 'NSE:NIFTY%02d%s%02d22550%s' % (d.year % 100, {10: 'O', 11: 'N', 12: 'D'}.get(d.month) or str(d.month), d.day, kind)
        s = self.stats(trade(sym=weekly(0, 'CE'), entry=100, exit=150, qty=10), trade(sym=weekly(1, 'PE'), entry=100, exit=70, qty=10, days_ago=0, hh=12, reason='stop-loss'), trade(sym=weekly(5, 'PE'), entry=100, exit=150, qty=10, hh=13, brain='godmode'),
                       trade(sym='NSE:RELIANCE-EQ', entry=100, exit=101, qty=10, hh=14, reason='square-off'))
        dte = dict(s['by_dte'])
        self.assertEqual(dte['expiry day']['n'], 1)
        self.assertEqual(dte['1 day before expiry']['n'], 1)
        self.assertEqual(dte['4+ days before expiry']['n'], 1)
        self.assertEqual(dte['shares']['n'], 1)
        self.assertEqual(dict(s['by_dir'])['call (bet on a rise)']['n'], 1)
        self.assertEqual(dict(s['by_dir'])['put (bet on a fall)']['n'], 2)
        self.assertEqual(dict(s['by_exit'])['stop-loss']['net'], -300.0)
        self.assertEqual({k for k, _ in s['by_brain']}, {'AI', 'GODMODE'})

    def test_empty_list_is_safe(self):
        s = self.m._n96_stats([])
        self.assertEqual((s['n'], s['net'], s['max_dd']), (0, 0, 0))
        self.assertIsNone(s['best'])
        self.assertEqual(s['days'], [])


# ===================================================================================================================
# 4. THE LEDGER IN PLAIN WORDS
# ===================================================================================================================
class TestSummaryText(LedgerCase):
    def test_the_screenshot_trade_is_explained_honestly(self):
        self.add(trade())
        out = self.say('ledger')
        for part in ('PAPER-TRADING LEDGER', 'VIRTUAL money', '1 trade: 1 won, 0 lost (win rate 100%)', 'Made before charges: +₹2,918', 'Estimated charges: ₹65', 'After charges: +₹2,854',
                     'Average win +₹2,854 · average loss none yet', 'far too few', 'anywhere from 21% to 100%', 'about 29 more trading days', 'bought at the ask and sold at the bid', 'Agent now:'):
            self.assertIn(part, out)
        self.assertLessEqual(len(out), 3900)
        self.assertEqual(self.broker_calls, [])

    def test_no_trades_yet(self):
        out = self.say('ledger')
        self.assertIn('No closed trades in this period yet', out)
        self.assertIn('why didn’t you trade', out)

    def test_both_modes_are_never_mixed(self):
        self.add(trade(), trade(mode='live', entry=100, exit=50, qty=65, reason='stop-loss', days_ago=1))
        n = len(self.sent)
        self.m.handle(self.msg('ledger'))
        texts = [t for c, t in self.sent[n:] if c == OWNER_ID]
        self.assertEqual(len(texts), 2)
        self.assertIn('REAL money', texts[0])                                              # live first
        self.assertIn('0 won, 1 lost', texts[0])
        self.assertIn('VIRTUAL money', texts[1])
        self.assertIn('1 won, 0 lost', texts[1])
        out = self.say('ledger virtual')
        self.assertIn('VIRTUAL', out)
        self.assertNotIn('REAL money', out)
        out = self.say('ledger live')
        self.assertIn('REAL money', out)
        self.assertNotIn('VIRTUAL', out)

    def test_periods(self):
        self.add(trade(days_ago=40), trade(days_ago=10), trade(days_ago=2), trade(days_ago=0))
        self.assertIn('4 trades', self.say('ledger'))
        self.assertIn('1 trade:', self.say('ledger today'))
        out = self.say('ledger 30 days')
        self.assertIn('3 trades', out)
        self.assertIn('last 30 days', out)
        self.assertIn('2 trades', self.say('ledger last 7 days'))
        self.assertIn('this week', self.say('ledger this week'))
        self.assertIn('this month', self.say('ledger month'))

    def test_break_even_and_profit_factor_lines(self):
        self.add(trade(entry=100, exit=150, qty=10, days_ago=3), trade(entry=100, exit=70, qty=10, days_ago=2, reason='stop-loss'), trade(entry=100, exit=150, qty=10, days_ago=1))
        self.start(self.m, '_n96_costs', lambda: dict(self.m._N96_COSTS_DEFAULT, on=0.0))
        out = self.say('ledger')
        self.assertIn('must win at least 38% of its trades just to break even', out)
        self.assertIn('It has won 67%', out)
        self.assertIn('For every ₹1 it lost it made ₹3.33', out)
        self.assertIn('Charges are switched off', out)

    def test_thirty_trades_switch_the_wording_to_a_measured_range(self):
        for i in range(32):
            self.add(trade(entry=100, exit=150 if i % 3 else 70, qty=10, days_ago=40 - i, reason='target' if i % 3 else 'stop-loss'))
        self.start(self.m, '_n96_costs', lambda: dict(self.m._N96_COSTS_DEFAULT, on=0.0))
        out = self.say('ledger')
        self.assertIn('With 32 trades the win rate is probably between', out)
        self.assertNotIn('far too few', out)
        self.assertIn('evidence is building', out)

    def test_not_proven_when_the_low_end_is_below_break_even(self):
        for i in range(30):
            self.add(trade(entry=100, exit=150 if i < 14 else 70, qty=10, days_ago=40 - i))
        self.start(self.m, '_n96_costs', lambda: dict(self.m._N96_COSTS_DEFAULT, on=0.0))
        out = self.say('ledger')
        self.assertIn('not proven yet', out)

    def test_expiry_exposure_and_one_good_day_are_called_out(self):
        today = D0

        def weekly(delta):
            d = today + dt.timedelta(days=delta)
            return 'NSE:NIFTY%02d%s%02d22550PE' % (d.year % 100, {10: 'O', 11: 'N', 12: 'D'}.get(d.month) or str(d.month), d.day)
        self.add(trade(sym=weekly(0), entry=100, exit=300, qty=10, days_ago=2), trade(sym=weekly(0), entry=100, exit=95, qty=10, days_ago=1, reason='stop-loss'), trade(sym=weekly(0), entry=100, exit=101, qty=10, days_ago=0))
        self.start(self.m, '_n96_costs', lambda: dict(self.m._N96_COSTS_DEFAULT, on=0.0))
        out = self.say('ledger')
        self.assertIn('bought on expiry day or the day before', out)
        self.assertIn('made ', out)
        self.assertIn('of the whole profit', out)

    def test_live_ledger_does_not_carry_the_virtual_fill_note(self):
        self.add(trade(mode='live'))
        self.assertNotIn('bought at the ask', self.say('ledger'))

    def test_a_recorded_hold_time_is_shown_only_when_known(self):
        self.add(trade())
        self.assertNotIn('Average time in a trade', self.say('ledger'))
        self.start(self.m, 'AUTO', dict(self.m.AUTO, mode='shadow', pos={'symbol': SYM, 'entry': 77.8, 'sl': 54.5, 'target': 116.7, 'qty': 65, 'at': ist_ts(0, 10, 12), 'reason': 'r'}))
        self.m._n96_observe()
        self.assertIn('Average time in a trade: 48 min', self.say('ledger'))


class TestViews(LedgerCase):
    def setUp(self):
        super().setUp()
        self.add(trade(entry=100, exit=150, qty=10, days_ago=3), trade(entry=100, exit=70, qty=10, days_ago=2, reason='stop-loss', why='AI NIFTY: weak (conf 6/10)'), trade(entry=100, exit=150, qty=10, days_ago=1, hh=14))
        self.start(self.m, '_n96_costs', lambda: dict(self.m._N96_COSTS_DEFAULT, on=0.0))

    def test_day_by_day_table_with_a_running_total(self):
        self.say('ledger days')
        text = self.mono[-1][1]
        self.assertIn('DAY BY DAY', text)
        self.assertIn('Running total', text)
        self.assertIn('+₹500', text)
        self.assertIn('+₹200', text)
        self.assertIn('+₹700', text)
        self.assertEqual(len([l for l in text.splitlines() if re.match(r'^\d\d [A-Z][a-z]{2}', l)]), 3)

    def test_the_period_words_do_not_turn_a_summary_into_the_days_table(self):
        out = self.say('ledger 30 days')
        self.assertIn('RESULT', out)
        self.assertEqual(self.mono, [])
        self.say('ledger week days')
        self.assertTrue(self.mono)

    def test_trade_list_and_one_trade_in_full(self):
        self.say('ledger trades')
        text = self.mono[-1][1]
        self.assertIn('LAST 3 TRADES', text)
        self.assertIn('#1', text)
        self.assertIn('#3', text)
        self.assertIn('NIFTY 22550PE', text)
        out = self.say('ledger trade 2')
        for part in ('TRADE #2 (virtual)', 'NIFTY 22550 PE', 'stop-loss hit', 'Result before charges -₹300', 'Why (the agent’s own note): AI NIFTY: weak (conf 6/10)', 'Chosen by the AI brain', 'not recorded'):
            self.assertIn(part, out)
        self.assertIn('TRADE #3', self.say('ledger last'))
        self.assertIn('TRADE #1', self.say('ledger #1'))
        out = self.say('ledger trade 9')
        self.assertIn('no trade #9', out)
        self.assertIn('1 to 3', out)

    def test_trade_in_full_with_noted_entry_shows_the_plan_and_the_charges(self):
        self.start(self.m, '_n96_costs', lambda: dict(self.m._N96_COSTS_DEFAULT))
        self.add(trade(days_ago=0, hh=11, mm=48))
        self.start(self.m, 'AUTO', dict(self.m.AUTO, mode='shadow', pos={'symbol': SYM, 'entry': 77.8, 'sl': 54.5, 'target': 116.7, 'qty': 65, 'at': ist_ts(0, 10, 12), 'reason': 'AI NIFTY: breakout (conf 7/10)'}))
        self.m._n96_observe()
        out = self.say('ledger trade 4')
        for part in ('Bought 65 units at 77.80 at 10:12', 'sold at 122.70 at 11:48', 'target hit', 'Held for 1 h', 'Bought 1 day before expiry', 'stop at 54.50 (-30%)', 'target at 116.70 (+50%)', 'estimated charges ₹65 (brokerage ₹40', 'after charges +₹2,854'):
            self.assertIn(part, out)
        self.assertRegex(out, r'Most it could lose: about ₹1,51\d; planned win: about ₹2,52\d \(before charges\)')

    def test_breakdown_needs_three_trades(self):
        out = self.say('ledger breakdown')
        self.assertIn('WHAT WORKED', out)
        self.assertIn('stop-loss: 1 trade, 0 won, -₹300', out)
        self.assertIn('target: 2 trades, 2 won, +₹1,000', out)
        del self.log[1:]
        self.m._n96_q('DELETE FROM ledger96_trade WHERE exit_reason=?', ('stop-loss',), write=True)
        self.assertIn('at least 3 trades', self.say('ledger breakdown'))

    def test_empty_single_views_say_so(self):
        self.m._n96_q('DELETE FROM ledger96_trade', write=True)
        del self.log[:]
        for q in ('ledger days', 'ledger trades', 'ledger trade 1', 'ledger csv', 'ledger chart', 'ledger breakdown'):
            self.assertIn('No closed virtual trades yet', self.say(q), q)

    def test_help(self):
        out = self.say('ledger help')
        for part in ('ledger days', 'ledger trade 3', 'ledger csv', 'ledger chart', 'ledger logic', 'ledger costs', 'only reads'):
            self.assertIn(part, out)


class TestFiles(LedgerCase):
    def setUp(self):
        super().setUp()
        self.add(trade(), trade(entry=100, exit=70, qty=10, days_ago=1, reason='stop-loss', why='=HYPERLINK("http://evil.example","x")'), trade(entry=100, exit=150, qty=10, days_ago=2, why='+cmd|calc'))

    def test_csv_has_every_trade_and_is_safe_in_a_spreadsheet(self):
        self.say('ledger csv')
        self.assertEqual(len(self.files), 1)
        cid, path, name, mime, raw = self.files[0]
        self.assertEqual(cid, OWNER_ID)
        self.assertRegex(name, r'^nemo-ledger-virtual-\d{8}\.csv$')
        self.assertEqual(mime, 'text/csv')
        self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))                                    # opens correctly in Excel
        rows = list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
        self.assertEqual(rows[0][:5], ['no', 'date', 'bought_at', 'sold_at', 'mode'])
        self.assertEqual(len(rows), 4)
        self.assertEqual([r[0] for r in rows[1:]], ['1', '2', '3'])                          # oldest first
        by_no = {r[0]: r for r in rows[1:]}
        self.assertEqual(by_no['3'][5], SYM)
        self.assertEqual(by_no['3'][11], '2918.50')
        notes = {r[0]: r[-1] for r in rows[1:]}
        self.assertEqual(notes['1'], "'+cmd|calc")
        self.assertEqual(notes['2'], "'=HYPERLINK(\"http://evil.example\",\"x\")")
        self.assertFalse(os.path.exists(path))                                              # the temporary file is removed

    def test_csv_failure_is_reported_and_cleaned_up(self):
        self.start(self.m, 'send_document', lambda *a, **k: False)
        out = self.say('ledger csv')
        self.assertIn('Telegram did not accept it', out)
        with mock.patch.object(self.m, '_n96_csv_bytes', side_effect=RuntimeError('x')):
            self.assertIn('could not make the CSV', self.say('ledger export'))

    def test_chart_is_a_png_after_two_trades(self):
        self.say('ledger chart')
        self.assertEqual(len(self.images), 1)
        raw = self.images[0][1]
        self.assertTrue(raw.startswith(b'\x89PNG'))
        self.assertIn('after estimated charges', self.images[0][3])

    def test_chart_needs_two_trades(self):
        del self.log[1:]
        self.m._n96_q('DELETE FROM ledger96_trade WHERE sym=? AND entry=100', (SYM,), write=True)
        self.m._n96_q('DELETE FROM ledger96_trade WHERE entry=100', write=True)
        out = self.say('ledger chart')
        self.assertIn('at least 2 closed trades', out)
        self.assertEqual(self.images, [])


# ===================================================================================================================
# 5. CHARGES COMMAND
# ===================================================================================================================
class TestCostsCommand(LedgerCase):
    def test_show_edit_off_on_reset(self):
        out = self.say('ledger costs')
        self.assertIn('CHARGES USED IN THE LEDGER', out)
        self.assertIn('brokerage per order (₹): 20', out)
        self.assertIn('Example: 65 units bought at 77.80 and sold at 122.70 → about ₹65', out)
        out = self.say('ledger costs stt_opt 0.1')
        self.assertIn('Saved.', out)
        self.assertIn('STT on the sell side of options (%): 0.1 (changed; default 0.15)', out)
        self.assertEqual(self.m._n96_costs()['stt_opt'], 0.1)
        self.assertIn('Charges are OFF', self.say('ledger costs off'))
        self.assertEqual(self.m._n96_costs()['on'], 0.0)
        self.assertIn('Charges are ON', self.say('ledger costs on'))
        self.assertIn('brokerage per order (₹): 15 (changed; default 20)', self.say('ledger costs brokerage = 15'))
        self.assertIn('Saved.', self.say('ledger costs reset'))
        self.assertEqual(self.m._n96_costs(), self.m._N96_COSTS_DEFAULT)

    def test_bad_input_changes_nothing(self):
        before = self.m._n96_costs()
        for q in ('ledger costs banana 3', 'ledger costs stt_opt abc', 'ledger costs stt_opt 5000', 'ledger costs stt_opt -1'):
            out = self.say(q)
            self.assertTrue('did not understand' in out or 'looks wrong' in out, q)
        self.assertEqual(self.m._n96_costs(), before)

    def test_saved_costs_drive_the_numbers_and_survive_garbage_in_the_store(self):
        self.add(trade())
        self.say('ledger costs off')
        self.assertIn('Charges are switched off', self.say('ledger'))
        self.m._n96_q("INSERT OR REPLACE INTO ledger96_setting(key,value) VALUES('costs',?)", ('{"stt_opt": "x", "bogus": 5, "brokerage": -3, "gst": 18}',), write=True)
        c = self.m._n96_costs()
        self.assertEqual(c['stt_opt'], self.m._N96_COSTS_DEFAULT['stt_opt'])
        self.assertEqual(c['brokerage'], self.m._N96_COSTS_DEFAULT['brokerage'])
        self.assertNotIn('bogus', c)
        self.m._n96_q("INSERT OR REPLACE INTO ledger96_setting(key,value) VALUES('costs','not json')", write=True)
        self.assertEqual(self.m._n96_costs(), self.m._N96_COSTS_DEFAULT)


# ===================================================================================================================
# 6. HOW THE AGENT DECIDES: the explanation must match the code
# ===================================================================================================================
class TestLogicExplanation(LedgerCase):
    def test_it_shows_the_live_settings(self):
        self.start(self.m, 'AUTO', dict(self.m.AUTO, mode='shadow', brain='ai', maxtrades=2, dayloss=4000))
        out = self.say('ledger logic')
        for part in ('HOW THE STOCK-MARKET AGENT DECIDES', 'mode SHADOW · brain AI · at most 2 trade(s) a day', '₹4,000', 'WHEN IT LOOKS', 'WHAT IT LOOKS AT', 'WHAT IT BUYS', 'WHEN IT SELLS', 'WHAT THAT MEANS',
                     'nearest', 'at the money', 'NIFTY: 65 units', 'about 38% winning trades'):
            self.assertIn(part, out.replace('at-the-money', 'at the money'))
        self.assertLessEqual(len(out), 3900)

    def test_every_claim_still_matches_the_source(self):
        """If someone changes the agent, these fail, and the explanation has to be updated with it."""
        src = bot_source()
        text = self.m._n96_logic_text()
        claims = [
            ('stop 30% below', 'sl, target = round(entry * 0.70, 1), round(entry * 1.50, 1)', 'Stop-loss at 30% below'),                  # AI path and GODMODE path
            ('target 50% above', 'sl, target = round(entry * 0.70, 1), round(entry * 1.50, 1)', 'target at 50% above'),
            ('square-off 15:10', 'return wd < 5 and m >= 15 * 60 + 10', '15:10'),
            ('AI must be 6/10 sure', 'd["confidence"] < 6', '6 out of 10'),
            ('GODMODE needs 4', 'abs(best[1]["score"]) < 4', 'is 4 or more'),
            ('new trades 09:20-14:30', "'entry_open':state=='OPEN' and 560<=minute<870", '09:20 and 14:30'),
            ('market hours scan 09:15-15:35', '555 <= (ist.tm_hour * 60 + ist.tm_min) <= 935', '09:15 to 15:35'),
            ('every 2nd minute', 'and SCHED_N["n"] % 2 == 0:\n                threading.Thread(target=auto_trade_tick', 'every 2 minutes'),
            ('scheduler sleeps 60 s', 'time.sleep(60)', 'every 2 minutes'),
            ('quote under 30 seconds old', 'if not -2<=now-ts<=30:raise ValueError()', 'under 30 seconds'),
            ('gap at most 2%', '(ask-bid)/ask>.02', 'at most 2%'),
            ('price within 1%', 'abs(ask-entry)/entry>.01', 'within 1%'),
            ('risk fits what is left of the day limit', "(ask-sl)*qty>remaining", 'what is left of the day’s loss limit'),
            ('last 45 days of own record', 'def strategy_insights(days=45)', 'last 45 days'),
            ('needs 6 trades of history', 'if len(ts) < 6:', '6 trades'),
            ('daily candles', 'resolution=D', 'DAILY candles'),
            ('three indexes', 'for idx in ("NIFTY", "BANKNIFTY", "SENSEX"):', 'NIFTY, BANKNIFTY and SENSEX'),
            ('buy only', 'BUY ONLY (never sell/write)', 'Buy only'),
            ('virtual entry at the ask', 'return ask,', 'bought at the ask'),
            ('virtual exit at the bid', "ltp=_q81['bid']", 'use the bid'),
            ('no expiry choice in the chain call', 'params={"symbol":underlying,"strikecount":max(1,min(int(strikes or 8),50))}', 'does not choose the expiry'),
            ('ATM strike', 'atm=min(c,key=lambda x:abs(x["strike"]-spot))', 'at-the-money'),
        ]
        for what, snippet, phrase in claims:
            self.assertIn(snippet, src, what + ': the code changed, update “ledger logic”')
            self.assertIn(phrase, text, what + ': the explanation lost this claim')
        self.assertEqual(self.m.lot_size('NIFTY'), 65)

    def test_the_break_even_figure_follows_from_the_two_percentages(self):
        self.assertAlmostEqual(30 / (30 + 50.0), 0.375)
        self.assertIn('about 38%', self.m._n96_logic_text())


# ===================================================================================================================
# 7. WIRING: the front door, the agent's tick, the day-end card
# ===================================================================================================================
class TestFrontDoor(LedgerCase):
    PHRASES = ('ledger', 'Ledger', '/ledger', 'show my ledger', 'show me the paper ledger', 'paper trading ledger', 'agent ledger', 'trading ledger today', 'please show the ledger', 'nemo ledger week',
               'full paper trading report', 'complete trading report', 'show me the whole agent history', 'how is the paper agent doing', 'how has the shadow agent done', 'how much has the paper agent made')

    def test_phrases_reach_the_ledger_and_are_not_passed_on(self):
        for q in self.PHRASES:
            n = len(self.sent)
            self.passed.clear()
            self.m.handle(self.msg(q))
            self.assertEqual(self.passed, [], q)
            self.assertTrue(any('LEDGER' in t for c, t in self.sent[n:]), q)

    def test_logic_questions(self):
        for q in ('ledger logic', 'how does the paper agent decide', 'explain the trading agent logic', 'what is the shadow agent strategy', 'how does the stock-market agent trade', 'tell me about the paper agent logic'):
            n = len(self.sent)
            self.passed.clear()
            self.m.handle(self.msg(q))
            self.assertEqual(self.passed, [], q)
            self.assertTrue(any('HOW THE STOCK-MARKET AGENT DECIDES' in t for c, t in self.sent[n:]), q)

    def test_other_sentences_go_on_to_the_older_handlers(self):
        for q in ('analyse this ledger of my expenses', 'how do I build a trading bot', 'the ledger is balanced', 'show me my expenses', 'explain how options work', 'full report on tata motors', 'open ledgerwood park', 'ledger banana split', 'show ledger of ramesh and sons'):
            self.passed.clear()
            self.m.handle(self.msg(q))
            self.assertEqual(len(self.passed), 1, q)

    def test_a_guest_cannot_see_the_ledger(self):
        self.add(trade())
        n = len(self.sent)
        self.m.handle(self.guest('ledger'))
        self.assertEqual(len(self.passed), 1)
        self.assertFalse(any('LEDGER' in t for c, t in self.sent[n:]))

    def test_a_file_or_picture_is_not_a_ledger_request(self):
        for extra in ({'document': {'file_id': 'x'}}, {'photo': [{'file_id': 'y'}]}):
            self.passed.clear()
            self.m.handle(self.msg('ledger', **extra))
            self.assertEqual(len(self.passed), 1)

    def test_a_group_chat_is_not_the_owner(self):
        self.passed.clear()
        self.m.handle({'chat': {'id': OWNER_ID, 'type': 'group'}, 'from': {'id': OWNER_ID}, 'message_id': 4, 'text': 'ledger'})
        self.assertEqual(len(self.passed), 1)

    def test_a_ledger_command_never_calls_a_broker_or_an_ai(self):
        self.add(trade())
        for q in ('ledger', 'ledger days', 'ledger trades', 'ledger trade 1', 'ledger csv', 'ledger chart', 'ledger logic', 'ledger costs', 'ledger breakdown'):
            self.say(q)
        self.assertEqual(self.broker_calls, [])
        self.assertEqual(self.ai_calls, [])
        self.assertEqual(self.m.AUTO['pos'], None)

    def test_parse(self):
        p = self.m._n96_parse
        self.assertEqual(p('')['action'], 'summary')
        self.assertEqual(p('7 days')['action'], 'summary')
        self.assertEqual(p('last 7 days')['label'], 'last 7 days')
        self.assertEqual(p('days')['action'], 'days')
        self.assertEqual(p('trade 12')['n'], 12)
        self.assertEqual(p('#4')['action'], 'trade')
        self.assertEqual(p('live csv')['mode'], 'live')
        self.assertEqual(p('virtual chart')['action'], 'chart')
        self.assertEqual(p('what worked')['action'], 'breakdown')
        self.assertEqual(p('week')['since'], '2026-10-05')                                  # Monday
        self.assertEqual(p('month')['since'], '2026-10-01')
        self.assertEqual(p('1 day')['since'], '2026-10-05')
        self.assertEqual(p('?')['action'], 'help')


class TestTickObserver(LedgerCase):
    def test_the_agents_tick_runs_unchanged_and_its_answer_is_passed_on(self):
        calls = []
        self.start(self.m, '_N96_TICK_PREV', lambda now=None: calls.append(now) or 'tick-result')
        with mock.patch.object(self.m, '_n96_observe') as obs:
            self.assertEqual(self.m.auto_trade_tick(123.0), 'tick-result')
            self.assertEqual(self.m.auto_trade_tick(), 'tick-result')
        self.assertEqual(calls, [123.0, None])
        self.assertEqual(obs.call_count, 2)

    def test_an_error_in_the_agent_still_propagates_and_the_ledger_still_looks(self):
        def boom(now=None):
            raise ValueError('agent problem')
        self.start(self.m, '_N96_TICK_PREV', boom)
        with mock.patch.object(self.m, '_n96_observe') as obs:
            with self.assertRaises(ValueError):
                self.m.auto_trade_tick()
        self.assertEqual(obs.call_count, 1)

    def test_a_failing_look_never_disturbs_the_agent(self):
        self.start(self.m, '_N96_TICK_PREV', lambda now=None: 'fine')
        with mock.patch.object(self.m, '_n96_observe', side_effect=RuntimeError('db locked')):
            self.assertEqual(self.m.auto_trade_tick(), 'fine')
        self.assertEqual(self.m._N96_STATS['errors'], 1)

    def test_the_look_changes_nothing_in_the_agent(self):
        m = self.m
        self.start(m, 'AUTO', dict(m.AUTO, mode='shadow', brain='ai', day='2026-10-05', trades=1, pnl=2918.5, halted='', pos={'symbol': SYM, 'entry': 77.8, 'sl': 54.5, 'target': 116.7, 'qty': 65, 'at': ist_ts(0, 10, 12), 'reason': 'r'}))
        self.add(trade())
        before = (copy.deepcopy(m.AUTO), copy.deepcopy(self.log))
        m._n96_observe()
        m._n96_observe()
        self.assertEqual((m.AUTO, self.log), before)
        self.assertEqual(self.broker_calls, [])

    def test_the_real_tick_closes_a_virtual_position_and_the_ledger_sees_it(self):
        """The owner's screenshot case, end to end: a virtual NIFTY put bought at 77.8 reaches its target; the REAL agent code books it; the ledger then shows it with its entry time."""
        m = self.m
        now = time.time()
        opened = now - 5760
        self.start(m, 'BROKER', dict(m.BROKER, token='test-token'))
        self.start(m, 'AUTO', dict(m.AUTO, mode='shadow', brain='ai', day=m.fyers_today(), trades=1, pnl=0.0, halted='', pos={'symbol': SYM, 'entry': 77.8, 'sl': 54.46, 'target': 116.7, 'qty': 65, 'at': opened,
                                                                                                                         'reason': 'AI NIFTY: strong trend (conf 7/10)', 'bracket': False}))
        self.start(m, '_n75_quote', lambda symbol: {'symbol': symbol, 'ts': time.time(), 'last': 123.0, 'bid': 122.7, 'ask': 123.2, 'bid_qty': 650, 'ask_qty': 650})
        self.start(m, 'save_data', lambda *a, **k: None)
        reports = []
        self.start(m, 'auto_report', lambda text: reports.append(text))
        self.start(m, 'must_square_off', lambda now=None: False)
        # the tick that opened the position (earlier today): the ledger notes the entry
        with mock.patch.object(m, '_N96_TICK_PREV', lambda now=None: None):
            m.auto_trade_tick()
        self.assertEqual(len(m._n96_q('SELECT 1 FROM ledger96_entry')), 1)
        # the real tick: target reached
        m._N96_TICK_PREV = self.real_tick
        m.auto_trade_tick()
        self.assertEqual(len(self.log), 1)
        row = self.log[0]
        self.assertEqual((row['sym'], row['entry'], row['exit'], row['pnl'], row['exit_reason'], row['mode']), (SYM, 77.8, 122.7, 2918.5, 'target', 'shadow'))
        self.assertIn('AUTO-TRADE EXIT (target)', reports[0])
        self.assertEqual(self.broker_calls, [])
        t = [x for x in m._n96_load() if not x['void']][-1]
        self.assertAlmostEqual(t['hold_min'], 96, 0)
        self.assertEqual((t['sl'], t['target']), (54.46, 116.7))
        self.assertEqual(t['exit_reason'], 'target')
        self.assertEqual(m._N96_STATS['archived'], 1)

    @property
    def real_tick(self):
        return self._real_tick

    def setUp(self):
        super().setUp()
        self._real_tick = self.m._N96_TICK_PREV
        orig = self.m._N96_TICK_PREV
        self.addCleanup(setattr, self.m, '_N96_TICK_PREV', orig)


class TestDayEndLine(LedgerCase):
    def test_the_card_is_unchanged_and_a_running_total_follows(self):
        m = self.m
        self.add(trade(), trade(entry=100, exit=60, qty=10, days_ago=1, reason='stop-loss'))
        n = len(self.mono)
        calls = []
        self.start(m, '_N96_EOD_PREV', lambda chat_id, on_demand=False, day=None: calls.append((chat_id, on_demand, day)) or 'card-result')
        m.ntfy_send = lambda *a, **k: None
        sent = len(self.sent)
        self.assertEqual(m.trading_day_report(OWNER_ID, True), 'card-result')
        self.assertEqual(calls, [(OWNER_ID, True, None)])
        line = [t for c, t in self.sent[sent:] if c == OWNER_ID]
        self.assertEqual(len(line), 1)
        for part in ('Running total (virtual): 2 trades over 2 days', 'after estimated charges', 'win rate 50%', 'Only 2 trades so far: too few to judge', 'Say “ledger”'):
            self.assertIn(part, line[0])
        self.assertEqual(m._N96_STATS['eod_lines'], 1)

    def test_no_line_when_nothing_was_traded_that_day(self):
        self.add(trade(days_ago=3))
        self.start(self.m, '_N96_EOD_PREV', lambda chat_id, on_demand=False, day=None: None)
        sent = len(self.sent)
        self.m.trading_day_report(OWNER_ID)
        self.assertEqual(self.sent[sent:], [])

    def test_the_real_card_still_comes_out_the_same(self):
        m = self.m
        self.add(trade())
        self.start(m, 'ntfy_send', lambda *a, **k: None)
        self.m.trading_day_report(OWNER_ID, True)
        cards = [text for _c, text in self.mono if 'DAY-END REPORT' in text]
        self.assertEqual(len(cards), 1)
        self.assertIn('Net P&L: Rs.+2,918', cards[0])
        self.assertIn('Mode: SHADOW   (VIRTUAL - no real money)', cards[0])
        self.assertIn('NIFTY option     1 trade(s)   Rs.+2,918', cards[0])

    def test_a_failure_in_the_extra_line_does_not_break_the_card(self):
        self.add(trade())
        self.start(self.m, '_N96_EOD_PREV', lambda chat_id, on_demand=False, day=None: 'ok')
        with mock.patch.object(self.m, '_n96_after_day_report', side_effect=RuntimeError('x')):
            self.assertEqual(self.m.trading_day_report(OWNER_ID), 'ok')
        self.assertEqual(self.m._N96_STATS['errors'], 1)

    def test_a_live_day_gets_its_own_real_money_line(self):
        self.add(trade(mode='live'))
        self.start(self.m, '_N96_EOD_PREV', lambda chat_id, on_demand=False, day=None: None)
        sent = len(self.sent)
        self.m.trading_day_report(OWNER_ID)
        self.assertIn('Running total (real)', '\n'.join(t for c, t in self.sent[sent:]))


# ===================================================================================================================
# 8. STATUS PAGES, COMMAND LIST, REGRESSION ROWS, STRUCTURE
# ===================================================================================================================
class TestWiringAndStructure(LedgerCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass() if hasattr(super(), 'setUpClass') else None
        cls.src = v96_source()
        cls.tree = ast.parse(cls.src)

    def test_capabilities_status_abilities_and_commands(self):
        m = self.m
        self.assertIn('Ledger 96:', m._n82_capabilities())
        self.assertIn('“ledger logic”', m._n82_capabilities())
        self.assertIn('LEDGER 96: views 0 · trades kept 0', m._n83_status_text(OWNER_ID))
        rows = {r[1]: r for r in m._n88_abilities(OWNER_ID)}
        self.assertIn('Paper-trading ledger', rows)
        self.assertEqual(rows['Paper-trading ledger'][2], 'ready')
        self.assertIn('ledger', [c[0] for c in m._N40_COMMANDS])

    def test_the_abilities_report_still_ends_properly_with_the_new_row(self):
        r = self.m._n88_eye_abilities(OWNER_ID, live=True)['text']
        self.assertLessEqual(len(r), 3900)
        self.assertIn('Paper-trading ledger', r)
        self.assertTrue(r.rstrip().endswith('still need your approval.'))

    def test_regression_rows_pass_and_join_the_suite(self):
        rows = self.m._n96_regression_rows()
        self.assertEqual(len(rows), 7)
        self.assertEqual([r['name'] for r in rows if not r['ok']], [])
        self.assertTrue(all(r['name'].startswith('v96-') for r in rows))
        self.assertIsNot(self.m.prime_regression_suite, self.m._N96_REG_PREV)

    def test_every_replaced_function_keeps_the_old_one(self):
        for fn, prev in (('handle', '_N96_HANDLE_PREV'), ('auto_trade_tick', '_N96_TICK_PREV'), ('trading_day_report', '_N96_EOD_PREV'), ('_n83_status_text', '_N96_STATUS_PREV'), ('_n82_capabilities', '_N96_CAPS_PREV'),
                         ('_n88_abilities', '_N96_ABIL_PREV'), ('prime_regression_suite', '_N96_REG_PREV'), ('main', '_N96_MAIN_PREV')):
            self.assertIn('%s = %s\n' % (prev, fn), self.src, fn)

    def test_all_layer_names_use_the_v96_prefix(self):
        defined = {n.name for n in self.tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        odd = [d for d in defined if not (d.startswith('_n96_') or d.startswith('_N96')) and d not in ('handle', '_n82_capabilities', '_n83_status_text', '_n88_abilities', 'prime_regression_suite', 'main', 'auto_trade_tick', 'trading_day_report')]
        self.assertEqual(odd, [])

    def test_the_layer_is_read_only(self):
        """It cannot place, change or simulate an order, write the agent's state or the log, touch credentials, or call the network."""
        src = self.src
        for word in ('fyers_place', '_order_send', 'request_order', 'save_secret', 'save_data', 'requests.', 'ask_ai', 'BROKER', 'OWNER[', 'WEBCFG', 'AUTOLOG.append', 'AUTOLOG.remove', 'del AUTOLOG', 'AUTOLOG[',
                     '_n81_paused', 'mm_locked', 'auto_report', 'subprocess', 'os.system', 'eval(', 'exec('):
            self.assertNotIn(word, src, word)
        self.assertIsNone(re.search(r'\bAUTO\s*\[[^\]]+\]\s*=[^=]', src))                  # never assigns into the agent's state
        self.assertIsNone(re.search(r'\bAUTO\s*\.\s*(?:update|pop|clear|setdefault|__setitem__)', src))
        self.assertNotIn('AUTO[\'mode\'] =', src)
        reads = set(re.findall(r"\bAUTO(?:\.get|\[)\(?['\"](\w+)", src))
        self.assertLessEqual(reads, {'pos', 'mode', 'brain', 'trades', 'maxtrades', 'dayloss'})

    def test_the_sql_only_touches_the_ledgers_own_tables(self):
        tables = set(re.findall(r'(?:FROM|INTO|TABLE(?: IF NOT EXISTS)?|UPDATE)\s+([a-z_0-9]+)', self.src))
        self.assertEqual(tables, {'ledger96_trade', 'ledger96_entry', 'ledger96_setting'})

    def test_the_protection_list_for_live_self_edit_names_the_new_prefix(self):
        self.assertIn("'_n95_','_n96_',", bot_source())

    def test_version_and_docstring(self):
        self.assertGreaterEqual(float(self.m.VERSION), 96.0)
        self.assertIn('v96.0 - LEDGER', bot_source()[:12000])                                   # (later versions put their own line first)
