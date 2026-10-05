"""Nemo v94 "Clear + Scout intel + Studio+": market replies and data dumps in plain words, NSE results/ban/flow checks, a holiday cross-check, a volatility forecast, AI enlarging, key-free background removal and a chart under every idea.

Offline. No Telegram, no network, no broker, no paid call, no trade. NSE, the AI picture tools and the forecast library are stand-ins that return what the real programs return (their shapes were read from the installed
libraries' own source); where a real library is available on this machine, the real helper program is also run, and those tests skip themselves when it is not.

    NEMO_FILE=/path/to/nemotron_bot.py python -m unittest tests.test_clear94 -v
"""
import ast
import copy
import datetime as dt
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from tests import test_cortex83 as base
from tests import test_scout93 as T
from tests.test_scout93 import ScoutCase, OptionCase, ScanCase, make_chain, news_sig, breakout_stock
from tests.test_forge91 import OWNER_ID

HERE = os.path.dirname(os.path.abspath(__file__))


REAL_SEND = None


def setUpModule():
    global REAL_SEND
    if base.m is None:
        base.setUpModule()
    REAL_SEND = real_send_text(base.m)


def real_send_text(m):
    """The v94 send_text wrapper, rebuilt from the layer's own source in the bot's namespace: the live name may be replaced by a recorder (or left replaced by an earlier test module), and these tests need the real thing."""
    fn = next(n for n in ast.parse(clear_source()).body if isinstance(n, ast.FunctionDef) and n.name == 'send_text')
    ns = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), '<v94 send_text>', 'exec'), m.__dict__, ns)
    return ns['send_text']


def v55_handler(m):
    """The MarketOS layer's own message handler (the layers above it are stubbed in these tests)."""
    for name, f in vars(m).items():
        if re.fullmatch(r'_N\d+_HANDLE_PREV', name) and callable(f) and '/chain55' in str(getattr(f, '__code__', None) and f.__code__.co_consts):
            return f
    raise AssertionError('no MarketOS handler found')


def clear_source():
    src = open(base.NEMO_FILE, encoding='utf-8').read()
    i = src.index('# NEMO 94 - CLEAR')
    j = src.index('# NEMO 95 - DOORS') if '# NEMO 95 - DOORS' in src else src.rindex("if __name__")       # (the next layer is checked by its own tests)
    return src[i:j]


def shapes():
    return json.load(open(os.path.join(HERE, 'fixtures', 'market55_shapes.json'), encoding='utf-8'))


def real_chain(m, spot=22421.95, days=2.062, step=50, n=12, oi_change=0.0):
    """The shape of the owner's own /chain55 NIFTY: no implied volatility, no expiry epochs, and 0 change in open interest on a first read."""
    ch = make_chain(m, spot=spot, iv=15.0, days=days, step=step, n=n, iv_null=True, expiry_ts=False, lot_prefix='NSE:NIFTY26O06')
    ch['expiry'] = '06-10-2026'
    ch['expiries'] = [{'label': '06-10-2026', 'timestamp': None}, {'label': '13-10-2026', 'timestamp': None}, {'label': '20-10-2026', 'timestamp': None}]
    for r in ch['rows']:
        r.update(chp=0.0, oi_change=oi_change)
    return ch


def no_raw_data(test, text):
    for bad in ('{', '}', '":', 'None', 'null', 'True', 'False', '[{'):
        test.assertNotIn(bad, text, bad)


class ClearCase(ScoutCase):
    def setUp(self):
        super().setUp()
        self.today = dt.date(2026, 10, 5)
        self.start(self.m, '_n94_today', lambda now=None: self.today)
        self.m._N94_INTEL.clear()
        for k in self.m._N94_STATS:
            self.m._N94_STATS[k] = 0
        self.m._n94_put('plain', 'on')
        self.out = []
        self.guest = lambda text, **k: dict({'chat': {'id': 5552, 'type': 'private'}, 'from': {'id': 5552, 'first_name': 'Asha'}, 'message_id': 3, 'text': text}, **k)
        self.wrapped_send = REAL_SEND                        # the real send_text of the bot (the v94 wrapper); the test base replaced m.send_text with a recorder
        self.h55 = v55_handler(self.m)
        self.start(self.m, '_N94_SEND_PREV', lambda cid, text, kb=None: self.out.append((cid, text)))

    def say55(self, text):
        n = len(self.sent)
        self.h55(self.msg(text))
        return '\n'.join(t for c, t in self.sent[n:] if c == OWNER_ID)


