import '../../../core/utils/date_utils.dart';
import '../../../shared/data/lms_api_client.dart';
import '../models/project_team_model.dart';
import '../models/seating_assignment_model.dart';
import '../models/seating_layout_model.dart';
import '../models/seating_room_model.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class SeatingRepository {
  SeatingRepository(this._api);

  final LmsApiClient _api;

  Stream<T> _watch<T>(T Function() select) async* {
    if (_api.snapshot.isEmpty) {
      try {
        await _api.bootstrap();
      } catch (_) {}
    }
    yield select();
    await for (final _ in _api.changes) {
      yield select();
    }
  }

  List<Map<String, dynamic>> _rooms(String cohortId) => _api
      .list('seatingRooms')
      .where((row) => '${row['cohortId']}' == cohortId)
      .toList();

  SeatingLayoutModel _layout(Map<String, dynamic> room) {
    final roomId = '${room['id']}';
    final cells = _api
        .list('seatingCells')
        .where((row) => '${row['roomId']}' == roomId)
        .map(
          (row) => SeatingCell.fromMap({
            'seatId': row['seatId'] ?? '${row['id']}',
            'row': row['row'] ?? 0,
            'col': row['col'] ?? 0,
            'label': row['label'] ?? '',
            'type': row['type'],
            'groupId': row['groupId'],
          }),
        )
        .toList();
    return SeatingLayoutModel(
      rows: (room['rows'] as num?)?.toInt() ?? kLayoutRows,
      cols: (room['cols'] as num?)?.toInt() ?? kLayoutCols,
      cells: cells,
      roomNumber: room['roomNumber'] as String?,
      maxStudents: (room['maxStudents'] as num?)?.toInt() ?? kMaxCohortStudents,
      updatedAt: AppDateUtils.timestampToDateTime(room['updatedAt']),
      updatedBy: room['updatedBy']?.toString(),
    );
  }

  SeatingRoomModel _room(Map<String, dynamic> row) => SeatingRoomModel(
        id: '${row['id']}',
        layout: _layout(row),
        createdAt: AppDateUtils.timestampToDateTime(row['createdAt']),
        updatedAt: AppDateUtils.timestampToDateTime(row['updatedAt']),
      );

  SeatingAssignmentModel _assignment(String roomId) {
    final row = _api
        .list('seatingAssignments')
        .where((item) => '${item['roomId'] ?? item['id']}' == roomId)
        .firstOrNull;
    final seats = _api.list('seatAssignments').where((item) => '${item['roomId']}' == roomId);
    final assignments = <String, String>{};
    for (final seat in seats) {
      assignments['${seat['cellId'] ?? seat['seatId']}'] = '${seat['userId']}';
    }
    return SeatingAssignmentModel(
      status: SeatingAssignmentStatus.fromString(row?['status'] as String?),
      assignments: assignments,
      publishedAt: AppDateUtils.timestampToDateTime(row?['publishedAt']),
      publishedBy: row?['publishedBy']?.toString(),
      updatedAt: AppDateUtils.timestampToDateTime(row?['updatedAt']),
      updatedBy: row?['updatedBy']?.toString(),
    );
  }

  Stream<List<SeatingRoomModel>> watchRooms(String cohortId) =>
      _watch(() => _rooms(cohortId).map(_room).toList());

  Stream<SeatingRoomModel?> watchRoom(String cohortId, String roomId) =>
      _watch(() => _rooms(cohortId).where((row) => '${row['id']}' == roomId).map(_room).firstOrNull);

  Stream<SeatingAssignmentModel?> watchAssignment(String cohortId, String roomId) =>
      _watch(() => _assignment(roomId));

  Stream<SeatingMetaModel> watchMeta(String cohortId) => _watch(() {
        final published = _api.snapshot['publishedSeatingRoomId']?.toString();
        final cohort = _api
            .list('cohorts')
            .where((row) => '${row['cohortId']}' == cohortId)
            .firstOrNull;
        return SeatingMetaModel(
          publishedRoomId: published ?? cohort?['publishedSeatingRoomId']?.toString(),
        );
      });

  Future<String> createRoom({
    required String cohortId,
    required SeatingLayoutModel layout,
    required String updatedBy,
  }) =>
      _api.command('upsert', {
        'table': 'seating_rooms',
        'action': 'insert',
        'cohortId': cohortId,
      }).then((value) => '${value['id'] ?? ''}');

  Future<void> saveRoom({
    required String cohortId,
    required String roomId,
    required SeatingLayoutModel layout,
    required String updatedBy,
  }) =>
      _api.command('upsert', {'table': 'seating_rooms', 'id': roomId, 'action': 'update'});

  Stream<SeatingLayoutModel?> watchPublishedLayout(String cohortId) =>
      watchMeta(cohortId).asyncExpand((meta) {
        final roomId = meta.publishedRoomId;
        if (roomId == null) return Stream.value(null);
        return watchRoom(cohortId, roomId).map((room) => room?.layout);
      });

  Stream<SeatingAssignmentModel?> watchPublishedAssignment(String cohortId) =>
      watchMeta(cohortId).asyncExpand((meta) {
        final roomId = meta.publishedRoomId;
        if (roomId == null) return Stream.value(null);
        return watchAssignment(cohortId, roomId);
      });

  Future<void> deleteRoom({
    required String cohortId,
    required String roomId,
  }) =>
      _api.command('upsert', {'table': 'seating_rooms', 'id': roomId, 'action': 'delete'});

  Future<void> saveAssignment({
    required String cohortId,
    required String roomId,
    required SeatingAssignmentModel assignment,
    required String updatedBy,
  }) =>
      _api.command('upsert', {'table': 'seating_assignments', 'id': roomId, 'action': 'update'});

  Future<void> publishAssignment({
    required String cohortId,
    required String roomId,
    required Map<String, String> assignments,
    required Map<String, String> seatNames,
    required String publishedBy,
  }) =>
      _api.command('publishSeating', {'cohortId': cohortId, 'roomId': roomId});

  Stream<List<ProjectTeamModel>> watchProjectTeams(String cohortId) => _watch(() {
        final list = _api
            .list('projectTeams')
            .where((row) => '${row['cohortId']}' == cohortId)
            .map(
              (row) => ProjectTeamModel(
                id: '${row['id']}',
                name: row['name'] as String? ?? '',
                memberIds: List<String>.from(row['memberIds'] as List? ?? const []),
                sortOrder: (row['sortOrder'] as num?)?.toInt() ?? 0,
                colorIndex: (row['colorIndex'] as num?)?.toInt() ?? 0,
              ),
            )
            .toList();
        list.sort((a, b) {
          final byOrder = a.sortOrder.compareTo(b.sortOrder);
          if (byOrder != 0) return byOrder;
          return a.name.compareTo(b.name);
        });
        return list;
      });

  Future<String> createProjectTeam({
    required String cohortId,
    required String name,
    required int sortOrder,
    required int colorIndex,
    required String updatedBy,
  }) =>
      _api.command('upsert', {'table': 'project_teams', 'action': 'insert'}).then((v) => '${v['id'] ?? ''}');

  Future<void> updateProjectTeam({
    required String cohortId,
    required ProjectTeamModel team,
    required String updatedBy,
  }) =>
      _api.command('upsert', {'table': 'project_teams', 'id': team.id, 'action': 'update'});

  Future<void> deleteProjectTeam({
    required String cohortId,
    required String teamId,
  }) =>
      _api.command('upsert', {'table': 'project_teams', 'id': teamId, 'action': 'delete'});

  Future<void> replaceProjectTeams({
    required String cohortId,
    required List<ProjectTeamModel> upserts,
    required List<String> deleteTeamIds,
    required String updatedBy,
  }) async {
    for (final id in deleteTeamIds) {
      await deleteProjectTeam(cohortId: cohortId, teamId: id);
    }
    for (final team in upserts) {
      await updateProjectTeam(cohortId: cohortId, team: team, updatedBy: updatedBy);
    }
  }
}

final seatingRepositoryProvider = Provider<SeatingRepository>((ref) {
  return SeatingRepository(lmsApiClient);
});
