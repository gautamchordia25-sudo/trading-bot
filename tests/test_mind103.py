"""Nemo v103 "Mind": the memory reads Hindi and Gujarati script and Hinglish, keeps the owner's own words as evidence for every fact, marks facts nobody has confirmed for a long time, answers "why do you
think ...", "history of my ...", "what did you know about me on 5 March", asks which person is meant instead of guessing, and closes the Twilio WhatsApp/voice lines to every number the owner has not allowed.

Offline. No Telegram, no cloud AI, no paid service, no broker, no order. The AI calls in these tests are scripted; the website is the real Flask app driven through its test client.

    NEMO_FILE=/path/to/nemotron_bot.py python -m unittest tests.test_mind103 -v
"""
import json
import os
import re
import sqlite3
import time
import unittest
from unittest import mock

from tests import test_cortex83 as base
from tests.test_cortex83 import CortexCase, OWNER_ID, clerk

try:
    import flask  # noqa: F401
    HAVE_FLASK = True
except Exception:                                   # pragma: no cover
    HAVE_FLASK = False
needs_flask = unittest.skipUnless(HAVE_FLASK, 'Flask is not installed')

DAY = 86400.0


def setUpModule():
    if base.m is None:
        base.setUpModule()


def mind_source():
    src = open(base.NEMO_FILE, encoding='utf-8').read()
    i = src.index('# NEMO 103 - MIND')
    j = src.index('# NEMO 104 - ') if '# NEMO 104 - ' in src else src.rindex("if __name__")
    return src[i:j]


