"""Candor 86, findings 4-6: research routing, ONE shared deadline, honest verification, plus structural and mutation checks.

Synthetic data only; a scripted fake AI provider; a fake clock (the "provider" advances it instead of sleeping, so deadline behaviour is exact
and instant); no network, no real keys, no trades, no paid calls.

    NEMO_FILE=/path/to/nemotron_bot.py python -m unittest tests.test_candor86_runtime -v
"""
import ast
import json
import os
import random
import re
import threading
import time
import unittest
from unittest import mock

from tests import test_cortex83 as base
from tests import test_candor86 as c86
from tests.test_cortex83 import answer_stage, scout, clerk, checker

PRICING = 'Compare Claude and OpenRouter API pricing.'
SOURCE_PATH = base.NEMO_FILE


def setUpModule():
    c86.setUpModule()


def hits(*urls, body='Claude and OpenRouter API pricing per million tokens, input and output'):
    return [{'title': 'Pricing %d' % i, 'href': u, 'body': body} for i, u in enumerate(urls)]


def two_sites():
    return hits('https://docs.example/claude-pricing', 'https://openrouter.example/models')


def answer_of(calls):
    return [c for c in calls if answer_stage(c['messages'])]


class RuntimeCase(c86.CandorCase):
    """CandorCase plus a helper to read the last receipt."""

    def receipt(self):
        with self.m._N83_LOCK:
            return self.m._N83_LAST[self.cid]

    def chat(self, text, **extra):
        return self.m._n83_chat(self.msg(text, **extra))

    def searches(self, rows=None, boom=None):
        """Patch web_search; returns the list of queries it was asked."""
        asked = []

        def ws(q):
            asked.append(q)
            if boom:
                raise boom
            return rows if rows is not None else []
        p = mock.patch.object(self.m, 'web_search', ws)
        p.start()
        self.patches.append(p)
        return asked


# ===================================================================================================================
# 4. RESEARCH ROUTING
# ===================================================================================================================
class TestResearchSignals(RuntimeCase):
    NEEDED = ('Compare Claude and OpenRouter API pricing.', 'What is the latest iPhone price in India?', 'bitcoin price today',
              'Is Gemini 3 available in India right now?', 'weather in Surat today', 'Compare Zerodha and Groww brokerage charges',
              'how much does Claude Max cost per month', 'latest news about OpenAI', 'who won the match yesterday', 'OpenRouter pricing')
    NOT_NEEDED = ('tell me a joke about cats', 'explain how compound interest works', 'write a poem about rain', 'thanks', 'translate good morning to Hindi',
                  'summarise our chat so far', 'hi', 'how are you', 'what is the capital of France', 'remind me to call Rahul at 5pm',
                  'fix this python function', 'how do I reset my router', 'compare my showroom sales with last month')

    def test_the_reported_question_is_classified_as_needing_current_information(self):
        sig = self.m._n86_research_signals(PRICING)
        self.assertEqual(sig['level'], 'needed')
        self.assertEqual(sig['entities'], ['claude', 'openrouter'])
        self.assertTrue(sig['time_signal'])
        self.assertFalse(self.m._n83_may_need_tools(PRICING), 'this is exactly the question the older keyword gate missed')

    def test_questions_that_need_the_web(self):
        for text in self.NEEDED:
            self.assertEqual(self.m._n86_research_signals(text)['level'], 'needed', text)

    def test_questions_that_do_not_need_the_web_stay_fast(self):
        for text in self.NOT_NEEDED:
            self.assertEqual(self.m._n86_research_signals(text)['level'], 'none', text)

    def test_judgement_calls_go_to_the_scout_instead_of_being_forced(self):
        for text in ('which is better, Notion or Obsidian?', 'Which model should I use for coding, Claude or GPT?', 'what changed in Python 3.14',
                     'what is the difference between Claude and ChatGPT'):
            self.assertEqual(self.m._n86_research_signals(text)['level'], 'maybe', text)

    def test_signals_are_deterministic_and_make_no_model_call(self):
        a = self.m._n86_research_signals(PRICING)
        b = self.m._n86_research_signals(PRICING)
        self.assertEqual(a, b)
        self.assertEqual(self.fake.calls, [])

    def test_planned_query_is_neutral_short_and_dated(self):
        q = self.m._n86_queries(self.cid, PRICING)
        self.assertEqual(len(q), 1)
        self.assertLessEqual(len(q[0]), 100)
        self.assertIn('Claude', q[0])
        self.assertIn('OpenRouter', q[0])
        self.assertRegex(q[0], r'\b20\d\d\b')

    def test_a_query_that_could_leak_something_is_never_planned(self):
        m = self.m
        q = m._n86_queries(self.cid, 'latest price for john@example.com today')
        self.assertEqual(len(q), 1)
        self.assertNotIn('john', q[0].lower(), 'an e-mail address is dropped from the outgoing query, not sent')
        self.assertNotIn('example.com', q[0].lower())
        self.assertEqual(m._n86_queries(self.cid, 'latest price of 9876543210 today'), [])
        self.assertEqual(m._n86_queries(self.cid, 'my password is ' + c86.SECRET + ' price today'), [])
        m._n35_set_fact(self.cid, 'home_address', '14 Lotus Park Colony Surat', 'owner-explicit')
        self.assertEqual(m._n86_queries(self.cid, 'latest news near 14 Lotus Park Colony Surat'), [], 'a stored address never goes out in a web query')


