"""채용 챗봇. 검색 / 채용 질문 / 공고 하나 묻기 세 갈래.

핵심 약속 둘.

1. **건수는 실제 결과에서 온다.** 답 문장을 LLM이 통째로 쓰면 없는 공고를 있다고
   말하게 된다. 그래서 조건 해석만 LLM에 맡기고 검색 답은 결과로 조립한다.
2. **답에는 근거가 붙는다.** 질문에는 공고를 센 표를, 공고 물음에는 그 공고 원문을
   준다. 근거 없이 쓰게 하면 우리 데이터와 상관없는 일반론이 나온다.
"""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from job_matching_bot.api import schemas
from job_matching_bot.api.service import ChatService, StoreUnavailable
from job_matching_bot.retrieval import store_search
from job_matching_bot.retrieval.store_search import KST
from job_matching_bot.ingestion.mock_source import mock_jobs
from job_matching_bot.ingestion.sqlite_store import SqliteJobStore


def turn(**kwargs) -> schemas.ChatTurnOut:
    understood = kwargs.pop("understood", "찾아볼게요.")
    intent = kwargs.pop("intent", "검색")
    counts_jobs = kwargs.pop("counts_jobs", True)
    requirement_query = kwargs.pop("requirement_query", "")
    unavailable = kwargs.pop("unavailable", "")
    job_refs = kwargs.pop("job_refs", [])
    topic = kwargs.pop("topic", "채용")
    refers_to_last_answer = kwargs.pop("refers_to_last_answer", False)
    show_more = kwargs.pop("show_more", False)
    return schemas.ChatTurnOut(
        intent=intent,
        topic=topic,
        refers_to_last_answer=refers_to_last_answer,
        show_more=show_more,
        counts_jobs=counts_jobs,
        requirement_query=requirement_query,
        unavailable=unavailable,
        job_refs=job_refs,
        filters=schemas.ChatFilters(**kwargs),
        understood=understood,
    )


def answer(text="이렇습니다.", followups=None) -> schemas.ChatAnswerOut:
    return schemas.ChatAnswerOut(answer=text, followups=followups or [])


class FakeHit:
    """벡터 검색이 돌려주는 것 중 우리가 쓰는 것은 job_id뿐이다."""

    def __init__(self, job_id: str):
        self.job_id = job_id


