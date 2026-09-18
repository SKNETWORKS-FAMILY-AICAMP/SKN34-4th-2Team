import '../../../core/routing/route_paths.dart';
import '../domain/onboarding_step.dart';
import 'student_onboarding_keys.dart';

abstract final class StudentOnboarding {
  static const tourId = 'student';
  static const version = 1;

  /// 14스텝: 네비 10 + CTA 3 + 마이페이지
  static const steps = <OnboardingStep>[
    OnboardingStep(
      id: 'nav_dashboard',
      title: '대시보드',
      body: '출석·공지·학습 현황을 한곳에서 확인합니다.',
      targetId: StudentOnboardingTargets.navDashboard,
      route: RoutePaths.dashboard,
    ),
    OnboardingStep(
      id: 'dashboard_calendar',
      title: '출석 캘린더',
      body: '월별 출석 상태를 캘린더에서 확인할 수 있습니다.',
      targetId: StudentOnboardingTargets.dashboardCalendar,
      route: RoutePaths.dashboard,
      skippableIfMissing: true,
    ),
    OnboardingStep(
      id: 'attendance_form',
      title: '출결 폼',
      body: '예외 출결을 제출하는 구글 폼입니다. 누르면 새 창이 열립니다.',
      targetId: StudentOnboardingTargets.attendanceForm,
      route: RoutePaths.dashboard,
    ),
    OnboardingStep(
      id: 'nav_resume',
      title: '이력서 관리',
      body: '이력서를 작성하고 피드백을 요청합니다. 피드백이 오면 확인하고 답글을 남길 수 있습니다.',
      targetId: StudentOnboardingTargets.navResume,
      route: RoutePaths.resume,
    ),
    OnboardingStep(
      id: 'nav_study',
      title: '학습실',
      body: '배정된 인프런 강의와 이번 주 커리큘럼 YouTube 추천을 확인합니다.',
      targetId: StudentOnboardingTargets.navStudyRoom,
      route: RoutePaths.studyRoom,
    ),
    OnboardingStep(
      id: 'nav_board',
      title: '게시판',
      body: '공지사항과 소통 피드를 확인합니다.',
      targetId: StudentOnboardingTargets.navBoard,
      route: RoutePaths.board,
    ),
    OnboardingStep(
      id: 'board_notices',
      title: '공지 목록',
      body: '중요 공지와 전체 공지를 여기서 확인하세요.',
      targetId: StudentOnboardingTargets.boardNotices,
      route: RoutePaths.board,
      skippableIfMissing: true,
    ),
    OnboardingStep(
      id: 'nav_seating',
      title: '자리 배치',
      body: '게시된 좌석 배치에서 내 자리를 확인합니다.',
      targetId: StudentOnboardingTargets.navSeating,
      route: RoutePaths.seating,
    ),
    OnboardingStep(
      id: 'nav_forms',
      title: '설문 · 제출',
      body: '설문·제출 과제를 확인하고 응답합니다.',
      targetId: StudentOnboardingTargets.navForms,
      route: RoutePaths.forms,
    ),
    OnboardingStep(
      id: 'nav_qual',
      title: '자격 시험 일정',
      body: '자격증·시험 일정을 확인합니다.',
      targetId: StudentOnboardingTargets.navQualExams,
      route: RoutePaths.qualExams,
    ),
    OnboardingStep(
      id: 'nav_records',
      title: '기록실',
      body: '블로그·스터디·자격증 기록을 제출하고 관리합니다.',
      targetId: StudentOnboardingTargets.navRecords,
      route: RoutePaths.records,
    ),
    OnboardingStep(
      id: 'nav_mileage',
      title: '마일리지',
      body: '적립·사용 내역과 상품을 확인합니다.',
      targetId: StudentOnboardingTargets.navMileage,
      route: RoutePaths.mileage,
    ),
    OnboardingStep(
      id: 'nav_assessments',
      title: '성취도평가',
      body: '공개된 평가에 응시하고 결과를 확인합니다.',
      targetId: StudentOnboardingTargets.navAssessments,
      route: RoutePaths.assessments,
    ),
    // 앱바는 어느 화면에나 있으므로 옮겨 다니지 않는다. route를 비워 둔다.
    OnboardingStep(
      id: 'nav_mypage',
      title: '마이페이지',
      body: '프로필·비밀번호를 관리합니다. 여기서 이용 안내를 다시 볼 수도 있습니다.',
      targetId: StudentOnboardingTargets.navMyPage,
    ),
  ];
}
