import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/demo/demo_accounts.dart';
import '../../../shared/models/user_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../data/seating_repository.dart';
import '../models/project_team_model.dart';
import '../models/seating_assignment_model.dart';
import '../models/seating_layout_model.dart';
import '../models/seating_room_model.dart';

SeatingLayoutModel _demoPublishedLayout() {
  var layout = SeatingLayoutModel.defaultGridSized(rows: 4, cols: 8);
  layout = layout.placeInstructor(0, 3);
  layout = layout.placeTable(1, 0, 3, 'demo-table-1');
  layout = layout.placeTable(1, 4, 3, 'demo-table-2');
  layout = layout.placeTable(2, 0, 3, 'demo-table-3');
  layout = layout.placeTable(2, 4, 3, 'demo-table-4');
  layout = layout.placeDoor(3, 3);
  return layout;
}

SeatingAssignmentModel _demoPublishedAssignment() {
  return SeatingAssignmentModel(
    status: SeatingAssignmentStatus.published,
    assignments: const {
      '1': 'demo-student-001',
      '2': 'demo-student-002',
      '3': 'demo-student-003',
      '4': 'demo-student-004',
    },
    seatNames: const {
      '1': '문성호',
      '2': '김하늘',
      '3': '박서연',
      '4': '이도윤',
    },
    publishedAt: null,
  );
}

final seatingRoomsProvider =
    StreamProvider.autoDispose<List<SeatingRoomModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null || DemoConfig.enabled) return Stream.value([]);
  return ref.watch(seatingRepositoryProvider).watchRooms(cohortId);
});

final projectTeamsProvider =
    StreamProvider.autoDispose<List<ProjectTeamModel>>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null || DemoConfig.enabled) return Stream.value([]);
  return ref.watch(seatingRepositoryProvider).watchProjectTeams(cohortId);
});

final seatingMetaProvider = StreamProvider.autoDispose<SeatingMetaModel>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null || DemoConfig.enabled) return Stream.value(const SeatingMetaModel());
  return ref.watch(seatingRepositoryProvider).watchMeta(cohortId);
});

final seatingRoomProvider =
    StreamProvider.autoDispose.family<SeatingRoomModel?, String>((ref, roomId) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null || DemoConfig.enabled) return Stream.value(null);
  return ref.watch(seatingRepositoryProvider).watchRoom(cohortId, roomId);
});

final seatingRoomAssignmentProvider = StreamProvider.autoDispose
    .family<SeatingAssignmentModel?, String>((ref, roomId) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null || DemoConfig.enabled) return Stream.value(null);
  return ref.watch(seatingRepositoryProvider).watchAssignment(cohortId, roomId);
});

/// 학생 — 확정된 강의실 레이아웃
final publishedSeatingLayoutProvider =
    StreamProvider.autoDispose<SeatingLayoutModel?>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value(null);
  if (DemoConfig.enabled) return Stream.value(_demoPublishedLayout());
  return ref.watch(seatingRepositoryProvider).watchPublishedLayout(cohortId);
});

/// 학생 — 확정된 배치
final publishedSeatingAssignmentProvider =
    StreamProvider.autoDispose<SeatingAssignmentModel?>((ref) {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) return Stream.value(null);
  if (DemoConfig.enabled) return Stream.value(_demoPublishedAssignment());
  return ref.watch(seatingRepositoryProvider).watchPublishedAssignment(cohortId);
});

/// 대시보드 미리보기 표시 기간 (관리자 확정 후)
const kSeatingDashboardPreviewDuration = Duration(days: 3);

bool isSeatingDashboardPreviewVisible(SeatingAssignmentModel? assignment) {
  if (assignment == null || !assignment.isPublished) return false;
  final publishedAt = assignment.publishedAt;
  if (publishedAt == null) return false;
  return DateTime.now().difference(publishedAt) <= kSeatingDashboardPreviewDuration;
}

/// 대시보드 — 확정 후 3일 이내에만 미니 배치표 표시
final showSeatingDashboardPreviewProvider =
    Provider.autoDispose<bool>((ref) {
  final assignment =
      ref.watch(publishedSeatingAssignmentProvider).asData?.value;
  return isSeatingDashboardPreviewVisible(assignment);
});

/// seatId → UserModel (배정된 학생, 확정된 배치 기준)
final seatingAssignedStudentsProvider =
    Provider.autoDispose<Map<String, UserModel>>((ref) {
  final assignment = ref.watch(publishedSeatingAssignmentProvider).asData?.value;
  final students = ref.watch(cohortStudentsProvider).asData?.value ?? [];
  if (assignment == null) return {};

  final byId = {for (final s in students) s.uid: s};
  final result = <String, UserModel>{};
  for (final entry in assignment.assignments.entries) {
    final student = byId[entry.value];
    if (student != null) {
      result[entry.key] = student;
    }
  }
  return result;
});

/// 미배정 재원 학생 (확정 배치 기준)
final seatingUnassignedStudentsProvider =
    Provider.autoDispose<List<UserModel>>((ref) {
  final assignment =
      ref.watch(publishedSeatingAssignmentProvider).asData?.value;
  final students = ref.watch(cohortStudentsProvider).asData?.value ?? [];
  final assignedUids = assignment?.assignments.values.toSet() ?? {};
  return students.where((s) => !assignedUids.contains(s.uid)).toList();
});

/// 배정은 있으나 비활성/퇴소 학생 (관리자 경고용 — roomId 지정)
final seatingInactiveAssignedProvider = Provider.autoDispose
    .family<Map<String, String>, String>((ref, roomId) {
  final assignment =
      ref.watch(seatingRoomAssignmentProvider(roomId)).asData?.value;
  if (assignment == null) return {};

  final activeStudents =
      ref.watch(cohortStudentsProvider).asData?.value ?? [];
  final activeUids = activeStudents.map((s) => s.uid).toSet();

  final orphan = <String, String>{};
  for (final entry in assignment.assignments.entries) {
    if (!activeUids.contains(entry.value)) {
      orphan[entry.key] = entry.value;
    }
  }
  return orphan;
});
