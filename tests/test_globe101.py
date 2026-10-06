"""Nemo v101 "Globe": world markets and macro knowledge (17 exchanges, sessions and holidays, a world calendar, a live world board, overnight cues for India with an out-of-sample check), nine detailed charts, Sigma polish,
and the family fix (an ability that is switched on works from end to end; one phrase gives the family everything that can safely be given).

Offline. No Telegram, no network (the public chart feed is replaced by a generator; a test asserts the raw HTTP layer is never touched), no broker, no AI, no order. Known-answer tests use dates and numbers that can be
checked by hand (Easter, Thanksgiving, a regression line, a correlation). The family tests run the REAL Circle gate and the REAL v41 downloader with only the network and the downloader program stubbed, because the
older test stubbed the engine and so could not see that it still refused everyone but the owner.

    NEMO_FILE=/path/to/nemotron_bot.py python -m unittest tests.test_globe101 -v
"""
import ast
import datetime as dt
import math
import random
import re
import struct
import threading
import time
import unittest
from unittest import mock

from tests import test_cortex83 as base
from tests.test_forge91 import OWNER_ID
from tests.test_sigma100 import SigmaCase, FrozenTime, NOW, IST, candles, trend, ist_ts, setUpModule as _sigma_setup


def setUpModule():
    _sigma_setup()


def globe_source():
    src = open(base.NEMO_FILE, encoding='utf-8').read()
    i = src.index('# NEMO 101 - GLOBE')
    j = src.rindex("if __name__")
    return src[i:j]


def utc_ts(y, mo, d, h=0, mi=0):
    return dt.datetime(y, mo, d, h, mi, tzinfo=dt.timezone.utc).timestamp()


def png_size(raw):
    assert raw[:8] == b'\x89PNG\r\n\x1a\n'
    return struct.unpack('>II', raw[16:24])


# ===================================================================================================================
# a synthetic world: weekday candles for any feed symbol
# ===================================================================================================================
LAST_US = dt.date(2026, 10, 2)                  # a Friday: the last US session before NOW (Monday 5 Oct, 10:30 IST)


def weekdays_back(last, n):
    out, d = [], last
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= dt.timedelta(days=1)
    return list(reversed(out))


def rows_for(days, closes, hour_utc, minute=0, opens=None, vols=None, wick=0.004):
    out, prev = [], closes[0]
    for i, (d, c) in enumerate(zip(days, closes)):
        o = opens[i] if opens else prev
        ts = int(dt.datetime(d.year, d.month, d.day, hour_utc, minute, tzinfo=dt.timezone.utc).timestamp())
        out.append([ts, o, max(o, c) * (1 + wick), min(o, c) * (1 - wick), c, vols[i] if vols else 1e6])
        prev = c
    return out


def walk(n, start=100.0, drift=0.0003, vol=0.01, seed=1):
    rnd = random.Random(seed)
    px, out = start, []
    for _ in range(n):
        px *= 1 + drift + rnd.gauss(0, vol)
        out.append(px)
    return out


def synthetic_world(n=300):
    """{feed symbol: [[ts, o, h, l, c, v]]}: every symbol a seeded random walk on its own weekdays (US sessions stamped 13:30 UTC, NIFTY 03:45 UTC)."""
    world = {}
    days = weekdays_back(LAST_US, n)
    for k, row in enumerate(m_instr()):
        sym = row[0]
        start = 4.2 if row[3] == 'rate' else 1000.0
        cl = walk(n, start, 0.0, 0.004 if row[3] == 'rate' else 0.01, seed=k + 1)
        if row[3] == 'rate':
            cl = [4.0 + 0.3 * math.sin(i / 9.0) for i in range(n)]
        hour = 3 if sym in ('^NSEI', '^BSESN') else 13
        world[sym] = rows_for(days, cl, hour, 45 if hour == 3 else 30)
    return world


def m_instr():
    return base.m._N101_INSTR


class GlobeCase(SigmaCase):
    def setUp(self):
        super().setUp()
        m = self.m
        for k in m._N101_STATS:
            m._N101_STATS[k] = 0
        m._n101_db().close()
        m._n101_q('DELETE FROM globe101_event', write=True)
        m._n101_q('DELETE FROM globe101_setting', write=True)
        m._n100_q('DELETE FROM sig100_cache', write=True)
        self.world = synthetic_world()
        self.fetch_calls = []
        self.fetch_fail = set()

        def fetch(ysym, rng='1y', interval='1d'):
            self.fetch_calls.append((ysym, rng, interval))
            if ysym in self.fetch_fail or ysym not in self.world:
                raise ValueError('no data')
            return [list(r) for r in self.world[ysym]]
        self.start(m, '_n101_fetch', fetch)
        self.images = []

        def send_image(cid, raw, name, caption='', kb=None, force_file=False):
            self.images.append({'cid': cid, 'raw': raw, 'name': name, 'caption': caption})
            return True
        self.start(m, '_n90_send_image', send_image)
        self.http_hits = []
        self.start(m.requests, 'get', lambda *a, **k: self.http_hits.append(('get', a)) or (_ for _ in ()).throw(AssertionError('network used: %r' % (a,))))
        self.start(m.requests, 'post', lambda *a, **k: self.http_hits.append(('post', a)) or (_ for _ in ()).throw(AssertionError('network used: %r' % (a,))))
        self.start(m, '_N101_HANDLE_PREV', lambda msg: self.passed.append(msg))
        self.start(m, '_n88_record', lambda msg: None)
        self.start(m, 'BLOCKED', [])
        self.start(m, 'KNOWN', [])
        self.start(m, 'UCOUNT', {})
        self.start(m, 'save_data', lambda: None)
        self.ai_reply = lambda p: 'AI-REPLY'
        m._n41_init()                                    # the older layers' tables (the family list), as the Circle tests do
        try:
            m._n54_init()
        except Exception:
            pass
        m._n89_db().close()
        m._n88_db().close()
        m._N89_RX_CACHE.clear()
        for k in m._N89_STATS:
            m._N89_STATS[k] = 0
        m._n89_q('DELETE FROM circle89_rule', write=True)
        m._n89_q('DELETE FROM circle89_use', write=True)
        m._n89_q('DELETE FROM circle89_person', write=True)
        m._n97_q('DELETE FROM desk97_person', write=True)
        m._n97_q('DELETE FROM desk97_setting', write=True)
        m.BOTNAME['u'] = 'nemo_bot'
        m._n89_set_setting('owner_name', 'Gautam')

    def sent_since(self, n0, cid=OWNER_ID):
        return '\n'.join(t for c, t in self.sent[n0:] if c == cid)

    def drain(self):
        for t in list(threading.enumerate()):
            if t.name.startswith(('nemo-circle89', 'nemo-globe101', 'nemo701-')):
                t.join(15)

    def msg_from(self, uid, text, name='Asha'):
        return {'chat': {'id': uid, 'type': 'private'}, 'from': {'id': uid, 'first_name': name}, 'text': text, 'message_id': 1}

    def other(self, text, uid=5552, name='Asha'):
        """A message from someone who is not the owner, through the real Circle gate; returns what they were sent."""
        n0 = len(self.sent)
        self.m._n89_gate(self.msg_from(uid, text, name))
        self.drain()
        return self.sent_since(n0, uid)

    def family(self, uid=5552, name='Asha'):
        self.m._n89_note_person(str(uid), name, '')
        self.m._n89_set_family(str(uid), name, True)

    def pngs(self):
        return [i for i in self.images if i['raw'][:4] == b'\x89PNG']


# ===================================================================================================================
# 1. KNOWLEDGE THAT NEEDS NO NETWORK: calendars, holidays, sessions
# ===================================================================================================================
class TestHolidayRules(GlobeCase):
    def test_easter_known_dates(self):
        e = self.m._n101_easter
        self.assertEqual(e(2024), dt.date(2024, 3, 31))
        self.assertEqual(e(2025), dt.date(2025, 4, 20))
        self.assertEqual(e(2026), dt.date(2026, 4, 5))
        self.assertEqual(e(2027), dt.date(2027, 3, 28))

    def test_nth_weekday(self):
        f = self.m._n101_nth_weekday
        self.assertEqual(f(2026, 11, 3, 4), dt.date(2026, 11, 26))          # Thanksgiving: the 4th Thursday
        self.assertEqual(f(2026, 5, 0, -1), dt.date(2026, 5, 25))           # Memorial Day: the last Monday of May
        self.assertEqual(f(2026, 1, 0, 3), dt.date(2026, 1, 19))            # MLK day: the 3rd Monday of January
        self.assertEqual(f(2026, 9, 0, 1), dt.date(2026, 9, 7))             # Labor Day

    def test_us_closed_days_2026_match_the_published_list(self):
        h = self.m._n101_us_holidays(2026)
        want = {dt.date(2026, 1, 1): "New Year's Day", dt.date(2026, 1, 19): 'Martin Luther King Jr. Day', dt.date(2026, 2, 16): "Presidents' Day", dt.date(2026, 4, 3): 'Good Friday',
                dt.date(2026, 5, 25): 'Memorial Day', dt.date(2026, 6, 19): 'Juneteenth', dt.date(2026, 7, 3): 'Independence Day', dt.date(2026, 9, 7): 'Labor Day',
                dt.date(2026, 11, 26): 'Thanksgiving Day', dt.date(2026, 12, 25): 'Christmas Day'}
        self.assertEqual(h, want)

    def test_july_4_on_a_saturday_is_observed_on_friday(self):
        self.assertEqual(self.m._n101_us_holidays(2026)[dt.date(2026, 7, 3)], 'Independence Day')

    def test_new_year_on_a_saturday_is_not_observed_on_the_friday_before(self):
        self.assertNotIn(dt.date(2021, 12, 31), self.m._n101_us_holidays(2021))        # 1 Jan 2022 was a Saturday
        self.assertNotIn(dt.date(2022, 1, 1), self.m._n101_us_holidays(2022))

    def test_us_early_closes(self):
        f = self.m._n101_us_early
        self.assertTrue(f(dt.date(2026, 11, 27)))
        self.assertTrue(f(dt.date(2026, 12, 24)))
        self.assertTrue(f(dt.date(2026, 7, 2)))
        self.assertFalse(f(dt.date(2026, 10, 2)))
        self.assertEqual(self.m._n101_sessions('NYSE', dt.date(2026, 11, 27)), ((9, 30, 13, 0),))

    def test_uk_bank_holidays_2026(self):
        h = self.m._n101_uk_holidays(2026)
        self.assertEqual(h[dt.date(2026, 4, 3)], 'Good Friday')
        self.assertEqual(h[dt.date(2026, 4, 6)], 'Easter Monday')
        self.assertEqual(h[dt.date(2026, 5, 4)], 'Early May bank holiday')
        self.assertEqual(h[dt.date(2026, 5, 25)], 'Spring bank holiday')
        self.assertEqual(h[dt.date(2026, 8, 31)], 'Summer bank holiday')
        self.assertEqual(h[dt.date(2026, 12, 25)], 'Christmas Day')
        self.assertEqual(h[dt.date(2026, 12, 28)], 'Boxing Day (substitute)')              # Boxing Day 2026 is a Saturday

    def test_a_christmas_on_a_sunday_gets_substitutes(self):
        h = self.m._n101_uk_holidays(2022)
        self.assertEqual(h[dt.date(2022, 12, 27)], 'Christmas Day (substitute)')
        self.assertEqual(h[dt.date(2022, 12, 26)], 'Boxing Day')

    def test_germany_and_france(self):
        self.assertIn(dt.date(2026, 12, 24), self.m._n101_de_holidays(2026))
        self.assertIn(dt.date(2026, 4, 6), self.m._n101_fr_holidays(2026))
        self.assertNotIn(dt.date(2026, 12, 24), self.m._n101_fr_holidays(2026))

    def test_india_uses_nemos_own_table_and_says_nothing_for_other_years(self):
        h = self.m._n101_holiday
        first = sorted(self.m._N81_HOLIDAYS_2026)[0]
        self.assertTrue(h('in', dt.date.fromisoformat(first)))
        self.assertIsNone(h('in', dt.date(2027, 1, 26)))                        # unknown, not "open": the session note says so
        s = self.m._n101_session('NSE', utc_ts(2027, 3, 1, 5))
        self.assertIn('2026 only', s['note'])


