"""Nemo v99.1 Answer: the owner's screenshot ("Trade Lab stopped: _N73Error" in answer to a general question about surviving on 20000 rupees of options trading) fixed at its three causes, and the question
answered from Nemo's own practice record and a simulation.

  1. a hypothetical or strategy question about trading is no longer sent to the paper-trading research tool;
  2. a failure of the direct AI gateway falls through to the older brains (switchable);
  3. a Trade Lab dead end caused by the AI becomes an ordinary answer.

Offline. No network, no broker, no AI: the AI calls are scripted.

    NEMO_FILE=/path/to/nemotron_bot.py python -m unittest tests.test_answer991 -v
"""
import ast
import copy
import random
import re
import time
import unittest
from unittest import mock

from tests import test_cortex83 as base
from tests.test_forge91 import OWNER_ID
from tests.test_ledger96 import LedgerCase, bot_source, trade

SHOT = ('nemo supposed you have 20000 rupees with you as a survive on trading in options in indian stock market how will you survive and what 1 year return you can make for you deeply analyse how and tell me')


def setUpModule():
    if base.m is None:
        base.setUpModule()


def v991_source():
    src = bot_source()
    i = src.index('# NEMO 99.1 - ANSWER')
    j = src.index('# NEMO 100 - ') if '# NEMO 100 - ' in src else src.rindex("if __name__")
    return src[i:j]


class AnswerCase(LedgerCase):
    def setUp(self):
        super().setUp()
        m = self.m
        for k in m._N991_STATS:
            m._N991_STATS[k] = 0
        self.start(m, '_N991_SYNC', True)
        m._N991_LAST.update(t=0.0, code='')
        self.kv = {}
        self.start(m, '_n36_kv_get', lambda k, d=None: self.kv.get(k, d))
        self.start(m, '_n36_kv_set', lambda k, v: self.kv.__setitem__(k, v))

    def many(self, n=22, win=0.45, seed=3, spacing=2):
        rnd = random.Random(seed)
        for i in range(n):
            e = round(60 + rnd.random() * 60, 1)
            won = rnd.random() < win
            x = round(e * (rnd.uniform(1.4, 1.7) if won else rnd.uniform(0.6, 0.75)), 1)
            self.add(trade(entry=e, exit=x, days_ago=(n - i) * spacing, reason='target' if won else 'stop-loss'))


# ===================================================================================================================
# 1. WHAT IS A GENERAL TRADING QUESTION, AND WHAT IS A CAPITAL QUESTION
# ===================================================================================================================
class TestClassifier(AnswerCase):
    GENERAL = (SHOT, 'suppose you had 50000 rupees for option trading how would you survive a year',
               'imagine you start options trading in the indian stock market with a small capital, what return can you make in 1 year?',
               'how will you survive trading nifty options with 1 lakh rupees',
               'if you had 30000 to trade futures and options, what would the yearly return be',
               'what if i start intraday trading in the share market with 25000 rupees how much can i make')
    MARKET = ('research the NIFTY option chain and show OI and PCR for this expiry', 'show my paper trading journal please', 'paper trade plan for NIFTY 24500 CE with entry at 120 stop at 90',
              'what is the max pain for banknifty this week and the implied volatility', 'refresh my paper positions and tell me the greeks of the open one', 'analyse the option chain of NIFTY and tell me the best strike')

    def test_general_questions_are_recognised(self):
        for q in self.GENERAL:
            self.assertTrue(self.m._n991_general_trading(q), q)

    def test_market_data_and_paper_requests_are_not_general(self):
        for q in self.MARKET:
            self.assertFalse(self.m._n991_general_trading(q), q)

    def test_not_about_trading_or_not_hypothetical(self):
        for q in ('suppose you have 20000 rupees how will you survive on a desert island and what return can you make', 'what is the nifty today', 'tell me a joke', 'hello nemo',
                  'buy 1 lot nifty', 'trading options is fun', 'i like options', 'suppose', ''):
            self.assertFalse(self.m._n991_general_trading(q), q)

    def test_amounts(self):
        f = self.m._n991_amount
        for text, want in (('₹20,000', 20000.0), ('Rs 20000', 20000.0), ('Rs. 50,000', 50000.0), ('20000 rupees', 20000.0), ('20k rupees', 20000.0), ('2 lakh rupees', 200000.0), ('₹1.5 lakh', 150000.0),
                           ('INR 75000', 75000.0), ('with 3 lac rs', 300000.0), ('1 crore rupees', 1e7)):
            self.assertEqual(f(text), want, text)
        for text in ('20 rupees', 'suppose 20000 will do', 'a 1 year return', 'rs 5', '₹5000000000', 'no money at all', ''):
            self.assertIsNone(f(text), text)

    def test_the_owners_exact_question_is_a_capital_question(self):
        self.assertTrue(self.m._n991_capital_question(SHOT))
        self.assertEqual(self.m._n991_amount(SHOT), 20000.0)

    def test_a_capital_question_needs_money_trading_and_a_return_or_survival_question(self):
        f = self.m._n991_capital_question
        self.assertTrue(f('suppose you had ₹50,000 for option trading, how will you survive and what return can you make in a year'))
        self.assertFalse(f('suppose you trade nifty options how will you survive'))                                  # no amount
        self.assertFalse(f('research the NIFTY option chain with 20000 rupees budget'))                              # a market request
        self.assertFalse(f('suppose you have 20000 rupees which phone should i buy'))                                # not trading


