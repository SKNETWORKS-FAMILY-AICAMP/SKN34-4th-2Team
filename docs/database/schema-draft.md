# PLAYDATA LMS PostgreSQL Redesign - Schema Draft

## assessments
```text
assessments
- id PK
- cohort_id FK
- title
- description NULL
- start_at
- end_at
- published
- lifecycle_status
- created_by FK
- created_at
- updated_at
```

lifecycle_status 후보:
`draft / active / closed / cancelled`

메모:
- 응시 기록이 없는 평가는 삭제 가능.
- 응시 기록이 있으면 physical delete 대신 cancelled/비공개 전환을 우선.

## assessment_questions
```text
assessment_questions
- id PK
- assessment_id FK
- order_no
- question_type
- prompt
- points
- choices JSONB NULL
- correct_index NULL
- accepted_answers JSONB NULL
- explanation NULL
- origin
- source_day NULL
- source_topic NULL
- prompt_version NULL
- ai_log_id FK NULL
```

question_type:
`multiple_choice / short_answer`

origin:
`manual / ai`

## assessment_submissions
```text
assessment_submissions
- id PK
- assessment_id FK
- user_id FK
- auto_total_score
- total_score
- submitted_at
- graded_at NULL
UNIQUE(assessment_id, user_id)
```

## assessment_answers
```text
assessment_answers
- submission_id FK
- question_id FK
- value JSONB NULL
- auto_score
- final_score
- is_correct
- comment NULL
PRIMARY KEY(submission_id, question_id)
```

메모:
- 객관식/단답형 자동 채점 결과를 auto_score에 저장.
- 강사가 수정한 확정 점수는 final_score에 저장.
- 단답형은 accepted_answers와 표현 차이로 자동 오답이 날 수 있으므로 수동 정정 가능.

## assessment_score_adjustments
```text
assessment_score_adjustments
- id PK
- submission_id FK
- question_id FK NULL
- previous_score
- next_score
- adjusted_by FK
- adjusted_at
- note NULL
```

- 강사의 점수 수정 이력을 보존한다.

## 평가 관계
```text
assessments
  1 ─── N assessment_questions

assessments
  1 ─── N assessment_submissions
             |
             └── N assessment_answers ─── 1 assessment_questions

assessment_submissions
  1 ─── N assessment_score_adjustments
```

## 아직 확정하지 않은 영역
- resumes/career
- skills/job preferences
- mileage 전체 규칙/상품/구매
- learning/curriculum
- community
- AI/LLMOps