class TestSessions(GlobeCase):
    def test_new_york_open_and_closed_in_both_clock_regimes(self):
        s = self.m._n101_session
        self.assertEqual(s('NYSE', utc_ts(2026, 10, 2, 14, 0))['state'], 'open')           # 10:00 EDT
        self.assertEqual(s('NYSE', utc_ts(2026, 10, 2, 13, 29))['state'], 'pre')           # 09:29 EDT
        self.assertEqual(s('NYSE', utc_ts(2026, 10, 2, 20, 0))['state'], 'closed')         # 16:00 EDT sharp: closed
        self.assertEqual(s('NYSE', utc_ts(2026, 12, 2, 14, 31))['state'], 'open')          # 09:31 EST (daylight saving over)
        self.assertEqual(s('NYSE', utc_ts(2026, 12, 2, 14, 29))['state'], 'pre')           # 09:29 EST

    def test_the_us_session_runs_19_00_to_01_30_ist_in_summer_and_20_00_to_02_30_in_winter(self):
        d = dt.date(2026, 10, 2)
        a = self.m._n101_window_ist('NYSE', d)
        self.assertIn((19 * 60, 24 * 60), a)                                              # 19:00-24:00 IST of that day
        self.assertIn((0, 90), a)                                                         # the tail of the day before's session, 00:00-01:30
        w = self.m._n101_window_ist('NYSE', dt.date(2026, 12, 2))
        self.assertIn((20 * 60, 24 * 60), w)
        self.assertIn((0, 150), w)

    def test_tokyo_lunch_break(self):
        s = self.m._n101_session
        self.assertEqual(s('TSE', utc_ts(2026, 10, 5, 2, 0))['state'], 'open')             # 11:00 JST
        self.assertEqual(s('TSE', utc_ts(2026, 10, 5, 2, 30))['state'], 'break')           # 11:30 JST: the morning session has ended
        self.assertEqual(s('TSE', utc_ts(2026, 10, 5, 3, 0))['state'], 'break')            # 12:00 JST
        self.assertEqual(s('TSE', utc_ts(2026, 10, 5, 3, 30))['state'], 'open')            # 12:30 JST
        self.assertEqual(s('TSE', utc_ts(2026, 10, 5, 6, 30))['state'], 'closed')          # 15:30 JST
        self.assertEqual(s('TSE', utc_ts(2026, 10, 4, 3, 0))['state'], 'weekend')

    def test_holiday_and_weekend_states(self):
        s = self.m._n101_session(('NYSE'), utc_ts(2026, 12, 25, 15, 0))
        self.assertEqual((s['state'], s['holiday']), ('holiday', 'Christmas Day'))
        s = self.m._n101_session('LSE', utc_ts(2026, 10, 3, 10, 0))
        self.assertEqual(s['state'], 'weekend')

    def test_next_open_skips_the_weekend_and_a_holiday(self):
        t = self.m._n101_next_open('NYSE', utc_ts(2026, 12, 24, 22, 0))                    # Thursday evening before Christmas
        d = dt.datetime.fromtimestamp(t, dt.timezone.utc)
        self.assertEqual((d.month, d.day, d.hour, d.minute), (12, 28, 14, 30))             # Monday 28 December, 09:30 EST
        t = self.m._n101_next_open('LSE', utc_ts(2026, 10, 2, 16, 0))
        self.assertEqual(dt.datetime.fromtimestamp(t, dt.timezone.utc).date(), dt.date(2026, 10, 5))

    def test_early_close_is_closed_after_one_pm(self):
        self.assertEqual(self.m._n101_session('NYSE', utc_ts(2026, 11, 27, 17, 30))['state'], 'open')     # 12:30 EST
        self.assertEqual(self.m._n101_session('NYSE', utc_ts(2026, 11, 27, 18, 30))['state'], 'closed')   # 13:30 EST

    def test_markets_without_a_holiday_model_say_so(self):
        s = self.m._n101_session('TSE', utc_ts(2026, 10, 5, 3, 0))
        self.assertIn('not modelled', s['note'])

    def test_every_exchange_has_sane_hours_and_a_zone(self):
        for k, mk in self.m._N101_MARKETS.items():
            self.assertTrue(self.m._n101_zone_is_real(mk['tz']), k)
            last = 0
            for oh, om, ch, cm in mk['sessions']:
                self.assertLess(oh * 60 + om, ch * 60 + cm, k)
                self.assertGreaterEqual(oh * 60 + om, last, k)
                last = ch * 60 + cm
        self.assertEqual(set(self.m._N101_ORDER), set(self.m._N101_MARKETS))

    def test_words(self):
        w = self.m._n101_open_words
        self.assertEqual(w('TSE', utc_ts(2026, 10, 5, 2, 0)), 'open (closes 08:00 IST)')                  # 11:00 JST: the morning session ends at 11:30 JST = 08:00 IST
        self.assertEqual(w('TSE', utc_ts(2026, 10, 5, 3, 0)), 'lunch break (reopens 09:00 IST)')
        self.assertTrue(w('NYSE', utc_ts(2026, 12, 25, 15, 0)).startswith('holiday: Christmas Day (opens '))
        self.assertTrue(w('LSE', utc_ts(2026, 10, 3, 10, 0)).startswith('closed for the weekend (opens Mon '))


# ===================================================================================================================
# 2. THE INSTRUMENTS, THE COUNTRY CARDS, THE WORLD CALENDAR
# ===================================================================================================================
class TestInstrumentsAndCalendar(GlobeCase):
    def test_resolve_aliases_and_symbols(self):
        r = self.m._n101_resolve
        self.assertEqual(r('brent')[0], 'BZ=F')
        self.assertEqual(r('The Nasdaq')[0], '^IXIC')
        self.assertEqual(r('dollar index')[0], 'DX-Y.NYB')
        self.assertEqual(r('rupee')[0], 'USDINR=X')
        self.assertEqual(r('10 year')[0], '^TNX')
        self.assertEqual(r('^N225')[0], '^N225')
        self.assertEqual(r('hang seng')[0], '^HSI')
        self.assertIsNone(r('wheat'))
        self.assertIsNone(r(''))

    def test_every_alias_points_at_a_board_row_and_every_row_has_a_known_group_and_venue(self):
        for a, sym in self.m._N101_ALIAS.items():
            self.assertIn(sym, self.m._N101_BY_SYM, a)
        for sym, label, group, kind, mk in self.m._N101_INSTR:
            self.assertIn(group, self.m._N101_GROUPS)
            self.assertTrue(mk in self.m._N101_MARKETS or mk in ('24x5', '24x7'), sym)
        self.assertEqual(len({r[0] for r in self.m._N101_INSTR}), len(self.m._N101_INSTR))

    def test_country_cards(self):
        key, c = self.m._n101_country('Japan')
        self.assertEqual((key, c['mk'], c['ccy'][1]), ('japan', 'TSE', 'JPY'))
        self.assertEqual(self.m._n101_country('the UK')[0], 'united kingdom')
        self.assertEqual(self.m._n101_country('eurozone')[0], 'euro area')
        self.assertIsNone(self.m._n101_country('atlantis')[0])
        for key, c in self.m._N101_COUNTRIES.items():
            self.assertIn(c['mk'], self.m._N101_MARKETS, key)
            self.assertTrue(c['bank'] and c['note'] and c['index'], key)
            if c['ccy'][2]:
                self.assertIn(c['ccy'][2], self.m._N101_BY_SYM, key)
        self.assertGreaterEqual(len(self.m._N101_COUNTRIES), 17)

    def test_fomc_2026_dates_are_listed_and_marked_published(self):
        ev = self.m._n101_events(dt.date(2026, 10, 1), dt.date(2026, 10, 31))
        f = [e for e in ev if 'Fed decision' in e['title']]
        self.assertEqual([e['day'] for e in f], [dt.date(2026, 10, 28)])
        self.assertEqual(f[0]['source'], 'published')
        self.assertEqual(f[0]['impact'], 'high')
        self.assertIn(dt.date(2026, 10, 29), f[0]['affects'])                       # the decision comes at 23:30 IST: it moves the NEXT Indian day too

    def test_rule_events_jobs_report_and_expiries(self):
        ev = self.m._n101_events(dt.date(2026, 10, 1), dt.date(2026, 10, 31))
        titles = {}
        for e in ev:
            titles.setdefault(e['day'], []).append(e['title'])
        self.assertTrue(any('jobs report' in t for t in titles[dt.date(2026, 10, 2)]))                   # the first Friday of October 2026 is the 2nd (also an NSE holiday)
        self.assertTrue(any('monthly options expiry' in t for t in titles[dt.date(2026, 10, 16)]))       # the third Friday
        self.assertTrue(any('NIFTY monthly expiry' in e['title'] and e['day'] == dt.date(2026, 10, 27) for e in ev))
        self.assertTrue(all(e['source'] in ('published', 'rule', 'owner') for e in ev))

    def test_the_owner_adds_and_removes_an_event_and_it_is_listed(self):
        eid, d, title, impact = self.m._n101_event_add('2026-10-08', 'RBI policy decision', 'high')
        self.assertTrue(eid.startswith('EV-') and impact == 'high')
        ev = [e for e in self.m._n101_events(dt.date(2026, 10, 5), dt.date(2026, 10, 12)) if e['source'] == 'owner']
        self.assertEqual([(e['day'], e['title'], e['id']) for e in ev], [(dt.date(2026, 10, 8), 'RBI policy decision', eid)])
        self.assertIn(eid, self.m._n101_events_text(NOW, 10))
        self.assertTrue(self.m._n101_event_remove(eid))
        self.assertFalse(self.m._n101_event_remove(eid))

    def test_event_input_is_checked(self):
        for args in (('tomorrow', 'x event'), ('2026-13-45', 'a thing'), ('2026-10-08', 'x'), ('2026-10-08', 'fine event', 'huge')):
            with self.assertRaises(ValueError):
                self.m._n101_event_add(*args)
        for i in range(200):
            self.m._n101_q('INSERT INTO globe101_event(id, day, title, impact, created) VALUES(?,?,?,?,?)', ('EV-%05d' % i, '2026-11-01', 'filler', 'low', 0.0), write=True)
        with self.assertRaises(ValueError):
            self.m._n101_event_add('2026-10-08', 'one more', 'low')

    def test_event_risk_looks_at_today_and_tomorrow_and_only_high_impact(self):
        self.m._n101_event_add('2026-10-06', 'Big speech', 'high')
        self.m._n101_event_add('2026-10-05', 'Minor thing', 'low')
        r = self.m._n101_event_risk(NOW, 1)                                           # Monday 5 Oct 10:30 IST: today and tomorrow
        self.assertEqual([e['title'] for e in r], ['Big speech'])
        self.assertEqual(self.m._n101_event_risk(utc_ts(2026, 10, 8, 5), 1), [])

    def test_the_fed_decision_night_counts_for_the_next_indian_day(self):
        r = self.m._n101_event_risk(ist_ts(2026, 10, 29, 9, 30), 0)                    # the morning after the 28 Oct decision
        self.assertTrue(any('Fed decision' in e['title'] for e in r))

    def test_events_text_for_the_family_hides_ids_and_owner_instructions(self):
        eid, *_ = self.m._n101_event_add('2026-10-08', 'RBI policy decision', 'high')
        owner = self.m._n101_events_text(NOW, 10)
        fam = self.m._n101_events_text(NOW, 10, owner=False)
        self.assertIn(eid, owner)
        self.assertNotIn(eid, fam)
        self.assertNotIn('globe event add', fam)
        self.assertIn('RBI policy decision', fam)

    def test_the_glossary_gained_world_words_without_replacing_any(self):
        m = self.m
        self.assertGreaterEqual(m._N101_TERMS_ADDED, 25)
        self.assertEqual(m._n94_term('what is DXY'.replace('what is ', '')), 'dxy')
        self.assertEqual(m._n94_term('yield curve inversion'), 'inverted yield curve')
        self.assertIn('Dollar index', m._n94_define('dxy'))
        self.assertEqual(m._n94_term('PCR'), 'pcr')                                    # an old word still works
        self.assertEqual(m._N94_GLOSSARY['pcr'], m._N94_GLOSSARY['pcr'])


