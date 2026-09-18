import '../../../core/routing/route_paths.dart';
import '../domain/onboarding_step.dart';
import 'admin_onboarding_keys.dart';

abstract final class AdminOnboarding {
  static const tourId = 'admin';
  static const version = 1;

  /// 17스텝: 사이드바 메뉴 15개 전부 + CTA 2
  static const steps = <OnboardingStep>[
    OnboardingStep(
      id: 'nav_dashboard',
      title: '대시보드',
      body: '기수 운영 현황을 한눈에 보는 관리자 홈입니다.',
      targetId: AdminOnboardingTargets.navDashboard,
      route: RoutePaths.admin,
    ),
    OnboardingStep(
      id: 'nav_cohorts',
      title: '기수 관리',
      body: '기수를 만들고 기간·설정을 관리합니다.',
      targetId: AdminOnboardingTargets.navCohorts,
      route: RoutePaths.adminCohorts,
    ),
    OnboardingStep(
      id: 'nav_students',
      title: '학생 관리',
      body: '학생 계정을 등록·조회·수정합니다.',
      targetId: AdminOnboardingTargets.navStudents,
      route: RoutePaths.adminStudents,
    ),
    OnboardingStep(
      id: 'nav_instructors',
      title: '강사 관리',
      body: '강사 계정을 등록하고 정보 수정·비밀번호 재발급을 합니다.',
      targetId: AdminOnboardingTargets.navInstructors,
      route: RoutePaths.adminInstructors,
    ),
    OnboardingStep(
      id: 'nav_attendance',
      title: '출석 관리',
      body: '기수별 당일 출석을 조회·수정하고 폼 반영을 확인합니다.',
      targetId: AdminOnboardingTargets.navAttendance,
      route: RoutePaths.adminAttendance,
    ),
    OnboardingStep(
      id: 'attendance_daily',
      title: '출결 공지',
      body: '매일 08:30 출결 폼 공지를 여기서 등록할 수 있습니다.',
      targetId: AdminOnboardingTargets.attendanceDailyNotice,
      route: RoutePaths.adminAttendance,
      skippableIfMissing: true,
    ),
    OnboardingStep(
      id: 'nav_seat_presence',
      title: '자리 확인',
      body: '오늘 좌석에 앉은 학생을 확인하고 확인·보류를 남깁니다.',
      targetId: AdminOnboardingTargets.navSeatPresence,
      route: RoutePaths.adminSeatPresence,
    ),
    OnboardingStep(
      id: 'nav_seating',
      title: '좌석 배치',
      body: '좌석 레이아웃을 만들고 배정·게시합니다.',
      targetId: AdminOnboardingTargets.navSeating,
      route: RoutePaths.adminSeating,
    ),
    OnboardingStep(
      id: 'nav_assessments',
      title: '성취도 평가',
      body: '평가 목록을 관리하고 발행 상태를 확인합니다.',
      targetId: AdminOnboardingTargets.navAssessments,
      route: RoutePaths.adminAssessments,
    ),
    OnboardingStep(
      id: 'nav_records',
      title: '기록실',
      body: '학생이 올린 자격증·스터디·블로그 기록을 승인하거나 반려합니다.',
      targetId: AdminOnboardingTargets.navRecords,
      route: RoutePaths.adminRecords,
    ),
    OnboardingStep(
      id: 'nav_resumes',
      title: '이력서',
      body: '학생이 피드백을 요청한 이력서를 열어 피드백을 남기고 승인합니다.',
      targetId: AdminOnboardingTargets.navResumes,
      route: RoutePaths.adminResumes,
    ),
    OnboardingStep(
      id: 'nav_forms',
      title: '설문 · 제출',
      body: '설문을 등록하고 마감 일시와 제출 현황을 관리합니다.',
      targetId: AdminOnboardingTargets.navFormTasks,
      route: RoutePaths.adminFormTasks,
    ),
    OnboardingStep(
      id: 'nav_study',
      title: '학습실',
      body: '인프런 강의 패키지를 등록하고 기수에 공개합니다.',
      targetId: AdminOnboardingTargets.navStudyRoom,
      route: RoutePaths.adminStudyRoom,
    ),
    OnboardingStep(
      id: 'nav_board',
      title: '게시판',
      body: '공지·예약 공지·알림 팝업을 관리합니다.',
      targetId: AdminOnboardingTargets.navBoard,
      route: RoutePaths.adminBoard,
    ),
    OnboardingStep(
      id: 'board_create',
      title: '공지 작성',
      body: '공지 작성으로 새 공지를 등록할 수 있습니다.',
      targetId: AdminOnboardingTargets.boardCreate,
      route: RoutePaths.adminBoard,
      skippableIfMissing: true,
    ),
    OnboardingStep(
      id: 'nav_mileage',
      title: '마일리지',
      body: '상품·요청·수동 조정 등 마일리지를 운영합니다.',
      targetId: AdminOnboardingTargets.navMileage,
      route: RoutePaths.adminMileage,
    ),
    OnboardingStep(
      id: 'nav_ai',
      title: 'LLMOps',
      body: 'AI 기능의 관측 지표(성공률·지연·비용)와 평가 결과, 프롬프트 버전별 채택률을 확인합니다.',
      targetId: AdminOnboardingTargets.navAiQuality,
      route: RoutePaths.adminAiQuality,
    ),
  ];
}
