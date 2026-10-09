"""Nemo v102 "Hearth": a local brain (an open model on the owner's own computer) that answers when the cloud brains fail, answers "private: ..." questions without any cloud AI, and can be the only brain
in offline mode; reached by a relay (the computer only makes outgoing calls) or a direct address.

Offline. No Telegram, no cloud AI, no paid service, no broker, no order. The "local model" is a small HTTP server started inside the test (it speaks Ollama's and the OpenAI-style protocol and records every
request it receives); the website is the real Flask app served on the loopback address; the relay script is the REAL script text that the owner would be sent, executed in the test. Privacy tests replace the
network layer with a tripwire that fails on any address but the local model's.

    NEMO_FILE=/path/to/nemotron_bot.py python -m unittest tests.test_hearth102 -v
"""
import ast
import http.server
import json
import os
import re
import sqlite3
import threading
import time
import unittest
from unittest import mock

import requests

from tests import test_cortex83 as base
from tests.test_forge91 import ForgeCase, OWNER_ID

try:
    import flask  # noqa: F401
    HAVE_FLASK = True
except Exception:                                   # pragma: no cover
    HAVE_FLASK = False
needs_flask = unittest.skipUnless(HAVE_FLASK, 'Flask is not installed')


def setUpModule():
    os.environ['NO_PROXY'] = '127.0.0.1,localhost'
    os.environ['no_proxy'] = '127.0.0.1,localhost'
    if base.m is None:
        base.setUpModule()


def hearth_source():
    src = open(base.NEMO_FILE, encoding='utf-8').read()
    i = src.index('# NEMO 102 - HEARTH')
    j = src.rindex("if __name__")
    return src[i:j]


# ===================================================================================================================
# a small model server: Ollama's protocol (or the OpenAI-style one), recording what it is asked
# ===================================================================================================================
class FakeModelServer:
    def __init__(self, models=('qwen3:8b',), api='ollama'):
        self.models = list(models)
        self.api = api
        self.requests = []                       # (method, path, body)
        self.reply = lambda body: 'Hello from the local brain.'
        self.status = 200
        self.delay = 0.0
        self.eval_count = 30
        self.eval_ms = 3000
        owner = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, obj):
                raw = json.dumps(obj).encode() if not isinstance(obj, bytes) else obj
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                owner.requests.append(('GET', self.path, None))
                if self.path == '/api/tags' and owner.api == 'ollama':
                    return self._send(200, {'models': [{'name': n} for n in owner.models]})
                if self.path == '/v1/models' and owner.api == 'openai':
                    return self._send(200, {'data': [{'id': n} for n in owner.models]})
                self._send(404, {'error': 'not found'})

            def do_POST(self):
                n = int(self.headers.get('Content-Length') or 0)
                body = json.loads(self.rfile.read(n).decode() or '{}')
                owner.requests.append(('POST', self.path, body))
                if owner.delay:
                    time.sleep(owner.delay)
                if owner.status != 200:
                    return self._send(owner.status, {'error': 'boom'})
                text = owner.reply(body)
                if self.path == '/api/chat' and owner.api == 'ollama':
                    return self._send(200, {'message': {'role': 'assistant', 'content': text}, 'eval_count': owner.eval_count, 'eval_duration': int(owner.eval_ms * 1e6)})
                if self.path == '/v1/chat/completions' and owner.api == 'openai':
                    return self._send(200, {'choices': [{'message': {'content': text}}], 'usage': {'completion_tokens': owner.eval_count}})
                self._send(404, {'error': 'not found'})

        self.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
        self.url = 'http://127.0.0.1:%d' % self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def chats(self):
        return [b for (mth, p, b) in self.requests if mth == 'POST']


class Cloud:
    """Stand-in for the cloud gateway that Hearth wraps (Brain73's real request function)."""

    def __init__(self):
        self.calls = []
        self.behave = lambda cid, role, messages: {'text': 'cloud answer', 'provider': 'fake', 'model': 'fake-1', 'usage': {}}

    def __call__(self, cid, role, messages, timeout=60, _route_override=None, _probe=False):
        self.calls.append({'cid': cid, 'role': role, 'messages': messages, 'timeout': timeout})
        out = self.behave(cid, role, messages)
        if isinstance(out, Exception):
            raise out
        return out


def answer_msgs(text='tell me a short story about a fox'):
    return [{'role': 'system', 'content': "You are Nemo, the owner's chief of staff and thinking partner."}, {'role': 'user', 'content': text}]


class HearthCase(ForgeCase):
    def setUp(self):
        super().setUp()
        m = self.m
        self.start(m, '_n73_request', base.ORIG_N73_REQUEST)          # Hearth's wrapper (the shared fixture put a scripted fake in its place)
        self.cloud = Cloud()
        self.start(m, '_N102_REQ_PREV', self.cloud)
        self.start(m, 'WEBCFG', dict(m.WEBCFG, public_url='https://nemo.example.com'))
        self.start(m, 'DEVICE_FILE', os.path.join(self.tmp.name, 'devices.json'))
        for d in (m._N102_RELAY, m._N102_STATE, m._N102_JOBS, m._N102_BUSY):
            d.clear()
        m._N102_NOTICE['t'] = 0.0
        m._N102_CACHE.update(t=0.0, nodes=None)
        m._N102_POLLING['n'] = 0
        for k in m._N102_STATS:
            m._N102_STATS[k] = 0
        m._n102_db().close()
        self.srv = FakeModelServer().start()
        self.addCleanup(self.srv.stop)
        self.docs = []

        def doc(chat_id, path, filename, mime):
            with open(path, encoding='utf-8') as f:
                self.docs.append((chat_id, filename, f.read()))
            return True
        self.start(m, 'send_document', doc)
        self.cid = OWNER_ID

    def add_direct(self, srv=None, name='box', model=''):
        srv = srv or self.srv
        nid, nname = self.m._n102_node_add('direct', name, url=srv.url, model=model, api=srv.api)
        return nid

    def said(self):
        return '\n'.join(t for (_c, t) in self.sent)

    def owner_msg(self, text, **extra):
        d = {'chat': {'id': OWNER_ID, 'type': 'private'}, 'from': {'id': OWNER_ID}, 'text': text, 'message_id': 1}
        d.update(extra)
        return d

    def passthrough(self):
        passed = []
        self.start(self.m, '_N102_HANDLE_PREV', lambda msg: passed.append(msg))
        return passed

    def route(self, text):
        return self.m._n102_route(OWNER_ID, text)


# ===================================================================================================================
# 1. THE SMALL PIECES
# ===================================================================================================================
class TestAddresses(HearthCase):
    def test_own_network_addresses_are_accepted(self):
        f = self.m._n102_safe_url
        for u in ('http://127.0.0.1:11434', 'http://100.64.0.5:11434', 'http://192.168.1.20:11434/', 'http://laptop.local:11434', 'http://box.tail1234.ts.net:11434', 'https://brain.example.com', 'https://brain.example.com:8443'):
            self.assertEqual(f(u), u.rstrip('/'), u)

    def test_everything_else_is_refused(self):
        f = self.m._n102_safe_url
        for u in ('ftp://100.64.0.5', 'http://', '100.64.0.5:11434', 'http://100.64.0.5:11434/api', 'http://100.64.0.5:11434/?x=1', 'http://user:pw@100.64.0.5:11434',
                  'http://169.254.169.254', 'http://metadata.google.internal', 'http://0.0.0.0:11434', 'http://224.0.0.1', 'http://[fe80::1]:11434', 'http://1.2.3.4:99999',
                  'http://example.com:11434', 'http://8.8.8.8:11434', '', None):
            with self.assertRaises(ValueError, msg=str(u)):
                f(u)

    def test_plain_http_only_inside_your_own_network(self):
        p = self.m._n102_plain_ok
        self.assertTrue(p('10.0.0.5') and p('127.0.0.1') and p('100.100.1.1') and p('localhost') and p('pc.local'))
        self.assertFalse(p('8.8.8.8') or p('example.com') or p('100.128.0.1'))


