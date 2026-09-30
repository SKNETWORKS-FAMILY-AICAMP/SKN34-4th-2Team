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
