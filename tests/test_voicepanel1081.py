"""Nemo v108.1 "Voice panel": replies go out as real voice notes (OGG/Opus with their length, so an iPhone shows the waveform and the speed button; MP3 only without
ffmpeg); a blocked voice note (Telegram privacy) is explained once and sent as an audio file; every older speaker sends a real voice note too; the voice options are a
card with buttons ("voice settings", "/voice", the owner's question "I can not see the voice options"); 🔊 Listen under longer answers; "test voice" reports exactly how
the voice note went; iPhone help; /voice in the owner's Telegram menu.

Offline. No Telegram, no network and no real voice service: Telegram calls and the voice engine are fakes (the fake voice engine makes a real MP3 with ffmpeg when it is
installed, so the OGG/Opus conversion and the length reading run for real).

    NEMO_FILE=/path/to/nemotron_bot.py python -m unittest tests.test_voicepanel1081 -v
"""
import json
import time
import unittest
from unittest import mock

from tests import test_cortex83 as base
from tests.test_voice108 import FFMPEG, VoiceCase, make_mp3, read, window_around_now


def setUpModule():
    if base.m is None:
        base.setUpModule()


def layer_source():
    src = read(base.NEMO_FILE)
    i = src.index('# NEMO 108.1 - VOICE PANEL')
    j = src.index('# NEMO 109 - ') if '# NEMO 109 - ' in src else src.rindex("if __name__")
    return src[i:j]


LONG = ('Your SIP of 5,000 rupees a month for ten years at a twelve percent return grows to about 11.6 lakh rupees, of which 6 lakh is what you put in and the rest is '
        'the growth. Starting two years earlier would add close to three lakh more.')


class PanelCase(VoiceCase):
    def setUp(self):
        super().setUp()
        m = self.m
        for k in m._N1081_STATS:
            m._N1081_STATS[k] = 0
        saved_last, saved_told = dict(m._N1081_LAST), dict(m._N1081_TOLD)
        m._N1081_LAST.update(kind=None, why='', secs=0, shown_as='', t=0.0)
        m._N1081_TOLD['forbidden'] = 0.0
        self.addCleanup(m._N1081_LAST.update, saved_last)
        self.addCleanup(m._N1081_TOLD.update, saved_told)
        saved_listen = dict(m._N1081_LISTEN)
        m._N1081_LISTEN.clear()
        self.addCleanup(lambda: (m._N1081_LISTEN.clear(), m._N1081_LISTEN.update(saved_listen)))
        self.put('send_text', m._n1081_send_text)                     # this layer's sender in front of v108's, in front of the recorder
        self.put('_N1081_SEND_PREV', m._n108_send_text)
        self.real_prev = m._N1081_HANDLE_PREV
        self.put('_N1081_HANDLE_PREV', self.prev)                     # the older layers, faked (a voice note still ends at the voice reader)

    def cq(self, data, sender=None, mid=500):
        return {'id': 'q1', 'data': data, 'from': {'id': self.cid if sender is None else sender}, 'message': {'message_id': mid, 'chat': {'id': self.cid}}}

    def last_kb(self):
        kb = [k for (_c, _t, k) in self.sent2 if k]
        return kb[-1] if kb else None

    def buttons(self, kb):
        return [b for row in kb['inline_keyboard'] for b in row]

    def toast(self):
        return [kw.get('text') for (mth, kw) in self.tgc if mth == 'answerCallbackQuery'][-1]