# ===================================================================================================================
# 2. FAULT 1: THE ROUTER
# ===================================================================================================================
class TestRouter(AnswerCase):
    def decide(self, route, text):
        self.start(self.m, '_N991_DECIDE_PREV', lambda cid, t, ctx: {'route': route})
        return self.m._n72_decide(OWNER_ID, text, '')

    def test_a_general_trading_question_goes_to_the_conversation_not_to_trade_lab(self):
        self.assertEqual(self.decide('trade75', SHOT), {'route': 'chat80'})
        self.assertEqual(self.m._N991_STATS['rerouted'], 1)

    def test_a_market_request_still_goes_to_trade_lab(self):
        self.assertEqual(self.decide('trade75', 'research the NIFTY option chain and show OI and PCR'), {'route': 'trade75'})
        self.assertEqual(self.m._N991_STATS['rerouted'], 0)

    def test_other_routes_are_untouched(self):
        for route in ('legacy', 'work', 'chat80', 'status', 'health'):
            self.assertEqual(self.decide(route, SHOT), {'route': route})

    def test_through_the_real_task_a_general_question_reaches_the_conversation_and_never_trade_lab(self):
        m = self.m
        q = 'imagine you trade nifty options for a year with a small capital: how do traders survive and what return can they expect?'
        self.start(m, '_N991_DECIDE_PREV', lambda cid, t, ctx: {'route': 'trade75'})
        chat, lab = [], []
        self.start(m, '_n80_chat', lambda msg: chat.append(msg['text']) or {'ok': True, 'text': 'A real answer.'})
        self.start(m, '_n75_trade_task', lambda msg: lab.append(msg) or {'ok': True, 'text': 'x'})
        out = m._n72_task(self.msg(q))
        self.assertEqual(out, {'ok': True, 'text': 'A real answer.'})
        self.assertEqual((chat, lab), ([q], []))
        # and a real market request still reaches Trade Lab
        q2 = 'research the NIFTY option chain and show OI and PCR for this expiry'
        m._n72_task(self.msg(q2))
        self.assertEqual(len(lab), 1)

    def test_the_routers_error_passes_through(self):
        def boom(cid, t, ctx):
            raise ValueError('router down')
        self.start(self.m, '_N991_DECIDE_PREV', boom)
        with self.assertRaises(ValueError):
            self.m._n72_decide(OWNER_ID, SHOT, '')

    def test_a_non_dict_decision_is_returned_as_it_is(self):
        self.start(self.m, '_N991_DECIDE_PREV', lambda cid, t, ctx: None)
        self.assertIsNone(self.m._n72_decide(OWNER_ID, SHOT, ''))


