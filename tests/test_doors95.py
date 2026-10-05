"""Nemo v95 Doors: the website's login, limits, headers and switches.

Offline. The website is built for real with Flask's test client (the tests skip when Flask is not installed); Telegram's signature is made in the test with its own copy of the documented algorithm, so the bot's check
is compared with an independent implementation. Nothing here uses the network, the broker or an order.

    NEMO_FILE=/path/to/nemotron_bot.py python -m unittest tests.test_doors95 -v
"""
import hashlib
import hmac
import json
import re
import sys
import time
import types
import unittest
import urllib.parse
from unittest import mock

from tests import test_cortex83 as base
from tests.test_scout93 import ScoutCase
from tests.test_forge91 import OWNER_ID

try:
    import flask  # noqa: F401
    HAVE_FLASK = True
except Exception:                                   # pragma: no cover
    HAVE_FLASK = False
needs_flask = unittest.skipUnless(HAVE_FLASK, 'Flask is not installed')

TOKEN = 'a1b2c3d4e5f60718293a4b5c6d7e8f90'            # a 128-bit key
BOT = '123456:TEST-TOKEN-NOT-REAL'


def setUpModule():
    if base.m is None:
        base.setUpModule()


def signed(uid=OWNER_ID, bot=BOT, now=None, extra=None, tamper=None):
    """A Mini App `initData` string signed the documented way (an independent copy of the algorithm)."""
    now = int(now if now is not None else time.time())
    f = {'auth_date': str(now), 'query_id': 'AAHdF6IQ', 'user': json.dumps({'id': uid, 'first_name': 'Asha', 'username': 'asha'}, separators=(',', ':'))}
    f.update(extra or {})
    check = '\n'.join('%s=%s' % (k, f[k]) for k in sorted(f))
    key = hmac.new(b'WebAppData', bot.encode(), hashlib.sha256).digest()
    f['hash'] = hmac.new(key, check.encode(), hashlib.sha256).hexdigest()
    s = urllib.parse.urlencode(f)
    return tamper(s) if tamper else s


class DoorsCase(ScoutCase):
    def setUp(self):
        super().setUp()
        m = self.m
        self.start(m, 'WEBCFG', dict(m.WEBCFG, token=TOKEN, public_url='https://nemo.example.com', port=8090, on=True))
        self.start(m, 'TELEGRAM_TOKEN', BOT)
        self.start(m, 'web_ai', lambda msg: 'echo:' + msg)
        self.saved = {}
        self.start(m, 'save_secret', lambda k, v: self.saved.__setitem__(k, v))
        self.menu = []
        self.start(m, 'tg', lambda method, **kw: self.menu.append((method, kw)) or {'ok': True})
        for d in (m._N95_FAILS, m._N95_BLOCKED, m._N95_HITS, m._N95_SESS):
            d.clear()
        for k in m._N95_STATS:
            m._N95_STATS[k] = 0
        for k in ('strict', 'lock', 'telegram'):
            m._n95_put(k, 'off')
        self.guest = lambda text, **k: dict({'chat': {'id': 5552, 'type': 'private'}, 'from': {'id': 5552, 'first_name': 'Asha'}, 'message_id': 3, 'text': text}, **k)

    def client(self):
        return self.m.build_web_app().test_client()


