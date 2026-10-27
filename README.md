# 🔎 무료 AI 쌀먹 레이더 v1.0

## 2026-10-27 실행 검증 및 보완

- Python 3.12 기본 라이브러리만 사용합니다. 별도 pip 설치나 AI API 키가 필요 없습니다.
- 공식 Gemini, Cloudflare Workers AI, OpenRouter 안내 페이지를 직접 수집하고 무료 안내 문구가 있을 때만 등록합니다. 공식 확인 시각과 API 호출·크레딧 지급 미검증 상태를 표시합니다.
- 공식 안내는 게시일을 임의 생성하지 않습니다. 재확인 시각으로 자료의 유지 기간을 계산합니다.
- 전체 수집 실패 시 기존 상태를 유지하면서 실패 내역을 새 화면에 표시하고 종료 코드 2를 반환합니다. Actions는 실패 화면을 배포한 뒤 실패를 보고합니다.
- 알림 오류에 비밀 URL/토큰이 포함되지 않도록 수정했고 CSV 수식 실행을 방지했습니다. 한 번에 실제 전송하는 최대 6건만 전송 완료로 기록합니다.
- 자동 테스트: `python -m unittest discover -s tests -v`.
- 제한된 Windows 실행 환경에서 임시 폴더 오류가 발생하면 프로젝트 외부의 쓰기 가능한 임시 폴더를 만들고 TEMP/TMP를 해당 경로로 지정한 뒤 테스트합니다.
- 30분 예약은 GitHub 실행 대기 상태에 따라 지연될 수 있습니다. 공개 저장소의 예약 작업은 장기간 활동이 없으면 비활성화될 수 있으므로 Actions 상태를 확인하세요.
- 무료 혜택의 계정별 제공 여부, 가입/결제 조건, API 추론 호출, 실제 크레딧 지급, Discord/Telegram 수신은 별도 검증 대상입니다.

**무료 AI API·토큰·크레딧·프로모션을 찾아서 모아 주는 Python 자동 모니터.** 추가 Python 패키지/유료 API 없음.

## 제공 기능

- AI 활용 갤러리(공개 게시글 목록), Google News 한국/해외 RSS, Hacker News 공개 검색 API
- 간단한 관련도 점수화/중복 제거/최근 14일 정보 유지/CSV 저장
- 디스코드 Webhook 또는 텔레그램 봇으로 **신규 발견 항목만** 알림
- 검색·출처 필터·점수 정렬이 있는 반응형 대시보드 (`site/index.html`)
- 작업 실패/403/429/디시 HTML 구조 변경 오류 표시. 차단·로그인·캡차 우회는 하지 않음.
- GitHub Actions (기본 약 30분 간격) + GitHub Pages로 PC 꺼도 모니터링 가능

## 가장 쉬운 설치: Windows

1. 이 ZIP을 풀고 **Python 3.10 이상**을 설치합니다.
2. `Windows_한번_수집.bat` 더블클릭 (또는 `python radar.py --once`).
3. 생성된 `site/index.html`을 브라우저에서 열면 됩니다.
4. PC가 켜진 동안 주기적으로 확인하려면 `Windows_계속_감시.bat` 사용.
5. 테스트 화면만 보고 싶다면 `python radar.py --demo` (※ 실제 혜택이 아닌 가상 자료로 출력됩니다. 데모는 `data/state.json`을 건드리지 않습니다.)

**처음 실행은 수집 목록을 저장하는 기준선 단계여서 과거 게시글 알림을 보내지 않습니다.** 그다음부터 새 항목을 알립니다.

## PC 꺼도 자동으로: GitHub Actions + Pages

1. **별도 공개 저장소** (예: `ai-free-credit-radar`)를 만들고 이 폴더의 내용 전체를 **루트**에 업로드합니다. 개인 게임 프로젝트에 섞지 않는 편이 안전합니다.
2. 저장소 `Settings → Pages → Build and deployment → Source`에서 **GitHub Actions**를 선택합니다.
3. 저장소 `Actions → AI Free Credit Radar → Run workflow`로 첫 실행을 시작합니다.
4. Actions 성공 후 `Settings → Pages`의 방문 주소에서 대시보드를 확인합니다. 일반적인 주소는 `https://<사용자명>.github.io/<저장소명>/`이지만 실제 주소는 GitHub Pages 설정에서 확인하세요.
5. 이후 workflow가 UTC 기준 매시 13분, 43분 실행을 시도합니다. GitHub 스케줄은 지연/누락될 수 있으며 **초단위 실시간이 아닙니다.**

