import 'package:cloud_firestore/cloud_firestore.dart';

import '../../core/constants/cohort_status.dart';
import '../../core/utils/date_utils.dart';
import 'resume_model.dart';

const _unset = Object();

/// Firestore `cohorts/{cohortId}` 문서 모델
class CohortModel {
  const CohortModel({
    required this.cohortId,
    required this.name,
    this.description,
    this.startDate,
    this.endDate,
    this.isActive = true,
    this.status = CohortStatus.active,
    this.termNumber,
    this.classroomName,
    this.studentCount = 0,
    this.createdAt,
  });

  final String cohortId;
  final String name;
  final String? description;
  final DateTime? startDate;
  final DateTime? endDate;
  final bool isActive;
  final CohortStatus status;
  final int? termNumber;
  final String? classroomName;
  final int studentCount;
  final DateTime? createdAt;

  bool get isSelectable =>
      status == CohortStatus.active || status == CohortStatus.upcoming;

  String get statusLabel => status.label;

  String get periodLabel {
    if (startDate == null && endDate == null) return '-';
    final start = startDate != null ? AppDateUtils.formatDisplay(startDate!) : '?';
    final end = endDate != null ? AppDateUtils.formatDisplay(endDate!) : '?';
    return '$start ~ $end';
  }

  factory CohortModel.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data()!;
    final statusRaw = data['status'] as String?;
    final isActive = data['isActive'] as bool? ?? true;
    final status = statusRaw != null
        ? CohortStatus.fromString(statusRaw)
        : (isActive ? CohortStatus.active : CohortStatus.archived);

    return CohortModel(
      cohortId: doc.id,
      name: data['name'] as String? ?? '',
      description: data['description'] as String?,
      startDate: AppDateUtils.timestampToDateTime(data['startDate']),
      endDate: AppDateUtils.timestampToDateTime(data['endDate']),
      isActive: isActive,
      status: status,
      termNumber: (data['termNumber'] as num?)?.toInt(),
      classroomName: data['classroomName'] as String?,
      studentCount: (data['studentCount'] as num?)?.toInt() ?? 0,
      createdAt: AppDateUtils.timestampToDateTime(data['createdAt']),
    );
  }

  Map<String, dynamic> toFirestore({bool isCreate = false}) {
    final isActiveValue = status != CohortStatus.archived;
    return {
      'name': name,
      if (startDate != null) 'startDate': Timestamp.fromDate(startDate!),
      if (endDate != null) 'endDate': Timestamp.fromDate(endDate!),
      'isActive': isActiveValue,
      'status': status.value,
      if (termNumber != null) 'termNumber': termNumber,
      'updatedAt': FieldValue.serverTimestamp(),
      if (isCreate) ...{
        if (description != null) 'description': description,
        if (classroomName != null) 'classroomName': classroomName,
        'studentCount': 0,
        'createdAt': FieldValue.serverTimestamp(),
      } else ...{
        'description': description ?? FieldValue.delete(),
        'classroomName': classroomName ?? FieldValue.delete(),
      },
    };
  }

  CohortModel copyWith({
    String? name,
    Object? description = _unset,
    DateTime? startDate,
    DateTime? endDate,
    CohortStatus? status,
    int? termNumber,
    Object? classroomName = _unset,
  }) {
    return CohortModel(
      cohortId: cohortId,
      name: name ?? this.name,
      description: identical(description, _unset)
          ? this.description
          : description as String?,
      startDate: startDate ?? this.startDate,
      endDate: endDate ?? this.endDate,
      isActive: (status ?? this.status) != CohortStatus.archived,
      status: status ?? this.status,
      termNumber: termNumber ?? this.termNumber,
      classroomName: identical(classroomName, _unset)
          ? this.classroomName
          : classroomName as String?,
      studentCount: studentCount,
      createdAt: createdAt,
    );
  }
}

/// 기수 + 소속 이력서 목록 (관리자 대시보드용)
class CohortWithResumes {
  const CohortWithResumes({
    required this.cohort,
    required this.resumes,
  });

  final CohortModel cohort;
  final List<ResumeModel> resumes;
}
