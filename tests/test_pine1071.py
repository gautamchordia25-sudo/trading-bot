"""Nemo v107.1 "Pine": Pine Script requests go straight to the Pine engine (never the 3-minute work planner that answered "WORK_BUDGET_REACHED");
"with your survival logic" builds Nemo's own Survival Strategy without AI (the trading agent's GODMODE score plus Nemo's survival rules, settings from
the owner's words); a request with no details gets a choice card; AI-written scripts are checked (and grammar-parsed when pynescript is installed);
TradingView errors pasted back are fixed; a work plan that runs out of time says so in plain words.

Offline. No Telegram, no network, no real AI (scripted). The grammar parser child is real python; the real Pine grammar test runs only when
NEMO_PINE_PY names a python that has pynescript installed (it is slow the first time: about half a minute to warm up).

    NEMO_FILE=/path/to/nemotron_bot.py python -m unittest tests.test_pine1071 -v
    NEMO_PINE_PY=/path/to/venv/bin/python python -m unittest tests.test_pine1071 -v
"""
import inspect
import json
import os
import re
import tempfile
import time
import unittest
from unittest import mock

from tests import test_cortex83 as base
from tests.test_cortex83 import OWNER_ID
from tests.test_steady106 import SteadyCase

PINE_PY = os.environ.get('NEMO_PINE_PY', '')


def setUpModule():
    if base.m is None:
        base.setUpModule()


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def layer_source():
    src = read(base.NEMO_FILE)
    i = src.index('# NEMO 107.1 - PINE')
    j = src.index('# NEMO 108 - ') if '# NEMO 108 - ' in src else src.rindex("if __name__")
    return src[i:j]


class PineCase(SteadyCase):
    def setUp(self):
        super().setUp()
        m = self.m
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.put('_n1071_out_dir', lambda: self.dir.name)
        m._N1071_SYNC['on'] = True
        self.addCleanup(m._N1071_SYNC.__setitem__, 'on', False)
        for d in (m._N1071_PEND, m._N1071_LAST):
            saved = dict(d)
            d.clear()
            self.addCleanup(lambda d=d, saved=saved: (d.clear(), d.update(saved)))
        saved_py = dict(m._N1071_PY)
        m._N1071_PY.update(t=time.time() + 1e6, py=None)          # no grammar parser unless a test gives one
        self.addCleanup(m._N1071_PY.update, saved_py)
        for k in m._N1071_STATS:
            m._N1071_STATS[k] = 0
        self.docs = []

        def send_doc(cid, path, name, mime):
            self.docs.append({'cid': cid, 'path': path, 'name': name, 'mime': mime, 'code': read(path)})
            return True
        self.swap('send_document', send_doc)
        self.ai = mock.Mock(side_effect=AssertionError('the AI was asked'))
        self.put('_pine_ask', self.ai)
        self.prev = mock.Mock(return_value='passed on')
        self.put('_N1071_HANDLE_PREV', self.prev)
        self.auto = dict(m.AUTO)
        self.addCleanup(lambda: (m.AUTO.clear(), m.AUTO.update(self.auto)))
        m.AUTO['maxtrades'] = 1

    def say(self, text, **extra):
        return self.m.handle(self.msg(text, **extra))

    def card_buttons(self):
        out = []
        for (_c, _t, kb) in self.cards:
            if kb:
                kb = json.loads(kb) if isinstance(kb, str) else kb
                out += [b['callback_data'] for row in kb.get('inline_keyboard', []) for b in row]
        return out

    def press(self, data, who=OWNER_ID):
        return self.m.handle_callback({'id': 'q1', 'data': data, 'from': {'id': who}, 'message': {'chat': {'id': who}, 'message_id': 9}})

    def good(self, title='Custom', extra=''):
        """A small strategy that passes Nemo's checks."""
        return ('//@version=6\nstrategy("%s", overlay=true)\nfastLen = input.int(9, "Fast")\nslowLen = input.int(21, "Slow")\nf = ta.ema(close, fastLen)\ns = ta.ema(close, slowLen)\n'
                'longSig = ta.crossover(f, s)\nif longSig\n    strategy.entry("Long", strategy.long)\nif strategy.position_size > 0\n'
                '    strategy.exit("X", from_entry="Long", limit=strategy.position_avg_price * 1.02, stop=strategy.position_avg_price * 0.99)\n'
                'plotshape(longSig, "Buy", shape.triangleup, location.belowbar, color.new(color.green, 0), size=size.small)\nalertcondition(longSig, "Buy", "BUY")\n%s' % (title, extra))