# ===================================================================================================================
# 1. THE SMALL PIECES
# ===================================================================================================================
class TestKeysAndAddresses(DoorsCase):
    def test_constant_time_compare_matches_only_equal_non_empty_secrets(self):
        eq = self.m._n95_eq
        self.assertTrue(eq('abc123', 'abc123'))
        self.assertFalse(eq('abc123', 'abc124'))
        self.assertFalse(eq('abc123', 'abc12'))
        self.assertFalse(eq('', ''))
        self.assertFalse(eq(None, None))
        self.assertFalse(eq('x', ''))
        self.assertTrue(eq('é–key', 'é–key'))

    def test_it_really_uses_the_constant_time_function(self):
        src = open(base.NEMO_FILE, encoding='utf-8').read()
        i = src.index('def _n95_eq(a, b):')
        self.assertIn('compare_digest', src[i:i + 500])

    def test_the_callers_address_is_the_connection_unless_the_tunnel_on_this_machine_says_otherwise(self):
        class Req:
            def __init__(self, remote, headers):
                self.remote_addr, self.headers = remote, headers
        f = self.m._n95_client_ip
        self.assertEqual(f(Req('8.8.8.8', {})), '8.8.8.8')
        self.assertEqual(f(Req('8.8.8.8', {'CF-Connecting-IP': '1.2.3.4'})), '8.8.8.8', 'a stranger cannot name his own address')
        self.assertEqual(f(Req('127.0.0.1', {'CF-Connecting-IP': '1.2.3.4'})), '1.2.3.4')
        self.assertEqual(f(Req('127.0.0.1', {'X-Forwarded-For': '5.6.7.8, 127.0.0.1'})), '5.6.7.8')
        self.assertEqual(f(Req('::1', {})), '::1')
        self.assertEqual(f(Req(None, {})), '?')

    def test_failed_attempts_block_an_address_for_fifteen_minutes(self):
        m, ip, t = self.m, '9.9.9.9', 1000.0
        for i in range(11):
            self.assertFalse(m._n95_note_fail(ip, t + i, 'guess%d' % i))
        self.assertEqual(m._n95_blocked(ip, t + 12), 0)
        self.assertTrue(m._n95_note_fail(ip, t + 12, 'guess11'))
        self.assertTrue(0 < m._n95_blocked(ip, t + 13) <= 900)
        self.assertEqual(m._n95_blocked(ip, t + 12 + 901), 0, 'the block ends')
        self.assertEqual(m._N95_STATS['blocked'], 1)

    def test_old_failures_are_forgotten(self):
        m, ip = self.m, '9.9.9.9'
        for i in range(11):
            m._n95_note_fail(ip, 100.0 + i, 'g%d' % i)
        self.assertFalse(m._n95_note_fail(ip, 100.0 + 700, 'g99'), 'the first eleven are more than 10 minutes old')

    def test_the_server_itself_is_never_blocked_or_limited(self):
        m = self.m
        for i in range(50):
            self.assertFalse(m._n95_note_fail('127.0.0.1', 5.0))
            self.assertTrue(m._n95_rate_ok('127.0.0.1', 5.0))
        self.assertEqual(m._n95_blocked('127.0.0.1', 5.0), 0)

    def test_the_request_rate_limit(self):
        m, ip = self.m, '7.7.7.7'
        for i in range(240):
            self.assertTrue(m._n95_rate_ok(ip, 10.0 + i * 0.01))
        self.assertFalse(m._n95_rate_ok(ip, 13.0))
        self.assertTrue(m._n95_rate_ok(ip, 10.0 + 61.0), 'a minute later it is fine again')
        self.assertEqual(m._N95_STATS['rate_limited'], 1)

    def test_the_tables_cannot_grow_without_limit(self):
        m = self.m
        for i in range(4500):
            m._n95_note_fail('10.%d.%d.1' % (i // 250, i % 250), 100.0 + i, 'x')
        self.assertLessEqual(len(m._N95_FAILS), 4000)
        for i in range(4500):
            m._n95_rate_ok('11.%d.%d.1' % (i // 250, i % 250), 100.0)
        self.assertLessEqual(len(m._N95_HITS), 4500)

    def test_sessions_expire_and_are_capped(self):
        m = self.m
        sid = m._n95_new_session(42, now=1000.0)
        self.assertEqual(m._n95_session_uid(sid, now=1000.0 + 3600), 42)
        self.assertIsNone(m._n95_session_uid(sid, now=1000.0 + 13 * 3600))
        self.assertIsNone(m._n95_session_uid('nope'))
        self.assertIsNone(m._n95_session_uid(''))
        for i in range(260):
            m._n95_new_session(i, now=2000.0 + i)
        self.assertLessEqual(len(m._N95_SESS), 200)
        n = len(m._N95_SESS)
        self.assertEqual(m._n95_drop_sessions(), n)
        self.assertEqual(len(m._N95_SESS), 0)

    def test_session_ids_are_long_and_random(self):
        a, b = self.m._n95_new_session(1), self.m._n95_new_session(1)
        self.assertNotEqual(a, b)
        self.assertGreaterEqual(len(a), 40)


# ===================================================================================================================
# 2. TELEGRAM'S SIGNATURE
# ===================================================================================================================
class TestTelegramLogin(DoorsCase):
    def check(self, data, **kw):
        return self.m._n95_verify_initdata(data, kw.pop('bot', BOT), **kw)

    def test_a_real_signature_gives_the_user(self):
        u = self.check(signed())
        self.assertEqual((u['id'], u['first_name']), (OWNER_ID, 'Asha'))

    def test_field_order_does_not_matter(self):
        s = signed()
        parts = s.split('&')
        self.assertEqual(self.check('&'.join(reversed(parts)))['id'], OWNER_ID)

    def test_a_changed_field_a_changed_user_or_another_bot_fails(self):
        with self.assertRaisesRegex(ValueError, 'bad signature'):
            self.check(signed(tamper=lambda s: s.replace('query_id=AAHdF6IQ', 'query_id=AAHdF6IR')))
        with self.assertRaisesRegex(ValueError, 'bad signature'):
            self.check(signed(tamper=lambda s: s.replace(str(OWNER_ID), '99')))
        with self.assertRaisesRegex(ValueError, 'bad signature'):
            self.check(signed(bot='999:OTHER'))
        with self.assertRaisesRegex(ValueError, 'bad signature'):
            self.check(signed(tamper=lambda s: s + '&extra=1'))

    def test_an_old_or_future_login_fails(self):
        now = 1_800_000_000
        with self.assertRaisesRegex(ValueError, 'too old'):
            self.check(signed(now=now - 90000), now=now)
        with self.assertRaisesRegex(ValueError, 'too old'):
            self.check(signed(now=now + 4000), now=now)
        self.assertEqual(self.check(signed(now=now - 80000), now=now)['id'], OWNER_ID)

    def test_missing_pieces_are_refused_with_a_reason(self):
        for data, why in (('', 'missing'), ('a=1&b=2', 'no signature'), ('hash=abc', 'bad signature'), ('x' * 7000, 'too long'), ('a=1&a=2&hash=ff', 'repeated')):
            with self.assertRaisesRegex(ValueError, why):
                self.check(data)
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.check(signed(), bot='')

    def test_signed_data_without_a_proper_user_is_refused(self):
        for extra in ({'user': '{"first_name":"A"}'}, {'user': '{"id":"42"}'}, {'user': 'not json'}, {'user': '[1,2]'}):
            with self.assertRaisesRegex(ValueError, 'no user|bad signature'):
                self.check(signed(extra=extra))

    def test_it_agrees_with_an_independent_copy_of_the_algorithm_on_many_inputs(self):
        for i in range(25):
            data = signed(uid=1000 + i, extra={'start_param': 'p%d' % i, 'chat_type': 'sender', 'chat_instance': str(i * 7919)})
            self.assertEqual(self.check(data)['id'], 1000 + i)


@needs_flask
class TestLoginRoutes(DoorsCase):
    def test_the_owner_gets_a_cookie_and_can_use_the_site_with_it(self):
        c = self.client()
        self.assertEqual(c.post('/api/chat', json={'message': 'hi'}).status_code, 401)
        r = c.post('/api/tglogin', json={'initData': signed()})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()['ok'])
        ck = r.headers['Set-Cookie']
        self.assertIn('nemo_sid=', ck)
        self.assertIn('HttpOnly', ck)
        self.assertIn('SameSite=Strict', ck)
        self.assertNotIn('Secure', ck)
        r = c.post('/api/chat', json={'message': 'hi'})
        self.assertEqual((r.status_code, r.get_json()['reply']), (200, 'echo:hi'))
        self.assertEqual(self.m._N95_STATS['logins'], 1)

    def test_behind_the_https_tunnel_the_cookie_is_secure(self):
        r = self.client().post('/api/tglogin', json={'initData': signed()}, headers={'X-Forwarded-Proto': 'https'})
        self.assertIn('Secure', r.headers['Set-Cookie'])

    def test_somebody_else_even_with_a_genuine_signature_is_refused(self):
        c = self.client()
        r = c.post('/api/tglogin', json={'initData': signed(uid=99)})
        self.assertEqual(r.status_code, 403)
        self.assertIn('private', r.get_json()['error'])
        self.assertEqual(c.post('/api/chat', json={'message': 'hi'}).status_code, 401)
        self.assertEqual(self.m._N95_STATS['login_refused'], 1)

    def test_a_forged_login_is_refused_with_the_reason(self):
        r = self.client().post('/api/tglogin', json={'initData': signed(bot='1:other')})
        self.assertEqual(r.status_code, 403)
        self.assertIn('bad signature', r.get_json()['error'])

    def test_junk_bodies_do_not_crash(self):
        c = self.client()
        for body in ({}, {'initData': 5}, {'initData': None}, [1, 2]):
            r = c.post('/api/tglogin', json=body)
            self.assertEqual(r.status_code, 403, body)
        self.assertEqual(c.post('/api/tglogin', data='garbage', content_type='text/plain').status_code, 403)

    def test_a_session_for_a_different_person_does_not_open_the_door(self):
        c = self.client()
        sid = self.m._n95_new_session(99)
        c.set_cookie('nemo_sid', sid)
        self.assertEqual(c.post('/api/chat', json={'message': 'hi'}).status_code, 401)

    def test_logout_ends_the_login(self):
        c = self.client()
        c.post('/api/tglogin', json={'initData': signed()})
        self.assertEqual(c.post('/api/chat', json={'message': 'hi'}).status_code, 200)
        self.assertEqual(c.post('/api/logout').status_code, 200)
        self.assertEqual(c.post('/api/chat', json={'message': 'hi'}).status_code, 401)

    def test_the_login_page_is_a_small_static_page_with_no_secret_in_it(self):
        r = self.client().get('/app')
        self.assertEqual(r.status_code, 200)
        t = r.get_data(as_text=True)
        self.assertIn('telegram-web-app.js', t)
        self.assertIn('/api/tglogin', t)
        self.assertIn('initData', t)
        self.assertNotIn(TOKEN, t)
        self.assertNotIn(BOT, t)


# ===================================================================================================================
# 3. EVERY ROUTE OF THE SITE, WHOEVER ADDED IT
# ===================================================================================================================
@needs_flask
class TestHooks(DoorsCase):
    def test_every_reply_carries_the_safe_headers(self):
        c = self.client()
        for path in ('/', '/health', '/manifest.json', '/cockpit', '/api/status', '/app'):
            r = c.get(path)
            self.assertEqual(r.headers.get('Referrer-Policy'), 'no-referrer', path)
            self.assertEqual(r.headers.get('X-Content-Type-Options'), 'nosniff', path)
            self.assertIn('noindex', r.headers.get('X-Robots-Tag', ''), path)
        self.assertEqual(c.get('/api/status').headers.get('Cache-Control'), 'no-store')
        self.assertEqual(c.get('/cockpit').headers.get('Cache-Control'), 'no-store')

    def test_hsts_only_on_https(self):
        c = self.client()
        self.assertNotIn('Strict-Transport-Security', c.get('/health').headers)
        self.assertIn('max-age', c.get('/health', headers={'X-Forwarded-Proto': 'https'}).headers['Strict-Transport-Security'])

    def test_the_old_ways_in_still_work_by_default(self):
        c = self.client()
        r = c.post('/api/chat', json={'message': 'hi'}, headers={'X-Nemo-Token': TOKEN})
        self.assertEqual((r.status_code, r.get_json()['reply']), (200, 'echo:hi'))
        r = c.post('/api/chat?k=' + TOKEN, json={'message': 'hi'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(c.get('/api/status?k=' + TOKEN).status_code, 200)
        self.assertEqual(c.post('/api/chat', json={'message': 'hi'}, headers={'X-Nemo-Token': TOKEN[:-1] + '1'}).status_code, 401)

    def test_strict_mode_refuses_the_key_in_the_address_but_not_in_a_header(self):
        self.m._n95_put('strict', 'on')
        c = self.client()
        self.assertEqual(c.post('/api/chat?k=' + TOKEN, json={'message': 'hi'}).status_code, 401)
        self.assertEqual(c.get('/api/status?k=' + TOKEN).status_code, 401)
        self.assertEqual(c.post('/api/chat?k=' + TOKEN, json={'message': 'hi'}, headers={'X-Nemo-Token': TOKEN}).status_code, 200)
        c.post('/api/tglogin', json={'initData': signed()})
        self.assertEqual(c.post('/api/chat', json={'message': 'hi'}).status_code, 200)

    def test_twelve_refused_requests_block_a_stranger_for_fifteen_minutes(self):
        c = self.client()
        env = {'REMOTE_ADDR': '8.8.4.4'}
        codes = [c.post('/api/chat', json={'message': 'x'}, headers={'X-Nemo-Token': 'guess%d' % i}, environ_base=env).status_code for i in range(12)]
        self.assertEqual(set(codes), {401})
        r = c.post('/api/chat', json={'message': 'x'}, headers={'X-Nemo-Token': 'guess12'}, environ_base=env)
        self.assertEqual(r.status_code, 429)
        self.assertTrue(int(r.headers['Retry-After']) > 0)
        self.assertIn('wait', r.get_json()['error'])
        r = c.post('/api/chat', json={'message': 'hi'}, headers={'X-Nemo-Token': TOKEN}, environ_base=env)
        self.assertEqual(r.status_code, 429, 'even the right key waits while the address is blocked')
        r = c.post('/api/chat', json={'message': 'hi'}, headers={'X-Nemo-Token': TOKEN}, environ_base={'REMOTE_ADDR': '8.8.8.8'})
        self.assertEqual(r.status_code, 200, 'another address is not affected')

    def test_the_health_check_is_never_blocked(self):
        c = self.client()
        env = {'REMOTE_ADDR': '8.8.4.4'}
        for i in range(14):
            c.post('/api/chat', json={'message': 'x'}, headers={'X-Nemo-Token': 'g%d' % i}, environ_base=env)
        self.assertEqual(c.get('/health', environ_base=env).status_code, 200)

    def test_the_server_itself_is_never_locked_out_by_its_own_mistakes(self):
        c = self.client()
        for i in range(30):
            self.assertEqual(c.post('/api/chat', json={'message': 'x'}, headers={'X-Nemo-Token': 'g%d' % i}).status_code, 401)

    def test_behind_the_tunnel_each_visitor_is_counted_separately(self):
        c = self.client()
        hdr = {'CF-Connecting-IP': '203.0.113.5'}
        for i in range(12):
            c.post('/api/chat', json={'message': 'x'}, headers=dict(hdr, **{'X-Nemo-Token': 'g%d' % i}))
        self.assertEqual(c.post('/api/chat', json={'message': 'x'}, headers=hdr).status_code, 429)
        self.assertEqual(c.post('/api/chat', json={'message': 'x'}, headers={'CF-Connecting-IP': '203.0.113.6'}).status_code, 401)
        self.assertEqual(c.post('/api/chat', json={'message': 'x'}, headers={'X-Nemo-Token': TOKEN}).status_code, 200, 'the owner on another address is fine')

    def test_a_stranger_cannot_use_a_forged_forwarded_header_to_dodge_the_block(self):
        c = self.client()
        env = {'REMOTE_ADDR': '8.8.4.4'}
        for i in range(12):
            c.post('/api/chat', json={'message': 'x'}, headers={'CF-Connecting-IP': '10.0.0.%d' % i, 'X-Nemo-Token': 'g%d' % i}, environ_base=env)
        self.assertEqual(c.post('/api/chat', json={'message': 'x'}, headers={'CF-Connecting-IP': '10.9.9.9'}, environ_base=env).status_code, 429)

    def test_a_flood_from_one_address_is_slowed(self):
        c = self.client()
        env = {'REMOTE_ADDR': '8.8.4.4'}
        codes = [c.get('/manifest.json', environ_base=env).status_code for _ in range(245)]
        self.assertEqual(codes[:240], [200] * 240)
        self.assertEqual(set(codes[240:]), {429})

    def test_refusals_from_the_older_routes_are_counted_too(self):
        c = self.client()
        env = {'REMOTE_ADDR': '8.8.4.4'}
        for i in range(12):
            self.assertEqual(c.post('/api/voice3/ping', json={'device_id': 'x'}, headers={'Authorization': 'Bearer nope%d' % i}, environ_base=env).status_code, 403)
        self.assertEqual(c.post('/api/voice3/ping', json={'device_id': 'x'}, environ_base=env).status_code, 429)

    def test_a_stale_page_repeating_one_old_key_does_not_lock_its_owner_out(self):
        c = self.client()
        env = {'REMOTE_ADDR': '8.8.4.4'}
        for _ in range(60):                                      # the Cockpit asks every 10 seconds with whatever key was in its address
            self.assertEqual(c.get('/api/cockpit?k=oldkey', environ_base=env).status_code, 401)
        r = c.get('/api/cockpit', headers={'X-Nemo-Token': TOKEN}, environ_base=env)
        self.assertNotEqual(r.status_code, 429)
        self.assertEqual(self.m._N95_STATS['blocked'], 0)

    def test_asking_with_no_key_at_all_again_and_again_is_not_a_guess_either(self):
        c = self.client()
        env = {'REMOTE_ADDR': '8.8.4.4'}
        for _ in range(40):
            self.assertEqual(c.post('/api/chat', json={'message': 'x'}, environ_base=env).status_code, 401)
        self.assertEqual(c.post('/api/chat', json={'message': 'hi'}, headers={'X-Nemo-Token': TOKEN}, environ_base=env).status_code, 200)

    def test_guessing_in_the_address_or_with_cookies_counts_the_same(self):
        c = self.client()
        env = {'REMOTE_ADDR': '8.8.4.4'}
        for i in range(6):
            c.get('/api/status?k=guess%d' % i, environ_base=env)
        for i in range(6):
            c.set_cookie('nemo_sid', 'fake%d' % i)
            c.get('/api/status', environ_base=env)
        c.set_cookie('nemo_sid', '')
        self.assertEqual(c.get('/api/status?k=again', environ_base=env).status_code, 429)

    def test_the_fingerprint_never_contains_the_key(self):
        c = self.m.build_web_app().test_client()
        seen = []
        real = self.m._n95_note_fail
        self.start(self.m, '_n95_note_fail', lambda ip, now=None, cred='': seen.append(cred) or real(ip, now, cred))
        c.get('/api/status?k=supersecretguess', environ_base={'REMOTE_ADDR': '8.8.4.4'})
        self.assertEqual(len(seen), 1)
        self.assertEqual(len(seen[0]), 12)
        self.assertNotIn('supersecretguess', seen[0])

    def test_the_hooks_are_installed_once(self):
        app = self.m.build_web_app()
        self.assertEqual(len(app.before_request_funcs.get(None, [])), 1)
        self.assertEqual(len(app.after_request_funcs.get(None, [])), 1)

    def test_a_failure_in_the_hook_code_never_breaks_a_reply(self):
        c = self.client()
        self.start(self.m, '_n95_note_fail', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('x')))
        self.assertEqual(c.post('/api/chat', json={'message': 'x'}).status_code, 401)
        self.assertGreaterEqual(self.m._N95_STATS['errors'], 1)

    def test_the_webhook_secrets_in_the_path_are_compared_with_the_safe_function(self):
        seen = []
        real = self.m._n95_eq
        self.start(self.m, '_n95_eq', lambda a, b: seen.append((a, b)) or real(a, b))
        c = self.client()
        self.assertEqual(c.post('/tv/' + 'wrong', json={}).status_code, 403)
        self.assertEqual(c.get('/api/device/grid?k=wrong').status_code, 403)
        self.assertTrue(any(a == 'wrong' for a, _b in seen), seen)
        self.assertIn(('wrong', TOKEN), seen)


# ===================================================================================================================
# 4. THE OWNER'S SWITCHES
# ===================================================================================================================
class TestSwitches(DoorsCase):
    def test_the_status_says_who_can_get_in(self):
        out = self.say('doors')
        for part in ('WHO CAN GET IN', 'Door 1: the website (port 8090)', 'Public address: https://nemo.example.com ✅', 'Key: about 128 bits ✅', 'Key in the address (?k=): accepted ⚠️', 'Telegram login: OFF',
                     'Failed-attempt limit: ON ✅', 'DIFFERENT wrong keys', 'Door 2: the gateway', 'Next steps I suggest:', 'doors telegram on', 'doors lock on'):
            self.assertIn(part, out)

    def test_a_short_key_is_called_out(self):
        self.m.WEBCFG['token'] = 'a1b2c3d4e5f6'
        out = self.say('doors')
        self.assertIn('about 48 bits ⚠️ short', out)
        self.assertIn('doors rotate', out)

    def test_no_public_address_is_called_out(self):
        self.m.WEBCFG['public_url'] = ''
        out = self.say('doors')
        self.assertIn('none set: only the direct address works', out)
        self.assertIn('/setdomain', out)

    def test_natural_ways_of_asking(self):
        for q in ('doors', 'doors status', 'website security', 'is my website safe', 'secure my website', 'web security', '/doors'):
            self.assertIn('WHO CAN GET IN', self.say(q), q)

    def test_telegram_login_needs_https_then_switches_on_and_moves_the_button(self):
        self.m.WEBCFG['public_url'] = ''
        self.assertIn('needs the website to have an https address', self.say('doors telegram on'))
        self.assertFalse(self.m._n95_on('telegram'))
        self.m.WEBCFG['public_url'] = 'https://nemo.example.com'
        out = self.say('doors telegram on')
        self.assertIn('Telegram login is ON', out)
        self.assertTrue(self.m._n95_on('telegram'))
        method, kw = self.menu[-1]
        self.assertEqual(method, 'setChatMenuButton')
        self.assertEqual(kw['menu_button']['web_app']['url'], 'https://nemo.example.com/app')

    def test_turning_it_off_gives_the_button_back_its_old_address(self):
        self.say('doors telegram on')
        self.say('doors telegram off')
        self.assertEqual(self.menu[-1][1]['menu_button']['web_app']['url'], 'https://nemo.example.com/cockpit?k=' + TOKEN)

    def test_strict_needs_telegram_login_first_so_the_owner_cannot_lock_himself_out(self):
        out = self.say('doors strict on')
        self.assertIn('I will not refuse keys in the address until Telegram login is on', out)
        self.assertFalse(self.m._n95_on('strict'))
        self.say('doors telegram on')
        self.assertIn('Keys in the address are now refused', self.say('doors strict on'))
        self.assertTrue(self.m._n95_on('strict'))
        self.assertIn('accepted again', self.say('doors strict off'))

    def test_lock_with_no_public_address_needs_a_confirmation(self):
        self.m.WEBCFG['public_url'] = ''
        out = self.say('doors lock on')
        self.assertIn('ONLY way in', out)
        self.assertFalse(self.m._n95_on('lock'))
        self.assertIn('after the next restart', self.say('doors lock on confirm'))
        self.assertTrue(self.m._n95_on('lock'))

    def test_lock_with_a_tunnel_is_a_plain_switch(self):
        self.assertIn('this server only after the next restart', self.say('doors lock on'))
        self.assertEqual(self.m._n95_bind_host(), '127.0.0.1')
        self.say('doors lock off')
        self.assertEqual(self.m._n95_bind_host(), '0.0.0.0')

    def test_rotate_makes_a_128_bit_key_ends_logins_and_does_not_print_the_key(self):
        self.m._n95_new_session(OWNER_ID)
        self.m.WEBCFG['token'] = 'a1b2c3d4e5f6'
        out = self.say('doors rotate')
        new = self.m.WEBCFG['token']
        self.assertTrue(re.fullmatch(r'[0-9a-f]{32}', new), new)
        self.assertEqual(self.saved['web_token'], new)
        self.assertNotIn(new, out)
        self.assertIn('1 Telegram login(s) were ended', out)
        self.assertIn('/connect', out)
        self.assertEqual(len(self.m._N95_SESS), 0)

    def test_logout_all(self):
        self.m._n95_new_session(OWNER_ID)
        self.m._n95_new_session(OWNER_ID)
        self.assertIn('Ended 2 Telegram login(s)', self.say('doors logout'))

    def test_unknown_words_get_the_list(self):
        self.assertIn('I know: doors', self.say('doors dance'))

    def test_a_guest_gets_none_of_it(self):
        for q in ('doors', 'doors rotate', 'doors telegram on', 'website security'):
            n = len(self.passed)
            self.m.handle(self.guest(q))
            self.assertEqual(len(self.passed), n + 1, q)
        self.assertEqual(self.saved, {})
        self.assertFalse(self.m._n95_on('telegram'))

    def test_the_status_reflects_the_switches_and_the_running_server(self):
        self.m._N95_STATE.update(host='0.0.0.0', server='flask', port=8090)
        out = self.m._n95_status_text()
        self.assertIn('every address ⚠️', out)
        self.assertIn('Flask development server ⚠️', out)
        self.m._n95_put('lock', 'on')
        self.assertIn('this server only (applies at the next restart)', self.m._n95_status_text())
        self.m._N95_STATE.update(host='127.0.0.1', server='waitress')
        out = self.m._n95_status_text()
        self.assertIn('this server only (127.0.0.1) ✅', out)
        self.assertIn('waitress (production) ✅', out)
        self.m._n95_put('telegram', 'on')
        self.m._n95_put('strict', 'on')
        out = self.m._n95_status_text()
        self.assertIn('refused ✅', out)
        self.assertIn('Telegram login: ON ✅', out)
        self.assertIn('nothing: every protection is on', out)


class TestServing(DoorsCase):
    class FakeApp:
        def __init__(self):
            self.ran = None

        def run(self, **kw):
            self.ran = kw

    def test_the_default_is_what_it_always_was(self):
        self.start(self.m, '_n92_have', lambda mod: False)
        app = self.FakeApp()
        self.m._n95_serve(app)
        self.assertEqual(app.ran, {'host': '0.0.0.0', 'port': 8090, 'threaded': True})
        self.assertEqual(self.m._N95_STATE['server'], 'flask')

    def test_the_lock_switch_narrows_the_address(self):
        self.start(self.m, '_n92_have', lambda mod: False)
        self.m._n95_put('lock', 'on')
        app = self.FakeApp()
        self.m._n95_serve(app)
        self.assertEqual(app.ran['host'], '127.0.0.1')
        self.assertEqual(self.m._N95_STATE['host'], '127.0.0.1')

    def test_waitress_is_used_when_it_is_installed(self):
        calls = []
        fake = types.ModuleType('waitress')
        fake.serve = lambda app, **kw: calls.append(kw)
        with mock.patch.dict(sys.modules, {'waitress': fake}):
            self.start(self.m, '_n92_have', lambda mod: mod == 'waitress')
            app = self.FakeApp()
            self.m._n95_serve(app)
        self.assertEqual(calls, [{'host': '0.0.0.0', 'port': 8090, 'threads': 8, 'ident': 'nemo'}])
        self.assertIsNone(app.ran)
        self.assertEqual(self.m._N95_STATE['server'], 'waitress')

    def test_a_waitress_that_cannot_start_falls_back_to_flask(self):
        fake = types.ModuleType('waitress')
        fake.serve = lambda app, **kw: (_ for _ in ()).throw(OSError('address in use'))
        with mock.patch.dict(sys.modules, {'waitress': fake}):
            self.start(self.m, '_n92_have', lambda mod: mod == 'waitress')
            app = self.FakeApp()
            self.m._n95_serve(app)
        self.assertEqual(app.ran['port'], 8090)
        self.assertEqual(self.m._N95_STATE['server'], 'flask')

    def test_the_port_comes_from_the_existing_setting(self):
        self.start(self.m, '_n92_have', lambda mod: False)
        self.m.WEBCFG['port'] = 9123
        app = self.FakeApp()
        self.m._n95_serve(app)
        self.assertEqual(app.ran['port'], 9123)


# ===================================================================================================================
# 5. THE EDITS TO OLDER CODE
# ===================================================================================================================
class TestEditsToOlderCode(DoorsCase):
    @classmethod
    def setUpClass(cls):
        cls.src = open(base.NEMO_FILE, encoding='utf-8').read()

    def test_the_old_checks_now_go_through_the_safe_comparison(self):
        s = self.src
        self.assertIn('    def ok_tok(req):\n        return _n95_ok_tok(req, sec())', s)
        self.assertEqual(s.count('        if not _n95_eq(s, sec()):\n'), 4)
        self.assertNotIn('        if s != sec():\n', s)
        self.assertIn('if not _n95_eq(request.args.get("k",""), sec())', s)
        self.assertIn('return bool(tok) and _n95_eq(tok, mm_secret())', s)
        self.assertNotIn('tok == mm_secret()', s)
        self.assertNotIn('t == sec()', s)

    def test_new_keys_are_128_bit(self):
        s = self.src
        self.assertIn('WEBCFG["token"] = _ps.token_hex(16)', s)
        self.assertIn('WEBCFG["token"] = _pysec.token_hex(16)', s)
        self.assertNotIn('token_hex(6)', s)

    def test_the_server_start_goes_through_the_serve_function(self):
        self.assertIn('        _n95_serve(app)', self.src)
        self.assertNotIn('app.run(host="0.0.0.0", port=int(WEBCFG.get("port", 8090)), threaded=True)', self.src)

    def test_the_app_button_address_follows_the_switch(self):
        self.assertIn('"web_app":{"url":_n95_app_url(url)}', self.src)
        self.assertIn('_n95_app_url(pub+"/cockpit?k="+WEBCFG["token"])', self.src)
        self.assertEqual(self.m._n95_app_url('https://x/cockpit?k=1'), 'https://x/cockpit?k=1')
        self.m._n95_put('telegram', 'on')
        self.assertEqual(self.m._n95_app_url('https://x/cockpit?k=1'), 'https://nemo.example.com/app')
        self.m.WEBCFG['public_url'] = 'http://1.2.3.4:8090'
        self.assertEqual(self.m._n95_app_url('http://1.2.3.4:8090/cockpit?k=1'), 'http://1.2.3.4:8090/cockpit?k=1', 'Telegram only opens https apps')

    def test_the_cockpit_button_in_chat_follows_the_switch(self):
        sent = []
        self.start(self.m, 'send_text', lambda cid, text, kb=None: sent.append(kb))
        self.m.cockpit_cmd(OWNER_ID)
        self.assertTrue(sent[-1]['inline_keyboard'][0][0]['web_app']['url'].endswith('/cockpit?k=' + TOKEN))
        self.m._n95_put('telegram', 'on')
        self.m.cockpit_cmd(OWNER_ID)
        self.assertEqual(sent[-1]['inline_keyboard'][0][0]['web_app']['url'], 'https://nemo.example.com/app')

    def test_the_layer_is_protected_from_live_self_editing(self):
        self.assertIn("'_n94_','_n95_'", self.src)
        for name in ('_n95_ok_tok', '_n95_verify_initdata', '_n95_serve', '_n95_clean', '_n95_gstin_check'):
            self.assertFalse(self.m._n79_editable(name), name)

    def test_the_hooks_are_installed_and_the_version_moved(self):
        self.assertIsNot(self.m.build_web_app, self.m._N95_BUILD_PREV)
        self.assertIsNot(self.m.handle, self.m._N95_HANDLE_PREV)
        self.assertIsNot(self.m.main, self.m._N95_MAIN_PREV)
        self.assertGreaterEqual(float(self.m.VERSION), 95.0)
        self.assertTrue(self.src.startswith('"""nemotron_bot.py v95.0 - DOORS + CARE + OFFICE'))
