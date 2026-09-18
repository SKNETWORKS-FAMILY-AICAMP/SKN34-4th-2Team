import 'package:cloud_firestore/cloud_firestore.dart';

import '../../core/utils/date_utils.dart';

class PostModel {
  const PostModel({
    required this.id,
    required this.authorId,
    required this.authorName,
    required this.content,
    this.likeCount = 0,
    this.commentCount = 0,
    this.createdAt,
  });

  final String id;
  final String authorId;
  final String authorName;
  final String content;
  final int likeCount;
  final int commentCount;
  final DateTime? createdAt;

  factory PostModel.fromFirestore(DocumentSnapshot<Map<String, dynamic>> doc) {
    final data = doc.data()!;
    return PostModel(
      id: doc.id,
      authorId: data['authorId'] as String? ?? '',
      authorName: data['authorName'] as String? ?? '',
      content: data['content'] as String? ?? '',
      likeCount: data['likeCount'] as int? ?? 0,
      commentCount: data['commentCount'] as int? ?? 0,
      createdAt: AppDateUtils.timestampToDateTime(data['createdAt']),
    );
  }

  Map<String, dynamic> toFirestore() => {
    'authorId': authorId,
    'authorName': authorName,
    'content': content,
    'likeCount': 0,
    'commentCount': 0,
    'createdAt': FieldValue.serverTimestamp(),
    'updatedAt': FieldValue.serverTimestamp(),
  };
}