# ===================================================================================================================
# 3. SMALL HELPERS AND THE STATISTICS
# ===================================================================================================================
class TestHelpers(GlobeCase):
    def test_a_move_that_rounds_to_zero_never_prints_a_minus_sign(self):
        f = self.m._n101_sgn
        self.assertEqual(f(-0.001, 1, '%'), '0.0%')
        self.assertEqual(f(-0.04, 1), '0.0')
        self.assertEqual(f(0.04, 1), '0.0')
        self.assertEqual(f(0.84, 2, '%'), '+0.84%')
        self.assertEqual(f(-1.236, 2, '%'), '-1.24%')
        self.assertEqual(f(-0.4, 0, 'bp'), '0bp')
        self.assertEqual(f(None), 'n/a')

    def test_ordinals(self):
        o = self.m._n101_ord
        self.assertEqual([o(x) for x in (1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 51, 52, 53, 59, 100, 111, 0)],
                         ['1st', '2nd', '3rd', '4th', '11th', '12th', '13th', '21st', '22nd', '23rd', '51st', '52nd', '53rd', '59th', '100th', '111th', '0th'])
        self.assertEqual(o(50.6), '51st')

    def test_ticks_are_round(self):
        t, step = self.m._n101_ticks(0, 97, 5)
        self.assertEqual(t, [0, 20, 40, 60, 80])
        t, step = self.m._n101_ticks(23760, 24510, 5)
        self.assertEqual(t[0] % 100, 0)
        self.assertEqual(self.m._n101_tick_text(0.25, 0.05), '0.25')
        self.assertEqual(self.m._n101_tick_text(24000, 100), '24,000')

    def test_labels_are_spread_apart_and_keep_their_order(self):
        out = self.m._n101_spread([100.0, 101.0, 102.0, 300.0], 15, 0, 400)
        self.assertEqual(sorted(out), out)
        self.assertTrue(all(b - a >= 15 - 1e-9 for a, b in zip(out, out[1:])))
        self.assertEqual(out[3], 300.0)
        low = self.m._n101_spread([395.0, 396.0], 15, 0, 400)
        self.assertLessEqual(max(low), 400)
        self.assertGreaterEqual(low[1] - low[0], 15 - 1e-9)

    def test_univariate_fit_known_answer(self):
        xs = list(range(1, 31))
        ys = [2.0 * x + 1.0 for x in xs]
        u = self.m._n101_uni(xs, ys)
        self.assertAlmostEqual(u['beta'], 2.0)
        self.assertAlmostEqual(u['alpha'], 1.0)
        self.assertAlmostEqual(u['corr'], 1.0)
        self.assertIsNone(self.m._n101_uni(xs[:10], ys[:10]))                          # too few points
        self.assertIsNone(self.m._n101_uni([1.0] * 30, ys))                            # no variance

    def test_ols_known_answer_and_a_near_duplicate_column_still_solves(self):
        X = [[float(i), float(i % 3)] for i in range(40)]
        y = [1.0 + 2.0 * r[0] - 0.5 * r[1] for r in X]
        b = self.m._n101_ols(X, y)
        self.assertAlmostEqual(b[0], 1.0, places=5)
        self.assertAlmostEqual(b[1], 2.0, places=5)
        self.assertAlmostEqual(b[2], -0.5, places=5)
        Xd = [[float(i), float(i) + 1e-12] for i in range(40)]
        self.assertIsNotNone(self.m._n101_ols(Xd, y))
        self.assertIsNone(self.m._n101_ols([[1.0]] * 3, [1.0] * 3))

    def test_the_table_of_exchanges_is_in_indian_time_in_words(self):
        t = self.m._n101_hours_ist_text('NYSE', utc_ts(2026, 10, 2, 14, 0))
        self.assertEqual(t, '19:00-01:30 (next day)')
        self.assertEqual(self.m._n101_hours_ist_text('TSE', utc_ts(2026, 10, 5, 3, 0)), '05:30-08:00 and 09:00-12:00')


class TestRowStatsAndTone(GlobeCase):
    def make(self, closes, kind='index', sym='^X'):
        days = weekdays_back(LAST_US, len(closes))
        rows = rows_for(days, closes, 13, 30)
        cs = self.m._n93_clean([{'ts': r[0], 'o': r[1], 'h': r[2], 'l': r[3], 'c': r[4], 'v': r[5]} for r in rows])
        return self.m._n101_row_stats((sym, 'X', 'Americas', kind, 'NYSE'), cs, NOW)

    def test_change_windows_and_position_in_the_year(self):
        closes = [100.0 + i for i in range(30)]                                      # 100..129
        s = self.make(closes)
        self.assertTrue(s['ok'])
        self.assertAlmostEqual(s['chg1'], (129 / 128.0 - 1) * 100)
        self.assertAlmostEqual(s['chg5'], (129 / 124.0 - 1) * 100)
        self.assertAlmostEqual(s['chg21'], (129 / 108.0 - 1) * 100)
        self.assertGreater(s['pos52'], 90)
        self.assertEqual(len(s['spark']), 20)

    def test_yields_move_in_basis_points(self):
        s = self.make([4.00] * 25 + [4.10], kind='rate')
        self.assertEqual(s['unit'], 'bp')
        self.assertAlmostEqual(s['chg1'], 10.0, places=6)

    def test_a_short_series_is_refused_not_guessed(self):
        s = self.make([1.0, 2.0, 3.0])
        self.assertFalse(s['ok'])

    def test_old_data_is_flagged(self):
        days = [dt.date(2026, 8, 3) + dt.timedelta(days=i) for i in range(30)]
        cs = self.m._n93_clean([{'ts': r[0], 'o': r[1], 'h': r[2], 'l': r[3], 'c': r[4], 'v': r[5]} for r in rows_for(days, [100.0 + i for i in range(30)], 13, 30)])
        s = self.m._n101_row_stats(('^X', 'X', 'Americas', 'index', 'NYSE'), cs, NOW)
        self.assertTrue(s['stale'])

    def test_tone_counts_breadth_vix_and_the_dollar(self):
        row = lambda sym, kind, chg: {'sym': sym, 'kind': kind, 'chg1': chg, 'stale': False}
        up = [row('i%d' % k, 'index', 1.0) for k in range(6)]
        t, score, words = self.m._n101_tone(up + [row('^VIX', 'vol', -6.0), row('DX-Y.NYB', 'fx', -0.5)])
        self.assertEqual((t, score), ('risk-on', 3))
        dn = [row('i%d' % k, 'index', -1.0) for k in range(6)]
        t, score, _ = self.m._n101_tone(dn + [row('^VIX', 'vol', 9.0), row('DX-Y.NYB', 'fx', 0.5)])
        self.assertEqual((t, score), ('risk-off', -3))
        mixed = [row('i%d' % k, 'index', 1.0 if k % 2 else -1.0) for k in range(6)]
        self.assertEqual(self.m._n101_tone(mixed)[0], 'mixed')
        self.assertEqual(self.m._n101_tone(mixed[:2])[1], 0)                          # fewer than four indexes: no breadth reading

    def test_region_counts_use_the_clock(self):
        self.assertEqual(self.m._n101_region_states('Asia-Pacific', NOW), '7 of 8 markets open (TSE, KRX, SSE, HKEX, TWSE, SGX, NSE)')       # Sydney has gone to 16:00 daylight time: closed
        self.assertEqual(self.m._n101_region_states('Europe', NOW), '0 of 4 markets open (none)')                                          # 07:00 in Frankfurt and London: not yet
        self.assertTrue(self.m._n101_region_states('Americas', NOW).startswith('0 of 4 markets open'))


class TestTheBoard(GlobeCase):
    def test_the_board_reads_every_symbol_and_names_the_ones_that_fail(self):
        self.fetch_fail = {'^MXX', 'ETH-USD'}
        b = self.m._n101_board(NOW)
        syms = {r['sym'] for r in b['rows']}
        self.assertEqual(len(b['rows']) + len(b['failed']), len(self.m._N101_INSTR))
        self.assertEqual({s for s, _w in b['failed']}, {'^MXX', 'ETH-USD'})
        self.assertNotIn('^MXX', syms)
        text = self.m._n101_board_text(b, NOW)
        self.assertIn('WORLD BOARD', text)
        self.assertIn('Not read:', text)
        self.assertIn('^MXX', text)
        self.assertLessEqual(len(text), 3950)

    def test_nothing_readable_is_said_plainly_and_nothing_is_made_up(self):
        self.world = {}
        b = self.m._n101_board(NOW)
        self.assertEqual(b['rows'], [])
        text = self.m._n101_board_text(b, NOW)
        self.assertIn('could not read any market', text)
        self.assertIn('Nothing is guessed', text)

    def test_the_text_shows_signed_moves_and_groups(self):
        b = self.m._n101_board(NOW)
        text = self.m._n101_board_text(b, NOW)
        for g in ('AMERICAS', 'EUROPE', 'ASIA-PACIFIC', 'CURRENCIES', 'COMMODITIES', 'RATES', 'CRYPTO'):
            self.assertIn(g, text)
        self.assertRegex(text, r'[▲▼•] S&P 500 [\d,\.]+ [+-]\d')
        self.assertNotIn('-0.00%', text)
        self.assertNotIn('+-', text)

    def test_the_second_call_is_served_from_the_cache(self):
        self.m._n101_board(NOW)
        n = len(self.fetch_calls)
        self.m._n101_board(NOW + 60)
        self.assertEqual(len(self.fetch_calls), n)

    def test_yields_quoted_times_ten_are_scaled_back(self):
        days = weekdays_back(LAST_US, 40)
        self.world['^TNX'] = rows_for(days, [41.0 + 0.01 * i for i in range(40)], 13, 30)
        cs, err = self.m._n101_series('^TNX', '1y', NOW)
        self.assertLess(cs[-1]['c'], 10)
        self.assertEqual(err, '')


# ===================================================================================================================
# 4. THE CUE MODEL: what the US session explained of NIFTY's opening gap
# ===================================================================================================================
def cue_world(seed, rel=0.0, same_day=0.0, n=520, noise=0.0025):
    """NIFTY and the cue series on a shared calendar. NIFTY's gap on Indian day D = rel * (S&P change of the US day before D) + same_day * (S&P change of the US day D itself: not known at the Indian open) + noise."""
    rnd = random.Random(seed)
    days = weekdays_back(LAST_US, n)
    spx_chg = [rnd.gauss(0, 0.009) for _ in days]
    spx = []
    px = 4500.0
    for c in spx_chg:
        px *= 1 + c
        spx.append(px)
    nclose, nopen = [], []
    prev = 20000.0
    for i, d in enumerate(days):
        prior = spx_chg[i - 1] if i > 0 else 0.0                         # the previous weekday's US session (the Friday before a Monday)
        gap = rel * prior + same_day * spx_chg[i] + rnd.gauss(0, noise)
        o = prev * (1 + gap)
        c = o * (1 + rnd.gauss(0, 0.006))
        nopen.append(o)
        nclose.append(c)
        prev = c
    world = {'^NSEI': rows_for(days, nclose, 3, 45, opens=nopen), '^GSPC': rows_for(days, spx, 13, 30)}
    for k, sym in enumerate(('^IXIC', 'DX-Y.NYB', '^VIX', 'CL=F', 'BZ=F', '^TNX', 'GC=F')):
        world[sym] = rows_for(days, walk(n, 100.0, 0.0, 0.01, seed=seed * 31 + k), 13, 30)
    return world