# ===================================================================================================================
# 1. THE REPLY THE OWNER COULD NOT READ: /chain55 NIFTY
# ===================================================================================================================
class TestChainInWords(ClearCase):
    def test_the_reply_is_words_with_no_braces_quotes_or_null(self):
        t = self.m._n55_trim_result(real_chain(self.m))
        no_raw_data(self, t)
        for part in ('OPTION CHAIN, in plain words', 'Index now: 22,421.95', '“at the money”', 'Put/Call ratio', 'Strikes around the price', 'Most open call contracts above the price',
                     'Most open put contracts below the price', 'How to read it', 'Information only. Nemo placed no order'):
            self.assertIn(part, t)
        self.assertLessEqual(len(t), 3900)

    def test_it_shows_the_strikes_near_the_price_not_the_cheapest_twelve_rows(self):
        t = self.m._n55_trim_result(real_chain(self.m))
        self.assertIn('22,400 ◀ price', t)
        self.assertIn('22,150', t)
        self.assertIn('22,650', t)
        self.assertNotIn('21,800', t)
        self.assertNotIn('23,000', t)
        self.assertEqual(len([ln for ln in t.splitlines() if ' │ Call ' in ln]), 11)

    def test_each_strike_line_has_call_and_put_prices_and_open_interest_in_lakh(self):
        t = self.m._n55_trim_result(real_chain(self.m))
        line = next(ln for ln in t.splitlines() if ln.startswith('22,400'))
        self.assertRegex(line, r'Call ₹\d[\d,]*\.\d\d · OI 1\.00 lakh │ Put ₹\d[\d,]*\.\d\d · OI 1\.00 lakh')

    def test_prices_keep_their_paise(self):
        t = self.m._n55_trim_result(real_chain(self.m))
        self.assertRegex(t, r'Call ₹\d+\.\d\d')
        self.assertNotRegex(t, r'Call ₹\d+ ')

    def test_the_expiry_and_days_left_are_in_words(self):
        t = self.m._n55_trim_result(real_chain(self.m))
        self.assertIn('Expiry: 06-10-2026 · about 2.1 days left', t)
        self.assertIn('Later expiries: 13-10-2026, 20-10-2026', t)

    def test_the_ceiling_and_the_floor_are_named_with_a_range(self):
        ch = real_chain(self.m)
        for r in ch['rows']:
            if r['type'] == 'CE' and r['strike'] == 22600.0:
                r['oi'] = 2_500_000.0
            if r['type'] == 'PE' and r['strike'] == 22200.0:
                r['oi'] = 3_100_000.0
        t = self.m._n55_trim_result(ch)
        self.assertIn('Most open call contracts above the price: 22,600 (25.00 lakh)', t)
        self.assertIn('Most open put contracts below the price: 22,200 (31.00 lakh)', t)
        self.assertIn('stay between 22,200 and 22,600', t)
        self.assertIn('a tendency, not a promise', t)

    def test_put_call_ratio_is_explained_at_each_level(self):
        for pcr, words in ((1.6, 'many more puts than calls'), (1.1, 'slightly more puts'), (0.85, 'slightly more calls'), (0.5, 'many more calls than puts')):
            ch = real_chain(self.m)
            ch['pcr_oi'] = pcr
            self.assertIn(words, self.m._n55_trim_result(ch), pcr)

    def test_the_expected_move_is_stated_in_points_and_percent(self):
        t = self.m._n55_trim_result(real_chain(self.m))
        self.assertRegex(t, r'together cost ₹\d+\.\d\d\. That is how far the market expects the index to move by expiry: about ±\d+ points \(±\d\.\d%\)')

    def test_implied_volatility_is_shown_and_credited_when_nemo_solved_it(self):
        ch = real_chain(self.m)
        self.assertNotIn('Implied volatility', self.m._n55_trim_result(ch), 'no volatility was sent and none was solved: none is invented')
        for r in ch['rows']:
            r['iv'] = 15.2
        ch['iv_solved'] = 50
        t = self.m._n55_trim_result(ch)
        self.assertIn('Implied volatility at the money: 15.2% (normal)', t)
        self.assertIn('worked out by Nemo from the option prices, because the broker did not send it', t)
        ch['iv_solved'] = 0
        self.assertNotIn('worked out by Nemo', self.m._n55_trim_result(ch))

    def test_a_change_in_open_interest_is_shown_only_when_there_is_one(self):
        self.assertNotIn('today)', self.m._n55_trim_result(real_chain(self.m)))
        t = self.m._n55_trim_result(real_chain(self.m, oi_change=1500.0))
        self.assertIn('(+1500 today)', t)
        t = self.m._n55_trim_result(real_chain(self.m, oi_change=-250000.0))
        self.assertIn('(-2.50 lakh today)', t)

    def test_a_chain_with_no_contracts_says_so_in_words(self):
        t = self.m._n55_trim_result({'ok': True, 'symbol': 'NIFTY', 'spot': 22000.0, 'atm': 22000.0, 'rows': []})
        self.assertIn('I could not get that for NIFTY', t)
        no_raw_data(self, t)

    def test_not_logged_in_names_the_fix(self):
        t = self.m._n55_trim_result({'ok': False, 'symbol': 'NIFTY', 'error': 'FYERS is not connected; structured live option chain requires the existing authenticated market-data connection'})
        self.assertIn('not logged in to Fyers', t)
        self.assertIn('/brokerurl', t)
        self.assertIn('8:20 AM', t)
        self.assertIn('no order was sent', t)
        self.assertNotIn('structured live option chain', t)

    def test_plain_off_brings_the_raw_data_back_and_plain_on_the_words(self):
        ch = real_chain(self.m)
        self.m._n94_put('plain', 'off')
        raw = self.m._n55_trim_result(ch)
        self.assertIn('"spot": 22421.95', raw)
        self.m._n94_put('plain', 'on')
        self.assertNotIn('"spot"', self.m._n55_trim_result(ch))

    def test_a_formatter_that_breaks_falls_back_to_a_readable_dump_never_an_error(self):
        self.start(self.m, '_n94_chain_by_strike', lambda rows: (_ for _ in ()).throw(RuntimeError('boom')))
        t = self.m._n55_trim_result(real_chain(self.m))
        self.assertIsInstance(t, str)
        self.assertGreater(len(t), 50)
        self.assertNotIn('"spot"', t)
        self.assertGreaterEqual(self.m._N94_STATS['errors'], 1)

    def test_the_command_sends_the_words_end_to_end(self):
        self.chain['NIFTY'] = real_chain(self.m)
        out = self.say55('/chain55 NIFTY')
        self.assertIn('OPTION CHAIN, in plain words', out)
        no_raw_data(self, out)
        self.assertEqual(self.broker_calls, [])