# ===================================================================================================================
# 1. Real voice notes: Telegram's own format first
# ===================================================================================================================
@unittest.skipUnless(FFMPEG, 'needs ffmpeg')
class TestRealVoiceNotes(PanelCase):
    def test_a_reply_goes_as_ogg_opus_with_its_length(self):
        m = self.m
        raw = []

        def fake_post(method, data, files, timeout=120):
            name, fobj, mime = list(files.values())[0]
            raw.append(fobj.read())
            self.posts.append({'method': method, 'data': dict(data), 'name': name, 'mime': mime, 'size': len(raw[-1])})
            return {'ok': True, 'result': {'message_id': 9, 'voice': {'file_id': 'V', 'duration': data.get('duration')}}}
        self.put('_n108_post', fake_post)
        self.put('_n108_tts', lambda text, lang, voice, rate, pitch, path, slow=False: make_mp3(path, 3) or 'edge-tts')
        self.assertEqual('voice-ogg', m._n108_speak(self.cid, 'Hello there, this is a test.'))
        self.assertEqual(1, len(self.posts), 'one upload: no MP3 first')
        p = self.posts[0]
        self.assertEqual(('sendVoice', 'nemo.ogg', 'audio/ogg'), (p['method'], p['name'], p['mime']))
        self.assertEqual(3, p['data']['duration'], 'the length goes with it, so the bubble shows it at once')
        self.assertTrue(raw[0].startswith(b'OggS') and b'OpusHead' in raw[0][:200], 'a real Ogg/Opus file')
        self.assertIn('vc108:slow:', p['data']['reply_markup'])
        self.assertEqual(('voice-ogg', 'voice', 3), (m._N1081_LAST['kind'], m._N1081_LAST['shown_as'], m._N1081_LAST['secs']))
        self.assertEqual(1, m._N1081_STATS['ogg'])
        self.assertIn('real voice notes', m._n1081_panel_text(self.cid))

    def test_the_format_is_the_one_telegram_voice_notes_use(self):
        m = self.m
        args = m._n1081_opus_args('in.mp3', 'out.ogg', 60)
        for a, b in (('-c:a', 'libopus'), ('-application', 'voip'), ('-ac', '1'), ('-ar', '48000'), ('-b:a', '32k')):
            self.assertEqual(b, args[args.index(a) + 1])
        self.assertEqual('16k', m._n1081_opus_args('a', 'b', 600)[m._n1081_opus_args('a', 'b', 600).index('-b:a') + 1], 'long notes stay small (Telegram keeps the waveform)')
        self.assertEqual('32k', m._n1081_opus_args('a', 'b', 0)[m._n1081_opus_args('a', 'b', 0).index('-b:a') + 1])

    def test_without_ffmpeg_it_is_an_mp3_and_the_owner_is_told_how_to_fix_it(self):
        m = self.m
        real_which = m._n108_shutil.which
        with mock.patch.object(m._n108_shutil, 'which', lambda name: None if name in ('ffmpeg', 'ffprobe') else real_which(name)):
            self.assertEqual('voice', m._n108_speak(self.cid, 'Hello there.'))
            self.assertEqual(['nemo.mp3'], [p['name'] for p in self.posts])
            self.assertEqual('no_ffmpeg', m._N1081_LAST['why'])
            self.assertIn('install ffmpeg on the server', m._n1081_report('voice'))
            self.assertIn('no ffmpeg', m._n1081_panel_text(self.cid))
            self.assertIn('no ffmpeg', m._n1081_format_line())
        self.assertEqual(1, m._N1081_STATS['mp3'])

    def test_a_refused_ogg_falls_back_to_mp3_and_says_why(self):
        m = self.m
        self.post_reply[('sendVoice', 'nemo.ogg')] = {'ok': False, 'description': 'Bad Request: wrong file type'}
        self.assertEqual('voice', m._n108_speak(self.cid, 'Hello there.'))
        self.assertIn('wrong file type', m._N1081_LAST['why'])
        self.assertIn('wrong file type', m._n1081_report('voice'))

    def test_a_blocked_voice_note_is_explained_once_and_sent_as_an_audio_file(self):
        m = self.m
        self.post_reply['sendVoice'] = {'ok': False, 'error_code': 400, 'description': 'Bad Request: VOICE_MESSAGES_FORBIDDEN'}
        self.assertEqual('audio', m._n108_speak(self.cid, 'Hello there.'))
        self.assertEqual(['sendVoice', 'sendAudio'], [p['method'] for p in self.posts], 'no second voice try once Telegram says it is blocked')
        told = [t for t in self.texts2() if 'Voice Messages' in t]
        self.assertEqual(1, len(told))
        self.assertIn('Privacy and Security', told[0])
        self.assertEqual('audio', m._n108_speak(self.cid, 'Hello again.'))
        self.assertEqual(1, len([t for t in self.texts2() if 'Voice Messages' in t]), 'told once a day, not on every voice note')
        self.assertEqual(2, m._N1081_STATS['forbidden'])
        self.assertIn('blocked', m._n1081_report('audio'))
        self.assertIn('blocking voice notes', m._n1081_panel_text(self.cid))

    def test_a_family_members_blocked_voice_note_tells_no_one(self):
        m = self.m
        self.post_reply['sendVoice'] = {'ok': False, 'description': 'Bad Request: VOICE_MESSAGES_FORBIDDEN'}
        self.assertEqual('audio', m._n108_speak(555, 'Namaste.'))
        self.assertEqual([], [t for t in self.texts2() if 'Voice Messages' in t])

    def test_telegram_storing_it_as_something_else_is_reported(self):
        m = self.m
        self.post_reply['sendVoice'] = {'ok': True, 'result': {'message_id': 3, 'document': {'file_id': 'D'}}}
        self.assertEqual('voice-ogg', m._n108_speak(self.cid, 'Hello there.'))
        self.assertIn('stored it as document', m._n1081_report('voice-ogg'))


