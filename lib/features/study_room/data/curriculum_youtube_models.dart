/// 커리큘럼 주차 YouTube 추천 (Cloud Function 응답)
class CurriculumYoutubeVideo {
  const CurriculumYoutubeVideo({
    required this.videoId,
    required this.title,
    required this.channelTitle,
    required this.thumbnailUrl,
    this.publishedAt,
    this.query = '',
    this.topicLabel = '',
  });

  final String videoId;
  final String title;
  final String channelTitle;
  final String thumbnailUrl;
  final String? publishedAt;
  final String query;
  final String topicLabel;

  String get youtubeUrl => 'https://www.youtube.com/watch?v=$videoId';

  factory CurriculumYoutubeVideo.fromMap(Map<String, dynamic> map) {
    return CurriculumYoutubeVideo(
      videoId: map['videoId'] as String? ?? '',
      title: map['title'] as String? ?? '',
      channelTitle: map['channelTitle'] as String? ?? '',
      thumbnailUrl: map['thumbnailUrl'] as String? ?? '',
      publishedAt: map['publishedAt'] as String?,
      query: map['query'] as String? ?? '',
      topicLabel: map['topicLabel'] as String? ?? '',
    );
  }
}

class CurriculumYoutubeRecommendations {
  const CurriculumYoutubeRecommendations({
    this.weekKey,
    this.weekLabel,
    this.topics = const [],
    this.videos = const [],
    this.cached = false,
    this.message,
  });

  final String? weekKey;
  final String? weekLabel;
  final List<String> topics;
  final List<CurriculumYoutubeVideo> videos;
  final bool cached;
  final String? message;

  factory CurriculumYoutubeRecommendations.fromMap(Map<String, dynamic> map) {
    final rawVideos = map['videos'] as List? ?? const [];
    final rawTopics = map['topics'] as List? ?? const [];
    return CurriculumYoutubeRecommendations(
      weekKey: map['weekKey'] as String?,
      weekLabel: map['weekLabel'] as String?,
      topics: rawTopics.map((e) => e.toString()).toList(),
      videos: rawVideos
          .map(
            (e) => CurriculumYoutubeVideo.fromMap(
              Map<String, dynamic>.from(e as Map),
            ),
          )
          .where((v) => v.videoId.isNotEmpty)
          .toList(),
      cached: map['cached'] as bool? ?? false,
      message: map['message'] as String?,
    );
  }
}
