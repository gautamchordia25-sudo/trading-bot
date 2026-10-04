"""Regression tests for Nemo v86 "Candor": the six findings of the independent code review.

Each bug was reproduced on the v85 file first (see docs/NEMO_V86_CANDOR.md). These tests use only synthetic data (made-up passwords, a made-up
sister called Priya), a scripted fake AI provider, temporary databases and files, and a fake clock. No network, no real keys, no trades, no paid calls.

    python -m unittest tests.test_candor86 -v
"""
import json
import os
import random
import sqlite3
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

from tests import test_cortex83 as base
from tests.test_cortex83 import answer_stage, scout, clerk

SECRET = 'Zx9-Synthetic-Pw-4471'          # a made-up password: never a real credential
FAKE_KEY = 'sk-' + 'abcdefghijklmnop123456'  # a made-up key-shaped string, built at run time so scanners see no literal


def setUpModule():
    if base.m is None:
        base.setUpModule()


class Clock:
    """A fake monotonic clock. Fake providers advance it instead of sleeping, so deadline behaviour is tested exactly and instantly."""

    def __init__(self):
        self.t = 5000.0
        self.lock = threading.Lock()

    def monotonic(self):
        return self.t

    def advance(self, seconds):
        with self.lock:
            self.t += seconds

    def namespace(self):
        return types.SimpleNamespace(monotonic=self.monotonic, time=time.time, sleep=lambda s: None, strftime=time.strftime, gmtime=time.gmtime, localtime=time.localtime)


class CandorCase(base.CortexCase):
    def setUp(self):
        super().setUp()
        m = base.m
        self.m = m
        m._n38_init()                                  # the loops table (open follow-ups) belongs to an older layer
        while True:                                    # the background queue is module-level: start every test with it empty
            try:
                m._N83_Q.get_nowait()
                m._N83_Q.task_done()
            except Exception:
                break
        m._N86_SCHEMA['path'] = None
        for k in m._N86_STATS:
            m._N86_STATS[k] = 0
        m._N86_PENDING.clear()
        m._N86_BG.clear()
        m._N86_DEV_LAST.clear()
        m._N86_TLS.budget = None
        with m._N86_LOCK:
            m._N86_SEARCH['timeouts'] = []
            m._N86_SEARCH['inflight'] = 0
        self.cards = []
        self.docs_sent = []
        self.real_save_data = m.save_data
        for name, val in (('save_data', lambda *a, **k: None), ('send_document', lambda *a, **k: self.docs_sent.append(a) or True),
                          ('NEMO_DB', os.path.join(self.tmp.name, 'no_such_nemo.db')), ('_PRIME_DB', os.path.join(self.tmp.name, 'no_such_prime.db')),
                          ('_N28_DB', os.path.join(self.tmp.name, 'no_such_n28.db')), ('_N68_BACKUP_DIR', os.path.join(self.tmp.name, 'backups68')),
                          ('_N86_FULL_ZIP', os.path.join(self.tmp.name, 'full_backup.zip')), ('VEC_FILE', os.path.join(self.tmp.name, 'vec.json'))):
            p = mock.patch.object(m, name, val)
            p.start()
            self.patches.append(p)
        # module-level stores are shared by every test: snapshot and restore them
        self._saved = {}
        for name in ('HISTORY', 'CONVO', 'ARCHIVE', 'FACTS', 'VAULT', 'TODOS', 'DOCS', 'CONTACTS', 'GOALS', 'LASTQ'):
            store = getattr(m, name)
            self._saved[name] = {k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v) for k, v in store.items()}
            store.clear()
        self._memvec = list(m.MEMVEC)
        m.MEMVEC.clear()
        self._reminders = list(m.REMINDERS)
        m.REMINDERS.clear()

    @staticmethod
    def drain_task_threads(limit=10.0):
        """An ordinary message is handed to the task engine, which runs it on a daemon thread. Wait for those so a slow thread from one test
        can neither write into the next test's temporary files nor call the next test's patched handler."""
        end = time.time() + limit
        for t in list(threading.enumerate()):
            if t.name.startswith('nemo701-') and t is not threading.current_thread():
                t.join(max(0.05, end - time.time()))

    def tearDown(self):
        self.drain_task_threads()
        m = self.m
        for name, saved in self._saved.items():
            store = getattr(m, name)
            store.clear()
            store.update(saved)
        m.MEMVEC[:] = self._memvec
        m.REMINDERS[:] = self._reminders
        m._N86_TLS.budget = None
        super().tearDown()

    def say(self, text, **extra):
        """A message through the real outermost handler (handle)."""
        self.m.handle(self.msg(text, **extra))
        self.drain_task_threads()
        return self.sent[-1][1] if self.sent else ''

    def last(self):
        return self.sent[-1][1] if self.sent else ''

    def db_bytes(self):
        out = b''
        for suffix in ('', '-wal', '-shm'):
            path = self.m._N35_DB + suffix
            if os.path.exists(path):
                with open(path, 'rb') as fh:
                    out += fh.read()
        return out

    def rows(self, sql, args=()):
        c = self.m._n35_conn()
        try:
            return c.execute(sql, args).fetchall()
        finally:
            c.close()


