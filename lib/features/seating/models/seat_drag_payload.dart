/// 드래그앤드롭 데이터
class SeatDragPayload {
  const SeatDragPayload({
    required this.userId,
    required this.displayName,
    this.fromSeatId,
  });

  final String userId;
  final String displayName;
  final String? fromSeatId;
}
