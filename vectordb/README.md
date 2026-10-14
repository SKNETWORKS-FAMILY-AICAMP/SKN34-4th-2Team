# 학생 챗봇 벡터 DB 적재

[학생 LMS 챗봇](../chatbot/README.md)이 검색하는 문서를 모아 정제·분류·청킹한 뒤 임베딩해서
Pinecone `student` 인덱스에 넣는다. **정책·프로젝트는 별도 CLI, 공지는 Cloud Functions 트리거 또는 관리자 배치로 적재한다.** 챗봇이
질문을 받을 때는 이미 만들어 둔 인덱스를 검색만 한다.

| namespace | 원본 | 적재 도구 | 언제 |
|---|---|---|---|
| `policy` | 정책·FAQ·가이드 문서(md·csv·pdf) + Notion 페이지 5개 | `policy_ingestion.py` | 문서가 바뀌었을 때 수동 실행 |
| `project_reference` | 전 기수 프로젝트 목록 CSV | `project_reference_ingestion.py` | 목록이 바뀌었을 때 수동 실행 |
| `notice` | Firestore `cohorts/{기수}/notices` | Cloud Function `syncNoticeVector` ([functions/](../functions/README.md)) | 공지 작성·수정·삭제 즉시 자동 |

## 공통 설정

| 항목 | 값 |
|---|---|
| 인덱스 | `student` (없으면 `policy_ingestion.py`가 serverless aws us-east-1로 만든다) |
| 임베딩 | OpenAI `text-embedding-3-small`, 1536차원, cosine |
| 원문 저장 | 청크 원문을 메타데이터 `page_content`에 같이 넣는다. 챗봇이 검색 결과에서 바로 읽는다 |
| 키 | `OPENAI_API_KEY`, `PINECONE_API_KEY2` (레포 루트 `.env`) |
| 재시도 | 외부 호출은 1·2초 간격으로 최대 3번 |

## 공통 데이터 규약

LangChain Document의 `page_content`는 검색·답변에 쓰는 청크 원문이며, `metadata.doc_id`를 Pinecone 벡터 ID로 사용한다. Pinecone 메타데이터에는 원문도 함께 저장한다. namespace와 doc_id를 함께 사용해야 서로 다른 종류의 문서가 충돌하지 않는다.

| namespace | 벡터 ID·doc_id | 주요 메타데이터 | 조회 범위 |
|---|---|---|---|
| policy | `{policy_type}_{type_chunk_index}` | page_content, doc_id, type, created_at | 전 학생 공통 훈련 정책·FAQ |
| notice | `{cohort}_{index}` | page_content, doc_id, cohort, title, author_id, author_name, is_favorite, priority, created_at, updated_at | 인증된 학생의 소속 기수로 서버 필터 고정 |
| project_reference | `{cohort}_{project_round}_{index}` | page_content, doc_id, cohort, project_round, github_url | 질문에서 추출한 기수·차수. 최종은 final |

공통 정규화 순서는 NFKC → CRLF/CR을 LF로 통일 → 제어문자·불필요 기호 제거 → 연속 공백 축약·앞뒤 공백 제거 → 3개 이상 연속 개행을 2개로 축약이다. `+ = < > \| ₩ $ € ¥` 등 의미 있는 비교·금액 기호는 남긴다. 정책·공지는 의미 구간을 먼저 나누고 긴 구간을 최대 500자·40자 겹침으로 분리하며, 프로젝트는 정규화하되 한 프로젝트를 한 문서로 유지한다.

## 1. 정책·FAQ (`policy`)

### 수집 데이터

`data/policy_*` 폴더의 파일과 Notion 공개 페이지를 읽는다.

| 폴더 | 파일 |
|---|---|
| `data/policy_md/` | 리소스 결제 및 환급절차 매뉴얼, G밸리 캠퍼스 FAQ, SKN 과정 마일리지 제도, 주간회고(WIL) 작성 가이드, 프로그래머스 코딩역량인증 시험 접수 매뉴얼 |
| `data/policy_csv/` | 마일리지 유형 및 한도, 마일리지 지급 체계 |
| `data/policy_pdf/` | 2026 플레이데이터 OT 자료(SK네트웍스 Family AI 캠프 34기) |
| Notion (`NOTION_URLS`) | 플레이데이터 공개 Notion 페이지 5개. `NOTION_TOKEN`이 있을 때만 |

지원 형식은 `.pdf .xlsx .xls .csv .md .txt`다.

### 전처리 흐름