# ===================================================================================================================
# 3. FAULT 2: THE GATEWAY FALLS THROUGH TO THE OLDER BRAINS
# ===================================================================================================================
class TestGatewayFallback(AnswerCase):
    def core(self, behaviour, **kw):
        self.start(self.m, '_N991_CORE_PREV', behaviour)
        return self.m._n73_core_reply(kw.get('cid', OWNER_ID), 'hi', [], raw=kw.get('raw', True))

    def raising(self, code):
        def f(*a, **k):
            raise self.m._N73Error(code, True)
        return f

    def test_a_gateway_failure_returns_none_so_the_older_brains_try(self):
        for code in ('http_429', 'http_402', 'http_401', 'brain_busy', 'providers_cooling_down', 'api_error', 'transport_or_response_error', 'empty_response', 'incomplete_response', 'invalid_json', 'model_not_in_catalog',
                     'invalid_brain_configuration'):
            self.assertIsNone(self.core(self.raising(code)), code)
        self.assertEqual(self.m._N991_STATS['fallbacks'], 12)
        self.assertEqual(self.m._N991_LAST['code'], 'invalid_brain_configuration')

    def test_not_after_a_refusal_a_cancellation_a_spent_time_budget_or_an_oversize_input(self):
        for code in ('provider_refusal', 'cancelled', 'time_budget_exhausted', 'input_too_large', 'text_context_too_large', 'unsupported_image', 'unsupported_input'):
            with self.assertRaises(self.m._N73Error, msg=code):
                self.core(self.raising(code))
        self.assertEqual(self.m._N991_STATS['fallbacks'], 0)

    def test_the_polite_failure_text_of_a_normal_call_also_falls_through(self):
        txt = 'I could not complete this answer (http_429). Your request was not executed by this model call. You can ask which AI brains are available and try again.'
        self.assertIsNone(self.core(lambda *a, **k: txt, raw=False))
        refused = 'I could not complete this answer (provider_refusal). Your request was not executed by this model call.'
        self.assertEqual(self.core(lambda *a, **k: refused, raw=False), refused)

    def test_a_good_answer_and_none_pass_through_unchanged(self):
        self.assertEqual(self.core(lambda *a, **k: 'a fine answer'), 'a fine answer')
        self.assertIsNone(self.core(lambda *a, **k: None))
        other = 'The turn ran out of time.'
        self.assertEqual(self.core(lambda *a, **k: other), other)

    def test_other_errors_are_not_swallowed(self):
        def boom(*a, **k):
            raise KeyError('x')
        with self.assertRaises(KeyError):
            self.core(boom)

    def test_the_switch(self):
        self.kv['n991_fallback'] = 'off'
        with self.assertRaises(self.m._N73Error):
            self.core(self.raising('http_429'))
        self.assertEqual(self.core(lambda *a, **k: 'I could not complete this answer (http_429).', raw=False), 'I could not complete this answer (http_429).')

    def test_only_the_owner_is_covered(self):
        with self.assertRaises(self.m._N73Error):
            self.core(self.raising('http_429'), cid=999)

    def test_the_arguments_reach_the_gateway_unchanged(self):
        seen = []
        self.start(self.m, '_N991_CORE_PREV', lambda *a, **k: seen.append((a, k)) or 'ok')
        self.m._n73_core_reply(OWNER_ID, 'q', [{'role': 'user', 'content': 'q'}], image=False, remember=False, timeout=33, long_output=True, models_override=None, deep=True, raw=True)
        self.assertEqual(seen[0][0], (OWNER_ID, 'q', [{'role': 'user', 'content': 'q'}]))
        self.assertEqual(seen[0][1], {'image': False, 'remember': False, 'timeout': 33, 'long_output': True, 'models_override': None, 'deep': True, 'raw': True})

    def test_end_to_end_through_the_real_ask_ai_the_older_brains_answer(self):
        """The gateway fails with a rate limit; the call that used to end in "Trade Lab stopped: _N73Error" now reaches the older chain, which (scripted) answers."""
        m = self.m
        import requests
        calls = []

        class Resp:
            status_code = 200
            text = ''

            def json(self_inner):
                return {'choices': [{'message': {'content': 'An answer from the older brain.'}, 'finish_reason': 'stop'}]}

        def fake_post(url, **kw):
            calls.append(url)
            return Resp()
        real = [p for p in self.fp if getattr(p, 'attribute', '') == 'ask_ai']
        for p in real:                                                          # the shared test base replaces ask_ai with a stub; this test needs the real chain
            p.stop()
            self.fp.remove(p)
        self.start(m, '_N991_CORE_PREV', self.raising('http_429'))
        self.start(requests, 'post', fake_post)
        out = m.ask_ai(OWNER_ID, 'What is photosynthesis?', remember=False, raw=True, timeout=20)
        self.assertIn('older brain', str(out))
        self.assertTrue(calls)
        self.assertEqual(m._N991_STATS['fallbacks'], 1)

    def test_the_fallback_status_text(self):
        text = self.m._n991_fallback_text()
        self.assertIn('BRAIN FALLBACK: ON', text)
        self.assertIn('not been needed since this version started', text)
        self.m._N991_LAST.update(t=time.time() - 600, code='http_429')
        self.assertIn('the gateway said http_429', self.m._n991_fallback_text())


