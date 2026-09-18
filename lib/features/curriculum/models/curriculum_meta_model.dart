import 'package:cloud_firestore/cloud_firestore.dart';

import '../../../core/utils/date_utils.dart';

/// `cohorts/{cohortId}/curriculum/meta`
class CurriculumMetaModel {
  const CurriculumMetaModel({
    this.published = false,
    this.fullPdfUrl,
    this.fullPdfFileName,
    this.updatedAt,
    this.updatedBy,
  });

  final bool published;
  final String? fullPdfUrl;
  final String? fullPdfFileName;
  final DateTime? updatedAt;
  final String? updatedBy;

  bool get hasFullPdf =>
      fullPdfUrl != null && fullPdfUrl!.trim().isNotEmpty;

  factory CurriculumMetaModel.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data() ?? {};
    return CurriculumMetaModel(
      published: data['published'] as bool? ?? false,
      fullPdfUrl: data['fullPdfUrl'] as String?,
      fullPdfFileName: data['fullPdfFileName'] as String?,
      updatedAt: AppDateUtils.timestampToDateTime(data['updatedAt']),
      updatedBy: data['updatedBy'] as String?,
    );
  }

  Map<String, dynamic> toFirestore({String? updatedBy}) => {
        'published': published,
        if (fullPdfUrl != null && fullPdfUrl!.isNotEmpty)
          'fullPdfUrl': fullPdfUrl,
        if (fullPdfFileName != null && fullPdfFileName!.isNotEmpty)
          'fullPdfFileName': fullPdfFileName,
        'updatedAt': FieldValue.serverTimestamp(),
        'updatedBy': ?updatedBy,
      };
}
