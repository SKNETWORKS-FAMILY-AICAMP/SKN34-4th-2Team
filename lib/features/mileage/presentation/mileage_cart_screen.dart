import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/constants/mileage_constants.dart';
import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_layout.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/models/mileage_models.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/mileage_providers.dart';
import '../theme/mileage_theme.dart';
import '../../../core/theme/app_space.dart';

/// 마일리지 장바구니 → 구매 요청
class MileageCartScreen extends ConsumerStatefulWidget {
  const MileageCartScreen({super.key});

  @override
  ConsumerState<MileageCartScreen> createState() => _MileageCartScreenState();
}

class _MileageCartScreenState extends ConsumerState<MileageCartScreen> {
  static const _contentMaxWidth = AppLayout.narrow;

  bool _submitting = false;

  String _errorMessage(Object e) {
    if (e is FirebaseFunctionsException) {
      final msg = e.message?.trim();
      if (msg != null && msg.isNotEmpty) return msg;
      return '요청에 실패했습니다. (${e.code})';
    }
    return '$e';
  }

  Future<void> _submit() async {
    final cohortId = ref.read(effectiveCohortIdProvider);
    final user = ref.read(currentUserSyncProvider);
    if (cohortId == null || user == null) return;

    final cart = ref.read(mileageCartProvider).value;
    if (cart == null || cart.isEmpty) return;

    if (user.mileageBalance < cart.totalAmount) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            '마일리지 잔액이 부족합니다. '
            '(잔액: ${formatMileageM(user.mileageBalance)}, '
            '필요: ${formatMileageM(cart.totalAmount)})',
          ),
        ),
      );
      return;
    }

    setState(() => _submitting = true);
    try {
      await ref
          .read(mileageFunctionsServiceProvider)
          .submitPurchaseRequest(
            cohortId: cohortId,
          );

      ref.read(mileageMainTabProvider.notifier).showRequests();
      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('구매 요청이 접수되었습니다.')),
      );
      context.go(RoutePaths.mileage);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(_errorMessage(e))),
        );
      }
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  Future<void> _removeItem(int index) async {
    final cohortId = ref.read(effectiveCohortIdProvider);
    final user = ref.read(currentUserSyncProvider);
    if (cohortId == null || user == null) return;

    final cart = ref.read(mileageCartProvider).value;
    if (cart == null) return;

    final items = [...cart.items]..removeAt(index);
    await ref
        .read(mileageRepositoryProvider)
        .saveMileageCart(
          cohortId: cohortId,
          userId: user.uid,
          items: items,
        );
  }

  @override
  Widget build(BuildContext context) {
    final cartAsync = ref.watch(mileageCartProvider);
    final balance = ref.watch(currentUserSyncProvider)?.mileageBalance ?? 0;

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.background,
        title: const Text('장바구니'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.pop(),
        ),
      ),
      body: cartAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => ErrorView(message: e.toString()),
        data: (cart) {
          if (cart.isEmpty) {
            return Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: _contentMaxWidth),
                child: Padding(
                  padding: EdgeInsets.symmetric(horizontal: AppSpace.s(24)),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        Icons.shopping_cart_outlined,
                        size: 40,
                        color: AppColors.textHint.withValues(alpha: 0.7),
                      ),
                      SizedBox(height: AppSpace.s(12)),
                      Text(
                        '장바구니가 비어 있습니다.',
                        style: TextStyle(
                          color: AppColors.textSecondary,
                          fontSize: 14,
                        ),
                      ),
                      SizedBox(height: AppSpace.s(20)),
                      FilledButton(
                        style: mileagePrimaryButtonStyle(),
                        onPressed: () => context.pop(),
                        child: const Text('교환소로 돌아가기'),
                      ),
                    ],
                  ),
                ),
              ),
            );
          }

          final insufficient = balance < cart.totalAmount;

          return Align(
            alignment: Alignment.topCenter,
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: _contentMaxWidth),
              child: Column(
                children: [
                  Expanded(
                    child: ListView.separated(
                      padding: EdgeInsets.fromLTRB(AppSpace.s(20), AppSpace.s(8), AppSpace.s(20), AppSpace.s(16)),
                      itemCount: cart.items.length,
                      separatorBuilder: (_, _) => SizedBox(height: AppSpace.s(8)),
                      itemBuilder: (_, i) => _CartItemRow(
                        item: cart.items[i],
                        onRemove: () => _removeItem(i),
                      ),
                    ),
                  ),
                  _CartCheckoutBar(
                    balance: balance,
                    total: cart.totalAmount,
                    insufficient: insufficient,
                    submitting: _submitting,
                    onSubmit: _submit,
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

class _CartItemRow extends StatelessWidget {
  const _CartItemRow({
    required this.item,
    required this.onRemove,
  });

  final MileageCartItemModel item;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    final tagColor = MileageColors.categoryTagColor(item.category);

    return Container(
      padding: EdgeInsets.fromLTRB(AppSpace.s(14), AppSpace.s(12), AppSpace.s(6), AppSpace.s(12)),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.border),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item.productName,
                  style: TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 14,
                    color: AppColors.textPrimary,
                    height: 1.3,
                  ),
                ),
                SizedBox(height: AppSpace.s(6)),
                Row(
                  children: [
                    Container(
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpace.s(7),
                        vertical: AppSpace.s(2),
                      ),
                      decoration: BoxDecoration(
                        color: tagColor.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text(
                        MileageCategories.labelOf(item.category),
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                          color: tagColor,
                        ),
                      ),
                    ),
                    SizedBox(width: AppSpace.s(8)),
                    Text(
                      '수량 ${item.quantity}',
                      style: TextStyle(
                        fontSize: 12,
                        color: AppColors.textSecondary,
                      ),
                    ),
                  ],
                ),
                if (item.purchaseLink != null &&
                    item.purchaseLink!.isNotEmpty) ...[
                  SizedBox(height: AppSpace.s(6)),
                  Text(
                    item.purchaseLink!,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 11,
                      color: AppColors.textHint,
                    ),
                  ),
                ],
              ],
            ),
          ),
          SizedBox(width: AppSpace.s(8)),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Padding(
                padding: EdgeInsets.only(right: AppSpace.s(6), top: AppSpace.s(2)),
                child: Text(
                  formatMileageM(item.subtotal),
                  style: TextStyle(
                    fontWeight: FontWeight.w800,
                    fontSize: 14,
                    color: AppColors.textPrimary,
                  ),
                ),
              ),
              IconButton(
                visualDensity: VisualDensity.compact,
                tooltip: '삭제',
                onPressed: onRemove,
                icon: Icon(
                  Icons.delete_outline,
                  size: 18,
                  color: AppColors.error,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _CartCheckoutBar extends StatelessWidget {
  const _CartCheckoutBar({
    required this.balance,
    required this.total,
    required this.insufficient,
    required this.submitting,
    required this.onSubmit,
  });

  final int balance;
  final int total;
  final bool insufficient;
  final bool submitting;
  final VoidCallback onSubmit;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.fromLTRB(AppSpace.s(20), AppSpace.s(14), AppSpace.s(20), AppSpace.s(20)),
      decoration: BoxDecoration(
        color: AppColors.surface,
        border: Border(top: BorderSide(color: AppColors.border)),
        boxShadow: [
          BoxShadow(
            color: AppColors.shadow.withValues(alpha: 0.06),
            blurRadius: 16,
            offset: const Offset(0, -4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _SummaryLine(
            label: '내 잔액',
            value: formatMileageM(balance),
          ),
          SizedBox(height: AppSpace.s(6)),
          _SummaryLine(
            label: '합계',
            value: formatMileageM(total),
            emphasize: true,
          ),
          if (insufficient) ...[
            SizedBox(height: AppSpace.s(10)),
            Container(
              padding: EdgeInsets.symmetric(horizontal: AppSpace.s(10), vertical: AppSpace.s(8)),
              decoration: BoxDecoration(
                color: AppColors.error.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Text(
                '잔액이 ${formatMileageM(total - balance)} 부족합니다.',
                style: TextStyle(
                  color: AppColors.error,
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ],
          SizedBox(height: AppSpace.s(12)),
          FilledButton(
            style: mileagePrimaryButtonStyle(minHeight: AppSpace.row(42)),
            onPressed: (submitting || insufficient) ? null : onSubmit,
            child: submitting
                ? SizedBox(
                    height: 18,
                    width: 18,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Colors.white,
                    ),
                  )
                : Text(insufficient ? '잔액 부족' : '구매 요청하기'),
          ),
        ],
      ),
    );
  }
}

class _SummaryLine extends StatelessWidget {
  const _SummaryLine({
    required this.label,
    required this.value,
    this.emphasize = false,
  });

  final String label;
  final String value;
  final bool emphasize;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          label,
          style: TextStyle(
            fontSize: emphasize ? 14 : 13,
            fontWeight: emphasize ? FontWeight.w700 : FontWeight.w500,
            color: AppColors.textSecondary,
          ),
        ),
        Text(
          value,
          style: TextStyle(
            fontSize: emphasize ? 17 : 13,
            fontWeight: emphasize ? FontWeight.w800 : FontWeight.w600,
            color: emphasize ? MileageColors.primary : AppColors.textPrimary,
          ),
        ),
      ],
    );
  }
}
