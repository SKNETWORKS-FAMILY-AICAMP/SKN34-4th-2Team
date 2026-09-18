import '../../../core/routing/route_paths.dart';
import '../domain/onboarding_step.dart';
import 'instructor_onboarding_keys.dart';

abstract final class InstructorOnboarding {
  static const tourId = 'instructor';
  static const version = 1;

  static const steps = <OnboardingStep>[
    OnboardingStep(
      id: 'nav_attendance',
      title: '자리 확인',
      body: '오늘 좌석·출석을 확인하고 확인/보류를 남깁니다.',
      targetId: InstructorOnboardingTargets.navAttendance,
      route: RoutePaths.instructor,
    ),
    OnboardingStep(
      id: 'attendance_summary',
      title: '날짜·교시·요약',
      body: '날짜와 교시를 고르고, 확인·보류 현황을 한눈에 볼 수 있습니다.',
      targetId: InstructorOnboardingTargets.attendanceSummary,
      route: RoutePaths.instructor,
      skippableIfMissing: true,
    ),
    OnboardingStep(
      id: 'attendance_confirm',
      title: '확인 버튼',
      body: '호명한 학생이 자리에 있으면 확인을 누릅니다. 없으면 옆의 보류입니다.',
      targetId: InstructorOnboardingTargets.attendanceConfirm,
      route: RoutePaths.instructor,
      skippableIfMissing: true,
    ),
    OnboardingStep(
      id: 'nav_resumes',
      title: '이력서관리',
      body: '학생이 피드백을 요청한 이력서를 열어 피드백을 남기는 메뉴입니다.',
      targetId: InstructorOnboardingTargets.navResumes,
      route: RoutePaths.instructorResumes,
    ),
    OnboardingStep(
      id: 'resumes_stats',
      title: '이력서 현황',
      body: '피드백 요청을 누르면 요청이 들어온 이력서만 추립니다. 목록에서 열어 피드백을 남깁니다.',
      targetId: InstructorOnboardingTargets.resumesStats,
      route: RoutePaths.instructorResumes,
      skippableIfMissing: true,
    ),
    OnboardingStep(
      id: 'nav_board',
      title: '게시물관리',
      body: '공지를 등록·수정하는 메뉴입니다.',
      targetId: InstructorOnboardingTargets.navBoard,
      route: RoutePaths.instructorBoard,
    ),
    OnboardingStep(
      id: 'board_create',
      title: '공지 작성',
      body: '공지 작성으로 새 공지를 등록할 수 있습니다.',
      targetId: InstructorOnboardingTargets.boardCreate,
      route: RoutePaths.instructorBoard,
    ),
    OnboardingStep(
      id: 'nav_assessments',
      title: '성취도평가',
      body: '평가를 만들고 발행·채점하는 메뉴입니다.',
      targetId: InstructorOnboardingTargets.navAssessments,
      route: RoutePaths.instructorAssessments,
    ),
    OnboardingStep(
      id: 'assessments_create',
      title: '평가 만들기',
      body: '평가 만들기로 새 평가와 문항을 구성합니다.',
      targetId: InstructorOnboardingTargets.assessmentsCreate,
      route: RoutePaths.instructorAssessments,
    ),
    OnboardingStep(
      id: 'nav_curriculum',
      title: '커리큘럼',
      body: '구글시트 CSV로 커리큘럼을 등록·교체합니다.',
      targetId: InstructorOnboardingTargets.navCurriculum,
      route: RoutePaths.instructorCurriculum,
    ),
    OnboardingStep(
      id: 'curriculum_upload',
      title: 'CSV 등록',
      body: 'CSV 등록/교체로 커리큘럼 표를 업로드합니다.',
      targetId: InstructorOnboardingTargets.curriculumUpload,
      route: RoutePaths.instructorCurriculum,
    ),
    OnboardingStep(
      id: 'nav_mypage',
      title: '마이페이지',
      body: '프로필·비밀번호를 관리합니다. 여기서 이용 안내를 다시 볼 수도 있습니다.',
      targetId: InstructorOnboardingTargets.navMyPage,
      route: RoutePaths.instructorMyPage,
    ),
  ];
}