# ===================================================================================================================
# 1. The screenshot: "create a pine script with your survival logics" now gets the script, not WORK_BUDGET_REACHED
# ===================================================================================================================
class TestTheScreenshot(PineCase):
    def test_the_message_from_the_screenshot_gets_nemos_survival_script_without_ai_or_the_work_planner(self):
        with mock.patch.object(self.m, '_N1071_N71_EXECUTE_PREV', side_effect=AssertionError('work planner used')):
            r = self.say('create a pine script with your survival logics')
        self.assertIsNone(r)
        self.prev.assert_not_called()
        self.ai.assert_not_called()
        self.assertEqual([], self.fake.calls, 'no AI call at all')
        self.assertEqual(1, len(self.docs))
        d = self.docs[0]
        self.assertEqual('nemo_survival_strategy.pine', d['name'])
        self.assertTrue(d['code'].startswith('//@version=6\n'))
        self.assertIn('strategy("Nemo Survival Strategy"', d['code'])
        text = self.texts()
        self.assertIn('Nemo Survival Strategy (Pine Script v6)', text)
        self.assertNotIn('WORK_BUDGET_REACHED', text)
        self.assertIn('I have not compiled it inside TradingView myself', text)
        self.assertEqual(1, self.m._N1071_STATS['survival'])

    def test_the_work_planner_hands_a_pine_request_over_if_the_router_still_sends_one(self):
        m = self.m
        m._n71_init()
        rid = 'W71-E8FAC87056'
        c = m._n35_conn()
        try:
            c.execute('INSERT INTO work71_run(id,chat_id,created,updated,request,status) VALUES(?,?,?,?,?,?)', (rid, str(self.cid), time.time(), time.time(), 'x', 'QUEUED'))
            c.commit()
        finally:
            c.close()
        with mock.patch.object(m, '_N1071_N71_EXECUTE_PREV', side_effect=AssertionError('planned anyway')):
            r = m._n71_execute(self.cid, rid, 'create a pine script with your survival logics', '')
        self.assertTrue(r['ok'])
        self.assertEqual('', r['text'], 'nothing extra is sent: the Pine engine sends the script itself')
        self.assertEqual(['nemo_survival_strategy.pine'], [d['name'] for d in self.docs])
        c = m._n35_conn()
        try:
            status = c.execute('SELECT status FROM work71_run WHERE id=?', (rid,)).fetchone()[0]
        finally:
            c.close()
        self.assertEqual('COMPLETE', status)
        self.assertEqual(1, m._N1071_STATS['handover'])

    def test_research_about_pine_still_goes_to_the_work_planner(self):
        prev = mock.Mock(return_value={'ok': True, 'text': 'report'})
        with mock.patch.object(self.m, '_N1071_N71_EXECUTE_PREV', prev):
            r = self.m._n71_execute(self.cid, 'W71-0000000001', 'research pine script libraries, compare them and create a pdf report', '')
        prev.assert_called_once()
        self.assertEqual('report', r['text'])
        self.assertEqual([], self.docs)

    def test_the_work_planner_running_out_of_time_says_so_in_plain_words(self):
        m = self.m
        m._n71_init()
        rid = 'W71-ABCDEF0123'
        plan = [{'tool': 'search', 'input': 'a'}, {'tool': 'search', 'input': 'b'}, {'tool': 'draft', 'input': 'c'}, {'tool': 'file', 'name': 'r.md', 'source': 2}]
        c = m._n35_conn()
        try:
            c.execute('INSERT INTO work71_run(id,chat_id,created,updated,request,status,plan) VALUES(?,?,?,?,?,?,?)', (rid, str(self.cid), time.time(), time.time(), 'x', 'PARTIAL', json.dumps(plan)))
            c.commit()
        finally:
            c.close()
        old = ('Work %s partial. Completed 2 planned steps. No later steps were started. Error: WORK_BUDGET_REACHED.\nAsk me how this task is going and include %s to inspect results.' % (rid, rid))
        with mock.patch.object(m, '_N1071_N71_EXECUTE_PREV', return_value={'ok': False, 'error': 'WORK_BUDGET_REACHED', 'text': old, 'verified': False}):
            r = m._n71_execute(self.cid, rid, 'compare three phones and make a report', '')
        self.assertFalse(r['ok'])
        self.assertNotIn('WORK_BUDGET_REACHED', r['text'])
        self.assertIn('ran out of its 3-minute limit after 2 of 4 steps (search, search)', r['text'])
        self.assertIn('Nothing was sent anywhere', r['text'])
        self.assertEqual(1, m._N1071_STATS['budget_plain'])