> GitHub Pages 사이트는 공개됩니다. 내용이 공개 제보뿐인지 확인하고 토큰/웹훅/개인정보를 코드·설정·JSON에 넣지 마세요. workflow가 상태를 저장하려면 기본 브랜치에 Actions의 쓰기 권한이 필요합니다. 저장소 `Settings → Actions → General → Workflow permissions`를 확인하고 브랜치 보호 규칙이 자동 푸시를 막지 않는지도 확인하세요.

## 휴대폰 알림 설정 (둘 중 하나)

### 디스코드

- 디스코드 서버 채널 설정에서 **연동 → 웹훅 → 새 웹훅** 생성, 웹훅 URL 복사.
- GitHub 저장소 `Settings → Secrets and variables → Actions → New repository secret`에 이름 `DISCORD_WEBHOOK_URL`로 등록.
- Windows 사용 시 환경변수 `DISCORD_WEBHOOK_URL`을 설정한 뒤 실행.

### 텔레그램

- Telegram `@BotFather`에서 봇을 만들고 토큰을 확보합니다.
- 봇에게 메시지를 하나 보낸 후 Telegram Bot API `getUpdates`를 이용해 대상 `chat_id`를 확인합니다.
- GitHub Secrets에 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 등록.
- 다른 사람과 API 키나 웹훅 URL을 공유하지 마세요.

알림 채널이 설정되지 않아도 대시보드에는 결과가 남습니다. 알림 실패한 항목은 다음 실행에 재시도합니다(처음 기준선의 과거 항목 제외).

## 검색/설정 바꾸기

`config.json` 수정:

- `sources.*.enabled`: 수집원 켜기/끄기.
- `sources.google_news_ko.queries` 등: 검색 문구 변경.
- `sources.dc_ai_gallery.pages`: AI 갤 공개 게시글 수집 페이지 수(최대 3, 기본 1).
- `alert_min_score`: 알림 문턱 점수 (기본 7).
- `max_age_days`: 최근 정보 보관일 (기본 14).

**점수는 단순 키워드 관련도이지 실제 프로모션의 신뢰도/유효기간을 뜻하지 않습니다.** `공식 확인 필요` 표시된 링크는 직접 조건 확인이 필요합니다. Google News는 뉴스 검색을 통해 수집하므로 자료 누락, 뉴스 링크 경유, 지연이 가능합니다.

## 정상 동작 확인/제한

- 실행: `python -m unittest discover -s tests -v`
- 공개 페이지에 대한 통신은 실제 네트워크에서만 가능합니다. 일부 환경에서 접근을 차단해도 우회하지 않습니다.
- 디시 수집은 2026년 10월 공개 AI 활용 갤러리의 목록 구조 기준으로 만든 실험 기능입니다. HTML 구조 변경 시 실패로 기록됩니다.
- Google News/Hacker News 검색이 모든 공지를 포함하진 않습니다. 또한 게시글은 발표·진행·종료 여부가 확인되지 않은 제보입니다.
- Reddit RSS는 2026년 11월 13일 종료 예정이라서 기본 수집원에 넣지 않았습니다.
- 폴링 간격보다 빠르게 올라왔다 사라지는 게시물은 누락될 수 있습니다. 삭제·철회·종료 여부를 자동으로 확정하지 않습니다.
- 알림 전송 성공 후 저장/푸시가 실패하면 중복 알림이 발생할 수 있습니다.
- GitHub Pages/Actions와 대상 서비스의 정책/무료 제공 범위는 바뀔 수 있습니다. 공개 저장소가 아닌 경우 비용이 발생할 수 있습니다.

## 소스 참고

- GitHub Actions 스케줄: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- GitHub Pages 배포: https://github.com/actions/deploy-pages
- Algolia HN 검색 API: https://hn.algolia.com/api
- AI 활용 갤러리: https://gall.dcinside.com/mgallery/board/lists/?id=ai_utilize
- Google News RSS 개요: https://feeder.co/knowledge-base/rss-feed-creation/google-news-rss-feeds/

## 보안/윤리

공식 프로모션 규정을 준수하세요. 다계정 남용, 결제 인증 우회, 유출 API 키 활용, 크레딧 거래는 지원하지 않습니다. 이 프로그램은 **공개된 안내를 모으는 도구**이며 자동 가입이나 계정 생성 기능은 없습니다.
