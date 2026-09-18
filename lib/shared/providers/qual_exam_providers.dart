import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../demo/demo_accounts.dart';
import '../models/qual_exam_schedule_model.dart';
import '../services/qual_exam_schedule_service.dart';

QualExamScheduleResult _demoQualExamSchedules() {
  final year = DateTime.now().year.toString();
  return QualExamScheduleResult(
    year: DateTime.now().year,
    totalCount: 4,
    items: [
      QualExamScheduleModel(
        implYy: year,
        implSeq: 1,
        qualgbCd: 'T',
        qualgbNm: '국가기술자격',
        description: '정보처리기사 ($year년 1회)',
        docRegStartDt: '${year}0310',
        docRegEndDt: '${year}0314',
        docExamStartDt: '${year}0419',
        docExamEndDt: '${year}0419',
        docPassDt: '${year}0516',
      ),
      QualExamScheduleModel(
        implYy: year,
        implSeq: 53,
        qualgbCd: 'T',
        qualgbNm: '국가기술자격',
        description: 'SQLD ($year년 53회)',
        docRegStartDt: '${year}0210',
        docRegEndDt: '${year}0214',
        docExamStartDt: '${year}0315',
        docExamEndDt: '${year}0315',
      ),
      QualExamScheduleModel(
        implYy: year,
        implSeq: 48,
        qualgbCd: 'T',
        qualgbNm: '국가기술자격',
        description: 'ADsP ($year년 48회)',
        docRegStartDt: '${year}0401',
        docRegEndDt: '${year}0405',
        docExamStartDt: '${year}0503',
        docExamEndDt: '${year}0503',
      ),
      QualExamScheduleModel(
        implYy: year,
        implSeq: 2,
        qualgbCd: 'T',
        qualgbNm: '국가기술자격',
        description: '리눅스마스터 2급 ($year년 2회)',
        docRegStartDt: '${year}0512',
        docRegEndDt: '${year}0516',
        docExamStartDt: '${year}0607',
        docExamEndDt: '${year}0607',
      ),
    ],
  );
}

/// Firestore systemCache 직접 조회 — 세션 동안 keepAlive
final qualExamSchedulesProvider =
    FutureProvider<QualExamScheduleResult>((ref) async {
  ref.keepAlive();

  if (DemoConfig.enabled) return _demoQualExamSchedules();

  return ref.read(qualExamScheduleServiceProvider).fetchSchedules();
});
