"""Nemo v106 "Steady": /update answers at once and runs every heavy check of a new file in a separate low-priority process (never inside the live bot);
"could not check" is never reported as "failed"; a safety net outside Nemo's service puts the previous version back if an update keeps crashing at start;
Nemo reads his own source for names without a full syntax tree; the voice, Gemini and Gmail checks tell the truth; a Nemo file sent in the chat is staged
for /update only.

Offline. No Telegram, no network, no AI, no systemd: the child processes are real (python), the service manager is a fake script.

    NEMO_FILE=/path/to/nemotron_bot.py python -m unittest tests.test_steady106 -v
"""
import ast
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

from tests import test_cortex83 as base
from tests.test_cortex83 import OWNER_ID
from tests.test_steward85 import StewardCase


def setUpModule():
    if base.m is None:
        base.setUpModule()


MUST = ('handle', 'main', 'ask_ai', 'handle_callback', 'send_text', 'self_update', 'apply_self_upgrade', 'self_rollback', 'tg', 'prime_regression_suite',
        'make_pdf', 'browser_agent', 'video_download', 'save_data', 'load_data', 'prime_policy_decide', 'prime_task_create', 'prime_eval_file',
        'prime_trade_reconcile_boot')       # the update checks' parts, then the Evaluation Lab's critical functions


def nemo_code(version='107.0', extra='', pad_lines=6000, drop=()):
    """A small file that looks like Nemo to the update checks (markers, the functions every Nemo has, over 100,000 characters)."""
    head = '"""nemotron_bot.py v%s - TEST BUILD"""\nVERSION = "27.0"\nTELEGRAM_TOKEN = ""\n' % version
    defs = ''.join('def %s(*a, **k):\n    return None\n\n\n' % n for n in MUST if n not in drop)
    return head + extra + defs + ('# padding line so the file is as big as a real update\n' * pad_lines) + 'VERSION = "%s"\n' % version


def sha(text):
    return hashlib.sha256(text.encode('utf-8', 'ignore')).hexdigest()


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def layer_source():
    src = read(base.NEMO_FILE)
    i = src.index('# NEMO 106 - STEADY')
    j = src.index('# NEMO 107 - ') if '# NEMO 107 - ' in src else src.rindex("if __name__")
    return src[i:j]


class SteadyCase(StewardCase):
    def setUp(self):
        super().setUp()
        m = self.m
        self.out = []                                    # (cid, text, kb) of every send_text

        def rec(cid, text, kb=None):
            self.sent.append((cid, text))
            self.out.append((cid, text, kb))
        self.swap('send_text', rec)
        self.kv = {}
        self.put('_n106_kv_get', lambda k, d=None: self.kv.get(k, d))
        self.put('_n106_kv_set', lambda k, v: self.kv.__setitem__(k, v) or True)
        m._N106_COMPILED.clear()
        m._N106_UPD.update(busy=False, chat=None, since=0.0, step='', proc=None, cancel=False, name='', last='')
        m._N85_FORCE.clear()
        m._N106_SYNC['on'] = True
        for k in m._N106_STATS:
            m._N106_STATS[k] = 0
        self._pendup = set(m.PENDUP)
        self._lastcode = m.LAST_CODE.get(self.cid)
        self.addCleanup(self._restore)

    def _restore(self):
        m = self.m
        m._N106_SYNC['on'] = False
        m._N106_COMPILED.clear()
        m._N85_FORCE.clear()
        m._N106_UPD.update(busy=False, proc=None, cancel=False)
        for k in set(m.PENDUP) - self._pendup:
            m.PENDUP.pop(k, None)
        if self._lastcode is None:
            m.LAST_CODE.pop(self.cid, None)
        else:
            m.LAST_CODE[self.cid] = self._lastcode

    def swap(self, name, val):
        """Patch an attribute a parent fixture already patched: undo the parent's patch first, so both come off in the right order."""
        for p in list(self.patches):
            if getattr(p, 'attribute', None) == name:
                p.stop()
                self.patches.remove(p)
        self.put(name, val)

    def put(self, name, val, obj=None):
        p = mock.patch.object(obj or self.m, name, val)
        p.start()
        self.addCleanup(p.stop)

    def texts(self):
        """Everything the owner saw: messages, status messages and their edits."""
        parts = [t for (_c, t) in self.sent] + [str(t or '') for (_c, t, _k) in self.cards] + [str(e.get('text') or '') for e in self.edits]
        return '\n'.join(parts)

    def kbs(self):
        return [b['callback_data'] for (_c, _t, kb) in self.out if kb for row in kb.get('inline_keyboard', []) for b in row]


# ===================================================================================================================
# 1. The compile check runs in a separate process, once per file, and "could not check" is never "failed"
# ===================================================================================================================
class TestCompileOutsideTheBot(SteadyCase):
    def test_small_code_is_still_checked_in_place_as_before(self):
        self.assertEqual(self.m._compile_check('x = 1\n'), (True, ''))
        ok, err = self.m._compile_check('def (:\n')
        self.assertFalse(ok)
        self.assertIn('SyntaxError', err)
        self.assertEqual(self.m._N106_STATS['compile_runs'], 0)

    def test_a_big_file_is_compiled_by_a_child_process_once_and_then_remembered(self):
        code = nemo_code(pad_lines=24000)
        self.assertGreater(len(code), self.m._N106_BIG)
        self.put('_N106_COMPILE_CHECK_PREV', mock.Mock(side_effect=AssertionError('compiled inside the live bot')))
        self.assertEqual(self.m._compile_check(code), (True, ''))
        self.assertEqual(self.m._N106_STATS['compile_runs'], 1)
        self.assertEqual(self.m._compile_check(code), (True, ''))
        self.assertEqual((self.m._N106_STATS['compile_runs'], self.m._N106_STATS['compile_cached']), (1, 1))

    def test_the_child_asks_the_kernel_to_stop_it_first_when_memory_runs_out(self):
        r = self.m._n106_compile_text(nemo_code())
        self.assertTrue(r['ok'])
        self.assertEqual(r.get('oom'), '1000')

    def test_a_syntax_error_is_reported_with_its_line(self):
        code = nemo_code(extra='def broken(:\n    pass\n', pad_lines=24000)
        ok, err = self.m._compile_check(code)
        self.assertFalse(ok)
        self.assertRegex(err, r'SyntaxError at line \d+')
        self.assertNotIn('could not check', err)

    def test_low_memory_means_not_checked_and_nothing_is_started_or_remembered(self):
        self.put('_n106_mem', lambda: {'MemAvailable': 200, 'SwapFree': 100})
        self.put('_n106_run_child', mock.Mock(side_effect=AssertionError('must not start a child')))
        r = self.m._n106_compile_text(nemo_code())
        self.assertIsNone(r['ok'])
        self.assertIn('only 300 MB of memory is free', r['why'])
        self.assertEqual(self.m._N106_COMPILED, {})
        ok, err = self.m._compile_check(nemo_code(pad_lines=24000))
        self.assertFalse(ok)
        self.assertTrue(err.startswith('could not check: '))

    def test_a_child_the_kernel_killed_is_not_a_failed_compile(self):
        self.put('_N106_COMPILE_CHILD', 'import os, signal\nos.kill(os.getpid(), signal.SIGKILL)\n')
        r = self.m._n106_compile_text(nemo_code())
        self.assertIsNone(r['ok'])
        self.assertIn('signal 9', r['why'])
        self.assertTrue(r.get('memory'))

    def test_a_check_that_takes_too_long_is_stopped_and_reported_as_not_checked(self):
        self.put('_N106_COMPILE_CHILD', 'import time\ntime.sleep(30)\n')
        with mock.patch.dict(self.m._N106_LIMITS, {'compile_s': 1}):
            t0 = time.time()
            r = self.m._n106_compile_text(nemo_code())
        self.assertLess(time.time() - t0, 15)
        self.assertIsNone(r['ok'])
        self.assertIn('longer than 1 seconds', r['why'])


