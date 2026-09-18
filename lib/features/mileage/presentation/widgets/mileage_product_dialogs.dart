import 'package:flutter/material.dart';

import '../../../../core/constants/mileage_constants.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../shared/models/mileage_models.dart';
import '../../theme/mileage_theme.dart';
import '../../../../core/theme/app_space.dart';

/// 고정가 상품 — 수량 선택 후 장바구니
Future<void> showFixedProductDialog(
  BuildContext context, {
  required MileageProductModel product,
  required Future<void> Function(int quantity) onAdd,
}) async {
  var quantity = 1;
  await showDialog<void>(
    context: context,
    builder: (ctx) => StatefulBuilder(
      builder: (ctx, setState) => AlertDialog(
        title: Text(product.name),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              formatMileageM(product.fixedPrice ?? 0),
              style: TextStyle(
                fontWeight: FontWeight.bold,
                color: MileageColors.primary,
                fontSize: 18,
              ),
            ),
            SizedBox(height: AppSpace.s(16)),
            Row(
              children: [
                const Text('수량'),
                const Spacer(),
                IconButton(
                  onPressed: quantity > 1
                      ? () => setState(() => quantity--)
                      : null,
                  icon: const Icon(Icons.remove_circle_outline),
                ),
                Text('$quantity', style: const TextStyle(fontSize: 16)),
                IconButton(
                  onPressed: () => setState(() => quantity++),
                  icon: const Icon(Icons.add_circle_outline),
                ),
              ],
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('취소'),
          ),
          FilledButton(
            style: mileagePrimaryButtonStyle(),
            onPressed: () async {
              Navigator.pop(ctx);
              await onAdd(quantity);
            },
            child: const Text('장바구니에 담기'),
          ),
        ],
      ),
    ),
  );
}

/// 인프런 / yes24 — 링크 + 가격 직접 입력
Future<void> showCustomProductDialog(
  BuildContext context, {
  required MileageProductModel product,
  required MileageCategoryUsageModel usage,
  required int mileageBalance,
  required Future<void> Function(String link, int price) onAdd,
}) {
  return showDialog<void>(
    context: context,
    builder: (ctx) => _CustomProductDialog(
      product: product,
      usage: usage,
      mileageBalance: mileageBalance,
      onAdd: onAdd,
    ),
  );
}

class _CustomProductDialog extends StatefulWidget {
  const _CustomProductDialog({
    required this.product,
    required this.usage,
    required this.mileageBalance,
    required this.onAdd,
  });

  final MileageProductModel product;
  final MileageCategoryUsageModel usage;
  final int mileageBalance;
  final Future<void> Function(String link, int price) onAdd;

  @override
  State<_CustomProductDialog> createState() => _CustomProductDialogState();
}

class _CustomProductDialogState extends State<_CustomProductDialog> {
  final _linkController = TextEditingController();
  final _priceController = TextEditingController();
  final _formKey = GlobalKey<FormState>();

  @override
  void dispose() {
    _linkController.dispose();
    _priceController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    final link = _linkController.text.trim();
    final price = int.parse(_priceController.text.trim());
    Navigator.pop(context);
    await widget.onAdd(link, price);
  }

  @override
  Widget build(BuildContext context) {
    final product = widget.product;
    final usage = widget.usage;
    final linkHint = product.category == MileageCategories.onlineCourse
        ? 'https://www.inflearn.com/course/...'
        : 'https://www.yes24.com/...';

    return AlertDialog(
      title: Row(
        children: [
          Container(
            width: 40,
            height: AppSpace.row(40),
            decoration: BoxDecoration(
              color: AppColors.surfaceVariant,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(
              product.category == MileageCategories.onlineCourse
                  ? Icons.play_circle_outline
                  : Icons.menu_book_outlined,
              color: AppColors.textSecondary,
            ),
          ),
          SizedBox(width: AppSpace.s(12)),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  product.name,
                  style: const TextStyle(fontSize: 16),
                ),
                Text(
                  '가격 직접 입력',
                  style: TextStyle(
                    color: MileageColors.primary,
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
          IconButton(
            onPressed: () => Navigator.pop(context),
            icon: const Icon(Icons.close, size: 20),
          ),
        ],
      ),
      content: Form(
        key: _formKey,
        child: SizedBox(
          width: 400,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Container(
                padding: EdgeInsets.all(AppSpace.s(12)),
                decoration: BoxDecoration(
                  color: MileageColors.infoBanner,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: MileageColors.infoBannerBorder),
                ),
                child: Row(
                  children: [
                    Icon(Icons.info_outline, size: 18, color: AppColors.info),
                    SizedBox(width: AppSpace.s(8)),
                    Expanded(
                      child: Text(
                        '${usage.categoryLabel} 잔여 한도: '
                        '${formatMileageM(usage.remaining)} / ${formatMileageM(usage.limit)}',
                        style: const TextStyle(fontSize: 13),
                      ),
                    ),
                  ],
                ),
              ),
              SizedBox(height: AppSpace.s(16)),
              TextFormField(
                controller: _linkController,
                decoration: InputDecoration(
                  labelText: product.category == MileageCategories.onlineCourse
                      ? '강의 링크'
                      : '도서 링크',
                  hintText: linkHint,
                  border: const OutlineInputBorder(),
                ),
                validator: (v) {
                  if (v == null || v.trim().isEmpty) return '링크를 입력해 주세요.';
                  if (!v.startsWith('http')) return '올바른 URL을 입력해 주세요.';
                  return null;
                },
              ),
              SizedBox(height: AppSpace.s(12)),
              TextFormField(
                controller: _priceController,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: '가격 (M)',
                  hintText: '예) 66000',
                  border: OutlineInputBorder(),
                ),
                validator: (v) {
                  final price = int.tryParse(v?.trim() ?? '');
                  if (price == null || price <= 0) {
                    return '올바른 가격을 입력해 주세요.';
                  }
                  if (price > usage.remaining) {
                    return '카테고리 잔여 한도를 초과합니다.';
                  }
                  if (price > widget.mileageBalance) {
                    return '마일리지 잔액이 부족합니다.';
                  }
                  return null;
                },
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('취소'),
        ),
        FilledButton(
          style: mileagePrimaryButtonStyle(),
          onPressed: _submit,
          child: const Text('장바구니에 담기'),
        ),
      ],
    );
  }
}
