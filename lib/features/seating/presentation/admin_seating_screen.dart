import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_layout.dart';
import '../../../core/widgets/app_dropdown.dart';
import '../../../core/widgets/filter_pill.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/models/user_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../auth/providers/auth_providers.dart';
import '../data/seating_repository.dart';
import '../models/seat_drag_payload.dart';
import '../models/project_team_model.dart';
import '../models/seating_assignment_model.dart';
import '../models/seating_layout_model.dart';
import '../models/seating_room_model.dart';
import '../providers/seating_providers.dart';
import 'widgets/layout_editor_grid.dart';
import 'widgets/project_teams_panel.dart';
import 'widgets/seat_grid.dart';
import 'widgets/unassigned_student_list.dart';
import '../utils/team_seating_assigner.dart';
import '../../../core/theme/app_space.dart';

/// 관리자 — 좌석 틀 설정(강의실 생성) + 배치 편집(학생 배치)
class AdminSeatingScreen extends ConsumerStatefulWidget {
  const AdminSeatingScreen({super.key});

  @override
  ConsumerState<AdminSeatingScreen> createState() => _AdminSeatingScreenState();
}

class _AdminSeatingScreenState extends ConsumerState<AdminSeatingScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;

  // ── 틀 설정 탭 ──
  String? _layoutRoomId;
  SeatingLayoutModel? _draftLayout;
  bool _layoutDraftDirty = false;
  final _roomNumberController = TextEditingController();
  int _nextGroupCounter = 1;

  // ── 배치 편집 탭 ──
  String? _assignmentRoomId;
  String? _assignmentSyncedRoomId;
  Map<String, String> _draftAssignments = {};
  bool _assignmentDraftDirty = false;
  SeatingLayoutModel? _assignmentLayout;

  bool _isSaving = false;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this)
      ..addListener(() {
        if (!_tabController.indexIsChanging) setState(() {});
      });
  }

  @override
  void dispose() {
    _tabController.dispose();
    _roomNumberController.dispose();
    super.dispose();
  }

  void _syncGroupCounter() {
    var max = 0;
    for (final c in _draftLayout?.cells ?? []) {
      final gid = c.groupId;
      if (gid != null && gid.startsWith('desk-')) {
        final n = int.tryParse(gid.substring(5)) ?? 0;
        if (n > max) max = n;
      }
    }
    _nextGroupCounter = max + 1;
  }

  String _newGroupId() => 'desk-${_nextGroupCounter++}';

  void _selectLayoutRoom(SeatingRoomModel? room) {
    setState(() {
      _layoutRoomId = room?.id;
      _draftLayout = room?.layout ?? SeatingLayoutModel.defaultGrid();
      _layoutDraftDirty = false;
      _roomNumberController.text = _draftLayout?.roomNumber ?? '';
      _syncGroupCounter();
    });
  }

  void _selectAssignmentRoom(String? roomId, SeatingRoomModel? room) {
    setState(() {
      _assignmentRoomId = roomId;
      _assignmentLayout = room?.layout;
      _draftAssignments = {};
      _assignmentDraftDirty = false;
      _assignmentSyncedRoomId = null;
    });
  }

  void _syncAssignmentFromProvider(
    String roomId,
    SeatingAssignmentModel? assignment,
  ) {
    if (_assignmentDraftDirty) return;
    final nextAssignments = Map<String, String>.from(
      assignment?.assignments ?? const {},
    );
    if (_assignmentSyncedRoomId == roomId &&
        mapEquals(_draftAssignments, nextAssignments)) {
      return;
    }
    _assignmentSyncedRoomId = roomId;
    setState(() {
      _draftAssignments = nextAssignments;
    });
  }

  void _updateRoomNumber(String value) {
    final layout = _draftLayout;
    if (layout == null) return;
    setState(() {
      _draftLayout = layout.copyWith(
        roomNumber: value.trim().isEmpty ? null : value.trim(),
      );
      _layoutDraftDirty = true;
    });
  }

  void _onLayoutChanged(SeatingLayoutModel newLayout) {
    setState(() {
      _draftLayout = newLayout;
      _layoutDraftDirty = true;
    });
  }

  Map<String, String> _buildSeatNames(List<UserModel> students) {
    final byId = {for (final s in students) s.uid: s.displayName};
    return {
      for (final e in _draftAssignments.entries)
        if (byId[e.value] != null) e.key: byId[e.value]!,
    };
  }

  List<UserModel> _unassignedStudents(List<UserModel> students) {
    final assigned = _draftAssignments.values.toSet();
    return students.where((s) => !assigned.contains(s.uid)).toList();
  }

  Set<String> _inactiveSeatIds(List<UserModel> students) {
    final activeUids = students.map((s) => s.uid).toSet();
    return _draftAssignments.entries
        .where((e) => !activeUids.contains(e.value))
        .map((e) => e.key)
        .toSet();
  }

  Map<String, String> _seatDisplayNames(List<UserModel> students) {
    final byId = {for (final s in students) s.uid: s.displayName};
    final names = <String, String>{};
    for (final e in _draftAssignments.entries) {
      final name = byId[e.value];
      if (name != null) names[e.key] = name;
    }
    return names;
  }

  Map<String, String> _remapAssignments(
    SeatingLayoutModel oldLayout,
    SeatingLayoutModel newLayout,
    Map<String, String> assignments,
  ) {
    final byPos = <String, String>{};
    for (final c in oldLayout.seatCells) {
      final uid = assignments[c.seatId];
      if (uid != null) byPos['${c.row},${c.col}'] = uid;
    }
    final next = <String, String>{};
    for (final c in newLayout.seatCells) {
      final uid = byPos['${c.row},${c.col}'];
      if (uid != null) next[c.seatId] = uid;
    }
    return next;
  }

  Future<String?> _promptNewRoomName(List<SeatingRoomModel> rooms) async {
    final suggested = _suggestRoomName(rooms);
    final controller = TextEditingController(text: suggested);
    final name = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('새 강의실'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(
            labelText: '표시 이름',
            hintText: '예: 401호, 강의실 1',
            border: OutlineInputBorder(),
          ),
          onSubmitted: (v) {
            final trimmed = v.trim();
            if (trimmed.isNotEmpty) Navigator.pop(ctx, trimmed);
          },
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('취소'),
          ),
          FilledButton(
            onPressed: () {
              final trimmed = controller.text.trim();
              if (trimmed.isEmpty) return;
              Navigator.pop(ctx, trimmed);
            },
            child: const Text('만들기'),
          ),
        ],
      ),
    );
    controller.dispose();
    return name;
  }

  String _suggestRoomName(List<SeatingRoomModel> rooms) {
    var max = rooms.length;
    final re = RegExp(r'강의실\s*(\d+)');
    for (final room in rooms) {
      final match = re.firstMatch(room.displayLabel);
      if (match == null) continue;
      final n = int.tryParse(match.group(1)!) ?? 0;
      if (n > max) max = n;
    }
    return '강의실 ${max + 1}';
  }

  Future<void> _createRoom(List<SeatingRoomModel> rooms) async {
    final cohortId = ref.read(effectiveCohortIdProvider);
    final uid = ref.read(currentUserProvider).asData?.value?.uid;
    if (cohortId == null || uid == null) return;

    final name = await _promptNewRoomName(rooms);
    if (name == null || !mounted) return;

    setState(() => _isSaving = true);
    try {
      final layout = SeatingLayoutModel.defaultGrid().copyWith(
        roomNumber: name,
      );
      final roomId = await ref
          .read(seatingRepositoryProvider)
          .createRoom(
            cohortId: cohortId,
            layout: layout,
            updatedBy: uid,
          );
      if (mounted) {
        _selectLayoutRoom(SeatingRoomModel(id: roomId, layout: layout));
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('"$name" 강의실이 생성되었습니다.')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('생성 실패: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _isSaving = false);
    }
  }

  Future<void> _deleteLayoutRoom() async {
    final roomId = _layoutRoomId;
    final cohortId = ref.read(effectiveCohortIdProvider);
    if (roomId == null || cohortId == null) return;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('강의실 삭제'),
        content: const Text('이 강의실과 저장된 배치 데이터가 모두 삭제됩니다. 계속할까요?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('취소'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('삭제'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _isSaving = true);
    try {
      await ref
          .read(seatingRepositoryProvider)
          .deleteRoom(
            cohortId: cohortId,
            roomId: roomId,
          );
      if (mounted) {
        _selectLayoutRoom(null);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('강의실이 삭제되었습니다.')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('삭제 실패: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _isSaving = false);
    }
  }

  Future<void> _saveLayout() async {
    final cohortId = ref.read(effectiveCohortIdProvider);
    final uid = ref.read(currentUserProvider).asData?.value?.uid;
    final layout = _draftLayout;
    if (cohortId == null || uid == null || layout == null) return;

    setState(() => _isSaving = true);
    try {
      final repo = ref.read(seatingRepositoryProvider);
      String roomId = _layoutRoomId ?? '';

      if (roomId.isEmpty) {
        roomId = await repo.createRoom(
          cohortId: cohortId,
          layout: layout,
          updatedBy: uid,
        );
      } else {
        final oldRoom = ref.read(seatingRoomProvider(roomId)).asData?.value;
        await repo.saveRoom(
          cohortId: cohortId,
          roomId: roomId,
          layout: layout,
          updatedBy: uid,
        );

        final assignment = ref
            .read(seatingRoomAssignmentProvider(roomId))
            .asData
            ?.value;
        if (assignment != null &&
            oldRoom != null &&
            assignment.assignments.isNotEmpty) {
          final remapped = _remapAssignments(
            oldRoom.layout,
            layout,
            assignment.assignments,
          );
          await repo.saveAssignment(
            cohortId: cohortId,
            roomId: roomId,
            assignment: SeatingAssignmentModel(
              status: assignment.status,
              assignments: remapped,
              seatNames: {
                for (final e in remapped.entries)
                  if (assignment.seatNames.containsKey(e.key))
                    e.key: assignment.seatNames[e.key]!,
              },
            ),
            updatedBy: uid,
          );
        }
      }

      if (mounted) {
        setState(() {
          _layoutRoomId = roomId;
          _layoutDraftDirty = false;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('강의실 틀이 저장되었습니다.')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('저장 실패: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _isSaving = false);
    }
  }

  Future<void> _saveAssignments({bool publish = false}) async {
    final cohortId = ref.read(effectiveCohortIdProvider);
    final uid = ref.read(currentUserProvider).asData?.value?.uid;
    final roomId = _assignmentRoomId;
    if (cohortId == null || uid == null || roomId == null) return;

    final students = ref.read(cohortStudentsProvider).asData?.value ?? [];
    final assignedCount = _draftAssignments.values.toSet().length;
    if (assignedCount > students.length) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('배정 인원이 재원 학생 수를 초과할 수 없습니다.')),
      );
      return;
    }

    setState(() => _isSaving = true);
    try {
      final repo = ref.read(seatingRepositoryProvider);
      final seatNames = _buildSeatNames(students);
      if (publish) {
        await repo.publishAssignment(
          cohortId: cohortId,
          roomId: roomId,
          assignments: _draftAssignments,
          seatNames: seatNames,
          publishedBy: uid,
        );
      } else {
        await repo.saveAssignment(
          cohortId: cohortId,
          roomId: roomId,
          assignment: SeatingAssignmentModel(
            status: SeatingAssignmentStatus.draft,
            assignments: _draftAssignments,
            seatNames: seatNames,
          ),
          updatedBy: uid,
        );
      }
      if (mounted) {
        setState(() => _assignmentDraftDirty = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(publish ? '좌석 배치가 확정되었습니다.' : '배치가 저장되었습니다.'),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('저장 실패: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _isSaving = false);
    }
  }

  void _assignStudent(String seatId, SeatDragPayload payload) {
    setState(() {
      _assignmentDraftDirty = true;
      _draftAssignments.removeWhere((_, uid) => uid == payload.userId);
      if (payload.fromSeatId != null) {
        _draftAssignments.remove(payload.fromSeatId);
      }
      _draftAssignments[seatId] = payload.userId;
    });
  }

  void _swapSeats(String fromSeatId, String toSeatId) {
    setState(() {
      _assignmentDraftDirty = true;
      final fromUser = _draftAssignments[fromSeatId];
      final toUser = _draftAssignments[toSeatId];
      if (fromUser == null) return;
      if (toUser != null) {
        _draftAssignments[fromSeatId] = toUser;
        _draftAssignments[toSeatId] = fromUser;
      } else {
        _draftAssignments.remove(fromSeatId);
        _draftAssignments[toSeatId] = fromUser;
      }
    });
  }

  void _unassignFromSeat(SeatDragPayload payload) {
    if (payload.fromSeatId == null) return;
    setState(() {
      _assignmentDraftDirty = true;
      _draftAssignments.remove(payload.fromSeatId);
    });
  }

  void _randomAssign() {
    final layout = _assignmentLayout;
    if (layout == null) return;

    final emptySeats = layout.seatCells
        .where((c) => !_draftAssignments.containsKey(c.seatId))
        .map((c) => c.seatId)
        .toList();
    final unassigned = _unassignedStudents(
      ref.read(cohortStudentsProvider).asData?.value ?? [],
    );
    if (emptySeats.isEmpty || unassigned.isEmpty) return;

    emptySeats.shuffle(Random());
    setState(() {
      _assignmentDraftDirty = true;
      for (var i = 0; i < unassigned.length && i < emptySeats.length; i++) {
        _draftAssignments[emptySeats[i]] = unassigned[i].uid;
      }
    });
  }

  Future<void> _assignByTeams() async {
    final layout = _assignmentLayout;
    if (layout == null) return;

    // autoDispose + TabBarView로 스트림이 끊긴 경우 로딩을 빈 목록으로
    // 오인하지 않도록 future까지 기다린다.
    final List<ProjectTeamModel> teams;
    try {
      teams = await ref.read(projectTeamsProvider.future);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('프로젝트 팀을 불러오지 못했습니다: $e')),
      );
      return;
    }

    final withMembers = teams.where((t) => t.memberIds.isNotEmpty).toList();
    if (withMembers.isEmpty) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            teams.isEmpty
                ? '구성된 프로젝트 팀이 없습니다. 「프로젝트 팀」 탭에서 먼저 만들어 주세요.'
                : '멤버가 있는 팀이 없습니다. 「프로젝트 팀」 탭에서 학생을 배정하세요.',
          ),
        ),
      );
      return;
    }

    final mapped = TeamSeatingAssigner.assign(
      layout: layout,
      teams: withMembers,
    );
    setState(() {
      _assignmentDraftDirty = true;
      _draftAssignments = mapped;
    });
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('${withMembers.length}개 팀을 인접 좌석에 배치했습니다. 확인 후 저장하세요.'),
      ),
    );
  }

  void _clearAssignments() {
    setState(() {
      _assignmentDraftDirty = true;
      _draftAssignments.clear();
    });
  }

  /// seatId → 프로젝트 팀 soft 색 (팀끼리 뭉침 확인용)
  Map<String, Color> _seatTeamTints(List<ProjectTeamModel> teams) {
    final userTint = <String, Color>{};
    for (final team in teams) {
      if (team.memberIds.isEmpty) continue;
      final soft = ProjectTeamColors.softOf(team.colorIndex);
      for (final uid in team.memberIds) {
        userTint[uid] = soft;
      }
    }
    if (userTint.isEmpty) return const {};

    final result = <String, Color>{};
    for (final e in _draftAssignments.entries) {
      final tint = userTint[e.value];
      if (tint != null) result[e.key] = tint;
    }
    return result;
  }

  @override
  Widget build(BuildContext context) {
    // 배치 편집 탭에서도 팀 스트림을 유지 (팀끼리 앉히기용)
    ref.watch(projectTeamsProvider);
    final roomsAsync = ref.watch(seatingRoomsProvider);
    final cohortName = ref.watch(effectiveCohortNameProvider);
    final studentsAsync = ref.watch(cohortStudentsProvider);

    final rooms = roomsAsync.asData?.value ?? [];
    final students = _deduplicateStudents(studentsAsync.asData?.value ?? []);

    // 틀 설정 탭: 첫 강의실 자동 선택
    if (_layoutRoomId == null && rooms.isNotEmpty && !_layoutDraftDirty) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _layoutRoomId == null) {
          _selectLayoutRoom(rooms.first);
        }
      });
    }

    // 배치 편집: 첫 강의실 자동 선택
    if (_assignmentRoomId == null && rooms.isNotEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _assignmentRoomId == null) {
          _selectAssignmentRoom(rooms.first.id, rooms.first);
        }
      });
    }

    // 배치 편집: 선택 강의실 layout/assignment 동기화
    if (_assignmentRoomId != null) {
      final room = ref
          .watch(seatingRoomProvider(_assignmentRoomId!))
          .asData
          ?.value;
      final assignmentAsync = ref.watch(
        seatingRoomAssignmentProvider(_assignmentRoomId!),
      );
      final assignment = assignmentAsync.asData?.value;
      if (room != null && _assignmentLayout?.cells != room.layout.cells) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted && _assignmentRoomId == room.id) {
            setState(() => _assignmentLayout = room.layout);
          }
        });
      }
      if (assignmentAsync.hasValue) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted && _assignmentRoomId != null) {
            _syncAssignmentFromProvider(_assignmentRoomId!, assignment);
          }
        });
      }
    }

    final appBarRoom = switch (_tabController.index) {
      0 => _draftLayout?.roomNumber,
      2 => _assignmentLayout?.roomNumber,
      _ => null,
    };

    return Scaffold(
      body: Column(
        children: [
          FilterPillHeader(
            title: _appBarTitle(cohortName, appBarRoom),
            pills: [
              FilterPill(
                label: '좌석 틀 설정',
                selected: _tabController.index == 0,
                onTap: () => _tabController.animateTo(0),
              ),
              FilterPill(
                label: '프로젝트 팀',
                selected: _tabController.index == 1,
                onTap: () => _tabController.animateTo(1),
              ),
              FilterPill(
                label: '배치 편집',
                selected: _tabController.index == 2,
                onTap: () => _tabController.animateTo(2),
              ),
            ],
          ),
          Expanded(
            child: roomsAsync.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => ErrorView(
                message: e.toString(),
                onRetry: () => ref.invalidate(seatingRoomsProvider),
              ),
              data: (_) => TabBarView(
                controller: _tabController,
                children: [
                  _buildLayoutTab(rooms),
                  ProjectTeamsPanel(students: students),
                  _buildAssignmentTab(
                    rooms,
                    students,
                    studentsAsync.isLoading,
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  List<UserModel> _deduplicateStudents(List<UserModel> students) {
    final byName = <String, UserModel>{};
    for (final student in students) {
      final key = student.displayName.trim();
      final existing = byName[key];
      if (existing == null) {
        byName[key] = student;
        continue;
      }
      final existingCreated = existing.createdAt;
      final candidateCreated = student.createdAt;
      if (existingCreated == null ||
          (candidateCreated != null && candidateCreated.isBefore(existingCreated))) {
        byName[key] = student;
      }
    }
    return byName.values.toList(growable: false);
  }

  String _appBarTitle(String? cohortName, String? roomNumber) {
    final parts = <String>['좌석 배치'];
    if (cohortName != null) parts.add(cohortName);
    final room = roomNumber?.trim();
    if (room != null && room.isNotEmpty) parts.add(room);
    return parts.join(' · ');
  }

  Widget _buildRoomSelector({
    required List<SeatingRoomModel> rooms,
    required String? selectedId,
    required ValueChanged<SeatingRoomModel?> onChanged,
    required String hint,
    double? width,
  }) {
    final field = AppDropdownField<String>(
      value: selectedId != null && rooms.any((r) => r.id == selectedId)
          ? selectedId
          : null,
      isDense: true,
      decoration: InputDecoration(
        labelText: hint,
        isDense: true,
        contentPadding: EdgeInsets.symmetric(
          horizontal: AppSpace.s(12),
          vertical: AppSpace.s(10),
        ),
      ),
      items: [
        for (final room in rooms)
          AppDropdownItem(
            value: room.id,
            label: '${room.displayLabel} (${room.seatCount}석)',
          ),
      ],
      onChanged: (id) {
        if (id == null) return;
        onChanged(rooms.firstWhere((r) => r.id == id));
      },
    );
    if (width == null) return field;
    return SizedBox(width: width, child: field);
  }

  Widget _buildLayoutToolbar(List<SeatingRoomModel> rooms) {
    if (rooms.isEmpty) {
      return Container(
        padding: EdgeInsets.symmetric(horizontal: AppSpace.s(14), vertical: AppSpace.s(12)),
        decoration: BoxDecoration(
          color: AppColors.surfaceVariant,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: AppColors.border),
        ),
        child: Row(
          children: [
            Icon(
              Icons.meeting_room_outlined,
              size: 20,
              color: AppColors.textSecondary,
            ),
            SizedBox(width: AppSpace.s(10)),
            Expanded(
              child: Text(
                '아직 강의실이 없습니다. 먼저 만들어 주세요.',
                style: TextStyle(fontSize: 13, color: AppColors.textSecondary),
              ),
            ),
            FilledButton.icon(
              onPressed: _isSaving ? null : () => _createRoom(rooms),
              icon: const Icon(Icons.add, size: 18),
              label: const Text('새 강의실'),
            ),
          ],
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Expanded(
              child: _buildRoomSelector(
                rooms: rooms,
                selectedId: _layoutRoomId,
                hint: '편집할 강의실',
                onChanged: _selectLayoutRoom,
              ),
            ),
            SizedBox(width: AppSpace.s(8)),
            FilledButton.tonalIcon(
              onPressed: _isSaving ? null : () => _createRoom(rooms),
              icon: const Icon(Icons.add, size: 18),
              label: const Text('새 강의실'),
            ),
          ],
        ),
        if (_layoutRoomId != null) ...[
          SizedBox(height: AppSpace.s(10)),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: TextField(
                  controller: _roomNumberController,
                  decoration: InputDecoration(
                    labelText: '표시 이름',
                    hintText: '예: 401호',
                    helperText: '드롭다운·상단에 보이는 이름입니다',
                    border: OutlineInputBorder(),
                    isDense: true,
                    contentPadding: EdgeInsets.symmetric(
                      horizontal: AppSpace.s(12),
                      vertical: AppSpace.s(10),
                    ),
                  ),
                  onChanged: _updateRoomNumber,
                ),
              ),
              SizedBox(width: AppSpace.s(8)),
              IconButton(
                onPressed: _isSaving ? null : _deleteLayoutRoom,
                icon: const Icon(Icons.delete_outline),
                tooltip: '이 강의실 삭제',
                color: AppColors.error,
              ),
              SizedBox(width: AppSpace.s(4)),
              if (_isSaving)
                Padding(
                  padding: EdgeInsets.symmetric(horizontal: AppSpace.s(12), vertical: AppSpace.s(10)),
                  child: SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                )
              else
                FilledButton.icon(
                  onPressed: _saveLayout,
                  style: FilledButton.styleFrom(
                    visualDensity: VisualDensity.compact,
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpace.s(14),
                      vertical: AppSpace.s(10),
                    ),
                    textStyle: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  icon: const Icon(Icons.save_outlined, size: 18),
                  label: const Text('틀 저장'),
                ),
            ],
          ),
        ],
      ],
    );
  }

  Widget _buildLayoutTab(List<SeatingRoomModel> rooms) {
    final draft = _draftLayout ?? SeatingLayoutModel.defaultGrid();
    final hasRoom = rooms.isNotEmpty && _layoutRoomId != null;

    return SingleChildScrollView(
      padding: EdgeInsets.all(AppSpace.s(16)),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: AppLayout.seating),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                '위에서 편집할 강의실을 고른 뒤, 8×10 그리드에 강사석·출입문·테이블을 배치하세요. 학생 배치는 「배치 편집」에서 합니다.',
                style: TextStyle(color: AppColors.textSecondary, fontSize: 13),
              ),
              SizedBox(height: AppSpace.s(12)),
              _buildLayoutToolbar(rooms),
              if (hasRoom) ...[
                SizedBox(height: AppSpace.s(10)),
                Text(
                  '좌석 ${draft.seatCount}석 · 재원 학생 최대 $kMaxCohortStudents명'
                  '${_layoutDraftDirty ? ' · 저장되지 않은 변경' : ''}',
                  style: TextStyle(
                    fontSize: 12,
                    color: _layoutDraftDirty
                        ? AppColors.warning
                        : AppColors.textSecondary,
                  ),
                ),
                SizedBox(height: AppSpace.s(16)),
                LayoutEditorGrid(
                  layout: draft,
                  onLayoutChanged: _onLayoutChanged,
                  newGroupId: _newGroupId,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildAssignmentTab(
    List<SeatingRoomModel> rooms,
    List<UserModel> students,
    bool studentsLoading,
  ) {
    if (studentsLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (rooms.isEmpty) {
      return const Center(
        child: Text('먼저 "좌석 틀 설정" 탭에서 강의실을 만들어주세요.'),
      );
    }

    final layout = _assignmentLayout;
    final roomId = _assignmentRoomId;
    final teams = ref.watch(projectTeamsProvider).asData?.value ?? [];
    final assignmentAsync = roomId != null
        ? ref.watch(seatingRoomAssignmentProvider(roomId))
        : null;
    final isPublished = assignmentAsync?.asData?.value?.isPublished ?? false;
    final inactiveSeats = _inactiveSeatIds(students);

    return Padding(
      padding: EdgeInsets.all(AppSpace.s(16)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Align(
            alignment: Alignment.centerLeft,
            child: _buildRoomSelector(
              rooms: rooms,
              selectedId: _assignmentRoomId,
              hint: '좌석을 확인할 강의실',
              onChanged: (room) => _selectAssignmentRoom(room?.id, room),
              width: 280,
            ),
          ),
          if (_assignmentRoomId == null) ...[
            SizedBox(height: AppSpace.s(24)),
            Center(
              child: Text(
                '좌석을 확인할 강의실을 선택해주세요.',
                style: TextStyle(color: AppColors.textSecondary),
              ),
            ),
          ] else if (layout == null) ...[
            SizedBox(height: AppSpace.s(24)),
            const Center(child: CircularProgressIndicator()),
          ] else ...[
            SizedBox(height: AppSpace.s(12)),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                if (isPublished)
                  Chip(
                    label: Text('확정됨', style: TextStyle(fontSize: 11)),
                    backgroundColor: AppColors.tint(const Color(0xFFD1FAE5)),
                  )
                else
                  Chip(
                    label: Text('작성 중', style: TextStyle(fontSize: 11)),
                    backgroundColor: AppColors.tint(const Color(0xFFFEF3C7)),
                  ),
                OutlinedButton.icon(
                  onPressed: _randomAssign,
                  icon: const Icon(Icons.shuffle, size: 18),
                  label: const Text('랜덤 배치'),
                ),
                FilledButton.tonalIcon(
                  onPressed: _assignByTeams,
                  icon: const Icon(Icons.groups_rounded, size: 18),
                  label: const Text('팀끼리 앉히기'),
                ),
                OutlinedButton.icon(
                  onPressed: _clearAssignments,
                  icon: const Icon(Icons.clear_all, size: 18),
                  label: const Text('전체 해제'),
                ),
                FilledButton.icon(
                  onPressed: _isSaving ? null : () => _saveAssignments(),
                  icon: const Icon(Icons.save_outlined, size: 18),
                  label: const Text('임시 저장'),
                ),
                FilledButton.icon(
                  onPressed: _isSaving
                      ? null
                      : () => _saveAssignments(publish: true),
                  icon: const Icon(Icons.check_circle_outline, size: 18),
                  label: Text(isPublished ? '재확정' : '확정'),
                ),
              ],
            ),
            if (inactiveSeats.isNotEmpty) ...[
              SizedBox(height: AppSpace.s(8)),
              Text(
                '⚠ 퇴소 학생이 배정된 좌석이 ${inactiveSeats.length}개 있습니다.',
                style: TextStyle(fontSize: 12, color: AppColors.warning),
              ),
            ],
            SizedBox(height: AppSpace.s(12)),
            Expanded(
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final wide = constraints.maxWidth >= 900;
                  final unassigned = _unassignedStudents(students);
                  final displayNames = _seatDisplayNames(students);
                  final grid = SingleChildScrollView(
                    child: SeatGrid(
                      layout: layout,
                      seatUserIds: _draftAssignments,
                      seatDisplayNames: displayNames,
                      editable: true,
                      inactiveSeatIds: inactiveSeats,
                      seatTintColors: _seatTeamTints(teams),
                      onAssign: _assignStudent,
                      onSwap: _swapSeats,
                    ),
                  );
                  final list = UnassignedStudentList(
                    students: unassigned,
                    onDropFromSeat: _unassignFromSeat,
                  );

                  if (wide) {
                    return Row(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        SizedBox(width: 280, child: list),
                        SizedBox(width: AppSpace.s(16)),
                        Expanded(child: grid),
                      ],
                    );
                  }
                  return Column(
                    children: [
                      SizedBox(height: 200, child: list),
                      SizedBox(height: AppSpace.s(12)),
                      Expanded(child: grid),
                    ],
                  );
                },
              ),
            ),
          ],
        ],
      ),
    );
  }
}