class MindCase(CortexCase):
    def setUp(self):
        super().setUp()
        m = self.m = base.m
        m._N103_SCHEMA['path'] = None
        m._N103_SYNC['on'] = True
        self.kbs = []
        self.passed = []

        def send(cid, text, kb=None):
            self.sent.append((cid, text))
            self.kbs.append((cid, kb))
        for name, val in (('send_text', send), ('_N103_HANDLE_PREV', lambda msg: self.passed.append(msg))):
            p = mock.patch.object(m, name, val)
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(lambda: m._N103_SYNC.__setitem__('on', False))
        for k in m._N103_STATS:
            m._N103_STATS[k] = 0
        m._n35_init()
        m._n103_conn().close()

    # ---- helpers
    def said(self):
        return '\n'.join(t for (_c, t) in self.sent)

    def owner_msg(self, text, **extra):
        d = {'chat': {'id': OWNER_ID, 'type': 'private'}, 'from': {'id': OWNER_ID}, 'text': text, 'message_id': 7, 'date': 1}
        d.update(extra)
        return d

    def put(self, key, value, cat='fact', created=None, updated=None, active=1, sup='', fid=None, evidence='', confirmed=0, via='you told me', source='owner-text'):
        """Insert a fact row directly (so tests control the dates)."""
        now = time.time()
        created = now if created is None else created
        updated = created if updated is None else updated
        fid = fid or 'F35-' + os.urandom(5).hex().upper()
        c = self.m._n103_conn()
        c.execute('INSERT INTO facts(id,chat_id,fkey,value,norm,category,source,confidence,active,seen_count,created,updated,superseded_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  (fid, str(self.cid), key, value, self.m._n35_norm(value), cat, source, .95, active, 1, created, updated, sup))
        if evidence or confirmed:
            c.execute('INSERT OR REPLACE INTO mind103_meta(fact_id,chat_id,evidence,lang,via,created,confirmed) VALUES(?,?,?,?,?,?,?)', (fid, str(self.cid), evidence, '', via, created, confirmed))
        c.commit()
        c.close()
        return fid

    def meta(self, fid):
        c = self.m._n103_conn()
        try:
            return c.execute('SELECT evidence,lang,via,created,confirmed FROM mind103_meta WHERE fact_id=?', (fid,)).fetchone()
        finally:
            c.close()

    def fid_of(self, key):
        r = self.m._n103_q('SELECT id FROM facts WHERE chat_id=? AND fkey=? AND active=1', (str(self.cid), key))
        return r[0][0] if r else None

    def propose(self, facts):
        self.fake.rules = [(p, r) for p, r in self.fake.rules if getattr(p, '_not_clerk', False)]
        self.fake.when(lambda r, t: clerk(t), json.dumps({'facts': facts}))


# ===================================================================================================================
# 1. THE LANGUAGE ENGINE (pure functions)
# ===================================================================================================================
class TestFolding(MindCase):
    def test_nukta_chandrabindu_zero_width_digits_danda(self):
        f = self.m._n103_fold
        self.assertEqual(f('क़ीमत'), f('कीमत'))                       # composed nukta letter == the plain letter
        self.assertEqual(f('चाँद'), f('चांद'))                          # chandrabindu -> anusvara
        self.assertEqual(f('ગુજ‍રાત'), f('ગુજરાત'))                # zero-width joiner
        self.assertEqual(f('१२३ ૪૫૬'), '123 456')
        self.assertEqual(f('हाँ।'), 'हां.')
        self.assertEqual(f('HeLLo'), 'hello')

    def test_scripts_and_native_detection(self):
        m = self.m
        self.assertTrue(m._n103_has_native('મારું ઘર'))
        self.assertTrue(m._n103_has_native('mera ghar घर'))
        self.assertFalse(m._n103_has_native('mera ghar'))
        s = m._n103_scripts('abc मेरा ભાઈ')
        self.assertEqual((s['latin'], s['deva'] > 0, s['guj'] > 0), (3, True, True))


class TestTransliteration(MindCase):
    CASES = [('गौतम', 'gautam'), ('ગૌતમ', 'gautam'), ('कमला', 'kamla'), ('भैया', 'bhaiya'), ('पत्नी', 'patni'), ('પત્ની', 'patni'), ('नाम', 'nam'), ('નામ', 'nam'),
             ('सूरत', 'surat'), ('સુરત', 'surat'), ('राहुल', 'rahul'), ('પ્રિયા', 'priya'), ('प्रिया', 'priya'), ('समझना', 'samajhna'), ('१२३', '123')]

    def test_known_words(self):
        for w, want in self.CASES:
            self.assertEqual(self.m._n103_translit(w), want, w)

    def test_gujarati_and_hindi_agree_on_the_same_word(self):
        t = self.m._n103_translit
        for hi, gu in (('गौतम', 'ગૌતમ'), ('सूरत', 'સુરત'), ('राहुल', 'રાહુલ'), ('भाई', 'ભાઈ'), ('पत्नी', 'પત્ની'), ('नाम', 'નામ')):
            self.assertEqual(t(hi), t(gu), hi)

    def test_latin_passes_through_and_spelling_variants_share_a_sound_key(self):
        m = self.m
        self.assertEqual(m._n103_translit('Hello'), 'hello')
        for a, b in (('bhaiya', 'bhaiyya'), ('Gautam', 'Gautham'), ('chai', 'chaay'), ('rahul', 'राहुल')):
            self.assertEqual(m._n103_soft(m._n103_translit(a)), m._n103_soft(m._n103_translit(b)), (a, b))
        self.assertEqual(m._n103_skel('kamla'), m._n103_skel('kamala'))                     # different vowels: the consonant skeleton still agrees
        self.assertEqual(m._n103_skel('amdavad'), m._n103_skel('ahmedabad'))               # v and b are folded
        self.assertEqual(m._n103_skel('ahmedabad'), m._n103_skel(m._n103_translit('अहमदाबाद')))
        self.assertNotEqual(m._n103_soft('rahul'), m._n103_soft('rohan'))


class TestLexiconAndTokens(MindCase):
    def test_one_concept_in_four_languages(self):
        r = self.m._n103_rel_of
        self.assertEqual({r('brother'), r('bhai'), r('भाई'), r('ભાઈ'), r('ભાઈનું')}, {'brother'})
        self.assertEqual({r('wife'), r('patni'), r('बीवी'), r('પત્ની'), r('પત્નીનું')}, {'wife'})
        self.assertEqual({r('mother'), r('mummy'), r('माँ'), r('मां'), r('મમ્મી'), r('maa')}, {'mother'})
        self.assertEqual(r('dukan'), '')                       # a shop is not a person

    def test_gujarati_postposition_is_stripped(self):
        m = self.m
        self.assertEqual(m._n103_strip_native('ભાઈનું'), 'ભાઈ')
        self.assertEqual(m._n103_strip_native('નામ'), 'નામ')       # nothing to strip: never shorter than 2 letters

    def test_called_is_not_tomorrow_and_rate_is_not_live(self):
        m = self.m
        self.assertNotIn('tomorrow', m._n103_token_info('called')[2])
        self.assertNotIn('live', m._n103_token_info('rate')[2])
        self.assertEqual(m._n103_token_info('kal')[2], frozenset({'tomorrow', 'yesterday'}))    # Hindi uses one word for both

    def test_stop_words_are_per_script(self):
        m = self.m
        self.assertTrue(m._n103_token_info('क्या')[0])
        self.assertTrue(m._n103_token_info('શું')[0])
        self.assertTrue(m._n103_token_info('kaun')[0])
        self.assertFalse(m._n103_token_info('माँ')[0])           # Hindi "mother" must not be eaten by the Gujarati postposition માં (both read "man" in Latin)
        self.assertFalse(m._n103_token_info('maa')[0])
        self.assertFalse(m._n103_token_info('ભાઈ')[0])

    def test_terms_use_concepts_for_known_words_and_sound_for_the_rest(self):
        w, s, sound = self.m._n103_terms('મારા ભાઈનું નામ રાહુલ છે')
        self.assertIn('c:brother', w)
        self.assertIn('c:name', w)
        self.assertIn('w:ral', w)
        self.assertIn('s:rl', s)
        self.assertEqual(sound, 'ral')
        self.assertEqual(self.m._n103_terms('what is the')[0], [])

    def test_language_detection(self):
        L = self.m._n103_lang
        self.assertEqual(L('મારા ભાઈનું નામ શું છે'), 'gu')
        self.assertEqual(L('मेरे भाई का नाम क्या है'), 'hi')
        self.assertEqual(L('mera bhai kaun hai aur kahan rehta hai'), 'hinglish')
        self.assertEqual(L('maru naam shu chhe'), 'gu-latin')
        self.assertEqual(L('what is my brother called'), 'en')
        self.assertEqual(L(''), 'en')
        self.assertEqual(L('ok'), 'en')


class TestSearch(MindCase):
    def rows(self):
        return self.m._n103_eval_rows()

    def top(self, q, k=3):
        rows = self.rows()
        return [rows[h['i']][0:2] for h in self.m._n103_search(rows, q, k=k)]

    def test_the_same_fact_is_found_in_every_language(self):
        for q in ('who is my brother', 'mera bhai kaun hai', 'मेरे भाई का नाम क्या है', 'મારા ભાઈનું નામ શું છે', 'bhaiya ka naam batao'):
            self.assertEqual(self.top(q)[0], ('brother', 'Rahul'), q)

    def test_native_script_names_match_latin_names(self):
        self.assertEqual(self.top('अमित कहाँ रहता है')[0][0], 'friend_amit')
        self.assertEqual(self.top('amit kahan rehta hai')[0][0], 'friend_amit')
        self.assertEqual(self.top('who is Rohan')[0][0], 'friend_rohan')
        self.assertEqual(self.top('Amdavad')[:1] and self.top('Amdavad')[0][0], 'city')          # a different spelling of Ahmedabad: the sound channel finds it

    def test_unrelated_questions_find_nothing(self):
        for q in ('tell me a joke', 'what is the capital of France', 'ek chutkula suna do', 'भारत की राजधानी क्या है', 'ગુજરાતની રાજધાની શું છે', 'write a poem about the sea', 'bitcoin ka rate kya hai',
                  'what is 15 percent of 2400', ''):
            self.assertEqual(self.top(q), [], q)

    def test_relative_cut_drops_weak_neighbours(self):
        got = self.m._n103_search(self.rows(), 'what tea do I like', k=8)
        self.assertEqual(self.rows()[got[0]['i']][1], 'likes strong tea without sugar')
        self.assertTrue(all(h['score'] >= got[0]['score'] * self.m._N103_RELATIVE_CUT for h in got))

    def test_search_is_fast_enough_for_every_turn(self):
        now = time.time()
        words = 'ahmedabad rahul priya showroom tea sugar trip goa options trading walks morning meeting bank loan emi dog bruno'.split()
        rows = [('fact_%d' % i, ' '.join(words[(i + j) % len(words)] for j in range(8)), 'fact', 'x', .9, 1, now - i, '') for i in range(240)]
        t = time.time()
        for q in ('where does rahul live', 'मेरे भाई का नाम', 'tea sugar trip'):
            self.m._n103_search(rows, q, k=8)
        self.assertLess((time.time() - t) / 3, 0.25)

    def test_ranking_counts_each_fact_once_and_orders_by_score(self):
        got = self.m._n103_search(self.rows(), 'meri behen aur bhai', k=8)
        idx = [h['i'] for h in got]
        self.assertEqual(len(idx), len(set(idx)))
        self.assertEqual([h['score'] for h in got], sorted((h['score'] for h in got), reverse=True))


class TestBuiltInEval(MindCase):
    def test_dev_half_floor(self):
        r = self.m._n103_eval_run(('dev',))['dev']
        top1 = sum(r[s]['hyb1'] for s in ('en', 'hinglish', 'hi', 'gu'))
        top3 = sum(r[s]['hyb3'] for s in ('en', 'hinglish', 'hi', 'gu'))
        self.assertGreaterEqual(top1, 30)
        self.assertGreaterEqual(top3, 31)
        self.assertLessEqual(r['neg']['hyb_false'], 2)

    def test_hold_out_half_floor(self):
        r = self.m._n103_eval_run(('hold',))['hold']
        top1 = sum(r[s]['hyb1'] for s in ('en', 'hinglish', 'hi', 'gu'))
        top3 = sum(r[s]['hyb3'] for s in ('en', 'hinglish', 'hi', 'gu'))
        self.assertGreaterEqual(top1, 26)
        self.assertGreaterEqual(top3, 28)
        self.assertLessEqual(r['neg']['hyb_false'], 2)

    def test_new_recall_beats_old_recall_in_every_language_row_on_both_halves(self):
        r = self.m._n103_eval_run()
        for sp in ('dev', 'hold'):
            for s in ('en', 'hinglish', 'hi', 'gu'):
                self.assertGreaterEqual(r[sp][s]['hyb1'], r[sp][s]['base1'], (sp, s))

    def test_questions_are_all_answerable_and_split_evenly(self):
        m = self.m
        n = len(m._N103_EVAL_FACTS)
        for sp, st, q, gold in m._N103_EVAL_Q:
            self.assertTrue(0 <= gold < n, q)
        for sp in ('dev', 'hold'):
            for st in ('en', 'hinglish', 'hi', 'gu'):
                self.assertEqual(sum(1 for a, b, c, d in m._N103_EVAL_Q if a == sp and b == st), 8, (sp, st))

    def test_the_old_rule_copy_matches_the_real_old_function(self):
        """The comparison is only fair if _n103_baseline is the v83 rule, so check it against the real previous function on every eval question."""
        m = self.m
        rows = m._n103_eval_rows()
        with mock.patch.object(m, '_n35_facts', lambda cid, limit=240: [r[:7] for r in rows]):
            for sp, st, q, gold in m._N103_EVAL_Q:
                real = [k for k in m._N103_MB_PREV(self.cid, q, 10, 100000, True)[1]]
                mine = [rows[i][0] for i in m._n103_baseline(rows, q)[:10]]
                self.assertEqual(real, mine, q)

    def test_the_report_states_its_limits(self):
        t = self.m._n103_eval_text()
        for needle in ('synthetic', 'same author', 'native', '8 questions', 'DEV half', 'HOLD-OUT half', 'old', 'new'):
            self.assertIn(needle, t)
        self.route('memory eval')
        self.assertIn('Memory eval', self.said())

    def route(self, text):
        return self.m._n103_route(self.cid, text)


# ===================================================================================================================
# 2. STORAGE AND THE NATIVE-SCRIPT FIXES
# ===================================================================================================================
class TestNativeStorage(MindCase):
    def test_comparison_text_of_script_is_not_empty_and_ascii_is_unchanged(self):
        n = self.m._n35_norm
        self.assertEqual(n('Hello World'), 'hello world')
        self.assertEqual(n('ગૌતમ'), 'gautam')
        self.assertNotEqual(n('ગૌતમ'), n('રાહુલ'))
        self.assertEqual(n('Priya પ્રિયા'), 'priya priya')
        self.assertEqual(n(''), '')

    def test_two_different_script_values_are_both_kept_and_a_repeat_is_not(self):
        m = self.m
        a = m._n35_set_fact(self.cid, 'preference', 'મને ચા ગમે છે')
        b = m._n35_set_fact(self.cid, 'preference', 'મને કોફી પસંદ નથી')
        c = m._n35_set_fact(self.cid, 'preference', 'મને ચા ગમે છે')
        self.assertEqual((a['status'], b['status'], c['status']), ('NEW', 'NEW', 'SAME'))      # before v103 the second one was dropped as a "duplicate" of the first (both compared as '')
        self.assertEqual(len([r for r in m._n35_facts(self.cid, 50) if r[0] == 'preference']), 2)

    def test_a_single_valued_script_fact_is_replaced_not_ignored(self):
        m = self.m
        m._n35_set_fact(self.cid, 'city', 'સુરત')
        r = m._n35_set_fact(self.cid, 'city', 'અમદાવાદ', 'owner-correction', force=True)
        self.assertEqual(r['status'], 'UPDATED')
        self.assertEqual(self.facts()['city'], 'અમદાવાદ')

    def test_old_rows_with_an_empty_comparison_text_are_repaired_once(self):
        m = self.m
        fid = self.put('remembered', 'ગૌતમ')
        c = m._n103_conn()
        c.execute("UPDATE facts SET norm='' WHERE id=?", (fid,))
        c.commit()
        c.close()
        m._N103_SCHEMA['path'] = None
        m._n103_conn().close()
        row = m._n103_q('SELECT norm FROM facts WHERE id=?', (fid,))[0][0]
        self.assertEqual(row, 'gautam')
        self.assertGreaterEqual(m._N103_STATS['migrated'], 1)

    def test_worth_extracting_for_script(self):
        w = self.m._n83_worth_extracting
        self.assertTrue(w({}, 'मेरी बहन पुणे में रहती है'))
        self.assertTrue(w({}, 'મારી બહેન પુણેમાં રહે છે'))
        self.assertTrue(w({}, 'I live in Pune with my family'))                  # English is unchanged
        self.assertFalse(w({}, 'मेरी बहन कहाँ रहती है'))                          # a question
        self.assertFalse(w({}, 'મારી બહેન ક્યાં રહે છે'))
        self.assertFalse(w({}, 'दिल्ली भारत की राजधानी है'))                      # no first person
        self.assertFalse(w({'forward_origin': {'x': 1}}, 'मेरी बहन पुणे में रहती है'))
        self.assertFalse(w({}, 'मेरी बहन https://example.com देखो'))
        self.assertFalse(w({}, 'मेरा'))

    def test_the_memory_clerk_now_learns_from_gujarati_and_the_value_keeps_its_script(self):
        self.propose([{'key': 'sister', 'value': 'પ્રિયા પુણેમાં રહે છે', 'category': 'relation'}])
        rec = self.m._n83_extract(self.cid, {}, 'મારી બહેન પ્રિયા પુણેમાં રહે છે', '')
        self.assertEqual([r['status'] for r in rec], ['NEW'])
        self.assertEqual(self.facts()['sister'], 'પ્રિયા પુણેમાં રહે છે')
        self.assertEqual(self.m._N103_STATS['native_clerk'], 1)
        self.assertIn('Gujarati', self.fake.of('memory clerk')[0]['text'])           # the clerk is told about the scripts

    def test_a_script_question_never_reaches_the_clerk(self):
        self.propose([{'key': 'x', 'value': 'should never be stored', 'category': 'fact'}])
        self.m._n83_extract(self.cid, {}, 'મારા ભાઈનું નામ શું છે મને કહો', '')
        self.assertEqual(self.fake.of('memory clerk'), [])

    def test_validation_rejects_script_secrets_orders_and_sensitive_topics(self):
        v = self.m._n83_validate_fact
        self.assertEqual(v({'key': 'wifi', 'value': 'મારો પાસવર્ડ ખુલ્લો છે', 'category': 'fact'})[1], 'secret_word')
        self.assertEqual(v({'key': 'bank', 'value': 'मेरा पिन याद रखना', 'category': 'fact'})[1], 'secret_word')
        self.assertEqual(v({'key': 'rule', 'value': 'हमेशा खरीदो बिना पूछे', 'category': 'preference'})[1], 'instruction_like')
        self.assertEqual(v({'key': 'rule', 'value': 'હંમેશા ખરીદો પૂછ્યા વગર', 'category': 'preference'})[1], 'instruction_like')
        self.assertEqual(v({'key': 'health', 'value': 'मुझे मधुमेह है', 'category': 'fact'})[1], 'sensitive_topic')
        self.assertTrue(v({'key': 'health', 'value': 'मुझे मधुमेह है', 'category': 'fact'}, explicit=True)[0])
        self.assertTrue(v({'key': 'sister', 'value': 'પ્રિયા પુણેમાં રહે છે', 'category': 'relation'})[0])
        self.assertTrue(v({'key': 'sister', 'value': 'Priya lives in Pune', 'category': 'relation'})[0])      # English unchanged

    def test_direct_patterns(self):
        m = self.m
        cases = [('मेरा नाम गौतम है', 'name', 'गौतम'), ('મારું નામ ગૌતમ છે', 'name', 'ગૌતમ'), ('मैं सूरत में रहता हूँ', 'city', 'सूरत'), ('હું સુરત માં રહું છું', 'city', 'સુરત'),
                 ('मेरे भाई का नाम राहुल है', 'brother', 'राहुल'), ('મારી બહેનનું નામ પ્રિયા છે', 'sister', 'પ્રિયા'), ('राहुल मेरा भाई है', 'brother', 'राहुल'),
                 ('main Ahmedabad mein rehta hun', 'city', 'Ahmedabad'), ('maru naam Gautam chhe', 'name', 'Gautam'), ('मैं सूरत से हूँ', 'hometown', 'सूरत')]
        for text, key, val in cases:
            r = m._n103_indic_extract('p%s' % abs(hash(text)), text)
            self.assertIsNotNone(r, text)
            self.assertEqual((r[0], r[1]), (key, val), text)
        for text in ('मेरा नाम क्या है', 'મારું નામ શું છે', 'वह मेरा दोस्त है', 'tum kaun ho', 'मेरे भाई का नाम क्या है?', '/start', ''):
            self.assertIsNone(m._n103_indic_extract('q', text), text)

    def test_the_v35_extractor_now_falls_through_to_the_script_patterns(self):
        r = self.m._n35_extract(self.cid, 'મારી બહેનનું નામ પ્રિયા છે', 'owner-text')
        self.assertEqual((r[0], r[1], r[2]['status']), ('sister', 'પ્રિયા', 'NEW'))
        self.assertEqual(self.m._N103_STATS['native_patterns'], 1)
        self.assertIsNone(self.m._n35_extract(self.cid, 'મારી બહેનનું નામ શું છે', 'owner-text'))
        self.assertEqual(self.m._n35_extract(self.cid, 'my name is Gautam', 'owner-text')[0], 'name')      # English path unchanged


class TestEvidence(MindCase):
    def test_a_stated_fact_keeps_the_sentence_how_and_when(self):
        self.m._n35_extract(self.cid, 'my name is Gautam', 'owner-text')
        ev, lang, via, created, confirmed = self.meta(self.fid_of('name'))
        self.assertEqual((ev, via, lang), ('my name is Gautam', 'you told me', 'en'))
        self.assertAlmostEqual(created, time.time(), delta=10)

    def test_a_clerk_fact_keeps_the_owner_message_not_the_models_words(self):
        self.propose([{'key': 'sister', 'value': 'Priya lives in Pune', 'category': 'relation'}])
        self.m._n83_extract(self.cid, {}, 'my sister Priya lives in Pune now', '')
        ev, lang, via, *_ = self.meta(self.fid_of('sister'))
        self.assertEqual(ev, 'my sister Priya lives in Pune now')
        self.assertEqual(via, 'picked up from your message')

    def test_script_evidence_and_language(self):
        self.m._n35_extract(self.cid, 'મારી બહેનનું નામ પ્રિયા છે', 'owner-text')
        ev, lang, *_ = self.meta(self.fid_of('sister'))
        self.assertEqual((ev, lang), ('મારી બહેનનું નામ પ્રિયા છે', 'gu'))

    def test_hearing_it_again_counts_as_a_confirmation_and_keeps_the_first_words(self):
        self.m._n35_extract(self.cid, 'my name is Gautam', 'owner-text')
        fid = self.fid_of('name')
        self.m._n103_q('UPDATE facts SET updated=updated-100 WHERE id=?', (fid,), write=True)
        self.m._n35_extract(self.cid, 'No, my name is Gautam', 'owner-text')            # same value again
        ev, lang, via, created, confirmed = self.meta(fid)
        self.assertEqual(ev, 'my name is Gautam')
        self.assertGreater(confirmed, created - 1)

    def test_a_correction_gets_its_own_evidence_and_the_old_version_stays_for_history(self):
        self.m._n35_extract(self.cid, 'I live in Surat', 'owner-text')
        old = self.fid_of('city')
        self.m._n35_extract(self.cid, 'Actually I live in Ahmedabad', 'owner-text')
        new = self.fid_of('city')
        self.assertNotEqual(old, new)
        self.assertEqual(self.meta(new)[0], 'Actually I live in Ahmedabad')
        self.assertEqual(self.meta(old)[0], 'I live in Surat')

    def test_evidence_is_cut_masked_and_absent_without_a_sentence(self):
        long = 'my favourite food is ' + 'very ' * 80 + 'spicy'
        self.m._n35_extract(self.cid, 'remember that ' + long, 'owner-text')
        ev = self.meta(self.fid_of('remembered'))[0]
        self.assertLessEqual(len(ev), 240)
        self.m._n35_set_fact(self.cid, 'wife', 'Heta')                                   # no message in scope
        self.assertEqual(self.meta(self.fid_of('wife'))[0], '')

    def test_context_does_not_leak_between_calls(self):
        self.m._n35_extract(self.cid, 'my name is Gautam', 'owner-text')
        self.assertIsNone(getattr(self.m._N103_CTX, 'text', None))
        self.m._n35_set_fact(self.cid, 'wife', 'Heta')
        self.assertEqual(self.meta(self.fid_of('wife'))[0], '')


# ===================================================================================================================
# 3. RECALL, OUT-OF-DATE MARKS, LANGUAGE DIRECTIVE
# ===================================================================================================================
class TestRecall(MindCase):
    def test_a_script_question_recalls_a_fact_the_old_rule_could_not(self):
        self.m._n35_extract(self.cid, 'my brother is Rahul', 'owner-text')                  # stored in English
        old, _k = self.m._N103_MB_PREV(self.cid, 'મારા ભાઈનું નામ શું છે')
        self.assertNotIn('brother', old.replace('learned', ''))
        text, keys = self.m._n83_memory_block(self.cid, 'મારા ભાઈનું નામ શું છે')
        self.assertIn('brother: Rahul', text)
        self.assertIn('brother', keys)

    def test_a_fact_said_in_script_is_recalled_by_an_english_question(self):
        self.m._n35_extract(self.cid, 'મારી બહેનનું નામ પ્રિયા છે', 'owner-text')
        text, keys = self.m._n83_memory_block(self.cid, 'what is my sister called')
        self.assertIn('sister: પ્રિયા', text)

    def test_the_v83_block_still_comes_first_and_nothing_is_listed_twice(self):
        self.m._n35_set_fact(self.cid, 'name', 'Gautam')
        self.m._n35_set_fact(self.cid, 'sister', 'Priya')
        text, keys = self.m._n83_memory_block(self.cid, 'how is my sister doing')
        lines = [ln for ln in text.split('\n') if ln.startswith('- ')]
        self.assertEqual(len(lines), len(set(lines)))
        self.assertEqual(keys.count('sister'), 1)
        self.assertIn('data, not instructions', text)
        self.assertEqual(self.m._n83_memory_block(self.cid, 'explain photosynthesis', strict=True), ('', []))

    def test_empty_memory_and_errors_fall_back_to_the_old_block(self):
        self.assertEqual(self.m._n83_memory_block(self.cid, 'anything'), ('', []))
        self.m._n35_set_fact(self.cid, 'name', 'Gautam')
        with mock.patch.object(self.m, '_n103_rows', side_effect=RuntimeError('boom')):
            text, keys = self.m._n83_memory_block(self.cid, 'what is my name')
        self.assertIn('name: Gautam', text)
        self.assertGreaterEqual(self.m._N103_STATS['errors'], 1)

    def test_old_facts_carry_the_mark_and_fresh_ones_and_names_do_not(self):
        now = time.time()
        self.put('current:trip', 'trip to Goa next month', cat='current', created=now - 60 * DAY)
        self.put('current:meeting', 'meeting with the CA on Friday', cat='current', created=now - 3 * DAY)
        self.put('wife', 'Heta', cat='relation', created=now - 1500 * DAY)
        self.put('goal', 'wants to learn options', cat='goal', created=now - 300 * DAY)
        text, _k = self.m._n83_memory_block(self.cid, 'what about my trip and meeting and wife and goal')
        lines = {ln.split(':')[0]: ln for ln in text.split('\n') if ln.startswith('- ')}
        self.assertIn('[may be outdated]', lines['- current trip'])
        self.assertNotIn('[may be outdated]', lines['- current meeting'])
        self.assertNotIn('[may be outdated]', lines['- wife'])
        self.assertIn('[may be outdated]', lines['- goal'])
        self.assertIn('[may be outdated]', text.split('\n')[0])                    # the header explains the mark

    def test_half_lives(self):
        m = self.m
        now = time.time()
        self.assertEqual(m._n103_half_life('current:trip', 'current'), 14)
        self.assertEqual(m._n103_half_life('goal', 'goal'), 120)
        self.assertEqual(m._n103_half_life('preference', 'preference'), 365)
        self.assertIsNone(m._n103_half_life('name', 'identity'))
        self.assertIsNone(m._n103_half_life('wife', 'relation'))
        self.assertIsNone(m._n103_half_life('friend_rahul', 'relation'))
        self.assertEqual(m._n103_half_life('city', 'relation'), 720)               # v35 files city under relations; it can change
        self.assertFalse(m._n103_stale('name', 'identity', now - 9999 * DAY))
        self.assertTrue(m._n103_stale('goal', 'goal', now - 241 * DAY))
        self.assertFalse(m._n103_stale('goal', 'goal', now - 239 * DAY))
        self.assertFalse(m._n103_stale('goal', 'goal', now - 900 * DAY, confirmed=now - DAY))      # confirmed yesterday

    def test_stale_facts_used_in_a_turn_are_collected(self):
        self.put('current:trip', 'trip to Goa next month', cat='current', created=time.time() - 60 * DAY)
        self.m._N103_CTX.stale = []
        try:
            self.m._n83_memory_block(self.cid, 'tell me about my trip')
            self.assertEqual([k for (_i, k, _v) in self.m._N103_CTX.stale], ['current:trip'])
        finally:
            self.m._N103_CTX.stale = None


class TestLanguageDirective(MindCase):
    def prompt(self, text):
        self.fake.when(lambda r, t: True, 'ok')
        self.m._n83_chat(self.msg(text))
        return next(c for c in self.fake.calls if base.answer_stage(c['messages']))['messages'][0]['content']

    def test_gujarati_message_asks_for_a_gujarati_reply(self):
        p = self.prompt('મારા ભાઈનું નામ શું છે')
        self.assertIn('Gujarati', p)
        self.assertIn('same language and script', p)

    def test_english_message_adds_nothing(self):
        self.assertNotIn('same language and script', self.prompt('what is my brother called'))

    def test_an_explicit_language_setting_wins(self):
        style = {'language': 'english', 'detail': 'normal'}
        self.m._N103_CTX.text = 'મારા ભાઈનું નામ શું છે'
        try:
            self.assertNotIn('same language and script', self.m._n83_system(self.cid, style, ''))
            style['language'] = 'auto'
            self.assertIn('same language and script', self.m._n83_system(self.cid, style, ''))
        finally:
            self.m._N103_CTX.text = None


class TestWholeTurn(MindCase):
    def test_a_gujarati_question_gets_the_english_fact_in_its_prompt(self):
        self.m._n35_extract(self.cid, 'my brother is Rahul', 'owner-text')
        self.fake.when(lambda r, t: True, 'તમારા ભાઈનું નામ રાહુલ છે.')
        out = self.m._n83_chat(self.msg('મારા ભાઈનું નામ શું છે'))
        system = next(c for c in self.fake.calls if base.answer_stage(c['messages']))['messages'][0]['content']
        self.assertIn('brother: Rahul', system)
        self.assertEqual(out['text'].split('\n')[0], 'તમારા ભાઈનું નામ રાહુલ છે.')

    def test_the_turn_wrapper_leaves_no_state_behind(self):
        self.fake.when(lambda r, t: True, 'ok')
        self.m._n83_chat(self.msg('hello there friend'))
        self.assertIsNone(getattr(self.m._N103_CTX, 'text', None))
        self.assertIsNone(getattr(self.m._N103_CTX, 'stale', None))


class TestTips(MindCase):
    def turn_with_stale_fact(self, who=None):
        self.put('current:trip', 'trip to Goa next month', cat='current', created=time.time() - 60 * DAY, fid='F35-AAAAAAAAAA')
        self.fake.when(lambda r, t: True, 'Your trip to Goa is next month.')
        self.sent.clear()
        self.m._n83_chat(self.msg('when is my trip'))
        return [t for (_c, t) in self.sent if t.startswith('💡')]

    def test_off_by_default(self):
        self.assertEqual(self.turn_with_stale_fact(), [])

    def test_on_sends_one_line_with_two_buttons_then_waits_a_day_and_a_week(self):
        self.m._n103_put(self.cid, 'tips', 'on')
        tips = self.turn_with_stale_fact()
        self.assertEqual(len(tips), 1)
        self.assertIn('trip', tips[0])
        kb = [k for (_c, k) in self.kbs if k][-1]
        self.assertEqual([b['callback_data'] for b in kb['inline_keyboard'][0]], ['m103:ok:F35-AAAAAAAAAA', 'm103:ch:F35-AAAAAAAAAA'])
        self.sent.clear()
        self.m._n83_chat(self.msg('when is my trip'))
        self.assertEqual([t for (_c, t) in self.sent if t.startswith('💡')], [])          # not twice in a day
        self.m._n103_put(self.cid, 'tip_last', time.time() - 21 * 3600)
        self.sent.clear()
        self.m._n83_chat(self.msg('when is my trip'))
        self.assertEqual([t for (_c, t) in self.sent if t.startswith('💡')], [])          # same fact: not again for 7 days
        self.m._n103_put(self.cid, 'tip_last', time.time() - 21 * 3600)
        self.m._n103_put(self.cid, 'tip:F35-AAAAAAAAAA', time.time() - 8 * DAY)
        self.sent.clear()
        self.m._n83_chat(self.msg('when is my trip'))
        self.assertEqual(len([t for (_c, t) in self.sent if t.startswith('💡')]), 1)

    def test_no_tip_when_the_fact_was_not_used_or_is_fresh_or_the_chat_is_not_the_owners(self):
        self.m._n103_put(self.cid, 'tips', 'on')
        self.fake.when(lambda r, t: True, 'ok')
        self.put('current:trip', 'trip to Goa next month', cat='current', created=time.time() - 2 * DAY)
        self.sent.clear()
        self.m._n83_chat(self.msg('when is my trip'))
        self.assertEqual([t for (_c, t) in self.sent if t.startswith('💡')], [])
        self.m._n103_maybe_tip(999, [('F35-BBBBBBBBBB', 'k', 'v')], {'ok': True, 'text': 'x'})
        self.m._n103_maybe_tip(self.cid, [], {'ok': True, 'text': 'x'})
        self.m._n103_maybe_tip(self.cid, [('F35-BBBBBBBBBB', 'k', 'v')], None)
        self.assertEqual([t for (_c, t) in self.sent if t.startswith('💡')], [])


# ===================================================================================================================
# 4. THE CARDS AND COMMANDS
# ===================================================================================================================
class TestCommands(MindCase):
    def route(self, text):
        self.sent.clear()
        self.kbs.clear()
        return self.m._n103_route(self.cid, text)

    def seed(self):
        now = time.time()
        self.put('name', 'Gautam', cat='identity', created=now - 400 * DAY, evidence='my name is Gautam')
        self.put('brother', 'Rahul', cat='relation', created=now - 90 * DAY, evidence='mera bhai Rahul hai')
        self.put('city', 'Ahmedabad', cat='relation', created=now - 20 * DAY, evidence='I live in Ahmedabad')
        self.put('city', 'Surat', cat='relation', created=now - 300 * DAY, updated=now - 20 * DAY, active=0, sup=self.fid_of('city'))
        self.put('current:trip', 'trip to Goa', cat='current', created=now - 60 * DAY)
        self.put('goal', 'learn options trading', cat='goal', created=now - 10 * DAY, evidence='I want to learn options trading')

    def test_card_groups_marks_and_lists_the_commands(self):
        self.seed()
        self.assertTrue(self.route('what do you know about me'))
        t = self.said()
        for needle in ('WHAT I REMEMBER ABOUT YOU', 'WHO YOU ARE', 'PEOPLE', 'RIGHT NOW', 'GOALS', 'name: Gautam', 'brother: Rahul', 'city: Ahmedabad', 'you told me', '⏳ may be out of date', 'history of my city', '/forget83'):
            self.assertIn(needle, t, needle)
        self.assertNotIn('Surat', t)                                 # a replaced version is history, not memory
        self.assertLessEqual(len(t), 3900)

    def test_card_phrases_in_four_languages_and_the_old_phrase(self):
        self.seed()
        for q in ('what do you remember about me', 'tell me everything you know about me', 'show my memory', 'mere baare mein kya kya jaante ho', 'मेरे बारे में क्या जानते हो', 'મારા વિશે તને શું ખબર છે'):
            self.assertTrue(self.route(q), q)
            self.assertIn('WHAT I REMEMBER ABOUT YOU', self.said(), q)
        self.assertIn('Gautam', self.m._n83_memory_text(self.cid))                  # the v83 command now shows the same card

    def test_empty_card_is_a_friendly_sentence(self):
        self.route('what do you know about me')
        self.assertIn('have not stored any facts', self.said())

    def test_topic_card(self):
        self.seed()
        self.assertTrue(self.route('what do you know about my brother'))
        self.assertIn('brother: Rahul', self.said())
        self.assertNotIn('goal', self.said())
        self.assertFalse(self.route('what do you know about my submarine'))          # nothing stored: leave it to the normal chat
        self.assertFalse(self.route('what do you know about Elon Musk'))             # not about me: the normal chat answers

    def test_why_shows_evidence_source_age_and_status(self):
        self.seed()
        self.assertTrue(self.route('why do you think my brother is Rahul'))
        t = self.said()
        for needle in ('Why I think brother = Rahul', '“mera bhai Rahul hai”', 'you told me', 'last confirmed', 'does not usually go out of date'):
            self.assertIn(needle, t, needle)
        self.assertTrue(self.route('how do you know my trip to Goa'))
        self.assertIn('did not keep your exact words', self.said())
        self.assertIn('⏳ It may be out of date', self.said())
        self.assertTrue(self.route('why do you think my goal is options trading'))
        self.assertIn('Probably still true', self.said())

    def test_why_leaves_other_why_questions_alone(self):
        self.seed()
        for q in ('why did you say that', 'how did you know that', 'why do you think nifty will fall', 'why do you think my submarine is red'):
            self.assertFalse(self.route(q), q)

    def test_history_lists_versions_with_dates(self):
        self.seed()
        self.assertTrue(self.route('history of my city'))
        t = self.said()
        self.assertIn('History of city', t)
        self.assertRegex(t, r'→ \d+ \w+ \d{4}: Surat  \(replaced\)')
        self.assertRegex(t, r'→ now: Ahmedabad')
        self.assertTrue(self.route('how has my city changed'))
        self.assertIn('Surat', self.said())
        self.assertTrue(self.route('what did I tell you about my city before'))
        self.assertFalse(self.route('history of Rome'))

    def test_history_of_an_unchanged_fact(self):
        self.seed()
        self.route('history of my name')
        self.assertIn('has not changed', self.said())

    def test_forgotten_versions_are_never_shown(self):
        self.seed()
        self.put('city', 'Pune', cat='relation', created=time.time() - 200 * DAY, updated=time.time() - 100 * DAY, active=0, sup='')       # deactivated by a forget: no successor
        self.route('history of my city')
        self.assertNotIn('Pune', self.said())
        self.route('what did you know about me on 1 jan 2000')
        self.route('what did you know about me 3 months ago')
        self.assertNotIn('Pune', self.said())

    def test_time_travel(self):
        self.seed()
        now = time.time()
        d = self.m._n103_ist(now - 150 * DAY).strftime('%d %B %Y')
        self.assertTrue(self.route('what did you know about me on %s' % d))
        t = self.said()
        self.assertIn('as of', t)
        self.assertIn('name: Gautam', t)
        self.assertNotIn('brother', t)                 # learned 90 days ago
        self.assertIn('city: Surat', t)
        self.assertIn('changed on', t)
        self.assertIn('to “Ahmedabad”', t)
        self.assertIn('learned after that date', t)
        self.assertTrue(self.route('what did you know about me 2 weeks ago'))
        self.assertIn('brother: Rahul', self.said())
        self.assertIn('city: Ahmedabad', self.said())
        self.assertTrue(self.route('what was my city on %s' % d))
        self.assertIn('Surat', self.said())

    def test_time_travel_asks_for_a_readable_date_and_handles_nothing_stored(self):
        self.seed()
        self.assertTrue(self.route('what did you know about me on blue moon'))
        self.assertIn('could not read that date', self.said())
        self.assertTrue(self.route('memory as of 2 jan 2000'))
        self.assertIn('nothing stored from before', self.said())

    def test_whats_new(self):
        self.seed()
        self.assertTrue(self.route("what's new about me this month"))
        t = self.said()
        self.assertIn('NEW  goal: learn options trading', t)
        self.assertIn('NEW  city: Ahmedabad', t)
        self.assertIn('CHANGED  city: “Surat” → “Ahmedabad”', t)
        self.assertNotIn('Gautam', t)
        self.assertTrue(self.route('what did you learn about me today'))
        self.assertIn('Nothing new', self.said())

    def test_whats_new_does_not_take_ordinary_small_talk_or_the_old_learning_log(self):
        for q in ("what's new", 'whats new with you', 'what did you learn recently', 'what have you learned about me'):
            self.assertFalse(self.route(q), q)

    def test_checkup_lists_stale_facts_with_buttons_and_the_callbacks_work(self):
        self.seed()
        self.assertTrue(self.route('memory check-up'))
        t = self.said()
        self.assertIn('trip to Goa', t)
        self.assertNotIn('Gautam', t)
        kb = [k for (_c, k) in self.kbs if k][-1]
        data = [b['callback_data'] for row in kb['inline_keyboard'] for b in row]
        fid = self.fid_of('current:trip')
        self.assertIn('m103:ok:' + fid, data)
        self.assertTrue(all(len(d.encode()) <= 64 for d in data))
        self.sent.clear()
        self.m.handle_callback({'id': 'q1', 'data': 'm103:ok:' + fid, 'from': {'id': OWNER_ID}, 'message': {'chat': {'id': OWNER_ID}}})
        self.assertIn('Kept: current trip', self.said())
        self.assertFalse(self.m._n103_stale('current:trip', 'current', self.m._n103_q('SELECT updated FROM facts WHERE id=?', (fid,))[0][0]))
        self.assertGreater(self.meta(fid)[4], time.time() - 10)
        self.route('memory check-up')
        self.assertIn('Nothing in my memory of you looks out of date', self.said())

    def test_checkup_changed_button_asks_for_the_new_value(self):
        self.seed()
        fid = self.fid_of('current:trip')
        self.m.handle_callback({'id': 'q1', 'data': 'm103:ch:' + fid, 'from': {'id': OWNER_ID}, 'message': {'chat': {'id': OWNER_ID}}})
        self.assertIn('actually, my current trip is', self.said())

    def test_callbacks_from_anyone_else_or_for_another_chats_fact_do_nothing(self):
        self.seed()
        fid = self.fid_of('current:trip')
        before = self.m._n103_q('SELECT updated FROM facts WHERE id=?', (fid,))[0][0]
        self.m.handle_callback({'id': 'q1', 'data': 'm103:ok:' + fid, 'from': {'id': 999}, 'message': {'chat': {'id': 999}}})
        self.m.handle_callback({'id': 'q1', 'data': 'm103:ok:' + fid, 'from': {'id': 999}, 'message': {'chat': {'id': OWNER_ID}}})
        self.assertEqual(self.m._n103_q('SELECT updated FROM facts WHERE id=?', (fid,))[0][0], before)
        self.assertEqual(self.sent, [])
        self.m._n103_callback({'id': 'q2', 'data': 'm103:ok:' + fid, 'from': {'id': OWNER_ID}, 'message': {'chat': {'id': 12345}}})           # the fact belongs to another chat
        self.assertEqual(self.m._n103_q('SELECT updated FROM facts WHERE id=?', (fid,))[0][0], before)

    def test_settings_and_status_and_help(self):
        self.assertTrue(self.route('memory tips on'))
        self.assertEqual(self.m._n103_get(self.cid, 'tips'), 'on')
        self.route('memory tips off')
        self.assertEqual(self.m._n103_get(self.cid, 'tips'), 'off')
        self.route('who do you mean off')
        self.assertEqual(self.m._n103_get(self.cid, 'questions'), 'off')
        self.route('who do you mean on')
        self.assertEqual(self.m._n103_get(self.cid, 'questions'), 'on')
        self.seed()
        self.route('memory 103 status')
        self.assertIn('Mind 103: 6 facts'.replace('6', '5'), self.said())
        self.route('memory help')
        for needle in ('what do you know about me', 'why do you think', 'history of my city', 'memory check-up', 'memory eval', 'allow whatsapp'):
            self.assertIn(needle, self.said())

    def test_phrases_that_belong_to_other_layers_are_not_taken(self):
        for q in ('who can use nemo', 'who can use my nemo', 'who can message nemo'):
            self.assertFalse(self.route(q), q)

    def test_ordinary_sentences_are_not_taken(self):
        for q in ('memory', 'memory test', 'show memory', 'show me memory', 'my memory', 'check my memory usage', 'how much memory is free', 'remember to buy milk', 'what is my wife called', 'hello', 'allow me to explain', 'history of the roman empire',
                  'what do you know about quantum physics', 'mind map', 'why do you think so', 'block the road', 'my friend is coming tomorrow'):
            self.assertFalse(self.route(q), q)
            self.assertEqual(self.sent, [], q)


class TestTimeParser(MindCase):
    NOW = 1790000000.0                    # 2026-09-21 14:13 UTC

    def when(self, text):
        return self.m._n103_when(text, now=self.NOW)

    def test_relative(self):
        self.assertEqual(self.when('2 weeks ago')[0], self.NOW - 14 * DAY)
        self.assertEqual(self.when('a month ago')[0], self.NOW - 30 * DAY)
        self.assertEqual(self.when('three days ago')[0], self.NOW - 3 * DAY)
        self.assertEqual(self.when('last week')[0], self.NOW - 7 * DAY)
        self.assertEqual(self.when('1 year ago')[1], '1 year ago')
        y = self.when('yesterday')
        self.assertLess(y[0], self.NOW)
        self.assertGreater(y[0], self.NOW - 2 * DAY)

    def test_dates_are_end_of_day_and_day_first(self):
        t, label = self.when('5 march 2025')
        self.assertEqual(label, '5 Mar 2025')
        self.assertEqual(self.m._n103_ist(t).strftime('%H:%M:%S'), '23:59:59')
        self.assertEqual(self.when('on 5th March 2025')[1], '5 Mar 2025')
        self.assertEqual(self.when('March 5, 2025')[1], '5 Mar 2025')
        self.assertEqual(self.when('2025-03-05')[1], '5 Mar 2025')
        self.assertEqual(self.when('05/03/2025')[1], '5 Mar 2025')                  # day first, as in India
        self.assertEqual(self.when('5.3.25')[1], '5 Mar 2025')

    def test_a_date_without_a_year_is_the_latest_one_not_in_the_future(self):
        self.assertEqual(self.when('5 march')[1], '5 Mar 2026')
        self.assertEqual(self.when('5 december')[1], '5 Dec 2025')

    def test_month_means_its_end(self):
        t, label = self.when('in March 2025')
        self.assertEqual(label, 'the end of March 2025')
        self.assertEqual(self.m._n103_ist(t).strftime('%d %b'), '31 Mar')
        self.assertEqual(self.when('in december')[1], 'the end of December 2025')
        self.assertEqual(self.when('in 2024')[1], 'the end of 2024')

    def test_unreadable_and_impossible_dates(self):
        for q in ('blue moon', '', '31 february 2025', '45 march', 'sometime'):
            self.assertIsNone(self.when(q), q)


# ===================================================================================================================
# 5. WHO DO YOU MEAN?
# ===================================================================================================================
class TestAskWhichPerson(MindCase):
    def setUp(self):
        super().setUp()
        now = time.time()
        self.put('friend_amit', 'Amit lives in Surat', cat='relation', created=now - 20 * DAY)
        self.put('friend_rohan', 'Rohan works at a bank', cat='relation', created=now - 10 * DAY)

    def ask(self, text):
        self.sent.clear()
        self.kbs.clear()
        msg = self.owner_msg(text)
        return self.m._n103_front(msg)

    def pending(self):
        return self.m._n103_q('SELECT token,text,role,names FROM mind103_pending')

    def test_a_question_about_my_friend_asks_which_one(self):
        self.assertTrue(self.ask('where does my friend live?'))
        t = self.said()
        self.assertIn('Which friend do you mean?', t)
        self.assertIn('Amit', t)
        self.assertIn('Rohan', t)
        kb = self.kbs[-1][1]['inline_keyboard']
        labels = [b['text'] for row in kb for b in row]
        self.assertEqual(sorted(labels), ['Amit', 'Rohan', 'Someone else'])
        self.assertTrue(all(len(b['callback_data'].encode()) <= 64 for row in kb for b in row))
        self.assertEqual(len(self.pending()), 1)
        self.assertEqual(self.passed, [])                                         # the message waits; nothing was answered or guessed

    def test_requests_in_other_languages(self):
        for i, q in enumerate(('mera dost kahan rehta hai', 'मेरा दोस्त कहाँ रहता है', 'મારો મિત્ર ક્યાં રહે છે', 'call my friend')):
            self.m._n103_q('DELETE FROM mind103_pending', write=True)
            self.assertTrue(self.ask(q), q)

    def test_nothing_to_ask(self):
        self.assertFalse(self.ask('where does Amit live?'))                       # a name is in the message
        self.assertFalse(self.ask('अमित कहाँ रहता है, मेरा दोस्त'))                  # the same name in script
        self.assertFalse(self.ask('my friend is coming to dinner tomorrow'))     # a statement, not a request
        self.assertFalse(self.ask('my friend told me what happened yesterday')) # "what" later in a statement is not a question to me
        self.assertFalse(self.ask('where does my cousin live?'))                  # no cousin stored
        self.assertFalse(self.ask('where does a friend live?'))                  # not "my"
        self.assertFalse(self.ask('/start my friend'))
        self.assertFalse(self.ask('ok'))
        self.assertEqual(self.pending(), [])

    def test_a_request_that_starts_a_little_late_still_asks(self):
        self.assertTrue(self.ask('can you call my friend'))
        self.assertIn('Which friend', self.said())

    def test_only_one_known_person_is_not_ambiguous(self):
        self.m._n103_q('UPDATE facts SET active=0 WHERE fkey=?', ('friend_rohan',), write=True)
        self.assertFalse(self.ask('where does my friend live?'))

    def test_can_be_switched_off(self):
        self.m._n103_put(self.cid, 'questions', 'off')
        self.assertFalse(self.ask('where does my friend live?'))

    def test_not_asked_twice_in_ten_minutes_if_unanswered(self):
        self.assertTrue(self.ask('where does my friend live?'))
        self.assertFalse(self.ask('what does my friend do?'))
        self.m._n103_q('UPDATE mind103_pending SET ts=ts-700', write=True)
        self.assertTrue(self.ask('what does my friend do?'))

    def test_not_for_the_family_or_in_groups(self):
        self.assertFalse(self.m._n103_front({'chat': {'id': 999, 'type': 'private'}, 'from': {'id': 999}, 'text': 'where does my friend live?'}))
        self.assertFalse(self.m._n103_front({'chat': {'id': OWNER_ID, 'type': 'group'}, 'from': {'id': OWNER_ID}, 'text': 'where does my friend live?'}))
        self.assertFalse(self.m._n103_front(self.owner_msg('where does my friend live?', photo=[{'file_id': 'x'}])))
        self.assertEqual(self.pending(), [])

    def test_picking_one_answers_the_original_with_the_name_and_remembers_the_choice_for_half_an_hour(self):
        self.ask('where does my friend live?')
        token, text, role, names = self.pending()[0]
        idx = json.loads(names).index('Amit')
        self.m.handle_callback({'id': 'c1', 'data': 'm103:p:%s:%d' % (token, idx), 'from': {'id': OWNER_ID}, 'message': {'chat': {'id': OWNER_ID}}})
        self.assertEqual(len(self.passed), 1)
        again = self.passed[0]
        self.assertTrue(again['_m103_asked'])
        self.assertEqual(again['text'], 'where does my friend live?\n(By “friend” I mean Amit.)')
        self.assertEqual((again['chat']['id'], again['from']['id'], again['message_id']), (OWNER_ID, OWNER_ID, 7))
        self.assertEqual(self.pending(), [])
        self.assertFalse(self.ask('what does my friend do?'))                    # sticky for 30 minutes
        self.m._n103_q('UPDATE mind103_pick SET ts=ts-1900', write=True)
        self.assertTrue(self.ask('what does my friend do?'))
        self.assertEqual(self.m._N103_STATS['picked'], 1)

    def test_someone_else_passes_the_original_unchanged(self):
        self.ask('where does my friend live?')
        token = self.pending()[0][0]
        self.assertEqual(len(token), 32)                                              # 128 bits
        self.m.handle_callback({'id': 'c1', 'data': 'm103:p:%s:x' % token, 'from': {'id': OWNER_ID}, 'message': {'chat': {'id': OWNER_ID}}})
        self.assertEqual(self.passed[0]['text'], 'where does my friend live?')
        self.assertTrue(self.passed[0]['_m103_asked'])
        self.assertEqual(self.m._n103_q('SELECT * FROM mind103_pick'), [])

    def test_a_replayed_message_is_never_asked_again(self):
        msg = self.owner_msg('where does my friend live?')
        msg['_m103_asked'] = True
        self.assertFalse(self.m._n103_front(msg))

    def test_expired_used_or_foreign_tokens(self):
        self.ask('where does my friend live?')
        token = self.pending()[0][0]
        self.m.handle_callback({'id': 'c1', 'data': 'm103:p:%s:0' % token, 'from': {'id': 999}, 'message': {'chat': {'id': 999}}})
        self.assertEqual(len(self.pending()), 1)                                  # a stranger's tap does nothing
        self.m._n103_q('UPDATE mind103_pending SET ts=ts-4000', write=True)
        self.sent.clear()
        self.m.handle_callback({'id': 'c1', 'data': 'm103:p:%s:0' % token, 'from': {'id': OWNER_ID}, 'message': {'chat': {'id': OWNER_ID}}})
        self.assertIn('expired', self.said())
        self.assertEqual(self.passed, [])
        self.m.handle_callback({'id': 'c1', 'data': 'm103:p:%s:0' % token, 'from': {'id': OWNER_ID}, 'message': {'chat': {'id': OWNER_ID}}})
        self.assertEqual(self.passed, [])

    def test_out_of_range_choice_is_ignored(self):
        self.ask('where does my friend live?')
        token = self.pending()[0][0]
        self.m.handle_callback({'id': 'c1', 'data': 'm103:p:%s:5' % token, 'from': {'id': OWNER_ID}, 'message': {'chat': {'id': OWNER_ID}}})
        self.assertEqual(self.passed, [])

    def test_the_handler_goes_through_the_real_wrapper_and_falls_back_to_the_rest_of_the_chain(self):
        self.assertIs(self.m.handle.__name__, 'handle')
        self.m.handle(self.owner_msg('where does my friend live?'))
        self.assertEqual(self.passed, [])
        self.assertIn('Which friend', self.said())
        self.m.handle(self.owner_msg('good morning nemo'))
        self.assertEqual([p['text'] for p in self.passed], ['good morning nemo'])


# ===================================================================================================================
# 6. THE DOOR
# ===================================================================================================================
@needs_flask
class TestTwilioDoor(MindCase):
    def setUp(self):
        super().setUp()
        m = self.m
        self.ai = []

        def web_ai(text):
            self.ai.append(text)
            return 'answer to ' + text
        p = mock.patch.object(m, 'web_ai', web_ai)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.dict(m.WEBCFG, {'token': 'secret1'})
        p.start()
        self.addCleanup(p.stop)
        self.http = m.build_web_app().test_client()

    def wa(self, number, body='hello', secret='secret1'):
        return self.http.post('/twilio/%s/whatsapp' % secret, data={'From': number, 'Body': body})

    def allow(self, number='+919876543210'):
        self.m._n103_route(self.cid, 'allow whatsapp ' + number)
        self.sent.clear()

    def test_default_is_deny(self):
        r = self.wa('whatsapp:+919876543210')
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(b'Message', r.data)
        self.assertEqual(self.ai, [])

    def test_an_allowed_number_passes_through_to_the_assistant(self):
        self.allow('+91 98765 43210')
        r = self.wa('whatsapp:+919876543210', 'what is my balance')
        self.assertEqual(self.ai, ['what is my balance'])
        self.assertIn(b'answer to what is my balance', r.data)

    def test_a_stranger_is_turned_away_and_the_owner_hears_once_a_day(self):
        self.allow()
        r = self.wa('whatsapp:+14155550123', 'hi')
        self.assertEqual((r.status_code, self.ai), (200, []))
        t = self.said()
        self.assertIn('ending 0123', t)
        self.assertNotIn('4155550123', t)                                           # only the last four digits are ever shown
        self.assertEqual(len(self.sent), 1)
        self.wa('whatsapp:+14155550123', 'hi again')
        self.assertEqual(len(self.sent), 1)                                          # the same number: not again today
        self.wa('whatsapp:+14155550999', 'hi')
        self.assertEqual(len(self.sent), 2)                                          # a different number is a new notice
        self.m._n103_q('UPDATE mind103_block SET notified=notified-90000', write=True)
        self.wa('whatsapp:+14155550123', 'hi')
        self.assertEqual(len(self.sent), 3)                                          # a day later: once more
        self.assertEqual(self.m._n103_q('SELECT count FROM mind103_block WHERE last4=?', ('0123',))[0][0], 3)

    def test_the_guard_wraps_exactly_the_three_twilio_routes_and_adds_no_global_hook(self):
        m = self.m
        app = m.build_web_app()
        self.assertEqual(len(app.before_request_funcs.get(None, [])), 1)               # the website's own (v95) hook only
        guarded = sorted(r.rule for r in app.url_map.iter_rules() if app.view_functions[r.endpoint].__code__.co_name == '_n103_guarded')
        self.assertEqual(guarded, ['/twilio/<s>/gather', '/twilio/<s>/voice', '/twilio/<s>/whatsapp'])

    def test_the_notice_to_the_owner_does_not_hold_up_the_reply(self):
        self.m._N103_SYNC['on'] = False
        told = []
        done = __import__('threading').Event()

        def slow_send(cid, text, kb=None):
            told.append(text)
            done.set()
        with mock.patch.object(self.m, 'send_text', slow_send):
            self.wa('whatsapp:+14155550123')
            self.assertTrue(done.wait(5))
        self.assertIn('ending 0123', told[0])

    def test_the_full_number_of_a_stranger_is_not_stored(self):
        self.wa('whatsapp:+14155550123')
        dump = json.dumps(self.m._n103_q('SELECT * FROM mind103_block'))
        self.assertNotIn('4155550123', dump)
        self.assertNotIn('14155550123', dump)

    def test_voice_calls_are_rejected_and_gather_too(self):
        r = self.http.post('/twilio/secret1/voice', data={'From': '+14155550123'})
        self.assertIn(b'<Reject/>', r.data)
        r = self.http.get('/twilio/secret1/voice?From=%2B14155550123')
        self.assertIn(b'<Reject/>', r.data)
        r = self.http.post('/twilio/secret1/gather', data={'From': '+14155550123', 'SpeechResult': 'sell everything'})
        self.assertIn(b'<Reject/>', r.data)
        self.assertEqual(self.ai, [])
        self.allow()
        r = self.http.post('/twilio/secret1/gather', data={'From': '+919876543210', 'SpeechResult': 'what is the time'})
        self.assertEqual(self.ai, ['what is the time'])

    def test_no_sender_or_a_garbled_one_is_refused(self):
        for data in ({'Body': 'hi'}, {'From': '', 'Body': 'hi'}, {'From': 'whatsapp:', 'Body': 'hi'}, {'From': 'abc', 'Body': 'hi'}):
            self.http.post('/twilio/secret1/whatsapp', data=data)
        self.assertEqual(self.ai, [])

    def test_the_secret_in_the_address_is_still_checked_for_an_allowed_number(self):
        self.allow()
        r = self.wa('whatsapp:+919876543210', secret='wrong')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.ai, [])

    def test_a_failure_in_the_check_fails_closed(self):
        self.allow()
        with mock.patch.object(self.m, '_n103_digits', side_effect=RuntimeError('boom')):
            r = self.wa('whatsapp:+919876543210')
        self.assertEqual(self.ai, [])
        self.assertEqual(r.status_code, 200)
        with mock.patch.object(self.m, '_n103_q', side_effect=sqlite3.OperationalError('locked')):
            r = self.wa('whatsapp:+919876543210')
        self.assertEqual(self.ai, [])

    def test_other_routes_are_untouched(self):
        self.assertEqual(self.http.get('/api/status').status_code, 401)             # still the website's own key check
        r = self.http.post('/tv/secret1', data='alert text')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.http.post('/api/chat', json={'message': 'hi'}).status_code, 401)

    def test_number_commands(self):
        m = self.m
        route = lambda t: (self.sent.clear(), m._n103_route(self.cid, t))[1]
        self.assertTrue(route('whatsapp numbers'))
        self.assertIn('every caller is turned away', self.said())
        self.assertTrue(route('allow whatsapp +91 98765 43210 as Gautam'))
        self.assertIn('may now use', self.said())
        self.assertIn('Gautam', self.said())
        self.assertNotIn('98765 43210', self.said())
        self.assertEqual(m._n103_q('SELECT number FROM mind103_allow')[0][0], '919876543210')
        route('allow phone 9876543211')
        self.assertEqual(sorted(r[0] for r in m._n103_q('SELECT number FROM mind103_allow')), ['919876543210', '919876543211'])    # a bare 10-digit number is Indian
        route('whatsapp numbers')
        self.assertIn('•', self.said())
        self.assertIn('3210', self.said())
        self.assertNotIn('9876543210', self.said())
        route('allow whatsapp 12345')
        self.assertIn('does not look like a full phone number', self.said())
        route('remove whatsapp +919876543210')
        self.assertIn('Removed', self.said())
        route('remove whatsapp +919876543210')
        self.assertIn('was not on the list', self.said())
        self.assertEqual(len(m._n103_q('SELECT number FROM mind103_allow')), 1)

    def test_digits(self):
        d = self.m._n103_digits
        self.assertEqual(d('whatsapp:+91 98765-43210'), '919876543210')
        self.assertEqual(d('09876543210'), '919876543210')
        self.assertEqual(d('+1 (415) 555-0123'), '14155550123')
        self.assertEqual(d(None), '')
        self.assertEqual(self.m._n103_masked('919876543210'), '+91••••••3210')


