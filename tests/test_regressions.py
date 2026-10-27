import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import radar

class Regressions(unittest.TestCase):
    def test_failed_collection_keeps_state_and_refreshes_health(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            cfg=root/'config.json'; cfg.write_text('{}',encoding='utf-8')
            state={'initialized':True,'items':{},'notified':[],'last_checked':'2026-01-01T00:00:00Z'}
            health=[{'source':'test','status':'失敗','count':0,'detail':'HTTP 403'}]
            with patch.object(radar,'CONFIG',cfg), patch.object(radar,'SITE',root/'site'), patch.object(radar,'load_state',return_value=state), patch.object(radar,'collect',return_value=([],health)), patch.object(radar,'atomic_json',wraps=radar.atomic_json) as save:
                self.assertEqual(radar.once(),2)
                report=json.loads((root/'site/data.json').read_text(encoding='utf-8'))
                self.assertEqual(report['health'],health)
                self.assertNotEqual(report['checked_at'],state['last_checked'])
                self.assertEqual(save.call_count,1)

    def test_successful_empty_feed_is_not_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); cfg=root/'config.json'; cfg.write_text('{}')
            with patch.object(radar,'CONFIG',cfg),patch.object(radar,'SITE',root/'site'),patch.object(radar,'STATE',root/'state.json'),patch.object(radar,'collect',return_value=([],[{'source':'empty','status':'성공','count':0,'detail':''}])):
                self.assertEqual(radar.once(),0)

    def test_official_phrase_required(self):
        cfg={'sources':{'official_pages':[{'name':'official','url':'https://ai.google.dev/pricing','title':'AI API free tier','required_terms':['Free input & output tokens']}]}}
        with patch.object(radar,'fetch',return_value='<main>Free input &amp; output tokens</main>'):
            items,health=radar.collect(cfg)
            self.assertEqual(items[0]['verification'],'official_page_text_only')
            self.assertIsNone(items[0]['published_at'])
            self.assertEqual(health[0]['status'],'성공')
        with patch.object(radar,'fetch',return_value='<main>Paid only</main>'):
            items,health=radar.collect(cfg)
            self.assertEqual(items,[])
            self.assertEqual(health[0]['status'],'실패')

    def test_notification_error_does_not_contain_secret(self):
        from urllib.error import URLError
        item={'score':10,'title':'AI free API','url':'https://example.org/'}
        with patch.dict(radar.os.environ,{'DISCORD_WEBHOOK_URL':'https://discord.com/api/webhooks/SECRET','TELEGRAM_BOT_TOKEN':'','TELEGRAM_CHAT_ID':''}),patch.object(radar,'urlopen',side_effect=URLError('https://discord.com/api/webhooks/SECRET')):
            ok,detail=radar.notify([item],{})
            self.assertFalse(ok)
            self.assertNotIn('SECRET',detail)

    def test_csv_formula_is_escaped(self):
        item=radar.standard_item('test','=AI API free credits','https://example.org/')
        item.update(tags=[],score=10,first_seen=radar.stamp(radar.now()),credibility='test')
        with tempfile.TemporaryDirectory() as folder,patch.object(radar,'SITE',Path(folder)):
            radar.write_site({'items':{item['id']:item}},[],{})
            rows=list(csv.reader(io.StringIO((Path(folder)/'results.csv').read_text(encoding='utf-8-sig'))))
            self.assertTrue(rows[1][0].startswith("'="))
