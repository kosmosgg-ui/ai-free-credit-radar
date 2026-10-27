#!/usr/bin/env python3
"""무료 AI 쌀먹 레이더: 표준 라이브러리로 수집/필터/중복 제거/알림/HTML 생성.
외부 사이트가 403/429를 반환하면 차단을 우회하지 않고 실패 사유를 기록합니다.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import hashlib
import html
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse, urlunparse, parse_qsl
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'config.json'
STATE = ROOT / 'data' / 'state.json'
SITE = ROOT / 'site'
UTC = timezone.utc
USER_AGENT = 'SsalRadar/1.0 (public-feed-monitor; polite requests; contact: repository owner)'
POSITIVE = (
    ('쌀먹', 7), ('무료 크레딧', 7), ('무료 토큰', 7), ('무료 api', 7),
    ('free credits', 7), ('free credit', 7), ('free tokens', 7),
    ('free api', 7), ('free inference', 7), ('free tier', 5),
    ('무료 제공', 5), ('무료체험', 5), ('무료 체험', 5),
    ('trial credits', 7), ('promo code', 6), ('coupon code', 6),
    ('프로모션', 4), ('크레딧', 4), ('credits', 4),
    ('무료', 3), ('free', 3), ('체험판', 3), ('trial', 2),
    ('증정', 4), ('이벤트', 2), ('할인', 2), ('discount', 2),
)
AI_HINTS = ('ai', '인공지능', 'llm', 'api', '토큰', 'token', '모델', 'model',
            'inference', '추론', '클로드', 'chatgpt', 'gemini', '제미나이',
            'openrouter', 'groq', 'cerebras', 'anthropic', 'openai',
            'kimi', '코덱스', 'codex', 'cursor', 'mistral', 'nvidia',
            '클라우드', 'huggingface', '허깅페이스', 'generative')
BLOCK_TERMS = ('계정 매매', '계정 판매', '공유 계정 판매', '크랙', 'cracked',
               'stolen key', '탈취', '불법 우회', '약관 우회', '무한 계정 생성')
OFFICIAL_HOSTS = ('ai.google.dev','cloud.google.com','docs.cloud.google.com',
                  'developers.cloudflare.com','openrouter.ai','groq.com',
                  'docs.mistral.ai','huggingface.co','openai.com',
                  'anthropic.com','cerebras.ai','build.nvidia.com',
                  'docs.nvidia.com','console.groq.com')
ATOM = '{http://www.w3.org/2005/Atom}'


def now():
    return datetime.now(UTC)


def stamp(dt):
    if dt is None:
        return None
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def parse_time(value):
    if not value:
        return None
    try:
        x = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        try:
            x = parsedate_to_datetime(value)
        except (ValueError, TypeError, IndexError):
            return None
    if x.tzinfo is None:
        x = x.replace(tzinfo=UTC)
    return x.astimezone(UTC)


def clean(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', ' ', str(s or '')))).strip()[:500]


def safe_url(raw):
    try:
        p = urlparse(raw)
        if p.scheme not in ('http', 'https') or not p.netloc or p.username or p.password:
            return ''
        return urlunparse((p.scheme, p.netloc.lower(), p.path, p.params, p.query, ''))
    except ValueError:
        return ''


def key_for(title, url):
    """뉴스처럼 같은 제목/다른 검색 질의로 반복되는 결과를 함께 묶습니다."""
    t = clean(title).lower()
    t = re.sub(r'\s+[-|]\s+[^-|]{2,50}$', '', t)  # 언론사 꼬리표 제거
    t = re.sub(r'[^\w가-힣]+', '', t, flags=re.UNICODE)
    if len(t) >= 12:
        basis = 'title:' + t
    else:
        p = urlparse(url)
        q = [(k,v) for k,v in parse_qsl(p.query) if k.lower() not in ('utm_source','utm_medium','utm_campaign','fbclid')]
        basis = 'url:' + p.netloc + p.path + urlencode(q)
    return hashlib.sha256(basis.encode()).hexdigest()[:20]


def fetch(url, *, timeout=15):
    req = Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/rss+xml, application/atom+xml, application/json, text/html;q=0.8, */*;q=0.6'})
    with urlopen(req, timeout=timeout) as response:
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError('응답 크기 2 MB 초과; 수집 중단')
        charset = response.headers.get_content_charset() or 'utf-8'
        return raw.decode(charset, errors='replace')


def standard_item(source, title, url, published=None, snippet=''):
    title, url = clean(title), safe_url(url)
    if len(title) < 4 or not url:
        return None
    return {'id':key_for(title,url), 'source':source,'title':title,'url':url,
            'published_at':stamp(published), 'snippet':clean(snippet),
            'first_seen':None, 'last_seen':None}


def rss_items(xml_text, source):
    root = ET.fromstring(xml_text)
    out = []
    for node in root.findall('.//item'):
        title = node.findtext('title', default='')
        url = node.findtext('link', default='')
        snippet = node.findtext('description', default='')
        item = standard_item(source, title, url, parse_time(node.findtext('pubDate')), snippet)
        if item:
            out.append(item)
    # Atom feeds, e.g. custom sources in future
    for node in root.findall(f'.//{ATOM}entry'):
        link = node.find(f'{ATOM}link')
        url = link.get('href','') if link is not None else ''
        title = node.findtext(f'{ATOM}title', default='')
        snippet = node.findtext(f'{ATOM}summary', default='')
        date = parse_time(node.findtext(f'{ATOM}updated', default=''))
        item = standard_item(source,title,url,date,snippet)
        if item:
            out.append(item)
    return out


class DCGalleryParser(HTMLParser):
    """AI 활용 갤 공개 목록의 제목만 읽는다. 로그인/CAPTCHA 우회 없음."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.row = None
        self.row_depth = 0
        self.capture = False
        self.buffer = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = set(a.get('class','').split())
        if tag == 'tr':
            if self.row is not None:
                self.row_depth += 1
            elif 'ub-content' in classes and a.get('data-no','').isdigit():
                self.row = {'no': a['data-no'], 'title':'', 'url':'', 'date':''}
                self.row_depth = 1
        if self.row is None:
            return
        if tag == 'td' and 'gall_date' in classes:
            self.row['date'] = a.get('title','')
        if tag == 'a':
            link = html.unescape(a.get('href',''))
            if 'board/view' in link and 'id=ai_utilize' in link and 'no=' in link and not self.row['url']:
                self.capture = True
                self.buffer = []
                self.row['url'] = urljoin('https://gall.dcinside.com/',link)

    def handle_data(self, data):
        if self.row is not None and self.capture:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if self.row is None:
            return
        if tag == 'a' and self.capture:
            title = clean(' '.join(self.buffer))
            if title:
                self.row['title'] = title
            self.capture = False
        if tag == 'tr':
            self.row_depth -= 1
            if self.row_depth == 0:
                if self.row['title'] and self.row['url']:
                    self.rows.append(self.row)
                self.row = None