# ===================================================================================================================
# 4. FAULT 3: A TRADE LAB DEAD END BECOMES AN ORDINARY ANSWER
# ===================================================================================================================
class TestTradeLabRescue(AnswerCase):
    def run_lab(self, result, text=SHOT):
        self.chat_calls, self.legacy_calls = [], []
        self.start(self.m, '_N991_TRADE_PREV', lambda msg: result)
        return self.m._n75_trade_task(self.msg(text))

    def test_an_ai_dead_end_is_handed_to_the_ordinary_conversation(self):
        self.start(self.m, '_n80_chat', lambda msg: self.chat_calls.append(msg) or {'ok': True, 'text': 'A real answer.'})
        out = self.run_lab({'ok': False, 'text': 'Trade Lab stopped: _N73Error. No real broker order was sent.'})
        self.assertEqual(out, {'ok': True, 'text': 'A real answer.'})
        self.assertEqual(len(self.chat_calls), 1)
        self.assertEqual(self.m._N991_STATS['rescued'], 1)

    def test_when_the_conversation_has_nothing_the_older_handler_is_used(self):
        self.start(self.m, '_n80_chat', lambda msg: None)
        self.start(self.m, '_n72_legacy', lambda msg: self.legacy_calls.append(msg))
        out = self.run_lab({'ok': False, 'text': 'Trade Lab stopped: _N73Error. No real broker order was sent.'})
        self.assertEqual(out, {'ok': True, 'text': ''})
        self.assertEqual(len(self.legacy_calls), 1)

    def test_the_other_ai_caused_stops_are_rescued_too(self):
        self.start(self.m, '_n80_chat', lambda msg: {'ok': True, 'text': 'ok'})
        for cause in ('Research model unavailable', 'Trading intent could not be validated; specify symbol and requested analysis'):
            self.assertTrue(self.run_lab({'ok': False, 'text': 'Trade Lab stopped: %s. No real broker order was sent.' % cause})['ok'], cause)

    def test_real_trade_lab_problems_keep_their_message(self):
        res = {'ok': False, 'text': 'Trade Lab stopped: Fyers market-data request failed. No real broker order was sent.'}
        self.assertEqual(self.run_lab(res), res)
        res = {'ok': False, 'text': 'Owner private chat only.'}
        self.assertEqual(self.run_lab(res), res)
        self.assertEqual(self.m._N991_STATS['rescued'], 0)

    def test_a_paper_plan_id_is_never_rescued(self):
        res = {'ok': False, 'text': 'Trade Lab stopped: _N73Error. No real broker order was sent.'}
        self.assertEqual(self.run_lab(res, 'paper trade P75-0123456789'), res)

    def test_good_results_pass_through(self):
        res = {'ok': True, 'text': 'PAPER RESEARCH | NIFTY\n...'}
        self.assertEqual(self.run_lab(res), res)

    def test_a_failing_rescue_does_not_raise(self):
        def boom(msg):
            raise RuntimeError('chat down')
        self.start(self.m, '_n80_chat', boom)
        res = {'ok': False, 'text': 'Trade Lab stopped: _N73Error. No real broker order was sent.'}
        self.assertEqual(self.run_lab(res), res)
        self.assertEqual(self.m._N991_STATS['errors'], 1)


