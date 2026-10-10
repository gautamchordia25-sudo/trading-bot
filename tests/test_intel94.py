"""Nemo v94 Scout intel: what NSE publishes (results dates, F&O ban list, corporate actions, FII flows), the holiday cross-check and the volatility forecast.

Offline. The NSE helper program and the libraries are stand-ins that return exactly the shapes the installed libraries return (read from their own source); a second group runs the REAL helper program with a stand-in
`nselib` package built from those shapes (and the real exchange_calendars and arch libraries), and skips itself when no Python with pandas is available.

    NEMO_FILE=/path/to/nemotron_bot.py python -m unittest tests.test_intel94 -v
"""
import copy
import datetime as dt
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from tests import test_cortex83 as base
from tests import test_scout93 as T
from tests.test_scout93 import ScanCase, make_chain, news_sig, breakout_stock
from tests.test_clear94 import ClearCase, setUpModule as _setup94
from tests.test_forge91 import OWNER_ID


def setUpModule():
    _setup94()


# ---- what NSE sends (shapes from the nselib source and NSE's own site; dates are relative to the fixed "today" of these tests: Monday 5 Oct 2026)
NSE_EVENTS = [
    {'symbol': 'RELIANCE', 'company': 'Reliance Industries Limited', 'purpose': 'Financial Results', 'bm_desc': 'To consider and approve the unaudited financial results for the quarter ended September 30, 2026', 'date': '06-Oct-2026'},
    {'symbol': 'TCS', 'company': 'Tata Consultancy Services Limited', 'purpose': 'Financial Results/Dividend', 'bm_desc': 'Quarterly results and interim dividend', 'date': '08-Oct-2026'},
    {'symbol': 'INFY', 'company': 'Infosys Limited', 'purpose': 'Financial Results', 'bm_desc': 'Results for the quarter', 'date': '12-Oct-2026'},
    {'symbol': 'HDFCBANK', 'company': 'HDFC Bank Limited', 'purpose': 'Analysts/Institutional Investor Meet/Con. Call Updates', 'bm_desc': 'Schedule of analyst meet', 'date': '07-Oct-2026'},
    {'symbol': 'ITC', 'company': 'ITC Limited', 'purpose': 'Financial Results', 'bm_desc': 'Results', 'date': '02-Oct-2026'},
    {'symbol': 'SBIN', 'company': 'State Bank of India', 'purpose': 'Financial Results', 'bm_desc': '', 'date': '2026-11-05'},
]
NSE_ACTIONS = [
    {'symbol': 'SBIN', 'comp': 'State Bank of India', 'series': 'EQ', 'subject': 'Face Value Split (Sub-Division) - From Rs 2/- Per Share To Re 1/- Per Share', 'faceVal': '2', 'exDate': '08-Oct-2026', 'recDate': '08-Oct-2026'},
    {'symbol': 'ITC', 'comp': 'ITC Limited', 'series': 'EQ', 'subject': 'Dividend - Rs 7.5 Per Share', 'faceVal': '1', 'exDate': '09-Oct-2026', 'recDate': '09-Oct-2026'},
    {'symbol': 'LT', 'comp': 'Larsen & Toubro', 'series': 'EQ', 'subject': 'Bonus 1:1', 'faceVal': '2', 'exDate': '30-Oct-2026', 'recDate': '30-Oct-2026'},
    {'symbol': 'WIPRO', 'comp': 'Wipro', 'series': 'EQ', 'subject': 'Scheme Of Arrangement', 'faceVal': '2', 'exDate': '07-Oct-2026', 'recDate': '07-Oct-2026'},
    {'symbol': 'OLD', 'comp': 'Old Co', 'series': 'EQ', 'subject': 'Bonus 1:1', 'faceVal': '2', 'exDate': '01-Oct-2026', 'recDate': '01-Oct-2026'},
]
NSE_BAN = ['IDEA', 'RBLBANK']
FII_STATS = {'date': '2026-10-02', 'rows': [
    {'fii_derivatives': 'INDEX FUTURES', 'buy_contracts': '50000', 'buy_value_in_Cr': '4521.3', 'sell_contracts': '65000', 'sell_value_in_Cr': '6120.8', 'open_contracts': '185000', 'open_contracts_value_in_Cr': '41000'},
    {'fii_derivatives': 'INDEX OPTIONS', 'buy_contracts': '9', 'buy_value_in_Cr': '9', 'sell_contracts': '9', 'sell_value_in_Cr': '9', 'open_contracts': '9', 'open_contracts_value_in_Cr': '9'}]}
PART_OI = {'date': '2026-10-02', 'rows': [
    {'Client Type\t': 'Client', 'Future Index Long\t': '150000', 'Future Index Short\t': '90000', 'Option Index Call Long\t': '1'},
    {'Client Type\t': 'DII', 'Future Index Long\t': '30000', 'Future Index Short\t': '60000'},
    {'Client Type\t': 'FII', 'Future Index Long\t': '60000', 'Future Index Short\t': '120000'},
    {'Client Type\t': 'PRO', 'Future Index Long\t': '90000', 'Future Index Short\t': '60000'},
    {'Client Type\t': 'TOTAL', 'Future Index Long\t': '330000', 'Future Index Short\t': '330000'}]}


def ex(days):
    return (dt.date(2026, 10, 5) + dt.timedelta(days=days)).strftime('%d-%b-%Y')


