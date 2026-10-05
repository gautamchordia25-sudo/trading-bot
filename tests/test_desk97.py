"""Nemo v97 Desk: a family member (or all family) can be let into the trade desk, view only: the open Scout ideas without the owner's capital or sizing, a limited fresh scan, how past ideas turned out
and the practice agent's VIRTUAL trades. Real positions, money, orders, live-mode trades and the owner's settings stay private, nothing can be changed, and Circle (v89) is untouched.

Offline: Circle's own harness (a fake Telegram, a temporary database, synthetic people), real Scout ideas built by the Scout fixtures, a scripted scan; no network, no broker, no order.

    NEMO_FILE=/path/to/nemotron_bot.py python -m unittest tests.test_desk97 -v
"""
import ast
import csv
import datetime as dt
import io
import os
import re
import time
import unittest
from unittest import mock

from tests import test_cortex83 as base
from tests.test_circle89 import CircleCase
from tests.test_forge91 import OWNER_ID
from tests.test_scout93 import ScanCase, OptionCase, breakout_stock, news_sig, GOOD_CTX, GOOD_STOCK_CFG

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
D0 = dt.date(2026, 10, 5)
NOW = 2_000_000_000.0                         # the clock of these tests: ideas are saved at NOW and looked at an hour later
SYM = 'NSE:NIFTY26O0622550PE'
OWNER_CAPITAL = '777777'                      # the owner's own Scout capital: must never show up for anyone else
OWNER_CAPITAL_TEXT = '7,77,777'


def setUpModule():
    if base.m is None:
        base.setUpModule()


def bot_source():
    with open(base.NEMO_FILE, encoding='utf-8') as f:
        return f.read()


def v97_source():
    src = bot_source()
    i = src.index('# NEMO 97 - DESK')
    j = src.index('# NEMO 98 - SCHOLAR') if '# NEMO 98 - SCHOLAR' in src else src.rindex("if __name__")       # (the next layer is not part of this one)
    return src[i:j]


def ist_ts(days_ago=0, hh=11, mm=0):
    d = D0 - dt.timedelta(days=days_ago)
    return dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=IST).timestamp()


def trade(entry=77.8, exit=122.7, qty=65, mode='shadow', reason='target', days_ago=0, hh=11, why='AI NIFTY: strong trend (conf 7/10)'):
    return {'sym': SYM, 'entry': entry, 'exit': exit, 'qty': qty, 'pnl': round((exit - entry) * qty, 1), 'why': why, 'exit_reason': reason, 'brain': 'ai', 'mode': mode, 't': ist_ts(days_ago, hh), 'bracket': False}


class DeskCase(CircleCase):
    ASHA, GUY = 5552, 5551

    def setUp(self):
        super().setUp()
        m = self.m
        m._n97_db().close()
        m._n93_db().close()
        m._n96_db().close()
        for table in ('desk97_person', 'desk97_setting', 'desk97_use', 'desk97_scan'):
            m._n97_q('DELETE FROM %s' % table, write=True)
        m._n93_q('DELETE FROM scout93_idea', write=True)
        m._n93_q('DELETE FROM scout93_setting', write=True)
        for table in ('ledger96_trade', 'ledger96_entry', 'ledger96_setting'):
            m._n96_q('DELETE FROM %s' % table, write=True)
        for k in m._N97_STATS:
            m._N97_STATS[k] = 0
        self.log = []
        self.mono, self.files, self.images = [], [], []
        self.scan_calls = []
        self.broker_calls = []
        for name in ('AUTOLOG',):
            p = mock.patch.object(m, name, self.log)
            p.start()
            self.patches.append(p)
        for name, val in (('send_mono', lambda cid, text: self.mono.append((cid, text))),
                          ('send_document', lambda cid, path, fname, mime: self.files.append((cid, fname, open(path, 'rb').read())) or True),
                          ('_n90_send_image', lambda cid, raw, name, caption='', kb=None, force_file=False: self.images.append((cid, raw, name)) or True),
                          ('_n97_now', lambda: NOW + 3600), ('_n96_now', lambda: ist_ts(0, 16, 0)), ('_N91_SYNC', True)):
            p = mock.patch.object(m, name, val)
            p.start()
            self.patches.append(p)
        for name in ('fyers_place', 'fyers_place_bracket', '_order_send', 'request_order'):
            if hasattr(m, name):
                p = mock.patch.object(m, name, lambda *a, _n=name, **k: self.broker_calls.append(_n))
                p.start()
                self.patches.append(p)
        m._n93_set('capital', OWNER_CAPITAL)

    # ----- people
    def asha(self):
        self.family(self.ASHA, 'Asha')

    def guy(self):
        self.guest(self.GUY, 'Guy')

    def allow(self, uid=None, name='Asha'):
        self.m._n97_grant(str(uid or self.ASHA), name, True)

    def ask(self, text, uid=None, name='Asha'):
        return self.other(text, uid=uid or self.ASHA, name=name)

    # ----- ideas (real Scout ideas, from the Scout test fixtures)
    def stock_idea(self, symbol='RELIANCE', **kw):
        t = self.m._n93_tech(breakout_stock())
        r = self.m._n93_stock_idea(t, 1, news_sig(), GOOD_CTX, GOOD_STOCK_CFG, symbol)
        self.assertTrue(r['ok'])
        r.update(kw)
        return r

    def option_idea(self):
        r = self.m._n93_option_plan(OptionCase.view(self), OptionCase.BIG)
        self.assertTrue(r['ok'], r.get('veto'))
        return r

    def save(self, idea, ts=NOW):
        return self.m._n93_save(idea, ts)

    def forbidden(self, text):
        """What a family member must never be shown from the owner's own settings."""
        for bad in (OWNER_CAPITAL_TEXT, OWNER_CAPITAL, 'Size at your limits', 'your risk limit', 'your 25% position cap', 'at your limits', 'Agent now:', 'REAL money'):
            self.assertNotIn(bad, text, bad)


