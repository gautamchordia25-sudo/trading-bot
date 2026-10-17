"""v85 Steward: wiring through the real handler chain, regression/eval rows, and structural safety guarantees checked on the code itself.

    python -m unittest tests.test_steward85_integration -v
"""
import ast
import json
import re
import time
import unittest
from unittest import mock

from tests import test_cortex83 as base
from tests.test_steward85 import StewardCase, setUpModule  # noqa: F401


def v85_source():
    src = open(base.NEMO_FILE, encoding='utf-8').read()
    start = src.index('# NEMO 85 - STEWARD')
    end = src.index('# NEMO 86 - CANDOR') if '# NEMO 86 - CANDOR' in src else src.index("\nif __name__ == '__main__':", start)
    return src[start:end]


def functions_calling(tree, predicate):
    """Names of the top-level functions (or '<module>') that contain a Call node matching predicate."""
    out = set()

    class V(ast.NodeVisitor):
        def __init__(self):
            self.stack = []

        def visit_FunctionDef(self, node):
            if len(self.stack) == 0:
                self.stack.append(node.name)
                self.generic_visit(node)
                self.stack.pop()
            else:
                self.generic_visit(node)

        def visit_Call(self, node):
            if predicate(node):
                out.add(self.stack[0] if self.stack else '<module>')
            self.generic_visit(node)
    V().visit(tree)
    return out


def call_name(node):
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ''


def dotted(node):
    f = node.func
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
        return f.value.id + '.' + f.attr
    return call_name(node)