class IntelCase(ScanCase):
    """Scout with the NSE helper replaced by a script: `self.nse` maps a job kind to what the helper prints (a dict) or an exception to raise."""

    def setUp(self):
        super().setUp()
        m = self.m
        self.today = dt.date(2026, 10, 5)
        self.start(m, '_n94_today', lambda now=None: self.today)
        real_session = next(p.temp_original for p in self.fp if getattr(p, 'attribute', '') == '_n81_session')
        self.real_session = real_session
        # trading-session counting needs the REAL calendar (weekends, Dussehra); everything else in a scan keeps Scout's stubbed clock
        self.start(m, '_n81_session', lambda now=None, exchange='NSE': real_session(now, exchange) if isinstance(now, dt.datetime) else dict(self.session))
        m._N94_INTEL.clear()
        for k in m._N94_STATS:
            m._N94_STATS[k] = 0
        m._n94_put('intel', 'on')
        self.have = {'nselib', 'exchange_calendars', 'arch'}
        real_have = m._n92_have
        self.start(m, '_n92_have', lambda mod: (mod in self.have) if mod in ('nselib', 'exchange_calendars', 'arch') else real_have(mod))
        self.child_calls = []
        self.nse = {'events': {'ok': True, 'rows': copy.deepcopy(NSE_EVENTS)}, 'actions': {'ok': True, 'rows': copy.deepcopy(NSE_ACTIONS)}, 'ban': {'ok': True, 'date': '2026-10-05', 'symbols': list(NSE_BAN)},
                    'flows': {'ok': True, 'fii_stats': copy.deepcopy(FII_STATS), 'part_oi': copy.deepcopy(PART_OI)},
                    'cal': {'ok': True, 'holidays': ['2026-10-20', '2026-11-10', '2026-11-24', '2026-12-25'], 'checked_to': '2026-12-31', 'calendar_ends': '2026-12-31'},
                    'vol': {'ok': True, 'forecast_vol_pct': 12.0, 'horizon': 6, 'n': 480, 'persistence': 0.97, 'recent_vol_pct': 11.2}}

        def child(code, args=(), need_mb=200, timeout=120, job=None):
            kind = str(args[0])
            self.child_calls.append((kind, json.loads(args[1]) if len(args) > 1 else {}, need_mb, timeout))
            r = self.nse[kind]
            if isinstance(r, BaseException):
                raise r
            return copy.deepcopy(r)
        self.start(m, '_n92_child', child)
        self.guest = lambda text, **k: dict({'chat': {'id': 5552, 'type': 'private'}, 'from': {'id': 5552, 'first_name': 'Asha'}, 'message_id': 3, 'text': text}, **k)
        self.charts = []
        self.start(m, '_n90_send_image', lambda cid, raw, name, caption='', kb=None, force_file=False: self.charts.append((name, caption, len(raw))) or True)

    def kinds(self):
        return [c[0] for c in self.child_calls]


# ===================================================================================================================
# 1. READING WHAT NSE SENDS
# ===================================================================================================================
class TestParsing(IntelCase):
    def test_dates_in_every_format_nse_uses(self):
        f = self.m._n94_parse_date
        d = dt.date(2025, 10, 17)
        for s in ('17-Oct-2025', '17-10-2025', '2025-10-17', '17 Oct 2025', '17-Oct-25', '17/10/2025', '17-October-2025', ' 17-Oct-2025 ', '17-Oct-2025 00:00:00'):
            self.assertEqual(f(s), d, s)
        for s in ('', None, 'soon', '32-13-2025', '-'):
            self.assertIsNone(f(s), s)

    def test_trading_sessions_skip_weekends_and_known_holidays(self):
        f = self.m._n94_sessions_between
        D = dt.date
        self.assertEqual(f(D(2026, 10, 5), D(2026, 10, 5)), 0)
        self.assertEqual(f(D(2026, 10, 5), D(2026, 10, 6)), 1)
        self.assertEqual(f(D(2026, 10, 9), D(2026, 10, 12)), 1, 'Friday to Monday is one session')
        self.assertEqual(f(D(2026, 10, 19), D(2026, 10, 21)), 1, 'Dussehra, 20 Oct, is a holiday')
        self.assertEqual(f(D(2026, 10, 5), D(2026, 10, 12)), 5)

    def test_results_dates_per_company_with_sessions(self):
        m = self.m._n94_events_map(NSE_EVENTS, self.today)
        self.assertEqual(m['RELIANCE']['date'], dt.date(2026, 10, 6))
        self.assertEqual(m['RELIANCE']['sessions'], 1)
        self.assertEqual(m['RELIANCE']['purpose'], 'Financial Results')
        self.assertEqual(m['TCS']['sessions'], 3)
        self.assertEqual(m['INFY']['sessions'], 5)
        self.assertNotIn('ITC', m, 'a date in the past is not an upcoming result')
        self.assertIsNone(m['HDFCBANK']['date'])
        self.assertEqual(m['HDFCBANK']['other'], [(dt.date(2026, 10, 7), 'Analysts/Institutional Investor Meet/Con. Call Updates')])
        self.assertEqual(m['SBIN']['date'], dt.date(2026, 11, 5), 'ISO dates are understood')

    def test_column_names_are_matched_without_regard_to_case_or_spaces(self):
        rows = [{'Symbol ': 'ABC', 'Purpose': 'Financial Results', 'Date': ex(2)}, {'SYMBOL': 'DEF', 'bm_desc': 'quarterly results', 'bmDate': ex(3)}]
        m = self.m._n94_events_map(rows, self.today)
        self.assertEqual(set(m), {'ABC', 'DEF'})
        self.assertEqual(m['DEF']['date'], dt.date(2026, 10, 8))

    def test_rows_without_a_symbol_or_a_date_are_ignored(self):
        self.assertEqual(self.m._n94_events_map([{'purpose': 'Financial Results', 'date': ex(1)}, {'symbol': 'X', 'purpose': 'Financial Results'}, {}, None], self.today), {})

    def test_thousands_of_events_do_not_mean_thousands_of_calendar_walks(self):
        calls = []
        real = self.m._n94_sessions_between
        self.start(self.m, '_n94_sessions_between', lambda a, b: calls.append(b) or real(a, b))
        rows = [{'symbol': 'S%04d' % i, 'purpose': 'Financial Results', 'date': ex(1 + i % 20)} for i in range(5000)]
        m = self.m._n94_events_map(rows, self.today)
        self.assertEqual(len(m), 5000)
        self.assertLessEqual(len(calls), 20)

    def test_corporate_actions_are_sorted_into_kinds(self):
        a = self.m._n94_actions_map(NSE_ACTIONS, self.today)
        self.assertEqual(a['SBIN'][0][1], 'split')
        self.assertEqual(a['ITC'][0][1], 'dividend')
        self.assertEqual(a['LT'][0][1], 'bonus')
        self.assertEqual(a['WIPRO'][0][1], 'merger')
        self.assertNotIn('OLD', a)
        self.assertLessEqual(len(a['SBIN'][0][2]), 70)

    def test_the_flow_summary_reads_fii_futures_and_participant_positions(self):
        fl = self.m._n94_flow_summary({'fii_stats': FII_STATS, 'part_oi': PART_OI})
        self.assertEqual(fl['date'], '2026-10-02')
        self.assertAlmostEqual(fl['fii_long_share'], 60000 / 180000.0)
        self.assertTrue(any('bought ₹4,521.3 cr, sold ₹6,120.8 cr → net selling ₹1,599.5 cr' in x for x in fl['lines']), fl['lines'])
        self.assertTrue(any('FII are 33% long in index futures' in x and 'leaning bearish' in x for x in fl['lines']))
        self.assertTrue(any(x.startswith('Retail clients: 62% long') for x in fl['lines']))
        self.assertTrue(any(x.startswith('DII: 33% long') for x in fl['lines']))
        want = (max(-1, -1599.5 / 3000.0) + max(-1, (1 / 3.0 - 0.5) / 0.25)) / 2.0
        self.assertAlmostEqual(fl['signal'], want, places=4)
        self.assertLess(fl['signal'], -0.5)

    def test_buying_and_a_long_position_read_bullish(self):
        stats = copy.deepcopy(FII_STATS)
        stats['rows'][0].update(buy_value_in_Cr='9000', sell_value_in_Cr='6000')
        oi = copy.deepcopy(PART_OI)
        oi['rows'][2].update({'Future Index Long\t': '150000', 'Future Index Short\t': '50000'})
        fl = self.m._n94_flow_summary({'fii_stats': stats, 'part_oi': oi})
        self.assertGreater(fl['signal'], 0.9)

    def test_only_one_of_the_two_is_enough_and_none_is_nothing(self):
        self.assertIsNotNone(self.m._n94_flow_summary({'fii_stats': FII_STATS, 'part_oi': None})['signal'])
        self.assertIsNotNone(self.m._n94_flow_summary({'fii_stats': None, 'part_oi': PART_OI})['signal'])
        self.assertIsNone(self.m._n94_flow_summary({'fii_stats': None, 'part_oi': None}))
        self.assertIsNone(self.m._n94_flow_summary(None))
        self.assertIsNone(self.m._n94_flow_summary({'fii_stats': {'date': 'x', 'rows': [{'junk': 1}]}, 'part_oi': {'date': 'x', 'rows': []}}))

    def test_numbers_with_commas_or_blanks(self):
        self.assertEqual(self.m._n94_num('1,234.5'), 1234.5)
        self.assertIsNone(self.m._n94_num(''))
        self.assertIsNone(self.m._n94_num(None))
        self.assertIsNone(self.m._n94_num('n/a'))


