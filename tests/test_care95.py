"""Nemo v95 Care: fix-it lines for older failure messages, the care report, safe clean-up, the daily housekeeping step, the Fyers shortcut, and the structure of the whole v95 layer.

Offline. Files are real (in a temporary folder); the server's memory and disk are scripted; no network, no broker, no order.

    NEMO_FILE=/path/to/nemotron_bot.py python -m unittest tests.test_care95 -v
"""
import ast
import datetime as dt
import json
import os
import re
import time
import unittest
from unittest import mock

from tests import test_cortex83 as base
from tests.test_scout93 import ScoutCase
from tests.test_forge91 import OWNER_ID

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
GB = 1073741824


def setUpModule():
    if base.m is None:
        base.setUpModule()


def v95_source():
    src = open(base.NEMO_FILE, encoding='utf-8').read()
    i = src.index('# NEMO 95 - DOORS')
    j = src.index('# NEMO 96 - LEDGER') if '# NEMO 96 - LEDGER' in src else src.rindex("if __name__")       # (the next layer is not part of this one)
    return src[i:j]


def ist(y, mo, d, h, mi=0):
    return dt.datetime(y, mo, d, h, mi, tzinfo=IST).timestamp()


class CareCase(ScoutCase):
    def setUp(self):
        super().setUp()
        m = self.m
        self.work = m._n92_dir()
        os.makedirs(self.work, exist_ok=True)
        self.scratch = os.path.join(self.tmp.name, 'scratch')
        os.makedirs(self.scratch, exist_ok=True)
        self.start(m, '_n95_tempdir', lambda: self.scratch)
        for k in m._N95_STATS:
            m._N95_STATS[k] = 0
        for key in ('care_auto', 'care_alerts', 'last_run', 'disk_alert'):
            m._n95_q('DELETE FROM office95_setting WHERE key=?', (key,), write=True)
        self.free = 40 * GB
        self.start(m, '_n91_free_bytes', lambda path: self.free)
        self.start(m._n91_shutil, 'disk_usage', lambda path: mock.Mock(total=77 * GB, free=self.free, used=77 * GB - self.free))
        self.mem = {'MemAvailable': int(2.1 * GB)}
        self.psi = {'some': 0.4}
        self.start(m, '_n91_meminfo', lambda: dict(self.mem))
        self.start(m, '_n91_psi', lambda: dict(self.psi))
        self.start(m, 'fyers_ready', lambda: True)
        self.guest = lambda text, **k: dict({'chat': {'id': 5552, 'type': 'private'}, 'from': {'id': 5552, 'first_name': 'Asha'}, 'message_id': 3, 'text': text}, **k)
        self.owner_msgs = []
        self.start(m, 'send_text', lambda cid, text, kb=None: self.sent.append((cid, text)))

    def job(self, name, age_s, size=1000, ref=None):
        p = os.path.join(self.work, name)
        os.makedirs(p, exist_ok=True)
        open(os.path.join(p, 'f.bin'), 'wb').write(b'x' * size)
        t = (ref if ref is not None else time.time()) - age_s
        os.utime(p, (t, t))
        return p

    def scratch_file(self, name, age_s, size=500):
        p = os.path.join(self.scratch, name)
        open(p, 'wb').write(b'y' * size)
        t = time.time() - age_s
        os.utime(p, (t, t))
        return p

    def insert_backup(self, ago_s=7200, status='OK', remote='OK', remote_cfg='gdrive-crypt:nemo', daily='1'):
        m = self.m
        m._n68_init()
        c = m._n68_conn()
        c.execute('INSERT INTO backup68(id,ts,mode,local_path,bytes,sha256,remote,remote_status,status,detail) VALUES(?,?,?,?,?,?,?,?,?,?)', ('B1', time.time() - ago_s, 'memory', '/x', 5 << 20, 'sha', remote_cfg, remote, status, ''))
        c.commit()
        c.close()
        m._n68_setcfg('backup_remote', remote_cfg)
        m._n68_setcfg('backup_daily', daily)