# ===================================================================================================================
# 2. A request with no details: a choice card, and the answer that follows
# ===================================================================================================================
class TestChoices(PineCase):
    def test_a_bare_request_gets_a_choice_card_not_a_guess(self):
        self.say('create a new pine script')
        self.assertEqual([], self.docs)
        self.ai.assert_not_called()
        buttons = self.card_buttons()
        self.assertEqual('pn1071:s', buttons[0], 'my survival strategy is the first choice')
        self.assertIn('pn1071:t:supertrend', buttons)
        self.assertIn(self.cid, self.m._N1071_PEND)

    def test_answering_the_card_in_words_gets_that_script(self):
        self.say('create a new pine script')
        self.say('use your survival logic')
        self.assertEqual(['nemo_survival_strategy.pine'], [d['name'] for d in self.docs])
        self.assertNotIn(self.cid, self.m._N1071_PEND)

    def test_answering_the_routers_clarifying_question_about_pine_also_reaches_the_pine_engine(self):
        m = self.m
        q = 'For the Nifty Pine Script, should I build a simple EMA-crossover indicator, or do you have different entry and exit rules in mind?'
        m._n80_clarify(self.cid, 'create a new pine script', q)
        self.say('with your survival logics')
        self.assertEqual(['nemo_survival_strategy.pine'], [d['name'] for d in self.docs])

    def test_after_the_card_unrelated_words_pass_through_and_the_card_expires(self):
        self.say('create a new pine script')
        self.say('what time is the meeting tomorrow')
        self.prev.assert_called_once()
        self.m._N1071_PEND[self.cid]['t'] -= 3600
        self.say('buy milk and bread')
        self.assertEqual(2, self.prev.call_count)
        self.assertEqual([], self.docs)

    def test_the_card_buttons(self):
        self.press('pn1071:s')
        self.press('pn1071:t:supertrend')
        self.assertEqual(['nemo_survival_strategy.pine', 'supertrend.pine'], [d['name'] for d in self.docs])
        self.assertEqual(self.m._pine_sanitize(self.m.PINE_T_SUPERTREND), self.docs[1]['code'])
        self.ai.assert_not_called()

    def test_someone_else_pressing_a_card_button_gets_nothing(self):
        self.press('pn1071:s', who=777)
        self.assertEqual([], self.docs)

    def test_slash_pine(self):
        self.say('/pine')
        self.assertIn('pn1071:s', self.card_buttons())
        self.assertEqual([], self.docs)
        self.say('/pinever')
        self.prev.assert_called_once()