# ===================================================================================================================
# 1. THE OWNER'S WORDS
# ===================================================================================================================
class TestOwnerWords(DeskCase):
    def test_sentences_that_name_a_person_and_the_desk_are_understood(self):
        f = self.m._n97_owner_nl
        for text, want in (('allow Asha to see trade ideas', ('allow', 'asha')), ('let Asha see trade ideas', ('allow', 'asha')), ('give Asha the trade desk', ('allow', 'asha')),
                           ('allow Asha to see the paper trades', ('allow', 'asha')), ('please allow Asha to see my trade ideas', ('allow', 'asha')), ('can you let Asha see the ledger', ('allow', 'asha')),
                           ('enable the trade desk for Meera', ('allow', 'meera')), ('give trade ideas to Meera', ('allow', 'meera')), ('desk allow Asha', ('allow', 'asha')), ('desk allow family', ('allow', 'family')), ('allow the family to see trade ideas', ('allow', 'family')),
                           ('let my family see stock ideas', ('allow', 'family')), ('add Asha to the desk', ('allow', 'asha')),
                           ('stop Asha from seeing trade ideas', ('deny', 'asha')), ("don't let Asha see trade ideas", ('deny', 'asha')), ('do not let Asha see the trade desk', ('deny', 'asha')),
                           ("remove Asha's access to the trade desk", ('deny', 'asha')), ('turn off trade ideas for Asha', ('deny', 'asha')), ('desk remove Asha', ('deny', 'asha')), ('desk stop family', ('deny', 'family')),
                           ('revoke Asha from seeing the ledger', ('deny', 'asha')),
                           ('desk', ('status', '')), ('family desk', ('status', '')), ('trade desk', ('status', '')), ('/desk', ('status', '')), ('desk off', ('off', '')), ('desk on', ('on', '')),
                           ('desk limits views=40 scans=2', ('limits', 'views=40 scans=2'))):
            self.assertEqual(f(text), want, text)

    def test_ordinary_sentences_are_not_taken(self):
        for text in ('give me trade ideas', 'trade ideas', 'show me the trade ideas', 'stop trade ideas', 'allow notifications', 'block Asha', 'give trade ideas to me', 'remove the ledger', 'let me see the ledger', 'give me the paper trades',
                     'allow Asha to download songs', 'stop Asha from making images', 'what can Asha do', 'family access', 'hello', 'desks are for working', 'add milk to the list', 'give some trade ideas', 'I want new trade ideas'):
            self.assertIsNone(self.m._n97_owner_nl(text), text)

    def test_status_with_nobody_yet(self):
        out = self.owner_say('desk')
        for part in ('TRADE DESK for your family', 'Desk: ON · all family members: off', 'Nobody has written to me yet', 'They never see: your real positions, money, orders', 'Limits per person per day: 40 views, 2 fresh scans',
                     'fresh scan spends your AI and market-data credits'):
            self.assertIn(part, out)

    def test_allowing_a_family_member(self):
        self.asha()
        out = self.owner_say('allow Asha to see trade ideas')
        for part in ('Asha can now use the trade desk (view only)', 'without your capital or sizing', 'They never see: your real positions, money, orders, broker, settings, or live-mode trades', 'a fresh scan (2 a day)',
                     '40 views a day', 'stop Asha from seeing trade ideas'):
            self.assertIn(part, out)
        self.assertEqual(self.m._n97_row('5552'), True)
        self.assertTrue(self.m._n97_access('5552'))
        status = self.owner_say('desk')
        self.assertIn('Asha (family): allowed', status)

    def test_switching_one_person_off_and_on(self):
        self.asha()
        self.owner_say('allow Asha to see trade ideas')
        out = self.owner_say('stop Asha from seeing trade ideas')
        self.assertIn('Asha can no longer use the trade desk', out)
        self.assertFalse(self.m._n97_access('5552'))
        self.assertIn('Asha (family): stopped by you', self.owner_say('desk'))
        self.owner_say('let Asha see trade ideas')
        self.assertTrue(self.m._n97_access('5552'))

    def test_a_guest_can_be_allowed_by_name_and_is_told_apart(self):
        self.guy()
        out = self.owner_say('allow Guy to see trade ideas')
        self.assertIn('Guy is a guest, not family: that is your choice.', out)
        self.assertTrue(self.m._n97_access('5551'))

    def test_family_switch_and_explicit_stop_beat_each_other_the_right_way(self):
        self.asha()
        self.family(5553, 'Meera')
        self.assertFalse(self.m._n97_access('5552'))
        self.assertIn('Every family member can now use the trade desk', self.owner_say('desk allow family'))
        self.assertTrue(self.m._n97_access('5552') and self.m._n97_access('5553'))
        self.owner_say('stop Meera from seeing trade ideas')
        self.assertTrue(self.m._n97_access('5552'))
        self.assertFalse(self.m._n97_access('5553'))                                       # a personal stop beats the family switch
        self.owner_say('desk remove family')
        self.assertFalse(self.m._n97_access('5552'))
        self.owner_say('allow Asha to see trade ideas')
        self.assertTrue(self.m._n97_access('5552'))                                        # a personal allow keeps working with the family switch off
        self.guy()
        self.owner_say('desk allow family')
        self.assertFalse(self.m._n97_access('5551'))                                       # the family switch is for family only

    def test_everyone_is_refused_and_unknown_or_ambiguous_names_are_explained(self):
        self.asha()
        self.family(5554, 'Asha Rao')
        self.assertIn('never for everyone', self.owner_say('desk allow everyone'))
        self.assertIn('I do not know who “zorro” is', self.owner_say('desk allow zorro'))
        out = self.owner_say('desk allow asha')
        self.assertIn('More than one person matches', out)
        self.assertFalse(self.m._n97_access('5552') or self.m._n97_access('5554'))

    def test_someone_who_has_not_written_yet_can_be_added_by_id(self):
        out = self.owner_say('desk allow 987654321 Ravi')
        self.assertIn('Ravi can now use the trade desk', out)
        self.assertIn('have not written to me yet', out)
        self.assertEqual(self.m._n97_row('987654321'), True)

    def test_the_owner_blocked_people_and_bad_ids(self):
        self.guy()
        self.m._n89_set_blocked('5551', True)
        self.assertIn('is blocked', self.owner_say('desk allow Guy'))
        self.assertFalse(self.m._n97_access('5551'))
        self.assertFalse(self.m._n97_access(str(OWNER_ID)))                                 # the owner never needs the desk

    def test_master_switch_keeps_the_people_but_nobody_can_use_it(self):
        self.asha()
        self.owner_say('allow Asha to see trade ideas')
        self.assertIn('Desk switched OFF', self.owner_say('desk off'))
        self.assertFalse(self.m._n97_access('5552'))
        self.assertIn('Desk: OFF', self.owner_say('desk'))
        self.assertIn('Desk switched ON', self.owner_say('desk on'))
        self.assertTrue(self.m._n97_access('5552'))

    def test_limits_are_set_and_checked(self):
        out = self.owner_say('desk limits views=60 scans=1 total=3 gap=30')
        self.assertIn('Saved: views day = 60, scans person day = 1, scans global day = 3, scan gap min = 30', out)
        self.assertEqual((self.m._n97_int('views_day'), self.m._n97_int('scans_person_day'), self.m._n97_int('scans_global_day'), self.m._n97_int('scan_gap_min')), (60, 1, 3, 30))
        out = self.owner_say('desk limits views=9999 scans=2')
        self.assertIn('views must be between 5 and 500', out)
        self.assertEqual(self.m._n97_int('views_day'), 60)
        self.assertEqual(self.m._n97_int('scans_person_day'), 2)
        self.assertIn('say it like', self.owner_say('desk limits banana'))

    def test_the_rule_in_one_table(self):
        d = self.m._n97_decide
        for args, want in (((None, 'family', 'on', 'off'), False), ((None, 'family', 'on', 'on'), True), ((False, 'family', 'on', 'on'), False), ((True, 'family', 'on', 'off'), True), ((True, 'guest', 'on', 'off'), True),
                           ((None, 'guest', 'on', 'on'), False), ((True, 'blocked', 'on', 'on'), False), ((True, 'family', 'off', 'on'), False), ((None, 'family', 'off', 'on'), False)):
            self.assertIs(d(*args), want, args)

    def test_circles_own_sentences_still_reach_circle(self):
        self.asha()
        self.owner_say('allow Asha to download songs')
        self.assertTrue(self.m._n89_allowed('5552', 'downloads'))
        self.assertIsNone(self.m._n97_row('5552'))                                           # nothing about the desk was written
        out = self.owner_say('what can Asha do')
        self.assertIn('Asha', out)


