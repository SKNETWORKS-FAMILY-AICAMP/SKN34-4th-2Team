import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../../core/theme/app_colors.dart';
import '../../providers/curriculum_providers.dart';
import '../../../../core/theme/app_space.dart';

/// 대시보드 사이드바 — 커리큘럼 PDF 바로보기
class CurriculumDashboardSection extends ConsumerWidget {
  const CurriculumDashboardSection({super.key});

  Future<void> _openPdf(BuildContext context, String url) async {
    final uri = Uri.tryParse(url);
    if (uri == null) return;
    final ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('PDF를 열 수 없습니다.')),
      );
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final metaAsync = ref.watch(curriculumMetaProvider);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: EdgeInsets.only(bottom: AppSpace.s(8)),
          child: Text(
            '커리큘럼',
            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
          ),
        ),
        Card(
          margin: EdgeInsets.zero,
          child: Padding(
            padding: EdgeInsets.fromLTRB(AppSpace.s(12), AppSpace.s(12), AppSpace.s(12), AppSpace.s(10)),
            child: metaAsync.when(
              loading: () => SizedBox(
                height: AppSpace.row(40),
                child: Center(
                  child: SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                ),
              ),
              error: (e, _) => Text(
                '커리큘럼을 불러오지 못했습니다',
                style: TextStyle(
                  fontSize: 12,
                  color: AppColors.error.withValues(alpha: 0.9),
                ),
              ),
              data: (meta) {
                final hasPdf =
                    meta != null && meta.published && meta.hasFullPdf;
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(
                          Icons.picture_as_pdf,
                          color: AppColors.error,
                          size: 22,
                        ),
                        SizedBox(width: AppSpace.s(8)),
                        Expanded(
                          child: Text(
                            hasPdf
                                ? (meta.fullPdfFileName ?? '커리큘럼 PDF')
                                : '등록된 커리큘럼 PDF가 없습니다',
                            style: TextStyle(
                              fontSize: 12,
                              height: 1.35,
                              color: hasPdf
                                  ? AppColors.textPrimary
                                  : AppColors.textSecondary,
                              fontWeight: hasPdf
                                  ? FontWeight.w600
                                  : FontWeight.w400,
                            ),
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ),
                    SizedBox(height: AppSpace.s(10)),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton.icon(
                        onPressed: hasPdf
                            ? () => _openPdf(context, meta.fullPdfUrl!)
                            : null,
                        style: FilledButton.styleFrom(
                          minimumSize: const Size.fromHeight(36),
                          padding: EdgeInsets.symmetric(horizontal: AppSpace.s(12)),
                          textStyle: const TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        icon: const Icon(Icons.open_in_new, size: 16),
                        label: const Text('PDF 보기'),
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
        ),
      ],
    );
  }
}
