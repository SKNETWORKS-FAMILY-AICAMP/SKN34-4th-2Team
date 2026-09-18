import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/constants/attendance_status.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/utils/class_period_utils.dart';
import '../../../core/utils/date_utils.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/models/domain_models.dart';
import '../../../shared/models/user_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../onboarding/domain/onboarding_target_registry.dart';
import '../../onboarding/instructor/instructor_onboarding_keys.dart';
import '../../seating/models/seating_assignment_model.dart';
import '../../seating/models/seating_layout_model.dart';
import '../../seating/providers/seating_providers.dart';
import '../../seating/presentation/widgets/seat_grid.dart';
import '../../../core/theme/app_space.dart';

List<UserModel> _sortByKoreanName(List<UserModel> students) {
  final copy = [...students];
  copy.sort((a, b) {
    final byName = a.displayName.compareTo(b.displayName);
    if (byName != 0) return byName;
    return a.uid.compareTo(b.uid);
  });
  return copy;
}

const _kAttendanceContentMaxWidth = 1100.0;
const _kRollCallWidth = 260.0;
const _kHeldWidth = 220.0;

/// 좌석 박스가 가용 폭을 채우도록 스케일 (안쪽 그리드 확대)
Size _seatingCardSize({
  required SeatingLayoutModel? layout,
  required double maxWidth,
  required double maxHeight,
}) {
  if (layout == null) return Size(math.min(520, maxWidth), 240);

  const cellW = 34.0;
  const cellH = 30.0;
  const rowGap = 3.0;
  const groupGap = 2.0;
  const hintH = 14.0;
  const titleH = 20.0;
  const padH = 10.0;
  const padV = 10.0;

  final natW = layout.cols * (cellW + groupGap * 2);
  final natH = hintH + layout.rows * (cellH + rowGap);

  final scaleByW = (maxWidth - padH) / natW;
  final heightIfFullWidth = natH * scaleByW + padV + titleH;
  if (heightIfFullWidth <= maxHeight) {
    return Size(maxWidth, heightIfFullWidth);
  }

  final scaleByH = (maxHeight - padV - titleH) / natH;
  return Size(
    (natW * scaleByH + padH).clamp(0.0, maxWidth),
    maxHeight,
  );
}

/// 강사/관리자 — 교시별 자리 확인 (학생 조작 없음)
class InstructorAttendanceScreen extends ConsumerStatefulWidget {
  const InstructorAttendanceScreen({
    super.key,
    this.title = '자리 확인',
  });

  final String title;

  @override
  ConsumerState<InstructorAttendanceScreen> createState() =>
      _InstructorAttendanceScreenState();
}

