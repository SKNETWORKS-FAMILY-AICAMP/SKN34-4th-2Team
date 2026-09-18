import 'package:flutter/material.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../core/theme/app_layout.dart';
import '../../../../shared/models/user_model.dart';
import '../../../../core/theme/app_space.dart';

class StudyRoomPageHeader extends StatelessWidget {
  const StudyRoomPageHeader({
    super.key,
    required this.user,
    this.cohortName,
    this.title = '학습실',
    this.subtitle = '배정된 인프런 강의를 확인하세요.',
    this.showProfile = true,
  });

  final UserModel user;
  final String? cohortName;
  final String title;
  final String subtitle;
  final bool showProfile;

  @override
  Widget build(BuildContext context) {
    final initial = user.displayName.isNotEmpty ? user.displayName[0] : '?';

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.bold,
                  color: AppColors.textPrimary,
                ),
              ),
              SizedBox(height: AppSpace.s(6)),
              Text(
                subtitle,
                style: TextStyle(
                  fontSize: 13,
                  color: AppColors.textSecondary,
                ),
              ),
            ],
          ),
        ),
        if (showProfile)
          Container(
            padding: EdgeInsets.symmetric(horizontal: AppSpace.s(12), vertical: AppSpace.s(8)),
            decoration: BoxDecoration(
              color: AppColors.surfaceVariant,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: AppColors.border),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                CircleAvatar(
                  radius: 16,
                  backgroundColor: AppColors.primaryLight,
                  child: Text(
                    initial,
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.bold,
                      color: AppColors.primary,
                    ),
                  ),
                ),
                SizedBox(width: AppSpace.s(8)),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      user.displayName,
                      style: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    Text(
                      cohortName ?? user.cohortName,
                      style: TextStyle(
                        fontSize: 11,
                        color: AppColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class StudyRoomSearchBar extends StatelessWidget {
  const StudyRoomSearchBar({
    super.key,
    required this.controller,
    this.hintText = '제목 검색',
    this.onChanged,
  });

  final TextEditingController controller;
  final String hintText;
  final ValueChanged<String>? onChanged;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      onChanged: onChanged,
      style: const TextStyle(fontSize: 13),
      decoration: InputDecoration(
        hintText: hintText,
        hintStyle: TextStyle(fontSize: 13, color: AppColors.textHint),
        prefixIcon: const Icon(Icons.search, size: 20),
        filled: true,
        fillColor: AppColors.surfaceVariant,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: BorderSide(color: AppColors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: BorderSide(color: AppColors.border),
        ),
        contentPadding: EdgeInsets.symmetric(vertical: AppSpace.s(0)),
      ),
    );
  }
}

abstract final class StudyRoomLayout {
  static const maxWidth = AppLayout.page;
  static const padding = 24.0;
}

Widget studyRoomContentWrapper({required Widget child}) {
  return Align(
    alignment: Alignment.topCenter,
    child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: StudyRoomLayout.maxWidth),
      child: Padding(
        padding: const EdgeInsets.all(StudyRoomLayout.padding),
        child: child,
      ),
    ),
  );
}
