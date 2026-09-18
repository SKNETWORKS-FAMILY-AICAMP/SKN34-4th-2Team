import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:table_calendar/table_calendar.dart';

import '../../../../core/constants/attendance_status.dart';
import '../../../../core/constants/korean_holidays.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/date_utils.dart';
import '../../../../core/widgets/app_dropdown.dart';
import '../../../../shared/models/user_model.dart';
import '../../../../shared/providers/cohort_providers.dart';
import '../../../../shared/providers/lms_providers.dart';
import '../../../../core/theme/app_space.dart';

/// 대시보드 출석 캘린더 — 상태 색상 (외출 포함)
class AttendanceCalendarCard extends ConsumerStatefulWidget {
  const AttendanceCalendarCard({
    super.key,
    required this.user,
    this.compact = false,
  });

  final UserModel user;
  final bool compact;

  @override
  ConsumerState<AttendanceCalendarCard> createState() =>
      _AttendanceCalendarCardState();
}

class _AttendanceCalendarCardState
    extends ConsumerState<AttendanceCalendarCard> {
  DateTime _focusedDay = DateTime.now();
  CalendarFormat _format = CalendarFormat.month;

  String get _targetUserId {
    final isAdmin = ref.watch(isAdminProvider);
    if (!isAdmin) return widget.user.uid;
    final selected = ref.watch(adminAttendanceTargetUserIdProvider);
    if (selected != null) return selected;
    final students = ref.watch(cohortStudentsProvider).asData?.value;
    if (students != null && students.isNotEmpty) return students.first.uid;
    return widget.user.uid;
  }

  String get _targetDisplayName {
    final isAdmin = ref.watch(isAdminProvider);
    if (!isAdmin) return widget.user.displayName;
    final students = ref.watch(cohortStudentsProvider).asData?.value ?? [];
    return students
            .where((s) => s.uid == _targetUserId)
            .map((s) => s.displayName)
            .firstOrNull ??
        widget.user.displayName;
  }

  Future<void> _onAdminSetStatus(DateTime day, String? current) async {
    final cohortId = ref.read(effectiveCohortIdProvider);
    if (cohortId == null) return;

    final picked = await showDialog<String?>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(AppDateUtils.toDateKey(day)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ...AttendanceStatus.all.map(
              (s) => ListTile(
                leading: CircleAvatar(
                  radius: 8,
                  backgroundColor: AttendanceStatus.colorOf(s),
                ),
                title: Text(AttendanceStatus.labelOf(s)),
                onTap: () => Navigator.pop(ctx, s),
              ),
            ),
            if (current != null)
              ListTile(
                leading: const Icon(Icons.clear, size: 18),
                title: const Text('기록 삭제'),
                onTap: () => Navigator.pop(ctx, '__clear__'),
              ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('닫기'),
          ),
        ],
      ),
    );

    if (picked == null || !mounted) return;

    try {
      if (picked == '__clear__') {
        await ref
            .read(lmsRepositoryProvider)
            .clearAttendanceStatus(
              cohortId: cohortId,
              userId: _targetUserId,
              dateKey: AppDateUtils.toDateKey(day),
            );
      } else {
        await ref
            .read(lmsRepositoryProvider)
            .upsertAttendanceStatus(
              cohortId: cohortId,
              userId: _targetUserId,
              userDisplayName: _targetDisplayName,
              dateKey: AppDateUtils.toDateKey(day),
              status: picked,
            );
      }
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('출석 상태가 저장되었습니다.')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('저장 실패: $e')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final isAdmin = ref.watch(isAdminProvider);
    final statusMapAsync = ref.watch(
      attendanceStatusMapProvider(_targetUserId),
    );
    final statusMap = statusMapAsync.asData?.value ?? {};
    final monthLabel =
        '${_focusedDay.year}.${_focusedDay.month.toString().padLeft(2, '0')}';
    final compact = widget.compact;

    return Material(
      color: AppColors.surface,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: AppColors.border),
      ),
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          compact ? AppSpace.s(10) : AppSpace.s(14),
          compact ? AppSpace.s(10) : AppSpace.s(14),
          compact ? AppSpace.s(10) : AppSpace.s(14),
          compact ? AppSpace.s(8) : AppSpace.s(10),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                const Text(
                  '출석',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                ),
                const Spacer(),
                if (isAdmin && !compact)
                  ref
                      .watch(cohortStudentsProvider)
                      .when(
                        loading: () => const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                        error: (_, _) => const SizedBox.shrink(),
                        data: (students) {
                          if (students.isEmpty) return const SizedBox.shrink();
                          return AppDropdownInline<String>(
                            value: students.any((s) => s.uid == _targetUserId)
                                ? _targetUserId
                                : students.first.uid,
                            fontSize: 11,
                            items: [
                              for (final s in students)
                                AppDropdownItem(
                                  value: s.uid,
                                  label: s.displayName,
                                ),
                            ],
                            onChanged: (uid) {
                              if (uid != null) {
                                ref
                                    .read(
                                      adminAttendanceTargetUserIdProvider
                                          .notifier,
                                    )
                                    .select(uid);
                              }
                            },
                          );
                        },
                      ),
              ],
            ),
            if (isAdmin && compact) ...[
              SizedBox(height: AppSpace.s(6)),
              ref
                  .watch(cohortStudentsProvider)
                  .when(
                    loading: () => const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                    error: (_, __) => const SizedBox.shrink(),
                    data: (students) {
                      if (students.isEmpty) return const SizedBox.shrink();
                      return AppDropdownInline<String>(
                        value: students.any((s) => s.uid == _targetUserId)
                            ? _targetUserId
                            : students.first.uid,
                        isExpanded: true,
                        fontSize: 11,
                        items: [
                          for (final s in students)
                            AppDropdownItem(
                              value: s.uid,
                              label: s.displayName,
                            ),
                        ],
                        onChanged: (uid) {
                          if (uid != null) {
                            ref
                                .read(
                                  adminAttendanceTargetUserIdProvider.notifier,
                                )
                                .select(uid);
                          }
                        },
                      );
                    },
                  ),
            ],
            if (statusMapAsync.hasError) ...[
              SizedBox(height: AppSpace.s(8)),
              Text(
                '출석 불러오기 실패: ${statusMapAsync.error}',
                style: TextStyle(fontSize: 11, color: AppColors.error),
              ),
            ],
            SizedBox(height: compact ? 4 : 8),
            Row(
              children: [
                IconButton(
                  icon: const Icon(Icons.chevron_left, size: 20),
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(
                    minWidth: 32,
                    minHeight: 32,
                  ),
                  onPressed: () => setState(() {
                    _focusedDay = DateTime(
                      _focusedDay.year,
                      _focusedDay.month - 1,
                    );
                  }),
                ),
                Expanded(
                  child: Text(
                    monthLabel,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 14,
                    ),
                  ),
                ),
                if (!compact)
                  TextButton(
                    onPressed: () => setState(() {
                      _format = _format == CalendarFormat.month
                          ? CalendarFormat.twoWeeks
                          : CalendarFormat.month;
                    }),
                    style: TextButton.styleFrom(
                      padding: EdgeInsets.symmetric(horizontal: AppSpace.s(8)),
                      minimumSize: Size.zero,
                      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    ),
                    child: Text(
                      _format == CalendarFormat.month ? '한 달' : '2주',
                      style: const TextStyle(fontSize: 11),
                    ),
                  ),
                IconButton(
                  icon: const Icon(Icons.chevron_right, size: 20),
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(
                    minWidth: 32,
                    minHeight: 32,
                  ),
                  onPressed: () => setState(() {
                    _focusedDay = DateTime(
                      _focusedDay.year,
                      _focusedDay.month + 1,
                    );
                  }),
                ),
              ],
            ),
            TableCalendar<void>(
              firstDay: DateTime.utc(2020, 1, 1),
              lastDay: DateTime.utc(2030, 12, 31),
              focusedDay: _focusedDay,
              calendarFormat: _format,
              availableCalendarFormats: const {
                CalendarFormat.month: '한 달',
                CalendarFormat.twoWeeks: '2주',
              },
              onFormatChanged: (f) => setState(() => _format = f),
              headerVisible: false,
              daysOfWeekHeight: compact ? 18 : 24,
              rowHeight: compact ? 26 : 34,
              onPageChanged: (focused) => setState(() => _focusedDay = focused),
              onDaySelected: (selected, focused) {
                setState(() => _focusedDay = focused);
                if (isAdmin) {
                  final key = _dateKeyOf(selected);
                  _onAdminSetStatus(selected, statusMap[key]);
                } else {
                  final key = _dateKeyOf(selected);
                  final s = statusMap[key];
                  if (s != null) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text(
                          '${AttendanceStatus.labelOf(s)} ($key)',
                        ),
                      ),
                    );
                  }
                }
              },
              // 요일을 지정하지 않으면 기기 언어를 따라 영어로 나온다. 그마저
              // 폭에 따라 Mo·We처럼 두 글자로 잘려 들쭉날쭉했다. 한 글자로 못박는다.
              daysOfWeekStyle: DaysOfWeekStyle(
                dowTextFormatter: (date, locale) => _dayNames[date.weekday % 7],
                weekdayStyle: TextStyle(
                  fontSize: compact ? 11 : 12,
                  color: AppColors.textSecondary,
                ),
                weekendStyle: TextStyle(
                  fontSize: compact ? 11 : 12,
                  color: AppColors.textSecondary,
                ),
              ),
              calendarStyle: CalendarStyle(
                outsideDaysVisible: !compact,
                defaultTextStyle: TextStyle(fontSize: compact ? 11 : 12),
                weekendTextStyle: TextStyle(fontSize: compact ? 11 : 12),
                outsideTextStyle: TextStyle(
                  fontSize: compact ? 11 : 12,
                  color: AppColors.textHint,
                ),
                todayDecoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(color: AppColors.textPrimary, width: 1.5),
                ),
                todayTextStyle: TextStyle(
                  fontWeight: FontWeight.bold,
                  color: AppColors.textPrimary,
                ),
                selectedDecoration: BoxDecoration(
                  color: AppColors.primary,
                  shape: BoxShape.circle,
                ),
                selectedTextStyle: const TextStyle(color: Colors.white),
              ),
              calendarBuilders: CalendarBuilders(
                // today/selected보다 우선 — 출석 색이 항상 보이게
                prioritizedBuilder: (context, day, focusedDay) {
                  return _statusDayCell(
                    day: day,
                    statusMap: statusMap,
                    compact: compact,
                  );
                },
                defaultBuilder: (context, day, focusedDay) =>
                    _plainDayCell(day, compact: compact, outside: false),
                outsideBuilder: (context, day, focusedDay) =>
                    _plainDayCell(day, compact: compact, outside: true),
                todayBuilder: (context, day, focusedDay) =>
                    _todayCell(day, compact: compact),
              ),
            ),
            SizedBox(height: compact ? 4 : 6),
            AttendanceStatusLegend(compact: compact),
          ],
        ),
      ),
    );
  }

  /// 일요일부터. `DateTime.weekday`는 월요일이 1, 일요일이 7이라 7로 나눈 나머지를 쓴다.
  static const _dayNames = ['일', '월', '화', '수', '목', '금', '토'];

  /// 종이 달력을 따른다. 공휴일과 일요일은 빨강, 토요일은 파랑.
  static Color _dayColor(DateTime day, {required bool outside}) {
    if (outside) return AppColors.textHint;
    if (koreanHolidays.containsKey(_dateKeyOf(day))) return AppColors.error;
    if (day.weekday == DateTime.sunday) return AppColors.error;
    if (day.weekday == DateTime.saturday) return AppColors.primary;
    return AppColors.textPrimary;
  }

  static Widget _plainDayCell(
    DateTime day, {
    required bool compact,
    required bool outside,
  }) => Center(
    child: Text(
      '${day.day}',
      style: TextStyle(
        fontSize: compact ? 11 : 12,
        color: _dayColor(day, outside: outside),
      ),
    ),
  );

  /// 오늘 표시. 동그라미 지름을 줄 높이 안으로 못박는다.
  ///
  /// 예전에는 칸 전체를 채우는 장식을 썼는데, 줄 높이가 26~34밖에 안 되어 원이
  /// 칸 밖으로 밀려났다. 달의 첫 칸에서는 왼쪽이 잘려 숫자까지 가렸다.
  static Widget _todayCell(DateTime day, {required bool compact}) {
    final diameter = compact ? 20.0 : 26.0;
    return Center(
      child: Container(
        width: diameter,
        height: diameter,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          border: Border.all(color: AppColors.textPrimary, width: 1.5),
        ),
        alignment: Alignment.center,
        child: Text(
          '${day.day}',
          style: TextStyle(
            fontSize: compact ? 10 : 12,
            fontWeight: FontWeight.bold,
            color: _dayColor(day, outside: false),
          ),
        ),
      ),
    );
  }

  static String _dateKeyOf(DateTime day) =>
      AppDateUtils.toDateKey(DateTime(day.year, day.month, day.day));

  static Widget? _statusDayCell({
    required DateTime day,
    required Map<String, String> statusMap,
    required bool compact,
  }) {
    final key = _dateKeyOf(day);
    final status = statusMap[key];
    if (status == null) return null;

    final color = AttendanceStatus.colorOf(status);
    final isToday = isSameDay(day, DateTime.now());
    return Container(
      margin: EdgeInsets.all(compact ? AppSpace.s(2) : AppSpace.s(4)),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.2),
        shape: BoxShape.circle,
        border: Border.all(
          color: isToday ? AppColors.textPrimary : color,
          width: isToday ? 1.5 : 1.4,
        ),
      ),
      alignment: Alignment.center,
      child: Text(
        '${day.day}',
        style: TextStyle(
          fontSize: compact ? 10 : 12,
          fontWeight: FontWeight.w700,
          color: color,
        ),
      ),
    );
  }
}