class ChatTestCase(unittest.TestCase):
    """공고 8건이 든 임시 저장소. LLM은 부르지 않는다."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "store.sqlite"
        base = mock_jobs()[0]
        jobs = [
            replace(
                base,
                job_id=f"J{i}",
                source_job_id=f"J{i}",
                company=f"{i}회사",
                title="백엔드 개발자",
                description="Python으로 서버를 만듭니다",
                tech_stack=["Python"],
                keywords=["IT개발·데이터"],
                region="서울 강남구" if i % 2 else "부산 해운대구",
                career_type="ENTRY",
                min_career_years=None,
                employment_type="정규직",
                deadline=None,
                status="OPEN",
            )
            for i in range(1, 9)
        ]
        with SqliteJobStore(self.path) as store:
            store.upsert(jobs, source="MOCK")

    def tearDown(self):
        self.temp.cleanup()

    def service(self, out, answered=None) -> ChatService:
        """LLM을 부르지 않는 서비스. `seen`에 무엇이 넘어갔는지 남긴다."""
        self.seen = {}
        self.advised = {}
        self.asked = {}
        self.compared = {}
        self.found = {}
        self.calls = 0
        self.by_meaning = getattr(self, "by_meaning", [])

        def generator(values):
            self.calls += 1
            self.seen.update(values)
            return out

        def adviser(values):
            self.advised.update(values)
            return answered or answer()

        def job_asker(values):
            self.asked.update(values)
            return answered or answer()

        def comparer(values):
            self.compared.update(values)
            return answered or answer()

        def finder(query, top_k, filter=None):
            self.found.update({"query": query, "top_k": top_k, "filter": filter})
            return [FakeHit(job_id) for job_id in self.by_meaning]

        return ChatService(
            generator=generator, store_path=self.path, adviser=adviser,
            job_asker=job_asker, finder=finder, comparer=comparer,
        )

    def ask(self, out, message="백엔드 찾아줘", filters=None, top_k=5,
            job_id=None, answered=None, resume_text=None, last_job_ids=None,
            last_answer_job_ids=None, seen_job_ids=None):
        request = schemas.JobChatRequest(
            message=message, filters=filters, top_k=top_k, job_id=job_id,
            resume_text=resume_text, last_job_ids=last_job_ids or [],
            last_answer_job_ids=last_answer_job_ids or [],
            seen_job_ids=seen_job_ids or [],
        )
        return self.service(out, answered=answered).chat(request)


class SearchTest(ChatTestCase):
    """말을 조건으로 바꿔 저장소에서 찾는다."""

    def test_finds_jobs_and_counts_them_from_the_store(self):
        response = self.ask(turn(roles=["백엔드"]))
        self.assertEqual(8, response.total)
        self.assertEqual(5, len(response.jobs), "top_k만큼만 보여준다")
        self.assertIn("8건", response.reply)

    def test_previous_filters_are_handed_to_the_model(self):
        """대화를 잇는 값은 서버가 아니라 요청에 실려 온다. 서버는 대화를 저장하지 않는다."""
        previous = schemas.ChatFilters(roles=["백엔드"])
        self.ask(turn(roles=["백엔드"], regions=["서울"]), message="서울만", filters=previous)
        self.assertIn("백엔드", self.seen["previous"])
        self.assertEqual("서울만", self.seen["message"])

    def test_narrowed_filters_come_back_for_the_next_turn(self):
        response = self.ask(turn(roles=["백엔드"], regions=["서울"]), message="서울만")
        self.assertEqual(["서울"], response.filters.regions)
        self.assertEqual(4, response.total, "서울 공고만 남는다")

    def test_no_result_says_so_and_offers_to_widen(self):
        response = self.ask(turn(roles=["용접"], regions=["제주"]))
        self.assertEqual(0, response.total)
        self.assertEqual([], response.jobs)
        self.assertIn("찾지 못했", response.reply)
        self.assertIn("지역 상관없이", response.suggestions)

    def test_suggestions_do_not_repeat_conditions_already_set(self):
        response = self.ask(turn(roles=["백엔드"], regions=["서울"], career="신입"))
        self.assertNotIn("서울만", response.suggestions)
        self.assertNotIn("신입만", response.suggestions)

    def test_empty_conditions_ask_back_instead_of_listing_everything(self):
        """조건이 없는데 공고를 쏟아내면 대화가 아니라 목록이 된다."""
        response = self.ask(turn(understood="어떤 일을 찾으시나요?"), message="공고")
        self.assertEqual(0, response.total)
        self.assertEqual([], response.jobs)
        self.assertIn("어떤 일", response.reply)

    def test_small_talk_keeps_previous_filters(self):
        previous = schemas.ChatFilters(roles=["백엔드"])
        response = self.ask(turn(intent="잡담"), message="안녕", filters=previous)
        self.assertEqual("안내", response.mode)
        self.assertEqual(["백엔드"], response.filters.roles)
        self.assertEqual([], response.jobs)

    def test_missing_store_is_a_clear_error(self):
        service = ChatService(generator=lambda v: turn(roles=["백엔드"]), store_path=Path("없는파일.sqlite"))
        with self.assertRaises(StoreUnavailable):
            service.chat(schemas.JobChatRequest(message="백엔드"))

    def test_condition_hits_do_not_call_the_index(self):
        """조건으로 찾았으면 벡터를 부르지 않는다. 평소 경로가 느려지면 안 된다."""
        self.by_meaning = ["J1"]
        response = self.ask(turn(roles=["백엔드"]))
        self.assertEqual(8, response.total)
        self.assertEqual({}, self.found, "인덱스를 부르지 않는다")

    def test_a_posting_whose_deadline_time_passed_is_not_sent(self):
        """조회는 날짜만 견준다. 밤 11시에 받은 "오늘 23:59 마감"을 자정 넘어 보면 닫혀
        있었다. 보내기 직전에 시각까지 본다."""
        passed = (datetime.now(KST) - timedelta(minutes=1)).isoformat(timespec="seconds")
        with SqliteJobStore(self.path) as store:
            store.upsert([replace(mock_jobs()[0], job_id="J1", source_job_id="J1",
                                  company="1회사", title="백엔드 개발자", tech_stack=["Python"],
                                  keywords=["IT개발·데이터"], region="서울 강남구",
                                  career_type="ENTRY", min_career_years=None,
                                  employment_type="정규직", deadline=passed, status="OPEN")],
                         source="MOCK")
        response = self.ask(turn(roles=["백엔드"]), top_k=8)
        self.assertNotIn("J1", [job.job_id for job in response.jobs])

    def test_reply_does_not_use_inner_words(self):
        """"직무가 맞는 건", "관련도"는 사용자가 알 필요 없는 구분이다."""
        response = self.ask(turn(roles=["백엔드"], understood=""))
        self.assertNotIn("관련도", response.reply)
        self.assertNotIn("맞는 건", response.reply)
        self.assertIn("공고 8건을 찾았어요", response.reply)

    def test_job_fields_are_ready_to_show(self):
        response = self.ask(turn(roles=["백엔드"]), top_k=1)
        job = response.jobs[0]
        self.assertTrue(job.job_id and job.company and job.title)
        self.assertEqual("신입", job.career)
        self.assertEqual("정규직", job.employment_type)


class ShowMoreTest(ChatTestCase):
    """"이거 말고"를 거듭하면 같은 조건에서 안 본 공고가 차례로 나온다.

    예전에는 같은 5건을 다시 보여 주면서 "기존 공고는 제외하고 다른 공고를
    찾아보겠습니다"라고 답했다. 목록을 끝까지 넘겨 볼 방법도 없었다.
    """

    def more(self, seen, understood="기존 공고는 제외하고 다른 공고를 찾아보겠습니다."):
        return self.ask(
            turn(roles=["백엔드"], show_more=True, understood=understood),
            message="이거 말고 다른 거", top_k=3,
            filters=schemas.ChatFilters(roles=["백엔드"]), seen_job_ids=seen,
        )

    def test_pages_do_not_overlap_and_accumulate(self):
        first = self.ask(turn(roles=["백엔드"]), top_k=3)
        page1 = [j.job_id for j in first.jobs]
        second = self.more(page1)
        page2 = [j.job_id for j in second.jobs]
        third = self.more(page1 + page2)
        page3 = [j.job_id for j in third.jobs]
        self.assertEqual(3, len(page2))
        self.assertFalse(set(page1) & set(page2), "첫 목록이 다시 나오면 안 된다")
        self.assertFalse(set(page1 + page2) & set(page3), "세 번째에도 앞 목록이 안 나온다")
        self.assertEqual(8, len(set(page1 + page2 + page3)), "끝까지 넘기면 전부 본다")

    def test_the_reply_says_which_ones_they_are(self):
        response = self.more(["J1", "J2", "J3"])
        self.assertIn("8건 중 4~6번째", response.reply)
        self.assertNotIn("제외하고", response.reply, "모델이 쓴 한 줄은 붙이지 않는다")
        self.assertEqual(8, response.total, "전체 건수는 뺀 뒤가 아니다")

    def test_when_everything_was_shown_it_says_so(self):
        response = self.more([f"J{i}" for i in range(1, 9)])
        self.assertEqual([], response.jobs)
        self.assertIn("8건이 전부예요", response.reply)

    def test_without_seen_ids_it_is_a_normal_search(self):
        """앱이 본 것을 안 보냈으면 뺄 것이 없다. 처음 찾는 것처럼 답한다."""
        response = self.more([], understood="찾아볼게요.")
        self.assertEqual(3, len(response.jobs))
        self.assertIn("공고 8건을 찾았어요", response.reply)

    def test_meaning_search_skips_what_was_shown(self):
        self.by_meaning = ["J1", "J2", "J3", "J4"]
        response = self.ask(
            turn(show_more=True, requirement_query="서버를 만드는 일"),
            message="이거 말고", top_k=2, seen_job_ids=["J1", "J2"],
        )
        self.assertEqual(["J3", "J4"], [j.job_id for j in response.jobs])
        self.assertIn("더 찾았어요", response.reply)


class BlockedBeforeTheModelTest(ChatTestCase):
    """목록에 적어 둔 말은 모델을 부르기 전에 막는다.

    무엇에 대한 말인지는 모델이 짚는다. 그 판단은 흔들릴 수 있고 호출 비용도 든다.
    적어 둔 말만큼은 그 앞에서 끊는다. 무엇을 적었는지는 `test_abuse.py`가 본다.
    """

    def test_no_call_goes_out_at_all(self):
        response = self.ask(turn(roles=["백엔드"]), message="바보")
        self.assertEqual(0, self.calls, "가르기 호출도 나가지 않는다")
        self.assertEqual("안내", response.mode)
        self.assertIn("채용과 취업 준비", response.reply)

    def test_it_blocks_even_when_a_job_is_picked(self):
        """공고를 골라 놓고 욕을 보내도 그 공고 프롬프트로 가지 않는다."""
        self.ask(turn(), message="멍청이", job_id="J1")
        self.assertEqual({}, self.asked)
        self.assertEqual(0, self.calls)

    def test_previous_conditions_survive(self):
        previous = schemas.ChatFilters(roles=["백엔드"], regions=["서울"])
        response = self.ask(turn(), message="바보", filters=previous)
        self.assertEqual(["백엔드"], response.filters.roles)
        self.assertEqual(["서울"], response.filters.regions)

    def test_a_sentence_flows_as_usual(self):
        """말 속에 들어 있을 뿐이면 평소 경로다. 여기서 막으면 하소연이 걸린다."""
        response = self.ask(turn(roles=["백엔드"]), message="미친 듯이 준비했는데 안 되네요")
        self.assertEqual(1, self.calls, "평소대로 한 번 부른다")
        self.assertEqual("검색", response.mode)


class OffTopicTest(ChatTestCase):
    """채용 밖의 일을 시킨 말. **답을 쓰는 단계로 보내지 않는다.**

    "호구"라고만 보냈더니 그 말의 뜻을 풀이하고 "이 말을 부드럽게 바꿔 말해줘"라는
    제안까지 붙여 내보냈다. 답을 쓰는 단계로 넘어가면 모델은 무엇이든 답한다.
    말투로 타이르는 것과 그 단계로 못 가게 막는 것은 다르다. 여기서는 막는다.
    """

    def test_the_answer_is_ours_not_the_models(self):
        """모델이 뜻풀이를 적어 보내도 그 문장은 나가지 않는다."""
        response = self.ask(
            turn(intent="질문", topic="그 밖", understood="'호구'는 이용당하기 쉬운 사람이라는 뜻입니다."),
            message="호구",
        )
        self.assertEqual("안내", response.mode)
        self.assertNotIn("이용당하기", response.reply)
        self.assertIn("채용과 취업 준비", response.reply)

    def test_no_one_is_asked_to_write_an_answer(self):
        self.ask(turn(intent="질문", topic="그 밖"), message="파이썬 코드 짜줘")
        self.assertEqual({}, self.advised, "답을 쓰는 단계를 부르지 않는다")
        self.assertEqual({}, self.asked)
        self.assertEqual({}, self.compared)

    def test_it_does_not_search_either(self):
        """조건이 뽑혀 있어도 목록을 내지 않는다. 물어본 것이 공고가 아니다."""
        response = self.ask(
            turn(intent="검색", topic="그 밖", roles=["백엔드"]), message="바보"
        )
        self.assertEqual([], response.jobs)
        self.assertEqual(0, response.total)
        self.assertEqual({}, self.found)

    def test_the_suggestions_point_back_to_what_we_do(self):
        response = self.ask(turn(topic="그 밖"), message="호구")
        self.assertTrue(response.suggestions)
        self.assertIn("서울 백엔드 신입", response.suggestions)

    def test_previous_conditions_survive(self):
        """상관없는 말 한마디에 앞 대화를 잃으면 다시 처음부터 말해야 한다."""
        previous = schemas.ChatFilters(roles=["백엔드"], regions=["서울"])
        response = self.ask(turn(topic="그 밖"), message="호구", filters=previous)
        self.assertEqual(["백엔드"], response.filters.roles)
        self.assertEqual(["서울"], response.filters.regions)

    def test_a_pointed_number_does_not_open_the_door(self):
        """"2번"을 붙여도 채용 밖이면 막힌다. 문이 번호보다 앞에 있다."""
        result = self.ask(
            turn(intent="질문", topic="그 밖", job_refs=[2]),
            message="2번 내용 영어로 번역해줘",
            last_job_ids=["J1", "J2"],
        )
        self.assertEqual("안내", result.mode)
        self.assertIn("채용과 취업 준비", result.reply)
        self.assertEqual({}, self.asked, "공고 묻기로 새지 않는다")

    def test_only_a_recruiting_turn_reaches_the_search(self):
        """문을 통과하는 것은 채용이라고 짚은 말뿐이다."""
        response = self.ask(turn(topic="채용", roles=["백엔드"]))
        self.assertEqual("검색", response.mode)
        self.assertEqual(8, response.total)

    def test_a_greeting_still_gets_through(self):
        """인사까지 막으면 처음 화면으로 돌아간다. 막을 것은 시키는 말이다."""
        response = self.ask(
            turn(intent="잡담", topic="인사", understood="안녕하세요!"), message="안녕"
        )
        self.assertEqual("안녕하세요!", response.reply)


class SmallTalkTest(ChatTestCase):
    """채용과 상관없는 말. **그래도 사람이 말을 건 것이다.**

    "안녕"에 사용법 안내가 돌아오면 대화가 아니라 자판기다. 잡담에는 답을 쓰는 다음
    단계가 없으므로, 갈래를 가르며 이미 받아 둔 `understood`를 그대로 내보낸다.
    답을 부르려고 모델을 한 번 더 쓰지 않는다.
    """

    def test_a_greeting_gets_a_greeting(self):
        response = self.ask(turn(intent="잡담", understood="안녕하세요!"), message="안녕")
        self.assertEqual("안내", response.mode)
        self.assertEqual("안녕하세요!", response.reply)

    def test_the_reply_costs_no_extra_call(self):
        """인사 한 번에 모델을 두 번 부를 이유가 없다."""
        self.ask(turn(intent="잡담", understood="안녕하세요!"), message="안녕")
        self.assertEqual(1, self.calls, "갈래를 가른 한 번이 전부다")
        self.assertEqual({}, self.advised)

    def test_an_empty_line_falls_back_to_the_guide(self):
        """모델이 빈손으로 오면 빈 말풍선이 뜬다. 그럴 바에는 사용법이라도 보여 준다."""
        response = self.ask(turn(intent="잡담", understood="   "), message="안녕")
        self.assertIn("공고를 찾으시려면", response.reply)

    def test_it_still_does_not_look_for_jobs(self):
        response = self.ask(turn(intent="잡담", understood="안녕하세요!"), message="안녕")
        self.assertEqual([], response.jobs)
        self.assertEqual(0, response.total)
        self.assertEqual({}, self.found)


class ConfusableTermTest(unittest.TestCase):
    """Java 로 찾을 때 JavaScript 가 걸리면 안 된다. 그렇다고 Spring 이 SpringBoot 를
    놓쳐서도 안 된다.

    `LIKE '%Java%'` 는 부분 문자열이라 실측에서 "Java" 검색 2,004건 중 198건(15%)이
    Java 태그 없이 Javascript 만 있는 공고였다. 그렇다고 단어 경계로 일괄 차단하면
    기술 태그 220종의 접두사 쌍 11개 중 10개가 같은 계열이라 열 곳이 나빠진다.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "store.sqlite"
        base = mock_jobs()[0]
        jobs = [
            replace(
                base, job_id=job_id, source_job_id=job_id, company=f"{job_id}회사",
                title=title, description=description, tech_stack=list(tech),
                keywords=["IT개발·데이터"], region="서울 강남구", career_type="ANY",
                min_career_years=None, employment_type="정규직", deadline=None, status="OPEN",
            )
            for job_id, title, description, tech in [
                ("J-JAVA", "백엔드 개발자", "Java와 Spring으로 서버를 만듭니다", ["Java", "Spring"]),
                ("J-JS", "프론트 개발자", "Javascript로 화면을 만듭니다", ["Javascript"]),
                ("J-BOTH", "풀스택 개발자", "Java와 Javascript를 씁니다", ["Java", "Javascript"]),
                ("J-BOOT", "서버 개발자", "SpringBoot로 API를 만듭니다", ["SpringBoot"]),
                ("J-KOR", "웹 개발자", "자바 기반 서비스를 운영합니다", []),
                ("J-KORJS", "화면 개발자", "자바스크립트로 UI를 만듭니다", []),
                ("J-GO", "서버 개발자", "Go로 API를 만듭니다", ["Go"]),
                ("J-GOLANG", "백엔드 개발자", "GoLang 기반 서비스", ["GoLang"]),
                ("J-MONGO", "데이터 개발자", "MongoDB와 Django를 씁니다", ["MongoDB", "Django"]),
                ("J-GOOGLE", "클라우드 엔지니어", "Google Cloud를 운영합니다", ["GCP"]),
            ]
        ]
        with SqliteJobStore(self.path) as store:
            store.upsert(jobs, source="MOCK")

    def tearDown(self):
        self.temp.cleanup()

    def found(self, term):
        result = store_search.search(
            self.path, store_search.JobFilters(skills=[term]), limit=50
        )
        return {job.job_id for job in result.jobs}

    def test_java_does_not_match_javascript(self):
        self.assertNotIn("J-JS", self.found("Java"))

    def test_java_still_matches_java(self):
        self.assertIn("J-JAVA", self.found("Java"))

    def test_a_job_with_both_is_found_by_java(self):
        """한 공고에 둘 다 있으면 Java 쪽이 걸린다. 빼면 진짜 Java 공고를 잃는다."""
        self.assertIn("J-BOTH", self.found("Java"))

    def test_javascript_still_finds_javascript(self):
        self.assertIn("J-JS", self.found("Javascript"))

    def test_korean_follows_the_same_rule(self):
        found = self.found("자바")
        self.assertIn("J-KOR", found)
        self.assertNotIn("J-KORJS", found)

    def test_go_does_not_match_mongodb_django_google(self):
        """두 글자짜리는 앞뒤를 다 봐야 한다. "Go" 는 Django 안에도 Google 안에도 있다."""
        found = self.found("Go")
        self.assertIn("J-GO", found)
        self.assertIn("J-GOLANG", found, "GoLang 은 Go 가 맞다")
        self.assertNotIn("J-MONGO", found)
        self.assertNotIn("J-GOOGLE", found)

    def test_spring_still_matches_springboot(self):
        """접두사 쌍 11개 중 10개는 같은 계열이라 막으면 손해다."""
        self.assertIn("J-BOOT", self.found("Spring"))


