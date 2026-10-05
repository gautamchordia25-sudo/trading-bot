"""Nemo v99 Lab: the read-only laboratory beside the stock-market agent: the price record of each trade, the replay engine, the rule comparison (and its refusal to call a winner on too few trades), the "why not" log,
excursions, direction, weekly and monthly reports, alerts, the live-readiness checklist, the front door, and the guarantee that the layer never changes what the agent does.

Offline. The agent's own tick runs for real in the end-to-end test (broker, quotes, AI, calendar and clock are stubbed); no network, no broker, no order.

    NEMO_FILE=/path/to/nemotron_bot.py python -m unittest tests.test_lab99 -v
"""
import ast
import copy
import datetime as dt
import json
import os
import re
import time
import unittest
from unittest import mock

from tests import test_cortex83 as base
from tests.test_forge91 import OWNER_ID
from tests.test_ledger96 import LedgerCase, D0, IST, ist_ts, bot_source

SYM = 'NSE:NIFTY26O0622550PE'          # expires 2026-10-06
SYM_FAR = 'NSE:NIFTY26O1322550PE'      # expires 2026-10-13
SYM_CE = 'NSE:NIFTY26O1322600CE'


def setUpModule():
    if base.m is None:
        base.setUpModule()


def v99_source():
    src = bot_source()
    i = src.index('# NEMO 99 - LAB')
    j = src.index('# NEMO 100 - ') if '# NEMO 100 - ' in src else src.rindex("if __name__")
    return src[i:j]


def sample(t, bid, clean=True, last=None, ask=None):
    return {'t': float(t), 'bid': bid, 'ask': ask if ask is not None else bid + 0.3, 'last': last if last is not None else bid, 'clean': clean}


def path_of(bids, t0=1000.0, step=120.0, clean=True):
    return [sample(t0 + step * (i + 1), b, clean) for i, b in enumerate(bids)]