# ===================================================================================================================
# 7. FORGETTING REACHES THE NEW TABLES
# ===================================================================================================================
class TestForgetting(MindCase):
    def forget(self, mode, needle=None):
        n = self.m._n86_needle(needle) if needle else None
        return self.m._n86_forget_execute(self.cid, mode, n)

    def test_the_store_is_registered_for_topic_conversation_and_everything(self):
        row = [s for s in self.m._N86_STORES if s[0] == 'mind103'][0]
        self.assertEqual(set(row[3]), {'topic', 'conversation', 'everything'})

    def test_forgetting_a_topic_removes_the_fact_and_its_evidence(self):
        self.m._n35_extract(self.cid, 'my brother is Rahul', 'owner-text')
        self.m._n35_extract(self.cid, 'my name is Gautam', 'owner-text')
        fid = self.fid_of('brother')
        self.assertTrue(self.meta(fid))
        self.forget('topic', 'brother Rahul')
        self.assertNotIn('brother', self.facts())
        self.assertIsNone(self.meta(fid))
        self.assertEqual(self.facts()['name'], 'Gautam')
        self.assertEqual(self.meta(self.fid_of('name'))[0], 'my name is Gautam')
        dump = json.dumps(self.m._n103_q('SELECT * FROM mind103_meta'))
        self.assertNotIn('Rahul', dump)

    def test_evidence_of_a_replaced_version_is_removed_with_its_topic_too(self):
        self.m._n35_extract(self.cid, 'I live in Surat', 'owner-text')
        self.m._n35_extract(self.cid, 'Actually I live in Ahmedabad', 'owner-text')
        self.forget('topic', 'Surat')
        self.assertNotIn('Surat', json.dumps(self.m._n103_q('SELECT * FROM mind103_meta')))
        self.assertNotIn('Surat', json.dumps(self.m._n103_q('SELECT * FROM facts')))

    def test_pending_questions_and_picks_that_mention_it_are_removed(self):
        now = time.time()
        self.m._n103_q('INSERT INTO mind103_pending(token,chat_id,text,role,names,msg,ts) VALUES(?,?,?,?,?,?,?)', ('a' * 12, str(self.cid), 'where does my friend Amit live', 'friend', '["Amit"]', '{}', now), write=True)
        self.m._n103_q('INSERT INTO mind103_pick(chat_id,role,name,ts) VALUES(?,?,?,?)', (str(self.cid), 'friend', 'Amit', now), write=True)
        self.forget('topic', 'Amit')
        self.assertEqual(self.m._n103_q('SELECT * FROM mind103_pending'), [])
        self.assertEqual(self.m._n103_q('SELECT * FROM mind103_pick'), [])

    def test_everything_clears_every_note(self):
        self.m._n35_extract(self.cid, 'my brother is Rahul', 'owner-text')
        self.forget('everything')
        self.assertEqual(self.m._n103_q('SELECT * FROM mind103_meta'), [])

    def test_the_door_lists_are_not_memory_and_survive(self):
        self.m._n103_route(self.cid, 'allow whatsapp +919876543210')
        self.m._n35_extract(self.cid, 'my brother is Rahul', 'owner-text')
        self.forget('everything')
        self.assertEqual(len(self.m._n103_q('SELECT * FROM mind103_allow')), 1)

    def test_a_forgotten_topic_is_not_relearned_from_script(self):
        self.m._n35_extract(self.cid, 'my brother is Rahul', 'owner-text')
        self.forget('topic', 'brother')
        self.propose([{'key': 'brother', 'value': 'Rahul', 'category': 'relation'}])
        rec = self.m._n83_extract(self.cid, {}, 'મારો ભાઈ Rahul છે અને હું તેને ખૂબ ચાહું છું', '')
        self.assertNotIn('brother', self.facts())


