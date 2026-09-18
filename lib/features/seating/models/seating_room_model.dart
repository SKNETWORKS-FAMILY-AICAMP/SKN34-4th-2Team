import 'package:cloud_firestore/cloud_firestore.dart';

import 'seating_layout_model.dart';

/// `cohorts/{cohortId}/seating/rooms/{roomId}`
class SeatingRoomModel {
  const SeatingRoomModel({
    required this.id,
    required this.layout,
    this.createdAt,
    this.updatedAt,
  });

  final String id;
  final SeatingLayoutModel layout;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  String? get roomNumber => layout.roomNumber;

  String get displayLabel {
    final room = roomNumber?.trim();
    if (room != null && room.isNotEmpty) return room;
    return '이름 없음';
  }

  int get seatCount => layout.seatCount;

  factory SeatingRoomModel.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    return SeatingRoomModel(
      id: doc.id,
      layout: SeatingLayoutModel.fromFirestore(doc),
      createdAt: (doc.data()?['createdAt'] as Timestamp?)?.toDate(),
      updatedAt: (doc.data()?['updatedAt'] as Timestamp?)?.toDate(),
    );
  }

  Map<String, dynamic> toFirestore({
    required String updatedBy,
    bool isCreate = false,
  }) {
    final data = layout.toFirestore(updatedBy: updatedBy);
    if (isCreate) {
      data['createdAt'] = FieldValue.serverTimestamp();
    }
    return data;
  }

  SeatingRoomModel copyWith({SeatingLayoutModel? layout}) {
    return SeatingRoomModel(
      id: id,
      layout: layout ?? this.layout,
      createdAt: createdAt,
      updatedAt: updatedAt,
    );
  }
}

/// `cohorts/{cohortId}/seating/meta`
class SeatingMetaModel {
  const SeatingMetaModel({this.publishedRoomId});

  final String? publishedRoomId;

  factory SeatingMetaModel.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data() ?? {};
    return SeatingMetaModel(
      publishedRoomId: data['publishedRoomId'] as String?,
    );
  }

  Map<String, dynamic> toFirestore({String? publishedRoomId}) => {
        if (publishedRoomId != null) 'publishedRoomId': publishedRoomId,
        'updatedAt': FieldValue.serverTimestamp(),
      };
}