class MeaningSearchTest(ChatTestCase):
    """조건으로 못 찾으면 뜻으로 찾는다.

    "돈 다루는 일"은 공고에 그렇게 적히지 않는다. 글자로 훑으면 0건이고, 요건 말투로
    고쳐 쓴 문장으로 인덱스를 찾으면 회계 공고가 나온다. 실측으로 확인한 차이다
    (유사도 0.377 → 0.773).
    """

    def setUp(self):
        super().setUp()
        self.by_meaning = ["J3", "J5"]

    def test_no_condition_match_falls_back_to_meaning(self):
        response = self.ask(
            turn(keywords=["돈 다루는 일"], requirement_query="[주요업무] 전표 처리, 결산"),
            message="돈 다루는 일 찾아줘",
        )
        self.assertEqual(["J3", "J5"], [job.job_id for job in response.jobs])
        self.assertIn("뜻이 가까운", response.reply, "어떻게 찾았는지 밝힌다")
        self.assertIn("전표 처리", self.found["query"], "요건 말투 문장으로 찾는다")

    def test_weak_body_only_matches_also_fall_back(self):
        """건수는 많은데 제목·태그에 하나도 안 걸렸으면 물어본 일과 상관없는 공고들이다."""
        self.by_meaning = ["J2"]
        response = self.ask(
            turn(roles=["서버"], requirement_query="[주요업무] 서버 운영"),
            message="서버 관련 일 찾아줘",
        )
        # 목록의 공고는 제목이 "백엔드 개발자"라 "서버"는 본문에만 있다(relevance 1).
        self.assertEqual(["J2"], [job.job_id for job in response.jobs])

    def test_conditions_are_carried_into_the_index_query(self):
        """지역·고용형태는 인덱스에도 걸어야 뜻만 맞고 조건은 틀린 공고가 안 나온다."""
        self.ask(
            turn(keywords=["돈 다루는 일"], regions=["서울"], career="신입",
                 requirement_query="[주요업무] 전표 처리"),
            message="서울에서 돈 다루는 일",
        )
        self.assertIsNotNone(self.found["filter"])

    def test_a_narrow_region_is_kept_after_the_index(self):
        """인덱스의 지역은 시·도라 "강남구"를 못 건다. 가져온 뒤 주소 글자로 거른다.

        "판교"를 경기로 넓혀 찾았더니 용인·수원 공고가 나갔다.
        """
        self.by_meaning = ["J1", "J2", "J3"]  # J2는 부산이다
        response = self.ask(
            turn(keywords=["돈 다루는 일"], regions=["강남구"], requirement_query="[주요업무] 전표 처리"),
        )
        self.assertEqual(["J1", "J3"], [job.job_id for job in response.jobs])
        self.assertNotIn("강남구", str(self.found["filter"]), "인덱스에는 시·도만 건다")

    def test_closed_jobs_from_the_index_are_dropped(self):
        """인덱스는 밤에 한 번 갱신된다. 낮에 마감된 공고가 남아 있을 수 있다."""
        self.by_meaning = ["J1", "없는공고", "J2"]
        response = self.ask(
            turn(keywords=["돈 다루는 일"], requirement_query="[주요업무] 전표 처리")
        )
        self.assertEqual(["J1", "J2"], [job.job_id for job in response.jobs])

    def test_index_failure_does_not_break_the_conversation(self):
        """인덱스가 안 붙었다고 챗봇이 멈출 이유가 없다."""

        def broken(query, top_k, filter=None):
            raise RuntimeError("Pinecone 연결 실패")

        service = self.service(
            turn(keywords=["돈 다루는 일"], requirement_query="[주요업무] 전표 처리")
        )
        service._finder = broken
        response = service.chat(schemas.JobChatRequest(message="돈 다루는 일"))
        self.assertEqual(0, response.total)
        self.assertIn("찾지 못했", response.reply)

    def test_no_conditions_at_all_still_searches_by_meaning(self):
        """"돈 다루는 일"은 조건으로 옮길 말이 없다. 그렇다고 되물으면 안 된다.

        조건이 비었다는 이유로 검색 전에 되묻는 바람에 의미 검색이 아예 실행되지
        않았다. 되묻는 것은 뜻으로 찾을 문장마저 없을 때다.
        """
        response = self.ask(
            turn(requirement_query="[주요업무] 전표 처리, 결산"),
            message="돈 다루는 일 찾아줘",
        )
        self.assertEqual("검색", response.mode)
        self.assertEqual(["J3", "J5"], [job.job_id for job in response.jobs])
        self.assertIn("뜻이 가까운", response.reply)

    def test_no_requirement_query_means_no_fallback(self):
        """LLM이 문장을 안 줬으면 부를 것이 없다."""
        self.ask(turn(keywords=["돈 다루는 일"], requirement_query=""))
        self.assertEqual({}, self.found)

    def test_region_only_search_does_not_use_meaning(self):
        """찾을 말이 없으면 조건 조회가 정확하다. "서울만"에 벡터를 부르면 낭비다."""
        self.ask(turn(regions=["제주"], requirement_query="[주요업무] 무엇이든"))
        self.assertEqual({}, self.found)