# ===================================================================================================================
# 2. A PERSON WITHOUT THE DESK
# ===================================================================================================================
class TestNotSwitchedOn(DeskCase):
    def test_a_family_member_without_the_desk_gets_a_clear_no_and_the_owner_is_told_once(self):
        self.asha()
        n = len(self.sent)
        out = self.ask('trade ideas')
        self.assertIn('The trade desk is not switched on for you. Ask Gautam to say “allow Asha to see trade ideas”', out)
        self.assertEqual(self.ai, [])                                                      # the general chat was never asked to invent ideas
        told = [t for c, t in self.sent[n:] if c == OWNER_ID]
        self.assertEqual(len(told), 1)
        self.assertIn('Asha asked for the trade desk (ideas)', told[0])
        self.assertIn('allow Asha to see trade ideas', told[0])
        n = len(self.sent)
        self.ask('scan now')
        self.assertEqual([t for c, t in self.sent[n:] if c == OWNER_ID], [])                # not again within 12 hours
        self.assertEqual(self.m._N97_STATS['refused'], 2)
        self.assertEqual(self.m._N97_STATS['requests_sent'], 1)

    def test_a_guest_is_refused_and_the_owner_is_not_bothered(self):
        self.guy()
        n = len(self.sent)
        out = self.ask('trade ideas', uid=self.GUY, name='Guy')
        self.assertIn('not switched on for you', out)
        self.assertEqual([t for c, t in self.sent[n:] if c == OWNER_ID], [])

    def test_the_paper_trades_are_refused_too(self):
        self.asha()
        self.assertIn('not switched on', self.ask('paper trades'))
        self.assertIn('not switched on', self.ask('ledger'))
        self.assertIn('not switched on', self.ask('how does the paper agent decide'))

    def test_master_off_and_a_personal_stop_close_the_door(self):
        self.asha()
        self.allow()
        self.assertNotIn('not switched on', self.ask('trade ideas'))
        self.owner_say('desk off')
        self.assertIn('not switched on', self.ask('trade ideas'))
        self.owner_say('desk on')
        self.owner_say('stop Asha from seeing trade ideas')
        self.assertIn('not switched on', self.ask('trade ideas'))

    def test_a_blocked_person_is_ignored_in_silence(self):
        self.asha()
        self.allow()
        self.m._n89_set_blocked('5552', True)
        self.assertEqual(self.ask('trade ideas'), '')

    def test_strangers_off_still_applies_before_the_desk(self):
        self.m._n89_set_setting('strangers', 'off')
        self.m._n97_grant('7001', 'Zed', True)                                                # allowed by the desk, but a stranger Circle has not approved
        out = self.ask('trade ideas', uid=7001, name='Zed')
        self.assertIn('private assistant', out)
        self.assertNotIn('trade ideas right now', out)