```mermaid
flowchart TB
  F["파일 · Notion 읽기"] --> N["텍스트 정규화"]
  N --> H["Markdown 제목 단위로 나누기<br>상위 제목을 앞에 붙임"]
  H --> C["정책 유형 분류<br>LLM → 실패 시 키워드 규칙"]
  C --> K["청킹<br>500자 · 40자 겹침 · FAQ는 문답 단위"]
  K --> J["policy_chunks.jsonl"]
  J --> E["임베딩 · Pinecone upsert"]
  E --> D["사라진 청크 삭제"]
```

| 단계 | 하는 일 | 이유 |
|---|---|---|
| 읽기 — PDF | PDF를 파일째 LLM에 넘겨 **렌더링된 페이지 이미지 기준으로** 정책 원문만 추출한다. 같은 한글이 3번 이상 반복되는 곳이 5곳 이상이면 실패로 본다 | OT 자료가 PowerPoint형이라 텍스트 레이어의 글꼴 매핑이 깨져 "교교교"처럼 나온다 |
| 읽기 — Notion | 블록을 Markdown으로 바꾼다. `last_edited_time`이 같으면 `.policy_notion_cache.json`의 캐시를 쓴다 | 바뀌지 않은 페이지를 다시 받지 않는다 |
| 읽기 — CSV·텍스트 | `utf-8-sig` → `cp949` 순서로 연다 | 엑셀에서 내보낸 CSV가 섞여 있다 |
| 잡음 제거 | Markdown에서 "선배들이 주는 tip", 전기수 블로그, `blog.naver.com` 줄과 `<aside>` 블록을 뺀다 | 정책이 아닌 개인 후기가 정책처럼 검색되는 것을 막는다 |
| 정규화 | NFKC, 제어문자·기호 제거(단 `+ = < > \| ₩ $ € ¥`는 남김), 공백·빈 줄 정리 | 금액·비교 기호는 정책 내용이다 |
| 제목 단위 분리 | `#` 제목마다 한 구간으로 자르고 상위 제목 경로를 앞에 붙인다 | 청크만 떼어 봐도 어느 정책의 어느 항목인지 알 수 있게 |
| 분류 | 18개 유형 중 하나(마일리지, 출결, 공가, 훈련장려금, 수료 및 제적, FAQ …). LLM이 JSON 스키마 enum으로 답하고, 실패하면 제목·키워드 점수로 정한다. 그래도 모호하면 "생활 및 기타" | 메타데이터 `type`으로 문서 성격을 남긴다 |
| OT PDF 거르기 | OT 자료에서는 훈련 방식·시간표·출결·장려금 등 운영 규정 유형만 남긴다 | 환영 인사·강사 소개·아이스브레이킹은 뺀다 |
| 청킹 | LangChain `RecursiveCharacterTextSplitter`로 **500자, 40자 겹침**(문단 → 줄 → 문장 → 공백 순). FAQ는 `Q.`/`A.` 문답 한 쌍을 먼저 한 덩어리로 자른다 | 정책 한 항목이 짧고, FAQ는 질문과 답이 떨어지면 쓸모가 없다 |

실패한 파일·단계는 멈추지 않고 `policy_ingestion_errors.jsonl`에 남긴 뒤 다음으로 넘어간다.

### 정책 유형 명세

유형은 다음 18개 enum 중 하나다. PDF 원문 추출·유형 분류의 기본 모델은 `gpt-5.6-luna`, 분류 temperature는 0이다. 모델 환경 변수·실패 시 대체 규칙은 아래 실행 안내를 따른다.

| type | 분류 내용 |
|---|---|
| `Mileage` | 마일리지 |
| `Resource_Payment_and_Refund` | 리소스 결제·환급 |
| `Retrospective_Writing_Guide` | 회고 작성 |
| `Programmers_Exam_Registration` | 프로그래머스 시험 접수 |
| `FAQ` | 자주 묻는 질문 |
| `Training_Method` | 훈련 방식 |
| `Training_Schedule` | 훈련 일정 |
| `Project` | 단위 프로젝트 |
| `Final_Project` | 최종 프로젝트 |
| `Post-Completion_Employment_Support` | 수료 후 취업 지원 |
| `Communication_Channel` | 소통 채널 |
| `Book_Rental` | 도서 대여 |
| `Attendance` | 출결 |
| `Official_Leave` | 공가 |
| `Completion_and_Dismissal` | 수료·제적 |
| `Training_Incentive` | 훈련장려금 |
| `Educational_Facilities_and_Equipment` | 교육 시설·장비 |
| `Life_and_Miscellaneous` | 생활·기타 |

### 메타데이터

```json
{
  "page_content": "## 출결\n지각·조퇴·외출 3회는 결석 1일로 ...",
  "doc_id": "Attendance_3",
  "type": "Attendance",
  "created_at": "2026-09-05T02:11:40+00:00"
}
```