# ===================================================================================================================
# 2. The older speakers send real voice notes too
# ===================================================================================================================
@unittest.skipUnless(FFMPEG, 'needs ffmpeg')
class TestOlderSpeakers(PanelCase):
    def test_the_old_speak_sends_a_voice_note_with_the_buttons_not_a_music_file(self):
        m = self.m
        self.assertTrue(m.speak(self.cid, 'Voice mode is on. I will speak my answers.'))
        self.assertEqual(['sendVoice'], [p['method'] for p in self.posts])
        self.assertEqual('nemo.ogg', self.posts[0]['name'])
        self.assertIn('vc108:', self.posts[0]['data']['reply_markup'])
        self.assertEqual(1, m._N1081_STATS['legacy_speak'])

    def test_say_in_the_chat_goes_through_every_layer_to_the_new_speaker(self):
        m = self.m
        self.put('_N1081_HANDLE_PREV', self.real_prev)                # the real chain of older layers, down to the oldest handler's “/say”
        m.handle(self.msg('/say hello there'))
        self.assertEqual(['sendVoice'], [p['method'] for p in self.posts])
        self.assertEqual('hello there', self.tts[-1]['text'])

    def test_an_old_speaker_takes_the_voice_turn_so_nothing_is_spoken_twice(self):
        m = self.m
        m._n108_mark_voice_turn(self.cid)
        m.speak(self.cid, 'Here is the diagram you asked for.')
        m.send_text(self.cid, 'And here is the long explanation of the diagram, written out in full for you to read.')
        self.assertEqual(1, len(self.voices()))

    def test_when_no_voice_can_be_made_the_old_speaker_still_tries(self):
        m = self.m
        self.put('_n108_tts', lambda *a, **k: '')
        old = mock.Mock(return_value=False)
        self.put('_N1081_SPEAK_PREV', old)
        self.assertFalse(m.speak(self.cid, 'Hello'))
        old.assert_called_once_with(self.cid, 'Hello')