class TestResearchTurns(RuntimeCase):
    def test_the_reported_question_is_researched_with_one_model_call(self):
        asked = self.searches(two_sites())
        self.fake.when(lambda r, t: True, 'Both publish per-token prices; see the cited pages.')
        out = self.chat(PRICING)
        self.assertTrue(out['ok'])
        self.assertEqual(len(asked), 1)
        self.assertEqual(self.fake.of('tool scout'), [], 'planned in code: no scout call')
        self.assertEqual(len(self.fake.calls), 1, 'one model call in total: the answer')
        self.assertIn('EVIDENCE GATHERED', json.dumps(self.fake.calls[0]['messages']))
        self.assertIn('https://docs.example/claude-pricing', out['text'])
        self.assertNotIn('Research:', out['text'], 'no warning when the evidence is adequate')
        self.assertEqual(self.receipt()['checks']['research']['status'], 'ok')
        self.assertEqual(self.m._N86_STATS['research_forced'], 1)
        self.assertEqual(self.m._N86_STATS['scout_skipped'], 1)

    def test_when_the_search_fails_the_answer_says_so(self):
        self.searches(boom=RuntimeError('network down'))
        self.fake.when(lambda r, t: True, 'Claude and OpenRouter both charge per million tokens.')
        out = self.chat(PRICING)
        self.assertIn('⚠️ Research: I tried to look this up but could not get usable sources', out['text'])
        self.assertIn('may be out of date', out['text'])
        prompt = json.dumps(self.fake.calls[0]['messages'])
        self.assertIn('RESEARCH STATUS: FAILED', prompt)
        self.assertIn('You MUST tell the owner plainly', prompt)
        self.assertEqual(self.receipt()['checks']['research']['status'], 'failed')
        self.assertIn('Research (current information): FAILED', self.m._n83_why_text(self.cid))
        self.assertEqual(self.m._N86_STATS['research_failed'], 1)
        # the failure reason names the kind of problem, never internals
        self.assertNotIn('network down', out['text'])

    def test_an_empty_result_is_a_failure_not_silence(self):
        self.searches([])
        self.fake.when(lambda r, t: True, 'I think they both bill per token.')
        out = self.chat(PRICING)
        self.assertIn('could not get usable sources', out['text'])
        self.assertIn('nothing usable', out['text'])

    def test_figures_in_a_failed_research_answer_are_called_unverified(self):
        self.searches(boom=RuntimeError('x'))
        self.fake.when(lambda r, t: True, 'Claude costs about $3 per million tokens and OpenRouter adds 5%.')
        out = self.chat(PRICING)
        self.assertIn('treat any prices or figures as unverified', out['text'])

    def test_thin_evidence_is_called_thin(self):
        self.searches(hits('https://only.example/page'))
        self.fake.when(lambda r, t: True, 'One page mentions both.')
        out = self.chat(PRICING)
        self.assertIn('⚠️ Research: evidence was thin', out['text'])
        self.assertIn('only 1 usable result', out['text'])
        self.assertIn('RESEARCH STATUS: THIN', json.dumps(self.fake.calls[0]['messages']))
        self.assertEqual(self.receipt()['checks']['research']['status'], 'thin')
        self.assertEqual(self.m._N86_STATS['research_thin'], 1)

    def test_evidence_that_never_mentions_one_of_the_products_is_thin_and_triggers_one_more_search(self):
        asked = self.searches(hits('https://a.example/x', 'https://b.example/y', body='Claude API pricing per million tokens'))
        self.fake.when(lambda r, t: True, 'Only Claude pricing was found.')
        out = self.chat(PRICING)
        self.assertEqual(len(asked), 2, 'a second, targeted search for the missing product')
        self.assertIn('openrouter', asked[1].lower())
        self.assertIn('no result mentions openrouter', out['text'])

    def test_simple_chat_stays_fast_and_cheap(self):
        asked = self.searches(two_sites())
        self.fake.when(lambda r, t: True, 'Why did the cat sit on the laptop? To keep an eye on the mouse.')
        out = self.chat('tell me a joke about cats')
        self.assertTrue(out['ok'])
        self.assertEqual(asked, [])
        self.assertEqual(len(self.fake.calls), 1)
        self.assertEqual(self.receipt()['checks']['research']['status'], 'not_needed')
        self.assertNotIn('Research:', out['text'])

    def test_a_mixed_question_uses_the_scout_and_still_gets_the_search(self):
        asked = self.searches(two_sites())

        def scout_reply(role, text, messages):
            if 'Evidence so far' in text:
                return json.dumps({'need': []})
            return json.dumps({'need': [{'tool': 'calculate', 'input': '1250*18/100'}]})       # the scout forgot the web lookup
        self.fake.when(lambda r, t: scout(t), scout_reply)
        self.fake.when(lambda r, t: True, '18% of 1250 is 225; both providers publish prices.')
        out = self.chat('Compare Claude and OpenRouter API pricing and what is 18% of 1250?')
        self.assertEqual(len(asked), 1, 'the search the question needs is done even though the scout skipped it')
        self.assertEqual(len(self.fake.of('tool scout')), 1)
        self.assertIn('225', out['text'])
        tools = [t['tool'] for t in self.receipt()['tools']]
        self.assertIn('search', tools)
        self.assertIn('calculate', tools)

    def test_the_scout_still_decides_judgement_questions(self):
        asked = self.searches(two_sites())
        self.fake.when(lambda r, t: scout(t), json.dumps({'need': []}))
        self.fake.when(lambda r, t: True, 'Notion suits notes, Obsidian suits local files.')
        self.chat('which is better, Notion or Obsidian?')
        self.assertEqual(len(self.fake.of('tool scout')), 1)
        self.assertEqual(asked, [], 'a maybe is not forced: the scout said no search')

    def test_nothing_is_searched_when_the_owner_switched_tools_off(self):
        asked = self.searches(two_sites())
        self.m._n83_set_flag(self.cid, 'tools', False)
        self.fake.when(lambda r, t: True, 'From general knowledge only.')
        out = self.chat(PRICING)
        self.assertEqual(asked, [])
        self.assertEqual(len(self.fake.calls), 1)
        self.assertNotIn('Research:', out['text'], 'tools were switched off on purpose; this is not a research failure')

    def test_a_search_cannot_be_forced_into_a_query_the_guard_rejects(self):
        asked = self.searches(two_sites())
        self.fake.when(lambda r, t: True, 'ok')
        out = self.chat('What is the latest price for account 9876543210 plan today')
        self.assertEqual(asked, [])
        self.assertIn('did not complete a lookup', out['text'], 'and the answer says the lookup was not done')

    def test_no_time_for_research_is_stated(self):
        self.searches(two_sites())
        self.m._n86_kv_set('turn_budget', 30)
        self.fake.when(lambda r, t: True, 'From general knowledge.')
        clock = c86.Clock()
        ns = clock.namespace()
        for name in ('_n86_time', '_n83_time'):
            p = mock.patch.object(self.m, name, ns)
            p.start()
            self.patches.append(p)
        with mock.patch.object(self.m, '_n86_research_signals', lambda t: {'level': 'needed', 'score': 9, 'reasons': [], 'entities': ['claude'], 'time_signal': True}):
            scope = self.m._N86Scope(total=30)
            with scope:
                clock.advance(10)                       # 20 s left: less than the 25 s the answer reserves
                out = self.m._n83_chat(self.msg(PRICING))
        self.assertTrue(out['ok'])
        self.assertIn('did not complete a lookup', out['text'])
        self.assertIn('not enough time left', out['text'])