class UnavailableTest(ChatTestCase):
    """모으지 않는 것으로 찾아 달라고 하면 없다고 말한다.

    실측: 오늘 받은 공고 696건 중 631건(90%)이 급여를 "면접 후 결정"으로 적었다.
    숫자가 있는 65건도 대부분 최저임금 안내다. 급여로 정렬하면 정작 많이 주는 곳이
    빠지고 순서가 거꾸로 나온다.
    """

    def test_pay_is_not_something_we_can_sort_by(self):
        response = self.ask(turn(unavailable="급여"), message="급여 제일 높은공고")
        self.assertEqual("안내", response.mode)
        self.assertEqual([], response.jobs)
        self.assertIn("면접 후 결정", response.reply, "왜 못 하는지 밝힌다")
        self.assertNotIn(
            "조건을 하나 빼거나", response.reply, "빼면 찾을 수 있다는 뜻이 되면 안 된다"
        )
        self.assertTrue(response.suggestions, "할 수 있는 것을 권한다")

    def test_it_does_not_search_with_a_condition_we_cannot_meet(self):
        """조건으로 넣으면 0건이 나오고 "지역을 넓혀 보라"는 엉뚱한 안내가 나간다."""
        self.ask(turn(unavailable="급여", keywords=["급여 높은"]))
        self.assertEqual({}, self.found, "인덱스도 부르지 않는다")

    def test_chance_of_passing_is_unknowable(self):
        response = self.ask(turn(unavailable="합격 가능성"), message="붙을 만한 데 있어?")
        self.assertEqual("안내", response.mode)
        self.assertIn("알 수 없어요", response.reply)