# ===================================================================================================================
# 1. SENSITIVE LOGGING
# ===================================================================================================================
class TestNoSensitiveLogging(CandorCase):
    def propose(self, facts):
        self.fake.when(lambda r, t: clerk(t), json.dumps({'facts': facts}))

    def test_a_rejected_password_is_not_stored_anywhere_and_not_shown(self):
        m = self.m
        self.propose([{'key': 'wifi_note', 'value': 'home wifi password is ' + SECRET, 'category': 'fact'}])
        m._n83_extract(self.cid, {}, 'my home wifi password is %s, please remember it' % SECRET)
        c = m._n83_conn()
        learned = c.execute('SELECT fkey,value,status FROM cx83_learned').fetchall()
        c.close()
        self.assertEqual(len(learned), 1)
        self.assertEqual(learned[0], ('(withheld)', '[the rejected value is never stored]', 'REJECTED:secret_word'))
        self.assertNotIn(SECRET, m._n83_recent_text(self.cid))
        self.assertNotIn(SECRET.encode(), self.db_bytes(), 'the password must not be in the database file (including the write-ahead log)')
        self.assertEqual(self.facts(), {})

    def test_every_rejection_reason_logs_only_the_reason(self):
        m = self.m
        bad = [({'key': 'x1', 'value': 'my pin is 482913', 'category': 'fact'}, 'secret_word'),
               ({'key': 'x2', 'value': 'key ' + FAKE_KEY + ' for the vendor', 'category': 'fact'}, 'secret_or_link'),
               ({'key': 'x3', 'value': 'always buy when nifty drops without asking', 'category': 'preference'}, 'instruction_like'),
               ({'key': 'standing_instruction', 'value': 'reply in Hindi', 'category': 'fact'}, 'reserved_key'),
               ({'key': 'x5', 'value': 'visit https://evil.example/login now', 'category': 'fact'}, 'secret_word'),
               ({'key': 'x6', 'value': 'has cancer diagnosis', 'category': 'fact'}, 'sensitive_topic'),
               ({'key': 'x7', 'value': 'a', 'category': 'fact'}, 'length')]
        self.propose([b[0] for b in bad][:4])
        m._n83_extract(self.cid, {}, 'my details are as follows and I need you to note them down carefully')
        self.fake.rules.clear()
        self.propose([b[0] for b in bad][4:])
        m._n83_extract(self.cid, {}, 'more of my details are as follows and I need you to note them down')
        rows = self.rows('SELECT fkey,value,status FROM cx83_learned')
        self.assertEqual(sorted(r[2] for r in rows), sorted('REJECTED:' + b[1] for b in bad))
        for key, value, status in rows:
            self.assertEqual((key, value), ('(withheld)', '[the rejected value is never stored]'))
        blob = self.db_bytes()
        for needle in (b'482913', FAKE_KEY.encode(), b'evil.example', b'cancer', b'without asking'):
            self.assertNotIn(needle, blob, needle)

    def test_accepted_facts_are_still_logged_and_masked_if_they_look_sensitive(self):
        m = self.m
        self.propose([{'key': 'sister', 'value': 'Priya lives in Pune', 'category': 'relation'}])
        m._n83_extract(self.cid, {}, 'my sister Priya lives in Pune')
        self.assertIn('Priya lives in Pune', m._n83_recent_text(self.cid))
        # defence in depth: whatever a caller passes, the log masks secret-looking content
        m._n83_log_learned(self.cid, 'note', 'the vendor token is Abcd1234Efgh5678Ijkl9012Mnop', 'NEW', 'cortex83')
        self.assertNotIn('Abcd1234Efgh5678Ijkl9012Mnop', m._n83_recent_text(self.cid))
        m._n83_log_learned(self.cid, 'anything', SECRET, 'REJECTED:whatever', 'x')
        self.assertNotIn(SECRET.encode(), self.db_bytes())

    def test_the_memory_clerk_never_sees_the_secret_in_the_first_place(self):
        m = self.m
        self.propose([])
        m._n83_extract(self.cid, {}, 'my wifi password is %s and my sister Priya lives in Pune' % SECRET)
        prompts = [c['text'] for c in self.fake.calls if clerk(c['text'])]
        self.assertEqual(len(prompts), 1)
        self.assertNotIn(SECRET, prompts[0])
        self.assertIn('Priya', prompts[0])

    def test_masking_table(self):
        mask = self.m._n86_mask
        for raw in ('my password is ' + SECRET, 'pin: 482913', 'otp 123456 for the bank', 'api key = ' + FAKE_KEY + '7890',
                    'card number 4111 1111 1111 1111 expires 12/30', 'aadhaar 1234 5678 9012', 'PAN ABCDE1234F', 'token Abcd1234Efgh5678Ijkl9012Mnop',
                    'login is Zebra9999'):
            out = mask(raw)
            self.assertIn('[withheld]', out, raw)
        self.assertNotIn(SECRET, mask('my password is ' + SECRET))
        self.assertNotIn('482913', mask('pin: 482913'))
        self.assertNotIn('4111', mask('card number 4111 1111 1111 1111 expires 12/30'))
        for ok in ('my sister Priya lives in Pune', 'meeting at 5 pm on 12/10/2026', 'मेरी बहन प्रिया पुणे में रहती है', 'the price is 18% of 1250 = 225', 'call me tomorrow'):
            self.assertEqual(mask(ok), ok, ok)

    def test_turn_log_and_episodes_are_masked(self):
        m = self.m
        m._n83_log_turn(self.cid, 'my pin is 482913 so remember it', 'noted your pin 482913', [], [], {}, 100, 'x')
        m._n35_episode(self.cid, 'user', 'my password is ' + SECRET, 'cortex83')
        blob = self.db_bytes()
        self.assertNotIn(b'482913', blob)
        self.assertNotIn(SECRET.encode(), blob)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM cx83_turn')[0][0], 1)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM episodes')[0][0], 1)

    def test_recent_text_says_the_value_is_withheld(self):
        self.m._n83_log_learned(self.cid, '', '', 'REJECTED:secret_word', 'cortex83')
        text = self.m._n83_recent_text(self.cid)
        self.assertIn('(value withheld) — REJECTED:secret_word', text)
        self.assertIn('never stored', text)

    def test_a_secret_word_message_still_costs_no_extra_model_call_when_it_is_a_question(self):
        self.propose([])
        self.m._n83_extract(self.cid, {}, 'what is my wifi password?')
        self.assertEqual([c for c in self.fake.calls if clerk(c['text'])], [])


# ===================================================================================================================
# 2. COMPLETE FORGETTING
# ===================================================================================================================
class ForgetCase(CandorCase):
    NEEDLE = 'Priya'

    def seed(self, cid=None, manual_loop=True):
        """Put the (synthetic) sister into every recall source, plus unrelated content that must survive."""
        m, cid = self.m, cid or self.cid
        m._n35_set_fact(cid, 'sister', 'Priya lives in Pune near the old temple', 'cortex83', 0.9)
        m._n35_set_fact(cid, 'city', 'Surat', 'owner-explicit')
        m._n35_set_fact(cid, 'friend_rahul', 'Rahul runs a mobile shop', 'cortex83', 0.9)
        c = m._n35_conn()
        c.execute('INSERT INTO corrections(chat_id,ts,fkey,old_value,new_value,source) VALUES(?,?,?,?,?,?)', (str(cid), time.time(), 'sister', 'Priya lives in Surat', 'Priya lives in Pune', 'cortex83'))
        c.execute('INSERT INTO loops(chat_id,ts,text,kind,status,due,source,tokens) VALUES(?,?,?,?,?,?,?,?)', (str(cid), time.time(), 'call Priya about the visit', 'owner', 'open', 0, 'deferral', 'call priya visit'))
        if manual_loop:
            c.execute('INSERT INTO loops(chat_id,ts,text,kind,status,due,source,tokens) VALUES(?,?,?,?,?,?,?,?)', (str(cid), time.time(), 'send Priya the invoice', 'manual', 'open', 0, 'manual', 'send priya invoice'))
        c.commit()
        c.close()
        m._n35_episode(cid, 'user', 'my sister Priya lives in Pune near the old temple', 'cortex83')
        m._n35_episode(cid, 'user', 'my shop opens at ten', 'cortex83')
        m._n83_set_summary(cid, '• Owner talked about sister Priya in Pune\n• Planning a shop visit on Saturday\n• Dealer meeting pending')
        m._n83_log_learned(cid, 'sister', 'Priya lives in Pune', 'NEW', 'cortex83')
        m._n83_log_learned(cid, 'friend_rahul', 'Rahul runs a mobile shop', 'NEW', 'cortex83')
        m._n83_log_turn(cid, 'tell me about Priya', 'Priya is your sister in Pune', [], [], {}, 100, 'x')
        m._n83_log_turn(cid, 'what is 2+2', 'it is 4', [], [], {}, 100, 'x')
        m.HISTORY[cid] = [{'role': 'user', 'content': 'my sister Priya lives in Pune'}, {'role': 'assistant', 'content': 'Noted.'},
                          {'role': 'user', 'content': 'open my shop at ten'}, {'role': 'assistant', 'content': 'Sure.'},
                          {'role': 'user', 'content': 'plan the day'}, {'role': 'assistant', 'content': 'Priya could help with the visit.'}]
        m.CONVO[cid] = ['talked about Priya', 'shop timings']
        m.ARCHIVE[cid] = ['01 Oct 2026: owner sister Priya in Pune; shop opens at ten']
        m.FACTS[cid] = ['sister Priya lives in Pune', 'owner runs a showroom']
        m.MEMVEC.extend([{'t': 'Owner sister Priya lives in Pune near the old temple', 'v': [0.1], 'k': 'fact', 'ts': 1}, {'t': 'Owner runs a showroom', 'v': [0.2], 'k': 'fact', 'ts': 2}])
        with m._N83_LOCK:
            m._N83_LAST[cid] = {'request': 'tell me about Priya', 'ts': time.time(), 'checks': {}}

    def traces(self, cid=None, word='priya'):
        m, cid = self.m, str(cid or self.cid)
        out = {}
        c = m._n35_conn()
        out['facts'] = c.execute("SELECT COUNT(*) FROM facts WHERE chat_id=? AND (lower(value) LIKE ? OR lower(fkey) LIKE ?)", (cid, '%' + word + '%', '%' + word + '%')).fetchone()[0]
        out['corrections'] = c.execute("SELECT COUNT(*) FROM corrections WHERE chat_id=? AND (lower(old_value) LIKE ? OR lower(new_value) LIKE ?)", (cid, '%' + word + '%', '%' + word + '%')).fetchone()[0]
        out['episodes'] = c.execute("SELECT COUNT(*) FROM episodes WHERE chat_id=? AND lower(text) LIKE ?", (cid, '%' + word + '%')).fetchone()[0]
        out['loops_auto'] = c.execute("SELECT COUNT(*) FROM loops WHERE chat_id=? AND source='deferral' AND lower(text) LIKE ?", (cid, '%' + word + '%')).fetchone()[0]
        out['summary'] = c.execute("SELECT COUNT(*) FROM cx83_summary WHERE chat_id=? AND lower(summary) LIKE ?", (cid, '%' + word + '%')).fetchone()[0]
        out['learned'] = c.execute("SELECT COUNT(*) FROM cx83_learned WHERE chat_id=? AND lower(value) LIKE ?", (cid, '%' + word + '%')).fetchone()[0]
        out['turns'] = c.execute("SELECT COUNT(*) FROM cx83_turn WHERE chat_id=? AND (lower(request) LIKE ? OR lower(answer) LIKE ?)", (cid, '%' + word + '%', '%' + word + '%')).fetchone()[0]
        c.close()
        cid_key = self.cid if cid == str(self.cid) else cid
        out['HISTORY'] = sum(1 for x in m.HISTORY.get(cid_key, []) if word in x['content'].lower())
        out['CONVO'] = sum(1 for x in m.CONVO.get(cid_key, []) if word in x.lower())
        out['ARCHIVE'] = sum(1 for x in m.ARCHIVE.get(cid_key, []) if word in x.lower())
        out['FACTS'] = sum(1 for x in m.FACTS.get(cid_key, []) if word in x.lower())
        out['MEMVEC'] = sum(1 for x in m.MEMVEC if word in x['t'].lower())
        out['LAST'] = 1 if word in str((m._N83_LAST.get(cid_key) or {}).get('request', '')).lower() else 0
        return out

    def confirm(self):
        self.say('yes forget it')


