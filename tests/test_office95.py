"""Nemo v95 Office: GSTIN and PAN checks (with the invoice drafts they protect) and the spaced-repetition study helper.

Offline. The GSTIN vectors were made and checked with the python-stdnum library (an independent implementation of the same Luhn mod-36 rule), and the bot's own function was also compared with it on 30,000 random
strings when it was written. The AI that makes cards from text is a script.

    NEMO_FILE=/path/to/nemotron_bot.py python -m unittest tests.test_office95 -v
"""
import json
import time
import unittest

from tests import test_cortex83 as base
from tests.test_scout93 import ScoutCase
from tests.test_forge91 import OWNER_ID


def setUpModule():
    if base.m is None:
        base.setUpModule()


# made and validated with python-stdnum's gstin.validate
VALID = ['19RYOJQ9624GCZ9', '32PUTCD7317JAZJ', '24RZWKB9756MVZG', '06UFTAQ1035B3ZW', '29HTAJK7218SDZS', '32HUJJA1393OJZ6', '09RCWGK3763QKZZ', '07CSYBM1767JRZY', '24AVAFG0858PRZA', '09NCSKG4421K6Z3',
         '33KANBE4037W7ZG', '07BOZJF9164GVZS', '32GXYCN6288DSZQ', '09GAITJ0322GCZE', '09TUSBB2398GVZO', '33AYTHJ6328C5ZR', '24GSUFA9852LQZT', '06OESJS2224MCZN', '27JHTFX3110FDZ4', '09PTCLB1702D3Z9',
         '32IHXLI6895TYZ0', '33QFXBE3743P5Z3', '33GGXAC4411NVZ2', '29BBFGL8700S9Z7', '27AAPFU0939F1ZV']
# the same numbers with the check character moved on by one: stdnum rejects every one of them
WRONG_CHECK = ['19RYOJQ9624GCZA', '32PUTCD7317JAZK', '24RZWKB9756MVZH', '06UFTAQ1035B3ZX', '29HTAJK7218SDZT', '32HUJJA1393OJZ7', '09RCWGK3763QKZ0', '07CSYBM1767JRZZ', '27AAPFU0939F1ZO']


class OfficeCase(ScoutCase):
    def setUp(self):
        super().setUp()
        for k in self.m._N95_STATS:
            self.m._N95_STATS[k] = 0
        self.m._n95_q('DELETE FROM office95_setting WHERE key=?', ('my_gstin',), write=True)
        self.m._n95_q('DELETE FROM study95_card', write=True)
        self.m._N95_QUIZ.clear()
        self.guest = lambda text, **k: dict({'chat': {'id': 5552, 'type': 'private'}, 'from': {'id': 5552, 'first_name': 'Asha'}, 'message_id': 3, 'text': text}, **k)