class RecommendHandoffTest(ChatTestCase):
    """이력서로 골라 달라는 말은 추천이 맡는다. 챗봇은 이력서를 받지 않는다."""

    def test_resume_based_ask_hands_off_instead_of_searching(self):
        """앞 대화에 조건이 남아 있어도 그걸로 목록을 내면 안 된다.

        실제로 "Python · 신입" 조건이 남은 상태에서 "내 이력서 보면 제일 잘 어울리는
        공고가 뭐예요?"를 물었더니, 이력서가 화면 왼쪽에 멀쩡히 있는데도 "이력서를
        먼저 올려 주세요"라고 답하면서 그 조건으로 486건을 검색해 보여 줬다.
        """
        previous = schemas.ChatFilters(skills=["Python"], career="신입")
        response = self.ask(
            turn(intent="추천", skills=["Python"], career="신입"),
            message="지금 내 이력서 보면 제일 잘 어울리는 공고가 뭐예요?",
            filters=previous,
        )
        self.assertEqual("추천", response.mode)
        self.assertEqual([], response.jobs, "챗봇이 목록을 내지 않는다")
        self.assertEqual(0, response.total)
        self.assertNotIn("올려", response.reply, "이력서가 없다고 하지 않는다")

    def test_previous_conditions_survive_the_handoff(self):
        """추천을 보고 와서 "그럼 서울만"으로 이어갈 수 있어야 한다."""
        previous = schemas.ChatFilters(roles=["백엔드"], regions=["서울"])
        response = self.ask(turn(intent="추천"), message="나한테 맞는 공고", filters=previous)
        self.assertEqual(["백엔드"], response.filters.roles)
        self.assertEqual(["서울"], response.filters.regions)


class AdviceTest(ChatTestCase):
    """채용 질문. 답은 LLM이 쓰지만 **숫자는 우리가 세어 건네준다.**"""

    def test_question_is_answered_with_counted_jobs(self):
        response = self.ask(
            turn(intent="질문", roles=["백엔드"]),
            message="백엔드 신입은 뭘 준비해야 해?",
            answered=answer("Python을 적은 공고가 많아요."),
        )
        self.assertEqual("질문", response.mode)
        self.assertEqual("Python을 적은 공고가 많아요.", response.reply)
        self.assertIn("8건", self.advised["stats"], "센 결과가 근거로 넘어가야 한다")
        self.assertIn("Python", self.advised["stats"])
        self.assertEqual("백엔드 신입은 뭘 준비해야 해?", self.advised["question"])

    def test_answer_does_not_attach_jobs(self):
        """사람이 답을 매겨 보니 질문 답에는 공고가 필요 없었다. 센 건수만 남긴다.

        예전에는 근거로 3건을 붙였고, 그걸 찾고 마감을 확인하느라 시간이 들었다.
        """
        response = self.ask(turn(intent="질문", roles=["백엔드"]), message="뭐가 필요해?")
        self.assertEqual([], response.jobs)
        self.assertEqual(8, response.total)

    def test_a_countable_question_with_no_conditions_counts_everything(self):
        """"요즘 많이 요구하는 기술이 뭐야?"에는 조건이 없다. 그래도 전체를 세면 답이 된다.

        조건이 없다고 세지 않았더니, 세어 달라는 질문에 "저희가 모은 공고로는 알 수
        없어요"라고 답했다. 조건 유무는 셀지 말지의 기준이 아니다.
        """
        response = self.ask(
            turn(intent="질문"), message="요즘 많이 요구하는 기술이 뭐야?"
        )
        self.assertEqual("질문", response.mode)
        self.assertIn("전체", self.advised["stats"])
        self.assertIn("Python", self.advised["stats"])
        self.assertEqual(8, response.total)

    def test_the_table_says_what_it_counted(self):
        """모수를 밝히지 않으면 모델이 표를 믿지 못해 "알 수 없다"고 물러선다.

        실제로 "신입 공고의 기술"을 물었을 때 표에 그 분포가 들어 있는데도 "전체 공고
        기준이라 신입 공고에서의 비율은 알 수 없다"고 답했다.
        """
        self.ask(turn(intent="질문", career="신입"), message="신입 공고에 자주 나오는 기술은?")
        stats = self.advised["stats"]
        self.assertIn("센 것:", stats)
        self.assertIn("신입이 지원할 수 있는", stats)
        self.assertIn("경력무관", stats, "무엇이 함께 들어갔는지 밝힌다")

    def test_advice_questions_do_not_count(self):
        """세어서 답할 물음이 아니면 조건이 남아 있어도 숫자를 대지 않는다.

        "서울 백엔드 신입"을 찾아본 뒤 "자소서 어떻게 써?"라고 물으면 조건은 그대로
        남아 있다. 그걸로 표를 만들면 상관없는 숫자가 답의 첫 문단을 차지한다.
        """
        response = self.ask(
            turn(intent="질문", counts_jobs=False, roles=["백엔드"], regions=["서울"]),
            message="자소서 어떻게 써?",
        )
        self.assertIn("세어 답할 것이 아니다", self.advised["stats"])
        self.assertEqual([], response.jobs)
        self.assertEqual(0, response.total)

    def test_followups_become_suggestions(self):
        response = self.ask(
            turn(intent="질문", roles=["백엔드"]),
            answered=answer(followups=["서울은 몇 건이야?", "이 조건으로 공고 보여줘", "가", "나"]),
        )
        self.assertEqual(3, len(response.suggestions), "세 개까지만")
        self.assertIn("서울은 몇 건이야?", response.suggestions)