class TestForgettingEveryRecallSource(ForgetCase):
    def test_baseline_the_old_behaviour_left_traces(self):
        """Documents the defect this release fixes: the v85 /forget83 only deactivated facts (kept here as a sanity check of the seed)."""
        self.seed()
        t = self.traces()
        self.assertTrue(all(t[k] >= 1 for k in ('facts', 'corrections', 'episodes', 'summary', 'learned', 'turns', 'HISTORY', 'CONVO', 'ARCHIVE', 'FACTS', 'MEMVEC', 'LAST')), t)

    def test_preview_deletes_nothing_and_does_not_echo_the_words(self):
        self.seed()
        before = self.traces()
        text = self.say('/forget83 Priya')
        self.assertIn('Reply "yes forget it"', text)
        self.assertNotIn('Priya', text)
        self.assertIn('saved facts 1', text)
        self.assertIn('chat history', text)
        self.assertEqual(self.traces(), before)
        self.assertEqual(self.m._n86_get_pending(self.cid)['kind'], 'forget')

    def test_confirming_removes_it_from_every_store_and_keeps_unrelated_data(self):
        self.seed()
        self.say('forget everything about Priya')
        self.confirm()
        t = self.traces()
        self.assertEqual(sum(t.values()), 0, t)
        self.assertEqual(self.facts().get('city'), 'Surat')
        self.assertEqual(self.facts().get('friend_rahul'), 'Rahul runs a mobile shop')
        self.assertEqual([x['content'] for x in self.m.HISTORY[self.cid]], ['open my shop at ten', 'Sure.'], 'the matching messages AND their partner messages are removed')
        self.assertIn('Planning a shop visit on Saturday', self.m._n83_get_summary(self.cid)[0])
        self.assertEqual(self.m.MEMVEC[0]['t'], 'Owner runs a showroom')
        self.assertEqual(self.m.FACTS[self.cid], ['owner runs a showroom'])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM loops WHERE source='manual'")[0][0], 1, 'a follow-up the owner created is reported, not deleted')
        self.assertEqual(self.rows('SELECT COUNT(*) FROM cx83_turn')[0][0], 1)

    def test_inactive_and_superseded_facts_are_hard_deleted_too(self):
        m = self.m
        m._n35_set_fact(self.cid, 'sister', 'Priya lives in Surat', 'owner-explicit', 0.99, force=True)
        m._n35_set_fact(self.cid, 'sister', 'Priya lives in Pune', 'owner-explicit', 0.99, force=True)       # supersedes: the first row becomes inactive
        self.assertEqual(self.rows("SELECT COUNT(*) FROM facts WHERE value LIKE '%Priya%'")[0][0], 2)
        self.say('/forget83 Priya')
        self.confirm()
        self.assertEqual(self.rows("SELECT COUNT(*) FROM facts WHERE value LIKE '%Priya%'")[0][0], 0)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM corrections WHERE new_value LIKE '%Priya%' OR old_value LIKE '%Priya%'")[0][0], 0)

    def test_the_database_file_itself_no_longer_contains_the_words(self):
        self.seed(manual_loop=False)
        self.assertTrue(b'Priya' in self.db_bytes())
        self.say('/forget83 Priya')
        self.confirm()
        blob = self.db_bytes()
        self.assertFalse(b'Priya' in blob, 'deleted rows are overwritten (secure_delete) and the log is checkpointed, not just unlinked')
        self.assertFalse(b'priya' in blob.lower(), 'the tombstone keeps only salted hashes')

    def test_saved_json_copies_are_rewritten_including_the_bak(self):
        m = self.m
        data = os.path.join(self.tmp.name, 'bot_memory.json')
        self.seed()
        with mock.patch.object(m, 'DATA_FILE', data), mock.patch.object(m, 'save_data', self.real_save_data):
            self.real_save_data()
            with open(data) as fh:
                self.assertIn('Priya', fh.read())
            self.say('/forget83 Priya')
            self.confirm()
            for path in (data, data + '.bak', m.VEC_FILE):
                self.assertTrue(os.path.exists(path), path)
                with open(path) as fh:
                    self.assertNotIn('Priya', fh.read(), path)

    def test_other_chats_are_untouched(self):
        self.seed()
        self.seed(cid=999)
        self.say('/forget83 Priya')
        self.confirm()
        self.assertEqual(sum(self.traces(self.cid).values()), 0)
        other = self.traces(999)
        self.assertTrue(other['facts'] and other['episodes'] and other['summary'] and other['turns'], other)

    def test_things_saved_on_purpose_are_reported_but_never_deleted(self):
        m = self.m
        self.seed()
        m.VAULT[self.cid] = {'sister_contact': 'Priya 98250 00000'}
        m.TODOS[self.cid] = [{'text': 'buy a gift for Priya', 'done': False}]
        self.say('/forget83 Priya')
        self.assertIn('Also in things you saved on purpose', self.last())
        self.confirm()
        self.assertEqual(m.VAULT[self.cid], {'sister_contact': 'Priya 98250 00000'})
        self.assertEqual(len(m.TODOS[self.cid]), 1)
        self.assertIn('NOT deleted', self.last())
        self.assertIn('vault 1', self.last())
        self.assertIn('to-dos 1', self.last())

    def test_the_report_explains_what_cannot_be_removed(self):
        self.seed()
        self.say('/forget83 Priya')
        self.confirm()
        text = self.last()
        for needle in ('What I cannot remove', 'Backups made earlier', 'Telegram messages', 'AI providers', 'Paraphrases', 'saved on purpose'):
            self.assertIn(needle, text)
        self.assertIn('removed from', text.lower())