# ===================================================================================================================
# 5. THE ANSWER: THE SIMULATION
# ===================================================================================================================
class TestSimulation(AnswerCase):
    def test_a_sure_win_grows_the_money_and_never_ruins(self):
        r = self.m._n991_sim(20000, 5000, lambda rng: 0.10, 10, 50, 1)
        self.assertAlmostEqual(r['median'], 20000 + 10 * 500, 6)
        self.assertEqual((r['below_start'], r['half_lost'], r['ruined']), (0.0, 0.0, 0.0))

    def test_a_sure_loss_runs_out_of_money_for_a_lot_and_stops(self):
        r = self.m._n991_sim(20000, 6000, lambda rng: -0.30, 100, 40, 1)
        # 20000 -> 18200 -> ... each trade loses 1800; the year stops once the money is below one lot (6000)
        self.assertEqual(r['ruined'], 1.0)
        n = 0
        c = 20000.0
        while c >= 6000:
            c -= 1800
            n += 1
        self.assertAlmostEqual(r['median'], 20000 - 1800 * n, 6)
        self.assertEqual(r['half_lost'], 1.0)

    def test_same_inputs_same_answer_and_the_seed_matters(self):
        f = lambda rng: 0.5 if rng.random() < 0.4 else -0.3
        a = self.m._n991_sim(20000, 6500, f, 100, 300, 5)
        self.assertEqual(a, self.m._n991_sim(20000, 6500, f, 100, 300, 5))
        self.assertNotEqual(a['median'], self.m._n991_sim(20000, 6500, f, 100, 300, 6)['median'])

    def test_percentiles_are_ordered_and_shares_are_between_zero_and_one(self):
        r = self.m._n991_sim(20000, 6500, lambda rng: 0.5 if rng.random() < 0.45 else -0.3, 120, 400, 9)
        self.assertLessEqual(r['p10'], r['median'])
        self.assertLessEqual(r['median'], r['p90'])
        for k in ('below_start', 'half_lost', 'ruined'):
            self.assertTrue(0.0 <= r[k] <= 1.0)
        self.assertLessEqual(r['half_lost'], r['below_start'])

    def test_a_better_win_rate_is_never_worse(self):
        res = [self.m._n991_sim(20000, 6500, lambda rng, p=p: (0.5 if rng.random() < p else -0.3) - 0.02, 150, 600, 11) for p in (0.30, 0.40, 0.50)]
        self.assertGreaterEqual(res[1]['median'], res[0]['median'])
        self.assertGreaterEqual(res[2]['median'], res[1]['median'])
        self.assertLessEqual(res[2]['ruined'], res[1]['ruined'])
        self.assertLessEqual(res[1]['ruined'], res[0]['ruined'])

    def test_the_pace_follows_the_record_or_is_assumed(self):
        self.assertEqual(self.m._n991_pace([]), 100)
        self.many(10, spacing=1)
        trs = [t for t in self.m._n96_load() if not t['void']]
        self.assertEqual(self.m._n991_pace(trs[:5]), 100)                           # too few days: assumed
        self.assertTrue(20 <= self.m._n991_pace(trs) <= 250)

    def test_the_median_helper(self):
        self.assertIsNone(self.m._n991_median([]))
        self.assertEqual(self.m._n991_median([3, 1, 2]), 2)
        self.assertEqual(self.m._n991_median([4, 1, 2, 3]), 2.5)