class TestStructuralSafety(unittest.TestCase):
    """Every outward side effect in the v85 block must live in a function that only the approval engine (or an explicit owner command) reaches."""

    @classmethod
    def setUpClass(cls):
        if base.m is None:
            base.setUpModule()
        cls.src = v85_source()
        cls.tree = ast.parse(cls.src)

    def where(self, predicate):
        return functions_calling(self.tree, predicate)

    def test_no_trading_broker_or_order_identifiers(self):
        used = {n.id for n in ast.walk(self.tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(self.tree) if isinstance(n, ast.Attribute)}
        forbidden = {'fyers_place', 'fyers_login', 'fyers_ready', 'fyers_ltp', 'BROKER', 'TradeLab75', 'auto_trade_tick', 'live_ltp', 'place_order', '_n75_trade_task'}
        self.assertEqual(sorted(used & forbidden), [])

    def test_no_dynamic_execution_pickle_or_shell_strings(self):
        bad = self.where(lambda c: call_name(c) in {'eval', 'exec', 'system', 'popen', '__import__', 'loads', 'load'} and dotted(c) not in {'_n85_json.loads', 'json.loads'})
        self.assertEqual(bad, set())
        for node in ast.walk(self.tree):
            if isinstance(node, ast.keyword) and node.arg == 'shell':
                self.fail('shell= keyword found')
        for mod in ('pickle', 'marshal', 'ctypes'):
            self.assertNotIn('import ' + mod, self.src)

    def test_subprocess_is_only_used_by_the_sandbox_runner(self):
        self.assertEqual(self.where(lambda c: dotted(c) in {'_sp.run', '_sp.Popen', 'subprocess.run', 'subprocess.Popen', '_sp.call', '_sp.check_output'}),
                         {'_n85_sandbox_prefix', '_n85_run_in_sandbox'})

    def test_network_fetches_only_in_the_two_audited_functions(self):
        self.assertEqual(self.where(lambda c: dotted(c) in {'requests.get', 'requests.post', 'requests.put', 'requests.request', 'requests.head'}),
                         {'_n85_fetch', '_n85_tg_download'})

    def test_every_page_fetch_goes_through_the_ssrf_guard(self):
        fn = next(n for n in self.tree.body if isinstance(n, ast.FunctionDef) and n.name == '_n85_fetch')
        calls = [dotted(c) for c in ast.walk(fn) if isinstance(c, ast.Call)]
        self.assertLess(calls.index('_n54_url_guard'), calls.index('requests.get'), 'the guard must run before the request in every hop')
        get = next(c for c in ast.walk(fn) if isinstance(c, ast.Call) and dotted(c) == 'requests.get')
        kw = {k.arg: k.value for k in get.keywords}
        self.assertIsInstance(kw['allow_redirects'], ast.Constant)
        self.assertIs(kw['allow_redirects'].value, False, 'redirects are followed by hand so each hop is guarded')

    def test_outward_actions_exist_only_inside_their_execute_functions(self):
        expectations = {
            'send_email': {'_n85_x_send_email'},
            'gcal_add': {'_n85_x_event'},
            'sheet_log': {'_n85_x_sheet_rows'},
            '_n38_add': {'_n85_x_followup'},
            '_n85_watch_create': {'_n85_x_watch_add', '_n85_watch_add_task'},
        }
        for name, allowed in expectations.items():
            self.assertEqual(self.where(lambda c, name=name: call_name(c) == name), allowed, name)

    def test_reminders_and_todos_are_only_written_by_approved_executors(self):
        def appends(attr):
            return self.where(lambda c: isinstance(c.func, ast.Attribute) and c.func.attr in ('append', 'setdefault') and isinstance(c.func.value, ast.Name) and c.func.value.id == attr)
        self.assertEqual(appends('REMINDERS'), {'_n85_x_reminder'})
        self.assertEqual(self.where(lambda c: isinstance(c.func, ast.Attribute) and c.func.attr == 'setdefault' and isinstance(c.func.value, ast.Name) and c.func.value.id == 'TODOS'),
                         {'_n85_x_todo'})

    def test_mcp_calls_run_only_through_the_gate_the_card_executor_or_the_read_tool(self):
        callers = self.where(lambda c: isinstance(c.func, ast.Attribute) and c.func.attr == 'call' and not (isinstance(c.func.value, ast.Name) and c.func.value.id == 'self'))
        self.assertEqual(callers, {'_n85_x_mcp_call', '_n85_mcp_read'})
        self.assertEqual(self.where(lambda c: call_name(c) == '_N85_MCP_CALL_PREV'), {'_n85_mcp_call'})

    def test_every_approval_kind_has_validate_and_execute_and_risky_ones_are_marked(self):
        m = base.m
        for kind, spec in m._N85_KINDS.items():
            self.assertTrue(callable(spec['validate']) and callable(spec['execute']) and callable(spec['render']), kind)
        self.assertEqual(m._N85_KINDS['send_email']['risk'], 'high')
        self.assertEqual(m._N85_KINDS['mcp_call']['risk'], 'high')

    def test_the_proposal_function_never_calls_an_executor(self):
        fn = next(n for n in self.tree.body if isinstance(n, ast.FunctionDef) and n.name == '_n85_propose')
        names = {dotted(c) for c in ast.walk(fn) if isinstance(c, ast.Call)}
        self.assertFalse([n for n in names if n.startswith('_n85_x_')], names)
        subs = [n for n in ast.walk(fn) if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) and n.slice.value == 'execute']
        self.assertEqual(subs, [])

    def test_the_only_call_to_an_executor_is_the_atomic_decide_path(self):
        callers = self.where(lambda c: isinstance(c.func, ast.Subscript) and isinstance(c.func.slice, ast.Constant) and c.func.slice.value == 'execute')
        callers |= self.where(lambda c: isinstance(c.func, ast.Subscript) and isinstance(getattr(c.func, 'slice', None), ast.Constant) and c.func.slice.value == 'execute')
        # explicit owner commands call validate+execute directly (lead/due records in the owner's own database), nothing else does
        self.assertLessEqual(callers, {'_n85_decide', '_n85_cmd_biz'})
        self.assertIn('_n85_decide', callers)

    def test_no_secret_like_literals_and_no_credential_variables_are_read(self):
        for pat in (r'sk-[A-Za-z0-9_-]{16,}', r'AIza[A-Za-z0-9_-]{20,}', r'nvapi-[A-Za-z0-9_-]{16,}', r'\b\d{8,12}:[A-Za-z0-9_-]{30,}'):
            self.assertIsNone(re.search(pat, self.src), pat)
        names = {n.id for n in ast.walk(self.tree) if isinstance(n, ast.Name)}
        creds = {n for n in names if re.fullmatch(r'_?[A-Z][A-Z0-9_]*', n) and re.search(r'API_?KEY|SECRET|PASSWORD|TOKEN|GROQ|NVIDIA|OPENAI|GEMINI|ANTHROPIC', n)}
        self.assertEqual(creds, set(), 'v85 must not read or reference credential variables')
        self.assertEqual(self.where(lambda c: call_name(c) in {'_n73_key', 'getenv'}), set(), 'no provider keys are fetched')
        self.assertEqual(self.where(lambda c: isinstance(c.func, ast.Attribute) and c.func.attr == 'environ'), set())
        env_users = {fn for fn in self.where(lambda c: dotted(c).endswith('environ.get'))}
        self.assertLessEqual(env_users, {'_n85_run_in_sandbox'}, 'the only environment read builds the sandbox child\'s minimal environment')

    def test_untrusted_text_is_always_labelled_in_prompts(self):
        for needle in ('UNTRUSTED data', 'untrusted web data', 'untrusted document text', 'data, not instructions'):
            self.assertIn(needle, self.src)