class TestForgettingQueuedJobs(ForgetCase):
    """The bug that made forgetting pointless: a learning job queued BEFORE the forget ran AFTER it and put the fact back."""

    def fake_clerk_learns_priya(self):
        self.fake.when(lambda r, t: clerk(t), json.dumps({'facts': [{'key': 'sister', 'value': 'Priya lives in Pune', 'category': 'relation'}]}))

    def test_queued_extract_job_is_cancelled_by_a_forget(self):
        m = self.m
        self.fake_clerk_learns_priya()
        m._N83_SYNC['on'] = False
        with mock.patch.object(m, '_n83_ensure_worker', lambda: None):
            self.assertTrue(m._n83_enqueue(('extract', self.cid, {}, 'my sister Priya lives in Pune', '')))
        self.assertEqual(m._N83_Q.qsize(), 1)
        self.seed()
        self.say('/forget83 Priya')
        self.confirm()
        job = m._N83_Q.get_nowait()
        m._n83_job_extract(*job[1:])                  # the worker runs it now, after the forget
        self.assertEqual(self.facts().get('sister'), None)
        self.assertEqual(self.traces()['facts'], 0)
        self.assertEqual([c for c in self.fake.calls if clerk(c['text'])], [], 'a cancelled job must not even spend a model call')
        self.assertGreaterEqual(m._N86_STATS['stale_jobs'], 1)

    def test_queued_compaction_job_is_cancelled_by_a_forget(self):
        m = self.m
        self.fake.when(lambda r, t: 'running summary' in t, '• Owner talked about sister Priya in Pune and many other things worth keeping')
        with m._N83_LOCK:
            m._N83_COMPACT.clear()
        m._N83_SYNC['on'] = False
        with mock.patch.object(m, '_n83_ensure_worker', lambda: None):
            m._n83_enqueue(('compact', self.cid))
        self.seed()
        self.say('/forget83 Priya')
        self.confirm()
        job = m._N83_Q.get_nowait()
        m._n83_job_compact(*job[1:])
        self.assertEqual(self.traces()['summary'], 0)
        self.assertEqual([c for c in self.fake.calls if 'running summary' in c['text']], [])

    def test_job_that_is_already_running_while_the_owner_forgets_writes_nothing(self):
        m = self.m

        def clerk_reply(role, text, messages):
            self.say('/forget83 Priya')          # the owner asks to forget WHILE the model is thinking...
            self.say('yes forget it')            # ...and confirms
            return json.dumps({'facts': [{'key': 'sister', 'value': 'Priya lives in Pune', 'category': 'relation'}]})
        self.seed()
        self.fake.when(lambda r, t: clerk(t), clerk_reply)
        receipts = m._n83_extract(self.cid, {}, 'my sister Priya now lives in Pune, near the old temple')
        self.assertEqual(receipts, [])
        self.assertEqual(self.traces()['facts'], 0)
        self.assertGreaterEqual(m._N86_STATS['stale_jobs'], 1)

    def test_compaction_running_during_a_forget_does_not_write_the_summary_back(self):
        m = self.m
        self.seed()
        m.HISTORY[self.cid] = [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': 'old message number %d about the shop' % i} for i in range(40)]

        def summary_reply(role, text, messages):
            self.say('/forget83 Priya')
            self.say('yes forget it')
            return '• Owner talked about sister Priya in Pune; shop opens at ten; dealer meeting pending'
        self.fake.when(lambda r, t: 'running summary' in t, summary_reply)
        with m._N83_LOCK:
            m._N83_COMPACT.clear()
        self.assertFalse(m._n83_compact(self.cid))
        self.assertEqual(self.traces()['summary'], 0)

    def test_summary_lines_that_mention_a_forgotten_topic_are_dropped_before_storing(self):
        m = self.m
        self.seed()
        self.say('/forget83 Priya')
        self.confirm()
        m.HISTORY[self.cid] = [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': 'old message number %d about the shop' % i} for i in range(40)]
        self.fake.when(lambda r, t: 'running summary' in t, '• Owner runs a showroom and likes early mornings\n• Dealer meeting about Priya pending')
        with m._N83_LOCK:
            m._N83_COMPACT.clear()
        self.assertTrue(m._n83_compact(self.cid))
        summary = m._n83_get_summary(self.cid)[0]
        self.assertIn('showroom', summary)
        self.assertNotIn('Priya', summary)

    def test_a_turn_in_flight_during_the_forget_leaves_no_trace(self):
        m = self.m
        self.seed()
        self.fake.when(lambda r, t: scout(t), '{"need":[]}')

        def answer(role, text, messages):
            self.say('/forget83 Priya')
            self.say('yes forget it')
            return 'Priya is your sister who lives in Pune.'
        self.fake.when(lambda r, t: True, answer)
        out = m._n83_chat_core(self.msg('Tell me about my sister Priya please'))
        self.assertIn('Priya', out['text'], 'the owner still gets the answer to the question they asked')
        self.assertEqual(self.traces(), {k: 0 for k in self.traces()}, 'but nothing about it is stored: history, episodes, turn log, receipts')
        self.assertEqual(m._N83_Q.qsize(), 0)

    def test_the_tombstone_blocks_casual_relearning_but_not_an_explicit_remember(self):
        m = self.m
        self.seed()
        self.say('/forget83 Priya')
        self.confirm()
        self.fake_clerk_learns_priya()
        self.assertEqual(m._n83_extract(self.cid, {}, 'my sister Priya moved to Surat last month'), [])
        self.assertEqual([c for c in self.fake.calls if clerk(c['text'])], [], 'blocked before any model call')
        res = m._n35_set_fact(self.cid, 'sister', 'Priya lives in Surat', 'cortex83', 0.9)
        self.assertEqual((res['ok'], res['status']), (False, 'FORGOTTEN'))
        self.assertEqual(m._n38_add(self.cid, 'call Priya tomorrow', 'owner', 0, 'deferral'), None)
        self.assertEqual(self.traces()['facts'], 0)
        # the owner deliberately teaches it again: allowed, and the block is lifted
        self.fake.rules.clear()
        self.fake.when(lambda r, t: clerk(t), json.dumps({'facts': [{'key': 'sister', 'value': 'Priya lives in Surat', 'category': 'relation'}]}))
        receipts = m._n83_extract(self.cid, {}, 'remember that my sister Priya lives in Surat')
        self.assertEqual(self.facts().get('sister'), 'Priya lives in Surat')
        self.assertEqual(m._n86_blocked(self.cid, 'Priya'), False)
        self.assertTrue(receipts)

    def test_explicit_fact_commands_lift_the_block_automatic_sources_do_not(self):
        m = self.m
        self.say('/forget83 Priya')
        self.say('yes forget it')
        self.assertTrue(m._n86_blocked(self.cid, 'Priya'))
        for source in ('owner-text', 'photo:P1', 'migrated:v28', 'cortex83'):
            self.assertEqual(m._n35_set_fact(self.cid, 'sister', 'Priya', source)['status'], 'FORGOTTEN', source)
        self.assertEqual(m._n35_set_fact(self.cid, 'sister', 'Priya', 'owner-explicit')['status'], 'NEW')
        self.assertFalse(m._n86_blocked(self.cid, 'Priya'))

    def test_legacy_background_learner_respects_the_forget(self):
        m = self.m
        self.seed()
        self.say('/forget83 Priya')
        self.confirm()

        class Inline:
            def __init__(self, target=None, daemon=None, name=None, args=(), kwargs=None):
                self.target, self.args, self.kwargs = target, args, kwargs or {}

            def start(self):
                self.target(*self.args, **self.kwargs)
        asked = []
        legacy_text = 'my sister Priya lives in Pune and I like tea'
        with mock.patch.object(m.threading, 'Thread', Inline), mock.patch.object(m, 'ask_ai', lambda *a, **k: asked.append(a) or 'sister Priya lives in Pune'):
            m.maybe_learn_fact(m.OWNER['id'], legacy_text)
            self.assertEqual(asked, [], 'a forgotten topic is not even sent to the model')
            # a different message whose answer happens to mention the forgotten topic is dropped at write time
            m.maybe_learn_fact(m.OWNER['id'], 'my favourite drink is masala tea these days')
        self.assertEqual(len(asked), 1)
        self.assertEqual(self.traces()['FACTS'], 0)
        self.assertEqual(self.traces()['MEMVEC'], 0)

    def test_web_learning_and_automatic_follow_ups_respect_the_forget(self):
        m = self.m
        self.seed()
        self.say('/forget83 Priya')
        self.confirm()
        seen = []
        with mock.patch.object(m, '_N86_LFW_PREV', lambda *a: seen.append(a)):
            m.learn_from_web(self.cid, 'Priya Pune restaurants', [{'title': 'x', 'body': 'y'}])
            m.learn_from_web(self.cid, 'best sweets in Surat', [{'title': 'x', 'body': 'y'}])
        self.assertEqual(len(seen), 1)

    def test_per_chat_background_cap_and_stale_ttl(self):
        m = self.m
        now = time.time()
        epoch = m._n86_epoch(self.cid)
        self.assertFalse(m._n86_job_dropped(self.cid, epoch, now))
        self.assertTrue(m._n86_job_dropped(self.cid, epoch, now - m._N86_JOB_TTL - 5), 'a job that waited too long is dropped')
        self.assertTrue(m._n86_job_dropped(self.cid, epoch - 1, now), 'a job from before a forget is dropped')
        m._N86_BG.clear()
        for _ in range(m._N86_BG_PER_HOUR):
            self.assertFalse(m._n86_job_dropped(self.cid, epoch, now))
        self.assertTrue(m._n86_job_dropped(self.cid, epoch, now), 'hourly cap of background model jobs per chat')
        self.assertGreaterEqual(m._N86_STATS['rate_dropped_jobs'], 1)


class TestForgetDialogue(ForgetCase):
    def test_natural_language_phrasings_all_start_a_preview(self):
        for phrase in ('forget everything about Priya', 'Please forget what I told you about Priya', 'delete Priya from your memory', 'forget Priya',
                       'forget about Priya', 'bhool jao Priya', 'Priya ko bhool jao', 'erase everything you know about Priya.'):
            self.m._N86_PENDING.clear()
            self.sent.clear()
            self.seed()
            self.say(phrase)
            self.assertIn('I found', self.last(), phrase)
            self.assertEqual(self.m._n86_get_pending(self.cid)['mode'], 'topic', phrase)

    def test_ordinary_chat_that_starts_with_forget_is_left_alone(self):
        seen = []
        with mock.patch.object(self.m, '_N86_HANDLE_PREV', lambda msg: seen.append(msg['text'])):
            for phrase in ('forget it', 'forget about it', 'forget that', 'forget the meeting tomorrow', 'forget what I just said'):
                self.m.handle(self.msg(phrase))
            self.drain_task_threads()
        self.assertEqual(len(seen), 5, 'nothing stored matches, so these go to normal conversation')
        self.assertEqual(self.sent, [])
        self.assertEqual(self.m._N86_PENDING, {})

    def test_no_keeps_everything_and_unrelated_messages_do_not_consume_the_question(self):
        self.seed()
        before = self.traces()
        self.say('/forget83 Priya')
        seen = []
        with mock.patch.object(self.m, '_N86_HANDLE_PREV', lambda msg: seen.append(msg['text'])):
            self.m.handle(self.msg('what is the weather today'))
            self.drain_task_threads()
        self.assertEqual(seen, ['what is the weather today'])
        self.assertIsNotNone(self.m._n86_get_pending(self.cid))
        self.say('no')
        self.assertIn('kept everything', self.last())
        self.assertIsNone(self.m._n86_get_pending(self.cid))
        self.assertEqual(self.traces(), before)
        self.say('yes forget it')                      # nothing pending any more: a stray "yes" does nothing
        self.assertEqual(self.traces(), before)

    def test_the_confirmation_expires_after_five_minutes(self):
        self.seed()
        before = self.traces()
        self.say('/forget83 Priya')
        real = time.time()
        seen = []
        with mock.patch.object(self.m._n86_time, 'time', lambda: real + 301), mock.patch.object(self.m, '_N86_HANDLE_PREV', lambda msg: seen.append(msg['text'])):
            self.m.handle(self.msg('yes forget it'))
            self.drain_task_threads()
        self.assertEqual(seen, ['yes forget it'])
        self.assertEqual(self.traces(), before)

    def test_forgetting_everything_needs_the_exact_extra_confirmation(self):
        m = self.m
        self.seed()
        m._n83_set_flag(self.cid, 'notify', True)
        self.say('forget everything')
        self.assertIn('EVERYTHING', self.last())
        self.say('yes')
        self.assertIn('exact words', self.last())
        self.assertEqual(self.facts().get('city'), 'Surat')
        self.say('yes erase everything')
        self.assertEqual(self.facts(), {})
        self.assertEqual(m.HISTORY.get(self.cid, []), [])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM episodes')[0][0], 0)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM cx83_turn')[0][0], 0)
        self.assertTrue(m._n83_flag(self.cid, 'notify'), 'your settings are not "memories" and are kept')
        self.assertEqual(m._n86_tombs(self.cid), [], '"everything" has no words to block; the epoch still cancels queued jobs')

    def test_forgetting_the_summary_or_the_conversation_only_touches_those(self):
        m = self.m
        self.seed()
        self.say('forget the conversation summary')
        self.assertIn('Reply "yes forget it"', self.last(), 'every destructive mode previews first')
        self.assertTrue(self.m._n83_get_summary(self.cid)[0])
        self.say('yes forget it')
        self.assertIn('SUMMARY CLEARED', self.last())
        self.assertEqual(m._n83_get_summary(self.cid)[0], '')
        self.assertEqual(m.ARCHIVE.get(self.cid), [])
        self.assertEqual(self.facts().get('sister'), 'Priya lives in Pune near the old temple')
        self.assertTrue(m.HISTORY[self.cid])
        self.seed()
        self.say('forget this conversation')
        self.say('yes forget it')
        self.assertIn('CONVERSATION FORGOTTEN', self.last())
        self.assertEqual(m.HISTORY[self.cid], [])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM episodes')[0][0], 0)
        self.assertEqual(self.facts().get('sister'), 'Priya lives in Pune near the old temple', 'facts are not part of "this conversation"')

    def test_list_shows_hashes_only_and_allow_lifts_the_block(self):
        m = self.m
        self.say('/forget83 Priya')
        self.say('yes forget it')
        self.say('/forget83 list')
        text = self.last()
        self.assertIn('BLOCKED FROM RELEARNING (1)', text)
        self.assertNotIn('Priya', text)
        self.assertTrue(m._n86_blocked(self.cid, 'Priya called'))
        self.say('/forget83 allow someone else')
        self.assertIn('not blocking that exact set', self.last())
        self.say('/forget83 allow Priya')
        self.assertIn('may learn about that again', self.last())
        self.assertFalse(m._n86_blocked(self.cid, 'Priya called'))

    def test_needle_validation(self):
        needle = self.m._n86_needle
        for bad in ('', ' ', 'it', 'the', 'a b', '!!!', 'x' * 130, 'one two three four five six seven eight nine ten'):
            with self.assertRaises(ValueError, msg=repr(bad)):
                needle(bad)
        self.assertEqual(needle('  "Priya"  ')['tokens'], ['priya'])
        self.assertEqual(needle('my sister Priya')['tokens'], ['sister', 'priya'])
        self.assertEqual(needle('प्रिया')['tokens'], ['प्रिया'])
        self.say('/forget83 it')
        self.assertIn('too generic', self.last())

    def test_matching_is_by_whole_words_not_substrings(self):
        match = self.m._n86_matcher(self.m._n86_needle('Priya'))
        self.assertTrue(match('Sister PRIYA lives in Pune'))
        self.assertTrue(match('priya.'))
        self.assertFalse(match('Priyanka lives in Pune'))
        self.assertFalse(match('nothing relevant'))
        both = self.m._n86_matcher(self.m._n86_needle('Priya Pune'))
        self.assertTrue(both('Pune is where Priya lives'))
        self.assertFalse(both('Priya lives in Surat'))

    def test_only_the_owner_in_a_private_chat_can_forget(self):
        self.seed()
        stranger = {'chat': {'id': 999, 'type': 'private'}, 'from': {'id': 999}, 'text': '/forget83 Priya'}
        group = {'chat': {'id': self.cid, 'type': 'group'}, 'from': {'id': self.cid}, 'text': '/forget83 Priya'}
        self.assertFalse(self.m._n86_dispatch(stranger))
        self.assertFalse(self.m._n86_dispatch(group))
        self.assertFalse(self.m._n86_dispatch(dict(self.msg('/forget83 Priya'), _n72_bypass=True)))
        self.assertEqual(self.sent, [])

    def test_backups_are_described_and_local_ones_can_be_deleted_on_request(self):
        m = self.m
        os.makedirs(m._N68_BACKUP_DIR)
        snaps = []
        for i in range(2):
            p = os.path.join(m._N68_BACKUP_DIR, 'B68-%d.tar.gz' % i)
            with open(p, 'wb') as fh:
                fh.write(b'x' * 2048)
            snaps.append(p)
        with open(m._N86_FULL_ZIP, 'wb') as fh:
            fh.write(b'zip' * 100)
        self.seed()
        self.say('/forget83 Priya')
        self.say('yes forget it')
        self.assertIn('Older backups still contain it: 2 local snapshot(s)', self.last())
        self.assertIn('the full-backup zip', self.last())
        self.assertTrue(all(os.path.exists(p) for p in snaps + [m._N86_FULL_ZIP]), 'forgetting never deletes backups by itself')
        self.say('also delete old backups')
        self.assertIn('3 local backup file(s)', self.last())
        self.assertTrue(os.path.exists(snaps[0]))
        self.say('yes')
        self.assertIn('Deleted 3 local backup file(s)', self.last())
        self.assertIn('Google Drive', self.last())
        self.assertFalse(any(os.path.exists(p) for p in snaps + [m._N86_FULL_ZIP]))

    def test_backup_deletion_can_be_declined_and_is_not_offered_unprompted(self):
        m = self.m
        os.makedirs(m._N68_BACKUP_DIR)
        p = os.path.join(m._N68_BACKUP_DIR, 'B68-1.tar.gz')
        with open(p, 'wb') as fh:
            fh.write(b'x')
        seen = []
        with mock.patch.object(m, '_N86_HANDLE_PREV', lambda msg: seen.append(msg['text'])):
            m.handle(self.msg('also delete old backups'))
        self.assertEqual(seen, ['also delete old backups'], 'without a preceding forget this phrase is ordinary text')
        self.seed()
        self.say('/forget83 Priya')
        self.say('yes forget it')
        self.say('delete the old backups')
        self.say('no')
        self.assertIn('kept the backups', self.last())
        self.assertTrue(os.path.exists(p))

    def test_forget_is_logged_by_counts_only(self):
        self.seed()
        self.say('/forget83 Priya')
        self.say('yes forget it')
        rows = self.rows('SELECT mode,report FROM fg86_log')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 'topic')
        self.assertNotIn('priya', rows[0][1].lower())
        self.assertGreater(json.loads(rows[0][1])['total'], 5)

    def test_a_store_that_fails_is_reported_as_not_done(self):
        m = self.m
        self.seed()
        orig = m._N86_STORES

        def boom(cid, match, apply):
            raise sqlite3.OperationalError('disk I/O error /root/secret/path')
        broken = tuple((k, l, boom if k == 'cache' else f, modes) for k, l, f, modes in orig)
        with mock.patch.object(m, '_N86_STORES', broken):
            self.say('/forget83 Priya')
            self.say('yes forget it')
        self.assertIn('Could not check: answer cache (this part is NOT done)', self.last())
        self.assertNotIn('/root/secret/path', self.last())
        self.assertEqual(self.traces()['facts'], 0, 'the other stores were still cleaned')