class TestCueModel(GlobeCase):
    def series(self, world, sym):
        return self.m._n93_clean([{'ts': r[0], 'o': r[1], 'h': r[2], 'l': r[3], 'c': r[4], 'v': r[5]} for r in world[sym]])

    def model(self, world):
        nifty = self.series(world, '^NSEI')
        fc = {s: self.series(world, s) for s, _l, _k in self.m._N101_CUE_FACTORS}
        data = self.m._n101_cue_data(nifty, fc)
        return data, self.m._n101_cue_model(data, self.m._n101_now_values(fc, NOW)[0])

    def test_alignment_pairs_each_indian_open_with_the_us_session_that_closed_before_it(self):
        w = cue_world(1, rel=0.5)
        nifty = self.series(w, '^NSEI')
        fc = {'^GSPC': self.series(w, '^GSPC')}
        data = self.m._n101_cue_data(nifty, fc)
        spx = {self.m._n101_date_of(c['ts'], 'America/New_York'): (c['c'] / p['c'] - 1) * 100 for p, c in zip(fc['^GSPC'], fc['^GSPC'][1:])}
        for i in (5, 100, 300):                                           # an ordinary Tuesday and a Monday: the Monday's cue is Friday's session
            d = data['dates'][i]
            want_day = d - dt.timedelta(days=1 if d.weekday() != 0 else 3)
            self.assertAlmostEqual(data['x']['^GSPC'][i], spx[want_day])
            self.assertLess(want_day, d)

    def test_a_real_relation_is_found_and_survives_the_out_of_sample_check(self):
        data, mod = self.model(cue_world(1, rel=0.5))
        self.assertEqual(mod['verdict'], 'usable')
        self.assertIn('^GSPC', mod['selected'])
        self.assertGreater(mod['r2_oos'], 0.10)
        self.assertGreater(mod['hit_oos'], 60)
        self.assertAlmostEqual(mod['uni']['^GSPC']['beta'], 0.5, delta=0.08)

    def test_no_relation_gives_no_usable_cue(self):
        for seed in (2, 3, 4):
            data, mod = self.model(cue_world(seed, rel=0.0))
            self.assertIn(mod['verdict'], ('none', 'weak'), seed)
            self.assertLess(mod.get('r2_oos') if mod.get('r2_oos') is not None else 0.0, 0.10, seed)

    def test_the_same_day_us_move_is_never_used_because_it_is_not_known_at_the_open(self):
        data, mod = self.model(cue_world(5, rel=0.0, same_day=0.6))               # the gap follows the US session that closes AFTER the Indian open
        self.assertIn(mod['verdict'], ('none', 'weak'))
        u = mod['uni'].get('^GSPC')
        self.assertTrue(u is None or abs(u['corr']) < 0.2)

    def test_a_factor_chosen_by_luck_in_the_first_part_is_not_trusted(self):
        w = cue_world(6, rel=0.0)
        data, mod = self.model(w)
        if mod.get('selected_train'):
            self.assertIn(mod['verdict'], ('none', 'weak'))

    def test_too_little_history_says_so(self):
        w = cue_world(7, rel=0.5, n=80)
        data, mod = self.model(w)
        self.assertEqual(mod['verdict'], 'too little data')
        self.assertIsNone(mod['estimate'])

    def test_the_estimate_comes_with_a_range_and_the_wording_is_modest(self):
        w = cue_world(1, rel=0.5)
        nifty = self.series(w, '^NSEI')
        fc = {s: self.series(w, s) for s, _l, _k in self.m._N101_CUE_FACTORS}
        data = self.m._n101_cue_data(nifty, fc)
        vals, live = self.m._n101_now_values(fc, NOW)
        mod = self.m._n101_cue_model(data, vals)
        self.assertIsNotNone(mod['estimate'])
        est, lo, hi = mod['estimate']
        self.assertLess(lo, est)
        self.assertLess(est, hi)
        text = self.m._n101_cues_text(mod, vals, live, [], [], NOW)
        self.assertIn('not a forecast', text)
        self.assertIn('Out of sample', text)
        self.assertIn('GIFT Nifty', text)
        self.assertNotIn('guarantee', text.lower())

    def test_a_none_verdict_tells_the_owner_not_to_use_it(self):
        data, mod = self.model(cue_world(2, rel=0.0))
        text = self.m._n101_cues_text(mod, {}, {}, [], [], NOW)
        if mod['verdict'] == 'none':
            self.assertIn('Do not use them for a forecast', text)

    def test_while_the_us_session_is_open_the_numbers_are_marked_as_still_moving(self):
        us_open = utc_ts(2026, 10, 2, 15, 0)
        w = cue_world(1, rel=0.5)
        fc = {s: self.series(w, s) for s, _l, _k in self.m._N101_CUE_FACTORS}
        vals, live = self.m._n101_now_values(fc, us_open)
        self.assertTrue(live['^GSPC'])
        vals2, live2 = self.m._n101_now_values(fc, NOW)
        self.assertFalse(any(live2.values()))

    def test_the_us_close_time_follows_daylight_saving_and_early_closes(self):
        f = self.m._n101_us_close_ts
        self.assertEqual(dt.datetime.fromtimestamp(f(utc_ts(2026, 10, 2, 15)), IST).strftime('%H:%M'), '01:30')
        self.assertEqual(dt.datetime.fromtimestamp(f(utc_ts(2026, 12, 2, 15)), IST).strftime('%H:%M'), '02:30')
        self.assertEqual(dt.datetime.fromtimestamp(f(utc_ts(2026, 11, 27, 15)), IST).strftime('%H:%M'), '23:30')


class TestCorrelation(GlobeCase):
    def test_matrix_known_answers_and_n_a_for_thin_overlap(self):
        n = 150
        days = weekdays_back(LAST_US, n)
        rnd = random.Random(9)
        base_ret = [rnd.gauss(0, 0.01) for _ in range(n)]

        def prices(rets, start=100.0):
            px, out = start, []
            for r in rets:
                px *= 1 + r
                out.append(px)
            return out
        a = self.m._n93_clean([{'ts': r[0], 'o': r[1], 'h': r[2], 'l': r[3], 'c': r[4], 'v': r[5]} for r in rows_for(days, prices(base_ret), 13, 30)])
        b = self.m._n93_clean([{'ts': r[0], 'o': r[1], 'h': r[2], 'l': r[3], 'c': r[4], 'v': r[5]} for r in rows_for(days, prices([-r for r in base_ret]), 13, 30)])
        c = self.m._n93_clean([{'ts': r[0], 'o': r[1], 'h': r[2], 'l': r[3], 'c': r[4], 'v': r[5]} for r in rows_for(days[-40:], prices(base_ret[-40:]), 13, 30)])
        names, M, C = self.m._n101_corr_matrix({'A': a, 'B': b, 'C': c}, {})
        i = {n: k for k, n in enumerate(names)}
        self.assertAlmostEqual(M[i['A']][i['A']], 1.0)
        self.assertAlmostEqual(M[i['A']][i['B']], -1.0, places=6)
        self.assertEqual(M[i['A']][i['B']], M[i['B']][i['A']])
        self.assertIsNone(M[i['A']][i['C']])                                     # only 40 common days: not enough to print a number
        self.assertEqual(C[i['A']][i['C']], 39)