# ===================================================================================================================
# 2. Nemo reads his own big source for names with a line scan, never a full syntax tree inside the bot
# ===================================================================================================================
class TestLightTree(SteadyCase):
    def test_nested_structure_and_names(self):
        t = self.m._n106_light_tree('def a():\n    def b():\n        pass\nclass C:\n    async def d(self):\n        pass\nasync def e():\n    pass\n')
        self.assertEqual([n.name for n in t.body], ['a', 'C', 'e'])
        self.assertIsInstance(t.body[2], ast.AsyncFunctionDef)
        self.assertEqual([n.name for n in ast.walk(t) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))], ['a', 'e', 'b', 'd'])

    def test_the_proxy_uses_the_real_parser_for_small_code_and_expressions(self):
        p = self.m._prime_ast
        self.assertIsInstance(p.parse('x = 1').body[0], ast.Assign)
        self.assertIsInstance(p.parse('1 + 2', mode='eval'), ast.Expression)
        self.assertIs(p.FunctionDef, ast.FunctionDef)
        self.assertEqual(self.m._n52_calculate('2 + 3 * 4')['result'], 14)        # the calculator still uses the real parser through the stand-in

    def test_the_running_file_finds_every_function_a_real_parse_finds(self):
        src = read(base.NEMO_FILE)
        light = {n.name for n in ast.walk(self.m._n106_light_tree(src)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        for name in ('handle', 'main', 'ask_ai', 'self_update', '_n106_update_steps', 'prime_regression_suite', 'send_long', 'omni_context', 'prime_goal_run'):
            self.assertIn(name, light)

    def test_big_sources_never_reach_the_real_parser(self):
        big = nemo_code(pad_lines=24000)
        with mock.patch('ast.parse', side_effect=AssertionError('full syntax tree of a big file')):
            tree = self.m._prime_ast.parse(big)
            names = self.m._prime_top_functions(big)[1]
        self.assertIn('handle', names)
        self.assertGreaterEqual(self.m._N106_STATS['light_trees'], 2)
        self.assertTrue(any(isinstance(n, ast.FunctionDef) for n in tree.body))


# ===================================================================================================================
# 3. Evaluation Lab: the real version, and "not checked" instead of a false FAIL
# ===================================================================================================================
class TestEvaluationLab(SteadyCase):
    def setUp(self):
        super().setUp()
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.cand = os.path.join(self.dir.name, 'cand.py')
        self.cur = os.path.join(self.dir.name, 'cur.py')
        with open(self.cand, 'w', encoding='utf-8') as f:
            f.write(nemo_code('107.0', pad_lines=24000))
        with open(self.cur, 'w', encoding='utf-8') as f:
            f.write(nemo_code('106.0', pad_lines=24000))

    def test_the_version_is_the_last_version_line_not_the_first(self):
        r = self.m.prime_eval_file(self.cand)
        self.assertEqual(r['version'], '107.0')
        self.assertIs(r['compile'], True)
        self.assertTrue(r['pass'])

    def test_a_compile_that_could_not_run_is_not_a_failure_and_does_not_cost_45_points(self):
        self.put('_n106_mem', lambda: {'MemAvailable': 100, 'SwapFree': 0})
        with mock.patch('ast.parse', side_effect=AssertionError('full syntax tree inside the bot')):
            ev = self.m.prime_eval_deep(self.cand)
        self.assertIsNone(ev['compile'])
        self.assertIn('only 100 MB', ev['unchecked'])
        self.assertTrue(ev['pass'], ev)
        self.assertFalse(any('AssertionError' in c for c in ev['critical']))
        self.assertGreaterEqual(ev['score'], 80)
        self.assertTrue(any('could not be checked' in w for w in ev['syntax_risk']))

    def test_compare_says_review_not_reject_when_the_compile_could_not_run(self):
        self.put('_n106_mem', lambda: {'MemAvailable': 100, 'SwapFree': 0})
        r = self.m.prime_eval_compare(self.cand, self.cur, False)
        self.assertEqual(r['verdict'], 'REVIEW')
        self.assertEqual(r['blockers'], [])
        self.assertTrue(any('could not be checked' in w for w in r['warnings']))
        self.assertNotIn('candidate version equals running version', r['warnings'])
        self.assertIn('candidate 107.0', r['summary'])

    def test_a_real_syntax_error_still_rejects(self):
        with open(self.cand, 'w', encoding='utf-8') as f:
            f.write(nemo_code('107.0', extra='def broken(:\n', pad_lines=24000))
        r = self.m.prime_eval_compare(self.cand, self.cur, False)
        self.assertEqual(r['verdict'], 'REJECT')

    def test_eval_command_shows_not_checked_in_words(self):
        self.put('_n106_mem', lambda: {'MemAvailable': 100, 'SwapFree': 0})
        self.put('prime_eval_deep', lambda p: {'version': '106.0', 'score': 96.0, 'compile': None, 'unchecked': 'only 100 MB of memory is free', 'functions': 5,
                                               'duplicates': [], 'required_missing': [], 'syntax_risk': []})
        self.m.handle(self.msg('/eval'))
        self.assertIn('Compile: NOT CHECKED (only 100 MB of memory is free)', self.texts())


# ===================================================================================================================
# 4. /update: talks at once, light, honest
# ===================================================================================================================
class UpdateCase(SteadyCase):
    def setUp(self):
        super().setUp()
        self.code = nemo_code('107.0', pad_lines=24000)          # over 1 MB, like a real update: Apply's compile check must come from the remembered result
        self.current = nemo_code('106.0')
        self.m.LAST_CODE[self.cid] = {'name': 'nemotron_bot.py', 'code': self.code}
        self.put('_n106_mem', lambda: {'MemTotal': 8000, 'MemAvailable': 6000, 'SwapFree': 1000, 'SwapTotal': 2000})
        self.trials = []
        self.trial_result = {'cand': {'ok': True, 'version': '107.0', 'import_s': 4.2, 'total': 950, 'failing': [], 'missing': []}, 'cur': None}
        self.put('_n106_trial', lambda code, beat=None, job=None: self.trials.append(len(code)) or self.trial_result)
        self.put('_n92_tool', lambda name: '')
        self.put('_self_read', lambda: self.current)
        self.put('_n106_guard_possible', lambda: (True, 'nemobot'))
        for name in ('prime_eval_compare', '_n92_update_checks', '_n85_gate', '_N106_COMPILE_CHECK_PREV', '_N85_SELF_UPDATE_PREV'):
            self.put(name, mock.Mock(side_effect=AssertionError(name + ' must not run for a Nemo file')))

    def new_cards(self):
        return [k for k in self.m.PENDUP if k not in self._pendup]


class TestUpdateFlow(UpdateCase):
    def test_the_first_message_goes_out_before_any_check_and_the_status_message_is_edited(self):
        order = []
        real = self.m._n106_compile_text
        self.put('_n106_compile_text', lambda *a, **k: order.append(('compile', len(self.cards))) or real(*a, **k))
        self.m.self_update(self.cid)
        self.assertEqual(order[0][1], 1, 'the status message was sent before the compile check started')
        self.assertIn('📥 Checking the update: nemotron_bot.py → v107.0', self.cards[0][1])
        self.assertTrue(self.edits, 'the status message is updated in place')
        self.assertIn('✅ Compiles cleanly', self.edits[-1]['text'])
        self.assertIn('✅ Trial start: v107.0 started in 4.2 s', self.edits[-1]['text'])

    def test_a_good_file_gets_the_apply_card_and_apply_does_not_compile_again(self):
        tok = self.m.self_update(self.cid)
        self.assertEqual(self.new_cards(), [tok])
        self.assertEqual(self.m.PENDUP[tok]['n106_sha'], sha(self.code))
        self.assertEqual(self.m.PENDUP[tok]['newtext'], self.code)
        self.assertIn('upok:' + tok, self.kbs())
        self.assertIn('upno:' + tok, self.kbs())
        card = self.out[-1][1]
        self.assertIn('Ready to install: v%s → v107.0' % self.m.VERSION, card)
        self.assertIn('🛟 Safety net', card)
        self.assertIn('/rollback', card)
        self.put('_n106_run_child', mock.Mock(side_effect=AssertionError('compiled again at Apply')))
        self.assertEqual(self.m._compile_check(self.code), (True, ''))

    def test_a_file_that_does_not_compile_gets_no_apply(self):
        self.m.LAST_CODE[self.cid] = {'name': 'x.py', 'code': nemo_code('107.0', extra='def broken(:\n')}
        self.assertIsNone(self.m.self_update(self.cid))
        self.assertEqual(self.new_cards(), [])
        self.assertRegex(self.texts(), r'❌ It does not compile: SyntaxError at line \d+')
        self.assertEqual(self.trials, [])

    def test_too_little_memory_to_check_means_no_apply_and_a_check_again_button(self):
        self.put('_n106_mem', lambda: {'MemAvailable': 250, 'SwapFree': 50})
        self.assertIsNone(self.m.self_update(self.cid))
        self.assertEqual(self.new_cards(), [])
        self.assertIn('❓ I could not run the compile check: only 300 MB of memory is free', self.texts())
        self.assertIn('I will not offer Apply for a file I could not check', self.texts())
        self.assertIn('n106:again', self.kbs())
        self.assertIn('server memory', self.texts())

    def test_memory_for_the_compile_but_not_for_a_second_nemo_skips_the_trial_and_says_so(self):
        self.put('_n106_mem', lambda: {'MemAvailable': 700, 'SwapFree': 0})
        tok = self.m.self_update(self.cid)
        self.assertTrue(tok)
        self.assertEqual(self.trials, [])
        self.assertIn('➖ Trial start skipped: only 700 MB of memory is free', self.texts())

    def test_a_file_that_crashes_while_starting_gets_no_apply(self):
        self.trial_result = {'cand': {'ok': False, 'stage': 'import', 'error': "NameError: name 'oops' is not defined"}, 'cur': None}
        self.assertIsNone(self.m.self_update(self.cid))
        self.assertEqual(self.new_cards(), [])
        self.assertIn("crashed while starting: NameError: name 'oops' is not defined", self.texts())
        self.assertIn('/updateforce85', self.texts())

    def test_a_trial_the_server_stopped_is_not_a_crash_and_apply_is_offered(self):
        self.trial_result = {'cand': {'ok': False, 'stage': 'killed', 'error': 'the server stopped it (signal 9; usually that means it ran out of memory)'}}
        self.assertTrue(self.m.self_update(self.cid))
        self.assertIn('❓ Trial start could not finish: the server stopped it', self.texts())

    def test_new_self_test_failures_are_named_and_apply_is_still_offered(self):
        self.trial_result = {'cand': {'ok': True, 'version': '107.0', 'import_s': 3, 'total': 10, 'failing': ['a', 'b'], 'missing': []},
                             'cur': {'ok': True, 'failing': ['a']}}
        self.assertTrue(self.m.self_update(self.cid))
        self.assertIn('⚠️ 1 of them pass in the running version but fail in the new one: b', self.texts())

    def test_force_skips_the_trial_once_and_gate_off_skips_it(self):
        self.m._N85_FORCE[self.cid] = True
        self.assertTrue(self.m.self_update(self.cid))
        self.assertEqual(self.trials, [])
        self.assertIn('you asked to skip it once', self.texts())
        self.assertTrue(self.m.self_update(self.cid))
        self.assertEqual(len(self.trials), 1, 'the skip is one-shot')
        self.m._n83_set_flag(self.cid, 'updategate', False)
        self.addCleanup(self.m._n83_set_flag, self.cid, 'updategate', True)
        self.assertTrue(self.m.self_update(self.cid))
        self.assertEqual(len(self.trials), 1)
        self.assertIn('switched off (/steward85 gate on', self.texts())

    def test_key_changes_are_named_never_shown(self):
        self.current = nemo_code('106.0', extra='GEMINI_KEY = "old-value-123"\nGROQ_KEY = "keep"\n')
        self.m.LAST_CODE[self.cid] = {'name': 'x.py', 'code': nemo_code('107.0', extra='GEMINI_KEY = "new-value-456"\n')}
        self.assertTrue(self.m.self_update(self.cid))
        t = self.texts()
        self.assertIn('CHANGES these key/config lines: GEMINI_KEY', t)
        self.assertIn('REMOVES these key/config lines: GROQ_KEY', t)
        for v in ('old-value-123', 'new-value-456', 'keep"'):
            self.assertNotIn(v, t)

    def test_an_incomplete_file_is_refused_before_any_check(self):
        self.m.LAST_CODE[self.cid] = {'name': 'x.py', 'code': nemo_code('107.0', drop=('handle_callback',))}
        self.put('_n106_compile_text', mock.Mock(side_effect=AssertionError('must not compile')))
        self.assertIsNone(self.m.self_update(self.cid))
        self.assertIn('not a complete Nemo file: it has no def handle_callback(', self.texts())

    def test_a_second_update_while_one_runs_gets_a_status_not_a_second_check(self):
        self.m._N106_UPD.update(busy=True, since=time.time() - 42, step='⏳ Compile check… 30 s', name='nemotron_bot.py')
        self.put('_n106_update_steps', mock.Mock(side_effect=AssertionError('second run')))
        self.m.self_update(self.cid)
        self.assertIn('already checking an update (nemotron_bot.py, started 42 s ago)', self.texts())
        self.assertIn('/update cancel', self.texts())

    def test_the_busy_flag_is_released_even_after_an_error(self):
        self.put('_n106_update_steps', mock.Mock(side_effect=RuntimeError('boom')))
        self.m.self_update(self.cid)
        self.assertFalse(self.m._N106_UPD['busy'])
        self.assertIn('stopped on an unexpected error (RuntimeError). Nothing was changed', self.texts())

    def test_check_again_button_reruns_for_the_owner_only(self):
        runs = []
        self.put('_n106_update', lambda cid: runs.append(cid))
        self.m.handle_callback({'id': 'cb', 'data': 'n106:again', 'from': {'id': 999}, 'message': {'chat': {'id': 999}}})
        self.assertEqual(runs, [])
        self.m.handle_callback({'id': 'cb', 'data': 'n106:again', 'from': {'id': self.cid}, 'message': {'chat': {'id': self.cid}}})
        self.assertEqual(runs, [self.cid])


class TestOtherUpdateCallers(UpdateCase):
    def test_other_chats_get_the_original_owner_only_answer(self):
        self.put('_N106_SELF_UPDATE_PREV', lambda cid: self.sent.append((cid, 'prev')))
        self.m.self_update(999)
        self.assertEqual(self.sent[-1], (999, 'prev'))
        self.assertEqual(self.new_cards(), [])

    def test_a_file_that_is_not_nemo_gets_the_original_refusal_without_the_old_heavy_steps(self):
        seen = []
        self.put('_N85_SELF_UPDATE_PREV', lambda cid: seen.append(cid))
        self.m.LAST_CODE[self.cid] = {'name': 'other.py', 'code': 'VERSION = 1\n' + 'x = 1\n' * 30000}
        self.m.self_update(self.cid)
        self.assertEqual(seen, [self.cid])

    def test_cancel_stops_a_running_check_and_its_child(self):
        self.put('_N106_COMPILE_CHILD', 'import time\ntime.sleep(60)\n')
        self.m._N106_SYNC['on'] = False
        t = threading.Thread(target=self.m.self_update, args=(self.cid,))
        t.start()
        deadline = time.time() + 15
        while self.m._N106_UPD.get('proc') is None and time.time() < deadline:
            time.sleep(0.05)
        proc = self.m._N106_UPD.get('proc')
        self.assertIsNotNone(proc)
        self.m._N106_SYNC['on'] = True
        self.m.handle(self.msg('/update cancel'))
        t.join(20)
        self.assertFalse(t.is_alive())
        self.assertIsNotNone(proc.poll(), 'the child process was stopped')
        self.assertIn('⏹ Stopping the update check', self.texts())
        self.assertIn('⏹ Stopped by you. Nothing was changed.', self.texts())
        self.assertFalse(self.m._N106_UPD['busy'])
        self.assertEqual(self.new_cards(), [])

    def test_update_status_and_cancel_when_idle(self):
        self.m.handle(self.msg('/update status'))
        self.assertIn('No update check is running', self.texts())
        self.m.handle(self.msg('/update cancel'))
        self.assertIn('No update check is running.', self.sent[-1][1])

    def test_updatecheck_runs_off_the_message_loop(self):
        seen = []
        self.put('updatecheck_cmd', lambda cid: seen.append(cid))
        self.m.handle(self.msg('/updatecheck'))
        self.assertEqual(seen, [self.cid])
        self.assertIn('Pre-flight of the staged file', self.texts())


# ===================================================================================================================
# 5. The trial start: lowest priority, first to be stopped, results read correctly
# ===================================================================================================================
TINY_OK = '''
VERSION = open('/proc/self/oom_score_adj').read().strip()
def handle(*a): pass
def main(*a): pass
def send_text(*a): pass
def tg(*a): pass
def ask_ai(*a): pass
def handle_callback(*a): pass
def self_update(*a): pass
def prime_regression_suite():
    return {'tests': [{'name': 'one', 'ok': True}, {'name': 'two', 'ok': False}]}
'''


class TestTrialRun(SteadyCase):
    def setUp(self):
        super().setUp()
        self.put('_n85_sandbox_prefix', lambda work, tag='run', probe=True: ([], ''))
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def test_a_good_candidate_reports_its_checks_and_runs_as_the_kernels_first_choice_to_stop(self):
        cur = os.path.join(self.dir.name, 'cur.py')
        with open(cur, 'w') as f:
            f.write(TINY_OK)
        r = self.m._n106_trial(TINY_OK, current_path=cur)
        self.assertTrue(r['cand']['ok'], r)
        self.assertEqual(r['cand']['version'], '1000')
        self.assertEqual((r['cand']['total'], r['cand']['failing']), (2, ['two']))
        self.assertTrue(r['cur']['ok'], 'the running file is started for comparison only because the new one has a failing check')

    def test_an_import_crash_is_reported_with_its_error(self):
        r = self.m._n106_trial('raise NameError("oops at start")\n')
        self.assertEqual(r['cand']['stage'], 'import')
        self.assertIn('oops at start', r['cand']['error'])
        self.assertIsNone(r['cur'])

    def test_no_sandbox_means_skipped_with_the_reason(self):
        self.put('_n85_sandbox_prefix', lambda work, tag='run', probe=True: (None, 'namespaces are not permitted here'))
        self.assertEqual(self.m._n106_trial(TINY_OK), {'skipped': 'namespaces are not permitted here'})


# ===================================================================================================================
# 6. The safety net
# ===================================================================================================================
FAKE_SYSTEMCTL = '''#!/bin/sh
echo "$@" >> "$FAKE_DIR/calls.log"
if [ "$1" = "show" ]; then
  n=$(cat "$FAKE_DIR/n" 2>/dev/null || echo 0)
  if [ "$FAKE_MODE" = "crash" ]; then n=$((n+1)); echo $n > "$FAKE_DIR/n"; fi
  echo "ActiveState=$(cat "$FAKE_DIR/state")"
  echo "NRestarts=$n"
fi
exit 0
'''


class TestSafetyNetScript(SteadyCase):
    def setUp(self):
        super().setUp()
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        d = self.dir.name
        self.bin = os.path.join(d, 'bin')
        os.makedirs(self.bin)
        p = os.path.join(self.bin, 'systemctl')
        with open(p, 'w') as f:
            f.write(FAKE_SYSTEMCTL)
        os.chmod(p, 0o755)
        self.guard = os.path.join(d, 'guard.py')
        with open(self.guard, 'w') as f:
            f.write(self.m._N106_GUARD)
        self.self_path = os.path.join(d, 'nemotron_bot.py')
        self.backup = os.path.join(d, 'backup.py')
        self.txn = os.path.join(d, 'txn.json')
        self.old, self.new = 'VERSION = "105.0"\nprint("old")\n', 'VERSION = "106.0"\nprint("new")\n'
        for path, text in ((self.self_path, self.new), (self.backup, self.old)):
            with open(path, 'w') as f:
                f.write(text)
        self.write_txn()
        self.set_state('activating')

    def write_txn(self, **kw):
        txn = {'status': 'pending_boot', 'new_hash': sha(self.new), 'old_hash': sha(self.old), 'backup': self.backup, 'attempts': 0, 'at': time.time()}
        txn.update(kw)
        with open(self.txn, 'w') as f:
            json.dump(txn, f)

    def set_state(self, s):
        with open(os.path.join(self.dir.name, 'state'), 'w') as f:
            f.write(s)

    def run_guard(self, mode='steady', wait='3'):
        env = dict(os.environ, PATH=self.bin + ':' + os.environ.get('PATH', ''), FAKE_DIR=self.dir.name, FAKE_MODE=mode)
        marker = os.path.join(self.dir.name, 'restarted')
        return subprocess.run([sys.executable, '-I', self.guard, self.txn, self.self_path, sha(self.new), 'nemobot', 'touch ' + marker, wait, '0.1'],
                              env=env, capture_output=True, text=True, timeout=60)

    def on_disk(self):
        with open(self.self_path) as f:
            return f.read()

    def log(self):
        p = os.path.join(self.dir.name, 'nemo_update_guard.log')
        return read(p) if os.path.exists(p) else ''

    def calls(self):
        p = os.path.join(self.dir.name, 'calls.log')
        return read(p) if os.path.exists(p) else ''

    def test_a_crash_loop_puts_the_previous_version_back_and_restarts(self):
        r = self.run_guard('crash', '20')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.on_disk(), self.old)
        with open(self.txn) as f:
            self.assertEqual(json.load(f)['status'], 'guard_rolled_back')
        self.assertIn('reset-failed nemobot', self.calls())
        self.assertTrue(os.path.exists(os.path.join(self.dir.name, 'restarted')))
        self.assertIn('the previous version is back', self.log())

    def test_a_failed_service_is_rolled_back_at_once(self):
        self.set_state('failed')
        r = self.run_guard('steady', '20')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.on_disk(), self.old)

    def test_windows_line_endings_in_the_update_do_not_blind_the_watcher(self):
        self.new = 'VERSION = "106.0"\r\nprint("new")\r\n'
        with open(self.self_path, 'w', newline='') as f:
            f.write(self.new)
        self.write_txn()
        self.set_state('failed')
        self.assertEqual(self.run_guard('steady', '20').returncode, 0)
        self.assertEqual(self.on_disk(), self.old)

    def test_a_healthy_service_is_left_alone(self):
        self.set_state('active')
        r = self.run_guard('steady', '1.5')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.on_disk(), self.new)
        self.assertIn('watch ended', self.log())
        self.assertFalse(os.path.exists(os.path.join(self.dir.name, 'restarted')))

    def test_a_confirmed_update_stands_the_watcher_down(self):
        self.write_txn(status='confirmed')
        self.set_state('failed')
        self.run_guard('crash', '20')
        self.assertEqual(self.on_disk(), self.new)
        self.assertIn('standing down', self.log())

    def test_it_never_restores_a_backup_that_is_not_the_recorded_previous_version(self):
        self.write_txn(old_hash='0' * 64)
        self.set_state('failed')
        r = self.run_guard('steady', '20')
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.on_disk(), self.new)
        self.assertIn('not the recorded previous version', self.log())

    def test_it_never_restores_a_backup_that_does_not_compile(self):
        self.old = 'def broken(:\n'
        with open(self.backup, 'w') as f:
            f.write(self.old)
        self.write_txn()
        self.set_state('failed')
        r = self.run_guard('steady', '20')
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.on_disk(), self.new)
        self.assertIn('does not compile', self.log())


