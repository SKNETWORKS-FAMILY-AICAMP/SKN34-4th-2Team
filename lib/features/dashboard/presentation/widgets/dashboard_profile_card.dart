import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../shared/models/user_model.dart';
import '../../../../shared/widgets/profile_avatar_editor.dart';
import 'skill_picker_dialog.dart';
import '../../../../core/theme/app_space.dart';

/// 대시보드 프로필 카드 — 스킬 선택 (마일리지는 별도 3D 카드)
class DashboardProfileCard extends ConsumerWidget {
  const DashboardProfileCard({super.key, required this.user});

  final UserModel user;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.border),
        boxShadow: [
          BoxShadow(
            color: AppColors.shadow,
            blurRadius: 16,
            offset: Offset(0, 4),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Material(
        color: Colors.transparent,
        child: Padding(
          padding: EdgeInsets.all(AppSpace.s(18)),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (user.isStudent) ...[
                    ProfileAvatarEditor(
                      uid: user.uid,
                      photoUrl: user.photoUrl,
                      photoStoragePath: user.photoStoragePath,
                      radius: 26,
                    ),
                    SizedBox(width: AppSpace.s(14)),
                  ],
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          user.cohortName,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            color: AppColors.textSecondary,
                            fontSize: 12,
                          ),
                        ),
                        Text(
                          '${user.displayName}님',
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.bold,
                            color: AppColors.textPrimary,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              SizedBox(height: AppSpace.s(14)),
              Divider(height: 1, color: AppColors.border),
              SizedBox(height: AppSpace.s(12)),
              InkWell(
                onTap: () => showSkillPickerDialog(
                  context,
                  ref,
                  uid: user.uid,
                  initialSkills: user.skills,
                ),
                borderRadius: BorderRadius.circular(8),
                child: Padding(
                  padding: EdgeInsets.symmetric(vertical: AppSpace.s(2)),
                  child: user.skills.isEmpty
                      ? Row(
                          children: [
                            Icon(
                              Icons.add_circle_outline,
                              size: 16,
                              color: AppColors.textHint.withValues(alpha: 0.9),
                            ),
                            SizedBox(width: AppSpace.s(6)),
                            Text(
                              '탭하여 스킬을 선택해 주세요',
                              style: TextStyle(
                                fontSize: 13,
                                color: AppColors.textHint,
                              ),
                            ),
                          ],
                        )
                      : Wrap(
                          spacing: 6,
                          runSpacing: 6,
                          children: [
                            ...user.skills
                                .take(6)
                                .map(
                                  (s) => Container(
                                    padding: EdgeInsets.symmetric(
                                      horizontal: AppSpace.s(10),
                                      vertical: AppSpace.s(4),
                                    ),
                                    decoration: BoxDecoration(
                                      color: AppColors.primaryLight,
                                      borderRadius: BorderRadius.circular(16),
                                    ),
                                    child: Text(
                                      s,
                                      style: TextStyle(
                                        fontSize: 11,
                                        color: AppColors.primary,
                                        fontWeight: FontWeight.w600,
                                      ),
                                    ),
                                  ),
                                ),
                            if (user.skills.length > 6)
                              Text(
                                '+${user.skills.length - 6}',
                                style: TextStyle(
                                  fontSize: 11,
                                  color: AppColors.textSecondary,
                                ),
                              ),
                          ],
                        ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
