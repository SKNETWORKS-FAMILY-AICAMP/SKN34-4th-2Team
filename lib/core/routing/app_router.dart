import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/admin/presentation/admin_alert_popup_form_screen.dart';
import '../../features/admin/presentation/admin_ai_quality_screen.dart';
import '../../features/admin/presentation/admin_assessments_screen.dart';
import '../../features/admin/presentation/admin_assessment_detail_screen.dart';
import '../../features/assessments/presentation/assessments_screen.dart';
import '../../features/assessments/presentation/assessment_take_screen.dart';
import '../../features/assessments/presentation/assessment_result_screen.dart';
import '../../features/instructor/presentation/instructor_assessments_screen.dart';
import '../../features/instructor/presentation/instructor_assessment_form_screen.dart';
import '../../features/instructor/presentation/instructor_assessment_detail_screen.dart';
import '../../features/instructor/presentation/instructor_assessment_submission_screen.dart';
import '../../features/instructor/presentation/instructor_curriculum_screen.dart';
import '../../features/admin/presentation/admin_attendance_screen.dart';
import '../../features/admin/presentation/admin_cohort_form_screen.dart';
import '../../features/admin/presentation/admin_cohorts_screen.dart';
import '../../features/admin/presentation/admin_inflearn_package_form_screen.dart';
import '../../features/admin/presentation/admin_form_tasks_screen.dart';
import '../../features/admin/presentation/admin_instructor_create_screen.dart';
import '../../features/admin/presentation/admin_instructors_screen.dart';
import '../../features/admin/presentation/admin_dashboard_screen.dart';
import '../../features/admin/presentation/admin_board_screen.dart';
import '../../features/admin/presentation/admin_notice_form_screen.dart';
import '../../features/admin/presentation/admin_scheduled_notice_form_screen.dart';
import '../../features/admin/presentation/admin_student_create_screen.dart';
import '../../features/admin/presentation/admin_student_detail_screen.dart';
import '../../features/admin/presentation/admin_student_edit_screen.dart';
import '../../features/admin/presentation/admin_students_screen.dart';
import '../../features/admin/presentation/admin_study_room_screen.dart';
import '../../features/admin/presentation/admin_mileage_hub_screen.dart';
import '../../features/admin/presentation/admin_mileage_products_screen.dart';
import '../../features/admin/presentation/admin_mileage_product_form_screen.dart';
import '../../features/admin/presentation/admin_mileage_settings_screen.dart';
import '../../features/admin/presentation/admin_purchase_requests_screen.dart';
import '../../features/admin/presentation/admin_mileage_adjust_screen.dart';
import '../../features/admin/shell/admin_shell_screen.dart';
import '../../features/instructor/presentation/instructor_attendance_screen.dart';
import '../../features/instructor/presentation/instructor_board_screen.dart';
import '../../features/instructor/shell/instructor_shell_screen.dart';
import '../../features/auth/presentation/change_password_screen.dart';
import '../../features/auth/presentation/login_screen.dart';
import '../../features/auth/providers/auth_providers.dart';
import '../../features/auth/providers/login_exit_hold_provider.dart';
import '../../features/dashboard/presentation/dashboard_screen.dart';
import '../../features/dashboard/presentation/qual_exam_schedules_screen.dart';
import '../../features/forms/presentation/form_tasks_screen.dart';
import '../../features/hub/presentation/board_screen.dart';
import '../../features/mileage/presentation/mileage_screen.dart';
import '../../features/mileage/presentation/mileage_shop_screen.dart';
import '../../features/mileage/presentation/mileage_cart_screen.dart';
import '../../features/my_page/presentation/my_page_screen.dart';
import '../../features/records/presentation/record_blog_form_screen.dart';
import '../../features/records/presentation/record_cert_form_screen.dart';
import '../../features/records/presentation/record_precourse_quiz_form_screen.dart';
import '../../features/records/presentation/record_study_cert_form_screen.dart';
import '../../features/records/presentation/record_study_form_screen.dart';
import '../../features/records/presentation/record_type_select_screen.dart';
import '../../features/records/presentation/records_screen.dart';
import '../../features/resume/presentation/resume_edit_screen.dart';
import '../../features/resume/presentation/resume_screen.dart';
import '../../features/seating/presentation/admin_seating_screen.dart';
import '../../features/seating/presentation/seating_screen.dart';
import '../../features/shell/main_shell_screen.dart';
import '../../features/study_room/presentation/study_room_note_source_screen.dart';
import '../../features/study_room/presentation/study_room_notes_screen.dart';
import '../../features/study_room/presentation/study_room_screen.dart';
import 'fade_page.dart';
import 'route_paths.dart';
import '../../features/settings/presentation/appearance_settings_screen.dart';

