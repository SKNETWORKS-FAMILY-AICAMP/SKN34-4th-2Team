import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/constants/attendance_status.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_layout.dart';
import '../../../core/utils/date_utils.dart';
import '../../../core/widgets/app_dropdown.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/models/domain_models.dart';
import '../../../shared/models/user_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../onboarding/admin/admin_onboarding_keys.dart';
import '../../onboarding/domain/onboarding_target_registry.dart';
import '../../../core/theme/app_space.dart';

/// 관리자 — 기수별 당일 출석 전체 조회/수정
class AdminAttendanceScreen extends ConsumerStatefulWidget {
  const AdminAttendanceScreen({super.key});

  @override
  ConsumerState<AdminAttendanceScreen> createState() =>
      _AdminAttendanceScreenState();
}

class _AdminAttendanceScreenState extends ConsumerState<AdminAttendanceScreen> {
  DateTime _day = DateTime.now();
  String _query = '';
  DemoAttendanceSeed? _seeding;
  bool _ensuringNotice = false;

  String get _dateKey => AppDateUtils.toDateKey(_day);

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _day,
      firstDate: DateTime(2024),
      lastDate: DateTime.now().add(const Duration(days: 365)),
    );
    if (picked != null) setState(() => _day = picked);
  }

  Future<void> _seedDemo(DemoAttendanceSeed seed) async {
    final cohortId = ref.read(effectiveCohortIdProvider);
    final students = ref.read(cohortStudentsProvider).asData?.value ?? [];
    if (cohortId == null) return;
    setState(() => _seeding = seed);
    try {
      final n =
          await ref
                  .read(lmsRepositoryProvider)
                  .seedDemoAttendances(
                    cohortId: cohortId,
                    dateKey: _dateKey,
                    students: students,
                    seed: seed,
                  )
              as int;
      if (!mounted) return;
      final label = seed == DemoAttendanceSeed.checkIn ? '예시 입실' : '예시 퇴실';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('$label $n건을 반영했습니다. (폼·수동 기록은 유지)')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('채우기 실패: $e')),
      );
    } finally {
      if (mounted) setState(() => _seeding = null);
    }
  }

  Future<void> _ensureNotice() async {
    final cohortId = ref.read(effectiveCohortIdProvider);
    final user = ref.read(currentUserSyncProvider);
    if (cohortId == null || user == null) return;
    setState(() => _ensuringNotice = true);
    try {
      final created =
          await ref
                  .read(lmsRepositoryProvider)
                  .ensureDailyAttendanceFormNotice(
                    cohortId: cohortId,
                    authorId: user.uid,
                    authorName: user.displayName,
                  )
              as bool;
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            created
                ? '매일 08:30 LMS 출결 폼 공지를 등록했습니다.'
                : '이미 등록된 매일 08:30 출결 공지가 있습니다.',
          ),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('공지 등록 실패: $e')),
      );
    } finally {
      if (mounted) setState(() => _ensuringNotice = false);
    }
  }

  Future<void> _setStatus({
    required UserModel student,
    required String status,
  }) async {
    final cohortId = ref.read(effectiveCohortIdProvider);
    if (cohortId == null) return;
    try {
      await ref
          .read(lmsRepositoryProvider)
          .upsertAttendanceStatus(
            cohortId: cohortId,
            userId: student.uid,
            userDisplayName: student.displayName,
            dateKey: _dateKey,
            status: status,
          );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('저장 실패: $e')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final cohortName = ref.watch(effectiveCohortNameProvider);
    final studentsAsync = ref.watch(cohortStudentsProvider);
    final attendancesAsync = ref.watch(attendancesByDateProvider(_dateKey));

    return Scaffold(
      body: studentsAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => ErrorView(
          message: e.toString(),
          onRetry: () => ref.invalidate(cohortStudentsProvider),
        ),
        data: (students) {
          final byUser = <String, AttendanceModel>{};
          for (final a in attendancesAsync.asData?.value ?? const []) {
            byUser[a.userId] = a;
          }
          final q = _query.trim();
          final filtered = students.where((s) {
            if (q.isEmpty) return true;
            return s.displayName.contains(q);
          }).toList()..sort((a, b) => a.displayName.compareTo(b.displayName));

          final counts = <String, int>{
            for (final s in AttendanceStatus.all) s: 0,
            '_none': 0,
          };
          for (final s in students) {
            final status = byUser[s.uid]?.dayStatus;
            if (status == null || !AttendanceStatus.all.contains(status)) {
              counts['_none'] = (counts['_none'] ?? 0) + 1;
            } else {
              counts[status] = (counts[status] ?? 0) + 1;
            }
          }

          // Scaffold body 높이를 명시해 Column+Expanded가 깨지지 않게 한다.
          // (DataTable+가로 ScrollView 중첩은 무한 높이 이슈가 있어 ListView로 대체)
          return LayoutBuilder(
            builder: (context, constraints) {
              final width = constraints.maxWidth < AppLayout.wide
                  ? constraints.maxWidth
                  : AppLayout.wide;
              return Align(
                alignment: Alignment.topCenter,
                child: SizedBox(
                  width: width,
                  height: constraints.maxHeight,
                  child: Padding(
                    padding: EdgeInsets.fromLTRB(AppSpace.s(20), AppSpace.s(16), AppSpace.s(20), AppSpace.s(28)),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(
                          cohortName ?? '기수를 먼저 선택하세요',
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w700,
                            color: AppColors.textPrimary,
                          ),
                        ),
                        SizedBox(height: AppSpace.s(6)),
                        Text(
                          '고용24 입퇴실은 예시 데이터입니다. 지각·조퇴·외출·결석·공가는 당일 구글폼 선택값이 반영됩니다.',
                          style: TextStyle(
                            fontSize: 13,
                            height: 1.4,
                            color: AppColors.textSecondary,
                          ),
                        ),
                        SizedBox(height: AppSpace.s(16)),
                        _ToolbarCard(
                          child: Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            crossAxisAlignment: WrapCrossAlignment.center,
                            children: [
                              OutlinedButton.icon(
                                onPressed: _pickDate,
                                icon: const Icon(
                                  Icons.calendar_today,
                                  size: 16,
                                ),
                                label: Text(_dateKey),
                              ),
                              TextButton(
                                onPressed: () =>
                                    setState(() => _day = DateTime.now()),
                                child: const Text('오늘'),
                              ),
                              SizedBox(width: AppSpace.s(4)),
                              FilledButton.icon(
                                onPressed: _seeding != null || students.isEmpty
                                    ? null
                                    : () =>
                                          _seedDemo(DemoAttendanceSeed.checkIn),
                                icon: _seeding == DemoAttendanceSeed.checkIn
                                    ? const SizedBox(
                                        width: 14,
                                        height: 14,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                        ),
                                      )
                                    : const Icon(Icons.login_rounded, size: 16),
                                label: const Text('예시 입실 채우기'),
                              ),
                              FilledButton.icon(
                                onPressed: _seeding != null || students.isEmpty
                                    ? null
                                    : () => _seedDemo(
                                        DemoAttendanceSeed.checkOut,
                                      ),
                                icon: _seeding == DemoAttendanceSeed.checkOut
                                    ? const SizedBox(
                                        width: 14,
                                        height: 14,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                        ),
                                      )
                                    : const Icon(
                                        Icons.logout_rounded,
                                        size: 16,
                                      ),
                                label: const Text('예시 퇴실 채우기'),
                              ),
                              KeyedSubtree(
                                key: OnboardingTargetRegistry.keyOf(
                                  AdminOnboardingTargets.attendanceDailyNotice,
                                ),
                                child: OutlinedButton.icon(
                                  onPressed: _ensuringNotice
                                      ? null
                                      : _ensureNotice,
                                  icon: _ensuringNotice
                                      ? const SizedBox(
                                          width: 14,
                                          height: 14,
                                          child: CircularProgressIndicator(
                                            strokeWidth: 2,
                                          ),
                                        )
                                      : const Icon(
                                          Icons.campaign_outlined,
                                          size: 16,
                                        ),
                                  label: const Text('매일 08:30 공지 등록'),
                                ),
                              ),
                            ],
                          ),
                        ),
                        SizedBox(height: AppSpace.s(12)),
                        _ToolbarCard(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Wrap(
                                spacing: 8,
                                runSpacing: 8,
                                children: [
                                  _CountChip(
                                    label: '전체 ${students.length}',
                                    color: AppColors.textPrimary,
                                  ),
                                  ...AttendanceStatus.all.map(
                                    (s) => _CountChip(
                                      label:
                                          '${AttendanceStatus.labelOf(s)} ${counts[s] ?? 0}',
                                      color: AttendanceStatus.colorOf(s),
                                    ),
                                  ),
                                  _CountChip(
                                    label: '미기록 ${counts['_none'] ?? 0}',
                                    color: AppColors.textHint,
                                  ),
                                ],
                              ),
                              SizedBox(height: AppSpace.s(12)),
                              TextField(
                                decoration: const InputDecoration(
                                  prefixIcon: Icon(Icons.search, size: 20),
                                  hintText: '이름 검색',
                                  isDense: true,
                                ),
                                onChanged: (v) => setState(() => _query = v),
                              ),
                            ],
                          ),
                        ),
                        SizedBox(height: AppSpace.s(12)),
                        Expanded(
                          child: _AttendanceList(
                            attendancesAsync: attendancesAsync,
                            studentsEmpty: students.isEmpty,
                            filtered: filtered,
                            byUser: byUser,
                            onStatusChanged: _setStatus,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }
}

class _AttendanceList extends StatelessWidget {
  const _AttendanceList({
    required this.attendancesAsync,
    required this.studentsEmpty,
    required this.filtered,
    required this.byUser,
    required this.onStatusChanged,
  });

  final AsyncValue<List<AttendanceModel>> attendancesAsync;
  final bool studentsEmpty;
  final List<UserModel> filtered;
  final Map<String, AttendanceModel> byUser;
  final Future<void> Function({
    required UserModel student,
    required String status,
  })
  onStatusChanged;

  @override
  Widget build(BuildContext context) {
    if (attendancesAsync.isLoading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (attendancesAsync.hasError) {
      return ErrorView(message: attendancesAsync.error.toString());
    }
    if (studentsEmpty) {
      return Center(
        child: Text(
          '이 기수에 재원 학생이 없습니다.',
          style: TextStyle(color: AppColors.textSecondary),
        ),
      );
    }
    if (filtered.isEmpty) {
      return Center(
        child: Text(
          '검색 결과가 없습니다.',
          style: TextStyle(color: AppColors.textSecondary),
        ),
      );
    }

    return SizedBox.expand(
      child: _ToolbarCard(
        padding: EdgeInsets.zero,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const _AttendanceHeader(),
            const Divider(height: 1),
            Expanded(
              child: ListView.separated(
                itemCount: filtered.length,
                separatorBuilder: (_, _) => const Divider(height: 1),
                itemBuilder: (context, index) {
                  final student = filtered[index];
                  return _AttendanceRow(
                    student: student,
                    attendance: byUser[student.uid],
                    onStatusChanged: onStatusChanged,
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _AttendanceHeader extends StatelessWidget {
  const _AttendanceHeader();

  @override
  Widget build(BuildContext context) {
    return Container(
      color: AppColors.surfaceVariant,
      padding: EdgeInsets.symmetric(horizontal: AppSpace.s(16), vertical: AppSpace.s(12)),
      child: Row(
        children: [
          Expanded(flex: 2, child: Text('이름', style: _headerStyle)),
          Expanded(child: Text('입실', style: _headerStyle)),
          Expanded(child: Text('퇴실', style: _headerStyle)),
          Expanded(flex: 2, child: Text('폼', style: _headerStyle)),
          SizedBox(width: 120, child: Text('최종 상태', style: _headerStyle)),
          Expanded(child: Text('출처', style: _headerStyle)),
        ],
      ),
    );
  }
}

TextStyle get _headerStyle => TextStyle(
  fontSize: 12,
  fontWeight: FontWeight.w700,
  color: AppColors.textSecondary,
);

class _AttendanceRow extends StatelessWidget {
  const _AttendanceRow({
    required this.student,
    required this.attendance,
    required this.onStatusChanged,
  });

  final UserModel student;
  final AttendanceModel? attendance;
  final Future<void> Function({
    required UserModel student,
    required String status,
  })
  onStatusChanged;

  @override
  Widget build(BuildContext context) {
    final status = attendance?.dayStatus;
    final value = AttendanceStatus.all.contains(status) ? status : null;

    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpace.s(16), vertical: AppSpace.s(8)),
      child: Row(
        children: [
          Expanded(
            flex: 2,
            child: Text(
              student.displayName,
              style: const TextStyle(fontWeight: FontWeight.w600),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          Expanded(
            child: Text(
              attendance?.checkInTime ?? '-',
              overflow: TextOverflow.ellipsis,
            ),
          ),
          Expanded(
            child: Text(
              attendance?.checkOutTime ?? '-',
              overflow: TextOverflow.ellipsis,
            ),
          ),
          Expanded(
            flex: 2,
            child: Text(
              attendance?.formSummary ?? '-',
              overflow: TextOverflow.ellipsis,
            ),
          ),
          SizedBox(
            width: 120,
            child: AppDropdownInline<String>(
              value: value,
              hint: '미기록',
              isExpanded: true,
              items: [
                for (final s in AttendanceStatus.all)
                  AppDropdownItem(
                    value: s,
                    label: AttendanceStatus.labelOf(s),
                    child: Row(
                      children: [
                        Container(
                          width: 8,
                          height: 8,
                          decoration: BoxDecoration(
                            color: AttendanceStatus.colorOf(s),
                            shape: BoxShape.circle,
                          ),
                        ),
                        SizedBox(width: AppSpace.s(6)),
                        Flexible(
                          child: Text(
                            AttendanceStatus.labelOf(s),
                            style: const TextStyle(fontSize: 13),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
              onChanged: (s) {
                if (s != null) {
                  onStatusChanged(student: student, status: s);
                }
              },
            ),
          ),
          Expanded(
            child: Text(
              attendance?.sourceLabel ?? '-',
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}

class _ToolbarCard extends StatelessWidget {
  const _ToolbarCard({required this.child, EdgeInsetsGeometry? padding})
    : _padding = padding;

  final Widget child;
  final EdgeInsetsGeometry? _padding;
  EdgeInsetsGeometry get padding => _padding ?? EdgeInsets.all(AppSpace.s(14));

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: AppColors.border),
      ),
      clipBehavior: Clip.antiAlias,
      child: Padding(padding: padding, child: child),
    );
  }
}

class _CountChip extends StatelessWidget {
  const _CountChip({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(horizontal: AppSpace.s(10), vertical: AppSpace.s(6)),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w600,
          color: color,
        ),
      ),
    );
  }
}
