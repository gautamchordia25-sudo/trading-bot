"""v85 Steward: showroom copilot (leads, dues, stock, exact GST invoices, rule-based proposals) and page watchers.

GST figures below are itemised by hand (see the comment above each case), not produced by the code under test.

    python -m unittest tests.test_steward85_biz -v
"""
import datetime as dt
import json
import time
import unittest
from decimal import Decimal as D
from unittest import mock

from tests import test_cortex83 as base
from tests.test_steward85 import StewardCase, ist_iso, setUpModule  # noqa: F401

NOW = dt.datetime(2026, 10, 5, 10, 0)           # Monday 5 Oct 2026, 10:00 IST


class BizCase(StewardCase):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(self.m, '_n83_now', lambda: NOW)
        p.start()
        self.patches.append(p)

    def line(self, name, qty, rate, gst, disc=0):
        return {'name': name, 'qty': qty, 'rate': rate, 'gst': gst, 'disc': disc}


# ================================= exact GST arithmetic =================================
class TestGstMaths(BizCase):
    def test_single_line_intra_state(self):
        # 62,000 taxable; GST 18% = 11,160.00 -> CGST 5,580.00 + SGST 5,580.00; total 73,160.00; no round-off
        t = self.m._n85_invoice_totals([self.line('TV', 1, 62000, 18)], 'intra')
        self.assertEqual((D(t['taxable']), D(t['cgst']), D(t['sgst']), D(t['igst'])), (D('62000.00'), D('5580.00'), D('5580.00'), D('0')))
        self.assertEqual((t['payable'], D(t['round_off'])), ('73160', D('0')))
        self.assertEqual(t['words'], 'Rupees Seventy Three Thousand One Hundred Sixty Only')

    def test_discount_decimals_and_round_off(self):
        # gross 3 x 1,499.50 = 4,498.50; less 100.00 = 4,398.50 taxable; 12% = 527.82 (4398.5 x 12 / 100 exactly)
        # CGST 263.91 + SGST 263.91; line total 4,926.32; payable rounds half-up to 4,926 (round-off -0.32)
        t = self.m._n85_invoice_totals([self.line('Speaker', 3, 1499.50, 12, 100)], 'intra')
        self.assertEqual((D(t['taxable']), D(t['cgst']), D(t['sgst'])), (D('4398.50'), D('263.91'), D('263.91')))
        self.assertEqual((D(t['grand']), t['payable'], D(t['round_off'])), (D('4926.32'), '4926', D('-0.32')))

    def test_odd_paise_tax_splits_without_losing_a_paisa(self):
        # taxable 100.60 at 5% = 5.03 exactly; half = 2.515 -> CGST 2.52 (half-up) and SGST is the remainder 2.51
        t = self.m._n85_invoice_totals([self.line('Cable', 1, 100.60, 5)], 'intra')
        self.assertEqual((D(t['cgst']), D(t['sgst'])), (D('2.52'), D('2.51')))
        self.assertEqual(D(t['cgst']) + D(t['sgst']), D('5.03'))

    def test_inter_state_is_all_igst(self):
        # 2 x 1,500 = 3,000 less 100 = 2,900 taxable; 18% = 522.00 IGST; total 3,422.00
        t = self.m._n85_invoice_totals([self.line('Mount', 2, 1500, 18, 100)], 'inter')
        self.assertEqual((D(t['igst']), D(t['cgst']), D(t['sgst']), t['payable']), (D('522.00'), D('0'), D('0'), '3422'))

    def test_multiple_lines_each_taxed_at_its_own_rate(self):
        # 10,000 @ 28% = 2,800 ; 500 @ 5% = 25 ; 2,000 @ 0% = 0   -> taxable 12,500 ; tax 2,825 ; grand 15,325 ; CGST 1,412.50 + SGST 1,412.50
        t = self.m._n85_invoice_totals([self.line('AC', 1, 10000, 28), self.line('Paper', 1, 500, 5), self.line('Books', 1, 2000, 0)], 'intra')
        self.assertEqual((D(t['taxable']), D(t['cgst']), D(t['sgst']), D(t['grand'])), (D('12500.00'), D('1412.50'), D('1412.50'), D('15325.00')))
        self.assertEqual([D(x['total']) for x in t['lines']], [D('12800.00'), D('525.00'), D('2000.00')])

    def test_round_off_is_half_up_in_both_directions(self):
        up = self.m._n85_invoice_totals([self.line('X', 1, 1000.50, 0)], 'intra')
        down = self.m._n85_invoice_totals([self.line('X', 1, 1000.49, 0)], 'intra')
        self.assertEqual((up['payable'], D(up['round_off'])), ('1001', D('0.50')))
        self.assertEqual((down['payable'], D(down['round_off'])), ('1000', D('-0.49')))

    def test_float_trap_amounts_stay_exact(self):
        # 0.1 x 3 style traps: 3 x 33.33 = 99.99 exactly with Decimal (floats give 99.99000000000001)
        t = self.m._n85_invoice_totals([self.line('Item', 3, 33.33, 0)], 'intra')
        self.assertEqual(t['lines'][0]['taxable'], '99.99')

    def test_bad_input_is_refused(self):
        with self.assertRaises(ValueError):
            self.m._n85_invoice_totals([self.line('X', 1, 100, 18)], 'sideways')
        with self.assertRaises(ValueError):
            self.m._n85_invoice_totals([self.line('X', 1, 100, 18, 500)], 'intra')       # discount more than the line value

    def test_words_in_the_indian_system(self):
        w = self.m._n85_words_inr
        for amount, want in ((125000, 'Rupees One Lakh Twenty Five Thousand Only'), (10000000, 'Rupees One Crore Only'), (0, 'Rupees Zero Only'),
                             (21, 'Rupees Twenty One Only'), (100000000000, 'Rupees Ten Thousand Crore Only'),
                             (1234567.89, 'Rupees Twelve Lakh Thirty Four Thousand Five Hundred Sixty Seven and Eighty Nine Paise Only'),
                             (100, 'Rupees One Hundred Only'), (1000, 'Rupees One Thousand Only'), (99999, 'Rupees Ninety Nine Thousand Nine Hundred Ninety Nine Only')):
            self.assertEqual(w(amount), want, amount)
        for bad in (-1, 10 ** 12, 'abc', float('nan')):
            with self.assertRaises(ValueError, msg=bad):
                w(bad)

    def test_line_parser(self):
        lines = self.m._n85_parse_lines('TV 55 inch x1 @62,000 gst18; Wall mount x2 @1500 gst 18% disc100;')
        self.assertEqual(lines[0], {'name': 'TV 55 inch', 'qty': 1.0, 'rate': 62000.0, 'gst': 18.0, 'disc': 0.0})
        self.assertEqual(lines[1], {'name': 'Wall mount', 'qty': 2.0, 'rate': 1500.0, 'gst': 18.0, 'disc': 100.0})
        for bad in ('TV x1 @62000', 'TV @62000 gst18', 'TV x1 @abc gst18', '', ';;', '; '.join('Item%d x1 @1 gst5' % i for i in range(41))):
            with self.assertRaises(ValueError, msg=bad):
                self.m._n85_parse_lines(bad)

    def test_a_missing_gst_rate_is_never_assumed(self):
        with self.assertRaises(ValueError) as cm:
            self.m._n85_parse_lines('TV x1 @62000')
        self.assertIn('never assumes a tax rate', str(cm.exception))

    def test_financial_year_label(self):
        d = dt.date
        self.assertEqual([self.m._n85_fy_label(x) for x in (d(2026, 3, 31), d(2026, 4, 1), d(2026, 12, 31), d(2027, 1, 1), d(2099, 6, 1))],
                         ['2025-26', '2026-27', '2026-27', '2026-27', '2099-00'])


