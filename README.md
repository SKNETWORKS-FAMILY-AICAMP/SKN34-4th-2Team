<div align="center">

# <sup><img src="assets/readme_image/playdata_logo_transparent.png" alt="PLAYDATA" width="180" align="middle"></sup> LXP 2.0 · AI 학습·취업 코치

[![React · TypeScript](https://img.shields.io/badge/React-TypeScript-20232A?style=flat-square&logo=react&logoColor=61DAFB)](https://react.dev)
[![Expo · React Native](https://img.shields.io/badge/Expo-React%20Native-000020?style=flat-square&logo=expo&logoColor=white)](https://expo.dev)
[![Django Ninja · FastAPI](https://img.shields.io/badge/Backend-Django%20Ninja%20%2B%20FastAPI-092E20?style=flat-square&logo=django&logoColor=white)](https://django-ninja.dev)
[![OpenAI API · LangGraph](https://img.shields.io/badge/AI-OpenAI%20API%20%2B%20LangGraph-1C3C3C?style=flat-square&logo=langchain&logoColor=white)](https://github.com/langchain-ai/langgraph)
[![PostgreSQL · Pinecone](https://img.shields.io/badge/Data-PostgreSQL%20%2B%20Pinecone-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![AWS RDS · S3](https://img.shields.io/badge/AWS-RDS%20%2B%20S3-232F3E?style=flat-square&logo=amazonaws&logoColor=white)](https://aws.amazon.com)
[![Redis · Celery](https://img.shields.io/badge/Jobs-Redis%20%2B%20Celery-B23B2A?style=flat-square&logo=redis&logoColor=white)](https://redis.io)
[![Docker · Nginx · GitHub Actions](https://img.shields.io/badge/Deploy-Docker%20%2B%20Nginx%20%2B%20GitHub%20Actions-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docs.docker.com)

### 교육기관·부트캠프 운영과 취업 준비를 잇는 LXP

Flutter·Firebase 기반 기존 서비스를 React·Django·AWS 기반 웹 구조로 재구성하고, 플레이데이터 부트캠프 LMS를 학습 경험 플랫폼(LXP)으로 확장한 프로젝트다. 학생은 훈련 정책·공지·전 기수 프로젝트를 챗봇에 질문하고, 이력서 맞춤 채용공고 추천과 공고 맞춤 첨삭, 수업 노트·복습 문제·코드 튜터를 이용한다. 관리자와 강사는 같은 서비스에서 출결·공지·평가 등 운영·수업 업무를 처리한다. AI 답변은 검색 문서와 원문을 근거로 하며, 근거가 부족하면 추측하지 않는다.

**SK네트웍스 Family AI 캠프 34기 · 4차 프로젝트 · 2팀**

</div>

---

## 목차

- [1. 팀 소개](#1-팀-소개)
- [2. 역할 분담](#2-역할-분담)
- [3. 프로젝트 소개](#3-프로젝트-소개)
- [4. 프로젝트 필요성 (배경)](#4-프로젝트-필요성-배경)
- [5. 프로젝트 목표](#5-프로젝트-목표)
- [6. 주요 기능](#6-주요-기능)
- [7. 요구사항 명세서](#7-요구사항-명세서)
- [8. UI 시안 / UX Flow](#ui-ux)
- [9. WBS](#9-wbs)
- [10. 시스템 아키텍처](#10-시스템-아키텍처)
- [11. 데이터 ERD](#11-데이터-erd)
- [12. 데이터 수집 및 전처리](#12-데이터-수집-및-전처리)
- [13. RAG 구성](#13-rag-구성)
- [14. 프롬프트 템플릿](#14-프롬프트-템플릿)
- [15. 기술 스택](#15-기술-스택)
- [16. 주요 기능 테스트 계획 및 결과](#16-주요-기능-테스트-계획-및-결과)
- [17. 필수 산출물 위치](#17-필수-산출물-위치)
- [18. 트러블슈팅](#18-트러블슈팅)
- [19. 협업 방식](#19-협업-방식)
- [20. 회고](#20-회고)
- [21. 폴더 구조](#21-폴더-구조)
- [22. 실행 방법](#22-실행-방법)

---

<a id="team"></a>

## 1. 팀 소개

<p align="center">
  <img src="assets/readme_image/team_photo.jpg" alt="팀 소개 이미지" width="540">
</p>
<div align="center">

| 팀명 |
| :---: |
| **"그냥 신사"** |

| 김기호 | 김대호 | 문성호 | 최성욱 |
| :---: | :---: | :---: | :---: |
| <img src="assets/readme_image/team_kim_kiho_square.png" alt="김기호 프로필 이미지 (김종민)" width="150" height="150"> | <img src="assets/readme_image/team_kim_daeho_square.png" alt="김대호 프로필 이미지 (장동건)" width="150" height="150"> | <img src="assets/readme_image/team_moon_sungho_square.png" alt="문성호 프로필 이미지 (이종혁)" width="150" height="150"> | <img src="assets/readme_image/team_choi_sungwook_square.png" alt="최성욱 프로필 이미지 (김수로)" width="150" height="150"> |
| [kyo-135](https://github.com/kyo-135) | [jjhok6389](https://github.com/jjhok6389) | [MoonSungHo](https://github.com/MoonSungHo-D) | [Overlay1010](https://github.com/Overlay1010) |

</div>

---

<a id="roles"></a>

## 2. 역할 분담

| 담당자 | 담당 영역 |
| --- | --- |
|김&#8288;기&#8288;호| 학생 LXP 챗봇 개선·트러블슈팅, 정책 문서화 및 청킹·벡터 적재 파이프라인 재설계, 벡터 DB 스키마 설계, 주요 기능 테스트, README·필수 산출물 작성 |
|김&#8288;대&#8288;호| FOvia 개발 및 연동, Expo 앱 빌드, 모바일 반응형 UI 설계, 관리자 AI 어시스턴트/운영·아카이빙 기능 구현, Django 백엔드·API 이전 및 연동 |
|문&#8288;성&#8288;호| 웹 배포 구조 전환 총괄, RDS·S3 설계, 학생 챗봇 정책·출결 응답 개선, 이력서 첨삭 고도화, 통합 QA |
|최&#8288;성&#8288;욱| React 웹 이전·화면 개선, 웹 반응형 UI 설계, 채용공고 수집·검색·추천, 채용 공고 고도화, 공부방·복습 연습장/코드 튜터 기능 구현 |

---

<a id="overview"></a>

## 3. 프로젝트 소개

### **PLAYDATA LXP 2.0** — AI 학습·취업 코치

PLAYDATA All-in-One LMS에 학생 학습과 취업 지원을 결합한 LXP다. 기존 Flutter·Firebase 프로젝트를 React·Django·AWS 기반의 웹 서비스 구조로 고도화한다.

- **학생:** 기수별 정책과 공지 이미지를 근거로 답하는 RAG 챗봇, 수업 노트·복습 문제·코딩 복습·코드 리뷰, 맞춤 채용공고 추천과 이력서 첨삭을 이용한다.
- **관리자:** 대화형 AI로 운영 현황을 조회하고, 확인 카드로 알림·공지 실행을 승인하며, 운영 기록을 파일로 보관한다.

---

## 4. 프로젝트 필요성 (배경)

기존 LMS는 출결·공지·평가 등 운영 관리에 집중한다. 평가서와 인터뷰에서는 학생의 학습·취업 지원, 기수별 정책 관리, 반복적인 운영 업무를 함께 개선할 필요가 확인됐다.

### 평가서·인터뷰에서 확인한 요구
![평가서·인터뷰 기반 고도화 요구사항 인포그래픽](./assets/readme_image/assessment_interview_needs.png)

- **학생:** 수업 노트와 AI 질의응답·복습 문제·풀이 분석·피드백, 코딩 복습·자동 채점·요구사항 맞춤 코드 리뷰, 태블릿 학습 환경 개선, 채용공고 추천과 이력서 첨삭의 정확도 및 후속 관리
- **관리자·강사:** 불시 출석 확인 문서화, 학생 지정 알림, 기수별 정책 문서화와 운영 기록 아카이빙
- **서비스 방향:** 실제 교육 현장에서 쓰기 쉽게 다듬고 구독형으로 제공

---

## 5. 프로젝트 목표

### 학생 챗봇의 근거·기수별 검색

기수별 훈련 정책을 문서화하고, LXP 웹에 등록한 정책 문서를 규칙 기반으로 청킹·임베딩한다. 각 청크에 기수 정보를 저장해 로그인 학생의 기수에 맞는 근거로 답변하며, 공지 이미지도 문자 추출 후 벡터 데이터로 저장해 검색한다.

### 복습 연습장과 코드 튜터의 단계별 학습 지원

문제·코드·오류와 학생의 풀이 상태를 바탕으로 단계별 힌트와 설명을 제공한다. 힌트 단계를 서버에서 관리하고, 대화를 이어서 볼 수 있게 하며, 정답은 정해진 풀이·제출 절차에 따라 확인하도록 한다.

복습 연습장에서는 수업별 복습 문제를 풀고 틀린 문항을 다시 풀며 학습 내용을 점검한다.

### 채용공고 검색·추천 개선

채용공고를 수집·정규화해 PostgreSQL과 Pinecone에 반영하고, 자연어 조건 검색과 후속 질문을 지원한다. 이력서·희망 조건에 맞는 공고를 필수 조건과 마감 여부부터 확인해 추천하고, 적합도와 원문 근거·추가 확인 조건을 제공해 맞춤 첨삭과 지원 준비로 연결한다.

### 근거와 사실을 지키는 이력서 첨삭

기본 이력서를 보존한 공고별 사본에서 학생의 경험과 공고 요구사항을 비교해 문장별 수정안·근거·보완 질문을 제안한다. 확인되지 않은 경험이나 수치를 만들지 않고, 학생이 선택한 수정만 적용하며 되돌리기와 지원 문항 답변 초안 작성을 지원한다.

### 아카이빙 및 관리자 AI 어시스턴트의 운영 지원

출결 신청·설문 결과·점검 기록은 범위와 건수를 확인해 Excel·CSV·Word·PDF 파일로 보관하는 운영 기록 아카이빙을 핵심 목표로 한다. 관리자 화면 오른쪽 패널에서 출결·지각·설문 미제출·처리 대기 현황을 대화로 조회하고, 알림·공지는 확인 카드에서 문구와 대상을 검토한 뒤 실행한다. 출결 신청은 기간·처리 상태, 불시 자리 점검은 날짜로 범위를 정한다. 

### 웹 서비스 구조로 전환

기존 로컬 실행 중심 Flutter·Firebase 구조를 React·TypeScript 웹, Django Ninja API, FastAPI AI 서버와 AWS 기반으로 재구성한다. PostgreSQL(RDS)·S3를 연동해 학생·강사·관리자 기능을 하나의 서비스로 제공하고, Docker·Nginx·GitHub Actions를 활용해 웹 배포와 운영을 고려한 구조를 마련한다.

---

<a id="features"></a>

## 6. 주요 기능

핵심 AI 기능의 입출력·처리 흐름·제약은 `docs/features/`에 정리한다.

| 기능 | 상세 명세 |
| --- | --- |
| 학생 챗봇 | [정책·공지·프로젝트 검색과 본인 학습 데이터 조회](docs/features/student-chatbot.md) |
| 채용공고 | [자연어 검색·이력서 기반 추천](docs/features/job-postings.md) |
| 이력서 첨삭 | [공고 맞춤 첨삭·지원 문항 작성](docs/features/resume-review.md) |
| 공부방·복습 연습장 | [수업 노트·복습 문제·풀이 기록](docs/features/study-room.md) |
| 코드 튜터 | [단계별 힌트·코드·오류 설명](docs/features/code-tutor.md) |
| 관리자 AI·아카이빙 | [운영 조회·실행 확인·기록 내보내기](docs/features/admin-assistant.md) |

LMS는 역할별로 출결·자리 확인, 공지·설문·제출, 평가, 이력서·기록실·마일리지 기능을 제공한다. 웹과 모바일은 같은 Django API를 사용하며, 코드 편집·연습장 등 일부 기능은 PC 웹에서 이용한다.

---

<a id="requirements"></a>

## 7. 요구사항 명세서

상세 요구사항은 [요구사항 명세서](docs/requirements/requirements.md)에 있다.

| ID | 요구사항 | 확인 기준 |
| --- | --- | --- |
| AUTH&#8288;-&#8288;01 | 역할·기수·소유권 기반 접근 제어 | 미인증·다른 기수·타인 자료 요청을 서버에서 제한한다. |
| CHAT&#8288;-&#8288;01 | 기수별 문서 기반 학생 챗봇 | 로그인 기수의 정책·공지와 접근 가능한 자료로 답변한다. |
| DATA&#8288;-&#8288;01 | 정책 문서·공지 이미지 검색 | 규칙 기반 청킹·OCR 후 출처와 기수를 포함해 적재한다. |
| STUDY&#8288;-&#8288;01 | 수업 노트·복습 문제 | 선택 자료로 생성하고 풀이·오답 기록을 관리한다. |
| TUTOR&#8288;-&#8288;01 | 단계별 코드 튜터 | 서버가 힌트 단계와 대화를 관리하고 정답 노출을 제한한다. |
| JOB&#8288;-&#8288;01 | 공고 검색·맞춤 추천 | 필수 조건·마감·원문 인용을 확인한다. |
| RESUME&#8288;-&#8288;01 | 근거 기반 첨삭·지원 문항 작성 | 사실을 만들지 않으며 선택한 수정만 적용·되돌린다. |
| ADMIN&#8288;-&#8288;01 | 관리자 AI 운영 지원 | 조회 결과로 제안하고 관리자 확인 후 실행한다. |
| ARCHIVE&#8288;-&#8288;01 | 운영 기록 아카이빙 | 조회 범위의 데이터를 Excel·CSV·Word로 내보내고 인쇄에서 PDF로 저장한다. |
| OPS&#8288;-&#8288;01 | 예약 작업·배포 구성 | 예약 공지·출제 작업을 분리하고 빌드와 실제 배포 상태를 구분한다. |
| NFR&#8288;-&#8288;07 | 웹·모바일 통합 서비스 기반 | Flutter·Firebase 로컬 구조를 React 웹·Expo·Django·FastAPI 기반으로 확장한다. |

---

<a id="ui-ux"></a>

## 8. UI 시안 / UX Flow

### UX Flow

#### 학생

```mermaid
flowchart TD
    S0["학생 로그인"] --> S1["대시보드에서<br/>학습·출결·공지 확인"]
    S1 --> S2{"이용 목적"}
    S2 -->|"수강 안내"| S3["학생 챗봇에 질문"]
    S3 --> S4["기수별 정책·공지와<br/>본인 자료의 근거 확인"]
    S2 -->|"학습·복습"| S5["공부방 자료·<br/>복습 문제 선택"]
    S5 --> S6["코드 작성·실행·채점"]
    S6 --> S7{"문제를 해결했는가"}
    S7 -->|"아니오"| S8["코드 튜터의<br/>단계별 힌트 확인"]
    S8 --> S6
    S7 -->|"예"| S9["결과 확인·오답 재도전"]
    S2 -->|"취업 준비"| S10["이력서 작성·저장"]
    S10 --> S11["채용공고 검색·맞춤 추천"]
    S11 --> S12["공고 맞춤 첨삭·<br/>지원 문항 작성"]
    S12 --> S13["수정 제안 검토·<br/>선택 적용·저장"]
    S2 -->|"출결 관리"| S14["출결 현황 확인·신청"]
    S14 --> S15["신청 처리 결과 확인"]
```

대시보드에서 수강 안내·학습·취업·출결 기능으로 이동한다. 복습 중 막히면 코드 튜터의 힌트를 확인하고 다시 풀며, 취업 준비는 저장한 이력서에서 공고 추천·맞춤 첨삭으로 이어진다.

#### 관리자

```mermaid
flowchart TD
    A0["관리자 로그인"] --> A1["기수 선택·대시보드 확인"]
    A1 --> A2{"운영 업무 선택"}
    A2 -->|"운영 관리"| A3["학생·출결·승인 대기 조회"]
    A3 --> A4["내용 검토·승인 또는 반려"]
    A2 -->|"AI 어시스턴트"| A5["현황 조회·알림·공지 요청"]
    A5 --> A6{"실행 제안인가"}
    A6 -->|"조회"| A7["조회 결과와 근거 확인"]
    A6 -->|"알림·공지"| A8["확인 카드의<br/>문구·대상 검토"]
    A8 --> A9{"관리자가 실행하는가"}
    A9 -->|"예"| A10["알림 발송·공지 등록"]
    A9 -->|"아니오"| A11["제안 상태로 유지"]
    A2 -->|"아카이빙"| A12["출결·설문·점검 기록 선택"]
    A12 --> A13["기간·상태·대상·<br/>건수 확인"]
    A13 --> A14{"파일 형식"}
    A14 -->|"Excel·CSV·Word"| A15["파일 다운로드"]
    A14 -->|"PDF"| A16["브라우저 인쇄에서<br/>PDF 저장"]
```

선택 기수의 운영 현황을 조회하고 승인 업무를 처리한다. AI가 제안한 알림·공지는 관리자가 확인한 뒤 실행하며, 기록 내보내기는 관리 화면에서 범위와 건수를 확인한 후 진행한다.

#### 강사

```mermaid
flowchart TD
    I0["강사 로그인"] --> I1["담당 기수 확인"]
    I1 --> I2{"수업 업무 선택"}
    I2 -->|"자리 확인"| I3["날짜·교시 선택"]
    I3 --> I4["좌석 배치 확인·학생 호명"]
    I4 --> I5{"자리를 확인했는가"}
    I5 -->|"예"| I6["확인 처리"]
    I5 -->|"보류"| I7["보류 목록에서 재확인"]
    I7 --> I5
    I6 --> I8["교시별 확인 기록 반영·<br/>당일 출석부 조회"]
    I2 -->|"수업 자료"| I9["커리큘럼·<br/>수업 저장소 관리"]
    I9 --> I10["학생 공부방에<br/>수업 자료 공유"]
    I2 -->|"학습 평가"| I11["평가 작성·발행"]
    I11 --> I12["제출 답안 확인·채점"]
    I2 -->|"복습 문제"| I13["학생이 신고한 문제 검토"]
    I13 --> I14["다시 보이기·<br/>숨김 유지 결정"]
```

담당 기수의 자리 확인·수업 자료·평가·복습 문제를 관리한다. 자리 확인은 출결 상태를 변경하지 않으며, 확인 기록의 파일 내보내기는 관리자 화면에서 진행한다.

### UI 시안

역할별 항목을 펼치면 실제 화면을 볼 수 있으며, 이미지를 클릭하면 원본 크기로 확인한다.

<details>
<summary><strong>학생 UI · 6개 화면</strong></summary>

| 대시보드 | 학생 챗봇 |
| --- | --- |
| [![학생 대시보드](assets/readme_image/ui/student_dashboard.png)](assets/readme_image/ui/student_dashboard.png) | [![학생 챗봇](assets/readme_image/ui/student_chatbot.png)](assets/readme_image/ui/student_chatbot.png) |

| 이력서 기반 채용공고 추천 | 이력서 첨삭·공고 맞춤 지원 |
| --- | --- |
| [![이력서 기반 채용공고 추천](assets/readme_image/ui/student_job_recommendations.png)](assets/readme_image/ui/student_job_recommendations.png) | [![이력서 첨삭·공고 맞춤 지원 문항 작성](assets/readme_image/ui/student_resume_review.png)](assets/readme_image/ui/student_resume_review.png) |

| 복습 연습장 | 코드 튜터 |
| --- | --- |
| [![학생 복습 연습장](assets/readme_image/ui/student_review_practice.png)](assets/readme_image/ui/student_review_practice.png) | [![학생 코드 튜터](assets/readme_image/ui/student_code_tutor.png)](assets/readme_image/ui/student_code_tutor.png) |

</details>

<details>
<summary><strong>관리자 UI · 3개 화면</strong></summary>

**대시보드**

[![관리자 대시보드](assets/readme_image/ui/admin_dashboard.png)](assets/readme_image/ui/admin_dashboard.png)

| AI 어시스턴트 | 운영 기록 아카이빙 |
| --- | --- |
| [![관리자 AI 어시스턴트](assets/readme_image/ui/admin_ai_assistant.png)](assets/readme_image/ui/admin_ai_assistant.png) | [![관리자 운영 기록 아카이빙](assets/readme_image/ui/admin_archiving.png)](assets/readme_image/ui/admin_archiving.png) |

</details>

<details>
<summary><strong>강사 UI · 1개 화면</strong></summary>

**자리 확인·당일 출석부 조회**

[![강사 자리 확인·당일 출석부 조회](assets/readme_image/ui/instructor_seat_check.png)](assets/readme_image/ui/instructor_seat_check.png)

</details>

---

<a id="wbs"></a>

## 9. WBS

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/readme_image/wbs_lxp_clean_dark.png">
  <img src="assets/readme_image/wbs_lxp_clean.png" alt="2026년 9월 18일부터 10월 14일까지의 프로젝트 WBS">
</picture>

| WBS | 작업 | 기간 (2026) | 관련 이슈 |
| --- | --- | --- | --- |
| 1.1 | 프로젝트 착수·코드 이관 | 09/18 ~ 09/19 | 커밋 기준 |
| 1.2 | 웹·API 전환·DB 통합 | 09/21 ~ 09/26 | [#2](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/2) · [#3](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/3) · [#8](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/8) |
| 1.3 | 화면 통일·반응형 개선 | 09/21 ~ 10/13 | [#4](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/4) · [#5](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/5) · [#6](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/6) · [#35](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/35) · [#40](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/40) |
| 2.1 | 학생 챗봇·기수별 정책 RAG | 09/23 ~ 10/12 | [#22](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/22) · [#39](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/39) |
| 2.2 | 채용 수집·검색·추천·코치 | 09/19 ~ 10/12 | [#14](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/14) · [#21](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/21) · [#23](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/23) · [#24](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/24) · [#30](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/30) |
| 2.3 | 이력서 첨삭·맞춤 지원 | 09/19 ~ 10/13 | [#25](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/25) · [#43](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/43) · [#46](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/46) · [#51](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/51) · [#52](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/52) · [#53](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/53) |
| 2.4 | 공부방·복습·코드 튜터 | 09/19 ~ 10/13 | [#26](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/26) · [#27](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/27) · [#32](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/32) |
| 3.1 | 관리자 운영·AI·아카이빙 | 09/26 ~ 10/13 | [#13](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/13) · [#38](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/38) · [#7](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/7) |
| 3.2 | Expo 앱·권한별 화면 | 09/22 ~ 10/13 | 커밋 기준 |
| 3.3 | 배포 구성·보안·안정화 | 09/22 ~ 10/13 | [#10](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/10) · [#15](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/15) · [#29](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/29) · [#31](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/31) |
| 4.1 | 검증 기록·문서·발표 정리 | 09/26 ~ 10/13 | [#17](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/17) · [#18](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/18) · [#19](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/19) · [#33](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/33) |
| 4.2 | 산출물 최종 확인·발표 준비 | 10/13 ~ 10/14 | [#18](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/18) · [#19](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues/19) |

[커밋·이슈별 일정 근거](docs/deliverables/wbs.md)

---

<a id="architecture"></a>

## 10. 시스템 아키텍처

### 전체 시스템 아키텍처

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/readme_image/system_architecture_readme_dark.png">
  <img src="assets/readme_image/system_architecture_readme.png" alt="LXP 전체 시스템 아키텍처">
</picture>

React 웹·Expo 앱의 요청은 Django에서 인증·권한을 확인한 뒤 처리한다. 학생 챗봇·공부방·첨삭·채용 추천은 별도 FastAPI 서버로 연결하고, 관리자 AI와 공지 이미지 추출은 Django에서 외부 AI를 호출한다.

| 구성 | 역할 |
| --- | --- |
| Django·Nginx | API 프록시, JWT 인증, 역할·기수·소유권 검사, LMS 업무를 담당한다. |
| FastAPI | 학생 챗봇·채용 추천·첨삭·학습 AI를 하나의 서비스로 제공한다. |
| PostgreSQL·S3·Pinecone | 각각 업무 원본, 파일, 의미 검색 인덱스를 저장한다. |
| Redis·Celery | 작업 큐·결과·캐시, 예약 공지·동기화·복습 출제·첨삭 후속 작업을 처리한다. |
| GitHub Actions | 웹 테스트·빌드와 API·AI 컨테이너 이미지 빌드를 수행하도록 구성한다. |

[서비스 경계·포트·데이터 흐름 상세](docs/architecture/system-architecture.md)

---

<a id="erd"></a>

## 11. 데이터 ERD

PostgreSQL의 핵심 테이블을 운영·학습·취업으로 나눈다. `PK`는 기본 키, `FK`는 외래 키, `FK?`는 NULL을 허용하는 외래 키이다. 주요 관계만 표시하며 전체 컬럼과 제약은 [Django 모델](lms_api/lms/models.py)·[마이그레이션](lms_api/lms/migrations/)·[공고 SQL](scripts/firestore_to_postgres/jobs_schema.sql)을 기준으로 한다.

### 교육 운영

기수를 기준으로 사용자·공지·출결·평가를 관리하고, 평가 문항과 응시·답안을 분리한다.

![기수·사용자·출결·평가 핵심 ERD](assets/readme_image/erd_operations_lxp_clean.png)

### 학습·복습·튜터

수업 저장소·노트, 문제 세트·문항, 학생별 시도, 튜터 대화를 별도로 저장한다. 노트와 문제 세트 사이에 직접 FK는 없다.

![공부방·복습 문제·튜터 핵심 ERD](assets/readme_image/erd_learning_lxp_clean.png)

### 이력서·지원·채용

기본 이력서와 맞춤 이력서, 확인된 경험, 지원서·문항·답변을 연결한다. 수집 공고는 `jobs` 스키마에 두며, `resumes.linked_job_id`와 `applications.job_id`는 물리 FK가 아닌 문자열 기반 논리 참조이다.

![이력서·지원서·채용공고 핵심 ERD](assets/readme_image/erd_career_lxp_clean.png)

### Pinecone 벡터 구조

`student`와 `job-posting` 인덱스에 검색용 벡터를 저장한다. namespace와 메타데이터로 검색 범위를 구분하고, 문서 키·공고 ID로 원본을 논리 참조한다.

![Pinecone 인덱스·namespace·메타데이터 구조](assets/readme_image/pinecone_erd_current.png)

### S3 파일 객체 구조

S3에 원본 파일을 저장하고 PostgreSQL에는 객체 키를 기록한다. 파일 조회 시 서명된 URL을 발급하며, 아래 연결은 외래 키가 아닌 문자열 키 참조이다.

![S3 파일 객체와 RDS 저장 키의 연결 구조](assets/readme_image/s3_erd_current.png)

---

## 12. 데이터 수집 및 전처리

문서·공고는 갱신 시 검색 인덱스를 적재하고, 학생의 업무 데이터는 질문 시 권한 범위 안에서 조회한다.

| 데이터 | 수집·전처리 | 저장·갱신 |
| --- | --- | --- |
|기&#8288;수&nbsp;정&#8288;책&#8288;·&#8288;커&#8288;리&#8288;큘&#8288;럼| 웹에서 DOCX·PDF를 업로드한다. 정책의 장·조·조건·예외를 보존하고 PDF는 페이지별 텍스트를 나눈다. | S3 원본 → 문서별 Pinecone namespace → 적재 확인 후 활성 문서 연결을 전환한다. |
|공&#8288;지&#8288;·&#8288;첨&#8288;부&nbsp;이&#8288;미&#8288;지| 공지 본문을 정리하고 이미지의 문자를 추출한다. 표의 제목·열 정보를 텍스트에 포함한다. | 이미지 추출문을 S3에 캐시하고 기수 정보와 함께 `notice`에 반영한다. |
|전&nbsp;기&#8288;수&nbsp;프&#8288;로&#8288;젝&#8288;트| CSV의 기수·차수·제목·GitHub 주소를 정리한다. | 프로젝트 단위 문서를 `project_reference`에 적재한다. |
|채&#8288;용&#8288;공&#8288;고| 공개 공고를 수집해 중복·상태·직무·지역·경력·기술을 정규화하고 요건 구간을 추출한다. | PostgreSQL `jobs` 원본과 Pinecone을 분리하고 변경 지문을 기준으로 벡터를 갱신한다. |
|수&#8288;업&nbsp;자&#8288;료| 등록된 GitHub 저장소의 날짜·폴더·파일 범위를 선택한다. | 동일 자료의 노트를 재사용하고 생성 결과·출제 범위를 PostgreSQL에 기록한다. |
|학&#8288;생&#8288;·&#8288;운&#8288;영&nbsp;데&#8288;이&#8288;터| 출결·이력서·학습 기록을 본인·기수 범위로 조회한다. | 조회 시 민감한 키와 문맥 길이를 제한하며, 질문마다 전체 데이터를 벡터로 적재하지 않는다. |

구현: [정책 청킹](vectordb/policy_ingestion.py) · [기수 문서 적재](chatbot/cohort_document_rag.py) · [공지 OCR·동기화](lms_api/lms/notice_vectors.py) · [프로젝트 적재](vectordb/project_reference_ingestion.py) · [공고 전처리](job_matching_bot/docs/data_preprocessing.md)

기수 문서는 파일 형식·크기·경로와 추출 결과를 확인한다. 텍스트를 읽을 수 없는 PDF는 적재를 중단하며, 문서 속 지시는 실행 명령으로 취급하지 않는다.

---

## 13. RAG 구성

### 벡터 인덱스

| **인덱스 / namespace** | **문서** | **청킹** | **메타데이터 필터** |
| --- | --- | --- | --- |
| `student` / `policy` | 기본 정책·FAQ·가이드 | 제목 단위 500자·40자 겹침. 구조화 DOCX는 조문 단위로 보존한다. | `cohort` |
| `student` / `cohort-doc-*` | LXP에 업로드한 기수별 정책 DOCX·PDF와 커리큘럼 PDF | 정책 DOCX는 조문 단위, PDF는 페이지별 1,000자·120자 겹침으로 나눈다. | `cohort` |
| `student` / `notice` | 기수 공지 본문과 첨부 이미지에서 추출한 텍스트 | 본문은 500자·40자 겹침, 이미지 추출문은 별도 청크로 저장한다. | `cohort` |
| `student` / `project_reference` | 전 기수 단위·최종 프로젝트 | 프로젝트 1건을 문서 1건으로 적재한다. | `cohort`, `project_round` |
| `job-posting` / 기본 namespace | 채용공고의 주요업무·자격요건·우대사항 | 청킹하지 않고 요건 구간을 임베딩한다. 120자 미만은 제외하고, 검색 근거는 최대 1,200자를 저장한다. | `status`, 지역, 고용형태, 경력, 학력 |

학생·정책·공지·프로젝트 인덱스는 설정에 따라 기본 모델을 OpenAI `text-embedding-3-small`(1,536차원)로 사용한다. 채용공고 인덱스도 같은 모델과 차원을 사용하며 cosine 유사도로 검색한다.

### 적재 방식과 사용 기능

| **인덱스 / namespace** | **적재** | **사용 기능** |
| --- | --- | --- |
| `student` / `policy` | [정책 적재 스크립트](vectordb/policy_ingestion.py)에서 별도 적재한다. | 학생 챗봇 |
| `student` / `cohort-doc-*` | LXP에서 정책·커리큘럼 파일을 올린다. S3 원본을 저장하고, Pinecone 적재와 검색 확인 후 기수별 활성 문서를 전환한다. | 학생 챗봇·커리큘럼 검색 |
| `student` / `notice` | 공지 저장·수정·삭제가 완료되면 반영한다. 이미지 문자는 추출해 캐시한 뒤 함께 적재한다. | 학생 챗봇 |
| `student` / `project_reference` | [프로젝트 적재 스크립트](vectordb/project_reference_ingestion.py)에서 CSV를 적재한다. | 학생 챗봇 |
| `job-posting` / 기본 namespace | 채용공고 야간 수집·동기화에서 변경된 공고만 증분 적재한다. | 채용공고 추천·검색 챗봇 |

### 요청 흐름

| **기능** | **흐름** |
| --- | --- |
|①&nbsp;학&#8288;생&nbsp;챗&#8288;봇| LangGraph가 질문을 분류해 필요한 범위를 정한다 → 로그인 학생의 기수로 정책·공지 검색 범위를 제한한다 → 요청한 경우 프로젝트와 본인 데이터를 조회한다 → 출석 계산은 서버에서 처리한다 → 검색 근거로 답변을 스트리밍한다. |
|②&nbsp;채&#8288;용&nbsp;추&#8288;천| 이력서에서 검색 질의를 만든다 → Pinecone에서 조건을 적용해 상위 25건을 검색한다 → 필수 조건과 마감을 확인하고 기술 겹침으로 후보를 재정렬한다 → 최대 14건의 LLM 평가와 조기 마감 확인을 병행한다 → 최대 12건을 남기고 공고 원문과 근거를 대조한다. |
|③&nbsp;공&#8288;고&nbsp;검&#8288;색&nbsp;챗&#8288;봇| 질문에서 조건을 추출한다 → 명시 조건은 저장소에서 조회하고 의미 조건은 Pinecone에서 검색한다 → 실제 조회 결과를 바탕으로 목록을 구성한다. |
|④&nbsp;이&#8288;력&#8288;서&nbsp;첨&#8288;삭| 서버가 저장된 이력서와 선택한 공고 원문을 읽는다 → 문장별 수정안을 만든다 → 새 사실이나 수치가 추가된 수정안은 보류한다 → 학생이 선택한 수정안만 적용한다. |

공부방 노트·복습 튜터·코드 튜터는 선택한 수업 자료와 문제·코드를 직접 문맥으로 사용한다. 관리자 AI는 권한이 검증된 운영 조회 도구를 사용한다.

### RAG 성능 가이드 대응

| **가이드** | **적용** |
| --- | --- |
|요&#8288;청&#8288;마&#8288;다 인&#8288;덱&#8288;싱&#8288;하&#8288;지 않&#8288;기| 문서 적재는 별도 CLI·관리자 업로드·공지 저장 후 동기화·야간 배치에서 처리한다. |
|변&#8288;경&#8288;분&#8288;만 증&#8288;분 인&#8288;덱&#8288;싱| 공고는 임베딩 본문·검색 메타데이터 지문이 바뀐 경우만 다시 적재한다. 공지는 저장·수정·삭제분만 반영한다. |
|문&#8288;서 고&#8288;유 I&#8288;D&#8288;와 버&#8288;전 관&#8288;리| 정책은 문서·기수·조문을 포함한 ID, 공지는 기수·공지·청크 ID, 프로젝트는 기수·차수·순번, 공고는 공고 ID를 사용한다. 업로드 문서는 파일별 namespace에 적재한다. |
|메&#8288;타&#8288;데&#8288;이&#8288;터&#8288;로 검&#8288;색 범&#8288;위 제&#8288;한| 정책·공지·업로드 문서는 로그인 기수, 프로젝트는 요청 기수·차수, 공고는 공개 상태·지역·고용형태·경력·학력으로 범위를 좁힌다. |
|t&#8288;o&#8288;p&#8288;-&#8288;k&#8288;와 문&#8288;맥 길&#8288;이 제&#8288;한| 학생 챗봇은 검색당 기본 4건, 복수 namespace 검색 시 기본 8건을 요청하며 질문에 지정된 개수는 최대 20건까지 반영한다. 커리큘럼은 8건, 프로젝트 범위 검색은 기수 구간별 3건을 검색한다. |
|후&#8288;보 검&#8288;증&#8288;과 재&#8288;정&#8288;렬| 추천은 25건 검색 후 규칙 필터·기술 겹침 순위를 적용하고 최대 14건을 병렬 LLM 평가와 조기 마감 확인에 넘긴다. 최종 후보는 최대 12건이며 인용 근거를 추가 확인한다. |
|검&#8288;색 결&#8288;과 문&#8288;맥 제&#8288;한| 정책은 같은 조문·명시 참조를 최대 8건, 총 6,000자까지 보강한다. 채용공고는 재정렬 근거를 1,200자로 제한한다. |
|객&#8288;체 재&#8288;사&#8288;용&#8288;과 처&#8288;리 시&#8288;간 기&#8288;록| 채용 검색은 Pinecone 클라이언트·인덱스를 재사용한다. 챗봇 검색·생성 및 채용 추천 단계의 처리 시간을 기록한다. |

---

## 14. 프롬프트 템플릿

역할·제약을 담은 시스템 지시와 사용자 질문·근거 자료를 분리한다. 분류·첨삭처럼 구조가 필요한 결과는 JSON·Pydantic 스키마와 서버 검증으로 제한한다.

| 기능 | 템플릿·구현 | 입력 → 출력 |
| --- | --- | --- |
|학&#8288;생&nbsp;질&#8288;문&nbsp;분&#8288;류&#8288;·&#8288;답&#8288;변| [`SUPERVISOR_PROMPT`, `ANSWER_PROMPT`](chatbot/student_chatbot.py) | 질문·최근 대화 → 검색 범위 / 근거 문맥 → 답변 |
|공&#8288;고&nbsp;검&#8288;색&#8288;·&#8288;추&#8288;천| [`CHAT_PROMPT`, `PROFILE_PROMPT`, `RERANK_PROMPT`](job_matching_bot/api/prompts.py) | 조건·이력서·공고 → 검색 조건·추천 질의·근거와 적합도 |
|이&#8288;력&#8288;서&nbsp;첨&#8288;삭&nbsp;v&#8288;2| [`ANALYST_SYSTEM_PROMPT`, `WRITER_SYSTEM_PROMPT`, `VERIFY_SYSTEM_PROMPT`](cover_letter_rag/app/resume_review_v2/prompts.py) | 사실 추출 → 근거 연결 문장 작성 → 사실·누락 검증 |
|지&#8288;원&nbsp;문&#8288;항&nbsp;작&#8288;성| [지원 답변 프롬프트](cover_letter_rag/app/application_writing/prompts.py) | 문항·공고 요구사항·확인된 경험 → 답변 초안 |
|공&#8288;부&#8288;방&nbsp;노&#8288;트| [`NOTE_PROMPT`](study_notes/pipeline.py) | 선택 수업 자료·학습 범위 → 구조화된 노트 |
|복&#8288;습&nbsp;문&#8288;제&#8288;·&#8288;튜&#8288;터| [출제](study_notes/practice/generate.py) · [튜터 `SYSTEM`](study_notes/practice/tutor.py) | 수업 자료 → 검증할 문제 / 문제·코드·힌트 단계 → 설명 |
|관&#8288;리&#8288;자&nbsp;A&#8288;I| [도구 정의·프롬프트](lms_api/lms/admin_assistant.py) | 업무 질문·조회 결과 → 현황 요약·실행 제안 |

학생 질문 분류와 공고 조건 해석에는 분기 예시를, 추천에는 적절한 근거와 부적절한 근거의 예시를 포함한다. 첨삭은 원문에 없는 경험·기술·수치를 만들지 않도록 제한한다. 실행 카드와 수정안은 프롬프트만 신뢰하지 않고 서버에서 다시 확인한다.

---

<a id="tech-stack"></a>

## 15. 기술 스택

| 영역 | 기술 | 용도 |
| --- | --- | --- |
| 웹 | ![React 18.3](https://img.shields.io/badge/React-18.3-61DAFB?style=flat-square&logo=react&logoColor=black) ![TypeScript 5.9](https://img.shields.io/badge/TypeScript-5.9-3178C6?style=flat-square&logo=typescript&logoColor=white) ![Vite 6](https://img.shields.io/badge/Vite-6-646CFF?style=flat-square&logo=vite&logoColor=white) | 역할별 웹 화면과 빌드를 구성한다. |
| 상태·통신 | ![React Router 6](https://img.shields.io/badge/React_Router-6-CA4245?style=flat-square&logo=reactrouter&logoColor=white) ![TanStack Query 5](https://img.shields.io/badge/TanStack_Query-5-FF4154?style=flat-square&logo=reactquery&logoColor=white) ![Zustand](https://img.shields.io/badge/Zustand-333333?style=flat-square) ![Axios](https://img.shields.io/badge/Axios-5A29E4?style=flat-square&logo=axios&logoColor=white) | 라우팅·서버 상태·화면 상태·API 통신을 처리한다. |
| 모바일 | ![Expo SDK 57](https://img.shields.io/badge/Expo-SDK_57-000020?style=flat-square&logo=expo&logoColor=white) ![React Native 0.86](https://img.shields.io/badge/React_Native-0.86-61DAFB?style=flat-square&logo=react&logoColor=black) ![Expo Router](https://img.shields.io/badge/Expo_Router-000020?style=flat-square&logo=expo&logoColor=white) | Django API를 공유하는 모바일 화면을 제공한다. |
| 업무 API | ![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white) ![Django 5.2](https://img.shields.io/badge/Django-5.2-092E20?style=flat-square&logo=django&logoColor=white) ![Django Ninja](https://img.shields.io/badge/Django_Ninja-092E20?style=flat-square&logo=django&logoColor=white) ![SimpleJWT](https://img.shields.io/badge/SimpleJWT-333333?style=flat-square) ![Gunicorn](https://img.shields.io/badge/Gunicorn-499848?style=flat-square&logo=gunicorn&logoColor=white) | 인증·권한·업무 처리를 담당한다. |
| AI API | ![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white) ![Uvicorn](https://img.shields.io/badge/Uvicorn-4051B5?style=flat-square) ![Pydantic](https://img.shields.io/badge/Pydantic-E92063?style=flat-square) | AI 기능을 통합하고 입출력 형식을 검증한다. |
| LLM·검색 | ![OpenAI API](https://img.shields.io/badge/OpenAI_API-412991?style=flat-square&logo=openai&logoColor=white) ![LangChain](https://img.shields.io/badge/LangChain-1C3C3C?style=flat-square&logo=langchain&logoColor=white) ![LangGraph](https://img.shields.io/badge/LangGraph-1C3C3C?style=flat-square&logo=langchain&logoColor=white) ![Pinecone](https://img.shields.io/badge/Pinecone-000000?style=flat-square&logo=pinecone&logoColor=white) | 생성·임베딩·워크플로·문서 검색을 구성한다. |
| 데이터·파일 | ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat-square&logo=postgresql&logoColor=white) ![Amazon RDS](https://img.shields.io/badge/Amazon_RDS-527FFF?style=flat-square&logo=amazonrds&logoColor=white) ![Amazon S3](https://img.shields.io/badge/Amazon_S3-569A31?style=flat-square&logo=amazons3&logoColor=white) | 업무 원본과 파일을 분리해 보관한다. |
| 비동기·캐시 | ![Celery](https://img.shields.io/badge/Celery-37814A?style=flat-square&logo=celery&logoColor=white) ![Redis 7](https://img.shields.io/badge/Redis-7-FF4438?style=flat-square&logo=redis&logoColor=white) | 예약 작업·작업 큐·결과·캐시를 처리한다. |
| 실습·아카이빙 | ![CodeMirror](https://img.shields.io/badge/CodeMirror-D30707?style=flat-square) ![Pyodide](https://img.shields.io/badge/Pyodide-306998?style=flat-square&logo=python&logoColor=white) ![ExcelJS](https://img.shields.io/badge/ExcelJS-217346?style=flat-square&logo=microsoftexcel&logoColor=white) ![docx](https://img.shields.io/badge/docx-2B579A?style=flat-square&logo=microsoftword&logoColor=white) | 코드 편집·실행과 기록 내보내기를 제공한다. |
| 배포·검증 | ![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white) ![Nginx](https://img.shields.io/badge/Nginx-009639?style=flat-square&logo=nginx&logoColor=white) ![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=flat-square&logo=githubactions&logoColor=white) ![Vitest](https://img.shields.io/badge/Vitest-6E9F18?style=flat-square&logo=vitest&logoColor=white) ![unittest](https://img.shields.io/badge/unittest-3776AB?style=flat-square&logo=python&logoColor=white) ![pytest](https://img.shields.io/badge/pytest-0A9EDC?style=flat-square&logo=pytest&logoColor=white) | 컨테이너·빌드·회귀 테스트를 구성한다. |
| 관측 | ![LangSmith](https://img.shields.io/badge/LangSmith-1C3C3C?style=flat-square&logo=langchain&logoColor=white) | 설정한 환경에서 LLM 호출을 추적한다. |

의존성 기준: [웹](lms_react/package.json) · [모바일](lms_mobile/package.json) · [Django](lms_api/requirements.txt) · [통합 AI](requirements.txt). PostgreSQL 16은 로컬 Compose의 버전이다.

---

## 16. 주요 기능 테스트 계획 및 결과

### 검증 계획

| 기능 | 검증 기준 | 상세 보고서 |
| --- | --- | --- |
|학생&nbsp;챗봇| 3차 질문 45개·50턴, 기수별 정책 검색·OCR·조회 범위 | [학생 챗봇](docs/reports/test_report_student_chatbot.md) |
|채용공고| 3차 대화 48개·62턴, 이력서 10종의 조건·인용·마감 | [검색·추천](docs/reports/test_report_job_postings.md) |
|이력서&nbsp;첨삭| 3차 원본 테스트, 사실 보존·선택 적용·v2 첨삭 | [이력서 첨삭](docs/reports/test_report_resume_review.md) |
|코드&nbsp;튜터| 단계별 힌트·코드 설명·정답 노출·학습 외 요청 | [코드 튜터](docs/reports/test_report_code_tutor.md) |
|관리자&nbsp;AI| 운영 조회·확인 카드·권한·아카이빙 파일 내용 | [관리자 AI·아카이빙](docs/reports/test_report_admin_assistant.md) |

공부방·복습 연습장은 이번 AI 테스트에서 제외한다. 3차 케이스는 원본을 유지하며 신규 기능은 합성 자료로 검증한다.

### 확인된 결과

2026년 10월 14일에 실행한 결과이다. 실제 OpenAI·Pinecone 호출과 격리 PostgreSQL 검증을 포함하며 단위·모델·화면 결과를 구분한다.

| 대상 | 결과 | 확인 범위 |
| --- | --- | --- |
|학생&nbsp;챗봇| Python 231개 통과, 라우팅 50/50턴, RAG 8/8개, OCR 1/1개 | 3차 검색 범위 기대값 6개는 모두 불일치한다. 최종 답변 전체 평가와 구분한다. |
|채용공고| 라우터 48/48개 × 3회, 검색 48/48개·62/62턴, 추천 120건 규칙 결함 0건 | Python 874개 중 856개 통과·5개 실패·2개 오류·11개 건너뜀이다. |
|이력서&nbsp;첨삭| 현재 Python 1,006개 통과, 실제 v2 첨삭 10개 처리 완료 | 3차 원본 227개 중 211개 통과·16개 실패이다. 모델 상태는 READY 6개·UNCHANGED 3개·NEEDS_EVIDENCE 1개이다. |
|코드&nbsp;튜터| Python 11개, 실제 모델·규칙 케이스 18/18개 통과 | 응답 유형·선별 정답 문자열 노출을 확인한다. |
|관리자&nbsp;AI| 실제 응답 8/8개, 아카이빙 16/16개 통과 | 카드·가드레일 35개 중 34개 통과·1개 실패이다. PDF는 인쇄용 HTML을 검증한다. |
|공통&nbsp;통합| Django 33개, 기존 React 선별 136개 통과 | 추가 아카이빙 16개는 별도 집계한다. |

학생 챗봇의 추가 조회 범위, 채용 회귀의 기대 계약, 관리자 학생 입력 필터를 후속 검토 대상으로 기록한다. 추천의 사람 적합도, 브라우저 전체 흐름, AWS 배포·Expo 실기기는 미검증이다. [종합 보고서·PDF](docs/deliverables/test-plan-results.md)에서 실행 근거와 한계를 확인한다.

---

## 17. 필수 산출물 위치

| 필수 산출물 | 문서·구현 위치 |
| --- | --- |
| 요구사항 정의서 | [양식 기반 Excel](docs/deliverables/requirements.xlsx) · [요구사항·구현 근거](docs/requirements/requirements.md) |
| 화면설계서 | [PDF](docs/deliverables/screen-design.pdf) · [화면별 동작·경로](docs/deliverables/screen-design.md) |
| 개발된 LLM 연동 웹 애플리케이션 | [React 웹](lms_react/) · [Django API](lms_api/) · [통합 AI](cover_letter_rag/app/integrated.py) · [Expo 앱](lms_expo/) · [실행방법](#22-실행-방법) |
| 시스템 구성도 | [전체 아키텍처 이미지](assets/readme_image/system_architecture_readme.png) · [서비스·데이터 흐름 상세](docs/architecture/system-architecture.md) |
| 테스트 계획 및 결과 보고서 | [PDF](docs/deliverables/test-plan-results.pdf) · [보고서 원문](docs/deliverables/test-plan-results.md) |

보조 산출물은 [WBS 일정 근거](docs/deliverables/wbs.md), [핵심 기능 명세](docs/features/), [데이터 ERD](#erd), [문서 이미지·SVG 원본](assets/readme_image/), [배포 구성](deploy/DEPLOYMENT.md)에 모은다.

---

<a id="troubleshooting"></a>

## 18. 트러블슈팅



---

## 19. 협업 방식

| 구분 | 협업 기준 |
| --- | --- |
|작&#8288;업&nbsp;관&#8288;리| GitHub 이슈에 기능 범위와 확인할 결과를 기록하고 프로젝트 보드로 진행 상태를 관리한다. |
|G&#8288;i&#8288;t&#8288;H&#8288;u&#8288;b&nbsp;F&#8288;l&#8288;o&#8288;w| 이슈를 등록하고 `develop`에서 기능·수정 브랜치를 만들어 작업한다. 변경 사항은 PR로 공유해 리뷰 후 `develop`에 병합하며, `main`은 배포 workflow의 기준으로 관리한다. |
|P&#8288;R| 관련 이슈, 변경 내용, 검증 결과를 남기고 리뷰 후 병합한다. |
|데&#8288;이&#8288;터&#8288;·&#8288;A&#8288;P&#8288;I| 모델·마이그레이션·응답 형식이 바뀌면 소비하는 웹·AI 코드와 문서를 함께 확인한다. |
|환&#8288;경&nbsp;설&#8288;정| `.env.example`에 필요한 키를 공유하고 실제 비밀값은 각 실행 환경에 별도로 설정한다. |
|문&#8288;서| 기능 명세는 `docs/features/`, 검증 기록은 `docs/validation/`에 모으고 README에서 연결한다. |

---

<a id="retrospective"></a>

## 20. 회고

### 김기호


### 김대호


### 문성호


### 최성욱


---

## 21. 폴더 구조

```text
SKN34-4th-2Team/
├── lms_react/          # React 웹 · 화면 테스트 · 사용자 매뉴얼
├── lms_mobile/         # Expo · React Native 모바일
├── lms_api/            # Django API · 모델 · 마이그레이션 · Celery
├── chatbot/            # 학생 챗봇 · 정책 검색 · 학생 문맥 조회
├── vectordb/           # 정책·프로젝트 수집 · 청킹 · 벡터 적재
├── job_matching_bot/   # 채용공고 수집 · 검색 · 추천
├── cover_letter_rag/   # 통합 FastAPI · 이력서 첨삭 · 지원 문항
├── study_notes/        # 수업 노트 · 복습 문제 · 코드 튜터
├── practice_verifier/  # 코드 문제 실행·검증
├── docs/               # 요구사항 · 기능 명세 · 설계 · 검증 기록
├── assets/readme_image/ # README 이미지
├── scripts/            # 데이터 이전 · 실행 · 문서 이미지 생성
├── deploy/             # Dockerfile · Nginx · 배포 구성
├── .github/workflows/  # 웹 테스트·빌드 · 컨테이너 이미지 빌드
├── docker-compose.yml  # 로컬 PostgreSQL · Redis · API · 작업 큐 컨테이너 설정 파일
├── docker-compose.prod.yml
├── requirements.txt    # 통합 AI 의존성
└── .env.example        # 환경변수 예시
```

| 폴더·파일 | 담당 기능 |
| --- | --- |
| `lms_react/` | 웹 화면 (React · TypeScript · Vite) · 화면 테스트 · 사용자 매뉴얼 |
| `lms_mobile/` | 모바일 앱 (Expo · React Native) |
| `lms_api/` | LMS API (Django · django-ninja · JWT) · 모델 · 마이그레이션 · Celery |
| `cover_letter_rag/` | 이력서 첨삭 · 지원 문항 · 통합 AI 서버 진입점 (`app/integrated.py`) |
| `chatbot/` | 학생 LMS 챗봇 · 정책 검색 · 학생 문맥 조회 |
| `job_matching_bot/` | 채용공고 크롤링 · 적재 · 추천 · 공고 대화 |
| `study_notes/` | 공부방 AI 수업 노트 · 복습 문제 · 코드 튜터 |
| `practice_verifier/` | 복습 문제 검증기 (브라우저와 같은 Pyodide) |
| `vectordb/` | 학생 챗봇 벡터 DB 적재 · 정책/프로젝트 수집·청킹 |
| `chatbot_lab/` | 챗봇 실험용 (운영과 연결 안 됨) |
| `scripts/` | 실행 · 이전 · 적재 스크립트 · 문서 이미지 생성 |
| `deploy/`, `docker-compose*.yml` | 배포 (Nginx · AI 서버 이미지) · 로컬/운영 컨테이너 구성 |
| `docs/` | 설계 · 이전 · 점검 · 기능 명세 · 필수 산출물 |
| `assets/readme_image/` | README 이미지 |
| `.github/workflows/` | 웹 테스트·빌드 · 컨테이너 이미지 빌드 |
| `functions/`, `config/firebase/` | 3차 Firebase 자산 (이전 참고용) |
| `requirements.txt` | 통합 AI 의존성 |
| `.env.example` | 환경변수 예시 |

---

## 22. 실행 방법

### 준비

Python 3.12, Node.js 20 이상, Git, Docker Compose를 준비한다.

```powershell
git clone --branch develop https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team.git
cd SKN34-4th-2Team
Copy-Item .env.example .env
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -r lms_api/requirements.txt
```

`.env`에 다음 값을 설정한다. 이미 받은 `.env`가 있으면 복사 단계는 생략한다.

| 항목 | 로컬 설정 |
| --- | --- |
| 데이터베이스 | `DB_HOST`를 비우고 `DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/lms`로 설정한다. |
| Redis | `REDIS_URL=redis://127.0.0.1:6379/0`으로 설정한다. |
| AI 주소 | `CHATBOT_URL`과 `JOBS_URL`을 `http://127.0.0.1:8001`로 설정한다. |
| 내부 인증 | Django와 AI에 같은 `LMS_AI_SHARED_TOKEN`을 설정한다. |
| 외부 AI·검색 | `OPENAI_API_KEY`, `PINECONE_API_KEY1`(공고), `PINECONE_API_KEY2`(학생 문서)를 설정한다. |
| 파일·자료 | S3 사용 시 `AWS_S3_BUCKET`·AWS 인증을 설정하고, 비공개 수업 저장소는 접근 토큰을 설정한다. |

RDS를 사용할 때는 `DB_HOST`·`DB_NAME`·`DB_USER`·`DB_PASSWORD`·`DB_PORT`·`DB_SSLMODE`를 맞춘다. `DB_HOST`가 있으면 `DATABASE_URL`보다 우선한다. 로그인에는 LMS 계정과 기수 데이터가 필요하며 팀의 개발용 계정을 사용한다.

### 데이터베이스와 업무 API

```powershell
# 저장소 루트, 가상환경 활성화 상태
docker compose up -d db redis
cd lms_api
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

`migrate`는 LMS 스키마를 준비한다. 공고 `jobs` 스키마와 데이터는 [공고 저장소 운영 문서](docs/database/job-posting-operations.md)와 수집·동기화 경로를 따른다. 빈 DB에서는 정책·공고·수업 자료를 별도로 등록해야 해당 AI 기능의 근거를 조회할 수 있다.

### 통합 AI 서버

새 터미널에서 저장소 루트로 이동하고 가상환경을 활성화한다.

```powershell
.venv\Scripts\Activate.ps1
python -m uvicorn app.integrated:app --app-dir cover_letter_rag --host 127.0.0.1 --port 8001
```

### 웹과 모바일

```powershell
# 새 터미널, 저장소 루트
cd lms_react
npm ci
npm run dev
```

웹 접속 주소는 `http://localhost:5173`이며 `/api`는 Django `8000`으로 전달한다. 모바일은 [Expo 실행 안내](lms_mobile/README.md)에 따라 같은 API에 연결한다.

### 예약·첨삭 후속 작업

가상환경을 활성화한 터미널 두 개에서 각각 `lms_api` 폴더로 이동해 실행한다. 로컬 Windows worker는 `solo` 풀을 사용한다.

```powershell
# 터미널 1
celery -A lms_server worker -l info --pool=solo
```

```powershell
# 터미널 2
celery -A lms_server beat -l info
```

Beat를 사용할 때는 `.env`의 `LMS_INLINE_PUBLISH=0`으로 중복 스케줄 실행을 막는다. 운영 컨테이너 구성은 [운영 Compose](docker-compose.prod.yml)와 [배포 문서](deploy/DEPLOYMENT.md)를 따른다.
