// 이 파일은 자동 생성됩니다. 직접 수정하지 마세요.
// 다시 만들려면 레포 루트에서 실행하세요:
//   python -m job_matching_bot
//
// 원본: scripts/resume_mocks.json

import '../../models/resume_mock_persona.dart';

const resumeMockPersonas = <ResumeMockPersona>[
  ResumeMockPersona(
    key: "backend_entry",
    title: "[목업] 백엔드 신입 — Python/Django",
    content: <String, dynamic>{
      "basicInfo": <String, dynamic>{
        "name": "",
        "phone": "010-0000-0001",
        "email": "",
        "birthDate": "1999-03-12",
        "githubUrl": "https://github.com/example-backend",
        "blogUrl": "https://example-backend.tistory.com",
      },
      "coreCompetencies": <String, dynamic>{
        "text": "Python·Django·FastAPI 기반 REST API 설계와 PostgreSQL 모델링 경험. Docker로 개발·배포 환경을 통일하고 AWS EC2에 서비스를 올려 운영해 봤습니다.",
      },
      "experience": <dynamic>[],
      "education": <dynamic>[
        <String, dynamic>{
          "id": "edu-1",
          "school": "한국대학교",
          "major": "컴퓨터공학과",
          "startDate": "2018-03",
          "endDate": "2024-02",
          "status": "졸업",
        },
      ],
      "techStack": <dynamic>[
        <String, dynamic>{
          "id": "ts-1",
          "name": "Python",
          "level": "고급",
        },
        <String, dynamic>{
          "id": "ts-2",
          "name": "Django",
          "level": "중급",
        },
        <String, dynamic>{
          "id": "ts-3",
          "name": "FastAPI",
          "level": "중급",
        },
        <String, dynamic>{
          "id": "ts-4",
          "name": "PostgreSQL",
          "level": "중급",
        },
        <String, dynamic>{
          "id": "ts-5",
          "name": "Docker",
          "level": "초급",
        },
        <String, dynamic>{
          "id": "ts-6",
          "name": "AWS",
          "level": "초급",
        },
      ],
      "certifications": <dynamic>[
        <String, dynamic>{
          "id": "cert-1",
          "name": "정보처리기사",
          "issuer": "한국산업인력공단",
          "acquiredDate": "2024-11",
        },
      ],
      "awards": <dynamic>[
        <String, dynamic>{
          "id": "awd-1",
          "name": "교내 소프트웨어 경진대회 장려상",
          "organization": "한국대학교 SW중심대학사업단",
          "date": "2023-11",
          "description": "학식 메뉴 알림 서비스로 참가. 크롤링과 알림 발송 백엔드를 맡았습니다.",
        },
      ],
      "trainingExperience": <dynamic>[
        <String, dynamic>{
          "id": "tr-1",
          "course": "SK네트웍스 Family AI 캠프 34기",
          "organization": "PLAYDATA",
          "startDate": "2026-03",
          "endDate": "2026-09",
          "description": "Python 백엔드와 LLM 서비스 개발 과정 수료 예정",
        },
      ],
      "otherActivities": <dynamic>[
        <String, dynamic>{
          "id": "act-0",
          "name": "(주)예시소프트 하계 백엔드 인턴",
          "startDate": "2025-07",
          "endDate": "2025-09",
          "description": "사내 관리자 페이지의 Django REST API 유지보수. 목록 조회에 select_related를 적용해 쿼리 수를 페이지당 60여 회에서 4회로 줄였습니다.",
        },
        <String, dynamic>{
          "id": "act-1",
          "name": "교내 알고리즘 스터디 운영",
          "startDate": "2022-03",
          "endDate": "2023-12",
          "description": "주 1회 문제 풀이 모임을 3학기 동안 운영했습니다. 풀이를 정리해 블로그에 올렸습니다.",
        },
        <String, dynamic>{
          "id": "act-2",
          "name": "오픈소스 문서 번역 기여",
          "startDate": "2025-04",
          "endDate": "2025-06",
          "description": "FastAPI 한국어 문서 오탈자와 예제 코드 수정 PR 3건이 병합됐습니다.",
        },
      ],
      "projects": <dynamic>[
        <String, dynamic>{
          "id": "prj-1",
          "name": "채용공고 추천 API",
          "startDate": "2026-06",
          "endDate": "2026-08",
          "role": "백엔드 개발(3인 팀)",
          "techStack": "Python, FastAPI, PostgreSQL, pgvector",
          "description": "이력서 임베딩과 공고 임베딩을 pgvector로 비교해 추천 목록을 내려주는 API. 응답 시간 800ms→220ms 개선.",
          "url": "https://github.com/example-backend/job-reco",
        },
        <String, dynamic>{
          "id": "prj-2",
          "name": "LMS 출결 관리 서비스",
          "startDate": "2026-04",
          "endDate": "2026-05",
          "role": "백엔드 개발",
          "techStack": "Python, Django, PostgreSQL",
          "description": "Django ORM으로 출결·마일리지 도메인 모델링, 관리자 페이지 커스터마이징.",
          "url": "",
        },
      ],
      "selfIntroduction": <String, dynamic>{
        "intro": <String, dynamic>{
          "subtitle": "문제를 끝까지 좁혀 가는 백엔드 지망생",
          "body": "API 하나를 만들 때도 요청이 어디서 느려지는지 측정하고 고치는 과정을 좋아합니다. 부트캠프에서 세 개의 팀 프로젝트를 백엔드 담당으로 마쳤습니다.",
        },
        "motivation": <String, dynamic>{
          "subtitle": "느린 API를 고쳐 본 경험에서 시작했습니다",
          "body": "데이터를 다루는 서비스의 뒷단을 안정적으로 만드는 일을 하고 싶습니다.",
        },
        "challenge": <String, dynamic>{
          "subtitle": "추천 API 응답을 800ms에서 220ms로",
          "body": "팀 프로젝트에서 추천 목록이 느리다는 피드백을 받았습니다. 처음엔 벡터 검색이 문제라고 짐작했는데, 구간별로 시간을 재 보니 실제 병목은 후보마다 공고를 한 건씩 조회하는 부분이었습니다. 한 번에 가져오도록 바꾸고 자주 쓰는 결과를 캐시해 220ms까지 줄였습니다. 짐작으로 고치지 않고 먼저 재는 습관이 여기서 생겼습니다.",
        },
        "growth": <String, dynamic>{
          "subtitle": "혼자 만들던 코드에서 같이 읽는 코드로",
          "body": "처음에는 동작하면 됐다고 생각했습니다. 3인 팀 프로젝트에서 제 코드를 다른 사람이 고치지 못해 작업이 멈추는 걸 보고 생각이 바뀌었습니다. 함수를 짧게 나누고 왜 그렇게 했는지 주석으로 남기기 시작했고, 리뷰에서 받은 지적을 따로 정리해 다음 PR에서 반복하지 않으려 했습니다.",
        },
        "strengthsWeaknesses": <String, dynamic>{
          "subtitle": "재고 나서 고칩니다 / 넓게 벌리는 것이 약합니다",
          "body": "강점은 문제를 좁히는 방식입니다. 느리다는 말을 들으면 어디가 느린지부터 재고, 고친 뒤에도 다시 재서 확인합니다. 약점은 익숙한 도구를 오래 붙잡는 편이라는 것입니다. Django로 충분하다고 생각해 다른 프레임워크를 늦게 봤고, 그래서 지금은 새 기술을 작은 토이 프로젝트로 먼저 써 보는 것을 규칙으로 두고 있습니다.",
        },
        "aspiration": <String, dynamic>{
          "subtitle": "1년 안에 장애 대응을 맡을 수 있는 사람으로",
          "body": "입사 후에는 담당 도메인의 데이터 흐름부터 그려 보고 싶습니다. 6개월 안에 기능 개발을 혼자 맡고, 1년 안에는 모니터링과 장애 대응을 맡을 수 있는 사람이 되는 것이 목표입니다. 인턴 때 지표를 보고 원인을 찾는 일이 가장 재미있었기 때문입니다.",
        },
      },
    },
  ),
  ResumeMockPersona(
    key: "frontend_entry",
    title: "[목업] 프론트엔드 신입 — React/TypeScript",
    content: <String, dynamic>{
      "basicInfo": <String, dynamic>{
        "name": "",
        "phone": "010-0000-0002",
        "email": "",
        "birthDate": "2000-07-21",
        "githubUrl": "https://github.com/example-frontend",
        "blogUrl": "https://example-frontend.dev",
      },
      "coreCompetencies": <String, dynamic>{
        "text": "React와 TypeScript로 컴포넌트 설계, Next.js 기반 SSR 페이지 구현. React Native로 모바일 앱 프로토타입을 만들어 배포까지 경험했습니다.",
      },
      "experience": <dynamic>[],
      "education": <dynamic>[
        <String, dynamic>{
          "id": "edu-1",
          "school": "서울디자인대학교",
          "major": "시각디자인학과",
          "startDate": "2019-03",
          "endDate": "2025-02",
          "status": "졸업",
        },
      ],
      "techStack": <dynamic>[
        <String, dynamic>{
          "id": "ts-1",
          "name": "JavaScript",
          "level": "고급",
        },
        <String, dynamic>{
          "id": "ts-2",
          "name": "TypeScript",
          "level": "중급",
        },
        <String, dynamic>{
          "id": "ts-3",
          "name": "React",
          "level": "고급",
        },
        <String, dynamic>{
          "id": "ts-4",
          "name": "React Native",
          "level": "초급",
        },
        <String, dynamic>{
          "id": "ts-5",
          "name": "Next.js",
          "level": "중급",
        },
        <String, dynamic>{
          "id": "ts-6",
          "name": "CSS",
          "level": "고급",
        },
      ],
      "certifications": <dynamic>[
        <String, dynamic>{
          "id": "cert-1",
          "name": "웹디자인기능사",
          "issuer": "한국산업인력공단",
          "acquiredDate": "2024-07",
        },
      ],
      "awards": <dynamic>[
        <String, dynamic>{
          "id": "aw-1",
          "name": "교내 해커톤 우수상",
          "organization": "서울디자인대학교",
          "date": "2024-11",
          "description": "접근성 개선 웹앱으로 수상",
        },
      ],
      "trainingExperience": <dynamic>[
        <String, dynamic>{
          "id": "tr-1",
          "course": "SK네트웍스 Family AI 캠프 34기",
          "organization": "PLAYDATA",
          "startDate": "2026-03",
          "endDate": "2026-09",
          "description": "",
        },
      ],
      "otherActivities": <dynamic>[
        <String, dynamic>{
          "id": "act-0",
          "name": "(주)예시디지털 프론트엔드 인턴",
          "startDate": "2025-06",
          "endDate": "2025-08",
          "description": "랜딩 페이지와 관리자 화면 퍼블리싱 및 React 컴포넌트 작업. 반복되던 폼 화면을 공통 컴포넌트로 묶어 코드량을 줄였습니다.",
        },
        <String, dynamic>{
          "id": "act-1",
          "name": "UI/UX 스터디",
          "startDate": "2025-01",
          "endDate": "2025-06",
          "description": "매주 서비스 하나를 골라 화면 흐름을 뜯어보고 개선안을 만들어 발표했습니다.",
        },
      ],
      "projects": <dynamic>[
        <String, dynamic>{
          "id": "prj-1",
          "name": "학습 대시보드 웹앱",
          "startDate": "2026-06",
          "endDate": "2026-08",
          "role": "프론트엔드 개발(리드)",
          "techStack": "React, TypeScript, Next.js",
          "description": "차트·필터가 있는 대시보드. 렌더링 병목을 메모이제이션으로 줄여 LCP 2.9s→1.4s.",
          "url": "https://github.com/example-frontend/dashboard",
        },
        <String, dynamic>{
          "id": "prj-2",
          "name": "출결 알림 모바일 앱",
          "startDate": "2026-05",
          "endDate": "2026-05",
          "role": "프론트엔드 개발",
          "techStack": "React Native, TypeScript",
          "description": "푸시 알림과 오프라인 캐시를 붙인 프로토타입.",
          "url": "",
        },
      ],
      "selfIntroduction": <String, dynamic>{
        "intro": <String, dynamic>{
          "subtitle": "화면 뒤의 성능까지 보는 프론트엔드 지망생",
          "body": "디자인을 전공하며 사용자가 멈칫하는 순간을 관찰하는 습관이 생겼고, 그 원인을 코드로 고치는 쪽으로 진로를 바꿨습니다.",
        },
        "motivation": <String, dynamic>{
          "subtitle": "화면이 바뀌면 반응이 바로 옵니다",
          "body": "인턴 때 버튼 위치를 옮겼더니 문의가 줄었다는 이야기를 들었습니다. 만든 것이 곧바로 쓰는 사람의 행동으로 돌아온다는 점이 프론트엔드를 계속하게 만든 이유입니다.",
        },
        "challenge": <String, dynamic>{
          "subtitle": "느린 목록을 데이터가 아니라 렌더링에서 찾았습니다",
          "body": "팀 프로젝트에서 목록 화면이 버벅였습니다. 처음엔 API가 느린 줄 알고 서버 담당에게 물었는데 응답은 100ms 안이었습니다. 프로파일러로 보니 스크롤마다 전체 목록이 다시 그려지고 있었습니다. 메모이제이션과 가상 스크롤을 적용해 끊김을 없앴습니다. 증상만 보고 남의 영역을 탓하지 않아야 한다는 걸 배웠습니다.",
        },
        "growth": <String, dynamic>{
          "subtitle": "디자이너와 같은 말을 쓰게 되기까지",
          "body": "초반에는 시안과 다르게 구현해 두고 \"거의 같다\"고 넘겼습니다. 여백 8px 차이가 왜 중요한지 설명을 듣고 나서, 시안을 받으면 간격과 상태(hover·비활성·에러)를 먼저 물어보게 됐습니다. 지금은 컴포넌트를 만들 때 상태별 화면을 먼저 정리하고 시작합니다.",
        },
        "strengthsWeaknesses": <String, dynamic>{
          "subtitle": "직접 눌러 봅니다 / 구조 설계는 아직 얕습니다",
          "body": "강점은 만든 화면을 실제 기기에서 눌러 보는 것입니다. 좁은 화면과 느린 네트워크에서 확인하는 습관이 있습니다. 약점은 상태 관리 구조를 크게 그리는 경험이 적다는 점입니다. 화면 수가 늘면 상태가 흩어지는 걸 겪었고, 지금은 규모가 큰 오픈소스의 구조를 따라 읽으며 보완하고 있습니다.",
        },
        "aspiration": <String, dynamic>{
          "subtitle": "재사용되는 컴포넌트를 남기는 사람으로",
          "body": "입사 후 6개월은 제품의 화면 흐름과 디자인 시스템을 익히는 데 쓰고 싶습니다. 이후에는 팀이 반복해서 만들던 화면을 공통 컴포넌트로 정리해, 다음 사람이 더 빨리 만들 수 있게 하는 일을 맡고 싶습니다.",
        },
      },
    },
  ),
  ResumeMockPersona(
    key: "backend_experienced_3y",
    title: "[목업] 백엔드 경력 3년 — Java/Spring Boot",
    content: <String, dynamic>{
      "basicInfo": <String, dynamic>{
        "name": "",
        "phone": "010-0000-0003",
        "email": "",
        "birthDate": "1996-11-02",
        "githubUrl": "https://github.com/example-java",
        "blogUrl": "https://example-server.tistory.com",
      },
      "coreCompetencies": <String, dynamic>{
        "text": "Java·Spring Boot·JPA로 커머스 주문 도메인을 3년간 개발·운영. MySQL 인덱스 튜닝과 Redis 캐시로 조회 API p95를 절반으로 줄인 경험. AWS ECS 기반 배포 파이프라인 운영.",
      },
      "experience": <dynamic>[
        <String, dynamic>{
          "id": "exp-1",
          "company": "(주)예시커머스",
          "role": "백엔드 개발자",
          "startDate": "2023-03",
          "endDate": "2026-03",
          "isCurrent": false,
          "description": "주문·결제 도메인 API 개발. 월 주문 40만 건 처리, 장애 대응 및 모니터링 체계 구축.",
        },
      ],
      "education": <dynamic>[
        <String, dynamic>{
          "id": "edu-1",
          "school": "부산대학교",
          "major": "정보컴퓨터공학부",
          "startDate": "2015-03",
          "endDate": "2022-02",
          "status": "졸업",
        },
      ],
      "techStack": <dynamic>[
        <String, dynamic>{
          "id": "ts-1",
          "name": "Java",
          "level": "고급",
        },
        <String, dynamic>{
          "id": "ts-2",
          "name": "Spring Boot",
          "level": "고급",
        },
        <String, dynamic>{
          "id": "ts-3",
          "name": "JPA",
          "level": "중급",
        },
        <String, dynamic>{
          "id": "ts-4",
          "name": "MySQL",
          "level": "고급",
        },
        <String, dynamic>{
          "id": "ts-5",
          "name": "Redis",
          "level": "중급",
        },
        <String, dynamic>{
          "id": "ts-6",
          "name": "AWS",
          "level": "중급",
        },
        <String, dynamic>{
          "id": "ts-7",
          "name": "Docker",
          "level": "중급",
        },
        <String, dynamic>{
          "id": "ts-8",
          "name": "Git",
          "level": "고급",
        },
      ],
      "certifications": <dynamic>[
        <String, dynamic>{
          "id": "cert-1",
          "name": "SQLD",
          "issuer": "한국데이터산업진흥원",
          "acquiredDate": "2022-06",
        },
      ],
      "awards": <dynamic>[
        <String, dynamic>{
          "id": "awd-1",
          "name": "사내 기술 개선 우수상",
          "organization": "(주)예시커머스",
          "date": "2025-12",
          "description": "주문 조회 API 응답 지연을 줄인 개선안으로 수상. 피크 시간대 타임아웃이 사라졌습니다.",
        },
      ],
      "trainingExperience": <dynamic>[
        <String, dynamic>{
          "id": "tr-1",
          "course": "SK네트웍스 Family AI 캠프 34기",
          "organization": "PLAYDATA",
          "startDate": "2026-03",
          "endDate": "2026-09",
          "description": "LLM 서비스 개발 역량 보강을 위해 수강",
        },
      ],
      "otherActivities": <dynamic>[
        <String, dynamic>{
          "id": "act-1",
          "name": "사내 백엔드 스터디 진행",
          "startDate": "2024-09",
          "endDate": "2025-06",
          "description": "격주로 대용량 처리 사례를 읽고 우리 서비스에 적용할 지점을 정리해 공유했습니다.",
        },
      ],
      "projects": <dynamic>[
        <String, dynamic>{
          "id": "prj-1",
          "name": "주문 조회 성능 개선",
          "startDate": "2025-01",
          "endDate": "2025-04",
          "role": "백엔드 개발(단독)",
          "techStack": "Java, Spring Boot, MySQL, Redis",
          "description": "N+1 제거와 커버링 인덱스, Redis 캐시 도입으로 주문 목록 API p95 1.2s→0.5s.",
          "url": "",
        },
        <String, dynamic>{
          "id": "prj-2",
          "name": "배포 파이프라인 전환",
          "startDate": "2024-06",
          "endDate": "2024-09",
          "role": "백엔드 개발",
          "techStack": "AWS, Docker",
          "description": "EC2 수동 배포를 ECS+GitHub Actions로 전환, 배포 시간 40분→8분.",
          "url": "",
        },
      ],
      "selfIntroduction": <String, dynamic>{
        "intro": <String, dynamic>{
          "subtitle": "운영까지 책임지는 백엔드 개발자",
          "body": "3년간 커머스 주문 도메인을 맡아 기능 개발보다 장애 없이 굴러가게 만드는 일에 더 많은 시간을 썼습니다.",
        },
        "motivation": <String, dynamic>{
          "subtitle": "규모가 커질 때 무너지는 지점을 다루고 싶습니다",
          "body": "주문·결제 도메인에서 월 40만 건을 처리하며, 평소엔 멀쩡하다가 피크에 무너지는 구간을 여러 번 만났습니다. 그때마다 원인을 찾아 고치는 일이 가장 배울 것이 많았습니다. 트래픽이 늘어도 버티는 구조를 만드는 일을 계속하고 싶습니다.",
        },
        "challenge": <String, dynamic>{
          "subtitle": "피크 시간 타임아웃을 없앤 일",
          "body": "행사 시간마다 주문 조회가 타임아웃 났습니다. 로그를 모아 보니 특정 쿼리가 인덱스를 타지 못하고 있었고, 조회 조건이 늘면서 생긴 문제였습니다. 인덱스를 다시 잡고 자주 쓰는 집계는 미리 계산해 두는 방식으로 바꿔 타임아웃을 없앴습니다. 이후 같은 일이 반복되지 않도록 느린 쿼리 알림을 붙였습니다.",
        },
        "growth": <String, dynamic>{
          "subtitle": "혼자 고치던 사람에서 재발을 막는 사람으로",
          "body": "처음 2년은 장애가 나면 빨리 고치는 것에 집중했습니다. 같은 장애가 세 번째 났을 때, 빨리 고치는 것만으로는 줄어들지 않는다는 걸 인정했습니다. 그 뒤로는 고친 다음에 원인과 재발 방지책을 문서로 남기고 알림을 붙이는 것까지를 한 작업으로 봅니다.",
        },
        "strengthsWeaknesses": <String, dynamic>{
          "subtitle": "운영 중인 서비스를 다뤄 봤습니다 / 새 기술 도입이 느립니다",
          "body": "강점은 돌아가는 서비스를 멈추지 않고 바꿔 본 경험입니다. 배포 순서와 롤백 계획을 먼저 정하고 움직입니다. 약점은 검증되지 않은 기술 도입에 보수적이라는 점입니다. 안정성을 우선하다 보니 팀의 시도가 늦어진 적이 있어, 지금은 영향 범위가 작은 곳부터 시험해 보는 방식으로 균형을 맞추고 있습니다.",
        },
        "aspiration": <String, dynamic>{
          "subtitle": "설계 단계에서 장애를 줄이는 사람으로",
          "body": "지금까지는 이미 만들어진 구조에서 문제를 고쳐 왔습니다. 앞으로는 설계 단계에서 부하와 실패를 미리 따져 보는 일을 맡고 싶습니다. 나아가 팀의 장애 대응 절차를 정리하고 후배가 같은 실수를 반복하지 않도록 돕는 역할을 하고 싶습니다.",
        },
      },
    },
  ),
  ResumeMockPersona(
    key: "data_entry_junior_college",
    title: "[목업] 데이터 신입 — Python/SQL (전문학사)",
    content: <String, dynamic>{
      "basicInfo": <String, dynamic>{
        "name": "",
        "phone": "010-0000-0004",
        "email": "",
        "birthDate": "2001-01-15",
        "githubUrl": "https://github.com/example-data",
        "blogUrl": "https://velog.io/@example-data",
      },
      "coreCompetencies": <String, dynamic>{
        "text": "Python·Pandas·SQL로 데이터 정제와 집계 파이프라인 구축, Airflow로 배치 스케줄링. Spark 기초와 Tensorflow 모델 학습 실습 경험.",
      },
      "experience": <dynamic>[],
      "education": <dynamic>[
        <String, dynamic>{
          "id": "edu-1",
          "school": "경기전문대학",
          "major": "빅데이터과(3년제)",
          "startDate": "2020-03",
          "endDate": "2023-02",
          "status": "졸업",
        },
      ],
      "techStack": <dynamic>[
        <String, dynamic>{
          "id": "ts-1",
          "name": "Python",
          "level": "고급",
        },
        <String, dynamic>{
          "id": "ts-2",
          "name": "SQL",
          "level": "고급",
        },
        <String, dynamic>{
          "id": "ts-3",
          "name": "Pandas",
          "level": "고급",
        },
        <String, dynamic>{
          "id": "ts-4",
          "name": "Spark",
          "level": "초급",
        },
        <String, dynamic>{
          "id": "ts-5",
          "name": "Airflow",
          "level": "중급",
        },
        <String, dynamic>{
          "id": "ts-6",
          "name": "Tensorflow",
          "level": "초급",
        },
      ],
      "certifications": <dynamic>[
        <String, dynamic>{
          "id": "cert-1",
          "name": "ADsP",
          "issuer": "한국데이터산업진흥원",
          "acquiredDate": "2023-05",
        },
        <String, dynamic>{
          "id": "cert-2",
          "name": "SQLD",
          "issuer": "한국데이터산업진흥원",
          "acquiredDate": "2023-09",
        },
      ],
      "awards": <dynamic>[
        <String, dynamic>{
          "id": "awd-1",
          "name": "공공데이터 활용 아이디어 공모전 입선",
          "organization": "한국지능정보사회진흥원",
          "date": "2025-10",
          "description": "지역별 대중교통 이용 데이터로 배차 개선안을 제안. 데이터 수집과 시각화를 맡았습니다.",
        },
      ],
      "trainingExperience": <dynamic>[
        <String, dynamic>{
          "id": "tr-1",
          "course": "SK네트웍스 Family AI 캠프 34기",
          "organization": "PLAYDATA",
          "startDate": "2026-03",
          "endDate": "2026-09",
          "description": "",
        },
      ],
      "otherActivities": <dynamic>[
        <String, dynamic>{
          "id": "act-0",
          "name": "(주)예시리테일 데이터 분석 인턴",
          "startDate": "2025-07",
          "endDate": "2025-09",
          "description": "매장별 매출 데이터를 SQL로 집계해 주간 리포트를 자동화했습니다. 손으로 만들던 4시간짜리 작업을 20분으로 줄였습니다.",
        },
        <String, dynamic>{
          "id": "act-1",
          "name": "데이터 분석 스터디",
          "startDate": "2025-02",
          "endDate": "2025-08",
          "description": "캐글 문제를 매주 하나씩 풀고 풀이를 정리해 공유했습니다.",
        },
      ],
      "projects": <dynamic>[
        <String, dynamic>{
          "id": "prj-1",
          "name": "채용공고 수집 파이프라인",
          "startDate": "2026-06",
          "endDate": "2026-08",
          "role": "데이터 엔지니어링",
          "techStack": "Python, SQL, Pandas, Airflow",
          "description": "공고 크롤 결과를 정규화·중복 제거해 일 단위로 적재. Airflow DAG 5개 운영.",
          "url": "",
        },
      ],
      "selfIntroduction": <String, dynamic>{
        "intro": <String, dynamic>{
          "subtitle": "데이터가 흐르게 만드는 사람",
          "body": "화려한 모델보다 데이터가 매일 깨지지 않고 들어오게 만드는 일에 흥미를 느낍니다.",
        },
        "motivation": <String, dynamic>{
          "subtitle": "느낌으로 정하던 것을 데이터로 바꿔 본 경험",
          "body": "인턴 때 \"주말 매출이 좋다\"는 말이 매장마다 다르다는 걸 데이터로 확인했습니다. 짐작과 실제가 다를 수 있다는 걸 눈으로 본 뒤로, 판단 근거를 만드는 일을 하고 싶어졌습니다.",
        },
        "challenge": <String, dynamic>{
          "subtitle": "4시간짜리 리포트를 20분으로",
          "body": "매주 월요일마다 매장별 매출을 손으로 취합하고 있었습니다. 자동화하려 했는데 매장마다 엑셀 양식이 조금씩 달라 막혔습니다. 양식을 통일하자고 설득하는 대신, 다른 양식도 읽히도록 파싱 규칙을 만들었습니다. 사람의 습관을 바꾸는 것보다 코드가 맞춰 주는 편이 빠를 때가 있다는 걸 배웠습니다.",
        },
        "growth": <String, dynamic>{
          "subtitle": "전문학사라는 조건을 채우는 방식",
          "body": "4년제가 아니라는 점이 불리하다는 말을 여러 번 들었습니다. 학력으로 증명할 수 없다면 결과물로 보여야 한다고 생각해, SQLD와 ADsP를 먼저 따고 분석 결과를 블로그에 정리했습니다. 부족한 통계 이론은 따로 강의를 들으며 메우고 있습니다.",
        },
        "strengthsWeaknesses": <String, dynamic>{
          "subtitle": "끝까지 정리합니다 / 모델링 경험이 얕습니다",
          "body": "강점은 지저분한 데이터를 끝까지 정리하는 끈기입니다. 결측과 중복을 어떻게 처리했는지 기록으로 남깁니다. 약점은 머신러닝 모델을 실제 서비스에 올려 본 경험이 없다는 점입니다. 분석에서 멈추지 않으려고 지금은 간단한 예측 모델을 API로 배포해 보는 연습을 하고 있습니다.",
        },
        "aspiration": <String, dynamic>{
          "subtitle": "묻기 전에 답이 준비된 지표를 만드는 사람으로",
          "body": "입사 후에는 팀이 반복해서 묻는 질문이 무엇인지부터 파악하고 싶습니다. 그 질문에 매번 손으로 답하지 않아도 되도록 지표와 대시보드를 만들어 두는 일을 맡고 싶습니다.",
        },
      },
    },
  ),
  ResumeMockPersona(
    key: "embedded_entry_regional",
    title: "[목업] 임베디드 신입 — C/C++/Linux (대전)",
    content: <String, dynamic>{
      "basicInfo": <String, dynamic>{
        "name": "",
        "phone": "010-0000-0005",
        "email": "",
        "birthDate": "1999-09-09",
        "githubUrl": "https://github.com/example-embedded",
        "blogUrl": "https://example-embedded.tistory.com",
      },
      "coreCompetencies": <String, dynamic>{
        "text": "C/C++로 임베디드 리눅스 보드(Raspberry Pi, STM32) 위에서 센서 드라이버와 RTOS 태스크를 구현. Linux 커널 모듈 빌드와 디바이스 트리 수정 경험.",
      },
      "experience": <dynamic>[],
      "education": <dynamic>[
        <String, dynamic>{
          "id": "edu-1",
          "school": "충남대학교",
          "major": "전자공학과",
          "startDate": "2018-03",
          "endDate": "2025-02",
          "status": "졸업",
        },
      ],
      "techStack": <dynamic>[
        <String, dynamic>{
          "id": "ts-1",
          "name": "C",
          "level": "고급",
        },
        <String, dynamic>{
          "id": "ts-2",
          "name": "C++",
          "level": "중급",
        },
        <String, dynamic>{
          "id": "ts-3",
          "name": "Linux",
          "level": "중급",
        },
        <String, dynamic>{
          "id": "ts-4",
          "name": "임베디드 리눅스",
          "level": "중급",
        },
        <String, dynamic>{
          "id": "ts-5",
          "name": "RTOS",
          "level": "초급",
        },
        <String, dynamic>{
          "id": "ts-6",
          "name": "Git",
          "level": "중급",
        },
      ],
      "certifications": <dynamic>[
        <String, dynamic>{
          "id": "cert-1",
          "name": "전자기사",
          "issuer": "한국산업인력공단",
          "acquiredDate": "2025-06",
        },
        <String, dynamic>{
          "id": "cert-2",
          "name": "리눅스마스터 2급",
          "issuer": "한국정보통신진흥협회",
          "acquiredDate": "2024-12",
        },
      ],
      "awards": <dynamic>[
        <String, dynamic>{
          "id": "awd-1",
          "name": "전국 대학생 임베디드 경진대회 본선 진출",
          "organization": "한국전자기술연구원",
          "date": "2024-09",
          "description": "자율주행 소형 로봇으로 참가. 모터 제어와 센서 필터링 펌웨어를 담당했습니다.",
        },
      ],
      "trainingExperience": <dynamic>[
        <String, dynamic>{
          "id": "tr-1",
          "course": "SK네트웍스 Family AI 캠프 34기",
          "organization": "PLAYDATA",
          "startDate": "2026-03",
          "endDate": "2026-09",
          "description": "엣지 AI 추론 파이프라인 학습",
        },
        <String, dynamic>{
          "id": "tr-2",
          "course": "산업체 현장실습 (펌웨어 개발)",
          "organization": "(주)예시테크",
          "startDate": "2025-09",
          "endDate": "2025-12",
          "description": "센서 보드의 UART 통신 모듈 유지보수와 시험 자동화 스크립트 작성. 수동 검증 절차를 스크립트로 옮겨 회귀 시험 시간을 줄였습니다.",
        },
      ],
      "otherActivities": <dynamic>[
        <String, dynamic>{
          "id": "act-1",
          "name": "교내 로봇 동아리",
          "startDate": "2019-03",
          "endDate": "2023-12",
          "description": "라인트레이서·드론 제어 펌웨어 담당",
        },
      ],
      "projects": <dynamic>[
        <String, dynamic>{
          "id": "prj-1",
          "name": "온도 센서 모니터링 장치",
          "startDate": "2026-05",
          "endDate": "2026-07",
          "role": "펌웨어 개발",
          "techStack": "C, Linux",
          "description": "I2C 센서 드라이버 작성, 수집값을 MQTT로 서버에 전송. 24시간 연속 동작 검증.",
          "url": "",
        },
      ],
      "selfIntroduction": <String, dynamic>{
        "intro": <String, dynamic>{
          "subtitle": "하드웨어와 소프트웨어 사이를 잇는 개발자",
          "body": "보드 위에서 코드가 실제로 움직이는 걸 볼 때 가장 즐겁습니다. 대전·충청권에서 일하고 싶습니다.",
        },
        "motivation": <String, dynamic>{
          "subtitle": "코드가 물리적으로 움직이는 것을 보는 일",
          "body": "동아리에서 처음 모터를 돌렸을 때, 화면 안에서 끝나지 않고 실제로 움직인다는 점이 좋았습니다. 제약이 많은 환경에서 동작을 맞춰 가는 일을 계속하고 싶습니다.",
        },
        "challenge": <String, dynamic>{
          "subtitle": "간헐적으로 끊기던 통신을 찾아낸 일",
          "body": "현장실습에서 UART 통신이 하루에 한두 번 끊기는 문제를 맡았습니다. 재현이 안 돼 로그를 며칠 쌓아 보니 특정 길이의 패킷에서만 발생했고, 버퍼 경계 처리가 원인이었습니다. 재현되지 않는 문제는 관찰 기간을 늘려야 한다는 걸 그때 배웠습니다.",
        },
        "growth": <String, dynamic>{
          "subtitle": "동작하는 것과 검증된 것의 차이",
          "body": "경진대회 때는 대회장에서 돌아가면 됐습니다. 현장실습에서는 같은 코드를 온도와 전압을 바꿔 가며 시험한다는 걸 보고 생각이 바뀌었습니다. 이후로는 기능을 만들면 어떤 조건에서 시험했는지 함께 적어 두게 됐습니다.",
        },
        "strengthsWeaknesses": <String, dynamic>{
          "subtitle": "데이터시트를 직접 읽습니다 / 상위 레벨 경험이 적습니다",
          "body": "강점은 모르는 칩을 만나면 데이터시트부터 찾아 읽는 것입니다. 남의 예제 코드를 그대로 쓰지 않고 레지스터 설정의 의미를 확인합니다. 약점은 서버·클라우드 쪽 경험이 적다는 점입니다. 장비에서 올린 데이터를 다루는 일이 늘고 있어, 지금은 수집 데이터를 서버로 보내는 연습을 하고 있습니다.",
        },
        "aspiration": <String, dynamic>{
          "subtitle": "대전에서 오래 일하며 깊어지는 사람으로",
          "body": "연구단지가 가까운 대전에서 계속 일하고 싶습니다. 입사 후에는 담당 보드의 하드웨어 구성을 이해하는 데 집중하고, 이후 시험 자동화까지 맡아 팀의 검증 시간을 줄이는 역할을 하고 싶습니다.",
        },
      },
    },
  ),
];