# ===================================================================================================================
# 3. The voice options card
# ===================================================================================================================
class TestPanel(PanelCase):
    def test_voice_settings_is_a_card_with_buttons(self):
        m = self.m
        m.handle(self.msg('voice settings'))
        self.prev.assert_not_called()
        text = self.texts2()[-1]
        self.assertTrue(text.startswith('🎙 Voice options'))
        labels = [b['text'] for b in self.buttons(self.last_kb())]
        for want in ('✓ 🎤 When I speak', '🗣 Always', '🔇 Off', '✓ 🎧📝 Voice and text', '🎧 Voice only', '✓ Normal', '▶️ Test my voice', '📖 Read my last answer',
                     '📱 Voice notes on iPhone', '🔊 Listen button: on', '👪 Family voice: on'):
            self.assertIn(want, labels)
        self.assertTrue(all(len(b['callback_data'].encode()) <= 64 for b in self.buttons(self.last_kb())), 'Telegram limits button data to 64 bytes')

    def test_the_owners_own_words_open_it(self):
        m = self.m
        for words in ('in my telegram i can not see voice message send options i use ios iphone', '/voice', 'voice options', 'Voice menu', 'show my voice settings',
                      'where are the voice buttons?', "I can't find the voice note settings"):
            n = len(self.sent2)
            m.handle(self.msg(words))
            self.assertEqual(n + 1, len(self.sent2), words)
            self.assertTrue(self.texts2()[-1].startswith('🎙 Voice options'), words)
        self.prev.assert_not_called()
        self.assertIn('Here they are', self.texts2()[0])

    def test_other_talk_about_voice_is_left_alone(self):
        m = self.m
        for words in ('what is the voice of the customer', 'make my voice deeper in this video', 'send the voice note to Riya'):
            m.handle(self.msg(words))
        passed = [c[0][0]['text'] for c in self.prev.call_args_list]
        self.assertEqual(['what is the voice of the customer', 'make my voice deeper in this video', 'send the voice note to Riya'], passed)

    def test_only_the_owner_in_their_own_chat(self):
        m = self.m
        msg = self.msg('voice settings')
        msg['from']['id'] = 555
        msg['chat']['id'] = 555
        m.handle(msg)
        g = self.msg('voice settings')
        g['chat']['type'] = 'group'
        g['chat']['id'] = -100
        m.handle(g)
        self.assertEqual(2, self.prev.call_count)
        self.assertEqual([], self.sent2)

    def test_a_tap_changes_the_setting_and_redraws_the_same_card(self):
        m = self.m
        m.handle_callback(self.cq('vp1081:s:voice_speed:slow'))
        self.assertEqual('slow', self.kv['n108_voice_speed'])
        edit = self.calls('editMessageText')[-1]
        self.assertEqual((self.cid, 500), (edit['chat_id'], edit['message_id']))
        self.assertIn('✓ 🐢 Slow', [b['text'] for b in self.buttons(edit['reply_markup'])])
        self.assertIn('speed slow', edit['text'])
        self.assertEqual('Slower.', self.toast())
        self.assertEqual([], self.sent2, 'the card is edited in place, not sent again')
        m.handle_callback(self.cq('vp1081:s:voice_gender:male'))
        self.assertEqual('male', self.kv['n108_voice_gender'])
        self.assertEqual('gu-IN-NiranjanNeural', m._n108_voice_name('gu'))
        m.handle_callback(self.cq('vp1081:s:listen:off'))
        self.assertEqual('off', self.kv['n108_listen'])
        self.assertIn('🔊 Listen button: off', [b['text'] for b in self.buttons(self.calls('editMessageText')[-1]['reply_markup'])])

    def test_bad_or_foreign_taps_change_nothing(self):
        m = self.m
        m.handle_callback(self.cq('vp1081:s:voice:loud'))
        m.handle_callback(self.cq('vp1081:s:trading:on'))
        self.assertNotIn('n108_voice', self.kv)
        self.assertNotIn('n108_trading', self.kv)
        m.handle_callback(self.cq('vp1081:s:voice:off', sender=555))
        self.assertNotIn('n108_voice', self.kv)
        self.assertIn('Only the owner', self.toast())
        self.assertEqual([], self.calls('editMessageText'))

    def test_a_card_that_cannot_be_edited_is_sent_again(self):
        m = self.m
        self.tg_fail['editMessageText'] = {'ok': False, 'description': 'Bad Request: message is not modified'}
        m.handle_callback(self.cq('vp1081:s:voice:mirror'))
        self.assertEqual([], self.sent2)
        self.tg_fail['editMessageText'] = {'ok': False, 'description': 'Bad Request: message to edit not found'}
        m.handle_callback(self.cq('vp1081:s:voice:always'))
        self.assertTrue(self.texts2()[-1].startswith('🎙 Voice options'))
        self.assertIn('✓ 🗣 Always', [b['text'] for b in self.buttons(self.last_kb())])

    def test_voice_off_also_turns_off_the_oldest_switch_and_slash_voice_on_off_work(self):
        m = self.m
        m.VOICE[self.cid] = True
        self.addCleanup(m.VOICE.pop, self.cid, None)
        m.handle_callback(self.cq('vp1081:s:voice:off'))
        self.assertNotIn(self.cid, m.VOICE)
        self.assertEqual('off', self.kv['n108_voice'])
        m.handle(self.msg('/voice on'))
        self.assertEqual('always', self.kv['n108_voice'])
        m.handle(self.msg('/voice off'))
        self.assertEqual('off', self.kv['n108_voice'])
        self.prev.assert_not_called()

    def test_the_card_is_a_reply_so_quiet_hours_never_hold_it(self):
        m = self.m
        self.kv['n108_quiet'] = window_around_now(m)
        m._N108_INBOUND.pop(self.cid, None)
        m.handle(self.msg('voice settings'))
        self.assertTrue(self.texts2()[-1].startswith('🎙 Voice options'))
        self.assertEqual(0, m._N108_STATS['held'])

    def test_voice_status_comes_with_the_buttons(self):
        m = self.m
        m.handle(self.msg('voice status'))
        self.assertIn('Engines:', self.texts2()[-1])
        self.assertIn('On your phone:', self.texts2()[-1])
        self.assertIn('/voice in your Telegram menu: not yet', self.texts2()[-1])
        self.assertIn('▶️ Test my voice', [b['text'] for b in self.buttons(self.last_kb())])

    def test_iphone_help(self):
        m = self.m
        m.handle_callback(self.cq('vp1081:iphone'))
        m.handle(self.msg('how do i send a voice note on my iphone'))
        tips = [t for t in self.texts2() if t.startswith('📱 Voice notes on iPhone')]
        self.assertEqual(2, len(tips))
        for want in ('leave the message box empty', 'square camera icon', 'Press and hold', 'Microphone on', 'test voice'):
            self.assertIn(want, tips[0])

    def test_read_my_last_answer(self):
        m = self.m
        m.handle_callback(self.cq('vp1081:last'))
        self.assertIn('nothing to read out yet', self.texts2()[-1])
        m._N108_LAST_REPLY[self.cid] = 'The meeting with Mehta is at four.'
        m.handle_callback(self.cq('vp1081:last'))
        self.assertEqual(1, len(self.voices()))
        self.assertIn('Mehta', self.tts[-1]['text'])