`doc_id`는 `{policy_type}_{type_chunk_index}`이고 유형별 청크 순번을 벡터 ID로 쓴다. `type`은 위 enum, `created_at`은 적재 시각이다. `page_content`에는 상위 제목과 실제 규정 원문을 보존하며, 메타데이터만 보고 정책 내용을 생성하지 않는다.

### 갱신과 삭제

`.policy_ingestion_state.json`에 원본 구간별로 올린 `doc_id`를 기록한다. 다시 올릴 때 이번에 없는 ID는
Pinecone에서 지운다. 인자 없이 전체 파일을 적재하면 파일 원본(csv·excel·file·pdf)에서 나온 예전 ID까지
정리 대상으로 본다.

### 실행

레포 루트에서 실행한다.

```powershell
python -m vectordb.policy_ingestion ingest --dry-run      # JSONL까지만. Pinecone은 건드리지 않음
python -m vectordb.policy_ingestion ingest                # 수집 → 분류 → 청킹 → 적재
python -m vectordb.policy_ingestion ingest vectordb/data/policy_md --source files   # 특정 폴더만
python -m vectordb.policy_ingestion upload --input vectordb/policy_chunks.jsonl     # 만들어 둔 JSONL만 적재
```

| 인자 | 기본값 | 설명 |
|---|---|---|
| `paths` | `data/policy_*` 전체 | 파일 또는 폴더 |
| `--source` | `all` | `files` / `notion` / `all` |
| `--chunk-size` | 500 | 청크 최대 글자 수 |
| `--chunk-overlap` | 40 | 겹치는 글자 수 |
| `--output` | `vectordb/policy_chunks.jsonl` | 청크 결과 파일 |

- `--dry-run`도 PDF 추출과 분류에는 LLM을 부른다. 비용이 없는 것은 임베딩과 Pinecone 쪽뿐이다.
- 분류·PDF 추출 모델은 `OPENAI_MODEL` → `OPENAI_CLASSIFICATION_MODEL` → `OPENAI_PDF_EXTRACTION_MODEL` → `gpt-5.6-luna` 순으로 정한다.

## 2. 전 기수 프로젝트 레퍼런스 (`project_reference`)

### 수집 데이터

`data/project_reference/`의 CSV. 플레이데이터에서 공유한 SK네트웍스 Family AI 캠프 프로젝트 목록이다.

필수 열: `기수`, `구분`, `주제`, `기획설명`, `활용데이터`, `활용기술`, `깃허브 주소`

기수·차수·팀은 본문 제목에도 명시한다. 메타데이터에만 저장하면 유사도 검색에서 기수·차수 정보가 약해져 다른 프로젝트가 검색될 수 있기 때문이다. 첨부 학생 챗봇 테스트의 프로젝트 데이터 범위는 1~28기이며, 현재 학생 기수 34와 구분한다.

### 전처리

| 단계 | 규칙 |
|---|---|
| 빈 행 | `주제`가 비면 건너뛴다(건수는 `skipped`로 보고) |
| 차수 | `교과목실습N` → `N`, `최종프로젝트` → `final`. 그 밖의 값은 오류로 멈춘다 |
| GitHub 주소 | `SKNETWORKS-FAMILY-AICAMP/<저장소>`를 찾아 `https://github.com/...`로 맞춘다. 없으면 오류 |
| 팀 번호 | 저장소 이름의 `-Nteam`에서 뽑는다. 없으면 "팀 번호 미상" |
| 청킹 | **하지 않는다.** 프로젝트 하나가 문서 하나다. 여러 프로젝트 내용이 한 청크에 섞이지 않게 |

문서 본문과 메타데이터:

```text
SKN {기수}기 {N차 프로젝트 | 최종 프로젝트} {팀}팀
주제: ...
기획 설명: ...
활용 데이터: ...
활용기술: ...
```

```json
{
  "page_content": "SKN 25기 3차 프로젝트 2팀\n주제: ...\n기획 설명: ...\n활용 데이터: ...\n활용기술: ...",
  "doc_id": "25_3_1",
  "cohort": "25",
  "project_round": "3",
  "github_url": "https://github.com/SKNETWORKS-FAMILY-AICAMP/..."
}
```

챗봇은 질문의 "N기", "N차", "최종 프로젝트"를 규칙으로 추출해 `cohort`·`project_round` 필터로 검색한다. `cohort`·`project_round`는 문자열이며, 순번은 기수·차수별로 부여한다. `github_url`은 답변의 프로젝트 원문 출처로 제공한다.

### 실행

```powershell
python -m vectordb.project_reference_ingestion --dry-run   # project_reference_documents.jsonl까지만
python -m vectordb.project_reference_ingestion             # 적재
```

