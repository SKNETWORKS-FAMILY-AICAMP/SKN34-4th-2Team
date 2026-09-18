import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../../core/constants/record_types.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/date_utils.dart';
import '../../../../shared/models/submission_model.dart';
import 'record_status_badge.dart';
import '../../../../core/theme/app_space.dart';

Future<String?> showSubmissionDetailSheet({
  required BuildContext context,
  required SubmissionModel submission,
  required bool isAdmin,
}) {
  return showModalBottomSheet<String>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    backgroundColor: AppColors.surface,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
    ),
    builder: (ctx) {
      final maxH = MediaQuery.sizeOf(ctx).height * 0.88;
      return ConstrainedBox(
        constraints: BoxConstraints(maxHeight: maxH),
        child: _SubmissionDetailBody(
          submission: submission,
          isAdmin: isAdmin,
        ),
      );
    },
  );
}

class _SubmissionDetailBody extends StatelessWidget {
  const _SubmissionDetailBody({
    required this.submission,
    required this.isAdmin,
  });

  final SubmissionModel submission;
  final bool isAdmin;

  Future<void> _openUrl(BuildContext context, String url) async {
    final uri = Uri.tryParse(url);
    if (uri == null) return;
    final ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('링크를 열 수 없습니다.')),
      );
    }
  }

  bool _looksLikeImage(String url) {
    final lower = url.toLowerCase();
    final path = Uri.tryParse(url)?.path.toLowerCase() ?? lower;
    if (path.endsWith('.png') ||
        path.endsWith('.jpg') ||
        path.endsWith('.jpeg') ||
        path.endsWith('.webp') ||
        path.endsWith('.gif') ||
        path.contains('.png') ||
        path.contains('.jpg') ||
        path.contains('.jpeg') ||
        path.contains('.webp') ||
        path.contains('.gif')) {
      return true;
    }
    // Firebase Storage download URL (확장자가 인코딩된 경로에 있음)
    if (lower.contains('firebasestorage.googleapis.com') ||
        lower.contains('alt=media')) {
      return true;
    }
    return lower.startsWith('demo://');
  }

  @override
  Widget build(BuildContext context) {
    final s = submission;
    return SafeArea(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(AppSpace.s(20), AppSpace.s(4), AppSpace.s(20), AppSpace.s(8)),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    '제출 상세',
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                RecordStatusBadge(status: s.status),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: ListView(
              padding: EdgeInsets.fromLTRB(AppSpace.s(20), AppSpace.s(12), AppSpace.s(20), AppSpace.s(16)),
              children: [
                _chip(s.typeLabel),
                SizedBox(height: AppSpace.s(10)),
                Text(
                  s.title,
                  style: const TextStyle(
                    fontSize: 17,
                    fontWeight: FontWeight.w700,
                    height: 1.3,
                  ),
                ),
                SizedBox(height: AppSpace.s(12)),
                if (isAdmin || s.userDisplayName.isNotEmpty)
                  _row('제출자', s.userDisplayName),
                if (s.submittedAt != null)
                  _row(
                    '제출 시각',
                    AppDateUtils.formatDateTime(s.submittedAt!),
                  ),
                if (s.certType != null) _row('자격 종류', s.certType!),
                if (s.quizScore != null) _row('점수', '${s.quizScore}점'),
                if (s.learningDate != null)
                  _row('학습일자', AppDateUtils.formatDisplay(s.learningDate!)),
                if (s.learningContent != null && s.learningContent!.isNotEmpty)
                  _row('학습 내용', s.learningContent!),
                if (s.isTeamStudy != null)
                  _row('팀 스터디', s.isTeamStudy! ? '예' : '아니오 (개인)'),
                if (s.startAt != null || s.endAt != null)
                  _row(
                    '기간',
                    [
                      if (s.startAt != null)
                        AppDateUtils.formatDisplay(s.startAt!),
                      if (s.endAt != null) AppDateUtils.formatDisplay(s.endAt!),
                    ].join(' ~ '),
                  ),
                if (s.weekLabel != null) _row('주차', s.weekLabel!),
                if (s.link != null && s.link!.isNotEmpty) ...[
                  SizedBox(height: AppSpace.s(4)),
                  Text(
                    '링크',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: AppColors.textSecondary,
                    ),
                  ),
                  SizedBox(height: AppSpace.s(4)),
                  InkWell(
                    onTap: () => _openUrl(context, s.link!),
                    child: Text(
                      s.link!,
                      style: TextStyle(
                        fontSize: 13,
                        color: AppColors.primary,
                        decoration: TextDecoration.underline,
                      ),
                    ),
                  ),
                ],
                if (s.mileageAmount > 0) _row('적립', '${s.mileageAmount}M'),
                if (s.reviewComment != null && s.reviewComment!.isNotEmpty)
                  _row('리뷰 코멘트', s.reviewComment!),
                if (s.fileUrls.isNotEmpty) ...[
                  SizedBox(height: AppSpace.s(14)),
                  Text(
                    '증빙 파일 (${s.fileUrls.length})',
                    style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  SizedBox(height: AppSpace.s(8)),
                  ...s.fileUrls.asMap().entries.map((e) {
                    final i = e.key;
                    final url = e.value;
                    final isImage = _looksLikeImage(url);
                    return Padding(
                      padding: EdgeInsets.only(bottom: AppSpace.s(10)),
                      child: Material(
                        color: AppColors.surfaceVariant,
                        borderRadius: BorderRadius.circular(10),
                        clipBehavior: Clip.antiAlias,
                        child: InkWell(
                          onTap: url.startsWith('demo://')
                              ? null
                              : () => _openUrl(context, url),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              if (isImage && !url.startsWith('demo://'))
                                AspectRatio(
                                  aspectRatio: 16 / 10,
                                  child: Image.network(
                                    url,
                                    fit: BoxFit.contain,
                                    gaplessPlayback: true,
                                    webHtmlElementStrategy: kIsWeb
                                        ? WebHtmlElementStrategy.prefer
                                        : WebHtmlElementStrategy.never,
                                    loadingBuilder: (context, child, progress) {
                                      if (progress == null) return child;
                                      return const Center(
                                        child: SizedBox(
                                          width: 22,
                                          height: 22,
                                          child: CircularProgressIndicator(
                                            strokeWidth: 2,
                                          ),
                                        ),
                                      );
                                    },
                                    errorBuilder: (_, _, _) => Padding(
                                      padding: EdgeInsets.all(AppSpace.s(16)),
                                      child: Column(
                                        mainAxisAlignment:
                                            MainAxisAlignment.center,
                                        children: [
                                          Icon(
                                            Icons.broken_image_outlined,
                                            color: AppColors.textHint,
                                          ),
                                          SizedBox(height: AppSpace.s(8)),
                                          TextButton.icon(
                                            onPressed: () =>
                                                _openUrl(context, url),
                                            icon: const Icon(
                                              Icons.open_in_new,
                                              size: 16,
                                            ),
                                            label: const Text('새 탭에서 열기'),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ),
                                )
                              else
                                Padding(
                                  padding: EdgeInsets.all(AppSpace.s(14)),
                                  child: Row(
                                    children: [
                                      Icon(
                                        isImage
                                            ? Icons.image_outlined
                                            : Icons.attach_file,
                                        size: 20,
                                        color: AppColors.textSecondary,
                                      ),
                                      SizedBox(width: AppSpace.s(8)),
                                      Expanded(
                                        child: Text(
                                          url.startsWith('demo://')
                                              ? '데모 파일 ${i + 1}'
                                              : '파일 ${i + 1} · 탭하여 열기',
                                          style: const TextStyle(fontSize: 13),
                                        ),
                                      ),
                                      if (!url.startsWith('demo://'))
                                        Icon(
                                          Icons.open_in_new,
                                          size: 16,
                                          color: AppColors.textHint,
                                        ),
                                    ],
                                  ),
                                ),
                            ],
                          ),
                        ),
                      ),
                    );
                  }),
                ],
                if (s.fileUrls.isEmpty &&
                    (s.link == null || s.link!.isEmpty) &&
                    s.type != RecordTypes.blog)
                  Padding(
                    padding: EdgeInsets.only(top: AppSpace.s(8)),
                    child: Text(
                      '첨부된 증빙이 없습니다.',
                      style: TextStyle(
                        fontSize: 12,
                        color: AppColors.textHint,
                      ),
                    ),
                  ),
              ],
            ),
          ),
          if (isAdmin && s.isPending)
            Padding(
              padding: EdgeInsets.fromLTRB(AppSpace.s(16), AppSpace.s(8), AppSpace.s(16), AppSpace.s(12)),
              child: Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () => Navigator.pop(context, 'rejected'),
                      child: const Text('반려'),
                    ),
                  ),
                  SizedBox(width: AppSpace.s(10)),
                  Expanded(
                    child: FilledButton(
                      onPressed: () => Navigator.pop(context, 'approved'),
                      style: FilledButton.styleFrom(
                        backgroundColor: AppColors.success,
                      ),
                      child: const Text('승인'),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _chip(String label) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        padding: EdgeInsets.symmetric(horizontal: AppSpace.s(8), vertical: AppSpace.s(3)),
        decoration: BoxDecoration(
          color: AppColors.surfaceVariant,
          borderRadius: BorderRadius.circular(6),
        ),
        child: Text(label, style: const TextStyle(fontSize: 11)),
      ),
    );
  }

  Widget _row(String label, String value) {
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpace.s(8)),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 78,
            child: Text(
              label,
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: AppColors.textSecondary,
              ),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(fontSize: 13, height: 1.35),
            ),
          ),
        ],
      ),
    );
  }
}