class JobQuestionTest(ChatTestCase):
    """공고 하나를 놓고 묻기. **그 공고 원문만** 근거로 쓴다."""

    def test_asking_about_a_job_skips_the_filter_step(self):
        """공고를 골라 물었으면 무슨 말이든 그 공고 이야기다. 조건을 다시 뽑지 않는다."""
        response = self.ask(
            turn(roles=["엉뚱한직무"]), message="신입도 지원할 수 있어?", job_id="J1"
        )
        self.assertEqual("공고", response.mode)
        self.assertEqual(0, self.calls, "조건 추출 LLM은 부르지 않는다")

    def test_the_resume_goes_with_the_question(self):
        """이력서 화면에서 물었으면 이력서를 함께 넘긴다.

        안 넘기던 때에는 "이 공고 나한테 맞아?"에 "현재 이력서 내용을 볼 수 없어
        판단하기는 어렵다"고 답했다. 이력서는 바로 옆 화면에 열려 있었다.
        """
        self.ask(
            turn(), message="나한테 맞는 공고야?", job_id="J1",
            resume_text="Python으로 FastAPI 추천 API를 만들었습니다.",
        )
        self.assertIn("FastAPI", self.asked["resume"])

    def test_without_a_resume_the_model_is_told_so(self):
        """안 받았으면 없다고 분명히 알린다. 빈 칸을 주면 지어내 채운다."""
        self.ask(turn(), message="뭘 요구해?", job_id="J1")
        self.assertEqual("(없음)", self.asked["resume"])

    def test_the_posting_text_is_handed_to_the_model(self):
        self.ask(turn(), message="뭘 요구해?", job_id="J1")
        job = self.asked["job"]
        self.assertIn("1회사", job)
        self.assertIn("백엔드 개발자", job)
        self.assertIn("Python으로 서버를 만듭니다", job, "본문이 통째로 들어가야 한다")
        self.assertIn("신입", job)
        self.assertEqual("뭘 요구해?", self.asked["question"])

    def test_previous_filters_survive_a_job_question(self):
        """공고를 물어본 뒤 "다른 것도 보여줘"로 돌아갈 수 있어야 한다."""
        previous = schemas.ChatFilters(roles=["백엔드"], regions=["서울"])
        response = self.ask(turn(), message="이거 어때?", job_id="J1", filters=previous)
        self.assertEqual(["백엔드"], response.filters.roles)
        self.assertEqual(["서울"], response.filters.regions)

    def test_missing_job_says_so_instead_of_guessing(self):
        response = self.ask(turn(), message="이거 어때?", job_id="없는공고")
        self.assertEqual("안내", response.mode)
        self.assertIn("찾지 못했", response.reply)
        self.assertEqual({}, self.asked, "없는 공고로 LLM을 부르지 않는다")


class JobReferenceTest(ChatTestCase):
    """"2번 자세히 봐줘" — 직전 목록에서 자리를 가리킨 말.

    서버는 대화를 저장하지 않는다. 직전에 무엇을 보여 줬는지는 앱이 `last_job_ids`로
    되돌려 줘야 안다. 이게 없던 때는 사용자가 공고 카드를 눌러 `job_id`를 보내야만
    그 공고를 놓고 물을 수 있었다.
    """

    def test_the_second_one_becomes_that_job(self):
        result = self.ask(
            turn(intent="질문", job_refs=[2]),
            message="2번 자세히 봐줘",
            last_job_ids=["J1", "J2", "J3"],
        )
        self.assertEqual("공고", result.mode)
        self.assertIn("2회사", self.asked["job"])

    def test_the_first_one_too(self):
        self.ask(
            turn(intent="질문", job_refs=[1]),
            message="첫 번째 거 자격요건 알려줘",
            last_job_ids=["J1", "J2", "J3"],
        )
        self.assertIn("1회사", self.asked["job"])

    def test_a_number_past_the_end_is_not_guessed(self):
        """세 건을 보여 줬는데 "5번"이라고 하면 엉뚱한 공고를 집지 않는다."""
        result = self.ask(
            turn(intent="질문", job_refs=[5]),
            message="5번 알려줘",
            last_job_ids=["J1", "J2", "J3"],
        )
        self.assertNotEqual("공고", result.mode)
        self.assertEqual({}, self.asked)

    def test_without_a_previous_list_it_says_so(self):
        """앞에 보여 준 것이 없으면 조건 검색으로 내려보내지 않고 그렇다고 말한다."""
        result = self.ask(
            turn(intent="질문", job_refs=[2]), message="2번 알려줘", last_job_ids=[]
        )
        self.assertEqual("안내", result.mode)
        self.assertIn("앞에 보여 드린 공고가 없어요", result.reply)

    def test_no_reference_still_searches(self):
        """번호를 안 가리킨 말은 예전 그대로 흐른다."""
        result = self.ask(turn(roles=["백엔드"]), last_job_ids=["J1", "J2"])
        self.assertEqual("검색", result.mode)
        self.assertEqual({}, self.asked)

    def test_the_tapped_card_still_wins(self):
        """카드를 눌러 물으면 그 공고다. 말 속의 번호를 따지지 않는다."""
        self.ask(
            turn(intent="질문", job_refs=[2]),
            message="여기 2번 항목이 뭐야?",
            job_id="J7",
            last_job_ids=["J1", "J2", "J3"],
        )
        self.assertIn("7회사", self.asked["job"])