@unittest.skipUnless(FFMPEG, 'needs ffmpeg')
class TestTestVoice(PanelCase):
    def test_test_voice_sends_one_and_says_how_it_went(self):
        m = self.m
        m.handle(self.msg('test voice'))
        self.assertEqual(1, len(self.voices()))
        self.assertTrue(self.texts2()[-1].startswith('✅ Sent as a real voice note (OGG/Opus, 1 s)'))
        m.handle_callback(self.cq('vp1081:test'))
        self.assertEqual(2, len(self.voices()))
        self.assertEqual(2, m._N1081_STATS['tests'])
        self.assertIn('Making a test voice note', self.toast())

    def test_no_voice_engine_is_named(self):
        m = self.m
        self.put('_n108_tts', lambda *a, **k: '')
        self.put('_n1081_engines', lambda: {'ffmpeg': True, 'edge_tts': False, 'gtts': False})
        m.handle(self.msg('check voice'))
        self.assertIn('no voice engine is installed', self.texts2()[-1])
        self.put('_n1081_engines', lambda: {'ffmpeg': True, 'edge_tts': True, 'gtts': True})
        m.handle(self.msg('voice test'))
        self.assertIn('did not answer', self.texts2()[-1])

    def test_telegram_refusing_everything_is_named(self):
        m = self.m
        self.post_reply['sendVoice'] = {'ok': False, 'description': 'Bad Request: chat not found'}
        self.post_reply['sendAudio'] = {'ok': False, 'description': 'Bad Request: chat not found'}
        m.handle(self.msg('send me a test voice note'))
        self.assertIn('chat not found', self.texts2()[-1])
        self.assertTrue(self.texts2()[-1].startswith('❌'))