# ===================================================================================================================
# 6. THE ANSWER: THE REPORT
# ===================================================================================================================
class TestReport(AnswerCase):
    def texts(self, capital=20000.0, paths=300):
        costs = self.m._n96_costs()
        trs = [t for t in self.m._n96_load(costs) if not t['void'] and t['mode'] == 'shadow']
        return self.m._n991_capital_texts(capital, trs, costs, paths)

    def test_three_messages_each_within_the_limit(self):
        self.many()
        t = self.texts()
        self.assertEqual(len(t), 3)
        for x in t:
            self.assertLessEqual(len(x), 3900)
            self.assertTrue(x.strip())

    def test_section_one_uses_the_real_lot_size_and_the_ledgers_premium(self):
        for e in (80.0, 100.0, 120.0, 90.0, 110.0, 100.0):
            self.add(trade(entry=e, exit=e * 1.1, days_ago=int(e) % 7 + 1))
        t = self.texts()[0]
        self.assertIn('One NIFTY lot is %d units' % self.m.lot_size('NIFTY'), t)
        self.assertIn('premium of about ₹100.00 (the middle of my own trades)', t)
        self.assertIn('one lot costs about ₹6,500', t)
        self.assertIn('buys at most 3 lots at a time', t)
        self.assertIn('a loss of about ₹1,950, which is 9.8% of ₹20,000', t)
        self.assertIn('1 to 2% of the money per trade (₹200 to ₹400)', t)

    def test_without_enough_trades_the_premium_is_assumed_and_says_so(self):
        t = self.texts()[0]
        self.assertIn('an assumed typical price', t)
        self.assertIn('no closed trades yet', t)

    def test_the_record_section_matches_the_ledger(self):
        self.many(22, win=0.5, seed=1)
        trs = [t for t in self.m._n96_load() if not t['void']]
        s = self.m._n96_stats(trs)
        t = self.texts()[0]
        self.assertIn('%d trades: %d won (%s' % (s['n'], s['wins'], self.m._n96_pct(s['win_rate'])), t)
        self.assertIn(self.m._n96_inr(s['net'], True), t)
        self.assertIn('Too few trades to call it skill', t)
        self.assertIn('must win about 37%', t)

    def test_enough_trades_change_the_wording(self):
        self.many(62, spacing=1)
        self.assertIn('the record starts to mean something', self.texts()[0])

    def test_the_simulation_lines(self):
        self.many()
        t = self.texts()[1]
        for label in ('30% win rate (below break-even)', '35% win rate (below break-even)', '40% win rate (about break-even)', '45% win rate (above break-even: needs a real edge'):
            self.assertIn(label, t)
        self.assertIn('like my record (its 22 results reused at random)', t)
        self.assertIn('300 simulated years for each line', t)
        self.assertIn('Reading it: even a trader who wins about 40% of the time', t)
        self.assertIn('luck', t)

    def test_no_record_row_without_enough_results(self):
        for e in (100.0, 90.0, 110.0):
            self.add(trade(entry=e, exit=e * 1.2))
        self.assertNotIn('like my record', self.texts()[1])

    def test_the_survival_and_honesty_section(self):
        self.many()
        t = self.texts()[2]
        for part in ('HOW I WOULD TRY TO SURVIVE', 'never add to a loser', 'daily loss limit of about 3% (₹600)', 'a fixed deposit', '“lab ready”', 'Plan on losing money', 'SEBI', '91%', '₹1.1 lakh',
                     'could not read SEBI\'s own page', 'Assumptions: premium', 'what if I risk 1% per trade'):
            self.assertIn(part, t, part)

    def test_it_says_no_ai_was_used_and_is_not_advice(self):
        self.many()
        t = self.texts()[0]
        self.assertIn('No AI was used', t)
        self.assertIn('not a promise and not advice', t)

    def test_deterministic(self):
        self.many()
        self.assertEqual(self.texts(), self.texts())

    def test_other_amounts(self):
        self.many()
        small = self.texts(3000.0)[0]
        self.assertIn('cannot even buy one lot', small)
        big = self.texts(200000.0)
        self.assertIn('₹2,00,000', big[0])
        self.assertIn('buys at most 32 lots', big[0].replace('buys at most 32 lots', 'buys at most 32 lots'))
        self.assertIn('₹2,00,000', big[1])

    def test_a_better_account_ruins_fewer_years(self):
        self.many()
        def ruined(capital):
            t = self.texts(capital, paths=400)[1]
            return int(re.search(r'40% win rate \(about break-even\): \d+% of years end below the start, \d+% lose half or more, (\d+)% are ruined', t).group(1))
        self.assertGreater(ruined(20000.0), ruined(100000.0))

    def test_the_pace_label_is_honest(self):
        self.many(22, spacing=2)
        self.assertIn('about the pace my agent has kept', self.texts()[1])
        self.log.clear()
        self.m._n96_q('DELETE FROM ledger96_trade', write=True)
        self.add(trade(), trade(entry=90, exit=95))
        self.assertIn('an assumed pace', self.texts()[1])

    def test_virtual_trades_only(self):
        self.many(22)
        self.add(trade(entry=70.0, exit=500.0, mode='live', days_ago=1))
        base_t = self.texts()
        costs = self.m._n96_costs()
        shadow = [t for t in self.m._n96_load(costs) if not t['void'] and t['mode'] == 'shadow']
        self.assertEqual(base_t, self.m._n991_capital_texts(20000.0, shadow, costs, 300))