# ===================================================================================================================
# 3. The survival script: Nemo's own rules, its settings from the owner's words
# ===================================================================================================================
class TestSurvivalScript(PineCase):
    def code(self, words=''):
        return self.m._n1071_survival_code(self.m._n1071_opts(words)[0])

    def test_it_passes_nemos_pine_checks_in_every_setting(self):
        m = self.m
        for words in ('', 'risk 2% per trade, 2 trades a day, long only, lot 65', 'capital 50000, stop after 1 loss, daily loss 2%, weekly loss 5%',
                      'signals on hourly, score 5, stop 2 atr, target 4 atr, entries between 9:30 and 14:00, square off 15:00', 'risk 0.5% and 10 trades a day'):
            code = self.code(words)
            self.assertEqual([], m.pine_lint(code), words)
            self.assertTrue(code.isascii())
            self.assertNotIn('{{', code)
            self.assertEqual(1, len(re.findall(r'(?m)^strategy\(', code)))
            for keep in m._N1071_SURVIVAL_KEEP:
                self.assertIn(keep, code, (words, keep))

    def test_the_signal_is_the_godmode_score_of_nemos_trading_agent(self):
        """The Pine score uses the same rules and numbers as godmode_analyze (the agent's fixed-rule brain) and the agent's ATR stop/target."""
        m = self.m
        gm = inspect.getsource(m._N99_GM_PREV) if hasattr(m, '_N99_GM_PREV') else inspect.getsource(m.godmode_analyze)
        for rule in ('ema_gap > 0.0015', 'rsi >= 55', 'rsi <= 45', 'hi3 * 0.98', 'lo3 * 1.02', 'score >= 4', 'score += 2', 'hist_now > 0 and hist_now > hist_prev'):
            self.assertIn(rule, gm, 'the agent rule changed: update the survival script too')
        code = self.code()
        for rule in ('trendGap   = input.float(0.15', 'rsiS >= 55 ? 1 : rsiS <= 45 ? -1', 'close >= hh * 0.98', 'close <= ll * 1.02', 'input.int(4, "Strong signal',
                     'trending and close > e20 and e20 > e50 ? 2', 'hist > 0 and hist > hist[1] ? 1', 'e20 > e20[5] ? 1'):
            self.assertIn(rule, code)
        atr = inspect.getsource(m.atr_levels)
        self.assertIn('1.5 * atr', atr)
        self.assertIn('3 * atr', atr)
        self.assertIn('input.float(1.5, "Stop-loss (x ATR', code)
        self.assertIn('input.float(3.0, "Target (x ATR', code)

    def test_the_survival_rules_are_nemos_stated_rules(self):
        m = self.m
        src = inspect.getsource(m._n991_capital_texts)
        self.assertIn('A daily loss limit of about 3%%', src)
        self.assertIn('weekly one of about 6%%', src)
        self.assertIn('two losses in a day and I stop', src)
        code = self.code()
        self.assertIn('input.float(1.0, "Risk per trade', code)
        self.assertIn('input.float(3.0, "Daily loss limit', code)
        self.assertIn('input.float(6.0, "Weekly loss limit', code)
        self.assertIn('input.int(2, "Stop for the day after this many losing trades"', code)
        self.assertIn('input.session("0920-1430"', code)
        self.assertIn('input.int(15, "Square off at hour"', code)
        self.assertIn('input.int(10, "Square off at minute"', code)
        self.assertIn('pyramiding=0', code)
        self.assertIn('lookahead=barmerge.lookahead_on', code, 'the higher-timeframe score uses completed bars only (no repainting)')
        self.assertIn('[s[1], a[1], r[1]]', code)

    def test_every_survival_rule_is_wired_into_the_trading_logic_not_just_declared(self):
        code = self.code()
        for line in ('riskAmt  = strategy.equity * riskPct / 100.0',
                     'units    = math.min(unitsRaw, maxUnits)',
                     'qty      = lotSize > 0 ? math.floor(units / lotSize) * lotSize : math.floor(units)',
                     'dayLossHit  = dayPnlPct <= -dayLossPct',
                     'weekLossHit = weekPnlPct <= -weekLossPct',
                     'haltWhy = tradesToday >= maxTrades ? "Trade limit for today used" : lossesToday >= maxLosses ? "Too many losses today" : dayLossHit ? "Daily loss limit hit" : '
                     'weekLossHit ? "Weekly loss limit hit" : ""',
                     'canEnter = flat and not halted and inEntry and not squareTime and qty > 0 and not na(score) and not na(atrSig)',
                     'goLong   = canEnter and score >= minScore',
                     'goShort  = canEnter and allowShort and score <= -minScore and not goLong',
                     'inEntry    = not timeframe.isintraday or not na(time(timeframe.period, entrySess, "Asia/Kolkata"))',
                     'squareTime = timeframe.isintraday and istMins >= sqHour * 60 + sqMinute',
                     'if squareTime and strategy.position_size != 0\n    strategy.close_all(',
                     'strategy.exit("Long exit", from_entry="Long", loss=stopTicks, profit=tgtTicks)',
                     'strategy.exit("Short exit", from_entry="Short", loss=stopTicks, profit=tgtTicks)',
                     '        if strategy.closedtrades.profit(i) < 0\n            lossesToday += 1',
                     'if timeframe.change("1D")\n    tradesToday := 0\n    lossesToday := 0\n    dayStartEq  := strategy.equity'):
            self.assertIn(line, code)

    def test_the_trade_limit_follows_the_agents_own_setting(self):
        self.m.AUTO['maxtrades'] = 2
        self.assertIn('input.int(2, "Max trades per day"', self.code())

    def test_words_change_the_settings_and_the_message_says_which(self):
        self.say('make a pine script with your survival rules, risk 2% per trade, 2 trades a day, long only, lot 65, capital 50000, stop after 1 loss, '
                 'daily loss 2%, weekly loss 5%')
        code = self.docs[0]['code']
        for part in ('input.float(2.0, "Risk per trade', 'input.int(2, "Max trades per day"', 'input.bool(false, "Also trade strong bearish', 'input.int(65, "Units per lot',
                     'initial_capital=50000', 'input.int(1, "Stop for the day after', 'input.float(2.0, "Daily loss limit', 'input.float(5.0, "Weekly loss limit'):
            self.assertIn(part, code)
        text = self.texts()
        self.assertIn('Changed from your words: risk 2% per trade; 2 trades a day; stop after 1 loss; daily loss limit 2%; weekly loss limit 5%; long trades only; lots of 65 units; '
                      'capital ₹50,000.', text)
        self.assertIn('(long trades only)', text)

    def test_settings_stay_inside_safe_limits(self):
        o, _ = self.m._n1071_opts('risk 50% per trade, 40 trades a day, entries between 8:00 and 17:00, square off 16:30, capital 500')
        self.assertEqual(5.0, o['risk'])
        self.assertEqual(10, o['max_trades'])
        self.assertEqual('0920-1430', o['session'])
        self.assertEqual((15, 10), o['sq'])
        self.assertEqual(10000, o['capital'])

    def test_make_it_long_only_right_after_changes_the_same_script_without_ai(self):
        self.say('create a pine script with your survival logic and risk 2%')
        self.say('make it long only')
        self.assertEqual(2, len(self.docs))
        code = self.docs[1]['code']
        self.assertIn('input.bool(false, "Also trade strong bearish', code)
        self.assertIn('input.float(2.0, "Risk per trade', code, 'the earlier change is kept')
        self.ai.assert_not_called()

    def test_email_it_too_when_asked(self):
        sent = mock.Mock(return_value=True)
        self.put('send_email', sent)
        self.say('create a pine script with your survival logic and email it to trader@example.com')
        sent.assert_called_once()
        to, subject, body, path = sent.call_args[0]
        self.assertEqual('trader@example.com', to)
        self.assertTrue(path.endswith('nemo_survival_strategy.pine'))
        self.assertIn('//@version=6', body)
        self.assertIn('Emailed it to trader@example.com', self.texts())

    def test_telegram_not_confirming_the_file_is_said(self):
        self.swap('send_document', lambda *a, **k: False)
        self.say('create a pine script with your survival logic')
        self.assertIn('Telegram did not confirm the file nemo_survival_strategy.pine', self.texts())
        self.assertIn('send the pine file again', self.texts())

    def test_send_the_file_again(self):
        self.say('create a pine script with your survival logic')
        self.say('send the pine file again')
        self.assertEqual(['nemo_survival_strategy.pine'] * 2, [d['name'] for d in self.docs])