class TestSafetyNetArming(SteadyCase):
    def setUp(self):
        super().setUp()
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.gpath = os.path.join(self.dir.name, '.nemo_update_guard.py')
        self.put('_n106_guard_path', lambda: self.gpath)
        self.runs = []
        self.rc = 0

        def fake_run(argv, **kw):
            self.runs.append(argv)
            return types.SimpleNamespace(returncode=self.rc, stdout='', stderr='Failed to start transient service' if self.rc else '')
        self.put('_n106_sp', types.SimpleNamespace(run=fake_run, PIPE=subprocess.PIPE, Popen=subprocess.Popen, TimeoutExpired=subprocess.TimeoutExpired))
        self.put('_n106_shutil', types.SimpleNamespace(which=lambda n: '/usr/bin/' + n if n in ('systemd-run', 'nice') else None, rmtree=shutil.rmtree))
        self.put('SELFCFG', {'restart_cmd': 'systemctl restart nemobot'})

    def test_it_starts_a_separate_transient_service_with_the_update_fingerprint(self):
        new = nemo_code('107.0', pad_lines=24000)
        ok, unit = self.m._n106_arm_guard(new)
        self.assertEqual((ok, unit), (True, 'nemobot'))
        argv = self.runs[0]
        self.assertEqual(argv[:3], ['/usr/bin/systemd-run', '--quiet', '--collect'])
        self.assertIn('RuntimeMaxSec=900', argv)
        self.assertIn(sha(new), argv)
        self.assertIn(self.m._TXN_FILE, argv)
        self.assertIn('nemobot', argv)
        self.assertEqual(read(self.gpath), self.m._N106_GUARD)
        self.assertEqual(stat.S_IMODE(os.stat(self.gpath).st_mode), 0o700)

    def test_no_systemctl_restart_or_no_systemd_run_means_no_watcher(self):
        self.put('SELFCFG', {'restart_cmd': 'pm2 restart nemo'})
        self.assertFalse(self.m._n106_arm_guard('x')[0])
        self.put('SELFCFG', {'restart_cmd': 'systemctl restart nemobot'})
        self.put('_n106_shutil', types.SimpleNamespace(which=lambda n: None))
        self.assertEqual(self.m._n106_guard_possible(), (False, 'systemd-run is not available'))
        self.assertEqual(self.runs, [])

    def test_a_refused_start_is_reported(self):
        self.rc = 1
        ok, why = self.m._n106_arm_guard(nemo_code())
        self.assertFalse(ok)
        self.assertIn('Failed to start', why)

    def test_apply_arms_the_watcher_first_for_the_owner_only(self):
        order = []
        self.put('_n106_arm_guard', lambda text: order.append(('arm', len(text))) or (True, 'nemobot'))
        self.put('_N106_APPLY_PREV', lambda cid, up: order.append(('apply', cid)) or True)
        big = nemo_code(pad_lines=24000)
        self.assertTrue(self.m.apply_self_upgrade(self.cid, {'newtext': big, 'target': 'FULL UPDATE'}))
        self.assertEqual(order, [('arm', len(big)), ('apply', self.cid)])
        order.clear()
        self.m.apply_self_upgrade(999, {'newtext': big})
        self.assertEqual(order, [('apply', 999)])

    def test_the_owner_hears_once_after_the_net_put_the_old_version_back(self):
        txn = {'status': 'guard_rolled_back'}
        self.put('_txn_load', lambda: dict(txn))
        self.put('_txn_save', lambda obj: txn.update(obj) or True)
        self.m._n106_after_boot()
        self.assertIn('safety net put the previous version back', self.texts())
        n = len(self.sent)
        self.m._n106_after_boot()
        self.assertEqual(len(self.sent), n)