# ===================================================================================================================
# 5. ONE SHARED DEADLINE, BOUNDED BACKGROUND WORK, FEWER MODEL CALLS
# ===================================================================================================================
class DeadlineCase(RuntimeCase):
    def setUp(self):
        super().setUp()
        self.clock = c86.Clock()
        ns = self.clock.namespace()
        for name in ('_n86_time', '_n83_time'):
            p = mock.patch.object(self.m, name, ns)
            p.start()
            self.patches.append(p)
        self.asked = self.searches(two_sites())

    def slow(self, seconds, reply):
        """A provider that spends `seconds` of fake time and then answers (or raises)."""
        def f(role, text, messages):
            self.clock.advance(seconds)
            return reply(role, text, messages) if callable(reply) else reply
        return f

    def started(self):
        return self.clock.t


class TestSharedDeadline(DeadlineCase):
    def test_a_late_failure_does_not_start_a_second_full_timeout(self):
        t0 = self.started()
        self.fake.when(lambda r, t: True, self.slow(85, self.m._N73Error('http_500')))
        out = self.m._n80_chat(self.msg('what is the capital of France?'))
        self.assertTrue(out['ok'])
        self.assertIn('ran out of my 100-second limit', out['text'])
        self.assertTrue(out['text'].startswith('⏱'))
        self.assertLessEqual(self.clock.t - t0, 100)
        self.assertEqual(len(self.fake.calls), 1, 'no fallback call: the budget is spent')
        self.assertEqual(self.m._N86_STATS['budget_exhausted'], 1)
        self.assertEqual(self.m.HISTORY.get(self.cid, []), [], 'an answer that was never produced is not stored as a conversation turn')

    def test_a_failure_with_time_left_falls_back_inside_the_same_budget(self):
        t0 = self.started()
        self.fake.when(lambda r, t: answer_stage_text(t), self.slow(30, self.m._N73Error('http_500')))
        self.fake.when(lambda r, t: True, self.slow(10, 'The capital of France is Paris.'))
        out = self.m._n80_chat(self.msg('what is the capital of France?'))
        self.assertIn('Paris', out['text'])
        self.assertEqual(len(self.fake.calls), 2)
        legacy = self.fake.calls[1]
        self.assertLessEqual(legacy['timeout'], 70.0001, 'the fallback may only use what is left of the same 100 s')
        self.assertLessEqual(self.clock.t - t0, 100)

    def test_every_call_gets_a_timeout_no_larger_than_what_is_left(self):
        for seed in range(1, 6):
            self.fake.calls.clear()
            self.fake.rules.clear()
            rng = random.Random(seed)
            self.fake.when(lambda r, t: True, lambda role, text, messages: self.slow(rng.uniform(1, 40), 'fine answer')(role, text, messages))
            start = self.clock.t
            self.m._n80_chat(self.msg('what is the capital of France?'))
            self.assertLessEqual(self.clock.t - start, 100.001)
            for call in self.fake.calls:
                self.assertLessEqual(call['timeout'], 100.0)

    def test_property_total_time_is_bounded_for_random_latencies_and_failures(self):
        """Honest providers (they stop at the timeout they were given) can never push a turn past the shared limit, whatever fails and when."""
        m = self.m
        outcomes = {'ok': 0, 'timeout_text': 0, 'other': 0}
        for seed in range(150):
            rng = random.Random(seed)
            self.fake.calls.clear()
            self.fake.rules.clear()
            self.m._N86_TLS.budget = None
            total = rng.choice([30, 45, 60, 100])
            m._n86_kv_set('turn_budget', total)

            def provider(role, text, messages, rng=rng):
                latency = rng.choice([0.5, 8, 30, 45, 70, 70, 120])
                timeout = self.fake.calls[-1]['timeout']
                if rng.random() < 0.3:
                    self.clock.advance(min(latency, timeout))
                    raise m._N73Error(rng.choice(['http_500', 'timeout', 'brain_busy']))
                if latency > timeout:
                    self.clock.advance(timeout)
                    raise m._N73Error('timeout')
                self.clock.advance(latency)
                if scout(text):
                    return json.dumps({'need': [{'tool': 'calculate', 'input': '2+2'}]}) if 'Evidence so far' not in text else json.dumps({'need': []})
                if checker(text):
                    return json.dumps({'issues': []})
                return 'A reasonable and fairly complete answer to the question. ' * 6
            self.fake.when(lambda r, t: True, provider)
            question = rng.choice([PRICING, 'what is 18% of 1250 and the weather today?', 'Please analyse my budget and recommend what to do next',
                                   'what is the capital of France?', 'thanks!'])
            start = self.clock.t
            out = m._n80_chat(self.msg(question))
            elapsed = self.clock.t - start
            self.assertLessEqual(elapsed, total + 0.001, 'seed %d: %r took %.1fs of a %ds limit' % (seed, question, elapsed, total))
            self.assertLessEqual(len(self.fake.calls), 8, 'seed %d: model calls are bounded' % seed)
            for call in self.fake.calls:
                self.assertLessEqual(call['timeout'], total + 0.001, 'seed %d' % seed)
            self.assertTrue(out is None or isinstance(out, dict), 'seed %d' % seed)
            outcomes['timeout_text' if out and out.get('text', '').startswith('⏱') else 'ok' if out else 'other'] += 1
        self.assertGreater(outcomes['ok'], 10)
        self.assertGreater(m._N86_STATS['budget_exhausted'], 3, 'the generator really does exhaust budgets: ' + str(outcomes))

    def test_exhausted_after_planning_the_answer_is_not_started(self):
        self.fake.when(lambda r, t: scout(t), self.slow(92, json.dumps({'need': []})))
        self.fake.when(lambda r, t: True, 'should never be asked')
        out = self.m._n80_chat(self.msg('how many days until 25 December 2026?'))
        self.assertIn('before I could start answering', out['text'])
        self.assertEqual(answer_of(self.fake.calls), [])
        self.assertEqual(len(self.fake.calls), 1)
        self.assertIn('Nothing was changed', out['text'])
        self.assertIn('set your answer time limit', out['text'])

    def test_a_slow_scout_cannot_starve_the_answer(self):
        def scout_slow(role, text, messages):
            timeout = self.fake.calls[-1]['timeout']
            self.assertLessEqual(timeout, 30.0, 'planning has its own cap')
            self.clock.advance(timeout)
            raise self.m._N73Error('timeout')
        self.fake.when(lambda r, t: scout(t), scout_slow)
        self.fake.when(lambda r, t: True, 'It is a Saturday.')
        out = self.m._n80_chat(self.msg('what day of the week is 3 November 2029?'))
        self.assertEqual(out['text'].split('\n')[0], 'It is a Saturday.')
        final = answer_of(self.fake.calls)[0]
        self.assertGreaterEqual(final['timeout'], 10.0)
        self.assertLessEqual(final['timeout'], 60.0)

    def test_a_very_short_limit_still_answers_from_knowledge(self):
        self.m._n86_kv_set('turn_budget', 30)
        self.fake.when(lambda r, t: True, 'Paris.')
        out = self.m._n80_chat(self.msg('what is the capital of France? and how many days until 25 December 2026?'))
        self.assertEqual(self.fake.of('tool scout'), [], 'a 30 s limit leaves no room for planning, so the answer comes first')
        self.assertIn('Paris', out['text'])

    def test_the_older_fallback_refuses_when_the_budget_is_spent(self):
        m = self.m
        seen = []
        with mock.patch.object(m, '_N86_CORE_PREV', lambda *a, **k: seen.append(k) or 'legacy answer'):
            with m._N86Scope(total=50):
                self.clock.advance(48)
                text = m._n73_core_reply(self.cid, 'hello', [{'role': 'user', 'content': 'hello'}])
                self.assertIn('ran out of my 50-second limit', text)
                with self.assertRaises(m._N73Error) as ctx:
                    m._n73_core_reply(self.cid, 'hello', [], raw=True)
                self.assertEqual(ctx.exception.code, 'time_budget_exhausted')
            self.assertEqual(seen, [], 'no provider call once the budget is spent')
            with m._N86Scope(total=100):
                self.clock.advance(60)
                m._n73_core_reply(self.cid, 'hello', [], timeout=60)
            self.assertLessEqual(seen[-1]['timeout'], 40.0001, 'a 60 s request is clamped to the 40 s that are left')
            m._n73_core_reply(self.cid, 'hello', [], timeout=60)           # outside any turn: untouched
            self.assertEqual(seen[-1]['timeout'], 60)

    def test_the_call_wrapper_clamps_and_refuses(self):
        m = self.m
        with m._N86Scope(total=50):
            self.clock.advance(30)
            m._n83_call(self.cid, 'chat', 'hello', 60)
            self.assertLessEqual(self.fake.calls[-1]['timeout'], 20.0001)
            m._n83_call(self.cid, 'chat', 'hello', 60, deadline=self.clock.monotonic() + 8)
            self.assertLessEqual(self.fake.calls[-1]['timeout'], 8.0001, 'an explicit earlier deadline still wins')
            n = len(self.fake.calls)
            self.clock.advance(18)
            with self.assertRaises(m._N73Error) as ctx:
                m._n83_call(self.cid, 'chat', 'hello', 60)
            self.assertEqual(ctx.exception.code, 'time_budget_exhausted')
            self.assertEqual(len(self.fake.calls), n)

    def test_nested_scopes_share_one_budget_and_other_threads_do_not_see_it(self):
        m = self.m
        with m._N86Scope(total=90) as outer:
            with m._N86Scope(total=10) as inner:
                self.assertIs(outer, inner)
                self.assertEqual(inner.total, 90)
            self.assertIs(m._n86_budget(), outer)
            seen = []
            t = threading.Thread(target=lambda: seen.append(m._n86_budget()))
            t.start()
            t.join()
            self.assertEqual(seen, [None])
        self.assertIsNone(m._n86_budget())

    def test_the_budget_counts_model_calls(self):
        self.fake.when(lambda r, t: True, 'A longer answer about budgets and savings. ' * 8)
        self.m._n83_chat(self.msg('Please analyse my budget and recommend what to do next'))
        self.assertEqual(self.receipt()['checks']['calls'], len([c for c in self.fake.calls if not clerk(c['text'])]), 'every model call of the turn is counted, background learning is not')

    def test_the_time_limit_can_be_changed_in_plain_language(self):
        self.say('set your answer time limit to 60 seconds')
        self.assertIn('60 seconds', self.last())
        self.assertEqual(self.m._n86_turn_total(), 60.0)
        self.say('what is your time limit?')
        self.assertIn('60 seconds', self.last())
        self.say('set your answer time limit to 5 seconds')
        self.assertIn('between 30 and 240', self.last())
        self.assertEqual(self.m._n86_turn_total(), 60.0)
        self.fake.when(lambda r, t: True, 'Paris.')
        self.chat('what is the capital of France?')
        self.assertEqual(self.receipt()['checks']['budget']['total'], 60)
        self.assertIn('of a 60s limit', self.m._n83_why_text(self.cid))

    def test_only_the_owner_can_change_the_limit(self):
        self.m.OWNER['id'] = 999
        self.fake.when(lambda r, t: True, 'ok')
        self.say('set your answer time limit to 60 seconds')
        self.assertEqual(self.m._n86_turn_total(), 100.0)