class TestPreparingAPrompt(HearthCase):
    def test_the_question_is_always_kept_and_the_size_is_bounded(self):
        m = self.m
        msgs = [{'role': 'system', 'content': 'S' * 90000}]
        for i in range(60):
            msgs.append({'role': 'user' if i % 2 == 0 else 'assistant', 'content': ('turn %d ' % i) * 200})
        msgs.append({'role': 'user', 'content': 'the actual question'})
        out = m._n102_prepare(msgs)
        self.assertEqual(out[0]['role'], 'system')
        self.assertEqual(out[-1], {'role': 'user', 'content': 'the actual question'})
        total = sum(len(x['content']) for x in out)
        self.assertLess(total, m._N102_BUDGET_CHARS + len(m._N102_NOTE) + 500)
        self.assertIn("Nemo's local brain", out[0]['content'])
        recent = [x['content'] for x in out[1:-1]]
        self.assertTrue(recent and 'turn 59' in recent[-1] or 'turn 58' in recent[-1], 'the newest turns are the ones kept')

    def test_a_long_system_prompt_is_cut_in_the_middle_keeping_both_ends(self):
        s = 'HEAD-' + 'x' * 30000 + '-TAIL'
        out = self.m._n102_prepare([{'role': 'system', 'content': s}, {'role': 'user', 'content': 'q'}])
        self.assertIn('HEAD-', out[0]['content'])
        self.assertIn('-TAIL', out[0]['content'])
        self.assertLess(len(out[0]['content']), len(s))

    def test_order_roles_and_empties(self):
        out = self.m._n102_prepare([{'role': 'system', 'content': 'a'}, {'role': 'tool', 'content': 'dropped'}, {'role': 'user', 'content': 'one'}, {'role': 'assistant', 'content': 'two'},
                                    {'role': 'system', 'content': 'live figures'}, {'role': 'user', 'content': 'three'}, {'role': 'user', 'content': '   '}])
        self.assertEqual([x['role'] for x in out], ['system', 'user', 'assistant', 'user'])
        self.assertIn('live figures', out[0]['content'])
        self.assertNotIn('dropped', json.dumps(out))
        self.assertEqual(self.m._n102_prepare([])[-1]['content'], 'Hello')

    def test_a_huge_question_is_trimmed_not_dropped(self):
        out = self.m._n102_prepare([{'role': 'user', 'content': 'q' * 50000}])
        self.assertLess(len(out[-1]['content']), 6000)
        self.assertTrue(out[-1]['content'].startswith('qqq'))

    def test_pictures_cannot_go_to_a_text_model(self):
        with self.assertRaises(self.m._N102Fail) as cm:
            self.m._n102_prepare([{'role': 'user', 'content': [{'type': 'text', 'text': 'what is this'}, {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,AAAA'}}]}])
        self.assertEqual(cm.exception.code, 'has_image')
        out = self.m._n102_prepare([{'role': 'user', 'content': [{'type': 'text', 'text': 'part one'}, {'type': 'text', 'text': 'part two'}]}])
        self.assertIn('part one\npart two', out[-1]['content'])

    def test_reasoning_blocks_and_control_tokens_never_reach_the_owner(self):
        c = self.m._n102_clean_answer
        self.assertEqual(c('<think>let me work it out\nstep</think>\n\nThe answer is 42.'), 'The answer is 42.')
        self.assertEqual(c('<THINK>x</THINK>Hi'), 'Hi')
        self.assertEqual(c('Hi<|im_end|>'), 'Hi')
        self.assertEqual(c('<think>never finishes and has no answer'), '')
        self.assertEqual(c(None), '')
        self.assertEqual(c('   '), '')


class TestWhichCallsMayUseTheLocalBrain(HearthCase):
    def test_kinds(self):
        k = self.m._n102_call_kind
        self.assertEqual(k('chat', answer_msgs()), 'answer')
        self.assertEqual(k('reason', answer_msgs()), 'answer')
        self.assertEqual(k('chat', [{'role': 'system', 'content': self.m._N83_HELPER_SYSTEM}, {'role': 'user', 'content': 'x'}]), 'helper')
        self.assertEqual(k('chat', [{'role': 'system', 'content': 'You are a tool scout.'}, {'role': 'user', 'content': 'x'}]), 'helper')
        self.assertEqual(k('chat', [{'role': 'user', 'content': 'List the items. Return ONLY JSON {"a":1}'}]), 'helper')
        self.assertEqual(k('chat', [{'role': 'user', 'content': 'Reply with JSON only.'}]), 'helper')
        self.assertEqual(k('code', answer_msgs()), 'skip')
        self.assertEqual(k('vision', answer_msgs()), 'skip')
        self.assertEqual(k('chat', [{'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': 'x'}}]}]), 'skip')

    def test_simple_questions(self):
        s = self.m._n102_is_simple
        self.assertTrue(s(answer_msgs('what does serendipity mean')))
        self.assertTrue(s(answer_msgs('write a short thank you note to my cousin')))
        for q in ('what is the nifty price today', 'latest news on the budget', 'analyse this contract', 'email the dealer', 'x' * 400, 'open https://example.com', 'what is 18% of 1250', 'debug this code', 'call 9876543210'):
            self.assertFalse(s(answer_msgs(q)), q)
        withground = answer_msgs('hello') + [{'role': 'system', 'content': 'LIVE GROUND TRUTH - the ONLY correct current numbers.'}]
        self.assertFalse(s(withground))


# ===================================================================================================================
# 2. A MODEL SERVER THE SERVER CAN REACH (DIRECT)
# ===================================================================================================================
class TestDirectNode(HearthCase):
    def test_it_finds_out_what_kind_of_server_it_is(self):
        m = self.m
        pr = m._n102_probe_direct({'url': self.srv.url})
        self.assertEqual((pr['ok'], pr['api'], pr['models']), (True, 'ollama', ['qwen3:8b']))
        other = FakeModelServer(models=('llama-3.1-8b',), api='openai').start()
        self.addCleanup(other.stop)
        pr = m._n102_probe_direct({'url': other.url})
        self.assertEqual((pr['ok'], pr['api'], pr['models']), (True, 'openai', ['llama-3.1-8b']))
        dead = FakeModelServer().start()
        url = dead.url
        dead.stop()
        pr = m._n102_probe_direct({'url': url}, timeout=2)
        self.assertFalse(pr['ok'])

    def test_a_question_is_answered_and_the_speed_is_measured(self):
        m = self.m
        nid = self.add_direct()
        m._N102_STATE[nid] = {'tps': 50.0, 'models': ['qwen3:8b'], 'api': 'ollama', 'fail': 0, 't': time.time()}      # a fast machine: plenty of room for a full-length answer
        self.srv.eval_count, self.srv.eval_ms = 30, 3000
        self.srv.reply = lambda body: '<think>hmm</think>It is a fox.'
        out = m._n102_generate(answer_msgs('what is this animal'), timeout=100)
        self.assertTrue(out['ok'], out)
        self.assertEqual((out['text'], out['model'], out['node_name']), ('It is a fox.', 'qwen3:8b', 'box'))
        self.assertEqual(out['tps'], 10.0)
        sent = self.srv.chats()[-1]
        self.assertEqual((sent['model'], sent['stream'], sent['keep_alive']), ('qwen3:8b', False, '30m'))
        self.assertEqual(sent['options']['num_predict'], 700)
        self.assertEqual(sent['options']['num_ctx'], m._N102_CTX)
        self.assertEqual(sent['messages'][0]['role'], 'system')
        self.assertTrue(sent['messages'][-1]['content'].startswith('what is this animal'))

    def test_qwen3_gets_its_no_thinking_switch_and_other_models_do_not(self):
        m = self.m
        self.add_direct()
        m._n102_generate(answer_msgs('hi there'), timeout=20)
        self.assertTrue(self.srv.chats()[-1]['messages'][-1]['content'].endswith('/no_think'))
        other = FakeModelServer(models=('llama3.2:3b',)).start()
        self.addCleanup(other.stop)
        m._n102_node_remove([n for n in m._n102_nodes(fresh=True)][0]['id'])
        self.add_direct(other, 'other')
        m._n102_generate(answer_msgs('hi there'), timeout=20)
        self.assertNotIn('/no_think', other.chats()[-1]['messages'][-1]['content'])

    def test_the_openai_style_protocol_works_too(self):
        m = self.m
        srv = FakeModelServer(models=('llama-3.1-8b',), api='openai').start()
        self.addCleanup(srv.stop)
        nid = self.add_direct(srv, 'llamacpp')
        m._N102_STATE[nid] = {'tps': 50.0, 'models': ['llama-3.1-8b'], 'api': 'openai', 'fail': 0, 't': time.time()}
        srv.eval_count = 20
        out = m._n102_generate(answer_msgs(), timeout=100)
        self.assertTrue(out['ok'], out)
        self.assertEqual(out['model'], 'llama-3.1-8b')
        self.assertEqual(out['tokens'], 20)
        body = srv.chats()[-1]
        self.assertEqual((body['max_tokens'], body['stream']), (700, False))

    def test_model_choice_prefers_the_setting_then_the_node_then_the_first_real_chat_model(self):
        m = self.m
        self.srv.models = ['nomic-embed-text', 'llama3.2:3b', 'qwen3:8b']
        nid = self.add_direct()
        m._n102_generate(answer_msgs(), timeout=20)
        self.assertEqual(self.srv.chats()[-1]['model'], 'llama3.2:3b', 'an embedding model is never used to chat')
        m._n102_put('model', 'qwen3:8b')
        m._n102_generate(answer_msgs(), timeout=20)
        self.assertEqual(self.srv.chats()[-1]['model'], 'qwen3:8b')
        m._n102_put('model', 'not-installed')
        m._n102_q('UPDATE hearth102_node SET model=? WHERE id=?', ('llama3.2:3b', nid), write=True)
        m._n102_nodes_changed()
        m._n102_generate(answer_msgs(), timeout=20)
        self.assertEqual(self.srv.chats()[-1]['model'], 'llama3.2:3b')

    def test_it_asks_for_no_more_words_than_can_arrive_in_time(self):
        m = self.m
        nid = self.add_direct()
        m._N102_STATE[nid] = {'tps': 5.0, 'models': ['qwen3:8b'], 'api': 'ollama', 'fail': 0, 't': time.time()}
        m._n102_generate(answer_msgs(), timeout=20, max_tokens=700)
        asked = self.srv.chats()[-1]['options']['num_predict']
        self.assertLessEqual(asked, int((20 - 4) * 5 * 0.85) + 1)
        self.assertGreaterEqual(asked, 60)
        m._n102_generate(answer_msgs(), timeout=100, max_tokens=700)
        self.assertEqual(self.srv.chats()[-1]['options']['num_predict'], 700, 'with time to spare the full length is asked for')

    def test_failures_are_reported_and_a_node_that_keeps_failing_is_left_alone_for_a_minute(self):
        m = self.m
        nid = self.add_direct()
        self.srv.status = 500
        for _ in range(3):
            out = m._n102_generate(answer_msgs(), timeout=10)
            self.assertFalse(out['ok'])
            self.assertIn('http_500', out['error'])
        self.assertEqual(m._N102_STATE[nid]['fail'], 3)
        n = m._n102_nodes()[0]
        self.assertFalse(m._n102_node_online(n))
        self.assertEqual(m._n102_generate(answer_msgs(), timeout=10)['error'], 'no_local_brain_online')
        m._N102_STATE[nid]['t'] -= 120
        self.srv.status = 200
        self.assertTrue(m._n102_generate(answer_msgs(), timeout=10)['ok'])
        self.assertEqual(m._N102_STATE[nid]['fail'], 0)

    def test_an_empty_answer_or_an_unfinished_reasoning_block_is_a_failure_not_an_answer(self):
        m = self.m
        self.add_direct()
        for bad in ('', '   ', '<think>endless'):
            self.srv.reply = lambda body, bad=bad: bad
            out = m._n102_generate(answer_msgs(), timeout=10)
            self.assertFalse(out['ok'], repr(bad))
            self.assertEqual(out['error'], 'empty_answer')

    def test_no_model_installed_is_said(self):
        self.srv.models = []
        self.add_direct()
        out = self.m._n102_generate(answer_msgs(), timeout=10)
        self.assertEqual((out['ok'], out['error']), (False, 'no_model_installed'))

    def test_a_slow_server_is_given_up_on_at_the_deadline(self):
        self.add_direct()
        self.srv.delay = 5
        t0 = time.time()
        out = self.m._n102_generate(answer_msgs(), timeout=3)
        self.assertFalse(out['ok'])
        self.assertLess(time.time() - t0, 5.5)

    def test_the_best_working_computer_is_used_and_a_failing_one_is_skipped(self):
        m = self.m
        bad = FakeModelServer().start()
        bad.status = 500
        self.addCleanup(bad.stop)
        good = FakeModelServer(models=('llama3.2:3b',)).start()
        self.addCleanup(good.stop)
        self.add_direct(bad, 'bad')
        gid = self.add_direct(good, 'good')
        out = m._n102_generate(answer_msgs(), timeout=15)
        self.assertTrue(out['ok'], out)
        self.assertEqual(out['node_name'], 'good')
        out = m._n102_generate(answer_msgs(), timeout=15)
        self.assertEqual(out['node_name'], 'good')
        self.assertEqual(len([r for r in bad.requests if r[0] == 'POST']), 1, 'after its success the good one is asked first')
        self.assertGreater(m._N102_STATE[gid]['ok'], 0)

    def test_one_question_at_a_time_per_computer(self):
        m = self.m

        class Held:
            def acquire(self, timeout=None):
                return False

            def release(self):
                raise AssertionError('never acquired')
        nid = self.add_direct()
        m._N102_BUSY[nid] = Held()
        out = m._n102_generate(answer_msgs(), timeout=10)
        self.assertEqual((out['ok'], out['error']), (False, 'busy'))
        self.assertEqual(self.srv.chats(), [])

    def test_a_picture_is_refused_before_anything_is_sent(self):
        self.add_direct()
        out = self.m._n102_generate([{'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': 'x'}}]}], timeout=10)
        self.assertEqual((out['ok'], out['error']), (False, 'has_image'))
        self.assertEqual(self.srv.requests, [])

    def test_with_nothing_connected_it_says_so_at_once(self):
        t0 = time.time()
        out = self.m._n102_generate(answer_msgs(), timeout=30)
        self.assertEqual((out['ok'], out['error']), (False, 'no_local_brain_online'))
        self.assertLess(time.time() - t0, 1)


