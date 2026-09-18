/// 국가자격 시험일정 (공공데이터포털)
class QualExamScheduleModel {
  const QualExamScheduleModel({
    required this.implYy,
    required this.implSeq,
    required this.qualgbCd,
    required this.qualgbNm,
    required this.description,
    this.docRegStartDt,
    this.docRegEndDt,
    this.docExamStartDt,
    this.docExamEndDt,
    this.docPassDt,
    this.pracRegStartDt,
    this.pracRegEndDt,
    this.pracExamStartDt,
    this.pracExamEndDt,
    this.pracPassDt,
  });

  final String implYy;
  final int implSeq;
  final String qualgbCd;
  final String qualgbNm;
  final String description;
  final String? docRegStartDt;
  final String? docRegEndDt;
  final String? docExamStartDt;
  final String? docExamEndDt;
  final String? docPassDt;
  final String? pracRegStartDt;
  final String? pracRegEndDt;
  final String? pracExamStartDt;
  final String? pracExamEndDt;
  final String? pracPassDt;

  String get title {
    final desc = description.trim();
    if (desc.isNotEmpty) return desc;
    return '$qualgbNm $implYy년 $implSeq회';
  }

  String? get nextExamDate =>
      docExamStartDt ?? docRegStartDt ?? pracExamStartDt ?? pracRegStartDt;

  String get nextExamLabel {
    if (docExamStartDt != null) return '필기 시험';
    if (docRegStartDt != null) return '필기 접수';
    if (pracExamStartDt != null) return '실기 시험';
    if (pracRegStartDt != null) return '실기 접수';
    return '일정';
  }

  factory QualExamScheduleModel.fromJson(Map<String, dynamic> json) {
    String? date(dynamic v) {
      if (v == null) return null;
      final s = v.toString().trim();
      if (s.isEmpty || s == 'null') return null;
      return s.length >= 8 ? s.substring(0, 8) : s;
    }

    return QualExamScheduleModel(
      implYy: json['implYy']?.toString() ?? '',
      implSeq: int.tryParse(json['implSeq']?.toString() ?? '') ?? 0,
      qualgbCd: json['qualgbCd']?.toString() ?? '',
      qualgbNm: json['qualgbNm']?.toString() ?? '',
      description: json['description']?.toString() ?? '',
      docRegStartDt: date(json['docRegStartDt']),
      docRegEndDt: date(json['docRegEndDt']),
      docExamStartDt: date(json['docExamStartDt']),
      docExamEndDt: date(json['docExamEndDt']),
      docPassDt: date(json['docPassDt']),
      pracRegStartDt: date(json['pracRegStartDt']),
      pracRegEndDt: date(json['pracRegEndDt']),
      pracExamStartDt: date(json['pracExamStartDt']),
      pracExamEndDt: date(json['pracExamEndDt']),
      pracPassDt: date(json['pracPassDt']),
    );
  }
}

class QualExamScheduleResult {
  const QualExamScheduleResult({
    required this.year,
    required this.items,
    required this.totalCount,
    this.syncedAt,
  });

  final int year;
  final List<QualExamScheduleModel> items;
  final int totalCount;
  final DateTime? syncedAt;
}