class _InstructorAttendanceScreenState
    extends ConsumerState<InstructorAttendanceScreen> {
  DateTime _day = DateTime.now();
  late ClassPeriod _period;
  String? _currentUid;
  bool _rotateSeating180 = false;
  final _rollCallScrollKey = GlobalKey<_RollCallPaneState>();

  @override
  void initState() {
    super.initState();
    _period = ClassPeriodUtils.suggestedPeriod(day: _day);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _carryForwardIfNeeded();
    });
  }

  String get _dateKey => AppDateUtils.toDateKey(_day);

  String get _scopeKey => ClassPeriodUtils.providerKey(_dateKey, _period.id);

  Future<void> _carryForwardIfNeeded() async {
    final cohortId = ref.read(effectiveCohortIdProvider);
    final user = ref.read(currentUserSyncProvider);
    if (cohortId == null || user == null) return;
    try {
      await ref
          .read(lmsRepositoryProvider)
          .ensureRollCallCarriedForward(
            cohortId: cohortId,
            dateKey: _dateKey,
            periodId: _period.id,
            updatedBy: user.uid,
          );
      if (!mounted) return;
      ref.invalidate(rollCallConfirmedProvider(_scopeKey));
      ref.invalidate(rollCallHeldProvider(_scopeKey));
    } catch (_) {
      // 이어받기 실패해도 자리 확인은 계속 사용 가능
    }
  }

  String? _resolvedCurrent(
    List<UserModel> students,
    Set<String> confirmed,
  ) {
    if (_currentUid != null && students.any((s) => s.uid == _currentUid)) {
      return _currentUid;
    }
    for (final s in students) {
      if (!confirmed.contains(s.uid)) return s.uid;
    }
    return students.isEmpty ? null : students.first.uid;
  }

  void _advanceAfterMark({
    required UserModel student,
    required List<UserModel> students,
    required Set<String> confirmed,
    required Set<String> held,
  }) {
    final skip = {...confirmed, ...held, student.uid};
    final remaining = students.where((s) => !skip.contains(s.uid)).toList();
    final nextUid = remaining.isEmpty ? student.uid : remaining.first.uid;
    setState(() => _currentUid = nextUid);
    _scrollRollCallTo(nextUid);
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _day,
      firstDate: DateTime(2024),
      lastDate: DateTime.now().add(const Duration(days: 365)),
    );
    if (picked != null) {
      setState(() {
        _day = picked;
        _period = ClassPeriodUtils.suggestedPeriod(day: picked);
        _currentUid = null;
      });
      _carryForwardIfNeeded();
    }
  }

  void _selectPeriod(ClassPeriod period) {
    if (period.id == _period.id) return;
    setState(() {
      _period = period;
      _currentUid = null;
    });
    _carryForwardIfNeeded();
  }

  void _selectStudent(String uid) {
    setState(() => _currentUid = uid);
    _scrollRollCallTo(uid);
  }

  void _move(List<UserModel> students, String? currentUid, int delta) {
    if (students.isEmpty) return;
    final i = students.indexWhere((s) => s.uid == currentUid);
    final next = (i < 0 ? 0 : i + delta).clamp(0, students.length - 1).toInt();
    final uid = students[next].uid;
    setState(() => _currentUid = uid);
    _scrollRollCallTo(uid);
  }

  void _scrollRollCallTo(String uid) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _rollCallScrollKey.currentState?.scrollToUid(uid);
    });
  }

  Future<void> _toggleConfirm({
    required UserModel student,
    required bool confirmed,
    required List<UserModel> students,
    required Set<String> alreadyConfirmed,
    required Set<String> held,
  }) async {
    final cohortId = ref.read(effectiveCohortIdProvider);
    final user = ref.read(currentUserSyncProvider);
    if (cohortId == null || user == null) return;
    try {
      await ref
          .read(lmsRepositoryProvider)
          .setRollCallConfirmed(
            cohortId: cohortId,
            dateKey: _dateKey,
            periodId: _period.id,
            userId: student.uid,
            confirmed: confirmed,
            updatedBy: user.uid,
          );
      if (!mounted) return;
      if (confirmed) {
        final nextHeld = Set<String>.from(held)..remove(student.uid);
        _advanceAfterMark(
          student: student,
          students: students,
          confirmed: {...alreadyConfirmed, student.uid},
          held: nextHeld,
        );
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('확인 저장 실패: $e')),
      );
    }
  }

  Future<void> _toggleHold({
    required UserModel student,
    required bool held,
    required List<UserModel> students,
    required Set<String> confirmed,
    required Set<String> alreadyHeld,
  }) async {
    final cohortId = ref.read(effectiveCohortIdProvider);
    final user = ref.read(currentUserSyncProvider);
    if (cohortId == null || user == null) return;
    try {
      await ref
          .read(lmsRepositoryProvider)
          .setRollCallHeld(
            cohortId: cohortId,
            dateKey: _dateKey,
            periodId: _period.id,
            userId: student.uid,
            held: held,
            updatedBy: user.uid,
          );
      if (!mounted) return;
      if (held) {
        final nextConfirmed = Set<String>.from(confirmed)..remove(student.uid);
        _advanceAfterMark(
          student: student,
          students: students,
          confirmed: nextConfirmed,
          held: {...alreadyHeld, student.uid},
        );
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('보류 저장 실패: $e')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final cohortName = ref.watch(effectiveCohortNameProvider);
    final studentsAsync = ref.watch(cohortStudentsProvider);
    final attendancesAsync = ref.watch(attendancesByDateProvider(_dateKey));
    final confirmedAsync = ref.watch(rollCallConfirmedProvider(_scopeKey));
    final heldAsync = ref.watch(rollCallHeldProvider(_scopeKey));
    final layoutAsync = ref.watch(publishedSeatingLayoutProvider);
    final assignmentAsync = ref.watch(publishedSeatingAssignmentProvider);

    return ColoredBox(
      color: AppColors.background,
      child: studentsAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => ErrorView(message: e.toString()),
        data: (rawStudents) {
          final students = _sortByKoreanName(rawStudents);
          final byUser = <String, AttendanceModel>{};
          for (final a in attendancesAsync.asData?.value ?? const []) {
            byUser[a.userId] = a;
          }
          final confirmed = confirmedAsync.asData?.value ?? const <String>{};
          final held = heldAsync.asData?.value ?? const <String>{};
          final currentUid = _resolvedCurrent(students, confirmed);
          final heldStudents = students
              .where((s) => held.contains(s.uid))
              .toList();
          final assignment = assignmentAsync.asData?.value;

          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Expanded(
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    final layout = layoutAsync.asData?.value;
                    final wide = constraints.maxWidth >= 900;
                    final chart = _SeatingPane(
                      layout: layout,
                      assignment: assignment,
                      assignedNames: {
                        for (final e
                            in ref
                                .watch(seatingAssignedStudentsProvider)
                                .entries)
                          e.key: e.value.displayName,
                      },
                      highlightUserId: currentUid,
                      confirmedUserIds: confirmed,
                      heldUserIds: held,
                      rotate180: _rotateSeating180,
                      onToggleFlip: () => setState(
                        () => _rotateSeating180 = !_rotateSeating180,
                      ),
                    );
                    final roll = _RollCallPane(
                      key: _rollCallScrollKey,
                      students: students,
                      currentUid: currentUid,
                      confirmed: confirmed,
                      held: held,
                      assignment: assignment,
                      onSelect: _selectStudent,
                      onPrev: () => _move(students, currentUid, -1),
                      onNext: () => _move(students, currentUid, 1),
                      onConfirm: (student, value) => _toggleConfirm(
                        student: student,
                        confirmed: value,
                        students: students,
                        alreadyConfirmed: confirmed,
                        held: held,
                      ),
                      onHold: (student, value) => _toggleHold(
                        student: student,
                        held: value,
                        students: students,
                        confirmed: confirmed,
                        alreadyHeld: held,
                      ),
                    );
                    final heldPane = _HeldPane(
                      students: heldStudents,
                      currentUid: currentUid,
                      assignment: assignment,
                      onSelect: _selectStudent,
                      onConfirm: (student) => _toggleConfirm(
                        student: student,
                        confirmed: true,
                        students: students,
                        alreadyConfirmed: confirmed,
                        held: held,
                      ),
                      onClearHold: (student) => _toggleHold(
                        student: student,
                        held: false,
                        students: students,
                        confirmed: confirmed,
                        alreadyHeld: held,
                      ),
                    );

                    final header = _Header(
                      title: widget.title,
                      cohortName: cohortName,
                      dateKey: _dateKey,
                      period: _period,
                      statusHint:
                          ClassPeriodUtils.isSameDay(_day, DateTime.now())
                          ? ClassPeriodUtils.statusHint(DateTime.now())
                          : '',
                      confirmedCount: confirmed.length,
                      heldCount: held.length,
                      total: students.length,
                      onPickDate: _pickDate,
                      onToday: () {
                        setState(() {
                          _day = DateTime.now();
                          _period = ClassPeriodUtils.suggestedPeriod(
                            day: DateTime.now(),
                          );
                          _currentUid = null;
                        });
                        _carryForwardIfNeeded();
                      },
                      onSelectPeriod: _selectPeriod,
                    );

                    if (!wide) {
                      final contentW = math.min(
                        _kAttendanceContentMaxWidth,
                        constraints.maxWidth - 40,
                      );
                      final seatSize = _seatingCardSize(
                        layout: layout,
                        maxWidth: contentW,
                        maxHeight: 440,
                      );
                      return Center(
                        child: SizedBox(
                          width: contentW,
                          child: ListView(
                            padding: EdgeInsets.fromLTRB(AppSpace.s(0), AppSpace.s(8), AppSpace.s(0), AppSpace.s(20)),
                            children: [
                              header,
                              SizedBox(height: AppSpace.s(8)),
                              SizedBox(
                                width: seatSize.width,
                                height: seatSize.height,
                                child: chart,
                              ),
                              SizedBox(height: AppSpace.s(12)),
                              SizedBox(height: 300, child: roll),
                              SizedBox(height: AppSpace.s(12)),
                              SizedBox(height: 160, child: heldPane),
                              SizedBox(height: AppSpace.s(12)),
                              _AttendanceTable(
                                students: students,
                                byUser: byUser,
                                currentUid: currentUid,
                                confirmed: confirmed,
                                held: held,
                              ),
                            ],
                          ),
                        ),
                      );
                    }

                    final contentW = math.min(
                      _kAttendanceContentMaxWidth,
                      constraints.maxWidth - 48,
                    );
                    final sideGap = 12.0;
                    final seatMaxW =
                        contentW - _kRollCallWidth - _kHeldWidth - sideGap * 2;
                    // 출석부는 페이지 스크롤로 펼치므로 좌석에 뷰포트 대부분 할당
                    final seatMaxH = math.max(
                      360.0,
                      constraints.maxHeight - 100,
                    );
                    final seatSize = _seatingCardSize(
                      layout: layout,
                      maxWidth: seatMaxW,
                      maxHeight: seatMaxH,
                    );
                    final sideH = math.max(seatSize.height, 420.0);

                    return Center(
                      child: SingleChildScrollView(
                        padding: EdgeInsets.fromLTRB(AppSpace.s(24), AppSpace.s(8), AppSpace.s(24), AppSpace.s(24)),
                        child: SizedBox(
                          width: contentW,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              header,
                              SizedBox(height: AppSpace.s(8)),
                              Row(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  SizedBox(
                                    width: seatSize.width,
                                    height: seatSize.height,
                                    child: chart,
                                  ),
                                  SizedBox(width: sideGap),
                                  SizedBox(
                                    width: _kRollCallWidth,
                                    height: sideH,
                                    child: roll,
                                  ),
                                  SizedBox(width: sideGap),
                                  SizedBox(
                                    width: _kHeldWidth,
                                    height: sideH,
                                    child: heldPane,
                                  ),
                                ],
                              ),
                              SizedBox(height: AppSpace.s(16)),
                              _AttendanceTable(
                                students: students,
                                byUser: byUser,
                                currentUid: currentUid,
                                confirmed: confirmed,
                                held: held,
                              ),
                            ],
                          ),
                        ),
                      ),
                    );
                  },
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({
    required this.title,
    required this.cohortName,
    required this.dateKey,
    required this.period,
    required this.statusHint,
    required this.confirmedCount,
    required this.heldCount,
    required this.total,
    required this.onPickDate,
    required this.onToday,
    required this.onSelectPeriod,
  });

  final String title;
  final String? cohortName;
  final String dateKey;
  final ClassPeriod period;
  final String statusHint;
  final int confirmedCount;
  final int heldCount;
  final int total;
  final VoidCallback onPickDate;
  final VoidCallback onToday;
  final ValueChanged<ClassPeriod> onSelectPeriod;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(AppSpace.s(4), AppSpace.s(4), AppSpace.s(4), AppSpace.s(12)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.bold,
            ),
          ),
          SizedBox(height: AppSpace.s(4)),
          Text(
            '${cohortName ?? '담당 기수'} · 교시마다 자리에 있는지 확인합니다. '
            '학생 조작은 없고, 확인·보류만 기록됩니다. (출석 상태는 변경되지 않음)',
            style: TextStyle(
              fontSize: 12,
              color: AppColors.textSecondary,
            ),
          ),
          if (statusHint.isNotEmpty) ...[
            SizedBox(height: AppSpace.s(6)),
            Text(
              statusHint,
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: AppColors.primary,
              ),
            ),
          ],
          SizedBox(height: AppSpace.s(12)),
          KeyedSubtree(
            key: OnboardingTargetRegistry.keyOf(
              InstructorOnboardingTargets.attendanceSummary,
            ),
            child: Wrap(
              spacing: 8,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                OutlinedButton.icon(
                  onPressed: onPickDate,
                  icon: const Icon(Icons.calendar_today, size: 16),
                  label: Text(dateKey),
                ),
                TextButton(
                  onPressed: onToday,
                  child: const Text('오늘'),
                ),
                _CountChip(
                  label: '확인 $confirmedCount / $total',
                  color: AppColors.success,
                ),
                _CountChip(
                  label: '보류 $heldCount',
                  color: const Color(0xFFEA580C),
                ),
              ],
            ),
          ),
          SizedBox(height: AppSpace.s(10)),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: [
                for (final p in ClassPeriodUtils.periods) ...[
                  Padding(
                    padding: EdgeInsets.only(right: AppSpace.s(6)),
                    child: ChoiceChip(
                      label: Text(
                        p.label,
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: p.id == period.id
                              ? FontWeight.w700
                              : FontWeight.w500,
                        ),
                      ),
                      selected: p.id == period.id,
                      onSelected: (_) => onSelectPeriod(p),
                      visualDensity: VisualDensity.compact,
                    ),
                  ),
                ],
              ],
            ),
          ),
          SizedBox(height: AppSpace.s(4)),
          Text(
            '선택 교시: ${period.rangeLabel}',
            style: TextStyle(
              fontSize: 11,
              color: AppColors.textSecondary,
            ),
          ),
        ],
      ),
    );
  }
}