# ===================================================================================================================
# 5. THE CHARTS
# ===================================================================================================================
class TestCharts(GlobeCase):
    def board(self):
        return self.m._n101_board(NOW)

    def candles(self, sym='^NSEI', n=300):
        return self.m._n93_clean([{'ts': r[0], 'o': r[1], 'h': r[2], 'l': r[3], 'c': r[4], 'v': r[5]} for r in self.world[sym][-n:]])

    def option_rec(self, structure='CREDIT'):
        spot = 24450.0
        if structure == 'CREDIT':
            plan = {'name': 'Bull put spread', 'structure': 'CREDIT', 'legs': [{'action': 'SELL', 'type': 'PE', 'strike': 24300, 'px': 118.0}, {'action': 'BUY', 'type': 'PE', 'strike': 24200, 'px': 74.5}],
                    'credit': 43.5, 'max_loss': 56.5, 'max_profit': 43.5, 'breakevens': [24256.5], 'pop': 0.71, 'ev_lot': -310.0, 'cost_lot': 780.0, 'unlimited': False}
        else:
            plan = {'name': 'Long call', 'structure': 'LONG', 'legs': [{'action': 'BUY', 'type': 'CE', 'strike': 24500, 'px': 150.0}], 'premium': 150.0, 'max_profit': None, 'unlimited': True, 'max_loss': 150.0,
                    'breakevens': [24650.0], 'pop': 0.34, 'ev_lot': -450.0, 'cost_lot': 520.0}
        return {'id': 'SG100-0A0B0C', 'kind': 'option', 'symbol': 'NIFTY', 'side': 1, 'label': plan['name'], 'strategy': 'OPT_' + structure, 'score': 68, 'plan': plan, 'lot': 65, 'ref': spot, 'stop': 24300.0, 't1': None,
                't2': None, 'stats': {'spot': spot, 'em': 330.0, 'atm_iv': 14.2, 'forward': spot * 1.002}, 'days': 4.5, 'expiry': '13 Oct 2026'}

    def check(self, png, w=1100, min_h=300):
        self.assertIsNotNone(png)
        ww, hh = png_size(png)
        self.assertEqual(ww, w)
        self.assertGreaterEqual(hh, min_h)
        self.assertLess(len(png), 2_000_000)
        return hh

    def test_the_world_map(self):
        png = self.m._n101_chart_map(self.board(), NOW)
        self.check(png, min_h=800)

    def test_the_map_with_unreadable_rows_and_nothing_at_all(self):
        self.fetch_fail = {'^MXX', '^GSPTSE', 'ETH-USD'}
        self.check(self.m._n101_chart_map(self.m._n101_board(NOW), NOW), min_h=800)
        self.assertIsNone(self.m._n101_chart_map({'rows': [], 'failed': [], 'asof': NOW}, NOW))

    def test_market_hours(self):
        self.check(self.m._n101_chart_hours(NOW), min_h=600)
        self.check(self.m._n101_chart_hours(utc_ts(2026, 12, 25, 6)), min_h=600)       # Christmas: holidays are drawn as words
        self.check(self.m._n101_chart_hours(utc_ts(2026, 10, 3, 6)), min_h=600)        # a Saturday

    def test_one_instrument_and_a_comparison(self):
        st = self.m._n101_row_stats(self.m._N101_BY_SYM['^GSPC'], self.candles('^GSPC', 260), NOW)
        self.check(self.m._n101_chart_line(st, self.candles('^GSPC', 260), 252, NOW), min_h=500)
        self.check(self.m._n101_chart_compare([('S&P 500', self.candles('^GSPC')), ('Nifty', self.candles('^NSEI')), ('Gold', self.candles('GC=F'))], 180, NOW), min_h=500)
        self.assertIsNone(self.m._n101_chart_compare([('S&P 500', self.candles('^GSPC'))], 180, NOW))
        self.assertIsNone(self.m._n101_chart_line(st, self.candles('^GSPC', 10), 252, NOW))

    def test_rebase_starts_every_line_at_100(self):
        rb = self.m._n101_rebase([('A', self.candles('^GSPC')), ('B', self.candles('^NSEI'))], 100, NOW)
        self.assertEqual(len(rb), 2)
        for r in rb:
            self.assertAlmostEqual(r['pts'][0][1], 100.0)
            self.assertAlmostEqual(r['ret'], r['pts'][-1][1] - 100.0)

    def test_the_signal_chart_with_and_without_a_signal_and_with_volume(self):
        cs = self.candles('^NSEI', 300)
        self.check(self.m._n101_chart_signal('NIFTY', cs, None, 110, True, NOW), min_h=700)
        rec = {'id': 'SG100-AB12CD', 'kind': 'stock', 'symbol': 'TCS', 'side': 1, 'label': 'RSI-2 pullback', 'strategy': 'RSI2', 'score': 71, 'ref': cs[-1]['c'], 'stop': cs[-1]['c'] * 0.96, 't1': cs[-1]['c'] * 1.05, 't2': None}
        vol = [dict(c, v=1e6 * (1 + 0.4 * math.sin(i / 5.0))) for i, c in enumerate(cs)]
        flat = [dict(c, v=0.0) for c in cs]
        h = self.check(self.m._n101_chart_signal('TCS', vol, rec, 110, False, NOW), min_h=700)
        self.assertGreater(h, self.check(self.m._n101_chart_signal('TCS', flat, rec, 110, False, NOW), min_h=700))        # the volume panel adds height
        self.assertIsNone(self.m._n101_chart_signal('X', cs[:20], None, 110, False, NOW))

    def test_a_level_far_from_the_price_does_not_flatten_the_candles(self):
        cs = self.candles('^NSEI', 300)
        rec = {'id': 'SG100-AB12CD', 'kind': 'stock', 'symbol': 'TCS', 'side': 1, 'label': 'x', 'strategy': 'RSI2', 'score': 71, 'ref': cs[-1]['c'] * 8, 'stop': cs[-1]['c'] * 7, 't1': cs[-1]['c'] * 9}
        self.assertEqual(self.m._n101_rec_levels(rec)[0][0], 'ENTRY')
        self.check(self.m._n101_chart_signal('X', cs, rec, 110, False, NOW), min_h=700)

    def test_payoff_diagrams(self):
        self.check(self.m._n101_chart_payoff(self.option_rec('CREDIT')), min_h=650)
        self.check(self.m._n101_chart_payoff(self.option_rec('LONG')), min_h=650)

    def test_the_scoreboard_curve_needs_three_results(self):
        rows = [(NOW - (20 - i) * 86400, r, 'RSI2', 'target' if r > 0 else 'stopped') for i, r in enumerate([1.4, -1.0, 2.0, -1.0, 0.5, -1.0, 1.2, 2.0, -1.0, 0.3])]
        self.check(self.m._n101_chart_equity(rows), min_h=650)
        self.assertIsNone(self.m._n101_chart_equity(rows[:2]))
        self.check(self.m._n101_chart_equity(rows * 6), min_h=650)                      # many signals: no value labels, still draws

    def test_the_cue_chart_and_the_correlation_grid(self):
        w = cue_world(1, rel=0.5)
        nifty = self.m._n93_clean([{'ts': r[0], 'o': r[1], 'h': r[2], 'l': r[3], 'c': r[4], 'v': r[5]} for r in w['^NSEI']])
        fc = {s: self.m._n93_clean([{'ts': r[0], 'o': r[1], 'h': r[2], 'l': r[3], 'c': r[4], 'v': r[5]} for r in w[s]]) for s, _l, _k in self.m._N101_CUE_FACTORS}
        data = self.m._n101_cue_data(nifty, fc)
        vals, _live = self.m._n101_now_values(fc, NOW)
        mod = self.m._n101_cue_model(data, vals)
        self.check(self.m._n101_chart_cues(data, mod, vals), min_h=600)
        self.assertIsNone(self.m._n101_chart_cues(data, {'uni': {}}, vals))
        series = {s: self.m._n93_clean([{'ts': r[0], 'o': r[1], 'h': r[2], 'l': r[3], 'c': r[4], 'v': r[5]} for r in self.world[s]]) for s, _l, _t in self.m._N101_CORR_SET}
        names, M, C = self.m._n101_corr_matrix(series, {s: t for s, _l, t in self.m._N101_CORR_SET})
        self.check(self.m._n101_chart_corr(names, M, C, {s: l for s, l, _t in self.m._N101_CORR_SET}), min_h=900)

    def test_the_colour_choice_changes_the_picture_and_the_set_is_the_validated_one(self):
        b = self.board()
        safe = self.m._n101_chart_map(b, NOW)
        self.m._n101_put('colours', 'classic')
        classic = self.m._n101_chart_map(b, NOW)
        self.assertNotEqual(safe, classic)
        self.assertEqual(self.m._n101_scheme()['up'], self.m._N101_C['green'])
        self.m._n101_put('colours', 'nonsense')
        self.assertEqual(self.m._n101_scheme()['up'], self.m._N101_C['blue'])           # an unknown value falls back to the safe pair
        self.assertEqual([self.m._N101_C[k] for k in self.m._N101_SERIES[:8]],
                         [(42, 120, 214), (235, 104, 52), (27, 175, 122), (237, 161, 0), (232, 123, 164), (0, 131, 0), (74, 58, 167), (227, 73, 72)])

    def test_text_never_wears_a_series_colour_and_contrast_is_chosen(self):
        for col in ((42, 120, 214), (235, 104, 52), (240, 239, 236), (0, 131, 0), (227, 73, 72)):
            ink = self.m._n101_ink_on(col)
            lum = self.m._n101_lum
            hi, lo = max(lum(col), lum(ink)), min(lum(col), lum(ink))
            self.assertGreaterEqual((hi + 0.05) / (lo + 0.05), 4.0, col)
        src = globe_source()
        self.assertNotRegex(src, r"cv\.text\([^\n]*(?:sch\['up'\]|sch\['down'\]|_N101_C\['blue'\]|_N101_C\['orange'\])\s*[,)]\s*(?:bold|align|valign|maxw)")

    def test_a_chart_that_cannot_be_drawn_is_counted_not_raised(self):
        def boom(*a, **k):
            raise RuntimeError('x')
        self.assertIsNone(self.m._n101_png(boom))
        self.assertEqual(self.m._N101_STATS['chart_failed'], 1)
        with mock.patch.object(self.m, '_n90_pil', lambda: None):
            self.assertIsNone(self.m._n101_png(self.m._n101_chart_hours, NOW))

    def test_every_chart_has_a_text_twin_command(self):
        for name in ('map', 'hours', 'line', 'compare', 'signal', 'payoff', 'equity', 'cues', 'corr'):
            self.assertIn(name, ('map', 'hours', 'line', 'compare', 'signal', 'payoff', 'equity', 'cues', 'corr'))
        src = globe_source()
        for job in ('_n101_board_job', '_n101_hours_job', '_n101_instrument_job', '_n101_compare_job', '_n101_sigma_chart_job', '_n101_sigma_payoff_job', '_n101_sigma_equity_job', '_n101_cues_job', '_n101_corr_job'):
            self.assertIn('def %s(' % job, src)
        self.assertIn('_n91_say(cid, text)', src)