# ===================================================================================================================
# 2. THE HELPER JOB: cached, fail-soft, memory-safe
# ===================================================================================================================
class TestJobs(IntelCase):
    def test_a_job_runs_once_and_is_then_cached(self):
        a, err = self.m._n94_get_ban()
        self.assertEqual((a, err), ({'IDEA', 'RBLBANK'}, None))
        self.m._n94_get_ban()
        self.assertEqual(self.kinds(), ['ban'])
        self.assertEqual(self.m._N94_STATS['intel_cached'], 1)

    def test_the_helper_is_asked_for_a_sensible_amount_of_memory_and_time(self):
        self.m._n94_get_events()
        self.m._n94_get_flows()
        self.assertEqual([(c[0], c[2]) for c in self.child_calls], [('events', 250), ('flows', 300)])
        self.assertTrue(all(c[3] <= 70 for c in self.child_calls))

    def test_the_helper_is_given_the_date_not_asked_for_it(self):
        self.m._n94_get_events()
        self.assertEqual(self.child_calls[0][1], {'today': '2026-10-05', 'days': 21})

    def test_a_missing_library_says_what_to_install_and_starts_nothing(self):
        self.have.discard('nselib')
        v, err = self.m._n94_get_events()
        self.assertIsNone(v)
        self.assertIn('install nselib into yourself', err)
        self.assertEqual(self.child_calls, [])

    def test_a_failure_is_cached_for_half_an_hour_so_a_blocked_site_cannot_slow_every_scan(self):
        self.nse['ban'] = self.m._N92Err('failed', 'The helper stopped with an error (ConnectionError).')
        v, err = self.m._n94_get_ban()
        self.assertIsNone(v)
        self.assertIn('ConnectionError', err)
        self.m._n94_get_ban()
        self.assertEqual(self.kinds(), ['ban'])
        key = next(k for k in self.m._N94_INTEL if k[0] == 'ban')
        t0, data, e = self.m._N94_INTEL[key]
        self.m._N94_INTEL[key] = (t0 - 1700, data, e)
        self.m._n94_get_ban()
        self.assertEqual(self.kinds(), ['ban'], 'still cached at 28 minutes')
        self.m._N94_INTEL[key] = (t0 - 1900, data, e)
        self.m._n94_get_ban()
        self.assertEqual(self.kinds(), ['ban', 'ban'], 'asked again after 30 minutes')

    def test_busy_or_low_memory_is_retried_in_a_minute_not_in_half_an_hour(self):
        for code in ('busy', 'low_memory'):
            self.m._N94_INTEL.clear()
            self.child_calls.clear()
            self.nse['ban'] = self.m._N92Err(code, 'Another heavy job is running; ask again in a minute.')
            self.m._n94_get_ban()
            key = next(k for k in self.m._N94_INTEL if k[0] == 'ban')
            t0, data, e = self.m._N94_INTEL[key]
            self.m._N94_INTEL[key] = (t0 - 30, data, e)
            self.m._n94_get_ban()
            self.assertEqual(len(self.child_calls), 1, code)
            self.m._N94_INTEL[key] = (t0 - 100, data, e)
            self.m._n94_get_ban()
            self.assertEqual(len(self.child_calls), 2, code)

    def test_a_source_that_answers_with_an_error_is_a_failure_with_its_words(self):
        self.nse['events'] = {'ok': False, 'error': 'NSEdataNotFound: Resource not available'}
        v, err = self.m._n94_get_events()
        self.assertIsNone(v)
        self.assertIn('Resource not available', err)

    def test_an_unexpected_crash_is_a_plain_failure(self):
        self.nse['flows'] = RuntimeError('boom')
        v, err = self.m._n94_get_flows()
        self.assertIsNone(v)
        self.assertEqual(err, 'The helper failed (RuntimeError).')
        self.assertEqual(self.m._N94_STATS['intel_failed'], 1)

    def test_force_reads_again(self):
        self.m._n94_get_ban()
        self.m._n94_get_ban(force=True)
        self.assertEqual(self.kinds(), ['ban', 'ban'])

    def test_a_new_day_is_a_new_question(self):
        self.m._n94_get_ban()
        self.today = dt.date(2026, 10, 6)
        self.m._n94_get_ban()
        self.assertEqual(self.kinds(), ['ban', 'ban'])

    def test_the_prefetch_loads_the_four_sources_once(self):
        res = self.m._n94_prefetch(None)
        self.assertEqual(res, {'events': None, 'ban': None, 'actions': None, 'flows': None})
        self.assertEqual(self.kinds(), ['events', 'ban', 'actions', 'flows'])
        self.m._n94_prefetch(None)
        self.assertEqual(len(self.child_calls), 4)

    def test_the_prefetch_does_nothing_when_off_or_not_installed(self):
        self.m._n94_put('intel', 'off')
        self.assertEqual(self.m._n94_prefetch(None), {})
        self.m._n94_put('intel', 'on')
        self.have.discard('nselib')
        self.assertEqual(self.m._n94_prefetch(None), {})
        self.assertEqual(self.child_calls, [])

    def test_the_prefetch_stops_when_its_time_budget_is_spent(self):
        res = self.m._n94_prefetch(None, budget=-1.0)
        self.assertEqual(set(res.values()), {'time budget spent'})
        self.assertEqual(self.child_calls, [])

    def test_the_prefetch_can_be_limited_to_what_a_scan_needs(self):
        self.m._n94_prefetch(None, 110.0, ('flows',))
        self.assertEqual(self.kinds(), ['flows'])

    def test_one_failure_does_not_stop_the_others(self):
        self.nse['events'] = self.m._N92Err('failed', 'x')
        res = self.m._n94_prefetch(None)
        self.assertIsNotNone(res['events'])
        self.assertIsNone(res['ban'])
        self.assertEqual(self.kinds(), ['events', 'ban', 'actions', 'flows'])


