import 'package:cloud_firestore/cloud_firestore.dart';

import '../../core/utils/date_utils.dart';

/// 커리큘럼 CSV 한 행
class CurriculumRowModel {
  const CurriculumRowModel({
    required this.dayIndex,
    required this.dateLabel,
    required this.subject,
    required this.topic,
    this.detail = '',
    this.order = 0,
  });

  final int dayIndex;
  final String dateLabel;
  final String subject;
  final String topic;
  final String detail;
  final int order;

  String get detailOrTopic => detail.trim().isEmpty ? topic : detail;

  String toAiContextLine() {
    final buf = StringBuffer()
      ..write('일수 $dayIndex')
      ..write(dateLabel.isEmpty ? '' : ' ($dateLabel)')
      ..write(': [$subject] $topic');
    if (detail.trim().isNotEmpty && detail.trim() != topic.trim()) {
      buf.write(' — $detail');
    }
    return buf.toString();
  }

  factory CurriculumRowModel.fromMap(Map<String, dynamic> data) {
    return CurriculumRowModel(
      dayIndex: (data['dayIndex'] as num?)?.toInt() ?? 0,
      dateLabel: data['dateLabel'] as String? ?? '',
      subject: data['subject'] as String? ?? '',
      topic: data['topic'] as String? ?? '',
      detail: data['detail'] as String? ?? '',
      order: (data['order'] as num?)?.toInt() ?? 0,
    );
  }

  Map<String, dynamic> toMap() => {
        'dayIndex': dayIndex,
        'dateLabel': dateLabel,
        'subject': subject,
        'topic': topic,
        'detail': detail,
        'order': order,
      };
}

/// 기수별 업로드된 커리큘럼 시트 (rows 임베드, ~100행)
class CurriculumSheetModel {
  const CurriculumSheetModel({
    required this.id,
    required this.title,
    required this.fileName,
    required this.rows,
    this.uploadedBy,
    this.uploadedByName,
    this.uploadedAt,
    this.storagePath,
    this.source = 'csv',
  });

  final String id;
  final String title;
  final String fileName;
  final List<CurriculumRowModel> rows;
  final String? uploadedBy;
  final String? uploadedByName;
  final DateTime? uploadedAt;
  final String? storagePath;
  final String source;

  int get rowCount => rows.length;

  factory CurriculumSheetModel.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data()!;
    final rawRows = data['rows'] as List? ?? [];
    return CurriculumSheetModel(
      id: doc.id,
      title: data['title'] as String? ?? '',
      fileName: data['fileName'] as String? ?? '',
      rows: rawRows
          .whereType<Map>()
          .map((e) => CurriculumRowModel.fromMap(Map<String, dynamic>.from(e)))
          .toList()
        ..sort((a, b) => a.dayIndex.compareTo(b.dayIndex)),
      uploadedBy: data['uploadedBy'] as String?,
      uploadedByName: data['uploadedByName'] as String?,
      uploadedAt: AppDateUtils.timestampToDateTime(data['uploadedAt']),
      storagePath: data['storagePath'] as String?,
      source: data['source'] as String? ?? 'csv',
    );
  }

  Map<String, dynamic> toFirestore() => {
        'title': title,
        'fileName': fileName,
        'rowCount': rows.length,
        'rows': rows.map((e) => e.toMap()).toList(),
        if (uploadedBy != null) 'uploadedBy': uploadedBy,
        if (uploadedByName != null) 'uploadedByName': uploadedByName,
        if (storagePath != null) 'storagePath': storagePath,
        'source': source,
        'uploadedAt': FieldValue.serverTimestamp(),
        'updatedAt': FieldValue.serverTimestamp(),
      };
}