class TestInvoices(BizCase):
    def test_numbering_gstin_and_text(self):
        a = self.m._n85_invoice_create(self.cid, 'Ramesh Traders', 'intra', 'TV x1 @62000 gst18; Mount x2 @1500 gst18 disc100', '24abcde1234f1z5')
        b = self.m._n85_invoice_create(self.cid, 'Suresh', 'inter', 'Fan x1 @1800 gst18')
        ia, ib = self.m._n85_invoice_get(self.cid, a), self.m._n85_invoice_get(self.cid, b)
        self.assertEqual((ia['no'], ib['no']), ('INV/2026-27/0001', 'INV/2026-27/0002'))
        self.assertEqual(ia['gstin'], '24ABCDE1234F1Z5')
        text = self.m._n85_invoice_text(ia)
        self.assertIn('PAYABLE: ₹', text)
        self.assertIn('CGST', text)
        self.assertIn('Draft prepared by Nemo from the rates YOU entered', text)
        self.assertIn('IGST', self.m._n85_invoice_text(ib))
        # 62,000 + 2,900 taxable; tax 11,160 + 522 ; grand 76,582
        self.assertEqual(ia['totals']['payable'], '76582')

    def test_bad_gstin_and_customer_isolation(self):
        for bad in ('12345', '24ABCDE1234F1Z', 'XXABCDE1234F1Z5'):
            with self.assertRaises(ValueError, msg=bad):
                self.m._n85_invoice_create(self.cid, 'X', 'intra', 'TV x1 @100 gst18', bad)
        inv = self.m._n85_invoice_create(self.cid, 'X', 'intra', 'TV x1 @100 gst18')
        with self.assertRaises(ValueError):
            self.m._n85_invoice_get(999, inv)

    def test_issue_marks_issued_once_and_reduces_stock_all_or_nothing(self):
        self.m._n85_stock_set(self.cid, 'LED bulb', 10, 'pcs', 3, 120, 18)
        self.m._n85_stock_set(self.cid, 'Fan', 1, 'pcs', 2, 1800, 18)
        ok = self.m._n85_invoice_create(self.cid, 'A', 'intra', 'LED bulb x4 @120 gst18')
        self.assertEqual(self.m._n85_invoice_issue(self.cid, ok, True), ['LED bulb → 6 left'])
        with self.assertRaises(ValueError):
            self.m._n85_invoice_issue(self.cid, ok, True)                      # already issued
        short = self.m._n85_invoice_create(self.cid, 'B', 'intra', 'LED bulb x2 @120 gst18; Fan x3 @1800 gst18')
        with self.assertRaises(ValueError) as cm:
            self.m._n85_invoice_issue(self.cid, short, True)
        self.assertIn('nothing was changed', str(cm.exception))
        self.assertEqual({r[0]: r[1] for r in self.m._n85_items(self.cid)}, {'Fan': 1.0, 'LED bulb': 6.0}, 'the bulbs were not taken either')
        self.assertEqual(self.m._n85_invoice_get(self.cid, short)['status'], 'draft')
        unknown = self.m._n85_invoice_create(self.cid, 'C', 'intra', 'Mystery item x1 @10 gst5')
        with self.assertRaises(ValueError):
            self.m._n85_invoice_issue(self.cid, unknown, True)
        self.assertEqual(self.m._n85_invoice_issue(self.cid, unknown, False), [])    # without stock tracking it can be issued

    def test_same_item_on_two_lines_is_checked_against_the_total(self):
        self.m._n85_stock_set(self.cid, 'Fan', 3, 'pcs', 1, 1800, 18)
        inv = self.m._n85_invoice_create(self.cid, 'A', 'intra', 'Fan x2 @1800 gst18; fan x2 @1700 gst18')
        with self.assertRaises(ValueError):
            self.m._n85_invoice_issue(self.cid, inv, True)
        self.assertEqual(self.m._n85_items(self.cid)[0][1], 3.0)


