import 'package:cloud_firestore/cloud_firestore.dart';

import '../../core/utils/date_utils.dart';

/// 로그인 직후 학생에게 띄우는 「매일 해야 할 일」 알림 팝업
class AlertPopupModel {
  const AlertPopupModel({
    required this.id,
    required this.title,
    required this.content,
    required this.authorName,
    this.authorId,
    this.isActive = true,
    this.sortOrder = 0,
    this.linkUrl,
    this.startTime,
    this.endTime,
    this.createdAt,
    this.updatedAt,
  });

  final String id;
  final String title;
  final String content;
  final String authorName;
  final String? authorId;
  final bool isActive;
  final int sortOrder;
  final String? linkUrl;

  /// 표시 시작 시각 `HH:mm` (null이면 00:00)
  final String? startTime;

  /// 표시 종료 시각 `HH:mm` (null이면 23:59)
  final String? endTime;

  final DateTime? createdAt;
  final DateTime? updatedAt;

  bool get hasTimeWindow {
    final start = startTime?.trim();
    final end = endTime?.trim();
    return (start != null && start.isNotEmpty) ||
        (end != null && end.isNotEmpty);
  }

  String get timeWindowLabel {
    if (!hasTimeWindow) return '종일';
    final start = startTime?.isNotEmpty == true ? startTime! : '00:00';
    final end = endTime?.isNotEmpty == true ? endTime! : '23:59';
    return '$start ~ $end';
  }

  /// 현재 시각(로컬)이 표시 구간에 포함되는지
  bool isVisibleAt(DateTime now) {
    if (!isActive) return false;
    if (!hasTimeWindow) return true;

    final minutes = now.hour * 60 + now.minute;
    final start = _minutesOf(startTime) ?? 0;
    final end = _minutesOf(endTime) ?? (23 * 60 + 59);

    if (start <= end) {
      return minutes >= start && minutes <= end;
    }
    // 자정 넘는 구간 (예: 22:00 ~ 06:00)
    return minutes >= start || minutes <= end;
  }

  static int? _minutesOf(String? hhmm) {
    if (hhmm == null || hhmm.isEmpty) return null;
    final parts = hhmm.split(':');
    if (parts.isEmpty) return null;
    final h = int.tryParse(parts[0]) ?? 0;
    final m = parts.length > 1 ? (int.tryParse(parts[1]) ?? 0) : 0;
    return h * 60 + m;
  }

  factory AlertPopupModel.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data()!;
    return AlertPopupModel(
      id: doc.id,
      title: data['title'] as String? ?? '',
      content: data['content'] as String? ?? '',
      authorName: data['authorName'] as String? ?? '',
      authorId: data['authorId'] as String?,
      isActive: _asBool(data['isActive'], true),
      sortOrder: (data['sortOrder'] as num?)?.toInt() ?? 0,
      linkUrl: _stringOrNull(data['linkUrl']),
      startTime: _stringOrNull(data['startTime']),
      endTime: _stringOrNull(data['endTime']),
      createdAt: AppDateUtils.timestampToDateTime(data['createdAt']),
      updatedAt: AppDateUtils.timestampToDateTime(data['updatedAt']),
    );
  }

  static String? _stringOrNull(dynamic value) {
    if (value == null) return null;
    final text = value.toString().trim();
    return text.isEmpty ? null : text;
  }

  static bool _asBool(dynamic value, bool fallback) {
    if (value is bool) return value;
    if (value is num) return value != 0;
    if (value is String) {
      final normalized = value.toLowerCase().trim();
      if (normalized == 'true' || normalized == '1') return true;
      if (normalized == 'false' || normalized == '0') return false;
    }
    return fallback;
  }

  Map<String, dynamic> toFirestore({
    required String authorId,
    required String authorName,
    bool isCreate = false,
  }) {
    final data = <String, dynamic>{
      'title': title,
      'content': content,
      'authorId': authorId,
      'authorName': authorName,
      'isActive': isActive,
      'sortOrder': sortOrder,
      'updatedAt': FieldValue.serverTimestamp(),
      if (isCreate) 'createdAt': FieldValue.serverTimestamp(),
    };

    void writeOrDelete(String key, String? value) {
      final trimmed = value?.trim();
      if (trimmed != null && trimmed.isNotEmpty) {
        data[key] = trimmed;
      } else if (!isCreate) {
        data[key] = FieldValue.delete();
      }
    }

    writeOrDelete('linkUrl', linkUrl);
    writeOrDelete('startTime', startTime);
    writeOrDelete('endTime', endTime);
    return data;
  }

  AlertPopupModel copyWith({
    String? id,
    String? title,
    String? content,
    String? authorName,
    String? authorId,
    bool? isActive,
    int? sortOrder,
    String? linkUrl,
    String? startTime,
    String? endTime,
    bool clearStartTime = false,
    bool clearEndTime = false,
    DateTime? createdAt,
    DateTime? updatedAt,
  }) {
    return AlertPopupModel(
      id: id ?? this.id,
      title: title ?? this.title,
      content: content ?? this.content,
      authorName: authorName ?? this.authorName,
      authorId: authorId ?? this.authorId,
      isActive: isActive ?? this.isActive,
      sortOrder: sortOrder ?? this.sortOrder,
      linkUrl: linkUrl ?? this.linkUrl,
      startTime: clearStartTime ? null : (startTime ?? this.startTime),
      endTime: clearEndTime ? null : (endTime ?? this.endTime),
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
    );
  }
}