# ===================================================================================================================
# 4. AI-written scripts are checked, repaired and, failing that, replaced by a checked script, with the reason
# ===================================================================================================================
class TestAiScripts(PineCase):
    def test_own_rules_are_written_by_the_ai_and_checked(self):
        self.put('_pine_ask', mock.Mock(return_value=self.good('RSI rules')))
        self.say('create a pine script: buy when rsi crosses above 30 and price is above the 200 ema, stop 1%, target 2%')
        self.assertEqual(1, len(self.docs))
        self.assertIn('strategy("RSI rules"', self.docs[0]['code'])
        text = self.texts()
        self.assertIn('✅ Your Pine Script v6 is attached', text)
        self.assertIn('The full grammar parse did not run (pynescript is not installed; say “install pynescript” to add it)', text)
        self.assertNotIn('grammar parse found no syntax error', text)

    def test_a_script_that_fails_the_checks_is_repaired(self):
        bad = self.good('Bad').replace('ta.ema(close, fastLen)', 'ema(close, fastLen)')
        ask = mock.Mock(side_effect=[bad, self.good('Fixed')])
        self.put('_pine_ask', ask)
        self.say('make a pine script for an ema crossover with a 2% target')
        self.assertEqual(2, ask.call_count)
        self.assertIn("'ema()' must be 'ta.ema()'", ask.call_args_list[1][0][0])
        self.assertIn('strategy("Fixed"', self.docs[0]['code'])

    def test_when_the_ai_keeps_failing_a_checked_script_is_sent_with_the_reason(self):
        bad = self.good('Bad').replace('ta.ema(close, fastLen)', 'ema(close, fastLen)')
        self.put('_pine_ask', mock.Mock(return_value=bad))
        self.say('make a pine script with a supertrend entry and a 2% target')
        self.assertEqual(self.m._pine_sanitize(self.m.PINE_T_SUPERTREND), self.docs[0]['code'])
        text = self.texts()
        self.assertIn('⚠️ The version the AI wrote still had problems after 2 fixes', text)
        self.assertIn("'ema()' must be 'ta.ema()'", text)
        self.assertEqual(1, self.m._N1071_STATS['fallbacks'])

    def test_no_repairs_when_the_time_budget_is_used_up(self):
        bad = self.good('Bad').replace('ta.ema(close, fastLen)', 'ema(close, fastLen)')
        ask = mock.Mock(return_value=bad)
        self.put('_pine_ask', ask)
        with mock.patch.dict(self.m._N1071_LIMITS, {'budget_s': 50}):
            self.say('make a pine script with a vwap entry')
        self.assertEqual(1, ask.call_count)
        self.assertIn('after 0 fixes', self.texts())

    def test_survival_with_other_entries_must_keep_every_survival_rule(self):
        m = self.m
        survival = m._n1071_survival_code(m._n1071_survival_defaults())
        stripped = survival.replace('riskPct', 'rp')
        changed = survival.replace('"Nemo strong bullish")', '"Nemo supertrend bullish")')
        ask = mock.Mock(side_effect=[stripped, changed])
        self.put('_pine_ask', ask)
        self.say('create a pine script with your survival logic but use supertrend for the entries')
        self.assertIn('Keep EVERY survival rule', ask.call_args_list[0][0][0])
        self.assertIn('The survival rules were removed or renamed (riskPct)', ask.call_args_list[1][0][0])
        self.assertEqual(changed, self.docs[0]['code'])
        self.assertTrue(self.docs[0]['name'].startswith('nemo_survival_'))

    def test_a_grammar_error_drives_a_repair(self):
        m = self.m
        seen = []

        class FakeGrammar(object):
            def __init__(self, warm=(), py=None, child=None):
                self.why = ''

            def check(self, code, timeout=None):
                seen.append(code)
                return {'state': 'error', 'line': 3, 'error': "no viable alternative at input 'x'"} if 'Broken' in code else {'state': 'ok'}

            def close(self):
                pass
        self.put('_N1071Grammar', FakeGrammar)
        ask = mock.Mock(side_effect=[self.good('Broken'), self.good('Whole')])
        self.put('_pine_ask', ask)
        self.say('make a pine script with an ema crossover and a 1% stop')
        self.assertIn('Pine grammar error at line 3', ask.call_args_list[1][0][0])
        self.assertIn('strategy("Whole"', self.docs[0]['code'])
        self.assertIn('a full Pine grammar parse found no syntax error', self.texts())
        self.assertEqual(2, len(seen))

    def test_changing_the_last_ai_script(self):
        self.put('_pine_ask', mock.Mock(return_value=self.good('First')))
        self.say('make a pine script: ema crossover with a 2% target')
        ask = mock.Mock(return_value=self.good('First', '// trailing stop added\n'))
        self.put('_pine_ask', ask)
        self.say('add a trailing stop to that script')
        self.assertIn('Change this Pine Script v6 as the request asks', ask.call_args[0][0])
        self.assertIn('strategy("First"', ask.call_args[0][0])
        self.assertEqual(2, len(self.docs))
        self.assertTrue(self.docs[1]['name'].endswith('_changed.pine'))

    def test_a_change_that_fails_leaves_the_last_script_alone(self):
        self.put('_pine_ask', mock.Mock(return_value=self.good('First')))
        self.say('make a pine script: ema crossover with a 2% target')
        bad = self.good('First').replace('ta.ema(close, fastLen)', 'ema(close, fastLen)')
        self.put('_pine_ask', mock.Mock(return_value=bad))
        self.say('add a trailing stop to that script')
        self.assertEqual(1, len(self.docs), 'no new file')
        self.assertIn('stays as it was', self.texts())