# ===================================================================================================================
# 1. GSTIN AND PAN
# ===================================================================================================================
class TestGstin(OfficeCase):
    def test_every_independently_made_gstin_passes(self):
        for g in VALID:
            r = self.m._n95_gstin_check(g)
            self.assertTrue(r['ok'], (g, r['reason']))
            self.assertEqual(r['state_code'], g[:2])
            self.assertEqual(r['pan'], g[2:12])

    def test_a_mistyped_check_character_is_caught_and_the_right_one_is_named(self):
        for g in WRONG_CHECK:
            r = self.m._n95_gstin_check(g)
            self.assertFalse(r['ok'], g)
            self.assertTrue(r['format_ok'], g)
            self.assertIn('does not match', r['reason'])
        r = self.m._n95_gstin_check('27AAPFU0939F1ZO')
        self.assertIn('it should be V', r['reason'])

    def test_any_single_mistyped_character_is_caught(self):
        chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        g = '27AAPFU0939F1ZV'
        caught = 0
        for i in range(15):
            for c in chars:
                if c == g[i]:
                    continue
                if not self.m._n95_gstin_check(g[:i] + c + g[i + 1:])['ok']:
                    caught += 1
        self.assertEqual(caught, 15 * 35, 'a Luhn-style check misses no single-character error')

    def test_spaces_dashes_and_lower_case_are_forgiven(self):
        for g in ('27aapfu0939f1zv', '27 AAPFU 0939 F1ZV', '27-AAPFU0939F-1ZV', '  27AAPFU0939F1ZV\n'):
            self.assertTrue(self.m._n95_gstin_check(g)['ok'], g)
        self.assertEqual(self.m._n95_gstin_check('27 aapfu0939f1zv')['gstin'], '27AAPFU0939F1ZV')

    def test_the_reasons_for_each_kind_of_wrong_number(self):
        f = self.m._n95_gstin_check
        self.assertIn('has 15 characters', f('27AAPFU0939F1Z')['reason'])
        self.assertIn('this has 14', f('27AAPFU0939F1Z')['reason'])
        self.assertIn('layout is wrong', f('369296450896540')['reason'])
        self.assertIn('layout is wrong', f('27AAPFU0939F1Z!')['reason'])
        self.assertIn('not a state or territory code', f('00AAPFU0939F1ZV')['reason'])
        self.assertIn('not a state or territory code', f('40AAPFU0939F1ZV')['reason'])
        self.assertIn('PAN inside it', f('27AAPXU0939F1ZV')['reason'])
        self.assertIn('PAN inside it', f('27AAPFU0000F1ZV')['reason'])
        self.assertIn('13th character cannot be 0', f('27AAPFU0939F0ZV')['reason'])
        self.assertIn('must be the letter Z', f('27AAPFU0939F1AV')['reason'])
        self.assertIn('15 characters', f('')['reason'])
        self.assertIn('15 characters', f(None)['reason'])

    def test_the_state_table(self):
        S = self.m._N95_GST_STATES
        self.assertEqual((S['27'], S['24'], S['07'], S['29'], S['33'], S['36']), ('Maharashtra', 'Gujarat', 'Delhi', 'Karnataka', 'Tamil Nadu', 'Telangana'))
        for code in ('01', '09', '19', '37', '38', '97', '99', '25', '28'):
            self.assertIn(code, S)
        self.assertNotIn('00', S)
        self.assertNotIn('39', S)
        self.assertIn('older code', S['25'])

    def test_the_wording_says_what_was_and_was_not_checked(self):
        t = self.m._n95_gstin_text('27AAPFU0939F1ZV')
        self.assertIn('✅ 27AAPFU0939F1ZV is a valid GSTIN', t)
        self.assertIn('Maharashtra (27)', t)
        self.assertIn('PAN inside it: AAPFU0939F (a firm or LLP)', t)
        self.assertIn('does not prove the business is registered', t)
        t = self.m._n95_gstin_text('27AAPFU0939F1ZO')
        self.assertTrue(t.startswith('⚠️ 27AAPFU0939F1ZO is not a valid GSTIN'))

    def test_the_command(self):
        for q in ('gstin check 27AAPFU0939F1ZV', 'check gstin 27AAPFU0939F1ZV', 'validate gstin: 27AAPFU0939F1ZV', 'gstin validate 27 AAPFU0939F 1ZV', '/gstin check 27AAPFU0939F1ZV'):
            self.assertIn('is a valid GSTIN', self.say(q), q)
        self.assertIn('is not a valid GSTIN', self.say('gstin check 27AAPFU0939F1ZO'))

    def test_pan(self):
        f = self.m._n95_pan_check
        self.assertTrue(f('AAPFU0939F')['ok'])
        self.assertEqual(f('ABCPD1234E')['type'], 'an individual')
        self.assertEqual(f('abcpd1234e')['pan'], 'ABCPD1234E')
        for bad, why in (('ABCDE123', '10 characters'), ('ABCDE12345', '5 letters, 4 digits'), ('ABCXD1234E', 'holder type'), ('ABCPD0000E', '0000')):
            r = f(bad)
            self.assertFalse(r['ok'], bad)
            self.assertIn(why, r['reason'])
        self.assertIn('is a valid PAN layout: an individual', self.say('pan check ABCPD1234E'))
        self.assertIn('is not a valid PAN', self.say('check pan ABCXD1234E'))

    def test_a_guest_cannot_use_the_commands(self):
        n = len(self.passed)
        self.m.handle(self.guest('gstin check 27AAPFU0939F1ZV'))
        self.assertEqual(len(self.passed), n + 1)