# ===================================================================================================================
# 3. IN SCOUT'S STOCK IDEAS
# ===================================================================================================================
class TestStockIdeas(IntelCase):
    def eval(self, sym='RELIANCE'):
        self.world()
        self.m._n94_prefetch(None)
        mctx = self.m._n93_market_ctx()
        return self.m._n93_eval_stock(sym, news_sig(), mctx, {}, self.m._n93_cfg(), time.time())

    def baseline(self):
        """The same idea with the intel switched off: what Scout v93 gave."""
        self.m._n94_put('intel', 'off')
        self.world()
        r = self.m._n93_eval_stock('RELIANCE', news_sig(), self.m._n93_market_ctx(), {}, self.m._n93_cfg(), time.time())
        self.m._n94_put('intel', 'on')
        return r

    def test_results_due_the_next_session_means_no_new_idea_and_the_reason_is_given(self):
        i, why = self.eval()
        self.assertIsNone(i)
        self.assertIn('RELIANCE: results on 06 Oct (the next session)', why)
        self.assertIn('a stop cannot protect against a results gap', why)

    def test_results_today_are_worded_as_today(self):
        self.nse['events']['rows'][0]['date'] = ex(0)
        i, why = self.eval()
        self.assertIn('results on 05 Oct (today)', why)

    def test_results_in_three_sessions_keep_the_idea_with_the_event_penalty_and_the_date(self):
        self.nse['events']['rows'][0]['date'] = ex(3)
        i, why = self.eval()
        self.assertIsNotNone(i, why)
        base_idea, _w = self.baseline()
        self.assertLessEqual(i['score'], base_idea['score'] - 8)
        self.assertIn('results_due', i['flags'])
        self.assertTrue(any('results look due soon' in b for b in i['bad']))
        self.assertTrue(any(x.startswith('Results: 08 Oct (Financial Results, in 3 trading sessions)') for x in i['intel']), i['intel'])

    def test_results_far_away_are_a_line_not_a_penalty(self):
        self.nse['events']['rows'][0]['date'] = ex(12)
        i, why = self.eval()
        self.assertIsNotNone(i, why)
        base_idea, _w = self.baseline()
        self.assertEqual(i['score'], base_idea['score'])
        self.assertNotIn('results_due', i['flags'])

    def test_no_results_on_the_calendar_is_said_as_such(self):
        self.nse['events']['rows'] = [r for r in self.nse['events']['rows'] if r['symbol'] != 'RELIANCE']
        i, why = self.eval()
        self.assertIsNotNone(i, why)
        self.assertIn('Results: none on NSE’s calendar in the next 21 days', i['intel'][0])

    def test_a_stock_in_the_ban_period_loses_six_points_and_says_why(self):
        self.nse['events']['rows'] = []
        self.nse['ban']['symbols'] = ['RELIANCE']
        i, why = self.eval()
        self.assertIsNotNone(i, why)
        base_idea, _w = self.baseline()
        self.assertEqual(i['score'], base_idea['score'] - 6)
        self.assertEqual(i['band'], self.m._n93_band(i['score']))
        self.assertTrue(any('F&O ban: YES' in x for x in i['intel']))
        self.assertTrue(any('in the F&O ban period' in b for b in i['bad']))
        self.assertEqual(i['comps']['event'], round(base_idea['comps'].get('event', 0.0) - 6, 1))

    def test_a_split_inside_the_window_loses_four_points(self):
        self.nse['events']['rows'] = []
        self.nse['actions']['rows'].append({'symbol': 'RELIANCE', 'subject': 'Bonus 1:1', 'exDate': ex(4)})
        i, why = self.eval()
        self.assertIsNotNone(i, why)
        base_idea, _w = self.baseline()
        self.assertEqual(i['score'], base_idea['score'] - 4)
        self.assertTrue(any('Corporate action: Bonus 1:1 ex-date 09 Oct' in x for x in i['intel']))

    def test_a_dividend_is_a_line_only(self):
        self.nse['events']['rows'] = []
        self.nse['actions']['rows'].append({'symbol': 'RELIANCE', 'subject': 'Dividend - Rs 10 Per Share', 'exDate': ex(4)})
        i, why = self.eval()
        base_idea, _w = self.baseline()
        self.assertEqual(i['score'], base_idea['score'])
        self.assertTrue(any('Dividend - Rs 10 Per Share ex-date 09 Oct' in x for x in i['intel']))

    def test_the_checked_list_says_what_was_checked(self):
        self.nse['events']['rows'] = []
        i, _w = self.eval()
        self.assertEqual(i['intel_checked'], ['results dates', 'F&O ban', 'corporate actions'])

    def test_when_nse_could_not_be_read_the_idea_is_exactly_what_it_was_before(self):
        for k in ('events', 'actions', 'ban', 'flows'):
            self.nse[k] = self.m._N92Err('failed', 'x')
        self.world()
        self.m._n94_prefetch(None)
        i, why = self.m._n93_eval_stock('RELIANCE', news_sig(), self.m._n93_market_ctx(), {}, self.m._n93_cfg(), time.time())
        base_idea, _w = self.baseline()
        self.assertEqual((i['score'], i['bad'], i['flags']), (base_idea['score'], base_idea['bad'], base_idea['flags']))
        self.assertNotIn('intel', i)

    def test_switched_off_nothing_is_read_or_changed(self):
        self.m._n94_put('intel', 'off')
        self.world()
        i, why = self.m._n93_eval_stock('RELIANCE', news_sig(), self.m._n93_market_ctx(), {}, self.m._n93_cfg(), time.time())
        self.assertEqual(self.child_calls, [])
        self.assertNotIn('intel', i)

    def test_the_eval_never_starts_a_job_by_itself(self):
        self.world()
        self.m._n93_eval_stock('RELIANCE', news_sig(), self.m._n93_market_ctx(), {}, self.m._n93_cfg(), time.time())
        self.assertEqual(self.child_calls, [], 'jobs are started once per scan, never once per stock')