# ===================================================================================================================
# 5. TradingView errors pasted back are fixed; other errors and questions are left alone
# ===================================================================================================================
class TestTradingViewErrors(PineCase):
    def test_a_tradingview_error_fixes_the_last_script(self):
        self.say('create a pine script with your survival logic')
        survival = self.docs[0]['code']
        fixed = survival.replace('"Nemo strong bullish")', '"Nemo bullish")')
        ask = mock.Mock(return_value=fixed)
        self.put('_pine_ask', ask)
        self.say("line 145: Undeclared identifier 'foo'")
        prompt = ask.call_args[0][0]
        self.assertIn("Undeclared identifier 'foo'", prompt)
        self.assertIn('strategy("Nemo Survival Strategy"', prompt)
        self.assertEqual('fixed_nemo_survival_strategy.pine', self.docs[1]['name'])
        self.assertEqual(fixed, self.docs[1]['code'])

    def test_a_fix_of_the_survival_script_must_keep_its_survival_rules(self):
        self.say('create a pine script with your survival logic')
        survival = self.docs[0]['code']
        dropped = survival.replace('weekLossPct', 'wl')
        fixed = survival.replace('"Nemo strong bullish")', '"Nemo bullish")')
        ask = mock.Mock(side_effect=[dropped, fixed])
        self.put('_pine_ask', ask)
        self.say("line 145: Undeclared identifier 'foo'")
        self.assertIn('The survival rules were removed or renamed (weekLossPct)', ask.call_args_list[1][0][0])
        self.assertEqual(fixed, self.docs[1]['code'])

    def test_a_pasted_script_with_its_error(self):
        ask = mock.Mock(return_value=self.good('Mine fixed'))
        self.put('_pine_ask', ask)
        self.say("TradingView says Syntax error at input 'end' for my script:\n" + self.good('Mine').replace('if longSig', 'if longSig end'))
        self.assertIn('if longSig end', ask.call_args[0][0])
        self.assertIn('strategy("Mine fixed"', self.docs[0]['code'])

    def test_python_errors_and_ordinary_sentences_are_not_taken_for_pine_errors(self):
        self.say('create a pine script with your survival logic')
        self.say('Traceback (most recent call last):\n  File "a.py", line 3, in <module>\nNameError: name \'x\' is not defined')
        self.say('this is not a valid email address, please check it')
        self.assertEqual(2, self.prev.call_count)
        self.assertEqual(1, len(self.docs))

    def test_an_error_report_without_the_error_text_asks_for_it(self):
        self.say('my pine script shows an error in tradingview')
        self.assertIn('Paste the exact error text from TradingView', self.texts())
        self.ai.assert_not_called()
        self.assertEqual([], self.docs)