# ===================================================================================================================
# 2. EVERY OTHER MARKETOS COMMAND
# ===================================================================================================================
EXPECT = {
    'mdata': ('NIFTY: 5-minute prices', 'The last 5 candles'), 'mguard': ('DATA CHECK', 'Quality grade: A'), 'mclock': ('MARKET CLOCK', 'NSE is OPEN'), 'breadth': ('could not read the stocks inside NIFTY', '/brokerurl'),
    'mtf': ('TREND ON EVERY TIMEFRAME', 'timeframes disagree'), 'chain': ('OPTION CHAIN', 'Put/Call ratio'), 'greeks': ('how its price reacts', 'Delta 0.52'), 'iv': ('IMPLIED VOLATILITY', 'at the money 14.0%'),
    'oi': ('OPEN INTEREST', 'Biggest call positions'), 'move': ('HOW FAR THE MARKET EXPECTS', '(±1.43%)'), 'gex': ('GAMMA MAP', 'Switch level: 23,925'), 'expiry': ('EXPIRY VIEW', '“Max pain” strike: 24,500'),
    'strike': ('CONTRACTS THAT FIT A BULLISH INTRADAY VIEW', 'Best fit first'), 'liq': ('HOW EASILY THE OPTIONS TRADE', 'Easiest to trade'), 'decomp': ('I could not get that', 'two option-chain readings'),
    'structure': ('PRICE STRUCTURE', 'Pattern:'), 'sweep': ('STOP-HUNT CHECK', 'No sweep'), 'vwap': ('VWAP', 'Price is right at VWAP'), 'profile': ('WHERE THE VOLUME TRADED', 'Most traded price'),
    'open': ('I could not get that', 'not available yet'), 'scan': ('scanner found no stocks', '/brokerurl'), 'rs': ('I could not get that', 'Not enough daily price history'),
    'sectors': ('WHICH SECTORS ARE LEADING', 'ENERGY'), 'unusual': ('I could not get that', 'Not enough daily volume history'), 'footprint': ('SIGNS OF BIG-PLAYER ACTIVITY', 'Evidence: low'),
}