# ===================================================================================================================
# 7. /rollback checks the backup outside the bot and never restores a file it could not check
# ===================================================================================================================
class TestRollback(SteadyCase):
    def setUp(self):
        super().setUp()
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.bpath = os.path.join(self.dir.name, 'backup.py')
        self.text = nemo_code('105.0', pad_lines=24000)
        with open(self.bpath, 'w') as f:
            f.write(self.text)
        self.put('_n106_last_backup', lambda: self.bpath)
        self.prev = []
        self.put('_N106_ROLLBACK_PREV', lambda cid: self.prev.append(cid))

    def test_a_checked_backup_goes_to_the_original_rollback_which_then_does_not_compile_again(self):
        self.m.self_rollback(self.cid)
        self.assertEqual(self.prev, [self.cid])
        self.put('_n106_run_child', mock.Mock(side_effect=AssertionError('compiled twice')))
        self.assertEqual(self.m._compile_check(self.text), (True, ''))

    def test_a_backup_that_could_not_be_checked_is_not_restored(self):
        self.put('_n106_mem', lambda: {'MemAvailable': 100, 'SwapFree': 0})
        self.m.self_rollback(self.cid)
        self.assertEqual(self.prev, [])
        self.assertIn('I could not check the backup (only 100 MB', self.texts())
        self.assertIn('Nothing was changed', self.texts())

    def test_other_chats_go_straight_to_the_original(self):
        self.m.self_rollback(999)
        self.assertEqual(self.prev, [999])


