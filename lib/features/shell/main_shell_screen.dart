import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/constants/attendance_status.dart';
import '../../core/routing/route_paths.dart';
import '../../core/theme/app_colors.dart';
import '../../shared/models/user_model.dart';
import '../../shared/providers/profile_photo_providers.dart';
import '../../shared/providers/side_rail_theme_provider.dart';
import '../../shared/widgets/app_side_rail.dart';
import '../../shared/widgets/profile_avatar.dart';
import '../../shared/widgets/profile_nav_chip.dart';
import '../auth/providers/auth_providers.dart';
import '../chatbot/presentation/student_chatbot_host.dart';
import '../onboarding/domain/onboarding_target_registry.dart';
import '../onboarding/presentation/onboarding_controller.dart';
import '../onboarding/student/student_onboarding_host.dart';
import '../onboarding/student/student_onboarding_keys.dart';
import 'widgets/alert_popup_host.dart';
import 'widgets/app_shell_header.dart';
import '../../core/theme/shell_chrome.dart';
import '../../core/theme/app_space.dart';

class _StudentNavItem {
  const _StudentNavItem(this.icon, this.label, this.path, this.targetId);
  final IconData icon;
  final String label;
  final String path;
  final String targetId;
}

const _kStudentNavItems = [
  _StudentNavItem(
    Icons.dashboard_rounded,
    '대시보드',
    RoutePaths.dashboard,
    StudentOnboardingTargets.navDashboard,
  ),
  _StudentNavItem(
    Icons.description_rounded,
    '이력서 관리',
    RoutePaths.resume,
    StudentOnboardingTargets.navResume,
  ),
  _StudentNavItem(
    Icons.menu_book_rounded,
    '학습실',
    RoutePaths.studyRoom,
    StudentOnboardingTargets.navStudyRoom,
  ),
  _StudentNavItem(
    Icons.forum_rounded,
    '게시판',
    RoutePaths.board,
    StudentOnboardingTargets.navBoard,
  ),
  _StudentNavItem(
    Icons.event_seat_rounded,
    '자리 배치',
    RoutePaths.seating,
    StudentOnboardingTargets.navSeating,
  ),
  _StudentNavItem(
    Icons.ballot_outlined,
    '설문 · 제출',
    RoutePaths.forms,
    StudentOnboardingTargets.navForms,
  ),
  _StudentNavItem(
    Icons.workspace_premium_outlined,
    '자격 시험 일정',
    RoutePaths.qualExams,
    StudentOnboardingTargets.navQualExams,
  ),
  _StudentNavItem(
    Icons.history_rounded,
    '기록실',
    RoutePaths.records,
    StudentOnboardingTargets.navRecords,
  ),
  _StudentNavItem(
    Icons.card_giftcard_rounded,
    '마일리지',
    RoutePaths.mileage,
    StudentOnboardingTargets.navMileage,
  ),
  _StudentNavItem(
    Icons.quiz_outlined,
    '성취도평가',
    RoutePaths.assessments,
    StudentOnboardingTargets.navAssessments,
  ),
];

/// 메인 Shell — 와이드: 좌측 아이콘+텍스트 레일 / 좁은 화면: Drawer
class MainShellScreen extends ConsumerWidget {
  const MainShellScreen({super.key, required this.child});

  final Widget child;

  static const _railBreakpoint = 900.0;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final currentUser = ref.watch(currentUserProvider);
    final user = currentUser.value;
    final wide = MediaQuery.sizeOf(context).width >= _railBreakpoint;
    final location = GoRouterState.of(context).matchedLocation;
    final preview = ref.watch(profilePhotoPreviewProvider);
    final tourActive =
        ref.watch(onboardingTourProvider)?.active == true &&
        ref.watch(onboardingTourProvider)?.tourId == 'student';
    final railDark = ref.watch(sideRailDarkModeProvider);
    final railPalette = ref.watch(sideRailDarkPaletteProvider);

    final railItems = [
      for (final item in _kStudentNavItems)
        AppSideRailItem(
          icon: item.icon,
          label: item.label,
          path: item.path,
          itemKey: wide ? OnboardingTargetRegistry.keyOf(item.targetId) : null,
        ),
      const AppSideRailItem(
        icon: Icons.settings_outlined,
        label: '설정',
        path: RoutePaths.settings,
      ),
    ];

    void navigate(String path) {
      if (tourActive) return;
      context.go(path);
    }

