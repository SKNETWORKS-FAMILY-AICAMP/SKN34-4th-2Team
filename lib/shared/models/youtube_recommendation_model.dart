import 'package:cloud_firestore/cloud_firestore.dart';

import '../../core/utils/date_utils.dart';

/// 학습실 YouTube 추천 영상 (관리자 큐레이션)
class YoutubeRecommendationModel {
  const YoutubeRecommendationModel({
    required this.id,
    required this.title,
    required this.youtubeUrl,
    this.videoId,
    this.thumbnailUrl,
    this.description,
    this.tags = const [],
    this.isPublished = false,
    this.sortOrder = 0,
    this.createdAt,
    this.updatedAt,
  });

  final String id;
  final String title;
  final String youtubeUrl;
  final String? videoId;
  final String? thumbnailUrl;
  final String? description;
  final List<String> tags;
  final bool isPublished;
  final int sortOrder;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  String get effectiveVideoId {
    final stored = videoId?.trim();
    if (stored != null && stored.isNotEmpty) return stored;
    return extractYoutubeVideoId(youtubeUrl) ?? '';
  }

  String get effectiveThumbnailUrl {
    final custom = thumbnailUrl?.trim();
    if (custom != null && custom.isNotEmpty) return custom;
    final id = effectiveVideoId;
    if (id.isEmpty) return '';
    return 'https://img.youtube.com/vi/$id/hqdefault.jpg';
  }

  factory YoutubeRecommendationModel.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data() ?? {};
    return YoutubeRecommendationModel(
      id: doc.id,
      title: data['title'] as String? ?? '',
      youtubeUrl: data['youtubeUrl'] as String? ?? '',
      videoId: data['videoId'] as String?,
      thumbnailUrl: data['thumbnailUrl'] as String?,
      description: data['description'] as String?,
      tags: List<String>.from(data['tags'] as List? ?? const []),
      isPublished: data['isPublished'] as bool? ?? false,
      sortOrder: (data['sortOrder'] as num?)?.toInt() ?? 0,
      createdAt: AppDateUtils.timestampToDateTime(data['createdAt']),
      updatedAt: AppDateUtils.timestampToDateTime(data['updatedAt']),
    );
  }

  Map<String, dynamic> toFirestore({bool isCreate = false}) {
    final id = effectiveVideoId;
    return {
      'title': title.trim(),
      'youtubeUrl': youtubeUrl.trim(),
      'videoId': id.isEmpty ? null : id,
      'thumbnailUrl': effectiveThumbnailUrl.isEmpty
          ? null
          : effectiveThumbnailUrl,
      'description': description?.trim(),
      'tags': tags.map((t) => t.trim()).where((t) => t.isNotEmpty).toList(),
      'isPublished': isPublished,
      'sortOrder': sortOrder,
      if (isCreate) 'createdAt': FieldValue.serverTimestamp(),
      'updatedAt': FieldValue.serverTimestamp(),
    };
  }

  YoutubeRecommendationModel copyWith({
    String? title,
    String? youtubeUrl,
    String? videoId,
    String? thumbnailUrl,
    String? description,
    List<String>? tags,
    bool? isPublished,
    int? sortOrder,
  }) {
    return YoutubeRecommendationModel(
      id: id,
      title: title ?? this.title,
      youtubeUrl: youtubeUrl ?? this.youtubeUrl,
      videoId: videoId ?? this.videoId,
      thumbnailUrl: thumbnailUrl ?? this.thumbnailUrl,
      description: description ?? this.description,
      tags: tags ?? this.tags,
      isPublished: isPublished ?? this.isPublished,
      sortOrder: sortOrder ?? this.sortOrder,
      createdAt: createdAt,
      updatedAt: updatedAt,
    );
  }
}

/// skills 매칭 점수와 함께 정렬된 추천
class RankedYoutubeRecommendation {
  const RankedYoutubeRecommendation({
    required this.item,
    required this.score,
    required this.matchedTags,
  });

  final YoutubeRecommendationModel item;
  final int score;
  final List<String> matchedTags;
}

/// YouTube URL에서 videoId 추출
String? extractYoutubeVideoId(String raw) {
  final url = raw.trim();
  if (url.isEmpty) return null;

  final uri = Uri.tryParse(url);
  if (uri == null) return null;

  final host = uri.host.toLowerCase();
  if (host.contains('youtu.be')) {
    final id = uri.pathSegments.isNotEmpty ? uri.pathSegments.first : '';
    return id.isEmpty ? null : id;
  }

  if (host.contains('youtube.com') || host.contains('youtube-nocookie.com')) {
    final v = uri.queryParameters['v'];
    if (v != null && v.isNotEmpty) return v;

    final segments = uri.pathSegments;
    if (segments.length >= 2 &&
        (segments[0] == 'embed' ||
            segments[0] == 'shorts' ||
            segments[0] == 'live')) {
      return segments[1];
    }
  }

  // bare id
  if (RegExp(r'^[\w-]{11}$').hasMatch(url)) return url;
  return null;
}

/// user.skills ∩ video.tags 기반 랭킹 (대소문자 무시, 부분 일치)
List<RankedYoutubeRecommendation> rankYoutubeRecommendations({
  required List<YoutubeRecommendationModel> videos,
  required List<String> skills,
}) {
  final normalizedSkills = skills
      .map((s) => s.trim().toLowerCase())
      .where((s) => s.isNotEmpty)
      .toList();

  final ranked = <RankedYoutubeRecommendation>[];

  for (final video in videos) {
    if (!video.isPublished) continue;

    final matched = <String>[];
    for (final tag in video.tags) {
      final t = tag.trim().toLowerCase();
      if (t.isEmpty) continue;
      final hit = normalizedSkills.any(
        (s) => s == t || s.contains(t) || t.contains(s),
      );
      if (hit) matched.add(tag);
    }

    // skills 없으면 공개 영상은 score 0으로라도 일부 노출용으로 포함 가능
    // → 호출측에서 skills empty일 때 별도 처리
    ranked.add(
      RankedYoutubeRecommendation(
        item: video,
        score: matched.length,
        matchedTags: matched,
      ),
    );
  }

  ranked.sort((a, b) {
    final byScore = b.score.compareTo(a.score);
    if (byScore != 0) return byScore;
    return a.item.sortOrder.compareTo(b.item.sortOrder);
  });

  return ranked;
}
