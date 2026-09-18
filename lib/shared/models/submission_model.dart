import 'package:cloud_firestore/cloud_firestore.dart';

import '../../core/constants/record_types.dart';
import '../../core/utils/date_utils.dart';

/// 기록실 제출 + 승인 워크플로우
class SubmissionModel {
  const SubmissionModel({
    required this.id,
    required this.userId,
    required this.userDisplayName,
    required this.title,
    required this.type,
    required this.status,
    this.submittedAt,
    this.reviewComment,
    this.certType,
    this.fileUrls = const [],
    this.startAt,
    this.endAt,
    this.weekNumber,
    this.weekLabel,
    this.link,
    this.quizScore,
    this.learningDate,
    this.learningContent,
    this.isTeamStudy,
    this.mileageGranted = false,
    this.mileageAmount = 0,
  });

  final String id;
  final String userId;
  final String userDisplayName;
  final String title;
  final String type;
  final String status;
  final DateTime? submittedAt;
  final String? reviewComment;
  final String? certType;
  final List<String> fileUrls;
  final DateTime? startAt;
  final DateTime? endAt;
  final int? weekNumber;
  final String? weekLabel;
  final String? link;
  final int? quizScore;
  final DateTime? learningDate;
  final String? learningContent;
  final bool? isTeamStudy;
  final bool mileageGranted;
  final int mileageAmount;

  bool get isApproved => status == 'approved';
  bool get isPending => status == 'pending';
  bool get isRejected => status == 'rejected';

  String get typeLabel => RecordTypes.labels[type] ?? type;

  factory SubmissionModel.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data()!;
    return SubmissionModel(
      id: doc.id,
      userId: data['userId'] as String? ?? '',
      userDisplayName: data['userDisplayName'] as String? ?? '',
      title: data['title'] as String? ?? '',
      type: data['type'] as String? ?? 'blog',
      status: data['status'] as String? ?? 'pending',
      submittedAt: AppDateUtils.timestampToDateTime(data['submittedAt']),
      reviewComment: data['reviewComment'] as String?,
      certType: data['certType'] as String?,
      fileUrls: List<String>.from(data['fileUrls'] as List? ?? []),
      startAt: AppDateUtils.timestampToDateTime(data['startAt']),
      endAt: AppDateUtils.timestampToDateTime(data['endAt']),
      weekNumber: data['weekNumber'] as int?,
      weekLabel: data['weekLabel'] as String?,
      link: data['link'] as String?,
      quizScore: (data['quizScore'] as num?)?.toInt(),
      learningDate: AppDateUtils.timestampToDateTime(data['learningDate']),
      learningContent: data['learningContent'] as String?,
      isTeamStudy: data['isTeamStudy'] as bool?,
      mileageGranted: data['mileageGranted'] == true,
      mileageAmount: (data['mileageAmount'] as num?)?.toInt() ?? 0,
    );
  }

  Map<String, dynamic> toFirestore() => {
        'userId': userId,
        'userDisplayName': userDisplayName,
        'title': title,
        'type': type,
        'status': status,
        'submittedAt': FieldValue.serverTimestamp(),
        if (certType != null) 'certType': certType,
        if (fileUrls.isNotEmpty) 'fileUrls': fileUrls,
        if (startAt != null) 'startAt': Timestamp.fromDate(startAt!),
        if (endAt != null) 'endAt': Timestamp.fromDate(endAt!),
        if (weekNumber != null) 'weekNumber': weekNumber,
        if (weekLabel != null) 'weekLabel': weekLabel,
        if (link != null) 'link': link,
        if (quizScore != null) 'quizScore': quizScore,
        if (learningDate != null)
          'learningDate': Timestamp.fromDate(learningDate!),
        if (learningContent != null && learningContent!.isNotEmpty)
          'learningContent': learningContent,
        if (isTeamStudy != null) 'isTeamStudy': isTeamStudy,
      };

  String get statusLabel => switch (status) {
        'approved' => '승인',
        'rejected' => '반려',
        _ => '대기',
      };
}
