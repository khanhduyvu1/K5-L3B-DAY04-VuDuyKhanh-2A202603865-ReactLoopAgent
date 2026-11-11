"""Tests cho cải tiến Bài 4: partial-failure gate và giới hạn retry rate limit."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'evals'))
from agent import run_agent
from scenarios import ScenarioTools
from bonus.tools import BonusTools
from test_lab import FakeProvider, tool_call, final


class UnverifiedProviderGateTests(unittest.TestCase):
    def test_timeout_provider_triggers_one_review(self):
        tools = ScenarioTools('cloudflare_timeout')
        a = tool_call('a', 'get_status', '{"provider":"github"}')
        b = tool_call('b', 'get_status', '{"provider":"cloudflare"}')
        a['calls'] += b['calls']
        a['message']['tool_calls'] += b['message']['tool_calls']
        fake = FakeProvider([a, final('Cloudflare operational'), final('Cloudflare: chưa xác minh do timeout')])
        result = run_agent('x', fake, tools, max_steps=5)
        self.assertEqual(result['status'], 'completed')
        self.assertIn('chưa xác minh', result['answer'])
        events = [x for x in result['trace'] if x['event'] == 'validation_unverified_provider']
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['providers'], ['cloudflare'])
        self.assertIn('cloudflare', fake.histories[2][-1]['content'])

    def test_all_providers_ok_needs_no_review(self):
        fake = FakeProvider([tool_call('a', 'get_status', '{"provider":"github"}'), final('ok')])
        result = run_agent('x', fake, ScenarioTools('cloudflare_timeout'))
        self.assertFalse(any(x['event'] == 'validation_unverified_provider' for x in result['trace']))

    def test_not_found_is_not_provider_failure(self):
        fake = FakeProvider([tool_call('a', 'get_incident_details', '{"provider":"cloudflare","incident_id":"nope"}'), final('Không tìm thấy')])
        result = run_agent('x', fake, ScenarioTools())
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(fake.histories), 2)


class RetryBudgetTests(unittest.TestCase):
    def test_rate_limit_retries_are_capped(self):
        responses = [tool_call(str(i), 'get_vercel_status', '{}') for i in range(5)] + [final('Vercel: chưa biết')]
        fake = FakeProvider(responses)
        result = run_agent('x', fake, BonusTools(scenario='rate_limit_always'), max_steps=10)
        executed = [x for x in result['trace'] if x['event'] == 'tool' and x['name'] == 'get_vercel_status']
        blocked = [x for x in result['trace'] if x['event'] == 'tool_blocked']
        self.assertEqual(len(executed), 3)
        self.assertEqual(len(blocked), 2)
        self.assertEqual(json.loads(fake.histories[4][-1]['content'])['error'], 'RETRY_BUDGET_EXHAUSTED')


if __name__ == '__main__':
    unittest.main()