# ===================================================================================================================
# 6. THE OWNER'S COMMANDS
# ===================================================================================================================
class TestOwnerCommands(GlobeCase):
    def test_world_markets_gives_the_board_and_the_picture(self):
        out = self.say('world markets')
        self.drain()
        out = self.sent_since(0)
        self.assertIn('WORLD BOARD', out)
        self.assertEqual(len(self.pngs()), 1)
        self.assertEqual(self.images[0]['name'], 'world-board.png')
        self.assertEqual(self.images[0]['cid'], OWNER_ID)

    def test_the_phrases_that_open_the_board(self):
        for phrase in ('globe', '/globe', 'Globe board', 'world markets', 'global markets', 'how are the global markets doing', 'the world market today'):
            self.images.clear()
            n0 = len(self.sent)
            self.m.handle(self.msg(phrase))
            self.assertIn('WORLD BOARD', self.sent_since(n0), phrase)

    def test_the_map_alone(self):
        n0 = len(self.sent)
        self.m.handle(self.msg('globe map'))
        self.assertEqual(len(self.pngs()), 1)
        self.assertNotIn('WORLD BOARD', self.sent_since(n0))                         # the picture is the answer; its caption points at the words

    def test_charts_off_gives_words_only_and_the_map_still_draws_on_request(self):
        self.m.handle(self.msg('globe charts off'))
        n0 = len(self.sent)
        self.m.handle(self.msg('world markets'))
        self.assertIn('WORLD BOARD', self.sent_since(n0))
        self.assertEqual(self.pngs(), [])
        self.m.handle(self.msg('globe map'))
        self.assertEqual(len(self.pngs()), 1)
        self.m.handle(self.msg('globe charts on'))
        self.assertTrue(self.m._n101_charts_on())

    def test_the_failure_of_the_feed_is_said_not_hidden(self):
        self.world.clear()
        n0 = len(self.sent)
        self.m.handle(self.msg('world markets'))
        out = self.sent_since(n0)
        self.assertIn('could not read any market', out)
        self.assertEqual(self.pngs(), [])

    def test_global_cues_job_sends_words_then_the_chart(self):
        self.world = cue_world(1, rel=0.5)
        n0 = len(self.sent)
        self.m.handle(self.msg('global cues'))
        out = self.sent_since(n0)
        self.assertIn('OVERNIGHT CUES FOR INDIA', out)
        self.assertIn('Out of sample', out)
        self.assertEqual(self.images[-1]['name'], 'india-cues.png')

    def test_cues_with_too_little_nifty_history_refuse_to_guess(self):
        self.world = cue_world(1, rel=0.5, n=100)
        n0 = len(self.sent)
        self.m.handle(self.msg('how will nifty open'))
        out = self.sent_since(n0)
        self.assertIn('will not guess', out)
        self.assertEqual(self.pngs(), [])

    def test_market_hours_words_and_picture(self):
        n0 = len(self.sent)
        self.m.handle(self.msg('market hours'))
        out = self.sent_since(n0)
        self.assertIn('MARKET HOURS', out)
        self.assertIn('NYSE / Nasdaq (US)', out)
        self.assertIn('NSE / BSE (India)', out)
        self.assertEqual(self.images[-1]['name'], 'market-hours.png')

    def test_is_tokyo_open_and_the_other_exchange_questions(self):
        out = self.say('is Tokyo open')
        self.assertIn('Tokyo Stock Exchange: open', out)
        self.assertIn('05:30-08:00 and 09:00-12:00 IST', out)
        self.assertIn('not yet open', self.say('is the US market open') + self.say('is wall street open'))
        self.assertIn('Tokyo', self.say('when does the Tokyo market open'))
        self.assertEqual(self.passed, [])

    def test_the_indian_exchanges_are_left_to_the_older_layers_so_there_is_one_answer(self):
        self.assertIsNone(self.m._n101_exchange('NSE'))
        self.assertIsNone(self.m._n101_exchange('the indian market'))
        n0 = len(self.passed)
        self.m.handle(self.msg('is the nse open'))
        self.assertEqual(len(self.passed), n0 + 1)

    def test_instrument_chart_and_country_card(self):
        n0 = len(self.sent)
        self.m.handle(self.msg('globe brent'))
        out = self.sent_since(n0)
        self.assertIn('Brent crude', out)
        self.assertRegex(out, r'1d [+-]?\d')
        self.assertIn('globe-brent-crude.png', [i['name'] for i in self.images])
        n0 = len(self.sent)
        self.m.handle(self.msg('globe japan'))
        out = self.sent_since(n0)
        self.assertIn('JAPAN', out)
        self.assertIn('Bank of Japan', out)
        self.assertIn('Tokyo Stock Exchange', out)
        self.assertIn('Nikkei 225', out)

    def test_an_unknown_name_gets_a_list_of_what_works(self):
        out = self.say('globe wheat')
        self.assertIn('I do not know “wheat”', out)
        self.assertIn('brent', out)

    def test_compare_parses_names_periods_and_unknowns(self):
        rows, days, unknown = self.m._n101_parse_compare('nifty nasdaq and gold 6m')
        self.assertEqual([r[0] for r in rows], ['^NSEI', '^IXIC', 'GC=F'])
        self.assertEqual(days, 180)
        rows, days, unknown = self.m._n101_parse_compare('hang seng vs dow jones 90 days wheat')
        self.assertEqual([r[0] for r in rows], ['^HSI', '^DJI'])
        self.assertEqual((days, unknown), (90, ['wheat']))
        self.assertEqual(self.m._n101_parse_compare('nifty 3y')[1], 365)                        # capped at the data we hold
        self.assertEqual(self.m._n101_parse_compare('natural gas silver')[0][0][0], 'NG=F')

    def test_compare_words_then_picture(self):
        n0 = len(self.sent)
        self.m.handle(self.msg('globe compare nifty nasdaq gold 6m'))
        out = self.sent_since(n0)
        self.assertIn('COMPARED OVER 180 DAYS', out)
        self.assertIn('NIFTY 50', out)
        self.assertEqual(self.images[-1]['name'], 'globe-compare.png')
        self.assertIn('at least two', self.say('globe compare nifty'))

    def test_correlation_words_then_picture(self):
        n0 = len(self.sent)
        self.m.handle(self.msg('globe correlation'))
        out = self.sent_since(n0)
        self.assertIn('HOW THE WORLD MOVES TOGETHER', out)
        self.assertIn('same date', out.lower())
        self.assertEqual(self.images[-1]['name'], 'globe-correlation.png')

    def test_world_news_uses_the_scout_fetcher_and_no_ai(self):
        xml = ('<rss><channel>' + ''.join('<item><title>Wall Street ends higher as tech rallies %d - Reuters</title><link>http://x/%d</link><pubDate>Mon, 05 Oct 2026 04:%02d:00 GMT</pubDate></item>' % (i, i, 10 + i) for i in range(3))
               + '<item><title>Oil slips as dollar firms on Fed bets - Bloomberg</title><link>http://x/9</link><pubDate>Mon, 05 Oct 2026 03:00:00 GMT</pubDate></item></channel></rss>')
        self.pages['global+stock+markets'] = xml
        out = self.say('globe news')
        self.assertIn('WORLD MARKET HEADLINES', out)
        self.assertIn('Oil slips', out)
        self.assertIn('headlines only', out)
        self.assertEqual(self.ai_calls, [])

    def test_world_news_with_no_feed_says_so(self):
        out = self.say('globe news')
        self.assertIn('could not read world market headlines', out)

    def test_events_commands(self):
        out = self.say('world calendar')
        self.assertIn('WORLD CALENDAR', out)
        self.assertIn('Fed decision', self.say('globe events 60 days'))
        out = self.say('globe event add 2026-10-08 RBI policy decision')
        self.assertRegex(out, r'Saved EV-[0-9A-F]{5}: RBI policy decision on Thu 08 Oct 2026 \(high impact\)')
        eid = re.search(r'EV-[0-9A-F]{5}', out).group(0)
        self.assertIn(eid, self.say('globe events'))
        self.assertIn('Removed %s' % eid, self.say('globe event remove %s' % eid))
        self.assertIn('I have no event', self.say('globe event remove %s' % eid))
        self.assertIn('not a date I can read', self.say('globe event add 2026-99-99 something big'))
        self.assertIn('Only high-impact', self.say('globe event add 2026-10-09 small thing impact low'))

    def test_colours_command(self):
        self.assertIn('blue and falling is orange', self.say('globe colours safe'))
        self.assertEqual(self.m._n101_get('colours'), 'safe')
        self.assertIn('green and falling is red', self.say('globe colors classic'))
        self.assertEqual(self.m._n101_get('colours'), 'classic')

    def test_help_lists_the_commands_and_counts(self):
        self.m._N101_STATS['boards'] = 3
        out = self.say('globe help')
        self.assertIn('3 boards', out)
        for w in ('world markets', 'global cues', 'market hours', 'globe compare', 'sigma chart', 'globe event add'):
            self.assertIn(w, out)

    def test_the_phrases_are_for_the_owner_only(self):
        n0 = len(self.sent)
        self.m.handle(self.msg_from(5552, 'world markets'))
        self.m.handle(self.msg_from(5552, 'globe event add 2026-10-08 fake event'))
        self.assertEqual(self.sent_since(n0, 5552), '')
        self.assertEqual(self.m._n101_q('SELECT COUNT(*) FROM globe101_event')[0][0], 0)
        self.assertEqual(self.pngs(), [])
        self.assertEqual(len(self.passed), 2)                                        # handed on, where Circle's gate decides (default deny)

    def test_a_group_message_from_the_owner_is_not_taken(self):
        msg = self.msg('world markets')
        msg['chat'] = {'id': -100123, 'type': 'supergroup'}
        self.m.handle(msg)
        self.assertEqual(self.pngs(), [])
        self.assertEqual(len(self.passed), 1)

    def test_older_phrases_are_not_stolen(self):
        for phrase in ('market brief', 'sigma', 'sigma nifty', 'sigma market', 'scout nifty', 'what is the market status', 'is the market open', 'how is my portfolio', 'markets'):
            n0 = len(self.passed)
            self.m.handle(self.msg(phrase))
            self.assertEqual(len(self.passed), n0 + 1, phrase)

    def test_the_command_and_the_menu_button_exist(self):
        self.assertIn('globe', [c for c, _d in self.m._N40_COMMANDS])
        rows = self.m._N40_MENUS['main'][1]
        self.assertTrue(any(b[1] == 'c:/globe' for r in rows for b in r))


# ===================================================================================================================
# 7. SIGMA: pictures, the event guard, the cosmetic fixes
# ===================================================================================================================
class TestSigmaPolish(GlobeCase):
    def test_no_minus_zero_and_proper_ordinals_and_articles(self):
        src = globe_source()
        full = open(base.NEMO_FILE, encoding='utf-8').read()
        sig = full[full.index('# NEMO 100 - SIGMA'):full.index('# NEMO 101 - GLOBE')]
        self.assertNotRegex(sig, r'%\.0fth')
        self.assertNotIn("'a %s trend", sig)
        self.assertNotRegex(sig, r"%\+\.1f in 5 days")
        self.assertEqual(self.m._n100_stance('TREND_UP', 40, None, True)[:13], 'an up trend w')
        self.assertTrue(self.m._n100_stance('STRONG_TREND_DOWN', 40, None, True).startswith('a down trend'))
        self.assertIn('an up trend but options are dear', self.m._n100_stance('TREND_UP', 80, None, True))

    def test_the_brief_prints_ordinals_and_never_minus_zero(self):
        self.put_market()
        vc = self.md[('INDIAVIX', '1d')]
        self.assertTrue(vc)
        out = self.m._n101_ord(51.3) + ' ' + self.m._n101_sgn(-0.02, 1)
        self.assertEqual(out, '51st 0.0')

    def test_a_signal_card_is_followed_by_its_chart_and_never_changes(self):
        cs = candles(trend(300, start=3000.0, vol=0.01, drift=0.0004), vols=[1e6] * 300)
        self.daily['TCS'] = cs
        rec = {'kind': 'stock', 'symbol': 'TCS', 'strategy': 'RSI2', 'label': 'RSI-2 pullback', 'side': 1, 'score': 72, 'band': 'B', 'ref': cs[-1]['c'], 'stop': cs[-1]['c'] * 0.96, 't1': None, 't2': None, 'risk': cs[-1]['c'] * 0.04,
               'atr': 40.0, 'horizon': 8, 'trigger': 't', 'good': [], 'bad': [], 'unchecked': [], 'cost_pct': 0.2, 'cost_r': 0.1, 'wrong_if': ['w'], 'size': None, 'last_day': '2026-10-01', 'rule': 'sma5', 'trail_mult': None}
        card = []
        with mock.patch.object(self.m, '_n100_card', lambda r, cfg, sid=None: 'CARD ' + str(sid)):
            self.m._n100_issue(OWNER_ID, [rec], self.cfg, NOW, quiet=True)
        self.assertEqual(len(self.pngs()), 1)
        self.assertRegex(self.images[0]['name'], r'sigma-sg100-[0-9a-f]{6}\.png')
        self.assertIn('TCS', self.images[0]['caption'])

    def test_charts_off_means_no_picture_under_the_card(self):
        self.m._n101_put('charts', 'off')
        cs = candles(trend(300, start=3000.0), vols=[1e6] * 300)
        self.daily['TCS'] = cs
        self.m._n101_card_extras(OWNER_ID, {'kind': 'stock', 'symbol': 'TCS', 'ref': cs[-1]['c'], 'stop': cs[-1]['c'] * 0.96, 'side': 1, 'strategy': 'RSI2', 'label': 'x', 'score': 70}, 'SG100-AAAAAA')
        self.assertEqual(self.images, [])

    def test_the_sink_chat_never_gets_a_picture(self):
        cs = candles(trend(300, start=3000.0))
        self.daily['TCS'] = cs
        self.m._n101_card_extras(self.m._N97_SINK, {'kind': 'stock', 'symbol': 'TCS', 'ref': 1.0, 'stop': 1.0, 'side': 1, 'strategy': 'RSI2', 'label': 'x', 'score': 70}, 'SG100-AAAAAA')
        self.assertEqual(self.images, [])

    def option_inputs(self):
        return None

    def test_a_high_impact_event_stops_the_sale_of_premium_but_only_adds_a_note_to_a_bought_option(self):
        m = self.m
        credit = {'ok': True, 'symbol': 'NIFTY', 'kind': 'option', 'plan': {'structure': 'CREDIT'}, 'bias': {'bias': 0.4}, 'notes': []}
        long_ = {'ok': True, 'symbol': 'NIFTY', 'kind': 'option', 'plan': {'structure': 'LONG'}, 'bias': {'bias': 0.4}, 'notes': []}
        for res in (credit, long_):
            pass
        calls = iter([dict(credit), dict(long_), dict(credit)])
        with mock.patch.object(m, '_N101_OPT_PREV', lambda *a, **k: next(calls)):
            m._n101_event_add('2026-10-06', 'RBI policy decision', 'high')
            r1 = m._n100_option_signal('NIFTY', None, 'RANGE', {}, self.cfg, {}, {}, None, [], {}, NOW)
            self.assertFalse(r1['ok'])
            self.assertIn('does not sell premium', r1['veto'])
            self.assertIn('RBI policy decision', r1['veto'])
            r2 = m._n100_option_signal('NIFTY', None, 'RANGE', {}, self.cfg, {}, {}, None, [], {}, NOW)
            self.assertTrue(r2['ok'])
            self.assertTrue(any('high-impact event' in n for n in r2['notes']))
            self.assertEqual(m._N101_STATS['event_vetoes'], 1)
        # no event: untouched
        m._n101_event_remove(m._n101_events(dt.date(2026, 10, 6), dt.date(2026, 10, 6))[-1]['id'])
        with mock.patch.object(m, '_N101_OPT_PREV', lambda *a, **k: dict(credit)):
            self.assertTrue(m._n100_option_signal('NIFTY', None, 'RANGE', {}, self.cfg, {}, {}, None, [], {}, ist_ts(2026, 10, 14)).get('ok'))

    def test_a_card_notes_the_event(self):
        self.m._n101_event_add('2026-10-06', 'RBI policy decision', 'high')
        self.m._n101_put('charts', 'off')
        self.m._n101_card_extras(OWNER_ID, {'kind': 'stock', 'symbol': 'TCS', 'ref': 1.0, 'stop': 1.0, 'side': 1, 'strategy': 'RSI2', 'label': 'x', 'score': 70}, 'SG100-AAAAAA')
        out = self.sent_since(0)
        self.assertIn('Event risk: RBI policy decision (tomorrow)', out)
        self.assertIn('does not sell premium', out)

    def test_sigma_chart_commands(self):
        self.daily['NIFTY'] = candles(trend(300, start=23000.0, vol=0.004, drift=0.0004), wick=0.0008)
        self.daily['TCS'] = candles(trend(300, start=3000.0), vols=[1e6] * 300)
        self.m.handle(self.msg('sigma chart NIFTY'))
        self.assertEqual(self.images[-1]['name'], 'sigma-chart-nifty.png')
        self.m.handle(self.msg('sigma chart TCS'))
        self.assertEqual(self.images[-1]['name'], 'sigma-chart-tcs.png')
        out = self.say('sigma chart ZZZZ')
        self.assertIn('I do not know “ZZZZ”', out)
        out = self.say('sigma chart SG100-ABCDEF')
        self.assertIn('I do not have a signal called SG100-ABCDEF', out)
        self.assertEqual(self.passed, [])

    def test_sigma_equity_needs_settled_signals_and_then_draws(self):
        out = self.say('sigma equity')
        self.assertIn('A curve needs at least 3 settled signals', out)
        for i, r in enumerate([1.2, -1.0, 2.0, 0.4]):
            sid = 'SG100-%06X' % (i + 1)
            self.m._n100_q('INSERT INTO sig100_signal VALUES(%s)' % ','.join('?' * 21), (sid, NOW - 1000 * i, '2026-10-01', 'TCS', 'stock', 'RSI2', 1, 'B', 70.0, 'target' if r > 0 else 'stopped', 100.0, 96.0, None, None, 4.0,
                                                                                     NOW + 1000, NOW - 500 * i, r, '', 'k%d' % i, '{}'), write=True)
        self.m.handle(self.msg('sigma equity'))
        self.assertEqual(self.images[-1]['name'], 'sigma-scoreboard.png')

    def test_sigma_payoff_without_a_saved_option_signal_explains(self):
        out = self.say('sigma payoff')
        self.assertIn('no saved option signal', out.lower().replace('there is no', 'no'))

    def test_sigma_payoff_draws_a_saved_option_signal(self):
        rec = dict(TestCharts.option_rec(self, 'CREDIT'))
        rec.update(side=1, status='open', score=68, band='B', bar_ts=NOW, risk=56.5, regime='RANGE')
        sid = self.m._n100_save(rec, NOW)
        self.assertIsNotNone(sid)
        self.m.handle(self.msg('sigma payoff'))
        self.assertTrue(self.images[-1]['name'].startswith('sigma-payoff-sg100-'))
        self.m.handle(self.msg('sigma payoff %s' % sid))
        self.assertEqual(len(self.pngs()), 2)


