# 채용공고 추천봇

이력서를 받아 맞는 채용공고를 골라 주고, **왜 맞는지를 양쪽 원문 인용으로** 보여 준다.
공고는 채용 사이트에서 수집해 Pinecone에 임베딩으로 담아 두고, 추천할 때마다
이력서로 그 인덱스를 검색한다. 이력서는 저장하지 않는다 — 요청마다 질의로만 쓴다.

이력서 첨삭은 이 모듈이 하지 않는다. 사용자가 추천 목록에서 공고를 고르면 팀원의
첨삭 모듈(S32-17)이 그 공고 기준으로 첨삭을 맡는다. 두 모듈은 코드가 분리돼 있지만
실행은 한 프로세스다. 통합 서버(`cover_letter_rag/app/integrated.py`)가 이 앱을 `/`에
붙여 포트 8000 하나로 함께 띄운다.

## 문서

| 문서 | 내용 |
|---|---|
| [docs/data_preprocessing.md](docs/data_preprocessing.md) | 수집 데이터 규모·구조, 전처리 단계별 건수와 판단 근거 |
| [docs/architecture.md](docs/architecture.md) | 시스템 구조, 인덱싱·추천·챗봇 흐름, 프롬프트, RAG 가이드 대응 |
| [docs/modules.md](docs/modules.md) | 모듈 구조 — 폴더·파일별 역할, 누가 누구를 부르는지, 실행하는 것, 정리할 거리 |
| [docs/chatbot.md](docs/chatbot.md) | 공고 찾기 챗봇 — 갈래, 막는 것, 맥락 잇기, 조건 조회, 단계별 시간, 라우터 흔들림 |
| [docs/test_report.md](docs/test_report.md) | 테스트 계획, 사람 채점·챗봇 평가 결과, 트러블슈팅 |
| [docs/graphs/](docs/graphs/README.md) | 흐름도 mermaid 원본 |
| [crawling/README.md](crawling/README.md) | 수집 규칙과 야간 배치 |