def dc_items(page_html):
    parser = DCGalleryParser()
    parser.feed(page_html)
    out = []
    for x in parser.rows:
        date = parse_time(x['date'].replace(' ', 'T')+'+09:00') if x['date'] else None
        item = standard_item('AI 활용 갤러리',x['title'],x['url'],date)
        if item:
            out.append(item)
    return out


def hn_items(text):
    obj = json.loads(text)
    out = []
    for hit in obj.get('hits', []):
        title = hit.get('title') or hit.get('story_title') or ''
        url = 'https://news.ycombinator.com/item?id=' + str(hit.get('objectID',''))
        item = standard_item('Hacker News', title, url, parse_time(hit.get('created_at')),
                             hit.get('story_text') or '')
        if item:
            out.append(item)
    return out


def score_item(item):
    s = (item['title'] + ' ' + item.get('snippet','')).lower()
    if any(x in s for x in BLOCK_TERMS):
        return 0, ['규정 위반 의심']
    positives = [(term,weight) for term,weight in POSITIVE if term in s]
    if not positives:
        return 0, []
    # 같은 단어 하위 일치를 중복 계산하지 않도록 가중치 상위 2개만 사용
    best = sorted((v for _,v in positives), reverse=True)[:2]
    ai = any(re.search(r'(?<![a-z])'+re.escape(x)+r'(?![a-z])', s) if x in ('ai','api','llm') else x in s for x in AI_HINTS)
    if not ai and item['source'] != 'AI 활용 갤러리':
        return 0, []
    score = sum(best) + (3 if ai else 2)
    if item['source'] == 'AI 활용 갤러리':
        score += 1
    labels = []
    if any(t in s for t in ('api','토큰','token','inference','llm')):
        labels.append('API·토큰')
    if any(t in s for t in ('credit','크레딧','쿠폰','promo','프로모션')):
        labels.append('크레딧·혜택')
    if any(t in s for t in ('trial','체험','free tier')):
        labels.append('체험·무료등급')
    return min(score, 25), labels or ['무료정보']


