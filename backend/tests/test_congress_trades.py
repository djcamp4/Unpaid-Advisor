import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import httpx
from analysis import congress_trades as trades


def purchase(symbol, **kwargs):
    return dict(symbol=symbol, type='Purchase', disclosureDate=str(datetime.now().date()),
                amount='$1,001 - $15,000', firstName='Test', lastName='Buyer', **kwargs)


class CongressionalTradesTests(unittest.IsolatedAsyncioTestCase):
    async def fetch(self, handler):
        real_client = httpx.AsyncClient
        with patch.dict(os.environ, FMP_API_KEY='test-secret'), patch.object(
            trades.httpx, 'AsyncClient',
            side_effect=lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
        ):
            return await trades.fetch_congressional_purchase_details(60)

    async def test_purchases_beyond_first_page_and_unique_tickers(self):
        calls = []
        def handler(request):
            page = int(request.url.params['page'])
            calls.append((request.url.path, page))
            if 'house' in request.url.path:
                return httpx.Response(200, json=[purchase('MSFT')] if page == 0 else [])
            pages = [
                [dict(purchase('SELL'), type='Sale')] * 25,
                [purchase('AAPL'), purchase('AAPL'), purchase('MSFT')],
                [],
            ]
            return httpx.Response(200, json=pages[page])
        details = await self.fetch(handler)
        self.assertEqual(set(details), {'AAPL', 'MSFT'})
        self.assertEqual(len(details['MSFT']['buyers']), 2)
        self.assertIn(('/stable/senate-latest', 2), calls)

    async def test_more_than_25_tickers_still_fetches_house(self):
        def handler(request):
            if int(request.url.params['page']) > 0:
                return httpx.Response(200, json=[])
            rows = [purchase(f'S{i}') for i in range(30)] if 'senate' in request.url.path else [purchase('HOUSE')]
            return httpx.Response(200, json=rows)
        details = await self.fetch(handler)
        self.assertEqual(len(details), 31)
        self.assertIn('HOUSE', details)

    async def test_stable_field_names_and_purchase_code(self):
        def handler(request):
            rows = [dict(purchase(''), ticker='AAPL', type=' P ', senator='Test Senator')]
            return httpx.Response(200, json=rows if int(request.url.params['page']) == 0 else [])
        details = await self.fetch(handler)
        self.assertEqual(details['AAPL']['buyers'][0]['name'], 'Test Senator')

    async def test_stops_at_old_disclosures_not_old_transactions(self):
        old = str(datetime.now().date() - timedelta(days=61))
        def handler(request):
            page = int(request.url.params['page'])
            pages = [[purchase('AAPL', transactionDate=old)],
                     [dict(purchase('OLD'), disclosureDate=old)]]
            return httpx.Response(200, json=pages[page])
        details = await self.fetch(handler)
        self.assertEqual(set(details), {'AAPL'})

    async def test_http_failure_is_visible_and_key_is_not_leaked(self):
        with self.assertRaisesRegex(RuntimeError, 'HTTP 403') as error:
            await self.fetch(lambda r: httpx.Response(403))
        self.assertNotIn('test-secret', str(error.exception))

    async def test_error_payload_is_not_an_empty_scan(self):
        with self.assertRaisesRegex(RuntimeError, 'unexpected response'):
            await self.fetch(lambda r: httpx.Response(200, json={'Error Message': 'Restricted'}))

    async def test_subscription_failure_explains_access_requirement(self):
        with self.assertRaisesRegex(RuntimeError, 'subscription includes congressional disclosures'):
            await self.fetch(lambda r: httpx.Response(402))

    async def test_repeated_page_is_not_silently_truncated(self):
        with self.assertRaisesRegex(RuntimeError, 'repeated a page'):
            await self.fetch(lambda r: httpx.Response(200, json=[purchase('AAPL')]))

    async def test_pagination_safety_limit_is_explicit(self):
        with patch.object(trades, 'MAX_PAGES', 1):
            with self.assertRaisesRegex(RuntimeError, 'pagination limit'):
                await self.fetch(lambda r: httpx.Response(200, json=[purchase('AAPL')]))

    def test_sync_context_uses_later_pages(self):
        def get(url, params, timeout):
            pages = [[dict(purchase('SELL'), type='Sale')], [purchase('AAPL')], []]
            return httpx.Response(200, json=pages[params['page']])
        with patch.dict(os.environ, FMP_API_KEY='test-secret'), patch('requests.Session') as session:
            session.return_value.__enter__.return_value.get.side_effect = get
            result = trades.get_ticker_congressional_context_sync('aapl')
        self.assertEqual(len(result['buyers']), 2)


if __name__ == '__main__':
    unittest.main()
