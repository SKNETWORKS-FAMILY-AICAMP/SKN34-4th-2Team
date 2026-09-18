import 'package:cloud_firestore/cloud_firestore.dart';

import '../../core/utils/date_utils.dart';

/// 인프런 강의 패키지 유형
enum InflearnPackageType {
  review('review', '예복습'),
  preview('preview', '예습'),
  bonus('bonus', '미리보기');

  const InflearnPackageType(this.value, this.label);

  final String value;
  final String label;

  static InflearnPackageType fromString(String? raw) {
    return InflearnPackageType.values.firstWhere(
      (t) => t.value == raw,
      orElse: () => InflearnPackageType.review,
    );
  }
}

/// 인프런 강의 1개
class InflearnCourseModel {
  const InflearnCourseModel({
    required this.title,
    required this.url,
  });

  final String title;
  final String url;

  factory InflearnCourseModel.fromMap(Map<String, dynamic> map) {
    return InflearnCourseModel(
      title: map['title'] as String? ?? '',
      url: map['url'] as String? ?? '',
    );
  }

  Map<String, dynamic> toMap() => {
        'title': title,
        'url': url,
      };

  InflearnCourseModel copyWith({String? title, String? url}) {
    return InflearnCourseModel(
      title: title ?? this.title,
      url: url ?? this.url,
    );
  }
}

/// 단원 (교과목 하위 그룹)
class InflearnUnitModel {
  const InflearnUnitModel({
    required this.name,
    this.courses = const [],
  });

  final String name;
  final List<InflearnCourseModel> courses;

  factory InflearnUnitModel.fromMap(Map<String, dynamic> map) {
    final rawCourses = map['courses'] as List? ?? [];
    return InflearnUnitModel(
      name: map['name'] as String? ?? '',
      courses: rawCourses
          .map((c) => InflearnCourseModel.fromMap(c as Map<String, dynamic>))
          .toList(),
    );
  }

  Map<String, dynamic> toMap() => {
        'name': name,
        'courses': courses.map((c) => c.toMap()).toList(),
      };

  InflearnUnitModel copyWith({
    String? name,
    List<InflearnCourseModel>? courses,
  }) {
    return InflearnUnitModel(
      name: name ?? this.name,
      courses: courses ?? this.courses,
    );
  }
}

/// 기수별 인프런 강의 패키지 (학습실)
class InflearnPackageModel {
  const InflearnPackageModel({
    required this.id,
    required this.title,
    required this.subject,
    this.type = InflearnPackageType.review,
    this.summary,
    this.units = const [],
    this.courses = const [],
    this.isPublished = false,
    this.sortOrder = 0,
    this.publishedAt,
    this.createdAt,
    this.updatedAt,
  });

  final String id;
  final String title;
  final String subject;
  final InflearnPackageType type;
  final String? summary;
  final List<InflearnUnitModel> units;
  final List<InflearnCourseModel> courses;
  final bool isPublished;
  final int sortOrder;
  final DateTime? publishedAt;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  bool get hasUnits => units.isNotEmpty;

  int get totalCourseCount {
    if (hasUnits) {
      return units.fold(0, (total, u) => total + u.courses.length);
    }
    return courses.length;
  }

  String get typeLabel => type.label;

  String? get publishedAtLabel =>
      publishedAt != null ? AppDateUtils.formatDisplay(publishedAt!) : null;

  factory InflearnPackageModel.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data()!;
    final rawUnits = data['units'] as List? ?? [];
    final rawCourses = data['courses'] as List? ?? [];

    return InflearnPackageModel(
      id: doc.id,
      title: data['title'] as String? ?? '',
      subject: data['subject'] as String? ?? '',
      type: InflearnPackageType.fromString(data['type'] as String?),
      summary: data['summary'] as String?,
      units: rawUnits
          .map((u) => InflearnUnitModel.fromMap(u as Map<String, dynamic>))
          .toList(),
      courses: rawCourses
          .map((c) => InflearnCourseModel.fromMap(c as Map<String, dynamic>))
          .toList(),
      isPublished: data['isPublished'] as bool? ?? false,
      sortOrder: (data['sortOrder'] as num?)?.toInt() ?? 0,
      publishedAt: AppDateUtils.timestampToDateTime(data['publishedAt']),
      createdAt: AppDateUtils.timestampToDateTime(data['createdAt']),
      updatedAt: AppDateUtils.timestampToDateTime(data['updatedAt']),
    );
  }

  Map<String, dynamic> toFirestore({bool isCreate = false}) {
    return {
      'title': title,
      'subject': subject,
      'type': type.value,
      if (summary != null && summary!.isNotEmpty) 'summary': summary,
      'units': units.map((u) => u.toMap()).toList(),
      'courses': courses.map((c) => c.toMap()).toList(),
      'isPublished': isPublished,
      'sortOrder': sortOrder,
      if (publishedAt != null) 'publishedAt': Timestamp.fromDate(publishedAt!),
      'updatedAt': FieldValue.serverTimestamp(),
      if (isCreate) 'createdAt': FieldValue.serverTimestamp(),
    };
  }

  InflearnPackageModel copyWith({
    String? title,
    String? subject,
    InflearnPackageType? type,
    String? summary,
    List<InflearnUnitModel>? units,
    List<InflearnCourseModel>? courses,
    bool? isPublished,
    int? sortOrder,
    DateTime? publishedAt,
  }) {
    return InflearnPackageModel(
      id: id,
      title: title ?? this.title,
      subject: subject ?? this.subject,
      type: type ?? this.type,
      summary: summary ?? this.summary,
      units: units ?? this.units,
      courses: courses ?? this.courses,
      isPublished: isPublished ?? this.isPublished,
      sortOrder: sortOrder ?? this.sortOrder,
      publishedAt: publishedAt ?? this.publishedAt,
      createdAt: createdAt,
      updatedAt: updatedAt,
    );
  }
}