# ===================================================================================================================
# 3. THE RELAY: THE WEBSITE'S TWO CALLS, ENROLMENT, AND THE REAL SCRIPT
# ===================================================================================================================
class RelayCase(HearthCase):
    def setUp(self):
        super().setUp()
        if not HAVE_FLASK:
            self.skipTest('Flask is not installed')
        self.app = self.m.build_web_app()
        self.http = self.app.test_client()

    def enrol(self, name='laptop', hearth=True, client=None):
        m = self.m
        nid = None
        if hearth:
            nid, nname = m._n102_node_add('relay', name)
            tok = m._n102_enroll_token(nname, nid)
        else:
            tok = m._device_enroll_create(name)
        r = (client or self.http).post('/api/device/enroll', json={'token': tok, 'name': name, 'platform': 'Windows', 'hostname': 'pc'})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        j = r.get_json()
        return j['device_id'], j['device_secret'], nid

    def poll(self, did, secret, wait=0, models=('qwen3:8b',), headers=None, **env):
        h = {'Authorization': 'Bearer ' + secret}
        h.update(headers or {})
        return self.http.post('/api/hearth/%s/next' % did, json={'wait': wait, 'models': list(models), 'version': '102.0'}, headers=h, environ_base=dict(env))

    def answer(self, did, secret, jid, text='an answer', ok=True, headers=None, **extra):
        body = {'id': jid, 'ok': ok, 'text': text, 'model': 'qwen3:8b', 'eval_count': 12, 'eval_ms': 1200, 'error': '' if ok else 'broken'}
        body.update(extra)
        h = {'Authorization': 'Bearer ' + secret}
        h.update(headers or {})
        return self.http.post('/api/hearth/%s/result' % did, json=body, headers=h)