# ===================================== leads / dues / stock =====================================
class TestLeadsDuesStock(BizCase):
    def test_customers_are_deduplicated_by_name(self):
        a = self.m._n85_cust(self.cid, 'Ramesh')
        b = self.m._n85_cust(self.cid, '  ramesh ')
        self.assertEqual(a, b)
        self.assertNotEqual(a, self.m._n85_cust(self.cid, 'Ramesh Jain'))

    def test_lead_lifecycle_and_follow_up_window(self):
        today, tomorrow = (NOW.date()).isoformat(), (NOW.date() + dt.timedelta(days=1)).isoformat()
        l1 = self.m._n85_lead_add(self.cid, 'Ramesh', '55 inch TV', 62000, today, 'asked for exchange', '98250 12345')
        l2 = self.m._n85_lead_add(self.cid, 'Mehta', 'Fridge', None, tomorrow)
        end = self.m._n85_ist_to_epoch(NOW.replace(hour=23, minute=59, second=59))
        due = self.m._n85_leads(self.cid, 'open', end)
        self.assertEqual([r[0] for r in due], [l1])
        self.m._n85_lead_update(self.cid, l1, status='won')
        self.assertEqual([r[0] for r in self.m._n85_leads(self.cid, 'open')], [l2])
        self.m._n85_lead_update(self.cid, l2, follow='2026-10-20')
        self.assertEqual(self.m._n85_leads(self.cid, 'open', end), [])
        for bad in ({'status': 'maybe'},):
            with self.assertRaises(ValueError):
                self.m._n85_lead_update(self.cid, l2, **bad)
        with self.assertRaises(ValueError):
            self.m._n85_lead_update(999, l2, status='won')

    def test_dues_partial_payment_overpayment_and_status(self):
        d = self.m._n85_due_add(self.cid, 'Suresh', 15000, '2026-10-01', 'TV balance')
        self.assertAlmostEqual(self.m._n85_due_paid(self.cid, d, 5000), 10000)
        with self.assertRaises(ValueError):
            self.m._n85_due_paid(self.cid, d, 10000.5)
        self.assertEqual(len(self.m._n85_dues(self.cid, 'open')), 1)
        self.assertAlmostEqual(self.m._n85_due_paid(self.cid, d), 0.0)
        self.assertEqual(self.m._n85_dues(self.cid, 'open'), [])
        self.assertEqual(len(self.m._n85_dues(self.cid, 'paid')), 1)
        with self.assertRaises(ValueError):
            self.m._n85_due_add(self.cid, 'Bad', -5)
        with self.assertRaises(ValueError):
            self.m._n85_due_paid(self.cid, 9999)

    def test_stock_moves_never_go_negative_and_report_the_reorder_level(self):
        self.m._n85_stock_set(self.cid, 'LED bulb', 12, 'pcs', 10, 120)
        self.assertEqual(self.m._n85_stock_move(self.cid, 'led BULB', -3, 'sale'), (9.0, 10.0))
        with self.assertRaises(ValueError) as cm:
            self.m._n85_stock_move(self.cid, 'LED bulb', -10, 'sale')
        self.assertIn('only 9', str(cm.exception))
        self.assertEqual(self.m._n85_items(self.cid)[0][1], 9.0)
        with self.assertRaises(ValueError):
            self.m._n85_stock_move(self.cid, 'Unknown thing', 1)
        with self.assertRaises(ValueError):
            self.m._n85_stock_move(self.cid, 'LED bulb', 0)
        self.assertEqual([r[0] for r in self.m._n85_items(self.cid, True)], ['LED bulb'])
        self.m._n85_stock_move(self.cid, 'LED bulb', 20, 'purchase')
        self.assertEqual(self.m._n85_items(self.cid, True), [])

    def test_data_is_private_to_the_chat(self):
        self.m._n85_lead_add(self.cid, 'Ramesh', 'TV')
        self.m._n85_stock_set(self.cid, 'Fan', 5)
        self.m._n85_due_add(self.cid, 'Suresh', 100)
        self.assertEqual((self.m._n85_leads(999), self.m._n85_items(999), self.m._n85_dues(999)), ([], [], []))

    def test_summary_numbers(self):
        yesterday = (NOW.date() - dt.timedelta(days=1)).isoformat()
        self.m._n85_lead_add(self.cid, 'Ramesh', 'TV', 62000, yesterday)
        self.m._n85_lead_add(self.cid, 'Mehta', 'Fridge', 30000, '2026-10-30')
        d = self.m._n85_due_add(self.cid, 'Suresh', 15000, yesterday)
        self.m._n85_due_paid(self.cid, d, 5000)
        self.m._n85_due_add(self.cid, 'Future', 4000, '2026-11-30')
        self.m._n85_stock_set(self.cid, 'LED bulb', 4, 'pcs', 10)
        text = self.m._n85_summary_text(self.cid, NOW)
        self.assertIn('Open leads: 2 (quoted value ₹92,000)', text)
        self.assertIn('follow-ups due today or earlier: 1', text)
        self.assertIn('Money still to collect: ₹14,000 across 2 due(s); overdue now: ₹10,000', text)
        self.assertIn('LED bulb 4/10', text)


class TestRuleBasedProposals(BizCase):
    def test_follow_ups_dues_and_low_stock_become_cards_never_messages(self):
        yesterday = (NOW.date() - dt.timedelta(days=1)).isoformat()
        self.m._n85_lead_add(self.cid, 'Ramesh', '55 inch TV', 62000, yesterday)
        self.m._n85_lead_add(self.cid, 'Mehta', 'Fridge', None, '2026-11-01')
        d = self.m._n85_due_add(self.cid, 'Suresh', 15000, yesterday, 'TV balance')
        self.m._n85_stock_set(self.cid, 'LED bulb', 4, 'pcs', 10)
        props = self.m._n85_biz_proposals(self.cid)
        self.assertEqual(sorted(p['kind'] for p in props), ['draft_message', 'draft_message', 'todo'])
        lead = next(p for p in props if p['source'].startswith('biz:lead'))
        self.assertIn('Ramesh', lead['payload']['text'])
        self.assertIn('₹62,000', lead['payload']['text'])
        due = next(p for p in props if p['source'] == 'biz:due%d' % d)
        self.assertIn('₹15,000', due['payload']['text'])
        todo = next(p for p in props if p['kind'] == 'todo')
        self.assertIn('Reorder LED bulb (4 pcs left, reorder level 10)', todo['payload']['text'])
        self.assertTrue(all(p['origin'] == 'rule' for p in props))
        with mock.patch.object(self.m, 'send_email', side_effect=AssertionError('never sends')):
            for p in props:
                pid = self.m._n85_propose(self.cid, p['kind'], p['payload'], p['source'], p['why'])
                self.m._n85_decide(self.cid, pid, 'y')

    def test_nothing_due_means_no_proposals(self):
        self.m._n85_lead_add(self.cid, 'Mehta', 'Fridge', None, '2026-11-01')
        self.m._n85_stock_set(self.cid, 'LED bulb', 40, 'pcs', 10)
        self.assertEqual(self.m._n85_biz_proposals(self.cid), [])


