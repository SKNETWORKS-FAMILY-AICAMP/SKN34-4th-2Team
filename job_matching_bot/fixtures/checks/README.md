# 규칙 결함 검사 기록

`python -m job_matching_bot.evaluation.recommend_check --save [--eval-resumes]`가 회차마다
한 파일씩 남긴다. **여기 있는 것은 지우지 않는다.** 고치기 전 숫자가 남아 있어야 고친 뒤
좋아졌는지 말할 수 있다.

파일에는 검사 항목별 건수와 결함 목록(공고 ID·사유)만 있다. 추천 응답 원본은
`artifacts/eval_runs/`에 저장되고 커밋하지 않는다.
