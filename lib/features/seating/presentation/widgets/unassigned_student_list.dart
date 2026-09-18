import 'package:flutter/material.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../shared/models/user_model.dart';
import '../../models/seat_drag_payload.dart';
import '../../../../core/theme/app_space.dart';

/// 미배정 학생 목록 (드래그 소스 + 드롭 타겟)
class UnassignedStudentList extends StatelessWidget {
  const UnassignedStudentList({
    super.key,
    required this.students,
    this.onDropFromSeat,
  });

  final List<UserModel> students;
  final void Function(SeatDragPayload payload)? onDropFromSeat;

  @override
  Widget build(BuildContext context) {
    return DragTarget<SeatDragPayload>(
      onWillAcceptWithDetails: (d) => d.data.fromSeatId != null,
      onAcceptWithDetails: (d) => onDropFromSeat?.call(d.data),
      builder: (context, candidate, _) {
        final isHover = candidate.isNotEmpty;
        return Card(
          color: isHover ? AppColors.primaryLight : null,
          child: Padding(
            padding: EdgeInsets.all(AppSpace.s(12)),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  children: [
                    const Icon(Icons.people_outline, size: 18),
                    SizedBox(width: AppSpace.s(6)),
                    Text(
                      '미배정 (${students.length}명)',
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                  ],
                ),
                SizedBox(height: AppSpace.s(4)),
                Text(
                  '학생을 좌석으로 드래그하세요',
                  style: TextStyle(
                    fontSize: 11,
                    color: AppColors.textSecondary,
                  ),
                ),
                if (isHover) ...[
                  SizedBox(height: AppSpace.s(8)),
                  Text(
                    '여기에 놓으면 배정 해제',
                    style: TextStyle(
                      fontSize: 11,
                      color: AppColors.primary,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
                SizedBox(height: AppSpace.s(12)),
                if (students.isEmpty)
                  Padding(
                    padding: EdgeInsets.symmetric(vertical: AppSpace.s(24)),
                    child: Center(
                      child: Text(
                        '미배정 학생이 없습니다',
                        style: TextStyle(color: AppColors.textSecondary),
                      ),
                    ),
                  )
                else
                  Expanded(
                    child: ListView.separated(
                      itemCount: students.length,
                      separatorBuilder: (_, _) => SizedBox(height: AppSpace.s(6)),
                      itemBuilder: (_, i) {
                        final s = students[i];
                        return Draggable<SeatDragPayload>(
                          data: SeatDragPayload(
                            userId: s.uid,
                            displayName: s.displayName,
                          ),
                          feedback: Material(
                            elevation: 4,
                            borderRadius: BorderRadius.circular(8),
                            child: Container(
                              padding: EdgeInsets.symmetric(
                                horizontal: AppSpace.s(12),
                                vertical: AppSpace.s(8),
                              ),
                              decoration: BoxDecoration(
                                color: AppColors.primaryLight,
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: Text(
                                s.displayName,
                                style: const TextStyle(
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                          ),
                          childWhenDragging: Opacity(
                            opacity: 0.35,
                            child: _StudentChip(name: s.displayName),
                          ),
                          child: _StudentChip(name: s.displayName),
                        );
                      },
                    ),
                  ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _StudentChip extends StatelessWidget {
  const _StudentChip({required this.name});

  final String name;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(horizontal: AppSpace.s(10), vertical: AppSpace.s(8)),
      decoration: BoxDecoration(
        color: AppColors.tint(const Color(0xFFF8FAFC)),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.border),
      ),
      child: Row(
        children: [
          CircleAvatar(
            radius: 14,
            backgroundColor: AppColors.primaryLight,
            child: Text(
              name.isNotEmpty ? name[0] : '?',
              style: TextStyle(
                fontSize: 12,
                color: AppColors.primary,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          SizedBox(width: AppSpace.s(8)),
          Expanded(
            child: Text(
              name,
              style: const TextStyle(fontWeight: FontWeight.w500),
            ),
          ),
          Icon(Icons.drag_indicator, size: 16, color: AppColors.textHint),
        ],
      ),
    );
  }
}