class LastAnswerTest(ChatTestCase):
    """"두 공고의 자격요건만 간단히 비교해줘" — 번호 없이 방금 그거를 가리킨 말.

    비교 답을 받은 직후 챗봇이 스스로 내놓은 제안이 이 꼴이다. 그런데 번호가 없어
    가리킨 자리가 없고, 서버는 대화를 저장하지 않아 방금 무엇을 견줬는지 모른다.
    그래서 자기가 권한 말을 눌렀는데 **"두 공고의 자격요건 내용이 보이지 않아 비교할
    수 없습니다"**라고 답했다.

    `last_job_ids`로는 안 된다. 그건 번호가 가리킬 *목록*이고, 여기서 필요한 것은
    직전 답이 다룬 *대상*이다. 둘은 다르다 — 비교하고 나서도 목록은 찾아 준 다섯 건
    그대로여야 "아까 1번 3번"이 걸린다.
    """

    def test_two_discussed_jobs_are_compared_again(self):
        result = self.ask(
            turn(intent="질문", refers_to_last_answer=True),
            message="두 공고의 자격요건만 간단히 비교해줘",
            last_job_ids=["J1", "J2", "J3", "J4", "J5"],
            last_answer_job_ids=["J2", "J5"],
        )
        self.assertEqual("비교", result.mode)
        self.assertIn("2회사", self.compared["job_a"])
        self.assertIn("5회사", self.compared["job_b"])

    def test_one_discussed_job_is_asked_about(self):
        result = self.ask(
            turn(intent="질문", refers_to_last_answer=True),
            message="이 공고 마감일이 언제야?",
            last_job_ids=["J1", "J2", "J3"],
            last_answer_job_ids=["J3"],
        )
        self.assertEqual("공고", result.mode)
        self.assertIn("3회사", self.asked["job"])

    def test_the_numbering_list_is_not_used_for_this(self):
        """목록의 앞 두 건을 집으면 안 된다. 사용자가 말한 것은 방금 견준 두 건이다."""
        self.ask(
            turn(intent="질문", refers_to_last_answer=True),
            message="둘 다 신입 지원 가능해?",
            last_job_ids=["J1", "J2", "J3", "J4", "J5"],
            last_answer_job_ids=["J4", "J5"],
        )
        self.assertIn("4회사", self.compared["job_a"])
        self.assertIn("5회사", self.compared["job_b"])

    def test_too_many_to_pick_asks_back(self):
        """직전 답이 다섯 건을 보여 줬는데 "두 공고"라고 하면 어느 둘인지 모른다.

        앞의 둘을 집으면 사용자가 생각한 공고가 아닐 수 있고, 답은 그럴듯해서 틀린
        줄도 모른다. 되묻는 편이 낫다.
        """
        result = self.ask(
            turn(intent="질문", refers_to_last_answer=True),
            message="두 공고 비교해줘",
            last_job_ids=["J1", "J2", "J3", "J4", "J5"],
            last_answer_job_ids=["J1", "J2", "J3", "J4", "J5"],
        )
        self.assertEqual("안내", result.mode)
        self.assertIn("번호로 알려 주세요", result.reply)
        self.assertEqual({}, self.compared)
        self.assertEqual({}, self.asked)

    def test_nothing_discussed_yet_says_so(self):
        result = self.ask(
            turn(intent="질문", refers_to_last_answer=True), message="두 공고 비교해줘"
        )
        self.assertEqual("안내", result.mode)
        self.assertIn("앞에 보여 드린 공고가 없어요", result.reply)

    def test_a_number_still_wins(self):
        """번호를 댔으면 그 번호다. 목록에서 고른다."""
        result = self.ask(
            turn(intent="질문", job_refs=[1, 3], refers_to_last_answer=False),
            message="1번하고 3번 비교해줘",
            last_job_ids=["J1", "J2", "J3"],
            last_answer_job_ids=["J4", "J5"],
        )
        self.assertEqual("비교", result.mode)
        self.assertIn("1회사", self.compared["job_a"])
        self.assertIn("3회사", self.compared["job_b"])

    def test_narrowing_the_list_is_a_search(self):
        """"그중에 정규직만"은 목록을 좁히는 말이다. 다섯 건 중 어느 것이냐고 되묻지 않는다."""
        ids = ["J1", "J2", "J3", "J4", "J5"]
        result = self.ask(
            turn(roles=["백엔드"], employment_types=["정규직"], refers_to_last_answer=True),
            message="그중에 정규직만",
            filters=schemas.ChatFilters(roles=["백엔드"]),
            last_job_ids=ids,
            last_answer_job_ids=ids,
        )
        self.assertEqual("검색", result.mode)
        self.assertNotIn("번호로 알려 주세요", result.reply)
        self.assertEqual(["정규직"], result.filters.employment_types)
        self.assertTrue(result.jobs)

    def test_narrowing_before_any_list_still_searches(self):
        """앞 목록이 없어도 조건이 있으면 찾는다. "보여 드린 공고가 없어요"로 막지 않는다."""
        result = self.ask(
            turn(roles=["백엔드"], employment_types=["정규직"], refers_to_last_answer=True),
            message="여기서 정규직만",
        )
        self.assertEqual("검색", result.mode)
        self.assertNotIn("앞에 보여 드린 공고가 없어요", result.reply)

    def test_a_new_search_is_not_a_reference(self):
        response = self.ask(
            turn(roles=["백엔드"], refers_to_last_answer=False),
            message="다른 공고도 보여줘",
            last_answer_job_ids=["J1", "J2"],
        )
        self.assertEqual("검색", response.mode)


class JobCompareTest(ChatTestCase):
    """"1번하고 3번 비교해줘" — 자리를 둘 가리키면 비교다.

    따로 의도를 두지 않는다. 개수가 곧 신호이고, LLM이 한 번 더 가를 일을 만들지
    않는 편이 틀릴 여지가 적다.
    """

    def test_two_references_compare_both(self):
        result = self.ask(
            turn(intent="질문", job_refs=[1, 3]),
            message="1번하고 3번 비교해줘",
            last_job_ids=["J1", "J2", "J3"],
        )
        self.assertEqual("비교", result.mode)
        self.assertIn("1회사", self.compared["job_a"])
        self.assertIn("3회사", self.compared["job_b"])
        self.assertEqual({}, self.asked, "하나 묻기로 새면 안 된다")

    def test_the_spoken_order_is_kept(self):
        self.ask(
            turn(intent="질문", job_refs=[3, 1]),
            message="3번이랑 1번 중 뭐가 나아?",
            last_job_ids=["J1", "J2", "J3"],
        )
        self.assertIn("3회사", self.compared["job_a"])
        self.assertIn("1회사", self.compared["job_b"])

    def test_both_jobs_come_back_for_the_screen(self):
        result = self.ask(
            turn(intent="질문", job_refs=[1, 2]), last_job_ids=["J1", "J2", "J3"]
        )
        self.assertEqual(["J1", "J2"], [job.job_id for job in result.jobs])
        self.assertEqual(2, result.total)

    def test_the_same_number_twice_is_not_a_comparison(self):
        """"1번하고 1번"은 비교가 아니다. 하나 묻기로 내려간다."""
        result = self.ask(
            turn(intent="질문", job_refs=[1, 1]), last_job_ids=["J1", "J2"]
        )
        self.assertEqual("공고", result.mode)
        self.assertEqual({}, self.compared)

    def test_a_number_past_the_end_is_dropped(self):
        """세 건을 보여 줬는데 "2번하고 9번"이면 남는 것이 하나뿐이라 비교가 아니다."""
        result = self.ask(
            turn(intent="질문", job_refs=[2, 9]), last_job_ids=["J1", "J2", "J3"]
        )
        self.assertEqual("공고", result.mode)
        self.assertIn("2회사", self.asked["job"])

    def test_the_resume_is_passed_through(self):
        self.ask(
            turn(intent="질문", job_refs=[1, 2]),
            message="둘 중 나한테 맞는 건?",
            last_job_ids=["J1", "J2"],
            resume_text="FastAPI로 추천 API를 개발했습니다.",
        )
        self.assertIn("FastAPI", self.compared["resume"])

    def test_without_a_resume_it_says_none(self):
        self.ask(turn(intent="질문", job_refs=[1, 2]), last_job_ids=["J1", "J2"])
        self.assertEqual("(없음)", self.compared["resume"])

    def test_a_closed_job_is_not_compared(self):
        """비교하는 사이에 한쪽이 마감됐을 수 있다. 없는 공고를 상대로 견주지 않는다."""
        service = self.service(turn(intent="질문", job_refs=[1, 2]))
        service.drop_dead = lambda ids: {i for i in ids if i != "J2"}
        result = service.chat(
            schemas.JobChatRequest(
                message="1번하고 2번 비교해줘", last_job_ids=["J1", "J2"]
            )
        )
        self.assertEqual("공고", result.mode)
        self.assertIn("1회사", self.asked["job"])
        self.assertEqual({}, self.compared)

    def test_both_closed_says_so(self):
        service = self.service(turn(intent="질문", job_refs=[1, 2]))
        service.drop_dead = lambda ids: set()
        result = service.chat(
            schemas.JobChatRequest(
                message="1번하고 2번 비교해줘", last_job_ids=["J1", "J2"]
            )
        )
        self.assertEqual("안내", result.mode)
        self.assertIn("비교할 공고를 찾지 못했어요", result.reply)