@needs_flask
class TestRelayWebsite(RelayCase):
    def test_only_a_hearth_computer_with_the_right_key_may_collect_questions(self):
        did, secret, _nid = self.enrol()
        self.assertEqual(self.poll(did, secret).status_code, 200)
        self.assertEqual(self.poll(did, secret + 'x').status_code, 403)
        self.assertEqual(self.poll('dev_nope', secret).status_code, 403)
        self.assertEqual(self.http.post('/api/hearth/%s/next' % did, json={}).status_code, 403)
        odid, osecret, _ = self.enrol('phone', hearth=False)
        self.assertEqual(self.poll(odid, osecret).status_code, 403, 'an ordinary enrolled device cannot collect questions')
        self.assertEqual(self.answer(odid, osecret, 'H123').status_code, 403)

    def test_a_removed_computer_is_refused(self):
        did, secret, nid = self.enrol()
        self.m._n102_revoke_device(did)
        self.assertEqual(self.poll(did, secret).status_code, 403)

    def test_questions_travel_only_over_https_or_your_own_network(self):
        did, secret, _nid = self.enrol()
        r = self.poll(did, secret, REMOTE_ADDR='8.8.8.8')
        self.assertEqual(r.status_code, 403)
        self.assertIn('https', r.get_json()['error'])
        self.assertEqual(self.poll(did, secret, headers={'X-Forwarded-Proto': 'https'}, REMOTE_ADDR='8.8.8.8').status_code, 200)
        self.assertEqual(self.poll(did, secret, REMOTE_ADDR='100.64.0.9').status_code, 200)
        self.assertEqual(self.poll(did, secret, REMOTE_ADDR='192.168.0.4').status_code, 200)

    def test_a_poll_marks_the_computer_online_and_records_its_models(self):
        m = self.m
        did, secret, nid = self.enrol()
        self.assertFalse(m._n102_relay_online(did))
        r = self.poll(did, secret, models=['qwen3:8b', 'llama3.2:3b', 5, None])
        self.assertEqual(r.get_json(), {'ok': True, 'job': None})
        self.assertTrue(m._n102_relay_online(did))
        self.assertEqual(m._N102_RELAY[did]['models'], ['qwen3:8b', 'llama3.2:3b'])
        self.assertEqual(m._N102_RELAY[did]['version'], '102.0')
        m._N102_RELAY[did]['poll'] -= 50
        self.assertFalse(m._n102_relay_online(did), 'silent for 45 seconds means offline')

    def test_a_question_goes_to_its_computer_only_and_the_answer_comes_back(self):
        m = self.m
        did, secret, nid = self.enrol()
        odid, osecret, _ = self.enrol('other')
        self.poll(did, secret)
        self.poll(odid, osecret)
        node = [n for n in m._n102_nodes(fresh=True) if n['id'] == nid][0]
        box = {}

        def ask():
            try:
                box['res'] = m._n102_chat_relay(node, 'qwen3:8b', [{'role': 'user', 'content': 'a secret question'}], 300, 0.4, 20)
            except Exception as exc:                                   # pragma: no cover
                box['err'] = exc
        t = threading.Thread(target=ask)
        t.start()
        time.sleep(0.3)
        r = self.poll(odid, osecret)
        self.assertIsNone(r.get_json()['job'], 'another computer is not given the question')
        job = self.poll(did, secret, wait=3).get_json()['job']
        self.assertEqual(job['messages'], [{'role': 'user', 'content': 'a secret question'}])
        self.assertEqual((job['model'], job['max_tokens']), ('qwen3:8b', 300))
        self.assertFalse(self.answer(odid, osecret, job['id']).get_json()['ok'], 'another computer cannot answer it')
        self.assertTrue(self.answer(did, secret, job['id'], 'the reply').get_json()['ok'])
        t.join(10)
        self.assertEqual(box['res']['text'], 'the reply')
        self.assertEqual((box['res']['tokens'], box['res']['eval_ms']), (12, 1200))
        self.assertEqual(m._N102_JOBS, {}, 'nothing is kept after the answer')
        self.assertFalse(self.answer(did, secret, job['id']).get_json()['ok'], 'a second answer to the same question is ignored')

    def test_a_computer_that_reports_a_failure_is_a_failure(self):
        m = self.m
        did, secret, nid = self.enrol()
        self.poll(did, secret)
        node = [n for n in m._n102_nodes(fresh=True) if n['id'] == nid][0]
        box = {}

        def ask():
            try:
                m._n102_chat_relay(node, 'qwen3:8b', [{'role': 'user', 'content': 'x'}], 100, 0.4, 20)
            except m._N102Fail as exc:
                box['err'] = exc
        t = threading.Thread(target=ask)
        t.start()
        job = self.poll(did, secret, wait=3).get_json()['job']
        self.answer(did, secret, job['id'], '', ok=False)
        t.join(10)
        self.assertEqual(box['err'].code, 'relay_error')
        self.assertIn('broken', box['err'].detail)

    def test_a_question_nobody_picks_up_times_out_and_is_removed(self):
        m = self.m
        did, secret, nid = self.enrol()
        self.poll(did, secret)
        node = [n for n in m._n102_nodes(fresh=True) if n['id'] == nid][0]
        with self.assertRaises(m._N102Fail) as cm:
            m._n102_chat_relay(node, 'qwen3:8b', [{'role': 'user', 'content': 'x'}], 100, 0.4, 1.2)
        self.assertEqual(cm.exception.code, 'relay_did_not_pick_up')
        self.assertEqual(m._N102_JOBS, {})

    def test_a_question_taken_but_never_answered_times_out(self):
        m = self.m
        did, secret, nid = self.enrol()
        self.poll(did, secret)
        node = [n for n in m._n102_nodes(fresh=True) if n['id'] == nid][0]
        box = {}

        def ask():
            try:
                m._n102_chat_relay(node, 'qwen3:8b', [{'role': 'user', 'content': 'x'}], 100, 0.4, 1.5)
            except m._N102Fail as exc:
                box['err'] = exc
        t = threading.Thread(target=ask)
        t.start()
        self.assertIsNotNone(self.poll(did, secret, wait=3).get_json()['job'])
        t.join(10)
        self.assertEqual(box['err'].code, 'timeout')

    def test_an_offline_computer_is_not_asked(self):
        m = self.m
        did, secret, nid = self.enrol()
        node = [n for n in m._n102_nodes(fresh=True) if n['id'] == nid][0]
        with self.assertRaises(m._N102Fail) as cm:
            m._n102_chat_relay(node, 'qwen3:8b', [{'role': 'user', 'content': 'x'}], 100, 0.4, 5)
        self.assertEqual(cm.exception.code, 'relay_offline')

    def test_only_a_few_long_polls_at_a_time(self):
        m = self.m
        did, secret, _nid = self.enrol()
        m._N102_POLLING['n'] = m._N102_MAX_POLLERS
        t0 = time.time()
        r = self.poll(did, secret, wait=15)
        self.assertLess(time.time() - t0, 2)
        self.assertIsNone(r.get_json()['job'])
        self.assertEqual(m._N102_POLLING['n'], m._N102_MAX_POLLERS, 'the count is restored')

    def test_nothing_about_a_question_is_ever_written_to_disk(self):
        m = self.m
        did, secret, nid = self.enrol()
        self.poll(did, secret)
        node = [n for n in m._n102_nodes(fresh=True) if n['id'] == nid][0]
        secret_text = 'ZEBRA-SECRET-QUESTION-12345'
        box = {}

        def ask():
            box['res'] = m._n102_chat_relay(node, 'qwen3:8b', [{'role': 'user', 'content': secret_text}], 100, 0.4, 20)
        t = threading.Thread(target=ask)
        t.start()
        job = self.poll(did, secret, wait=3).get_json()['job']
        self.answer(did, secret, job['id'], 'ZEBRA-SECRET-ANSWER-67890')
        t.join(10)
        found = []
        for root, _d, files in os.walk(self.tmp.name):
            for f in files:
                try:
                    raw = open(os.path.join(root, f), 'rb').read()
                except OSError:
                    continue
                if b'ZEBRA-SECRET' in raw:
                    found.append(f)
        self.assertEqual(found, [])


@needs_flask
class TestEnrolment(RelayCase):
    def test_a_hearth_token_makes_a_hearth_computer_and_links_its_entry(self):
        m = self.m
        did, secret, nid = self.enrol()
        dev = m._device_load()['devices'][did]
        self.assertTrue(dev['hearth'])
        node = [n for n in m._n102_nodes(fresh=True) if n['id'] == nid][0]
        self.assertEqual((node['device_id'], node['kind']), (did, 'relay'))

    def test_an_ordinary_token_is_unchanged(self):
        m = self.m
        did, secret, nid = self.enrol('phone', hearth=False)
        self.assertNotIn('hearth', m._device_load()['devices'][did])
        self.assertIsNone(nid)

    def test_a_token_works_once_and_expires(self):
        m = self.m
        nid, nname = m._n102_node_add('relay', 'laptop')
        tok = m._n102_enroll_token(nname, nid)
        r1 = self.http.post('/api/device/enroll', json={'token': tok, 'name': 'laptop'})
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(self.http.post('/api/device/enroll', json={'token': tok, 'name': 'laptop'}).status_code, 403)
        nid2, nname2 = m._n102_node_add('relay', 'old')
        tok2 = m._n102_enroll_token(nname2, nid2)
        with m._DEVICE_LOCK:
            db = m._device_load()
            db['enroll'][tok2]['expires'] = time.time() - 5
            m._device_save(db)
        self.assertEqual(self.http.post('/api/device/enroll', json={'token': tok2, 'name': 'old'}).status_code, 403)
        self.assertEqual([n for n in m._n102_nodes(fresh=True) if n['id'] == nid2][0]['device_id'], '')

    def test_removing_the_computer_cancels_its_key(self):
        m = self.m
        did, secret, nid = self.enrol()
        self.poll(did, secret)
        self.assertTrue(self.route('local brain remove laptop'))
        self.assertEqual(m._n102_nodes(fresh=True), [])
        self.assertTrue(m._device_load()['devices'][did]['revoked'])
        self.assertEqual(self.poll(did, secret).status_code, 403)
        self.assertNotIn(did, m._N102_RELAY)


