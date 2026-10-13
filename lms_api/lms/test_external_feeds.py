from datetime import date
from unittest import mock

from django.test import SimpleTestCase

from lms import external_feeds as feeds


def _row(label, subject, topic, detail=None):
    return {"date_label": label, "subject": subject, "topic": topic, "detail": detail if detail is not None else topic}


class QualExamItemTests(SimpleTestCase):
    def test_empty_dates_become_none(self):
        item = feeds._qual_item({
            "implYy": "2026", "implSeq": "107", "qualgbNm": "국가기술자격", "description": "기능사",
            "docExamStartDt": "", "pracExamStartDt": "20261207", "docPassDt": "null",
        })
        self.assertIsNone(item["docExamStartDt"])
        self.assertIsNone(item["docPassDt"])
        self.assertEqual(item["pracExamStartDt"], "20261207")
        self.assertEqual(item["implSeq"], 107)

    def test_single_item_object_is_listed(self):
        rows = feeds._qual_rows({"body": {"items": {"item": {"implYy": "2026"}}}})
        self.assertEqual(rows, [{"implYy": "2026"}])

    def test_missing_key_is_reported(self):
        with mock.patch.dict("os.environ", {"DATA_GO_KR_SERVICE_KEY": ""}):
            with self.assertRaises(feeds.FeedError) as ctx:
                feeds.fetch_qual_exams(2026)
        self.assertEqual(ctx.exception.status, 503)

    def test_paginates_until_total(self):
        pages = [
            {"header": {"resultCode": "00"}, "body": {"totalCount": 51, "items": [{"implSeq": i} for i in range(50)]}},
            {"header": {"resultCode": "00"}, "body": {"totalCount": 51, "items": [{"implSeq": 99}]}},
        ]
        with mock.patch.dict("os.environ", {"DATA_GO_KR_SERVICE_KEY": "k"}), \
                mock.patch.object(feeds, "_get_json", side_effect=pages) as get:
            items, total = feeds.fetch_qual_exams(2026)
        self.assertEqual((len(items), total, get.call_count), (51, 51, 2))

    def test_same_round_with_two_reg_periods_is_merged(self):
        base = {"jmCd": "1320", "implYy": "2026", "implSeq": 3, "description": "국가기술자격 기사 (2026년도 제3회)",
                "docExamStartDt": "20260807", "pracRegStartDt": "20260921", "pracRegEndDt": "20261019"}
        late = {**base, "docRegStartDt": "20260801", "docRegEndDt": "20260802"}
        early = {**base, "docRegStartDt": "20260720", "docRegEndDt": "20260723"}
        other = {**base, "implSeq": 2, "docRegStartDt": "20260420", "docRegEndDt": "20260423"}
        merged = feeds._merge_extra_regs([late, early, other])
        self.assertEqual(len(merged), 2)
        third = next(m for m in merged if m["implSeq"] == 3)
        self.assertEqual((third["docRegStartDt"], third["docRegEndDt"]), ("20260720", "20260723"))
        self.assertEqual(third["docRegExtra"], [["20260801", "20260802"]])
        self.assertNotIn("pracRegExtra", third)

    def test_subjects_are_tagged_with_code_and_name(self):
        row = {"implYy": "2026", "implSeq": 1, "description": "기사", "docRegStartDt": "20260112"}
        page = {"header": {"resultCode": "00"}, "body": {"totalCount": 1, "items": [row]}}
        with mock.patch.dict("os.environ", {"DATA_GO_KR_SERVICE_KEY": "k"}),                 mock.patch.object(feeds, "QUAL_SUBJECTS", (("1320", "정보처리기사"), ("6921", "프로그래밍기능사"))),                 mock.patch.object(feeds, "_get_json", return_value=page) as get:
            items = feeds.fetch_qual_subjects(2026)
        self.assertEqual([(i["jmCd"], i["jmNm"]) for i in items], [("1320", "정보처리기사"), ("6921", "프로그래밍기능사")])
        self.assertIn("jmCd=1320", get.call_args_list[0].args[0])

    def test_api_error_header_raises(self):
        with mock.patch.dict("os.environ", {"DATA_GO_KR_SERVICE_KEY": "k"}), \
                mock.patch.object(feeds, "_get_json", return_value={"header": {"resultCode": "30", "resultMsg": "KEY ERROR"}}):
            with self.assertRaises(feeds.FeedError) as ctx:
                feeds.fetch_qual_exams(2026)
        self.assertIn("KEY ERROR", ctx.exception.detail)