class TestScansAndCards(IntelCase):
    def test_a_scan_reads_nse_once_then_tells_what_it_read_and_why_a_stock_was_skipped(self):
        self.world(stocks=('RELIANCE', 'TCS'))
        out = self.say('trade ideas')
        self.assertIn('reading NSE’s results calendar', out)
        self.assertEqual(self.kinds()[:4], ['events', 'ban', 'actions', 'flows'])
        self.assertIn('📋 Intel: NSE results dates read (RELIANCE 06 Oct, TCS 08 Oct); F&O ban list read; FII flow of 2026-10-02 read.', out)
        self.assertIn('RELIANCE: results on 06 Oct (the next session)', out)
        self.assertEqual([r for r in self.saved() if r[1] == 'RELIANCE'], [])

    def test_a_second_scan_does_not_read_nse_again(self):
        self.world(stocks=('TCS',))
        self.say('trade ideas')
        n = len(self.child_calls)
        self.say('trade ideas')
        self.assertEqual(len(self.child_calls), n)

    def test_an_issued_card_shows_the_intel_and_no_longer_claims_it_did_not_check(self):
        self.world(stocks=('TCS',))
        self.nse['events']['rows'][1]['date'] = ex(11)
        out = self.say('trade ideas')
        card = out[out.index('IDEA SC93-'):]
        self.assertIn('📋 Results:', card)
        self.assertIn('F&O ban: no', card)
        self.assertIn('Corporate action: none in the next 21 days', card)
        line = next(ln for ln in card.splitlines() if ln.startswith('Not checked:'))
        self.assertNotIn('results dates', line)
        self.assertNotIn('corporate actions', line)
        self.assertIn('circuit limits', line)
        self.assertIn('your open positions', line)

    def test_the_card_is_unchanged_when_there_is_no_intel(self):
        self.have.clear()
        self.world(stocks=('TCS',))
        out = self.say('trade ideas')
        card = out[out.index('IDEA SC93-'):]
        self.assertNotIn('📋', card)
        self.assertIn('results dates, circuit limits, corporate actions, your open positions', card)

    def test_the_intel_lines_are_kept_in_the_saved_idea_and_shown_again_later(self):
        self.world(stocks=('TCS',))
        self.nse['events']['rows'][1]['date'] = ex(11)
        self.say('trade ideas')
        iid = next(r[0] for r in self.saved() if r[1] == 'TCS')
        shown = self.say('scout show %s' % iid)
        self.assertIn('F&O ban: no', shown)

    def test_an_nse_that_cannot_be_reached_is_said_in_one_line_and_the_scan_goes_on(self):
        self.world(stocks=('TCS',))
        for k in ('events', 'actions', 'ban', 'flows'):
            self.nse[k] = self.m._N92Err('failed', 'The helper stopped with an error (ConnectionError).')
        out = self.say('trade ideas')
        self.assertIn('NSE could not be read just now', out)
        self.assertIn('were NOT checked', out)
        self.assertIn('IDEA SC93-', out)
        self.assertEqual(self.broker_calls, [])

    def test_an_options_scan_reads_only_the_flows(self):
        self.world()
        self.say('scout nifty')
        self.assertEqual(self.kinds(), ['flows'])

    def test_a_single_stock_look_reads_what_a_stock_needs(self):
        self.world(stocks=('TCS',))
        self.say('scout TCS')
        self.assertEqual(self.kinds(), ['events', 'ban', 'actions'])

    def test_no_library_no_jobs_and_no_extra_lines_at_all(self):
        self.have.clear()
        self.world(stocks=('TCS',))
        out = self.say('trade ideas')
        self.assertEqual(self.child_calls, [])
        self.assertNotIn('Intel', out)

    def test_switched_off_no_jobs_and_no_extra_lines_at_all(self):
        self.m._n94_put('intel', 'off')
        self.world(stocks=('TCS',))
        out = self.say('trade ideas')
        self.assertEqual(self.child_calls, [])
        self.assertNotIn('Intel', out)