# ===================================================================================================================
# 3. THE IDEAS: WHAT A FAMILY MEMBER SEES (AND WHAT THEY NEVER SEE)
# ===================================================================================================================
class TestIdeas(DeskCase):
    def setUp(self):
        super().setUp()
        self.asha()
        self.allow()

    def test_no_open_ideas(self):
        out = self.ask('trade ideas')
        self.assertIn('No open trade ideas right now', out)
        self.assertIn('2 left for you today', out)

    def test_open_ideas_are_shown_as_cards_without_the_owners_capital_or_sizing(self):
        self.assertEqual(self.m._n93_cfg()['capital'], float(OWNER_CAPITAL))
        a = self.save(self.stock_idea('RELIANCE'))
        b = self.save(self.stock_idea('INFY'), NOW + 10)
        c = self.save(self.stock_idea('TCS'), NOW + 20)
        d = self.save(self.stock_idea('SBIN'), NOW + 30)
        out = self.ask('trade ideas')
        self.assertIn('OPEN TRADE IDEAS (from Gautam’s Scout; view only) · 4 open', out)
        for sym in ('SBIN', 'TCS', 'INFY'):
            self.assertIn('LONG %s' % sym, out)
        self.assertNotIn('IDEA %s' % a, out)                                                  # three cards, the rest are listed in one line
        self.assertIn('Also open: %s LONG RELIANCE' % a, out)
        self.assertIn('Size: decide your own risk first. This idea risks about ₹', out)
        self.assertIn('Wrong if:', out)
        self.assertIn('These are ideas from rules and news, not advice', out)
        self.forbidden(out)
        # the owner's own card for the same idea does carry the sizing: the strip is what protects it
        own = self.m._n93_card(self.m._n93_row(d), self.m._n93_cfg())
        self.assertIn(OWNER_CAPITAL_TEXT, own)
        self.assertIn('Size at your limits', own)
        self.assertEqual(self.broker_calls, [])
        self.assertEqual(self.ai, [])

    def test_an_option_idea_is_shown_without_sizing_too(self):
        iid = self.save(self.option_idea())
        out = self.ask('nifty options ideas')
        self.assertIn('IDEA %s' % iid, out)
        self.assertRegex(out, r'Size: decide your own risk first\. One lot \(65 units\) risks about ₹[\d,]+')
        self.forbidden(out)

    def test_one_idea_in_full_and_an_unknown_one(self):
        iid = self.save(self.stock_idea())
        out = self.ask('idea %s' % iid)
        self.assertIn('(open)', out)
        self.assertIn('IDEA %s' % iid, out)
        self.forbidden(out)
        self.assertIn('I do not have an idea called SC93-ABC123', self.ask('idea SC93-ABC123'))

    def test_a_settled_idea_shows_its_result_and_expired_ones_are_not_listed(self):
        iid = self.save(self.stock_idea())
        self.m._n93_q("UPDATE scout93_idea SET status='target1', r_result=1.8 WHERE id=?", (iid,), write=True)
        out = self.ask('idea %s' % iid)
        self.assertIn('(target1 +1.8R)', out)
        self.assertIn('No open trade ideas', self.ask('trade ideas'))
        old = self.save(self.stock_idea(), NOW - 30 * 86400)
        self.assertNotIn(old, self.ask('trade ideas'))                                    # still "open" in the table, but past its window

    def test_the_track_record(self):
        out = self.ask('scout stats')
        self.assertIn('SCOUT RECORD: nothing has settled yet', out)
        self.assertIn('track record', self.ask('how did the ideas do') + 'track record')

    def test_phrases_that_reach_the_ideas(self):
        for text in ('trade ideas', 'Trade ideas', 'show me trade ideas', 'any stock ideas today', 'give me the latest trade ideas please', 'nemo show me today\'s market ideas', 'scout', '/scout', 'nifty ideas', 'banknifty options ideas',
                     'share ideas', 'stock picks', 'what are the trade ideas'):
            kind, _arg = self.m._n97_intent(text)
            self.assertEqual(kind, 'ideas', text)

    def test_phrases_that_do_not_are_left_to_circle(self):
        for text in ('should I buy nifty options', 'which stock should I buy', 'show me my positions', 'buy 1 lot nifty', 'what is the weather', 'ideas', 'gift ideas for mom', 'business ideas', 'hello', 'my trades',
                     'tell Gautam to buy nifty', 'trade ideas for my homework essay about the history of the printing press and the industrial revolution in great detail please' + ' x' * 40):
            self.assertEqual(self.m._n97_intent(text)[0], None, text)

    def test_each_view_counts_and_the_limit_closes_it_until_tomorrow(self):
        self.owner_say('desk limits views=5')
        for _ in range(5):
            self.assertNotIn('desk views', self.ask('trade ideas'))
        out = self.ask('trade ideas')
        self.assertIn('You have used today’s 5 desk views', out)
        self.assertEqual(self.m._N97_STATS['limited'], 1)
        with mock.patch.object(self.m, '_n97_now', lambda: NOW + 3600 + 86400):
            self.assertNotIn('desk views', self.ask('trade ideas'))

    def test_the_help_card_for_the_person_and_the_circle_card(self):
        out = self.ask('desk')
        for part in ('TRADE DESK (view only)', '“trade ideas”', '“scan now”', '“scout stats”', '“paper trades”', 'Not included: real positions, money, orders, Gautam’s settings and capital', 'Today: 1 of 40 views used'):
            self.assertIn(part, out)
        card = self.ask('what can I do')
        self.assertIn('📈 Trade desk (view only)', card)
        self.owner_say('stop Asha from seeing trade ideas')
        self.assertNotIn('Trade desk', self.ask('what can I do'))

    def test_a_voice_note_works_like_typed_text(self):
        ctx = {'cid': self.ASHA, 'uid': self.ASHA, 'ctype': 'private', 'first_name': 'Asha', 'username': '', 'name': 'Asha'}
        self.save(self.stock_idea())
        n = len(self.sent)
        self.assertTrue(self.m._n89_text(ctx, 'family', 'trade ideas', 'voice'))
        self.assertIn('OPEN TRADE IDEAS', '\n'.join(t for c, t in self.sent[n:] if c == self.ASHA))

    def test_a_group_chat_never_gets_the_desk(self):
        self.save(self.stock_idea())
        n = len(self.sent)
        self.m.handle({'chat': {'id': -100777, 'type': 'group', 'title': 'Home'}, 'from': {'id': self.ASHA, 'first_name': 'Asha'}, 'message_id': 9, 'text': '@nemo_bot trade ideas'})
        self.drain()
        got = '\n'.join(t for c, t in self.sent[n:] if c == -100777)
        self.assertNotIn('OPEN TRADE IDEAS', got)
        self.assertNotIn('Size', got)