/// 출결 색 설명. 달력 아래에 한 줄로 놓인다.
class AttendanceStatusLegend extends StatelessWidget {
  const AttendanceStatusLegend({super.key, required this.compact});

  final bool compact;

  @override
  Widget build(BuildContext context) {
    // 범례는 한 줄이어야 한다. 여섯 가지가 두 줄로 갈라지면 어느 색이 어느 줄의
    // 설명인지 눈이 한 번 더 헤맨다. 칸이 좁으면 줄바꿈 대신 통째로 줄인다.
    return FittedBox(
      fit: BoxFit.scaleDown,
      alignment: Alignment.centerLeft,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (final (i, s) in AttendanceStatus.all.indexed) ...[
            if (i > 0) SizedBox(width: compact ? 6 : 10),
            _legendItem(s),
          ],
        ],
      ),
    );
  }

  Widget _legendItem(String s) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: compact ? 7 : 8,
          height: compact ? 7 : 8,
          decoration: BoxDecoration(
            color: AttendanceStatus.colorOf(s),
            shape: BoxShape.circle,
          ),
        ),
        SizedBox(width: AppSpace.s(4)),
        Text(
          AttendanceStatus.labelOf(s),
          style: TextStyle(
            fontSize: compact ? 9 : 10,
            color: AppColors.textSecondary,
          ),
        ),
      ],
    );
  }
}
