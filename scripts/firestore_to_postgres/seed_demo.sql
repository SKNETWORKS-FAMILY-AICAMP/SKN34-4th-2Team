-- 로컬 개발용 데모 데이터 — Firebase 키 없이 로그인해 볼 수 있게.
--
-- 기수 하나와 계정 셋(관리자 · 강사 · 학생). React 로그인 화면의 「빠른 로그인 (데모)」 버튼과
-- 같은 이메일 · 비밀번호다(lms_react/src/data/seed.ts 의 DemoAccounts).
--
-- 실행(스키마를 올린 뒤):
--   docker compose exec -T db psql -U postgres -d lms -f - < scripts/firestore_to_postgres/seed_demo.sql
-- 또는 직접 설치한 PostgreSQL:
--   psql -U postgres -d lms -f scripts/firestore_to_postgres/seed_demo.sql
--
-- 여러 번 실행해도 된다(이미 있으면 건너뛴다). 운영 DB 에는 넣지 않는다.

BEGIN;

INSERT INTO cohorts (code, name, description, term_number, status, is_active, start_date, end_date, created_at)
VALUES ('cohort_34', 'SK네트웍스 Family AI 캠프 34기', '데이터·AI 전 과정 6개월 부트캠프', 34, 'active', true,
        current_date - 90, current_date + 90, now())
ON CONFLICT (code) DO NOTHING;

INSERT INTO users (firebase_uid, email, password, display_name, role, cohort_id, seat_number, is_active,
                   must_change_password, created_at, updated_at)
SELECT v.uid, v.email, 'Playdata123!', v.name, v.role, c.id, v.seat, true, false, now(), now()
FROM (VALUES
        ('demo-admin-001', 'admin@playdata.co.kr', 'PLAYDATA 관리자', 'admin', NULL::int),
        ('demo-instructor-001', 'instructor@playdata.co.kr', '김강사', 'instructor', NULL::int),
        ('demo-student-001', 'student@playdata.co.kr', '이수민', 'student', 12)
     ) AS v(uid, email, name, role, seat)
CROSS JOIN (SELECT id FROM cohorts WHERE code = 'cohort_34') AS c
ON CONFLICT (email) DO NOTHING;

COMMIT;