# ===================================================================================================================
# 1. A FIX-IT LINE ON THE FAILURES OLDER FUNCTIONS REPORT
# ===================================================================================================================
class TestFixItLines(CareCase):
    @classmethod
    def setUpClass(cls):
        cls.src = open(base.NEMO_FILE, encoding='utf-8').read()

    def test_every_phrase_a_rule_waits_for_really_exists_in_the_bots_own_messages(self):
        for phrase in ('Fyers market-data request failed', 'Fyers returned no usable market data', 'Connect Fyers first', 'Broker not logged in', 'FYERS is not connected', 'No module named', 'No space left on device'):
            self.assertIn(phrase, self.src, phrase)

    def test_the_trade_lab_message_from_the_owners_own_screen(self):
        t = self.m._n95_hint('Trade Lab stopped: Fyers market-data request failed; check broker login. No real broker order was sent.')
        self.assertTrue(t.startswith('Trade Lab stopped: Fyers market-data request failed; check broker login. No real broker order was sent.'))
        self.assertIn('🛠 Fix: Fyers is not logged in today. Say “fyers login”', t)
        self.assertIn('/brokerurl', t)
        self.assertIn('8:20 AM', t)
        self.assertEqual(self.m._N95_STATS['hints'], 1)

    def test_the_other_fyers_wordings(self):
        for msg in ('Connect Fyers first; a market-data session is required', 'Fyers returned no usable market data; check login and symbol', 'Broker not logged in: Fyers credentials incomplete', 'FYERS is not connected; the chain needs it'):
            self.assertIn('🛠 Fix: Fyers is not logged in today', self.m._n95_hint(msg), msg)

    def test_a_message_that_already_says_how_to_fix_it_is_left_alone(self):
        for msg in ('Broker not logged in: run /brokerurl once', 'Fyers market-data request failed. Say “fyers login”', 'Not connected to Fyers; send /brokerlogin', self.m._n94_why('fyers is not connected')):
            self.assertEqual(self.m._n95_hint(msg), msg)

    def test_a_missing_package_says_what_to_install_using_the_right_pip_name(self):
        self.assertIn('Say “install pyotp into yourself”', self.m._n95_hint("ModuleNotFoundError: No module named 'pyotp'"))
        self.assertIn('install pandas-ta-classic into yourself', self.m._n95_hint("No module named 'pandas_ta_classic'"))
        self.assertIn('install pillow into yourself', self.m._n95_hint("No module named 'PIL'"))
        self.assertIn('install some-thing into yourself', self.m._n95_hint("No module named 'some_thing'"))
        msg = 'rembg is not installed in me yet. Say “install rembg into yourself”. No module named \'rembg\''
        self.assertEqual(self.m._n95_hint(msg), msg)

    def test_a_full_disk_points_at_care(self):
        t = self.m._n95_hint('Download failed: OSError: [Errno 28] No space left on device')
        self.assertIn('Say “care”', t)
        self.assertIn('“care clean”', t)

    def test_ordinary_messages_and_odd_inputs_are_returned_unchanged(self):
        for msg in ('hello', 'Your balance is ₹1,23,456', '', None, 0, 'x' * 7000, 'No module named \'x\'' + ' pad' * 600):
            out = self.m._n95_hint(msg)
            self.assertEqual(out, msg if isinstance(msg, str) else (msg or ''), str(msg)[:20])
        self.assertEqual(self.m._N95_STATS['hints'], 0)

    def test_only_the_start_of_a_message_counts(self):
        t = 'Here is a long answer. ' * 40 + 'Fyers market-data request failed'
        self.assertEqual(self.m._n95_hint(t), t)

    def test_a_json_dump_that_mentions_a_failure_becomes_words_first_and_then_gets_the_line(self):
        dump = json.dumps({'ok': False, 'symbol': 'NIFTY', 'error': 'FYERS is not connected; structured live option chain requires the existing authenticated market-data connection', 'detail': {'a': 1, 'b': 2}}, indent=2)
        t = self.m._n95_hint(dump)
        self.assertNotIn('{', t)
        self.assertIn('Symbol: NIFTY', t)
        self.assertTrue(t.rstrip().endswith('Nemo also logs in by himself at 8:20 AM on trading days.'))

    def test_with_plain_words_off_a_json_dump_is_not_touched(self):
        self.m._n94_put('plain', 'off')
        dump = json.dumps({'ok': False, 'error': 'FYERS is not connected', 'detail': {'a': 1, 'b': 2}}, indent=2)
        self.assertIn('"ok": false', self.m._n95_hint(dump))
        self.m._n94_put('plain', 'on')

    def test_the_wrapper_sends_the_line_and_passes_the_buttons_on(self):
        out = []
        send = self.rebuild_wrapper()
        self.start(self.m, '_N95_SEND_PREV', lambda cid, text, kb=None: out.append((cid, text, kb)))
        send(OWNER_ID, 'Connect Fyers first; a market-data session is required')
        send(OWNER_ID, 'Pick one', {'inline_keyboard': []})
        send(OWNER_ID, 'plain text')
        self.assertIn('🛠 Fix: Fyers', out[0][1])
        self.assertIsNone(out[0][2])
        self.assertEqual(out[1], (OWNER_ID, 'Pick one', {'inline_keyboard': []}))
        self.assertEqual(out[2][1], 'plain text')

    def test_a_failure_in_the_hint_never_stops_a_message(self):
        out = []
        send = self.rebuild_wrapper()
        self.start(self.m, '_N95_SEND_PREV', lambda cid, text, kb=None: out.append(text))
        self.start(self.m, '_n95_hint', lambda t: (_ for _ in ()).throw(RuntimeError('x')))
        send(OWNER_ID, 'Connect Fyers first')
        self.assertEqual(out, ['Connect Fyers first'])
        self.assertEqual(self.m._N95_STATS['errors'], 1)

    def rebuild_wrapper(self):
        """The v95 send_text rebuilt from its own source (the live name may be a recorder in these tests)."""
        fn = next(n for n in ast.parse(v95_source()).body if isinstance(n, ast.FunctionDef) and n.name == 'send_text')
        ns = {}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<v95 send_text>', 'exec'), self.m.__dict__, ns)
        return ns['send_text']