class TestEveryCommandInWords(ClearCase):
    def test_the_clock_date_does_not_depend_on_the_servers_timezone(self):
        for tz in ('UTC', 'Asia/Tokyo', 'America/New_York'):
            with mock.patch.dict(os.environ, {'TZ': tz}):
                time.tzset()
                t = self.m._n55_trim_result({'state': 'OPEN', 'date': '2026-10-05', 'market_open': True, 'entry_open': True, 'holiday': None, 'weekday': 'Monday'})
                self.assertIn('Monday, 05 Oct 2026', t, tz)
        time.tzset()

    def test_all_25_results_are_words(self):
        data = shapes()
        self.assertEqual(set(data), set(EXPECT))
        for name, x in data.items():
            with self.subTest(name):
                t = self.m._n55_trim_result(x)
                no_raw_data(self, t)
                self.assertLessEqual(len(t), 3900)
                for part in EXPECT[name]:
                    self.assertIn(part, t)

    def test_every_result_that_worked_ends_with_the_no_order_line_or_an_in_plain_words_line(self):
        for name, x in shapes().items():
            if x.get('ok') is False or name in ('breadth', 'scan'):
                continue
            t = self.m._n55_trim_result(x)
            self.assertTrue('In plain words' in t or 'Information only' in t or 'How to read it' in t, name)

    def test_the_old_function_is_kept_as_the_fallback_and_is_still_json(self):
        self.assertIn('"spot"', self.m._N94_TRIM_PREV(real_chain(self.m)))

    def test_greeks_in_words(self):
        t = self.m._n55_trim_result(shapes()['greeks'])
        self.assertIn('24,500 Call (27 Oct)', t)
        self.assertIn('if the index moves ₹100, this option moves about ₹52 in the same direction', t)
        self.assertIn('loses about ₹16.8 a day', t)
        self.assertIn('if implied volatility rises 1 point, the price rises about ₹12.5', t)

    def test_a_put_delta_is_described_as_moving_the_other_way(self):
        g = dict(shapes()['greeks'], kind='PE', delta=-0.48)
        t = self.m._n55_trim_result(g)
        self.assertIn('Put (27 Oct)', t)
        self.assertIn('(a put moves the opposite way)', t)

    def test_the_strike_ranking_names_each_contract(self):
        t = self.m._n55_trim_result(shapes()['strike'])
        self.assertIn('1. 24,500 Call · price ₹183.51 · delta 0.518', t)
        self.assertIn('it is not a buy call', t)

    def test_mtf_table_names_each_timeframe_in_words(self):
        t = self.m._n55_trim_result(shapes()['mtf'])
        for part in ('1-minute: not enough data', '5-minute: sideways (no clear direction) · sure at 52.5%', '15-minute', '1-hour', 'daily: not enough data'):
            self.assertIn(part, t)

    def test_levels_for_the_expiry_view_use_points_and_percent(self):
        t = self.m._n55_trim_result(shapes()['expiry'])
        self.assertIn('The index is 10 points below it', t)
        self.assertIn('Pull toward that level (0–100): 95 → strong', t)

    def test_a_sweep_and_a_structure_event_are_explained(self):
        s = dict(shapes()['sweep'], event='HIGH_SWEEP_REJECTION', strength=77.5)
        t = self.m._n55_trim_result(s)
        self.assertIn('poked above the recent high and fell back', t)
        self.assertIn('Strength: 77.5/100', t)
        st = dict(shapes()['structure'], event='CHOCH_UP', trend_structure='LH_LL_DOWN')
        t = self.m._n55_trim_result(st)
        self.assertIn('the downtrend may be turning', t)
        self.assertIn('downtrend (lower highs and lower lows)', t)

    def test_the_real_sector_rotation_shape_is_not_mistaken_for_the_scanner(self):
        secs = [{'sector': 'ENERGY', 'ret5': 2.5, 'ret20': 6.0, 'relative_score': 3.1, 'source': 'FYERS'}, {'sector': 'IT', 'ret5': -2.0, 'ret20': 1.0, 'relative_score': -1.2, 'source': 'FYERS'},
                {'sector': 'BANK', 'ret5': 0.5, 'ret20': 2.0, 'relative_score': 0.9, 'source': 'FYERS'}]
        t = self.m._n55_trim_result({'ok': True, 'benchmark': 'NIFTY', 'leaders': secs[:2], 'laggards': list(reversed(secs))[:2], 'sectors': secs, 'note': 'relative-rotation ranking, not a forecast'})
        self.assertIn('WHICH SECTORS ARE LEADING', t)
        self.assertIn('1. ENERGY: score 3.1 · 5-day +2.5% · 20-day +6.0%', t)
        self.assertNotIn('STOCK SCANNER', t)
        self.assertNotIn('n/a', t)
        self.assertLess(t.index('ENERGY'), t.index('BANK'))
        self.assertLess(t.index('BANK'), t.index('IT'))

    def test_the_scanner_and_the_sector_table_show_ranked_rows(self):
        row = {'symbol': 'RELIANCE', 'price': 2850.5, 'ret1': 1.2, 'ret5': 3.4, 'ret20': 8.1, 'rsi': 66.2, 'volume_ratio': 2.3, 'breakout20': True, 'breakdown20': False, 'scanner_score': 71.0}
        t = self.m._n55_trim_result({'ok': True, 'index': 'NIFTY', 'scanned': 30, 'leaders': [row], 'laggards': [dict(row, symbol='TCS', breakout20=False, breakdown20=True, ret5=-4.0, scanner_score=-33.0)]})
        self.assertIn('1. RELIANCE ₹2,850.50 · 5-day +3.4% · 20-day +8.1% · RSI 66.2 · volume 2.3× normal · 20-day breakout · score 71', t)
        self.assertIn('TCS', t)
        self.assertIn('20-day breakdown', t)
        sec = self.m._n55_trim_result({'ok': True, 'sectors': [{'sector': 'IT', 'relative_score': -1.2, 'ret5': -2.0, 'ret20': 1.0}, {'sector': 'ENERGY', 'relative_score': 3.1, 'ret5': 2.5, 'ret20': 6.0}]})
        self.assertLess(sec.index('ENERGY'), sec.index('IT'))

    def test_the_commands_reach_the_user_in_words_through_the_real_handler(self):
        data = shapes()
        table = (('/mdata55 NIFTY', '_n55_market_data', 'mdata'), ('/mguard55 NIFTY', '_n55_guardian_tool', 'mguard'), ('/mclock55', '_n55_market_clock', 'mclock'), ('/breadth55 NIFTY', '_n55_breadth', 'breadth'),
                 ('/mtf55 NIFTY', '_n55_mtf_regime', 'mtf'), ('/greeks55 NIFTY 24500 CE', '_n55_greeks_tool', 'greeks'), ('/iv55 NIFTY', '_n55_iv_surface', 'iv'), ('/oi55 NIFTY', '_n55_oi_intel', 'oi'),
                 ('/move55 NIFTY', '_n55_expected_move', 'move'), ('/gex55 NIFTY', '_n55_gex', 'gex'), ('/expiry55 NIFTY', '_n55_expiry_intel', 'expiry'), ('/strike55 NIFTY bullish intraday', '_n55_strike_rank', 'strike'),
                 ('/liq55 NIFTY', '_n55_liquidity', 'liq'), ('/decomp55 NIFTY 24500 CE', '_n55_decomp_tool', 'decomp'), ('/structure55 NIFTY', '_n55_structure', 'structure'), ('/sweep55 NIFTY', '_n55_sweep', 'sweep'),
                 ('/vwap55 NIFTY', '_n55_vwap', 'vwap'), ('/profile55 NIFTY', '_n55_volume_profile', 'profile'), ('/open55 NIFTY', '_n55_opening_gap', 'open'), ('/rs55 RELIANCE NIFTY', '_n55_relative_strength', 'rs'),
                 ('/sectors55', '_n55_sector_rotation', 'sectors'), ('/unusual55 NIFTY', '_n55_unusual_activity', 'unusual'), ('/footprint55 NIFTY', '_n55_institutional_footprint', 'footprint'))
        for cmd, fn, key in table:
            with self.subTest(cmd):
                self.start(self.m, fn, lambda *a, _k=key, **k: copy.deepcopy(data[_k]))
                out = self.say55(cmd)
                self.assertTrue(out, cmd)
                no_raw_data(self, out)
                self.assertIn(EXPECT[key][0], out)