@needs_flask
class TestTheRealRelayScript(RelayCase):
    """The script text the owner is sent, executed here against the real website (served on the loopback address) and a fake Ollama."""

    def setUp(self):
        super().setUp()
        from werkzeug.serving import make_server
        self.server = make_server('127.0.0.1', 0, self.app, threaded=True)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.addCleanup(self.server.shutdown)
        self.base = 'http://127.0.0.1:%d' % self.server.server_address[1]
        self.stop = threading.Event()

    def load_script(self, base=None, token=None, ollama=None):
        m = self.m
        nid, nname = m._n102_node_add('relay', 'laptop')
        tok = token or m._n102_enroll_token(nname, nid)
        code = m._n102_relay_script(base or self.base, tok, nname)
        ns = {'__name__': 'hearth_relay_test'}
        exec(compile(code, 'hearth_relay.py', 'exec'), ns)
        ns['STATE'] = os.path.join(self.tmp.name, 'hearth_state.json')
        ns['OLLAMA'] = ollama or self.srv.url
        return ns, nid

    def run_relay(self, ns):
        st = ns['enroll']()

        def loop():
            while not self.stop.is_set():
                try:
                    ns['step'](st, wait=1)
                except Exception:
                    time.sleep(0.2)
        t = threading.Thread(target=loop, daemon=True)
        t.start()
        self.addCleanup(lambda: (self.stop.set(), t.join(5)))
        return st

    def test_end_to_end_a_question_reaches_the_model_on_the_computer_and_the_answer_comes_back(self):
        m = self.m
        ns, nid = self.load_script()
        st = self.run_relay(ns)
        for _ in range(60):
            if m._n102_relay_online(st['device_id']):
                break
            time.sleep(0.1)
        self.assertTrue(m._n102_relay_online(st['device_id']))
        self.srv.reply = lambda body: 'The fox is brown.'
        out = m._n102_generate(answer_msgs('what colour is the fox'), timeout=30)
        self.assertTrue(out['ok'], out)
        self.assertEqual((out['text'], out['model'], out['node_name']), ('The fox is brown.', 'qwen3:8b', 'laptop'))
        self.assertEqual(out['tps'], 10.0)
        asked = self.srv.chats()[-1]
        self.assertEqual(asked['model'], 'qwen3:8b')
        self.assertTrue(asked['messages'][-1]['content'].startswith('what colour is the fox'))
        self.assertEqual(asked['options']['num_ctx'], 6144)
        self.assertEqual(os.stat(ns['STATE']).st_mode & 0o077, 0, 'the key file is private to the user')
        with open(ns['STATE']) as f:
            self.assertEqual(json.load(f)['device_id'], st['device_id'])

    def test_a_model_the_computer_does_not_have_is_reported_not_guessed(self):
        m = self.m
        ns, nid = self.load_script()
        st = ns['enroll']()
        res = ns['chat']({'id': 'H1', 'model': 'missing:7b', 'messages': [{'role': 'user', 'content': 'x'}]}, ['qwen3:8b'])
        self.assertFalse(res['ok'])
        self.assertIn('not installed', res['error'])
        self.assertEqual(self.srv.chats(), [])
        bad = ns['chat']({'id': 'H2', 'model': 'qwen3:8b', 'messages': [{'role': 'tool', 'content': 'x'}, {'role': 'user', 'content': 5}]}, ['qwen3:8b'])
        self.assertEqual((bad['ok'], bad['error']), (False, 'no messages'))
        self.assertTrue(st['device_id'])

    def test_the_job_cannot_change_where_the_script_connects_or_what_it_runs(self):
        ns, nid = self.load_script()
        ns['enroll']()
        job = {'id': 'H3', 'model': 'qwen3:8b', 'url': 'http://evil.example.com', 'path': '/api/delete', 'command': 'rm -rf /', 'max_tokens': 999999, 'temperature': 99,
               'messages': [{'role': 'user', 'content': 'x' * 100000}]}
        res = ns['chat'](job, ['qwen3:8b'])
        self.assertTrue(res['ok'])
        asked = self.srv.chats()[-1]
        self.assertEqual(asked['options']['num_predict'], 2000)
        self.assertEqual(asked['options']['temperature'], 1.5)
        self.assertEqual(len(asked['messages'][0]['content']), 30000)
        self.assertEqual([p for (mth, p, b) in self.srv.requests], ['/api/chat'])

    def test_the_script_refuses_plain_http_to_a_public_address_and_a_model_server_that_is_not_this_computer(self):
        m = self.m
        nid, nname = m._n102_node_add('relay', 'x')
        code = m._n102_relay_script('http://nemo.example.com', 'tok', nname)
        with self.assertRaises(SystemExit) as cm:
            exec(compile(code, 'r.py', 'exec'), {'__name__': 't'})
        self.assertIn('plain http', str(cm.exception))
        code = m._n102_relay_script('https://nemo.example.com', 'tok', nname)
        with mock.patch.dict(os.environ, {'OLLAMA_URL': 'http://8.8.8.8:11434'}):
            with self.assertRaises(SystemExit) as cm:
                exec(compile(code, 'r.py', 'exec'), {'__name__': 't'})
        self.assertIn('this computer', str(cm.exception))
        exec(compile(m._n102_relay_script('https://nemo.example.com', 'tok', nname), 'r.py', 'exec'), {'__name__': 't'})
        exec(compile(m._n102_relay_script('http://100.64.0.9:8090', 'tok', nname), 'r.py', 'exec'), {'__name__': 't'})

    def test_the_script_cannot_listen_run_commands_or_evaluate_text(self):
        code = self.m._n102_relay_script('https://nemo.example.com', 'tok', 'n')
        tree = ast.parse(code)
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name.split('.')[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add((node.module or '').split('.')[0])
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, ('eval', 'exec', 'compile', '__import__', 'open_url'), node.func.id)
        self.assertEqual(names - {'json', 'os', 'platform', 'sys', 'time', 'urllib', 'ipaddress'}, set())
        for bad in ('socket', 'subprocess', 'os.system', 'popen', '.listen(', 'http.server', 'flask', 'shell=True'):
            self.assertNotIn(bad, code, bad)

    def test_the_setup_command_sends_this_script_with_a_one_time_code_for_a_fresh_node(self):
        m = self.m
        self.assertTrue(self.route('set up local brain on my laptop'))
        self.assertEqual(len(self.docs), 1)
        _cid, filename, code = self.docs[0]
        self.assertEqual(filename, 'nemo_hearth_relay.py')
        self.assertIn("BASE = 'https://nemo.example.com'.rstrip('/')", code)
        tok = re.search(r"ENROLL = '([^']+)'", code).group(1)
        self.assertGreater(len(tok), 16)
        db = m._device_load()
        self.assertTrue(db['enroll'][tok]['hearth'])
        self.assertAlmostEqual(db['enroll'][tok]['expires'] - db['enroll'][tok]['created'], 900, delta=5)
        nodes = m._n102_nodes(fresh=True)
        self.assertEqual([(n['kind'], n['name'], n['device_id']) for n in nodes], [('relay', 'laptop', '')])
        said = self.said()
        self.assertIn('ollama pull qwen3:8b', said)
        self.assertIn('opens no port', said)
        self.assertNotIn(tok, said, 'the code travels only in the file')
        self.assertFalse(os.path.exists(os.path.join(__import__('tempfile').gettempdir(), 'nemo_hearth_relay.py')), 'the temporary file is removed')

    def test_setup_needs_a_secure_address_and_changes_nothing_without_one(self):
        m = self.m
        self.start(m, 'WEBCFG', dict(m.WEBCFG, public_url='http://1.2.3.4:8090'))
        self.assertTrue(self.route('local brain setup'))
        self.assertEqual(self.docs, [])
        self.assertEqual(m._n102_nodes(fresh=True), [])
        self.assertEqual(m._device_load().get('enroll', {}), {})
        self.assertIn('/setdomain', self.said())