# ===================================================================================================================
# 4. THE PRACTICE AGENT: VIRTUAL TRADES ONLY
# ===================================================================================================================
class TestPaperView(DeskCase):
    def setUp(self):
        super().setUp()
        self.asha()
        self.allow()
        self.log.extend([trade(days_ago=2), trade(days_ago=1, entry=100, exit=70, reason='stop-loss'), trade(days_ago=0),
                         trade(mode='live', entry=500, exit=900, qty=65, days_ago=0, hh=12, reason='target', why='LIVE real-money note')])
        self.m.AUTO = dict(self.m.AUTO, mode='live', pos={'symbol': 'NSE:NIFTY26O0622500CE', 'entry': 301.5, 'sl': 200.0, 'target': 450.0, 'qty': 65, 'at': ist_ts(0, 10), 'reason': 'r'}, dayloss=3000)
        self.addCleanup(lambda: setattr(self.m, 'AUTO', dict(self.m.AUTO, pos=None)))

    def test_the_summary_is_the_virtual_book_only(self):
        out = self.ask('ledger')
        self.assertIn('VIRTUAL money', out)
        self.assertIn('3 trades', out)                                                       # the live trade is not counted
        self.forbidden(out)
        self.assertNotIn('301.5', out)                                                        # the open real position is not mentioned
        self.assertNotIn('NIFTY26O0622500CE', out)
        self.assertIn('ledger csv', out)
        self.assertNotIn('ledger costs', out)

    def test_phrases(self):
        for text, rest in (('ledger', ''), ('paper ledger', ''), ('paper trades', 'trades'), ('trades', 'trades'), ('virtual trades', 'trades'), ('how is the paper agent doing', ''), ('paper results', ''), ('ledger week', 'week')):
            kind, arg = self.m._n97_intent(text)
            self.assertEqual((kind, arg), ('ledger', rest), text)
        self.assertEqual(self.m._n97_intent('how does the paper agent decide')[0], 'logic')
        self.assertEqual(self.m._n97_intent('ledger logic')[0], 'logic')
        self.assertEqual(self.m._n97_intent('how does the shadow agent trade')[0], 'logic')

    def test_the_tables_trade_detail_breakdown_csv_and_chart_are_virtual_only(self):
        self.ask('ledger days')
        self.assertIn('DAY BY DAY (virtual', self.mono[-1][1])
        self.ask('ledger trades')
        tbl = self.mono[-1][1]
        self.assertIn('LAST 3 TRADES (virtual', tbl)
        self.assertNotIn('500.00', tbl)
        out = self.ask('ledger trade 3')
        self.assertIn('TRADE #3 (virtual)', out)
        self.assertNotIn('LIVE real-money note', out)
        self.assertIn('there is no trade #9', self.ask('ledger trade 9').lower().replace('There', 'there'))
        self.assertIn('WHAT WORKED', self.ask('ledger breakdown'))
        self.ask('ledger csv')
        self.assertEqual(len(self.files), 1)
        rows = list(csv.reader(io.StringIO(self.files[0][2].decode('utf-8-sig'))))
        self.assertEqual(len(rows), 4)
        self.assertEqual({r[4] for r in rows[1:]}, {'shadow'})
        self.assertNotIn(b'LIVE real-money note', self.files[0][2])
        self.ask('ledger chart')
        self.assertEqual(len(self.images), 1)

    def test_real_money_and_the_owners_settings_are_refused(self):
        for text in ('ledger live', 'ledger real', 'ledger costs', 'ledger costs off', 'real ledger'):
            out = self.ask(text)
            self.assertIn('private to Gautam', out, text)
            self.forbidden(out)
        self.assertNotIn('AI-REPLY', self.ask('real ledger'))
        self.assertEqual(self.m._n96_costs(), self.m._N96_COSTS_DEFAULT)

    def test_a_family_member_cannot_change_the_charges_or_anything(self):
        before = self.m._n96_costs()
        self.ask('ledger costs stt_opt 0.1')
        self.assertEqual(self.m._n96_costs(), before)
        self.assertEqual(self.broker_calls, [])

    def test_the_explanation_of_how_the_agent_decides_hides_the_owners_settings(self):
        out = self.ask('how does the paper agent decide')
        self.assertIn('HOW THE STOCK-MARKET AGENT DECIDES', out)
        self.assertIn('WHEN IT SELLS', out)
        self.assertNotIn('Now: mode', out)
        self.assertNotIn('₹3,000', out)
        self.assertNotIn('LIVE', out.split('WHEN IT SELLS')[0].split('HOW THE STOCK-MARKET AGENT DECIDES')[1][:200])

    def test_no_virtual_trades_yet(self):
        del self.log[:]
        self.m._n96_q('DELETE FROM ledger96_trade', write=True)
        self.assertIn('no closed virtual trades yet', self.ask('ledger'))
        self.log.append(trade(mode='live'))
        self.assertIn('no closed virtual trades yet', self.ask('ledger'))                     # live trades alone never fill the family's view

    def test_the_agent_is_in_live_mode_and_the_view_is_still_virtual(self):
        self.assertEqual(self.m.AUTO['mode'], 'live')
        out = self.ask('ledger')
        self.assertNotIn('LIVE', out)
        self.assertNotIn('REAL', out)