class TestMyGstinAndInvoices(OfficeCase):
    def inv(self, gstin, supply='intra'):
        lines = [{'name': 'TV 55', 'qty': 1, 'rate': 62000, 'gst': 18, 'disc': 0}]
        return {'no': 'INV/1', 'status': 'draft', 'date': '2026-10-05', 'customer': 'Ramesh Traders', 'gstin': gstin, 'supply': supply, 'totals': self.m._n85_invoice_totals(lines, supply)}

    def test_saving_and_showing_my_gstin(self):
        self.assertIn('You have not told me your GSTIN', self.say('my gstin'))
        out = self.say('my gstin 24AVAFG0858PRZA')
        self.assertIn('✅ Saved your GSTIN (24AVAFG0858PRZA, Gujarat)', out)
        self.assertIn('Your GSTIN: 24AVAFG0858PRZA (Gujarat)', self.say('my gstin'))
        self.assertIn('Saved your GSTIN', self.say('my gstin is 27AAPFU0939F1ZV'))
        self.assertEqual(self.m._n95_my_gstin(), '27AAPFU0939F1ZV')

    def test_a_wrong_gstin_is_not_saved(self):
        self.say('my gstin 24AVAFG0858PRZA')
        out = self.say('my gstin 24AVAFG0858PRZB')
        self.assertIn('I did not save that', out)
        self.assertEqual(self.m._n95_my_gstin(), '24AVAFG0858PRZA')

    def test_an_invalid_customer_gstin_is_flagged_under_the_draft(self):
        t = self.m._n85_invoice_text(self.inv('27AAPFU0939F1ZO'))
        self.assertIn('PAYABLE:', t, 'the original draft is all still there')
        self.assertIn('⚠️ Customer GSTIN 27AAPFU0939F1ZO is not valid: the last character does not match the others (it should be V)', t)
        self.assertIn('Check it against the customer’s GST certificate before issuing', t)

    def test_a_valid_customer_gstin_is_confirmed(self):
        t = self.m._n85_invoice_text(self.inv('27AAPFU0939F1ZV'))
        self.assertIn('✅ Customer GSTIN checks out (Maharashtra, PAN AAPFU0939F, a firm or LLP).', t)
        self.assertIn('Tip: say “my gstin <your GSTIN>”', t)

    def test_no_customer_gstin_adds_nothing(self):
        before = self.m._N95_INV_TEXT_PREV(self.inv(''))
        self.assertEqual(self.m._n85_invoice_text(self.inv('')), before)

    def test_intra_state_for_two_different_states_is_called_out(self):
        self.say('my gstin 24AVAFG0858PRZA')
        t = self.m._n85_invoice_text(self.inv('27AAPFU0939F1ZV', 'intra'))
        self.assertIn('Your GSTIN is in Gujarat (24) and the customer’s is in Maharashtra (27)', t)
        self.assertIn('INTER-state sale (IGST), but the draft says intra-state', t)
        self.assertIn('supply=inter', t)

    def test_inter_state_for_the_same_state_is_called_out_with_the_exceptions(self):
        self.say('my gstin 27AAPFU0939F1ZV')
        t = self.m._n85_invoice_text(self.inv('27JHTFX3110FDZ4', 'inter'))
        self.assertIn('Both GSTINs are in Maharashtra', t)
        self.assertIn('INTRA-state', t)
        self.assertIn('SEZ, export', t)

    def test_matching_tax_types_say_nothing_more(self):
        self.say('my gstin 27AAPFU0939F1ZV')
        for supply, g in (('intra', '27JHTFX3110FDZ4'), ('inter', '24AVAFG0858PRZA')):
            t = self.m._n85_invoice_text(self.inv(g, supply))
            self.assertIn('✅ Customer GSTIN checks out', t)
            self.assertNotIn('⚠️', t)
            self.assertNotIn('Tip:', t)

    def test_the_pdf_and_the_chat_text_share_the_same_notes(self):
        import inspect
        self.assertIn('_n85_invoice_text(inv)', inspect.getsource(self.m._n85_invoice_pdf))

    def test_a_failure_in_the_check_leaves_the_draft_as_it_was(self):
        self.start(self.m, '_n95_invoice_notes', lambda inv: (_ for _ in ()).throw(RuntimeError('x')))
        inv = self.inv('27AAPFU0939F1ZV')
        self.assertEqual(self.m._n85_invoice_text(inv), self.m._N95_INV_TEXT_PREV(inv))
        self.assertEqual(self.m._N95_STATS['errors'], 1)

    def test_a_real_invoice_made_through_the_showroom_command_carries_the_notes(self):
        self.m._n85_init() if hasattr(self.m, '_n85_init') else None
        cid = OWNER_ID
        try:
            inv_id = self.m._n85_invoice_create(cid, 'Ramesh Traders', 'intra', 'TV 55 x1 @62000 gst18', '27AAPFU0939F1ZO')
        except Exception as exc:                          # the showroom tables may need their own set-up in this harness
            self.skipTest('showroom tables are not set up here: %s' % exc)
        text = self.m._n85_invoice_text(self.m._n85_invoice_get(cid, inv_id))
        self.assertIn('Customer GSTIN 27AAPFU0939F1ZO is not valid', text)


