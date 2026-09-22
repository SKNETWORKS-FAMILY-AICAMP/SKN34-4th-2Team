# PLAYDATA LMS PostgreSQL Redesign - Schema Draft

## mileage_transactions
```text
mileage_transactions
- id PK
- user_id FK
- cohort_id FK
- amount
- transaction_type
- record_submission_id FK NULL
- purchase_request_id FK NULL
- related_transaction_id FK NULL
- reason
- created_by FK NULL
- created_at
```

transaction_type 후보:
`record_reward / admin_adjustment / purchase / refund / reversal / expiry`

원칙:
- 금액은 적립/환급이면 양수, 차감/구매/소멸이면 음수.
- 기존 거래는 수정/삭제하지 않는다.
- 동일 자동 보상 중복 생성을 방지하는 idempotency 제약 필요.

## users mileage cache
```text
users
...
- mileage_balance
```

- 선택적 캐시 필드.
- mileage_transactions가 canonical ledger.
- 거래 생성/환급/소멸과 동일 transaction 안에서 갱신.

## mileage_products
```text
mileage_products
- id PK
- cohort_id FK
- name
- description
- image_storage_key NULL
- category
- pricing_type
- fixed_price NULL
- is_active
- sort_order
- created_at
- updated_at
```

category:
`gifticon / book / online_course`

pricing_type:
`fixed / variable`

## mileage_cart_items
```text
mileage_cart_items
- user_id FK
- product_id FK
- quantity
- unit_price NULL
- purchase_link NULL
- updated_at
PRIMARY KEY(user_id, product_id)
```

메모:
- 서버 저장 장바구니가 필요할 때 사용.
- 단순 로컬 장바구니만 유지한다면 생략 가능.

## purchase_requests
```text
purchase_requests
- id PK
- user_id FK
- cohort_id FK
- total_amount
- status
- student_note NULL
- review_comment NULL
- processed_by FK NULL
- processed_at NULL
- created_at
- updated_at
```

status:
`pending / approved / modify_requested / rejected / cancelled`

원칙:
- 요청 생성 시 차감하지 않는다.
- 승인 시 서버가 잔액/한도 재검증 후 purchase transaction 생성.
- 승인 후 취소/환급은 refund transaction 생성.

## purchase_request_items
```text
purchase_request_items
- id PK
- request_id FK
- product_id FK NULL
- product_name
- category
- pricing_type
- unit_price
- quantity
- purchase_link NULL
```

- 구매 당시 상품 정보를 snapshot으로 보존.

## mileage_settings
```text
mileage_settings
- cohort_id PK/FK
- category_limits JSONB
- accrual_rules JSONB
- expires_at
- updated_by FK
- updated_at
```

expires_at 기본 계산:
`cohorts.end_date + 14 days`

메모:
- 설정 변경이 잦고 기수별 구조 차이를 허용하기 위해 JSONB 사용.
- 실제 소멸 거래는 mileage_transactions에 기록.

## 구매 승인 처리 트랜잭션
```text
BEGIN

1. purchase_requests row SELECT FOR UPDATE
2. users/current balance SELECT FOR UPDATE
3. status = pending 또는 modify_requested 확인
4. category limit 검증
5. 잔액 >= total_amount 검증
6. purchase_request status = approved
7. mileage_transactions INSERT (negative purchase amount)
8. users.mileage_balance UPDATE (캐시 사용 시)

COMMIT
```

## 아직 확정하지 않은 영역
- resumes/career
- skills/job preferences
- learning/curriculum
- community
- AI/LLMOps