class _SeatingPane extends StatelessWidget {
  const _SeatingPane({
    required this.layout,
    required this.assignment,
    required this.assignedNames,
    required this.highlightUserId,
    required this.confirmedUserIds,
    required this.heldUserIds,
    required this.rotate180,
    required this.onToggleFlip,
  });

  final SeatingLayoutModel? layout;
  final SeatingAssignmentModel? assignment;
  final Map<String, String> assignedNames;
  final String? highlightUserId;
  final Set<String> confirmedUserIds;
  final Set<String> heldUserIds;
  final bool rotate180;
  final VoidCallback onToggleFlip;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.border),
      ),
      child: layout == null || assignment == null || !assignment!.isPublished
          ? Center(
              child: Padding(
                padding: EdgeInsets.all(AppSpace.s(20)),
                child: Text(
                  '확정된 좌석 배치가 없습니다.\n관리자가 배치를 확정하면 자리 확인 시 좌석이 표시됩니다.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: AppColors.textSecondary, height: 1.5),
                ),
              ),
            )
          : Padding(
              padding: EdgeInsets.fromLTRB(AppSpace.s(6), AppSpace.s(6), AppSpace.s(6), AppSpace.s(6)),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Padding(
                    padding: EdgeInsets.only(left: AppSpace.s(4), bottom: AppSpace.s(4)),
                    child: Row(
                      children: [
                        const Text(
                          '좌석 배치',
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        const Spacer(),
                        TextButton.icon(
                          onPressed: onToggleFlip,
                          icon: const Icon(Icons.rotate_right, size: 16),
                          label: Text(rotate180 ? '원래 방향' : '180도 회전'),
                        ),
                      ],
                    ),
                  ),
                  Expanded(
                    child: FittedBox(
                      fit: BoxFit.contain,
                      alignment: Alignment.center,
                      child: SeatGrid(
                        layout: layout!,
                        seatUserIds: assignment!.assignments,
                        seatDisplayNames: assignment!.seatNames.isNotEmpty
                            ? assignment!.seatNames
                            : assignedNames,
                        highlightUserId: highlightUserId,
                        highlightCaption: '호명',
                        pulseHighlight: true,
                        confirmedUserIds: confirmedUserIds,
                        heldUserIds: heldUserIds,
                        compact: true,
                        showInstructorHint: false,
                        rotate180: rotate180,
                        editable: false,
                      ),
                    ),
                  ),
                ],
              ),
            ),
    );
  }
}