class TestOtherMessagesPassThrough(PineCase):
    def test_questions_about_pine_are_ordinary_chat(self):
        for q in ('what is pine script?', 'how do I add a pine script to the chart', 'explain pine script v6 to me'):
            self.say(q)
        self.assertEqual(3, self.prev.call_count)
        self.assertEqual([], self.docs)

    def test_sentences_that_only_mention_pine_are_ordinary_chat(self):
        for q in ('open the pine editor', 'pine script is hard', 'I was reading about pine script on the train'):
            self.say(q)
        self.assertEqual(3, self.prev.call_count)
        self.assertEqual([], self.docs)
        self.assertEqual([], self.cards)

    def test_no_verb_needed_for_the_survival_script(self):
        self.say('pine script with your survival logic')
        self.assertEqual(['nemo_survival_strategy.pine'], [d['name'] for d in self.docs])

    def test_other_people_and_other_chats(self):
        self.m.handle({'chat': {'id': 555, 'type': 'private'}, 'from': {'id': 555}, 'text': 'create a pine script with your survival logic', 'message_id': 2})
        self.m.handle({'chat': {'id': -100, 'type': 'group'}, 'from': {'id': OWNER_ID}, 'text': 'create a pine script with your survival logic', 'message_id': 3})
        self.assertEqual(2, self.prev.call_count)
        self.assertEqual([], self.docs)

    def test_make_it_short_with_no_script_just_delivered_is_not_ours(self):
        self.say('make it short and friendly')
        self.prev.assert_called_once()

    def test_make_it_short_after_talking_about_something_else_is_not_ours(self):
        self.say('create a pine script with your survival logic')
        with self.m.LOCK:
            self.m.HISTORY[self.cid].extend([{'role': 'user', 'content': 'draft an email to the dealer'}, {'role': 'assistant', 'content': 'Here is a draft…'}])
        self.say('make it short and friendly')
        self.prev.assert_called_once()
        self.assertEqual(1, len(self.docs))


# ===================================================================================================================
# 6. The grammar parser child (protocol, unavailable, timeout) and, when installed, the real Pine grammar
# ===================================================================================================================
FAKE_CHILD = r'''
import sys, json, time
sys.stdout.write(json.dumps({'ready': True}) + '\n'); sys.stdout.flush()
for line in sys.stdin:
    req = json.loads(line)
    code = req['code']
    if 'SLEEP' in code:
        time.sleep(30)
    r = {'state': 'error', 'line': 2, 'error': 'mismatched input'} if 'BROKEN' in code else {'state': 'ok'}
    r['id'] = req['id']
    sys.stdout.write(json.dumps(r) + '\n'); sys.stdout.flush()
'''