# ===================================================================================================================
# 4. 🔊 Listen under longer answers
# ===================================================================================================================
@unittest.skipUnless(FFMPEG, 'needs ffmpeg')
class TestListen(PanelCase):
    def setUp(self):
        super().setUp()
        self.m._N108_INBOUND[self.cid] = time.time()                  # the owner just wrote: what Nemo sends now is a reply

    def test_a_longer_answer_gets_listen_and_a_tap_speaks_that_answer(self):
        m = self.m
        m.send_text(self.cid, LONG)
        kb = self.last_kb()
        self.assertEqual(['🔊 Listen'], [b['text'] for b in self.buttons(kb)])
        m.send_text(self.cid, 'Something else entirely, long enough to get its own listen button under it as well, so that the two can be told apart later on.')
        m.handle_callback(self.cq(kb['inline_keyboard'][0][0]['callback_data']))
        self.assertEqual(1, len(self.voices()))
        self.assertIn('Your SIP of 5,000 rupees', self.tts[-1]['text'], 'the answer under which it was tapped, not the latest one')
        self.assertIn('Recording it as a voice note', self.toast())
        self.assertEqual(1, m._N1081_STATS['listen_taps'])

    def test_no_listen_button_where_it_does_not_belong(self):
        m = self.m
        m.send_text(self.cid, 'Done.')                                                    # short
        m.send_text(self.cid, 'Your meeting with Mehta is at four today, and the bank call is at six this evening.')   # one line: quicker to read than to hear
        m.send_text(self.cid, '🧭 Understanding your request... ' + LONG)                 # progress
        card = {'inline_keyboard': [[{'text': 'Approve', 'callback_data': 'x'}]]}
        m.send_text(self.cid, LONG, card)                                                 # its own buttons
        m.send_text(555, LONG)                                                            # someone else's chat
        self.assertEqual([None, None, None, card, None], [k for (_c, _t, k) in self.sent2])
        m._N108_INBOUND[self.cid] = time.time() - 4000
        m.send_text(self.cid, LONG)                                                       # sent on Nemo's own, not a reply
        self.kv['n108_listen'] = 'off'
        m._N108_INBOUND[self.cid] = time.time()
        m.send_text(self.cid, LONG)                                                       # switched off
        self.assertEqual([None, None], [k for (_c, _t, k) in self.sent2[-2:]])

    def test_an_answer_that_is_spoken_anyway_gets_no_listen_button(self):
        m = self.m
        m._n108_mark_voice_turn(self.cid)
        m.send_text(self.cid, LONG)
        self.assertIsNone(self.sent2[-1][2])
        self.assertEqual(1, len(self.voices()), 'the answer to a voice note is spoken')
        self.kv['n108_voice'] = 'always'
        m.send_text(self.cid, LONG)
        self.assertIsNone(self.sent2[-1][2])

    def test_old_buttons_and_other_chats(self):
        m = self.m
        m.handle_callback(self.cq('vp1081:say:deadbeef'))
        self.assertIn('too old', self.toast())
        m.send_text(self.cid, LONG)
        data = self.buttons(self.last_kb())[0]['callback_data']
        m.handle_callback(self.cq(data, sender=555))
        self.assertEqual([], self.voices())

    def test_listen_buttons_in_words_and_the_store_is_bounded_and_forgettable(self):
        m = self.m
        m.handle(self.msg('listen button off'))
        self.assertEqual('off', self.kv['n108_listen'])
        m.handle(self.msg('show listen buttons'))
        self.assertEqual('on', self.kv['n108_listen'])
        m._N108_INBOUND[self.cid] = time.time()
        for i in range(230):
            m.send_text(self.cid, LONG + (' Sharma.' if i == 229 else ' #%d' % i))
        self.assertEqual(200, len(m._N1081_LISTEN))
        self.assertEqual(1, m._n1081_st_listen(self.cid, lambda s: 'Sharma' in s, False))
        self.assertEqual(1, m._n1081_st_listen(self.cid, lambda s: 'Sharma' in s, True))
        self.assertEqual(0, m._n1081_st_listen(self.cid, lambda s: 'Sharma' in s, False))
        self.assertIn('voicepanel1081', {s[0] for s in m._N86_STORES})