# ===================================================================================================================
# 3. SELF-DEVELOPMENT: hook, shortlist, interception before media routing, staged failures
# ===================================================================================================================
MINI_SOURCE = '''VERSION = "1"


def send_text(cid, text):
    pass


def _n79_feature(msg):
    """Editable extension entry: return True only when a new feature handles the message."""
    return False


def media_download_helper(url):
    """download a video from a link"""
    return url


def reminder_nightly_digest():
    """show tomorrow's reminders"""
    return []


def main():
    pass


if __name__ == '__main__':
    main()
'''
GOOD_FEATURE = ("def _n79_feature(msg):\n    text = str(msg.get('text') or '')\n    if text == '/ping86':\n"
                "        send_text(msg['chat']['id'], 'pong')\n        return True\n    return False\n")
LEAK = 'sk-' + 'LEAKLEAKLEAKLEAK123456'            # built at run time: a made-up key-shaped string that must never appear in a failure message


class DevCase(CandorCase):
    """_n79_build against a tiny synthetic source (the real 4 MB file takes ~10 s to compile) with a scripted coding model."""

    def setUp(self):
        super().setUp()
        m = self.m
        self.folder = os.path.join(self.tmp.name, 'dev')
        os.makedirs(self.folder)
        self.source = MINI_SOURCE
        self.script = []                 # one reply per coding-AI call; an Exception instance is raised
        self.code_calls = []

        def code_ai(cid, role, messages, timeout=60, _route_override=None, _probe=False):
            self.code_calls.append({'role': role, 'text': '\n'.join(str(x.get('content')) for x in messages), 'timeout': timeout})
            if role != 'code':
                return {'text': 'ok', 'provider': 'f', 'model': 'm', 'usage': {}}
            out = self.script.pop(0)
            if isinstance(out, Exception):
                raise out
            return {'text': out if isinstance(out, str) else json.dumps(out), 'provider': 'f', 'model': 'm', 'usage': {}}
        for name, val in (('_n73_request', code_ai), ('_self_read', lambda: self.source), ('_n79_folder', lambda: self.folder)):
            p = mock.patch.object(m, name, val)
            p.start()
            self.patches.append(p)

    def build(self, request='add a /ping86 command that replies pong'):    # (no download/reminder words: only the hook is offered)
        return self.m._n79_build(self.msg('x'), request)

    def good(self, **kw):
        pick = {'functions': ['_n79_feature']}
        proposal = {'summary': 'adds /ping86', 'edits': [{'name': '_n79_feature', 'code': GOOD_FEATURE}], 'manual_checks': ['send /ping86']}
        review = {'approved': True, 'concerns': []}
        return [kw.get('pick', pick), kw.get('proposal', proposal), kw.get('review', review)]


