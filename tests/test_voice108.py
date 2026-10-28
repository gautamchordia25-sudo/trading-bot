"""Nemo v108 "Voice": answers appear as a live draft while they are written (with a stop button); a voice note goes through the whole of today's Nemo and is answered with a
real voice-note bubble in the reply's language; quiet hours, snooze and a daily digest hold what Nemo would send on its own (never replies, never urgent things); tone dials per
person and situation; reactions instead of "you are welcome"; polls, quiz polls and round video notes.

Offline. No Telegram, no network, no real AI and no real voice service: Telegram calls, the provider stream and the voice engine are fakes (the fake voice engine makes a real
MP3 with ffmpeg when it is installed, so the OGG conversion and the video note run for real).

    NEMO_FILE=/path/to/nemotron_bot.py python -m unittest tests.test_voice108 -v
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest import mock

from tests import test_cortex83 as base
from tests.test_cortex83 import OWNER_ID
from tests.test_steady106 import SteadyCase

FFMPEG = shutil.which('ffmpeg')


def setUpModule():
    if base.m is None:
        base.setUpModule()


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def layer_source():
    src = read(base.NEMO_FILE)
    i = src.index('# NEMO 108 - VOICE')
    j = src.index('# NEMO 109 - ') if '# NEMO 109 - ' in src else src.rindex("if __name__")
    return src[i:j]


def make_mp3(path, seconds=1):
    if FFMPEG:
        subprocess.run([FFMPEG, '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=%d' % seconds, '-c:a', 'libmp3lame', '-b:a', '32k', path],
                       check=True, stdin=subprocess.DEVNULL)
    else:
        with open(path, 'wb') as f:
            f.write(b'ID3' + b'\0' * 2000)


class FakeStream(object):
    """A provider's streamed HTTP answer: lines of server-sent events."""

    def __init__(self, lines, status=200, on_line=None):
        self.lines, self.status_code, self.on_line, self.closed = list(lines), status, on_line, False
        self.content = b'{}'
        self.headers = {'Content-Type': 'text/event-stream; charset=utf-8'}

    def iter_lines(self, decode_unicode=False):
        for i, ln in enumerate(self.lines):
            if self.on_line:
                self.on_line(i)
            yield ln

    def close(self):
        self.closed = True