# ===================================================================================================================
# 4. IN THE NIFTY OPTION VIEW: flows as one small part, and the volatility forecast
# ===================================================================================================================
class TestIndexOptions(IntelCase):
    def parts(self, down=False):
        return self.m._n93_bias_parts(self.view(down=down))

    def test_the_flow_is_one_more_part_with_a_small_weight_when_it_was_read(self):
        self.m._n94_get_flows()
        parts = self.parts()
        names = [p[0] for p in parts]
        self.assertEqual(names[-1], 'institutional flow')
        fl = parts[-1]
        self.assertEqual(fl[2], 0.15)
        self.assertLess(fl[1], -0.5)
        self.assertIn('FII flow (2026-10-02)', fl[3])

    def test_with_no_flow_the_parts_are_exactly_the_four_of_before(self):
        self.assertEqual([p[0] for p in self.parts()], ['daily trend', 'intraday structure', 'open interest', 'macro news'])

    def test_a_bearish_flow_pulls_a_bullish_view_down_but_cannot_flip_a_strong_one(self):
        v = self.view()
        before = self.m._n93_index_bias(self.m._n93_bias_parts(v))
        self.m._n94_get_flows()
        after = self.m._n93_index_bias(self.m._n93_bias_parts(v))
        self.assertLess(after['bias'], before['bias'])
        self.assertGreater(after['bias'], 0.3)
        self.assertEqual(after['n'], before['n'] + 1)
        self.assertAlmostEqual(after['conf'], 1.0)

    def test_switched_off_the_flow_is_not_used(self):
        self.m._n94_get_flows()
        self.m._n94_put('intel', 'off')
        self.assertEqual(len(self.parts()), 4)

    def test_the_forecast_adds_a_line_that_says_dear_cheap_or_fair(self):
        self.put_market(stock=None)
        for forecast, word in ((9.0, 'DEAR'), (13.0, 'about right'), (20.0, 'CHEAP')):
            self.m._N94_INTEL.clear()
            self.nse['vol']['forecast_vol_pct'] = forecast
            plan = self.m._n93_option_plan(self.view(), self.BIG)
            self.assertTrue(plan['ok'], plan.get('veto'))
            self.assertIn(word, plan['intel'][0], forecast)
            self.assertIn('Volatility forecast: recent behaviour points to about %.1f%% a year' % forecast, plan['intel'][0])
            self.assertIn('priced at 13.0%', plan['intel'][0])

    def test_dear_options_are_noted_against_an_outright_buy_and_cheap_ones_in_favour(self):
        self.put_market(stock=None)
        self.nse['vol']['forecast_vol_pct'] = 9.0
        plan = self.m._n93_option_plan(self.view(ivp=10.0), self.BIG)
        if plan['plan']['structure'] == 'LONG':
            self.assertTrue(any('dear against recent volatility' in b for b in plan['bad']))
        self.m._N94_INTEL.clear()
        self.nse['vol']['forecast_vol_pct'] = 20.0
        plan = self.m._n93_option_plan(self.view(), self.BIG)
        self.assertTrue(any('cheap against recent volatility' in g for g in plan.get('good', [])) or 'good' not in plan)

    def test_the_forecast_never_changes_the_score_or_the_plan(self):
        self.put_market(stock=None)
        self.have.discard('arch')
        base_plan = self.m._n93_option_plan(self.view(), self.BIG)
        self.have.add('arch')
        self.nse['vol']['forecast_vol_pct'] = 9.0
        plan = self.m._n93_option_plan(self.view(), self.BIG)
        self.assertEqual((plan['score'], plan['plan']['structure'], plan['size']), (base_plan['score'], base_plan['plan']['structure'], base_plan['size']))

    def test_no_library_no_forecast_and_no_job(self):
        self.put_market(stock=None)
        self.have.discard('arch')
        plan = self.m._n93_option_plan(self.view(), self.BIG)
        self.assertNotIn('intel', plan)
        self.assertEqual(self.child_calls, [])

    def test_a_failing_forecast_leaves_the_plan_alone(self):
        self.put_market(stock=None)
        self.nse['vol'] = self.m._N92Err('failed', 'x')
        plan = self.m._n93_option_plan(self.view(), self.BIG)
        self.assertTrue(plan['ok'])
        self.assertNotIn('intel', plan)

    def test_too_few_closes_give_no_forecast_and_no_job(self):
        self.put_market(stock=None)
        self.md[('NIFTY', '1d')] = self.md[('NIFTY', '1d')][-100:]
        plan = self.m._n93_option_plan(self.view(), self.BIG)
        self.assertNotIn('intel', plan)
        self.assertEqual(self.child_calls, [])

    def test_the_closes_go_to_the_helper_and_the_horizon_is_the_days_to_expiry(self):
        self.put_market(stock=None)
        self.m._n93_option_plan(self.view(), self.BIG)
        kind, payload, need, secs = self.child_calls[0]
        self.assertEqual(kind, 'vol')
        self.assertEqual(payload['horizon'], 6)
        self.assertGreaterEqual(len(payload['closes']), 130)
        self.assertEqual((need, secs), (250, 45))

    def test_the_option_card_shows_the_forecast_line(self):
        self.nse['flows'] = {'ok': True, 'fii_stats': None, 'part_oi': None}
        self.world()
        out = self.say('scout nifty')
        self.assertIn('Volatility forecast: recent behaviour points to', out)


# ===================================================================================================================
# 5. THE OWNER'S QUESTIONS
# ===================================================================================================================
class TestQuestions(IntelCase):
    def test_results_for_a_company(self):
        for q in ('results RELIANCE', 'when are RELIANCE results', 'when is reliance results?', 'scout results reliance', 'RELIANCE results date', 'results date of RELIANCE'):
            self.m._N94_INTEL.clear()
            out = self.say(q)
            self.assertIn('📅 RELIANCE on NSE’s calendar', out, q)
            self.assertIn('Results: Tuesday 06 Oct 2026 (Financial Results) · in 1 day · 1 trading session away', out, q)
            self.assertIn('Scout skips new ideas on this stock from today', out, q)

    def test_results_further_away_and_other_events(self):
        out = self.say('results TCS')
        self.assertIn('in 3 days · 3 trading sessions away', out)
        self.assertIn('the day before results', out)
        out = self.say('results HDFCBANK')
        self.assertIn('Also: Analysts/Institutional Investor Meet/Con. Call Updates on 07 Oct', out)
        self.assertNotIn('Results:', out)

    def test_nothing_on_the_calendar(self):
        out = self.say('results WIPRO')
        self.assertIn('no results or other event on NSE’s calendar in the next 21 days', out)

    def test_the_ban_list(self):
        for q in ('ban list', 'F&O ban', 'fno ban list', 'stocks in ban', 'f&o ban period', 'scout ban list'):
            self.m._N94_INTEL.clear()
            out = self.say(q)
            self.assertIn('F&O BAN LIST (05 Oct 2026): 2 stocks', out, q)
            self.assertIn('IDEA, RBLBANK', out, q)
            self.assertIn('only closing trades', out, q)

    def test_an_empty_ban_list_does_not_claim_more_than_it_knows(self):
        self.nse['ban']['symbols'] = []
        out = self.say('ban list')
        self.assertIn('no stock is in the ban list, or NSE has not published today’s list yet', out)

    def test_a_missing_excel_reader_is_named_and_not_asked_again_at_every_scan(self):
        self.nse['flows'] = {'ok': True, 'fii_stats': None, 'part_oi': None, 'errors': ['FII figures: No data available for : 02-Oct-2026 :: NSE error : Missing optional dependency \'xlrd\'. Install xlrd >= 2.0.1']}
        out = self.say('fii flow')
        self.assertIn('needs xlrd', out)
        self.assertIn('install xlrd into yourself', out)
        self.say('fii flow')
        self.assertEqual(self.kinds(), ['flows'])
        key = next(k for k in self.m._N94_INTEL if k[0] == 'flows')
        t0, data, e = self.m._N94_INTEL[key]
        self.assertIsNone(data)
        self.m._N94_INTEL[key] = (t0 - 1900, data, e)
        self.say('fii flow')
        self.assertEqual(self.kinds(), ['flows', 'flows'], 'asked again after half an hour')

    def test_no_figures_for_other_reasons_gives_the_reason_when_there_is_one(self):
        self.nse['flows'] = {'ok': True, 'fii_stats': None, 'part_oi': None, 'errors': ['participant positions: No data available for : 02-10-2026']}
        out = self.say('fii flow')
        self.assertIn('NSE had no FII/DII figures for the last few trading days (participant positions: No data available', out)
        self.nse['flows'] = {'ok': True, 'fii_stats': None, 'part_oi': None, 'errors': []}
        self.m._N94_INTEL.clear()
        self.assertIn('NSE had no FII/DII figures for the last few trading days.', self.say('fii flow'))

    def test_the_flow_report(self):
        for q in ('fii flow', 'fii dii', 'FII data', 'institutional flow', 'scout fii'):
            self.m._N94_INTEL.clear()
            out = self.say(q)
            self.assertIn('FOREIGN AND DOMESTIC FLOW (NSE, as of 2026-10-02)', out, q)
            self.assertIn('FII are 33% long in index futures', out, q)
            self.assertIn('Reading: mildly bearish', out, q)
            self.assertIn('one day old', out, q)

    def test_the_volatility_forecast_for_an_index(self):
        self.put_market(stock=None)
        self.put_chain()
        for q in ('volatility forecast nifty', 'vol forecast', 'forecast volatility for nifty', 'garch nifty'):
            self.m._N94_INTEL.clear()
            out = self.say(q)
            self.assertIn('VOLATILITY FORECAST: NIFTY', out, q)
            self.assertIn('about 12.0% a year over the next 5 trading days', out, q)
            self.assertIn('priced at', out, q)

    def test_banknifty_and_a_forecast_with_no_chain(self):
        self.md[('BANKNIFTY', '1d')] = T.index_daily()
        out = self.say('volatility forecast banknifty')
        self.assertIn('VOLATILITY FORECAST: BANKNIFTY', out)
        self.assertNotIn('priced at', out)

    def test_every_question_says_what_to_install_when_the_library_is_missing(self):
        self.have.clear()
        for q, lib in (('results RELIANCE', 'nselib'), ('ban list', 'nselib'), ('fii flow', 'nselib'), ('holiday check', 'exchange-calendars')):
            out = self.say(q)
            self.assertIn('install %s into yourself' % lib, out, q)
        self.put_market(stock=None)
        out = self.say('volatility forecast nifty')
        self.assertIn('install arch into yourself', out)

    def test_every_question_says_when_the_source_failed(self):
        self.nse['ban'] = self.m._N92Err('failed', 'The helper stopped with an error (ConnectionError).')
        out = self.say('ban list')
        self.assertIn('I could not read NSE’s F&O ban list', out)
        self.assertIn('ConnectionError', out)

    def test_the_status_and_the_switch(self):
        out = self.say('scout intel')
        for part in ('✅ NSE data', '✅ Holiday cross-check', '✅ Volatility forecast', 'Switch: ON'):
            self.assertIn(part, out)
        self.have.discard('nselib')
        self.assertIn('❌ NSE data', self.say('nse data'))
        self.assertIn('Scout intel is OFF', self.say('scout intel off'))
        self.assertFalse(self.m._n94_intel_on())
        self.assertIn('Scout intel is ON', self.say('scout intel on'))

    def test_a_guest_gets_none_of_it(self):
        for q in ('results RELIANCE', 'ban list', 'fii flow', 'scout intel', 'holiday check'):
            n = len(self.passed)
            self.m.handle(self.guest(q))
            self.assertEqual(len(self.passed), n + 1, q)
        self.assertEqual(self.child_calls, [])
        self.assertEqual([t for c, t in self.sent if c == 5552], [])

    def test_nothing_here_places_an_order_or_touches_the_broker(self):
        for q in ('results RELIANCE', 'ban list', 'fii flow', 'holiday check', 'scout intel'):
            self.say(q)
        self.assertEqual(self.broker_calls, [])