def answer_stage_text(text):
    return 'chief of staff' in text


class TestBoundedWork(DeadlineCase):
    def test_search_concurrency_is_capped_and_a_hung_search_keeps_its_slot(self):
        m = self.m
        gate, started = threading.Event(), []

        def slow_search(q):
            started.append(q)
            gate.wait(20)
            return two_sites()
        results, errors = [], []

        def run(i):
            try:
                results.append(m._n83_tool_search(self.cid, 'claude pricing %d' % i))
            except Exception as exc:
                errors.append(str(exc))
        with mock.patch.object(m, 'web_search', slow_search):
            workers = [threading.Thread(target=run, args=(i,)) for i in range(m._N86_SEARCH_MAX_INFLIGHT)]
            for w in workers:
                w.start()
            deadline = time.time() + 5
            while time.time() < deadline and m._n86_search_state()['inflight'] < m._N86_SEARCH_MAX_INFLIGHT:
                time.sleep(0.01)
            self.assertEqual(m._n86_search_state()['inflight'], m._N86_SEARCH_MAX_INFLIGHT)
            with self.assertRaises(RuntimeError) as ctx:
                m._n83_tool_search(self.cid, 'claude pricing extra')
            self.assertIn('capacity is busy', str(ctx.exception))
            self.assertLessEqual(len(started), m._N86_SEARCH_WORKERS, 'only the pool size ever runs at once')
            gate.set()
            for w in workers:
                w.join(10)
        self.assertEqual(len(results), m._N86_SEARCH_MAX_INFLIGHT)
        self.assertEqual(m._n86_search_state()['inflight'], 0)
        self.assertGreaterEqual(m._N86_STATS['search_busy'], 1)

    def test_three_timeouts_in_a_minute_stop_searching_for_a_while(self):
        m = self.m
        now = time.time()
        with m._N86_LOCK:
            m._N86_SEARCH['timeouts'] = [now - 5, now - 3, now - 1]
        called = []
        with mock.patch.object(m, 'web_search', lambda q: called.append(q) or two_sites()):
            with self.assertRaises(RuntimeError) as ctx:
                m._n83_tool_search(self.cid, 'claude pricing')
        self.assertIn('temporarily unavailable', str(ctx.exception))
        self.assertEqual(called, [])
        with m._N86_LOCK:
            m._N86_SEARCH['timeouts'] = [now - 100, now - 90, now - 80]          # old timeouts expire
        with mock.patch.object(m, 'web_search', lambda q: two_sites()):
            self.assertEqual(len(m._n83_tool_search(self.cid, 'claude pricing')), 2)

    def test_a_search_that_hangs_times_out_with_a_clear_reason(self):
        m = self.m
        release = threading.Event()
        with mock.patch.object(m, '_N86_SEARCH_TIMEOUT', 2.0), mock.patch.object(m, 'web_search', lambda q: release.wait(10) or []):
            t0 = time.time()
            with self.assertRaises(RuntimeError) as ctx:
                m._n83_tool_search(self.cid, 'claude pricing')
            self.assertLess(time.time() - t0, 6)
            release.set()
        self.assertIn('timed out after 2 seconds', str(ctx.exception))
        self.assertEqual(m._N86_STATS['search_timeouts'], 1)

    def test_search_needs_the_budget_it_asks_for(self):
        m = self.m
        with m._N86Scope(total=30):
            self.clock.advance(26)
            with self.assertRaises(RuntimeError) as ctx:
                m._n83_tool_search(self.cid, 'claude pricing')
        self.assertIn('no time left', str(ctx.exception))

    def test_search_results_are_cleaned_and_bounded(self):
        rows = [{'title': 'A\x00title', 'href': 'https://ok.example/a', 'body': 'x' * 900}, {'title': 'bad', 'href': 'javascript:alert(1)', 'body': 'y'},
                {'title': 'ftp', 'href': 'ftp://x.example/', 'body': 'z'}] + [{'title': 'n%d' % i, 'href': 'https://n%d.example/' % i, 'body': 'b'} for i in range(8)]
        with mock.patch.object(self.m, 'web_search', lambda q: rows):
            out = self.m._n83_tool_search(self.cid, 'claude pricing')
        self.assertLessEqual(len(out), 5)
        self.assertTrue(all(r['url'].startswith('https://') for r in out))
        self.assertLessEqual(len(out[0]['excerpt']), 350)
        self.assertNotIn('\x00', out[0]['title'])

    def test_a_stuck_tool_cannot_stall_the_turn(self):
        m = self.m
        release = threading.Event()
        needs = [{'tool': 'search', 'input': 'claude pricing'}, {'tool': 'date', 'input': 'today'}]
        with m._N86Scope(total=30):
            self.clock.advance(22)                                       # 8 s left: the wait is clamped to 3 s of real time
            with mock.patch.object(m, '_n83_run_one', lambda cid, n, allow: release.wait(10) or {'tool': n['tool'], 'input': n['input'], 'ok': True, 'output': 'x', 'urls': [], 'rows': []}):
                t0 = time.time()
                evidence = m._n83_run_tools(self.cid, needs, True)
                took = time.time() - t0
        release.set()
        self.assertLess(took, 8)
        self.assertTrue(all(not e['ok'] and 'did not finish in time' in e['output'] for e in evidence))

    def test_the_scout_round_does_not_start_without_time(self):
        m = self.m
        self.fake.when(lambda r, t: True, json.dumps({'need': []}))
        t_end = self.clock.monotonic() + 5
        self.assertEqual(m._n83_gather(self.cid, 'how many days until 25 December 2026?', [], '', '', t_end), [])
        self.assertEqual(self.fake.calls, [], 'less than 8 s left: no planning call is made')

    def test_background_work_is_bounded(self):
        m = self.m
        self.assertEqual(m._N83_Q.maxsize, 8)
        self.assertEqual(m._N86_JOB_TTL, 180)
        self.assertEqual(m._N86_BG_PER_HOUR, 30)
        # a job that waited past its TTL is dropped without a model call
        self.fake.when(lambda r, t: True, json.dumps({'facts': []}))
        old = time.time() - 400
        self.assertFalse(m._n83_job_extract(self.cid, {}, 'my sister Priya lives in Pune and works at a bank', '', m._n86_epoch(self.cid), old))
        self.assertEqual(self.fake.calls, [])
        self.assertGreaterEqual(m._N86_STATS['stale_jobs'], 1)

    def test_greetings_and_questions_cost_no_memory_clerk_call(self):
        m = self.m
        self.fake.when(lambda r, t: True, json.dumps({'facts': []}))
        for text in ('thanks!', 'ok', 'what is the capital of France?', 'what is my sister name?', 'hi there'):
            m._n83_extract(self.cid, {}, text)
        self.assertEqual(self.fake.calls, [], 'no personal content to learn, so no model call')
        m._n83_extract(self.cid, {}, 'my sister Priya lives in Pune and works at a bank')
        self.assertEqual(len([c for c in self.fake.calls if clerk(c['text'])]), 1)

    def test_common_turns_use_the_minimum_number_of_model_calls(self):
        self.fake.when(lambda r, t: True, 'Short answer.')
        for question, expected in (('thanks!', 1), ('what is the capital of France?', 1), (PRICING, 1), ('tell me a joke about cats', 1)):
            self.fake.calls.clear()
            self.chat(question)
            self.assertEqual(len(self.fake.calls), expected, question)


