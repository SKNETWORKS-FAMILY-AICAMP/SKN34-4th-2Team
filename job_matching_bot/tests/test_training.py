"""교육 과정 모집은 채용이 아니다 — 추천 · 검색에서 뺀다(retrieval/training.py)."""

import unittest

from job_matching_bot.retrieval.training import is_training


class TrainingTitleTest(unittest.TestCase):
    def test_training_programs(self):
        for title in (
            "[IBM] Cloud Native Dev base AI agent 6기",
            "SW 개발자 부트캠프 교육생 모집",
            "2026 K-뉴딜 아카데미 Let's Grow with LG전자 2기",
            "K-디지털 트레이닝 백엔드 과정",
            "국비지원 풀스택 개발자 양성 과정 수강생 모집",
            "[국비최대무료/취업연계/기숙사제공]AI인공지능/빅데이터/풀스택/부트캠프",
            "(취업연계)[IBM]AI Agent 서비스 개발자 교육생 모집",
            "[K-뉴딜아카데미] 전력시장 디지털 인재 아카데미",
            "2026 직업상담사 취업예정자 양성과정 20기 모집",
            "[K-뉴딜] 어도비 AI 콘텐츠 마케팅 과정",
            "[K-뉴딜] Microsoft AI 실전 프로젝트 과정",
        ):
            with self.subTest(title=title):
                self.assertTrue(is_training(title))

    def test_hiring_is_not_training(self):
        for title in (
            "백엔드 개발자 채용",
            "채용연계형 SW 아카데미 개발자 모집",
            "2026년 하반기 AI 인재 1기 신입사원 공개채용",
            "2026 CJ그룹 신입사원 모집",
            "Java 5년 이상 경력자 모집",
            "AI 개발자 채용 (AI개발 국비 교육 이수必)",
            "AI 엔지니어 채용 (이어드림스쿨/K-디지털트레이닝/폴리텍하이테크)",
            "[SBS아카데미게임학원 부평] 취업지원 담당자 채용",
            "(코리아AI아카데미) IT분야 강사 및 직업훈련교사 채용",
            "채용약정형 첨단의료 AI 서비스 개발 부트캠프",
            "AI 백엔드 개발(이어드림스쿨, K-디지털 트레이닝, 폴리텍 하이테크 수료)",
            "K-디지털트레이닝, 이어드림 스쿨, 폴리텍 출신 SW 개발자를 모십니다.",
            "[다온H&S] LLM·RAG 기반 AI/Data Engineer(정부 AI 교육과정 수료자)",
            "[하이미디어 종로] 교육사업분야 공모사업운영 인력모집(K디지털트레이닝,",
            "[크라우드아카데미] 사업팀 매니저",
            "[젠지글로벌아카데미] 해외 대학 입시 컨설턴트 (경력)",
            "박사후연수생 (생물학 전공)",
            "[IT 강사채용] SKT K뉴딜 정보보안 강사채용",
            "석사과정 연구원 (AI 비전)",
            "물류로봇 기업 I 수주장비 전과정 총괄 (부장~임원)",
            "",
            None,
        ):
            with self.subTest(title=title):
                self.assertFalse(is_training(title))


if __name__ == "__main__":
    unittest.main()