# ===================================================================================================================
# 8. A Nemo file sent in the chat is staged for /update only
# ===================================================================================================================
class TestUpdateFileInChat(SteadyCase):
    def setUp(self):
        super().setUp()
        self.code = nemo_code('107.0')
        self.raw = self.code.encode('utf-8')
        self.prev_docs = []
        self.put('_N106_DOC_PREV', lambda cid, doc, caption='': self.prev_docs.append((cid, doc.get('file_name'), caption)))
        fake_tg = self.m.tg

        def tg2(method, **kw):
            if method == 'getFile':
                return {'result': {'file_path': 'documents/file.py'}}
            return fake_tg(method, **kw)
        self.swap('tg', tg2)
        self.put('requests', types.SimpleNamespace(get=lambda url, timeout=0: types.SimpleNamespace(content=self.raw)))
        self.docs_before = self.m.DOCS.get(self.cid)
        self.addCleanup(self._docs_back)

    def _docs_back(self):
        if self.docs_before is None:
            self.m.DOCS.pop(self.cid, None)
        else:
            self.m.DOCS[self.cid] = self.docs_before

    def doc(self, name='nemotron_bot.py', size=None):
        return {'file_id': 'f1', 'file_name': name, 'file_size': size if size is not None else len(self.raw)}

    def test_it_is_staged_not_read_as_a_document_and_an_old_copy_is_dropped(self):
        self.m.DOCS[self.cid] = {'name': 'nemotron_bot old.py', 'text': '"""nemotron_bot.py v103.0 - MIND ...'}
        lib = []
        self.put('_N106_LIB_SAVE_PREV', lambda name, text: lib.append(name))
        self.m.handle_document(self.cid, self.doc(), '')
        self.assertEqual(self.m.LAST_CODE[self.cid]['code'], self.code.strip())
        self.assertNotIn(self.cid, self.m.DOCS)
        self.assertEqual((self.prev_docs, lib), ([], []))
        t = self.texts()
        self.assertIn('v107.0 of me', t)
        self.assertIn('Send /update to install it', t)
        self.assertIn('kept it out of your documents', t)

    def test_with_the_caption_update_the_check_starts_at_once(self):
        runs = []
        self.put('_n106_update', lambda cid: runs.append(cid))
        self.m.handle_document(self.cid, self.doc(), 'update')
        self.assertEqual(runs, [self.cid])

    def test_other_files_and_other_people_take_the_old_path(self):
        self.raw = ('x = 1\n' * 30000).encode()
        self.m.handle_document(self.cid, self.doc('other.py'), '')
        self.m.handle_document(self.cid, self.doc('small.py', size=500), '')
        self.m.handle_document(999, self.doc(), '')
        self.m.handle_document(self.cid, self.doc(), 'doc')
        self.assertEqual([d[1] for d in self.prev_docs], ['other.py', 'small.py', 'nemotron_bot.py', 'nemotron_bot.py'])

    def test_a_copy_of_nemo_kept_as_the_document_is_no_longer_sent_with_questions(self):
        self.m.DOCS[self.cid] = {'name': 'nemotron_bot hhhhhhhh.py', 'text': '"""nemotron_bot.py v105.0 - WEB HANDS SECRET-MARKER-TEXT'}
        prompt = self.m.build_system(self.cid)
        self.assertNotIn('SECRET-MARKER-TEXT', prompt)
        self.assertNotIn(self.cid, self.m.DOCS)
        self.m.DOCS[self.cid] = {'name': 'invoice.txt', 'text': 'Invoice 42 from the dealer'}
        self.assertIn('Invoice 42 from the dealer', self.m.build_system(self.cid))
        self.assertIn(self.cid, self.m.DOCS)

    def test_the_library_does_not_keep_copies_of_nemo(self):
        lib = []
        self.put('_N106_LIB_SAVE_PREV', lambda name, text: lib.append(name) or True)
        self.assertFalse(self.m.lib_save('nemotron_bot.py', self.code))
        self.assertTrue(self.m.lib_save('notes.txt', 'ordinary notes'))
        self.assertEqual(lib, ['notes.txt'])


