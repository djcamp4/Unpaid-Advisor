import copy
import os
import unittest
from unittest.mock import Mock, patch

import requests
from analysis import financials
from analysis.fetcher import get_fundamentals, get_kpis, get_balance_sheet_metrics
from analysis.streaming import failure_reason


def statements():
    return {
        'income_statement': [
            {'period_end': '2025-09-27', 'revenue': 1000, 'net_income': 100,
             'eps_basic': 2, 'gross_profit': 400, 'operating_income': 200},
            {'period_end': '2024-09-28', 'revenue': 800, 'net_income': 80}],
        'balance_sheet': [
            {'period_end': '2024-09-28', 'total_assets': 1600},
            {'period_end': '2025-09-27', 'total_assets': 2000,
             'total_stockholders_equity': 500, 'long_term_debt': 50,
             'total_current_assets': 300, 'total_current_liabilities': 100,
             'cash_and_equivalents': 75}],
        'cash_flow_statement': [
            {'period_end': '2025-09-27', 'net_cash_operating': 150,
             'capital_expenditures': 20, 'depreciation_amortization': 10}],
    }


class FinancialsTests(unittest.TestCase):
    def setUp(self):
        financials._cache.clear()

    def test_period_join_and_real_metric_calculations(self):
        fins = financials.normalize_statements(statements())
        data = {'fins': fins, 'snap': {}, 'prev': {'c': 20},
                'details': {'weighted_shares_outstanding': 50, 'market_cap': 1000}}
        kpis = get_kpis(data)
        fundamentals = get_fundamentals(data)
        self.assertEqual(kpis['pe_ratio'], 10)
        self.assertEqual(kpis['price_to_book'], 2)
        self.assertEqual(fundamentals['revenue_ttm'], 1000)
        self.assertEqual(fundamentals['revenue_growth_yoy'], .25)
        self.assertEqual(fundamentals['roe'], .2)
        self.assertEqual(fundamentals['free_cash_flow'], 2.6)
        bs = get_balance_sheet_metrics(data)
        self.assertEqual(bs['current_assets'], [300])
        self.assertEqual(bs['da'], [10])
        self.assertEqual(bs['cash'], [75])

    def test_no_mixing_latest_income_with_old_balance_sheet(self):
        sample = statements()
        sample['balance_sheet'] = sample['balance_sheet'][:1]
        with self.assertRaises(financials.FinancialDataError) as error:
            financials.normalize_statements(sample)
        self.assertFalse(error.exception.global_failure)

    def test_latest_restatement_wins(self):
        sample = statements()
        updated = copy.deepcopy(sample['income_statement'][0])
        updated.update(as_reported_filed='2026-01-01', revenue=1200)
        sample['income_statement'].insert(0, updated)
        result = financials.normalize_statements(sample)
        self.assertEqual(result[0]['financials']['income_statement']['revenues']['value'], 1200)

    def test_missing_capex_is_not_invented_free_cash_flow(self):
        sample = statements()
        sample['cash_flow_statement'][0]['capital_expenditures'] = None
        data = {'fins': financials.normalize_statements(sample), 'details': {}, 'snap': {}, 'prev': {}}
        self.assertIsNone(get_fundamentals(data)['free_cash_flow'])

    def test_zero_capex_is_preserved(self):
        sample = statements()
        sample['cash_flow_statement'][0]['capital_expenditures'] = 0
        result = financials.normalize_statements(sample)
        self.assertEqual(result[0]['financials']['cash_flow_statement']['capital_expenditure']['value'], 0)

    def test_fetch_auth_schema_cache_and_cash_flow_name(self):
        sample = statements()
        def get(url, **kwargs):
            self.assertEqual(kwargs['headers']['X-API-Key'], 'private-key')
            self.assertNotIn('private-key', url)
            self.assertEqual(kwargs['params']['period'], 'annual')
            name = kwargs['params']['statement']
            name = 'cash_flow_statement' if name == 'cash_flow' else name
            return Mock(status_code=200, json=lambda: {'data': sample[name]})
        with patch.dict(os.environ, FINDATAENGINE_API_KEY='private-key'), patch.object(financials.requests, 'get', side_effect=get) as request:
            self.assertTrue(financials.fetch_financials('AAPL'))
            financials.fetch_financials('AAPL')
            self.assertEqual(request.call_count, 3)

    def test_failures_are_explicit_not_cached_or_retried(self):
        for status, phrase in [(401, 'API key'), (403, 'denied'), (404, 'does not have'), (429, 'limit')]:
            with self.subTest(status=status), patch.dict(os.environ, FINDATAENGINE_API_KEY='secret'), patch.object(financials.requests, 'get', return_value=Mock(status_code=status)) as request:
                with self.assertRaises(financials.FinancialDataError) as error:
                    financials.fetch_financials('AAPL')
                self.assertIn(phrase, str(error.exception))
                self.assertEqual(failure_reason(error.exception), str(error.exception))
                self.assertEqual(request.call_count, 1)
                self.assertEqual(financials._cache, {})

    def test_timeout_does_not_leak_exception_or_key(self):
        with patch.object(financials.requests, 'get', side_effect=requests.Timeout('secret URL')):
            with self.assertRaises(financials.FinancialDataError) as error:
                financials._statement('AAPL', 'income_statement', 'secret')
        self.assertIn('timed out', str(error.exception))
        self.assertNotIn('secret', str(error.exception))

    def test_invalid_response_is_not_empty_financials(self):
        with patch.object(financials.requests, 'get', return_value=Mock(status_code=200, json=lambda: {'data': {}})):
            with self.assertRaises(financials.FinancialDataError):
                financials._statement('AAPL', 'income_statement', 'secret')

    def test_server_error_retries_once(self):
        with patch.object(financials.requests, 'get', return_value=Mock(status_code=503)) as request, patch.object(financials.time, 'sleep'):
            with self.assertRaises(financials.FinancialDataError):
                financials._statement('AAPL', 'income_statement', 'secret')
        self.assertEqual(request.call_count, 2)