class WeekPickTests(SimpleTestCase):
    ROWS = [
        _row("2026년 9월 21일 월요일", "AI 활용 애플리케이션 개발", "SW공학"),
        _row("2026년 9월 28일 월요일", "AI 활용 애플리케이션 개발", "화면 구현"),
        _row("2026년 9월 29일 화요일", "AI 활용 애플리케이션 개발", "화면 구현"),
        _row("2026년 9월 30일 수요일", "AI 활용 애플리케이션 개발", "Django Framework"),
        _row("2026년 10월 8일 목요일", "AI 활용 애플리케이션 개발", "클라우드"),
        _row("날짜 없음", "기타", "무시"),
    ]

    def test_this_week_first_then_nearest(self):
        monday, picked = feeds.pick_week_rows(self.ROWS, date(2026, 9, 30))
        self.assertEqual(monday, date(2026, 9, 28))
        labels = [feeds.topic_label(r) for r in picked]
        self.assertEqual(labels[:2], ["화면 구현", "Django Framework"])
        self.assertEqual(len(labels), len(set(labels)))
        self.assertNotIn("무시", labels)

    def test_empty_week_falls_back_to_nearest_dates(self):
        _, picked = feeds.pick_week_rows(self.ROWS, date(2026, 10, 7))
        self.assertEqual(feeds.topic_label(picked[0]), "클라우드")

    def test_queries_skip_broad_subject(self):
        queries = feeds._search_queries([_row("2026년 9월 30일", "AI 활용 애플리케이션 개발", "Django Framework")])
        self.assertTrue(queries)
        self.assertTrue(all("AI 활용" not in q for q, _, _ in queries))
        self.assertEqual(queries[0][0], "Django Framework 강의")

    def test_subject_used_when_topic_empty(self):
        self.assertEqual(feeds._variants(_row("x", "최종프로젝트", "", ""))[0], "최종프로젝트 강의")


    def test_project_days_become_previous_topic(self):
        rows = self.ROWS + [
            _row("2026년 10월 14일 수요일", "AI 활용 애플리케이션 개발", "단위 프로젝트"),
            _row("2026년 10월 16일 금요일", "최종프로젝트", "", ""),
        ]
        _, picked = feeds.pick_week_rows(rows, date(2026, 10, 14))
        labels = [feeds.topic_label(r) for r in picked]
        self.assertEqual(labels[0], "클라우드")
        self.assertFalse(any("프로젝트" in label for label in labels))

    def test_project_before_any_topic_is_dropped(self):
        rows = [_row("2026년 9월 1일 화요일", "최종프로젝트", "", "")]
        self.assertEqual(feeds.pick_week_rows(rows, date(2026, 9, 1))[1], [])

    def test_title_must_mention_topic(self):
        self.assertTrue(feeds.is_relevant("[화면구현] ReactJS 화면단 구현하기", "화면 구현"))
        self.assertFalse(feeds.is_relevant("ZOOMIT 사용법 PC화면에 그림그리기", "화면 구현"))
        self.assertTrue(feeds.is_relevant("Python Django Web Framework - 수업소개", "Django Framework"))
        self.assertFalse(feeds.is_relevant("FastAPI 프레임워크 Framework 소개", "Django Framework"))
        self.assertTrue(feeds.is_relevant("멀티모달 AI 한 번에 정리", "자연어-이미지 멀티모달"))
        self.assertTrue(feeds.is_relevant("AWS 클라우드 입문", "클라우드"))


    def test_project_week_adds_talk_queries(self):
        rows = self.ROWS + [
            _row("2026년 10월 16일 금요일", "최종프로젝트", "", ""),
            _row("2026년 9월 16일 수요일", "LLM", "단위 프로젝트"),
        ]
        self.assertTrue(feeds.has_project_week(rows, date(2026, 10, 12)))  # 금요일 하루뿐이어도 그 주 전체
        self.assertTrue(feeds.has_project_week(rows, date(2026, 9, 14)))  # 단위 프로젝트도
        self.assertFalse(feeds.has_project_week(rows, date(2026, 10, 5)))
        _, picked = feeds.pick_week_rows(rows, date(2026, 10, 14))
        queries = feeds._search_queries(picked, project_week=True)
        self.assertEqual([label for _, label, _ in queries[-2:]], ["발표 준비", "개발자 발표"])
        self.assertEqual(queries[0][1], "클라우드")
        self.assertLessEqual(len(queries), feeds.YT_MAX_QUERIES)

    def test_talk_titles_pass_with_event_names(self):
        self.assertTrue(feeds.is_relevant("[우아콘2024] 배달 앱 검색 개선기", "개발자 발표"))
        self.assertTrue(feeds.is_relevant("if(kakao)2024 추천 시스템", "개발자 발표"))
        self.assertTrue(feeds.is_relevant("발표 PPT 잘 만드는 법", "발표 준비"))
        self.assertFalse(feeds.is_relevant("오늘 저녁 메뉴 추천", "개발자 발표"))

    def test_videos_shown_before_go_last(self):
        def video(i):
            return {"videoId": f"v{i}", "title": f"클라우드 {i}", "channelTitle": f"ch{i}"}
        with mock.patch.object(feeds, "_search_youtube", return_value=[video(1), video(2), video(3)]):
            out = feeds._collect_videos("k", [("클라우드 강의", "클라우드", "medium")], {"v1"})
        self.assertEqual([v["videoId"] for v in out], ["v2", "v3", "v1"])

    def test_talks_are_a_quarter_after_every_three_study_videos(self):
        def video(i, label):
            return {"videoId": f"{label}{i}", "topicLabel": label}
        videos = [video(i, label) for label in ("클라우드", "Django", "발표 준비", "개발자 발표") for i in range(10)]
        out = feeds._mix(videos, 12)
        labels = [v["topicLabel"] for v in out]
        self.assertEqual(len(out), 12)
        self.assertEqual(sum(label in feeds.LABEL_KEYWORDS for label in labels), 3)
        self.assertEqual([label in feeds.LABEL_KEYWORDS for label in labels[:4]], [False, False, False, True])

    def test_talks_fill_in_when_study_videos_run_short(self):
        videos = [{"videoId": "s", "topicLabel": "클라우드"}] + [
            {"videoId": f"t{i}", "topicLabel": "개발자 발표"} for i in range(10)
        ]
        self.assertEqual(len(feeds._mix(videos, 12)), 11)

    def test_shown_before_reads_only_recent_past_weeks(self):
        cur = mock.MagicMock()
        cur.fetchall.return_value = [
            ("youtubeCurriculum_cohort_34_20261005_v4", {"videos": [{"videoId": "old"}]}),
            ("youtubeCurriculum_cohort_34_20261012_v4", {"videos": [{"videoId": "same-week"}]}),
            ("youtubeCurriculum_cohort_34_20250101_v3", {"videos": [{"videoId": "too-old"}]}),
        ]
        self.assertEqual(feeds._shown_before(cur, "cohort_34", "20261012"), {"old"})


