# 채용공고 수집

채용 사이트에서 공고 목록과 상세 요강을 받아 JSONL로 남긴다. 여기서 나온 원본을
`job_matching_bot/sync.py`가 정제·중복제거·임베딩해 벡터 인덱스에 적재한다.
이 모듈은 수집까지만 책임지고, 그 뒤 단계는 건드리지 않는다.

## 수집 규칙

크롤링은 상대 서버에 부담을 주는 행위다. 아래는 지키기로 정한 선이고, 편의를 위해
느슨하게 바꾸지 않는다. 코드에도 같은 내용이 강제돼 있다.

1. **robots.txt가 허용한 경로만 요청한다.** 목록과 상세, 두 경로뿐이다.
   허용 목록(`ALLOWED_PATH_PREFIXES`)에 없는 경로는 코드가 요청 자체를 막는다.
   로그인·검색·관리 페이지는 대상이 아니다.

2. **요청 간격을 둔다.** 상세를 열 때마다 3~5초 쉰다. 목록 페이지 사이에도 대기를 둔다.
   한 번에 몰아서 받지 않고, 1,000건 단위로 끊어 실행한다.

3. **차단 신호가 오면 즉시 멈춘다.** 429 응답이나 차단 안내 문구
   (`BLOCK_PAGE_MARKERS`)가 감지되면 스크립트가 그 자리에서 종료된다.
   재시도로 밀어붙이거나 우회하지 않는다.

4. **신원을 숨기지 않는다.** User-Agent는 하나로 고정한다. 무작위로 바꾸지 않고,
   프록시나 IP 로테이션도 쓰지 않는다. 차단을 피하려고 정체를 감추는 기법은 쓰지 않는다.

5. **공개된 것만 받는다.** 로그인해야 보이는 정보, 지원자 정보, 개인정보는 대상이 아니다.
   받는 것은 기업이 공개한 채용공고 본문과 조건뿐이다.

6. **캡차는 풀지 않는다.** 캡차가 뜨면 사람이 보고 판단한다. 자동으로 통과시키지 않는다.

## 폴더 구성

| 파일 | 역할 |
|---|---|
| `http_session.py` | HTTP 세션. UA 고정, 대기, 차단 감지가 여기 있다 |
| `crawl_list.py` | 목록 수집. 카테고리·정렬·페이지 크기를 인자로 받는다 |
| `crawl_detail.py` | 상세 요강 수집. 목록에서 얻은 링크를 순회한다 |
| `detail_queue.py` | 상세 수집 순서를 정한다. 인기 배지 → 목록 순위 → 마감일 순 |
| `nightly.py` | 야간 배치. 목록 sweep → 신규 상세 → 링크 확인 → 적재를 한 번에 돈다 |
| `schedule_nightly.ps1` | 야간 배치를 Windows 작업 스케줄러에 등록·해제·확인한다 |

수집 결과는 `job_matching_bot/artifacts/raw/`에 쌓인다. 저장소에 올리지 않는다.

## 실행

저장소 루트에서 패키지 모듈로 실행한다.

```powershell
pip install -r requirements.txt

# 전체 카테고리를 지원순으로 수집
python -m job_matching_bot.crawling.crawl_list --all-categories --sort AD --page-count 100

# 상세 수집 순서를 정하고
python -m job_matching_bot.crawling.detail_queue

# 상세 요강을 받는다. 1,000건씩 끊어 돌린다
python -m job_matching_bot.crawling.crawl_detail --limit 1000
```

목록만으로는 자격요건을 알 수 없어 상세 요강이 반드시 필요하다. 상세가 이미지로만
되어 있는 공고는 텍스트를 뽑을 수 없으므로 `body_is_image`로 표시해 두고, 매칭에서는
기업이 고른 기술 태그로만 판단한다.

## 야간 배치