# ===================================================================================================================
# 3. ANY OTHER JSON DUMP IS TURNED INTO WORDS (and ordinary messages are never touched)
# ===================================================================================================================
class TestHumanize(ClearCase):
    def test_names_numbers_booleans_and_nothing_are_readable(self):
        t = self.m._n94_humanize({'status': 'ok', 'version': '94.0', 'counts': {'a': 1, 'b': 2}, 'items': [1, 2, 3], 'big': 1234567.891, 'flag': True, 'nothing': None, 'call_oi_total': 966871.38, 'atm_iv_pct': 14.0})
        self.assertEqual(t.splitlines(), ['Status: ok', 'Version: 94.0', 'Counts:', '  A: 1', '  B: 2', 'Items: 1, 2, 3', 'Big: 12,34,568', 'Flag: yes', 'Nothing: not available', 'Call OI total: 9,66,871', 'ATM IV %: 14'])

    def test_epoch_times_become_dates_and_other_numbers_do_not(self):
        t = self.m._n94_humanize({'started_at': 1790000000, 'cycle': 1790000000, 'expiry_ts': 1791280800})
        self.assertIn('Started at: 21 Sep 2026, 19:43', t)
        self.assertIn('Cycle: 1,79,00,00,000', t)
        self.assertIn('Expiry time: 06 Oct 2026, 15:30', t)

    def test_a_ok_true_is_not_noise_and_a_failure_is_said(self):
        self.assertNotIn('OK', self.m._n94_humanize({'ok': True, 'cycle': 3}))
        self.assertIn('Result: did not succeed', self.m._n94_humanize({'ok': False, 'error': 'x'}))

    def test_records_lead_with_their_name_and_a_long_list_is_cut_honestly(self):
        t = self.m._n94_humanize({'rows': [{'id': i, 'name': 'n%d' % i, 'value': i * 1.5} for i in range(30)]})
        self.assertIn('Rows (30):', t)
        self.assertIn('1. n0 · ID 0 · Value 0', t)
        self.assertIn('… and 24 more', t)

    def test_depth_and_length_are_limited(self):
        deep = {'a': {'b': {'c': {'d': {'e': {'f': 1}}}}}}
        self.assertNotIn('{', self.m._n94_humanize(deep))
        long = self.m._n94_humanize({'k%d' % i: 'x' * 100 for i in range(200)}, limit=1000)
        self.assertLessEqual(len(long), 1000)
        self.assertTrue(long.endswith('(shortened)'))

    def test_a_title_in_front_of_the_json_is_kept(self):
        t = self.m._n94_dejson('🌐 INTERNET CAPABILITY AUDIT\n' + json.dumps({'ok': True, 'checks': 4, 'detail': {'dns': 'ok', 'tls': 'ok'}}, indent=2))
        self.assertTrue(t.startswith('🌐 INTERNET CAPABILITY AUDIT\n'))
        self.assertIn('Checks: 4', t)
        self.assertIn('Dns: ok', t)
        t = self.m._n94_dejson('Evolution result: ' + json.dumps({'ok': True, 'cycle': 3, 'changes': [{'name': 'a', 'n': 1.23456}]}))
        self.assertTrue(t.startswith('Evolution result\n'))

    def test_a_dump_that_was_cut_to_fit_a_message_is_still_readable(self):
        full = json.dumps({'a': list(range(50)), 'rows': [{'id': i, 'v': i * 1.5} for i in range(30)]}, indent=2)
        for n in (300, 700, 1000):
            t = self.m._n94_dejson(full[:n])
            self.assertIsNotNone(t, n)
            self.assertIn('cut to fit one message', t)
            no_raw_data(self, t)

    def test_ordinary_messages_are_left_alone(self):
        f = self.m._n94_dejson
        for s in ('Hello there, here is some [text] and {braces} that are not JSON at all, long enough to pass 40 chars.', '[1, 2, 3]', 'Usage: {"a": 1} is how you write it. ' * 3,
                  '```json\n{"a":1,"b":2}\n```', 'def f(x):\n    return {"a": x, "b": [1, 2, 3]}  # python code, not data, in a long enough line to be tested', 'x' * 100, '', 'ok',
                  '[Nemo] your reminder: call the bank at 5 pm, then pay the electricity bill and the "water" bill', 'Total: {a}'):
            self.assertIsNone(f(s), s[:40])

    def test_json_inside_a_code_fence_or_followed_by_words_is_left_alone(self):
        blob = json.dumps({'name': 'example', 'version': '1.0', 'items': [1, 2, 3], 'nested': {'a': True, 'b': None}}, indent=2)
        for s in ('```json\n' + blob + '\n```', 'Here is the config you asked for:\n' + blob + '\nSave it as config.json and restart.', blob + ' (this is only an example)'):
            self.assertIsNone(self.m._n94_dejson(s), s[:40])
        self.assertEqual(self.m._n94_json_loose(blob + ' trailing words'), (None, False))

    def test_a_single_key_object_or_a_short_list_is_left_alone(self):
        self.assertIsNone(self.m._n94_dejson(json.dumps({'only': 'one key here, long enough to be over forty characters easily'})))
        self.assertIsNone(self.m._n94_dejson('[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25]'))

    def test_loose_parsing(self):
        f = self.m._n94_json_loose
        self.assertEqual(f('{"a": 1}'), ({'a': 1}, False))
        self.assertEqual(f('{"a": 1, "b": [1, 2, 3'), ({'a': 1, 'b': [1, 2]}, True))
        self.assertEqual(f('{"a": 1, "b": "text that is cut'), ({'a': 1}, True))
        self.assertEqual(f('not json'), (None, False))
        self.assertEqual(f('{"a": 1}}'), (None, False))

    def test_large_dumps_are_not_attempted(self):
        self.assertIsNone(self.m._n94_dejson('{"a": "%s", "b": 1}' % ('x' * 70000)))