# ===================================================================================================================
# 8. STRUCTURE
# ===================================================================================================================
class TestStructure(MindCase):
    def test_version_docstring_and_protected_names(self):
        src = open(base.NEMO_FILE, encoding='utf-8').read()
        self.assertGreaterEqual(float(self.m.VERSION), 103.0)
        self.assertIn('v103.0 - MIND', src[:6000])
        self.assertIn("'_n103_'", src)

    def test_the_layer_calls_no_ai_makes_no_network_call_and_places_no_order(self):
        L = mind_source()
        for bad in ('ask_ai(', '_n73_request(', '_n83_call(', 'requests.', 'urllib', 'socket.', 'subprocess', 'os.system', 'eval(', 'exec(', 'place_order', 'OWNER_LOCK', 'owner_lock', 'GUARD'):
            self.assertNotIn(bad, L, bad)
        self.assertIsNone(re.search(r'\b(?:fyers|broker|kite|angel)\w*\(', L, re.I))              # no call into a broker (the word may appear in a comment or in the regression row that checks for it)
        self.assertNotIn('ask_ai', [n for n in re.findall(r'^def (\w+)', L, re.M)])

    def test_ask_ai_is_left_alone(self):
        self.assertFalse(any(n.lower().startswith('_n103') for n in self.m.ask_ai.__code__.co_names))

    def test_only_its_own_tables_are_created_and_nothing_secret_is_written(self):
        L = mind_source()
        tables = set(re.findall(r'CREATE TABLE IF NOT EXISTS (\w+)', L))
        self.assertEqual(tables, {'mind103_meta', 'mind103_set', 'mind103_pick', 'mind103_pending', 'mind103_allow', 'mind103_block'})
        for bad in ('token_hex(2)', 'api_key', 'sk-', 'AIza', 'password ='):
            self.assertNotIn(bad, L, bad)

    def test_the_older_phrases_that_mean_something_else_are_left_to_their_owners(self):
        """'memory' alone is the server's RAM, 'what's new' is small talk, 'why did you say that' is the answer receipt: the front door must not take them."""
        for q in ('memory', "what's new", 'why did you say that', 'how did you know that', 'forget my sister', 'mind map'):
            self.assertFalse(self.m._n103_route(self.cid, q), q)

    def test_every_hook_is_installed_exactly_once_on_top_of_the_previous_layer(self):
        m = self.m
        self.assertIs(m._n83_memory_block.__name__, '_n83_memory_block')
        for name, prev in (('_n35_norm', '_N103_NORM_PREV'), ('_n83_memory_block', '_N103_MB_PREV'), ('_n35_set_fact', '_N103_SETFACT_PREV'), ('_n35_extract', '_N103_EXTRACT_PREV'),
                           ('_n83_extract', '_N103_CLERK_PREV'), ('_n83_worth_extracting', '_N103_WORTH_PREV'), ('_n83_validate_fact', '_N103_VALIDATE_PREV'), ('_n83_system', '_N103_SYSTEM_PREV'),
                           ('_n86_turn', '_N103_TURN_PREV'), ('handle_callback', '_N103_CALLBACK_PREV'), ('build_web_app', '_N103_BUILD_PREV'), ('_n83_memory_text', '_N103_MEMTEXT_PREV'),
                           ('_n82_capabilities', '_N103_CAPS_PREV'), ('prime_regression_suite', '_N103_REG_PREV'), ('main', '_N103_MAIN_PREV')):
            self.assertIsNot(getattr(m, name), getattr(m, prev), name)

    def test_regression_rows_pass_and_are_named_v103(self):
        r = self.m.prime_regression_suite()
        rows = [x for x in r['tests'] if x['name'].startswith('v103-')]
        self.assertGreaterEqual(len(rows), 12)
        self.assertEqual([x['name'] for x in rows if not x['ok']], [])

    def test_capabilities_mention_the_new_powers(self):
        t = self.m._n82_capabilities()
        for needle in ('Mind 103', 'Hindi and Gujarati', 'may be outdated', 'history of my city', 'which one before answering', 'Twilio'):
            self.assertIn(needle, t)

    def test_help_command_is_registered(self):
        self.assertIn('mind103', [c[0] for c in self.m._N40_COMMANDS])

    def test_main_prepares_the_tables(self):
        with mock.patch.object(self.m, '_N103_MAIN_PREV', lambda *a, **k: 'ran'):
            self.m._N103_SCHEMA['path'] = None
            self.assertEqual(self.m.main(), 'ran')
            self.assertEqual(self.m._N103_SCHEMA['path'], self.m._N35_DB)


if __name__ == '__main__':
    unittest.main()