class TestBizCommandsAndNaturalLanguage(BizCase):
    def run_cmd(self, line):
        return self.m._n85_cmd_biz(self.cid, line)

    def test_explicit_commands_write_directly_and_validate_inputs(self):
        out = self.run_cmd('lead name="Ramesh Jain" item="55 inch TV" quote=62000 follow=2026-10-12 phone=9825012345')
        self.assertIn('Lead #1 saved for Ramesh Jain', out)
        self.assertIn('Ramesh Jain — 55 inch TV · quoted ₹62,000', self.run_cmd('leads'))
        self.assertIn('Saved LED bulb', self.run_cmd('stock set item="LED bulb" qty=40 reorder=10 price=120'))
        self.assertIn('LED bulb: -5 → 35 in stock', self.run_cmd('stock out item="LED bulb" qty=5'))
        self.assertIn('⚠️ at or below the reorder level 10', self.run_cmd('stock out item="LED bulb" qty=26'))
        self.assertIn('Due #1 recorded: Suresh owes ₹15,000', self.run_cmd('due add name=Suresh amount=15000 due=2026-10-20'))
        self.assertIn('Still to collect: ₹10,000', self.run_cmd('due paid 1 amount=5000'))
        self.assertIn('Fully paid', self.run_cmd('due paid 1'))
        self.assertIn('Lead #1 marked won', self.run_cmd('lead won 1'))
        self.assertIn('No open leads', self.run_cmd('leads'))

    def test_bad_commands_explain_themselves(self):
        for line, needle in (('lead name=Ramesh', 'missing: item'), ('lead name=A item=B color=red', 'unknown parameter'), ('stock out item=Fan qty=1', 'no stock item'),
                             ('stock out item=Fan qty=abc', 'not a number'), ('due add name=A amount=0', 'between'), ('invoice new customer=A supply=up lines="X x1 @1 gst5"', 'supply must be'),
                             ('invoice new customer=A supply=intra lines="X x1 @1"', 'no gst rate'), ('lead name=A name=B item=C', 'given twice'), ('lead won abc', 'usage'),
                             ('invoice show INV-NOPE', 'no such invoice')):
            with self.assertRaises(ValueError, msg=line) as cm:
                self.run_cmd(line)
            self.assertIn(needle, str(cm.exception), line)

    def test_smart_quotes_from_phones_are_understood(self):
        out = self.run_cmd('lead name=“Ramesh Jain” item=“55 inch TV” quote=62000')
        self.assertIn('Ramesh Jain', out)

    def test_invoice_flow_through_commands(self):
        out = self.run_cmd('invoice new customer="Ramesh Traders" supply=intra lines="TV x1 @62000 gst18" gstin=24ABCDE1234F1Z5')
        self.assertIn('PAYABLE: ₹73,160.00', out)
        inv_id = out.rsplit('/biz85 invoice issue ', 1)[1].strip()
        self.assertIn('INV/2026-27/0001', self.run_cmd('invoice list'))
        self.assertIn('DRAFT', self.run_cmd('invoice show ' + inv_id))
        self.assertIn('Invoice issued', self.run_cmd('invoice issue ' + inv_id))
        self.assertIn('ISSUED', self.run_cmd('invoice show ' + inv_id))
        with mock.patch.object(self.m, 'simple_pdf', lambda title, body, path: open(path, 'wb').write(b'%PDF')) as pdf:
            self.assertIn('PDF sent', self.run_cmd('invoice pdf ' + inv_id))

    def test_natural_language_becomes_a_card_that_writes_only_on_approval(self):
        reply = {'name': 'Ramesh', 'item': '55 inch TV', 'quote': 62000, 'follow': '2026-10-09', 'note': 'wants exchange'}
        self.fake.when(lambda r, t: 'Extract ONE lead record' in t, lambda r, t, msgs: json.dumps(reply))
        res = self.m._n85_nl_task(self.cid, 'lead', 'Ramesh wants a 55 inch TV, quoted 62000, call Friday, wants exchange')
        self.assertEqual(res['text'], '')
        self.assertEqual(self.m._n85_leads(self.cid), [], 'nothing saved before the tap')
        item = self.m._n85_pending(self.cid)[0]
        self.assertEqual(item['kind'], 'biz_lead')
        self.assertIn('quoted ₹62,000', self.cards[-1][1])
        self.cb(item['id'], 'y')
        self.assertEqual(self.m._n85_leads(self.cid)[0][1:4], ('Ramesh', '', '55 inch TV'))

    def test_model_output_is_validated_by_code(self):
        past = {'name': 'Ramesh', 'item': 'TV', 'follow': '2020-01-01'}
        self.fake.when(lambda r, t: 'Extract ONE lead record' in t, lambda r, t, msgs: json.dumps(past))
        res = self.m._n85_nl_task(self.cid, 'lead', 'Ramesh wants a TV, follow up long ago')
        self.assertIn('in the past', res['text'])
        self.assertEqual(self.m._n85_pending(self.cid), [])
        self.fake.rules.insert(0, (lambda r, t: 'Extract ONE due record' in t, json.dumps({'name': 'Suresh', 'amount': -5})))
        res = self.m._n85_nl_task(self.cid, 'due', 'Suresh owes minus five')
        self.assertIn('could not turn that into a record', res['text'])
        self.fake.rules.insert(0, (lambda r, t: 'Extract ONE stock record' in t, 'this is not json'))
        self.assertIn('could not turn', self.m._n85_nl_task(self.cid, 'stock', 'sold some bulbs')['text'])

    def test_provider_outage_points_to_the_exact_command(self):
        self.fake.rules.insert(0, (lambda r, t: True, self.m._N73Error('all_providers_failed')))
        res = self.m._n85_nl_task(self.cid, 'lead', 'Ramesh wants a TV')
        self.assertIn('/biz85 help', res['text'])

    def test_stock_card_creates_or_adjusts_and_never_goes_negative(self):
        pid = self.m._n85_propose(self.cid, 'biz_stock', {'item': 'Fan', 'delta': 5, 'reason': 'purchase', 'unit': 'pcs', 'reorder': 2}, 'you, in chat')
        self.cb(pid, 'y')
        self.assertEqual(self.m._n85_items(self.cid)[0][:2], ('Fan', 5.0))
        pid = self.m._n85_propose(self.cid, 'biz_stock', {'item': 'Fan', 'delta': -9, 'reason': 'sale'}, 'you, in chat')
        state, text = self.m._n85_decide(self.cid, pid, 'y')
        self.assertEqual(state, 'failed')
        self.assertEqual(self.m._n85_items(self.cid)[0][1], 5.0)
        for bad in ({'item': 'Fan', 'delta': 0}, {'item': 'Fan', 'delta': 1, 'reason': 'theft'}, {'item': '', 'delta': 1}, {'item': 'Fan', 'delta': 1, 'extra': 2}):
            with self.assertRaises(ValueError, msg=bad):
                self.m._n85_propose(self.cid, 'biz_stock', bad, 'x')

    def test_dispatch_routes_prefixes_and_phrases(self):
        started = []
        with mock.patch.object(self.m, '_n66_submit', lambda cid, kind, req, fn, *a, **k: started.append((kind, fn.__name__, a)) or 'T1'):
            self.assertTrue(self.m._n85_dispatch(self.msg('lead: Ramesh wants a 55 inch TV, quoted 62000')))
            self.assertTrue(self.m._n85_dispatch(self.msg('Inventory: sold 2 LED bulbs')))
            self.assertFalse(self.m._n85_dispatch(self.msg('stock: reliance price today')), 'for a trading assistant "stock:" means shares, not showroom inventory')
            self.assertTrue(self.m._n85_dispatch(self.msg('due: Suresh owes 15000 by 20th')))
            self.assertTrue(self.m._n85_dispatch(self.msg('research: GST rate on LED televisions in India')))
            self.assertTrue(self.m._n85_dispatch(self.msg('doc: what is the notice period in my lease')))
            self.assertTrue(self.m._n85_dispatch(self.msg('watch: https://shop.example/tv tell me when it drops below 49999')))
            self.assertFalse(self.m._n85_dispatch(self.msg('lead')), 'a bare word is just chat')
            self.assertFalse(self.m._n85_dispatch(self.msg('I will lead the team: it is a plan')), 'the prefix must start the message')
        self.assertEqual([k for k, _f, _a in started], ['BIZ85', 'BIZ85', 'BIZ85', 'RESEARCH85', 'DOC85', 'BIZ85'])


