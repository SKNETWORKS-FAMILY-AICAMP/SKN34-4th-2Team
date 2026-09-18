# 학생 챗봇 Luna Lab

운영/통합 서버와 연결되지 않는 실험 전용 패키지다. 기존 `chatbot/`과
`cover_letter_rag/app/integrated.py`는 수정하지 않는다.

## 안전 경계

- 실행 포트: `8002` (기존 통합 서버 `8000`과 분리)
- API prefix: `/api/v1/student-chatbot-lab`
- 모델: 코드에 `gpt-5.6-luna`로 고정
- 벡터 DB 키: `PINECONE_API_KEY2`만 허용
- Flutter 설정과 통합 서버에는 실험 라우터를 등록하지 않음
- 중단하려면 8002 서버만 종료하면 됨. 원본 복구나 코드 되돌리기가 필요 없음

## 실행 및 확인

저장소 루트에서 기존 가상환경을 사용한다.

```powershell
.\playdata_venv\Scripts\python.exe -m uvicorn chatbot_lab.main:app --port 8002
```

브라우저에서 `http://127.0.0.1:8002/docs`를 열어 `health`, `init`, `stream`을
확인한다. 실제 질문은 기존과 동일하게 Firebase 학생 ID 토큰이 필요하다.
운영 사이트의 API 주소는 변경하지 않는다.

Flutter에서 개선 챗봇만 임시 연결하려면 앱 코드는 바꾸지 않고 다음처럼 실행한다.
실험 서버는 8002 안에서만 Flutter 호환 경로 `/api/v1/student-chatbot`을 함께 제공한다.

```powershell
flutter run -d chrome --dart-define=STUDENT_CHATBOT_API_URL=http://127.0.0.1:8002
```

원복은 Flutter를 종료한 뒤 `--dart-define` 없이 다시 실행하면 된다. 다른 기능의 기본
서버 주소는 계속 8000이므로 추천·이력서 기능을 함께 확인하려면 통합 서버도 켜 둔다.

### 나란히 비교하는 Streamlit 화면

실험 UI 의존성은 루트 requirements가 아니라 이 폴더 안의 파일로 따로 설치한다.

```powershell
.\playdata_venv\Scripts\python.exe -m pip install -r chatbot_lab\requirements-lab.txt
.\playdata_venv\Scripts\python.exe -m streamlit run chatbot_lab\streamlit_app.py
```

브라우저의 `http://localhost:8501`에서 왼쪽 `기존 구조 (Luna)`와 오른쪽
`개선 구조 (Luna)`에 같은 질문을 동시에 보낼 수 있다. 기본값인 `Supervisor만` 모드는
Pinecone과 최종 답변 생성을 실행하지 않는다. `전체 답변`을 선택할 때만 양쪽에서 검색과
답변 생성이 실행된다. 평가 결과는 Git에서 제외된 `chatbot_lab/results/`에만 저장된다.

개선판은 Luna의 의미 분류를 유지하면서 `routing.py`가 질문에 명시된 공지·정책·프로젝트·
개인/기수 데이터·파일 범위의 명백한 누락만 보정한다. 또한 개인 정보 과조회와 LMS 밖의
콘텐츠 대필 오분류를 보수적으로 제거한다. 이 규칙은 운영 챗봇에는 등록되지 않는다.

기본 목업 모드의 개인 데이터 질문은 실제 Firebase에 접속하지 않고
`fixtures/mock_firebase.json`을 사용한다.
fixture에는 계산된 출석률을 저장하지 않고 Firestore와 비슷하게 수업일과 날짜별 출결 상태만
기록한다. 실행 시 운영 코드의 `calculate_unit_period_context()`가 출석률과 기준 충족 여부를
계산하므로 모델에 정답 수치를 직접 제공하지 않는다.

사이드바의 `학생 데이터`를 `실제 Firebase`로 바꾸고 학생 UID 또는 이메일을 입력하면 Flutter
백엔드와 동일한 Firebase Admin 설정 및 `load_student_context()`를 사용한다. 선택한 활성 학생과
그 학생의 기수로 조회 범위를 고정하며, 다른 학생으로 범위를 넓히는 요청은 차단한다. 실제 데이터
모드의 대화와 판정은 `results/`에 저장하지 않는다.

Supervisor는 저장된 기대값과 Luna 실험판만 비교한다. 운영 Sol은 호출하지 않는다.
아래 명령은 Luna에 대한 실제 OpenAI API 비용만 발생한다.

Supervisor 전용 평가는 Pinecone과 embedding을 초기화하지 않으며, 같은 Luna 모델에서
기존 프롬프트와 개선 프롬프트+규칙 보조 라우터를 각각 실행해 정답 수와 지연시간을 비교한다.

```powershell
.\playdata_venv\Scripts\python.exe -m chatbot_lab.evaluate_supervisor
```

결과는 기본적으로 `chatbot_lab/eval_result.json`에 생성된다. 사례를 늘릴 때는
`eval_cases.json`에 기대 route, namespace, student scope를 추가한다.

## 삭제 가능한 범위

실험을 폐기할 때는 이 `chatbot_lab/` 폴더만 제거하면 된다. 다른 파일에 등록된
의존성이 없으므로 기존 Sol 챗봇 동작에는 영향이 없다.
