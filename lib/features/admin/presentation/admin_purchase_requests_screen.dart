import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../core/constants/mileage_constants.dart';
import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/utils/date_utils.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/models/mileage_models.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/mileage_providers.dart';
import '../../mileage/presentation/widgets/mileage_widgets.dart';
import '../../mileage/theme/mileage_theme.dart';
import 'widgets/admin_page_layout.dart';
import '../../../core/theme/app_space.dart';

/// 관리자 — 구매 요청 처리
class AdminPurchaseRequestsScreen extends ConsumerStatefulWidget {
  const AdminPurchaseRequestsScreen({super.key});

  @override
  ConsumerState<AdminPurchaseRequestsScreen> createState() =>
      _AdminPurchaseRequestsScreenState();
}

class _AdminPurchaseRequestsScreenState
    extends ConsumerState<AdminPurchaseRequestsScreen> {
  String _statusFilter = 'all';
  String _categoryFilter = 'all';

  Future<void> _review(
    PurchaseRequestModel request, {
    required String status,
  }) async {
    final cohortId = ref.read(effectiveCohortIdProvider);
    if (cohortId == null) return;

    final memoController = TextEditingController();
    final linkController = TextEditingController(
      text: request.managerPurchaseLink ?? '',
    );

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(_actionTitle(status)),
        content: SizedBox(
          width: 400,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                '${request.userDisplayName} · ${formatMileageM(request.totalAmount)}',
              ),
              SizedBox(height: AppSpace.s(12)),
              TextField(
                controller: memoController,
                decoration: const InputDecoration(
                  labelText: '매니저 메모',
                  border: OutlineInputBorder(),
                ),
                maxLines: 2,
              ),
              if (status == 'approved') ...[
                SizedBox(height: AppSpace.s(12)),
                TextField(
                  controller: linkController,
                  decoration: const InputDecoration(
                    labelText: '구매 링크 (선택)',
                    border: OutlineInputBorder(),
                  ),
                ),
              ],
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('취소'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('확인'),
          ),
        ],
      ),
    );

    final managerMemo = memoController.text.trim();
    final managerPurchaseLink = linkController.text.trim();
    memoController.dispose();
    linkController.dispose();

    if (ok != true || !mounted) return;

    try {
      await ref
          .read(mileageFunctionsServiceProvider)
          .reviewPurchaseRequest(
            cohortId: cohortId,
            requestId: request.id,
            status: status,
            managerMemo: managerMemo.isEmpty ? null : managerMemo,
            managerPurchaseLink: managerPurchaseLink.isEmpty
                ? null
                : managerPurchaseLink,
          );

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('${_actionTitle(status)} 처리되었습니다.')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('처리 실패: $e')),
        );
      }
    }
  }

  String _actionTitle(String status) => switch (status) {
    'approved' => '승인',
    'rejected' => '반려',
    'modify_requested' => '수정 요청',
    _ => status,
  };

  @override
  Widget build(BuildContext context) {
    final requestsAsync = ref.watch(allPurchaseRequestsProvider);

    return adminPageWrapper(
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                IconButton(
                  visualDensity: VisualDensity.compact,
                  onPressed: () => context.go(RoutePaths.adminMileage),
                  icon: const Icon(Icons.arrow_back, size: 20),
                ),
                const Text(
                  '구매 요청 처리',
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                ),
              ],
            ),
            SizedBox(height: AppSpace.s(12)),
            MileageFilterChipRow(
              label: '상태',
              selected: _statusFilter,
              onSelected: (v) => setState(() => _statusFilter = v),
              options: const [
                ('all', '전체'),
                ('pending', '대기'),
                ('approved', '승인'),
                ('modify_requested', '수정 요청'),
                ('rejected', '반려'),
                ('cancelled', '취소'),
              ],
            ),
            SizedBox(height: AppSpace.s(8)),
            MileageFilterChipRow(
              label: '상품 타입',
              selected: _categoryFilter,
              onSelected: (v) => setState(() => _categoryFilter = v),
              options: const [
                ('all', '전체'),
                ('gifticon', '기프티콘'),
                ('book', '도서'),
                ('onlineCourse', '인터넷 강의'),
              ],
            ),
            SizedBox(height: AppSpace.s(16)),
            requestsAsync.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => ErrorView(message: e.toString()),
              data: (requests) {
                var filtered = requests;
                if (_statusFilter != 'all') {
                  filtered = filtered
                      .where((r) => r.status == _statusFilter)
                      .toList();
                }
                if (_categoryFilter != 'all') {
                  filtered = filtered
                      .where(
                        (r) =>
                            r.items.any((i) => i.category == _categoryFilter),
                      )
                      .toList();
                }

                if (filtered.isEmpty) {
                  return Padding(
                    padding: EdgeInsets.all(AppSpace.s(32)),
                    child: Center(child: Text('구매 요청이 없습니다')),
                  );
                }

                return Column(
                  children: filtered
                      .map(
                        (req) => Padding(
                          padding: EdgeInsets.only(bottom: AppSpace.s(12)),
                          child: _AdminRequestCard(
                            request: req,
                            onReview: _review,
                          ),
                        ),
                      )
                      .toList(),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _AdminRequestCard extends StatelessWidget {
  const _AdminRequestCard({
    required this.request,
    required this.onReview,
  });

  final PurchaseRequestModel request;
  final Future<void> Function(
    PurchaseRequestModel request, {
    required String status,
  })
  onReview;

  @override
  Widget build(BuildContext context) {
    final category = request.primaryCategory ?? MileageCategories.gifticon;
    final canProcess =
        request.status == PurchaseRequestStatus.pending ||
        request.status == PurchaseRequestStatus.modifyRequested;
    final studentLinks = request.items
        .map((e) => e.purchaseLink?.trim())
        .whereType<String>()
        .where((e) => e.isNotEmpty)
        .toList();

    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: EdgeInsets.all(AppSpace.s(12)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                MileageTagChip(
                  label: request.statusLabel,
                  color: MileageColors.statusColor(request.status),
                ),
                SizedBox(width: AppSpace.s(6)),
                MileageTagChip(
                  label: MileageCategories.labelOf(category),
                  color: MileageColors.categoryTagColor(category),
                ),
                const Spacer(),
                Text(
                  request.userDisplayName,
                  style: const TextStyle(
                    fontWeight: FontWeight.w600,
                    fontSize: 13,
                  ),
                ),
              ],
            ),
            SizedBox(height: AppSpace.s(6)),
            Text(
              request.primaryProductName,
              style: const TextStyle(fontSize: 14, fontWeight: FontWeight.bold),
            ),
            SizedBox(height: AppSpace.s(6)),
            Text(
              '신청 금액: ${formatMileageM(request.totalAmount)}',
              style: const TextStyle(fontSize: 13),
            ),
            SizedBox(height: AppSpace.s(4)),
            Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                if (request.createdAt != null)
                  Text(
                    '신청일: ${AppDateUtils.formatDetailDateTime(request.createdAt!)}',
                    style: TextStyle(
                      color: AppColors.textSecondary,
                      fontSize: 12,
                    ),
                  ),
                if (studentLinks.isNotEmpty) ...[
                  SizedBox(width: AppSpace.s(12)),
                  Expanded(
                    child: Align(
                      alignment: Alignment.centerRight,
                      child: Wrap(
                        spacing: 8,
                        runSpacing: 2,
                        alignment: WrapAlignment.end,
                        children: [
                          for (final link in studentLinks)
                            _StudentLinkButton(url: link),
                        ],
                      ),
                    ),
                  ),
                ] else
                  const Spacer(),
              ],
            ),
            if (request.managerMemo != null && request.managerMemo!.isNotEmpty)
              Text('메모: ${request.managerMemo}'),
            if (canProcess) ...[
              SizedBox(height: AppSpace.s(10)),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: [
                  FilledButton(
                    style: FilledButton.styleFrom(
                      backgroundColor: AppColors.success,
                      minimumSize: const Size(0, 32),
                      padding: EdgeInsets.symmetric(horizontal: AppSpace.s(12)),
                      textStyle: const TextStyle(fontSize: 12),
                    ),
                    onPressed: () => onReview(
                      request,
                      status: PurchaseRequestStatus.approved,
                    ),
                    child: const Text('승인'),
                  ),
                  OutlinedButton(
                    style: mileageOutlinedButtonStyle(),
                    onPressed: () => onReview(
                      request,
                      status: PurchaseRequestStatus.modifyRequested,
                    ),
                    child: const Text('수정 요청'),
                  ),
                  OutlinedButton(
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppColors.error,
                      minimumSize: const Size(0, 32),
                      padding: EdgeInsets.symmetric(horizontal: AppSpace.s(12)),
                      textStyle: const TextStyle(fontSize: 12),
                    ),
                    onPressed: () => onReview(
                      request,
                      status: PurchaseRequestStatus.rejected,
                    ),
                    child: const Text('반려'),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _StudentLinkButton extends StatelessWidget {
  const _StudentLinkButton({required this.url});

  final String url;

  Future<void> _open(BuildContext context) async {
    final uri = Uri.tryParse(url);
    if (uri == null) return;
    final ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('링크를 열 수 없습니다.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: () => _open(context),
      borderRadius: BorderRadius.circular(4),
      child: Padding(
        padding: EdgeInsets.symmetric(vertical: AppSpace.s(2)),
        child: Text.rich(
          TextSpan(
            style: TextStyle(fontSize: 12, color: AppColors.info),
            children: [
              const TextSpan(text: '학생 링크: '),
              TextSpan(
                text: url,
                style: TextStyle(
                  decoration: TextDecoration.underline,
                  decorationColor: AppColors.info,
                ),
              ),
            ],
          ),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          textAlign: TextAlign.right,
        ),
      ),
    );
  }
}