# ======================================= watchers =======================================
def page(text='', meta=None, jsonld=None):
    return {'text': text, 'meta': meta or {}, 'jsonld': jsonld or []}


class TestWatcherExtraction(BizCase):
    def test_price_sources_in_priority_order(self):
        e = self.m._n85_extract_price
        self.assertEqual(e(page('Price ₹1,999', meta={'product:price:amount': '49,999'})), (49999.0, 'page metadata (product:price:amount)'))
        ld = [{'@type': 'Product', 'offers': [{'@type': 'Offer', 'price': '52000'}, {'@type': 'Offer', 'price': '50999.00'}]}]
        self.assertEqual(e(page('₹1', jsonld=ld)), (50999.0, 'structured product data'))
        self.assertEqual(e(page('Samsung 55" TV\nMRP ₹64,990\nDeal price ₹49,999\nEMI from ₹2,500'), 'Deal price')[0], 49999.0)
        self.assertEqual(e(page('Now ₹100. Was ₹150. Today only ₹100. Save ₹50.'))[0], 100.0)

    def test_price_missing_or_keyword_absent_returns_a_reason(self):
        self.assertEqual(self.m._n85_extract_price(page('no numbers here')), (None, 'no price found on the page'))
        price, why = self.m._n85_extract_price(page('Price ₹500'), 'Deal price')
        self.assertIsNone(price)
        self.assertIn('Deal price', why)

    def test_stock_from_structured_data_and_wording(self):
        s = self.m._n85_extract_stock
        self.assertEqual(s(page(jsonld=[{'offers': {'availability': 'https://schema.org/OutOfStock'}}]))[0], 'out')
        self.assertEqual(s(page(jsonld=[{'offers': {'availability': 'https://schema.org/InStock'}}]))[0], 'in')
        self.assertEqual(s(page('Currently unavailable. Notify me when back'))[0], 'out')
        self.assertEqual(s(page('Add to cart'))[0], 'in')
        self.assertEqual(s(page('Add to cart  Out of stock in some colours'))[0], 'unknown')
        self.assertEqual(s(page('nothing relevant'))[0], 'unknown')