# ===================================================================================================================
# 7. THE FRONT DOOR
# ===================================================================================================================
class TestFrontDoor(AnswerCase):
    def test_the_owners_question_is_answered_from_the_record_with_no_ai(self):
        self.many()
        self.start(self.m, 'ask_ai', lambda *a, **k: (_ for _ in ()).throw(AssertionError('the AI must not be called')))
        n = len(self.sent)
        self.m.handle(self.msg(SHOT))
        out = [t for c, t in self.sent[n:] if c == OWNER_ID]
        self.assertEqual(len(out), 4)                                           # one line to say it is working, then the three messages
        self.assertIn('no AI needed', out[0])
        self.assertIn('₹20,000 IN NIFTY OPTIONS FOR ONE YEAR', out[1])
        self.assertIn('A YEAR OF ABOUT', out[2])
        self.assertIn('HOW I WOULD TRY TO SURVIVE', out[3])
        self.assertEqual(self.passed, [])
        self.assertEqual(self.m._N991_STATS['plans'], 1)
        self.assertEqual(self.broker_calls, [])

    def test_the_amount_in_the_question_is_the_amount_in_the_answer(self):
        self.m.handle(self.msg('suppose you have 50000 rupees for options trading, how will you survive and what return in a year?'))
        self.assertIn('₹50,000 IN NIFTY OPTIONS', self.texts_to_owner())

    def test_a_job_that_fails_says_so_plainly(self):
        self.start(self.m, '_n991_capital_texts', lambda *a, **k: (_ for _ in ()).throw(ValueError('x')))
        self.m.handle(self.msg(SHOT))
        self.assertIn('could not finish that analysis', self.texts_to_owner())
        self.assertEqual(self.m._N991_STATS['errors'], 1)

    def test_other_trading_messages_go_on_to_the_older_handlers(self):
        for q in ('research the NIFTY option chain and show OI and PCR for this expiry', 'show my paper trading journal', 'suppose you trade nifty options how will you survive', 'how is the paper agent doing',
                  'what is the nifty today', 'buy 1 lot nifty', 'hello nemo', 'what is photosynthesis'):
            self.passed.clear()
            n = len(self.sent)
            self.m.handle(self.msg(q))
            plan = [t for c, t in self.sent[n:] if 'IN NIFTY OPTIONS FOR ONE YEAR' in t]
            self.assertEqual(plan, [], q)
            if q in ('how is the paper agent doing',):
                continue                                                         # the ledger answers this one
            self.assertEqual(len(self.passed), 1, q)

    def test_a_guest_is_not_served(self):
        self.passed.clear()
        n = len(self.sent)
        self.m.handle(self.guest(SHOT))
        self.assertEqual(len(self.passed), 1)
        self.assertEqual([t for c, t in self.sent[n:] if 'IN NIFTY OPTIONS' in t], [])

    def test_a_picture_or_file_or_group_is_not_a_question(self):
        for extra in ({'document': {'file_id': 'x'}}, {'photo': [{'file_id': 'y'}]}):
            self.passed.clear()
            self.m.handle(self.msg(SHOT, **extra))
            self.assertEqual(len(self.passed), 1)
        self.passed.clear()
        self.m.handle({'chat': {'id': OWNER_ID, 'type': 'group'}, 'from': {'id': OWNER_ID}, 'message_id': 4, 'text': SHOT})
        self.assertEqual(len(self.passed), 1)

    def test_the_brain_fallback_switch(self):
        out = self.say('brain fallback')
        self.assertIn('BRAIN FALLBACK: ON', out)
        out = self.say('brain fallback off')
        self.assertIn('Saved.', out)
        self.assertIn('BRAIN FALLBACK: OFF', out)
        self.assertEqual(self.kv['n991_fallback'], 'off')
        self.assertIn('BRAIN FALLBACK: ON', self.say('Brain fallback ON'))
        self.assertEqual(self.kv['n991_fallback'], 'on')
        self.assertEqual(self.m._N991_STATS['switch'], 2)

    def test_the_switch_is_owner_only(self):
        self.passed.clear()
        self.m.handle(self.guest('brain fallback off'))
        self.assertEqual(len(self.passed), 1)
        self.assertNotIn('n991_fallback', self.kv)