매일 밤 한 번 `nightly.py`가 돈다. 목록을 끝까지 훑어 신규를 찾고, 상세를 받고,
저장소와 인덱스를 맞춘다.

```powershell
python -m job_matching_bot.crawling.nightly                  # 오늘 몫
python -m job_matching_bot.crawling.nightly --dry-run        # 목록만 훑고 계획만 본다
python -m job_matching_bot.crawling.nightly --full           # 전 대분류를 강제로
python -m job_matching_bot.crawling.nightly --max-minutes 300
```

| 요일 | 훑는 대분류 | 목록 | 상세 |
|---|---|---|---|
| 월~토 | IT개발·데이터, 연구·R&D, 디자인, 기획·전략 | 약 250쪽, 15분 | 신규 약 1,000건, 1시간 |
| 일 | 운전·운송·배송을 뺀 14개 전부 | 약 1,760쪽, 2~3시간 | 신규는 시간 한도까지, 나머지는 다음 밤에 |

- **사라짐 판정.** 목록에서 본 (공고, 대분류)를 저장소 `list_seen`에 남긴다. 끝까지 훑은
  대분류에서 안 보인 공고만 "안 보였다"로 세고, 이틀 연속이면 삭제한다. 주 1회 훑는
  대분류의 공고는 마지막 관측 뒤 15일까지 살아 있는 것으로 본다. 차단 등으로 sweep이
  중간에 끊기면 그날은 아무것도 지우지 않는다.
- **링크 확인.** 삭제로 넘어가기 직전인 공고는 상세 페이지를 열어 본다. 아직 열려 있으면
  지우지 않는다. 하룻밤 상한이 있어 시간을 다 쓰지 않는다.
- **시간 한도.** 기본 7시간. 목록과 링크 확인을 먼저 하고 남는 시간에 상세를 받는다.
  못 받은 신규는 다음 밤에 인기 배지 → 목록 순위 → 마감 순으로 이어서 받는다.
- 결과는 `artifacts/nightly/<날짜>-<시작 시각>.json`(예: `2026-09-13-2300.json`)에, 목록은
  `artifacts/raw/sweeps/<날짜>-<시작 시각>.json`(14일 보관)에 남는다. **시각을 붙이는 까닭:** 날짜만
  쓰던 때 같은 날 두 번 돈 배치(00:55 재실행, 23:00 정기)가 서로 파일을 덮어썼다.
- 받은 상세는 `artifacts/raw/details/<날짜>.jsonl`에 **덧붙인다.** 같은 날 다시 돌리면 이미 받은
  상세를 건너뛰고 이어 받게 일부러 날짜 하나로 둔다.

**스케줄 등록.** 작업 스케줄러에 매일 23:00으로 건다. 가상환경 python을 쓰고 로그는
`artifacts/nightly/log/<날짜>.log`에 남는다. 노트북이 꺼져 있던 밤은 건너뛰고 다음 밤에 이어서 받는다.

```powershell
.\job_matching_bot\crawling\schedule_nightly.ps1 -Register     # 등록
.\job_matching_bot\crawling\schedule_nightly.ps1 -Status       # 다음·마지막 실행 확인
.\job_matching_bot\crawling\schedule_nightly.ps1 -RunNow       # 지금 한 번
.\job_matching_bot\crawling\schedule_nightly.ps1 -Unregister   # 해제
```

## 수집 이후

원본 JSONL은 `job_matching_bot/sync.py`가 받아서 처리한다.

```
원본 JSONL → 유효성 검사 → 중복 제거 → 최신 레코드 선택 → 필드 정규화
→ 본문 정제 → 상태·품질 판정 → 변경 여부 확인 → 임베딩 → 벡터 인덱스 적재
```

임베딩은 요건 구간과 검색 필터 값으로 만든 지문(`embed_hash`)이 바뀐 공고만 다시 한다.
같은 공고를 여러 번 받아도, 마감일이나 수집 시각만 달라져도 임베딩 비용은 들지 않는다.