class TestWatcherEvaluation(BizCase):
    def ev(self, kind, params, state, text, **kw):
        return self.m._n85_watch_eval(kind, params, state, page(text, **kw), 1000.0)

    def test_first_check_only_sets_the_baseline(self):
        st, alert, val = self.ev('price', {'target': 100}, {}, 'Price ₹90')
        self.assertIsNone(alert)
        self.assertEqual(val, '₹90')

    def test_price_target_alert_is_edge_triggered_and_rearms_after_recovery(self):
        p = {'target': 100}
        st, _a, _v = self.ev('price', p, {}, 'Price ₹120')
        st, alert, _ = self.ev('price', p, st, 'Price ₹99')
        self.assertIn('Price alert', alert)
        self.assertIn('₹99', alert)
        st, alert, _ = self.ev('price', p, st, 'Price ₹99')
        self.assertIsNone(alert, 'same price again: no repeat')
        st, alert, _ = self.ev('price', p, st, 'Price ₹98.50')
        self.assertIsNone(alert, 'less than 1% lower: still the same alert')
        st, alert, _ = self.ev('price', p, st, 'Price ₹90')
        self.assertIn('Price alert', alert, 'a clearly lower price is news again')
        st, alert, _ = self.ev('price', p, st, 'Price ₹130')
        self.assertIsNone(alert)
        st, alert, _ = self.ev('price', p, st, 'Price ₹95')
        self.assertIn('Price alert', alert, 'after a recovery the next drop alerts again')

    def test_percentage_drop_is_relative_to_the_starting_price(self):
        p = {'drop': 10}
        st, _a, _v = self.ev('price', p, {}, 'Price ₹1000')
        st, alert, _ = self.ev('price', p, st, 'Price ₹950')
        self.assertIsNone(alert)
        st, alert, _ = self.ev('price', p, st, 'Price ₹900')
        self.assertIn('fell 10.0% to ₹900', alert)
        self.assertIn('was ₹1,000', alert)

    def test_price_extraction_failure_is_an_error_not_a_silent_ok(self):
        with self.assertRaises(ValueError):
            self.ev('price', {'drop': 5}, {}, 'no price here')

    def test_stock_alert_only_on_the_way_back(self):
        st, _a, _v = self.ev('stock', {}, {}, 'Out of stock')
        st, alert, _ = self.ev('stock', {}, st, 'Out of stock')
        self.assertIsNone(alert)
        st, alert, _ = self.ev('stock', {}, st, 'Add to cart')
        self.assertIn('Back in stock', alert)
        st, alert, _ = self.ev('stock', {}, st, 'Add to cart')
        self.assertIsNone(alert)
        st, alert, _ = self.ev('stock', {}, st, 'Sold out')
        self.assertIsNone(alert, 'going out of stock is not an alert')

    def test_keyword_appears_and_disappears(self):
        st, _a, _v = self.ev('keyword', {'word': 'tender', 'mode': 'appears'}, {}, 'Nothing yet')
        st, alert, _ = self.ev('keyword', {'word': 'tender', 'mode': 'appears'}, st, 'New TENDER notice published')
        self.assertIn('now appears', alert)
        st, alert, _ = self.ev('keyword', {'word': 'tender', 'mode': 'appears'}, st, 'tender still here')
        self.assertIsNone(alert)
        st, _a, _v = self.ev('keyword', {'word': 'sale', 'mode': 'disappears'}, {}, 'Big sale on')
        st, alert, _ = self.ev('keyword', {'word': 'sale', 'mode': 'disappears'}, st, 'Big sale on')
        self.assertIsNone(alert)
        st, alert, _ = self.ev('keyword', {'word': 'sale', 'mode': 'disappears'}, st, 'Prices are normal')
        self.assertIn('no longer', alert)

    def test_change_detection_threshold_ignore_numbers_and_long_pages(self):
        base_text = ' '.join('word%d' % i for i in range(200)) + ' visitors 1200'
        p = {'min_change': 0.1}
        st, _a, _v = self.ev('change', p, {}, base_text)
        st, alert, _ = self.ev('change', p, st, base_text)
        self.assertIsNone(alert)
        st, alert, _ = self.ev('change', p, st, base_text + ' one extra word')
        self.assertIsNone(alert, 'a one-word change is below 10%')
        st2, alert, _ = self.ev('change', p, st, ' '.join('other%d' % i for i in range(200)))
        self.assertIn('changed', alert)
        q = {'min_change': 0.005, 'ignore_numbers': True}
        st, _a, _v = self.ev('change', q, {}, base_text)
        st, alert, _ = self.ev('change', q, st, base_text.replace('1200', '1350'))
        self.assertIsNone(alert, 'only a number changed and numbers are ignored')
        long_text = ('The quick brown fox jumps over the lazy dog. ' * 1000)       # 45,000 characters
        st, _a, _v = self.ev('change', p, {}, long_text)
        st, alert, _ = self.ev('change', p, st, long_text)
        self.assertIsNone(alert, 'identical long pages must never look changed')

    def test_change_alert_names_what_was_added_and_removed(self):
        st, _a, _v = self.ev('change', {'min_change': 0.05}, {}, 'Alpha line one here today\nBeta line two is here now\nGamma line three stays put')
        st, alert, _ = self.ev('change', {'min_change': 0.05}, st, 'Alpha line one here today\nDelta line four is brand new\nGamma line three stays put')
        self.assertIn('New: Delta line four is brand new', alert)
        self.assertIn('Gone: Beta line two is here now', alert)