def credibility(item):
    host = (urlparse(item['url']).hostname or '').lower()
    if any(host == h or host.endswith('.'+h) for h in OFFICIAL_HOSTS):
        return '공식 도메인 게시물 · 조건 별도 확인'
    if item['source'] == 'AI 활용 갤러리' or item['source'] == 'Hacker News':
        return '커뮤니티 제보 · 검증 필요'
    return '뉴스 검색 결과 · 공식 확인 필요'


def collect(config):
    gathered, health = [], []
    sources = config.get('sources',{})
    jobs = []
    official = {}
    for page in sources.get('official_pages', []):
        if page.get('enabled', True):
            official[page['url']] = page
            jobs.append((page['name'], page['url'], 'official'))
    for name, region, locale in [('google_news_ko','KR','ko'),('google_news_en','US','en')]:
        obj = sources.get(name,{})
        if not obj.get('enabled',False):
            continue
        for query in obj.get('queries',[]):
            params = urlencode({'q':query+' when:7d','hl':f'{locale}-{region}', 'gl':region,'ceid':f'{region}:{locale}'})
            jobs.append(('Google News · '+('한국' if locale=='ko' else '해외'),
                         'https://news.google.com/rss/search?'+params,'rss'))
    if sources.get('hacker_news',{}).get('enabled',False):
        for query in sources['hacker_news'].get('queries',[]):
            params = urlencode({'query':query,'tags':'story','hitsPerPage':30})
            jobs.append(('Hacker News','https://hn.algolia.com/api/v1/search_by_date?'+params,'hn'))
    dc = sources.get('dc_ai_gallery',{})
    if dc.get('enabled',False):
        for page in range(1, min(3, max(1, int(dc.get('pages',1))))+1):
            jobs.append(('AI 활용 갤러리',
                         f'https://gall.dcinside.com/mgallery/board/lists/?id=ai_utilize&list_num=100&page={page}', 'dc'))
    for i,(name,url,kind) in enumerate(jobs):
        try:
            raw = fetch(url)
            if kind == 'rss':
                items = rss_items(raw,name)
            elif kind == 'hn':
                items = hn_items(raw)
            elif kind == 'official':
                page = official[url]
                text = clean_document(raw)
                match = next((re.search(re.escape(term), text, re.I)
                              for term in page['required_terms']
                              if re.search(re.escape(term), text, re.I)), None)
                if not match:
                    raise ValueError('공식 무료 안내 문구 미확인; 조건 또는 페이지 변경 확인 필요')
                evidence = text[max(0, match.start()-40):match.end()+160]
                item = standard_item(name, page['title'], url, snippet=evidence)
                item['verified_at'] = stamp(now())
                item['verification'] = 'official_page_text_only'
                items = [item]
            else:
                items = dc_items(raw)
                if not items:
                    raise ValueError('게시글 목록 인식 불가(접근 제한 또는 HTML 변경 가능)')
            gathered.extend(items)
            health.append({'source':name,'status':'성공','count':len(items),'detail':''})
        except (HTTPError,URLError,TimeoutError,ValueError,ET.ParseError,json.JSONDecodeError) as e:
            # 403/429에 대한 재시도/우회 없음. 수집 실패가 UI에 표시됨.
            health.append({'source':name,'status':'실패','count':0,'detail':str(e)[:150]})
        if i < len(jobs)-1:
            time.sleep(1.1)
    return gathered, health


def clean_document(raw):
    raw = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', raw, flags=re.I | re.S)
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', ' ', raw))).strip()


def load_state():
    if STATE.exists():
        try:
            obj = json.loads(STATE.read_text(encoding='utf-8'))
            if isinstance(obj.get('items'), dict):
                return obj
        except (OSError, ValueError):
            # 파일 오류는 기록을 덮어써 알림을 중복 발송하는 상황을 막기 위해 중단
            raise RuntimeError('state.json 손상. 자동으로 초기화하지 않습니다. 수동 복구하세요.')
    return {'initialized':False,'items':{},'notified':[], 'last_checked':None}


