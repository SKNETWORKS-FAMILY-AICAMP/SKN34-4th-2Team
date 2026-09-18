import 'package:cloud_firestore/cloud_firestore.dart';

/// 배치 확정 상태
enum SeatingAssignmentStatus {
  draft('draft'),
  published('published');

  const SeatingAssignmentStatus(this.value);
  final String value;

  static SeatingAssignmentStatus fromString(String? raw) {
    return SeatingAssignmentStatus.values.firstWhere(
      (e) => e.value == raw,
      orElse: () => SeatingAssignmentStatus.draft,
    );
  }
}

/// `cohorts/{cohortId}/seating/assignment`
class SeatingAssignmentModel {
  const SeatingAssignmentModel({
    this.status = SeatingAssignmentStatus.draft,
    this.assignments = const {},
    this.seatNames = const {},
    this.publishedAt,
    this.publishedBy,
    this.updatedAt,
    this.updatedBy,
  });

  final SeatingAssignmentStatus status;
  final Map<String, String> assignments;
  /// seatId → 표시 이름 (학생 조회용, publish 시 스냅샷)
  final Map<String, String> seatNames;
  final DateTime? publishedAt;
  final String? publishedBy;
  final DateTime? updatedAt;
  final String? updatedBy;

  bool get isPublished => status == SeatingAssignmentStatus.published;

  String? userIdForSeat(String seatId) => assignments[seatId];

  String? seatIdForUser(String userId) {
    for (final entry in assignments.entries) {
      if (entry.value == userId) return entry.key;
    }
    return null;
  }

  factory SeatingAssignmentModel.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data() ?? {};
    final raw = data['assignments'] as Map<String, dynamic>? ?? {};
    final rawNames = data['seatNames'] as Map<String, dynamic>? ?? {};
    return SeatingAssignmentModel(
      status: SeatingAssignmentStatus.fromString(data['status'] as String?),
      assignments: raw.map((k, v) => MapEntry(k, v as String)),
      seatNames: rawNames.map((k, v) => MapEntry(k, v as String)),
      publishedAt: (data['publishedAt'] as Timestamp?)?.toDate(),
      publishedBy: data['publishedBy'] as String?,
      updatedAt: (data['updatedAt'] as Timestamp?)?.toDate(),
      updatedBy: data['updatedBy'] as String?,
    );
  }

  Map<String, dynamic> toFirestore({
    String? updatedBy,
    bool setPublished = false,
    String? publishedBy,
  }) =>
      {
        'status': status.value,
        'assignments': assignments,
        'seatNames': seatNames,
        'updatedAt': FieldValue.serverTimestamp(),
        if (updatedBy != null) 'updatedBy': updatedBy,
        if (setPublished) ...{
          'publishedAt': FieldValue.serverTimestamp(),
          if (publishedBy != null) 'publishedBy': publishedBy,
        },
      };

  SeatingAssignmentModel copyWith({
    SeatingAssignmentStatus? status,
    Map<String, String>? assignments,
  }) {
    return SeatingAssignmentModel(
      status: status ?? this.status,
      assignments: assignments ?? this.assignments,
      publishedAt: publishedAt,
      publishedBy: publishedBy,
      updatedAt: updatedAt,
      updatedBy: updatedBy,
    );
  }
}