# ===================================================================================================================
# 2. THE CARE REPORT
# ===================================================================================================================
class TestCareReport(CareCase):
    def test_a_healthy_server_reads_healthy(self):
        self.insert_backup()
        out = self.say('care')
        for part in ('NEMO CARE', '✅ Disk: 40.0 GB free of 77.0 GB (52%)', '✅ Memory: 2.1 GB available · not swapping now', '✅ Nemo’s database: quick check ok', '✅ Leftover job folders: none',
                     '✅ Old scratch files: none', '✅ Backups: last one 2 h ago · OK · daily on', '✅ Fyers: logged in today', 'Housekeeping: automatic, about 03:30 every day'):
            self.assertIn(part, out)
        self.assertNotIn('⚠️ Disk', out)
        self.assertEqual(self.m._N95_STATS['care_runs'], 1)

    def test_natural_ways_of_asking(self):
        for q in ('care', 'nemo care', 'server care', 'housekeeping', 'health care', '/care', 'care status'):
            self.assertIn('NEMO CARE', self.say(q), q)

    def test_low_disk_is_a_warning_with_the_next_step(self):
        self.free = int(1.5 * GB)
        out = self.say('care')
        self.assertIn('⚠️ Disk: 1.5 GB free of 77.0 GB (2%) · running low: say “care clean”, then “server status”', out)
        self.free = 5 * GB
        self.assertIn('⚠️ Disk', self.say('care'), 'under 10 percent of the disk')

    def test_memory_pressure_is_said(self):
        self.psi = {'some': 35.0}
        self.assertIn('⚠️ Memory: 2.1 GB available · programs are waiting for memory right now', self.say('care'))

    def test_leftover_job_folders_and_old_scratch_files_are_counted(self):
        self.job('J92-old1', 4000, 2_000_000)
        self.job('J92-new1', 10)
        self.scratch_file('nemo_old.png', 5 * 86400, 3_000_000)
        self.scratch_file('nemo_new.png', 60)
        out = self.say('care')
        self.assertIn('⚠️ Leftover job folders: 1 older than 30 minutes (2 MB): say “care clean”', out)
        self.assertIn('⚠️ Old scratch files: 1 older than 3 days (3 MB): say “care clean”', out)

    def test_a_database_that_cannot_be_checked_is_a_warning_not_a_crash(self):
        self.start(self.m, '_n35_conn', lambda: (_ for _ in ()).throw(OSError('disk I/O error')))
        out = self.m._n95_care_report()
        self.assertIn('⚠️ Nemo’s database: could not be checked (OSError)', out)

    def test_a_database_that_says_it_is_damaged_is_a_warning(self):
        class Cur:
            def fetchone(self):
                return ('*** in database main *** Page 5: btree error',)

        class Conn:
            def execute(self, sql, *a):
                return Cur()

            def close(self):
                pass
        self.start(self.m, '_n35_conn', lambda: Conn())
        self.assertIn('⚠️ Nemo’s database: quick check says: *** in database main', self.m._n95_care_report())

    def test_the_log_file_is_mentioned_only_when_it_is_big(self):
        self.start(self.m, '_n95_db_health', lambda: (True, 'quick check ok', 3 * 1048576, 60 * 1048576))
        self.assertIn('✅ Nemo’s database: quick check ok · 3 MB (+60 MB log)', self.m._n95_care_report())
        self.start(self.m, '_n95_db_health', lambda: (True, 'quick check ok', 3 * 1048576, 2 * 1048576))
        self.assertNotIn('(+2 MB log)', self.m._n95_care_report())

    def test_backups_every_state(self):
        m = self.m
        lvl, words = m._n95_backup_health()
        self.assertEqual(lvl, 'warn')
        self.assertIn('no backup has been made yet', words)
        self.insert_backup(remote_cfg='')
        m._n68_setcfg('backup_remote', '')
        lvl, words = m._n95_backup_health()
        self.assertEqual(lvl, 'warn')
        self.assertIn('no off-site copy', words)
        m._n68_setcfg('backup_remote', 'gdrive-crypt:nemo')
        c = m._n68_conn()
        c.execute("UPDATE backup68 SET remote_status='FAILED: timeout', remote='gdrive-crypt:nemo'")
        c.commit()
        c.close()
        self.assertIn('off-site copy: FAILED: timeout', m._n95_backup_health()[1])
        c = m._n68_conn()
        c.execute("UPDATE backup68 SET remote_status='OK', ts=?", (time.time() - 4 * 86400,))
        c.commit()
        c.close()
        lvl, words = m._n95_backup_health()
        self.assertEqual(lvl, 'warn')
        self.assertIn('older than 3 days', words)

    def test_the_broker_login_and_the_website_door_appear(self):
        self.start(self.m, 'fyers_ready', lambda: False)
        out = self.m._n95_care_report()
        self.assertIn('⚠️ Fyers: not logged in: say “fyers login”', out)
        self.assertIn('⚠️ Website:', out)
        self.assertIn('say “doors”', out)

    def test_the_report_fits_a_message(self):
        for i in range(60):
            self.job('J92-%03d' % i, 4000)
        self.assertLessEqual(len(self.m._n95_care_report()), 3900)

    def test_a_guest_gets_none_of_it(self):
        for q in ('care', 'care clean', 'housekeeping'):
            n = len(self.passed)
            self.m.handle(self.guest(q))
            self.assertEqual(len(self.passed), n + 1, q)
        self.assertEqual([t for c, t in self.sent if c == 5552], [])