if __name__ == "__main__":
    unittest.main()


class AskJobLivenessTest(ChatTestCase):
    """공고 하나를 놓고 물을 때도 마감을 확인한다.

    마감일이 남아 있어도 회사가 채용을 마치면 먼저 닫는다. 검색·질문·비교는 이미
    확인하는데 여기만 안 했다. 어제 띄워 둔 화면을 오늘 다시 눌러 "이 공고 자격요건
    뭐야?"라고 물으면 마감된 공고를 열려 있는 것처럼 답했다.

    같은 대화 안에서 방금 본 공고면 24시간 캐시가 있어 요청이 안 나간다.
    """

    def test_a_closed_job_is_not_answered(self):
        service = self.service(turn(intent="질문"))
        service.drop_dead = lambda ids: set()
        result = service.chat(schemas.JobChatRequest(message="자격요건 알려줘", job_id="J1"))
        self.assertEqual("안내", result.mode)
        self.assertIn("접수가 마감됐어요", result.reply)
        self.assertEqual({}, self.asked, "마감된 공고를 LLM에 넘기지 않는다")

    def test_a_live_job_is_answered_as_before(self):
        service = self.service(turn(intent="질문"))
        service.drop_dead = lambda ids: set(ids)
        result = service.chat(schemas.JobChatRequest(message="자격요건 알려줘", job_id="J1"))
        self.assertEqual("공고", result.mode)
        self.assertIn("1회사", self.asked["job"])

    def test_the_check_runs_for_a_numbered_reference_too(self):
        """"2번 자세히 봐줘"도 같은 길로 내려간다."""
        service = self.service(turn(intent="질문", job_refs=[2]))
        service.drop_dead = lambda ids: set()
        result = service.chat(schemas.JobChatRequest(
            message="2번 자세히 봐줘", last_job_ids=["J1", "J2", "J3"]))
        self.assertEqual("안내", result.mode)
        self.assertIn("접수가 마감됐어요", result.reply)


class OrdinalStrippedTest(unittest.TestCase):
    """"2번"은 서버가 이미 풀었다. 그 말을 LLM에 그대로 넘기면 안 된다.

    공고 원문 하나만 보고 있는 모델은 "2번"을 본문 속 항목 번호로 읽는다. 실제로
    이렇게 답했다.

        이 공고에는 번호가 매겨진 항목이 없어 '2번'이 무엇을 뜻하는지 확인하기
        어렵습니다. 자세히 보고 싶은 항목을 말씀해 주세요.

    사용자는 목록에서 2번을 가리킨 것이고 서버는 그 공고를 이미 찾아 놨다.
    """

    def strip(self, message):
        from job_matching_bot.api.service import _without_ordinal
        return _without_ordinal(message)

    def test_the_number_goes_and_the_question_stays(self):
        self.assertEqual("자세히 봐줘", self.strip("2번 자세히 봐줘"))
        self.assertEqual("자격요건 알려줘", self.strip("첫 번째 거 자격요건 알려줘"))

    def test_the_particle_goes_with_it(self):
        """`3번 공고는` 에서 `는`만 남으면 물음이 깨진다."""
        self.assertEqual("어디야?", self.strip("3번 공고는 어디야?"))
        self.assertEqual("비슷한 거 더 있어?", self.strip("2번이랑 비슷한 거 더 있어?"))

    def test_a_bare_number_becomes_a_real_question(self):
        """그냥 "2번"이면 무엇을 묻는지 모른다. 빈 물음을 넘기지 않는다."""
        asked = self.strip("2번")
        self.assertNotEqual("", asked)
        self.assertNotIn("2번", asked)

    def test_a_question_without_an_ordinal_is_untouched(self):
        for message in ("이 공고 자격요건 뭐야?", "나한테 맞아?", "연봉 나와 있어?"):
            self.assertEqual(message, self.strip(message), message)


class AskJobEchoesTheJobTest(ChatTestCase):
    """어느 공고를 두고 답했는지 함께 보낸다.

    없으면 화면이 답만 띄우고, 사용자는 그게 자기가 가리킨 공고인지 확인할 길이 없다.
    """

    def test_the_answered_job_comes_back(self):
        result = self.ask(turn(intent="질문"), message="자격요건 알려줘", job_id="J3")
        self.assertEqual("공고", result.mode)
        self.assertEqual(["J3"], [j.job_id for j in result.jobs])
        self.assertEqual(1, result.total)

    def test_a_numbered_reference_echoes_the_right_one(self):
        result = self.ask(
            turn(intent="질문", job_refs=[2]),
            message="2번 자세히 봐줘", last_job_ids=["J1", "J2", "J3"],
        )
        self.assertEqual(["J2"], [j.job_id for j in result.jobs])

    def test_the_ordinal_is_not_sent_to_the_model(self):
        self.ask(turn(intent="질문", job_refs=[2]),
                 message="2번 자세히 봐줘", last_job_ids=["J1", "J2", "J3"])
        self.assertNotIn("2번", self.asked["question"])
        self.assertIn("자세히", self.asked["question"])


class ChatTimingsTest(ChatTestCase):
    """갈래마다 지난 단계의 시간만 남긴다. LLM 횟수가 0~2번으로 달라 전체 시간만으로는
    어디가 느린지 모른다."""

    def _ask_quietly(self, *args, **kwargs):
        import io
        from contextlib import redirect_stdout

        out = io.StringIO()
        with redirect_stdout(out):
            result = self.ask(*args, **kwargs)
        return result, out.getvalue()

    def test_search_times_routing_lookup_and_liveness(self):
        result, log = self._ask_quietly(turn(roles=["백엔드"]))
        self.assertEqual("검색", result.mode)
        self.assertEqual(["route", "search", "liveness", "total"], list(result.timings_ms))
        self.assertIn("[챗봇 시간] 검색 · 가르기", log)

    def test_a_card_question_skips_routing(self):
        """카드를 눌러 물으면 가르지 않는다. 가르기 시간이 없어야 맞다."""
        result, _ = self._ask_quietly(turn(intent="질문"), message="자격요건 알려줘", job_id="J3")
        self.assertEqual(["store", "liveness", "answer", "total"], list(result.timings_ms))

    def test_a_blocked_word_has_only_the_total(self):
        result, log = self._ask_quietly(turn(), message="호구")
        self.assertEqual(["total"], list(result.timings_ms))
        self.assertIn("[챗봇 시간] 안내", log)