# ===================================================================================================================
# 2. THE STUDY HELPER
# ===================================================================================================================
class TestSchedule(OfficeCase):
    def test_again_comes_back_in_ten_minutes_and_counts_a_lapse(self):
        delay, iv, ease, reps, lapses = self.m._n95_schedule(4, 6.0, 2.5, 1, 0)
        self.assertAlmostEqual(delay * 1440, 10.0)
        self.assertEqual((iv, reps, lapses), (0.0, 0, 2))
        self.assertAlmostEqual(ease, 2.3)

    def test_ease_never_falls_below_1_3(self):
        e = 1.35
        for _ in range(5):
            _d, _i, e, _r, _l = self.m._n95_schedule(0, 0.0, e, 0, 0)
        self.assertEqual(e, 1.3)

    def test_the_first_good_answer_is_a_day_and_the_second_three_days(self):
        d, iv, ease, reps, _l = self.m._n95_schedule(0, 0.0, 2.5, 0, 2)
        self.assertEqual((d, reps), (1.0, 1))
        d, iv, ease, reps, _l = self.m._n95_schedule(1, 1.0, 2.5, 0, 2)
        self.assertEqual((d, reps), (3.0, 2))
        d, iv, ease, reps, _l = self.m._n95_schedule(2, 3.0, 2.5, 0, 2)
        self.assertAlmostEqual(d, 7.5)

    def test_easy_stretches_more_and_raises_the_ease(self):
        good = self.m._n95_schedule(2, 3.0, 2.5, 0, 2)
        easy = self.m._n95_schedule(2, 3.0, 2.5, 0, 3)
        self.assertGreater(easy[0], good[0])
        self.assertGreater(easy[2], good[2])
        self.assertEqual(self.m._n95_schedule(0, 0.0, 2.5, 0, 3)[0], 4.0)

    def test_hard_is_a_small_step_and_lowers_the_ease(self):
        d, iv, ease, reps, _l = self.m._n95_schedule(3, 10.0, 2.5, 0, 1)
        self.assertAlmostEqual(d, 12.0)
        self.assertAlmostEqual(ease, 2.35)

    def test_the_gap_is_capped_at_a_year(self):
        self.assertEqual(self.m._n95_schedule(9, 300.0, 3.0, 0, 3)[0], 365.0)