class TestShortlistAndHook(CandorCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if base.m is None:
            base.setUpModule()
        cls.src = open(base.NEMO_FILE, encoding='utf-8').read()
        cls.index = base.m._n79_index(cls.src)

    def test_the_old_window_could_not_contain_the_hook_in_the_real_file(self):
        names = '\n'.join(self.index)
        self.assertIn('_n79_feature', self.index)
        self.assertGreater(len(names), 35000, 'the old code sent only names[:35000]: the editable list is longer than that window')
        self.assertGreater(names.find('_n79_feature'), 35000, 'and the hook sits beyond it, so the model was never offered the hook for new chat features')

    def test_the_shortlist_always_starts_with_the_hook_and_is_bounded(self):
        for request in ('Upgrade your system in download videos', 'add a /stats command that shows disk usage', 'make replies shorter', 'x', ''):
            sl = self.m._n86_dev_shortlist(request, self.index)
            self.assertEqual(sl[0], '_n79_feature', request)
            self.assertLessEqual(len(sl), 121)
            self.assertLessEqual(len('\n'.join(sl)), 6000)
            self.assertEqual(len(set(sl)), len(sl), 'no duplicates')
            self.assertTrue(all(n in self.index for n in sl))

    def test_the_shortlist_is_relevant(self):
        sl = self.m._n86_dev_shortlist('Upgrade your system in download videos', self.index)
        hits = [n for n in sl if any(w in n.lower() for w in ('download', 'video', 'media', 'youtube', 'yt'))]
        self.assertGreaterEqual(len(hits), 8, sl[:30])
        sl2 = self.m._n86_dev_shortlist('show tomorrow\'s reminders every night', self.index)
        self.assertTrue(any(('remind' in n.lower() or 'sched' in n.lower()) for n in sl2), sl2[:30])
        # unrelated words give just the hook, never padding with random functions
        self.assertEqual(self.m._n86_dev_shortlist('zzzqqq', self.index), ['_n79_feature'])

    def test_ties_prefer_the_newest_definition(self):
        idx = {'_n79_feature': (None, 0, 0, ''), 'old_download': (None, 0, 0, 'x'), 'new_download': (None, 0, 0, 'x')}
        self.assertEqual(self.m._n86_dev_shortlist('download', idx)[:3], ['_n79_feature', 'new_download', 'old_download'])

    def test_a_missing_hook_is_an_explicit_failure(self):
        with mock.patch.object(self.m, '_n79_index', lambda src: {'a': (None, 0, 0, '')}):
            with self.assertRaises(self.m._N86DevError) as cm:
                self.m._n86_dev_index('whatever')
        self.assertEqual(cm.exception.step, 1)
        self.assertIn('_n79_feature', cm.exception.reason)


class TestBuildPipeline(DevCase):
    def test_success_path_offers_the_hook_and_saves_a_reviewable_candidate(self):
        self.script = self.good()
        out = self.build('make the video download helper also accept youtube links, and reply pong to /ping86')
        self.assertTrue(out['ok'], out)
        self.assertIn('DEVELOPMENT BUILD NB79-', out['text'])
        pick_prompt = self.code_calls[0]['text']
        self.assertIn('_n79_feature', pick_prompt.split('Editable function names')[1])
        self.assertIn('media_download_helper', pick_prompt, 'a relevant function is offered too')
        self.assertNotIn('def _n79_feature', pick_prompt, 'only names are sent in step 2')
        files = sorted(os.listdir(self.folder))
        self.assertEqual([os.path.splitext(f)[1] for f in files], ['.diff', '.json', '.py'])
        with open(os.path.join(self.folder, [f for f in files if f.endswith('.py')][0])) as fh:
            self.assertIn("'/ping86'", fh.read())
        self.assertEqual(self.m._N86_DEV_LAST[self.cid]['ok'], True)
        self.assertEqual(len(self.docs_sent), 1)
        self.assertEqual(self.source, MINI_SOURCE, 'the running source is never modified')

    def test_the_calls_share_one_budget_and_the_provider_timeouts_are_clamped(self):
        self.script = self.good()
        self.build()
        self.assertEqual(len(self.code_calls), 3)
        self.assertTrue(all(c['timeout'] <= 100 for c in self.code_calls))

    def test_the_lock_is_released_after_a_failure(self):
        self.script = [self.m._N73Error('http_529')]
        self.build()
        self.script = self.good()
        self.assertTrue(self.build()['ok'])

    def expect_failure(self, script, step, needle, request='add a /ping86 command that replies pong'):
        self.script = script
        out = self.build(request)
        self.assertFalse(out['ok'])
        self.assertIn('stopped at step %d of 7' % step, out['text'], out['text'])
        self.assertIn(needle, out['text'], out['text'])
        self.assertIn('running code was not changed', out['text'])
        self.assertNotIn(LEAK, out['text'])
        self.assertEqual(os.listdir(self.folder), [], 'nothing is saved when a stage fails')
        last = self.m._N86_DEV_LAST[self.cid]
        self.assertEqual((last['ok'], last['stage']), (False, step))
        return out['text']

    def test_each_stage_reports_where_it_stopped_without_exposing_anything(self):
        m = self.m
        # step 1
        self.source = ''
        self.expect_failure([], 1, 'could not read my own source')
        self.source = MINI_SOURCE.replace('def _n79_feature', 'def _n79_feature_gone')
        self.expect_failure([], 1, 'extension hook _n79_feature is missing')
        self.source = MINI_SOURCE
        # step 2: provider, format, empty, too many, unknown
        self.expect_failure([m._N73Error('http_529')], 2, 'AI provider call failed (http_529)')
        self.expect_failure([m._N73Error('weird code ' + LEAK)], 2, 'provider error')
        self.expect_failure(['this is not json ' + LEAK], 2, 'did not return the JSON structure')
        self.expect_failure([{'functions': 'nope'}], 2, 'wrong format')
        self.expect_failure([{'functions': []}], 2, 'declined to choose any function')
        self.expect_failure([{'functions': ['a', 'b', 'c', 'd', 'e']}], 2, 'more than four functions')
        self.expect_failure([{'functions': ['_n79_feature', 'does_not_exist']}], 2, '1 of the chosen function names are not editable')
        # step 3
        self.expect_failure([{'functions': ['_n79_feature']}, m._N73Error('brain_busy')], 3, 'brain_busy')
        self.expect_failure([{'functions': ['_n79_feature']}, {'summary': 's', 'edits': [{'name': 'media_download_helper', 'code': 'def media_download_helper(url):\n    return 1\n'}]}], 3, 'edits functions that were not selected')
        self.expect_failure([{'functions': ['_n79_feature']}, {'summary': 's', 'edits': 'oops'}], 3, 'not selected')
        # step 4: structural checks
        self.expect_failure([{'functions': ['_n79_feature']}, {'summary': 's', 'edits': [{'name': '_n79_feature', 'code': 'def _n79_feature(msg):\n    return (\n'}]}], 4, 'does not compile (line')
        leaking = 'def _n79_feature(msg):\n    key = "%s"\n    return False\n' % LEAK
        self.expect_failure([{'functions': ['_n79_feature']}, {'summary': 's', 'edits': [{'name': '_n79_feature', 'code': leaking}]}], 4, 'Credential-like content rejected')
        evil = 'def _n79_feature(msg):\n    eval("1")\n    return False\n'
        self.expect_failure([{'functions': ['_n79_feature']}, {'summary': 's', 'edits': [{'name': '_n79_feature', 'code': evil}]}], 4, 'protected control capability')

    def test_step_5_and_6_and_7_failures(self):
        m = self.m
        with mock.patch.object(m, '_n79_candidate', lambda src, edits: src + '# padding line\n' * 6000):
            self.expect_failure(self.good()[:2], 5, 'too large for this development build')
        denied = self.good(review={'approved': False, 'concerns': ['calls an undefined helper %s' % LEAK, 'second', 'third', 'fourth']})
        text = self.expect_failure(denied, 6, 'the AI reviewer did not approve this candidate')
        self.assertIn('second', text)
        self.assertNotIn('fourth', text, 'at most three concerns are shown')
        self.assertIn('[REDACTED]', text, 'credential-like text in reviewer remarks is redacted')
        self.script = self.good()
        with mock.patch.object(m, '_n79_write', side_effect=OSError('permission denied: /root/secret/path ' + LEAK)):
            out = self.build()
        self.assertIn('stopped at step 7 of 7', out['text'])
        self.assertIn('saving the candidate files failed (disk or permissions)', out['text'])
        self.assertNotIn('/root/secret/path', out['text'])
        self.assertNotIn(LEAK, out['text'])

    def test_running_source_changed_during_the_build(self):
        script = self.good()
        reads = {'n': 0}

        def drifting():
            reads['n'] += 1
            return MINI_SOURCE if reads['n'] == 1 else MINI_SOURCE + '# changed\n'
        with mock.patch.object(self.m, '_self_read', drifting):
            self.script = script
            out = self.build()
        self.assertIn('stopped at step 6 of 7', out['text'])
        self.assertIn('my running source changed during the build', out['text'])

    def test_unexpected_errors_name_only_the_type_and_the_stage(self):
        self.script = [{'functions': ['_n79_feature']}]
        with mock.patch.object(self.m, '_n79_candidate', side_effect=RuntimeError('boom with ' + LEAK)):
            self.script = self.good()[:2]
            out = self.build()
        self.assertIn('stopped at step 4 of 7', out['text'])
        self.assertIn('an unexpected RuntimeError error', out['text'])
        self.assertNotIn('boom', out['text'])
        self.assertNotIn(LEAK, out['text'])

    def test_a_time_budget_that_ran_out_is_named_as_such(self):
        self.script = self.good()
        with mock.patch.object(self.m, '_N86Scope', lambda total=None, label='turn': _TinyScope(self.m)):
            out = self.build()
        self.assertIn('stopped at step 2 of 7', out['text'])
        self.assertIn('time_budget_exhausted', out['text'])

    def test_why_did_the_build_fail_answers_from_the_last_record(self):
        self.say('why did the development build fail')
        self.assertIn('not tried to build anything', self.last())
        self.script = [{'functions': []}]
        self.build()
        self.say('why did the development build fail')
        self.assertIn('stopped at step 2 of 7 (choose which functions to inspect)', self.last())
        self.assertIn('Nothing was changed', self.last())


class _TinyScope:
    """A development scope whose budget is already almost gone (to prove the failure names the time limit)."""

    def __init__(self, m):
        self.m = m
        self.b = m._N86Budget(2.0, 'develop')

    def __enter__(self):
        self.m._N86_TLS.budget = self.b
        return self.b

    def __exit__(self, *exc):
        self.m._N86_TLS.budget = None
        return False


class TestUpgradeRoutingAndIntake(DevCase):
    def test_intent_table(self):
        intent = self.m._n86_dev_intent
        vague = ['Upgrade your system in download videos', 'upgrade yourself', 'Please improve yourself', 'can you upgrade your download feature?', 'improve your code',
                 'make yourself better', 'teach yourself something new', 'Nemo, upgrade your system', 'enhance your downloader', 'Upgrade your system.']
        specific = ['Upgrade yourself so that failed video downloads are retried three times', 'improve your downloader so it skips videos longer than 30 minutes when disk is low',
                    'add a feature to yourself that sends me a summary every night after the market closes']
        for t in vague:
            self.assertEqual((intent(t) or {}).get('kind'), 'vague', t)
        for t in specific:
            self.assertEqual((intent(t) or {}).get('kind'), 'specific', t)
        for t in ["don't upgrade yourself", 'how do I upgrade yourself', 'why does the bot upgrade itself', 'what if you upgrade yourself', 'download videos', 'download this video https://x.example/v',
                  'upgrade my plan', 'update the server', '/upgrade something', 'improve yourself: add a /stats command', 'build yourself: add a feature', 'I think you could improve yourself someday',
                  'tell me how to update yourself', '']:
            self.assertIsNone(intent(t), t)
        self.assertEqual(intent('Upgrade your system in download videos')['topic'], 'download videos')

    def test_protected_areas_are_flagged(self):
        intent = self.m._n86_dev_intent
        for t in ('upgrade yourself to change my api key', 'improve yourself so live trading places orders without asking', 'upgrade your code to skip the backup step',
                  'improve yourself and install packages with pip install', 'upgrade your system to remove the owner lock'):
            self.assertTrue(intent(t)['protected'], t)
        self.assertFalse(intent('upgrade your system in download videos')['protected'])

    def test_download_wording_never_reaches_media_routing(self):
        m = self.m
        started = []
        self.fake.when(lambda r, t: 'intent router' in t, '{"route":"legacy"}')       # the model router would send this to the media workflow
        self.fake.when(lambda r, t: True, 'ok')
        with mock.patch.object(m, '_n66_submit', lambda *a, **k: started.append(a[1]) or 'T1'), \
                mock.patch.object(m, '_n65_download', side_effect=AssertionError('media download must not start'), create=True), \
                mock.patch.object(m, '_n41_download', side_effect=AssertionError('media download must not start'), create=True):
            self.say('Upgrade your system in download videos')
            time.sleep(0.2)
        self.assertEqual(started, [], 'no task of any kind was started')
        self.assertEqual(self.fake.calls, [], 'not even a router call: a deterministic interception costs nothing')
        self.assertIn('What code improvement do you want in download videos?', self.last())
        self.assertIn('I have not downloaded or changed anything', self.last())
        self.assertEqual(self.m._n86_get_pending(self.cid)['kind'], 'dev_ask')

    def test_the_dialogue_ask_then_confirm_then_build(self):
        m = self.m
        queued = []
        with mock.patch.object(m, '_n66_submit', lambda cid, kind, req, fn, *a, **k: queued.append((kind, fn.__name__, a[1])) or 'T1'):
            self.say('Upgrade your system in download videos')
            self.say('when a download fails retry twice and tell me why it failed')
            self.assertIn('Here is what I would ask my coding AI to build', self.last())
            self.assertIn('download videos: when a download fails retry twice', self.last())
            self.assertIn('up to 3 AI calls', self.last())
            self.assertEqual(queued, [], 'nothing is queued before the owner says yes')
            self.say('yes')
        self.assertEqual(queued, [('DEVELOP79', '_n79_build', 'download videos: when a download fails retry twice and tell me why it failed')])
        self.assertIn('Development build queued', self.last())
        self.assertIsNone(self.m._n86_get_pending(self.cid))

    def test_the_dialogue_can_be_cancelled_at_either_step(self):
        queued = []
        with mock.patch.object(self.m, '_n66_submit', lambda *a, **k: queued.append(1) or 'T1'):
            self.say('Upgrade your system in download videos')
            self.say('cancel')
            self.assertIn('I changed nothing', self.last())
            self.say('upgrade yourself')
            self.say('add a nightly summary of unpaid bills')
            self.say('no')
            self.assertIn('I changed nothing', self.last())
        self.assertEqual(queued, [])

    def test_a_question_or_command_reply_leaves_the_dialogue_and_is_handled_normally(self):
        seen = []
        self.say('Upgrade your system in download videos')
        with mock.patch.object(self.m, '_N86_HANDLE_PREV', lambda msg: seen.append(msg['text'])):
            self.m.handle(self.msg('what is the weather today?'))
            self.m.handle(self.msg('/status'))
            self.drain_task_threads()
        self.assertEqual(seen, ['what is the weather today?', '/status'])
        self.assertIsNone(self.m._n86_get_pending(self.cid))

    def test_very_short_or_protected_replies_do_not_start_a_build(self):
        queued = []
        with mock.patch.object(self.m, '_n66_submit', lambda *a, **k: queued.append(1) or 'T1'):
            self.say('Upgrade your system in download videos')
            self.say('better')
            self.assertIn('one concrete change', self.last())
            self.say('change my api key and place live orders automatically')
            self.assertIn('protected', self.last())
            self.say('yes')
        self.assertEqual(queued, [])

    def test_a_specific_request_goes_to_confirmation_not_straight_to_a_build(self):
        queued = []
        with mock.patch.object(self.m, '_n66_submit', lambda *a, **k: queued.append(1) or 'T1'):
            self.say('Upgrade yourself so that failed video downloads are retried three times')
            self.assertIn('Here is what I would ask my coding AI to build', self.last())
        self.assertEqual(queued, [])

    def test_protected_requests_are_refused_with_an_alternative(self):
        self.say('upgrade yourself to change my api key')
        self.assertIn('protected', self.last())
        self.assertIsNone(self.m._n86_get_pending(self.cid))

    def test_the_dialogue_expires(self):
        self.say('Upgrade your system in download videos')
        real = time.time()
        seen = []
        with mock.patch.object(self.m._n86_time, 'time', lambda: real + 601), mock.patch.object(self.m, '_N86_HANDLE_PREV', lambda msg: seen.append(msg['text'])):
            self.m.handle(self.msg('retry failed downloads twice'))
            self.drain_task_threads()
        self.assertEqual(seen, ['retry failed downloads twice'])

    def test_the_explicit_colon_command_keeps_its_own_direct_path(self):
        m = self.m
        started = []
        with mock.patch.object(m, '_n66_submit', lambda cid, kind, req, fn, *a, **k: started.append(kind) or 'T1'):
            self.say('improve yourself: add a /stats command that shows disk usage')
        self.assertEqual(started, ['DEVELOP79'], 'unchanged: the existing explicit command queues the build directly')

    def test_the_router_is_a_second_line_of_defence(self):
        m = self.m
        with mock.patch.object(m, '_N86_DECIDE_PREV', side_effect=AssertionError('router model must not be asked')):
            decision = m._n72_decide(self.cid, 'Upgrade your system in download videos', '')
        self.assertEqual(decision['route'], 'clarify')
        self.assertIn('What code improvement', decision['question'])
        self.assertLessEqual(len(decision['question']), 400)
        m._n72_validate(decision)                                    # the router's own schema accepts it
        with mock.patch.object(m, '_N86_DECIDE_PREV', lambda cid, text, ctx: {'route': 'chat80'}):
            self.assertEqual(m._n72_decide(self.cid, 'tell me a joke', '')['route'], 'chat80')

    def test_only_the_owner_in_private_chat(self):
        m = self.m
        stranger = {'chat': {'id': 999, 'type': 'private'}, 'from': {'id': 999}, 'text': 'Upgrade your system in download videos'}
        self.assertFalse(m._n86_dispatch(stranger))
        self.assertEqual(self.sent, [])
        self.assertFalse(m._n86_dispatch(dict(self.msg('Upgrade your system in download videos'), _n72_bypass=True)))
