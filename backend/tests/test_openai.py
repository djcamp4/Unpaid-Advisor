import os
import json
import unittest
from unittest.mock import patch
import httpx
from analysis import summarizer as s


def response(text='Complete answer.'):
    return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':text}]}]}


class OpenAITests(unittest.TestCase):
    def setUp(self):
        s._debate_cache.clear()
        s._pitches_cache.clear()

    def invoke(self, handler, **kwargs):
        real=httpx.Client
        with patch.object(s.httpx,'Client',side_effect=lambda **kw:real(transport=httpx.MockTransport(handler),**kw)), patch.object(s.time,'sleep'):
            return s._call([{'role':'system','content':'Be concise'},{'role':'user','content':'Analyze'}],'test-key',**kwargs)

    def test_request(self):
        def handler(req):
            self.assertEqual(str(req.url),'https://api.openai.com/v1/responses')
            self.assertEqual(req.headers['Authorization'],'Bearer test-key')
            body=json.loads(req.content)
            self.assertEqual(body['model'],'gpt-5.4-mini')
            self.assertEqual(body['max_output_tokens'],400)
            self.assertEqual(body['reasoning'],{'effort':'none'})
            self.assertFalse(body['store'])
            self.assertEqual(body['input'][0]['role'],'system')
            return httpx.Response(200,json=response())
        self.assertEqual(self.invoke(handler,max_tokens=400),'Complete answer.')

    def test_incomplete(self):
        data=response(); data['status']='incomplete'
        self.assertIsNone(self.invoke(lambda req:httpx.Response(200,json=data)))

    def test_auth_no_retry(self):
        calls=[]
        def handler(req):
            calls.append(req); return httpx.Response(401)
        self.assertIsNone(self.invoke(handler)); self.assertEqual(len(calls),1)

    def test_rate_limit_retry(self):
        calls=[]
        def handler(req):
            calls.append(req)
            return httpx.Response(429) if len(calls)==1 else httpx.Response(200,json=response())
        self.assertEqual(self.invoke(handler),'Complete answer.'); self.assertEqual(len(calls),2)

    def test_bounded_retries(self):
        calls=[]
        def handler(req):
            calls.append(req); return httpx.Response(503)
        self.assertIsNone(self.invoke(handler)); self.assertEqual(len(calls),3)

    def test_missing_key(self):
        with patch.dict(os.environ,{},clear=True),patch.object(s,'_call') as call:
            self.assertIsNone(s.generate_stock_pitches('X','Example','HOLD',50,{},[],{},{}))
            call.assert_not_called()

    def test_debate_routing(self):
        with patch.dict(os.environ,OPENAI_API_KEY='test-key'),patch.object(s,'_data_block',return_value='metrics'),patch.object(s,'_call',side_effect=['Value.\nDECISION: BUY','Growth.\nDECISION: BUY','Strong company.\nCONFIDENCE: 80%\nFINAL VERDICT: BUY']) as call:
            result=s.generate_debate('X','Example','BUY',80,{},[],{},{})
        self.assertEqual(result['verdict'],'BUY'); self.assertEqual(result['confidence'],80)
        self.assertEqual([c.kwargs.get('model',s._INVESTOR_MODEL) for c in call.call_args_list],['gpt-5.4-mini','gpt-5.4-mini','gpt-5.4'])

    def test_pitch_routing(self):
        with patch.dict(os.environ,OPENAI_API_KEY='test-key'),patch.object(s,'_data_block',return_value='metrics'),patch.object(s,'_call',return_value='Case.') as call:
            self.assertIsNotNone(s.generate_stock_pitches('X','Example','BUY',80,{},[],{},{}))
        self.assertEqual([c.kwargs.get('model',s._INVESTOR_MODEL) for c in call.call_args_list],['gpt-5.4-mini','gpt-5.4-mini'])

    def test_rank_routing(self):
        with patch.dict(os.environ,OPENAI_API_KEY='test-key'),patch.object(s,'_call',return_value='#1 AAPL | 80%\nStrong earnings.') as call:
            ranked=s.rank_stocks([{'ticker':'AAPL','rule_score':70}])
        self.assertEqual(call.call_args.kwargs['model'],'gpt-5.4')
        self.assertEqual(ranked[0]['symbol'],'AAPL'); self.assertEqual(ranked[0]['confidence'],80)