/// Auth 상태 변화 시 go_router redirect 재실행용
class _RouterRefresh extends ChangeNotifier {
  _RouterRefresh(this._ref) {
    _ref.listen(sessionUidProvider, (_, _) => notifyListeners());
    _ref.listen(currentUserProvider, (_, _) => notifyListeners());
    _ref.listen(loginExitHoldProvider, (_, _) => notifyListeners());
  }

  final Ref _ref;
}

bool _isAdminRoute(String location) => location.startsWith('/admin');

bool _isInstructorRoute(String location) => location.startsWith('/instructor');

String? _adminRedirectForStudentRoute(String location) {
  if (location == RoutePaths.studyRoom ||
      location.startsWith('${RoutePaths.studyRoom}/')) {
    return RoutePaths.adminStudyRoom;
  }
  return switch (location) {
    RoutePaths.dashboard => RoutePaths.admin,
    RoutePaths.records ||
    RoutePaths.recordsCreate ||
    RoutePaths.recordsCreateCert ||
    RoutePaths.recordsCreateStudy ||
    RoutePaths.recordsCreateBlog ||
    RoutePaths.recordsCreateStudyCert ||
    RoutePaths.recordsCreatePrecourseQuiz => RoutePaths.adminRecords,
    RoutePaths.resume => RoutePaths.adminResumes,
    RoutePaths.board => RoutePaths.adminBoard,
    RoutePaths.studyRoom => RoutePaths.adminStudyRoom,
    RoutePaths.forms => RoutePaths.adminFormTasks,
    RoutePaths.seating => RoutePaths.adminSeating,
    RoutePaths.myPage => RoutePaths.adminMyPage,
    RoutePaths.mileage => RoutePaths.adminMileage,
    RoutePaths.assessments => RoutePaths.adminAssessments,
    RoutePaths.adminStudents => RoutePaths.adminStudents,
    RoutePaths.adminFormTasks => RoutePaths.adminFormTasks,
    _ => null,
  };
}

String? _instructorRedirectForStudentRoute(String location) {
  return switch (location) {
    RoutePaths.dashboard => RoutePaths.instructor,
    RoutePaths.resume => RoutePaths.instructorResumes,
    RoutePaths.board => RoutePaths.instructorBoard,
    RoutePaths.myPage => RoutePaths.instructorMyPage,
    RoutePaths.assessments => RoutePaths.instructorAssessments,
    _ => null,
  };
}