    return StudentOnboardingHost(
      child: Scaffold(
        backgroundColor: AppColors.background,
        appBar: AppBar(
          backgroundColor: ShellChrome.appBarBackground(railDark, railPalette),
          foregroundColor: ShellChrome.appBarForeground(railDark),
          surfaceTintColor: Colors.transparent,
          elevation: 0,
          scrolledUnderElevation: 0,
          iconTheme: IconThemeData(
            color: ShellChrome.appBarForeground(railDark),
          ),
          flexibleSpace: wide
              ? ShellChrome.railCorner(
                  railDark: railDark,
                  palette: railPalette,
                )
              : null,
          title: AppShellHeader(overRail: wide),
          automaticallyImplyLeading: !wide,
          actions: [
            KeyedSubtree(
              key: OnboardingTargetRegistry.keyOf(
                StudentOnboardingTargets.attendanceForm,
              ),
              child: TextButton.icon(
                onPressed: tourActive
                    ? null
                    : () => launchUrl(
                        Uri.parse(AttendanceForm.url),
                        mode: LaunchMode.externalApplication,
                      ),
                style: TextButton.styleFrom(
                  foregroundColor: ShellChrome.actionForeground(
                    railDark,
                    railPalette,
                  ),
                  // 투어 중에는 눌리지 않게 막는데, 그러면 글씨가 기본 흐림색으로
                  // 바뀐다. 어두운 앱바 위에서는 그 색이 배경에 묻혀 "출결 폼"을
                  // 설명하는 단계에서 정작 글씨가 사라진다. 잠겨도 색은 그대로 둔다.
                  disabledForegroundColor: ShellChrome.actionForeground(
                    railDark,
                    railPalette,
                  ),
                ),
                icon: const Icon(Icons.open_in_new, size: 16),
                label: const Text('출결 폼'),
              ),
            ),
            if (user != null)
              Center(
                child: Padding(
                  padding: EdgeInsets.only(right: AppSpace.s(12)),
                  child: KeyedSubtree(
                    key: OnboardingTargetRegistry.keyOf(
                      StudentOnboardingTargets.navMyPage,
                    ),
                    child: ProfileNavChip(
                      user: user,
                      style: ProfileNavChipStyle.appBar,
                      onTap: tourActive
                          ? () {}
                          : () => context.go(RoutePaths.myPage),
                    ),
                  ),
                ),
              ),
          ],
        ),
        drawer: wide ? null : _AppDrawer(user: user, tourActive: tourActive),
        body: Row(
          children: [
            if (wide)
              AppSideRail(
                items: railItems,
                location: location,
                onNavigate: navigate,
                onLogout: tourActive
                    ? null
                    : () => ref.read(authRepositoryProvider).signOut(),
                profile: user == null
                    ? null
                    : SideRailProfileTile(
                        label: user.displayName.isNotEmpty
                            ? user.displayName
                            : '마이페이지',
                        initial: user.displayName.isNotEmpty
                            ? user.displayName[0]
                            : 'S',
                        onTap: tourActive
                            ? () {}
                            : () => context.go(RoutePaths.myPage),
                        leading: Builder(
                          builder: (ctx) {
                            final rail = SideRailStyle.of(ctx);
                            return Container(
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                border: Border.all(
                                  color: rail.border,
                                  width: 1.5,
                                ),
                              ),
                              child: ProfileAvatar(
                                radius: 14,
                                userId: user.uid,
                                photoUrl: user.photoUrl,
                                photoStoragePath: user.photoStoragePath,
                                previewBytes: preview,
                              ),
                            );
                          },
                        ),
                      ),
              ),
            Expanded(
              child: user?.isStudent == true
                  ? StudentChatbotHost(
                      user: user!,
                      child: AlertPopupHost(child: child),
                    )
                  : AlertPopupHost(child: child),
            ),
          ],
        ),
      ),
    );
  }
}

class _AppDrawer extends ConsumerWidget {
  const _AppDrawer({this.user, required this.tourActive});

  final UserModel? user;
  final bool tourActive;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final menuItems = [
      for (final item in _kStudentNavItems)
        AppSideRailItem(
          icon: item.icon,
          label: item.label,
          path: item.path,
          itemKey: OnboardingTargetRegistry.keyOf(item.targetId),
        ),
      AppSideRailItem(
        icon: Icons.person_rounded,
        label: '마이페이지',
        path: RoutePaths.myPage,
      ),
      const AppSideRailItem(
        icon: Icons.settings_outlined,
        label: '설정',
        path: RoutePaths.settings,
      ),
    ];

    return Drawer(
      child: Column(
        children: [
          SafeArea(
            bottom: false,
            child: Container(
              width: double.infinity,
              padding: EdgeInsets.fromLTRB(AppSpace.s(16), AppSpace.s(12), AppSpace.s(16), AppSpace.s(16)),
              decoration: BoxDecoration(
                color: AppColors.surface,
                border: Border(bottom: BorderSide(color: AppColors.border)),
              ),
              child: user != null
                  ? ProfileNavChip(
                      user: user!,
                      style: ProfileNavChipStyle.drawer,
                      onTap: () {
                        if (tourActive) return;
                        Navigator.pop(context);
                        context.go(RoutePaths.myPage);
                      },
                    )
                  : Padding(
                      padding: EdgeInsets.all(AppSpace.s(8)),
                      child: Text('게스트'),
                    ),
            ),
          ),
          Expanded(
            child: ListView(
              padding: EdgeInsets.symmetric(horizontal: AppSpace.s(8), vertical: AppSpace.s(8)),
              children: menuItems.map((item) {
                final isSelected =
                    GoRouterState.of(context).matchedLocation == item.path;
                return KeyedSubtree(
                  key: item.itemKey,
                  child: ListTile(
                    leading: Icon(
                      item.icon,
                      color: isSelected
                          ? AppColors.primary
                          : AppColors.textSecondary,
                    ),
                    title: Text(
                      item.label,
                      style: TextStyle(
                        color: isSelected
                            ? AppColors.primary
                            : AppColors.textPrimary,
                        fontWeight: isSelected ? FontWeight.w600 : null,
                      ),
                    ),
                    selected: isSelected,
                    selectedTileColor: AppColors.primaryLight,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(10),
                    ),
                    onTap: () {
                      if (tourActive) return;
                      Navigator.pop(context);
                      context.go(item.path);
                    },
                  ),
                );
              }).toList(),
            ),
          ),
          const Divider(),
          ListTile(
            leading: Icon(Icons.logout, color: AppColors.error),
            title: Text(
              '로그아웃',
              style: TextStyle(color: AppColors.error),
            ),
            onTap: tourActive
                ? null
                : () async {
                    Navigator.pop(context);
                    await ref.read(authRepositoryProvider).signOut();
                  },
          ),
          SizedBox(height: AppSpace.s(8)),
        ],
      ),
    );
  }
}