class LabCase(LedgerCase):
    def setUp(self):
        super().setUp()
        m = self.m
        for table in ('lab99_path', 'lab99_pos', 'lab99_why', 'lab99_event', 'lab99_setting'):
            m._n99_q('DELETE FROM %s' % table, write=True)
        for k in m._N99_STATS:
            m._N99_STATS[k] = 0
        for name, empty in (('_N99_PENDING', []), ('_N99_RECENT', {})):
            self.start(m, name, empty)
        self.start(m, '_N99_CUR', {'key': None, 'sym': None, 'mode': None, 'at': 0, 'entry': 0.0, 'und': None, 'sign': 0})
        self.start(m, '_N99_FOLLOWING', {'key': None, 'sym': None, 'until': 0.0, 'fails': 0, 'last': 0.0})
        self.start(m, 'OWNER', dict(m.OWNER, id=OWNER_ID))
        self.spots = {}
        self.start(m, 'fyers_ltp', lambda sym: self.spots.get(sym))

    # ----- helpers
    def put_trade(self, sym=SYM, entry=100.0, bids=(95, 85, 75, 68), reason='stop-loss', after=(), days_ago=0, hh=10, mm=0, step=120, qty=65, mode='shadow', why='AI NIFTY: strong trend (conf 7/10)',
                  spot_in=None, spot_out=None, record=True, sl=None, target=None):
        """A closed trade as the ledger keeps it, with the entry record and (when record) a price path: bids is what the agent saw until it sold (the last one is the sale), after is what the follow-through saw."""
        m = self.m
        at = ist_ts(days_ago, hh, mm)
        sl = sl if sl is not None else round(entry * 0.70, 1)
        tg = target if target is not None else round(entry * 1.50, 1)
        ex = bids[-1]
        t_exit = at + step * len(bids) + 1
        self.log.append({'sym': sym, 'entry': entry, 'exit': ex, 'qty': qty, 'pnl': round((ex - entry) * qty, 1), 'why': why, 'exit_reason': reason, 'brain': 'ai', 'mode': mode, 't': t_exit, 'bracket': False})
        m._n96_q('INSERT INTO ledger96_entry(key,sym,mode,entry,at,sl,target,qty,reason,brain,seen) VALUES(?,?,?,?,?,?,?,?,?,?,?)', ('%s|%s|%d' % (sym, mode, int(at)), sym, mode, entry, at, sl, tg, qty, why, 'ai', at), write=True)
        key = m._n99_key(sym, mode, at)
        u = m._n99_underlying(sym)
        m._n99_q('INSERT INTO lab99_pos(key,sym,mode,entry,at,status,und,sign,spot_in,spot_in_t,spot_out,spot_out_t,follow_until,closed_t,closed_px,reason,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                 (key, sym, mode, entry, at, 'done', u[0] if u else None, u[1] if u else 0, spot_in, at if spot_in else None, spot_out, t_exit if spot_out else None, None, t_exit, ex, reason, at), write=True)
        if record:
            rows = [(key, at - 1, entry - 0.3, entry, entry, at - 2, 1, 'entry')]
            rows += [(key, at + step * (i + 1), b, b + 0.3, b, at + step * (i + 1) - 1, 1, 'depth') for i, b in enumerate(bids)]
            rows += [(key, t_exit + step * (j + 1), b, b + 0.3, b, t_exit + step * (j + 1) - 1, 1, 'depth') for j, b in enumerate(after)]
            m._n99_many('INSERT OR IGNORE INTO lab99_path(key,t,bid,ask,last,ltt,clean,src) VALUES(?,?,?,?,?,?,?,?)', rows)
        return key

    def dataset(self, mode='shadow'):
        return self.m._n99_dataset(mode)

    def compare(self, rule_name, mode='shadow'):
        trs, costs = self.dataset(mode)
        rule = [r for r in self.m._N99_RULES if r[0] == rule_name][0][3]
        return self.m._n99_compare(trs, rule, costs)

    def net(self, sym, qty, entry, px):
        return (px - entry) * qty - self.m._n96_charge_parts(sym, qty, entry, px)['total']


# ===================================================================================================================
# 1. THE REPLAY ENGINE (pure numbers)
# ===================================================================================================================
class TestReplay(LabCase):
    def rp(self, entry, bids, rule=None, t0=1000.0, **kw):
        return self.m._n99_replay(entry, t0, path_of(bids, t0), rule or dict(self.m._N99_NOW), **kw)

    def test_the_agents_own_rule_stops_at_minus_30_percent_and_sells_at_the_bid(self):
        r = self.rp(100, [95, 85, 75, 68, 90])
        self.assertEqual((r['px'], r['why']), (68, 'stop-loss'))
        self.assertEqual(r['t'], 1000.0 + 120 * 4)

    def test_it_sells_at_the_target_plus_50_percent(self):
        r = self.rp(100, [110, 130, 148, 152, 90])
        self.assertEqual((r['px'], r['why']), (152, 'target'))

    def test_a_stop_exactly_at_the_level_sells(self):
        self.assertEqual(self.rp(100, [80, 70.0])['why'], 'stop-loss')

    def test_the_stored_stop_and_target_are_used_for_the_agents_own_rule(self):
        """The agent sets its levels from the price it saw BEFORE the quote it bought on: the replay uses the saved levels, not new ones."""
        r = self.rp(100.2, [95, 85, 75, 69], sl=70.0, target=150.0)
        self.assertEqual((r['px'], r['why']), (69, 'stop-loss'))
        r = self.rp(100.2, [95, 85, 75, 71], sl=70.0, target=150.0)
        self.assertTrue(r.get('unknown'))

    def test_the_square_off_is_third_after_stop_and_target(self):
        path = [sample(ist_ts(0, 15, 8), 90), sample(ist_ts(0, 15, 10), 95), sample(ist_ts(0, 15, 12), 99)]
        r = self.m._n99_replay(100, ist_ts(0, 15, 0), path, dict(self.m._N99_NOW))
        self.assertEqual((r['px'], r['why']), (95, 'square-off'))
        crash = [sample(ist_ts(0, 15, 10), 60)]
        self.assertEqual(self.m._n99_replay(100, ist_ts(0, 15, 0), crash, dict(self.m._N99_NOW))['why'], 'stop-loss')

    def test_only_clean_quotes_can_end_a_trade(self):
        self.assertTrue(self.m._n99_replay(100, 1000.0, path_of([60, 50], clean=False), dict(self.m._N99_NOW)).get('unknown'))
        mixed = [sample(1120, 60, clean=False), sample(1240, 62, clean=True)]
        self.assertEqual(self.m._n99_replay(100, 1000.0, mixed, dict(self.m._N99_NOW))['t'], 1240)

    def test_quotes_before_the_purchase_are_ignored(self):
        path = [sample(900, 50)] + path_of([95, 90])
        self.assertTrue(self.m._n99_replay(100, 1000.0, path, dict(self.m._N99_NOW)).get('unknown'))

    def test_the_last_price_stands_in_when_there_is_no_bid(self):
        path = [{'t': 1120.0, 'bid': None, 'ask': None, 'last': 65.0, 'clean': True}]
        self.assertEqual(self.m._n99_replay(100, 1000.0, path, dict(self.m._N99_NOW))['px'], 65.0)

    def test_a_path_that_ends_before_the_rule_would_sell_is_unknown_never_guessed(self):
        r = self.rp(100, [95, 90, 85])
        self.assertEqual(r, {'unknown': True})

    def test_a_tighter_rule_sells_earlier(self):
        tight = dict(self.m._N99_RULES[1][3])
        r = self.rp(100, [95, 85, 75, 68], tight)
        self.assertEqual((r['px'], r['why']), (75, 'stop-loss'))

    def test_a_wider_rule_can_hold_on_through_the_agents_exit(self):
        wide = dict(self.m._N99_RULES[2][3])
        r = self.rp(100, [95, 85, 75, 68, 72, 90, 171], wide)                      # follow-through then reaches +70%
        self.assertEqual((r['px'], r['why']), (171, 'target'))

    def test_break_even_stop_saves_a_trade_that_faded(self):
        be = dict(self.m._N99_RULES[4][3])
        path = [110, 126, 118, 99, 80, 69]
        self.assertEqual(self.rp(100, path, be)['px'], 99)
        self.assertEqual(self.rp(100, path)['px'], 69)
        self.assertEqual(self.rp(100, path, be)['why'], 'raised-stop')

    def test_break_even_does_nothing_before_the_trigger(self):
        be = dict(self.m._N99_RULES[4][3])
        self.assertEqual(self.rp(100, [110, 118, 99, 80, 69], be)['px'], 69)         # never reached +25%

    def test_trailing_stop_follows_the_high(self):
        tr = dict(self.m._N99_RULES[5][3])
        r = self.rp(100, [110, 140, 175, 150, 160, 148])                             # high 175 -> stop 148.8 (15% below)
        self.assertTrue(r.get('unknown') or r['px'] > 0)
        r = self.rp(100, [110, 140, 175, 150, 160, 148], tr)
        self.assertEqual((r['px'], r['why']), (148, 'raised-stop'))

    def test_no_fixed_target_for_the_trailing_rule(self):
        tr = dict(self.m._N99_RULES[5][3])
        r = self.rp(100, [160, 200, 260, 250, 240, 220], tr)                         # runs far past +50% and keeps going
        self.assertEqual(r['px'], 220)

    def test_time_exit_gets_out_of_a_trade_that_goes_nowhere(self):
        te = dict(self.m._N99_RULES[6][3])
        flat = [100.5] * 40                                                           # 40 checks of 2 minutes: 80 minutes
        r = self.rp(100, flat, te)
        self.assertEqual(r['why'], 'time')
        self.assertGreaterEqual((r['t'] - 1000.0) / 60.0, 60)
        up = [100.5] * 5 + [112] * 40
        self.assertTrue(self.rp(100, up, te).get('unknown'))                          # up 12% at the 60-minute mark: stays in

    def test_never_overnight_sells_at_the_last_clean_quote_of_the_day(self):
        sd = dict(self.m._N99_RULES[7][3])
        t0 = ist_ts(0, 14, 40)
        day = [sample(t0 + 120 * (i + 1), 100 + i) for i in range(10)]                # to 15:00, nothing triggers
        nxt = [sample(ist_ts(-1, 9, 20), 60)]
        r = self.m._n99_replay(100, t0, day + nxt, sd)
        self.assertEqual((r['why'], r['px']), ('end-of-day', 109))
        self.assertEqual(self.m._n99_replay(100, t0, day + nxt, dict(self.m._N99_NOW))['why'], 'stop-loss')   # the agent's own rule carries it over the night

    def test_a_complete_record_squares_a_rule_off_at_the_end_and_an_incomplete_one_stays_unknown(self):
        t0 = ist_ts(0, 14, 40)
        day = [sample(t0 + 120 * (i + 1), 100 + i) for i in range(14)]                  # to 15:08, nothing triggers
        wide = dict(self.m._N99_RULES[2][3])
        r = self.m._n99_replay(100, t0, day, wide, complete=True)
        self.assertEqual((r['why'], r['px']), ('end-of-follow', 113))
        self.assertTrue(self.m._n99_replay(100, t0, day, wide).get('unknown'))
        self.assertTrue(self.m._n99_replay(100, t0, day[:6], wide, complete=False).get('unknown'))

    def test_a_record_is_complete_when_it_reaches_the_end_of_the_day_of_the_sale(self):
        f = self.m._n99_day_complete
        d = D0.isoformat()
        self.assertTrue(f([sample(ist_ts(0, 15, 8), 1)], d))
        self.assertTrue(f([sample(ist_ts(0, 15, 10), 1)], d))
        self.assertFalse(f([sample(ist_ts(0, 15, 4), 1)], d))
        self.assertFalse(f([sample(ist_ts(1, 15, 8), 1)], d))                            # the record ends on another day
        self.assertFalse(f([], d))

    def test_the_end_of_follow_exit_is_the_last_clean_quote(self):
        t0 = ist_ts(0, 14, 40)
        day = [sample(t0 + 120 * (i + 1), 100 + i) for i in range(13)] + [sample(t0 + 120 * 14, 50, clean=False)]
        r = self.m._n99_replay(100, t0, day, dict(self.m._N99_RULES[2][3]), complete=True)
        self.assertEqual(r['px'], 112)                                                    # an unclean last quote is not used

    def test_rule_rounding_matches_the_agent(self):
        r = self.rp(77.8, [54.4], None)
        self.assertEqual(r['why'], 'stop-loss')                                         # 77.8 * 0.7 = 54.46 -> 54.5; 54.4 <= 54.5
        self.assertEqual(self.rp(77.8, [54.5])['why'], 'stop-loss')
        self.assertTrue(self.rp(77.8, [54.6]).get('unknown'))

    def test_holes_in_the_record_are_found_inside_a_day_but_not_overnight(self):
        g = self.m._n99_path_gaps
        self.assertEqual(g([sample(1000, 1), sample(1100, 1), sample(1900, 1)]), 1)
        self.assertEqual(g([sample(ist_ts(0, 15, 20), 1), sample(ist_ts(-1, 9, 20), 1)]), 0)
        self.assertEqual(g(path_of([1, 2, 3, 4])), 0)

    def test_square_off_time_follows_the_agent(self):
        f = self.m._n99_sqoff
        self.assertFalse(f(ist_ts(0, 15, 9)))
        self.assertTrue(f(ist_ts(0, 15, 10)))
        self.assertFalse(f(ist_ts(0, 16, 0, today=dt.date(2026, 10, 10))))          # (a Saturday: the agent's rule only runs on weekdays)

    def test_the_replay_never_changes_its_inputs(self):
        path = path_of([95, 85, 75, 68])
        rule = dict(self.m._N99_NOW)
        before = (copy.deepcopy(path), copy.deepcopy(rule))
        self.m._n99_replay(100, 1000.0, path, rule)
        self.assertEqual((path, rule), before)


# ===================================================================================================================
# 2. WHICH TRADES CAN BE TESTED
# ===================================================================================================================
class TestUsable(LabCase):
    def usable(self, **kw):
        self.put_trade(**kw)
        trs, _ = self.dataset()
        return self.m._n99_prepare(trs[-1]), trs[-1]['lab']

    def test_a_trade_with_a_clean_record_that_replays_to_the_real_exit_is_usable(self):
        ok, lab = self.usable()
        self.assertTrue(ok)
        self.assertEqual(lab['replay_now']['px'], 68)

    def test_a_trade_from_before_the_lab_has_no_price_record(self):
        ok, lab = self.usable(record=False)
        self.assertFalse(ok)
        self.assertEqual(lab['skip'], 'no price record')

    def test_a_hole_in_the_record_makes_it_unusable(self):
        self.put_trade(bids=(95, 85, 75, 68), step=300)
        key = self.m._n99_key(SYM, 'shadow', ist_ts(0, 10, 0))
        self.m._n99_q('DELETE FROM lab99_path WHERE key=? AND t IN (?,?)', (key, ist_ts(0, 10, 0) + 600, ist_ts(0, 10, 0) + 900), write=True)
        trs, _ = self.dataset()
        self.assertFalse(self.m._n99_prepare(trs[0]))
        self.assertIn('hole', trs[0]['lab']['skip'])

    def test_a_record_that_stops_before_the_exit_is_unusable(self):
        self.put_trade(bids=(95, 85, 75, 68))
        key = self.m._n99_key(SYM, 'shadow', ist_ts(0, 10, 0))
        self.m._n99_q('DELETE FROM lab99_path WHERE key=? AND t>?', (key, ist_ts(0, 10, 0) + 130), write=True)
        trs, _ = self.dataset()
        self.assertFalse(self.m._n99_prepare(trs[0]))

    def test_a_trade_whose_replay_disagrees_with_the_real_exit_is_left_out_never_guessed(self):
        ok, lab = self.usable(bids=(95, 85, 75, 72), reason='stop-loss')           # sold at 72 although 72 is above the stop: the record cannot explain it
        self.assertFalse(ok)
        self.assertIn('did not replay', lab['skip'])

    def test_a_wrong_reason_is_also_a_mismatch(self):
        ok, lab = self.usable(bids=(95, 85, 75, 68), reason='target')
        self.assertFalse(ok)

    def test_no_entry_record_means_no_test(self):
        self.put_trade()
        self.m._n96_q('DELETE FROM ledger96_entry', write=True)
        trs, _ = self.dataset()
        self.assertFalse(self.m._n99_prepare(trs[0]))
        self.assertEqual(trs[0]['lab']['skip'], 'no entry record')

    def test_a_share_trade_is_not_used_for_the_exit_rules(self):
        ok, lab = self.usable(sym='NSE:SBIN-EQ')
        self.assertFalse(ok)
        self.assertIn('a share trade', lab['skip'])

    def test_the_decision_is_made_once(self):
        self.put_trade()
        trs, _ = self.dataset()
        self.m._n99_prepare(trs[0])
        trs[0]['lab']['path'] = []
        self.assertTrue(self.m._n99_prepare(trs[0]))


# ===================================================================================================================
# 3. THE RULES COMPARED
# ===================================================================================================================
class TestCompare(LabCase):
    def corpus(self):
        """A winner that kept running after the sale, a loser that recovered after the stop, and a trade that rose 26% and faded to the stop."""
        self.put_trade(bids=(105, 120, 135, 152), reason='target', after=(160, 170), days_ago=2)
        self.put_trade(bids=(95, 85, 75, 68), reason='stop-loss', after=(72, 90, 105, 110), days_ago=1)
        self.put_trade(bids=(110, 126, 118, 99, 80, 69), reason='stop-loss', after=(60,), days_ago=0)

    def test_the_baseline_is_the_agents_own_result(self):
        self.corpus()
        r = self.compare('now')
        trs, _ = self.dataset()
        self.assertEqual(r['pairs'], 3)
        self.assertAlmostEqual(r['var_net'], sum(t['net'] for t in trs), 6)
        self.assertAlmostEqual(r['diff'], 0.0, 6)
        self.assertEqual(r['verdict'][1], 'base')

    def test_tighter_rule_numbers(self):
        self.corpus()
        r = self.compare('tight')
        # winner: 152 (target 140 reached at the 4th check); loser: 75 (stop 75); faded: 75 (stop 75 hit at the 5th check)... checked by hand below
        self.assertEqual(r['pairs'], 3)
        expect = (self.net(SYM, 65, 100, 152) + self.net(SYM, 65, 100, 75) + self.net(SYM, 65, 100, 80))
        # the faded trade: stop 75, bids 110,126,118,99,80,69 -> first <=75 is 69
        expect = self.net(SYM, 65, 100, 152) + self.net(SYM, 65, 100, 75) + self.net(SYM, 65, 100, 69)
        self.assertAlmostEqual(r['var_net'], expect, 4)

    def test_wider_rule_can_only_be_tested_where_the_record_follows_on(self):
        self.corpus()
        r = self.compare('wide')
        # winner reaches +70% (170) in the follow-through; loser never gets to 60 or 170 and the record ends; faded trade: stop 60, bids go to 69 then follow 60 -> sold at 60
        self.assertEqual(r['unknown'], 1)
        self.assertEqual(r['pairs'], 2)
        expect = self.net(SYM, 65, 100, 170) + self.net(SYM, 65, 100, 60)
        self.assertAlmostEqual(r['var_net'], expect, 4)

    def test_a_wider_rule_that_never_triggers_is_squared_off_where_the_record_ends_when_it_followed_to_the_end_of_the_day(self):
        self.put_trade(bids=(95, 85, 75, 68), reason='stop-loss', after=(72, 80, 90, 95) + (96,) * 6, hh=14, mm=40)         # sold 14:48; followed to 15:08
        r = self.compare('wide')
        self.assertEqual((r['pairs'], r['unknown']), (1, 0))
        self.assertAlmostEqual(r['var_net'], self.net(SYM, 65, 100, 96), 4)                 # held through the stop it never reached, out at the end of the day
        self.assertGreater(r['diff'], 0)

    def test_break_even_rule_only_changes_the_trade_that_faded(self):
        self.corpus()
        r = self.compare('breakeven')
        trs, _ = self.dataset()
        self.assertAlmostEqual(r['diff'], self.net(SYM, 65, 100, 99) - trs[2]['net'], 4)
        self.assertEqual((r['better'], r['worse'], r['same']), (1, 0, 2))

    def test_never_overnight_needs_no_follow_data_when_the_agent_sold_the_same_day(self):
        self.corpus()
        r = self.compare('sameday')
        self.assertEqual(r['pairs'], 3)

    def test_entry_rules_use_every_trade_even_without_a_price_record(self):
        self.put_trade(sym=SYM_FAR, record=False, days_ago=2, bids=(95, 85, 75, 68), reason='stop-loss')    # more than a week to expiry: kept
        self.put_trade(sym=SYM, record=False, days_ago=0, bids=(105, 120, 135, 152), reason='target')       # bought the day before it expires: skipped by the 2-day rule
        r = self.compare('dte2')
        trs, _ = self.dataset()
        self.assertEqual((r['pairs'], r['taken'], r['skipped']), (2, 1, 1))
        self.assertAlmostEqual(r['var_net'], trs[0]['net'], 6)
        self.assertAlmostEqual(r['diff'], -trs[1]['net'], 6)

    def test_exit_rules_leave_out_trades_without_a_record(self):
        self.put_trade(record=False, days_ago=1)
        self.put_trade(days_ago=0)
        r = self.compare('tight')
        self.assertEqual((r['pairs'], r['unusable']), (1, 1))

    def test_skip_the_first_half_hour(self):
        self.put_trade(hh=9, mm=25, days_ago=2, record=False)
        self.put_trade(hh=10, mm=30, days_ago=1, record=False, sym=SYM_FAR)
        r = self.compare('calm')
        self.assertEqual((r['taken'], r['skipped']), (1, 1))

    def test_only_confident_trades(self):
        self.put_trade(why='AI NIFTY: x (conf 6/10)', record=False, days_ago=2, sym=SYM_FAR)
        self.put_trade(why='AI NIFTY: x (conf 9/10)', record=False, days_ago=1, sym=SYM_FAR)
        self.put_trade(why='GODMODE NIFTY bullish (score +5)', record=False, days_ago=0, sym=SYM_FAR)
        r = self.compare('conf8')
        self.assertEqual((r['taken'], r['skipped']), (1, 2))                          # no stated confidence = not shown to be high

    def test_confidence_is_read_from_the_agents_note(self):
        f = self.m._n99_conf
        self.assertEqual(f({'why': 'AI NIFTY: strong (conf 7/10)'}), 7)
        self.assertEqual(f({'why': 'x confidence 10/10'}), 10)
        self.assertIsNone(f({'why': 'GODMODE'}))
        self.assertIsNone(f({}))

    def test_the_whole_report_lists_every_rule(self):
        self.corpus()
        trs, costs = self.dataset()
        parts = self.m._n99_lab_parts('shadow', trs, costs)
        self.assertEqual(len(parts['res']), len(self.m._N99_RULES))
        for _n, _l, short, _r in self.m._N99_RULES:
            self.assertIn('• %s:' % short, parts['rules'])
        self.assertIn('3 of 3 closed trades can be used', parts['head'])
        self.assertIn('on 3 of the 3 trades it was tried on', parts['head'])
        self.assertIn('Too few trades (3 of 30 needed)', parts['rules'])
        self.assertIn('Only 3 usable trades', parts['notes'])
        self.assertIn('11 rules are tried at once', parts['notes'])
        self.assertLessEqual(len(parts['head']) + len(parts['rules']), 3900)

    def test_each_rule_line_says_which_trades_it_used_and_what_was_left_out(self):
        self.corpus()
        trs, costs = self.dataset()
        lines = {r['label']: self.m._n99_rule_line(r) for r in self.m._n99_lab_parts('shadow', trs, costs)['res']}
        self.assertIn('on the same 3 trades', lines['Tighter -25/+40'])
        self.assertIn("against the agent's", lines['Tighter -25/+40'])
        self.assertIn('1 left out: the record ends before this rule would have sold', lines['Wider -40/+70'])
        self.assertIn('on the same 2 trades', lines['Wider -40/+70'])
        self.assertIn('kept 3 of the 3', lines['Skip before 09:50'])
        self.assertTrue(lines['As agent -30/+50'].startswith('• As agent -30/+50: '))

    def test_a_trade_that_does_not_replay_is_counted_in_the_check_line(self):
        self.corpus()
        self.put_trade(bids=(95, 85, 75, 72), reason='stop-loss', days_ago=5)                    # the record cannot explain this sale
        trs, costs = self.dataset()
        head = self.m._n99_lab_parts('shadow', trs, costs)['head']
        self.assertIn('on 3 of the 4 trades it was tried on (the others are left out, never guessed)', head)
        self.assertIn('1 the agent\'s own rule did not replay to its real exit', head)

    def test_an_empty_lab_says_so(self):
        trs, costs = self.dataset()
        parts = self.m._n99_lab_parts('shadow', trs, costs)
        self.assertIsNone(parts['rules'])
        self.assertIn('No closed trades yet', parts['head'])


class TestVerdict(LabCase):
    def v(self, pairs, t, half, name='x'):
        return self.m._n99_verdict({'rule': {'name': name}, 'pairs': pairs, 't': t, 'half': half})

    def test_never_a_winner_on_fewer_than_30_trades(self):
        self.assertEqual(self.v(29, 9.0, (500, 500))[1], 'few')
        self.assertIn('29 of 30', self.v(29, 9.0, (500, 500))[0])

    def test_clear_in_both_halves_between_30_and_59_is_only_an_early_sign(self):
        r = self.v(45, 3.1, (200.0, 150.0))
        self.assertEqual(r[1], 'up')
        self.assertIn('early sign of better', r[0])
        self.assertIn('needs 60', r[0])

    def test_clear_in_both_halves_on_60_or_more_is_worth_a_closer_look(self):
        self.assertEqual(self.v(60, 2.8, (100, 100)), ('worth a closer look: better', 'up'))

    def test_a_good_whole_that_is_bad_in_one_half_is_no_clear_difference(self):
        self.assertEqual(self.v(80, 3.5, (900, -50))[1], 'flat')

    def test_a_t_below_2_5_is_no_clear_difference(self):
        self.assertEqual(self.v(80, 2.4, (100, 100))[1], 'flat')

    def test_clearly_worse_in_both_halves(self):
        self.assertEqual(self.v(80, -3.0, (-100, -100)), ('looks worse', 'down'))
        self.assertIn('early sign of worse', self.v(40, -3.0, (-100, -100))[0])

    def test_a_missing_t_or_half_is_no_clear_difference(self):
        self.assertEqual(self.v(80, None, None)[1], 'flat')

    def test_the_baseline_has_no_verdict(self):
        self.assertEqual(self.v(80, 0, (0, 0), name='now'), ('the baseline', 'base'))

    def test_end_to_end_a_rule_that_is_better_on_every_trade_is_called_only_after_enough_trades(self):
        """Many trades that each rose 26% and faded: a break-even stop is better on every one of them, in both halves."""
        for i in range(32):
            self.put_trade(bids=(110, 126, 118, 99, 80, 69), reason='stop-loss', days_ago=i, record=True)
        r = self.compare('breakeven')
        self.assertEqual(r['pairs'], 32)
        self.assertEqual((r['better'], r['worse']), (32, 0))
        self.assertGreater(r['diff'], 0)
        self.assertTrue(all(d > 0 for d in r['half']))
        # identical differences give no spread, so the t value is undefined: the report must not call it a finding
        self.assertEqual(r['verdict'][1], 'flat')

    def test_end_to_end_with_some_spread_the_same_rule_is_an_early_sign_then_worth_a_look(self):
        for i in range(62):
            bump = (i % 5)                                                     # the trades differ a little in how deep they faded
            self.put_trade(bids=(110, 126, 118, 99 - bump, 80, 69), reason='stop-loss', days_ago=i)
        r = self.compare('breakeven')
        self.assertEqual(r['pairs'], 62)
        self.assertEqual(r['verdict'][1], 'up')
        self.assertEqual(r['verdict'][0], 'worth a closer look: better')


# ===================================================================================================================
# 4. THE RECORDER
# ===================================================================================================================
class TestRecorder(LabCase):
    def setUp(self):
        super().setUp()
        m = self.m
        self.now = ist_ts(0, 10, 0)
        self.start(time, 'time', lambda: self.now)
        self.pos = {'symbol': SYM, 'entry': 100.2, 'sl': 70.0, 'target': 150.0, 'qty': 65, 'at': self.now - 300, 'reason': 'AI NIFTY: x (conf 7/10)', 'bracket': False}
        self.start(m, 'AUTO', dict(m.AUTO, mode='shadow', brain='ai', pos=self.pos, watch=[]))
        self.key = m._n99_key(SYM, 'shadow', self.pos['at'])
        m._N99_CUR.update(key=self.key, sym=SYM, mode='shadow', at=int(self.pos['at']), entry=100.2)

    def q(self, bid, ask=None, ts=None, symbol=SYM, **kw):
        return dict({'symbol': symbol, 'ts': ts if ts is not None else self.now - 1, 'last': bid, 'bid': bid, 'ask': ask if ask is not None else bid + 0.3, 'bid_qty': 650, 'ask_qty': 650}, **kw)

    def test_a_quote_for_the_open_position_is_kept_with_its_cleanliness(self):
        m = self.m
        m._n99_note_quote(SYM, self.q(95))
        self.now += 5
        m._n99_note_quote(SYM, self.q(94, ts=self.now - 90))                      # an old trade time: the agent would not accept it
        m._n99_flush()
        rows = m._n99_q('SELECT bid,clean,src FROM lab99_path WHERE key=? ORDER BY t', (self.key,))
        self.assertEqual([(r[0], r[1], r[2]) for r in rows], [(95.0, 1, 'depth'), (94.0, 0, 'depth')])

    def test_the_same_second_keeps_one_sample_per_key_and_time(self):
        m = self.m
        m._n99_note_quote(SYM, self.q(95))
        m._n99_note_quote(SYM, self.q(95))
        m._n99_flush()
        self.assertEqual(len(m._n99_q('SELECT 1 FROM lab99_path')), 1)

    def test_quotes_of_other_contracts_are_not_kept_but_the_latest_is_remembered(self):
        m = self.m
        m._n99_note_quote('NSE:SBIN-EQ', self.q(800, symbol='NSE:SBIN-EQ'))
        m._n99_flush()
        self.assertEqual(m._n99_q('SELECT 1 FROM lab99_path'), [])
        self.assertIn('NSE:SBIN-EQ', m._N99_RECENT)

    def test_the_memory_of_recent_quotes_is_bounded(self):
        for i in range(30):
            self.m._n99_note_quote('NSE:X%d-EQ' % i, self.q(10, symbol='NSE:X%d-EQ' % i))
        self.assertLessEqual(len(self.m._N99_RECENT), 8)

    def test_junk_quotes_never_raise(self):
        m = self.m
        for junk in (None, 5, 'x', {}, {'bid': 'nan'}, {'bid': float('nan'), 'ask': float('inf'), 'symbol': SYM}):
            m._n99_note_quote(SYM, junk)
        m._n99_note_quote('', self.q(1))

    def test_the_quote_function_returns_exactly_what_the_broker_gave(self):
        q = self.q(95)
        self.start(self.m, '_N99_QUOTE_PREV', lambda symbol: q)
        self.assertIs(self.m._n75_quote(SYM), q)
        self.assertEqual(self.m._N99_STATS['samples'], 1)

    def test_a_broker_error_passes_through_and_nothing_is_recorded(self):
        def boom(symbol):
            raise ValueError('Broker depth missing requested symbol')
        self.start(self.m, '_N99_QUOTE_PREV', boom)
        with self.assertRaises(ValueError):
            self.m._n75_quote(SYM)
        self.assertEqual(self.m._N99_STATS['samples'], 0)

    def test_a_failing_copy_never_disturbs_the_quote(self):
        q = self.q(95)
        self.start(self.m, '_N99_QUOTE_PREV', lambda symbol: q)
        with mock.patch.object(self.m, '_n99_note_quote', side_effect=RuntimeError('db locked')):
            self.assertIs(self.m._n75_quote(SYM), q)
        self.assertEqual(self.m._N99_STATS['errors'], 1)

    def test_the_live_agents_plain_price_is_kept_for_the_open_position_only(self):
        m = self.m
        self.start(m, '_N99_LTP_PREV', lambda symbol: 91.5)
        self.assertEqual(m.live_ltp(SYM), 91.5)
        self.assertEqual(m.live_ltp('NSE:SBIN-EQ'), 91.5)
        m._n99_flush()
        rows = m._n99_q('SELECT key,last,bid,clean,src FROM lab99_path')
        self.assertEqual(rows, [(self.key, 91.5, None, 1, 'ltp')])

    def test_a_missing_price_from_the_live_agent_is_not_kept(self):
        self.start(self.m, '_N99_LTP_PREV', lambda symbol: None)
        self.assertIsNone(self.m.live_ltp(SYM))
        self.m._n99_flush()
        self.assertEqual(self.m._n99_q('SELECT 1 FROM lab99_path'), [])

    def test_a_contract_being_followed_is_recorded_under_its_own_key(self):
        m = self.m
        m._N99_FOLLOWING.update(key='old|key|1', sym='NSE:OLD26O0622000CE', until=self.now + 900)
        m._n99_note_quote('NSE:OLD26O0622000CE', self.q(50, symbol='NSE:OLD26O0622000CE'))
        m._n99_flush()
        self.assertEqual([r[0] for r in m._n99_q('SELECT key FROM lab99_path')], ['old|key|1'])


# ===================================================================================================================
# 5. THE OBSERVER AND THE REAL AGENT TICK, END TO END
# ===================================================================================================================
class TestEndToEnd(LabCase):
    def setUp(self):
        super().setUp()
        m = self.m
        self.now = ist_ts(0, 10, 0)
        self.start(time, 'time', lambda: self.now)
        self.start(m, 'BROKER', dict(m.BROKER, token='test-token', halt=False))
        self.start(m, 'AUTO', dict(m.AUTO, mode='shadow', brain='ai', day=D0.isoformat(), trades=0, pnl=0.0, halted='', pos=None, dayloss=3000, maxtrades=1, watch=[]))
        self.start(m, 'save_data', lambda *a, **k: None)
        self.reports = []
        self.start(m, 'auto_report', lambda text: self.reports.append(text))
        self.bid = 100.0
        self.quote_calls = []

        def quote(symbol):
            self.quote_calls.append(symbol)
            return {'symbol': symbol, 'ts': self.now - 1, 'last': self.bid, 'bid': self.bid, 'ask': round(self.bid + 0.2, 2), 'bid_qty': 650, 'ask_qty': 650}
        self.start(m, '_N99_QUOTE_PREV', quote)
        self.decision = {'action': 'BUY_PE', 'index': 'NIFTY', 'confidence': 8, 'reason': 'weak close below support'}
        self.start(m, '_N99_AI_PREV', lambda now=None: self.decision)
        self.start(m, 'index_atm_option', lambda index, bullish: (SYM, 100.0, 65))
        self.spots = {'NSE:NIFTY50-INDEX': 24500.0}
        self.start(m, '_n36_kv_get', lambda k, d=None: '0' if k == 'n81_entries_paused' else d)
        self.start(m, 'mm_locked', lambda: False)
        self.start(m, '_N99_FOLLOW_GAP', 0)

    def tick(self, bid=None, advance=120):
        self.now += advance
        if bid is not None:
            self.bid = bid
        return self.m.auto_trade_tick()

    def test_the_whole_story(self):
        m = self.m
        before_keys = set(m.AUTO)
        self.tick(100.0, advance=0)                                               # 10:00 the AI says BUY_PE; the agent buys at the ask
        pos = m.AUTO['pos']
        self.assertEqual(pos['symbol'], SYM)
        self.assertAlmostEqual(pos['entry'], 100.2)
        self.assertEqual((pos['sl'], pos['target']), (70.0, 150.0))
        key = m._n99_key(SYM, 'shadow', pos['at'])
        reg = m._n99_q('SELECT und,sign,spot_in,status FROM lab99_pos WHERE key=?', (key,))
        self.assertEqual(reg, [('NSE:NIFTY50-INDEX', -1, 24500.0, 'open')])
        self.assertEqual(m._n99_q('SELECT src FROM lab99_path WHERE key=?', (key,)), [('entry',)])    # the quote it bought on starts the path
        for bid in (95.0, 85.0, 75.0):
            self.tick(bid)
            self.assertIsNotNone(m.AUTO['pos'])
        self.spots['NSE:NIFTY50-INDEX'] = 24600.0
        self.tick(68.0)                                                           # the stop: the agent sells
        self.assertIsNone(m.AUTO['pos'])
        self.assertEqual(len(self.log), 1)
        self.assertEqual((self.log[0]['exit'], self.log[0]['exit_reason']), (68.0, 'stop-loss'))
        reg = m._n99_q('SELECT status,spot_out,reason,closed_px FROM lab99_pos WHERE key=?', (key,))
        self.assertEqual(reg, [('following', 24600.0, 'stop-loss', 68.0)])
        n_agent = len(self.quote_calls)
        for bid in (72.0, 90.0, 105.0):                                           # the follow-through: one more quote per check
            self.tick(bid)
        self.assertEqual(len(self.quote_calls) - n_agent, 3)
        self.assertEqual(m._N99_STATS['follow_calls'], 3)
        rows = m._n99_q('SELECT bid,clean,src FROM lab99_path WHERE key=? ORDER BY t', (key,))
        self.assertEqual([r[0] for r in rows], [100.0, 95.0, 85.0, 75.0, 68.0, 72.0, 90.0, 105.0])
        self.assertEqual({r[1] for r in rows[1:]}, {1})
        m._N99_FOLLOWING['until'] = self.now - 1                                  # the 15:12 moment passes
        self.tick(110.0)
        self.assertEqual(m._n99_q('SELECT status FROM lab99_pos WHERE key=?', (key,)), [('done',)])
        self.assertIsNone(m._N99_FOLLOWING['key'])
        # the road is now testable
        trs, costs = self.dataset()
        self.assertEqual(len(trs), 1)
        self.assertTrue(m._n99_prepare(trs[0]), trs[0]['lab'].get('skip'))
        self.assertEqual(trs[0]['lab']['replay_now']['px'], 68.0)
        tight = self.compare('tight')
        self.assertEqual(tight['pairs'], 1)
        self.assertGreater(tight['diff'], 0)                                       # stop at 75 instead of 68
        wide = self.compare('wide')
        self.assertEqual((wide['pairs'], wide['unknown']), (0, 1))                 # it never reached the wider stop or target on the record: not guessed
        d = m._n99_direction(trs)
        self.assertEqual([(r[2]) for r in d], ['wrong'])                           # a put, and the index went UP
        self.assertEqual(set(m.AUTO) - before_keys, {'_n81_reason', '_exit_warned'})                # the agent's own bookkeeping keys; the lab adds none

    def test_what_the_agent_does_is_exactly_what_it_did_before(self):
        """The same ticks with the lab's hooks bypassed give the same agent state and the same log."""
        m = self.m

        def run():
            m.AUTO.update(pos=None, trades=0, pnl=0.0, day=D0.isoformat())
            del self.log[:]
            self.now = ist_ts(0, 10, 0)
            self.tick(100.0, advance=0)
            for bid in (95.0, 85.0, 75.0, 68.0, 72.0):
                self.tick(bid)
            return copy.deepcopy({k: v for k, v in m.AUTO.items() if k not in ('_n81_reason',)}), copy.deepcopy(self.log), list(self.reports)
        with_lab = run()
        for name in ('_n99_observe', '_n99_why_note'):
            self.start(m, name, lambda *a, **k: None)
        self.start(m, '_N99_QUOTE_PREV', self.m._N99_QUOTE_PREV)
        del self.reports[:]
        without = run()

        def norm(x):
            st, log, rep = x
            st = dict(st)
            st['pos'] = None
            for r in log:
                r.pop('t', None)
            return st, log, rep
        self.assertEqual(norm(with_lab)[0].keys(), norm(without)[0].keys())
        self.assertEqual(norm(with_lab)[1], norm(without)[1])
        self.assertEqual(norm(with_lab)[2], norm(without)[2])

    def test_no_follow_when_switched_off(self):
        m = self.m
        m._n99_set('follow', 'off')
        self.tick(100.0, advance=0)
        for bid in (95.0, 85.0, 75.0, 68.0):
            self.tick(bid)
        n = len(self.quote_calls)
        self.tick(72.0)
        self.assertEqual(len(self.quote_calls), n)
        self.assertEqual(m._n99_q('SELECT status FROM lab99_pos'), [('done',)])

    def test_a_sale_by_the_square_off_is_not_followed(self):
        m = self.m
        self.assertIsNone(m._n99_follow_plan(ist_ts(0, 15, 10), 'square-off', ist_ts(0, 15, 10)))
        self.assertIsNone(m._n99_follow_plan(ist_ts(0, 15, 11), 'target', ist_ts(0, 15, 11)))     # sold after 15:10 (carried): the day is over
        self.assertEqual(m._n99_follow_plan(ist_ts(0, 11, 0), 'target', ist_ts(0, 11, 0)), ist_ts(0, 15, 12))
        self.assertIsNone(m._n99_follow_plan(ist_ts(0, 11, 0), 'target', ist_ts(0, 15, 13)))
        self.assertIsNone(m._n99_follow_plan(ist_ts(0, 11, 0, today=dt.date(2026, 10, 10)), 'target', ist_ts(0, 11, 0, today=dt.date(2026, 10, 10))))   # a Saturday

    def test_the_follow_stops_when_the_market_closes_and_after_five_failures(self):
        m = self.m
        m._N99_FOLLOWING.update(key='k|1', sym=SYM, until=self.now + 3600, fails=0, last=0.0)
        self.start(m, '_n75_quote', lambda symbol: (_ for _ in ()).throw(ValueError('Broker depth missing')))
        for _ in range(5):
            m._n99_follow_step()
        self.assertEqual(m._N99_FOLLOWING['fails'], 5)
        m._n99_follow_step()
        self.assertIsNone(m._N99_FOLLOWING['key'])
        m._N99_FOLLOWING.update(key='k|2', sym=SYM, until=self.now + 3600, fails=0, last=0.0)
        self.session['market_open'] = False
        m._n99_follow_step()
        self.assertIsNone(m._N99_FOLLOWING['key'])

    def test_a_restart_with_a_position_open_adopts_it_without_a_second_entry_lookup(self):
        m = self.m
        self.tick(100.0, advance=0)
        key = m._n99_key(SYM, 'shadow', m.AUTO['pos']['at'])
        m._N99_CUR.update(key=None, sym=None, mode=None, at=0, entry=0.0)          # the bot restarted: memory is empty
        calls = []
        self.start(m, 'fyers_ltp', lambda s: calls.append(s) or 24500.0)
        self.tick(95.0)
        self.assertEqual(m._N99_CUR['key'], key)
        self.assertEqual(calls, [])                                                # the position was already noted: no new index lookup
        self.assertEqual(m._n99_q('SELECT COUNT(*) FROM lab99_pos')[0][0], 1)

    def test_two_looks_at_once_do_not_collide(self):
        m = self.m
        self.assertTrue(m._N99_OBS.acquire(False))
        try:
            m._n99_observe()                                                       # returns at once instead of waiting
        finally:
            m._N99_OBS.release()

    def test_the_tick_result_and_errors_pass_through(self):
        m = self.m
        self.start(m, '_N99_TICK_PREV', lambda now=None: 'tick-result')
        self.assertEqual(m.auto_trade_tick(5.0), 'tick-result')

        def boom(now=None):
            raise ValueError('agent problem')
        self.start(m, '_N99_TICK_PREV', boom)
        with self.assertRaises(ValueError):
            m.auto_trade_tick()
        rows = m._n99_q("SELECT code,detail FROM lab99_why WHERE code='error'")
        self.assertEqual(len(rows), 1)
        self.assertIn('ValueError', rows[0][1])

    def test_a_failing_look_never_disturbs_the_agent(self):
        m = self.m
        self.start(m, '_N99_TICK_PREV', lambda now=None: 'fine')
        with mock.patch.object(m, '_n99_observe', side_effect=RuntimeError('db locked')):
            self.assertEqual(m.auto_trade_tick(), 'fine')
        self.assertEqual(m._N99_STATS['errors'], 1)

    def test_a_check_that_starts_while_another_is_running_is_counted_and_not_blocked(self):
        m = self.m
        order = []

        def slow_tick(now=None):
            if not order:
                order.append('outer')
                inner = m.auto_trade_tick()                                          # the scheduler starts the next check before this one has finished
                order.append(inner)
                return 'outer-result'
            return 'inner-result'
        self.start(m, '_N99_TICK_PREV', slow_tick)
        self.assertEqual(m.auto_trade_tick(), 'outer-result')
        self.assertEqual(order, ['outer', 'inner-result'])                          # both ran, both returned their own answer
        self.assertEqual(m._N99_STATS['overlaps'], 1)
        self.assertEqual(m._n99_why_rows(m._n96_day(self.now))['overlap']['n'], 1)
        self.assertEqual(m._N99_ACTIVE['n'], 0)
        m.auto_trade_tick()
        self.assertEqual(m._N99_STATS['overlaps'], 1)                                # one after the other is not an overlap

    def test_the_running_count_comes_back_to_zero_after_an_error(self):
        m = self.m

        def boom(now=None):
            raise ValueError('agent problem')
        self.start(m, '_N99_TICK_PREV', boom)
        with self.assertRaises(ValueError):
            m.auto_trade_tick()
        self.assertEqual(m._N99_ACTIVE['n'], 0)
        with self.assertRaises(ValueError):
            m.auto_trade_tick()
        self.assertEqual(m._N99_STATS['overlaps'], 0)

    def test_more_trades_than_the_limit_is_noted_and_the_owner_hears_once_a_day(self):
        m = self.m
        self.start(m, '_N99_TICK_PREV', lambda now=None: None)
        m.AUTO.update(trades=2, maxtrades=1)
        m._n99_note_overlap(self.now)
        m.auto_trade_tick()
        m.auto_trade_tick()
        al = [t for c, t in self.sent if c == OWNER_ID and 'opened 2 trades today but its limit is 1' in t]
        self.assertEqual(len(al), 1)
        self.assertIn('1 check overlapped today', al[0])
        self.assertIn('Nothing was changed', al[0])
        self.assertEqual(m._n99_why_rows(m._n96_day(self.now))['over_limit']['n'], 2)
        self.now += 86400
        m.auto_trade_tick()
        self.assertEqual(len([1 for c, t in self.sent if c == OWNER_ID and 'but its limit is 1' in t]), 2)

    def test_no_notice_at_the_limit_or_when_alerts_are_off(self):
        m = self.m
        self.start(m, '_N99_TICK_PREV', lambda now=None: None)
        m.AUTO.update(trades=1, maxtrades=1)
        m.auto_trade_tick()
        m.AUTO['trades'] = 3
        m._n99_set('alerts', 'off')
        m.auto_trade_tick()
        self.assertEqual([t for c, t in self.sent if c == OWNER_ID and 'limit is' in t], [])
        self.assertEqual(m._n99_why_rows(m._n96_day(self.now))['over_limit']['n'], 1)          # still noted (once, on the second look); only the message is off

    def test_the_agents_state_and_log_are_untouched_by_the_look(self):
        m = self.m
        self.tick(100.0, advance=0)
        self.tick(95.0)
        before = (copy.deepcopy(m.AUTO), copy.deepcopy(self.log))
        m._n99_observe()
        m._n99_observe()
        self.assertEqual((m.AUTO, self.log), before)
        self.assertEqual(self.broker_calls, [])


# ===================================================================================================================
# 6. WHY THE AGENT DID NOT TRADE
# ===================================================================================================================
class TestWhyNot(LabCase):
    def setUp(self):
        super().setUp()
        m = self.m
        self.now = ist_ts(0, 11, 0)
        self.start(m, 'BROKER', dict(m.BROKER, token='t', halt=False))
        self.start(m, 'AUTO', dict(m.AUTO, mode='shadow', brain='ai', day=D0.isoformat(), trades=0, pnl=0.0, pos=None, dayloss=3000, maxtrades=1, watch=['NSE:SBIN-EQ']))
        self.start(m, 'mm_locked', lambda: False)
        self.start(m, '_n81_paused', lambda: False)
        self.start(m, 'can_enter', lambda now=None: True)

    def cls(self, **cap):
        base_cap = {'before': None, 'ai': None, 'gm': {}, 'entry': None, 'chain': None, 'error': None}
        base_cap.update(cap)
        return self.m._n99_classify(self.now, base_cap)

    def test_the_ai_chose_no_trade(self):
        got = self.cls(ai=('ok', {'action': 'NONE', 'confidence': 3, 'reason': 'range-bound, no edge'}))
        self.assertEqual(got[0], 'ai_none')
        self.assertIn('no edge', got[1])

    def test_the_ai_was_not_confident_enough(self):
        got = self.cls(ai=('ok', {'action': 'BUY_CE', 'confidence': 5, 'reason': 'maybe'}))
        self.assertEqual(got[0], 'ai_low')
        self.assertIn('5/10', got[1])

    def test_the_ai_gave_no_usable_answer(self):
        self.assertEqual(self.cls(ai=('ok', None))[0], 'ai_failed')

    def test_the_price_checks_refused_the_entry(self):
        got = self.cls(ai=('ok', {'action': 'BUY_PE', 'confidence': 8, 'reason': 'x'}), entry=(None, 'Entry blocked: missing/stale timestamp, invalid prices or thin/wide depth.'))
        self.assertEqual(got[0], 'entry_blocked')
        self.assertIn('thin/wide depth', got[1])

    def test_no_option_contract(self):
        self.assertEqual(self.cls(ai=('ok', {'action': 'BUY_CE', 'confidence': 9, 'reason': 'x'}), chain='NIFTY')[0], 'chain_failed')

    def test_a_share_that_is_not_on_the_watchlist(self):
        self.assertEqual(self.cls(ai=('ok', {'action': 'BUY_EQ', 'confidence': 9, 'symbol': 'NSE:TCS-EQ', 'reason': 'x'}))[0], 'eq_unlisted')
        self.assertEqual(self.cls(ai=('ok', {'action': 'BUY_EQ', 'confidence': 9, 'symbol': 'NSE:SBIN-EQ', 'reason': 'x'}))[0], 'unknown')

    def test_the_fixed_rules_brain_names_the_strongest_read(self):
        self.m.AUTO['brain'] = 'godmode'
        got = self.cls(gm={'NIFTY': (2, 'mildly bullish', 24500), 'BANKNIFTY': (-3, 'bearish', 52000), 'SENSEX': None})
        self.assertEqual(got[0], 'godmode_weak')
        self.assertIn('BANKNIFTY -3', got[1])
        self.assertIn('needs 4', got[1])

    def test_the_gates_in_the_agents_own_order(self):
        m = self.m
        m.AUTO['pnl'] = -3000.0
        self.assertEqual(self.cls()[0], 'dayloss')
        m.AUTO.update(pnl=0.0, trades=1)
        self.assertEqual(self.cls()[0], 'maxtrades')
        m.AUTO['trades'] = 0
        self.start(m, 'can_enter', lambda now=None: False)
        self.assertEqual(self.cls()[0], 'window')
        self.start(m, '_n81_paused', lambda: True)
        self.assertEqual(self.cls()[0], 'paused')
        self.start(m, 'mm_locked', lambda: True)
        self.assertEqual(self.cls()[0], 'lockdown')
        self.session.update(market_open=False, state='CLOSED_HOLIDAY', holiday='Dussehra')
        self.assertEqual(self.cls()[0], 'closed')
        self.start(m, 'BROKER', dict(m.BROKER, token='', halt=False))
        self.assertEqual(self.cls()[0], 'broker')

    def test_nothing_to_say_when_the_agent_is_off_or_managing_a_position(self):
        m = self.m
        m.AUTO['mode'] = 'off'
        self.assertIsNone(self.cls())
        m.AUTO['mode'] = 'shadow'
        m.AUTO['pos'] = {'symbol': SYM, 'at': self.now - 600, 'entry': 100, 'reason': 'r'}
        before = m._n99_key(SYM, 'shadow', self.now - 600)
        self.assertIsNone(self.cls(before=before))                                 # it was managing the open position

    def test_a_new_position_is_an_entry_and_a_sale_is_not_a_why_not(self):
        m = self.m
        m.AUTO['pos'] = {'symbol': SYM, 'at': self.now - 5, 'entry': 100, 'reason': 'AI NIFTY: weak close (conf 8/10)'}
        got = self.cls()
        self.assertEqual(got[0], 'entered')
        self.assertIn('weak close', got[1])
        m.AUTO['pos'] = None
        self.assertIsNone(self.cls(before='k'))

    def test_an_error_in_the_check(self):
        self.assertEqual(self.cls(error='KeyError')[0], 'error')

    def test_unknown_when_nothing_explains_it(self):
        self.assertEqual(self.cls()[0], 'unknown')

    def test_text_from_the_model_is_cleaned_and_cut(self):
        got = self.cls(ai=('ok', {'action': 'NONE', 'confidence': 1, 'reason': 'x\x00y\n' + 'z' * 500}))
        self.assertNotIn('\x00', got[1])
        self.assertNotIn('\n', got[1])
        self.assertLess(len(got[1]), 200)

    def test_storage_counts_each_reason_per_day_and_keeps_the_latest_detail(self):
        m = self.m
        for i in range(3):
            m._n99_why_note(self.now + 120 * i, {'before': None, 'ai': ('ok', {'action': 'NONE', 'confidence': 2, 'reason': 'flat %d' % i}), 'gm': {}, 'entry': None, 'chain': None, 'error': None})
        m._n99_why_note(self.now + 600, {'before': None, 'ai': ('ok', {'action': 'BUY_CE', 'confidence': 4, 'reason': 'unsure'}), 'gm': {}, 'entry': None, 'chain': None, 'error': None})
        rows = m._n99_why_rows(D0.isoformat())
        self.assertEqual(rows['ai_none']['n'], 3)
        self.assertEqual(rows['ai_none']['detail'].split(': ')[-1], 'flat 2')
        self.assertEqual(rows['ai_low']['n'], 1)
        ev = m._n99_q('SELECT code FROM lab99_event ORDER BY id')
        self.assertEqual([e[0] for e in ev], ['ai_none', 'ai_none', 'ai_none', 'ai_low'])      # (the detail changed each time)

    def test_a_repeated_identical_reason_is_one_event(self):
        m = self.m
        cap = {'before': None, 'ai': None, 'gm': {}, 'entry': None, 'chain': None, 'error': None}
        m.AUTO['trades'] = 1
        for i in range(5):
            m._n99_why_note(self.now + 120 * i, cap)
        self.assertEqual(m._n99_why_rows(D0.isoformat())['maxtrades']['n'], 5)
        self.assertEqual(len(m._n99_q('SELECT 1 FROM lab99_event')), 1)

    def test_the_event_list_is_bounded(self):
        m = self.m
        for i in range(450):
            m._n99_q('INSERT INTO lab99_event(t,code,detail) VALUES(?,?,?)', (i, 'ai_none', 'd%d' % i), write=True)
        m._n99_set('pruned', '')
        m._n99_prune(self.now)
        self.assertEqual(len(m._n99_q('SELECT 1 FROM lab99_event')), 400)

    def test_the_text_in_plain_words(self):
        m = self.m
        for i in range(4):
            m._n99_why_note(self.now + 120 * i, {'before': None, 'ai': ('ok', {'action': 'NONE', 'confidence': 2, 'reason': 'range bound'}), 'gm': {}, 'entry': None, 'chain': None, 'error': None})
        text = m._n99_why_text('today', D0.isoformat())
        self.assertIn('4 checks', text)
        self.assertIn('4 × the AI looked and chose no trade', text)
        self.assertIn('range bound', text)
        self.assertIn('about 2 minutes apart', text)

    def test_the_full_text_counts_the_questions_put_to_the_ai(self):
        m = self.m
        for i in range(5):
            m._n99_why_note(self.now + 120 * i, {'before': None, 'ai': ('ok', {'action': 'NONE', 'confidence': 2, 'reason': 'flat'}), 'gm': {}, 'entry': None, 'chain': None, 'error': None})
        m._n99_why_note(self.now + 900, {'before': None, 'ai': ('ok', {'action': 'BUY_CE', 'confidence': 4, 'reason': 'unsure'}), 'gm': {}, 'entry': None, 'chain': None, 'error': None})
        text = m._n99_why_text('today', D0.isoformat())
        self.assertIn('the AI brain was asked at least 6 times', text)
        self.assertIn('still uses your AI quota', text)
        self.assertNotIn('asked at least', m._n99_why_text('today', D0.isoformat(), short=True))

    def test_overlaps_show_in_the_why_text_and_the_status(self):
        m = self.m
        m._n99_note_overlap(self.now)
        m._n99_note_overlap(self.now + 60)
        text = m._n99_why_text('today', D0.isoformat())
        self.assertIn('2 × a check started while the previous one was still running', text)
        self.assertIn('A check started at', text)
        self.assertIn('overlapping checks seen so far: 2', m._n99_status_text())

    def test_the_empty_text_says_when_the_log_starts(self):
        self.assertIn('no checks recorded yet', self.m._n99_why_text('today', D0.isoformat()))

    def test_the_older_guard_status_gets_the_block_only_when_there_is_one(self):
        m = self.m
        self.start(m, '_n96_now', lambda: self.now)
        self.session['time_ist'] = '2026-10-05T11:00:00+05:30'
        plain = m._n81_status()
        self.assertNotIn('WHY THE AGENT', plain)
        m._n99_why_note(self.now, {'before': None, 'ai': ('ok', {'action': 'NONE', 'confidence': 2, 'reason': 'x'}), 'gm': {}, 'entry': None, 'chain': None, 'error': None})
        text = m._n81_status()
        self.assertTrue(text.startswith(plain))
        self.assertIn('WHY THE AGENT DID OR DID NOT TRADE (today): 1 check', text)

    def test_the_real_tick_with_an_ai_that_says_none_leaves_the_reason(self):
        m = self.m
        self.start(time, 'time', lambda: self.now)
        self.start(m, '_N99_AI_PREV', lambda now=None: {'action': 'NONE', 'confidence': 2, 'reason': 'no clear edge'})
        self.start(m, 'can_enter', lambda now=None: True)
        self.start(m, 'save_data', lambda *a, **k: None)
        m.auto_trade_tick()
        self.assertEqual(m._n99_why_rows(D0.isoformat())['ai_none']['n'], 1)

    def test_the_decision_wrappers_pass_everything_through(self):
        m = self.m
        d = {'action': 'NONE', 'confidence': 2}
        self.start(m, '_N99_AI_PREV', lambda now=None: d)
        self.assertIs(m.ai_decide(), d)
        self.start(m, '_N99_AI_PREV', lambda now=None: (_ for _ in ()).throw(KeyError('x')))
        with self.assertRaises(KeyError):
            m.ai_decide()
        r = {'score': 3, 'signal': 's', 'price': 1}
        self.start(m, '_N99_GM_PREV', lambda sym: r)
        self.assertIs(m.godmode_analyze('NIFTY'), r)
        self.start(m, '_N99_ENTRY_PREV', lambda *a, **k: (None, 'blocked'))
        self.assertEqual(m._n81_entry_quote('x', 1, 1, 1, 1), (None, 'blocked'))
        calls = []
        self.start(m, '_N99_CHAIN_PREV', lambda *a, **k: calls.append((a, k)) or 'sent')
        self.assertEqual(m._option_chain_failure_notice('NIFTY', 'AI'), 'sent')
        self.assertEqual(calls, [(('NIFTY', 'AI'), {})])

    def test_decisions_outside_an_agent_tick_are_not_recorded(self):
        m = self.m
        self.start(m, '_N99_GM_PREV', lambda sym: {'score': 3, 'signal': 's', 'price': 1})
        m.godmode_analyze('NIFTY')                                                 # a person asking for an analysis in the chat
        self.assertIsNone(getattr(m._N99_TL, 'cap', None))


# ===================================================================================================================
# 7. EXCURSIONS AND DIRECTION
# ===================================================================================================================
class TestExcursions(LabCase):
    def corpus(self):
        self.put_trade(bids=(110, 126, 118, 99, 80, 69), reason='stop-loss', after=(72, 88, 101, 104) + (110,) * 4, hh=14, mm=40, days_ago=3)   # up 26% then stopped; recovered later that day (the follow reaches 15:08)
        self.put_trade(bids=(105, 120, 135, 152), reason='target', after=(160, 175, 190, 200, 210) + (210,) * 5, hh=14, mm=40, days_ago=2)    # target, ran on
        self.put_trade(bids=(95, 85, 75, 68), reason='stop-loss', after=(60, 58), hh=10, mm=0, days_ago=1)                              # follow-through ends early

    def test_best_and_worst_price_while_held(self):
        self.corpus()
        trs, _ = self.dataset()
        rows = self.m._n99_excursions(trs)
        self.assertEqual(len(rows), 3)
        self.assertAlmostEqual(rows[0]['mfe'], 0.26, 6)
        self.assertAlmostEqual(rows[0]['mae'], -0.31, 6)
        self.assertTrue(rows[0]['gave_back'])
        self.assertAlmostEqual(rows[1]['mfe'], 0.52, 6)
        self.assertFalse(rows[1]['gave_back'])

    def test_what_happened_after_the_sale_only_counts_when_the_follow_reached_the_end_of_the_day(self):
        self.corpus()
        trs, _ = self.dataset()
        rows = self.m._n99_excursions(trs)
        self.assertTrue(rows[0]['follow_ok'] and rows[1]['follow_ok'])
        self.assertFalse(rows[2]['follow_ok'])
        self.assertAlmostEqual(rows[0]['after_max'], 0.10, 6)
        self.assertAlmostEqual(rows[1]['after_max'], 1.10, 6)

    def test_text(self):
        self.corpus()
        trs, _ = self.dataset()
        text = self.m._n99_excursions_text('shadow', trs)
        self.assertIn('3 trades with a price record', text)
        self.assertIn('median best price: +26%', text)
        self.assertIn('reached +25% at some point: 2 of 3', text)
        self.assertIn('went up 25% or more and then ended below the buying price', text)
        self.assertIn('climbed back to the buying price or higher in 1', text)
        self.assertIn('10 points higher still in 1', text)
        self.assertIn('Only 3 trades: treat these as a first look', text)

    def test_no_record_no_numbers(self):
        self.put_trade(record=False)
        trs, _ = self.dataset()
        self.assertIn('No trade has a usable price record yet (1 closed)', self.m._n99_excursions_text('shadow', trs))

    def test_a_record_with_a_hole_is_not_used(self):
        self.put_trade(bids=(95, 85, 75, 68), step=300)
        key = self.m._n99_key(SYM, 'shadow', ist_ts(0, 10, 0))
        self.m._n99_q('DELETE FROM lab99_path WHERE key=? AND t IN (?,?)', (key, ist_ts(0, 10, 0) + 600, ist_ts(0, 10, 0) + 900), write=True)
        trs, _ = self.dataset()
        self.assertEqual(self.m._n99_excursions(trs), [])


class TestDirection(LabCase):
    def test_right_wrong_and_flat(self):
        self.put_trade(sym=SYM, spot_in=24500.0, spot_out=24400.0, days_ago=4)                     # a put, the index fell: right
        self.put_trade(sym=SYM_CE, bids=(105, 120, 135, 152), reason='target', spot_in=24500.0, spot_out=24650.0, days_ago=3)    # a call, the index rose: right
        self.put_trade(sym=SYM, spot_in=24500.0, spot_out=24600.0, days_ago=2)                     # a put, the index rose: wrong
        self.put_trade(sym=SYM_CE, spot_in=24500.0, spot_out=24501.0, days_ago=1)                  # hardly moved
        trs, _ = self.dataset()
        rows = self.m._n99_direction(trs)
        self.assertEqual([r[2] for r in rows], ['right', 'right', 'wrong', 'flat'])
        self.assertAlmostEqual(rows[0][1], 100 / 24500.0, 8)

    def test_trades_without_both_index_levels_or_with_late_lookups_are_left_out(self):
        self.put_trade(spot_in=24500.0, days_ago=3)                                              # no level at the sale
        self.put_trade(spot_in=24500.0, spot_out=24400.0, days_ago=2)
        key = self.m._n99_key(SYM, 'shadow', ist_ts(2, 10, 0))
        self.m._n99_q('UPDATE lab99_pos SET spot_in_t=? WHERE key=?', (ist_ts(2, 10, 0) + 3600, key), write=True)    # the lookup was an hour late (a restart)
        trs, _ = self.dataset()
        self.assertEqual(self.m._n99_direction(trs), [])

    def test_text(self):
        self.put_trade(sym=SYM, spot_in=24500.0, spot_out=24400.0, bids=(105, 120, 135, 152), reason='target', days_ago=4)     # right direction and it won
        self.put_trade(sym=SYM, spot_in=24500.0, spot_out=24600.0, bids=(105, 120, 135, 152), reason='target', days_ago=3)     # wrong direction but the option still won
        self.put_trade(sym=SYM, spot_in=24500.0, spot_out=24380.0, days_ago=2)                                                 # right direction and still lost (stopped on the way)
        trs, _ = self.dataset()
        text = self.m._n99_direction_text('shadow', trs)
        self.assertIn('3 trades with the index noted at both ends', text)
        self.assertIn('moved the expected way: 2 · the other way: 1', text)
        self.assertIn('direction hit rate 67%', text)
        self.assertIn('made money in 1 and lost in 1', text)
        self.assertIn('still made money in 1 of 1', text)
        self.assertIn('Only 3 trades', text)

    def test_underlying_and_sign(self):
        f = self.m._n99_underlying
        self.assertEqual(f(SYM), ('NSE:NIFTY50-INDEX', -1))
        self.assertEqual(f(SYM_CE), ('NSE:NIFTY50-INDEX', 1))
        self.assertEqual(f('NSE:BANKNIFTY26OCT52000CE'), ('NSE:NIFTYBANK-INDEX', 1))
        self.assertEqual(f('NSE:SBIN-EQ'), ('NSE:SBIN-EQ', 1))
        self.assertIsNone(f('weird'))

    def test_an_index_lookup_that_fails_is_simply_missing(self):
        self.start(self.m, 'fyers_ltp', lambda s: (_ for _ in ()).throw(RuntimeError('x')))
        self.assertIsNone(self.m._n99_spot('NSE:NIFTY50-INDEX'))
        self.start(self.m, 'fyers_ltp', lambda s: None)
        self.assertIsNone(self.m._n99_spot('NSE:NIFTY50-INDEX'))
        self.start(self.m, 'fyers_ltp', lambda s: float('nan'))
        self.assertIsNone(self.m._n99_spot('NSE:NIFTY50-INDEX'))


# ===================================================================================================================
# 8. WHAT-IF
# ===================================================================================================================
class TestWhatIf(LabCase):
    def test_parse(self):
        p = self.m._n99_whatif_parse
        r = p('what if stop 20 target 40')
        self.assertEqual((r['stop'], r['target']), (0.2, 0.4))
        self.assertEqual(r['said'], 'stop 20%, target 40%')
        r = p('lab what if stop loss was 25% and the target was 60%')
        self.assertEqual((r['stop'], r['target']), (0.25, 0.6))
        r = p('break-even 25')
        self.assertEqual((r['be_at'], r['stop'], r['target']), (0.25, 0.30, 0.50))
        r = p('trailing 20/15')
        self.assertEqual((r['trail_at'], r['trail']), (0.2, 0.15))
        r = p('trail 30 and 10')
        self.assertEqual((r['trail_at'], r['trail']), (0.3, 0.1))
        r = p('time exit 45 minutes')
        self.assertEqual((r['time_min'], r['time_need']), (45, 0.10))
        r = p('time 60/5')
        self.assertEqual((r['time_min'], r['time_need']), (60, 0.05))
        self.assertTrue(p('never carry overnight')['eod'])
        self.assertIsNone(p('hello there'))
        self.assertIsNone(p(''))

    def test_out_of_range_numbers_are_refused_with_a_reason(self):
        p = self.m._n99_whatif_parse
        for q in ('stop 99', 'stop 2', 'target 900', 'break-even 1', 'trailing 300', 'trailing 20/90', 'time 1', 'time 500'):
            r = p(q)
            self.assertIn('error', r, q)

    def test_the_text_compares_with_the_agents_own_rule_on_the_same_trades(self):
        self.put_trade(bids=(95, 85, 75, 68), reason='stop-loss', days_ago=2)
        self.put_trade(bids=(110, 126, 118, 99, 80, 69), reason='stop-loss', days_ago=1)
        trs, costs = self.dataset()
        rule = self.m._n99_whatif_parse('stop 25 break-even 25')
        text = self.m._n99_whatif_text('shadow', trs, costs, rule)
        self.assertIn('WHAT IF (virtual money): stop 25%, break-even once up 25%', text)
        self.assertIn('On the 2 usable trades', text)
        self.assertIn('the agent\'s own rule:', text)
        self.assertIn('would have done better', text)
        self.assertIn('Verdict: too few trades', text)
        self.assertIn('one rule picked after seeing the results', text)

    def test_nothing_usable_says_so(self):
        self.put_trade(record=False)
        trs, costs = self.dataset()
        text = self.m._n99_whatif_text('shadow', trs, costs, self.m._n99_whatif_parse('stop 20'))
        self.assertIn('No usable trades yet (1 closed, 0 with a usable price record)', text)

    def test_the_command_answers_without_a_broker_or_an_ai(self):
        self.put_trade()
        out = self.say('lab what if stop 20 target 40')
        self.assertIn('WHAT IF', out)
        self.assertEqual((self.broker_calls, self.ai_calls), ([], []))
        self.assertIn('Tell me the rule in numbers', self.say('lab what if'))
        self.assertIn('must be between', self.say('lab what if stop 99'))


# ===================================================================================================================
# 9. WEEKLY AND MONTHLY
# ===================================================================================================================
class TestPeriods(LabCase):
    def setUp(self):
        super().setUp()
        m = self.m
        self.holidays = set()
        self.start(m, '_n81_session', lambda now=None, exchange='NSE': dict(self.session, state='CLOSED_HOLIDAY' if _day_of(now) in self.holidays else 'OPEN'))
        self.sent_days = []

    def test_week_and_month_bounds(self):
        b = self.m._n99_bounds
        self.assertEqual(b('week', '2026-10-07'), ('2026-10-05', '2026-10-11', 'week 05 Oct to 11 Oct'))
        self.assertEqual(b('week', '2026-10-07', -1)[:2], ('2026-09-28', '2026-10-04'))
        self.assertEqual(b('month', '2026-10-07'), ('2026-10-01', '2026-10-31', 'October 2026'))
        self.assertEqual(b('month', '2026-10-07', -1)[:2], ('2026-09-01', '2026-09-30'))
        self.assertEqual(b('month', '2026-01-15', -1)[:2], ('2025-12-01', '2025-12-31'))
        self.assertEqual(b('month', '2026-12-15', 1)[:2], ('2027-01-01', '2027-01-31'))
        self.assertEqual(b('month', '2028-02-10')[:2], ('2028-02-01', '2028-02-29'))

    def test_the_last_trading_day_of_a_week_skips_holidays_and_weekends(self):
        m = self.m
        self.assertTrue(m._n99_last_trading_day('week', '2026-10-09'))                    # a Friday
        self.assertFalse(m._n99_last_trading_day('week', '2026-10-08'))
        self.holidays.add('2026-10-09')
        self.assertTrue(m._n99_last_trading_day('week', '2026-10-08'))                    # Friday is a holiday: Thursday is the last
        self.assertFalse(m._n99_last_trading_day('week', '2026-10-07'))
        self.assertTrue(m._n99_last_trading_day('month', '2026-10-30'))
        self.assertFalse(m._n99_last_trading_day('month', '2026-10-29'))
        self.holidays.add('2026-10-30')
        self.assertTrue(m._n99_last_trading_day('month', '2026-10-29'))

    def trades(self):
        self.put_trade(bids=(105, 120, 135, 152), reason='target', days_ago=7, record=False)           # last week (Mon 28 Sep)
        self.put_trade(bids=(95, 85, 75, 68), reason='stop-loss', days_ago=5, record=False)           # last week (Wed 30 Sep)
        self.put_trade(bids=(105, 120, 135, 152), reason='target', days_ago=-1, record=False)         # this week (Tue 6 Oct)
        self.put_trade(bids=(95, 85, 75, 68), reason='stop-loss', days_ago=0, record=False)           # this week (Mon 5 Oct)

    def test_the_week_text(self):
        self.trades()
        all_real = [t for t in self.m._n96_load() if not t['void']]
        text, mine = self.m._n99_period_text('week', D0.isoformat(), 0, 'shadow', self.m._n96_costs(), all_real)
        self.assertEqual(len(mine), 2)
        self.assertIn('WEEK · week 05 Oct to 11 Oct · virtual money', text)
        self.assertIn('2 trades: 1 won, 1 lost', text)
        self.assertIn('the week before:', text)
        self.assertIn('worst dip inside the week', text)
        self.assertIn('too few to judge skill', text)

    def test_an_empty_period(self):
        text, mine = self.m._n99_period_text('week', D0.isoformat(), 0, 'shadow', self.m._n96_costs(), [])
        self.assertEqual(mine, [])
        self.assertIn('No closed trades in this week', text)

    def test_a_trade_carried_over_a_night_is_flagged(self):
        self.put_trade(bids=(105, 120, 135, 152), reason='target', days_ago=0, record=False)
        self.log[-1]['t'] += 86400                                                                  # sold the next day
        all_real = [t for t in self.m._n96_load() if not t['void']]
        text, _ = self.m._n99_period_text('month', D0.isoformat(), 0, 'shadow', self.m._n96_costs(), all_real)
        self.assertIn('held over a night', text)

    def test_the_reasons_for_no_entry_join_the_report(self):
        m = self.m
        self.put_trade(days_ago=0, record=False)
        for i in range(6):
            m._n99_q('INSERT OR REPLACE INTO lab99_why(day,code,n,first_t,last_t,detail) VALUES(?,?,?,?,?,?)', (D0.isoformat(), 'ai_none', 6, 1, 2, 'x'), write=True)
        all_real = [t for t in m._n96_load() if not t['void']]
        text, _ = m._n99_period_text('week', D0.isoformat(), 0, 'shadow', m._n96_costs(), all_real)
        self.assertIn('of 6 checks the agent mostly did not trade because: the AI looked and chose no trade (6)', text)

    def test_the_command_sends_the_text_the_csv_and_the_chart(self):
        self.put_trade(days_ago=0, record=False)
        self.put_trade(bids=(105, 120, 135, 152), reason='target', days_ago=0, hh=12, record=False)
        out = self.say('lab week')
        self.assertIn('WEEK', out)
        self.assertEqual(len(self.files), 1)
        self.assertTrue(self.files[0][2].endswith('.csv'))
        self.assertEqual(len(self.images), 1)

    def test_last_week_and_last_month(self):
        self.put_trade(days_ago=7, record=False)
        self.assertIn('week 28 Sep to 04 Oct', self.say('lab last week'))
        self.assertIn('September 2026', self.say('lab last month'))

    def day_report(self, day, on_demand=False):
        self.start(self.m, '_N99_EOD_PREV', lambda chat_id, on_demand=False, day=None: None)
        n = len(self.sent)
        self.m.trading_day_report(OWNER_ID, on_demand, day)
        return '\n'.join(t for c, t in self.sent[n:] if c == OWNER_ID)

    def test_sent_once_on_the_last_trading_day_after_the_day_end_card(self):
        self.put_trade(days_ago=0, record=False)
        self.start(self.m, '_n96_now', lambda: ist_ts(-4, 16, 0))                               # Friday 9 Oct, 4 days after D0
        self.start(self.m, 'fyers_today', lambda: '2026-10-09')
        text = self.day_report('2026-10-09')
        self.assertIn('WEEK', text)
        self.assertEqual(self.m._N99_STATS['weekly'], 1)
        again = self.day_report('2026-10-09')
        self.assertNotIn('WEEK', again)

    def test_a_day_without_a_trade_gets_one_line_with_the_reasons_after_the_card(self):
        m = self.m
        for i in range(4):
            m._n99_q('INSERT OR REPLACE INTO lab99_why(day,code,n,first_t,last_t,detail) VALUES(?,?,?,?,?,?)', ('2026-10-07', 'ai_none' if i < 3 else 'window', 10 + i, 1, 2, 'x'), write=True)
        text = self.day_report('2026-10-07')
        self.assertIn('No trade today.', text)
        self.assertIn('× the AI looked and chose no trade', text)
        self.assertIn('“lab why” has the detail', text)
        self.assertNotIn('WEEK', text)
        self.assertIn('No trade today.', self.day_report('2026-10-07', on_demand=True))          # also when someone asks for the card

    def test_no_such_line_when_the_agent_traded_or_nothing_was_recorded(self):
        m = self.m
        m._n99_q('INSERT INTO lab99_why(day,code,n,first_t,last_t,detail) VALUES(?,?,?,?,?,?)', ('2026-10-07', 'ai_none', 5, 1, 2, 'x'), write=True)
        m._n99_q('INSERT INTO lab99_why(day,code,n,first_t,last_t,detail) VALUES(?,?,?,?,?,?)', ('2026-10-07', 'entered', 1, 1, 2, 'x'), write=True)
        self.assertEqual(self.day_report('2026-10-07'), '')
        self.assertEqual(self.day_report('2026-10-06'), '')

    def test_not_sent_midweek_nor_when_someone_asks_for_the_card(self):
        self.put_trade(days_ago=0, record=False)
        self.assertNotIn('WEEK', self.day_report('2026-10-07'))
        self.assertNotIn('WEEK', self.day_report('2026-10-09', on_demand=True))

    def test_the_thursday_before_a_friday_holiday(self):
        self.put_trade(days_ago=0, record=False)
        self.holidays.add('2026-10-09')
        self.assertIn('WEEK', self.day_report('2026-10-08'))

    def test_the_month_report_goes_on_the_last_trading_day_of_the_month(self):
        self.put_trade(days_ago=0, record=False)
        text = self.day_report('2026-10-30')
        self.assertIn('MONTH', text)
        self.assertIn('WEEK', text)                                                              # 30 Oct is also a Friday

    def test_can_be_switched_off(self):
        self.put_trade(days_ago=0, record=False)
        self.say('lab weekly off')
        self.say('lab monthly off')
        self.assertEqual(self.day_report('2026-10-30'), '')

    def test_no_trades_in_the_period_sends_nothing(self):
        self.put_trade(days_ago=40, record=False)
        self.assertEqual(self.day_report('2026-10-09'), '')

    def test_nothing_is_sent_when_nobody_is_the_owner(self):
        self.start(self.m, 'OWNER', {})
        self.put_trade(days_ago=0, record=False)
        self.assertEqual(self.day_report('2026-10-09'), '')


def _day_of(ts):
    if ts is None:
        return None
    return dt.datetime.fromtimestamp(float(ts), IST).date().isoformat()


# ===================================================================================================================
# 10. ALERTS
# ===================================================================================================================
class TestAlerts(LabCase):
    def feed(self, *results, start=20):
        """Add closed trades with these results (+ win, - loss), one per day, oldest first."""
        for i, r in enumerate(results):
            if r > 0:
                self.put_trade(bids=(105, 120, 135, 152), reason='target', days_ago=start - i, record=False)
            else:
                self.put_trade(bids=(95, 85, 75, 68), reason='stop-loss', days_ago=start - i, record=False)

    def alert_texts(self):
        return [t for c, t in self.sent if c == OWNER_ID and t.startswith('⚠️')]

    def test_the_first_look_is_silent_about_history(self):
        self.feed(-1, -1, -1, -1, -1)
        self.m._n99_check_alerts()
        self.assertEqual(self.alert_texts(), [])

    def test_a_new_streak_after_the_first_look_raises_one_alert(self):
        m = self.m
        self.feed(+1, +1)
        m._n99_check_alerts()
        for k, days_ago in enumerate((4, 3, 2, 1)):
            self.put_trade(bids=(95, 85, 75, 68), reason='stop-loss', days_ago=days_ago, record=False)
            m._n99_check_alerts()
        al = self.alert_texts()
        self.assertEqual(len(al), 1)
        self.assertIn('4 losing trades in a row', al[0])
        self.assertIn('Practice agent', al[0])
        self.assertIn('Nothing was changed', al[0])
        self.put_trade(bids=(95, 85, 75, 68), reason='stop-loss', days_ago=0, record=False)       # a fifth loss: no second alert for the same streak
        m._n99_check_alerts()
        self.assertEqual(len(self.alert_texts()), 1)

    def test_a_win_re_arms_the_streak_alert(self):
        m = self.m
        self.feed(+1)
        m._n99_check_alerts()
        days = list(range(12, 0, -1))
        seq = [-1, -1, -1, -1, +1, -1, -1, -1, -1]
        for r, d in zip(seq, days):
            self.feed(r, start=d)
            m._n99_check_alerts()
        self.assertEqual(len(self.alert_texts()), 2)

    def test_a_deep_dip_raises_one_alert_with_the_owners_limit(self):
        m = self.m
        self.say('lab alerts streak=20 dip=2000')
        self.feed(+1)
        m._n99_check_alerts()
        for d in (5, 4, 3):
            self.feed(-1, start=d)
            m._n99_check_alerts()
        al = [a for a in self.alert_texts() if 'below its high point' in a]
        self.assertEqual(len(al), 1)
        self.assertIn('your alert limit is ₹2,000', al[0])

    def test_the_dip_alert_comes_again_only_after_the_dip_has_eased(self):
        m = self.m
        self.say('lab alerts streak=20 dip=2000')
        self.feed(+1)
        m._n99_check_alerts()
        for d in (9, 8, 7):
            self.feed(-1, start=d)
            m._n99_check_alerts()
        for d in (6, 5, 4, 3):
            self.feed(+1, start=d)
            m._n99_check_alerts()
        for d in (2, 1, 0):
            self.feed(-1, start=d)
            m._n99_check_alerts()
        self.assertEqual(len([a for a in self.alert_texts() if 'below its high point' in a]), 2)

    def test_the_default_dip_limit_is_five_daily_loss_limits(self):
        self.assertEqual(self.m._n99_dip_limit(), 15000.0)
        self.m.AUTO['dayloss'] = 1000
        self.assertEqual(self.m._n99_dip_limit(), 5000.0)
        self.say('lab alerts dip=7000')
        self.assertEqual(self.m._n99_dip_limit(), 7000.0)
        self.say('lab alerts dip=0')
        self.assertEqual(self.m._n99_dip_limit(), 5000.0)

    def test_off_means_off_and_on_means_on(self):
        m = self.m
        self.say('lab alerts off')
        self.feed(+1)
        m._n99_check_alerts()
        self.feed(-1, -1, -1, -1, start=10)
        m._n99_check_alerts()
        self.assertEqual(self.alert_texts(), [])
        self.assertIn('ALERTS: ON', self.say('lab alerts on'))

    def test_settings_have_limits_and_bad_words_change_nothing(self):
        self.assertIn('must be between', self.say('lab alerts streak=1'))
        self.assertIn('must be between', self.say('lab alerts streak=99'))
        self.assertIn('did not understand', self.say('lab alerts banana'))
        self.assertEqual(self.m._n99_num('streak', 2, 20), 4)
        self.assertIn('streak 6', self.say('lab alerts streak=6').replace('losing streak 6', 'streak 6'))

    def test_a_live_alert_says_real_money(self):
        m = self.m
        self.put_trade(mode='live', bids=(105, 120, 135, 152), reason='target', days_ago=9, record=False)
        m._n99_check_alerts()
        for d in (4, 3, 2, 1):
            self.put_trade(mode='live', bids=(95, 85, 75, 68), reason='stop-loss', days_ago=d, record=False)
            m._n99_check_alerts()
        self.assertIn('LIVE (real money)', self.alert_texts()[0])

    def test_the_alert_goes_to_the_owner_only_and_never_through_the_push_channels(self):
        m = self.m
        pushed = []
        self.start(m, 'ntfy_send', lambda *a, **k: pushed.append(a))
        self.start(m, 'wa_send', lambda *a, **k: pushed.append(a))
        self.feed(+1)
        m._n99_check_alerts()
        self.feed(-1, -1, -1, -1, start=10)
        m._n99_check_alerts()
        self.assertEqual({c for c, t in self.sent if t.startswith('⚠️')}, {OWNER_ID})
        self.assertEqual(pushed, [])


# ===================================================================================================================
# 11. READY FOR LIVE?
# ===================================================================================================================
class TestReady(LabCase):
    def test_no_trades(self):
        text = self.m._n99_ready_text('shadow', [])
        self.assertIn('nothing to check', text)

    def test_a_short_record_fails_the_first_check_and_says_it_is_advice_only(self):
        for i in range(5):
            self.put_trade(bids=(105, 120, 135, 152), reason='target', days_ago=i, record=False)
        trs, _ = self.dataset()
        text = self.m._n99_ready_text('shadow', trs)
        self.assertIn('✖ at least 60 trades over at least 20 trading days: 5 trades over 5 days', text)
        self.assertIn('✔ a profit after estimated charges', text)
        self.assertIn('“/autotrade live” is not blocked or changed', text)
        self.assertIn('Not yet', text)

    def test_a_strong_record_passes_every_check(self):
        for i in range(70):
            if i % 4 == 3:
                self.put_trade(bids=(95, 85, 75, 68), reason='stop-loss', days_ago=i, record=False)
            else:
                self.put_trade(bids=(105, 120, 135, 152), reason='target', days_ago=i, record=False)
        trs, _ = self.dataset()
        text = self.m._n99_ready_text('shadow', trs)
        self.assertEqual(text.count('✔'), 7, text)
        self.assertIn('7 of 7 checks pass.', text)
        self.assertIn('Passing does not mean real trading will make money', text)

    def winners(self, n, entry0=100.0, **kw):
        """n winners, each bought at a slightly different price (so that the ledger can tell the entries apart)."""
        for i in range(n):
            e = entry0 + 0.5 * i
            self.put_trade(entry=e, bids=(e * 1.05, e * 1.2, e * 1.35, e * 1.52), reason='target', days_ago=kw.get('start', 30) - i, record=False, qty=kw.get('qty', 65))

    def test_one_trade_making_most_of_the_profit_fails(self):
        self.winners(9)
        self.put_trade(entry=90.0, bids=(95, 120, 150, 140), reason='target', days_ago=0, record=False, qty=650, sl=63.0, target=135.0)      # one big trade
        trs, _ = self.dataset()
        s = self.m._n96_stats(trs)
        self.assertGreater(s['best']['net'] / s['net'], 0.4)
        text = self.m._n99_ready_text('shadow', trs)
        self.assertIn('✖ no single trade made more than 40% of the profit', text)

    def test_profit_that_comes_from_overnight_carries_fails(self):
        for i in range(8):
            e = 100.0 + 0.5 * i
            self.put_trade(entry=e, bids=(e * 1.05, e * 1.2, e * 1.35, e * 1.52), reason='target', days_ago=20 - i, record=False)
            self.log[-1]['t'] += 86400                                                           # every winner was held over a night
        for i in range(3):
            e = 80.0 + 0.5 * i
            self.put_trade(entry=e, bids=(e * 0.99, e * 0.98, e * 0.97, e * 0.96), reason='square-off', days_ago=10 - i, record=False)
        trs, _ = self.dataset()
        text = self.m._n99_ready_text('shadow', trs)
        self.assertIn('✖ less than half of the profit comes from trades carried over a night: 8 carried trades', text)

    def test_with_no_profit_the_profit_based_checks_are_marked_not_applicable_not_passed(self):
        for i in range(5):
            e = 100.0 + 0.5 * i
            self.put_trade(entry=e, bids=(e * 0.95, e * 0.85, e * 0.75, e * 0.69), reason='stop-loss', days_ago=10 - i, record=False)
        trs, _ = self.dataset()
        text = self.m._n99_ready_text('shadow', trs)
        self.assertIn('– no single trade made more than 40% of the profit: not applicable: there is no profit yet', text)
        self.assertIn('– less than half of the profit comes from trades carried over a night: not applicable', text)
        self.assertRegex(text, r'1 of 5 checks pass \(2 not applicable yet\)\.')
        self.assertNotIn('✔ no single', text)

    def test_the_check_is_only_a_report(self):
        self.put_trade(record=False)
        before = copy.deepcopy(self.m.AUTO)
        self.say('lab ready')
        self.say('is the agent ready for live')
        self.assertEqual(self.m.AUTO, before)
        self.assertEqual(self.broker_calls, [])


# ===================================================================================================================
# 12. THE FRONT DOOR
# ===================================================================================================================
class TestFrontDoor(LabCase):
    LAB = ('lab', 'Lab', '/lab', 'lab help', 'lab status', 'lab what if stop 20 target 40', 'lab excursions', 'lab direction', 'lab why', 'lab why week', 'lab week', 'lab month', 'lab last week', 'lab ready',
           'lab alerts', 'lab follow', 'lab weekly', 'lab live')
    NL = {
        'what if the stop was 20% and the target was 40%': 'WHAT IF',
        'what if my stop loss was 25 percent': 'WHAT IF',
        "what if the agent's target was 30%": 'WHAT IF',
        'which exit rules would have done better': 'LAB',
        'would a break-even stop have helped the trades': 'LAB',
        'compare the other exit rules': 'LAB',
        'how far do the trades go before they end': 'HOW FAR THE TRADES WENT',
        'excursions': 'HOW FAR THE TRADES WENT',
        'direction hit rate': 'DIRECTION',
        'is the agent right about the direction': 'DIRECTION',
        'why did the agent not trade today': 'WHY THE AGENT',
        "why didn't the paper agent make any trades this week": 'WHY THE AGENT',
        'why no trades today': 'WHY THE AGENT',
        'is the agent ready for live': 'LIVE-READINESS',
        'can I go live': 'LIVE-READINESS',
        'live readiness check': 'LIVE-READINESS',
        'weekly trading report': 'WEEK',
        "this week's agent report": 'WEEK',
        'last month trading summary': 'MONTH',
    }
    NOT = ('lab report for my blood test', 'lab results are ready', 'lab test tomorrow', 'chemistry lab', 'what if the target is a book of 40 pages', 'what if I miss the bus', 'why did you not trade',
           "why didn't you trade", 'check trading safety', 'is the market open', 'ledger', 'show my ledger', 'ledger week', 'full paper trading report', 'how is the paper agent doing', 'how does the paper agent decide',
           'how do I stop smoking', 'what is a stop loss order', 'explain trailing stop loss', 'compare iphone and pixel', 'how far is the airport', 'is my phone ready for the update', 'weekly report on my sales', 'monthly budget')

    def test_lab_commands_reach_the_lab_and_are_not_passed_on(self):
        for q in self.LAB:
            n = len(self.sent)
            self.passed.clear()
            self.m.handle(self.msg(q))
            self.assertEqual(self.passed, [], q)
            self.assertTrue(any(c == OWNER_ID for c, t in self.sent[n:]), q)

    def test_plain_sentences(self):
        self.start(self.m, '_n96_now', lambda: ist_ts(0, 16, 0))
        self.m._n99_q('INSERT INTO lab99_why(day,code,n,first_t,last_t,detail) VALUES(?,?,?,?,?,?)', (D0.isoformat(), 'ai_none', 3, 1, 2, 'x'), write=True)
        for q, want in self.NL.items():
            n = len(self.sent)
            self.passed.clear()
            self.m.handle(self.msg(q))
            self.assertEqual(self.passed, [], q)
            got = '\n'.join(t for c, t in self.sent[n:] if c == OWNER_ID)
            self.assertIn(want, got, q)

    def test_other_sentences_go_on_to_the_older_handlers(self):
        for q in self.NOT:
            self.passed.clear()
            n = len(self.sent)
            self.m.handle(self.msg(q))
            lab_said = [t for c, t in self.sent[n:] if '🧪' in t or '🔎' in t or '📆' in t]
            if q in ('ledger', 'show my ledger', 'ledger week', 'full paper trading report', 'how is the paper agent doing', 'how does the paper agent decide'):
                self.assertEqual(lab_said, [], q)                                           # the ledger answers these, as before
                self.assertEqual(self.passed, [], q)
            else:
                self.assertEqual(lab_said, [], q)
                self.assertEqual(len(self.passed), 1, q)

    def test_the_ledgers_own_phrases_are_untouched(self):
        for q in ('ledger', 'ledger week', 'ledger logic', 'ledger costs', 'full paper trading report', 'how is the paper agent doing'):
            n = len(self.sent)
            self.m.handle(self.msg(q))
            text = '\n'.join(t for c, t in self.sent[n:] if c == OWNER_ID)
            self.assertTrue('LEDGER' in text or 'HOW THE STOCK-MARKET AGENT DECIDES' in text or 'CHARGES' in text.upper(), q)
            self.assertNotIn('🧪', text, q)

    def test_the_older_guard_phrases_are_untouched(self):
        for q in ('why did you not trade', "why didn't you trade", 'check trading safety'):
            n = len(self.sent)
            self.passed.clear()
            self.m.handle(self.msg(q))
            self.assertEqual(len(self.passed), 1, q)                                         # they are the guard's, which sits below these layers

    def test_a_guest_cannot_use_the_lab(self):
        self.put_trade()
        for q in ('lab', 'lab why', 'lab what if stop 20', 'weekly trading report', 'is the agent ready for live'):
            n = len(self.sent)
            self.passed.clear()
            self.m.handle(self.guest(q))
            self.assertEqual(len(self.passed), 1, q)
            self.assertFalse(any('🧪' in t or '🔎' in t or '📆' in t or '✅' in t for c, t in self.sent[n:]), q)

    def test_a_file_a_picture_or_a_group_is_not_a_lab_request(self):
        for extra in ({'document': {'file_id': 'x'}}, {'photo': [{'file_id': 'y'}]}):
            self.passed.clear()
            self.m.handle(self.msg('lab', **extra))
            self.assertEqual(len(self.passed), 1)
        self.passed.clear()
        self.m.handle({'chat': {'id': OWNER_ID, 'type': 'group'}, 'from': {'id': OWNER_ID}, 'message_id': 4, 'text': 'lab'})
        self.assertEqual(len(self.passed), 1)

    def test_a_lab_command_never_calls_a_broker_or_an_ai_or_changes_the_agent(self):
        self.put_trade()
        before = copy.deepcopy(self.m.AUTO)
        for q in ('lab', 'lab what if stop 20 target 40', 'lab excursions', 'lab direction', 'lab why', 'lab week', 'lab month', 'lab ready', 'lab status', 'lab help', 'lab alerts', 'lab follow'):
            self.say(q)
        self.assertEqual((self.broker_calls, self.ai_calls), ([], []))
        self.assertEqual(self.m.AUTO, before)

    def test_help_status_and_settings(self):
        self.assertIn('LAB: what-if tests', self.say('lab help'))
        out = self.say('lab status')
        self.assertIn('LAB STATUS', out)
        self.assertIn('price records: 0 trades', out)
        self.assertIn('never places or changes an order', out)
        self.assertIn('Follow-through is ON', self.say('lab follow'))
        self.assertIn('Follow-through is OFF', self.say('lab follow off'))
        self.assertEqual(self.m._n99_get('follow'), 'off')
        self.assertIn('Follow-through is ON', self.say('lab follow on'))
        self.assertIn('weekly report is OFF', self.say('lab weekly off'))
        self.assertIn('monthly report is OFF', self.say('lab monthly off'))
        self.assertIn('weekly report is ON', self.say('lab weekly on'))

    def test_an_unknown_lab_word_gets_the_help_not_silence(self):
        out = self.say('/lab banana')
        self.assertIn('I did not understand', out)
        self.assertIn('LAB: what-if tests', out)

    def test_the_why_command_variants(self):
        m = self.m
        self.start(m, '_n96_now', lambda: ist_ts(0, 16, 0))
        m._n99_q('INSERT INTO lab99_why(day,code,n,first_t,last_t,detail) VALUES(?,?,?,?,?,?)', ('2026-10-02', 'ai_none', 9, 1, 2, 'x'), write=True)
        self.assertIn('no checks recorded yet', self.say('lab why'))
        self.assertIn('9 × the AI looked and chose no trade', self.say('lab why yesterday'))
        week = self.say('lab why week')
        self.assertIn('this week', week)
        self.assertIn('no checks recorded yet', week)                                        # the 2nd of October is in the previous week

    def test_asking_if_it_is_ready_for_live_does_not_switch_the_record_to_the_live_one(self):
        self.put_trade(mode='live', bids=(105, 120, 135, 152), reason='target', record=False)
        out = self.say('lab ready for live')
        self.assertIn('LIVE-READINESS CHECKLIST (virtual money record)', out)
        out = self.say('lab ready live')
        self.assertIn('LIVE-READINESS CHECKLIST (real money record)', out)

    def test_live_and_virtual_are_kept_apart(self):
        self.put_trade(mode='live', bids=(105, 120, 135, 152), reason='target', record=False)
        out = self.say('lab live')
        self.assertIn('live agent', out)
        self.assertIn('REAL', out)
        self.assertIn('1 closed trade', out)
        out = self.say('lab')
        self.assertIn('No closed trades yet', out)


# ===================================================================================================================
# 13. WIRING, STRUCTURE, SAFETY
# ===================================================================================================================
class TestWiringAndStructure(LabCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass() if hasattr(super(), 'setUpClass') else None
        cls.src = v99_source()
        cls.tree = ast.parse(cls.src)

    def test_capabilities_status_abilities_and_commands(self):
        m = self.m
        self.assertIn('Lab 99:', m._n82_capabilities())
        self.assertIn('never changes what the agent does', m._n82_capabilities())
        self.assertIn('LAB 99: views 0 · price samples 0', m._n83_status_text(OWNER_ID))
        rows = {r[1]: r for r in m._n88_abilities(OWNER_ID)}
        self.assertIn('Strategy lab', rows)
        self.assertEqual(rows['Strategy lab'][2], 'ready')
        self.assertIn('lab', [c[0] for c in m._N40_COMMANDS])

    def test_the_abilities_report_still_ends_properly_with_the_new_row(self):
        r = self.m._n88_eye_abilities(OWNER_ID, live=True)['text']
        self.assertLessEqual(len(r), 3900)
        self.assertIn('Strategy lab', r)
        self.assertTrue(r.rstrip().endswith('still need your approval.'))

    def test_regression_rows_pass_and_join_the_suite(self):
        rows = self.m._n99_regression_rows()
        self.assertEqual(len(rows), 8)
        self.assertEqual([r['name'] for r in rows if not r['ok']], [])
        self.assertTrue(all(r['name'].startswith('v99-') for r in rows))
        self.assertIsNot(self.m.prime_regression_suite, self.m._N99_REG_PREV)

    def test_every_replaced_function_keeps_the_old_one(self):
        for fn, prev in (('handle', '_N99_HANDLE_PREV'), ('auto_trade_tick', '_N99_TICK_PREV'), ('trading_day_report', '_N99_EOD_PREV'), ('_n83_status_text', '_N99_STATUS_PREV'), ('_n82_capabilities', '_N99_CAPS_PREV'),
                         ('_n88_abilities', '_N99_ABIL_PREV'), ('prime_regression_suite', '_N99_REG_PREV'), ('main', '_N99_MAIN_PREV'), ('_n75_quote', '_N99_QUOTE_PREV'), ('live_ltp', '_N99_LTP_PREV'),
                         ('ai_decide', '_N99_AI_PREV'), ('godmode_analyze', '_N99_GM_PREV'), ('_n81_entry_quote', '_N99_ENTRY_PREV'), ('_option_chain_failure_notice', '_N99_CHAIN_PREV'), ('_n81_status', '_N99_N81_PREV')):
            self.assertIn('%s = %s\n' % (prev, fn), self.src, fn)

    def test_all_layer_names_use_the_v99_prefix(self):
        defined = {n.name for n in self.tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        allowed = ('handle', '_n82_capabilities', '_n83_status_text', '_n88_abilities', 'prime_regression_suite', 'main', 'auto_trade_tick', 'trading_day_report', '_n75_quote', 'live_ltp', 'ai_decide', 'godmode_analyze',
                   '_n81_entry_quote', '_option_chain_failure_notice', '_n81_status')
        odd = [d for d in defined if not (d.startswith('_n99_') or d.startswith('_N99')) and d not in allowed]
        self.assertEqual(odd, [])

    def test_the_wrapped_agent_functions_only_pass_through(self):
        """Each wrapped function of the agent (quote, price, AI decision, analysis, entry check, chain notice) calls the old one with the same arguments and returns its answer or raises its error."""
        for fn in ('_n75_quote', 'live_ltp', 'ai_decide', 'godmode_analyze', '_n81_entry_quote', '_option_chain_failure_notice'):
            node = [n for n in self.tree.body if isinstance(n, ast.FunctionDef) and n.name == fn][0]
            body = ast.unparse(node)
            self.assertRegex(body, r'_N99_[A-Z]+_PREV\(', fn)
            self.assertNotRegex(body, r'return\s+None\b', fn)
            self.assertNotIn('AUTO[', body.replace("AUTO.get", ''), fn)

    def test_the_layer_never_places_changes_or_simulates_an_order_and_never_writes_the_agents_state(self):
        src = self.src
        for word in ('fyers_place', '_order_send', 'request_order', 'save_secret', 'save_data', 'requests.', 'ask_ai', 'AUTOLOG.append', 'AUTOLOG.remove', 'del AUTOLOG', 'AUTOLOG[', 'auto_report', 'subprocess', 'os.system',
                     'eval(', 'exec(', 'ntfy_send', 'wa_send', 'WEBCFG', 'save_json', 'set_cap', 'kv_set'):
            self.assertNotIn(word, src, word)
        self.assertIsNone(re.search(r'\bAUTO\s*\[[^\]]+\]\s*=[^=]', src))
        self.assertIsNone(re.search(r'\bAUTO\s*\.\s*(?:update|pop|clear|setdefault|__setitem__)', src))
        self.assertIsNone(re.search(r'\bBROKER\s*\[[^\]]+\]\s*=[^=]', src))
        self.assertIsNone(re.search(r'\bOWNER\s*\[[^\]]+\]\s*=[^=]', src))
        reads = set(re.findall(r"\bAUTO(?:\.get|\[)\(?['\"](\w+)", src))
        self.assertLessEqual(reads, {'pos', 'mode', 'brain', 'trades', 'maxtrades', 'dayloss', 'pnl', 'watch'})

    def test_the_only_calls_out_of_the_layer_are_price_reads_and_messages_to_the_owner(self):
        names = {c.func.id for c in ast.walk(self.tree) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
        outside = {n for n in names if n.startswith(('fyers_', '_n75_', 'send_', 'live_', 'ask_', 'requests'))}
        self.assertEqual(outside, {'fyers_ltp', 'fyers_today', '_n75_quote', 'send_text'})
        for need in ('_n96_send_csv', '_n96_send_chart'):
            self.assertIn(need, self.src)

    def test_the_sql_writes_only_the_labs_own_tables_and_reads_the_ledger(self):
        writes = set(re.findall(r'(?:INSERT(?: OR \w+)? INTO|UPDATE|DELETE FROM|CREATE TABLE IF NOT EXISTS)\s+([a-z_0-9]+)', self.src))
        self.assertEqual(writes, {'lab99_path', 'lab99_pos', 'lab99_why', 'lab99_event', 'lab99_setting'})
        reads = set(re.findall(r'FROM\s+([a-z_0-9]+)', self.src))
        self.assertEqual(reads - writes, {'ledger96_trade'})
        self.assertNotIn('ledger96_trade SET', self.src)

    def test_the_protection_list_for_live_self_edit_names_the_new_prefix(self):
        self.assertIn("'_n98_','_n99_',", bot_source())

    def test_version_and_docstring(self):
        self.assertGreaterEqual(float(self.m.VERSION), 99.0)
        self.assertIn('v99.0 - LAB', bot_source()[:20000])

    def test_no_secret_shaped_text_in_the_layer(self):
        for rx in (r'AIza[0-9A-Za-z_-]{20,}', r'sk-[A-Za-z0-9]{20,}', r'gh[pousr]_[A-Za-z0-9]{20,}', r'\b\d{8,10}:[A-Za-z0-9_-]{30,}\b', r'-----BEGIN [A-Z ]*PRIVATE KEY'):
            self.assertIsNone(re.search(rx, self.src), rx)

    def test_stats_are_all_counted_from_zero(self):
        self.assertTrue(all(v == 0 for v in self.m._N99_STATS.values()))

    def test_pruning_drops_old_paths_and_reasons_but_not_recent_ones(self):
        m = self.m
        self.put_trade(days_ago=0)
        old_key = self.put_trade(days_ago=2)
        m._n99_q('UPDATE lab99_pos SET created=? WHERE key=?', (time.time() - 500 * 86400, old_key), write=True)
        m._n99_q('INSERT INTO lab99_why(day,code,n,first_t,last_t,detail) VALUES(?,?,?,?,?,?)', ('2025-01-01', 'ai_none', 1, 1, 1, 'x'), write=True)
        m._n99_q('INSERT INTO lab99_why(day,code,n,first_t,last_t,detail) VALUES(?,?,?,?,?,?)', (D0.isoformat(), 'ai_none', 1, 1, 1, 'x'), write=True)
        m._n99_set('pruned', '')
        m._n99_prune(time.time())
        self.assertEqual(m._n99_q('SELECT COUNT(*) FROM lab99_pos')[0][0], 1)
        self.assertEqual(m._n99_q('SELECT COUNT(DISTINCT key) FROM lab99_path')[0][0], 1)
        self.assertEqual([r[0] for r in m._n99_q('SELECT day FROM lab99_why')], [D0.isoformat()])
        m._n99_prune(time.time())                                                          # once a day: the second call does nothing
        self.assertEqual(m._n99_q('SELECT COUNT(*) FROM lab99_pos')[0][0], 1)

    def test_a_restart_closes_a_follow_that_was_cut_short(self):
        m = self.m
        key = self.put_trade()
        m._n99_q("UPDATE lab99_pos SET status='following' WHERE key=?", (key,), write=True)
        self.start(m, '_N99_MAIN_PREV', lambda *a, **k: 'ran')
        m.main()
        self.assertEqual(m._n99_q('SELECT status FROM lab99_pos WHERE key=?', (key,)), [('done',)])

    def test_the_prune_runs_with_the_look_at_the_agent_not_only_at_boot(self):
        m = self.m
        key = self.put_trade()
        m._n99_q('UPDATE lab99_pos SET created=? WHERE key=?', (time.time() - 500 * 86400, key), write=True)
        m._n99_set('pruned', '')
        m._n99_observe()
        self.assertEqual(m._n99_q('SELECT COUNT(*) FROM lab99_pos')[0][0], 0)

    def test_main_prepares_the_database(self):
        calls = []
        self.start(self.m, '_N99_MAIN_PREV', lambda *a, **k: calls.append('main') or 'ran')
        self.assertEqual(self.m.main(), 'ran')
        self.assertEqual(calls, ['main'])


if __name__ == '__main__':
    unittest.main()
