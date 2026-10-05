"""Nemo v94 Studio+: real AI enlarging (Real-ESRGAN), key-free background removal (rembg) and a chart under every Scout idea, plus the structural rules of the whole v94 layer.

Offline. The two AI programs are stand-ins that read and write the same files the real programs do (their command lines and memory needs were measured on the real libraries earlier); the charts are drawn for real with Pillow.

    NEMO_FILE=/path/to/nemotron_bot.py python -m unittest tests.test_studioplus94 -v
"""
import ast
import copy
import io
import json
import os
import re
import tempfile
import threading
import time
import unittest
from unittest import mock

from tests import test_cortex83 as base
from tests import test_scout93 as T
from tests.test_forge91 import ForgeCase, OWNER_ID
from tests.test_intel94 import IntelCase, setUpModule as _setup_intel
from tests.test_clear94 import clear_source

try:
    from PIL import Image, ImageDraw
    HAVE_PIL = True
except Exception:                                   # pragma: no cover
    HAVE_PIL = False
needs_pil = unittest.skipUnless(HAVE_PIL, 'Pillow is not installed')


def setUpModule():
    _setup_intel()


def photo(w=300, h=200, plain=False):
    im = Image.new('RGB', (w, h), (240, 240, 240) if plain else (30, 60, 120))
    d = ImageDraw.Draw(im)
    if not plain:
        for y in range(h):
            d.line((0, y, w, y), fill=(30 + y * 200 // max(1, h), 60 + (y * 7) % 40, 120))
    d.ellipse((w // 4, h // 4, 3 * w // 4, 3 * h // 4), fill=(250, 200, 40))
    return im


def png_bytes(im):
    b = io.BytesIO()
    im.save(b, 'PNG')
    return b.getvalue()


class PlusCase(ForgeCase):
    """Forge's world plus a scripted stand-in for the AI programs."""

    def setUp(self):
        super().setUp()
        m = self.m
        m._n94_put('studio_ai', 'on')
        for k in m._N94_STATS:
            m._N94_STATS[k] = 0
        self.have = {'realesrgan_ncnn_py', 'rembg'}
        real_have = m._n92_have
        self.start(m, '_n92_have', lambda mod: (mod in self.have) if mod in ('realesrgan_ncnn_py', 'rembg', 'nselib', 'exchange_calendars', 'arch') else real_have(mod))
        self.calls = []
        self.child_error = None
        self.esrgan_size = None

        def child(py, code, args=(), need_mb=400, timeout=120, job=None):
            self.calls.append({'py': py, 'code': code, 'args': [str(a) for a in args], 'need': need_mb, 'timeout': timeout, 'job': job})
            if self.child_error is not None:
                raise self.child_error
            if 'Realesrgan' in code:
                src, dst, model, tile = args
                im = Image.open(src).convert('RGB')
                scale = {0: 2, 4: 4}[int(model)]
                out = im.resize(self.esrgan_size or (im.size[0] * scale, im.size[1] * scale), Image.BICUBIC)
                out.save(dst, 'PNG')
                return {'ok': True, 'w': out.size[0], 'h': out.size[1]}
            if 'new_session' in code:
                src, dst = args
                im = Image.open(src).convert('RGBA')
                a = Image.new('L', im.size, 0)
                ImageDraw.Draw(a).ellipse((im.size[0] // 4, im.size[1] // 4, 3 * im.size[0] // 4, 3 * im.size[1] // 4), fill=255)
                im.putalpha(a)
                im.save(dst, 'PNG')
                return {'ok': True, 'w': im.size[0], 'h': im.size[1]}
            raise AssertionError('unknown program')
        self.start(m, '_n94_child_py', child)

    def leftover_jobs(self):
        d = self.m._n92_dir()
        return [x for x in os.listdir(d) if x.startswith('J92-')] if os.path.isdir(d) else []


# ===================================================================================================================
# 1. WHICH PYTHON, AND THE SAFE WAY TO RUN IT
# ===================================================================================================================
class TestPythonAndRunner(ForgeCase):
    def test_a_library_installed_into_the_bot_is_run_with_the_bots_own_python(self):
        self.start(self.m, '_n92_have', lambda mod: mod == 'rembg')
        self.assertEqual(self.m._n94_py_for('rembg', 'rembg'), self.m._n92_python())

    def test_a_tool_environment_is_used_when_the_library_is_not_in_the_bot(self):
        envdir = os.path.join(self.tmp.name, 'toolenv')
        os.makedirs(os.path.join(envdir, 'bin'))
        open(os.path.join(envdir, 'bin', 'python'), 'w').write('#!/bin/sh\n')
        self.start(self.m, '_n92_have', lambda mod: False)
        self.start(self.m, '_n91_ledger_find', lambda name: {'target': 'tool', 'env': 'rembg-env', 'manifest': {}} if name == 'rembg' else None)
        self.start(self.m, '_n91_env_dir', lambda env: envdir)
        self.assertEqual(self.m._n94_py_for('rembg', 'rembg'), os.path.join(envdir, 'bin', 'python'))
        self.assertEqual(self.m._n94_py_for('realesrgan_ncnn_py', 'realesrgan-ncnn-py'), '')

    def test_nothing_installed_is_an_empty_answer_not_an_error(self):
        self.start(self.m, '_n92_have', lambda mod: False)
        self.start(self.m, '_n91_ledger_find', lambda name: (_ for _ in ()).throw(RuntimeError('ledger broken')))
        self.assertEqual(self.m._n94_py_for('rembg', 'rembg'), '')

    def runner(self, rc=0, out='{"ok": true}\n', err=''):
        seen = []

        def run(argv, timeout=120, env=None, cwd=None):
            seen.append({'argv': argv, 'timeout': timeout, 'env': env, 'cwd': cwd})
            return rc, out, err
        self.start(self.m, '_n91_run', run)
        self.start(self.m, '_n92_guard', lambda need: (True, ''))
        return seen

    def test_the_child_is_niced_has_a_clean_environment_and_runs_in_the_job_folder(self):
        seen = self.runner()
        self.start(self.m, '_n91_env', lambda extra=None: dict({'PATH': '/usr/bin', 'HOME': '/tmp/h', 'PIP_INDEX_URL': 'x', 'NVIDIA_KEY': 'must-not-appear'}, **(extra or {})))
        data = self.m._n94_child_py(self.m._n92_python(), 'print(1)', ['a', 3], need_mb=450, timeout=77, job='/tmp/j')
        self.assertEqual(data, {'ok': True})
        r = seen[0]
        self.assertEqual(r['argv'][-4:], ['-c', 'print(1)', 'a', '3'])
        self.assertIn(self.m._n92_python(), r['argv'])
        self.assertEqual((r['timeout'], r['cwd']), (77, '/tmp/j'))
        self.assertNotIn('PIP_INDEX_URL', r['env'])
        self.assertNotIn('NVIDIA_KEY', json.dumps(r['argv']))

    def test_a_tool_python_gets_its_own_bin_first_on_the_path(self):
        seen = self.runner()
        self.start(self.m, '_n91_env', lambda extra=None: dict({'PATH': '/usr/bin'}, **(extra or {})))
        self.m._n94_child_py('/envs/rembg/bin/python', 'x', [], 100, 10)
        self.assertTrue(seen[0]['env']['PATH'].startswith('/envs/rembg/bin:'))

    def test_not_enough_memory_refuses_before_starting_anything(self):
        seen = self.runner()
        self.start(self.m, '_n92_guard', lambda need: (False, 'I am low on memory right now (%d MB needed).' % need))
        with self.assertRaises(self.m._N92Err) as cm:
            self.m._n94_child_py('py', 'x', [], 1100, 10)
        self.assertEqual(cm.exception.code, 'low_memory')
        self.assertIn('1100 MB', cm.exception.msg)
        self.assertEqual(seen, [])

    def test_only_one_heavy_job_at_a_time(self):
        seen = self.runner()
        self.assertTrue(self.m._N92_LOCK.acquire(blocking=False))
        try:
            with self.assertRaises(self.m._N92Err) as cm:
                self.m._n94_child_py('py', 'x', [], 100, 10)
            self.assertEqual(cm.exception.code, 'busy')
        finally:
            self.m._N92_LOCK.release()
        self.assertEqual(seen, [])

    def test_the_lock_is_released_after_a_failure(self):
        self.runner(rc=1, err='Traceback ...\nValueError: x')
        with self.assertRaises(self.m._N92Err):
            self.m._n94_child_py('py', 'x', [], 100, 10)
        self.assertTrue(self.m._N92_LOCK.acquire(blocking=False))
        self.m._N92_LOCK.release()

    def test_missing_system_libraries_are_named_with_the_fix(self):
        self.runner(rc=1, err='ImportError: libomp.so.5: cannot open shared object file: No such file or directory')
        with self.assertRaises(self.m._N92Err) as cm:
            self.m._n94_child_py('py', 'x', [], 100, 10)
        self.assertEqual(cm.exception.code, 'system_libs')
        self.assertIn('forge apt allow libomp5 libvulkan1', cm.exception.msg)
        self.assertIn('forge apt libomp5 libvulkan1', cm.exception.msg)
        self.runner(rc=1, err='OSError: libvulkan.so.1: cannot open shared object file')
        with self.assertRaises(self.m._N92Err) as cm:
            self.m._n94_child_py('py', 'x', [], 100, 10)
        self.assertEqual(cm.exception.code, 'system_libs')

    def test_other_failures_use_the_same_plain_sentences_as_the_other_helpers(self):
        self.runner(rc=1, err="ModuleNotFoundError: No module named 'rembg'")
        with self.assertRaises(self.m._N92Err) as cm:
            self.m._n94_child_py('py', 'x', [], 100, 10)
        self.assertEqual(cm.exception.code, 'not_installed')
        self.runner(rc=124, err='timed out after 150 s')
        with self.assertRaises(self.m._N92Err) as cm:
            self.m._n94_child_py('py', 'x', [], 100, 10)
        self.assertEqual(cm.exception.code, 'timeout')

    def test_output_that_is_not_one_good_json_line_is_refused(self):
        for out in ('', 'garbage', '[1, 2]', '{"ok": false}', '{"nothing": 1}'):
            self.runner(out=out)
            with self.assertRaises(self.m._N92Err) as cm:
                self.m._n94_child_py('py', 'x', [], 100, 10)
            self.assertEqual(cm.exception.code, 'bad_output', out)

    def test_the_last_line_is_the_answer_so_chatty_libraries_do_no_harm(self):
        self.runner(out='loading model...\nwarning: something\n{"ok": true, "w": 5}\n')
        self.assertEqual(self.m._n94_child_py('py', 'x', [], 100, 10)['w'], 5)


# ===================================================================================================================
# 2. REAL AI ENLARGING
# ===================================================================================================================
@needs_pil
class TestEnlarging(PlusCase):
    def test_a_two_times_enlarge_uses_the_x2_model_and_gives_the_exact_size(self):
        out = self.m._n90_op_upscale(photo(300, 200), 2)
        self.assertEqual(out.size, (600, 400))
        c = self.calls[0]
        self.assertEqual((c['args'][2], c['need'], c['timeout']), ('0', 450, 180))
        self.assertIn('Realesrgan(gpuid=-1', c['code'])
        self.assertEqual(self.m._N94_STATS['upscale_ai'], 1)

    def test_a_four_times_enlarge_uses_the_photo_model_with_its_bigger_memory(self):
        out = self.m._n90_op_upscale(photo(160, 120), 4)
        self.assertEqual(out.size, (640, 480))
        c = self.calls[0]
        self.assertEqual((c['args'][2], c['need'], c['timeout']), ('4', 2000, 240))

    def test_the_picture_is_always_tiled(self):
        self.m._n90_op_upscale(photo(300, 200), 2)
        self.assertEqual(self.calls[0]['args'][3], '128')

    def test_the_note_says_it_was_an_ai_model_and_warns_against_evidence_use(self):
        ctx = self.m._N90Ctx(OWNER_ID)
        self.m._n90_apply_ops(png_bytes(photo(300, 200)), [{'op': 'upscale', 'factor': 2}], ctx)
        note = ctx.notes[-1]
        self.assertIn('enlarged 2x to 600x400 with Real-ESRGAN (an AI model', note)
        self.assertIn('do not use it for evidence or documents', note)
        self.assertNotIn('no new detail is invented', note)

    def test_too_big_for_the_server_falls_back_to_the_plain_method_and_says_why(self):
        ctx = self.m._N90Ctx(OWNER_ID)
        self.m._n90_apply_ops(png_bytes(photo(1400, 300)), [{'op': 'upscale', 'factor': 2}], ctx)
        self.assertEqual(self.calls, [])
        self.assertIn('enlarged 2x to 2800x600 (sharpened; no new detail is invented) · plain method used: this picture is too big for the AI enlarger at 2x on this server (limit 1280 px on the long side)', ctx.notes[-1])
        ctx = self.m._N90Ctx(OWNER_ID)
        self.m._n90_apply_ops(png_bytes(photo(400, 300)), [{'op': 'upscale', 'factor': 4}], ctx)
        self.assertIn('limit 320 px', ctx.notes[-1])

    def test_three_times_uses_the_plain_method(self):
        ctx = self.m._N90Ctx(OWNER_ID)
        self.m._n90_apply_ops(png_bytes(photo(300, 200)), [{'op': 'upscale', 'factor': 3}], ctx)
        self.assertEqual(self.calls, [])
        self.assertIn('plain method used: the AI enlarger is set up for 2x and 4x only', ctx.notes[-1])

    def test_not_installed_means_the_old_behaviour_exactly_with_no_extra_words(self):
        self.have.clear()
        self.start(self.m, '_n91_ledger_find', lambda name: None)
        im = photo(300, 200)
        out = self.m._n90_op_upscale(im, 2)
        from PIL import ImageFilter
        want = im.convert('RGB').resize((600, 400), Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=1.6, percent=80, threshold=2))
        self.assertEqual(out.tobytes(), want.tobytes())
        ctx = self.m._N90Ctx(OWNER_ID)
        self.m._n90_apply_ops(png_bytes(im), [{'op': 'upscale', 'factor': 2}], ctx)
        self.assertEqual(ctx.notes[-1], 'enlarged 2x to 600x400 (sharpened; no new detail is invented)')
        self.assertEqual(self.calls, [])

    def test_switched_off_the_plain_method_is_used_and_the_switch_is_named(self):
        self.m._n94_put('studio_ai', 'off')
        ctx = self.m._N90Ctx(OWNER_ID)
        self.m._n90_apply_ops(png_bytes(photo(300, 200)), [{'op': 'upscale', 'factor': 2}], ctx)
        self.assertEqual(self.calls, [])
        self.assertIn('AI enlarging is switched off (“studio ai on” turns it on)', ctx.notes[-1])

    def test_when_the_server_is_short_of_memory_the_old_method_gives_the_picture_anyway(self):
        self.child_error = self.m._N92Err('low_memory', 'I am low on memory right now (1.1 GB available; this needs about 450 MB plus a safety margin), so I did not start it.')
        ctx = self.m._N90Ctx(OWNER_ID)
        im = self.m._n90_apply_ops(png_bytes(photo(300, 200)), [{'op': 'upscale', 'factor': 2}], ctx)
        self.assertEqual(im.size, (600, 400))
        self.assertIn('plain method used: I am low on memory right now', ctx.notes[-1])
        self.assertEqual(self.m._N94_STATS['upscale_fallback'], 1)
        self.assertEqual(self.leftover_jobs(), [])

    def test_a_crash_in_the_helper_is_a_fallback_not_an_error(self):
        self.child_error = RuntimeError('boom')
        im = self.m._n90_op_upscale(photo(300, 200), 2)
        self.assertEqual(im.size, (600, 400))
        self.assertIn('the AI enlarger failed (RuntimeError)', self.m._n94_upscale_note(2, im.size))

    def test_the_missing_system_libraries_message_reaches_the_note(self):
        self.child_error = self.m._N92Err('system_libs', 'The AI enlarger needs two system libraries that are not on this server. Say “forge apt allow libomp5 libvulkan1” and then “forge apt libomp5 libvulkan1”.')
        self.m._n90_op_upscale(photo(300, 200), 2)
        self.assertIn('forge apt allow libomp5 libvulkan1', self.m._n94_upscale_note(2, (600, 400)))

    def test_a_helper_answer_of_the_wrong_size_is_corrected_to_the_exact_size(self):
        self.esrgan_size = (599, 399)
        self.assertEqual(self.m._n90_op_upscale(photo(300, 200), 2).size, (600, 400))

    def test_a_picture_with_transparency_keeps_it(self):
        im = photo(200, 100).convert('RGBA')
        a = Image.new('L', im.size, 255)
        ImageDraw.Draw(a).rectangle((0, 0, 100, 50), fill=0)
        im.putalpha(a)
        out = self.m._n90_op_upscale(im, 2)
        self.assertEqual(out.mode, 'RGBA')
        self.assertEqual(out.size, (400, 200))
        self.assertEqual(out.getchannel('A').getpixel((10, 10)), 0)
        self.assertEqual(out.getchannel('A').getpixel((390, 190)), 255)

    def test_the_job_folder_is_private_and_removed_afterwards(self):
        self.m._n90_op_upscale(photo(300, 200), 2)
        c = self.calls[0]
        self.assertTrue(os.path.basename(c['job']).startswith('J92-'))
        self.assertFalse(os.path.exists(c['job']))
        self.assertEqual(self.leftover_jobs(), [])

    def test_the_limits_of_the_bot_stay_in_force_before_any_ai(self):
        with self.assertRaises(self.m._N90Fail) as cm:
            self.m._n90_op_upscale(photo(2500, 2000), 4)
        self.assertEqual(cm.exception.code, 'too_big')
        self.assertEqual(self.calls, [])

    def test_the_note_of_a_second_picture_is_not_polluted_by_the_first(self):
        self.m._n90_op_upscale(photo(300, 200), 2)
        self.assertTrue(self.m._N94_UP.ai)
        self.have.clear()
        self.start(self.m, '_n91_ledger_find', lambda name: None)
        self.m._n90_op_upscale(photo(300, 200), 2)
        self.assertFalse(self.m._N94_UP.ai)
        self.assertNotIn('Real-ESRGAN', self.m._n94_upscale_note(2, (600, 400)))

    def test_the_two_programs_have_the_models_and_limits_that_were_measured(self):
        self.assertEqual(self.m._N94_AI_LIMITS, {2: (1280, 450, 180), 4: (320, 2000, 240)})
        self.assertEqual(self.m._N94_ESRGAN_MODEL, {2: 0, 4: 4})
        self.assertIn('process_pil', self.m._N94_PROG_ESRGAN)
        self.assertIn('gpuid=-1', self.m._N94_PROG_ESRGAN)


# ===================================================================================================================
# 3. BACKGROUND REMOVAL WITH NO KEY
# ===================================================================================================================
@needs_pil
class TestBackgroundRemoval(PlusCase):
    def remove(self, im):
        ctx = self.m._N90Ctx(OWNER_ID)
        out = self.m._n90_remove_background(im, png_bytes(im), ctx)
        return out, ctx

    def test_a_plain_background_is_cut_out_by_colour_first_with_no_ai_started(self):
        out, ctx = self.remove(photo(300, 200, plain=True))
        self.assertEqual(self.calls, [])
        self.assertIn('plain-background cut-out', ctx.removed_with)
        self.assertEqual(out.mode, 'RGBA')

    def test_a_busy_background_goes_to_the_ai_model_and_says_so(self):
        out, ctx = self.remove(photo(300, 200))
        self.assertEqual(len(self.calls), 1)
        self.assertIn('rembg AI model (silueta), run on this server, no key needed', ctx.removed_with)
        self.assertEqual(out.mode, 'RGBA')
        self.assertEqual(out.getchannel('A').getpixel((150, 100)), 255)
        self.assertEqual(out.getchannel('A').getpixel((2, 2)), 0)
        self.assertEqual(self.m._N94_STATS['rembg'], 1)
        c = self.calls[0]
        self.assertEqual((c['need'], c['timeout']), (1100, 150))
        self.assertEqual(self.leftover_jobs(), [])

    def test_the_paid_service_is_only_the_last_resort(self):
        self.have.clear()
        self.start(self.m, '_n91_ledger_find', lambda name: None)
        calls = []
        self.start(self.m, '_n90_removebg_api', lambda raw: calls.append(1) or png_bytes(photo(300, 200)))
        out, ctx = self.remove(photo(300, 200))
        self.assertEqual(ctx.removed_with, 'remove.bg')
        self.assertEqual(self.calls, [])
        self.assertEqual(calls, [1])

    def test_ai_first_so_the_paid_service_is_not_called_when_the_ai_works(self):
        calls = []
        self.start(self.m, '_n90_removebg_api', lambda raw: calls.append(1) or None)
        self.remove(photo(300, 200))
        self.assertEqual(calls, [])

    def test_no_ai_and_no_key_still_refuses_a_busy_background_the_old_way(self):
        self.have.clear()
        self.start(self.m, '_n91_ledger_find', lambda name: None)
        self.start(self.m, '_n90_removebg_api', lambda raw: None)
        with self.assertRaises(self.m._N90Fail) as cm:
            self.remove(photo(300, 200))
        self.assertEqual(cm.exception.code, 'busy_background')

    def test_low_memory_falls_through_to_the_next_option(self):
        self.child_error = self.m._N92Err('low_memory', 'low')
        self.start(self.m, '_n90_removebg_api', lambda raw: None)
        with self.assertRaises(self.m._N90Fail):
            self.remove(photo(300, 200))
        self.assertEqual(self.m._N94_STATS['rembg_fallback'], 1)
        self.assertEqual(self.m._N94_UP.rembg_reason, 'low')

    def test_switched_off_the_ai_is_not_started(self):
        self.m._n94_put('studio_ai', 'off')
        self.start(self.m, '_n90_removebg_api', lambda raw: None)
        with self.assertRaises(self.m._N90Fail):
            self.remove(photo(300, 200))
        self.assertEqual(self.calls, [])

    def test_a_crash_is_a_fallback(self):
        self.child_error = ValueError('x')
        self.assertIsNone(self.m._n90_remove_bg_rembg(photo(300, 200)))

    def test_the_program_works_on_a_small_copy_so_memory_stays_the_same_for_a_big_photo(self):
        src = self.m._N94_PROG_REMBG
        self.assertIn("new_session('silueta')", src)
        self.assertIn('only_mask=True', src)
        self.assertIn('thumbnail((1024, 1024))', src)
        self.assertIn('putalpha', src)

    def test_it_is_not_imported_into_the_bot(self):
        tree = ast.parse(clear_source())
        for n in ast.walk(tree):
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in n.names] + [getattr(n, 'module', '') or '']
                for x in names:
                    self.assertFalse(x.split('.')[0] in ('rembg', 'realesrgan_ncnn_py', 'onnxruntime', 'nselib', 'arch', 'exchange_calendars', 'pandas', 'numpy'), x)


# ===================================================================================================================
# 4. A CHART UNDER EVERY SCOUT IDEA
# ===================================================================================================================
def candles(n=80, base=2800.0, slope=1.5):
    return T.wavy(n=n, base_px=base, slope=slope, amp=60.0, noise=15.0, seed=2)


def stock_idea(entry=2860.0):
    return {'id': 'SC93-ABC123', 'kind': 'stock', 'symbol': 'RELIANCE', 'side': 'LONG', 'setup': 'BREAKOUT', 'score': 78, 'entry': entry, 'entry_hi': entry + 12.0, 'stop': entry - 70.0, 't1': entry + 110.0, 't2': entry + 190.0}


@needs_pil
class TestChartDrawing(PlusCase):
    def draw(self, idea=None, cs=None):
        raw = self.m._n94_chart_png(idea or stock_idea(), cs if cs is not None else candles())
        return raw, (Image.open(io.BytesIO(raw)).convert('RGB') if raw else None)

    def colours(self, im):
        return set(im.getdata())

    def test_it_is_a_png_of_a_good_size_for_a_phone(self):
        raw, im = self.draw()
        self.assertEqual(raw[:8], b'\x89PNG\r\n\x1a\n')
        self.assertEqual(im.size, (1000, 580))
        self.assertLess(len(raw), 200 * 1024)

    def test_the_levels_are_drawn_in_their_colours(self):
        _raw, im = self.draw()
        cols = self.colours(im)
        for name, c in (('stop', (200, 40, 40)), ('target', (30, 150, 70)), ('entry', (30, 90, 200)), ('average', (240, 150, 30)), ('zone', (222, 234, 252))):
            self.assertIn(c, cols, name)

    def test_the_stop_line_sits_below_the_entry_and_the_target_above(self):
        _raw, im = self.draw()
        px = im.load()
        rows = {}
        for y in range(70, 520):
            for x in range(852, 1000):            # the labels in the right margin: candles never reach it
                p = px[x, y]
                if p == (200, 40, 40):
                    rows.setdefault('stop', []).append(y)
                elif p == (30, 90, 200):
                    rows.setdefault('entry', []).append(y)
                elif p == (30, 150, 70):
                    rows.setdefault('target', []).append(y)
        self.assertGreater(min(rows['stop']), min(rows['entry']), 'a long idea: the stop is drawn lower (larger y) than the entry')
        self.assertLess(min(rows['target']), min(rows['entry']), 'and the targets higher')

    def test_a_short_idea_draws_the_stop_above(self):
        idea = dict(stock_idea(), side='SHORT', entry=2860.0, entry_hi=2848.0, stop=2930.0, t1=2750.0, t2=2670.0)
        _raw, im = self.draw(idea)
        px = im.load()
        stop_rows = [y for y in range(70, 520) for x in range(852, 1000) if px[x, y] == (200, 40, 40)]
        entry_rows = [y for y in range(70, 520) for x in range(852, 1000) if px[x, y] == (30, 90, 200)]
        self.assertTrue(stop_rows and entry_rows)
        self.assertLess(min(stop_rows), min(entry_rows))

    def test_the_level_labels_are_drawn_in_the_right_margin(self):
        _raw, im = self.draw()
        px = im.load()
        right = [(x, y) for x in range(850, 1000) for y in range(70, 520) if px[x, y] != (255, 255, 255)]
        self.assertGreater(len(right), 150, 'text for Entry, Stop, T1, T2')

    def test_an_option_idea_is_drawn_on_the_index_with_its_levels(self):
        idea = {'id': 'SC93-OPT001', 'kind': 'option', 'symbol': 'NIFTY', 'side': 'BULL CALL SPREAD', 'setup': 'INDEX_SPREAD', 'score': 71, 'entry': 24490.0, 'stop': 24300.0, 't1': 24700.0, 't2': 24850.0}
        raw, im = self.draw(idea, candles(base=24000.0, slope=6.0))
        self.assertIsNotNone(raw)
        self.assertIn((200, 40, 40), self.colours(im))

    def test_a_missing_second_target_or_zone_is_fine(self):
        idea = stock_idea()
        idea.pop('t2')
        idea.pop('entry_hi')
        raw, im = self.draw(idea)
        self.assertIsNotNone(raw)
        self.assertNotIn((222, 234, 252), self.colours(im))

    def test_too_few_candles_give_no_chart(self):
        self.assertIsNone(self.m._n94_chart_png(stock_idea(), candles(10)))
        self.assertIsNone(self.m._n94_chart_png(stock_idea(), []))
        self.assertIsNone(self.m._n94_chart_png(stock_idea(), None))

    def test_candles_with_missing_fields_are_skipped_not_fatal(self):
        cs = candles(60)
        cs[5] = {'ts': 1}
        self.assertIsNotNone(self.m._n94_chart_png(stock_idea(), cs))

    def test_a_level_far_outside_the_candles_still_fits_the_picture(self):
        idea = dict(stock_idea(), t2=9000.0, stop=100.0)
        raw, im = self.draw(idea)
        self.assertIsNotNone(raw)

    def test_the_footer_says_it_is_not_advice(self):
        _raw, im = self.draw()
        px = im.load()
        footer = sum(1 for x in range(70, 900) for y in range(550, 575) if px[x, y] != (255, 255, 255))
        self.assertGreater(footer, 200)

    def test_the_average_is_an_ema(self):
        e = self.m._n94_ema([1.0, 2.0, 3.0, 4.0], 3)
        self.assertEqual(e[0], 1.0)
        self.assertAlmostEqual(e[1], 1.5)
        self.assertAlmostEqual(e[2], 2.25)

    def test_without_pillow_there_is_no_chart_and_no_error(self):
        self.start(self.m, '_n90_pil', lambda: None)
        self.assertIsNone(self.m._n94_chart_png(stock_idea(), candles()))


@needs_pil
class TestChartsInScouting(IntelCase):
    def setUp(self):
        super().setUp()
        self.events = []
        self.start(self.m, '_n90_send_image', lambda cid, raw, name, caption='', kb=None, force_file=False: self.events.append(('chart', name, caption)) or self.charts.append((name, caption, len(raw))) or True)
        real_say = self.m._n91_say
        self.start(self.m, '_n91_say', lambda cid, text, kb=None: self.events.append(('text', text)) or real_say(cid, text, kb))

    def scan(self):
        self.world(stocks=('TCS',))
        self.nse['events']['rows'][1]['date'] = '16-Oct-2026'
        return self.say('trade ideas')

    def test_each_issued_idea_gets_its_chart_right_after_its_card(self):
        out = self.scan()
        issued = [r[0] for r in self.saved()]
        self.assertTrue(issued, out[-1200:])
        self.assertEqual(len(self.charts), len(issued))
        order = [e for e in self.events if (e[0] == 'text' and 'IDEA SC93-' in e[1]) or e[0] == 'chart']
        for i in range(0, len(order), 2):
            self.assertEqual(order[i][0], 'text')
            self.assertEqual(order[i + 1][0], 'chart')
            iid = re.search(r'IDEA (SC93-[0-9A-F]{6})', order[i][1]).group(1)
            self.assertEqual(order[i + 1][1], 'scout-%s.png' % iid)

    def test_the_caption_names_the_side_and_the_symbol(self):
        self.scan()
        self.assertTrue(any('LONG TCS: levels on the daily chart' in c[1] for c in self.charts), self.charts)

    def test_a_watch_that_is_not_an_idea_gets_no_chart(self):
        self.world(stocks=('TCS',), news=False)
        self.say('trade ideas')
        self.assertEqual(self.charts, [])

    def test_charts_can_be_switched_off_and_on(self):
        self.assertIn('Charts under Scout ideas are OFF', self.say('scout charts off'))
        self.scan()
        self.assertEqual(self.charts, [])
        self.assertIn('Charts under Scout ideas are ON', self.say('scout charts on'))
        self.events.clear()
        self.scan()
        self.assertTrue(self.charts)

    def test_a_chart_that_cannot_be_drawn_never_stops_the_scan(self):
        self.start(self.m, '_n94_chart_png', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('draw failed')))
        out = self.scan()
        self.assertIn('IDEA SC93-', out)
        self.assertEqual(self.charts, [])
        self.assertGreaterEqual(self.m._N94_STATS['chart_failed'], 1)

    def test_a_chart_on_demand_for_an_older_idea(self):
        self.scan()
        iid = self.saved()[0][0]
        self.charts.clear()
        self.assertEqual(self.say('scout chart %s' % iid), '')
        self.assertEqual(len(self.charts), 1)
        self.assertEqual(self.charts[0][0], 'scout-%s.png' % iid)
        self.charts.clear()
        self.say('chart ' + iid)
        self.assertEqual(len(self.charts), 1)

    def test_an_unknown_idea_is_said(self):
        out = self.say('scout chart SC93-AAAAAA')
        self.assertIn('I do not have an idea called SC93-AAAAAA', out)

    def test_the_drawing_failing_on_demand_is_said_with_the_way_out(self):
        self.scan()
        iid = self.saved()[0][0]
        self.start(self.m, '_n94_chart_png', lambda *a, **k: None)
        out = self.say('scout chart %s' % iid)
        self.assertIn('I could not draw the chart for %s' % iid, out)
        self.assertIn('scout show %s' % iid, out)

    def test_a_guest_cannot_ask_for_a_chart(self):
        n = len(self.passed)
        self.m.handle(self.guest('scout chart SC93-AAAAAA'))
        self.assertEqual(len(self.passed), n + 1)
        self.assertEqual(self.charts, [])

    def test_an_options_idea_gets_a_chart_of_the_index(self):
        self.nse['flows'] = {'ok': True, 'fii_stats': None, 'part_oi': None}
        self.world()
        self.say('scout nifty')
        self.assertTrue(any('NIFTY' in c[1] for c in self.charts), self.charts)


# ===================================================================================================================
# 5. STATUS, SWITCHES AND WIRING
# ===================================================================================================================
class TestWiringAndStatus(IntelCase):
    def test_studio_status_gains_the_studio_plus_lines(self):
        self.have.clear()
        self.start(self.m, '_n91_ledger_find', lambda name: None)
        out = self.m._n90_status_text(self.cid)
        self.assertIn('Studio+ (v94):', out)
        self.assertIn('❌ AI enlarging (Real-ESRGAN): not installed: say “install realesrgan-ncnn-py into yourself”', out)
        self.assertIn('forge apt allow libomp5 libvulkan1', out)
        self.assertIn('❌ AI background removal (rembg, no key needed): not installed: say “install rembg”', out)
        self.assertIn('✅ Charts under Scout ideas: on', out)
        self.assertIn('AI tools switch: ON', out)
        self.start(self.m, '_n92_have', lambda mod: True)
        out = self.m._n90_status_text(self.cid)
        self.assertIn('✅ AI enlarging (Real-ESRGAN): ready for 2x (up to 1280 px) and 4x (up to 320 px)', out)
        self.assertIn('✅ AI background removal (rembg, no key needed): ready', out)

    def test_the_ai_switch(self):
        self.assertIn('Studio AI tools are OFF', self.say('studio ai off'))
        self.assertFalse(self.m._n94_ai_enabled())
        self.assertIn('AI tools switch: OFF', self.m._n94_studio_plus_text())
        self.assertIn('Studio AI tools are ON', self.say('studio ai on'))
        self.assertTrue(self.m._n94_ai_enabled())
        n = len(self.passed)
        self.m.handle(self.guest('studio ai off'))
        self.assertEqual(len(self.passed), n + 1)
        self.assertTrue(self.m._n94_ai_enabled())

    def test_capabilities_status_abilities_and_commands(self):
        caps = self.m._n82_capabilities()
        for part in ('Clear 94:', '“what is PCR”', '“guide”', 'Scout intel', '“ban list”', 'Studio+ adds AI enlarging'):
            self.assertIn(part, caps)
        st = self.m._n83_status_text(self.cid)
        self.assertIn('CLEAR 94: market replies in words 0', st)
        self.assertIn('plain words on', st)
        rows = {r[1]: r for r in self.m._n88_abilities(self.cid)}
        self.assertIn('Plain words', rows)
        self.assertIn('Scout intel (NSE)', rows)
        self.assertIn('AI enlarge and cut-out', rows)
        self.assertEqual(rows['Scout intel (NSE)'][2], 'ready')
        self.have.discard('nselib')
        self.assertEqual({r[1]: r for r in self.m._n88_abilities(self.cid)}['Scout intel (NSE)'][2], 'needs install')
        names = [c[0] for c in self.m._N40_COMMANDS]
        self.assertIn('guide', names)
        self.assertIn('plain', names)

    def test_the_regression_rows_all_pass_and_are_added_to_the_suite(self):
        rows = self.m._n94_regression_rows()
        self.assertEqual(len(rows), 8)
        self.assertEqual([r['name'] for r in rows if not r['ok']], [])
        self.assertTrue(all(r['name'].startswith('v94-') for r in rows))
        self.assertIsNot(self.m.prime_regression_suite, self.m._N94_REG_PREV)
        suite = self.m.prime_regression_suite()
        self.assertTrue(any(t['name'] == 'v94-chain-in-words' for t in suite['tests']))

    def test_the_hooks_are_installed_and_the_version_moved(self):
        self.assertIsNot(self.m.handle, self.m._N94_HANDLE_PREV)
        self.assertIsNot(self.m.main, self.m._N94_MAIN_PREV)
        self.assertIsNot(self.m._n55_trim_result, self.m._N94_TRIM_PREV)
        self.assertIsNot(self.m._n93_eval_stock, self.m._N94_EVAL_PREV)
        self.assertIsNot(self.m._n93_option_plan, self.m._N94_PLAN_PREV)
        self.assertIsNot(self.m._n93_bias_parts, self.m._N94_PARTS_PREV)
        self.assertIsNot(self.m._n93_card, self.m._N94_CARD_PREV)
        self.assertIsNot(self.m._n93_scan, self.m._N94_SCAN_PREV)
        self.assertGreaterEqual(float(self.m.VERSION), 94.0)

    def test_boot_opens_the_settings_table(self):
        calls = []
        self.start(self.m, '_N94_MAIN_PREV', lambda *a, **k: calls.append('main') or 'ok')
        self.assertEqual(self.m.main(), 'ok')
        self.assertEqual(calls, ['main'])
        names = {r[0] for r in self.m._n94_q("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn('clear94_setting', names)

    def test_an_error_while_starting_never_stops_the_bot(self):
        self.start(self.m, '_N94_MAIN_PREV', lambda *a, **k: 'ok')
        self.start(self.m, '_n94_db', lambda: (_ for _ in ()).throw(RuntimeError('x')))
        self.assertEqual(self.m.main(), 'ok')
        self.assertEqual(self.m._N94_STATS['errors'], 1)

    def test_the_new_layer_is_protected_from_live_self_editing(self):
        src = open(base.NEMO_FILE, encoding='utf-8').read()
        self.assertIn("'_n93_','_n94_'", src)
        for name in ('_n94_clear_market', '_n94_job', '_n94_child_py', '_n94_front', '_n94_chart_png', '_n94_dejson'):
            self.assertFalse(self.m._n79_editable(name), name)

    def test_the_only_edits_to_older_code_are_the_listed_ones(self):
        src = open(base.NEMO_FILE, encoding='utf-8').read()
        self.assertIn('v94.0 - CLEAR + SCOUT INTEL + STUDIO PLUS', src[:3500])
        self.assertEqual(src.count('_n94_fill_iv_rows(flat,spot,days)'), 1)
        self.assertEqual(src.count('_n94_upscale_note(op[\'factor\'], im.size)'), 1)
        self.assertEqual(src.count('\n            _n94_chart_after(cid, i)\n'), 2)
        self.assertEqual(src.count('_il = _n94_scan_line(cand, idx)'), 1)
        self.assertEqual(src.count("solved = solved or int(ch.get('iv_solved') or 0)"), 1)

    def test_the_trading_holiday_guard_and_the_owner_lock_are_exactly_as_they_were(self):
        before = dict(self.m._N81_HOLIDAYS_2026)
        self.assertEqual(len(before), 17)
        src = clear_source()
        self.assertNotIn('_N81_HOLIDAYS_2026[', src)
        self.assertNotIn("OWNER['", src)


# ===================================================================================================================
# 6. STRUCTURE: the layer can never place an order, touch the trading agent, the guards, the owner lock or the credentials
# ===================================================================================================================
class TestStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if base.m is None:
            base.setUpModule()
        cls.src = clear_source()
        cls.tree = ast.parse(cls.src)

    def names(self):
        out = set()
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Name):
                out.add(n.id)
            elif isinstance(n, ast.Attribute):
                out.add(n.attr)
        return out

    def calls(self):
        out = set()
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Call):
                f = n.func
                parts = []
                while isinstance(f, ast.Attribute):
                    parts.append(f.attr)
                    f = f.value
                if isinstance(f, ast.Name):
                    parts.append(f.id)
                out.add('.'.join(reversed(parts)))
        return out

    def test_no_order_function_and_no_trading_agent_is_ever_named(self):
        used = self.names()
        for bad in ('fyers_place', 'fyers_place_bracket', '_order_send', 'request_order', 'place_order', 'auto_trade_tick', 'ai_decide', 'godmode_analyze', 'TradeLab75', 'BROKER', 'can_enter', 'must_square_off',
                    'save_secret', 'mm_locked', '_n81_paused', '_n81_entry_quote', '_n75_quote', 'live_ltp', 'fyers_ltp', 'fyers_data', 'fyers_login', 'fyers_ready', 'AUTOLOG', 'AUTO', 'OWNER', 'NVIDIA_KEY', '_n90_secret'):
            self.assertNotIn(bad, used, bad)
        for n in used:
            self.assertNotIn('fyers', n.lower(), n)

    def test_the_holiday_table_is_only_read(self):
        for n in ast.walk(self.tree):
            if isinstance(n, (ast.Assign, ast.AugAssign, ast.Delete)):
                targets = n.targets if isinstance(n, (ast.Assign, ast.Delete)) else [n.target]
                for t in targets:
                    if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id.startswith('_N81'):
                        self.fail('the layer writes the holiday table')
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id == '_N81_HOLIDAYS_2026':
                self.assertEqual(n.func.attr, 'get')

    def test_the_only_program_that_is_started_is_the_one_inside_the_runner(self):
        calls = self.calls()
        for bad in ('_n91_sp.run', '_n91_sp.Popen', 'subprocess.run', 'subprocess.Popen', 'os.system', '_n91_os.system', '_n91_os.popen', 'eval', 'exec', 'compile', '__import__'):
            self.assertNotIn(bad, calls, bad)
        self.assertEqual(len([n for n in ast.walk(self.tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == '_n91_run']), 1)
        for node in ast.walk(self.tree):
            if isinstance(node, ast.keyword) and node.arg == 'shell':
                self.fail('shell= is never used')
        self.assertEqual([c for c in calls if c.startswith('requests.')], [])

    def test_the_helpers_get_a_clean_environment_and_are_never_given_a_key(self):
        text = self.src
        self.assertIn('_n91_env(', text)
        for bad in ('NVIDIA_KEY', 'TELEGRAM', 'os.environ', '_n91_os.environ', 'getenv', 'FYERS'):
            self.assertNotIn(bad, text, bad)

    def test_the_helper_programs_are_plain_strings_with_no_network_of_their_own(self):
        for name in ('_N94_PROG', '_N94_PROG_ESRGAN', '_N94_PROG_REMBG'):
            prog = next(n.value.value for n in self.tree.body if isinstance(n, ast.Assign) and n.targets[0].id == name)
            ast.parse(prog)
            for bad in ('requests', 'urllib', 'socket', 'subprocess', 'os.system', 'eval(', 'exec('):
                self.assertNotIn(bad, prog, name + ' ' + bad)
            self.assertIsNone(re.search(r'(?<![.\w])open\(', prog), name + ' opens a file by itself')

    def test_the_layer_only_sends_to_the_owner_or_to_the_callers_own_chat(self):
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ('send_text', '_n91_say', '_n90_send_image', '_N94_SEND_PREV'):
                first = ast.unparse(n.args[0]) if n.args else ''
                self.assertIn(first, ('cid', 'chat_id'), first)

    def test_all_layer_names_use_the_v94_prefix(self):
        defined = {n.name for n in self.tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        odd = [d for d in defined if not (d.startswith('_n94_') or d.startswith('_N94')) and d not in ('handle', '_n82_capabilities', '_n83_status_text', '_n88_abilities', 'prime_regression_suite', 'main', 'send_text',
                                                                                                     '_n55_trim_result', '_n90_status_text', '_n93_eval_stock', '_n93_bias_parts', '_n93_option_plan', '_n93_card',
                                                                                                     '_n93_scan', '_n93_symbol_job', '_n90_op_upscale', '_n90_remove_bg_rembg', '_n90_remove_background')]
        self.assertEqual(odd, [])

    def test_every_replaced_function_keeps_the_old_one_as_its_fallback_or_is_a_marked_replacement(self):
        for fn, prev in (('handle', '_N94_HANDLE_PREV'), ('send_text', '_N94_SEND_PREV'), ('_n55_trim_result', '_N94_TRIM_PREV'), ('_n83_status_text', '_N94_STATUS_PREV'), ('_n82_capabilities', '_N94_CAPS_PREV'),
                         ('_n88_abilities', '_N94_ABIL_PREV'), ('prime_regression_suite', '_N94_REG_PREV'), ('main', '_N94_MAIN_PREV'), ('_n93_eval_stock', '_N94_EVAL_PREV'), ('_n93_card', '_N94_CARD_PREV'),
                         ('_n93_scan', '_N94_SCAN_PREV'), ('_n93_option_plan', '_N94_PLAN_PREV'), ('_n93_bias_parts', '_N94_PARTS_PREV'), ('_n90_status_text', '_N94_STUDIO_STATUS_PREV')):
            self.assertIn('%s = %s\n' % (prev, fn), self.src, fn)

    def test_the_wrappers_of_scout_do_not_change_what_scout_places_or_decides(self):
        # the only things they touch on an idea are its score (by the stated penalties), its bad/good lists, its flags and its intel lines
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id in ('idea', 'plan'):
                        key = ast.unparse(t.slice)
                        self.assertIn(key, ("'score'", "'band'", "'comps'", "'intel'", "'intel_checked'"), key)