# ===================================================================================================================
# 5. /voice in the owner's Telegram menu
# ===================================================================================================================
class TestMenu(PanelCase):
    def fake_menu(self, chat=None, private=None, default=None, fail=None):
        calls = []

        def tg(method, **kw):
            calls.append((method, kw))
            if fail and method in fail:
                return fail[method]
            if method == 'getMyCommands':
                kind = kw['scope']['type']
                return {'ok': True, 'result': {'chat': chat, 'all_private_chats': private, 'default': default}[kind] or []}
            return {'ok': True, 'result': True}
        self.swap('tg', tg)
        return calls

    def test_voice_joins_the_commands_already_there(self):
        m = self.m
        calls = self.fake_menu(default=[{'command': 'start', 'description': 'Start'}, {'command': 'help', 'description': 'Help'}])
        self.assertEqual('done', m._n1081_menu(True))
        sets = [kw for (mth, kw) in calls if mth == 'setMyCommands']
        self.assertEqual(1, len(sets))
        self.assertEqual(['voice', 'start', 'help'], [c['command'] for c in sets[0]['commands']])
        self.assertEqual({'type': 'chat', 'chat_id': self.cid}, sets[0]['scope'], 'only the owner\'s own menu')
        self.assertEqual('on', self.kv['n108_menu1081'])

    def test_already_there_and_removing_it(self):
        m = self.m
        calls = self.fake_menu(chat=[{'command': 'voice', 'description': 'Voice'}, {'command': 'start', 'description': 'Start'}])
        self.assertEqual('already', m._n1081_menu(True))
        self.assertEqual([], [1 for (mth, _k) in calls if mth == 'setMyCommands'])
        self.assertEqual('done', m._n1081_menu(False))
        self.assertEqual(['start'], [c['command'] for c in [kw for (mth, kw) in calls if mth == 'setMyCommands'][-1]['commands']])
        self.assertEqual('off', self.kv['n108_menu1081'])
        calls = self.fake_menu(chat=[{'command': 'voice', 'description': 'Voice'}])
        self.assertEqual('done', m._n1081_menu(False))
        self.assertEqual(['deleteMyCommands'], [mth for (mth, _k) in calls if mth in ('setMyCommands', 'deleteMyCommands')])

    def test_telegram_saying_no_is_reported_and_bad_entries_are_dropped(self):
        m = self.m
        self.fake_menu(fail={'getMyCommands': {'ok': False, 'description': 'Unauthorized'}})
        self.assertIn('Unauthorized', m._n1081_menu(True))
        calls = self.fake_menu(default=[{'command': 'Bad Name!', 'description': 'x'}, {'command': 'ok_1', 'description': ''}, 'junk'],
                               fail={'setMyCommands': {'ok': False, 'description': 'Bad Request: too many'}})
        self.assertIn('too many', m._n1081_menu(True))
        self.assertEqual(['voice', 'ok_1'], [c['command'] for c in [kw for (mth, kw) in calls if mth == 'setMyCommands'][0]['commands']])
        self.assertNotIn('n108_menu1081', self.kv)

    def test_in_words(self):
        m = self.m
        self.fake_menu()
        m.handle(self.msg('add voice to my menu'))
        self.assertIn('/voice is in your Telegram menu', self.texts2()[-1])
        m.handle(self.msg('remove voice from the menu'))
        self.assertIn('no longer in your Telegram menu', self.texts2()[-1])


# ===================================================================================================================
# 6. Boot and housekeeping
# ===================================================================================================================
class TestHousekeeping(PanelCase):
    def test_after_start_the_menu_and_one_card_once(self):
        m = self.m
        menu = mock.Mock(return_value='done')
        self.put('_n1081_menu', menu)
        with mock.patch.object(m._n108_time, 'sleep', lambda s: None):
            m._n1081_boot()
            self.kv['n108_menu1081'] = 'on'
            m._n1081_boot()
        menu.assert_called_once_with(True)
        cards = [t for t in self.texts2() if t.startswith('🎙 Voice options')]
        self.assertEqual(1, len(cards))
        self.assertIn('now buttons', cards[0])
        self.kv['n108_menu1081'] = 'off'                              # the owner removed it: not added back
        with mock.patch.object(m._n108_time, 'sleep', lambda s: None):
            m._n1081_boot()
        menu.assert_called_once_with(True)

    def test_version_rows_capabilities_and_hooks(self):
        m = self.m
        self.assertEqual('108.1', m.VERSION)
        rows = m._n1081_regression_rows()
        self.assertTrue(rows and all(r['ok'] for r in rows), [r for r in rows if not r['ok']])
        names = {r['name'] for r in m.prime_regression_suite()['tests']}
        self.assertIn('v1081-hooks-installed', names)
        self.assertIn('v108-hooks-installed', names)
        self.assertIn('Voice panel 108.1', m._n82_capabilities())
        self.assertFalse(m._n79_editable('_n1081_route'))
        self.assertIn(('voice', 'Voice options: voice replies, speed, female or male voice, Listen buttons, test voice, iPhone help'), m._N40_COMMANDS)
        self.assertIsNot(m.main, m._N1081_MAIN_PREV)
        self.assertTrue(read(base.NEMO_FILE).startswith('"""nemotron_bot.py v108.1 - VOICE PANEL'))

    def test_the_layer_places_no_orders_and_holds_no_secrets(self):
        src = layer_source()
        for bad in ('fyers_place', 'place_order', '_p75_open', 'save_secret', 'api_key', "AUTO['", 'BOT_TOKEN'):
            self.assertNotIn(bad, src, bad)


if __name__ == '__main__':
    unittest.main()
