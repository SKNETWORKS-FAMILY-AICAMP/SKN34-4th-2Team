import 'package:flutter/material.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../core/widgets/app_dropdown.dart';
import '../../../../shared/models/assessment_model.dart';
import '../../../../shared/widgets/status_badge.dart';
import 'assessment_thumbnail.dart';
import '../../../../core/theme/app_space.dart';

class AssessmentStatusChip extends StatelessWidget {
  const AssessmentStatusChip({super.key, required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return switch (label) {
      '진행중' => StatusBadge.success(label),
      '예정' => StatusBadge.info(label),
      '종료' => StatusBadge.neutral(label),
      _ => StatusBadge.warning(label),
    };
  }
}

class AssessmentCompletedBadge extends StatelessWidget {
  const AssessmentCompletedBadge({super.key});

  @override
  Widget build(BuildContext context) {
    return StatusBadge.success('완료', icon: Icons.check_circle);
  }
}

/// 가로형 카드 — 썸네일 작게, 본문 옆에 배치해 화면을 덜 채움.
class AssessmentCard extends StatelessWidget {
  const AssessmentCard({
    super.key,
    required this.assessment,
    required this.onTap,
    this.completed = false,
    this.score,
    this.onEdit,
    this.onDelete,
    this.onPublish,
    this.publishing = false,
  });

  final AssessmentModel assessment;
  final VoidCallback onTap;
  final bool completed;
  final int? score;
  final VoidCallback? onEdit;
  final VoidCallback? onDelete;
  final VoidCallback? onPublish;
  final bool publishing;

  @override
  Widget build(BuildContext context) {
    final hasMenu = onEdit != null || onDelete != null;
    final showPublish =
        onPublish != null && !assessment.published && !completed;

    return Material(
      color: AppColors.surface,
      borderRadius: BorderRadius.circular(10),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Ink(
          decoration: BoxDecoration(
            border: Border.all(color: AppColors.border),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Padding(
            padding: EdgeInsets.all(AppSpace.s(10)),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                SizedBox(
                  width: 96,
                  height: 72,
                  child: Stack(
                    fit: StackFit.expand,
                    children: [
                      AssessmentThumbnail(
                        key: ValueKey(
                          assessment.thumbnailPath ??
                              assessment.thumbnailUrl ??
                              assessment.id,
                        ),
                        url: assessment.thumbnailUrl,
                        storagePath: assessment.thumbnailPath,
                        title: assessment.title,
                        width: 96,
                        height: 72,
                      ),
                      Positioned(
                        top: 4,
                        left: 4,
                        child: AssessmentStatusChip(
                          label: assessment.statusLabel,
                        ),
                      ),
                    ],
                  ),
                ),
                SizedBox(width: AppSpace.s(12)),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (assessment.tags.isNotEmpty)
                        Padding(
                          padding: EdgeInsets.only(bottom: AppSpace.s(4)),
                          child: Wrap(
                            spacing: 4,
                            runSpacing: 4,
                            children: assessment.tags
                                .take(3)
                                .map(
                                  (t) => Container(
                                    padding: EdgeInsets.symmetric(
                                      horizontal: AppSpace.s(6),
                                      vertical: AppSpace.s(2),
                                    ),
                                    decoration: BoxDecoration(
                                      color: AppColors.surfaceVariant,
                                      borderRadius: BorderRadius.circular(12),
                                    ),
                                    child: Text(
                                      t,
                                      style: TextStyle(
                                        fontSize: 10,
                                        color: AppColors.textSecondary,
                                      ),
                                    ),
                                  ),
                                )
                                .toList(),
                          ),
                        ),
                      Text(
                        assessment.title,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                          color: AppColors.textPrimary,
                          height: 1.25,
                        ),
                      ),
                      SizedBox(height: AppSpace.s(6)),
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              '${assessment.questionCount}문제 · ${assessment.maxScore}점',
                              style: TextStyle(
                                fontSize: 12,
                                color: AppColors.textSecondary,
                              ),
                            ),
                          ),
                          if (completed) ...[
                            if (score != null)
                              Padding(
                                padding: EdgeInsets.only(right: AppSpace.s(6)),
                                child: Text(
                                  '$score점',
                                  style: TextStyle(
                                    fontSize: 12,
                                    fontWeight: FontWeight.w700,
                                    color: AppColors.textPrimary,
                                  ),
                                ),
                              ),
                            const AssessmentCompletedBadge(),
                          ],
                        ],
                      ),
                    ],
                  ),
                ),
                if (showPublish) ...[
                  SizedBox(width: AppSpace.s(8)),
                  FilledButton(
                    onPressed: publishing ? null : onPublish,
                    style: FilledButton.styleFrom(
                      backgroundColor: AppColors.primary,
                      foregroundColor: Colors.white,
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpace.s(14),
                        vertical: AppSpace.s(10),
                      ),
                      minimumSize: const Size(0, 36),
                      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    ),
                    child: publishing
                        ? SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          )
                        : const Text('발행'),
                  ),
                ],
                if (hasMenu)
                  AppIconMenu<String>(
                    tooltip: '더보기',
                    onSelected: (value) {
                      if (value == 'edit') onEdit?.call();
                      if (value == 'delete') onDelete?.call();
                      if (value == 'publish') onPublish?.call();
                    },
                    items: [
                      if (onEdit != null)
                        const AppMenuAction(value: 'edit', label: '수정'),
                      if (showPublish)
                        const AppMenuAction(value: 'publish', label: '발행'),
                      if (onDelete != null)
                        const AppMenuAction(
                          value: 'delete',
                          label: '삭제',
                          danger: true,
                        ),
                    ],
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