class TestWatcherLifecycle(BizCase):
    URL = 'https://shop.example.com/tv'

    def setUp(self):
        super().setUp()
        self.pages = {self.URL: 'Samsung TV\nPrice ₹52,000\nAdd to cart'}
        self.fetches = []

        def fake_fetch(url, *a, **k):
            self.fetches.append(url)
            if url.endswith('/robots.txt'):
                raise ValueError('HTTP 404')
            if self.pages.get(url) is None:
                raise ValueError('HTTP 500')
            return page(self.pages[url])
        for name, val in (('_n85_fetch', fake_fetch), ('_n54_url_guard', lambda u, resolve=False: (u.startswith('https://') and 'localhost' not in u and '127.' not in u, 'host'))):
            q = mock.patch.object(self.m, name, val)
            q.start()
            self.patches.append(q)
        self.m._N85_ROBOTS.clear()
        self.m._N85_HOST_LAST.clear()

    def create(self, **kw):
        payload = {'kind': 'price', 'url': self.URL, 'params': {'target': 49999}}
        payload.update(kw)
        return self.m._n85_watch_create(self.cid, payload)

    def tick(self, now):
        return self.m._n85_watch_tick(now)

    def test_validation_rules(self):
        v = self.m._n85_watch_validate
        ok = v({'kind': 'price', 'url': self.URL, 'params': {'target': '49,999'}, 'every': 60})
        self.assertEqual((ok['kind'], ok['params'], ok['every'], ok['label']), ('price', {'target': 49999.0}, 60, 'shop.example.com'))
        self.assertEqual(v({'kind': 'price', 'url': self.URL})['params'], {'drop': 5.0}, 'default: alert on a 5% drop')
        for bad in ({'kind': 'price', 'url': 'http://127.0.0.1/x'}, {'kind': 'price', 'url': 'ftp://x.example.com/'}, {'kind': 'nope', 'url': self.URL},
                    {'kind': 'price', 'url': self.URL, 'every': 5}, {'kind': 'price', 'url': self.URL, 'every': 99999}, {'kind': 'keyword', 'url': self.URL, 'params': {}},
                    {'kind': 'keyword', 'url': self.URL, 'params': {'word': 'x', 'mode': 'sometimes'}}, {'kind': 'price', 'url': self.URL, 'extra': 1},
                    {'kind': 'price', 'url': self.URL, 'params': {'target': -5}}, {'kind': 'change', 'url': self.URL, 'params': {'min_change': 5}}, 'junk'):
            with self.assertRaises(ValueError, msg=bad):
                v(bad)

    def test_create_reads_the_page_once_and_reports_what_it_saw(self):
        wid, info = self.create()
        self.assertIn('₹52,000', info)
        self.assertIn(self.URL, self.fetches)
        w = self.m._n85_watch_get(self.cid, wid)
        self.assertEqual((w['kind'], w['status'], w['last_value'], w['every']), ('price', 'active', '₹52,000', 120))

    def test_create_fails_loudly_when_the_page_cannot_be_read_or_has_no_price(self):
        self.pages[self.URL] = 'Samsung TV with no price shown'
        with self.assertRaises(ValueError):
            self.create()
        self.pages = {}
        with self.assertRaises(ValueError):
            self.create()

    def test_robots_txt_is_honoured(self):
        def with_robots(url, *a, **k):
            if url.endswith('/robots.txt'):
                return page('User-agent: *\nDisallow: /tv')
            return page(self.pages[url])
        with mock.patch.object(self.m, '_n85_fetch', with_robots):
            with self.assertRaises(ValueError) as cm:
                self.create()
        self.assertIn('robots.txt', str(cm.exception))

    def test_limit_of_fifteen_watchers(self):
        for i in range(15):
            self.pages['https://shop.example.com/p%d' % i] = 'Price ₹%d' % (1000 + i)
            self.create(url='https://shop.example.com/p%d' % i)
        with self.assertRaises(ValueError) as cm:
            self.create()
        self.assertIn('15 watchers', str(cm.exception))

    def test_tick_alerts_once_then_stays_quiet_and_respects_the_cooldown(self):
        wid, _ = self.create()
        t0 = time.time()
        self.pages[self.URL] = 'Samsung TV\nPrice ₹52,000'
        self.assertEqual(self.tick(t0 + 7300), 1)
        self.assertEqual([t for _, t in self.sent if 'Price alert' in t], [])
        self.pages[self.URL] = 'Samsung TV\nPrice ₹49,000'
        self.m._N85_HOST_LAST.clear()
        self.tick(t0 + 14600)
        alerts = [t for _, t in self.sent if 'Price alert' in t]
        self.assertEqual(len(alerts), 1)
        self.assertIn('₹49,000', alerts[0])
        self.assertIn(wid, alerts[0])
        self.pages[self.URL] = 'Samsung TV\nPrice ₹47,000'
        self.m._N85_HOST_LAST.clear()
        self.tick(t0 + 21900)
        self.assertEqual(len([t for _, t in self.sent if 'Price alert' in t]), 1, 'cooldown: 3 hours between alerts for one watcher')
        self.assertEqual(self.m._n85_watch_get(self.cid, wid)['last_value'], '₹47,000', 'but the stored value keeps tracking')

    def test_only_due_active_watchers_are_checked_and_hosts_are_spaced(self):
        w1, _ = self.create()
        self.pages['https://shop.example.com/fan'] = 'Price ₹1,800'
        w2, _ = self.create(url='https://shop.example.com/fan', params={'drop': 5})
        self.pages['https://other.example.org/x'] = 'Price ₹10'
        w3, _ = self.create(url='https://other.example.org/x', params={'drop': 5})
        self.fetches.clear()
        t = time.time() + 7300
        self.assertEqual(self.tick(t), 2, 'two hosts: one fetch each; the second shop.example.com page waits one gap')
        self.assertEqual(self.tick(t + 30), 0, 'the same host is not hit again within the gap')
        self.assertEqual(self.tick(t + 61), 1)
        self.m._n85_watch_set_status(self.cid, w1, 'paused')
        self.m._n85_watch_set_status(self.cid, w2, 'deleted')
        self.assertEqual(self.tick(t + 99999), 1, 'only the active watcher remains')

    def test_failures_back_off_then_pause_with_a_message(self):
        wid, _ = self.create()
        self.pages = {}
        t = time.time()
        due = lambda: self.m._n85_watch_get(self.cid, wid)['next_check']
        gaps = []
        for i in range(5):
            self.m._N85_HOST_LAST.clear()
            self.m._n85_watch_run(self.m._n85_watch_get(self.cid, wid), t)
            w = self.m._n85_watch_get(self.cid, wid)
            gaps.append(round((w['next_check'] - t) / 60))
            t = w['next_check'] + 1
        self.assertEqual(gaps, [240, 480, 960, 960, 960], 'every=120min doubled, capped at 8x')
        self.assertEqual(self.m._n85_watch_get(self.cid, wid)['status'], 'paused')
        self.assertTrue(any('paused after 5 failed checks' in t for _, t in self.sent))
        self.assertIn('Watcher %s is now active' % wid, self.m._n85_watch_set_status(self.cid, wid, 'active'))
        self.assertEqual(self.m._n85_watch_get(self.cid, wid)['fails'], 0)

    def test_robots_change_stops_a_running_watcher_politely(self):
        wid, _ = self.create()
        self.m._N85_ROBOTS.clear()
        with mock.patch.object(self.m, '_n85_robots_ok', lambda url: False):
            res = self.m._n85_watch_run(self.m._n85_watch_get(self.cid, wid), time.time())
        self.assertIn('failed', res)
        self.assertEqual(self.m._n85_watch_get(self.cid, wid)['fails'], 1)

    def test_commands_list_history_check_pause_and_delete(self):
        with mock.patch.object(self.m, '_n66_submit', lambda cid, kind, req, fn, *a, **k: fn(*a, **k) and 'T1' or 'T1'):
            out = self.m._n85_cmd_watch(self.cid, 'add url=%s kind=price target=49999 label="Samsung 55"' % self.URL)
        wid = self.m._n85_watch_list_text(self.cid).split('• ')[1].split(' ')[0]
        listing = self.m._n85_cmd_watch(self.cid, 'list')
        self.assertIn('Samsung 55', listing)
        self.assertIn('₹52,000', listing)
        self.assertIn('₹52,000', self.m._n85_cmd_watch(self.cid, 'history ' + wid))
        self.pages[self.URL] = 'Price ₹51,000'
        self.assertIn('Checked %s: ok' % wid, self.m._n85_cmd_watch(self.cid, 'check ' + wid.lower()))
        self.assertIn('paused', self.m._n85_cmd_watch(self.cid, 'pause ' + wid))
        self.assertIn('removed', self.m._n85_cmd_watch(self.cid, 'del ' + wid))
        self.assertIn('No watchers yet', self.m._n85_cmd_watch(self.cid, 'list'))
        with self.assertRaises(ValueError):
            self.m._n85_cmd_watch(self.cid, 'check W-NOPE00')
        with self.assertRaises(ValueError):
            self.m._n85_cmd_watch(self.cid, 'add url=http://127.0.0.1/x kind=price')
        with self.assertRaises(ValueError):
            self.m._n85_cmd_watch(self.cid, 'add kind=price')

    def test_watch_card_from_chat_creates_only_after_approval_and_undo_removes_it(self):
        reply = {'kind': 'price', 'params': {'target': 49999}, 'label': 'Samsung 55 TV'}
        self.fake.when(lambda r, t: 'page-watcher spec' in t, lambda r, t, msgs: json.dumps(reply))
        res = self.m._n85_nl_task(self.cid, 'watch', 'watch ' + self.URL + ' and tell me when it drops below 49999')
        self.assertEqual(res['text'], '')
        self.assertEqual(self.m._n85_watch_list_text(self.cid).split('\n')[0], 'No watchers yet. Example: /watch85 add url=https://shop.example/tv kind=price target=49999')
        item = self.m._n85_pending(self.cid)[0]
        self.assertEqual(item['payload']['url'], self.URL, 'the URL comes from the owner text, never from the model')
        prompt = next(c for c in self.fake.calls if 'page-watcher spec' in c['text'])['text']
        self.assertNotIn(self.URL, prompt, 'the model is not even shown the URL')
        self.cb(item['id'], 'y')
        self.assertEqual(len(self.m._n85_watch_list_text(self.cid).split('\n')) - 2, 1)
        self.cb(item['id'], 'u')
        self.assertIn('No watchers yet', self.m._n85_watch_list_text(self.cid))

    def test_model_cannot_swap_the_url_and_two_links_are_refused(self):
        reply = {'kind': 'price', 'params': {'target': 100}, 'url': 'https://evil.example.com/'}
        self.fake.when(lambda r, t: 'page-watcher spec' in t, lambda r, t, msgs: json.dumps(reply))
        self.m._n85_nl_task(self.cid, 'watch', 'watch ' + self.URL + ' below 100')
        self.assertEqual(self.m._n85_pending(self.cid)[0]['payload']['url'], self.URL)
        res = self.m._n85_nl_task(self.cid, 'watch', 'watch https://a.example.com/x and https://b.example.com/y')
        self.assertIn('exactly one page link', res['text'])
        res = self.m._n85_nl_task(self.cid, 'watch', 'watch the price of that TV')
        self.assertIn('exactly one page link', res['text'])


