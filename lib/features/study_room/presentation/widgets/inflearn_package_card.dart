import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../shared/models/inflearn_package_model.dart';
import '../../../../core/theme/app_space.dart';

Color inflearnTypeBadgeColor(InflearnPackageType type) {
  return switch (type) {
    InflearnPackageType.review => const Color(0xFF2563EB),
    InflearnPackageType.preview => AppColors.primary,
    InflearnPackageType.bonus => const Color(0xFF059669),
  };
}

Future<void> openInflearnCourse(BuildContext context, String url) async {
  final trimmed = url.trim();
  if (trimmed.isEmpty) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('강의 링크가 등록되지 않았습니다.')),
    );
    return;
  }
  final uri = Uri.tryParse(trimmed);
  if (uri == null || !uri.hasScheme) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('올바르지 않은 링크입니다.')),
    );
    return;
  }
  final ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
  if (!ok && context.mounted) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('링크를 열 수 없습니다.')),
    );
  }
}

/// 학습실 — 인프런 강의 패키지 카드
class InflearnPackageCard extends StatelessWidget {
  const InflearnPackageCard({
    super.key,
    required this.package,
    this.showDraft = false,
    this.onTap,
  });

  final InflearnPackageModel package;
  final bool showDraft;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    if (!package.isPublished && !showDraft) return const SizedBox.shrink();

    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: AppColors.border),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: EdgeInsets.all(AppSpace.s(20)),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _Header(package: package, showDraft: showDraft),
              if (package.summary != null && package.summary!.isNotEmpty) ...[
                SizedBox(height: AppSpace.s(12)),
                Text(
                  package.summary!,
                  style: TextStyle(
                    fontSize: 13,
                    height: 1.5,
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
              SizedBox(height: AppSpace.s(16)),
              if (package.hasUnits)
                ...package.units.map((unit) => _UnitSection(unit: unit))
              else
                _FlatCourseList(courses: package.courses),
            ],
          ),
        ),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.package, required this.showDraft});

  final InflearnPackageModel package;
  final bool showDraft;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            _Badge(
              label: package.typeLabel,
              color: inflearnTypeBadgeColor(package.type),
            ),
            _Badge(
              label: package.subject,
              color: AppColors.textPrimary,
            ),
            if (!package.isPublished && showDraft)
              _Badge(label: '임시저장', color: AppColors.textSecondary),
            if (package.publishedAtLabel != null)
              Text(
                '배정일 ${package.publishedAtLabel}',
                style: TextStyle(
                  fontSize: 12,
                  color: AppColors.textSecondary,
                ),
              ),
          ],
        ),
        SizedBox(height: AppSpace.s(10)),
        Text(
          package.title,
          style: TextStyle(
            fontSize: 17,
            fontWeight: FontWeight.bold,
            color: AppColors.textPrimary,
          ),
        ),
        SizedBox(height: AppSpace.s(4)),
        Text(
          '총 ${package.totalCourseCount}개 강의',
          style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
        ),
      ],
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(horizontal: AppSpace.s(8), vertical: AppSpace.s(4)),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w600,
          color: color,
        ),
      ),
    );
  }
}

class _UnitSection extends StatelessWidget {
  const _UnitSection({required this.unit});

  final InflearnUnitModel unit;

  @override
  Widget build(BuildContext context) {
    return Theme(
      data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
      child: ExpansionTile(
        tilePadding: EdgeInsets.zero,
        childrenPadding: EdgeInsets.zero,
        title: Text(
          unit.name,
          style: TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w600,
            color: AppColors.textSecondary,
          ),
        ),
        subtitle: Text(
          '${unit.courses.length}개 강의',
          style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
        ),
        children: unit.courses.map((c) => _CourseTile(course: c)).toList(),
      ),
    );
  }
}

class _FlatCourseList extends StatelessWidget {
  const _FlatCourseList({required this.courses});

  final List<InflearnCourseModel> courses;

  @override
  Widget build(BuildContext context) {
    if (courses.isEmpty) {
      return Text(
        '등록된 강의가 없습니다.',
        style: TextStyle(fontSize: 13, color: AppColors.textSecondary),
      );
    }
    return Column(
      children: courses.map((c) => _CourseTile(course: c)).toList(),
    );
  }
}

class _CourseTile extends StatelessWidget {
  const _CourseTile({required this.course});

  final InflearnCourseModel course;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.surfaceVariant,
      borderRadius: BorderRadius.circular(8),
      child: InkWell(
        onTap: () => openInflearnCourse(context, course.url),
        borderRadius: BorderRadius.circular(8),
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: AppSpace.s(12), vertical: AppSpace.s(10)),
          child: Row(
            children: [
              Icon(
                Icons.play_circle_outline,
                size: 18,
                color: AppColors.primary,
              ),
              SizedBox(width: AppSpace.s(10)),
              Expanded(
                child: Text(
                  course.title,
                  style: TextStyle(
                    fontSize: 13,
                    color: AppColors.primaryDark,
                    decoration: TextDecoration.underline,
                    decorationColor: AppColors.primary.withValues(alpha: 0.35),
                  ),
                ),
              ),
              Icon(
                Icons.open_in_new,
                size: 16,
                color: AppColors.textSecondary,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// 관리자 목록용 컴팩트 카드
class InflearnPackageListTile extends StatelessWidget {
  const InflearnPackageListTile({
    super.key,
    required this.package,
    required this.onTap,
    this.onDelete,
  });

  final InflearnPackageModel package;
  final VoidCallback onTap;
  final VoidCallback? onDelete;

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      margin: EdgeInsets.only(bottom: AppSpace.s(12)),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(10),
        side: BorderSide(color: AppColors.border),
      ),
      child: ListTile(
        onTap: onTap,
        title: Text(
          package.title,
          style: const TextStyle(fontWeight: FontWeight.w600),
        ),
        subtitle: Text(
          '${package.subject} · ${package.typeLabel} · ${package.totalCourseCount}강'
          '${package.isPublished ? '' : ' · 임시저장'}',
        ),
        trailing: onDelete != null
            ? IconButton(
                icon: Icon(Icons.delete_outline, color: AppColors.error),
                onPressed: onDelete,
              )
            : const Icon(Icons.chevron_right),
      ),
    );
  }
}