class TestSendTextSafetyNet(ClearCase):
    def send(self, text, kb=None):
        self.out.clear()
        self.wrapped_send(OWNER_ID, text, kb) if kb is not None else self.wrapped_send(OWNER_ID, text)
        return self.out[-1][1]

    def test_a_json_dump_is_sent_as_words(self):
        t = self.send(json.dumps({'status': 'ok', 'version': '94.0', 'counts': {'a': 1, 'b': 2}}, indent=2))
        self.assertEqual(t, 'Status: ok\nVersion: 94.0\nCounts:\n  A: 1\n  B: 2')
        self.assertEqual(self.m._N94_STATS['clear_json'], 1)

    def test_other_text_is_sent_exactly_as_it_is(self):
        for s in ('hello', 'Your balance is ₹1,23,456. {not json}', 'Result: [1, 2, 3]', '```python\nx = {"a": 1}\n```', '', 'a' * 5000):
            self.assertEqual(self.send(s), s)

    def test_buttons_are_passed_through(self):
        kb = {'inline_keyboard': [[{'text': 'OK', 'callback_data': 'x'}]]}
        self.out.clear()
        self.wrapped_send(OWNER_ID, 'Pick one', kb)
        self.assertEqual(self.out[-1], (OWNER_ID, 'Pick one'))

    def test_plain_off_sends_the_json_untouched(self):
        raw = json.dumps({'status': 'ok', 'version': '94.0', 'counts': {'a': 1, 'b': 2}}, indent=2)
        self.m._n94_put('plain', 'off')
        self.assertEqual(self.send(raw), raw)

    def test_a_failure_while_reading_never_stops_the_message(self):
        raw = json.dumps({'status': 'ok', 'version': '94.0', 'counts': {'a': 1, 'b': 2}}, indent=2)
        self.start(self.m, '_n94_dejson', lambda t: (_ for _ in ()).throw(RuntimeError('x')))
        self.assertEqual(self.send(raw), raw)
        self.assertEqual(self.m._N94_STATS['errors'], 1)

    def test_diagnostic_commands_that_print_json_now_read_as_words(self):
        stats = {'window_hours': 24, 'messages': 12, 'errors': 0, 'by_route': {'chat': 9, 'tool': 3}}          # the shape /observe-style commands dump
        t = self.send(json.dumps(stats, ensure_ascii=False, indent=2)[:3900])
        self.assertIn('Messages: 12', t)
        self.assertIn('By route:', t)
        self.assertNotIn('{', t)

    def test_the_wrapper_is_the_front_of_the_chain_and_the_old_one_is_kept(self):
        self.assertIsNot(self.wrapped_send, self.m._N94_SEND_PREV)
        self.assertEqual(self.wrapped_send.__name__, 'send_text')