# ===================================================================================================================
# 3. CLEANING: ONLY NEMO'S OWN LEFTOVERS
# ===================================================================================================================
class TestClean(CareCase):
    def test_old_job_folders_go_and_young_ones_stay(self):
        old, young = self.job('J92-old', 4000), self.job('J92-young', 60)
        res = self.m._n95_clean()
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(young))
        self.assertEqual(res['jobs'], 1)

    def test_only_folders_with_the_helper_prefix_are_ever_touched(self):
        keep = [self.job('studio-keep', 99999), self.job('J91-other', 99999), self.job('mine', 99999)]
        open(os.path.join(self.work, 'J92-afile'), 'wb').write(b'x')
        t = time.time() - 99999
        os.utime(os.path.join(self.work, 'J92-afile'), (t, t))
        self.m._n95_clean()
        for p in keep:
            self.assertTrue(os.path.exists(p), p)
        self.assertTrue(os.path.exists(os.path.join(self.work, 'J92-afile')), 'a plain file with that name is not a job folder')

    def test_a_link_is_never_followed_or_removed(self):
        target = os.path.join(self.tmp.name, 'precious')
        os.makedirs(target)
        open(os.path.join(target, 'data'), 'w').write('keep me')
        link = os.path.join(self.work, 'J92-link')
        os.symlink(target, link)
        t = time.time() - 99999
        os.utime(link, (t, t), follow_symlinks=False)
        self.m._n95_clean()
        self.assertTrue(os.path.islink(link))
        self.assertEqual(open(os.path.join(target, 'data')).read(), 'keep me')
        lnk = os.path.join(self.scratch, 'nemo_link.png')
        os.symlink(os.path.join(target, 'data'), lnk)
        self.m._n95_clean()
        self.assertTrue(os.path.islink(lnk))

    def test_scratch_files_need_the_exact_name_pattern_and_age(self):
        gone = [self.scratch_file('nemo_browser.png', 4 * 86400), self.scratch_file('nemo_invoice85_17.pdf', 4 * 86400), self.scratch_file('nemo_a-b_c.1.mp3', 9 * 86400)]
        kept = [self.scratch_file('nemo_new.png', 3600), self.scratch_file('other.png', 9 * 86400), self.scratch_file('nemo_state.json', 9 * 86400), self.scratch_file('nemo_.png', 9 * 86400),
                self.scratch_file('xnemo_a.png', 9 * 86400), self.scratch_file('nemo_a.png.exe', 9 * 86400)]
        os.makedirs(os.path.join(self.scratch, 'nemo_dir.png'))
        res = self.m._n95_clean()
        for p in gone:
            self.assertFalse(os.path.exists(p), p)
        for p in kept:
            self.assertTrue(os.path.exists(p), p)
        self.assertTrue(os.path.isdir(os.path.join(self.scratch, 'nemo_dir.png')))
        self.assertEqual(res['files'], 3)

    def test_the_command_reports_what_it_did_and_the_bytes(self):
        self.job('J92-a', 4000, 2 * 1048576)
        self.scratch_file('nemo_x.png', 5 * 86400, 1048576)
        out = self.say('care clean')
        self.assertIn('removed 1 leftover job folder(s) and 1 old scratch file(s) (3 MB freed)', out)
        self.assertIn('compacted my database log', out)
        self.assertIn('Only my own temporary files were touched', out)
        self.assertIn('removed 1 job folder(s) and 1 file(s)', self.m._n95_get('last_run', '', 'office95_setting'))

    def test_the_automatic_cleaning_leaves_the_scratch_files_alone(self):
        f = self.scratch_file('nemo_x.png', 5 * 86400)
        j = self.job('J92-a', 4000)
        self.m._n95_clean(include_temp=False)
        self.assertTrue(os.path.exists(f))
        self.assertFalse(os.path.exists(j))

    def test_nothing_to_clean_is_fine(self):
        self.assertIn('removed 0 leftover job folder(s) and 0 old scratch file(s)', self.say('care clean'))

    def test_a_missing_work_area_is_fine(self):
        import shutil
        shutil.rmtree(self.work, ignore_errors=True)
        self.assertEqual(self.m._n95_leftover_jobs(), [])
        self.assertEqual(self.m._n95_clean()['jobs'], 0)

    def test_the_switches(self):
        self.assertIn('Automatic housekeeping is OFF', self.say('care auto off'))
        self.assertIn('automatic cleaning is OFF', self.say('care'))
        self.assertIn('Automatic housekeeping is ON', self.say('care auto on'))
        self.assertIn('Low-disk alerts are OFF', self.say('care alerts off'))