class TestSharedLoop(BizCase):
    def test_tick_runs_watchers_expiry_and_brief_and_respects_the_switches(self):
        calls = []
        with mock.patch.object(self.m, '_n85_watch_tick', lambda *a, **k: calls.append('watch')), mock.patch.object(self.m, '_n85_brief_tick', lambda cid: calls.append('brief')), \
                mock.patch.object(self.m, '_n85_expire_old', lambda *a: calls.append('expire')):
            self.m._n85_tick()
            self.assertEqual(calls, ['expire', 'watch', 'brief'])
            calls.clear()
            self.m._n83_set_flag(self.cid, 'watchers', False)
            self.m._n85_tick()
            self.assertEqual(calls, ['expire', 'brief'])

    def test_loop_survives_an_exception_in_a_tick(self):
        import threading
        n = {'c': 0}

        def boom():
            n['c'] += 1
            if n['c'] == 1:
                raise RuntimeError('boom')
            raise KeyboardInterrupt
        sleeps = []
        with mock.patch.object(self.m, '_n85_tick', boom), mock.patch.object(self.m._n85_time, 'sleep', lambda s: sleeps.append(s)):
            with self.assertRaises(KeyboardInterrupt):
                self.m._n85_loop()
        self.assertEqual((n['c'], sleeps), (2, [30]))
        self.assertEqual(self.m._N85_STATS['errors'], 1)

    def test_ensure_loop_starts_one_daemon_thread_only(self):
        started = []

        class T:
            def __init__(self, target=None, daemon=None, name=None):
                started.append((target, daemon, name))
                self.alive = False

            def start(self):
                self.alive = True

            def is_alive(self):
                return self.alive
        self.m._N85_LOOP['thread'] = None
        with mock.patch.object(self.m._n85_threading, 'Thread', T):
            self.m._n85_ensure_loop()
            self.m._n85_ensure_loop()
        self.m._N85_LOOP['thread'] = None
        self.assertEqual(len(started), 1)
        self.assertTrue(started[0][1])
