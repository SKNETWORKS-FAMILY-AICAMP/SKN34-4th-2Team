# PLAYDATA LMS PostgreSQL Redesign - DB Decision Log

## DEC-001 ~ DEC-030
기존 결정 유지.

## DEC-031 마일리지 원장은 mileage_transactions
- 적립/차감/구매/환급/소멸은 모두 거래 행으로 남긴다.
- 기존 거래를 수정하거나 삭제하여 잔액을 맞추지 않는다.
- 현재 잔액은 거래 합계로 재계산 가능해야 한다.

## DEC-032 캐시 잔액은 허용하되 원장이 우선
- users.mileage_balance 같은 캐시 잔액을 사용할 수 있다.
- 거래 INSERT와 잔액 UPDATE는 동일 DB transaction에서 처리한다.
- 불일치 시 mileage_transactions 합계를 기준으로 복구할 수 있어야 한다.

## DEC-033 구매 요청 시점에는 차감하지 않음
- 학생이 purchase_request를 생성할 때는 마일리지를 예약/차감하지 않는다.
- 관리자가 요청을 approved로 확정하는 순간 차감 transaction을 생성한다.
- 승인 처리 시 잔액 부족 여부를 서버에서 다시 검증한다.

## DEC-034 승인 후 취소는 환급 거래로 처리
- 이미 승인된 구매 요청의 취소/환불이 필요하면 기존 차감 거래를 변경하지 않는다.
- 별도 양수 refund transaction을 생성한다.
- 원거래와 환급거래 연결을 위해 reversed_transaction_id 또는 related_transaction_id를 사용한다.

## DEC-035 상품 가격 방식
- fixed: 관리자가 정한 고정 가격.
- variable: 학생이 실제 가격을 입력한다.
- variable 상품은 구매 링크와 금액을 요청에 snapshot으로 보존한다.

## DEC-036 구매 요청 상태
- pending / approved / modify_requested / rejected / cancelled를 지원한다.
- modify_requested는 관리자 검토 결과 학생의 링크/가격/기타 정보 수정이 필요할 때 사용한다.

## DEC-037 구매 요청 품목은 snapshot 저장
- purchase_request_items에 product_id FK를 둘 수 있으나 상품명이 변경/삭제되어도 과거 요청 의미가 유지되어야 한다.
- product_name, category, pricing_type, unit_price, purchase_link 등 구매 당시 값을 snapshot으로 저장한다.

## DEC-038 기수별 마일리지 설정
- category_limits와 accrual_rules는 기수 단위 설정으로 관리한다.
- 구조가 자주 변할 수 있어 JSONB 사용을 허용한다.
- 핵심 거래 데이터는 JSONB로 저장하지 않는다.

## DEC-039 종강 2주 후 마일리지 소멸
- 기수 종료일 + 14일 이후 남은 마일리지는 사용 불가하다.
- 소멸은 기존 적립 거래를 삭제하지 않고 expiry 음수 transaction으로 남긴다.
- Celery 예약/배치 작업으로 처리할 수 있다.