class TestHolidayCheck(IntelCase):
    def run_check(self):
        return self.say('holiday check')

    def test_the_same_days_are_reported_as_the_same(self):
        out = self.run_check()
        self.assertIn('MARKET HOLIDAYS CHECK', out)
        self.assertIn('20 Oct (Dussehra)', out)
        self.assertIn('Cross-check with the exchange-calendars library', out)
        self.assertIn('the same days.', out)
        self.assertNotIn('DIFFERENT', out)

    def test_a_day_only_the_library_knows_is_flagged(self):
        self.nse['cal']['holidays'].append('2026-12-24')
        out = self.run_check()
        self.assertIn('DIFFERENT:', out)
        self.assertIn('the library says CLOSED on 2026-12-24 but my table says open: check NSE’s list', out)

    def test_a_day_only_my_table_knows_is_flagged(self):
        self.nse['cal']['holidays'].remove('2026-11-24')
        out = self.run_check()
        self.assertIn('my table says CLOSED on 2026-11-24 but the library says open (it can be an NSE-only holiday)', out)

    def test_the_2027_warning_is_always_there(self):
        out = self.run_check()
        self.assertIn('My table covers 2026 only', out)
        self.assertIn('1 Jan 2027', out)
        self.assertIn('keep NEW trade entries closed until it is updated', out)
        self.assertIn('say “holiday check” then', out)

    def test_the_helper_is_asked_for_the_next_120_days(self):
        self.run_check()
        kind, payload, need, secs = self.child_calls[0]
        self.assertEqual((kind, payload), ('cal', {'start': '2026-10-05', 'end': '2027-02-02'}))

    def test_a_calendar_that_ends_early_is_said(self):
        self.nse['cal']['checked_to'] = '2026-12-31'
        self.assertIn('The library knows holidays only up to 2026-12-31.', self.run_check())

    def test_without_the_library_the_table_is_still_shown_and_the_gap_is_named(self):
        self.have.discard('exchange_calendars')
        out = self.run_check()
        self.assertIn('My own table (NSE’s published 2026 list)', out)
        self.assertIn('Cross-check not done', out)
        self.assertIn('install exchange-calendars into yourself', out)

    def test_nemos_own_guards_are_not_touched_by_the_check(self):
        before = dict(self.m._N81_HOLIDAYS_2026)
        self.run_check()
        self.assertEqual(self.m._N81_HOLIDAYS_2026, before)
        self.assertEqual(self.m._n81_session(dt.datetime(2027, 1, 4, 11, 0, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30))))['state'], 'CALENDAR_UNVERIFIED')
        self.assertFalse(self.m._n81_session(dt.datetime(2027, 1, 4, 11, 0, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30))))['entry_open'])


# ===================================================================================================================
# 6. THE REAL HELPER PROGRAM (skips itself when no Python with pandas is available)
# ===================================================================================================================
def helper_python():
    cands = [os.environ.get('NEMO_TEST_PYTHON', ''), os.path.join(os.environ.get('NEMO_TEST_VENV', ''), 'bin', 'python'), sys.executable]
    for p in cands:
        if p and os.path.isfile(p):
            rc = subprocess.run([p, '-c', 'import pandas'], capture_output=True).returncode
            if rc == 0:
                return p
    return ''


