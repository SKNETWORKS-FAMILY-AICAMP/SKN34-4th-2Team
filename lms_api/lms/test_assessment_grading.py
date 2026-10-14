"""성취도평가 서버 채점 — functions/src/assessments.ts gradeAnswer 와 같은 규칙인지."""

from django.test import SimpleTestCase

from lms.assessment_service import grade_answer


class GradeAnswerTests(SimpleTestCase):
    MC = {"type": "mc", "points": 5, "correct_index": 1}
    SA = {"type": "shortAnswer", "points": 3, "accepted_answers": '["print", "Print Function"]'}

    def test_객관식은_번호가_같아야_맞다(self):
        self.assertTrue(grade_answer(self.MC, 1)["isCorrect"])
        self.assertTrue(grade_answer(self.MC, "1")["isCorrect"])
        wrong = grade_answer(self.MC, 2)
        self.assertEqual((wrong["isCorrect"], wrong["finalScore"]), (False, 0))

    def test_객관식_무응답_이상한_값은_틀림(self):
        for raw in (None, "", "abc", True):
            self.assertFalse(grade_answer(self.MC, raw)["isCorrect"], raw)

    def test_단답은_앞뒤_공백_대소문자_가운데_공백을_무시한다(self):
        self.assertEqual(grade_answer(self.SA, "  PRINT ")["finalScore"], 3)
        self.assertTrue(grade_answer(self.SA, "print   function")["isCorrect"])
        self.assertFalse(grade_answer(self.SA, "")["isCorrect"])
        self.assertFalse(grade_answer(self.SA, "input")["isCorrect"])

    def test_화면_문항_이름도_객관식으로_본다(self):
        self.assertTrue(grade_answer({**self.MC, "type": "multipleChoice"}, 1)["isCorrect"])