# ===================================================================================================================
# 6. HONEST VERIFICATION
# ===================================================================================================================
LONG = 'Here is a careful, reasonably long answer about budgeting, saving and spending that is certainly more than two hundred characters. ' * 3
DEEP = 'Please analyse my budget and recommend what to do next'


class TestHonestVerification(DeadlineCase):
    def items(self):
        return {i['name']: i for i in self.receipt()['checks']['items']}

    def run_deep(self, critic, answer=LONG, revise=None):
        self.fake.when(lambda r, t: checker(t), critic)
        if revise is not None:
            self.fake.when(lambda r, t: 'A reviewer found these concrete defects' in t, revise)
        self.fake.when(lambda r, t: True, answer)
        return self.chat(DEEP)

    def test_a_review_that_failed_is_reported_as_failed_never_as_zero_issues(self):
        out = self.run_deep(self.m._N73Error('http_500'))
        item = self.items()['critique']
        self.assertEqual(item['status'], 'failed')
        self.assertIn('NOT reviewed', item['detail'])
        self.assertIn('This answer was NOT independently reviewed', out['text'])
        why = self.m._n83_why_text(self.cid)
        self.assertIn('❌ Review of the answer — failed', why)
        self.assertNotRegex(why.lower(), r'0 issues|zero issues|no issues|no verifiable defects')
        self.assertEqual(self.m._N86_STATS['checks_failed'], 1)
        self.assertEqual(self.receipt()['checks']['critique_issues'], 0, 'the old counter alone cannot tell "none" from "did not run"; the status can')

    def test_every_way_the_reviewer_can_break_is_a_failure(self):
        for reply in ('this is not json at all', json.dumps({'issues': 'none'}), json.dumps({'something': 'else'}), '', json.dumps(['x'])):
            self.fake.calls.clear()
            self.fake.rules.clear()
            out = self.run_deep(reply)
            self.assertEqual(self.items()['critique']['status'], 'failed', repr(reply))
            self.assertIn('NOT independently reviewed', out['text'], repr(reply))

    def test_no_provider_for_the_review_is_a_failure(self):
        real = self.m._n83_call
        with mock.patch.object(self.m, '_n83_call', lambda cid, role, *a, **k: None if role == 'route' else real(cid, role, *a, **k)):
            out = self.run_deep(json.dumps({'issues': []}))
        self.assertEqual(self.items()['critique']['status'], 'failed')
        self.assertIn('no AI provider was available', self.items()['critique']['detail'])
        self.assertIn('NOT independently reviewed', out['text'])

    def test_a_review_that_ran_and_found_nothing_is_the_only_time_that_is_claimed(self):
        out = self.run_deep(json.dumps({'issues': []}))
        item = self.items()['critique']
        self.assertEqual(item['status'], 'completed')
        self.assertIn('no verifiable defects found', item['detail'])
        self.assertEqual(len(self.fake.of('fact-and-logic checker')), 1, 'the claim is backed by a real reviewer call')
        self.assertIn('✅ Review of the answer — completed', self.m._n83_why_text(self.cid))
        self.assertNotIn('NOT independently reviewed', out['text'])

    def test_remarks_without_an_exact_quote_are_ignored_and_counted(self):
        self.run_deep(json.dumps({'issues': [{'quote': 'text that is nowhere in the answer', 'problem': 'x', 'fix': 'y'}]}))
        item = self.items()['critique']
        self.assertEqual(item['status'], 'completed')
        self.assertIn('1 remark(s) without an exact quote from the answer were ignored', item['detail'])

    def test_defects_found_and_fixed_are_reported_as_issues_found(self):
        quote = 'certainly more than two hundred characters'
        out = self.run_deep(json.dumps({'issues': [{'quote': quote, 'problem': 'overclaims', 'fix': 'soften'}]}), revise=LONG.replace('certainly', 'probably'))
        item = self.items()['critique']
        self.assertEqual(item['status'], 'issues_found')
        self.assertIn('1 defect(s) found and the answer was revised', item['detail'])
        self.assertIn('probably', out['text'])
        self.assertTrue(self.receipt()['checks']['critique_fixed'])
        self.assertIn('⚠️ Review of the answer — issues found', self.m._n83_why_text(self.cid))

    def test_defects_that_could_not_be_fixed_are_shown_under_the_answer(self):
        quote = 'certainly more than two hundred characters'
        out = self.run_deep(json.dumps({'issues': [{'quote': quote, 'problem': 'overclaims', 'fix': 'soften'}]}), revise=self.m._N73Error('http_500'))
        item = self.items()['critique']
        self.assertEqual(item['status'], 'issues_found')
        self.assertIn('NOT fixed', item['detail'])
        self.assertIn('the revision call failed', item['detail'])
        self.assertIn('⚠️ Review found possible problems I could not fix: overclaims', out['text'])
        self.assertFalse(self.receipt()['checks']['critique_fixed'])

    def test_skipped_reviews_say_why(self):
        m = self.m
        cases = []
        self.fake.when(lambda r, t: True, 'Paris.')
        self.chat('what is the capital of France?')
        cases.append((self.items()['critique'], 'not a complex answer'))
        self.fake.rules.clear()
        self.fake.when(lambda r, t: True, 'Short.')
        self.chat(DEEP)
        cases.append((self.items()['critique'], 'too short'))
        self.fake.rules.clear()
        self.fake.when(lambda r, t: True, LONG)
        m._n83_set_flag(self.cid, 'verify', False)
        self.chat(DEEP)
        cases.append((self.items()['critique'], 'verification was OFF'))
        cases.append((self.items()['arithmetic_date'], 'verification was OFF'))
        m._n83_set_flag(self.cid, 'verify', True)
        for item, needle in cases:
            self.assertEqual(item['status'], 'skipped', item)
            self.assertIn(needle, item['detail'])
        self.assertGreaterEqual(m._N86_STATS['checks_skipped'], 4)

    def test_a_review_without_enough_time_is_skipped_not_claimed(self):
        self.fake.when(lambda r, t: True, self.slow(0, LONG))
        # leave ~30 s: more than the answer needs, fewer than the review needs
        self.fake.rules.clear()

        def answer_then_burn(role, text, messages):
            self.clock.advance(70)
            return LONG
        self.fake.when(lambda r, t: True, answer_then_burn)
        out = self.m._n80_chat(self.msg(DEEP))
        item = self.items()['critique']
        self.assertEqual(item['status'], 'skipped')
        self.assertIn('not enough time left', item['detail'])
        self.assertEqual(self.fake.of('fact-and-logic checker'), [])
        self.assertNotIn('NOT independently reviewed', out['text'], 'a skip by design is in /why83, not a scare in the reply')

    def test_arithmetic_outcomes_are_recorded_exactly(self):
        m = self.m
        # fixed
        self.fake.when(lambda r, t: 'check failed' in t, 'GST at 18% of 1250 = 225, total 1475.')
        self.fake.when(lambda r, t: True, 'GST at 18% of 1250 = 250, total 1500.')
        out = self.chat('how much GST on 1250 at 18%?')
        item = self.items()['arithmetic_date']
        self.assertEqual((item['status'], self.items()['critique']['status']), ('issues_found', 'skipped'))
        self.assertIn('corrected', item['detail'])
        self.assertIn('= 225', out['text'])
        # not fixed
        self.fake.rules.clear()
        self.fake.when(lambda r, t: True, '18% of 1250 = 250.')
        out = self.chat('how much GST on 1250 at 18%?')
        item = self.items()['arithmetic_date']
        self.assertEqual(item['status'], 'issues_found')
        self.assertIn('NOT corrected', item['detail'])
        self.assertIn('Arithmetic check', out['text'])
        # repair call fails
        self.fake.rules.clear()
        self.fake.when(lambda r, t: 'check failed' in t, m._N73Error('http_500'))
        self.fake.when(lambda r, t: True, '18% of 1250 = 250.')
        self.chat('how much GST on 1250 at 18%?')
        self.assertIn('the repair call failed (http_500)', self.items()['arithmetic_date']['detail'])
        # clean
        self.fake.rules.clear()
        self.fake.when(lambda r, t: True, '18% of 1250 = 225.')
        self.chat('how much GST on 1250 at 18%?')
        item = self.items()['arithmetic_date']
        self.assertEqual(item['status'], 'completed')
        self.assertIn('none found', item['detail'])

    def test_a_wrong_weekday_is_flagged_as_a_date_check(self):
        self.fake.when(lambda r, t: True, '25 December 2026 is a Monday.')
        out = self.chat('what day is 25 December 2026?')
        self.assertEqual(self.items()['arithmetic_date']['status'], 'issues_found')
        self.assertIn('Date check', out['text'])
        self.assertIn('Friday', out['text'])

    def test_receipts_keep_per_check_results_and_survive_a_restart(self):
        self.run_deep(json.dumps({'issues': []}))
        persisted = self.rows('SELECT checks FROM cx83_turn ORDER BY id DESC LIMIT 1')[0][0]
        items = json.loads(persisted)['items']
        self.assertEqual([(i['name'], i['status']) for i in items], [('arithmetic_date', 'completed'), ('critique', 'completed')])
        with self.m._N83_LOCK:
            self.m._N83_LAST.clear()
        why = self.m._n83_why_text(self.cid)
        self.assertIn('✅ Arithmetic & date check — completed', why)
        self.assertIn('✅ Review of the answer — completed', why)

    def test_an_old_receipt_is_labelled_not_guessed(self):
        with self.m._N83_LOCK:
            self.m._N83_LAST[self.cid] = {'request': 'x', 'ts': time.time(), 'tools': [], 'memory': [], 'checks': {'arith_flagged': 0, 'critique_issues': 0},
                                          'model': 'm/x', 'latency_ms': 1000, 'summary': None}
        why = self.m._n83_why_text(self.cid)
        self.assertIn('older receipt: per-check results were not recorded', why)
        self.assertNotIn('0 issues', why)

    def test_why_always_states_what_is_not_verified(self):
        self.run_deep(json.dumps({'issues': []}))
        self.assertIn('Not externally verified', self.m._n83_why_text(self.cid))

    def test_status_shows_the_real_counts(self):
        self.run_deep(self.m._N73Error('http_500'))
        status = self.m._n83_status_text(self.cid)
        self.assertIn('CANDOR 86', status)
        self.assertIn('failed 1', status)

    def test_matrix_completed_is_only_ever_claimed_when_the_check_really_ran(self):
        """For every combination: a 'completed' review implies a real reviewer call that returned a parsable list; any other outcome never says completed."""
        m = self.m
        replies = {'clean': json.dumps({'issues': []}), 'garbage': 'nope', 'error': m._N73Error('http_500'),
                   'defect': json.dumps({'issues': [{'quote': 'certainly more than two hundred characters', 'problem': 'p', 'fix': 'f'}]})}
        for verify in (True, False):
            for question in (DEEP, 'what is the capital of France?'):
                for answer in (LONG, 'Short.'):
                    for kind, reply in replies.items():
                        self.fake.calls.clear()
                        self.fake.rules.clear()
                        m._n83_set_flag(self.cid, 'verify', verify)
                        self.fake.when(lambda r, t: checker(t), reply)
                        self.fake.when(lambda r, t: 'A reviewer found these concrete defects' in t, LONG.replace('certainly', 'probably'))
                        self.fake.when(lambda r, t: True, answer)
                        self.chat(question)
                        item = self.items()['critique']
                        reviewer_calls = len(self.fake.of('fact-and-logic checker'))
                        label = (verify, question[:12], len(answer), kind)
                        self.assertIn(item['status'], ('completed', 'issues_found', 'skipped', 'failed'), label)
                        if item['status'] in ('completed', 'issues_found'):
                            self.assertEqual(reviewer_calls, 1, label)
                            self.assertIn(kind, ('clean', 'defect'), label)
                        if kind in ('garbage', 'error') and reviewer_calls:
                            self.assertEqual(item['status'], 'failed', label)
                        if reviewer_calls == 0:
                            self.assertEqual(item['status'], 'skipped', label)
        m._n83_set_flag(self.cid, 'verify', True)