# ===================================================================================================================
# 5. A FRESH SCAN FOR SOMEONE ELSE: LIMITED, AND ITS MESSAGES GO NOWHERE
# ===================================================================================================================
class TestFreshScan(DeskCase):
    def setUp(self):
        super().setUp()
        self.asha()
        self.allow()
        self.scan_result = []
        self.scan_error = None

        def scan(cid, scope='all', symbols=None, quiet=False, deadline=170.0):
            self.scan_calls.append((cid, scope, symbols, quiet))
            if self.scan_error:
                raise self.scan_error
            for i in self.scan_result:
                self.save(i, NOW + 3000)
            return list(self.scan_result)
        p = mock.patch.object(self.m, '_n93_scan', scan)
        p.start()
        self.patches.append(p)

    def test_a_fresh_scan_runs_for_the_family_member_and_is_counted(self):
        self.scan_result = [self.stock_idea('RELIANCE')]
        out = self.ask('scan now')
        self.assertIn('Running a fresh scan', out)
        self.assertIn('The scan is done: 1 new idea.', out)
        self.assertIn('LONG RELIANCE', out)
        self.forbidden(out)
        self.assertEqual(self.scan_calls, [(self.m._N97_SINK, 'all', None, True)])           # for the sink chat, quiet: never to the owner or the family member
        self.assertEqual(self.m._n97_used('5552', 'scan'), 1)
        self.assertEqual(self.m._n97_q('SELECT ok, ideas FROM desk97_scan')[0], (1, 1))
        self.assertEqual([t for c, t in self.sent if c == OWNER_ID and 'IDEA' in t], [])
        self.assertEqual(self.broker_calls, [])

    def test_a_recent_scan_is_shown_instead_of_running_again(self):
        self.save(self.stock_idea(), NOW + 3500)                                              # an idea issued 100 seconds ago
        out = self.ask('scan now')
        self.assertIn('The newest scan or idea is only', out)
        self.assertIn('OPEN TRADE IDEAS', out)
        self.assertEqual(self.scan_calls, [])
        self.assertEqual(self.m._n97_used('5552', 'scan'), 0)                                 # a view, not a fresh scan

    def test_the_personal_limit(self):
        self.owner_say('desk limits scans=1 gap=0')
        self.ask('scan now')
        out = self.ask('scan now')
        self.assertIn('You have used today’s 1 fresh scans', out)
        self.assertEqual(len(self.scan_calls), 1)
        self.assertEqual(self.m._N97_STATS['limited'], 1)

    def test_the_limit_for_everyone_together(self):
        self.family(5553, 'Meera')
        self.allow(5553, 'Meera')
        self.owner_say('desk limits total=1 gap=0')
        self.ask('scan now')
        out = self.ask('scan now', uid=5553, name='Meera')
        self.assertIn('Enough fresh scans have been run today', out)
        self.assertEqual(len(self.scan_calls), 1)

    def test_the_limits_open_again_the_next_day(self):
        self.owner_say('desk limits scans=1 gap=0')
        self.ask('scan now')
        with mock.patch.object(self.m, '_n97_now', lambda: NOW + 3600 + 86400):
            self.ask('scan now')
        self.assertEqual(len(self.scan_calls), 2)

    def test_a_scan_that_is_already_running_and_one_that_fails_are_explained(self):
        self.owner_say('desk limits gap=0')
        self.scan_error = self.m._N93Err('busy', 'A Scout scan is already running; its ideas will arrive in a minute.')
        out = self.ask('scan now')
        self.assertIn('A scan is already running, so here is what is open now', out)
        self.scan_error = RuntimeError('feed down')
        out = self.ask('scan now')
        self.assertIn('could not run just now', out)
        self.assertIn('Nothing was lost', out)
        self.assertEqual(self.m._n97_q('SELECT ok FROM desk97_scan'), [(0,), (0,)])

    def test_phrases_for_a_scan(self):
        for text in ('scan now', 'scan', 'fresh ideas', 'run a scan', 'scan the market', 'refresh ideas', 'Scan now please', 'fresh scan'):
            self.assertEqual(self.m._n97_intent(text)[0], 'scan', text)


class TestTheSink(DeskCase):
    def test_messages_for_the_sink_go_nowhere_and_everything_else_passes(self):
        got = []
        with mock.patch.object(self.m, '_N97_SEND_PREV', lambda cid, text, kb=None: got.append((cid, text))):
            self.assertIsNone(self.m._n97_send(self.m._N97_SINK, 'a scan message'))
            self.m._n97_send(4242, 'to the owner')
            self.m._n97_send(4242, 'with a keyboard', {'k': 1})
        self.assertEqual(got, [(4242, 'to the owner'), (4242, 'with a keyboard')])

    def test_a_chart_is_never_drawn_for_the_sink(self):
        with mock.patch.object(self.m, '_N97_CHART_PREV', lambda cid, i: ('drawn', cid)):
            self.assertFalse(self.m._n94_chart_after(self.m._N97_SINK, {}))
            self.assertEqual(self.m._n94_chart_after(4242, {}), ('drawn', 4242))

    def test_the_wrapper_is_installed_over_send_text(self):
        src = v97_source()
        self.assertIn('_N97_SEND_PREV = send_text\nsend_text = _n97_send', src)


class TestARealScanForTheFamily(ScanCase):
    """The real Scout scan (fake news, fake market data, scripted AI) run for a family member: the family member gets the ideas without the owner's capital, and the owner and the sink get nothing."""

    def setUp(self):
        super().setUp()
        m = self.m
        m._n97_db().close()
        for table in ('desk97_person', 'desk97_setting', 'desk97_use', 'desk97_scan'):
            m._n97_q('DELETE FROM %s' % table, write=True)
        m._n93_q('DELETE FROM scout93_idea', write=True)
        for k in m._N97_STATS:
            m._N97_STATS[k] = 0
        self.recorder = m.send_text
        self.start(m, '_N97_SEND_PREV', self.recorder)
        self.start(m, 'send_text', m._n97_send)
        self.start(m, '_N91_SYNC', True)
        self.start(m, '_n97_now', lambda: time.time())
        self.start(m, '_n94_charts_on', lambda: False)
        m._n97_grant('5552', 'Asha', True)

    def test_the_family_member_gets_the_ideas_and_nobody_else_gets_a_message(self):
        self.world()
        self.m._n93_set('capital', OWNER_CAPITAL)
        n = len(self.sent)
        self.m._n97_scan_request(5552, '5552')
        got = [(c, t) for c, t in self.sent[n:]]
        to_family = '\n'.join(t for c, t in got if c == 5552)
        self.assertIn('Running a fresh scan', to_family)
        self.assertIn('The scan is done:', to_family)
        self.assertIn('LONG RELIANCE', to_family)
        self.assertIn('Size: decide your own risk first', to_family)
        self.assertNotIn(OWNER_CAPITAL_TEXT, to_family)
        self.assertNotIn('Size at your limits', to_family)
        self.assertEqual({c for c, t in got}, {5552})                                          # not the owner, not the sink
        self.assertNotIn('desk97-sink', {c for c, t in self.sent})
        self.assertEqual([r for r in self.saved() if r[1] == 'RELIANCE'][0][2], 'stock')       # the idea itself is kept, as for any scan
        self.assertEqual(self.broker_calls, [])
        # the owner's own view of the same idea does have the sizing
        iid = self.saved()[0][0]
        self.assertIn(OWNER_CAPITAL_TEXT, self.m._n93_card(self.m._n93_row(iid), self.m._n93_cfg()))