# ===================================================================================================================
# 4. THE OPTION-CHAIN READER FILLS THE IMPLIED VOLATILITY THE BROKER LEAVES OUT
# ===================================================================================================================
def broker_payload(spot=22421.95, step=50, n=6, days=2.0):
    """What the broker's option-chain endpoint sends: no iv on any row, the expiry epoch as text."""
    chain = [{'symbol': 'NSE:NIFTY50-INDEX', 'option_type': '', 'strike_price': -1, 'ltp': spot}]
    atm = round(spot / step) * step
    for k in range(-n, n + 1):
        K = atm + k * step
        for typ in ('CE', 'PE'):
            p = max(0.5, base.m._n93_bs_price(spot, K, 15.0, days, typ))
            chain.append({'symbol': 'NSE:NIFTY26O06%d%s' % (K, typ), 'option_type': typ, 'strike_price': K, 'ltp': round(p, 2), 'bid': round(p * 0.997, 2), 'ask': round(p * 1.003, 2), 'oi': 100000, 'volume': 5000})
    return {'s': 'ok', 'data': {'optionsChain': chain, 'expiryData': [{'date': '06-10-2026', 'expiry': str(int(time.time() + days * 86400))}, {'date': '13-10-2026', 'expiry': ''}]}}


class TestChainReaderFillsVolatility(ClearCase):
    def setUp(self):
        super().setUp()
        m = self.m
        m._n55_init()                                          # the MarketOS tables, in this test's own database
        self.real_chain_fn = next(p.temp_original for p in self.fp if getattr(p, 'attribute', '') == '_n55_option_chain_struct')
        self.start(m, 'fyers_ready', lambda: True)
        self.start(m, 'fyers_data', lambda path: broker_payload())
        self.start(m, 'fyers_ltp', lambda sym: 22421.95)

    def test_every_row_gets_a_volatility_and_the_count_is_kept(self):
        ch = self.real_chain_fn('NIFTY', 6, persist=False)
        self.assertTrue(ch['ok'], ch)
        self.assertEqual(ch['iv_solved'], len(ch['rows']))
        for r in ch['rows']:
            self.assertTrue(12.0 <= r['iv'] <= 18.0, r)

    def test_the_stored_snapshot_has_the_volatility_so_the_price_breakdown_can_use_it(self):
        ch = self.real_chain_fn('NIFTY', 6, persist=True)
        row = self.m._n35_conn().execute('SELECT payload FROM market55_option_snapshot ORDER BY ts DESC LIMIT 1').fetchone()
        stored = json.loads(row[0])
        self.assertTrue(all(r.get('iv') for r in stored['rows']))
        self.assertEqual(stored['iv_solved'], ch['iv_solved'])

    def test_a_volatility_the_broker_does_send_is_left_alone(self):
        payload = broker_payload()
        payload['data']['optionsChain'][3]['iv'] = 41.5
        self.start(self.m, 'fyers_data', lambda path: payload)
        ch = self.real_chain_fn('NIFTY', 6, persist=False)
        kept = [r for r in ch['rows'] if r['iv'] == 41.5]
        self.assertEqual(len(kept), 1)
        self.assertEqual(ch['iv_solved'], len(ch['rows']) - 1)

    def test_without_days_to_expiry_nothing_is_guessed(self):
        self.assertEqual(self.m._n94_fill_iv_rows([{'strike': 22400.0, 'type': 'CE', 'ltp': 100.0}], 22400.0, None), 0)
        self.assertEqual(self.m._n94_fill_iv_rows([{'strike': 22400.0, 'type': 'CE', 'ltp': 100.0}], None, 2.0), 0)

    def test_the_greeks_and_the_iv_surface_now_work_on_this_feed(self):
        self.start(self.m, '_n55_option_chain_struct', lambda sym, strikes=12, expiry_ts=None, persist=True: self.real_chain_fn(sym, strikes, expiry_ts, persist))
        g = self.m._n55_greeks_tool('NIFTY', 22400.0, 'CE')
        self.assertTrue(g.get('ok'), g)
        self.assertTrue(12.0 <= g['iv_pct'] <= 18.0)
        s = self.m._n55_iv_surface('NIFTY', 1, 6)
        self.assertTrue(s['surface'][0]['points'])
        t = self.m._n55_trim_result(s)
        self.assertIn('at the money', t)

    def test_the_scout_option_note_still_says_the_volatility_was_solved(self):
        d = T.index_daily()
        self.md[('NIFTY', '1d')] = d
        self.md[('NIFTY', '15m')] = T.index_intraday(d[-1]['c'])
        self.md[('INDIAVIX', '1d')] = T.vix_series()
        solved = make_chain(self.m, spot=float(round(d[-1]['c'])), iv=13.0, days=6.0)
        solved['iv_solved'] = len(solved['rows'])
        self.chain['NIFTY'] = solved
        v, why = self.m._n93_index_view('NIFTY', self.m._n93_market_ctx(), news_sig(), time.time())
        self.assertIsNone(why)
        self.assertTrue(any('solved from the option prices' in n for n in v['notes']))