# ===================================================================================================================
# 9. Health checks that tell the truth
# ===================================================================================================================
class TestVoiceCheck(SteadyCase):
    def setUp(self):
        super().setUp()
        self.m._N106_VOICE.update(at=0.0, ok=None, why='', engine='')
        self.addCleanup(self.m._N106_VOICE.update, at=0.0, ok=None, why='', engine='')

    def test_the_old_check_looked_for_functions_that_do_not_exist(self):
        self.assertFalse(callable(getattr(self.m, 'tts', None)) or callable(getattr(self.m, 'voice_reply', None)))
        self.assertTrue(callable(self.m.speak))

    def test_a_working_engine_passes_and_the_real_test_runs_at_most_every_6_hours(self):
        self.put('_n106_voice_engines', lambda: {'edge_tts': True, 'gtts': False})
        tries = []
        self.put('_n106_voice_try', lambda engines: tries.append(1) or (True, '', 'edge-tts'))
        r = self.m._health_probe('Voice engine (TTS)', 'media', lambda: False)
        self.assertTrue(r['ok'], r)
        self.assertIn('edge-tts yes', r['detail'])
        self.m._health_probe('Voice engine (TTS)', 'media', lambda: False)
        self.assertEqual(len(tries), 1)

    def test_no_engine_says_how_to_install_one(self):
        self.put('_n106_voice_engines', lambda: {'edge_tts': False, 'gtts': False})
        r = self.m._n106_voice_probe()
        self.assertFalse(r['ok'])
        self.assertIn('install edge-tts into yourself', r['reason'])

    def test_a_failing_real_test_is_reported_with_its_reason(self):
        self.put('_n106_voice_engines', lambda: {'edge_tts': True, 'gtts': True})
        self.put('_n106_voice_try', lambda engines: (False, 'edge-tts: ConnectionError; gTTS: ConnectionError', ''))
        r = self.m._n106_voice_probe()
        self.assertFalse(r['ok'])
        self.assertIn('voice test failed: edge-tts: ConnectionError', r['reason'])

    def test_other_probes_are_unchanged(self):
        self.assertTrue(self.m._health_probe('Disk', 'system', lambda: True)['ok'])
        self.assertFalse(self.m._health_probe('Disk', 'system', lambda: False)['ok'])