class _RollCallPane extends StatefulWidget {
  const _RollCallPane({
    super.key,
    required this.students,
    required this.currentUid,
    required this.confirmed,
    required this.held,
    required this.assignment,
    required this.onSelect,
    required this.onPrev,
    required this.onNext,
    required this.onConfirm,
    required this.onHold,
  });

  static const itemHeight = 40.0;

  final List<UserModel> students;
  final String? currentUid;
  final Set<String> confirmed;
  final Set<String> held;
  final SeatingAssignmentModel? assignment;
  final ValueChanged<String> onSelect;
  final VoidCallback onPrev;
  final VoidCallback onNext;
  final Future<void> Function(UserModel student, bool confirmed) onConfirm;
  final Future<void> Function(UserModel student, bool held) onHold;

  @override
  State<_RollCallPane> createState() => _RollCallPaneState();
}

class _RollCallPaneState extends State<_RollCallPane> {
  final _scrollController = ScrollController();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      scrollToUid(widget.currentUid);
    });
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant _RollCallPane oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.currentUid != oldWidget.currentUid) {
      scrollToUid(widget.currentUid);
    }
  }

  void scrollToUid(String? uid) {
    if (uid == null) return;
    final index = widget.students.indexWhere((s) => s.uid == uid);
    if (index < 0) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;
      final itemH = _RollCallPane.itemHeight;
      final offset = index * itemH;
      final viewport = _scrollController.position.viewportDimension;
      final maxScroll = _scrollController.position.maxScrollExtent;
      final target = (offset - viewport / 2 + itemH / 2).clamp(0.0, maxScroll);
      _scrollController.animateTo(
        target,
        duration: const Duration(milliseconds: 220),
        curve: Curves.easeOut,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final current = widget.students
        .where((s) => s.uid == widget.currentUid)
        .firstOrNull;
    final currentConfirmed =
        current != null && widget.confirmed.contains(current.uid);
    final currentHeld = current != null && widget.held.contains(current.uid);

    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(AppSpace.s(12), AppSpace.s(10), AppSpace.s(12), AppSpace.s(4)),
            child: Text(
              current == null
                  ? '호명할 학생이 없습니다'
                  : '${current.displayName}'
                        '${_seatLabel(current.uid, widget.assignment)}',
              style: const TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          Padding(
            padding: EdgeInsets.fromLTRB(AppSpace.s(8), AppSpace.s(0), AppSpace.s(8), AppSpace.s(8)),
            child: Row(
              children: [
                IconButton(
                  visualDensity: VisualDensity.compact,
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(
                    minWidth: 28,
                    minHeight: 32,
                  ),
                  onPressed: widget.students.isEmpty ? null : widget.onPrev,
                  icon: const Icon(Icons.chevron_left),
                ),
                Expanded(
                  child: KeyedSubtree(
                    key: OnboardingTargetRegistry.keyOf(
                      InstructorOnboardingTargets.attendanceConfirm,
                    ),
                    child: FilledButton(
                      style: FilledButton.styleFrom(
                        minimumSize: const Size(0, 34),
                        padding: EdgeInsets.symmetric(horizontal: AppSpace.s(8)),
                      ),
                      onPressed: current == null
                          ? null
                          : () => widget.onConfirm(current, !currentConfirmed),
                      child: Text(currentConfirmed ? '확인 취소' : '확인'),
                    ),
                  ),
                ),
                SizedBox(width: AppSpace.s(6)),
                Expanded(
                  child: OutlinedButton(
                    style: OutlinedButton.styleFrom(
                      minimumSize: const Size(0, 34),
                      padding: EdgeInsets.symmetric(horizontal: AppSpace.s(8)),
                      foregroundColor: const Color(0xFFC2410C),
                      side: const BorderSide(color: Color(0xFFFDBA74)),
                    ),
                    onPressed: current == null
                        ? null
                        : () => widget.onHold(current, !currentHeld),
                    child: Text(currentHeld ? '보류 취소' : '보류'),
                  ),
                ),
                IconButton(
                  visualDensity: VisualDensity.compact,
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(
                    minWidth: 28,
                    minHeight: 32,
                  ),
                  onPressed: widget.students.isEmpty ? null : widget.onNext,
                  icon: const Icon(Icons.chevron_right),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: widget.students.isEmpty
                ? Center(
                    child: Text(
                      '이 기수에 재원 학생이 없습니다.',
                      style: TextStyle(color: AppColors.textSecondary),
                    ),
                  )
                : ListView.builder(
                    controller: _scrollController,
                    itemExtent: _RollCallPane.itemHeight,
                    itemCount: widget.students.length,
                    itemBuilder: (_, i) {
                      final student = widget.students[i];
                      final selected = student.uid == widget.currentUid;
                      final done = widget.confirmed.contains(student.uid);
                      final isHeld = widget.held.contains(student.uid);
                      final seatId = widget.assignment?.seatIdForUser(
                        student.uid,
                      );
                      return Material(
                        color: selected
                            ? AppColors.tint(const Color(0xFFFFFBEB))
                            : Colors.transparent,
                        child: InkWell(
                          onTap: () => widget.onSelect(student.uid),
                          child: Padding(
                            padding: EdgeInsets.symmetric(horizontal: AppSpace.s(10)),
                            child: Row(
                              children: [
                                Container(
                                  width: 22,
                                  height: 22,
                                  alignment: Alignment.center,
                                  decoration: BoxDecoration(
                                    color: done
                                        ? AppColors.tint(
                                            const Color(0xFFDCFCE7),
                                          )
                                        : isHeld
                                        ? AppColors.tint(
                                            const Color(0xFFFFEDD5),
                                          )
                                        : selected
                                        ? AppColors.tint(
                                            const Color(0xFFFEF3C7),
                                          )
                                        : AppColors.surfaceVariant,
                                    shape: BoxShape.circle,
                                  ),
                                  child: Text(
                                    '${i + 1}',
                                    style: TextStyle(
                                      fontSize: 10,
                                      fontWeight: FontWeight.w700,
                                      color: done
                                          ? const Color(0xFF15803D)
                                          : isHeld
                                          ? const Color(0xFFC2410C)
                                          : AppColors.textPrimary,
                                    ),
                                  ),
                                ),
                                SizedBox(width: AppSpace.s(8)),
                                Expanded(
                                  child: Column(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        student.displayName,
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                        style: const TextStyle(
                                          fontSize: 13,
                                          fontWeight: FontWeight.w600,
                                        ),
                                      ),
                                      Text(
                                        seatId == null ? '좌석 없음' : '$seatId번',
                                        style: TextStyle(
                                          fontSize: 10,
                                          color: AppColors.textSecondary,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                                if (done)
                                  const Icon(
                                    Icons.check_circle,
                                    color: Color(0xFF16A34A),
                                    size: 16,
                                  )
                                else if (isHeld)
                                  const Icon(
                                    Icons.pause_circle_filled,
                                    color: Color(0xFFEA580C),
                                    size: 16,
                                  ),
                              ],
                            ),
                          ),
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }

  String _seatLabel(String uid, SeatingAssignmentModel? assignment) {
    final seatId = assignment?.seatIdForUser(uid);
    if (seatId == null) return ' · 좌석 없음';
    return ' · $seatId번';
  }
}

class _HeldPane extends StatelessWidget {
  const _HeldPane({
    required this.students,
    required this.currentUid,
    required this.assignment,
    required this.onSelect,
    required this.onConfirm,
    required this.onClearHold,
  });

  final List<UserModel> students;
  final String? currentUid;
  final SeatingAssignmentModel? assignment;
  final ValueChanged<String> onSelect;
  final Future<void> Function(UserModel student) onConfirm;
  final Future<void> Function(UserModel student) onClearHold;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: const Color(0xFFFDBA74)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(AppSpace.s(12), AppSpace.s(10), AppSpace.s(12), AppSpace.s(8)),
            child: Row(
              children: [
                const Text(
                  '보류',
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFFC2410C),
                  ),
                ),
                SizedBox(width: AppSpace.s(6)),
                Text(
                  '${students.length}명',
                  style: TextStyle(
                    fontSize: 12,
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: students.isEmpty
                ? Center(
                    child: Text(
                      '보류된 학생이 없습니다.',
                      style: TextStyle(
                        fontSize: 12,
                        color: AppColors.textSecondary,
                      ),
                    ),
                  )
                : ListView.builder(
                    itemCount: students.length,
                    itemBuilder: (_, i) {
                      final student = students[i];
                      final selected = student.uid == currentUid;
                      final seatId = assignment?.seatIdForUser(student.uid);
                      return Material(
                        color: selected
                            ? AppColors.tint(const Color(0xFFFFF7ED))
                            : Colors.transparent,
                        child: InkWell(
                          onTap: () => onSelect(student.uid),
                          child: Padding(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpace.s(8),
                              vertical: AppSpace.s(6),
                            ),
                            child: Row(
                              children: [
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        student.displayName,
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                        style: const TextStyle(
                                          fontSize: 13,
                                          fontWeight: FontWeight.w600,
                                        ),
                                      ),
                                      Text(
                                        seatId == null ? '좌석 없음' : '$seatId번',
                                        style: TextStyle(
                                          fontSize: 10,
                                          color: AppColors.textSecondary,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                                TextButton(
                                  style: TextButton.styleFrom(
                                    visualDensity: VisualDensity.compact,
                                    padding: EdgeInsets.symmetric(
                                      horizontal: AppSpace.s(4),
                                    ),
                                    foregroundColor: AppColors.success,
                                  ),
                                  onPressed: () => onConfirm(student),
                                  child: const Text(
                                    '확인',
                                    style: TextStyle(fontSize: 12),
                                  ),
                                ),
                                TextButton(
                                  style: TextButton.styleFrom(
                                    visualDensity: VisualDensity.compact,
                                    padding: EdgeInsets.symmetric(
                                      horizontal: AppSpace.s(4),
                                    ),
                                    foregroundColor: const Color(0xFFC2410C),
                                  ),
                                  onPressed: () => onClearHold(student),
                                  child: const Text(
                                    '해제',
                                    style: TextStyle(fontSize: 12),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}

class _AttendanceTable extends StatelessWidget {
  const _AttendanceTable({
    required this.students,
    required this.byUser,
    required this.currentUid,
    required this.confirmed,
    required this.held,
  });

  final List<UserModel> students;
  final Map<String, AttendanceModel> byUser;
  final String? currentUid;
  final Set<String> confirmed;
  final Set<String> held;

  static const _rowH = 32.0;

  String _rollLabel(String uid) {
    if (confirmed.contains(uid)) return '확인';
    if (held.contains(uid)) return '보류';
    return '-';
  }

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(AppSpace.s(12), AppSpace.s(10), AppSpace.s(12), AppSpace.s(8)),
            child: Row(
              children: [
                Text(
                  '당일 출석부',
                  style: TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
                ),
                SizedBox(width: AppSpace.s(8)),
                Expanded(
                  child: Text(
                    '조회 전용 · 입퇴실·예외는 관리자 출석부와 동일',
                    style: TextStyle(
                      fontSize: 11,
                      color: AppColors.textSecondary,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          _headerRow(),
          const Divider(height: 1),
          if (students.isEmpty)
            Padding(
              padding: EdgeInsets.symmetric(vertical: AppSpace.s(24)),
              child: Center(
                child: Text(
                  '학생이 없습니다.',
                  style: TextStyle(color: AppColors.textSecondary),
                ),
              ),
            )
          else
            for (final student in students)
              ColoredBox(
                color: student.uid == currentUid
                    ? AppColors.tint(const Color(0xFFFFFBEB))
                    : Colors.transparent,
                child: SizedBox(
                  height: _rowH,
                  child: _dataRow(
                    name: student.displayName,
                    roll: _rollLabel(student.uid),
                    checkIn: byUser[student.uid]?.checkInTime ?? '-',
                    checkOut: byUser[student.uid]?.checkOutTime ?? '-',
                    status: AttendanceStatus.labelOf(
                      byUser[student.uid]?.dayStatus,
                    ),
                    source: byUser[student.uid]?.sourceLabel ?? '-',
                  ),
                ),
              ),
        ],
      ),
    );
  }

  Widget _headerRow() {
    return ColoredBox(
      color: AppColors.surfaceVariant,
      child: SizedBox(
        height: _rowH,
        child: _dataRow(
          name: '이름',
          roll: '호명',
          checkIn: '입실',
          checkOut: '퇴실',
          status: '최종 상태',
          source: '출처',
          isHeader: true,
        ),
      ),
    );
  }

  Widget _dataRow({
    required String name,
    required String roll,
    required String checkIn,
    required String checkOut,
    required String status,
    required String source,
    bool isHeader = false,
  }) {
    final style = TextStyle(
      fontSize: 12,
      fontWeight: isHeader ? FontWeight.w600 : FontWeight.w400,
      color: isHeader ? AppColors.textSecondary : AppColors.textPrimary,
    );
    Widget cell(String text, {int flex = 1}) {
      return Expanded(
        flex: flex,
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: AppSpace.s(8)),
          child: Text(
            text,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: style,
          ),
        ),
      );
    }

    return Row(
      children: [
        cell(name, flex: 3),
        cell(roll, flex: 2),
        cell(checkIn, flex: 2),
        cell(checkOut, flex: 2),
        cell(status, flex: 3),
        cell(source, flex: 2),
      ],
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