# ===================================================================================================================
# 8. WIRING AND STRUCTURE
# ===================================================================================================================
class TestWiringAndStructure(AnswerCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass() if hasattr(super(), 'setUpClass') else None
        cls.src = v991_source()
        cls.tree = ast.parse(cls.src)

    def test_capabilities_status_and_regression_rows(self):
        m = self.m
        self.assertIn('Answer 99.1:', m._n82_capabilities())
        self.assertIn('ANSWER 99.1: fallback ON', m._n83_status_text(OWNER_ID))
        rows = m._n991_regression_rows()
        self.assertEqual(len(rows), 6)
        self.assertEqual([r['name'] for r in rows if not r['ok']], [])
        self.assertTrue(all(r['name'].startswith('v991-') for r in rows))
        self.assertIsNot(m.prime_regression_suite, m._N991_REG_PREV)

    def test_every_replaced_function_keeps_the_old_one(self):
        for fn, prev in (('_n72_decide', '_N991_DECIDE_PREV'), ('_n73_core_reply', '_N991_CORE_PREV'), ('_n75_trade_task', '_N991_TRADE_PREV'), ('handle', '_N991_HANDLE_PREV'),
                         ('_n83_status_text', '_N991_STATUS_PREV'), ('_n82_capabilities', '_N991_CAPS_PREV'), ('prime_regression_suite', '_N991_REG_PREV')):
            self.assertIn('%s = %s\n' % (prev, fn), self.src, fn)

    def test_all_layer_names_use_the_v991_prefix(self):
        defined = {n.name for n in self.tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        allowed = ('handle', '_n82_capabilities', '_n83_status_text', 'prime_regression_suite', '_n72_decide', '_n73_core_reply', '_n75_trade_task', '_n96_inr1_rs')
        odd = [d for d in defined if not (d.startswith('_n991_') or d.startswith('_N991')) and d not in allowed]
        self.assertEqual(odd, [])

    def test_the_layer_never_touches_orders_the_agent_the_guards_or_credentials(self):
        src = self.src
        for word in ('fyers_place', '_order_send', 'request_order', 'save_secret', 'save_data', 'requests.', 'subprocess', 'os.system', 'eval(', 'exec(', 'AUTOLOG.append', 'del AUTOLOG', 'BROKER', 'WEBCFG', '_n81_paused', 'mm_locked'):
            self.assertNotIn(word, src, word)
        self.assertIsNone(re.search(r'\bAUTO\s*\[[^\]]+\]\s*=[^=]', src))
        self.assertIsNone(re.search(r'\bAUTO\s*\.\s*(?:update|pop|clear|setdefault)', src))
        reads = set(re.findall(r"\bAUTO(?:\.get|\[)\(?['\"](\w+)", src))
        self.assertLessEqual(reads, {'maxtrades'})

    def test_the_layer_calls_no_ai_and_no_network(self):
        names = {c.func.id for c in ast.walk(self.tree) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
        self.assertNotIn('ask_ai', names)
        self.assertEqual({n for n in names if n.startswith(('fyers_', '_n75_quote', 'live_ltp', 'groq_', 'gemini_', 'claude_', '_n73_request'))}, set())

    def test_the_only_state_written_is_the_one_switch(self):
        self.assertEqual(sorted(set(re.findall(r"_n36_kv_set\('(\w+)'", self.src))), ['n991_fallback'])

    def test_the_protection_list_for_live_self_edit_names_the_new_prefix(self):
        self.assertIn("'_n99_','_n991_',", bot_source())

    def test_version_and_docstring(self):
        self.assertGreaterEqual(float(self.m.VERSION), 99.1)
        self.assertIn('v99.1 - ANSWER', bot_source()[:3000])
        self.assertIn('v99.0 - LAB', bot_source()[:20000])

    def test_no_secret_shaped_text_in_the_layer(self):
        for rx in (r'AIza[0-9A-Za-z_-]{20,}', r'sk-[A-Za-z0-9]{20,}', r'gh[pousr]_[A-Za-z0-9]{20,}', r'\b\d{8,10}:[A-Za-z0-9_-]{30,}\b', r'-----BEGIN [A-Z ]*PRIVATE KEY'):
            self.assertIsNone(re.search(rx, self.src), rx)

    def test_stats_start_at_zero(self):
        self.assertTrue(all(v == 0 for v in self.m._N991_STATS.values()))


if __name__ == '__main__':
    unittest.main()
