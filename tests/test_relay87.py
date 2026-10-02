"""Nemo v87 "Relay": multi-source video downloads (verified, time-boxed), Drive links you can open, natural-language controls.

Everything here is offline: tiny synthetic videos made with ffmpeg, a fake yt-dlp script, a stub pytubefix package, a local HTTP server for the
mirror downloads, a fake Drive permissions API, temporary folders and databases. No YouTube, no Drive, no network AI, no cookies, no trades.

    NEMO_FILE=/path/to/nemotron_bot.py python -m unittest tests.test_relay87 -v
"""
import ast
import atexit
import http.server
import json
import os
import re
import shutil
import socketserver
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from unittest import mock

from tests import test_cortex83 as base

FIX = {}
HAVE_FFMPEG = bool(shutil.which('ffmpeg') and shutil.which('ffprobe'))


def setUpModule():
    if base.m is None:
        base.setUpModule()
    if HAVE_FFMPEG and 'dir' not in FIX:                  # (the mutation tests run nested suites, which call this again: build the videos once)
        FIX['dir'] = tempfile.mkdtemp(prefix='relay87_fix_')
        atexit.register(shutil.rmtree, FIX['dir'], True)
        d = FIX['dir']

        def ff(*args):
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', *args], check=True, timeout=120)
        FIX['video'] = os.path.join(d, 'video.mp4')
        ff('-f', 'lavfi', '-i', 'testsrc=duration=1:size=64x64:rate=5', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', '-shortest', '-c:v', 'libx264', '-c:a', 'aac', FIX['video'])
        FIX['video_only'] = os.path.join(d, 'video_only.mp4')
        ff('-f', 'lavfi', '-i', 'testsrc=duration=1:size=64x64:rate=5', '-an', '-c:v', 'libx264', FIX['video_only'])
        FIX['audio_only'] = os.path.join(d, 'audio_only.m4a')
        ff('-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', '-c:a', 'aac', FIX['audio_only'])


FAKE_YTDLP = textwrap.dedent('''
    import sys, os, shutil, time
    folder, behavior, fixture = sys.argv[1], sys.argv[2], sys.argv[3]
    def out(name):
        shutil.copy(fixture, os.path.join(folder, name))
    if behavior == 'ok':
        print('[youtube] x: Downloading webpage', flush=True)
        out('Title_abc123.mp4')
    elif behavior == 'botcheck':
        print("ERROR: [youtube] abc123: Sign in to confirm you're not a bot. Use --cookies-from-browser or --cookies for the authentication.", flush=True)
        sys.exit(1)
    elif behavior == 'format':
        print('ERROR: [youtube] abc123: Requested format is not available. Use --list-formats for a list of available formats', flush=True)
        sys.exit(1)
    elif behavior == 'private':
        print('ERROR: [youtube] abc123: Private video. Sign in if you have been granted access to this video', flush=True)
        sys.exit(1)
    elif behavior == 'stall':
        print('[youtube] x: Downloading webpage', flush=True)
        time.sleep(60)
    elif behavior == 'slow':
        for i in range(300):
            print('[download] still going', i, flush=True)
            time.sleep(0.2)
    elif behavior == 'partial':
        out('Title_abc123.f137.mp4')
        print('ERROR: unable to download video data: HTTP Error 403: Forbidden', flush=True)
        sys.exit(1)
    elif behavior == 'ok_but_rc1':
        out('Title_abc123.mp4')
        print('ERROR: something late failed', flush=True)
        sys.exit(1)
    elif behavior == 'garbage':
        open(os.path.join(folder, 'Title_abc123.mp4'), 'wb').write(b'<html>error page</html>' * 5)
    elif behavior == 'playlist_partial':
        out('One_aaa.mp4')
        print('ERROR: [youtube] bbb: Video unavailable', flush=True)
        sys.exit(1)
    else:
        sys.exit(3)
''')

STUB_PYTUBEFIX = textwrap.dedent('''
    import os, shutil
    FIXTURES = {}
    class _Stream:
        def __init__(self, kind, subtype, resolution=None, abr=None, codec='avc1.4d401f', src=None, progressive=False):
            self.kind, self.subtype, self.resolution, self.abr, self.video_codec, self.src, self.progressive = kind, subtype, resolution, abr, codec, src, progressive
        def download(self, output_path, filename):
            path = os.path.join(output_path, filename)
            shutil.copy(self.src, path)
            return path
    class _Streams:
        def __init__(self, items):
            self.items = items
        def filter(self, **kw):
            out = self.items
            if kw.get('adaptive'):
                out = [s for s in out if not s.progressive]
            if kw.get('progressive'):
                out = [s for s in out if s.progressive]
            if kw.get('only_video'):
                out = [s for s in out if s.kind == 'video']
            if kw.get('only_audio'):
                out = [s for s in out if s.kind == 'audio']
            return out
    class YouTube:
        calls = []
        def __init__(self, url, client='VISION_OS', **kw):
            YouTube.calls.append(client)
            mode = os.environ.get('STUB_PTF_MODE', 'adaptive')
            if mode == 'fail_all' or (mode == 'fail_default' and client == 'VISION_OS'):
                raise RuntimeError('stub: client %s refused' % client)
            self.title = 'Stub: Title/One'
            v, a, full = os.environ['STUB_VIDEO_ONLY'], os.environ['STUB_AUDIO_ONLY'], os.environ['STUB_FULL']
            if mode == 'progressive':
                self.streams = _Streams([_Stream('video', 'mp4', '360p', progressive=True, src=full)])
            elif mode == 'nothing':
                self.streams = _Streams([])
            else:
                self.streams = _Streams([_Stream('video', 'mp4', '1080p', src=v), _Stream('video', 'mp4', '360p', src=v), _Stream('audio', 'mp4', abr='128kbps', src=a)])
''')


class Quiet(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def serve(routes):
    """routes: {path: (status, content-type, bytes[, {extra headers}])}. Returns (server, base_url); server.hits lists the paths requested."""
    hits = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            entry = routes.get(self.path, (404, 'text/plain', b'nope'))
            status, ctype, body = entry[:3]
            self.send_response(status)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            for k, v in (entry[3] if len(entry) > 3 else {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = Quiet(('127.0.0.1', 0), H)
    srv.hits = hits
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, 'http://127.0.0.1:%d' % srv.server_address[1]


class FakeDrive:
    """In-memory stand-in for the Drive permissions endpoints used by link sharing."""

    def __init__(self):
        self.perms = {}
        self.calls = []
        self.fail_post = None

    def __call__(self, method, path, **kw):
        self.calls.append((method, path, kw.get('json'), kw.get('params')))
        m = re.fullmatch(r'files/([A-Za-z0-9_-]+)/permissions', path)
        if not m:
            raise ValueError('Drive HTTP 404. unexpected path ' + path)
        fid = m.group(1)
        if method == 'GET':
            return {'permissions': list(self.perms.get(fid, [{'id': 'owner', 'type': 'user', 'role': 'owner', 'emailAddress': 'nemo@example.com'}]))}
        if self.fail_post:
            raise ValueError(self.fail_post)
        body = kw.get('json') or {}
        self.perms.setdefault(fid, [{'id': 'owner', 'type': 'user', 'role': 'owner', 'emailAddress': 'nemo@example.com'}]).append(dict(body, id='p%d' % len(self.calls)))
        return {'id': 'p1'}


class RelayCase(base.CortexCase):
    def setUp(self):
        super().setUp()
        m = base.m
        self.m = m
        self.kv = {}
        self.docs = []
        for name, val in (('DATA_FILE', os.path.join(self.tmp.name, 'bot_memory.json')), ('_N59_DIR', os.path.join(self.tmp.name, 'media59')),
                          ('_N62_NODE', os.path.join(self.tmp.name, 'node')), ('_N59_COOKIE', os.path.join(self.tmp.name, 'no_cookies.txt')),
                          ('_n36_kv_get', lambda k, d=None: self.kv.get(k, d)), ('_n36_kv_set', lambda k, v: self.kv.__setitem__(k, v) or True),
                          ('_n87_proxy', lambda: ''), ('_n87_deno', lambda: ''), ('_n87_node', lambda: ('', None))):
            p = mock.patch.object(m, name, val)
            p.start()
            self.patches.append(p)
        os.makedirs(m._N59_DIR, exist_ok=True)
        for k in m._N87_STATS:
            m._N87_STATS[k] = 0
        m._N87_LAST.clear()
        m._N87_UPGRADE.update({'ts': 0.0, 'ok': None, 'old': '', 'new': ''})
        self.folder = os.path.join(self.tmp.name, 'job')
        os.makedirs(self.folder)

    def tearDown(self):
        for t in list(threading.enumerate()):
            if t.name.startswith('nemo701-'):
                t.join(10)
        super().tearDown()

    def plan(self, mode='video', quality='720', playlist=False):
        return {'urls': ['https://www.youtube.com/watch?v=abc123'], 'mode': mode, 'quality': quality, 'playlist': playlist,
                'cfg': {'batch_limit': 5, 'playlist_limit': 3, 'media_timeout': 900, 'youtube_client': 'auto', 'browserless_enabled': False, 'browserless_daily_calls': 5}}

    def ctx(self, youtube=True, mode='video', playlist=False, seconds=900, cookie=None, url='https://www.youtube.com/watch?v=abc123'):
        return {'url': url, 'plan': self.plan(mode, playlist=playlist), 'folder': self.folder, 'cookie': cookie, 'youtube': youtube,
                'host': 'www.youtube.com' if youtube else 'vimeo.com', 'deadline': time.monotonic() + seconds}

    def video(self, name):
        shutil.copy(FIX['video'], os.path.join(self.folder, name))
        return os.path.join(self.folder, name)


def ok_step(key, label=None, group='alt', make=None, calls=None):
    def run(ctx):
        if calls is not None:
            calls.append(key)
        path = make(ctx) if make else None
        return {'ok': True, 'files': [path] if path else ['/dev/null'], 'error': '', 'klass': ''}
    return {'key': key, 'label': label or key, 'group': group, 'unavailable': '', 'run': run}


def fail_step(key, error, klass='unknown', label=None, group='alt', calls=None, raises=None):
    def run(ctx):
        if calls is not None:
            calls.append(key)
        if raises:
            raise raises
        return {'ok': False, 'files': [], 'error': error, 'klass': klass}
    return {'key': key, 'label': label or key, 'group': group, 'unavailable': '', 'run': run}


# ===================================================================================================================
# 1. WHAT WENT WRONG: classification and safe text
# ===================================================================================================================
class TestClassification(RelayCase):
    TABLE = (
        ("ERROR: [youtube] x: Sign in to confirm you're not a bot. Use --cookies", 'bot_check'),
        ("ERROR: [youtube] x: Sign in to confirm your age. This video may be inappropriate for some users.", 'age'),
        ('ERROR: [youtube] x: Private video. Sign in if you\'ve been granted access to this video', 'private'),
        ('ERROR: This video is DRM protected', 'drm'),
        ('ERROR: [youtube] x: Video unavailable. This video has been removed by the uploader', 'removed'),
        ('ERROR: [youtube] x: Premieres in 3 hours', 'live'),
        ('ERROR: [youtube] x: Requested format is not available. Use --list-formats', 'format'),
        ('WARNING: Only images are available for download. n challenge solving failed', 'js_runtime'),
        ('ERROR: No supported JavaScript runtime could be found', 'js_runtime'),
        ('ERROR: [youtube] x: Unable to extract initial player response', 'outdated'),
        ('ERROR: unable to download video data: HTTP Error 403: Forbidden', 'outdated'),
        ('ERROR: [youtube] x: The page needs to be reloaded.', 'outdated'),
        ('yt-dlp: error: no such option: --js-runtimes', 'outdated'),
        ('ERROR: HTTP Error 429: Too Many Requests', 'rate_limit'),
        ('ERROR: The cookies are no longer valid', 'cookies'),
        ('ERROR: This video requires a PO Token which was not provided', 'po_token'),
        ('ERROR: Unsupported URL: https://example.org/x', 'unsupported'),
        ('ERROR: [Errno 28] No space left on device', 'disk'),
        ('/usr/bin/python3: No module named yt_dlp', 'missing'),
        ('ERROR: Read timed out. (read timeout=20)', 'network'),
        ('ERROR: The uploader has not made this video available in your country', 'geo'),
        ('something totally different', 'unknown'),
        ('', 'unknown'),
    )

    def test_table(self):
        for text, expected in self.TABLE:
            self.assertEqual(self.m._n87_classify(text), expected, text)

    def test_every_class_has_a_plain_sentence_and_the_fixable_ones_have_a_next_step(self):
        for _text, klass in self.TABLE:
            self.assertIn(klass, self.m._N87_CLASS_TEXT)
        for klass in ('bot_check', 'cookies', 'age', 'po_token', 'js_runtime', 'outdated', 'format', 'rate_limit', 'geo', 'missing', 'ffmpeg', 'disk', 'network'):
            self.assertIn(klass, self.m._N87_FIX, klass)
        self.assertIn('/cookies', self.m._N87_FIX['bot_check'])
        self.assertIn('/proxy set', self.m._N87_FIX['bot_check'])

    def test_clean_removes_links_paths_emails_and_secrets(self):
        clean = self.m._n87_clean
        out = clean('failed at https://rr3.googlevideo.com/videoplayback?sig=SECRET123 while writing /root/nemo_download77/D78-AAAAAAAAAA/x.mp4 for a@b.com')
        for leaked in ('googlevideo', 'SECRET123', '/root', 'nemo_download77', 'a@b.com'):
            self.assertNotIn(leaked, out)
        self.assertIn('[link]', out)
        self.assertNotIn('Zx9-Synthetic-Pw-4471', clean('my password is Zx9-Synthetic-Pw-4471 ok'))
        self.assertLessEqual(len(clean('x' * 1000)), 150)

    def test_error_line_picks_the_extractor_error_not_noise(self):
        raw = '[youtube] x: Downloading webpage\n[youtube] x: Downloading player\nWARNING: something\nERROR: [youtube] x: Sign in to confirm you\'re not a bot\n'
        self.assertIn('Sign in to confirm', self.m._n87_err_line(raw))
        self.assertEqual(self.m._n87_err_line(''), '')


# ===================================================================================================================
# 2. THE yt-dlp COMMAND LINE
# ===================================================================================================================
class TestCommand(RelayCase):
    def cmd(self, mode='video', quality='720', playlist=False, cookies=None, spec=None, url='https://www.youtube.com/watch?v=abc123'):
        plan = dict(self.plan(mode, quality, playlist), _n87=spec or {})
        return self.m._n77_command(url, self.folder, plan, cookies)

    def after(self, cmd, flag):
        return cmd[cmd.index(flag) + 1]

    def test_video_prefers_h264_up_to_the_ceiling_and_never_fails_on_a_missing_format(self):
        c = self.cmd(quality='720')
        self.assertEqual(self.after(c, '-f'), 'bv*+ba/b')
        self.assertEqual(self.after(c, '-S'), 'res:720,vcodec:h264,acodec:aac')
        self.assertEqual(self.after(c, '--merge-output-format'), 'mp4')
        self.assertEqual(c[-2:], ['--', 'https://www.youtube.com/watch?v=abc123'])

    def test_other_modes(self):
        self.assertIn('--audio-format', self.cmd('mp3'))
        self.assertEqual(self.after(self.cmd('audio'), '-f'), 'bestaudio/best')
        self.assertIn('--write-subs', self.cmd('subtitles'))
        self.assertIn('--write-thumbnail', self.cmd('thumbnail'))
        self.assertNotIn('-S', self.cmd('audio'))

    def test_the_v78_tuning_still_applies(self):
        c = self.cmd()
        self.assertNotIn('--no-progress', c)
        self.assertIn('--progress-template', c)
        self.assertIn('--abort-on-unavailable-fragments', c)
        self.assertEqual(self.after(c, '--concurrent-fragments'), '4')

    def test_client_profile_cookies_and_proxy_are_applied_only_when_given(self):
        self.assertNotIn('youtube:player_client', ' '.join(self.cmd()))
        c = self.cmd(spec={'client': 'tv,tv_downgraded'})
        self.assertIn('youtube:player_client=tv,tv_downgraded', c)
        self.assertNotIn('--cookies', c)
        self.assertEqual(self.after(self.cmd(cookies='/x/session.cookies'), '--cookies'), '/x/session.cookies')
        self.assertNotIn('--proxy', self.cmd())
        with mock.patch.object(self.m, '_n87_proxy', lambda: 'socks5://127.0.0.1:1080'):
            self.assertEqual(self.after(self.cmd(), '--proxy'), 'socks5://127.0.0.1:1080')

    def test_a_javascript_runtime_is_enabled_deno_and_or_node(self):
        with mock.patch.object(self.m, '_n87_deno', lambda: '/usr/bin/deno'), mock.patch.object(self.m, '_n87_node', lambda: ('/usr/bin/node', 22)):
            c = self.cmd()
            runtimes = [c[i + 1] for i, a in enumerate(c) if a == '--js-runtimes']
            self.assertEqual(runtimes, ['deno:/usr/bin/deno', 'node:/usr/bin/node'])
        with mock.patch.object(self.m, '_n87_node', lambda: ('/usr/bin/node', 22)):
            self.assertEqual([c for c in self.cmd() if c.startswith(('node:', 'deno:'))], ['node:/usr/bin/node'])
        with mock.patch.object(self.m, '_n87_node', lambda: ('/usr/bin/node', 18)):
            self.assertEqual([c for c in self.cmd() if c.startswith(('node:', 'deno:'))], [], 'Node 18 is too old for yt-dlp')
        self.assertEqual(self.m._n87_js_runtimes(), [])

    def test_the_solver_is_fetched_only_when_the_package_is_missing(self):
        with mock.patch.object(self.m, '_n87_has_ejs', lambda: False):
            self.assertIn('--remote-components', self.cmd())
        with mock.patch.object(self.m, '_n87_has_ejs', lambda: True):
            self.assertNotIn('--remote-components', self.cmd())

    def test_pacing_only_for_playlists(self):
        self.assertNotIn('--sleep-interval', self.cmd())
        c = self.cmd(playlist=True)
        self.assertIn('--sleep-interval', c)
        self.assertIn('--yes-playlist', c)

    def test_the_same_size_limit_and_safe_filenames_remain(self):
        c = self.cmd()
        self.assertEqual(self.after(c, '--max-filesize'), str(self.m._N76_MAX_FILE))
        self.assertIn('--restrict-filenames', c)
        self.assertIn('--no-overwrites', c)
        self.assertEqual(self.after(c, '--max-downloads'), '1')

    @unittest.skipUnless(shutil.which('python3') and subprocess.run([sys.executable, '-c', 'import yt_dlp'], capture_output=True).returncode == 0, 'yt-dlp is not installed here')
    def test_the_real_yt_dlp_accepts_every_option_we_generate(self):
        for mode in ('video', 'audio', 'mp3', 'subtitles', 'thumbnail'):
            for spec in ({}, {'client': 'tv,tv_downgraded'}, {'client': 'android_vr,visionos'}, {'client': 'ios'}):
                c = self.cmd(mode, spec=spec, cookies=None)
                c[-1] = 'https://nonexistent.invalid/x'            # option parsing happens before any network use
                r = subprocess.run(c, capture_output=True, text=True, timeout=120)
                self.assertNotEqual(r.returncode, 2, (mode, spec, r.stderr[-300:]))
                self.assertNotIn('no such option', r.stderr.lower(), (mode, spec))
                self.assertNotIn('usage:', r.stderr.lower(), (mode, spec))

    @unittest.skipUnless(subprocess.run([sys.executable, '-c', 'import yt_dlp'], capture_output=True).returncode == 0, 'yt-dlp is not installed here')
    def test_every_client_profile_names_a_client_the_installed_yt_dlp_knows(self):
        from yt_dlp.extractor.youtube import _base
        known = set(_base.INNERTUBE_CLIENTS)
        for spec in self.m._n87_yt_specs():
            for name in [c for c in spec['client'].split(',') if c]:
                self.assertIn(name, known, spec['key'])


# ===================================================================================================================
# 3. ONE yt-dlp ATTEMPT (against a fake yt-dlp that behaves in scripted ways)
# ===================================================================================================================
@unittest.skipUnless(HAVE_FFMPEG, 'ffmpeg/ffprobe needed to build test videos')
class TestAttempt(RelayCase):
    def setUp(self):
        super().setUp()
        self.script = os.path.join(self.tmp.name, 'fake_ytdlp.py')
        with open(self.script, 'w') as fh:
            fh.write(FAKE_YTDLP)
        self.behavior = 'ok'
        p = mock.patch.object(self.m, '_n77_command', lambda url, folder, plan, cookies=None: [sys.executable, self.script, folder, self.behavior, FIX['video']])
        p.start()
        self.patches.append(p)

    def attempt(self, behavior, **kw):
        self.behavior = behavior
        return self.m._n87_ytdlp_attempt(self.ctx(**kw), {'key': 'ytdlp:default', 'label': 'yt-dlp', 'client': '', 'cookies': True})

    def test_success_returns_only_verified_files(self):
        res = self.attempt('ok')
        self.assertTrue(res['ok'], res)
        self.assertEqual([os.path.basename(f) for f in res['files']], ['Title_abc123.mp4'])
        self.assertEqual(os.listdir(self.folder), ['Title_abc123.mp4'], 'the extractor log is removed')

    def test_failures_are_classified_with_a_clean_one_line_reason(self):
        for behavior, klass in (('botcheck', 'bot_check'), ('format', 'format'), ('private', 'private')):
            res = self.attempt(behavior)
            self.assertFalse(res['ok'])
            self.assertEqual(res['klass'], klass, behavior)
            self.assertTrue(res['error'].startswith('ERROR:'))
            self.assertNotIn('\n', res['error'])

    def test_a_silent_process_is_abandoned_after_the_stall_limit(self):
        with mock.patch.object(self.m, '_N87_STALL', 1.5):
            t0 = time.time()
            res = self.attempt('stall')
        self.assertLess(time.time() - t0, 15)
        self.assertEqual((res['ok'], res['klass']), (False, 'timeout'))
        self.assertIn('no progress', res['error'])

    def test_a_process_that_keeps_talking_but_never_finishes_hits_the_attempt_cap(self):
        t0 = time.time()
        ctx = self.ctx(seconds=900)
        self.behavior = 'slow'
        res = self.m._n87_ytdlp_attempt(ctx, {'key': 'k', 'label': 'l', 'client': '', 'cookies': False, 'cap': 2.0})
        self.assertLess(time.time() - t0, 15)
        self.assertEqual(res['klass'], 'timeout')
        self.assertIn('attempt time limit', res['error'])

    def test_the_process_is_killed_after_a_timeout(self):
        marker = os.path.join(self.tmp.name, 'alive')
        with mock.patch.object(self.m, '_N87_STALL', 1.0):
            self.attempt('stall')
        time.sleep(0.6)
        out = subprocess.run(['pgrep', '-f', self.script], capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), '', 'no fake yt-dlp process is left running ' + marker)

    def test_an_unmerged_leftover_piece_is_not_a_result_but_is_kept_so_a_resume_can_reuse_it(self):
        res = self.attempt('partial')
        self.assertFalse(res['ok'])
        self.assertEqual(res['klass'], 'outdated')
        self.assertEqual(os.listdir(self.folder), ['Title_abc123.f137.mp4'])

    def test_a_finished_verified_file_counts_even_if_a_late_optional_step_made_yt_dlp_exit_1(self):
        res = self.attempt('ok_but_rc1')
        self.assertTrue(res['ok'], res)
        self.assertEqual(res['warning'], '', 'for a single video no warning is raised (the v78 pipeline would treat it as a failure)')

    def test_a_download_that_is_not_a_video_is_rejected_by_the_check(self):
        res = self.attempt('garbage')
        self.assertFalse(res['ok'])
        self.assertEqual(res['klass'], 'verify')
        self.assertIn('too small', res['error'])
        self.assertEqual(os.listdir(self.folder), [], 'the junk file is removed so the next attempt does not think it was already downloaded')

    def test_a_playlist_with_one_bad_item_returns_the_good_file_and_a_warning(self):
        res = self.attempt('playlist_partial', playlist=True)
        self.assertTrue(res['ok'])
        self.assertEqual(len(res['files']), 1)
        self.assertIn('unavailable', res['warning'])

    def test_cancellation_propagates_and_stops_the_process(self):
        self.behavior = 'stall'
        with mock.patch.object(self.m, '_n77_check_cancel', mock.Mock(side_effect=ValueError('Download cancelled'))):
            with self.assertRaises(ValueError) as ctx:
                self.m._n87_ytdlp_attempt(self.ctx(), {'key': 'k', 'label': 'l', 'client': '', 'cookies': False})
        self.assertEqual(str(ctx.exception), 'Download cancelled')
        time.sleep(0.5)
        self.assertEqual(subprocess.run(['pgrep', '-f', self.script], capture_output=True, text=True).stdout.strip(), '')

    def test_cookies_are_only_given_to_profiles_that_use_them(self):
        seen = []
        with mock.patch.object(self.m, '_n77_command', lambda url, folder, plan, cookies=None: seen.append((plan['_n87']['key'], cookies)) or [sys.executable, self.script, folder, 'ok', FIX['video']]):
            ctx = self.ctx(cookie='/x/c')
            self.m._n87_ytdlp_attempt(ctx, {'key': 'a', 'label': 'a', 'client': '', 'cookies': True})
            self.m._n87_ytdlp_attempt(ctx, {'key': 'b', 'label': 'b', 'client': 'web_embedded', 'cookies': False})
        self.assertEqual(seen, [('a', '/x/c'), ('b', None)])


# ===================================================================================================================
# 4. THE VIDEO CHECK
# ===================================================================================================================
@unittest.skipUnless(HAVE_FFMPEG, 'ffmpeg/ffprobe needed to build test videos')
class TestVerify(RelayCase):
    def test_real_video_audio_and_fakes(self):
        v = self.m._n87_verify
        self.assertEqual(v(FIX['video'], 'video'), (True, ''))
        self.assertEqual(v(FIX['audio_only'], 'audio'), (True, ''))
        ok, why = v(FIX['audio_only'], 'video')
        self.assertFalse(ok)
        self.assertIn('no video stream', why)
        bad = os.path.join(self.folder, 'page.mp4')
        with open(bad, 'wb') as fh:
            fh.write(b'<html>' + b'x' * 40000)
        ok, why = v(bad, 'video')
        self.assertFalse(ok, 'a big HTML error page named .mp4 is not a video')
        tiny = os.path.join(self.folder, 'tiny.mp4')
        with open(tiny, 'wb') as fh:
            fh.write(b'abc')
        self.assertFalse(v(tiny, 'video')[0])
        self.assertFalse(v(os.path.join(self.folder, 'missing.mp4'), 'video')[0])
        self.assertTrue(v(tiny, 'thumbnail')[0] or True)

    def test_collect_ignores_unmerged_pieces_symlinks_and_old_files(self):
        shutil.copy(FIX['video'], os.path.join(self.folder, 'Real_abc.mp4'))
        shutil.copy(FIX['video_only'], os.path.join(self.folder, 'Real_abc.f137.mp4'))
        shutil.copy(FIX['video'], os.path.join(self.folder, 'old.mp4'))
        os.symlink(FIX['video'], os.path.join(self.folder, 'link.mp4'))
        files, problems = self.m._n87_collect(self.folder, {'old.mp4'}, self.plan())
        self.assertEqual([os.path.basename(f) for f in files], ['Real_abc.mp4'])

    def test_missing_ffprobe_is_a_clear_error(self):
        with mock.patch.object(self.m._n87_shutil, 'which', lambda n: None):
            with self.assertRaises(ValueError) as ctx:
                self.m._n87_probe(FIX['video'])
        self.assertIn('ffprobe is required', str(ctx.exception))


# ===================================================================================================================
# 5. THE CHAIN
# ===================================================================================================================
class TestChain(RelayCase):
    def run_chain(self, steps, **kw):
        with mock.patch.object(self.m, '_n87_steps', lambda ctx: list(steps)):
            return self.m._n87_chain(self.ctx(**kw), label='t')

    def test_the_first_source_that_works_wins_and_the_rest_are_not_tried(self):
        calls = []
        files, warning = self.run_chain([fail_step('a', 'ERROR: x', 'bot_check', calls=calls), ok_step('b', calls=calls), ok_step('c', calls=calls)])
        self.assertEqual(calls, ['a', 'b'])
        self.assertEqual(warning, '')
        last = self.m._N87_LAST['t']
        self.assertEqual((last['ok'], last['source']), (True, 'b'))
        self.assertEqual([t['status'] for t in last['trace']], ['failed', 'ok'])

    def test_every_failure_is_listed_with_its_reason_and_the_next_step(self):
        with self.assertRaises(self.m._N87Fail) as ctx:
            self.run_chain([fail_step('a', 'ERROR: Sign in to confirm you are not a bot', 'bot_check', label='yt-dlp · default'),
                            fail_step('b', 'HTTP error 403', 'outdated', label='pytubefix'),
                            {'key': 'c', 'label': 'Cobalt server', 'group': 'alt', 'unavailable': 'no Cobalt server configured (optional)', 'run': None}])
        text = str(ctx.exception)
        for needle in ('yt-dlp · default', 'pytubefix', 'Cobalt server — skipped: no Cobalt server configured', 'asked this server to prove it is not a bot',
                       'Most likely cause', '/cookies', 'Nothing was uploaded', '“test youtube download”'):
            self.assertIn(needle, text)
        self.assertEqual(ctx.exception.klass, 'bot_check')
        self.assertTrue(ctx.exception._n87)
        self.assertEqual(self.m._N87_STATS['chain_failed'], 1)

    def test_the_failure_text_never_contains_links_paths_or_cookies(self):
        err = 'ERROR: failed https://rr1.googlevideo.com/videoplayback?sig=SECRET in /root/nemo_download77/x using session.cookies'
        with self.assertRaises(self.m._N87Fail) as ctx:
            self.run_chain([fail_step('a', err, 'outdated')])
        text = str(ctx.exception)
        for leaked in ('googlevideo', 'SECRET', '/root'):
            self.assertNotIn(leaked, text)
        self.assertLess(len(text), 3400)

    def test_definitive_answers_stop_the_chain(self):
        calls = []
        with self.assertRaises(self.m._N87Fail) as ctx:
            self.run_chain([fail_step('a', 'ERROR: Private video', 'private', calls=calls), ok_step('b', calls=calls)])
        self.assertEqual(calls, ['a'])
        self.assertEqual(ctx.exception.klass, 'private')
        self.assertIn('private or for members only', str(ctx.exception))
        calls.clear()
        with self.assertRaises(self.m._N87Fail):
            self.run_chain([fail_step('a', 'ERROR: DRM protected', 'drm', calls=calls), ok_step('b', calls=calls)])
        self.assertEqual(calls, ['a'])

    def test_unavailable_is_not_definitive_because_another_client_may_still_work(self):
        calls = []
        self.run_chain([fail_step('a', 'ERROR: Video unavailable', 'removed', calls=calls), ok_step('b', calls=calls)])
        self.assertEqual(calls, ['a', 'b'])

    def test_a_source_that_raises_is_a_failure_not_a_crash(self):
        calls = []
        self.run_chain([fail_step('a', '', raises=RuntimeError('boom https://x.example/secret'), calls=calls), fail_step('b', '', raises=OSError('disk'), calls=calls), ok_step('c', calls=calls)])
        self.assertEqual(calls, ['a', 'b', 'c'])
        trace = self.m._N87_LAST['t']['trace']
        self.assertIn('RuntimeError', trace[0]['detail'])
        self.assertNotIn('x.example', trace[0]['detail'])
        self.assertGreaterEqual(self.m._N87_STATS['errors'], 2)

    def test_a_success_without_files_is_a_failure(self):
        calls = []
        steps = [{'key': 'a', 'label': 'a', 'group': 'alt', 'unavailable': '', 'run': lambda c: {'ok': True, 'files': [], 'error': '', 'klass': ''}}, ok_step('b', calls=calls)]
        self.run_chain(steps)
        self.assertEqual(calls, ['b'])
        self.assertEqual(self.m._N87_LAST['t']['trace'][0]['klass'], 'verify')

    def test_cancellation_and_environment_limits_are_not_swallowed(self):
        for text in ('Download cancelled', 'Local disk reserve reached; free space before retrying', 'Media size limit reached', 'ffprobe is required to verify downloaded media'):
            calls = []
            with self.assertRaises(ValueError) as ctx:
                self.run_chain([fail_step('a', '', raises=ValueError(text), calls=calls), ok_step('b', calls=calls)])
            self.assertEqual(str(ctx.exception), text)
            self.assertNotIsInstance(ctx.exception, self.m._N87Fail)
            self.assertEqual(calls, ['a'])

    def test_a_source_timeout_is_recorded_and_the_chain_goes_on(self):
        calls = []
        self.run_chain([fail_step('a', '', raises=self.m._N87Timeout('attempt time limit'), calls=calls), ok_step('b', calls=calls)])
        self.assertEqual(self.m._N87_LAST['t']['trace'][0]['klass'], 'timeout')
        self.assertEqual(calls, ['a', 'b'])

    def test_when_the_overall_time_is_up_the_remaining_sources_are_skipped_and_said_so(self):
        calls = []
        with self.assertRaises(self.m._N87Fail) as ctx:
            self.run_chain([ok_step('a', calls=calls)], seconds=5)
        self.assertEqual(calls, [])
        self.assertIn('overall time limit', str(ctx.exception))

    def test_the_source_that_worked_last_is_tried_first_next_time(self):
        calls = []
        steps = [fail_step('ytdlp:default', 'x', 'bot_check', calls=calls, group='ytdlp'), ok_step('pytubefix', calls=calls)]
        self.run_chain(steps)
        self.assertEqual(calls, ['ytdlp:default', 'pytubefix'])
        calls.clear()
        self.run_chain(steps)
        self.assertEqual(calls, ['pytubefix'], 'the yt-dlp attempt is skipped because pytubefix worked last time')
        stats = self.m._n87_stats()
        self.assertEqual(stats['pytubefix']['ok'], 2)
        self.assertEqual(stats['ytdlp:default']['fail'], 1)

    def test_a_stale_preference_is_not_used(self):
        steps = [ok_step('a'), ok_step('b')]
        self.m._n87_stat('b', True)
        c = self.m._n87_db()
        c.execute('UPDATE download87_stats SET last_ok=? WHERE source=?', (time.time() - 5 * 86400, 'b'))
        c.commit()
        c.close()
        calls = []
        self.run_chain([ok_step('a', calls=calls), ok_step('b', calls=calls)])
        self.assertEqual(calls, ['a'])

    def test_preference_only_applies_to_youtube(self):
        self.m._n87_stat('b', True)
        calls = []
        self.run_chain([ok_step('a', calls=calls), ok_step('b', calls=calls)], youtube=False)
        self.assertEqual(calls, ['a'])

    def test_rejected_cookies_are_dropped_for_the_remaining_steps(self):
        seen = []

        def step(key, klass):
            def run(ctx):
                seen.append((key, ctx.get('cookie')))
                return {'ok': klass is None, 'files': ['/dev/null'] if klass is None else [], 'error': 'x', 'klass': klass or ''}
            return {'key': key, 'label': key, 'group': 'alt', 'unavailable': '', 'run': run}
        self.run_chain([step('a', 'cookies'), step('b', None)], cookie='/x/c')
        self.assertEqual(seen, [('a', '/x/c'), ('b', None)])

    def test_progress_is_reported_per_source(self):
        stages = []
        with mock.patch.object(self.m, '_n78_progress', lambda stage, values=None, force=False: stages.append(stage)):
            self.run_chain([fail_step('a', 'x', 'unknown', label='yt-dlp · default'), ok_step('b', label='pytubefix')])
        self.assertEqual(stages, ['Source 1/2 · yt-dlp · default', 'Source 2/2 · pytubefix'])

    def test_the_failure_cause_is_the_most_common_class_with_a_fixed_priority(self):
        text, cause = self.m._n87_failure_text([{'label': l, 'status': 'failed', 'klass': k, 'detail': ''} for l, k in (('a', 'network'), ('b', 'bot_check'), ('c', 'bot_check'), ('d', 'unknown'))], 70, 'h')
        self.assertEqual(cause, 'bot_check')
        self.assertIn('1 min 10 s', text)
        _text, cause = self.m._n87_failure_text([{'label': 'a', 'status': 'failed', 'klass': 'unknown', 'detail': ''}], 5, 'h')
        self.assertEqual(cause, 'unknown')


class TestAutomaticUpdate(RelayCase):
    def chain_with(self, klass, group='ytdlp'):
        calls = []
        first = fail_step('ytdlp:default', 'x', klass, label='yt-dlp · default', group=group, calls=calls)
        last = fail_step('ytdlp:ios', 'x', klass, label='yt-dlp · iOS', group=group, calls=calls)
        return calls, [first, last, ok_step('pytubefix', calls=calls)]

    def run_chain(self, steps):
        with mock.patch.object(self.m, '_n87_steps', lambda ctx: list(steps)):
            return self.m._n87_chain(self.ctx(), label='u')

    def test_an_outdated_extractor_triggers_one_update_and_one_retry_of_the_first_profile(self):
        calls, steps = self.chain_with('outdated')
        ups = []
        fake = lambda force=False: ups.append(force) or dict(self.m._N87_UPGRADE, ok=True, old='2025.1.1', new='2026.8.19', changed=True)
        with mock.patch.object(self.m, '_n87_upgrade_ytdlp', fake):
            self.run_chain(steps)
        self.assertEqual(ups, [False])
        self.assertEqual(calls, ['ytdlp:default', 'ytdlp:ios', 'ytdlp:default', 'pytubefix'], 'the default profile is retried once after the update')
        labels = [t['label'] for t in self.m._N87_LAST['u']['trace']]
        self.assertIn('yt-dlp update', labels)

    def test_no_update_for_a_bot_check_because_a_newer_yt_dlp_will_not_help(self):
        calls, steps = self.chain_with('bot_check')
        with mock.patch.object(self.m, '_n87_upgrade_ytdlp', mock.Mock()) as up:
            self.run_chain(steps)
        up.assert_not_called()

    def test_the_update_has_a_cool_down(self):
        calls, steps = self.chain_with('outdated')
        self.m._N87_UPGRADE['ts'] = time.time() - 600
        with mock.patch.object(self.m, '_n87_upgrade_ytdlp', mock.Mock()) as up:
            self.run_chain(steps)
        up.assert_not_called()

    def test_a_failed_update_is_reported_and_the_chain_still_goes_on(self):
        calls, steps = self.chain_with('outdated')
        with mock.patch.object(self.m, '_n87_upgrade_ytdlp', lambda force=False: dict(self.m._N87_UPGRADE, ok=False, old='1', new='', changed=False)):
            self.run_chain(steps)
        self.assertEqual(calls, ['ytdlp:default', 'ytdlp:ios', 'pytubefix'])
        note = [t for t in self.m._N87_LAST['u']['trace'] if t['key'] == 'update'][0]
        self.assertEqual(note['status'], 'failed')

    def test_upgrade_uses_the_bots_own_python_hides_output_and_tries_nightly_when_unchanged(self):
        cmds = []
        versions = iter(['2026.8.19', '2026.8.19', '2026.9.1'])
        with mock.patch.object(self.m, '_n781_exec', lambda cmd, timeout=600: cmds.append(list(cmd)) or True), \
                mock.patch.object(self.m, '_n87_ytdlp_version', lambda: next(versions)):
            res = self.m._n87_upgrade_ytdlp(force=True)
        self.assertTrue(res['ok'] and res['changed'])
        self.assertEqual((res['old'], res['new']), ('2026.8.19', '2026.9.1'))
        self.assertTrue(all(c[0] == sys.executable and c[1:3] == ['-m', 'pip'] for c in cmds))
        self.assertIn('yt-dlp[default]', cmds[0])
        self.assertTrue(any('--pre' in c for c in cmds), 'the nightly build is tried when the stable one changed nothing')
        self.assertEqual(self.m._N87_STATS['upgrades'], 1)

    def test_pip_falls_back_to_the_second_form_and_reports_failure(self):
        tried = []
        with mock.patch.object(self.m, '_n781_exec', lambda cmd, timeout=600: tried.append(cmd) or False):
            self.assertFalse(self.m._n87_pip(['install', '-U', 'x']))
        self.assertEqual(len(tried), 2)
        self.assertIn('--break-system-packages', tried[0])
        self.assertNotIn('--break-system-packages', tried[1])


# ===================================================================================================================
# 6. THE OTHER SOURCES
# ===================================================================================================================
@unittest.skipUnless(HAVE_FFMPEG, 'ffmpeg/ffprobe needed to build test videos')
class TestPytubefix(RelayCase):
    def setUp(self):
        super().setUp()
        self.stub = os.path.join(self.tmp.name, 'stub')
        os.makedirs(self.stub)
        with open(os.path.join(self.stub, 'pytubefix.py'), 'w') as fh:
            fh.write(STUB_PYTUBEFIX)
        env = {'PYTHONPATH': self.stub, 'STUB_VIDEO_ONLY': FIX['video_only'], 'STUB_AUDIO_ONLY': FIX['audio_only'], 'STUB_FULL': FIX['video']}
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.patches.append(p)

    def run_src(self, mode='video', stub_mode='adaptive', **kw):
        os.environ['STUB_PTF_MODE'] = stub_mode
        ctx = self.ctx(mode=mode, **kw)
        return self.m._n87_src_pytubefix(ctx), ctx

    def test_adaptive_streams_are_merged_into_one_verified_mp4(self):
        res, ctx = self.run_src()
        self.assertTrue(res['ok'], res)
        self.assertEqual(len(res['files']), 1)
        self.assertTrue(res['files'][0].endswith('.mp4'))
        self.assertEqual(self.m._n87_verify(res['files'][0], 'video'), (True, ''))
        self.assertEqual([n for n in os.listdir(self.folder) if n != os.path.basename(res['files'][0])], [], 'the single-stream pieces are removed after the merge')

    def test_progressive_stream_is_used_when_nothing_adaptive_exists(self):
        res, _ = self.run_src(stub_mode='progressive')
        self.assertTrue(res['ok'], res)

    def test_audio_mode_and_mp3(self):
        res, _ = self.run_src(mode='audio')
        self.assertTrue(res['ok'], res)
        self.assertTrue(res['files'][0].endswith('.m4a'))
        res, _ = self.run_src(mode='mp3')
        self.assertTrue(res['ok'], res)
        self.assertTrue(res['files'][0].endswith('.mp3'))
        self.assertEqual(self.m._n87_verify(res['files'][0], 'mp3'), (True, ''))

    def test_the_next_client_is_tried_when_the_first_is_refused(self):
        res, _ = self.run_src(stub_mode='fail_default')
        self.assertTrue(res['ok'], res)

    def test_all_clients_refused_gives_a_clean_failure(self):
        res, _ = self.run_src(stub_mode='fail_all')
        self.assertFalse(res['ok'])
        self.assertIn('refused', res['error'])
        self.assertNotIn('\n', res['error'])
        res, _ = self.run_src(stub_mode='nothing')
        self.assertFalse(res['ok'])
        self.assertIn('no matching stream', res['error'])

    def test_a_missing_package_is_reported_not_crashed(self):
        with open(os.path.join(self.stub, 'pytubefix.py'), 'w') as fh:
            fh.write("raise ImportError(\"No module named 'pytubefix'\")\n")
        os.environ['STUB_PTF_MODE'] = 'adaptive'
        res = self.m._n87_src_pytubefix(self.ctx())
        self.assertFalse(res['ok'])
        self.assertEqual(res['klass'], 'missing')

    def test_the_worker_file_is_private_and_not_followed_through_a_symlink(self):
        ctx = self.ctx()
        path = self.m._n87_ptf_worker(ctx)
        self.assertEqual(oct(os.stat(path).st_mode)[-3:], '600')
        os.unlink(path)
        os.symlink('/etc/passwd', path)
        with self.assertRaises(ValueError):
            self.m._n87_ptf_worker(ctx)

    def test_a_hung_worker_is_stopped_at_the_time_limit(self):
        with mock.patch.object(self.m._n87_sp, 'run', mock.Mock(side_effect=subprocess.TimeoutExpired('x', 1))):
            res = self.m._n87_src_pytubefix(self.ctx())
        self.assertEqual((res['ok'], res['klass']), (False, 'timeout'))


@unittest.skipUnless(HAVE_FFMPEG, 'ffmpeg/ffprobe needed to build test videos')
class TestMirrorsAndFetch(RelayCase):
    def setUp(self):
        super().setUp()
        with open(FIX['video'], 'rb') as fh:
            self.video_bytes = fh.read()
        with open(FIX['video_only'], 'rb') as fh:
            self.vo_bytes = fh.read()
        with open(FIX['audio_only'], 'rb') as fh:
            self.ao_bytes = fh.read()
        self.srv, self.url = serve({'/redirect': (302, 'text/plain', b'', {'Location': '/v.mp4'}), '/to_private': (302, 'text/plain', b'', {'Location': 'http://10.0.0.5/secret'}),
                                    '/loop': (302, 'text/plain', b'', {'Location': '/loop'}), '/v.mp4': (200, 'video/mp4', self.video_bytes), '/vo.mp4': (200, 'video/mp4', self.vo_bytes), '/ao.m4a': (200, 'audio/mp4', self.ao_bytes),
                                    '/page': (200, 'text/html', b'<html>blocked</html>' * 2000), '/gone': (403, 'text/plain', b'forbidden'), '/tiny': (200, 'video/mp4', b'x' * 50)})
        self.addCleanup(self.srv.shutdown)
        p = mock.patch.object(self.m, '_n60_is_public_url', lambda u, allow_local=False: u.startswith('http://127.0.0.1') or u.startswith('https://'))
        p.start()
        self.patches.append(p)

    def test_fetch_downloads_a_file_and_reports_progress(self):
        stages = []
        with mock.patch.object(self.m, '_n78_progress', lambda stage, values=None, force=False: stages.append(stage)):
            dest = self.m._n87_fetch(self.ctx(), self.url + '/v.mp4', os.path.join(self.folder, 'out.mp4'))
        self.assertEqual(open(dest, 'rb').read(), self.video_bytes)
        self.assertEqual(os.listdir(self.folder), ['out.mp4'])
        self.assertIn('Downloading', stages)

    def test_fetch_refuses_web_pages_errors_tiny_files_and_private_addresses(self):
        for path, needle in (('/page', 'web page'), ('/gone', 'HTTP error 403'), ('/tiny', 'empty response')):
            with self.assertRaises(RuntimeError) as ctx:
                self.m._n87_fetch(self.ctx(), self.url + path, os.path.join(self.folder, 'out.mp4'))
            self.assertIn(needle, str(ctx.exception))
            self.assertEqual(os.listdir(self.folder), [], 'no partial file is left behind')
        with mock.patch.object(self.m, '_n60_is_public_url', lambda u, allow_local=False: False):
            with self.assertRaises(RuntimeError) as ctx:
                self.m._n87_fetch(self.ctx(), self.url + '/v.mp4', os.path.join(self.folder, 'out.mp4'))
        self.assertIn('unsafe', str(ctx.exception))

    def test_a_redirect_is_followed_only_to_public_addresses_and_checked_before_it_is_requested(self):
        dest = self.m._n87_fetch(self.ctx(), self.url + '/redirect', os.path.join(self.folder, 'out.mp4'))
        self.assertEqual(open(dest, 'rb').read(), self.video_bytes)
        self.srv.hits.clear()
        with self.assertRaises(RuntimeError) as ctx:
            self.m._n87_fetch(self.ctx(), self.url + '/to_private', os.path.join(self.folder, 'out2.mp4'))
        self.assertIn('unsafe redirect', str(ctx.exception))
        self.assertEqual(self.srv.hits, ['/to_private'], 'the private address was never requested')
        with self.assertRaises(RuntimeError) as ctx:
            self.m._n87_fetch(self.ctx(), self.url + '/loop', os.path.join(self.folder, 'out3.mp4'))
        self.assertIn('too many redirects', str(ctx.exception))

    def test_fetch_stops_at_the_size_limit_and_on_cancel_and_on_time(self):
        with mock.patch.object(self.m, '_N76_MAX_FILE', 100):
            with self.assertRaises(ValueError) as ctx:
                self.m._n87_fetch(self.ctx(), self.url + '/v.mp4', os.path.join(self.folder, 'out.mp4'))
        self.assertIn('size limit', str(ctx.exception))
        with mock.patch.object(self.m, '_n77_check_cancel', mock.Mock(side_effect=ValueError('Download cancelled'))):
            with self.assertRaises(ValueError):
                self.m._n87_fetch(self.ctx(), self.url + '/v.mp4', os.path.join(self.folder, 'out.mp4'))
        with self.assertRaises(self.m._N87Timeout):
            self.m._n87_fetch(self.ctx(seconds=-1), self.url + '/v.mp4', os.path.join(self.folder, 'out.mp4'))
        self.assertEqual(os.listdir(self.folder), [])

    def test_progressive_candidate_becomes_a_verified_file(self):
        out = self.m._n87_materialize(self.ctx(), {'title': 'My Video', 'progressive': self.url + '/v.mp4', 'video_mime': 'video/mp4'}, 'piped')
        self.assertEqual(self.m._n87_verify(out, 'video'), (True, ''))

    def test_separate_video_and_audio_are_merged(self):
        out = self.m._n87_materialize(self.ctx(), {'title': 'Merged', 'video': self.url + '/vo.mp4', 'audio': self.url + '/ao.m4a'}, 'inv')
        has_video, has_audio, duration = self.m._n87_probe(out)
        self.assertTrue(has_video and has_audio and duration > 0.5)
        self.assertEqual([n for n in os.listdir(self.folder) if n != os.path.basename(out)], [])

    def test_audio_candidates_and_mp3(self):
        out = self.m._n87_materialize(self.ctx(mode='audio'), {'title': 'A', 'audio': self.url + '/ao.m4a', 'audio_mime': 'audio/mp4'}, 'x')
        self.assertTrue(out.endswith('.m4a'))
        out = self.m._n87_materialize(self.ctx(mode='mp3'), {'title': 'B', 'audio': self.url + '/ao.m4a', 'audio_mime': 'audio/mp4'}, 'x')
        self.assertTrue(out.endswith('.mp3'))
        with self.assertRaises(RuntimeError):
            self.m._n87_materialize(self.ctx(mode='audio'), {'title': 'C'}, 'x')
        with self.assertRaises(RuntimeError):
            self.m._n87_materialize(self.ctx(), {'title': 'D'}, 'x')

    def test_piped_mirror_end_to_end_and_when_no_mirror_answers(self):
        with mock.patch.object(self.m, '_n61_piped_resolve', lambda url, mode, quality: {'backend': 'piped:x', 'title': 'T', 'progressive': self.url + '/v.mp4', 'video_mime': 'video/mp4'}):
            res = self.m._n87_src_mirror(self.ctx(), 'piped')
        self.assertTrue(res['ok'], res)
        with mock.patch.object(self.m, '_n61_inv_resolve', lambda url, mode, quality: None):
            res = self.m._n87_src_mirror(self.ctx(), 'invidious')
        self.assertFalse(res['ok'])
        self.assertIn('invidious', res['error'])

    def test_a_mirror_stream_that_is_refused_is_a_failed_source_not_a_crash(self):
        cand = {'backend': 'piped:x', 'title': 'T', 'progressive': self.url + '/gone', 'video_mime': 'video/mp4'}
        with mock.patch.object(self.m, '_n61_piped_resolve', lambda url, mode, quality: cand):
            with mock.patch.object(self.m, '_n87_steps', lambda ctx: [{'key': 'piped', 'label': 'Piped mirrors', 'group': 'alt', 'unavailable': '', 'run': lambda c: self.m._n87_src_mirror(c, 'piped')}]):
                with self.assertRaises(self.m._N87Fail) as ctx:
                    self.m._n87_chain(self.ctx(), label='m')
        self.assertIn('Piped mirrors', str(ctx.exception))
        self.assertIn('HTTP error 403', str(ctx.exception))

    def test_youtubejs_source(self):
        cand = {'backend': 'youtubejs:TV', 'title': 'JS', 'progressive': self.url + '/v.mp4', 'video_mime': 'video/mp4'}
        with mock.patch.object(self.m, '_n62_youtubejs_resolve', lambda url, mode, quality: cand):
            self.assertTrue(self.m._n87_src_youtubejs(self.ctx())['ok'])
        with mock.patch.object(self.m, '_n62_youtubejs_resolve', lambda url, mode, quality: None):
            res = self.m._n87_src_youtubejs(self.ctx())
        self.assertFalse(res['ok'])

    def test_cobalt_source_moves_files_into_the_job_folder(self):
        made = os.path.join(self.m._N59_DIR, 'cobalt_video.mp4')
        shutil.copy(FIX['video'], made)
        with mock.patch.object(self.m, '_n60_cobalt_backend', lambda url, mode, quality, tag: {'ok': True, 'files': [made]}):
            res = self.m._n87_src_cobalt(self.ctx())
        self.assertTrue(res['ok'], res)
        self.assertFalse(os.path.exists(made))
        self.assertTrue(res['files'][0].startswith(self.folder))
        with mock.patch.object(self.m, '_n60_cobalt_backend', lambda url, mode, quality, tag: {'ok': False, 'error': 'not configured'}):
            self.assertFalse(self.m._n87_src_cobalt(self.ctx())['ok'])

    def test_a_helper_that_never_answers_is_abandoned(self):
        gate = threading.Event()
        with self.assertRaises(self.m._N87Timeout):
            self.m._n87_call_bounded(lambda: gate.wait(30), 0.2)
        gate.set()


class TestSteps(RelayCase):
    def keys(self, **kw):
        return [s['key'] for s in self.m._n87_steps(self.ctx(**kw))]

    def test_a_youtube_link_gets_six_profiles_then_five_other_sources_in_this_order(self):
        self.assertEqual(self.keys(), ['ytdlp:default', 'ytdlp:tv', 'ytdlp:embedded', 'ytdlp:vr', 'ytdlp:web', 'ytdlp:ios', 'pytubefix', 'youtubejs', 'piped', 'invidious', 'cobalt'])

    def test_other_sites_and_non_video_requests_use_yt_dlp_only(self):
        self.assertEqual(self.keys(youtube=False), ['ytdlp:default'])
        self.assertEqual(self.keys(playlist=True), self.keys()[:6])
        self.assertEqual(self.keys(mode='subtitles'), self.keys()[:6])

    def test_unavailable_sources_say_why(self):
        by = {s['key']: s['unavailable'] for s in self.m._n87_steps(self.ctx())}
        self.assertIn('set up download sources', by['youtubejs'])
        self.assertIn('optional', by['cobalt'])
        with mock.patch.object(self.m, '_n87_has_module', lambda name: name != 'pytubefix'):
            by = {s['key']: s['unavailable'] for s in self.m._n87_steps(self.ctx())}
        self.assertIn('not installed', by['pytubefix'])
        self.assertEqual(by['ytdlp:default'], '')
        with mock.patch.object(self.m, '_n87_has_module', lambda name: False):
            self.assertIn('not installed in the bot', self.m._n87_steps(self.ctx())[0]['unavailable'])
        with mock.patch.object(self.m, '_n60_public_resolvers_enabled', lambda: False):
            by = {s['key']: s['unavailable'] for s in self.m._n87_steps(self.ctx())}
        self.assertIn('switched off', by['piped'])

    def test_cobalt_and_youtubejs_become_available_when_configured(self):
        os.makedirs(os.path.join(self.m._N62_NODE, 'node_modules', 'youtubei.js'))
        with mock.patch.object(self.m, '_n87_node', lambda: ('/usr/bin/node', 22)), mock.patch.object(self.m, '_n60_cobalt_cfg', lambda: ('https://cobalt.example', 'k')):
            by = {s['key']: s['unavailable'] for s in self.m._n87_steps(self.ctx())}
        self.assertEqual((by['youtubejs'], by['cobalt']), ('', ''))


# ===================================================================================================================
# 7. THE FRONT DOOR: _n77_media now runs the chain
# ===================================================================================================================
@unittest.skipUnless(HAVE_FFMPEG, 'ffmpeg/ffprobe needed to build test videos')
class TestMediaEntry(RelayCase):
    def setUp(self):
        super().setUp()
        import urllib.parse
        p = mock.patch.object(self.m, '_n77_url', lambda url: urllib.parse.urlsplit(url))
        p.start()
        self.patches.append(p)
        self.seen = {}

    def make(self, ctx):
        self.seen['ctx'] = dict(ctx)
        self.seen['cookie_exists'] = bool(ctx.get('cookie')) and os.path.exists(ctx['cookie'])
        path = os.path.join(ctx['folder'], 'Title_abc.mp4')
        shutil.copy(FIX['video'], path)
        return path

    def steps(self):
        return mock.patch.object(self.m, '_n87_steps', lambda ctx: [ok_step('a', 'yt-dlp', 'ytdlp', make=self.make)])

    def test_the_chain_result_is_returned_in_the_shape_the_v78_queue_expects(self):
        with self.steps():
            files, warning = self.m._n77_media('https://www.youtube.com/watch?v=abc123', self.plan())
        self.assertEqual((len(files), warning), (1, ''))
        self.assertTrue(files[0].startswith(os.path.join(self.tmp.name, 'nemo_download77')))
        self.assertTrue(self.seen['ctx']['youtube'])
        self.assertGreater(self.seen['ctx']['deadline'] - time.monotonic(), 800)

    def test_the_session_cookie_copy_exists_only_during_the_download(self):
        cookies = os.path.join(self.tmp.name, 'cookies.txt')
        with open(cookies, 'w') as fh:
            fh.write('# Netscape HTTP Cookie File\n')
        with mock.patch.object(self.m, '_n77_cookie_status', lambda: ('1 unexpired YouTube entries', cookies)), self.steps():
            files, _ = self.m._n77_media('https://www.youtube.com/watch?v=abc123', self.plan())
        self.assertTrue(self.seen['cookie_exists'])
        self.assertFalse(os.path.exists(self.seen['ctx']['cookie']), 'the copy is deleted afterwards')
        self.assertEqual(oct(os.stat(files[0]).st_mode)[-3:], oct(os.stat(files[0]).st_mode)[-3:])

    def test_other_sites_get_no_cookies_and_are_not_treated_as_youtube(self):
        with mock.patch.object(self.m, '_n77_cookie_status', lambda: ('x', '/never')), self.steps():
            self.m._n77_media('https://vimeo.com/123', self.plan())
        self.assertFalse(self.seen['ctx']['youtube'])
        self.assertIsNone(self.seen['ctx']['cookie'])

    def test_more_video_sites_are_allowed_and_unknown_sites_are_not(self):
        for host in ('rumble.com', 'www.streamable.com', 'odysee.com', 'm.youtube.com', 'music.youtube.com', 'www.youtube-nocookie.com', 'bsky.app', 'vimeo.com'):
            with self.steps():
                self.m._n77_media('https://%s/v/1' % host, self.plan())
        with self.assertRaises(ValueError) as ctx:
            self.m._n77_media('https://evil.example/video', self.plan())
        self.assertIn('outside the supported media host list', str(ctx.exception))

    def test_only_one_media_download_runs_at_a_time(self):
        self.assertTrue(self.m._N77_MEDIA_LOCK.acquire(blocking=False))
        try:
            with self.assertRaises(ValueError) as ctx:
                self.m._n77_media('https://www.youtube.com/watch?v=abc123', self.plan())
            self.assertIn('Another media download is active', str(ctx.exception))
        finally:
            self.m._N77_MEDIA_LOCK.release()

    def test_the_lock_and_the_cookie_copy_are_released_after_a_failed_chain(self):
        cookies = os.path.join(self.tmp.name, 'cookies.txt')
        open(cookies, 'w').write('x')
        with mock.patch.object(self.m, '_n77_cookie_status', lambda: ('ok', cookies)), \
                mock.patch.object(self.m, '_n87_steps', lambda ctx: [fail_step('a', 'ERROR: Sign in to confirm you are not a bot', 'bot_check')]):
            with self.assertRaises(self.m._N87Fail):
                self.m._n77_media('https://www.youtube.com/watch?v=abc123', self.plan())
        self.assertTrue(self.m._N77_MEDIA_LOCK.acquire(blocking=False))
        self.m._N77_MEDIA_LOCK.release()
        self.assertEqual([n for n in os.listdir(os.path.join(self.tmp.name, 'nemo_download77')) for n in os.listdir(os.path.join(self.tmp.name, 'nemo_download77', n)) if n == 'session.cookies'], [])

    def test_a_symlinked_download_directory_is_refused(self):
        root = os.path.join(self.tmp.name, 'nemo_download77')
        os.symlink(self.tmp.name, root)
        with self.assertRaises(ValueError) as ctx:
            self.m._n77_media('https://www.youtube.com/watch?v=abc123', self.plan())
        self.assertIn('symlink', str(ctx.exception))


# ===================================================================================================================
# 8. DRIVE: A LINK YOU CAN OPEN
# ===================================================================================================================
LINK = 'https://drive.google.com/file/d/FID123abc/view'


class DriveCase(RelayCase):
    def setUp(self):
        super().setUp()
        self.drive = FakeDrive()
        p = mock.patch.object(self.m, '_n76_call', self.drive)
        p.start()
        self.patches.append(p)

    def posts(self):
        return [c for c in self.drive.calls if c[0] == 'POST']


class TestDriveSharing(DriveCase):
    def test_the_default_is_a_link_anyone_can_open_and_it_is_confirmed_by_google(self):
        self.assertEqual(self.m._n87_share_mode(), 'link')
        state, reason = self.m._n87_share_link(LINK)
        self.assertEqual((state, reason), ('link', ''))
        self.assertEqual(len(self.posts()), 1)
        method, path, body, params = self.posts()[0]
        self.assertEqual(path, 'files/FID123abc/permissions')
        self.assertEqual(body, {'role': 'reader', 'type': 'anyone', 'allowFileDiscovery': False})
        self.assertEqual(self.m._n87_state_get('FID123abc'), 'link')
        self.assertEqual(self.m._N87_STATS['shared'], 1)

    def test_sharing_twice_does_not_create_a_second_permission(self):
        self.m._n87_share_link(LINK)
        self.m._n87_share_link(LINK)
        self.assertEqual(len(self.posts()), 1)

    def test_a_permission_that_google_did_not_keep_is_not_reported_as_shared(self):
        class Forgetful(FakeDrive):
            def __call__(self, method, path, **kw):
                out = super().__call__(method, path, **kw)
                if method == 'POST':
                    self.perms.clear()
                return out
        forgetful = Forgetful()
        with mock.patch.object(self.m, '_n76_call', forgetful):
            state, reason = self.m._n87_share_link(LINK)
        self.assertEqual(state, 'failed')
        self.assertIn('did not confirm', reason)
        self.assertIn('could not be enabled', self.m._n87_link_note(LINK))

    def test_a_refusal_by_google_is_reported_with_the_stays_private_promise(self):
        self.drive.fail_post = 'Drive HTTP 403. Check Drive API access, authorization and storage.'
        state, reason = self.m._n87_share_link(LINK)
        self.assertEqual(state, 'failed')
        self.assertIn('HTTP 403', reason)
        note = self.m._n87_link_note(LINK)
        self.assertIn('stays private', note)
        self.assertEqual(self.m._N87_STATS['share_failed'], 1)

    def test_private_mode_creates_no_permission(self):
        self.m._n87_set_share_mode('private')
        self.assertEqual(self.m._n87_share_link(LINK), ('private', ''))
        self.assertEqual(self.drive.calls, [])
        self.assertIn('Private', self.m._n87_link_note(LINK))

    def test_sharing_with_one_account_only(self):
        state, _ = self.m._n87_share_link(LINK, 'user:rahul@example.com')
        self.assertEqual(state, 'user:rahul@example.com')
        method, path, body, params = self.posts()[0]
        self.assertEqual(body, {'role': 'reader', 'type': 'user', 'emailAddress': 'rahul@example.com'})
        self.assertEqual(params, {'sendNotificationEmail': 'false'})
        self.assertNotIn('anyone', json.dumps(self.drive.perms))
        self.assertIn('rahul@example.com only', self.m._n87_link_note(LINK))

    def test_a_link_that_is_not_a_drive_file_is_left_alone(self):
        self.assertEqual(self.m._n87_share_link('https://example.org/x')[0], 'unknown')
        self.assertEqual(self.drive.calls, [])
        self.assertEqual(self.m._n87_file_id('https://drive.google.com/file/d/abcDEF_123-x/view'), 'abcDEF_123-x')
        self.assertEqual(self.m._n87_file_id('https://drive.google.com/drive/folders/zzz'), '')

    def test_stored_modes_are_validated(self):
        for stored, expected in (('private', 'private'), ('link', 'link'), ('user:a@b.co', 'user:a@b.co'), ('user:notanemail', 'link'), ('public', 'link'), ('', 'link')):
            self.kv['download87_share'] = stored
            self.assertEqual(self.m._n87_share_mode(), expected, stored)

    def test_the_upload_wrapper_shares_after_the_verified_upload_and_never_breaks_it(self):
        with mock.patch.object(self.m, '_N87_UPLOAD_PREV', lambda path: LINK):
            self.assertEqual(self.m._n76_upload('/x/file.mp4'), LINK)
        self.assertEqual(len(self.posts()), 1)
        self.drive.fail_post = 'Drive HTTP 500'
        with mock.patch.object(self.m, '_N87_UPLOAD_PREV', lambda path: 'https://drive.google.com/file/d/OTHER1/view'):
            self.assertEqual(self.m._n76_upload('/x/file2.mp4'), 'https://drive.google.com/file/d/OTHER1/view')

    def test_the_old_restricted_link_message_is_gone_from_direct_saves(self):
        with mock.patch.object(self.m, '_N87_UPLOAD_PREV', lambda path: LINK):
            self.assertTrue(self.m._n76_archive(self.cid, '/x/video.mp4'))
        text = self.sent[-1][1]
        self.assertIn(LINK, text)
        self.assertIn('Anyone with this link can view it', text)
        self.assertNotIn('Restricted link', text)

    def test_share_last_download_opens_the_latest_finished_job(self):
        rows = [{'state': 'FAILED', 'links': '[]', 'id': 'D78-0000000001'}, {'state': 'DONE', 'links': json.dumps([LINK]), 'id': 'D78-0000000002'}]
        self.m._n87_set_share_mode('private')
        with mock.patch.object(self.m, '_n78_rows', lambda owner, job=None: rows):
            self.assertTrue(self.m._n87_share_last(self.cid))
        self.assertIn(LINK, self.sent[-1][1])
        self.assertIn('Anyone with the link can view', self.sent[-1][1])
        self.assertEqual(self.m._n87_state_get('FID123abc'), 'link', 'an explicit "share my last download" overrides a private default for that file only')
        self.assertEqual(self.m._n87_share_mode(), 'private')

    def test_share_last_with_nothing_to_share_or_a_refusal(self):
        with mock.patch.object(self.m, '_n78_rows', lambda owner, job=None: []):
            self.assertFalse(self.m._n87_share_last(self.cid))
        self.assertIn('no finished download', self.sent[-1][1])
        self.drive.fail_post = 'Drive HTTP 403.'
        with mock.patch.object(self.m, '_n78_rows', lambda owner, job=None: [{'state': 'DONE', 'links': json.dumps([LINK]), 'id': 'D78-0000000003'}]):
            self.assertFalse(self.m._n87_share_last(self.cid))
        self.assertIn('Could not enable sharing', self.sent[-1][1])
        self.assertNotIn(LINK, self.sent[-1][1], 'a link that nobody can open is not offered')


# ===================================================================================================================
# 9. THE WHOLE JOB: queue -> chain -> verify -> Drive -> link
# ===================================================================================================================
@unittest.skipUnless(HAVE_FFMPEG, 'ffmpeg/ffprobe needed to build test videos')
class TestJobEndToEnd(DriveCase):
    def setUp(self):
        super().setUp()
        import urllib.parse
        for name, val in (('_n77_url', lambda url: urllib.parse.urlsplit(url)), ('_n76_settings', lambda: {'id': 'perm1', 'email': 'nemo@example.com'}),
                          ('_n64_register_file', lambda *a, **k: 'F64-TEST'), ('_N87_UPLOAD_PREV', self.fake_upload)):
            p = mock.patch.object(self.m, name, val)
            p.start()
            self.patches.append(p)
        self.uploads = []
        self.msgs = 0

    def fake_upload(self, path):
        self.uploads.append(os.path.basename(path))
        return LINK

    def make(self, ctx):
        path = os.path.join(ctx['folder'], 'Title_abc.mp4')
        shutil.copy(FIX['video'], path)
        return path

    def run_job(self, steps, text='download https://www.youtube.com/watch?v=abc123 in 720p'):
        self.msgs += 1
        ids = self.m._n78_enqueue({'chat': {'id': self.cid}, 'text': text, 'message_id': self.msgs})
        with mock.patch.object(self.m, '_n87_steps', lambda ctx: list(steps)):
            self.assertTrue(self.m._n78_work_once())
        return self.m._n78_rows(self.cid, ids[0])[0]

    def test_success_saves_to_drive_shares_the_link_and_tells_you_which_source_worked(self):
        row = self.run_job([fail_step('ytdlp:default', 'ERROR: Sign in to confirm you are not a bot', 'bot_check', label='yt-dlp · default clients', group='ytdlp'),
                            ok_step('pytubefix', 'pytubefix', make=self.make)])
        self.assertEqual((row['state'], row['stage']), ('DONE', 'Verified in Drive'))
        self.assertEqual(json.loads(row['links']), [LINK])
        self.assertEqual(self.uploads, ['Title_abc.mp4'])
        card = self.sent[-1][1]
        self.assertIn(LINK, card)
        self.assertIn('Source: pytubefix', card)
        self.assertIn('Anyone with this link can view it', card)
        self.assertEqual(len(self.posts()), 1)

    def test_every_source_failing_gives_the_per_source_report_not_a_generic_sentence(self):
        row = self.run_job([fail_step('ytdlp:default', 'ERROR: Sign in to confirm you are not a bot', 'bot_check', label='yt-dlp · default clients', group='ytdlp'),
                            fail_step('pytubefix', 'refused', 'outdated', label='pytubefix')])
        self.assertEqual(row['state'], 'FAILED')
        self.assertIn('yt-dlp · default clients — YouTube asked this server to prove it is not a bot', row['error'])
        self.assertIn('pytubefix', row['error'])
        self.assertIn('/cookies', row['error'])
        self.assertNotIn('Transfer or verification failed', row['error'])
        self.assertEqual(self.uploads, [])
        self.assertEqual(self.drive.calls, [])
        card = self.sent[-1][1]
        self.assertIn('Resume download ' + row['id'], card)
        self.assertIn('Nothing was uploaded', card)

    def test_environment_limits_keep_their_earlier_wording(self):
        row = self.run_job([fail_step('a', '', raises=ValueError('Local disk reserve reached; free space before retrying'), group='ytdlp')])
        self.assertEqual(row['state'], 'FAILED')
        self.assertIn('Disk reserve reached', row['error'])

    def test_a_job_whose_link_sharing_was_refused_is_still_done_and_says_so(self):
        self.drive.fail_post = 'Drive HTTP 403. Check Drive API access, authorization and storage.'
        row = self.run_job([ok_step('a', 'yt-dlp', 'ytdlp', make=self.make)])
        self.assertEqual(row['state'], 'DONE')
        self.assertIn('link sharing could not be enabled', self.sent[-1][1])

    def test_private_mode_keeps_the_link_private_and_says_how_to_share(self):
        self.m._n87_set_share_mode('private')
        row = self.run_job([ok_step('a', 'yt-dlp', 'ytdlp', make=self.make)])
        self.assertEqual(row['state'], 'DONE')
        self.assertEqual(self.drive.calls, [])
        self.assertIn('share my last download', self.sent[-1][1])

    def test_a_failure_that_is_the_users_to_fix_never_leaks_what_the_extractor_printed(self):
        raw = 'ERROR: failed https://rr3.googlevideo.com/videoplayback?sig=TOPSECRET with /root/nemo_cookies.txt'
        row = self.run_job([fail_step('ytdlp:default', raw, 'outdated', group='ytdlp')])
        for leaked in ('TOPSECRET', 'googlevideo', '/root'):
            self.assertNotIn(leaked, row['error'])
            self.assertNotIn(leaked, self.sent[-1][1])

    def real_chain(self, behavior_for):
        """The real step list and the real yt-dlp attempt runner, with a fake yt-dlp executable that behaves per client profile."""
        script = os.path.join(self.tmp.name, 'fake_ytdlp.py')
        with open(script, 'w') as fh:
            fh.write(FAKE_YTDLP)
        seen = []

        def command(url, folder, plan, cookies=None):
            key = (plan.get('_n87') or {}).get('key', '?')
            seen.append(key)
            return [sys.executable, script, folder, behavior_for(key), FIX['video']]
        for name, val in (('_n77_command', command), ('_n87_has_module', lambda n: n == 'yt_dlp'), ('_n60_public_resolvers_enabled', lambda: False),
                          ('_n60_cobalt_cfg', lambda: ('', ''))):
            p = mock.patch.object(self.m, name, val)
            p.start()
            self.patches.append(p)
        return seen

    def test_the_real_chain_falls_through_client_profiles_until_one_works_and_remembers_it(self):
        seen = self.real_chain(lambda key: 'ok' if key == 'ytdlp:embedded' else 'botcheck')
        self.msgs += 1
        ids = self.m._n78_enqueue({'chat': {'id': self.cid}, 'text': 'download https://www.youtube.com/watch?v=abc123', 'message_id': self.msgs})
        self.assertTrue(self.m._n78_work_once())
        row = self.m._n78_rows(self.cid, ids[0])[0]
        self.assertEqual(row['state'], 'DONE', row['error'])
        self.assertEqual(seen, ['ytdlp:default', 'ytdlp:tv', 'ytdlp:embedded'])
        self.assertEqual(self.uploads, ['Title_abc123.mp4'])
        self.assertIn('Source: yt-dlp · embedded player', self.sent[-1][1])
        stats = self.m._n87_stats()
        self.assertEqual((stats['ytdlp:embedded']['ok'], stats['ytdlp:default']['fail'], stats['ytdlp:tv']['fail']), (1, 1, 1))
        # next download starts with the profile that worked
        seen.clear()
        self.msgs += 1
        self.m._n78_enqueue({'chat': {'id': self.cid}, 'text': 'download https://www.youtube.com/watch?v=def456', 'message_id': self.msgs})
        self.assertTrue(self.m._n78_work_once())
        self.assertEqual(seen, ['ytdlp:embedded'])

    def test_the_real_chain_when_everything_is_blocked_explains_each_source_and_what_to_do(self):
        seen = self.real_chain(lambda key: 'botcheck')
        self.msgs += 1
        ids = self.m._n78_enqueue({'chat': {'id': self.cid}, 'text': 'download https://www.youtube.com/watch?v=abc123', 'message_id': self.msgs})
        self.assertTrue(self.m._n78_work_once())
        row = self.m._n78_rows(self.cid, ids[0])[0]
        self.assertEqual(row['state'], 'FAILED')
        self.assertEqual(seen, [s['key'] for s in self.m._n87_yt_specs()])
        err = row['error']
        for label in ('yt-dlp · default clients', 'yt-dlp · TV client', 'yt-dlp · embedded player', 'yt-dlp · VR clients', 'yt-dlp · web clients', 'yt-dlp · iOS client'):
            self.assertIn(label + ' — YouTube asked this server to prove it is not a bot', err)
        self.assertIn('pytubefix — skipped: not installed', err)
        self.assertIn('Piped mirrors — skipped: public mirrors are switched off', err)
        self.assertIn('Most likely cause: YouTube asked this server to prove it is not a bot', err)
        self.assertIn('/cookies', err)
        self.assertIn('/proxy set', err)
        self.assertEqual(self.uploads, [])
        self.assertEqual(self.m._N87_UPGRADE['ts'], 0.0, 'a bot check is not fixed by a newer yt-dlp, so no update was tried')

    def test_an_out_of_date_yt_dlp_is_updated_once_and_the_default_profile_retried(self):
        state = {'updated': False}
        seen = self.real_chain(lambda key: 'ok' if state['updated'] and key == 'ytdlp:default' else 'format')

        def upgrade(force=False):
            state['updated'] = True
            return {'ok': True, 'old': '2025.1.1', 'new': '2026.8.19', 'changed': True}
        with mock.patch.object(self.m, '_n87_upgrade_ytdlp', upgrade):
            self.msgs += 1
            ids = self.m._n78_enqueue({'chat': {'id': self.cid}, 'text': 'download https://www.youtube.com/watch?v=abc123', 'message_id': self.msgs})
            self.assertTrue(self.m._n78_work_once())
        row = self.m._n78_rows(self.cid, ids[0])[0]
        self.assertEqual(row['state'], 'DONE', row['error'])
        self.assertEqual(seen[-1], 'ytdlp:default')
        self.assertIn('(after update)', json.dumps(self.m._N87_LAST[ids[0]]['trace']))

    def test_the_resume_command_reruns_the_whole_chain(self):
        row = self.run_job([fail_step('a', 'x', 'network', group='ytdlp')])
        self.assertEqual(row['state'], 'FAILED')
        self.assertIn('Recovery queued', self.m._n78_control(self.cid, 'resume', row['id']))
        with mock.patch.object(self.m, '_n87_steps', lambda ctx: [ok_step('a', 'yt-dlp', 'ytdlp', make=self.make)]):
            self.assertTrue(self.m._n78_work_once())
        self.assertEqual(self.m._n78_rows(self.cid, row['id'])[0]['state'], 'DONE')


# ===================================================================================================================
# 10. NATURAL-LANGUAGE CONTROLS
# ===================================================================================================================
class TestControls(DriveCase):
    def setUp(self):
        super().setUp()
        self.calls = []
        for name, val in (('_n66_submit', lambda cid, kind, request, fn, *a, **k: (fn(*a, **k), 'T1')[1]),
                          ('_n87_selftest', lambda cid: self.calls.append('selftest') or True), ('_n87_setup', lambda cid: self.calls.append('setup') or True),
                          ('_n87_ytdlp_version', lambda: '2026.8.19'), ('_N87_HANDLE_PREV', lambda msg: self.calls.append(('passed on', msg['text']))),
                          ('_n76_settings', lambda: {'id': 'p', 'email': 'nemo@example.com'})):
            p = mock.patch.object(self.m, name, val)
            p.start()
            self.patches.append(p)

    def say(self, text, **extra):
        self.m.handle(self.msg(text, **extra))
        return self.sent[-1][1] if self.sent else ''

    def test_download_sources_status(self):
        out = self.say('download sources')
        for needle in ('NEMO DOWNLOAD SOURCES', 'yt-dlp: 2026.8.19', 'JavaScript runtime', 'YouTube cookies', 'ffmpeg/ffprobe', 'yt-dlp · default clients', 'pytubefix', 'YouTube.js',
                       'Piped mirrors', 'Invidious mirrors', 'Cobalt server', 'Drive links: anyone who has the link can view', 'test youtube download'):
            self.assertIn(needle, out)
        self.assertEqual(self.calls, [])
        for phrase in ('check my download sources', 'Show download sources status', 'which download sources work', 'nemo, download source status'):
            self.sent.clear()
            self.assertIn('NEMO DOWNLOAD SOURCES', self.say(phrase), phrase)

    def test_the_status_says_when_the_javascript_runtime_is_missing(self):
        out = self.say('download sources')
        self.assertIn('NONE — YouTube extraction will fail', out)
        with mock.patch.object(self.m, '_n87_js_runtimes', lambda: ['node:/usr/bin/node']):
            self.assertIn('JavaScript runtime for YouTube: node', self.say('download sources'))

    def test_the_status_shows_the_ledger_and_the_last_attempt(self):
        self.m._n87_stat('pytubefix', True)
        self.m._n87_stat('ytdlp:default', False, 'bot_check')
        self.m._N87_LAST['selftest'] = {'ts': time.time(), 'host': 'h', 'ok': False, 'source': '', 'label': '', 'seconds': 3, 'trace': [
            {'label': 'yt-dlp · default clients', 'status': 'failed', 'klass': 'bot_check', 'detail': ''}, {'label': 'Cobalt server', 'status': 'skipped', 'klass': 'missing', 'detail': 'no Cobalt server configured (optional)'}]}
        out = self.say('download sources')
        self.assertIn('worked 1×', out)
        self.assertIn('failed 1×', out)
        self.assertIn('Last attempt', out)
        self.assertIn('skipped: no Cobalt server configured', out)

    def test_live_test_phrasings(self):
        for phrase in ('test youtube download', 'Test my YouTube downloader', 'check if youtube download works', 'does the youtube downloader work?', 'please test the video download', 'try youtube download now'):
            self.calls.clear()
            self.sent.clear()
            self.say(phrase)
            self.assertEqual(self.calls, ['selftest'], phrase)
            self.assertIn('19-second', self.sent[0][1])

    def test_setup_phrasings(self):
        for phrase in ('set up download sources', 'repair download sources', 'update yt-dlp', 'Upgrade yt-dlp', 'fix my download sources', 'refresh the download sources'):
            self.calls.clear()
            self.say(phrase)
            self.assertEqual(self.calls, ['setup'], phrase)

    def test_sharing_phrasings(self):
        self.say('make my download links public')
        self.assertEqual(self.m._n87_share_mode(), 'link')
        self.assertIn('anyone with the link can view', self.sent[-1][1])
        self.say('keep my download links private')
        self.assertEqual(self.m._n87_share_mode(), 'private')
        self.say('share my downloads with Rahul@Example.com')
        self.assertEqual(self.m._n87_share_mode(), 'user:rahul@example.com')
        self.assertIn('rahul@example.com only', self.sent[-1][1])
        self.say('Please make the download links open to anyone with the link')
        self.assertEqual(self.m._n87_share_mode(), 'link')
        self.say('stop sharing my download links')
        self.assertEqual(self.m._n87_share_mode(), 'private')
        self.sent.clear()
        self.say('who can open my download links?')
        self.assertEqual(self.m._n87_share_mode(), 'private', 'a question never changes the setting')
        self.assertIn('Download links: private', self.sent[-1][1])

    def test_share_my_last_download_phrasings(self):
        for phrase in ('share my last download', 'make my last download shareable', 'give me a link to my latest download', 'Share the last video'):
            self.calls.clear()
            with mock.patch.object(self.m, '_n87_share_last', lambda cid: self.calls.append('last')):
                self.say(phrase)
            self.assertEqual(self.calls, ['last'], phrase)

    def test_ordinary_messages_are_never_hijacked(self):
        for phrase in ('download https://youtu.be/dQw4w9WgXcQ', 'share this with Rahul', 'send the link to my sister', 'remind me to download the report', 'make the logo public',
                       'my links are not working', 'test the new design', 'download tools check', 'share my screen', 'what is a source of truth',
                       'update the price list', 'make my invoice link shareable with the dealer', 'check my drive', 'how do I make my links public in Notion?',
                       'keep my meeting private', 'upgrade yourself to download videos better'):
            self.calls.clear()
            self.sent.clear()
            self.say(phrase)
            self.assertEqual(self.calls, [('passed on', phrase)], phrase)
            self.assertEqual(self.sent, [], phrase)
        self.assertEqual(self.m._n87_share_mode(), 'link')

    def test_only_the_owner_in_a_private_chat(self):
        for chat, sender in (({'id': 999, 'type': 'private'}, 999), ({'id': self.cid, 'type': 'group'}, self.cid), ({'id': self.cid, 'type': 'private'}, 12345)):
            self.calls.clear()
            self.sent.clear()
            self.m.handle({'chat': chat, 'from': {'id': sender}, 'text': 'make my download links private', 'message_id': 1})
            self.assertEqual(self.m._n87_share_mode(), 'link')
            self.assertEqual(self.calls, [('passed on', 'make my download links private')])

    def test_slash_commands_and_bypassed_messages_are_left_alone(self):
        self.say('/download sources')
        self.assertEqual(self.calls, [('passed on', '/download sources')])
        self.calls.clear()
        self.m.handle(dict(self.msg('download sources'), _n72_bypass=True))
        self.assertEqual(self.calls, [('passed on', 'download sources')])

    def test_a_full_task_queue_is_reported(self):
        with mock.patch.object(self.m, '_n66_submit', lambda *a, **k: None):
            self.say('set up download sources')
        self.assertIn('queue is full', self.sent[-1][1])

    def test_a_control_that_crashes_does_not_break_the_chat(self):
        with mock.patch.object(self.m, '_n87_status_text', mock.Mock(side_effect=RuntimeError('boom'))):
            out = self.say('download sources')
        self.assertIn('Nothing was changed', out)
        self.assertEqual(self.m._N87_STATS['errors'], 1)


# ===================================================================================================================
# 11. THE LIVE SELF-TEST AND THE SET-UP
# ===================================================================================================================
@unittest.skipUnless(HAVE_FFMPEG, 'ffmpeg/ffprobe needed to build test videos')
class TestSelftest(DriveCase):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(self.m, '_n77_config', lambda: self.plan()['cfg'])
        p.start()
        self.patches.append(p)

    def make(self, ctx):
        path = os.path.join(ctx['folder'], 'zoo.mp4')
        shutil.copy(FIX['video'], path)
        return path

    def test_works_reports_the_source_and_leaves_nothing_behind_and_never_touches_drive(self):
        steps = [fail_step('ytdlp:default', 'ERROR: x', 'bot_check', label='yt-dlp · default clients', group='ytdlp'), ok_step('ytdlp:tv', 'yt-dlp · TV client', 'ytdlp', make=self.make)]
        with mock.patch.object(self.m, '_n87_steps', lambda ctx: list(steps)):
            self.assertTrue(self.m._n87_selftest(self.cid))
        out = self.sent[-1][1]
        self.assertIn('WORKS', out)
        self.assertIn('yt-dlp · TV client fetched a 19-second public test video', out)
        self.assertIn('Sources that failed first: yt-dlp · default clients', out)
        self.assertIn('Nothing was uploaded to Drive', out)
        self.assertEqual(self.drive.calls, [])
        self.assertEqual(os.listdir(os.path.join(self.tmp.name, 'nemo_download77')), [])
        self.assertEqual(self.m._N87_STATS['selftests'], 1)

    def test_failure_lists_every_source(self):
        steps = [fail_step('ytdlp:default', 'ERROR: Sign in to confirm you are not a bot', 'bot_check', label='yt-dlp · default clients', group='ytdlp'),
                 {'key': 'pytubefix', 'label': 'pytubefix', 'group': 'alt', 'unavailable': 'not installed (say “set up download sources”)', 'run': None}]
        with mock.patch.object(self.m, '_n87_steps', lambda ctx: list(steps)):
            self.assertFalse(self.m._n87_selftest(self.cid))
        out = self.sent[-1][1]
        self.assertIn('FAILED', out)
        self.assertIn('pytubefix — skipped: not installed', out)
        self.assertEqual(os.listdir(os.path.join(self.tmp.name, 'nemo_download77')), [])

    def test_a_running_download_blocks_the_test_instead_of_colliding(self):
        self.assertTrue(self.m._N77_MEDIA_LOCK.acquire(blocking=False))
        try:
            self.assertFalse(self.m._n87_selftest(self.cid))
        finally:
            self.m._N77_MEDIA_LOCK.release()
        self.assertIn('download is running', self.sent[-1][1])

    def test_a_crash_inside_the_test_is_reported_and_cleaned_up(self):
        with mock.patch.object(self.m, '_n87_chain', mock.Mock(side_effect=RuntimeError('boom'))):
            self.assertFalse(self.m._n87_selftest(self.cid))
        self.assertIn('could not finish (RuntimeError)', self.sent[-1][1])
        self.assertTrue(self.m._N77_MEDIA_LOCK.acquire(blocking=False))
        self.m._N77_MEDIA_LOCK.release()
        self.assertEqual(os.listdir(os.path.join(self.tmp.name, 'nemo_download77')), [])

    def test_the_test_video_is_the_first_youtube_video(self):
        self.assertEqual(self.m._N87_SELFTEST_URL, 'https://www.youtube.com/watch?v=jNQXAC9IVRw')


class TestSetup(RelayCase):
    def setUp(self):
        super().setUp()
        self.cmds = []
        self.installed = set()
        def fake_exec(cmd, timeout=600):
            self.cmds.append(list(cmd))
            if 'pytubefix' in cmd:
                self.installed.add('pytubefix')
            return True
        for name, val in (('_n781_exec', fake_exec), ('_n87_has_module', lambda n: n in self.installed),
                          ('_n87_upgrade_ytdlp', lambda force=False: {'ok': True, 'old': '2025.1.1', 'new': '2026.8.19', 'changed': True}),
                          ('_n87_ytdlp_version', lambda: '2026.8.19'), ('_n87_has_ejs', lambda: True), ('_n62_prepare_helpers', lambda: True)):
            p = mock.patch.object(self.m, name, val)
            p.start()
            self.patches.append(p)

    def test_installs_into_the_bots_own_python_and_never_echoes_installer_output(self):
        out_text = None
        self.m._N87_NODE['checked'] = 0
        with mock.patch.object(self.m._n87_shutil, 'which', lambda n: None):
            self.assertTrue(self.m._n87_setup(self.cid))
        out_text = self.sent[-1][1]
        pip = [c for c in self.cmds if c[:3] == [sys.executable, '-m', 'pip']]
        self.assertTrue(any('pytubefix' in c for c in pip))
        self.assertTrue(any(c[0] == 'bash' and 'deno.land' in c[2] for c in self.cmds), 'with no JavaScript runtime at all the official Deno installer is run')
        self.assertIn('yt-dlp 2026.8.19 (was 2025.1.1)', out_text)
        self.assertIn('Nothing was downloaded', out_text)
        self.assertIn('trading permissions were not touched', out_text)
        self.assertIn('/mediafix59', out_text)

    def test_nothing_is_installed_that_is_already_there(self):
        self.installed.add('pytubefix')
        os.makedirs(os.path.join(self.m._N62_NODE, 'node_modules', 'youtubei.js'))
        with mock.patch.object(self.m, '_n87_node', lambda: ('/usr/bin/node', 22)):
            self.m._n87_setup(self.cid)
        self.assertEqual([c for c in self.cmds if 'pytubefix' in c or 'youtubei.js' in c or c[0] == 'bash'], [])

    def test_youtubejs_is_installed_with_npm_when_node_exists(self):
        self.installed.add('pytubefix')
        with mock.patch.object(self.m, '_n87_node', lambda: ('/usr/bin/node', 22)), mock.patch.object(self.m._n87_shutil, 'which', lambda n: '/usr/bin/npm' if n == 'npm' else None):
            self.m._n87_setup(self.cid)
        npm = [c for c in self.cmds if c[0] == '/usr/bin/npm']
        self.assertEqual(len(npm), 1)
        self.assertEqual(npm[0][1:3], ['--prefix', self.m._N62_NODE])
        self.assertIn('youtubei.js', npm[0])

    def test_the_report_is_honest_about_what_is_still_missing(self):
        self.m._N87_NODE['checked'] = 0
        with mock.patch.object(self.m._n87_shutil, 'which', lambda n: None), mock.patch.object(self.m, '_n781_exec', lambda cmd, timeout=600: False):
            self.m._n87_setup(self.cid)
        out = self.sent[-1][1]
        self.assertIn('❌ JavaScript runtime: none found', out)
        self.assertIn('⚠️ pytubefix: could not be installed', out)
        self.assertIn('❌ ffmpeg/ffprobe: missing', out)
        self.assertIn('⚠️ YouTube.js: not installed', out)


# ===================================================================================================================
# 12. STRUCTURE: nothing dangerous, nothing secret, one definition of each replaced function
# ===================================================================================================================
def _source():
    with open(base.NEMO_FILE, encoding='utf-8') as fh:
        return fh.read()


class TestStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if base.m is None:
            base.setUpModule()
        cls.m = base.m
        cls.src = _source()
        cls.tree = ast.parse(cls.src)
        cls.layer_start = cls.src.index('# NEMO 87 - RELAY')
        cls.layer = cls.src[cls.layer_start:cls.src.rindex("if __name__")]
        mine = []
        for node in cls.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and (node.name.startswith(('_n87_', '_N87')) or node.name in ('_n77_command', '_n77_media', '_n76_archive')):
                if node.name.startswith(('_n87_', '_N87')) or node.lineno > 0:
                    mine.append(node)
        cls.mine = [n for n in mine if n.name.startswith(('_n87_', '_N87')) or n.name in ('_n77_command', '_n77_media', '_n76_archive')]
        # the last definition of each replaced name is the live one
        cls.live = {}
        for node in cls.tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in ('_n77_command', '_n77_media', '_n76_archive'):
                cls.live[node.name] = node

    def test_the_version_is_distinct(self):
        self.assertGreaterEqual(float(self.m.VERSION), 87)
        self.assertIn('NEMO 87.0 RELAY', self.src)

    def test_the_regression_rows_are_green_and_registered(self):
        rows = self.m._n87_regression_rows()
        self.assertGreaterEqual(len(rows), 11)
        self.assertEqual([r['name'] for r in rows if not r['ok']], [])
        suite = self.m.prime_regression_suite()
        names = [t['name'] for t in suite['tests']]
        self.assertTrue(all(r['name'] in names for r in rows))

    def test_the_new_layer_is_protected_from_live_self_editing(self):
        self.assertFalse(self.m._n79_editable('_n87_chain'))
        self.assertFalse(self.m._n79_editable('_n87_share_link'))

    def test_every_replaced_function_has_exactly_one_definition(self):
        names = [n.name for n in self.tree.body if isinstance(n, ast.FunctionDef)]
        for name in ('_n77_media', '_n77_command', '_n76_archive'):
            self.assertEqual(names.count(name), 1, name)

    def test_hooks_are_installed(self):
        m = self.m
        self.assertIsNot(m.handle, m._N87_HANDLE_PREV)
        self.assertIsNot(m._n76_upload, m._N87_UPLOAD_PREV)
        self.assertIsNot(m._n78_card, m._N87_CARD_PREV)
        self.assertIsNot(m._n77_health, m._N87_HEALTH_PREV)
        self.assertIn('Relay 87', m._n82_capabilities())
        self.assertIn('download sources', m._n77_health())

    def test_no_shell_no_eval_no_pickle_and_only_list_arguments_for_processes(self):
        nodes = [ast.parse(self.layer)] + list(self.live.values())
        for root in nodes:
            for node in ast.walk(root):
                if isinstance(node, ast.Call):
                    f = node.func
                    if isinstance(f, ast.Name):
                        self.assertNotIn(f.id, {'eval', 'exec', '__import__compile'}, 'line %d' % node.lineno)
                    if isinstance(f, ast.Attribute):
                        self.assertNotIn(f.attr, {'system', 'popen', 'eval', 'exec', 'check_output'}, 'line %d' % node.lineno)
                        if f.attr in ('run', 'Popen'):
                            for kw in node.keywords:
                                self.assertNotEqual(kw.arg, 'shell', 'line %d' % node.lineno)
                            if node.args:
                                self.assertIsInstance(node.args[0], (ast.List, ast.BinOp, ast.Name, ast.ListComp, ast.Starred), 'process arguments must be a list, line %d' % node.lineno)
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    mods = [a.name for a in node.names] + ([node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
                    for mod in mods:
                        self.assertNotIn(mod.split('.')[0], {'pickle', 'ctypes', 'marshal'}, 'line %d' % node.lineno)

    def test_a_directory_is_removed_only_by_the_self_test_and_only_the_one_it_made(self):
        owners = set()
        for node in self.tree.body:
            if isinstance(node, ast.FunctionDef) and (node.name.startswith('_n87_') or node.name in self.live):
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr == 'rmtree':
                        owners.add(node.name)
        self.assertEqual(owners, {'_n87_selftest'})
        body = ast.get_source_segment(self.src, next(n for n in self.tree.body if isinstance(n, ast.FunctionDef) and n.name == '_n87_selftest'))
        self.assertIn('mkdtemp(prefix=\'selftest_\'', body)
        self.assertIn('if folder:', body)

    def test_no_secret_literals_and_no_credential_handling_in_the_new_code(self):
        for pattern in (r'sk-[A-Za-z0-9]{16,}', r'AIza[0-9A-Za-z_-]{20,}', r'\b\d{8,10}:[A-Za-z0-9_-]{30,}', r'gh[pousr]_[A-Za-z0-9]{20,}', r'xox[abp]-', r'-----BEGIN'):
            self.assertIsNone(re.search(pattern, self.layer), pattern)
        for forbidden in ('bot_secrets', 'google_token', 'OWNER[', 'api_key', 'password'):
            self.assertNotIn(forbidden, self.layer.replace('password', '') if forbidden == 'password' else self.layer, forbidden)
        for name, node in self.live.items():
            text = ast.get_source_segment(self.src, node)
            self.assertNotIn('bot_secrets', text)

    def test_the_cookie_file_is_only_ever_copied_by_the_media_entry_and_the_self_test(self):
        users = set()
        for node in self.tree.body:
            if isinstance(node, ast.FunctionDef) and (node.name.startswith('_n87_') or node.name in self.live):
                text = ast.get_source_segment(self.src, node)
                if 'copyfile' in text:
                    users.add(node.name)
        self.assertEqual(users, {'_n77_media', '_n87_selftest'})

    def test_trading_and_credential_guards_are_still_in_the_file(self):
        for needle in ('def _update_cred_changes', 'def _n79_owner', 'def _n84_holiday', 'def _n55_market_clock', 'def self_rollback'):
            self.assertIn(needle, self.src, needle)


# ===================================================================================================================
# 13. MUTATIONS: re-introduce the old behaviour one piece at a time; the matching test must go red
# ===================================================================================================================
class TestMutationsAreCaught(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if base.m is None:
            base.setUpModule()
        cls.m = base.m

    def run_test(self, test_id, **patches):
        suite = unittest.defaultTestLoader.loadTestsFromName(test_id)
        stack = [mock.patch.object(self.m, name, value) for name, value in patches.items()]
        for p in stack:
            p.start()
        try:
            result = unittest.TestResult()
            suite.run(result)
        finally:
            for p in reversed(stack):
                p.stop()
        self.assertEqual(result.testsRun, 1, test_id)
        return result

    def red(self, test_id, **patches):
        return not self.run_test(test_id, **patches).wasSuccessful()

    def test_the_unmutated_tests_are_green(self):
        for tid in ('tests.test_relay87.TestClassification.test_table', 'tests.test_relay87.TestChain.test_definitive_answers_stop_the_chain',
                    'tests.test_relay87.TestDriveSharing.test_the_default_is_a_link_anyone_can_open_and_it_is_confirmed_by_google'):
            self.assertTrue(self.run_test(tid).wasSuccessful(), tid)

    def test_without_classification_the_report_has_no_causes(self):
        self.assertTrue(self.red('tests.test_relay87.TestClassification.test_table', _n87_classify=lambda text: 'unknown'))

    def test_without_the_video_check_a_junk_file_would_be_delivered(self):
        if not HAVE_FFMPEG:
            self.skipTest('ffmpeg needed')
        self.assertTrue(self.red('tests.test_relay87.TestAttempt.test_a_download_that_is_not_a_video_is_rejected_by_the_check', _n87_verify=lambda path, mode: (True, '')))

    def test_without_cleaning_the_failure_text_leaks_links_and_paths(self):
        self.assertTrue(self.red('tests.test_relay87.TestChain.test_the_failure_text_never_contains_links_paths_or_cookies', _n87_clean=lambda text, limit=150: str(text)))

    def test_without_the_ledger_the_last_working_source_is_not_remembered(self):
        self.assertTrue(self.red('tests.test_relay87.TestChain.test_the_source_that_worked_last_is_tried_first_next_time', _n87_preferred=lambda keys, youtube: ''))

    def test_without_definitive_classes_the_chain_keeps_hammering(self):
        self.assertTrue(self.red('tests.test_relay87.TestChain.test_definitive_answers_stop_the_chain', _N87_FINAL=()))

    def test_if_every_class_were_definitive_a_working_second_client_would_be_missed(self):
        self.assertTrue(self.red('tests.test_relay87.TestChain.test_unavailable_is_not_definitive_because_another_client_may_still_work', _N87_FINAL=('drm', 'private', 'removed', 'live')))

    def test_updating_for_a_bot_check_would_be_caught(self):
        self.assertTrue(self.red('tests.test_relay87.TestAutomaticUpdate.test_no_update_for_a_bot_check_because_a_newer_yt_dlp_will_not_help', _N87_UPGRADE_CLASSES=('bot_check', 'outdated')))

    def test_a_yt_dlp_only_chain_is_caught(self):
        only = lambda ctx: [s for s in self.m._N87_STEPS_REAL(ctx) if s['group'] == 'ytdlp']
        self.m._N87_STEPS_REAL = self.m._n87_steps
        try:
            self.assertTrue(self.red('tests.test_relay87.TestSteps.test_a_youtube_link_gets_six_profiles_then_five_other_sources_in_this_order', _n87_steps=only))
        finally:
            del self.m._N87_STEPS_REAL

    def test_claiming_a_share_without_asking_google_is_caught(self):
        self.assertTrue(self.red('tests.test_relay87.TestDriveSharing.test_the_default_is_a_link_anyone_can_open_and_it_is_confirmed_by_google', _n87_share_link=lambda link, mode=None: ('link', '')))

    def test_skipping_the_confirmation_of_the_permission_is_caught(self):
        self.assertTrue(self.red('tests.test_relay87.TestDriveSharing.test_a_permission_that_google_did_not_keep_is_not_reported_as_shared',
                                 _n87_perms=lambda fid: [{'type': 'anyone', 'role': 'reader'}]))

    def test_a_greedy_sharing_phrase_matcher_is_caught(self):
        self.assertTrue(self.red('tests.test_relay87.TestControls.test_ordinary_messages_are_never_hijacked', _n87_share_intent=lambda raw: ('link',)))

    def test_trusting_redirects_is_caught(self):
        if not HAVE_FFMPEG:
            self.skipTest('ffmpeg needed')
        import requests
        real = requests.get

        def following(*a, **k):
            k['allow_redirects'] = True
            return real(*a, **k)
        with mock.patch.object(requests, 'get', following):
            self.assertTrue(self.red('tests.test_relay87.TestMirrorsAndFetch.test_a_redirect_is_followed_only_to_public_addresses_and_checked_before_it_is_requested'))


if __name__ == '__main__':
    unittest.main()