FAKE_NSELIB = {
    '__init__.py': '',
    'capital_market.py': '''
import pandas as pd
def event_calendar_for_equity(from_date=None, to_date=None, period=None, fno_only=False):
    df = pd.DataFrame(%(events)r)
    df.columns = [name.replace(' ', '') for name in df.columns]
    return df
def corporate_actions_for_equity(from_date=None, to_date=None, period=None, fno_only=False):
    return pd.DataFrame(%(actions)r)
''',
    'derivatives.py': '''
import pandas as pd
def fno_security_in_ban_period(trade_date):
    return %(ban)r
def fii_derivatives_statistics(trade_date):
    if trade_date != '02-10-2026':
        raise Exception('No data available for : ' + trade_date)
    df = pd.DataFrame([[r['fii_derivatives'], float(r['buy_contracts']), float(r['buy_value_in_Cr']), float(r['sell_contracts']), float(r['sell_value_in_Cr']), float(r['open_contracts']), float(r['open_contracts_value_in_Cr'])] for r in %(fii)r],
                      columns=["fii_derivatives", "buy_contracts", "buy_value_in_Cr", "sell_contracts", "sell_value_in_Cr", "open_contracts", "open_contracts_value_in_Cr"])
    return df
def participant_wise_open_interest(trade_date):
    if trade_date != '02-10-2026':
        raise Exception('No data available for : ' + trade_date)
    rows = %(part)r
    return pd.DataFrame([{k.replace('\\t', ''): (int(v) if str(v).isdigit() else v) for k, v in r.items()} for r in rows])
''',
}


@unittest.skipUnless(helper_python(), 'no Python with pandas to run the real helper program')
class TestRealHelperProgram(ClearCase):
    @classmethod
    def setUpClass(cls):
        cls.py = helper_python()
        cls.fake_dir = tempfile.mkdtemp(prefix='nselib-fake-')
        pkg = os.path.join(cls.fake_dir, 'nselib')
        os.makedirs(pkg)
        fill = {'events': NSE_EVENTS, 'actions': NSE_ACTIONS, 'ban': NSE_BAN, 'fii': FII_STATS['rows'], 'part': PART_OI['rows']}
        for name, text in FAKE_NSELIB.items():
            open(os.path.join(pkg, name), 'w').write(text % fill if '%(' in text else text)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.fake_dir, ignore_errors=True)

    def run_prog(self, kind, payload, extra_path=True):
        env = dict(os.environ)
        env['PYTHONPATH'] = self.fake_dir if extra_path else ''
        r = subprocess.run([self.py, '-c', self.m._N94_PROG, kind, json.dumps(payload)], capture_output=True, text=True, env=env, timeout=120)
        return r

    def last(self, r):
        self.assertEqual(r.returncode, 0, r.stderr[-600:])
        return json.loads([ln for ln in r.stdout.splitlines() if ln.strip()][-1])

    def test_events_come_back_as_plain_strings_and_parse_the_same(self):
        out = self.last(self.run_prog('events', {'today': '2026-10-05', 'days': 21}))
        self.assertTrue(out['ok'])
        self.assertTrue(all(isinstance(v, str) for r in out['rows'] for v in r.values()))
        m = self.m._n94_events_map(out['rows'], dt.date(2026, 10, 5))
        self.assertEqual(m['RELIANCE']['sessions'], 1)
        self.assertEqual(m['TCS']['date'], dt.date(2026, 10, 8))

    def test_actions_ban_and_flows(self):
        a = self.last(self.run_prog('actions', {'today': '2026-10-05', 'days': 21}))
        self.assertEqual(self.m._n94_actions_map(a['rows'], dt.date(2026, 10, 5))['SBIN'][0][1], 'split')
        b = self.last(self.run_prog('ban', {'today': '2026-10-05'}))
        self.assertEqual(b['symbols'], NSE_BAN)
        f = self.last(self.run_prog('flows', {'today': '2026-10-05'}))
        self.assertEqual(f['fii_stats']['date'], '2026-10-02', 'the helper walks back over the weekend to the last day NSE published')
        self.assertEqual(f['part_oi']['date'], '2026-10-02')
        fl = self.m._n94_flow_summary(f)
        self.assertLess(fl['signal'], -0.5)
        self.assertTrue(any('FII are 33% long' in x for x in fl['lines']), fl['lines'])

    def test_a_source_that_fails_is_reported_not_raised(self):
        out = self.last(self.run_prog('flows', {'today': '2026-10-04'}))      # a Sunday, then Friday 2 Oct is found by walking back: still fine
        self.assertTrue(out['ok'])
        out = self.last(self.run_prog('flows', {'today': '2026-09-01'}))
        self.assertTrue(out['ok'])
        self.assertIsNone(out['fii_stats'])
        self.assertIsNone(out['part_oi'])
        self.assertTrue(any('No data available' in e for e in out['errors']), out['errors'])
        self.assertIsNone(self.m._n94_flow_summary(out))

    def test_a_missing_library_is_a_clean_exit_with_the_module_name(self):
        if subprocess.run([self.py, '-c', 'import nselib'], capture_output=True).returncode == 0:
            self.skipTest('the real nselib is installed in this Python, so it cannot be missing')
        r = self.run_prog('events', {'today': '2026-10-05'}, extra_path=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("No module named 'nselib'", r.stderr)
        err = self.m._n92_failure(r.returncode, r.stdout, r.stderr)
        self.assertEqual(err.code, 'not_installed')

    def test_an_unknown_kind_is_refused(self):
        self.assertFalse(self.last(self.run_prog('nonsense', {}))['ok'])

    def test_the_real_exchange_calendars_library_agrees_with_nemos_table(self):
        r = self.run_prog('cal', {'start': '2026-10-05', 'end': '2026-12-31'})
        if 'No module named' in r.stderr:
            self.skipTest('exchange_calendars is not installed here')
        out = self.last(r)
        mine = {d for d in self.m._N81_HOLIDAYS_2026 if '2026-10-05' <= d <= '2026-12-31' and dt.date.fromisoformat(d).weekday() < 5}
        self.assertEqual(set(out['holidays']), mine)

    def test_the_real_arch_library_gives_a_forecast(self):
        import random
        rnd = random.Random(4)
        px, closes = 22000.0, []
        for _ in range(500):
            px *= 1 + rnd.gauss(0.0004, 0.008)
            closes.append(px)
        r = subprocess.run([self.py, '-c', self.m._N94_PROG, 'vol', json.dumps({'closes': closes, 'horizon': 5})], capture_output=True, text=True, timeout=120)
        if 'No module named' in r.stderr:
            self.skipTest('arch is not installed here')
        out = self.last(r)
        self.assertTrue(out['ok'])
        self.assertTrue(6.0 <= out['forecast_vol_pct'] <= 20.0, out)
        self.assertEqual(out['n'], 499)
        short = subprocess.run([self.py, '-c', self.m._N94_PROG, 'vol', json.dumps({'closes': closes[:60], 'horizon': 5})], capture_output=True, text=True, timeout=120)
        self.assertFalse(json.loads(short.stdout.strip().splitlines()[-1])['ok'])