class TestGrammarChild(PineCase):
    def test_the_protocol(self):
        import sys
        g = self.m._N1071Grammar(warm=['//@version=6\nwarm'], py=sys.executable, child=FAKE_CHILD)
        try:
            self.assertEqual('ok', g.check('//@version=6\nfine')['state'])
            r = g.check('//@version=6\nBROKEN')
            self.assertEqual(('error', 2), (r['state'], r['line']))
            self.assertEqual('ok', g.check('//@version=6\nfine again')['state'])
        finally:
            g.close()
        self.assertEqual('unavailable', g.check('x')['state'])

    def test_no_parser_installed(self):
        g = self.m._N1071Grammar()
        self.assertEqual('unavailable', g.check('x')['state'])
        self.assertIn('pynescript is not installed', g.why)

    def test_a_parser_that_cannot_load_is_unavailable_not_failed(self):
        import sys
        g = self.m._N1071Grammar(py=sys.executable, child="import json,sys\nsys.stdout.write(json.dumps({'ready': False, 'why': 'ImportError'})+'\\n')\n")
        r = g.check('//@version=6\nx')
        self.assertEqual('unavailable', r['state'])
        self.assertIn('ImportError', g.why)

    def test_a_slow_parse_is_given_up_and_said(self):
        import sys
        g = self.m._N1071Grammar(py=sys.executable, child=FAKE_CHILD)
        t0 = time.time()
        r = g.check('SLEEP', timeout=2)
        self.assertLess(time.time() - t0, 10)
        self.assertEqual('unavailable', r['state'])
        self.assertIn('took longer than 2 seconds', g.why)

    def test_the_parser_python_is_found_once(self):
        m = self.m
        m._N1071_PY.update(t=0.0, py=None)
        calls = []
        self.put('_n1071_has_parser', lambda py: calls.append(py) or False)
        self.assertIsNone(m._n1071_parser_python())
        n = len(calls)
        self.assertGreaterEqual(n, 1)
        self.assertIsNone(m._n1071_parser_python())
        self.assertEqual(n, len(calls), 'looked up again within 10 minutes')


@unittest.skipUnless(PINE_PY and os.path.exists(PINE_PY), 'set NEMO_PINE_PY to a python with pynescript installed')
class TestRealPineGrammar(PineCase):
    """The survival script and every ready-made script parse with a real Pine grammar (pynescript); broken code does not."""

    def test_scripts_parse(self):
        m = self.m
        scripts = {'survival default': m._n1071_survival_code(m._n1071_survival_defaults())}
        for words in ('risk 2% per trade, 2 trades a day, long only, lot 65, capital 50000', 'signals on hourly, score 5, entries between 9:30 and 14:00, square off 15:00'):
            scripts['survival ' + words] = m._n1071_survival_code(m._n1071_opts(words)[0])
        for key, (_title, var, _base) in m._N1071_TEMPLATES.items():
            scripts['template ' + key] = m._pine_sanitize(getattr(m, var))
        g = m._N1071Grammar(py=PINE_PY)
        try:
            for name, code in scripts.items():
                r = g.check(code, timeout=300)
                self.assertEqual('ok', r['state'], (name, r))
            bad = scripts['survival default'].replace('s += e20 > e20[5] ? 1', 's += e20 > > e20[5] ? 1')
            r = g.check(bad, timeout=120)
            self.assertEqual('error', r['state'])
            self.assertEqual(bad.split('\n').index(next(ln for ln in bad.split('\n') if '> > e20' in ln)) + 1, r['line'])
        finally:
            g.close()


# ===================================================================================================================
# 7. Status, forgetting, capabilities, self-checks and safety of the layer
# ===================================================================================================================
class TestHousekeeping(PineCase):
    def test_version_and_regression_rows(self):
        m = self.m
        self.assertEqual('107.1', m.VERSION)
        rows = m._n1071_regression_rows()
        self.assertTrue(rows and all(r['ok'] for r in rows), [r for r in rows if not r['ok']])
        names = {r['name'] for r in m.prime_regression_suite()['tests']}
        self.assertIn('v1071-routes-survival', names)

    def test_status(self):
        self.say('create a pine script with your survival logic')
        self.say('pine status')
        text = self.texts()
        self.assertIn('Last script: nemo_survival_strategy.pine (survival)', text)
        self.assertIn('not installed (say “install pynescript” to add it)', text)

    def test_forgetting_the_last_request(self):
        m = self.m
        self.say('create a pine script with your survival logic')
        self.assertIn('pine1071', {s[0] for s in m._N86_STORES})
        self.assertEqual(1, m._n1071_st_pine(self.cid, lambda t: 'survival' in t, False))
        self.assertIsNotNone(m._n1071_last(self.cid))
        self.assertEqual(1, m._n1071_st_pine(self.cid, lambda t: 'survival' in t, True))
        self.assertIsNone(m._n1071_last(self.cid))

    def test_capabilities_and_self_development_cannot_edit_the_layer(self):
        m = self.m
        self.assertIn('Pine 107.1', m._n82_capabilities())
        self.assertFalse(m._n79_editable('_n1071_route'))

    def test_the_layer_places_no_orders_and_holds_no_secrets(self):
        src = layer_source()
        for bad in ('fyers_place', 'place_order', 'fyers_place_bracket', '_p75_open', 'AUTO[', "AUTO['", 'save_secret', 'TOKEN', 'api_key'):
            self.assertNotIn(bad, src.replace("AUTO.get('maxtrades')", ''), bad)
        self.assertNotIn('requests.post', src)


if __name__ == '__main__':
    unittest.main()