# ===================================================================================================================
# 4. THE QUIET DAILY STEP
# ===================================================================================================================
class TestHousekeepingTick(CareCase):
    def test_it_cleans_once_a_day_after_half_past_three(self):
        j = self.job('J92-a', 4000, ref=ist(2026, 10, 5, 3, 31))
        self.assertEqual(self.m._n95_care_tick(ist(2026, 10, 5, 3, 29)), [])
        self.assertTrue(os.path.exists(j))
        self.assertEqual(self.m._n95_care_tick(ist(2026, 10, 5, 3, 31)), ['clean'])
        self.assertFalse(os.path.exists(j))
        j2 = self.job('J92-b', 4000, ref=ist(2026, 10, 5, 12, 0))
        self.assertEqual(self.m._n95_care_tick(ist(2026, 10, 5, 12, 0)), [], 'not twice in a day')
        self.assertTrue(os.path.exists(j2))
        self.assertEqual(self.m._n95_care_tick(ist(2026, 10, 6, 3, 40)), ['clean'])

    def test_a_big_clean_up_is_reported_a_small_one_is_silent(self):
        self.job('J92-a', 4000, 60 * 1048576, ref=ist(2026, 10, 5, 4, 0))
        self.m._n95_care_tick(ist(2026, 10, 5, 4, 0))
        self.assertTrue(any('removed 1 leftover job folder(s)' in t and 'freed' in t for c, t in self.sent if c == OWNER_ID), self.sent)
        self.sent.clear()
        self.m._n95_q('DELETE FROM office95_setting WHERE key=?', ('last_run',), write=True)
        self.job('J92-b', 4000, 1000, ref=ist(2026, 10, 7, 4, 0))
        self.m._n95_care_tick(ist(2026, 10, 7, 4, 0))
        self.assertEqual(self.sent, [])

    def test_switched_off_it_cleans_nothing(self):
        self.m._n95_put('care_auto', 'off', 'office95_setting')
        j = self.job('J92-a', 4000, ref=ist(2026, 10, 5, 4, 0))
        self.assertEqual(self.m._n95_care_tick(ist(2026, 10, 5, 4, 0)), [])
        self.assertTrue(os.path.exists(j))

    def test_a_low_disk_alert_goes_out_once_a_day(self):
        self.free = int(1.2 * GB)
        self.m._n95_put('care_auto', 'off', 'office95_setting')
        t = ist(2026, 10, 5, 1, 0)
        self.assertEqual(self.m._n95_care_tick(t), ['alert'])
        alerts = [x for c, x in self.sent if c == OWNER_ID and 'running low' in x]
        self.assertEqual(len(alerts), 1)
        self.assertIn('1.2 GB free', alerts[0])
        self.assertEqual(self.m._n95_care_tick(t + 3600), [])
        self.assertEqual(self.m._n95_care_tick(t + 21 * 3600), ['alert'])

    def test_no_alert_when_the_disk_is_fine_or_alerts_are_off(self):
        self.assertEqual(self.m._n95_care_tick(ist(2026, 10, 5, 1, 0)), [])
        self.free = int(1.2 * GB)
        self.m._n95_put('care_alerts', 'off', 'office95_setting')
        self.assertEqual(self.m._n95_care_tick(ist(2026, 10, 5, 1, 0)), [])
        self.assertEqual([x for c, x in self.sent if 'running low' in x], [])

    def test_the_loop_is_started_once_by_main_and_an_error_never_stops_the_bot(self):
        calls = []
        self.start(self.m, '_N95_MAIN_PREV', lambda *a, **k: calls.append('main') or 'ok')
        self.start(self.m, '_n95_ensure_thread', lambda: calls.append('thread'))
        self.assertEqual(self.m.main(), 'ok')
        self.assertEqual(calls, ['thread', 'main'])
        self.start(self.m, '_n95_ensure_thread', lambda: (_ for _ in ()).throw(RuntimeError('x')))
        self.assertEqual(self.m.main(), 'ok')
        self.assertEqual(self.m._N95_STATS['errors'], 1)

    def test_a_failing_tick_is_counted_not_raised_by_the_loop(self):
        self.start(self.m, '_n95_care_tick', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('x')))
        n = []

        def fake_sleep(s):
            n.append(s)
            raise SystemExit
        self.start(self.m._n91_time, 'sleep', fake_sleep)
        with self.assertRaises(SystemExit):
            self.m._n95_care_loop()
        self.assertEqual(n, [1800])
        self.assertEqual(self.m._N95_STATS['errors'], 1)