def anthropic_sse(chunks, stop='end_turn'):
    out = ['event: message_start', 'data: ' + json.dumps({'type': 'message_start', 'message': {'id': 'msg_1', 'usage': {'input_tokens': 120, 'output_tokens': 1}}}), '',
           'event: content_block_start', 'data: ' + json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}}), '',
           'event: ping', 'data: {"type": "ping"}', '']
    for c in chunks:
        out += ['event: content_block_delta', 'data: ' + json.dumps({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': c}}), '']
    out += ['event: content_block_stop', 'data: {"type":"content_block_stop","index":0}', '']
    if stop:
        out += ['event: message_delta', 'data: ' + json.dumps({'type': 'message_delta', 'delta': {'stop_reason': stop}, 'usage': {'output_tokens': 42}}), '']
    out += ['event: message_stop', 'data: {"type":"message_stop"}', '']
    return out


class VoiceCase(SteadyCase):
    def setUp(self):
        super().setUp()
        m = self.m
        m._N108_SYNC['on'] = True
        self.addCleanup(m._N108_SYNC.__setitem__, 'on', False)
        for name in ('_N108_VOICE_TURN', '_N108_INBOUND', '_N108_LAST_REPLY', '_N108_SAID', '_N108_STOPPED', '_N108_VOICE_MSG'):
            d = getattr(m, name)
            saved = dict(d)
            d.clear()
            self.addCleanup(lambda d=d, saved=saved: (d.clear(), d.update(saved)))
        saved_draft = dict(m._N108_DRAFT)
        m._N108_DRAFT.update(off_until=0.0, why='')
        self.addCleanup(m._N108_DRAFT.update, saved_draft)
        for k in m._N108_STATS:
            m._N108_STATS[k] = 0
        # Telegram
        self.tgc = []
        self.tg_fail = {}

        def fake_tg(method, **kw):
            self.tgc.append((method, kw))
            if method in self.tg_fail:
                return self.tg_fail[method]
            if method == 'sendMessage':
                return {'ok': True, 'result': {'message_id': 2000 + len(self.tgc)}}
            if method == 'getFile':
                return {'ok': True, 'result': {'file_path': 'voice/file_1.oga'}}
            return {'ok': True, 'result': True}
        self.swap('tg', fake_tg)
        self.posts = []
        self.post_reply = {}

        def fake_post(method, data, files, timeout=120):
            name, fobj, mime = list(files.values())[0]
            self.posts.append({'method': method, 'data': dict(data), 'name': name, 'mime': mime, 'size': len(fobj.read())})
            return self.post_reply.get((method, name), self.post_reply.get(method, {'ok': True, 'result': {'message_id': 9}}))
        self.put('_n108_post', fake_post)
        self.tts = []

        def fake_tts(text, lang, voice, rate, pitch, path, slow=False):
            self.tts.append({'text': text, 'lang': lang, 'voice': voice, 'rate': rate, 'pitch': pitch, 'slow': slow})
            make_mp3(path)
            return 'edge-tts'
        self.put('_n108_tts', fake_tts)
        # the sender: the real v108 wrapper in front of a recorder
        self.sent2 = []

        def base_send(cid, text, kb=None):
            self.sent2.append((cid, text, kb))
        self.put('send_text', m._n108_send_text)
        self.put('_N108_SEND_PREV', base_send)
        self.prev = mock.Mock(side_effect=self.older_layers)
        self.voice_prev = mock.Mock(return_value=None)
        self.put('_N108_HANDLE_VOICE_PREV', self.voice_prev)
        self.put('_n36_kv_get', lambda k, d=None: self.kv.get(k, d))         # the older settings store needs the main database, which tests do not start
        self.put('_n36_kv_set', lambda k, v: self.kv.__setitem__(k, v) or True)

    def older_layers(self, msg):
        """The older layers, faked as far as voice goes: as in the real chain, a voice note ends at the voice reader."""
        if msg.get('voice') or msg.get('audio'):
            return self.m.handle_voice(msg['chat']['id'], msg.get('voice') or msg.get('audio'))
        return None

    def msg(self, text='', **extra):
        d = super().msg(text, **extra)
        if not text:
            d.pop('text', None)
        return d

    def texts2(self):
        return [t for (_c, t, _k) in self.sent2]

    def voices(self):
        return [p for p in self.posts if p['method'] in ('sendVoice', 'sendAudio')]

    def calls(self, method):
        return [kw for (mth, kw) in self.tgc if mth == method]


# ===================================================================================================================
# 1. A voice note is a message for the whole of Nemo, and the answer comes back as a voice note
# ===================================================================================================================
class TestVoiceConversation(VoiceCase):
    def test_a_voice_note_reaches_todays_nemo_and_the_pine_engine_answers_with_a_file_and_a_voice_note(self):
        m = self.m
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.put('_n1071_out_dir', lambda: d.name)
        m._N1071_SYNC['on'] = True
        self.addCleanup(m._N1071_SYNC.__setitem__, 'on', False)
        docs = []
        self.swap('send_document', lambda cid, path, name, mime: docs.append(name) or True)
        self.put('_n108_transcribe', lambda v: 'create a pine script with your survival logic')
        m.handle(self.msg(voice={'file_id': 'F1', 'duration': 4, 'file_size': 9000}))
        self.assertEqual('🎤 create a pine script with your survival logic', self.texts2()[0])
        self.assertEqual(['nemo_survival_strategy.pine'], docs, 'the voice note reached the Pine engine, not the old v13 answer path')
        v = self.voices()
        self.assertEqual(1, len(v))
        self.assertEqual('sendVoice', v[0]['method'])
        self.assertEqual('audio/mpeg', v[0]['mime'])
        self.assertIn('Nemo Survival Strategy', self.tts[0]['text'])
        kb = json.loads(v[0]['data']['reply_markup'])
        self.assertEqual(['🐢 Slower', '⚡ Faster', '📝 Text'], [b['text'] for b in kb['inline_keyboard'][0]])
        self.assertEqual(1, m._N108_STATS['voice_in'])

    def test_the_transcript_goes_on_as_a_typed_message_with_the_voice_mark(self):
        m = self.m
        self.put('_N108_HANDLE_PREV', self.prev)
        self.put('_n108_transcribe', lambda v: 'what is on my calendar today')
        m.handle(self.msg(voice={'file_id': 'F1', 'duration': 3}, message_id=77))
        first, passed = [c[0][0] for c in self.prev.call_args_list]
        self.assertEqual('F1', first['voice']['file_id'], 'the older layers see the voice note itself first (Argus records it, Scout passes it on)')
        self.assertEqual('what is on my calendar today', passed['text'])
        self.assertTrue(passed['_n108_voice'])
        self.assertEqual(77, passed['message_id'])
        self.assertIn(self.cid, m._N108_VOICE_TURN)
        self.voice_prev.assert_not_called()
        self.assertEqual({}, m._N108_VOICE_MSG)

    def test_a_talk_session_audio_files_and_other_chats_keep_the_older_voice_readers(self):
        m = self.m
        self.put('_n108_transcribe', lambda v: self.fail('today\'s voice reader should not run'))
        self.put('_n37_talk_on', lambda cid: True)
        m.handle(self.msg(voice={'file_id': 'T1', 'duration': 3}))
        self.assertEqual('T1', self.voice_prev.call_args[0][1]['file_id'], 'a /talk session keeps its own reader (and its “bye”)')
        self.put('_n37_talk_on', lambda cid: False)
        m.handle(self.msg(audio={'file_id': 'A1', 'duration': 30}))
        self.assertEqual('A1', self.voice_prev.call_args[0][1]['file_id'])
        m.handle_voice(self.cid, {'file_id': 'NEVER-SEEN'})
        self.assertEqual('NEVER-SEEN', self.voice_prev.call_args[0][1]['file_id'], 'a voice note the front door did not see')
        self.assertEqual(3, self.voice_prev.call_count)
        self.assertEqual([], self.voices())

    def test_voice_notes_some_older_layer_kept_are_not_remembered_for_ever(self):
        m = self.m
        self.put('_N108_HANDLE_PREV', mock.Mock(return_value=True))
        for i in range(80):
            m.handle(self.msg(voice={'file_id': 'K%d' % i, 'duration': 3}))
        self.assertEqual(50, len(m._N108_VOICE_MSG))
        self.assertNotIn('K0', m._N108_VOICE_MSG)
        self.assertIn('K79', m._N108_VOICE_MSG)
        m._N108_VOICE_MSG.clear()

    def test_progress_messages_are_not_spoken_the_answer_is(self):
        m = self.m
        m._n108_mark_voice_turn(self.cid)
        m.send_text(self.cid, '🧭 Understanding your request...')
        m.send_text(self.cid, 'I am working on it. Reference: W71-1')
        self.assertEqual([], self.voices())
        m.send_text(self.cid, 'You have two meetings today: 11:00 with Mehta and 16:00 with the bank.')
        self.assertEqual(1, len(self.voices()))
        m.send_text(self.cid, 'And one more thing.')
        self.assertEqual(1, len(self.voices()), 'only the first answer after a voice note is spoken')

    def test_an_old_voice_turn_is_not_spoken(self):
        m = self.m
        m._n108_mark_voice_turn(self.cid)
        m._N108_VOICE_TURN[self.cid]['t'] -= 1000
        m.send_text(self.cid, 'A message much later.')
        self.assertEqual([], self.voices())

    def test_voice_replies_off_still_understands_voice_notes(self):
        m = self.m
        self.kv['n108_voice'] = 'off'
        self.put('_N108_HANDLE_PREV', self.prev)
        self.put('_n108_transcribe', lambda v: 'hello')
        m.handle(self.msg(voice={'file_id': 'F1', 'duration': 3}))
        self.assertEqual('hello', self.prev.call_args[0][0]['text'])
        m.send_text(self.cid, 'Hello! How can I help?')
        self.assertEqual([], self.voices())

    def test_always_reply_in_voice_while_talking(self):
        m = self.m
        self.put('_N108_HANDLE_PREV', self.prev)
        m.handle(self.msg('always reply in voice'))
        self.assertEqual('always', self.kv['n108_voice'])
        n = len(self.voices())                                   # the confirmation itself is already spoken
        m.send_text(self.cid, 'Sure, here is the answer.')
        self.assertEqual(n + 1, len(self.voices()))
        m._N108_INBOUND[self.cid] -= 3600
        m.send_text(self.cid, 'An alert an hour later.')
        self.assertEqual(n + 1, len(self.voices()), 'not when the owner is not talking to me')

    def test_voice_only_drops_the_text_unless_it_needs_reading(self):
        m = self.m
        self.kv['n108_voice_text'] = 'voice'
        m._n108_mark_voice_turn(self.cid)
        m.send_text(self.cid, 'It will rain this evening, so take an umbrella.')
        self.assertEqual(1, len(self.voices()))
        self.assertNotIn('It will rain this evening, so take an umbrella.', self.texts2())
        m._n108_mark_voice_turn(self.cid)
        m.send_text(self.cid, 'The report is at https://example.com/r/1')
        self.assertIn('The report is at https://example.com/r/1', self.texts2(), 'a link is kept as text')
        self.assertEqual(2, len(self.voices()))

    def test_a_voice_note_that_is_too_long_or_unclear(self):
        m = self.m
        m.handle(self.msg(voice={'file_id': 'F1', 'duration': 5000, 'file_size': 1000}))
        self.assertIn('longer than I can take', self.texts2()[-1])
        self.put('_n108_transcribe', lambda v: None)
        self.put('GROQ_KEY', 'gsk_test')
        m.handle(self.msg(voice={'file_id': 'F2', 'duration': 3}))
        self.assertIn('I could not make that out', self.texts2()[-1])

    def test_a_voice_note_with_a_caption_is_left_to_the_older_readers(self):
        m = self.m
        self.put('_N108_HANDLE_PREV', self.prev)
        m.handle(self.msg(voice={'file_id': 'F1', 'duration': 3}, caption='transcribe'))
        self.prev.assert_called_once()
        self.voice_prev.assert_called_once()
        self.assertEqual([], self.texts2(), 'no “🎤 …” transcript from this layer')

    def test_family_voice_notes_get_voice_back(self):
        m = self.m
        fam = 555

        def prev(ctx, role, msg):
            m.send_text(ctx['cid'], '🎤 namaste')
            m.send_text(ctx['cid'], 'Namaste Riya! Kaise ho?')
            return True
        self.put('_N108_N89_VOICE_PREV', prev)
        m._n89_voice({'cid': fam, 'uid': fam, 'name': 'Riya'}, 'family', {})
        v = self.voices()
        self.assertEqual(1, len(v))
        self.assertEqual(fam, v[0]['data']['chat_id'])
        self.kv['n108_family_voice'] = 'off'
        m._n89_voice({'cid': fam, 'uid': fam, 'name': 'Riya'}, 'family', {})
        self.assertEqual(1, len(self.voices()))

    def test_the_old_talk_session_uses_todays_nemo_and_cannot_loop(self):
        m = self.m
        self.put('_N108_HANDLE_PREV', self.prev)
        self.put('_n37_talk_touch', lambda cid: None)
        self.put('_n37_talk_on', lambda cid: True)                     # a /talk session is open
        started = []
        fake_threading = mock.Mock()
        fake_threading.Thread.side_effect = lambda **kw: started.append(kw) or mock.Mock()
        self.put('_n37_threading', fake_threading)
        m._n37_talk_turn(self.cid, 'remind me at 5 to call Mehta', 'text')
        passed = self.prev.call_args[0][0]
        self.assertTrue(passed['_n108_voice'] and passed['_n37_talk'])
        self.assertFalse(m._n37_dispatch(passed), 'v37 does not catch the same turn again')
        self.assertEqual([], started, 'no second talk turn was started (no loop)')
        self.assertTrue(m._n37_dispatch(self.msg('a new thing I say in the session')), 'a new message in the session still reaches the session')
        self.assertIn(self.cid, m._N108_VOICE_TURN)


class TestVoiceSound(VoiceCase):
    def test_language_voice_and_gender(self):
        m = self.m
        self.assertEqual('gu', m._n108_lang('તમે કેમ છો?'))
        self.assertEqual('hi', m._n108_lang('आप कैसे हैं?'))
        self.assertEqual('en', m._n108_lang('Aap kaise ho?'))
        self.kv['n108_voice_gender'] = 'male'
        self.assertEqual('gu-IN-NiranjanNeural', m._n108_voice_name('gu'))
        self.assertEqual('hi-IN-MadhurNeural', m._n108_voice_name('hi'))
        self.kv['n108_voice_gender'] = 'female'
        self.assertEqual('gu-IN-DhwaniNeural', m._n108_voice_name('gu'))
        m._n108_speak(self.cid, 'તમારો ઓર્ડર તૈયાર છે.')
        self.assertEqual(('gu', 'gu-IN-DhwaniNeural'), (self.tts[-1]['lang'], self.tts[-1]['voice']))

    def test_what_is_spoken(self):
        m = self.m
        s, cut = m._n108_speech_text('**Done!** 🎉 See https://x.example/a\n• one\n• two\n```py\nprint(1)\n```', 500)
        for bad in ('**', '🎉', 'https', '```', 'print(1)'):
            self.assertNotIn(bad, s)
        self.assertIn('the link', s)
        self.assertFalse(cut)
        long = ' '.join('Sentence number %d is here.' % i for i in range(100))
        s, cut = m._n108_speech_text(long, 300)
        self.assertTrue(cut)
        self.assertTrue(s.endswith('.'))
        self.assertLessEqual(len(s), 300)

    def test_expressive_delivery_and_speed(self):
        m = self.m
        self.assertEqual(('+8%', '+3Hz', 'excited'), m._n108_prosody('Congratulations on the order!'))
        self.assertEqual(('-8%', '-2Hz', 'calm'), m._n108_prosody('So sorry to hear she is not well.'))
        self.assertEqual(('-5%', '-3Hz', 'serious'), m._n108_prosody('Warning: the stop is close.'))
        self.assertEqual(('-12%', '+0Hz', 'neutral'), m._n108_prosody('The meeting is at 4.', 'slow'))
        self.assertEqual(('+0%', '+0Hz', 'neutral'), m._n108_prosody('Congratulations!', 'normal', expressive=False))

    @unittest.skipUnless(FFMPEG, 'ffmpeg is not installed')
    def test_when_telegram_refuses_the_mp3_it_gets_ogg_opus_then_the_old_audio_file(self):
        m = self.m
        self.post_reply[('sendVoice', 'nemo.mp3')] = {'ok': False, 'description': 'Bad Request: wrong file type'}
        self.assertEqual('voice-ogg', m._n108_speak(self.cid, 'Hello there.'))
        self.assertEqual(['nemo.mp3', 'nemo.ogg'], [p['name'] for p in self.posts])
        self.assertEqual('audio/ogg', self.posts[1]['mime'])
        self.posts.clear()
        self.post_reply['sendVoice'] = {'ok': False}
        self.assertEqual('audio', m._n108_speak(self.cid, 'Hello again.'))
        self.assertEqual('sendAudio', self.posts[-1]['method'])

    def test_no_voice_engine_means_no_voice_and_no_crash(self):
        m = self.m
        self.put('_n108_tts', lambda *a, **k: '')
        m._n108_mark_voice_turn(self.cid)
        m.send_text(self.cid, 'Here you go.')
        self.assertEqual([], self.voices())
        self.assertIn('Here you go.', self.texts2())
        self.assertEqual(1, m._N108_STATS['voice_fail'])

    def test_the_buttons_under_a_voice_note(self):
        m = self.m
        m._n108_speak(self.cid, 'The answer is forty two.')
        vid = json.loads(self.voices()[0]['data']['reply_markup'])['inline_keyboard'][0][2]['callback_data'].split(':')[2]
        m.handle_callback({'id': 'q', 'data': 'vc108:text:' + vid, 'from': {'id': self.cid}, 'message': {'chat': {'id': self.cid}}})
        self.assertIn('The answer is forty two.', self.texts2())
        m.handle_callback({'id': 'q', 'data': 'vc108:slow:' + vid, 'from': {'id': self.cid}, 'message': {'chat': {'id': self.cid}}})
        self.assertTrue(self.tts[-1]['slow'])
        self.assertEqual('-12%', self.tts[-1]['rate'])
        n = len(self.voices())
        m.handle_callback({'id': 'q', 'data': 'vc108:fast:' + vid, 'from': {'id': 999}, 'message': {'chat': {'id': self.cid}}})
        self.assertEqual(n, len(self.voices()), 'someone else cannot use the owner\'s buttons')

    def test_voice_settings_in_words(self):
        m = self.m
        self.put('_N108_HANDLE_PREV', self.prev)
        for words, key, value in (('speak slower', 'voice_speed', 'slow'), ('use a male voice', 'voice_gender', 'male'), ('voice only', 'voice_text', 'voice'),
                                  ('voice and text', 'voice_text', 'both'), ('expressive voice off', 'expressive', 'off'), ('voice replies off', 'voice', 'off'),
                                  ('voice replies on', 'voice', 'mirror'), ('streaming off', 'stream', 'off'), ('reactions off', 'react', 'off')):
            m.handle(self.msg(words))
            self.assertEqual(value, self.kv['n108_' + key], words)
        self.prev.assert_not_called()
        m.handle(self.msg('voice status'))
        self.assertIn('Voice replies:', self.texts2()[-1])

    def test_read_that_out_and_video_note_use_the_last_answer(self):
        m = self.m
        m.send_text(self.cid, 'Gold closed at 74,210 today.')
        m.handle(self.msg('read that out slower'))
        self.assertEqual('slow', 'slow' if self.tts[-1]['slow'] else 'normal')
        self.assertIn('Gold closed', self.tts[-1]['text'])

    @unittest.skipUnless(FFMPEG, 'ffmpeg is not installed')
    def test_a_round_video_note_is_made_with_ffmpeg(self):
        m = self.m
        m.send_text(self.cid, 'Happy birthday, Riya!')
        m.handle(self.msg('send that as a video note'))
        vn = [p for p in self.posts if p['method'] == 'sendVideoNote']
        self.assertEqual(1, len(vn))
        self.assertEqual('video/mp4', vn[0]['mime'])
        self.assertGreater(vn[0]['size'], 1000)

    def test_video_note_without_ffmpeg_says_so(self):
        m = self.m
        m.send_text(self.cid, 'Hello.')
        with mock.patch.object(m._n108_shutil, 'which', return_value=None):
            m.handle(self.msg('send that as a video note'))
        self.assertIn('needs ffmpeg', self.texts2()[-1])


# ===================================================================================================================
# 2. Live drafts while the answer is written
# ===================================================================================================================
PERSONA = [{'role': 'system', 'content': 'You are Nemo, the owner\'s assistant.'}, {'role': 'user', 'content': 'hi'}]


class TestStreaming(VoiceCase):
    def setUp(self):
        super().setUp()
        self.req_prev = mock.Mock(return_value={'text': 'from the unchanged gateway', 'provider': 'x', 'model': 'y', 'usage': {}})
        self.put('_N108_REQ_PREV', self.req_prev)
        self.put('_n73_request', self.m._n108_request)                       # the shared fixture puts a fake AI here; the voice layer's entry goes back in front of it
        self.put('_n102_has_nodes', lambda: False)
        self.streams = []
        self.next_stream = None

        def fake_post(url, headers=None, json=None, timeout=None, allow_redirects=True, stream=False):
            self.streams.append({'url': url, 'headers': headers, 'json': json, 'stream': stream})
            return self.next_stream
        self.put('post', fake_post, obj=self.m.requests)
        self.m._N73_COOLDOWN.clear()
        self.addCleanup(self.m._N73_COOLDOWN.clear)

    def turn(self, inner, text='hi', chat_type='private'):
        self.put('_N108_TURN_PREV', inner)
        msg = self.msg(text)
        msg['chat']['type'] = chat_type
        return self.m._n86_turn(self.cid, msg, text, None)

    def answer_inner(self, messages=PERSONA, role='chat'):
        def inner(cid, msg, text, budget):
            r = self.m._n73_request(cid, role, messages, timeout=60)
            return {'ok': True, 'text': r['text']}
        return inner

    def test_the_answer_streams_into_a_live_draft(self):
        m = self.m
        self.next_stream = FakeStream(anthropic_sse(['The capital ', 'of India is New Delhi, ', 'a city of more than thirty million people. ', 'It became the capital in 1931.']))
        self.put('_N108_LIMITS', dict(m._N108_LIMITS, draft_every_s=0.0, draft_min_chars=1))
        out = self.turn(self.answer_inner())
        self.assertEqual('The capital of India is New Delhi, a city of more than thirty million people. It became the capital in 1931.', out['text'])
        self.req_prev.assert_not_called()
        self.assertTrue(self.streams[0]['stream'])
        self.assertTrue(self.streams[0]['json']['stream'])
        self.assertEqual('text/event-stream', self.streams[0]['headers']['Accept'])
        drafts = self.calls('sendMessageDraft')
        self.assertEqual('', drafts[0]['text'], 'the first draft is Telegram\'s “Thinking…”')
        self.assertTrue(all(d['can_stop'] for d in drafts))
        self.assertEqual(1, len({d['draft_id'] for d in drafts}), 'one draft, animated as it grows')
        self.assertTrue(drafts[-1]['text'].startswith('The capital of India'))
        self.assertEqual(1, m._N108_STATS['streams'])

    def test_openrouter_streams_too(self):
        m = self.m
        cfg = {'enabled': True, 'routes': dict(m._N73_MODELS, chat=[('openrouter', 'openai/gpt-6.1-sol')]), 'max_attempts': 2}
        self.put('_n73_config', lambda: cfg)
        self.put('_n74_check_catalog', lambda *a: None)
        self.put('_n74_valid_model', lambda p, mdl: True)
        lines = [': OPENROUTER PROCESSING', 'data: ' + json.dumps({'model': 'openai/gpt-6.1-sol', 'choices': [{'delta': {'content': 'Hello '}, 'finish_reason': None}]}),
                 'data: ' + json.dumps({'choices': [{'delta': {'content': 'there.'}, 'finish_reason': 'stop'}]}),
                 'data: ' + json.dumps({'choices': [], 'usage': {'prompt_tokens': 10, 'completion_tokens': 3, 'cost': 0.0001}}), 'data: [DONE]']
        self.next_stream = FakeStream(lines)
        out = self.turn(self.answer_inner())
        self.assertEqual('Hello there.', out['text'])
        self.assertEqual('Bearer test-key', self.streams[0]['headers']['Authorization'])
        self.req_prev.assert_not_called()

    def test_helper_calls_and_later_calls_never_stream(self):
        m = self.m
        seen = []

        def inner(cid, msg, text, budget):
            seen.append(m._n73_request(cid, 'chat', [{'role': 'system', 'content': m._N83_HELPER_SYSTEM}, {'role': 'user', 'content': 'x'}], timeout=30)['text'])
            seen.append(m._n73_request(cid, 'chat', PERSONA, timeout=30, _route_override=[('openrouter', 'x')])['text'])
            seen.append(m._n73_request(cid, 'chat', PERSONA, timeout=30)['text'])          # the answer: streams
            seen.append(m._n73_request(cid, 'chat', PERSONA, timeout=30)['text'])          # a repair after the check: does not
            return {'ok': True, 'text': seen[2]}
        self.next_stream = FakeStream(anthropic_sse(['Streamed answer.']))
        self.turn(inner)
        self.assertEqual(['from the unchanged gateway', 'from the unchanged gateway', 'Streamed answer.', 'from the unchanged gateway'], seen)
        self.assertEqual(1, len(self.streams))

    def test_a_refusal_in_the_stream_is_a_refusal(self):
        m = self.m
        self.next_stream = FakeStream(anthropic_sse(['I can'], stop='refusal'))
        with self.assertRaises(m._N73Error) as ctx:
            self.turn(self.answer_inner())
        self.assertEqual('provider_refusal', ctx.exception.code)
        self.assertTrue(ctx.exception.terminal)
        self.req_prev.assert_not_called()

    def test_an_unfinished_stream_falls_back_to_the_unchanged_gateway(self):
        m = self.m
        self.next_stream = FakeStream(anthropic_sse(['Half an ans'], stop=None))
        out = self.turn(self.answer_inner())
        self.assertEqual('from the unchanged gateway', out['text'])
        self.assertIn(('anthropic', 'claude-sonnet-5-5'), m._N73_COOLDOWN)
        self.assertEqual(1, m._N108_STATS['stream_fallbacks'])

    def test_a_whole_answer_instead_of_a_stream_is_read_as_the_gateway_reads_it(self):
        m = self.m
        body = {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': 'A whole answer.'}], 'usage': {'input_tokens': 10, 'output_tokens': 4}}
        resp = FakeStream([])
        resp.headers = {'content-type': 'application/json'}
        resp.content = json.dumps(body).encode()
        resp.json = lambda: body
        self.next_stream = resp
        out = self.turn(self.answer_inner())
        self.assertEqual('A whole answer.', out['text'])
        self.req_prev.assert_not_called()
        self.assertEqual({}, dict(m._N73_COOLDOWN))

    def test_a_broken_stream_lets_the_gateway_try_the_same_model_again(self):
        m = self.m

        def broken(*a, **kw):
            raise ConnectionError('reset by peer')
        self.put('post', broken, obj=m.requests)
        out = self.turn(self.answer_inner())
        self.assertEqual('from the unchanged gateway', out['text'])
        self.assertEqual({}, dict(m._N73_COOLDOWN), 'a broken stream is not a broken model: no cooldown')
        self.assertEqual(1, m._N108_STATS['stream_fallbacks'])
        self.put('post', lambda *a, **kw: self.next_stream, obj=m.requests)
        self.next_stream = FakeStream(['data: {not json'])                 # garbled events
        self.assertEqual('from the unchanged gateway', self.turn(self.answer_inner())['text'])
        self.assertEqual({}, dict(m._N73_COOLDOWN))

    def test_an_answer_the_gateway_would_reject_is_rejected_when_streamed_too(self):
        m = self.m
        seen = []
        self.put('_n73_validate_output', lambda role, text: seen.append(text) or (_ for _ in ()).throw(m._N73Error('invalid_output')))
        self.next_stream = FakeStream(anthropic_sse(['A streamed answer.']))
        self.assertEqual('from the unchanged gateway', self.turn(self.answer_inner())['text'])
        self.assertEqual(['A streamed answer.'], seen)
        self.assertIn(('anthropic', 'claude-sonnet-5-5'), m._N73_COOLDOWN, 'the model\'s own answer failed: cooled as the gateway would')

    def test_an_http_error_falls_back_and_cools_the_model(self):
        m = self.m
        self.next_stream = FakeStream([], status=529)
        out = self.turn(self.answer_inner())
        self.assertEqual('from the unchanged gateway', out['text'])
        self.assertIn(('anthropic', 'claude-sonnet-5-5'), m._N73_COOLDOWN)

    def test_the_stop_button_stops_the_answer(self):
        m = self.m
        holder = {}

        def on_line(i):
            if i == 12:            # the owner presses stop while the answer is being written
                m._n108_on_stop_update({'chat': {'id': self.cid}, 'draft_id': holder['id']})

        def inner(cid, msg, text, budget):
            holder['id'] = m._N108_TLS.arm['draft_id']
            try:
                m._n73_request(cid, 'chat', PERSONA, timeout=60)
            except m._N73Error as exc:
                if exc.code == 'cancelled':
                    return {'ok': False, 'text': 'Stopped before answering. Nothing was changed.', 'error': 'cancelled'}
                raise
            return {'ok': True, 'text': 'not stopped'}
        self.next_stream = FakeStream(anthropic_sse(['one ', 'two ', 'three ', 'four ', 'five ']), on_line=on_line)
        out = self.turn(inner)
        self.assertEqual('⏹ Stopped. Tell me what you meant, or ask again.', out['text'])
        self.assertTrue(self.next_stream.closed)
        self.assertEqual(1, m._N108_STATS['stream_stops'])

    def test_a_stop_from_someone_else_is_ignored(self):
        m = self.m
        m._n108_on_stop_update({'chat': {'id': 999}, 'draft_id': 5})
        self.assertNotIn(5, m._N108_STOPPED)

    def test_telegram_refusing_drafts_pauses_them_and_the_answer_still_arrives(self):
        m = self.m
        self.tg_fail['sendMessageDraft'] = {'ok': False, 'description': 'Not Found: method not found'}
        self.next_stream = FakeStream(anthropic_sse(['Still answered.']))
        out = self.turn(self.answer_inner())
        self.assertEqual('Still answered.', out['text'])
        self.assertGreater(m._N108_DRAFT['off_until'], time.time() + 3000)
        self.assertIn('method not found', m._N108_DRAFT['why'])
        self.assertEqual(1, len(self.calls('sendMessageDraft')), 'no more drafts for an hour')
        self.assertIn('paused for an hour', m._n108_status_text(self.cid))

    def test_streaming_off_groups_and_local_brain_first_do_not_stream(self):
        m = self.m
        self.kv['n108_stream'] = 'off'
        self.assertEqual('from the unchanged gateway', self.turn(self.answer_inner())['text'])
        self.kv['n108_stream'] = 'on'
        self.assertEqual('from the unchanged gateway', self.turn(self.answer_inner(), chat_type='group')['text'])
        self.put('_n102_has_nodes', lambda: True)
        self.put('_n102_mode', lambda: 'offline')
        self.assertEqual('from the unchanged gateway', self.turn(self.answer_inner())['text'])
        self.assertEqual([], self.streams)

    def test_the_update_loop_hands_the_stop_button_to_the_voice_layer(self):
        src = read(base.NEMO_FILE)
        self.assertIn('elif u.get("stopped_message_generation"):\n                    threading.Thread(target=_n108_on_stop_update, args=(u["stopped_message_generation"],), daemon=True).start()', src)


# ===================================================================================================================
# 3. Notification manners
# ===================================================================================================================
def window_around_now(m, inside=True):
    d = m._n108_ist()
    now = d.hour * 60 + d.minute
    a, b = ((now - 30) % 1440, (now + 30) % 1440) if inside else ((now + 60) % 1440, (now + 120) % 1440)
    return '%02d:%02d-%02d:%02d' % (a // 60, a % 60, b // 60, b % 60)


class TestManners(VoiceCase):
    def test_off_by_default_nothing_is_held(self):
        m = self.m
        m.send_text(self.cid, 'Your weekly summary is ready.')
        self.assertIn('Your weekly summary is ready.', self.texts2())

    def test_quiet_hours_in_words(self):
        m = self.m
        self.assertEqual('23:00-07:00', m._n108_parse_quiet('quiet hours 11 to 7'))
        self.assertEqual('22:30-06:45', m._n108_parse_quiet('quiet hours from 22:30 to 6:45'))
        self.assertEqual('23:00-06:00', m._n108_parse_quiet('do not disturb 11 pm to 6 am'))
        self.assertIsNone(m._n108_parse_quiet('quiet hours 7 to 7'))
        m.handle(self.msg('quiet hours 11 to 7'))
        self.assertEqual('23:00-07:00', self.kv['n108_quiet'])
        self.assertEqual('23:00-07:00', m._n36_kv_get('n38_quiet', ''))
        self.assertIn('Quiet hours 23:00 to 07:00 IST', self.texts2()[-1])

    def test_quiet_hours_hold_what_nemo_sends_on_its_own_but_never_replies_or_urgent_things(self):
        m = self.m
        self.kv['n108_quiet'] = window_around_now(m)
        m.send_text(self.cid, 'Here is a thought about your garden.')
        m.send_text(self.cid, '🤖 AUTO-TRADE EXIT (stop) NSE:NIFTY... P&L Rs.-650')
        m.send_text(self.cid, '⏰ Reminder: call Mehta')
        self.assertEqual(['🤖 AUTO-TRADE EXIT (stop) NSE:NIFTY... P&L Rs.-650', '⏰ Reminder: call Mehta'], self.texts2())
        self.assertEqual(1, len(m._n108_held_rows(self.cid)))
        m._N108_INBOUND[self.cid] = time.time()                   # the owner writes: everything now is a reply
        m.send_text(self.cid, 'A reply to you.')
        self.assertIn('A reply to you.', self.texts2())
        m.send_text(555, 'A family member\'s reply.')
        self.assertIn('A family member\'s reply.', self.texts2())

    def test_held_messages_come_back_as_one_summary_and_cards_keep_their_buttons(self):
        m = self.m
        self.kv['n108_quiet'] = window_around_now(m)
        m.send_text(self.cid, 'First quiet thing.\nwith a second line')
        card = {'inline_keyboard': [[{'text': 'Approve', 'callback_data': 'x:1'}]]}
        m.send_text(self.cid, 'A card to decide on', card)
        self.assertEqual([], self.texts2())
        self.kv['n108_quiet'] = window_around_now(m, inside=False)
        m._n108_tick()
        out = self.sent2
        self.assertTrue(out[0][1].startswith('🌅 While you were away: 2 messages.'))
        self.assertIn('First quiet thing.', out[0][1])
        self.assertNotIn('with a second line', out[0][1])
        self.assertEqual(('A card to decide on', card), (out[1][1], out[1][2]))
        self.assertEqual([], m._n108_held_rows(self.cid))
        m._n108_tick()
        self.assertEqual(2, len(self.sent2), 'given back once')

    def test_snooze_and_unsnooze(self):
        m = self.m
        self.assertEqual(7200, m._n108_parse_snooze('snooze nemo 2 hours'))
        self.assertEqual(1800, m._n108_parse_snooze('mute nemo for half an hour'))
        self.assertEqual(3600, m._n108_parse_snooze('snooze for an hour'))
        self.assertIsNone(m._n108_parse_snooze('snooze nemo 3 days'))
        m.handle(self.msg('snooze nemo 2 hours'))
        self.assertAlmostEqual(time.time() + 7200, float(self.kv['n108_snooze_until']), delta=5)
        m._N108_INBOUND[self.cid] -= 3600
        m.send_text(self.cid, 'Your topic watch found a story.')
        self.assertNotIn('Your topic watch found a story.', self.texts2())
        m.handle(self.msg('unsnooze'))
        self.assertTrue(any(t.startswith('🔔 Held while snoozed: 1 message.') for t in self.texts2()))

    def test_one_daily_digest_for_routine_updates(self):
        m = self.m
        m.handle(self.msg('daily digest at 8 am'))
        self.assertEqual('08:00', self.kv['n108_digest'])
        m._N108_INBOUND[self.cid] -= 3600
        m.send_text(self.cid, '📰 Topic watch: 3 new stories on solar subsidy')
        m.send_text(self.cid, 'Your invoice INV-12 was paid.')
        self.assertEqual(['Your invoice INV-12 was paid.'], [t for t in self.texts2() if 'INV-12' in t or 'Topic watch' in t])
        at = m._n108_dt.datetime.now(m._N108_IST).replace(hour=8, minute=5, second=0, microsecond=0).timestamp()
        m._n108_tick(at)
        self.assertTrue(any(t.startswith('🗞 Your daily digest: 1 message.') for t in self.texts2()))
        m.send_text(self.cid, '📰 Topic watch: 1 new story on gold')            # a routine update after today's digest waits for tomorrow's
        n = len(self.sent2)
        m._n108_tick(at + 600)
        self.assertEqual(n, len(self.sent2), 'one digest a day')
        m._n108_tick(at + 86400)
        self.assertTrue(self.texts2()[-1].startswith('🗞 Your daily digest: 1 message.'))

    def test_what_did_i_miss_shows_them_in_full(self):
        m = self.m
        self.kv['n108_quiet'] = window_around_now(m)
        m.send_text(self.cid, 'Something long\nwith all of its lines')
        m._N108_INBOUND[self.cid] = time.time()
        m.handle(self.msg('what did i miss'))
        self.assertTrue(any('with all of its lines' in t for t in self.texts2()))
        self.assertEqual([], m._n108_held_rows(self.cid))

    def test_what_counts_as_urgent(self):
        m = self.m
        for t in ('🚨 Unauthorized login attempt blocked', 'Payment of Rs 5,000 debited', 'Reminder: pay the electricity bill', 'Backup failed: disk full', 'Update v108 installed, restarting',
                  '📅 Meeting in 10 minutes', 'Your OTP is 1234', 'Stop-loss hit on NIFTY'):
            self.assertEqual('urgent', m._n108_tier(t), t)
        for t in ('📰 Morning digest', '💡 Tip of the day: try voice notes', 'Weekly report for the showroom'):
            self.assertEqual('low', m._n108_tier(t), t)
        self.assertEqual('normal', m._n108_tier('The plumber replied to your email'))

    def test_a_fault_in_manners_never_stops_a_message(self):
        m = self.m
        self.put('_n108_manners_gate', mock.Mock(side_effect=RuntimeError('boom')))
        m.send_text(self.cid, 'Still delivered.')
        self.assertIn('Still delivered.', self.texts2())


# ===================================================================================================================
# 4. Tone dials and reactions
# ===================================================================================================================
class TestTone(VoiceCase):
    def test_dials_in_words(self):
        m = self.m
        self.assertEqual(('me', {'length': 'short'}), m._n108_parse_tone('be shorter'))
        self.assertEqual(('me', {'length': 'short'}), m._n108_parse_tone('from now on keep your replies short'))
        self.assertEqual(('customers', {'formality': 'formal'}), m._n108_parse_tone('be more formal with customers'))
        self.assertEqual(('person:riya', {'formality': 'casual'}), m._n108_parse_tone('be casual with Riya'))
        self.assertEqual(('me', {'emoji': 'off'}), m._n108_parse_tone('no emojis'))
        for one_off in ('keep it short', 'formal', 'short', 'shorter', 'make it formal', 'be careful'):
            self.assertIsNone(m._n108_parse_tone(one_off), one_off)

    def test_the_owners_dial_and_the_customers_dial_reach_the_answer_model(self):
        m = self.m
        self.put('_N108_HANDLE_PREV', self.prev)
        m.handle(self.msg('be shorter'))
        m.handle(self.msg('be more formal with customers'))
        self.prev.assert_not_called()
        self.assertEqual('brief', m._n36_kv_get('n80_detail_' + str(self.cid), ''))
        self.put('_N108_SYSTEM_PREV', lambda cid, style, mem: 'BASE')
        with mock.patch.object(m._N103_CTX, 'text', 'draft a reply to the customer asking about the delivery date', create=True):
            sysmsg = m._n83_system(self.cid, {'language': 'auto', 'detail': 'brief'}, '')
        self.assertIn('Tone the owner asked for in replies to them: short', sysmsg)
        self.assertIn("Anything you write for the owner's customers should be formal and polite", sysmsg)
        for text in ('what is the weather', 'how many customers came to the showroom today?'):
            with mock.patch.object(m._N103_CTX, 'text', text, create=True):
                sysmsg = m._n83_system(self.cid, {'language': 'auto', 'detail': 'brief'}, '')
            self.assertNotIn('customers should be', sysmsg, text)
            self.assertIn('Tone the owner asked for in replies to them: short', sysmsg)

    def test_a_persons_dial_reaches_the_family_chat(self):
        m = self.m
        m.handle(self.msg('be casual with Riya'))
        g = m._n89_chat_ground('Riya Shah', 'family', 'Gautam', 'chat')
        self.assertIn('casual and relaxed', g)
        self.assertNotIn('casual and relaxed', m._n89_chat_ground('Mehul', 'guest', 'Gautam', 'chat'))

    def test_show_and_reset(self):
        m = self.m
        m.handle(self.msg('be more formal with customers'))
        m.handle(self.msg('tone settings'))
        self.assertIn('For your customers: formal and polite', self.texts2()[-1])
        m.handle(self.msg('reset tone'))
        self.assertEqual({}, m._n108_tone('customers'))


class TestReactions(VoiceCase):
    def setUp(self):
        super().setUp()
        self.put('_N108_HANDLE_PREV', self.prev)
        self.put('_n49_pending_confirmation', lambda cid: False)

    def reactions(self):
        return [(kw['message_id'], kw['reaction'][0]['emoji']) for kw in self.calls('setMessageReaction')]

    def test_thanks_gets_a_heart_and_no_message(self):
        self.m.handle(self.msg('Thanks!', message_id=41))
        self.assertEqual([(41, '❤')], self.reactions())
        self.prev.assert_not_called()
        self.assertEqual([], self.texts2())
        self.m.handle(self.msg('shukriya', message_id=42))
        self.assertEqual((42, '🙏'), self.reactions()[-1])

    def test_ok_gets_a_thumbs_up_unless_it_may_be_an_answer(self):
        m = self.m
        m.handle(self.msg('ok', message_id=50))
        self.assertEqual([(50, '👍')], self.reactions())
        self.prev.assert_not_called()
        m.send_text(self.cid, 'Shall I send the invoice to Mehta?')
        m.handle(self.msg('ok', message_id=51))
        self.prev.assert_called_once()
        self.assertEqual(1, len(self.reactions()))

    def test_a_pending_confirmation_gets_its_ok(self):
        self.put('_n49_pending_confirmation', lambda cid: True)
        self.m.handle(self.msg('ok', message_id=60))
        self.prev.assert_called_once()
        self.assertEqual([], self.reactions())

    def test_good_and_sad_news_get_a_reaction_and_an_answer(self):
        m = self.m
        m.handle(self.msg('I got the order from Tata today!', message_id=70))
        m.handle(self.msg('My uncle passed away this morning', message_id=71))
        self.assertEqual([(70, '🎉'), (71, '🙏')], self.reactions())
        self.assertEqual(2, self.prev.call_count)

    def test_reactions_off_and_a_refused_reaction_mean_a_normal_reply(self):
        m = self.m
        self.kv['n108_react'] = 'off'
        m.handle(self.msg('thanks', message_id=80))
        self.prev.assert_called_once()
        self.kv['n108_react'] = 'on'
        self.tg_fail['setMessageReaction'] = {'ok': False, 'description': 'REACTION_INVALID'}
        m.handle(self.msg('thanks', message_id=81))
        self.assertEqual(2, self.prev.call_count)

    def test_a_spoken_thanks_is_answered_normally(self):
        self.m.handle(self.msg('thanks', message_id=90, _n108_voice=True))
        self.prev.assert_called_once()


# ===================================================================================================================
# 5. Polls, quizzes
# ===================================================================================================================
class TestPolls(VoiceCase):
    def setUp(self):
        super().setUp()
        self.put('_N108_HANDLE_PREV', self.prev)

    def test_poll_in_words(self):
        m = self.m
        p = m._n108_parse_poll('poll: Where for dinner? Pizza, Thali, Chinese')
        self.assertEqual(('Where for dinner?', ['Pizza', 'Thali', 'Chinese'], False), (p['question'], p['options'], p['multi']))
        p = m._n108_parse_poll('make a poll asking tea or coffee: tea / coffee')
        self.assertEqual(['tea', 'coffee'], p['options'])
        self.assertTrue(m._n108_parse_poll('multiple choice poll: Which days? Mon, Tue, Wed')['multi'])
        self.assertIn('error', m._n108_parse_poll('poll: Only one? Yes'))
        self.assertIn('error', m._n108_parse_poll('poll: Too many? ' + ', '.join('o%d' % i for i in range(13))))
        self.assertIsNone(m._n108_parse_poll('what is a poll tax'))

    def test_a_poll_is_sent_as_a_native_poll(self):
        m = self.m
        m.handle(self.msg('poll: Where for dinner? Pizza, Thali, Chinese'))
        sp = self.calls('sendPoll')[0]
        self.assertEqual('Where for dinner?', sp['question'])
        self.assertEqual([{'text': 'Pizza'}, {'text': 'Thali'}, {'text': 'Chinese'}], sp['options'])
        self.prev.assert_not_called()

    def test_the_owner_can_start_a_poll_in_a_family_group_and_others_cannot(self):
        m = self.m
        g = {'chat': {'id': -100, 'type': 'group'}, 'from': {'id': self.cid}, 'text': 'poll: Picnic on Sunday? Yes, No', 'message_id': 3}
        m.handle(g)
        sp = self.calls('sendPoll')[-1]
        self.assertEqual((-100, False), (sp['chat_id'], sp['is_anonymous']))
        m.handle({'chat': {'id': -100, 'type': 'group'}, 'from': {'id': 777}, 'text': 'poll: Mine? A, B', 'message_id': 4})
        self.assertEqual(1, len(self.calls('sendPoll')))
        self.prev.assert_called_once()

    def test_quiz_poll_from_the_study_cards(self):
        m = self.m
        for front, back in (('Capital of Gujarat?', 'Gandhinagar'), ('Capital of Rajasthan?', 'Jaipur'), ('Capital of Kerala?', 'Thiruvananthapuram')):
            m._n95_card_add(self.cid, front, back, 'states')
        card = m._n95_q('SELECT front, back FROM study95_card WHERE chat_id=? ORDER BY due LIMIT 1', (str(self.cid),))[0]
        with mock.patch.object(m._n108_random, 'shuffle', lambda x: None):        # unshuffled, the right answer is the last choice, never the first by luck
            m.handle(self.msg('quiz poll'))
        m.handle(self.msg('quiz poll'))                                           # and shuffled
        for sp in self.calls('sendPoll')[-2:]:
            self.assertEqual('quiz', sp['type'])
            options = [o['text'] for o in sp['options']]
            self.assertEqual(card[0], sp['question'])
            self.assertEqual(card[1], options[sp['correct_option_ids'][0]])
        self.assertEqual(len(self.calls('sendPoll')[-2]['options']) - 1, self.calls('sendPoll')[-2]['correct_option_ids'][0])

    def test_quiz_poll_falls_back_to_the_older_field(self):
        m = self.m
        for front, back in (('2+2?', '4'), ('3+3?', '6')):
            m._n95_card_add(self.cid, front, back, 'maths')
        replies = [{'ok': False, 'description': 'Bad Request: unknown field'}, {'ok': True, 'result': {}}]
        self.swap('tg', lambda method, **kw: (self.tgc.append((method, kw)), replies.pop(0) if method == 'sendPoll' else {'ok': True})[1])
        m._n108_quiz_poll(self.cid)
        polls = self.calls('sendPoll')
        self.assertIn('correct_option_ids', polls[0])
        self.assertIn('correct_option_id', polls[1])
        self.assertEqual(1, m._N108_STATS['quizzes'])

    def test_quiz_poll_without_cards(self):
        self.m.handle(self.msg('quiz poll'))
        self.assertIn('no study cards yet', self.texts2()[-1])


# ===================================================================================================================
# 6. Housekeeping
# ===================================================================================================================
class TestHousekeeping(VoiceCase):
    def test_version_rows_capabilities(self):
        m = self.m
        self.assertEqual('108.0', m.VERSION)
        rows = m._n108_regression_rows()
        self.assertTrue(rows and all(r['ok'] for r in rows), [r for r in rows if not r['ok']])
        self.assertIn('v108-hooks-installed', {r['name'] for r in m.prime_regression_suite()['tests']})
        self.assertIn('Voice 108', m._n82_capabilities())
        self.assertFalse(m._n79_editable('_n108_route'))

    def test_forgetting(self):
        m = self.m
        self.kv['n108_quiet'] = window_around_now(m)
        m.send_text(self.cid, 'A note about the Sharma wedding.')
        m.handle(self.msg('be casual with Sharma'))
        self.assertIn('voice108', {s[0] for s in m._N86_STORES})
        self.assertEqual(2, m._n108_st_voice(self.cid, lambda t: 'sharma' in t.lower(), True))
        self.assertEqual([], m._n108_held_rows(self.cid))
        self.assertEqual({}, m._n108_tone('person:sharma'))

    def test_the_sender_keeps_its_contract(self):
        m = self.m
        kb = {'inline_keyboard': []}
        self.assertIsNone(m.send_text(self.cid, 'x', kb))
        self.assertEqual((self.cid, 'x', kb), self.sent2[-1])

    def test_the_layer_places_no_orders_and_holds_no_secrets(self):
        src = layer_source()
        for bad in ('fyers_place', 'place_order', '_p75_open', 'save_secret', 'api_key', "AUTO['"):
            self.assertNotIn(bad, src, bad)


if __name__ == '__main__':
    unittest.main()