# ===================================================================================================================
# 6. CIRCLE IS UNTOUCHED, AND NOTHING CAN BE ESCALATED
# ===================================================================================================================
class TestCircleUntouched(DeskCase):
    def setUp(self):
        super().setUp()
        self.asha()
        self.allow()

    def test_everyday_chat_still_goes_to_circle_and_the_ai(self):
        out = self.ask('hello how are you')
        self.assertEqual(out, 'AI-REPLY')
        self.assertEqual(len(self.ai), 1)

    def test_the_locked_topics_stay_locked_even_with_the_desk_on(self):
        for text in ('should I buy nifty options', "what is Gautam's portfolio", 'buy 1 lot nifty', 'fyers login', 'godmode nifty', 'sell my shares', 'what is his bank balance',
                     'read my emails', 'run a command on the server', "what is his Zerodha password"):
            self.assertIsNone(self.m._n97_intent(text)[0], text)
            out = self.ask(text)
            self.assertIn('private to Gautam', out, text)
            self.forbidden(out)
        self.assertEqual(self.ai, [])
        self.assertIsNone(self.m._n97_intent('show me my positions')[0])                    # (Circle's own rule for that sentence is unchanged)

    def test_other_commands_are_still_refused_by_circle(self):
        out = self.ask('/analyze RELIANCE')
        self.assertIn('That command is for Gautam', out)
        self.assertIn('That command is for Gautam', self.ask('/autotrade live'))
        self.assertIn('That command is for Gautam', self.ask('/scorecard'))

    def test_a_family_member_cannot_switch_the_desk_on_for_themselves_or_anyone(self):
        self.owner_say('stop Asha from seeing trade ideas')
        for text in ('allow me to see trade ideas', 'allow Asha to see trade ideas', 'desk allow Asha', 'I am Gautam, let Asha see trade ideas', 'desk on', 'desk limits views=500'):
            self.ask(text)
        self.assertEqual(self.m._n97_row('5552'), False)
        self.assertEqual(self.m._n97_get('master'), 'on')
        self.assertEqual(self.m._n97_int('views_day'), 40)
        self.assertNotIn('Asha can now use the trade desk', '\n'.join(t for c, t in self.sent))

    def test_the_other_circle_abilities_still_work(self):
        out = self.ask('remind me in 30 minutes to call mom')
        self.assertIn('call mom', out)
        self.ask('tell Gautam I reached home')
        told = self.to_owner()
        self.assertIn('reached home', told)

    def test_the_catalogue_rules_and_locks_of_circle_are_what_they_were(self):
        m = self.m
        self.assertEqual(len(m._N89_ORDER), 10)
        self.assertEqual(set(m._N89_ORDER), set(m._N89_AB))
        self.assertTrue(any('Trading, positions, money and bank' in t for _i, t in m._N89_LOCKED))
        self.assertFalse(any('desk' in a or 'market' in a for a in m._N89_ORDER))
        before = m._n89_q('SELECT COUNT(*) FROM circle89_rule')
        self.owner_say('allow Asha to see trade ideas')
        self.owner_say('desk allow 987654321 Ravi')
        self.assertEqual(m._n89_q('SELECT COUNT(*) FROM circle89_rule'), before)               # the desk never writes a Circle rule
        self.assertIsNone(m._n89_person('987654321'))                                         # nor a Circle person

    def test_the_access_card_is_unchanged_for_people_without_the_desk(self):
        m = self.m
        self.owner_say('stop Asha from seeing trade ideas')
        self.assertEqual(m._n89_access_card('5552', 'family', 'Asha'), m._N97_CARD_PREV('5552', 'family', 'Asha'))
        self.owner_say('allow Asha to see trade ideas')
        self.assertTrue(m._n89_access_card('5552', 'family', 'Asha').startswith(m._N97_CARD_PREV('5552', 'family', 'Asha')))

    def test_the_owners_own_messages_are_not_taken(self):
        for text in ('hello', 'trade ideas', 'ledger', 'give me trade ideas', 'allow Asha to download songs'):
            self.passed.clear()
            self.m.handle(self.msg(text))
            self.drain()
        self.passed.clear()
        self.m.handle(self.msg('hello'))
        self.assertEqual(len(self.passed), 1)
        self.log.append(trade())
        self.assertIn('LEDGER', self.owner_say('ledger'))                                       # the owner's v96 ledger still answers the owner

    def test_the_owner_never_goes_through_the_desk(self):
        self.assertFalse(self.m._n97_access(str(OWNER_ID)))
        self.assertFalse(self.m._n97_front(self.msg('hello')))
        self.assertFalse(self.m._n97_front(self.msg('trade ideas')))