# ===================================================================================================================
# 5. THE FYERS SHORTCUT
# ===================================================================================================================
class TestFyersShortcut(CareCase):
    def setUp(self):
        super().setUp()
        self.down = []
        self.start(self.m, '_N95_HANDLE_PREV', lambda msg: self.down.append(msg['text']))

    def test_natural_ways_of_asking_for_the_login(self):
        for q in ('fyers login', 'Fyers login', 'broker login', 'login to fyers', 'log in to fyers', 'connect fyers', 'connect to fyers', '/fyers login'):
            self.down.clear()
            out = self.say(q)
            self.assertEqual(self.down, ['/brokerlogin'], q)
            self.assertIn('Trying the Fyers login now', out, q)

    def test_the_status(self):
        for q in ('fyers status', 'broker status'):
            self.down.clear()
            self.say(q)
            self.assertEqual(self.down, ['/broker'], q)

    def test_a_guest_cannot_trigger_a_login(self):
        self.down.clear()
        self.m.handle(self.guest('fyers login'))
        self.assertEqual(self.down, ['fyers login'], 'a guest message goes down the ordinary chain untouched')
        self.assertNotIn('/brokerlogin', self.down)
        self.assertEqual(self.broker_calls, [])

    def test_it_only_forwards_the_existing_owner_commands(self):
        src = v95_source()
        self.assertIn("dict(msg, text='/brokerlogin')", src)
        self.assertNotIn('fyers_login(', src)