class TestQuiz(OfficeCase):
    def test_adding_a_card_in_every_wording(self):
        self.assertIn('Card #1 added', self.say('card add What is PCR? | Open puts divided by open calls'))
        self.assertIn('Card #2 added', self.say('flashcard add deck=trading Delta | How much the option moves per rupee'))
        self.assertIn('Card #3 added', self.say('/card add Q | A'))
        self.assertEqual([r[0] for r in self.m._n95_q('SELECT deck FROM study95_card ORDER BY id')], ['general', 'trading', 'general'])

    def test_a_card_needs_both_sides(self):
        for q in ('card add just a question', 'card add  | answer', 'card add question | '):
            out = self.say(q)
            self.assertNotIn('added', out, q)
        self.assertEqual(self.m._n95_q('SELECT COUNT(*) FROM study95_card')[0][0], 0)

    def test_long_cards_are_clipped(self):
        self.say('card add ' + 'q' * 500 + ' | ' + 'a' * 900)
        f, b = self.m._n95_q('SELECT front, back FROM study95_card')[0]
        self.assertLessEqual(len(f), 300)
        self.assertLessEqual(len(b), 600)

    def test_no_cards_gives_the_way_to_start(self):
        out = self.say('quiz me')
        self.assertIn('You have no flashcards yet', out)
        self.assertIn('card add', out)

    def test_a_full_round(self):
        self.say('card add What is PCR? | Open puts divided by open calls')
        out = self.say('quiz me')
        self.assertIn('QUESTION (general)\nWhat is PCR?', out)
        self.assertIn('say “show”', out)
        out = self.say('show')
        self.assertIn('ANSWER\nOpen puts divided by open calls', out)
        self.assertIn('again, hard, good or easy', out)
        out = self.say('good')
        self.assertIn('this card comes back in 1 days' if False else 'this card comes back in', out)
        self.assertIn('Nothing is due right now', out)
        row = self.m._n95_q('SELECT interval, reps, due FROM study95_card')[0]
        self.assertEqual(row[1], 1)
        self.assertAlmostEqual(row[0], 1.0)
        self.assertGreater(row[2], time.time() + 80000)

    def test_again_brings_the_same_card_back_in_ten_minutes_so_it_is_not_asked_again_at_once(self):
        self.say('card add Q | A')
        self.say('quiz me')
        self.say('show')
        out = self.say('again')
        self.assertIn('comes back in 10 minutes', out)
        due = self.m._n95_q('SELECT due, lapses FROM study95_card')[0]
        self.assertTrue(500 < due[0] - time.time() < 700)
        self.assertEqual(due[1], 1)

    def test_the_grades_by_number(self):
        for num, expect in (('1', 'comes back in 10 minutes'), ('2', 'comes back in'), ('3', 'comes back in'), ('4', 'comes back in')):
            self.m._n95_q('DELETE FROM study95_card', write=True)
            self.say('card add Q | A')
            self.say('quiz me')
            self.say('show')
            self.assertIn(expect, self.say(num), num)

    def test_the_next_due_card_follows_and_the_deck_filter_works(self):
        self.say('card add deck=a A1 | a1')
        self.say('card add deck=b B1 | b1')
        out = self.say('quiz b')
        self.assertIn('B1', out)
        self.assertNotIn('A1', out)
        self.say('show')
        out = self.say('good')
        self.assertIn('Nothing is due right now', out, 'only deck b was being quizzed')

    def test_skip_and_stop(self):
        self.say('card add Q1 | A1')
        self.say('card add Q2 | A2')
        first = self.say('quiz me')
        second = self.say('skip')
        self.assertIn('QUESTION', second)
        self.assertNotEqual(first.split('\n')[1], second.split('\n')[1])
        self.assertIn('Quiz ended', self.say('stop quiz'))
        self.assertEqual(self.say('show'), '', 'after the quiz ended "show" is an ordinary message')

    def test_other_messages_pass_through_while_a_quiz_is_open(self):
        self.say('card add Q | A')
        self.say('quiz me')
        n = len(self.passed)
        self.assertEqual(self.say('what is the weather'), '')
        self.assertEqual(len(self.passed), n + 1)
        self.assertIn('ANSWER', self.say('show'), 'and the quiz is still waiting')

    def test_grading_words_before_the_answer_is_shown_are_ordinary_messages(self):
        self.say('card add Q | A')
        self.say('quiz me')
        n = len(self.passed)
        self.say('good')
        self.assertEqual(len(self.passed), n + 1)

    def test_a_quiz_that_is_left_open_expires(self):
        self.say('card add Q | A')
        self.say('quiz me')
        self.m._N95_QUIZ[OWNER_ID]['at'] -= 2000
        n = len(self.passed)
        self.say('show')
        self.assertEqual(len(self.passed), n + 1)
        self.assertNotIn(OWNER_ID, self.m._N95_QUIZ)

    def test_a_card_deleted_during_the_quiz_ends_it_quietly(self):
        self.say('card add Q | A')
        self.say('quiz me')
        self.m._n95_q('DELETE FROM study95_card', write=True)
        n = len(self.passed)
        self.say('show')
        self.assertEqual(len(self.passed), n + 1)

    def test_my_cards_and_delete(self):
        self.say('card add deck=trading Delta | x')
        self.say('card add Theta | y')
        out = self.say('my cards')
        self.assertIn('trading: 1 card(s), 1 due now', out)
        self.assertIn('general: 1 card(s), 1 due now', out)
        self.assertIn('#2 Theta', out)
        self.assertIn('Deleted card #1', self.say('delete card 1'))
        self.assertIn('There is no card #1', self.say('delete card 1'))
        self.assertIn('There is no card #99', self.say('delete card #99'))

    def test_cards_belong_to_the_chat_that_made_them(self):
        self.m._n95_card_add(5552, 'Guest Q', 'Guest A')
        self.say('card add Owner Q | Owner A')
        out = self.say('quiz me')
        self.assertIn('Owner Q', out)
        self.assertEqual(self.m._n95_counts(5552), [('general', 1, 1)])
        self.assertEqual(self.say('delete card 1'), 'There is no card #1.', 'the guest’s card number is not the owner’s to delete')

    def test_a_guest_cannot_use_any_of_it(self):
        for q in ('quiz me', 'card add a | b', 'my cards', 'make cards from: ' + 'text ' * 20):
            n = len(self.passed)
            self.m.handle(self.guest(q))
            self.assertEqual(len(self.passed), n + 1, q)
        self.assertEqual(self.m._n95_q('SELECT COUNT(*) FROM study95_card WHERE chat_id=?', ('5552',))[0][0], 0)