class WeeklyYoutubeAccessTests(SimpleTestCase):
    def test_student_cannot_read_other_cohort(self):
        cur = mock.MagicMock()
        with self.assertRaises(feeds.FeedError) as ctx:
            feeds._cohort_for(cur, {"role": "student", "cohort_code": "cohort_34"}, "cohort_35")
        self.assertEqual(ctx.exception.status, 403)
        cur.execute.assert_not_called()

    def test_admin_can_read_any_cohort(self):
        cur = mock.MagicMock()
        cur.fetchone.return_value = (3, "cohort_35")
        cohort = feeds._cohort_for(cur, {"role": "admin", "cohort_code": "cohort_34"}, "cohort_35")
        self.assertEqual(cohort, {"id": 3, "code": "cohort_35"})

    def test_titles_are_unescaped(self):
        payload = {"items": [{"id": {"videoId": "abc"}, "snippet": {"title": "Tom&#39;s &quot;Django&quot;", "channelTitle": "A&amp;B"}}]}
        with mock.patch.object(feeds, "_get_json", return_value=payload):
            videos = feeds._search_youtube("k", "q", None)
        self.assertEqual(videos[0]["title"], 'Tom\'s "Django"')
        self.assertEqual(videos[0]["channelTitle"], "A&B")
        self.assertTrue(videos[0]["thumbnailUrl"].endswith("/abc/hqdefault.jpg"))