# ===================================================================================================================
# STRUCTURE, REGRESSION ROWS AND MUTATION CHECKS
# ===================================================================================================================
def _layer_source():
    with open(SOURCE_PATH, encoding='utf-8') as fh:
        src = fh.read()
    start = src.index('# NEMO 86 - CANDOR')
    return src, src[start:src.rindex("if __name__")]


class TestStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        c86.setUpModule()
        cls.m = base.m
        cls.full, cls.layer = _layer_source()
        cls.tree = ast.parse(cls.layer)

    def test_the_version_is_distinct(self):
        self.assertEqual(self.m.VERSION, '86.0')
        self.assertIn('NEMO 86.0 CANDOR', self.full)

    def test_the_regression_rows_are_green(self):
        rows = self.m._n86_regression_rows()
        self.assertGreaterEqual(len(rows), 13)
        bad = [r['name'] for r in rows if not r['ok']]
        self.assertEqual(bad, [])
        suite = self.m.prime_regression_suite()
        names = [t['name'] for t in suite['tests']]
        self.assertTrue(all(n in names for n in [r['name'] for r in rows]))

    def test_the_new_layer_cannot_be_rewritten_by_the_development_builder(self):
        self.assertFalse(self.m._n79_editable('_n86_forget_execute'))
        self.assertFalse(self.m._n79_editable('_n86_x'))

    def test_no_dangerous_calls_and_no_secret_literals_in_the_new_layer(self):
        banned = {'eval', 'exec', 'compile', '__import__'}
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name):
                    self.assertNotIn(f.id, banned, 'line %d' % node.lineno)
                if isinstance(f, ast.Attribute):
                    self.assertNotIn(f.attr, {'system', 'popen', 'Popen', 'check_output', 'urlopen', 'rmtree', 'eval', 'exec'}, 'line %d' % node.lineno)
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mods = [a.name for a in node.names] + ([node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
                for mod in mods:
                    self.assertNotIn(mod.split('.')[0], {'subprocess', 'requests', 'urllib', 'socket', 'ctypes', 'shutil', 'pickle'}, 'line %d' % node.lineno)
        for pattern in (r'sk-[A-Za-z0-9]{16,}', r'AIza[0-9A-Za-z_-]{20,}', r'\b\d{8,10}:[A-Za-z0-9_-]{30,}', r'gh[pousr]_[A-Za-z0-9]{20,}', r'xox[abp]-'):
            self.assertIsNone(re.search(pattern, self.layer), pattern)

    def test_files_are_only_removed_by_the_backup_purge_and_only_on_request(self):
        owners = []
        for fn in [n for n in self.tree.body if isinstance(n, ast.FunctionDef)]:
            for node in ast.walk(fn):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ('remove', 'unlink') and 'os' in ast.dump(node.func.value):
                    owners.append(fn.name)
        self.assertEqual(set(owners), {'_n86_purge_backups'})
        callers = [fn.name for fn in self.tree.body if isinstance(fn, ast.FunctionDef) and fn.name != '_n86_purge_backups'
                   and any(isinstance(n, ast.Name) and n.id == '_n86_purge_backups' for n in ast.walk(fn))]
        self.assertEqual(callers, ['_n86_pending_reply'], 'only the confirmed backup-deletion reply may call it')

    def test_the_credential_and_trading_guards_were_not_touched(self):
        src = self.full
        for needle in ('def _update_cred_changes', 'def _n79_owner', 'def _n84_holiday', 'def _n55_market_clock', 'def _n68_snapshot', 'def self_rollback'):
            self.assertIn(needle, src, needle)
        # the layer only reads the owner lock; it never assigns it or any key
        self.assertNotRegex(self.layer, r"OWNER\[['\"]id['\"]\]\s*=")
        self.assertNotRegex(self.layer, r"(?i)(api_key|token|secret|password)\w*\s*=\s*['\"][^'\"]{6,}['\"]")

    def test_there_is_exactly_one_definition_of_each_replaced_function(self):
        tree = ast.parse(self.full)
        names = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
        for fn in ('_n83_log_learned', '_n83_extract', '_n83_verify', '_n83_chat_core', '_n83_tool_search', '_n83_run_tools', '_n83_why_text', '_n79_build', '_n83_compact'):
            self.assertEqual(names.count(fn), 1, fn)


class TestMutationsAreCaught(unittest.TestCase):
    """The regression tests must fail when the fix is removed. Each mutation re-implements the OLD behaviour and one named test must go red."""

    @classmethod
    def setUpClass(cls):
        c86.setUpModule()
        cls.m = base.m

    def red(self, test_id, **patches):
        """Run one named test with the given attributes of the module replaced; return True if that test FAILED (i.e. it catches the mutation)."""
        suite = unittest.defaultTestLoader.loadTestsFromName(test_id)
        stack = [mock.patch.object(self.m, name, value) for name, value in patches.items()]
        for p in stack:
            p.start()
        try:
            result = unittest.TestResult()
            suite.run(result)
        finally:
            for p in reversed(stack):
                p.stop()
        self.assertEqual(result.testsRun, 1, test_id)
        return not result.wasSuccessful()

    def green(self, test_id):
        suite = unittest.defaultTestLoader.loadTestsFromName(test_id)
        result = unittest.TestResult()
        suite.run(result)
        return result.wasSuccessful()

    def test_the_unmutated_tests_are_green(self):
        for tid in ('tests.test_candor86.TestNoSensitiveLogging.test_masking_table',
                    'tests.test_candor86_runtime.TestResearchTurns.test_the_reported_question_is_researched_with_one_model_call'):
            self.assertTrue(self.green(tid), tid)

    def test_without_masking_the_logging_tests_fail(self):
        self.assertTrue(self.red('tests.test_candor86.TestNoSensitiveLogging.test_masking_table', _n86_mask=lambda t: t))
        self.assertTrue(self.red('tests.test_candor86.TestNoSensitiveLogging.test_turn_log_and_episodes_are_masked', _n86_mask=lambda t: t))

    def test_without_the_epoch_check_a_queued_job_restores_what_was_forgotten(self):
        self.assertTrue(self.red('tests.test_candor86.TestForgettingQueuedJobs.test_queued_extract_job_is_cancelled_by_a_forget', _n86_job_dropped=lambda cid, epoch, ts: False))

    def test_without_the_dev_intercept_the_upgrade_request_is_not_caught(self):
        self.assertTrue(self.red('tests.test_candor86.TestUpgradeRoutingAndIntake.test_download_wording_never_reaches_media_routing', _n86_dev_intent=lambda text: None))

    def test_without_the_signal_scorer_the_pricing_question_is_missed_again(self):
        sig = {'level': 'none', 'score': 0, 'reasons': [], 'entities': [], 'time_signal': False}
        self.assertTrue(self.red('tests.test_candor86_runtime.TestResearchTurns.test_the_reported_question_is_researched_with_one_model_call', _n86_research_signals=lambda t: sig))

    def test_without_a_failure_footer_the_research_failure_test_fails(self):
        self.assertTrue(self.red('tests.test_candor86_runtime.TestResearchTurns.test_when_the_search_fails_the_answer_says_so', _n86_research_footer=lambda r, a: ''))

    def test_with_the_budget_ignored_the_deadline_tests_fail(self):
        self.assertTrue(self.red('tests.test_candor86_runtime.TestSharedDeadline.test_the_call_wrapper_clamps_and_refuses', _n86_effective_deadline=lambda d: d))
        self.assertTrue(self.red('tests.test_candor86_runtime.TestSharedDeadline.test_the_older_fallback_refuses_when_the_budget_is_spent', _n73_core_reply=self.m._N86_CORE_PREV))

    def test_with_per_stage_timeouts_only_the_total_time_property_fails(self):
        """The old behaviour: each call keeps its own timeout and the fallback starts a fresh one."""
        self.assertTrue(self.red('tests.test_candor86_runtime.TestSharedDeadline.test_property_total_time_is_bounded_for_random_latencies_and_failures',
                                 _n86_effective_deadline=lambda d: d, _n73_core_reply=self.m._N86_CORE_PREV, _n86_budget=lambda: None))

    def test_recording_a_skipped_review_as_completed_is_caught(self):
        real = self.m._n86_add_check

        def lying(items, name, status, detail):
            return real(items, name, 'completed' if status == 'skipped' else status, detail)
        self.assertTrue(self.red('tests.test_candor86_runtime.TestHonestVerification.test_skipped_reviews_say_why', _n86_add_check=lying))

    def test_hiding_a_failed_review_is_caught(self):
        self.assertTrue(self.red('tests.test_candor86_runtime.TestHonestVerification.test_a_review_that_failed_is_reported_as_failed_never_as_zero_issues', _n86_review_footer=lambda checks: ''))


if __name__ == '__main__':
    unittest.main()