함께 보는 README: [프로젝트 전체](../README.md) · [공고 맞춤 첨삭](../cover_letter_rag/README.md) ·
[앱의 AI 취업 코치 화면](../lib/README.md#ai-취업-코치-resumeai_coach)

## 어떻게 추천하는가

한 번의 요청이 일곱 단계를 지난다. 검색이나 하드 필터가 실패하면 추천을 내보내지
않는다(503) — 검색이 죽었는데 아무 공고나 내보내는 것보다 낫다. 나머지 단계는 실패해도
경고를 달고 계속한다. 질의문 생성이 실패하면 이력서 원문으로 검색하고, 마감 확인이
실패하면 전부 열려 있다고 보고, 재정렬에서 판정을 못 받은 공고는 "낮음"으로 두고 ⑤에서
세운 순서를 따른다.

```
① 이력서 → 검색 질의문           LLM. 이력서를 "공고 자격요건처럼" 고쳐 쓴다
② 벡터 검색 (상위 25)            Pinecone. 지역·고용형태·연차를 메타데이터로 거른다
③ 하드 필터                      규칙. 연차·학력·지역·고용형태·전공·자격증
④ 마감 확인                      후보 공고 페이지를 열어 조기 마감된 것을 뺀다
⑤ 기술 겹침으로 다시 세우기        규칙. 벡터 순위와 기술 겹침을 반씩 섞는다
⑥ LLM 재정렬 (상위 12, 병렬)      적합도(높음/보통/낮음) + 근거 + 우려
⑦ 근거 검증                      인용이 원문에 실제로 있는지 대조. 없으면 버린다
```

⑤를 넣은 이유: 벡터 유사도가 후보 안에서 거의 평평하다(실측 폭 0.042~0.140). 그 좁은
구간의 순서로 누구를 LLM에 보낼지 정하고 있었다. 기술 겹침은 넓게 흩어지고 LLM 판정과도
이어져서(높음 30% · 보통 19% · 낮음 10%), 둘을 섞으면 판정을 더 잘 예측한다. 이력서 6종의
후보 79건을 전부 판정시켜 재 본 순위상관이 벡터만 +0.26, 겹침만 +0.33, 반씩 섞어 +0.42다.
기술 태그가 없는 공고는 요건 구간 글에서 같은 어휘로 기술을 찾는다. 그래도 없으면
(OPEN 공고의 54%) **제자리에 남긴다** — 근거가 없는 것이지 안 맞는 것이 아니다.
자세한 것은 `matching/pre_ranker.py`.

①을 LLM에 맡기는 이유: 이력서는 "FastAPI로 API를 개발했습니다"처럼 **경험**으로
쓰이고, 공고는 "Python 개발 경험 2년 이상"처럼 **요구**로 쓰인다. 표현을 공고 쪽으로
맞춰야 벡터 검색이 걸린다.

③이 ⑥보다 앞에 있는 이유: 임베딩만으로 순위를 매기면 신입 이력서에 경력 7년 공고가
3위로 올라온다(실측으로 확인). 조건은 규칙으로
먼저 자르고, LLM은 조건이 맞는 것들 사이에서만 고른다.

⑦을 규칙으로 하는 이유: 모델은 근거를 지어낸다. 인용이 이력서와 공고 양쪽 원문에 **글자 그대로**
있어야 살아남는다(공백 차이만 무시한다). 근거가 하나도 안 남으면 적합도를 "낮음"으로
내린다.

## 판정 원칙

- **근거는 인용이다.** "백엔드 경험이 있습니다"가 아니라
  `"FastAPI로 추천 API를 개발하고"` ↔ `"Python 기반 백엔드(FastAPI) API 서버 개발"`.
- **적혀 있지 않은 것과 못 갖춘 것은 다르다.** 공고에 학력이 없으면 탈락이 아니라
  `CHECK_REQUIRED`다. 하드 필터는 PASS / CHECK_REQUIRED / FAIL 셋으로 답한다.
- **조건 충족은 근거가 아니다.** 연차·학력·지역은 `conditions`로 따로 보여 준다.
  근거 칸에는 무엇을 할 줄 아는지만 넣는다.
- **우대사항은 가산만 한다.** 충족하면 근거에 들어가고, 못 채웠어도 우려에 넣지 않는다.
  우대사항이 없어도 지원에 지장이 없다.
- **이력서로 확인할 수 없는 것은 우려가 아니다.** "커뮤니케이션 능력", "졸업 예정" 같은
  항목을 우려로 세면 이력서를 아무리 잘 써도 감점된다.
- **적합도는 개수가 아니라 주력이 겹치는가다.** 근거 3개면 높음, 같은 식으로 세지 않는다.
  Flutter 공고에 Flutter로 앱 둘을 만든 이력서면 높음이고, Kotlin 공고면 보통이다.
- **합격 가능성을 말하지 않는다.** 점수화·서열화도 하지 않는다.

## 모듈 구조

```text
crawling/     목록·상세 수집. 수집 규칙은 crawling/README.md
    ↓
ingestion/    원본 → Job 정규화. 요건 구간 분리, 전공·자격증 추출, 제외 직무
    ↓
retrieval/    Pinecone 적재·검색. 중복 제거, 만료 판정, 증분 적재
    ↓
matching/     하드 필터, 기술 겹침으로 다시 세우기(pre_ranker)
    ↓
api/          FastAPI. 위 단계를 한 요청으로 잇는다. 추천·공고 찾기 챗봇

schemas/      Job / ResumeProfile / 원본 레코드
evaluation/   사람 채점 도구, 규칙 결함 검사, 챗봇 평가
sharing/      팀원 공유용 슬림 저장소 생성·업로드
sync.py       수집 원본 → 인덱스까지 한 번에 (증분)
```

`coach/`는 공고 본문에서 요구역량을 뽑는 수집 단계의 도구다. `exporters/`에는
이력서 목업을 앱용 Dart로 내보내는 것만 남아 있다.

벡터 검색 이전의 규칙 기반 추천 경로(파이프라인·랭킹·Skill Gap·공고 Dart 내보내기)는
없앴다. 추천은 `api/`만 담당한다. 앱에 있던 공고 생성 파일(`collected_jobs.g.dart`)도
챗봇 공고 검색을 서버로 옮기면서 지웠다.

## 준비

API 키와 로컬 서버 설정은 레포 루트 `.env` 한 곳에 둔다. Firebase Functions 배포 전에는
`powershell -ExecutionPolicy Bypass -File scripts/sync-functions-env.ps1`로 생성본
`functions/.env`를 동기화한다. 키를 코드나 문서에 적지 않는다.

```
OPENAI_API_KEY=
PINECONE_API_KEY1=                # 채용공고 인덱스 키. 공지·정책 쪽은 PINECONE_API_KEY2다
PINECONE_INDEX=job-posting        # 생략하면 job-posting
PINECONE_NAMESPACE=               # 생략하면 기본 namespace
OPENAI_MODEL=                     # 생략하면 코드 기본값
OPENAI_EMBEDDING_MODEL=           # 생략하면 text-embedding-3-small
CORS_ALLOW_ORIGINS=               # API 서버용. 쉼표로 구분
```

레포 루트 `.env.example`에 있는 `PINECONE_INDEX_NAME`은 첨삭 모듈의 레거시 설정이다. 이 모듈은
`PINECONE_INDEX`를 읽고, 없으면 `job-posting`을 쓴다.

```powershell
py -3.12 -m venv playdata_venv
playdata_venv\Scripts\activate
pip install -r requirements.txt       # 레포 루트. 수집·적재·API·통합 서버에 필요한 것 전부
```

설치하는 패키지가 아니라 레포 루트에서 `python -m job_matching_bot.<모듈>`로 실행한다.
의존성 목록은 `pyproject.toml`에 있다.

## 실행

**테스트** — 외부 접속 없이 돈다.

```powershell
python -m unittest discover -s job_matching_bot/tests -t .
```

2026-09-15 수집본이 없는 체크아웃 기준 670개 실행, 통과(건너뜀 8개). 건너뛴 8개는 실제 공고 수집본
(`artifacts/`)이 있어야 도는 테스트다. 평가 도구(규칙 결함 검사·사람 채점·챗봇 대조)는 추천 API를 실제로 부르므로
[docs/test_report.md](docs/test_report.md) 2장의 명령으로 따로 돌린다.

**야간 배치** — 목록 훑기 → 신규 상세 → 링크 확인 → 적재 → 공유 파일 업로드를 한 번에. 매일 23:00 Windows 작업 스케줄러가 돌린다.

```powershell
python -m job_matching_bot.crawling.nightly                  # 오늘 몫 (월~토: IT 인접 4개 대분류 / 일: 전부)
python -m job_matching_bot.crawling.nightly --dry-run        # 목록만 훑고 상세·기록·적재는 안 함
.\job_matching_bot\crawling\schedule_nightly.ps1 -Register   # 스케줄 등록 (-Status, -RunNow, -Unregister)
```

**공유 공고 DB** — 저장소 파일(375MB)은 레포에 올리지 않는다. 슬림 파일을 Firebase Storage로 나눈다.

```powershell
python -m job_matching_bot.sharing.share_store --export --upload     # 만들어서 올리기 (야간 배치가 한다)
python -m job_matching_bot.sharing.share_store --download-if-newer   # 새 파일만 받아 안전 교체 (팀원용)
python -m job_matching_bot.sharing.share_store --info                # 올라가 있는 파일 정보
```

**수집** — 단계를 하나씩 돌릴 때. 규칙과 인자는 [crawling/README.md](crawling/README.md).

```powershell
python -m job_matching_bot.crawling.crawl_list --all-categories --sort AD --page-count 100
python -m job_matching_bot.crawling.detail_queue
python -m job_matching_bot.crawling.crawl_detail --limit 1000
```

**적재** — 수집 원본을 정제해 인덱스에 넣는다. 내용이 그대로인 공고는 다시 임베딩하지
않으므로 여러 번 돌려도 비용은 바뀐 것에만 든다.

```powershell
python -m job_matching_bot.sync                   # 증분 적재
python -m job_matching_bot.sync --dry-run         # 뭘 할지만 본다
python -m job_matching_bot.sync --skip-index      # 정제까지만, 인덱스는 안 건드림
python -m job_matching_bot.retrieval.refresh_metadata   # 메타데이터만 갱신. 임베딩 안 함
python -m job_matching_bot.retrieval.index_state        # 저장소가 기억하는 인덱스 상태. --adopt 로 기존 벡터 등록
python -m job_matching_bot.exporters.resume_mocks_dart  # 이력서 목업 → 앱 생성 파일
```

```
원본 JSONL → 유효성 검사 → 중복 제거 → 최신 레코드 선택 → 필드 정규화
→ 본문 정제 → 상태·품질 판정 → 변경 여부 확인 → 임베딩 → Pinecone 적재
```

**API 서버** — 보통은 첨삭·학생 챗봇까지 한 번에 뜨는 통합 서버로 띄운다.

```powershell
python -m uvicorn app.integrated:app --app-dir cover_letter_rag --host 127.0.0.1 --port 8000
python -m uvicorn job_matching_bot.api.main:app --host 127.0.0.1 --port 8000   # 추천봇만
```

통합 백엔드를 로컬에서 켤 때는 아래 스크립트를 쓰면 Firebase Storage의 공유 공고 DB가
새 generation인지 확인하고, 새 파일만 무결성 검사 후 교체한 다음 서버를 시작한다.
크롤링·임베딩·Pinecone 적재는 실행하지 않는다.

```powershell
.\scripts\start-backend.ps1
```

```
GET  /health                        인덱스 이름, 벡터 수, LLM 설정 여부
POST /api/v1/resume/profile         이력서 구조화. 앱이 저장할 때 미리 받아 두면 추천에서 건너뛴다
POST /api/v1/jobs/recommend         추천
POST /api/v1/jobs/recommend/stream  추천. 단계 진행을 SSE로 흘려보낸다
POST /api/v1/jobs/chat              공고 찾기 챗봇
```

요청은 이력서 원문과 조건이다. 앱이 이력서 화면의 값을 그대로 보낸다.

```json
{
  "resume_text": "[프로젝트 경험] ...",
  "preferred_regions": ["서울", "경기"],
  "preferred_employment_types": ["정규직"],
  "education_level": "대졸",
  "career_years": 0,
  "majors": [],
  "certifications": [],
  "top_k": 10
}
```

응답의 공고 하나는 이렇게 생겼다.

```json
{
  "company": "...", "title": "...", "source_url": "...",
  "fit": "높음",
  "reasons": [
    {"claim": "Spring Boot 기반 API를 만든 경험이 있습니다",
     "resume_quote": "주문·결제 REST API를 설계하고 구현했습니다.",
     "job_quote": "Spring Boot 기반 백엔드 서비스 설계 및 개발"}
  ],
  "concerns": ["Kafka 기반 이벤트 처리 경험이 이력서에서 확인되지 않는다"],
  "conditions": {"region": "서울 강남구", "career": "경력무관", "education": "학력무관"},
  "filter_status": "PASS",
  "unknown_conditions": []
}
```

`top_k`는 기본 10, 최대 12다. 한 회사는 두 건까지만 올린다. 검색·필터가 실패하면 503이다.

공고 찾기 챗봇(`/api/v1/jobs/chat`)의 요청·응답과 대화 맥락 잇기는 [docs/chatbot.md](docs/chatbot.md)에 있다.

## 인덱스와 비용

- 인덱스 `job-posting`, 1536차원, cosine, serverless(aws us-east-1)
- 임베딩은 `text-embedding-3-small`. 모델을 바꾸면 차원이 달라져 인덱스를 새로 만들어야 한다
- **임베딩 대상은 요건 구간만**(주요업무·자격요건·우대사항). 본문 앞의 분류 경로 줄은
  모든 공고를 서로 비슷하게 만들어 유사도가 0.37~0.50에 뭉치게 하므로 뺀다
- 메타데이터에 요건 원문 1,200자를 같이 담는다. LLM 재정렬이 이걸 읽는다.
  300자로 자르면 자격요건이 잘려 적합도가 전부 "보통"으로 나온다

비용은 두 군데서 난다.

| 어디 | 언제 | 얼마나 |
|---|---|---|
| OpenAI 임베딩 | 적재 때, 바뀐 공고만 | 공고 1건에 요건 ~1,200자 |
| OpenAI 채팅 | 추천 요청마다 프로필 생성 1회 + 후보 판정 최대 12회(병렬) | 판정 한 번에 공고 1건 × 1,200자를 읽는다. 프로필은 앱이 미리 만들어 보내면 건너뛴다 |
| Pinecone | 검색·적재 | serverless 무료 구간 안 |

429가 오면 기다렸다 다시 시도한다(OpenAI 5→60초, Pinecone 2→30초). 적재는
100건 단위로 나눠 보내고 청크마다 upsert해서, 중간에 끊겨도 진척이 남는다.

## 알려진 한계

- 추천 한 번에 중앙값 18.6초(14~23초)가 걸린다. 절반 이상이 LLM 재정렬(중앙값 11.0초)이고,
  마감 확인도 2.6초다. 서버를 띄운 뒤 첫 요청은 36초였다. 단계별 시간은 서버 로그의
  `[추천 시간]` 줄과 응답의 `timings_ms`에 남는다
- 신입·경력을 함께 뽑는 공고(메타 `경력무관`, 요건에 "신입"과 "경력 3년 이상"이 같이 있음)는
  경력무관으로 둔다. 직무마다 조건이 달라 한 값으로 정할 수 없다. 이런 OPEN 공고가 526건이다
- 상세가 이미지뿐인 공고(`body_is_image`)는 기업이 고른 기술 태그로만 판단한다
- 야간 배치가 상세를 하룻밤에 다 받지 못한다. 시간 한도에서 멈추고 남은 신규는 다음 밤에 이어서 받는다
- 야간 배치는 한 노트북의 작업 스케줄러에서 돈다. 노트북이 꺼진 밤은 건너뛴다
