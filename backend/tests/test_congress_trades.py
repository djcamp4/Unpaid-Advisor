import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
import httpx
from analysis import congress_trades as trades

def purchase(ticker, **kwargs):
    return {"ticker": ticker, "transaction_type": "purchase", "disclosure_date": str(datetime.now().date()), "transaction_date": str(datetime.now().date()), "amount_range": "$1,001 - $15,000", "politician": "Test Buyer", "chamber": "house", **kwargs}

def osp_response(rows):
    return {"data": rows, "meta": {"page": 1, "per_page": 100, "total": len(rows)}}

class CongressionalTradesTests(unittest.IsolatedAsyncioTestCase):
    async def fetch(self, handler):
        real_client = httpx.AsyncClient
        with patch.dict(os.environ, OSP_API_KEY="test-secret"), patch.object(trades.httpx, "AsyncClient", side_effect=lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)):
            return await trades.fetch_congressional_purchase_details(60)

    async def test_purchases_beyond_first_page_and_unique_tickers(self):
        calls = []
        def handler(request):
            page = int(request.url.params["page"]); calls.append(page)
            rows = [purchase("AAPL")] * 100 if page == 1 else [purchase("AAPL"), purchase("MSFT")] if page == 2 else []
            return httpx.Response(200, json=osp_response(rows))
        details = await self.fetch(handler)
        self.assertEqual(set(details), {"AAPL", "MSFT"}); self.assertEqual(len(details["AAPL"]["buyers"]), 101); self.assertIn(2, calls)

    async def test_sales_are_excluded_and_duplicates_are_collapsed(self):
        def handler(request):
            return httpx.Response(200, json=osp_response([purchase("AAPL"), purchase("AAPL", transaction_type="sale")]))
        details = await self.fetch(handler)
        self.assertEqual(set(details), {"AAPL"}); self.assertEqual(len(details["AAPL"]["buyers"]), 1)

    async def test_old_disclosure_is_filtered(self):
        old = str(datetime.now().date() - timedelta(days=61))
        def handler(request):
            return httpx.Response(200, json=osp_response([purchase("AAPL"), purchase("OLD", disclosure_date=old)]))
        self.assertEqual(set(await self.fetch(handler)), {"AAPL"})

    async def test_auth_failure_is_visible(self):
        with self.assertRaisesRegex(RuntimeError, "HTTP 401"):
            await self.fetch(lambda request: httpx.Response(401))

    async def test_unexpected_payload_is_not_an_empty_scan(self):
        with self.assertRaisesRegex(RuntimeError, "unexpected response"):
            await self.fetch(lambda request: httpx.Response(200, json={"error": "bad"}))

    async def test_missing_key_is_explicit(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(RuntimeError, "OSP_API_KEY"):
            await trades.fetch_congressional_purchase_details(60)

    def test_sync_context_uses_osp(self):
        def get(url, headers, params, timeout):
            rows = [purchase("AAPL")] if params["page"] == 1 else []
            return httpx.Response(200, json=osp_response(rows))
        with patch.dict(os.environ, OSP_API_KEY="test-secret"), patch("requests.Session") as session:
            session.return_value.__enter__.return_value.get.side_effect = get
            result = trades.get_ticker_congressional_context_sync("aapl")
        self.assertEqual(len(result["buyers"]), 1)

if __name__ == "__main__":
    unittest.main()