# ===================================================================================================================
# 5. TRADING WORDS IN PLAIN ENGLISH, THE GUIDE AND THE PLAIN SWITCH
# ===================================================================================================================
class TestGlossary(ClearCase):
    def test_what_is_pcr_is_answered_at_once_with_no_ai_and_no_network(self):
        out = self.say('what is PCR')
        self.assertIn('Put/Call ratio (PCR)', out)
        self.assertIn('Open put contracts divided by open call contracts', out)
        self.assertEqual(self.ai_calls, [])
        self.assertEqual(self.http.calls, [])
        self.assertEqual(self.m._N94_STATS['glossary'], 1)

    def test_the_many_ways_of_asking(self):
        for q, key in (('what is theta?', 'Theta (time decay)'), ("what's delta", 'Delta'), ('what does OI mean', 'Open interest (OI)'), ('explain implied volatility', 'Implied volatility (IV)'),
                       ('meaning of max pain', 'Max pain'), ('define stop loss', 'Stop loss'), ('what are the greeks', 'Delta'), ('what is a straddle', 'Straddle'), ('what is the vwap', 'VWAP'),
                       ('What is India VIX?', 'India VIX'), ('what does ATM stand for', 'At the money (ATM)'), ('what is open interest', 'Open interest (OI)'), ('what is risk-reward', 'Risk-reward'),
                       ('what is fii', 'FII / FPI'), ('what is an f&o ban', 'F&O ban period'), ('what is slippage', 'Slippage')):
            out = self.say(q)
            self.assertIn(key, out, q)

    def test_an_unknown_word_is_not_answered_here_so_the_assistant_can_answer(self):
        for q in ('what is the capital of France', 'what is my balance', 'what is a quasar', 'explain quantum computing', 'what is the weather'):
            n = len(self.passed)
            out = self.say(q)
            self.assertEqual(out, '', q)
            self.assertEqual(len(self.passed), n + 1, q)

    def test_single_letters_and_bare_everyday_words_are_not_hijacked(self):
        for q in ('what is r', 'what is x', 'words', 'terms', 'what is a'):
            n = len(self.passed)
            self.assertEqual(self.say(q), '', q)
            self.assertEqual(len(self.passed), n + 1, q)
        self.assertIn('R (risk multiple)', self.say('what is r multiple'))

    def test_the_glossary_list_and_the_guide(self):
        out = self.say('glossary')
        self.assertIn('TRADING WORDS I CAN EXPLAIN', out)
        for w in ('Delta', 'Put/Call ratio (PCR)', 'Theta (time decay)', 'F&O ban period'):
            self.assertIn(w, out)
        g = self.say('guide')
        for part in ('NEMO IN PLAIN WORDS', 'trade ideas', '/chain55 NIFTY', 'what is PCR', 'plain off', 'I never place an order'):
            self.assertIn(part, g)
        self.assertLessEqual(len(g), 3900)
        for alias in ('/guide', 'nemo guide', 'start here', 'what can I say'):
            self.assertIn('NEMO IN PLAIN WORDS', self.say(alias), alias)

    def test_every_entry_is_short_plain_and_free_of_markdown(self):
        G = self.m._N94_GLOSSARY
        self.assertGreaterEqual(len(G), 50)
        for k, (name, text) in G.items():
            self.assertLessEqual(len(text), 420, k)
            self.assertGreaterEqual(len(text), 40, k)
            self.assertNotIn('`', text)
            self.assertNotIn('**', text)
            self.assertTrue(name and name[0].isupper(), k)

    def test_every_alias_points_at_a_real_entry(self):
        for a, k in self.m._N94_ALIASES.items():
            self.assertIn(k, self.m._N94_GLOSSARY, a)
            self.assertEqual(self.m._n94_term(a), k, a)

    def test_the_words_used_in_the_replies_are_all_explained(self):
        for w in ('pcr', 'oi', 'iv', 'atm', 'delta', 'gamma', 'theta', 'vega', 'vwap', 'atr', 'rsi', 'adx', 'ema', 'max pain', 'gex', 'straddle', 'spread', 'liquidity', 'expiry', 'lot', 'breadth', 'poc', 'fvg', 'sweep', 'f&o ban',
                  'fii', 'stop loss', 'target', 'risk reward', 'r', 'position size', 'backtest', 'expectancy', 'drawdown', 'win rate'):
            self.assertIn(w, self.m._N94_GLOSSARY, w)

    def test_a_guest_is_not_served(self):
        n = len(self.passed)
        self.m.handle(self.guest('what is PCR'))
        self.assertEqual(len(self.passed), n + 1)
        self.assertEqual([t for c, t in self.sent if c == 5552], [])

    def test_the_plain_switch(self):
        self.assertIn('Plain words are OFF', self.say('plain off'))
        self.assertFalse(self.m._n94_plain_on())
        self.assertIn('Plain words are OFF', self.say('plain'))
        self.assertIn('Plain words are ON', self.say('plain on'))
        self.assertTrue(self.m._n94_plain_on())
        self.assertIn('Plain words are OFF', self.say('show me the raw data'))
        self.assertIn('Plain words are ON', self.say('turn the plain words on'))

    def test_a_guest_cannot_change_it(self):
        self.m.handle(self.guest('plain off'))
        self.assertTrue(self.m._n94_plain_on())
