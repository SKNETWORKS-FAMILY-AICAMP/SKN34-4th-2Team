import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/date_utils.dart';
import '../../../../shared/models/form_task_model.dart';
import '../../../../core/theme/app_space.dart';

class FormTaskCard extends StatelessWidget {
  const FormTaskCard({
    super.key,
    required this.item,
    this.compact = false,
    this.onTap,
  });

  final FormTaskWithStatus item;
  final bool compact;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final task = item.task;
    final statusColor = item.isCompleted
        ? AppColors.success
        : item.isOverdue
            ? AppColors.error
            : AppColors.warning;

    return Card(
      margin: compact ? EdgeInsets.zero : EdgeInsets.only(bottom: AppSpace.s(10)),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: Padding(
          padding: EdgeInsets.all(compact ? AppSpace.s(14) : AppSpace.s(16)),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          task.title,
                          style: const TextStyle(
                            fontWeight: FontWeight.w600,
                            fontSize: 15,
                          ),
                        ),
                        if (task.description.isNotEmpty && !compact) ...[
                          SizedBox(height: AppSpace.s(4)),
                          Text(
                            task.description,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: 12,
                              color: AppColors.textSecondary,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                  SizedBox(width: AppSpace.s(8)),
                  _StatusChip(label: item.statusLabel, color: statusColor),
                ],
              ),
              SizedBox(height: AppSpace.s(10)),
              Row(
                children: [
                  Icon(
                    Icons.schedule,
                    size: 14,
                    color: item.isOverdue ? AppColors.error : AppColors.textHint,
                  ),
                  SizedBox(width: AppSpace.s(4)),
                  Text(
                    '마감 ${AppDateUtils.formatDisplay(task.dueAt)}'
                    '${item.isCompleted ? '' : ' · D-${task.daysRemaining.clamp(0, 999)}'}',
                    style: TextStyle(
                      fontSize: 11,
                      color: item.isOverdue ? AppColors.error : AppColors.textSecondary,
                    ),
                  ),
                ],
              ),
              SizedBox(height: AppSpace.s(12)),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  FilledButton.icon(
                    onPressed: () => _openUrl(task.formUrl),
                    icon: const Icon(Icons.description_outlined, size: 16),
                    label: const Text('구글폼 작성'),
                    style: FilledButton.styleFrom(
                      minimumSize: const Size(0, 36),
                      textStyle: const TextStyle(fontSize: 12),
                    ),
                  ),
                  if (task.notionGuideUrl != null &&
                      task.notionGuideUrl!.isNotEmpty)
                    OutlinedButton.icon(
                      onPressed: () => _openUrl(task.notionGuideUrl!),
                      icon: const Icon(Icons.menu_book_outlined, size: 16),
                      label: const Text('노션 가이드'),
                      style: OutlinedButton.styleFrom(
                        minimumSize: const Size(0, 36),
                        textStyle: const TextStyle(fontSize: 12),
                      ),
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _openUrl(String url) async {
    final uri = Uri.tryParse(url);
    if (uri == null) return;
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(horizontal: AppSpace.s(8), vertical: AppSpace.s(4)),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w700,
          color: color,
        ),
      ),
    );
  }
}
