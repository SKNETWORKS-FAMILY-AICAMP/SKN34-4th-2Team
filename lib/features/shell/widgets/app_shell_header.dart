import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/constants/cohort_status.dart';
import '../../../core/constants/app_constants.dart';
import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/widgets/app_dropdown.dart';
import '../../../shared/models/cohort_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../../shared/providers/side_rail_theme_provider.dart';
import '../../../core/theme/shell_chrome.dart';
import '../../../core/theme/app_space.dart';

/// AppBar — PLAYDATA 홈 이동 + 관리자 기수 선택
class AppShellHeader extends ConsumerWidget {
  const AppShellHeader({
    super.key,
    this.homePath = RoutePaths.dashboard,
    this.overRail = false,
  });

  final String homePath;

  /// 로고가 사이드바 위 칸에 걸쳐 있는가. 넓은 화면에서 참이다.
  final bool overRail;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isAdmin = ref.watch(isAdminProvider);
    final railDark = ref.watch(sideRailDarkModeProvider);

    final logo = InkWell(
      onTap: () => context.go(homePath),
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: EdgeInsets.symmetric(vertical: AppSpace.s(4)),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            // 로고는 정사각형이다. 한 변만 줄이면 찌그러진다.
            Container(
              width: AppSpace.row(36),
              height: AppSpace.row(36),
              padding: EdgeInsets.all(AppSpace.s(4)),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: AppColors.border),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.06),
                    blurRadius: 6,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: Image.asset(
                'assets/brand/playdata.jpg',
                fit: BoxFit.contain,
                filterQuality: FilterQuality.high,
              ),
            ),
            SizedBox(width: AppSpace.s(10)),
            Flexible(
              child: FittedBox(
                fit: BoxFit.scaleDown,
                child: Text(
                  AppConstants.appName,
                  style: TextStyle(
                    fontWeight: FontWeight.w800,
                    color: overRail && railDark
                        ? Colors.white
                        : ShellChrome.appBarForeground(railDark),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );

    return Row(
      children: [
        // 넓은 화면에서는 로고 칸을 사이드바 폭에 맞춘다. 글자 폭만큼만 차지하면
        // 기수 선택이 사이드바 경계 위에 걸쳐 두 색에 반씩 올라앉는다.
        if (overRail)
          SizedBox(
            width: ShellChrome.railWidth - NavigationToolbar.kMiddleSpacing,
            child: Align(alignment: Alignment.centerLeft, child: logo),
          )
        else
          logo,
        if (isAdmin) ...[
          SizedBox(width: AppSpace.s(12)),
          Flexible(child: _CohortSelector(isDark: railDark)),
        ],
      ],
    );
  }
}

class _CohortSelector extends ConsumerStatefulWidget {
  const _CohortSelector({required this.isDark});

  final bool isDark;

  @override
  ConsumerState<_CohortSelector> createState() => _CohortSelectorState();
}

class _CohortSelectorState extends ConsumerState<_CohortSelector> {
  final _anchorKey = GlobalKey();
  double _width = 0;

  void _measure() {
    final box = _anchorKey.currentContext?.findRenderObject() as RenderBox?;
    if (box == null || !box.hasSize) return;
    final next = box.size.width;
    if ((next - _width).abs() > 0.5) {
      setState(() => _width = next);
    }
  }

  @override
  Widget build(BuildContext context) {
    final cohortsAsync = ref.watch(cohortsStreamProvider);
    final effectiveId = ref.watch(effectiveCohortIdProvider);

    return cohortsAsync.when(
      loading: () => const SizedBox(
        width: 16,
        height: 16,
        child: CircularProgressIndicator(strokeWidth: 2),
      ),
      error: (_, _) => const SizedBox.shrink(),
      data: (cohorts) {
        if (cohorts.isEmpty || effectiveId == null) {
          return const SizedBox.shrink();
        }

        final selected = cohorts.firstWhere(
          (c) => c.cohortId == effectiveId,
          orElse: () => cohorts.first,
        );

        final menuWidth = _menuWidth(context, cohorts, _width);

        return Align(
          alignment: Alignment.centerLeft,
          child: MenuAnchor(
            crossAxisUnconstrained: true,
            style: AppMenuStyles.matchedPanel(menuWidth),
            alignmentOffset: const Offset(0, 2),
            builder: (context, controller, _) {
              WidgetsBinding.instance.addPostFrameCallback((_) {
                if (mounted) _measure();
              });
              return KeyedSubtree(
                key: _anchorKey,
                child: _CohortTrigger(
                  label: _cohortLabel(selected),
                  isOpen: controller.isOpen,
                  isDark: widget.isDark,
                  onPressed: () {
                    if (controller.isOpen) {
                      controller.close();
                    } else {
                      controller.open();
                    }
                  },
                ),
              );
            },
            menuChildren: [
              for (final cohort in cohorts)
                MenuItemButton(
                  onPressed: () => selectCohort(ref, cohort.cohortId),
                  style: ButtonStyle(
                    minimumSize: WidgetStatePropertyAll(Size(menuWidth, 40)),
                    maximumSize: WidgetStatePropertyAll(Size(menuWidth, 64)),
                    backgroundColor: WidgetStateProperty.resolveWith((states) {
                      final selectedItem = cohort.cohortId == selected.cohortId;
                      if (selectedItem) return AppColors.primaryLight;
                      if (states.contains(WidgetState.hovered) ||
                          states.contains(WidgetState.focused)) {
                        return AppColors.surfaceVariant;
                      }
                      return Colors.transparent;
                    }),
                    padding: WidgetStatePropertyAll(
                      EdgeInsets.symmetric(
                        horizontal: AppSpace.s(12),
                        vertical: AppSpace.s(10),
                      ),
                    ),
                  ),
                  leadingIcon: SizedBox(
                    width: 18,
                    child: cohort.cohortId == selected.cohortId
                        ? Icon(Icons.check, size: 16, color: AppColors.primary)
                        : null,
                  ),
                  child: Text(
                    _cohortLabel(cohort),
                    maxLines: 1,
                    softWrap: false,
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: cohort.cohortId == selected.cohortId
                          ? FontWeight.w600
                          : FontWeight.w500,
                      color: AppColors.textPrimary,
                    ),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }
}

double _menuWidth(
  BuildContext context,
  List<CohortModel> cohorts,
  double triggerWidth,
) {
  const style = TextStyle(fontSize: 13, fontWeight: FontWeight.w600);
  var textWidth = 0.0;
  for (final cohort in cohorts) {
    final painter = TextPainter(
      text: TextSpan(text: _cohortLabel(cohort), style: style),
      maxLines: 1,
      textDirection: Directionality.of(context),
    )..layout();
    if (painter.width > textWidth) textWidth = painter.width;
  }

  // 체크 아이콘 + 항목 패딩 + 메뉴 내부 여백. 글자 끝이 잘리지 않게 넉넉히.
  final content = textWidth + 18 + 28 + 48;
  final screen = MediaQuery.sizeOf(context).width - 24;
  final floor = triggerWidth > 0 ? triggerWidth : 180.0;
  return content.clamp(floor, screen);
}

String _cohortLabel(CohortModel cohort) => cohort.status == CohortStatus.active
    ? cohort.name
    : '${cohort.name} (${cohort.statusLabel})';

class _CohortTrigger extends StatelessWidget {
  const _CohortTrigger({
    required this.label,
    required this.isOpen,
    required this.isDark,
    required this.onPressed,
  });

  final String label;
  final bool isOpen;
  final bool isDark;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: ShellChrome.chipFill(isDark),
      borderRadius: BorderRadius.circular(10),
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(10),
        child: Container(
          constraints: BoxConstraints(minHeight: AppSpace.row(36)),
          padding: EdgeInsets.fromLTRB(
            AppSpace.s(12),
            AppSpace.s(6),
            AppSpace.s(8),
            AppSpace.s(6),
          ),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: ShellChrome.chipBorder(isDark)),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Flexible(
                child: Text(
                  label,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: ShellChrome.appBarForeground(isDark),
                    height: 1.2,
                  ),
                ),
              ),
              SizedBox(width: AppSpace.s(4)),
              Icon(
                isOpen ? Icons.keyboard_arrow_up : Icons.keyboard_arrow_down,
                size: 18,
                color: ShellChrome.appBarMuted(isDark),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