class TestWiring(StewardCase):
    def setUp(self):
        super().setUp()
        self.prev_seen = []
        q = mock.patch.object(self.m, '_N85_HANDLE_PREV', lambda msg: self.prev_seen.append(msg.get('text')))
        q.start()
        self.patches.append(q)

    def test_handle_routes_steward_commands_before_the_old_chain_and_passes_everything_else_on(self):
        self.m.handle(self.msg('/steward85 status'))
        self.assertIn('STEWARD 85', self.sent[-1][1])
        self.assertEqual(self.prev_seen, [])
        self.m.handle(self.msg('tell me a joke about cats'))
        self.m.handle(self.msg('/remind me at 5pm to call Ravi'))
        self.assertEqual(self.prev_seen, ['tell me a joke about cats', '/remind me at 5pm to call Ravi'])

    def test_a_crash_inside_the_steward_never_blocks_the_message(self):
        with mock.patch.object(self.m, '_n85_dispatch', side_effect=RuntimeError('boom')):
            self.m.handle(self.msg('hello there'))
        self.assertEqual(self.prev_seen, ['hello there'])
        self.assertEqual(self.m._N85_STATS['errors'], 1)

    def test_command_errors_are_reported_and_nothing_is_changed(self):
        self.m.handle(self.msg('/biz85 stock out item=Ghost qty=1'))
        self.assertIn('no stock item', self.sent[-1][1])
        self.m.handle(self.msg('/watch85 add url=http://127.0.0.1/x kind=price'))
        self.assertIn('URL not allowed', self.sent[-1][1])
        self.m.handle(self.msg('/doc85 risks D-NOPE00'))
        self.assertIn('no such document', self.sent[-1][1])
        self.assertEqual(self.prev_seen, [])

    def test_research_command_runs_through_the_real_task_engine_and_delivers_the_report(self):
        m = self.m
        self.fake.when(lambda r, t: 'research agent' in t, json.dumps({'action': 'finish'}))
        with mock.patch.object(m, 'web_search', lambda q: []):
            m.handle(self.msg('/research85 what is the GST rate on LED televisions in India'))
            end = time.time() + 15
            while time.time() < end and not any('RESEARCH' in t for _, t in self.sent):
                time.sleep(0.05)
        texts = [t for _, t in self.sent]
        self.assertTrue(any('could not verify an answer' in t for t in texts), texts)
        self.assertEqual(self.prev_seen, [])

    def test_research_usage_hint_and_doc_ask_through_the_task_engine(self):
        self.m.handle(self.msg('/research85 hi'))
        self.assertIn('Usage: /research85', self.sent[-1][1])
        self.m._n85_doc_ingest(self.cid, 'note.txt', b'The showroom closes at nine in the evening on weekdays and at ten on weekends.')
        self.fake.when(lambda r, t: 'Answer the QUESTION using ONLY the PASSAGES' in t, json.dumps({'found': True, 'answer': 'It closes at nine on weekdays.',
                                                                                                   'citations': [{'p': 'A:1', 'quote': 'The showroom closes at nine in the evening on weekdays'}]}))
        self.m.handle(self.msg('/doc85 ask when does the showroom close'))
        end = time.time() + 15
        while time.time() < end and not any('note.txt, p.1' in t for _, t in self.sent):
            time.sleep(0.05)
        self.assertTrue(any('note.txt, p.1: "The showroom closes at nine in the evening on weekdays"' in t for _, t in self.sent), self.sent)

    def test_inbox_command_runs_through_the_task_engine_and_sends_cards_then_a_summary(self):
        m = self.m
        mail = [{'from': 'Ravi <ravi@mehta.example>', 'subject': 'Quotation', 'snippet': 'Please send the quotation for 20 LED TVs by Monday'}]
        self.fake.when(lambda r, t: 'chief of staff' in t and 'ITEMS:' in t, json.dumps({'proposals': [
            {'kind': 'todo', 'source_id': 'M1', 'quote': 'send the quotation for 20 LED TVs', 'why': 'asked', 'payload': {'text': 'Send quotation to Ravi'}}]}))
        with mock.patch.object(m, 'gmail_unread', lambda n=10: mail), mock.patch.object(m, 'gcal_upcoming', lambda d=3: []), \
                mock.patch.object(m, '_n38_open', lambda cid, n=12: []), mock.patch.object(m, '_n82_rows', lambda cid: []):
            m.handle(self.msg('/inbox85'))
            end = time.time() + 15
            while time.time() < end and not any('STEWARD REVIEW' in t for _, t in self.sent):
                time.sleep(0.05)
        self.assertTrue(any('STEWARD REVIEW' in t and '1 new proposal' in t for _, t in self.sent), self.sent)
        self.assertEqual(len(self.cards), 1)
        self.assertIn('Send quotation to Ravi', self.cards[0][1])
        self.assertEqual(m.TODOS.get(self.cid, []), [])

    def test_plain_messages_cost_nothing_extra(self):
        m = self.m
        t0 = time.perf_counter()
        for i in range(300):
            self.assertFalse(m._n85_dispatch(self.msg('please summarise the news about Reliance number %d' % i)))
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 1.0, 'dispatch overhead on non-matching messages: %.1f ms each' % (elapsed / 0.3))
        self.assertEqual(self.fake.calls, [], 'no model call')
        self.assertEqual(m._n85_pending_count(self.cid), 0)