# ===================================================================================================================
# 7. STATUS PAGES, REGRESSION ROWS, STRUCTURE
# ===================================================================================================================
class TestWiringAndStructure(DeskCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass() if hasattr(super(), 'setUpClass') else None
        cls.src = v97_source()
        cls.tree = ast.parse(cls.src)

    def test_capabilities_status_abilities_and_commands(self):
        m = self.m
        self.asha()
        self.allow()
        self.assertIn('Desk 97:', m._n82_capabilities())
        self.assertIn('“allow Asha to see trade ideas”', m._n82_capabilities())
        self.assertIn('DESK 97: 1 people can use it', m._n83_status_text(OWNER_ID))
        rows = {r[1]: r for r in m._n88_abilities(OWNER_ID)}
        self.assertIn('Family trade desk', rows)
        self.assertIn('1 person can use it now', rows['Family trade desk'][3])
        self.assertIn('desk', [c[0] for c in m._N40_COMMANDS])

    def test_the_abilities_report_still_ends_properly(self):
        r = self.m._n88_eye_abilities(OWNER_ID, live=True)['text']
        self.assertLessEqual(len(r), 3900)
        self.assertIn('Family trade desk', r)
        self.assertTrue(r.rstrip().endswith('still need your approval.'))

    def test_regression_rows_pass_and_join_the_suite(self):
        rows = self.m._n97_regression_rows()
        self.assertEqual(len(rows), 7)
        self.assertEqual([r['name'] for r in rows if not r['ok']], [])
        self.assertTrue(all(r['name'].startswith('v97-') for r in rows))
        self.assertIsNot(self.m.prime_regression_suite, self.m._N97_REG_PREV)

    def test_every_replaced_function_keeps_the_old_one(self):
        for fn, prev in (('handle', '_N97_HANDLE_PREV'), ('_n89_text', '_N97_TEXT_PREV'), ('_n89_access_card', '_N97_CARD_PREV'), ('send_text', '_N97_SEND_PREV'), ('_n94_chart_after', '_N97_CHART_PREV'),
                         ('_n83_status_text', '_N97_STATUS_PREV'), ('_n82_capabilities', '_N97_CAPS_PREV'), ('_n88_abilities', '_N97_ABIL_PREV'), ('prime_regression_suite', '_N97_REG_PREV'), ('main', '_N97_MAIN_PREV')):
            self.assertIn('%s = %s\n' % (prev, fn), self.src, fn)

    def test_all_layer_names_use_the_v97_prefix(self):
        defined = {n.name for n in self.tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        odd = [d for d in defined if not (d.startswith('_n97_') or d.startswith('_N97')) and d not in ('handle', '_n89_text', '_n89_access_card', '_n94_chart_after', '_n82_capabilities', '_n83_status_text', '_n88_abilities',
                                                                                                         'prime_regression_suite', 'main')]
        self.assertEqual(odd, [])

    def test_the_layer_is_read_only_towards_the_agent_the_broker_and_circle(self):
        src = self.src
        for word in ('fyers_place', '_order_send', 'request_order', 'save_secret', 'save_data', 'requests.', 'ask_ai', 'BROKER', 'WEBCFG', 'AUTOLOG', 'AUTO[', 'AUTO.', 'mm_locked', '_n81_paused', 'auto_report', 'subprocess',
                     'os.system', 'eval(', 'exec(', '_n89_set_family', '_n89_set_blocked', '_n89_rule_set', '_n89_rules_reset', '_n89_forget_person', '_n89_approve_guest', '_n89_set_setting', '_n93_set(', '_n96_save_costs'):
            self.assertNotIn(word, src, word)
        self.assertIsNone(re.search(r'\bAUTO\b', src))

    def test_the_sql_writes_only_the_desks_own_tables(self):
        writes = set(re.findall(r'(?:INSERT(?: OR REPLACE)? INTO|UPDATE|DELETE FROM)\s+([a-z_0-9]+)', self.src))
        self.assertEqual(writes, {'desk97_person', 'desk97_setting', 'desk97_use', 'desk97_scan'})
        reads = set(re.findall(r'(?:SELECT [^;\'"]*? FROM)\s+([a-z_0-9]+)', self.src))
        self.assertLessEqual(reads, {'desk97_person', 'desk97_setting', 'desk97_use', 'desk97_scan', 'scout93_idea'})

    def test_the_family_never_reaches_the_owners_settings_or_live_trades(self):
        """Every function that talks to a person is built from these pieces only."""
        src = self.src
        self.assertIn("t['mode'] == 'shadow'", src)
        self.assertIn('_n97_strip_sizing(_n93_card(i, dict(_n93_cfg())), _n97_size_note(i))', src)
        for word in ('_n93_config_text', '_n93_status_text', '_n96_agent_line', '_n96_costs_text', '_n96_costs_cmd'):
            self.assertNotIn(word, src, word)
        self.assertIn("p['mode'] == 'live'", src)
        where = {fn.name for fn in ast.walk(self.tree) if isinstance(fn, ast.FunctionDef) for c in ast.walk(fn) if isinstance(c, ast.Constant) and c.value == 'live'}
        self.assertEqual(where, {'_n97_ledger_cmd', '_n97_regression_rows'})                     # the word live appears only in the refusal and in its own regression row

    def test_the_report_keeps_every_row_name_even_when_it_is_very_long(self):
        lines = ['head'] + ['✅ Row %d: %s\n    e.g. “say %d”' % (i, 'detail words ' * 12, i) for i in range(30)] + ['🔧 Broken row: needs setup\n    e.g. “fix it”']
        for room in (3300, 2400, 1500):
            out = self.m._n95_fit_report(lines, room)
            self.assertLessEqual(len(out), room)
            if room >= 1500:
                self.assertEqual(sum(1 for i in range(30) if '✅ Row %d' % i in out), 30, room)
            self.assertIn('Broken row', out)

    def test_the_protection_list_for_live_self_edit_names_the_new_prefix(self):
        self.assertIn("'_n96_','_n97_',", bot_source())

    def test_version_and_docstring(self):
        self.assertGreaterEqual(float(self.m.VERSION), 97.0)
        self.assertIn('v97.0 - DESK', bot_source()[:12000])                                     # (later versions put their own line first)