class TestGeminiCheck(SteadyCase):
    def setUp(self):
        super().setUp()
        self.put('GEMINI_KEY', 'test-key')
        self.calls = []
        self.result = {'provider': 'Gemini', 'ok': False, 'reason': 'rate limit/quota', 'attempts': [{'model': 'gemini-2.5-flash', 'status': 429, 'reason': 'rate limit/quota'}]}
        self.put('_N106_GEMINI_PROBE_PREV', lambda max_models=6: self.calls.append(max_models) or dict(self.result))

    def test_at_most_two_requests_then_rest_while_the_allowance_is_used_up(self):
        r = self.m.gemini_probe_diagnostic()
        self.assertEqual(self.calls, [2])
        self.assertFalse(r['ok'])
        until = float(self.kv['n106_gemini_rest_until'])
        self.assertGreater(until, time.time())
        self.assertLessEqual(until, time.time() + 3 * 3600 + 5)
        r2 = self.m.gemini_probe_diagnostic()
        self.assertEqual(self.calls, [2], 'no request while resting')
        self.assertTrue(r2['quota_rest'])
        self.assertIn('India time', r2['reason'])
        self.assertIn('quota', r2['reason'])

    def test_a_working_gemini_clears_the_rest(self):
        self.kv['n106_gemini_rest_until'] = str(time.time() - 1)
        self.result = {'provider': 'Gemini', 'ok': True, 'model': 'gemini-2.5-flash'}
        self.assertTrue(self.m.gemini_probe_diagnostic()['ok'])
        self.assertEqual(self.kv['n106_gemini_rest_until'], '0')

    def test_other_failures_do_not_rest(self):
        self.result = {'provider': 'Gemini', 'ok': False, 'reason': 'authentication rejected', 'attempts': [{'status': 401, 'reason': 'authentication rejected'}]}
        self.m.gemini_probe_diagnostic()
        self.m.gemini_probe_diagnostic()
        self.assertEqual(self.calls, [2, 2])

    def test_the_daily_reset_is_midnight_pacific_including_the_clock_change(self):
        import datetime as dt
        utc = dt.timezone.utc
        a = self.m._n106_next_pacific_midnight(dt.datetime(2026, 10, 27, 12, 0, tzinfo=utc).timestamp())
        self.assertEqual(dt.datetime.fromtimestamp(a, utc), dt.datetime(2026, 10, 28, 7, 0, tzinfo=utc))
        b = self.m._n106_next_pacific_midnight(dt.datetime(2026, 11, 2, 12, 0, tzinfo=utc).timestamp())
        self.assertEqual(dt.datetime.fromtimestamp(b, utc), dt.datetime(2026, 11, 3, 8, 0, tzinfo=utc))
        self.assertEqual(self.m._n106_ist_hhmm(a), '12:30 India time')


class TestHealthRunReuse(SteadyCase):
    def test_the_idle_loop_reuses_a_recent_run_and_commands_run_fresh(self):
        runs = []
        self.put('_N106_HEALTH_PREV', lambda notify=False: runs.append(notify) or {'passed': 1, 'total': 1, 'probes': []})
        self.put('_N106_HEALTH_CACHE', {'at': 0.0, 'r': None})

        def loop_twice():
            self.m.prime_health_run(False)
            self.m.prime_health_run(False)
        t = threading.Thread(target=loop_twice, name='nemo-continuous-evolution')
        t.start()
        t.join(10)
        self.assertEqual(runs, [False])
        self.m.prime_health_run(False)
        self.m.prime_health_run(True)
        self.assertEqual(runs, [False, False, True])