def atomic_json(path, obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp = path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
    tmp.replace(path)


def merge(existing, fresh, config, current):
    cutoff = current-timedelta(days=max(1,int(config.get('max_age_days',14))))
    items = existing.get('items',{})
    # 과거에 수집했던 동일 ID는 갱신하되, 최초 발견 시각은 유지
    changed = []
    for item in fresh:
        published = parse_time(item['published_at'])
        if published and (published < cutoff or published > current+timedelta(days=1)):
            continue
        score,tags = score_item(item)
        if score == 0:
            continue
        item['score'] = score
        item['tags'] = tags
        item['credibility'] = credibility(item)
        item['last_seen'] = stamp(current)
        old = items.get(item['id'])
        if old:
            item['first_seen'] = old['first_seen']
            # 같은 제목에 여러 출처: 이미 보유한 링크를 우선 유지
            item['url'] = old.get('url',item['url'])
            item['source'] = old.get('source',item['source'])
            if not item['published_at']:
                item['published_at'] = old.get('published_at')
            item['credibility'] = credibility(item)
        else:
            item['first_seen'] = stamp(current)
            changed.append(item['id'])
        items[item['id']] = item
    # 오래되거나 과거 제보인 경우 제거 (거짓 유효기간 표시 방지)
    items = {k:v for k,v in items.items() if (parse_time(v.get('verified_at') or v.get('published_at') or v.get('first_seen')) or current) >= cutoff}
    sorted_items = sorted(items.values(), key=lambda x: (x.get('published_at') or x['first_seen']), reverse=True)
    top = sorted_items[:max(1,int(config.get('max_items',250)))]
    existing['items'] = {x['id']:x for x in top}
    existing['notified'] = [x for x in existing.get('notified',[]) if x in existing['items']]
    existing['last_checked'] = stamp(current)
    return existing, changed


def notify(items, config):
    """알림 대상이 없는 경우 성공. 설정된 채널 중 실패하면 재시도 대상 유지."""
    if not items:
        return True, '알림 대상 없음'
    discord = os.getenv('DISCORD_WEBHOOK_URL','').strip()
    telegram_token = os.getenv('TELEGRAM_BOT_TOKEN','').strip()
    telegram_chat = os.getenv('TELEGRAM_CHAT_ID','').strip()
    if not discord and not (telegram_token and telegram_chat):
        return False, '알림 채널 미설정(대시보드에는 표시됨)'
    lines = ['🔎 무료 AI 쌀먹 레이더 · 새 제보 (혜택 검증 전)']
    for item in items[:6]:
        lines.append(f"• [{item['score']}점] {item['title'][:90]}\n  {item['url']}")
    if len(items) > 6:
        lines.append(f'외 {len(items)-6}건: 대시보드에서 확인')
    message = '\n'.join(lines)[:1800]
    ok = True
    errors = []
    if discord:
        if not discord.startswith('https://'):
            ok = False; errors.append('Discord 웹훅은 HTTPS 필요')
        else:
            try:
                payload = json.dumps({'content':message, 'allowed_mentions':{'parse':[]}},ensure_ascii=False).encode()
                req = Request(discord,data=payload,headers={'Content-Type':'application/json','User-Agent':USER_AGENT})
                with urlopen(req,timeout=15):
                    pass
            except (HTTPError,URLError,TimeoutError) as e:
                ok = False; errors.append('Discord 전송 실패 ('+type(e).__name__+')')
    if telegram_token and telegram_chat:
        try:
            target = 'https://api.telegram.org/bot'+telegram_token+'/sendMessage'
            payload = urlencode({'chat_id':telegram_chat,'text':message,'disable_web_page_preview':'true'}).encode()
            req = Request(target,data=payload,headers={'User-Agent':USER_AGENT})
            with urlopen(req,timeout=15) as response:
                obj = json.loads(response.read().decode())
                if not obj.get('ok'):
                    raise ValueError('Telegram API 응답 실패')
        except (HTTPError,URLError,TimeoutError,ValueError) as e:
            ok = False; errors.append('Telegram 전송 실패 ('+type(e).__name__+')')
    return ok, ', '.join(errors) if errors else '전송 성공'


def write_site(state, health, config, *, demo=False):
    SITE.mkdir(exist_ok=True)
    items = sorted(state['items'].values(),key=lambda x: (x.get('published_at') or x.get('first_seen') or ''),reverse=True)
    report = {'project':config.get('project_name','무료 AI 쌀먹 레이더'),
              'checked_at':state.get('last_checked'), 'demo':demo,
              'notice':'공식 안내 문구 확인과 뉴스/커뮤니티 제보를 구분합니다. API 호출, 계정별 자격 및 크레딧 지급은 검증하지 않았습니다.',
              'health':health,'items':items}
    atomic_json(SITE/'data.json',report)
    # 웹페이지에서 JSON을 안전하게 인라인 삽입. 로컬 파일로 열어도 표시됨.
    embedded = json.dumps(report,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    template = (ROOT/'dashboard.template.html').read_text(encoding='utf-8')
    (SITE/'index.html').write_text(template.replace('__INLINE_DATA__',embedded),encoding='utf-8')
    with (SITE/'results.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['제목','분류','점수','출처','게시일(UTC)','최초수집(UTC)','검증','링크'])
        for x in items:
            row = [x['title'],' / '.join(x['tags']),x['score'],x['source'],
                   x.get('published_at'),x['first_seen'],x['credibility'],x['url']]
            writer.writerow([("'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v) for v in row])


def demonstration():
    t = now()
    samples = [
        ('예시: 신규 AI API 무료 크레딧 안내 (가상 데이터)','https://example.com/demo/free-ai-credit',2,'Google News · 한국'),
        ('예시: LLM free inference API promotion (synthetic)','https://example.com/demo/inference',7,'Hacker News'),
        ('예시: 무료 토큰 이벤트 공유 (데모, 실존 혜택 아님)','https://example.com/demo/tokens',15,'AI 활용 갤러리')
    ]
    state = {'initialized':True,'items':{},'notified':[],'last_checked':stamp(t)}
    for title,url,hours,source in samples:
        item = standard_item(source,title,url,t-timedelta(hours=hours))
        sc,tags = score_item(item)
        item.update(score=sc,tags=tags,credibility=credibility(item),
                    first_seen=stamp(t),last_seen=stamp(t))
        state['items'][item['id']]=item
    write_site(state,[{'source':'모의 자료','status':'데모','count':3,'detail':'실제 서비스에 연결하지 않음'}],
               json.loads(CONFIG.read_text(encoding='utf-8')),demo=True)
    print('데모 생성 완료: site/index.html (실제 정보 아님)')


def once():
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    previous = load_state()
    raw, health = collect(config)
    current = now()
    if not raw and not any(h['status'] == '성공' for h in health):
        failed = dict(previous, last_checked=stamp(current))
        write_site(failed,health,config)
        print('모든 수집이 실패했습니다. 기존 기록을 유지하고 실패 상태를 화면에 표시합니다.',file=sys.stderr)
        for h in health:
            print(' -',h['source'],h['status'],h['detail'],file=sys.stderr)
        return 2
    state, ids = merge(previous,raw,config,current)
    initialized = bool(previous['initialized'])
    state['initialized'] = True
    pending = [x for x in state['items'].values() if x['id'] not in state['notified']
               and x.get('score',0) >= int(config.get('alert_min_score',7))
               and parse_time(x.get('first_seen')) and parse_time(x['first_seen']) >= current-timedelta(hours=48)]
    pending.sort(key=lambda x:x['first_seen'],reverse=True)
    # 최초 실행에는 과거 발견한 수백 건을 알리지 않음
    if not initialized:
        state['notified'].extend(x['id'] for x in pending)
        print('첫 실행: 기존 목록 기준선 저장(과거 제보 알림 생략)')
    elif pending:
        pending = pending[:6]
        ok, detail = notify(pending,config)
        print('알림:',detail)
        if ok:
            state['notified'].extend(x['id'] for x in pending)
    # 메인 저장 성공 후 정적 사이트 생성
    atomic_json(STATE,state)
    write_site(state,health,config)
    print(f"수집 {len(raw)}건 / 신규 {len(ids)}건 / 대시보드 {len(state['items'])}건")
    for h in health:
        if h['status']!='성공':
            print('수집 실패:',h['source'],h['detail'])
    return 0


def main():
    parser = argparse.ArgumentParser(description='무료 AI 쌀먹 정보 자동 수집기')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--demo',action='store_true',help='실제 수집 없이 가상 데이터로 화면 생성')
    group.add_argument('--watch',type=int,metavar='MINUTES',help='PC 켜진 동안 주기적 수집(최소 5분)')
    group.add_argument('--once',action='store_true',help='1회 수집(기본값)')
    args = parser.parse_args()
    if args.demo:
        demonstration(); return
    if args.watch is not None and args.watch < 5:
        parser.error('--watch 주기는 최소 5분입니다')
    while True:
        try:
            result = once()
        except (OSError,RuntimeError,ValueError) as e:
            print('치명 오류:',e,file=sys.stderr)
            sys.exit(1)
        if args.watch is None:
            sys.exit(result)
        print(f'{args.watch}분 후 다음 검사 (Ctrl+C 종료)',flush=True)
        try:
            time.sleep(args.watch*60)
        except KeyboardInterrupt:
            print('종료'); return

if __name__ == '__main__':
    main()
