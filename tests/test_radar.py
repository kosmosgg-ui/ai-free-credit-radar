import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import radar

class RadarTests(unittest.TestCase):
    def test_rss_extract_and_clean(self):
        data = '''<rss version="2.0"><channel><item><title>AI API free credits - Example</title><link>https://example.org/a</link><description>free tokens</description><pubDate>Mon, 26 Oct 2026 09:00:00 GMT</pubDate></item></channel></rss>'''
        xs=radar.rss_items(data,'Google News · 해외')
        self.assertEqual(len(xs),1)
        self.assertEqual(xs[0]['published_at'],'2026-10-26T09:00:00Z')
        self.assertGreaterEqual(radar.score_item(xs[0])[0],7)

    def test_atom_extract(self):
        data='''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>LLM free inference API</title><link href="https://example.com/abc"/><updated>2026-10-26T12:00:00Z</updated></entry></feed>'''
        self.assertEqual(len(radar.rss_items(data,'Atom')),1)

    def test_dc_html_parse(self):
        page='''<table><tr class="ub-content us-post" data-no="12345"><td class="gall_num">12345</td><td class="gall_tit ub-word"><a href="/mgallery/board/view/?id=ai_utilize&amp;no=12345">무료 AI 크레딧 쌀먹 정리</a></td><td class="gall_date" title="2026-10-27 10:20:30">10:20</td></tr></table>'''
        xs=radar.dc_items(page)
        self.assertEqual(len(xs),1)
        self.assertIn('12345', xs[0]['url'])
        self.assertEqual(xs[0]['published_at'],'2026-10-27T01:20:30Z')
        self.assertGreaterEqual(radar.score_item(xs[0])[0],7)

    def test_hn_json(self):
        result=radar.hn_items(json.dumps({'hits':[{'objectID':'321','title':'Free AI credits for developers','created_at':'2026-10-27T06:00:00.000Z'}]}))
        self.assertEqual(len(result),1)
        self.assertIn('321',result[0]['url'])

    def test_negative_and_xss(self):
        item=radar.standard_item('AI 활용 갤러리','크랙 AI 무료 api','https://example.org/abc')
        self.assertEqual(radar.score_item(item)[0],0)
        self.assertEqual(radar.safe_url('javascript:alert(1)'),'')
        self.assertEqual(radar.safe_url('https://attacker:pass@example.org/'), '')
        item=radar.standard_item('news','<script>alert(1)</script> AI free credits','https://example.org/')
        self.assertNotIn('<',item['title'])

    def test_dedupe_age(self):
        t=datetime(2026,10,27,tzinfo=timezone.utc)
        config={'max_age_days':14, 'max_items':250}
        x=radar.standard_item('test','AI API free credits','https://example.org/a',t)
        y=radar.standard_item('test','AI API free credits','https://example.org/b',t)
        old=radar.standard_item('test','old AI free credits','https://example.org/old',t-timedelta(days=50))
        state={'initialized':False,'items':{},'notified':[]}
        state,changed=radar.merge(state,[x,y,old],config,t)
        self.assertEqual(len(state['items']),1)
        self.assertEqual(len(changed),1)
        self.assertEqual(list(state['items'].values())[0]['url'],'https://example.org/a')

    def test_first_run_baseline_and_new_alert_only_once(self):
        t=radar.now()
        base=radar.standard_item('AI 활용 갤러리','새 AI 무료 크레딧 예시', 'https://example.org/one',t)
        second=radar.standard_item('AI 활용 갤러리','신규 AI 무료 토큰 지원 이벤트', 'https://example.org/two',t)
        with tempfile.TemporaryDirectory() as d:
            d=Path(d)
            config=d/'config.json'
            config.write_text(json.dumps({'max_age_days':14,'max_items':50,'alert_min_score':7,'project_name':'Test'}))
            with patch.object(radar,'CONFIG',config),patch.object(radar,'STATE',d/'data'/'state.json'),patch.object(radar,'SITE',d/'site'):
                with patch.object(radar,'collect',return_value=([dict(base)],[])), patch.object(radar,'notify',return_value=(True,'ok')) as notify:
                    self.assertEqual(radar.once(),0)
                    notify.assert_not_called()  # first-run baseline
                with patch.object(radar,'collect',return_value=([dict(base),dict(second)],[])), patch.object(radar,'notify',return_value=(True,'ok')) as notify:
                    self.assertEqual(radar.once(),0)
                    notify.assert_called_once()
                    self.assertEqual(len(notify.call_args.args[0]),1)
                with patch.object(radar,'collect',return_value=([dict(base),dict(second)],[])), patch.object(radar,'notify',return_value=(True,'ok')) as notify:
                    self.assertEqual(radar.once(),0)
                    notify.assert_not_called()

    def test_site_no_script_injection(self):
        t=datetime(2026,10,27,tzinfo=timezone.utc)
        x=radar.standard_item('test','Free AI credit </script><script>bad()</script>', 'https://example.org/',t)
        x.update(first_seen=radar.stamp(t),last_seen=radar.stamp(t), score=10,tags=['혜택'],credibility='제보')
        # HTML output must escape untrusted strings even if an adapter bypasses clean().
        x['title'] = 'AI free credit </script><script>bad()</script>'
        state={'initialized':True,'items':{x['id']:x},'last_checked':radar.stamp(t),'notified':[]}
        with tempfile.TemporaryDirectory() as d:
            with patch.object(radar,'SITE',Path(d)):
                radar.write_site(state,[],{'project_name':'Test'})
                site=(Path(d)/'index.html').read_text(encoding='utf-8')
                self.assertNotIn('</script><script>bad()',site)
                self.assertIn('\\u003c/script\\u003e',site)
                self.assertTrue((Path(d)/'results.csv').exists())

if __name__=='__main__':
    unittest.main()