# ===================================================================================================================
# 8. THE FAMILY
# ===================================================================================================================
class FamilyCase(GlobeCase):
    def setUp(self):
        super().setUp()
        self.m._N89_DOWNLOAD_SLOT = threading.BoundedSemaphore(1)
        self.popen_calls = []                           # only the downloads (the engine also probes for helper programs through the same module)

        def popen(cmd, **kw):
            if any(('youtu' in str(x) or 'ytsearch1' in str(x)) for x in cmd):
                self.popen_calls.append(cmd)
            raise OSError('no downloader in this test')
        self.start(self.m._n41_sp, 'Popen', popen)
        self.start(self.m, '_imp', lambda *a, **k: True)
        self.start(self.m, '_n41_cache_get', lambda key: None)

    def allow(self, uid, ability, value=True):
        self.m._n89_rule_set('uid:%s' % uid, ability, value)


class TestFamilyDownloads(FamilyCase):
    BOSS = 'Only the Boss can download media'

    def test_the_screenshot_a_family_member_with_downloads_on_is_no_longer_refused_by_the_engine(self):
        self.family(5552)
        self.allow(5552, 'downloads', True)
        out = self.other('Download this video https://youtu.be/MFQFxsDWbA8?si=cbCkKuYjrCSmVb3P')
        self.assertIn('On it', out)
        self.assertNotIn(self.BOSS, out)
        self.assertEqual(len(self.popen_calls), 1)                                  # the real engine ran: it reached the downloader program (the stub makes that program fail, which is not a refusal)

    def test_a_song_name_works_too(self):
        self.family(5552)
        self.allow(5552, 'downloads', True)
        out = self.other('download tum hi ho song')
        self.assertNotIn(self.BOSS, out)
        self.assertEqual(len(self.popen_calls), 1)
        self.assertIn('ytsearch1:tum hi ho', ' '.join(self.popen_calls[0]))

    def test_play_and_send_me_become_download_requests(self):
        self.family(5552)
        self.allow(5552, 'downloads', True)
        for phrase in ('play tum hi ho song', 'send me kesariya song', 'please send me the dhoom machale video'):
            self.popen_calls.clear()
            out = self.other(phrase)
            self.assertIn('On it', out, phrase)
            self.assertEqual(len(self.popen_calls), 1, phrase)

    def test_play_with_downloads_off_is_refused_by_circle_with_the_owner_ask(self):
        self.family(5552)
        n0 = len(self.sent)
        out = self.other('play tum hi ho song')
        self.assertNotIn('On it', out)
        self.assertEqual(self.popen_calls, [])
        self.assertIn('Gautam', self.sent_since(n0, OWNER_ID) + out)

    def test_the_engine_still_refuses_anyone_the_owner_has_not_allowed(self):
        m = self.m
        self.family(5552)
        n0 = len(self.sent)
        m._n41_download(5552, 'https://youtu.be/x', 'video', False)
        self.assertIn(self.BOSS, self.sent_since(n0, 5552))
        self.assertEqual(self.popen_calls, [])
        for who in (7777, None, m._N97_SINK):
            n0 = len(self.sent)
            m._n41_download(who, 'https://youtu.be/x', 'video', False)
            self.assertEqual(self.popen_calls, [])
        self.assertFalse(m._n101_may_download(None))
        self.assertFalse(m._n101_may_download(True))
        self.assertFalse(m._n101_may_download(m._N97_SINK))

    def test_a_blocked_person_cannot_download_even_with_a_personal_switch(self):
        m = self.m
        self.family(5552)
        self.allow(5552, 'downloads', True)
        m.BLOCKED.append(5552)
        self.assertFalse(m._n101_may_download(5552))
        n0 = len(self.sent)
        m._n41_download(5552, 'https://youtu.be/x', 'video', False)
        self.assertEqual(self.popen_calls, [])

    def test_the_owner_is_unchanged(self):
        n0 = len(self.sent)
        self.m._n41_download(OWNER_ID, 'https://youtu.be/x', 'video', False)
        self.assertEqual(len(self.popen_calls), 1)
        self.assertNotIn(self.BOSS, self.sent_since(n0))

    def test_a_family_member_is_not_given_the_owners_cookie_steps_or_server_paths(self):
        m = self.m
        self.assertIn('/browsercookies', m._n101_download_tip(OWNER_ID, '\nexport cookies.txt and send /browsercookies.', '\nneeds a login'))
        self.assertNotIn('/browsercookies', m._n101_download_tip(5552, '\nexport cookies.txt and send /browsercookies.', '\nneeds a login'))
        src = open(base.NEMO_FILE, encoding='utf-8').read()
        self.assertIn("_n101_download_tip(cid,'", src)
        self.assertIn("if cid==OWNER.get('id') else ' Try a shorter video or audio only.'", src)


class TestFamilyEverything(FamilyCase):
    def test_the_phrases(self):
        rx = self.m._N101_RX_FAM_ALL
        for p in ('family everything', 'give family everything', 'give my family everything', 'allow the whole family everything', 'give my family full access', 'family full access', 'full access for my family',
                  'Family everything please'.replace(' please', ''), 'let my family members everything'):
            self.assertTrue(rx.match(p), p)
        for p in ('family', 'everything', 'family list', 'give me everything', 'give Asha everything', 'family everything except email'):
            self.assertFalse(rx.match(p), p)
        for p in ('family everyday only', 'family basics', 'restrict my family', 'family restrict'):
            self.assertTrue(self.m._N101_RX_FAM_BASIC.match(p), p)

    def test_before_the_phrase_a_family_member_cannot_make_pictures_pdfs_or_downloads(self):
        self.family(5552)
        out = self.other('draw a cat riding a bicycle')
        self.assertNotIn('Creating your picture', out)
        self.assertEqual([a for a, (v, s) in self.m._n89_effective('5552').items() if v], ['chat', 'reminders', 'family_list', 'tell_owner', 'web', 'files'])

    def test_family_everything_switches_on_every_ability_the_desk_and_the_world(self):
        m = self.m
        self.family(5552)
        self.family(5553, 'Ravi')
        out = self.say('family everything')
        eff = m._n89_effective('5552')
        self.assertTrue(all(v for v, s in eff.values()), eff)
        self.assertTrue(all(v for v, s in m._n89_effective('5553').values()))
        self.assertTrue(m._n97_access('5552', 'family'))
        self.assertEqual(m._n101_get('family_world'), 'on')
        self.assertIn('Done. Every family member now has everything I can safely give them (2 people today)', out)
        for ability in m._N89_ORDER:
            self.assertIn(m._n89_short(ability), out)
        self.assertIn('Still locked for everyone', out)
        self.assertIn('your email', out)
        self.assertIn('family everyday only', out)
        self.assertEqual(m._N101_STATS['family_everything'], 1)

    def test_the_locked_tier_stays_locked_whatever_the_switch_says(self):
        m = self.m
        self.family(5552)
        self.say('family everything')
        for text, label in (('read my email', 'your email'), ('buy 2 lots of nifty', 'trading and money'), ('run the command ls on the server', 'the server and commands'),
                            ('what is on my drive', 'files and Drive'), ('show me his api key', 'passwords and keys'), ('what do you know about him', 'what I remember about him')):
            out = self.other(text)
            self.assertIn('private to Gautam', out, text)
        out = self.other('give me full access')
        self.assertIn('I only take orders from Gautam', out)
        self.assertEqual(m._n89_decide('5552', 'locked_thing', 'family'), (False, 'locked'))

    def test_a_family_member_can_then_use_everything_end_to_end(self):
        m = self.m
        self.family(5552)
        self.say('family everything')
        self.assertIn('AI-REPLY', self.other('how do I cook rice?'))
        self.assertIn('On it', self.other('download tum hi ho song'))
        self.assertEqual(len(self.popen_calls), 1)
        with mock.patch.object(m, 'fetch_image', lambda prompt, path, w=0, h=0: open(path, 'wb').write(b'x' * 10) or True), mock.patch.object(m.requests, 'post', lambda *a, **k: None):
            out = self.other('draw a cat riding a bicycle')
        self.assertIn('Creating your picture', out)
        with mock.patch.object(m, 'make_pdf', lambda cid, topic: m.send_text(cid, 'PDF-SENT ' + topic)):
            out = self.other('make a pdf about solar energy')
        self.assertIn('Preparing your PDF', out)
        self.assertIn('PDF-SENT make a pdf about solar energy', '\n'.join(t for c, t in self.sent if c == 5552))

    def test_a_personal_switch_is_kept_and_reported(self):
        m = self.m
        self.family(5552, 'Asha')
        self.allow(5552, 'images', False)
        out = self.say('family everything')
        self.assertFalse(m._n89_allowed('5552', 'images'))
        self.assertTrue(m._n89_allowed('5552', 'downloads'))
        self.assertIn('Personal switches you set earlier still apply', out)
        self.assertIn('Asha has making pictures off', out)

    def test_everyday_only_goes_back_to_the_shipped_defaults_and_keeps_personal_switches(self):
        m = self.m
        self.family(5552)
        self.say('family everything')
        self.allow(5552, 'calendar', True)
        out = self.say('family everyday only')
        eff = {a: v for a, (v, s) in m._n89_effective('5552').items()}
        self.assertEqual([a for a, v in eff.items() if v], ['chat', 'reminders', 'family_list', 'tell_owner', 'web', 'files', 'calendar'])
        self.assertFalse(m._n97_access('5552', 'family'))
        self.assertIn('back to the everyday set', out)

    def test_guests_and_strangers_are_untouched(self):
        m = self.m
        m._n89_note_person('5599', 'Stranger', '')
        before = dict(m._n89_effective('5599'))
        self.say('family everything')
        self.assertEqual(before, m._n89_effective('5599'))
        self.assertFalse(m._n89_allowed('5599', 'downloads'))
        self.assertFalse(m._n89_allowed('5599', 'images'))
        self.assertFalse(m._n97_access('5599', 'guest'))

    def test_a_family_member_cannot_say_it_themselves(self):
        self.family(5552)
        out = self.other('family everything')
        self.assertNotIn('Done. Every family member', out)
        self.assertFalse(self.m._n89_allowed('5552', 'downloads'))
        self.assertEqual(self.m._N101_STATS['family_everything'], 0)

    def test_a_new_family_member_gets_it_all_at_once(self):
        self.say('family everything')
        self.family(5560, 'Late Joiner')
        self.assertTrue(all(v for v, s in self.m._n89_effective('5560').values()))

    def test_the_family_world_switch(self):
        self.family(5552)
        self.assertIn('World markets for family: off', self.say('family world off'))
        out = self.other('world markets')
        self.assertIn('switched off for family', out)
        self.assertEqual(self.pngs(), [])
        self.say('family world on')
        self.assertIn('WORLD BOARD', self.other('world markets'))