class TestGoogleSignIn(SteadyCase):
    def setUp(self):
        super().setUp()
        self.put('GOOGLE', {'client_id': 'cid.apps', 'client_secret': 'SECRET-CLIENT', 'refresh': 'REFRESH-ONE', 'token': '', 'token_exp': 0})
        self.put('google_ready', lambda: True)
        self.posts = []
        self.reply = (400, {'error': 'invalid_grant', 'error_description': 'Token has been expired or revoked.'})

        def post(url, data=None, timeout=0):
            self.posts.append(dict(data or {}))
            code, body = self.reply
            return types.SimpleNamespace(status_code=code, json=lambda: body)
        self.put('requests', types.SimpleNamespace(post=post))
        self.m._N106_GOOGLE.update(error='', desc='', at=0.0, bad_fp='', status=0)
        self.addCleanup(self.m._N106_GOOGLE.update, error='', desc='', at=0.0, bad_fp='', status=0)

    def test_googles_own_reason_is_kept_and_a_refused_sign_in_is_not_asked_again_at_once(self):
        self.assertIsNone(self.m.google_token())
        self.assertEqual(self.m._N106_GOOGLE['error'], 'invalid_grant')
        saved = json.loads(self.kv['n106_google_error'])
        self.assertEqual(saved['desc'], 'Token has been expired or revoked.')
        self.assertIsNone(self.m.google_token())
        self.assertEqual(len(self.posts), 1)
        self.m.GOOGLE['refresh'] = 'REFRESH-TWO'
        self.reply = (200, {'access_token': 'ACCESS', 'expires_in': 3600})
        self.assertEqual(self.m.google_token(), 'ACCESS')
        self.assertEqual(len(self.posts), 2)
        self.assertEqual(self.m._N106_GOOGLE['error'], '')
        for secret in ('SECRET-CLIENT', 'REFRESH-ONE', 'REFRESH-TWO', 'ACCESS'):
            self.assertNotIn(secret, json.dumps(self.kv))

    def test_the_advice_names_the_7_day_testing_limit_when_it_fits(self):
        self.m.google_token()
        self.kv['n106_google_signin_at'] = str(self.m._N106_GOOGLE['at'] - 7.02 * 86400)
        adv = self.m._n106_google_advice()
        self.assertIn('Google said: invalid_grant — “Token has been expired or revoked.”', adv)
        self.assertIn('7.0 days', adv)
        self.assertIn('7-day limit for apps in “Testing” mode', adv)
        self.assertIn('send /google', adv)
        self.assertIn('In production', adv)
        for secret in ('SECRET-CLIENT', 'REFRESH-ONE'):
            self.assertNotIn(secret, adv)

    def test_the_gmail_health_check_shows_the_real_reason(self):
        self.m.google_token()
        self.put('_N106_EMAIL_HEALTH_PREV', lambda: {'ok': False, 'reason': 'Google OAuth token refresh failed; re-authorize /google'})
        r = self.m._email_api_health()
        self.assertEqual(r['reason'], 'Google refused the saved sign-in (invalid_grant: Token has been expired or revoked.); send /google')

    def test_a_new_sign_in_is_remembered_and_clears_the_error(self):
        self.m.google_token()
        self.put('_N106_GEXCHANGE_PREV', lambda code: (True, 'Google connected'))
        self.assertEqual(self.m.google_exchange('4/abc'), (True, 'Google connected'))
        self.assertGreater(float(self.kv['n106_google_signin_at']), 0)
        self.assertEqual(self.kv['n106_google_error'], '')
        self.assertEqual(self.m._n106_google_advice(), '')

    def test_asking_about_gmail_answers_with_the_reason(self):
        self.m.google_token()
        self.m.handle(self.msg('gmail status'))
        self.assertIn('Google refused my saved sign-in', self.texts())


class TestAlerts(SteadyCase):
    def test_the_three_alerts_from_the_screenshot(self):
        rows = [{'name': 'Backup brain (Gemini)', 'ok': 0, 'reason': 'rate limit/quota', 'consecutive': 9},
                {'name': 'Email sending (Gmail API / SMTP)', 'ok': 0, 'reason': 'Google OAuth token refresh failed; re-authorize /google', 'consecutive': 2},
                {'name': 'Voice engine (TTS)', 'ok': 0, 'reason': 'empty/false response', 'consecutive': 9}]
        text = self.m._n106_alert_text(rows)
        self.assertIn('- Gmail: Google OAuth token refresh failed', text)
        self.assertIn('What to do:', text)
        self.assertIn('/google', text)
        self.assertNotIn('Voice engine', text)
        self.assertIn('ℹ️ Gemini (a backup brain): the free daily allowance is used up. Not a fault', text)
        self.assertNotIn('/drill', text)

    def test_only_a_used_up_allowance_and_the_old_voice_false_alarm_mean_no_alert(self):
        rows = [{'name': 'Backup brain (Gemini)', 'ok': 0, 'reason': 'rate limit/quota', 'consecutive': 9},
                {'name': 'Voice engine (TTS)', 'ok': 0, 'reason': 'empty/false response', 'consecutive': 9}]
        self.assertEqual(self.m._n106_alert_text(rows), '')

    def test_real_failures_still_alert(self):
        text = self.m._n106_alert_text([{'name': 'Web search', 'ok': 0, 'reason': 'network: ConnectTimeout', 'consecutive': 3}])
        self.assertIn('- Web search: network: ConnectTimeout (3 checks in a row)', text)

    def test_the_hourly_signal_is_rewritten_only_when_there_is_one(self):
        self.put('_N106_SIGNAL_PREV', lambda: '')
        self.assertEqual(self.m._v136_proactive_signal(), '')
        self.put('_N106_SIGNAL_PREV', lambda: 'PROACTIVE ALERT\n- old')
        self.put('_n106_alert_rows', lambda: [{'name': 'Web search', 'ok': 0, 'reason': 'x', 'consecutive': 2}])
        self.assertIn('- Web search: x (2 checks in a row)', self.m._v136_proactive_signal())


# ===================================================================================================================
# 10. Commands, regression rows, structure
# ===================================================================================================================
class TestCommandsAndStructure(SteadyCase):
    def test_steady_status_for_the_owner_only(self):
        self.m.handle(self.msg('/steady'))
        t = self.texts()
        self.assertIn('STEADY (v%s)' % self.m.VERSION, t)
        self.assertIn('Safety net after Apply', t)
        passed = []
        self.put('_N106_HANDLE_PREV', lambda msg: passed.append(msg))
        other = self.msg('/steady')
        other['chat']['id'] = other['from']['id'] = 999
        self.m.handle(other)
        self.assertEqual(len(passed), 1)

    def test_version_and_regression_rows(self):
        self.assertGreaterEqual(float(self.m.VERSION), 106)
        rows = self.m._n106_regression_rows()
        self.assertEqual([r['name'] for r in rows if not r['ok']], [])
        self.assertGreaterEqual(len(rows), 9)

    def test_the_old_update_steps_are_still_in_the_chain_behind_the_new_one(self):
        self.assertIs(self.m._N106_SELF_UPDATE_PREV.__globals__, self.m.__dict__)
        self.assertIn('_n92_update_checks', self.m._N106_SELF_UPDATE_PREV.__code__.co_names)

    def test_the_update_flow_never_calls_the_heavy_in_bot_steps(self):
        names = set()
        for fn in (self.m._n106_update, self.m._n106_update_steps, self.m._n106_trial_step, self.m._n106_trial, self.m._n106_extra_checks):
            names |= set(fn.__code__.co_names)
        for heavy in ('prime_eval_compare', 'prime_eval_deep', '_n85_gate', '_n92_update_checks', '_compile_check', 'compile'):
            self.assertNotIn(heavy, names)

    def test_no_secrets_no_shell_commands_from_chat_text(self):
        src = layer_source()
        for pattern in (r'sk-[A-Za-z0-9]{16,}', r'AIza[0-9A-Za-z_-]{20,}', r'\b\d{8,10}:[A-Za-z0-9_-]{30,}', r'ya29\.', r'-----BEGIN'):
            self.assertIsNone(re.search(pattern, src), pattern)
        self.assertNotIn('os.system(', src)
        self.assertNotIn('token_hex(6)', src)
        self.assertNotIn('shell=True', src.replace(self.m._N106_GUARD, ''))

    def test_the_layer_comes_last_before_the_entry_point(self):
        src = read(base.NEMO_FILE)
        self.assertLess(len(src[src.rindex("if __name__"):]), 400)
        self.assertGreater(src.index('# NEMO 106 - STEADY'), src.index('# NEMO 105 - WEB HANDS'))


if __name__ == '__main__':
    unittest.main()