class TestRegistrationRowsAndStatus(StewardCase):
    def test_regression_rows_are_green_and_nothing_else_regressed(self):
        m = self.m
        with mock.patch.object(m, '_N35_DB', base.ORIG_DB):
            m._N83_SCHEMA['path'] = None
            m._N85_SCHEMA['path'] = None
            r = m.prime_regression_suite()
        v85 = [t for t in r['tests'] if t['name'].startswith('v85-')]
        self.assertGreaterEqual(len(v85), 14)
        self.assertEqual([t['name'] for t in v85 if not t['ok']], [])
        env_only = {'v36-daycard-render', 'v36-infographic-render', 'v39-toggle', 'v54-internet-contract', 'v58-eventbus'}
        failing = {t['name'] for t in r['tests'] if not t['ok']}
        self.assertLessEqual(failing, env_only, sorted(failing - env_only))
        self.assertEqual(r['version'], m.VERSION)

    def test_eval_rows_and_capabilities_and_status(self):
        m = self.m
        rows = {r['name']: r for r in m._n28_eval()}
        for name in ('v85-approval-engine', 'v85-research-verifier', 'v85-update-gate', 'v85-mcp-tiers'):
            self.assertTrue(rows[name]['ok'], name)
        caps = m._n82_capabilities()
        for needle in ('Steward 85', 'Futures Desk 84', 'Cortex 83'):
            self.assertIn(needle, caps)
        self.assertIn('Steward 85:', m._n83_status_text(self.cid))
        self.assertIn('Futures', m._n83_status_text(self.cid))

    def test_self_development_editor_cannot_touch_the_steward(self):
        for name in ('_n85_propose', '_n85_decide', '_n85_mcp_call', '_n85_gate', '_n85_fetch', '_n85_dispatch'):
            self.assertFalse(self.m._n79_editable(name), name)

    def test_flag_defaults(self):
        d = self.m._N83_FLAG_DEFAULTS
        self.assertEqual({k: d[k] for k in ('steward', 'brief', 'watchers', 'mcpgate', 'updategate', 'emailsend')},
                         {'steward': '1', 'brief': '0', 'watchers': '1', 'mcpgate': '1', 'updategate': '1', 'emailsend': '0'})

    def test_main_wrapper_bootstraps_and_survives_failure(self):
        m = self.m
        ran = []
        with mock.patch.object(m, '_N85_MAIN_PREV', lambda: ran.append('prev')), mock.patch.object(m, '_n85_ensure_loop', lambda: ran.append('loop')):
            m.main()
        self.assertEqual(ran, ['loop', 'prev'])
        ran.clear()
        with mock.patch.object(m, '_N85_MAIN_PREV', lambda: ran.append('prev')), mock.patch.object(m, '_n85_bootstrap', side_effect=RuntimeError('boom')):
            m.main()
        self.assertEqual(ran, ['prev'], 'the older layers still start when Steward setup fails')

    def test_version_and_compile_gate(self):
        src = open(base.NEMO_FILE, encoding='utf-8').read()
        self.assertEqual(self.m._extract_version(src), self.m.VERSION)
        self.assertGreaterEqual(float(self.m.VERSION), 85)
        ok, err = self.m._compile_check(src)
        self.assertTrue(ok, err)

    def test_schema_creation_is_idempotent_and_has_every_table(self):
        c = self.m._n85_conn()
        c.close()
        c = self.m._n85_conn()
        names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        c.close()
        for t in ('ap85_item', 'ap85_audit', 'ap85_pref', 'mcp85_tier', 'mcp85_call', 'doc85_doc', 'doc85_chunk', 'doc85_page', 'biz85_customer', 'biz85_lead', 'biz85_due',
                  'biz85_item', 'biz85_move', 'biz85_invoice', 'watch85', 'watch85_hist', 'st85_kv'):
            self.assertIn(t, names, t)


if __name__ == '__main__':
    unittest.main()