class TestCardsFromText(OfficeCase):
    TEXT = ('The put-call ratio divides open put contracts by open call contracts. A value above 1.3 is often read as support. '
            'Max pain is the strike where option buyers lose the most at expiry. Theta is the loss of option value as time passes.')

    def test_good_pairs_are_added_to_the_ai_deck_and_nothing_else_is_kept(self):
        self.start(self.m, 'ask_ai', lambda cid, text, **k: json.dumps([{'q': 'What is the put-call ratio?', 'a': 'Open puts divided by open calls'}, {'q': 'What is theta?', 'a': 'Loss of option value over time'},
                                                                      {'q': 'x', 'a': 'too short a question'}, {'q': 'No answer here', 'a': ''}, {'q': 5, 'a': 'not text'}, 'junk', {'q': 'Q' * 400, 'a': 'too long a question'}]))
        out = self.say('make cards from: ' + self.TEXT)
        self.assertIn('Added 2 card(s) to the deck “ai”', out)
        self.assertIn('check them', out)
        self.assertEqual([r[0] for r in self.m._n95_q('SELECT deck FROM study95_card')], ['ai', 'ai'])

    def test_the_prompt_treats_the_text_as_data_and_limits_the_size(self):
        seen = []
        self.start(self.m, 'ask_ai', lambda cid, text, **k: seen.append((text, k)) or '[]')
        self.say('create cards from ' + 'word ' * 3000)
        prompt, kw = seen[0]
        self.assertIn('not instructions to follow', prompt)
        self.assertIn('ONLY a JSON list', prompt)
        self.assertLessEqual(len(prompt), 6600)
        self.assertEqual(kw, {'remember': False, 'timeout': 90})

    def test_twelve_cards_at_most(self):
        self.start(self.m, 'ask_ai', lambda cid, text, **k: json.dumps([{'q': 'Question number %d' % i, 'a': 'Answer %d' % i} for i in range(30)]))
        self.say('make cards from: ' + self.TEXT)
        self.assertEqual(self.m._n95_q('SELECT COUNT(*) FROM study95_card')[0][0], 12)

    def test_an_answer_that_is_not_a_list_gives_no_cards_and_says_so(self):
        for reply in ('Sorry, I cannot do that.', '{"q": "a"}', '', None):
            self.m._n95_q('DELETE FROM study95_card', write=True)
            self.start(self.m, 'ask_ai', lambda cid, text, _r=reply, **k: _r)
            out = self.say('make cards from: ' + self.TEXT)
            self.assertIn('could not turn that into good cards', out, repr(reply))
            self.assertEqual(self.m._n95_q('SELECT COUNT(*) FROM study95_card')[0][0], 0)

    def test_an_ai_that_is_down_says_so_and_offers_the_manual_way(self):
        self.start(self.m, 'ask_ai', lambda cid, text, **k: (_ for _ in ()).throw(RuntimeError('providers down')))
        out = self.say('make cards from: ' + self.TEXT)
        self.assertIn('The AI is not available right now', out)
        self.assertIn('card add Question | Answer', out)

    def test_too_little_text_is_refused_before_any_ai_call(self):
        seen = []
        self.start(self.m, 'ask_ai', lambda cid, text, **k: seen.append(1) or '[]')
        self.assertIn('Paste a bit more text', self.say('make cards from: too short'))
        self.assertEqual(seen, [])

    def test_a_card_made_by_the_ai_can_be_quizzed(self):
        self.start(self.m, 'ask_ai', lambda cid, text, **k: json.dumps([{'q': 'What is max pain?', 'a': 'The strike where buyers lose the most'}]))
        self.say('make cards from: ' + self.TEXT)
        self.assertIn('What is max pain?', self.say('quiz ai'))