/// go_router Provider — authState + role 기반 redirect
final appRouterProvider = Provider<GoRouter>((ref) {
  // 여기서 currentUserProvider를 watch하면 프로필 저장(updatedAt 갱신)마다
  // Provider가 다시 빌드돼 GoRouter가 새로 만들어지고, 화면이 initialLocation으로
  // 돌아간다. 최신 값은 redirect 안에서 read하고, 재평가는 refreshListenable이 맡는다.
  final refresh = _RouterRefresh(ref);
  ref.onDispose(refresh.dispose);

  return GoRouter(
    initialLocation: RoutePaths.dashboard,
    debugLogDiagnostics: true,
    refreshListenable: refresh,
    redirect: (context, state) {
      final sessionUid = ref.read(sessionUidProvider);
      final currentUser = ref.read(currentUserProvider);
      final isLoggedIn = sessionUid.value != null;
      final isLoggingIn = state.matchedLocation == RoutePaths.login;
      final isChangingPassword =
          state.matchedLocation == RoutePaths.changePassword;
      final location = state.matchedLocation;
      final isAdminRoute = _isAdminRoute(location);
      final isInstructorRoute = _isInstructorRoute(location);
      final isResumeEdit =
          location.startsWith('/resume/') && location.endsWith('/edit');

      if (sessionUid.isLoading) return null;

      if (!isLoggedIn) {
        return isLoggingIn ? null : RoutePaths.login;
      }

      if (isLoggingIn) {
        // 로그인 성공 퇴장 연출 중에는 redirect 보류
        if (ref.read(loginExitHoldProvider)) return null;
        final user = currentUser.value;
        if (user != null && user.mustChangePassword) {
          return RoutePaths.changePassword;
        }
        if (user != null) return RoutePaths.homeFor(user.role);
        return null;
      }

      final user = currentUser.value;
      if (user != null && user.mustChangePassword && !isChangingPassword) {
        return RoutePaths.changePassword;
      }

      if (user != null && !user.mustChangePassword && isChangingPassword) {
        return RoutePaths.homeFor(user.role);
      }

      if (currentUser.isLoading) return null;

      if (user != null) {
        if (user.isAdmin) {
          if (isInstructorRoute) return RoutePaths.adminInstructors;
          if (!isAdminRoute && !isChangingPassword && !isResumeEdit) {
            final adminPath = _adminRedirectForStudentRoute(location);
            if (adminPath != null) return adminPath;
          }
        } else if (user.isInstructor) {
          if (isAdminRoute) return RoutePaths.instructor;
          if (!isInstructorRoute && !isChangingPassword && !isResumeEdit) {
            final instructorPath = _instructorRedirectForStudentRoute(location);
            if (instructorPath != null) return instructorPath;
            return RoutePaths.instructor;
          }
        } else if (isAdminRoute || isInstructorRoute) {
          return RoutePaths.dashboard;
        }
      }

      return null;
    },
    routes: [
      GoRoute(
        path: RoutePaths.login,
        pageBuilder: (context, state) => fadePage(
          key: state.pageKey,
          child: const LoginScreen(),
        ),
      ),
      GoRoute(
        path: RoutePaths.changePassword,
        builder: (_, _) => const ChangePasswordScreen(),
      ),
      GoRoute(
        path: '/resume/:resumeId/edit',
        pageBuilder: (_, state) => NoTransitionPage(
          child: ResumeEditScreen(
            resumeId: state.pathParameters['resumeId']!,
            initialSection: state.uri.queryParameters['section'],
            cohortId: state.uri.queryParameters['cohortId'],
            openFeedback: state.uri.queryParameters['feedback'] == '1',
          ),
        ),
      ),
      GoRoute(
        path: '/assessments/:assessmentId/take',
        builder: (_, state) => AssessmentTakeScreen(
          assessmentId: state.pathParameters['assessmentId']!,
        ),
      ),
      GoRoute(
        path: '/assessments/:assessmentId/result',
        builder: (_, state) => AssessmentResultScreen(
          assessmentId: state.pathParameters['assessmentId']!,
        ),
      ),
      ShellRoute(
        pageBuilder: (context, state, child) => fadePage(
          key: state.pageKey,
          child: MainShellScreen(child: child),
        ),
        routes: [
          GoRoute(
            path: RoutePaths.dashboard,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: DashboardScreen(),
            ),
          ),
          GoRoute(
            path: RoutePaths.resume,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: ResumeScreen(),
            ),
          ),
          GoRoute(
            path: RoutePaths.studyRoom,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: StudyRoomScreen(),
            ),
          ),
          GoRoute(
            path: RoutePaths.studyRoomNotes,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: StudyRoomNotesScreen(),
            ),
            routes: [
              GoRoute(
                path: ':sourceId',
                pageBuilder: (_, state) => NoTransitionPage(
                  child: StudyRoomNoteSourceScreen(
                    sourceId: state.pathParameters['sourceId']!,
                    initialNoteId: state.uri.queryParameters['noteId'],
                  ),
                ),
              ),
            ],
          ),
          GoRoute(
            path: RoutePaths.board,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: BoardScreen(),
            ),
          ),
          GoRoute(
            path: RoutePaths.records,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: RecordsScreen(),
            ),
          ),
          GoRoute(
            path: RoutePaths.recordsCreate,
            builder: (_, _) => const RecordTypeSelectScreen(),
          ),
          GoRoute(
            path: RoutePaths.recordsCreateCert,
            builder: (_, _) => const RecordCertFormScreen(),
          ),
          GoRoute(
            path: RoutePaths.recordsCreateStudy,
            builder: (_, _) => const RecordStudyFormScreen(),
          ),
          GoRoute(
            path: RoutePaths.recordsCreateBlog,
            builder: (_, _) => const RecordBlogFormScreen(),
          ),
          GoRoute(
            path: RoutePaths.recordsCreateStudyCert,
            builder: (_, _) => const RecordStudyCertFormScreen(),
          ),
          GoRoute(
            path: RoutePaths.recordsCreatePrecourseQuiz,
            builder: (_, _) => const RecordPrecourseQuizFormScreen(),
          ),
          GoRoute(
            path: RoutePaths.mileage,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: MileageScreen(),
            ),
            routes: [
              GoRoute(
                path: 'shop',
                builder: (_, _) => const MileageShopScreen(),
                routes: [
                  GoRoute(
                    path: 'cart',
                    builder: (_, _) => const MileageCartScreen(),
                  ),
                ],
              ),
            ],
          ),
          GoRoute(
            path: RoutePaths.assessments,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: AssessmentsScreen(),
            ),
          ),
          GoRoute(
            path: RoutePaths.forms,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: FormTasksScreen(),
            ),
          ),
          GoRoute(
            path: RoutePaths.qualExams,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: QualExamSchedulesScreen(),
            ),
          ),
          GoRoute(
            path: RoutePaths.seating,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: SeatingScreen(),
            ),
          ),
          GoRoute(
            path: RoutePaths.myPage,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: MyPageScreen(),
            ),
          ),
          GoRoute(
            path: RoutePaths.settings,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: AppearanceSettingsScreen(),
            ),
          ),
        ],
      ),
      ShellRoute(
        pageBuilder: (context, state, child) => fadePage(
          key: state.pageKey,
          child: AdminShellScreen(child: child),
        ),
        routes: [
          GoRoute(
            path: RoutePaths.admin,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: AdminDashboardScreen(),
            ),
          ),
          GoRoute(
            path: RoutePaths.adminRecords,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: RecordsScreen(),
            ),
          ),
          GoRoute(
            path: RoutePaths.adminResumes,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: ResumeScreen(),
            ),
          ),
          GoRoute(
            path: RoutePaths.adminBoard,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: AdminBoardScreen(),
            ),
            routes: [
              GoRoute(
                path: 'create',
                builder: (_, _) => const AdminNoticeFormScreen(),
              ),
              GoRoute(
                path: 'scheduled/create',
                builder: (_, _) => const AdminScheduledNoticeFormScreen(),
              ),
              GoRoute(
                path: 'scheduled/:scheduledId/edit',
                builder: (_, state) => AdminScheduledNoticeFormScreen(
                  scheduledId: state.pathParameters['scheduledId'],
                ),
              ),
              GoRoute(
                path: 'alert-popups/create',
                builder: (_, _) => const AdminAlertPopupFormScreen(),
              ),
              GoRoute(
                path: 'alert-popups/:popupId/edit',
                builder: (_, state) => AdminAlertPopupFormScreen(
                  popupId: state.pathParameters['popupId'],
                ),
              ),
              GoRoute(
                path: ':noticeId/edit',
                builder: (_, state) => AdminNoticeFormScreen(
                  noticeId: state.pathParameters['noticeId'],
                ),
              ),
            ],
          ),
          GoRoute(
            path: RoutePaths.adminStudyRoom,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: AdminStudyRoomScreen(),
            ),
            routes: [
              GoRoute(
                path: 'create',
                builder: (_, _) => const AdminInflearnPackageFormScreen(),
              ),
              GoRoute(
                path: ':packageId',
                builder: (_, state) => AdminInflearnPackageFormScreen(
                  packageId: state.pathParameters['packageId'],
                ),
              ),
            ],
          ),
          GoRoute(
            path: RoutePaths.adminStudents,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: AdminStudentsScreen(),
            ),
            routes: [
              GoRoute(
                path: 'create',
                builder: (_, _) => const AdminStudentCreateScreen(),
              ),
              GoRoute(
                path: ':studentUid',
                builder: (_, state) => AdminStudentDetailScreen(
                  studentUid: state.pathParameters['studentUid']!,
                ),
                routes: [
                  GoRoute(
                    path: 'edit',
                    builder: (_, state) => AdminStudentEditScreen(
                      studentUid: state.pathParameters['studentUid']!,
                    ),
                  ),
                ],
              ),
            ],
          ),
          GoRoute(
            path: RoutePaths.adminAttendance,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: AdminAttendanceScreen(),
            ),
          ),
          GoRoute(
            path: RoutePaths.adminSeatPresence,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: InstructorAttendanceScreen(title: '자리 확인'),
            ),
          ),
          GoRoute(
            path: RoutePaths.adminInstructors,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: AdminInstructorsScreen(),
            ),
            routes: [
              GoRoute(
                path: 'create',
                builder: (_, _) => const AdminInstructorCreateScreen(),
              ),
            ],
          ),
          GoRoute(
            path: RoutePaths.adminCohorts,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: AdminCohortsScreen(),
            ),
            routes: [
              GoRoute(
                path: 'create',
                builder: (_, _) => const AdminCohortFormScreen(),
              ),
              GoRoute(
                path: ':cohortId/edit',
                builder: (_, state) => AdminCohortFormScreen(
                  cohortId: state.pathParameters['cohortId'],
                ),
              ),
            ],
          ),
          GoRoute(
            path: RoutePaths.adminFormTasks,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: AdminFormTasksScreen(),
            ),
            routes: [
              GoRoute(
                path: 'create',
                builder: (_, _) => const AdminFormTaskFormScreen(),
              ),
              GoRoute(
                path: ':taskId',
                builder: (_, state) => AdminFormTaskDetailScreen(
                  taskId: state.pathParameters['taskId']!,
                ),
                routes: [
                  GoRoute(
                    path: 'edit',
                    builder: (_, state) => AdminFormTaskFormScreen(
                      taskId: state.pathParameters['taskId'],
                    ),
                  ),
                ],
              ),
            ],
          ),
          GoRoute(
            path: RoutePaths.adminSeating,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: AdminSeatingScreen(),
            ),
          ),
          GoRoute(
            path: RoutePaths.adminMyPage,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: MyPageScreen(),
            ),
          ),
          GoRoute(
            path: RoutePaths.adminSettings,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: AppearanceSettingsScreen(),
            ),
          ),
          GoRoute(
            path: RoutePaths.adminMileage,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: AdminMileageHubScreen(),
            ),
            routes: [
              GoRoute(
                path: 'products',
                pageBuilder: (_, _) => const NoTransitionPage(
                  child: AdminMileageProductsScreen(),
                ),
                routes: [
                  GoRoute(
                    path: 'create',
                    builder: (_, _) => const AdminMileageProductFormScreen(),
                  ),
                  GoRoute(
                    path: ':productId/edit',
                    builder: (_, state) => AdminMileageProductFormScreen(
                      productId: state.pathParameters['productId'],
                    ),
                  ),
                ],
              ),
              GoRoute(
                path: 'requests',
                pageBuilder: (_, _) => const NoTransitionPage(
                  child: AdminPurchaseRequestsScreen(),
                ),
              ),
              GoRoute(
                path: 'adjust',
                pageBuilder: (_, _) => const NoTransitionPage(
                  child: AdminMileageAdjustScreen(),
                ),
              ),
              GoRoute(
                path: 'settings',
                pageBuilder: (_, _) => const NoTransitionPage(
                  child: AdminMileageSettingsScreen(),
                ),
              ),
            ],
          ),
          GoRoute(
            path: RoutePaths.adminAssessments,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: AdminAssessmentsScreen(),
            ),
            routes: [
              GoRoute(
                path: ':assessmentId',
                builder: (_, state) => AdminAssessmentDetailScreen(
                  assessmentId: state.pathParameters['assessmentId']!,
                ),
                routes: [
                  GoRoute(
                    path: 'submissions/:submissionId',
                    builder: (_, state) => InstructorAssessmentSubmissionScreen(
                      assessmentId: state.pathParameters['assessmentId']!,
                      submissionId: state.pathParameters['submissionId']!,
                      canEditScores: false,
                    ),
                  ),
                ],
              ),
            ],
          ),
          GoRoute(
            path: RoutePaths.adminAiQuality,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: AdminAiQualityScreen(),
            ),
          ),
        ],
      ),
      ShellRoute(
        pageBuilder: (context, state, child) => fadePage(
          key: state.pageKey,
          child: InstructorShellScreen(child: child),
        ),
        routes: [
          GoRoute(
            path: RoutePaths.instructor,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: InstructorAttendanceScreen(),
            ),
          ),
          GoRoute(
            path: RoutePaths.instructorResumes,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: ResumeScreen(),
            ),
          ),
          GoRoute(
            path: RoutePaths.instructorBoard,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: InstructorBoardScreen(),
            ),
            routes: [
              GoRoute(
                path: 'create',
                builder: (_, _) => const AdminNoticeFormScreen(),
              ),
              GoRoute(
                path: ':noticeId/edit',
                builder: (_, state) => AdminNoticeFormScreen(
                  noticeId: state.pathParameters['noticeId'],
                ),
              ),
            ],
          ),
          GoRoute(
            path: RoutePaths.instructorAssessments,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: InstructorAssessmentsScreen(),
            ),
            routes: [
              GoRoute(
                path: 'create',
                builder: (_, _) => const InstructorAssessmentFormScreen(),
              ),
              GoRoute(
                path: ':assessmentId',
                builder: (_, state) => InstructorAssessmentDetailScreen(
                  assessmentId: state.pathParameters['assessmentId']!,
                ),
                routes: [
                  GoRoute(
                    path: 'edit',
                    builder: (_, state) => InstructorAssessmentFormScreen(
                      assessmentId: state.pathParameters['assessmentId'],
                    ),
                  ),
                  GoRoute(
                    path: 'submissions/:submissionId',
                    builder: (_, state) => InstructorAssessmentSubmissionScreen(
                      assessmentId: state.pathParameters['assessmentId']!,
                      submissionId: state.pathParameters['submissionId']!,
                    ),
                  ),
                ],
              ),
            ],
          ),
          GoRoute(
            path: RoutePaths.instructorCurriculum,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: InstructorCurriculumScreen(),
            ),
          ),
          GoRoute(
            path: RoutePaths.instructorMyPage,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: MyPageScreen(),
            ),
          ),
          GoRoute(
            path: RoutePaths.instructorSettings,
            pageBuilder: (_, _) => const NoTransitionPage(
              child: AppearanceSettingsScreen(),
            ),
          ),
        ],
      ),
    ],
  );
});