같은 `doc_id`는 덮어쓴다. 행이 줄어 없어진 `doc_id`를 지우는 기능은 없다.

## 3. 공지 (`notice`) — 자동 동기화

일상적인 공지 변경에는 수동 적재가 필요 없다. 관리자·강사가 앱에서 공지를 쓰면
`functions/src/noticeVectors.ts`의 Firestore 트리거가 바로 반영한다.

- 정규화와 청킹(500자, 40자 겹침)을 `policy_ingestion.py`와 같은 순서로 TypeScript에 옮겼다.
- 벡터 ID는 `{기수}_{순번}`. 순번 카운터는 `cohorts/{기수}/vectorMetadata/notices`에 있고, 공지마다 쓰는 순번을 `_vectorIndexes` 필드에 적어 둔다.
- 공지가 짧아져 청크가 줄면 남는 벡터를, 공지를 지우면 그 공지의 벡터를 모두 지운다.
- 메타데이터에 `cohort`가 있어 챗봇이 학생 기수로만 검색한다.

### 공지 메타데이터

| 필드 | 의미·작성 기준 |
|---|---|
| page_content | 정규화·청킹된 공지 원문 |
| doc_id | `{cohort}_{index}`, 벡터 ID와 동일 |
| cohort | Firestore 공지가 속한 기수, 학생 인증 문맥의 기수와 일치하는 문서만 검색 |
| title | 공지 제목 |
| author_id·author_name | 작성자 ID·표시 이름 |
| is_favorite·priority | 중요 공지 표시·우선순위 |
| created_at·updated_at | 생성·수정 시각. 정책과 공지의 최신성 구분에 사용 |

공지별 `_vectorIndexes[]`는 Firestore 원문과 여러 청크의 관계를 추적한다. 작성 시 새 청크를 올리고 수정 시 기존 ID를 갱신하며, 줄어든 청크·삭제된 공지의 벡터는 제거한다.

### 기존 공지 일괄 동기화

기존 공지가 있거나 초기 구축 시 관리자가 실행한다. Firebase Admin 권한과 루트 .env의 OpenAI·Pinecone 키가 필요하다. 아래는 레포 루트에서 시작하는 명령이며, 실제 클라우드 벡터 데이터를 변경한다.

```powershell
gcloud auth application-default login
cd functions
npm run build
node --env-file=../.env lib/noticeVectors.js --sync
cd ..
```

### 자동 동기화 배포

일괄 동기화는 한 번의 실행이고, 신규 공지 자동 반영에는 Firestore 트리거 배포가 필요하다. Firebase CLI가 대상 프로젝트로 설정되어 있는지 먼저 확인한다. 키의 실제 값은 문서·Git에 기록하지 않는다.

```powershell
firebase functions:secrets:set OPENAI_API_KEY
firebase functions:secrets:set PINECONE_API_KEY2
firebase deploy --only functions:syncNoticeVector
```

## 검증 기준

| 대상 | 확인할 내용 |
|---|---|
| 정책 JSONL | 빈 원문·깨진 한글이 없는지, type이 18개 enum인지, doc_id·created_at 보존 여부 |
| 프로젝트 JSONL | 기수·차수·팀이 본문에 있는지, cohort·project_round 문자열과 GitHub 링크가 원본 CSV와 일치하는지 |
| 공지 동기화 | 작성·수정·삭제 후 청크와 _vectorIndexes 일치, 다른 기수 공지 검색 차단 |
| 챗봇 연동 | 정책/공지 병렬 검색과 프로젝트 필터, 출처별 내용 구분, 검색 근거 없는 답변 생성 방지 |

정책 `--dry-run`은 임베딩·upsert를 하지 않지만 PDF 추출·분류 LLM 비용은 발생한다. 프로젝트 `--dry-run`은 CSV 변환 결과를 확인하는 용도다. 실행 테스트 질문·결과는 [chatbot/student_chatbot_test_question.md](../chatbot/student_chatbot_test_question.md)와 [chatbot/student_chatbot_test_result.md](../chatbot/student_chatbot_test_result.md)에 있다.

## 파일

| 파일 | 역할 |
|---|---|
| `policy_ingestion.py` | 정책·FAQ 수집·분류·청킹·적재 CLI |
| `project_reference_ingestion.py` | 프로젝트 레퍼런스 CSV 적재 CLI |
| `utills.py` | `.env` 읽기, 재시도, 텍스트 정규화, 청킹 |
| `data/` | 원본 문서 |

실행하면 생기는 `policy_chunks.jsonl`, `project_reference_documents.jsonl`, `policy_ingestion_errors.jsonl`,
`.policy_ingestion_state.json`, `.policy_notion_cache.json`은 결과물이다.