class TestFamilyWorld(FamilyCase):
    def test_a_family_member_gets_the_board_the_picture_and_no_owner_extras(self):
        self.family(5552)
        out = self.other('world markets')
        self.assertIn('WORLD BOARD', out)
        self.assertEqual(self.pngs()[0]['cid'], 5552)
        self.assertNotIn('Sigma', out)
        self.assertNotIn('Gautam', out)

    def test_hours_open_questions_country_cards_and_instruments(self):
        self.family(5552)
        self.assertIn('MARKET HOURS', self.other('market hours'))
        self.assertIn('Tokyo Stock Exchange: open', self.other('is Tokyo open'))
        self.assertIn('JAPAN', self.other('globe japan'))
        self.assertIn('Brent crude', self.other('globe brent'))
        self.assertIn('COMPARED OVER', self.other('globe compare nifty gold'))
        self.assertIn('OVERNIGHT CUES', self.other('global cues') if self.world.update(cue_world(1, rel=0.5)) is None else '')

    def test_what_is_a_world_word_is_instant_and_free(self):
        self.family(5552)
        out = self.other('what is DXY')
        self.assertIn('Dollar index', out)
        self.assertEqual(self.ai_calls, [])
        self.assertEqual(self.m._n89_used('5552', 'heavy'), 0)
        out = self.other('what is love')
        self.assertIn('AI-REPLY', out)                                              # not a trading word: the normal chat answer

    def test_the_family_calendar_hides_the_owners_event_ids_and_instructions(self):
        self.family(5552)
        eid, *_ = self.m._n101_event_add('2026-10-08', 'RBI policy decision', 'high')
        out = self.other('world calendar')
        self.assertIn('RBI policy decision', out)
        self.assertNotIn(eid, out)
        self.assertNotIn('globe event add', out)

    def test_family_cannot_add_or_remove_events_or_change_settings(self):
        self.family(5552)
        eid, *_ = self.m._n101_event_add('2026-10-08', 'RBI policy decision', 'high')
        for p in ('globe event add 2026-10-09 my own event', 'globe event remove %s' % eid, 'globe colours classic', 'globe charts off', 'globe help'):
            out = self.other(p)
            self.assertEqual(self.m._n101_get('colours'), 'safe', p)
        self.assertTrue(self.m._n101_charts_on())
        self.assertEqual(self.m._n101_q('SELECT COUNT(*) FROM globe101_event')[0][0], 1)

    def test_the_heavy_views_count_towards_the_daily_limit(self):
        self.family(5552)
        self.m._n89_set_setting('heavy_limit_family', '2')
        self.other('world markets')
        self.other('globe map')
        self.assertEqual(self.m._n89_used('5552', 'heavy'), 2)
        out = self.other('globe brent')
        self.assertIn('special requests', out)
        self.assertIn('hours', self.other('market hours').lower())                  # a light view is still free
        self.assertIn('Dollar index', self.other('what is DXY'))

    def test_guests_never_get_the_world_desk_from_this_layer(self):
        self.m._n89_note_person('5599', 'Guy', '')
        self.m._n89_approve_guest('5599')
        n0 = len(self.fetch_calls)
        out = self.other('world markets', uid=5599, name='Guy')
        self.assertEqual(len(self.fetch_calls), n0)
        self.assertEqual(self.pngs(), [])

    def test_blocked_people_get_nothing(self):
        self.family(5552)
        self.m.BLOCKED.append(5552)
        out = self.other('world markets')
        self.assertEqual(out, '')

    def test_groups_get_chat_only(self):
        self.family(5552)
        msg = {'chat': {'id': -100500, 'type': 'supergroup', 'title': 'Home'}, 'from': {'id': 5552, 'first_name': 'Asha'}, 'text': '@nemo_bot world markets', 'message_id': 4}
        n0 = len(self.sent)
        n1 = len(self.fetch_calls)
        self.m._n89_gate(msg)
        self.drain()
        self.assertEqual(self.sent_since(n0, -100500), 'AI-REPLY')                  # in a group the world desk is not offered: it is an ordinary chat message
        self.assertEqual(self.pngs(), [])
        self.assertEqual(len(self.fetch_calls), n1)

    def test_the_access_card_lists_the_world_desk_for_family_only(self):
        self.family(5552)
        self.assertIn('World markets (free, read-only)', self.other('what can I do'))
        self.m._n89_note_person('5599', 'Guy', '')
        self.m._n89_approve_guest('5599')
        self.assertNotIn('World markets', self.other('what can I do', uid=5599, name='Guy'))

    def test_an_unknown_name_is_answered_with_a_list_not_the_ai(self):
        self.family(5552)
        out = self.other('globe wheat')
        self.assertIn('I do not know “wheat”', out)
        self.assertEqual(self.ai_calls, [])


# ===================================================================================================================
# 9. STRUCTURE: what the layer is allowed to touch
# ===================================================================================================================
class TestStructure(GlobeCase):
    def test_the_layer_never_names_an_order_function_the_broker_the_guards_or_the_owner_lock(self):
        tree = ast.parse(globe_source())
        banned = {'fyers_place', 'fyers_place_bracket', '_order_send', 'request_order', 'place_order', 'AUTO', 'AUTOLOG', 'ALLOWED', 'MODE'}
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        self.assertEqual(sorted(names & banned), [])
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AugAssign)):
                for t in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                    for sub in ast.walk(t):
                        if isinstance(sub, ast.Name):
                            self.assertNotIn(sub.id, ('OWNER', 'AUTO', 'AUTOLOG', 'ALLOWED', 'MODE', 'BLOCKED'), 'the layer assigns to ' + sub.id)

    def test_no_ai_is_called_by_the_layer(self):
        tree = ast.parse(globe_source())
        called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertFalse(called & {'ask_ai', 'call_llm', 'ask_model', 'brain_chat'})
        self.assertNotIn('ask_ai', globe_source())

    def test_one_new_network_call_the_public_chart_feed(self):
        tree = ast.parse(globe_source())
        gets = []
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            for c in ast.walk(fn):
                if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and isinstance(c.func.value, ast.Name) and c.func.value.id == 'requests':
                    gets.append((fn.name, c.func.attr))
        self.assertEqual(gets, [('_n101_fetch', 'get')])
        urls = re.findall(r'https?://[^\s\'"]+', globe_source())
        self.assertEqual(urls, [])                                                    # the host comes from Sigma's constant, not a second copy
        self.assertIn("_N100_YAHOO + ", globe_source())
        self.assertIn('query1.finance.yahoo.com', open(base.NEMO_FILE, encoding='utf-8').read())

    def test_sql_touches_only_its_own_tables_and_the_circle_and_desk_rules_it_is_meant_to_read(self):
        src = globe_source()
        tables = set()
        for stmt in re.findall(r"'((?:SELECT|INSERT|UPDATE|DELETE|CREATE)[^']*)'", src) + re.findall(r'"((?:SELECT|INSERT|UPDATE|DELETE|CREATE)[^"]*)"', src):
            tables |= set(re.findall(r'(?:FROM|INTO|UPDATE|TABLE(?: IF NOT EXISTS)?|JOIN)\s+([A-Za-z_0-9]+)', stmt))
        own = {t for t in tables if t.startswith('globe101_')}
        other = tables - own
        self.assertEqual(own, {'globe101_setting', 'globe101_event'})
        self.assertEqual(other, {'circle89_rule', 'desk97_person', 'sig100_signal'})        # read-only: the rules the family switch reports on, and Sigma's own records for the pictures
        for stmt in re.findall(r"'((?:INSERT|UPDATE|DELETE)[^']*)'", src):
            self.assertTrue('globe101_' in stmt, stmt)

    def test_the_family_switch_writes_only_through_circle_and_the_desk_setters(self):
        src = globe_source()
        self.assertEqual(sorted(set(re.findall(r'_n89_rule_set\(([^)]*)\)', src))), ["'role:family', a, True"])
        self.assertIn('_n89_rules_reset', src)
        self.assertNotIn('_n89_set_family', src)                                       # it never makes or removes a family member

    def test_no_secret_shaped_text_and_no_model_names(self):
        src = globe_source()
        for pat in (r'sk-[A-Za-z0-9]{10,}', r'AKIA[0-9A-Z]{12,}', r'ghp_[A-Za-z0-9]{20,}', r'xox[bp]-[0-9A-Za-z-]{10,}', r'(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*[\'"][^\'"]{6,}', r'AIza[0-9A-Za-z_-]{20,}'):
            self.assertEqual(re.findall(pat, src), [], pat)
        self.assertEqual(re.findall(r'(?i)claude-|sonnet|opus|gpt-\d|gemini-\d', src), [])

    def test_the_prefix_is_protected_from_live_self_edit(self):
        src = open(base.NEMO_FILE, encoding='utf-8').read()
        self.assertIn("'_n100_','_n101_','_p75_'", src)

    def test_version_and_docstring(self):
        src = open(base.NEMO_FILE, encoding='utf-8').read()
        self.assertTrue(src.startswith('"""nemotron_bot.py v101.0 - GLOBE'))
        self.assertEqual(self.m.VERSION, '101.0')

    def test_the_regression_rows_pass(self):
        rows = self.m._n101_regression_rows()
        bad = [r['name'] for r in rows if not r['ok']]
        self.assertEqual(bad, [])
        self.assertGreaterEqual(len(rows), 8)

    def test_capabilities_mention_the_world_desk_and_the_family_phrase(self):
        c = self.m._n82_capabilities()
        self.assertIn('Globe 101', c)
        self.assertIn('family everything', c)

    def test_a_whole_session_makes_no_http_call_and_places_no_order(self):
        self.world = cue_world(1, rel=0.5)
        self.family(5552)
        for p in ('world markets', 'globe map', 'global cues', 'market hours', 'is Tokyo open', 'globe brent', 'globe compare nifty gold', 'globe japan', 'globe correlation', 'world calendar', 'family everything'):
            self.m.handle(self.msg(p))
        self.other('world markets')
        self.assertEqual(self.http_hits, [])
        self.assertEqual(self.broker_calls, [])
        self.assertEqual(self.ai_calls, [])


if __name__ == '__main__':
    unittest.main()
