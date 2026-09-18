import 'package:cloud_firestore/cloud_firestore.dart';

import '../../core/utils/date_utils.dart';

/// 기수별 공부방 소스 (수업 GitHub 저장소)
class StudySourceModel {
  const StudySourceModel({
    required this.id,
    required this.title,
    required this.repoUrl,
    this.branch = 'main',
    this.allowedPrefixes = const [],
    this.isActive = true,
    this.sortOrder = 0,
    this.createdAt,
    this.updatedAt,
  });

  final String id;
  final String title;
  final String repoUrl;
  final String branch;
  final List<String> allowedPrefixes;
  final bool isActive;
  final int sortOrder;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  String get repoLabel {
    final uri = Uri.tryParse(repoUrl);
    if (uri == null) return repoUrl;
    final parts = uri.pathSegments.where((s) => s.isNotEmpty).toList();
    if (parts.length < 2) return repoUrl;
    final repo = parts[1].replaceAll(RegExp(r'\.git$'), '');
    return '${parts[0]}/$repo';
  }

  String get prefixSummary {
    if (allowedPrefixes.isEmpty) return '허용 폴더 없음 · 날짜·파일로 선택';
    if (allowedPrefixes.length <= 2) return allowedPrefixes.join(', ');
    return '${allowedPrefixes.take(2).join(', ')} 외 ${allowedPrefixes.length - 2}개';
  }

  factory StudySourceModel.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data() ?? {};
    final rawPrefixes = data['allowedPrefixes'] as List? ?? [];
    return StudySourceModel(
      id: doc.id,
      title: data['title'] as String? ?? '',
      repoUrl: data['repoUrl'] as String? ?? '',
      branch: data['branch'] as String? ?? 'main',
      allowedPrefixes: rawPrefixes.map((e) => e.toString()).toList(),
      isActive: data['isActive'] as bool? ?? true,
      sortOrder: (data['sortOrder'] as num?)?.toInt() ?? 0,
      createdAt: AppDateUtils.timestampToDateTime(data['createdAt']),
      updatedAt: AppDateUtils.timestampToDateTime(data['updatedAt']),
    );
  }

  Map<String, dynamic> toFirestore({bool isCreate = false}) {
    return {
      'title': title,
      'repoUrl': repoUrl,
      'branch': branch.isEmpty ? 'main' : branch,
      'allowedPrefixes': allowedPrefixes,
      'isActive': isActive,
      'sortOrder': sortOrder,
      'updatedAt': FieldValue.serverTimestamp(),
      if (isCreate) 'createdAt': FieldValue.serverTimestamp(),
    };
  }

  static final repoUrlPattern = RegExp(
    r'^https://github\.com/[\w.-]+/[\w.-]+/?$',
  );

  static String? validateRepoUrl(String raw) {
    final value = raw.trim();
    if (!repoUrlPattern.hasMatch(value)) {
      return 'https://github.com/owner/repo 형식만 가능합니다.';
    }
    return null;
  }
}

class StudyNoteFileRef {
  const StudyNoteFileRef({required this.path, required this.commit});

  final String path;
  final String commit;

  factory StudyNoteFileRef.fromMap(Map<String, dynamic> map) {
    return StudyNoteFileRef(
      path: map['path'] as String? ?? '',
      commit: map['commit'] as String? ?? '',
    );
  }
}

/// 통합 서버(8000)가 git clone으로 만든 공부방 노트
class StudyNoteModel {
  const StudyNoteModel({
    required this.id,
    required this.status,
    this.sourceId = '',
    this.scopeType,
    this.scopeValue,
    this.scopeKey,
    this.reportMarkdown = '',
    this.reviewMarkdown = '',
    this.errorMessage,
    this.message,
    this.files = const [],
  });

  final String id;
  final String status;
  final String sourceId;
  final String? scopeType;
  final Object? scopeValue;
  final String? scopeKey;
  final String reportMarkdown;
  final String reviewMarkdown;
  final String? errorMessage;
  final String? message;
  final List<StudyNoteFileRef> files;

  bool get isReady => status == 'ready';
  bool get isTooBroad => status == 'too_broad';
  bool get isFailed => status == 'failed';
  bool get isGenerating => status == 'generating';

  String get scopeLabel {
    if (scopeType == 'date') return scopeValue?.toString() ?? id;
    if (scopeType == 'prefix') return scopeValue?.toString() ?? '폴더';
    if (scopeType == 'files') {
      if (scopeValue is List) return '파일 ${(scopeValue as List).length}개';
      return '선택한 파일';
    }
    return id;
  }

  String get displayTitle {
    if (scopeType == 'date') {
      final raw = scopeValue?.toString() ?? '';
      final match = RegExp(r'^(\d{4})-(\d{2})-(\d{2})$').firstMatch(raw);
      if (match != null) {
        return '${int.parse(match.group(2)!)}월 ${int.parse(match.group(3)!)}일 수업';
      }
      return raw.isEmpty ? '수업 노트' : raw;
    }
    if (scopeType == 'prefix') {
      final path = scopeValue?.toString() ?? '';
      if (path.isEmpty) return '폴더 노트';
      final name = path.split('/').where((part) => part.isNotEmpty).lastOrNull;
      return name == null || name == path ? path : name;
    }
    if (scopeType == 'files') {
      if (files.length == 1) return fileNameOf(files.first.path);
      if (files.isNotEmpty) return '선택한 파일 ${files.length}개';
      if (scopeValue is List) return '선택한 파일 ${(scopeValue as List).length}개';
      return '선택한 파일';
    }
    return '수업 노트';
  }

  String get displaySubtitle {
    if (files.isEmpty) return scopeLabel;
    if (files.length <= 2) {
      return files.map((file) => fileNameOf(file.path)).join(' · ');
    }
    return '${fileNameOf(files.first.path)} 외 ${files.length - 1}개 파일';
  }

  static String fileNameOf(String path) {
    final parts = path.split('/');
    return parts.isEmpty ? path : parts.last;
  }

  factory StudyNoteModel.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    return StudyNoteModel.fromMap(doc.id, doc.data() ?? {});
  }

  factory StudyNoteModel.fromCallable(Map<String, dynamic> data) {
    return StudyNoteModel.fromMap(
      data['noteId'] as String? ?? '',
      data,
    );
  }

  factory StudyNoteModel.fromMap(String id, Map<String, dynamic> data) {
    final rawFiles = data['files'] as List? ?? [];
    return StudyNoteModel(
      id: id,
      status: data['status'] as String? ?? 'missing',
      sourceId: data['sourceId'] as String? ?? '',
      scopeType: data['scopeType'] as String?,
      scopeValue: data['scopeValue'],
      scopeKey: data['scopeKey'] as String?,
      reportMarkdown: data['reportMarkdown'] as String? ?? '',
      reviewMarkdown: data['reviewMarkdown'] as String? ?? '',
      errorMessage: data['errorMessage'] as String?,
      message: data['message'] as String?,
      files: rawFiles
          .whereType<Map>()
          .map((e) => StudyNoteFileRef.fromMap(Map<String, dynamic>.from(e)))
          .toList(),
    );
  }
}
