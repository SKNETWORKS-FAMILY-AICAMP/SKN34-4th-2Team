import 'package:cloud_firestore/cloud_firestore.dart';

import '../../core/utils/date_utils.dart';

class TodoModel {
  const TodoModel({
    required this.id,
    required this.title,
    required this.isCompleted,
    this.createdAt,
  });

  final String id;
  final String title;
  final bool isCompleted;
  final DateTime? createdAt;

  factory TodoModel.fromFirestore(DocumentSnapshot<Map<String, dynamic>> doc) {
    final data = doc.data()!;
    return TodoModel(
      id: doc.id,
      title: data['title'] as String? ?? '',
      isCompleted: data['isCompleted'] as bool? ?? false,
      createdAt: AppDateUtils.timestampToDateTime(data['createdAt']),
    );
  }

  Map<String, dynamic> toFirestore() => {
    'title': title,
    'isCompleted': isCompleted,
    'createdAt': FieldValue.serverTimestamp(),
  };
}