# ===================================================================================================================
# 6. STRUCTURE: the whole v95 layer can never place an order, touch the guards, or hand out a secret
# ===================================================================================================================
class TestStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if base.m is None:
            base.setUpModule()
        cls.src = v95_source()
        cls.tree = ast.parse(cls.src)
        cls.m = base.m

    def names(self):
        out = set()
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Name):
                out.add(n.id)
            elif isinstance(n, ast.Attribute):
                out.add(n.attr)
        return out

    def calls(self):
        out = []
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Call):
                f = n.func
                parts = []
                while isinstance(f, ast.Attribute):
                    parts.append(f.attr)
                    f = f.value
                if isinstance(f, ast.Name):
                    parts.append(f.id)
                out.append('.'.join(reversed(parts)))
        return out

    def test_no_order_function_trading_agent_or_guard_is_named(self):
        used = self.names()
        for bad in ('fyers_place', 'fyers_place_bracket', '_order_send', 'request_order', 'place_order', 'auto_trade_tick', 'ai_decide', 'godmode_analyze', 'TradeLab75', 'BROKER', 'can_enter', 'must_square_off',
                    'mm_locked', '_n81_paused', '_n81_entry_quote', '_n75_quote', 'live_ltp', 'fyers_ltp', 'fyers_data', 'fyers_login', 'AUTO', 'AUTOLOG', 'NVIDIA_KEY', '_n90_secret', '_N81_HOLIDAYS_2026', '_n81_session'):
            self.assertNotIn(bad, used, bad)

    def test_the_broker_login_is_only_ever_read_never_driven_from_the_layer(self):
        self.assertEqual(sorted(set(c for c in self.calls() if c.split('.')[-1].lower().startswith('fyers'))), ['fyers_ready'])

    def test_the_telegram_token_is_only_used_to_check_a_signature(self):
        hits = [n for n in ast.walk(self.tree) if isinstance(n, ast.Constant) and n.value == 'TELEGRAM_TOKEN']
        self.assertEqual(len(hits), 1)
        i = self.src.index("globals().get('TELEGRAM_TOKEN')")
        self.assertIn('_n95_verify_initdata(', self.src[i - 200:i + 60])
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ('send_text', '_n91_say'):
                self.assertNotIn('TELEGRAM_TOKEN', ast.unparse(n))

    def test_no_program_is_started_and_nothing_is_evaluated(self):
        calls = self.calls()
        for bad in ('_n91_run', '_n91_sp.run', '_n91_sp.Popen', 'subprocess.run', 'subprocess.Popen', 'os.system', '_n91_os.system', '_n91_os.popen', 'eval', 'exec', 'compile', '__import__'):
            self.assertNotIn(bad, calls, bad)
        self.assertEqual([c for c in calls if c.startswith('requests.')], [])

    def test_files_are_removed_in_exactly_one_place_and_never_by_a_glob(self):
        for n in ast.walk(self.tree):
            if isinstance(n, ast.FunctionDef):
                inner = [ast.unparse(c.func) for c in ast.walk(n) if isinstance(c, ast.Call)]
                has = [c for c in inner if c.endswith('.remove') or c.endswith('rmtree') or c.endswith('.unlink')]
                if has:
                    self.assertEqual(n.name, '_n95_remove_path', n.name)
        self.assertIsNone(re.search(r'\bglob\b', self.src))

    def test_the_layer_only_sends_to_the_owner_or_the_callers_own_chat(self):
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ('send_text', '_n91_say', '_N95_SEND_PREV'):
                first = ast.unparse(n.args[0]) if n.args else ''
                self.assertIn(first, ('cid', "OWNER['id']", 'chat_id'), first)

    def test_all_layer_names_use_the_v95_prefix(self):
        defined = {n.name for n in self.tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        odd = [d for d in defined if not (d.startswith('_n95_') or d.startswith('_N95')) and d not in ('handle', '_n82_capabilities', '_n83_status_text', '_n88_abilities', 'prime_regression_suite', 'main', 'send_text',
                                                                                                     'build_web_app', '_n85_invoice_text')]
        self.assertEqual(odd, [])

    def test_every_replaced_function_keeps_the_old_one(self):
        for fn, prev in (('handle', '_N95_HANDLE_PREV'), ('send_text', '_N95_SEND_PREV'), ('build_web_app', '_N95_BUILD_PREV'), ('_n83_status_text', '_N95_STATUS_PREV'), ('_n82_capabilities', '_N95_CAPS_PREV'),
                         ('_n88_abilities', '_N95_ABIL_PREV'), ('prime_regression_suite', '_N95_REG_PREV'), ('main', '_N95_MAIN_PREV'), ('_n85_invoice_text', '_N95_INV_TEXT_PREV')):
            self.assertIn('%s = %s\n' % (prev, fn), self.src, fn)

    def test_the_regression_rows_pass_and_join_the_suite(self):
        rows = self.m._n95_regression_rows()
        self.assertEqual(len(rows), 9)
        self.assertEqual([r['name'] for r in rows if not r['ok']], [])
        self.assertTrue(all(r['name'].startswith('v95-') for r in rows))
        self.assertIsNot(self.m.prime_regression_suite, self.m._N95_REG_PREV)

    def test_capabilities_status_abilities_and_commands(self):
        caps = self.m._n82_capabilities()
        for part in ('Doors 95:', 'Care 95:', 'Office 95:', '“doors”', '“care clean”', '“fyers login”', '“quiz me”', '“gstin check <number>”'):
            self.assertIn(part, caps)
        self.assertIn('DOORS/CARE/OFFICE 95: refused-request blocks 0', self.m._n83_status_text(OWNER_ID))
        names = {r[1] for r in self.m._n88_abilities(OWNER_ID)}
        for n in ('Website doors', 'Care and housekeeping', 'GSTIN and PAN checks', 'Study helper'):
            self.assertIn(n, names)
        cmds = [c[0] for c in self.m._N40_COMMANDS]
        for c in ('doors', 'care', 'quiz'):
            self.assertIn(c, cmds)


class AbilitiesReportFits(CareCase):
    """The "what can you do" report had a hard cut at 3900 characters; with the v93-v95 rows it lost its last lines ("To fix" and the safety line). It now shortens rows instead."""

    def full_lines(self, rows):
        lines, group = ['🧭 WHAT NEMO CAN SEE AND DO RIGHT NOW (live check)'], ''
        for g, name, status, detail, example in rows:
            if g != group:
                group = g
                lines.append('— %s —' % g)
            lines.append('%s %s: %s\n    e.g. %s' % (self.m._N88_ICON.get(status, '•'), name, detail, example))
        return lines

    def test_fit_leaves_a_short_report_alone(self):
        lines = ['head', '✅ A: fine\n    e.g. “a”', '✅ B: fine\n    e.g. “b”']
        self.assertEqual(self.m._n95_fit_report(lines, 3000), '\n'.join(lines))

    def test_fit_shortens_details_then_examples_from_the_end_and_never_the_start(self):
        lines = ['head'] + ['✅ Row %d: %s\n    e.g. “say %d”' % (i, 'detail ' * 8, i) for i in range(12)]
        self.assertGreater(len('\n'.join(lines)), 1000)
        out = self.m._n95_fit_report(lines, 850)
        self.assertLessEqual(len(out), 850)
        self.assertTrue(out.startswith('head'))
        self.assertIn('e.g. “say 0”', out)                       # the first rows keep their examples
        self.assertNotIn('e.g. “say 11”', out)                    # the last rows lose theirs first
        self.assertEqual(out.count('✅ Row'), 12)                  # every row is still listed

    def test_fit_keeps_the_examples_of_rows_that_need_attention(self):
        lines = ['head'] + ['✅ Row %d: %s\n    e.g. “say %d”' % (i, 'x' * 60, i) for i in range(10)] + ['🔧 Broken: not set up\n    e.g. “fix it”']
        self.assertGreater(len('\n'.join(lines)), 800)
        out = self.m._n95_fit_report(lines, 760)
        self.assertIn('e.g. “fix it”', out)
        self.assertNotIn('e.g. “say 9”', out)

    def test_fit_never_exceeds_the_room(self):
        lines = ['head'] + ['✅ Row %d: %s' % (i, 'y' * 300) for i in range(30)]
        for room in (50, 400, 1500):
            self.assertLessEqual(len(self.m._n95_fit_report(lines, room)), room)

    def test_the_real_report_has_every_row_and_its_ending(self):
        rows = self.m._n88_abilities(OWNER_ID, live=True)
        self.assertGreater(len(self.m._n95_fit_report(self.full_lines(rows), 100000)), 3300)    # it really is long
        r = self.m._n88_eye_abilities(OWNER_ID, live=True)['text']
        self.assertLessEqual(len(r), 3900)
        self.assertIn('All of this is read-only and private to you', r)
        self.assertTrue(r.rstrip().endswith('still need your approval.'))
        for name in ('Website doors', 'Care and housekeeping', 'GSTIN and PAN checks', 'Study helper', 'Live trading (Fyers)'):
            self.assertIn(name, r)

    def test_to_fix_line_survives_when_something_needs_setup(self):
        self.start(self.m, 'fyers_ready', lambda: False)
        r = self.m._n88_eye_abilities(OWNER_ID, live=True)['text']
        self.assertIn('To fix:', r)
        self.assertLess(r.index('To fix:'), r.index('All of this is read-only'))
        self.assertLessEqual(len(r), 3900)
