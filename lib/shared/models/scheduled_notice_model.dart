import 'package:cloud_firestore/cloud_firestore.dart';

import '../../core/utils/date_utils.dart';

enum ScheduleRepeatType {
  once('once', '1회'),
  daily('daily', '매일'),
  weekly('weekly', '매주');

  const ScheduleRepeatType(this.value, this.label);

  final String value;
  final String label;

  static ScheduleRepeatType fromString(String? raw) {
    return ScheduleRepeatType.values.firstWhere(
      (t) => t.value == raw,
      orElse: () => ScheduleRepeatType.once,
    );
  }
}

class ScheduledNoticeModel {
  const ScheduledNoticeModel({
    required this.id,
    required this.title,
    required this.content,
    required this.authorName,
    this.isFavorite = false,
    this.repeatType = ScheduleRepeatType.once,
    this.publishTime = '09:00',
    this.publishAt,
    this.weekday = DateTime.monday,
    this.isActive = true,
    this.authorId,
    this.lastPublishedAt,
    this.nextPublishAt,
    this.createdAt,
    this.updatedAt,
  });

  final String id;
  final String title;
  final String content;
  final String authorName;
  final bool isFavorite;
  final ScheduleRepeatType repeatType;
  final String publishTime;
  final DateTime? publishAt;
  final int weekday;
  final bool isActive;
  final String? authorId;
  final DateTime? lastPublishedAt;
  final DateTime? nextPublishAt;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  String get repeatLabel {
    return switch (repeatType) {
      ScheduleRepeatType.once => publishAt != null
          ? '1회 · ${AppDateUtils.formatDateTime(publishAt!)}'
          : '1회',
      ScheduleRepeatType.daily => '매일 $publishTime',
      ScheduleRepeatType.weekly =>
        '매주 ${_weekdayLabel(weekday)} $publishTime',
    };
  }

  static String _weekdayLabel(int day) {
    return switch (day) {
      DateTime.monday => '월',
      DateTime.tuesday => '화',
      DateTime.wednesday => '수',
      DateTime.thursday => '목',
      DateTime.friday => '금',
      DateTime.saturday => '토',
      DateTime.sunday => '일',
      _ => '$day',
    };
  }

  factory ScheduledNoticeModel.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data()!;
    return ScheduledNoticeModel(
      id: doc.id,
      title: data['title'] as String? ?? '',
      content: data['content'] as String? ?? '',
      authorName: data['authorName'] as String? ?? '',
      isFavorite: data['isFavorite'] as bool? ?? false,
      repeatType: ScheduleRepeatType.fromString(data['repeatType'] as String?),
      publishTime: data['publishTime'] as String? ?? '09:00',
      publishAt: AppDateUtils.timestampToDateTime(data['publishAt']),
      weekday: (data['weekday'] as num?)?.toInt() ?? DateTime.monday,
      isActive: data['isActive'] as bool? ?? true,
      authorId: data['authorId'] as String?,
      lastPublishedAt:
          AppDateUtils.timestampToDateTime(data['lastPublishedAt']),
      nextPublishAt: AppDateUtils.timestampToDateTime(data['nextPublishAt']),
      createdAt: AppDateUtils.timestampToDateTime(data['createdAt']),
      updatedAt: AppDateUtils.timestampToDateTime(data['updatedAt']),
    );
  }

  Map<String, dynamic> toFirestore({
    required String authorId,
    required String authorName,
    required DateTime nextPublishAt,
    bool isCreate = false,
  }) =>
      {
        'title': title,
        'content': content,
        'authorId': authorId,
        'authorName': authorName,
        'isFavorite': isFavorite,
        'repeatType': repeatType.value,
        'publishTime': publishTime,
        if (publishAt != null) 'publishAt': Timestamp.fromDate(publishAt!),
        'weekday': weekday,
        'isActive': isActive,
        'nextPublishAt': Timestamp.fromDate(nextPublishAt),
        'updatedAt': FieldValue.serverTimestamp(),
        if (isCreate) 'createdAt': FieldValue.serverTimestamp(),
      };

  Map<String, dynamic> toFirestoreUpdate({
    required DateTime nextPublishAt,
    String? authorId,
    String? authorName,
  }) =>
      {
        'title': title,
        'content': content,
        'isFavorite': isFavorite,
        'repeatType': repeatType.value,
        'publishTime': publishTime,
        if (publishAt != null) 'publishAt': Timestamp.fromDate(publishAt!),
        'weekday': weekday,
        'isActive': isActive,
        'nextPublishAt': Timestamp.fromDate(nextPublishAt),
        if (authorId != null) 'authorId': authorId,
        if (authorName != null) 'authorName': authorName,
        'updatedAt': FieldValue.serverTimestamp(),
      };

  ScheduledNoticeModel copyWith({
    String? id,
    String? title,
    String? content,
    String? authorName,
    bool? isFavorite,
    ScheduleRepeatType? repeatType,
    String? publishTime,
    DateTime? publishAt,
    int? weekday,
    bool? isActive,
    String? authorId,
    DateTime? lastPublishedAt,
    DateTime? nextPublishAt,
    DateTime? createdAt,
    DateTime? updatedAt,
  }) {
    return ScheduledNoticeModel(
      id: id ?? this.id,
      title: title ?? this.title,
      content: content ?? this.content,
      authorName: authorName ?? this.authorName,
      isFavorite: isFavorite ?? this.isFavorite,
      repeatType: repeatType ?? this.repeatType,
      publishTime: publishTime ?? this.publishTime,
      publishAt: publishAt ?? this.publishAt,
      weekday: weekday ?? this.weekday,
      isActive: isActive ?? this.isActive,
      authorId: authorId ?? this.authorId,
      lastPublishedAt: lastPublishedAt ?? this.lastPublishedAt,
      nextPublishAt: nextPublishAt ?? this.nextPublishAt,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
    );
  }
}

/// 예약 공지의 다음 게시 시각 계산 (Asia/Seoul 기준)
DateTime computeNextPublishAt({
  required ScheduleRepeatType repeatType,
  required String publishTime,
  DateTime? publishAt,
  int weekday = DateTime.monday,
  DateTime? from,
}) {
  final base = from ?? DateTime.now();
  final parts = publishTime.split(':');
  final hour = int.tryParse(parts.first) ?? 9;
  final minute = parts.length > 1 ? (int.tryParse(parts[1]) ?? 0) : 0;

  switch (repeatType) {
    case ScheduleRepeatType.once:
      if (publishAt == null) {
        return DateTime(base.year, base.month, base.day, hour, minute);
      }
      return publishAt;

    case ScheduleRepeatType.daily:
      var candidate = DateTime(base.year, base.month, base.day, hour, minute);
      if (!candidate.isAfter(base)) {
        candidate = candidate.add(const Duration(days: 1));
      }
      return candidate;

    case ScheduleRepeatType.weekly:
      var candidate = DateTime(base.year, base.month, base.day, hour, minute);
      while (candidate.weekday != weekday || !candidate.isAfter(base)) {
        candidate = candidate.add(const Duration(days: 1));
      }
      return candidate;
  }
}