# ===================================================================================================================
# 4. THE GATEWAY: WHEN THE LOCAL BRAIN IS USED
# ===================================================================================================================
class TestTheGateway(HearthCase):
    def call(self, msgs=None, role='chat', cid=OWNER_ID, timeout=30):
        return self.m._n73_request(cid, role, msgs or answer_msgs(), timeout=timeout)

    def test_nothing_connected_means_nothing_changes(self):
        r = self.call()
        self.assertEqual(r['text'], 'cloud answer')
        self.assertEqual(len(self.cloud.calls), 1)
        self.cloud.behave = lambda *a: self.m._N73Error('http_429')
        with self.assertRaises(self.m._N73Error):
            self.call()

    def test_auto_mode_asks_the_cloud_first_and_leaves_the_local_brain_alone_when_it_answers(self):
        self.add_direct()
        self.assertEqual(self.call()['text'], 'cloud answer')
        self.assertEqual(self.srv.chats(), [])
        self.assertEqual(self.sent, [])

    def test_when_the_cloud_fails_the_local_brain_answers_with_a_receipt_and_one_notice(self):
        m = self.m
        self.add_direct()
        self.cloud.behave = lambda *a: m._N73Error('http_429')
        self.srv.reply = lambda body: 'Once upon a time there was a fox.'
        r = self.call()
        self.assertEqual((r['text'], r['provider'], r['model']), ('Once upon a time there was a fox.', 'local', 'qwen3:8b'))
        self.assertEqual(len(self.cloud.calls), 1)
        self.assertEqual(len(self.sent), 1)
        self.assertIn('cloud brains are not answering', self.sent[0][1])
        self.assertIn('qwen3:8b on box', self.sent[0][1])
        self.assertEqual(self.call()['provider'], 'local')
        self.assertEqual(len(self.sent), 1, 'one notice per outage, not one per answer')
        self.assertEqual((m._N102_STATS['answers'], m._N102_STATS['fallbacks']), (2, 2))
        rows = m._n102_q("SELECT provider, model, ok FROM brain73_calls WHERE provider='local' ORDER BY id")
        self.assertEqual([tuple(x) for x in rows], [('local', 'qwen3:8b', 1), ('local', 'qwen3:8b', 1)])

    def test_the_notice_can_be_switched_off(self):
        m = self.m
        self.add_direct()
        m._n102_put('notice', 'off')
        self.cloud.behave = lambda *a: m._N73Error('http_500')
        self.assertEqual(self.call()['provider'], 'local')
        self.assertEqual(self.sent, [])

    def test_reasoning_calls_may_also_fall_back(self):
        m = self.m
        nid = self.add_direct()
        m._N102_STATE[nid] = {'tps': 50.0, 'models': ['qwen3:8b'], 'api': 'ollama', 'fail': 0, 't': time.time()}
        self.cloud.behave = lambda *a: m._N73Error('http_500')
        self.assertEqual(self.call(role='reason')['provider'], 'local')
        self.assertEqual(self.srv.chats()[-1]['options']['num_predict'], 900)

    def test_a_refusal_a_cancellation_or_an_exhausted_budget_are_not_handed_to_the_local_brain(self):
        m = self.m
        self.add_direct()
        for code in ('provider_refusal', 'cancelled', 'time_budget_exhausted', 'input_too_large', 'text_context_too_large', 'unsupported_input'):
            self.cloud.behave = lambda *a, code=code: m._N73Error(code)
            with self.assertRaises(m._N73Error, msg=code) as cm:
                self.call()
            self.assertEqual(cm.exception.code, code)
        self.assertEqual(self.srv.chats(), [])

    def test_the_fallback_can_be_switched_off(self):
        m = self.m
        self.add_direct()
        m._n102_put('fallback', 'off')
        self.cloud.behave = lambda *a: m._N73Error('http_500')
        with self.assertRaises(m._N73Error):
            self.call()
        self.assertEqual(self.srv.chats(), [])

    def test_helper_steps_that_need_strict_json_never_use_the_local_brain(self):
        m = self.m
        self.add_direct()
        self.cloud.behave = lambda *a: m._N73Error('http_500')
        helper = [{'role': 'system', 'content': m._N83_HELPER_SYSTEM}, {'role': 'user', 'content': 'Return ONLY JSON {"a":1}'}]
        with self.assertRaises(m._N73Error):
            self.call(helper)
        self.assertEqual(self.srv.chats(), [])

    def test_pictures_the_code_writer_and_connection_tests_pass_straight_through(self):
        m = self.m
        self.add_direct()
        pic = [{'role': 'user', 'content': [{'type': 'text', 'text': 'what is this'}, {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,AAAA'}}]}]
        self.assertEqual(self.call(pic)['text'], 'cloud answer')
        self.assertEqual(self.call(role='code')['text'], 'cloud answer')
        r = m._n73_request(OWNER_ID, 'chat', answer_msgs(), timeout=10, _probe=True)
        self.assertEqual(r['text'], 'cloud answer')
        self.cloud.behave = lambda *a: m._N73Error('http_500')
        with self.assertRaises(m._N73Error):
            self.call(pic)
        with self.assertRaises(m._N73Error):
            m._n73_request(OWNER_ID, 'chat', answer_msgs(), timeout=10, _probe=True)
        self.assertEqual(self.srv.chats(), [])

    def test_only_the_owner_gets_it(self):
        m = self.m
        self.add_direct()
        self.cloud.behave = lambda *a: m._N73Error('http_500')
        with self.assertRaises(m._N73Error):
            self.call(cid=5552)
        m.OWNER['id'] = None
        with self.assertRaises(m._N73Error):
            self.call(cid=None)
        self.assertEqual(self.srv.chats(), [])

    def test_if_the_local_brain_cannot_answer_the_original_failure_stands(self):
        m = self.m
        self.srv.status = 500
        self.add_direct()
        self.cloud.behave = lambda *a: m._N73Error('http_429')
        with self.assertRaises(m._N73Error) as cm:
            self.call()
        self.assertEqual(cm.exception.code, 'http_429')
        self.assertEqual(self.sent, [], 'no notice about an answer that did not come')
        rows = m._n102_q("SELECT ok, error FROM brain73_calls WHERE provider='local'")
        self.assertEqual([r[0] for r in rows], [0])

    def test_no_time_left_means_no_local_attempt(self):
        m = self.m
        self.add_direct()
        self.cloud.behave = lambda *a: m._N73Error('http_429')
        with mock.patch.object(m, '_n86_budget', lambda: type('B', (), {'remaining': lambda s: 4.0})()):
            with self.assertRaises(m._N73Error):
                self.call(timeout=60)
        self.assertEqual(self.srv.chats(), [])

    def test_simple_questions_first_is_off_by_default_and_an_opt_in(self):
        m = self.m
        self.add_direct()
        self.assertEqual(self.call(answer_msgs('what does serendipity mean'))['text'], 'cloud answer')
        m._n102_put('first_simple', 'on')
        self.srv.reply = lambda body: 'A happy accident.'
        r = self.call(answer_msgs('what does serendipity mean'))
        self.assertEqual((r['text'], r['provider']), ('A happy accident.', 'local'))
        self.assertEqual(len(self.cloud.calls), 1, 'the cloud was not asked the second time')
        self.assertEqual(self.sent, [], 'no outage notice for a choice the owner made')
        self.assertEqual(self.call(answer_msgs('what is the nifty price today'))['text'], 'cloud answer')
        self.srv.status = 500
        self.assertEqual(self.call(answer_msgs('what does serendipity mean'))['text'], 'cloud answer', 'a failing local brain falls back to the cloud')

    def test_offline_mode_never_asks_the_cloud(self):
        m = self.m
        self.add_direct()
        m._n102_put('mode', 'offline')
        self.cloud.behave = lambda *a: AssertionError('the cloud must not be asked')
        r = self.call()
        self.assertEqual(r['provider'], 'local')
        self.assertEqual(self.cloud.calls, [])
        with self.assertRaises(m._N73Error) as cm:
            self.call([{'role': 'system', 'content': m._N83_HELPER_SYSTEM}, {'role': 'user', 'content': 'x'}])
        self.assertEqual(cm.exception.code, 'local_only_helper_skipped')
        self.assertEqual(m._N102_STATS['helpers_skipped'], 1)
        self.srv.status = 500
        with self.assertRaises(m._N73Error) as cm:
            self.call()
        self.assertEqual(cm.exception.code, 'local_brain_unavailable')
        self.assertIn('local_brain_unavailable', m._N991_REFUSE, 'v99.1 does not hand the question to the older cloud chain')
        self.assertEqual(self.cloud.calls, [])

    def test_the_older_gateway_wrapper_turns_an_offline_refusal_into_a_plain_message_not_a_cloud_call(self):
        m = self.m
        self.add_direct()
        m._n102_put('mode', 'offline')
        self.srv.status = 500
        self.cloud.behave = lambda *a: AssertionError('the cloud must not be asked')
        out = m._n73_core_reply(OWNER_ID, 'hello', answer_msgs('hello'), timeout=20)
        self.assertTrue(str(out).startswith('I could not complete this answer (local_brain_unavailable)'), out)
        self.assertEqual(self.cloud.calls, [])

    def test_the_older_gateway_path_gets_the_local_answer_too(self):
        m = self.m
        self.add_direct()
        self.cloud.behave = lambda *a: m._N73Error('http_500')
        self.srv.reply = lambda body: 'Local words.'
        out = m._n73_core_reply(OWNER_ID, 'hello', answer_msgs('hello'), timeout=20)
        self.assertEqual(out, 'Local words.')


class TestAConversationTurn(HearthCase):
    """The real Cortex conversation: every cloud call fails; the helper steps degrade as they always did, and the reply comes from the local brain."""

    def test_the_owner_still_gets_an_answer_when_every_cloud_call_fails(self):
        m = self.m
        self.add_direct()
        self.cloud.behave = lambda *a: m._N73Error('http_500')
        self.srv.reply = lambda body: 'Your wife is called Hetvi.'
        m._n35_set_fact(self.cid, 'wife', 'Hetvi')
        out = m._n83_chat(self.owner_msg("what is my wife's name?"))
        self.assertTrue(out and out.get('ok'), out)
        self.assertIn('Hetvi', out['text'])
        sent = self.srv.chats()[-1]['messages']
        self.assertIn('wife: Hetvi', sent[0]['content'], 'the owner\'s memory block travels to his own computer')
        self.assertIn("Nemo's local brain", sent[0]['content'])
        for call in self.cloud.calls:
            self.assertIn(call['cid'], (OWNER_ID,))

    def test_offline_mode_runs_a_whole_turn_without_one_cloud_call(self):
        m = self.m
        self.add_direct()
        m._n102_put('mode', 'offline')
        self.cloud.behave = lambda *a: AssertionError('the cloud must not be asked')
        self.srv.reply = lambda body: 'Fine, thanks.'
        out = m._n83_chat(self.owner_msg('how are you doing today, my friend?'))
        self.assertEqual(self.cloud.calls, [])
        self.assertTrue(out and 'Fine, thanks.' in out['text'], out)


# ===================================================================================================================
# 5. THE OLDER CHAIN (ask_ai) IS LEFT ALONE: ITS ANSWERS PASS THROUGH THE GATEWAY
# ===================================================================================================================
class TestTheOlderChain(HearthCase):
    """v51's explicit-model contract needs ask_ai to stay the v69 function, so Hearth does not wrap it. The older chain is covered because the owner's answers go through the gateway first."""

    def setUp(self):
        super().setUp()
        self.start(self.m, '_n54_human_contract', lambda cid, text: ('', {}))       # the older chain keeps its conversation settings in tables that the shared fixture's fresh database does not have

    def test_ask_ai_is_not_wrapped(self):
        m = self.m
        self.assertNotIn('def ask_ai', hearth_source())
        self.assertFalse(any(n.lower().startswith('_n102') for n in m.ask_ai.__code__.co_names))
        self.assertIn('v51-explicit-model-override-authoritative', [t['name'] for t in m.prime_regression_suite()['tests'] if t['ok']])

    def test_a_cloud_failure_still_ends_in_a_local_answer_through_ask_ai(self):
        m = self.m
        self.add_direct()
        self.cloud.behave = lambda *a: m._N73Error('http_500')
        self.srv.reply = lambda body: 'Local words.'
        m.HISTORY.pop(OWNER_ID, None)
        out = m.ask_ai(OWNER_ID, 'what animal is orange and sly')
        self.assertEqual(out, 'Local words.')
        h = m.HISTORY[OWNER_ID]
        self.assertEqual(h[-1]['content'], 'Local words.')
        self.assertIn('what animal is orange and sly', h[-2]['content'])
        self.assertEqual(len(self.sent), 1)
        self.assertIn('cloud brains are not answering', self.sent[0][1])

    def test_offline_mode_answers_ask_ai_without_one_cloud_call(self):
        m = self.m
        self.add_direct()
        m._n102_put('mode', 'offline')
        self.cloud.behave = lambda *a: AssertionError('the cloud must not be asked')
        self.srv.reply = lambda body: 'Offline words.'
        self.assertEqual(m.ask_ai(OWNER_ID, 'hello there'), 'Offline words.')
        self.assertEqual(self.cloud.calls, [])
        self.assertEqual(self.sent, [], 'no outage notice in a mode the owner chose')
        self.srv.status = 500
        out = m.ask_ai(OWNER_ID, 'hello again')
        self.assertTrue(out.startswith('I could not complete this answer (local_brain_unavailable)'), out)
        self.assertEqual(self.cloud.calls, [])

    def test_a_good_cloud_answer_is_left_alone(self):
        self.add_direct()
        self.assertEqual(self.m.ask_ai(OWNER_ID, 'hello'), 'cloud answer')
        self.assertEqual(self.srv.chats(), [])

    def test_other_people_never_get_the_local_brain(self):
        m = self.m
        self.add_direct()
        m.OWNER['id'] = 777
        self.cloud.behave = lambda *a: m._N73Error('http_500')
        out = m.ask_ai(5552, 'hello')                                      # a family member, as before: the cloud chain only
        self.assertEqual(self.srv.chats(), [])
        self.assertNotEqual(out, 'Hello from the local brain.')


# ===================================================================================================================
# 6. "PRIVATE: ..."
# ===================================================================================================================
class TestPrivate(HearthCase):
    def setUp(self):
        super().setUp()
        self.add_direct()
        self.srv.reply = lambda body: 'Private reply.'

    def tripwire(self):
        """Any network address except the local model's, any cloud gateway, any older AI chain: fails the test."""
        m, srv = self.m, self.srv
        real = requests.request

        def guard(method, url, *a, **k):
            if not str(url).startswith(srv.url):
                raise AssertionError('left the building: %s' % url)
            return real(method, url, *a, **k)
        self.start(requests, 'request', guard)
        for name in ('get', 'post', 'put', 'head', 'delete', 'patch'):
            self.start(requests, name, lambda url, *a, **k: (_ for _ in ()).throw(AssertionError('left the building: %s' % url)))
        self.start(m, '_N102_REQ_PREV', lambda *a, **k: (_ for _ in ()).throw(AssertionError('the cloud gateway was asked')))
        self.start(m, 'ask_ai', lambda *a, **k: (_ for _ in ()).throw(AssertionError('the cloud chain was asked')))
        for fn in ('groq_chat', 'cerebras_chat', 'gemini_chat', 'claude_chat', 'web_search'):
            self.start(m, fn, lambda *a, **k: (_ for _ in ()).throw(AssertionError('a cloud brain or a search was asked')))

    def test_a_private_question_is_answered_by_the_local_brain_alone(self):
        m = self.m
        self.tripwire()
        self.assertTrue(self.route('private: what should I give my wife for our anniversary'))
        self.assertEqual(len(self.srv.chats()), 1)
        self.assertIn('anniversary', self.srv.chats()[-1]['messages'][-1]['content'])
        said = self.said()
        self.assertIn('🔒 Private reply.', said)
        self.assertIn('answered on your own computer', said)
        self.assertIn('nothing left it', said)
        self.assertEqual(m._N102_STATS['privates'], 1)

    def test_it_works_through_the_real_front_door_and_never_reaches_the_ordinary_chat(self):
        m = self.m
        self.tripwire()
        passed = self.passthrough()
        m.handle(self.owner_msg('Private - what do I owe my cousin'))
        self.assertEqual(passed, [])
        self.assertIn('Private reply.', self.said())

    def test_all_the_ways_of_asking(self):
        for form in ('private: q1', 'Private - q2', 'privately: q3', 'locally: q4', 'local: q5', '/private q6', 'ask locally: q7', 'keep this private: q8', 'PRIVATE:   q9  '):
            n = len(self.srv.chats())
            self.assertTrue(self.route(form), form)
            self.assertEqual(len(self.srv.chats()), n + 1, form)
        self.assertTrue(self.srv.chats()[-1]['messages'][-1]['content'].startswith('q9'))

    def test_the_word_alone_or_an_ordinary_sentence_is_not_a_private_question(self):
        for t in ('private', 'private:', 'the private equity fund is up', 'local brain', 'this is private: not for you'):
            n = len(self.srv.chats())
            self.route(t)
            self.assertEqual(len(self.srv.chats()), n, t)

    def test_not_for_other_people_and_not_in_a_group(self):
        m = self.m
        passed = self.passthrough()
        guest = {'chat': {'id': 5552, 'type': 'private'}, 'from': {'id': 5552}, 'text': 'private: hello', 'message_id': 1}
        m.handle(guest)
        group = {'chat': {'id': -100123, 'type': 'group'}, 'from': {'id': OWNER_ID}, 'text': 'private: hello', 'message_id': 1}
        m.handle(group)
        self.assertEqual(len(passed), 2)
        self.assertEqual(self.srv.chats(), [])

    def test_the_private_chat_has_its_own_memory_and_the_shared_history_never_sees_it(self):
        m = self.m
        m.HISTORY[OWNER_ID] = [{'role': 'user', 'content': 'earlier ordinary talk'}, {'role': 'assistant', 'content': 'ok'}]
        before = json.dumps(m.HISTORY[OWNER_ID])
        self.route('private: my secret number is 1234')
        self.route('private: what was my number')
        second = json.dumps(self.srv.chats()[-1]['messages'])
        self.assertIn('my secret number is 1234', second, 'a follow-up sees the private conversation')
        self.assertNotIn('earlier ordinary talk', second, 'but not the shared one')
        self.assertEqual(json.dumps(m.HISTORY[OWNER_ID]), before)
        rows = m._n102_q('SELECT role FROM hearth102_turn ORDER BY id')
        self.assertEqual([r[0] for r in rows], ['user', 'assistant', 'user', 'assistant'])

    def test_the_owners_memory_and_persona_do_go_to_his_own_computer(self):
        m = self.m
        m._n35_set_fact(self.cid, 'wife', 'Hetvi')
        self.route('private: what is my wife called')
        system = self.srv.chats()[-1]['messages'][0]['content']
        self.assertIn('Hetvi', system)
        self.assertIn('Nemo', system)

    def test_forgetting_wipes_the_private_chat(self):
        m = self.m
        self.route('private: remember this')
        self.assertTrue(self.route('forget my private chat'))
        self.assertEqual(m._n102_q('SELECT COUNT(*) FROM hearth102_turn')[0][0], 0)
        self.route('private: again')
        self.assertNotIn('remember this', json.dumps(self.srv.chats()[-1]['messages']))

    def test_the_private_chat_is_kept_short(self):
        m = self.m
        for i in range(30):
            self.route('private: question number %d' % i)
        self.assertLessEqual(m._n102_q('SELECT COUNT(*) FROM hearth102_turn')[0][0], 41)

    def test_no_local_brain_means_no_answer_and_nothing_sent_elsewhere(self):
        m = self.m
        self.tripwire()
        m._n102_set_all(False)
        self.assertTrue(self.route('private: something sensitive'))
        said = self.said()
        self.assertIn('did not answer', said)
        self.assertIn('not sent your question anywhere else'.replace('not sent', 'not sent'), said.replace('have not sent', 'not sent'))
        self.assertEqual(self.srv.chats(), [])

    def test_a_local_brain_that_fails_means_no_answer_and_nothing_sent_elsewhere(self):
        self.tripwire()
        self.srv.status = 500
        self.assertTrue(self.route('private: something sensitive'))
        self.assertIn('Nothing was sent anywhere else', self.said())

    def test_a_private_question_never_triggers_a_search_a_tool_or_the_memory_clerk(self):
        m = self.m
        self.tripwire()
        self.route('private: what is the latest news on the nifty and search the web for it')
        self.assertEqual(len(self.srv.chats()), 1)

    def test_offline_mode_does_not_change_it(self):
        self.m._n102_put('mode', 'offline')
        self.route('private: hello')
        self.assertIn('Private reply.', self.said())


# ===================================================================================================================
# 7. THE WORDS THE OWNER SAYS
# ===================================================================================================================
class TestCommands(HearthCase):
    def test_status_with_nothing_connected_says_how_to_start(self):
        self.assertTrue(self.route('local brain'))
        said = self.said()
        self.assertIn('LOCAL BRAIN', said)
        self.assertIn('Nothing is connected yet', said)
        self.assertIn('local brain setup', said)
        self.assertIn('AUTO', said)

    def test_status_shows_each_computer_with_its_speed(self):
        m = self.m
        nid = self.add_direct()
        m._n102_generate(answer_msgs(), timeout=20)
        self.route('local brain status')
        said = self.said()
        self.assertIn('box', said)
        self.assertIn('ollama', said)
        self.assertIn('qwen3:8b', said)
        self.assertIn('10.0 tokens a second', said)
        self.assertIn('does not cover pictures', said)
        self.assertEqual(m._n102_nodes()[0]['id'], nid)

    def test_status_for_a_relay_that_has_not_connected_says_what_to_do(self):
        self.route('local brain setup')
        self.sent.clear()
        self.route('hearth status')
        said = self.said()
        self.assertIn('waiting for the script', said)
        did, _s, _n = None, None, None

    def test_help_and_the_model_guide(self):
        self.assertTrue(self.route('local brain help'))
        said = self.said()
        for phrase in ('local brain setup', 'private:', 'go offline', 'test local brain'):
            self.assertIn(phrase, said)
        self.sent.clear()
        for q in ('which local model should I use', 'local brain models', 'local brain recommend'):
            self.assertTrue(self.route(q), q)
        said = self.said()
        self.assertIn('qwen3:8b', said)
        self.assertIn('no public Gujarati test', said)
        self.assertIn('no internet', said)

    def test_connecting_a_direct_address(self):
        m = self.m
        self.assertTrue(self.route('local brain connect %s llama3.2:3b' % self.srv.url))
        n = m._n102_nodes(fresh=True)
        self.assertEqual([(x['kind'], x['url'], x['model'], x['api']) for x in n], [('direct', self.srv.url, 'llama3.2:3b', 'ollama')])
        self.assertIn('Connected', self.said())
        self.assertIn('qwen3:8b', self.said())
        self.assertTrue(m._n102_generate(answer_msgs(), timeout=20)['ok'])

    def test_a_bad_or_unreachable_address_saves_nothing(self):
        m = self.m
        for u in ('http://example.com:11434', 'http://169.254.169.254', 'ftp://x'):
            self.route('local brain connect ' + u)
        self.assertEqual(m._n102_nodes(fresh=True), [])
        dead = FakeModelServer().start()
        url = dead.url
        dead.stop()
        self.sent.clear()
        self.route('local brain connect ' + url)
        self.assertEqual(m._n102_nodes(fresh=True), [])
        self.assertIn('Nothing was saved', self.said())

    def test_switching_everything_off_and_on_and_removing_one(self):
        m = self.m
        self.add_direct()
        self.assertTrue(self.route('local brain off'))
        self.assertFalse(m._n102_has_nodes() and m._n102_nodes(True))
        self.assertEqual(m._n102_generate(answer_msgs(), timeout=5)['error'], 'no_local_brain_online')
        self.assertTrue(self.route('local brain on'))
        self.assertTrue(m._n102_generate(answer_msgs(), timeout=10)['ok'])
        self.assertTrue(self.route('remove local brain'))
        self.assertEqual(m._n102_nodes(fresh=True), [])
        self.add_direct(name='a')
        self.add_direct(name='b')
        self.sent.clear()
        self.assertTrue(self.route('remove local brain'))
        self.assertIn('Which one?', self.said())
        self.assertEqual(len(m._n102_nodes(fresh=True)), 2)
        self.route('local brain remove b')
        self.assertEqual([n['name'] for n in m._n102_nodes(fresh=True)], ['a'])

    def test_a_node_name_is_made_unique(self):
        m = self.m
        a = m._n102_node_add('direct', 'box', url=self.srv.url)
        b = m._n102_node_add('direct', 'box', url=self.srv.url)
        self.assertEqual([x['name'] for x in m._n102_nodes(fresh=True)], ['box', 'box-2'])

    def test_choosing_a_model(self):
        m = self.m
        self.assertTrue(self.route('local brain model llama3.1:8b'))
        self.assertEqual(m._n102_get('model'), 'llama3.1:8b')
        self.assertIn('llama3.1:8b', self.said())

    def test_the_timed_test(self):
        m = self.m
        self.add_direct()
        self.srv.reply = lambda body: '42 ok'
        self.assertTrue(self.route('test local brain'))
        said = self.said()
        self.assertIn('✅', said)
        self.assertIn('10.0 tokens a second', said)
        self.assertIn('Arithmetic check: passed', said)
        self.sent.clear()
        self.srv.reply = lambda body: '40 ok'
        self.route('local brain test')
        self.assertIn('Arithmetic check: FAILED', self.said())
        self.assertIn('never trust it with figures', self.said())

    def test_the_timed_test_with_nothing_reachable(self):
        self.route('test local brain')
        self.assertIn('No local brain is connected', self.said())
        self.sent.clear()
        self.add_direct()
        self.srv.status = 500
        self.route('test local brain')
        self.assertIn('did not answer', self.said())

    def test_offline_and_online(self):
        m = self.m
        self.assertTrue(self.route('go offline'))
        self.assertEqual(m._n102_mode(), 'auto', 'nothing to go offline with')
        self.assertIn('Say “local brain setup” first', self.said())
        self.add_direct()
        self.sent.clear()
        self.route('go offline')
        self.assertEqual(m._n102_mode(), 'offline')
        self.assertIn('Offline mode on', self.said())
        self.assertIn('still use the internet', self.said())
        self.route('local brain status')
        self.assertIn('OFFLINE', self.said())
        self.sent.clear()
        self.route('go online')
        self.assertEqual(m._n102_mode(), 'auto')
        self.assertIn('Back online', self.said())

    def test_the_switches(self):
        m = self.m
        self.route('local brain for simple questions on')
        self.assertEqual(m._n102_get('first_simple'), 'on')
        self.route('stop using the local brain for simple questions')
        self.assertEqual(m._n102_get('first_simple'), 'off')
        self.route('use local brain for simple questions')
        self.assertEqual(m._n102_get('first_simple'), 'on')
        self.route('local brain fallback off')
        self.assertFalse(m._n102_fallback_on())
        self.route('local brain fallback on')
        self.assertTrue(m._n102_fallback_on())
        self.route('local brain notices off')
        self.assertEqual(m._n102_get('notice'), 'off')

    def test_setup_phrases(self):
        for phrase in ('set up local brain on my laptop', 'connect my laptop as the local brain'.replace('connect my laptop as the local brain', 'use my laptop as the local brain'), 'local brain setup', 'please setup the local brain', 'enable the local brain on my pc', 'local brain relay home'):
            self.docs.clear()
            self.assertTrue(self.route(phrase), phrase)
            self.assertEqual(len(self.docs), 1, phrase)

    def test_ordinary_sentences_are_left_for_the_rest_of_nemo(self):
        passed = self.passthrough()
        for t in ('what is the weather', 'brain surgery cost', 'how do I set up a local business', 'go offline for a while and rest', 'the home brain of the operation', 'local brains are cool'):
            self.m.handle(self.owner_msg(t))
        self.assertEqual(len(passed), 6)
        self.assertEqual(self.sent, [])

    def test_commands_are_owner_only_private_chat_only(self):
        m = self.m
        passed = self.passthrough()
        m.handle({'chat': {'id': 5552, 'type': 'private'}, 'from': {'id': 5552}, 'text': 'local brain status', 'message_id': 1})
        m.handle({'chat': {'id': -1001, 'type': 'supergroup'}, 'from': {'id': OWNER_ID}, 'text': 'go offline', 'message_id': 1})
        m.handle(self.owner_msg('local brain status', photo=[{'file_id': 'x'}]))
        self.assertEqual(len(passed), 3)
        self.assertEqual(m._n102_mode(), 'auto')

    def test_the_front_door_handles_the_real_message_path(self):
        passed = self.passthrough()
        self.m.handle(self.owner_msg('Hey Nemo, please local brain status'))
        self.assertEqual(passed, [])
        self.assertIn('LOCAL BRAIN', self.said())
        self.assertEqual(self.m._N102_STATS['front_door'], 1)

    def test_a_long_message_is_never_mistaken_for_a_command(self):
        self.assertFalse(self.route('local brain status ' + 'x' * 400))


# ===================================================================================================================
# 8. THE LAYER ITSELF
# ===================================================================================================================
class TestTheLayerItself(HearthCase):
    def test_version_docstring_and_protection(self):
        src = open(base.NEMO_FILE, encoding='utf-8').read()
        self.assertGreaterEqual(float(self.m.VERSION), 102.0)
        self.assertIn('v102.0 - HEARTH', src[:3000])
        self.assertIn("'_n101_','_n102_',", src)
        self.assertEqual(src.count('# NEMO 102 - HEARTH'), 1)

    def test_the_layer_touches_no_order_broker_guard_or_owner_lock(self):
        tree = ast.parse(hearth_source())
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        for bad in ('fyers_place', 'fyers_place_bracket', '_order_send', 'request_order', 'AUTO', 'GUARDS', 'subprocess', 'Popen', 'popen'):
            self.assertNotIn(bad, names, bad)
        called = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                f = n.func
                called.add(f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else '')
        for bad in ('eval', 'exec', '__import__', 'system', 'run', 'check_output', 'check_call', 'Popen'):
            self.assertNotIn(bad, called, bad)
        src = hearth_source()
        for bad in ('save_secret(', 'OWNER[', "OWNER['id'] =", 'bot_secrets', 'api_key', 'groq_key', 'Authorization'):
            if bad == 'Authorization':
                self.assertEqual(src.count(bad), 2, 'only the relay\'s own bearer reading and the script text')
            else:
                self.assertNotIn(bad, src, bad)

    def test_the_layer_calls_no_cloud_ai_itself(self):
        src = hearth_source()
        for fn in ('groq_chat(', 'cerebras_chat(', 'gemini_chat(', 'claude_chat(', 'web_search(', '_n73_core_reply(', 'OR_URL'):
            self.assertNotIn(fn, src, fn)
        tree = ast.parse(src)
        req_calls = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == 'requests']
        self.assertEqual(len(req_calls), 1, 'one network call site in the whole layer: the model-server call')

    def test_it_writes_only_its_own_tables_and_the_device_store(self):
        src = hearth_source()
        tables = set(re.findall(r'(?:INSERT (?:OR REPLACE )?INTO|UPDATE|DELETE FROM|CREATE TABLE IF NOT EXISTS)\s+(\w+)', src))
        self.assertEqual(tables, {'hearth102_setting', 'hearth102_node', 'hearth102_turn'})

    def test_the_hooks_are_installed_and_unchanged_behaviour_is_kept_for_everyone_else(self):
        m = self.m
        self.assertIsNot(m.handle, m._N102_HANDLE_PREV)
        self.assertIsNot(m.build_web_app, m._N102_BUILD_PREV)
        self.assertIsNot(m._device_enroll_claim, m._N102_CLAIM_PREV)
        self.assertIsNot(base.ORIG_N73_REQUEST, m._N102_REQ_PREV)

    def test_the_regression_rows_all_pass(self):
        rows = self.m._n102_regression_rows()
        self.assertGreaterEqual(len(rows), 9)
        failed = [r['name'] for r in rows if not r['ok']]
        self.assertEqual(failed, [])
        suite = self.m.prime_regression_suite()
        self.assertTrue([r for r in suite['tests'] if r['name'].startswith('v102-')])

    def test_the_capabilities_text_mentions_it(self):
        self.assertIn('Hearth 102', self.m._n82_capabilities())

    def test_the_status_text_never_contains_a_key_or_a_token(self):
        m = self.m
        self.route('local brain setup')
        tok = re.search(r"ENROLL = '([^']+)'", self.docs[0][2]).group(1)
        self.route('local brain status')
        self.assertNotIn(tok, self.said())


if __name__ == '__main__':
    unittest.main()
