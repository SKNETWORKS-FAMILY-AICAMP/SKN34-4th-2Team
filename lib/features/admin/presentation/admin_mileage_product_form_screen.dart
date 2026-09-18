import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/constants/mileage_constants.dart';
import '../../../core/widgets/app_dropdown.dart';
import '../../../shared/models/mileage_models.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/mileage_providers.dart';
import '../../mileage/theme/mileage_theme.dart';
import 'widgets/admin_page_layout.dart';
import '../../../core/theme/app_space.dart';

/// 관리자 — 마일리지 상품 등록/수정 폼
class AdminMileageProductFormScreen extends ConsumerStatefulWidget {
  const AdminMileageProductFormScreen({super.key, this.productId});

  final String? productId;

  bool get isEditing => productId != null && productId!.isNotEmpty;

  @override
  ConsumerState<AdminMileageProductFormScreen> createState() =>
      _AdminMileageProductFormScreenState();
}

class _AdminMileageProductFormScreenState
    extends ConsumerState<AdminMileageProductFormScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _descriptionController = TextEditingController();
  final _imageUrlController = TextEditingController();
  final _fixedPriceController = TextEditingController();
  final _sortOrderController = TextEditingController(text: '0');

  String _category = MileageCategories.gifticon;
  String _pricingType = MileagePricingTypes.fixed;
  bool _isActive = true;
  bool _loaded = false;
  bool _saving = false;

  @override
  void dispose() {
    _nameController.dispose();
    _descriptionController.dispose();
    _imageUrlController.dispose();
    _fixedPriceController.dispose();
    _sortOrderController.dispose();
    super.dispose();
  }

  void _loadProduct(MileageProductModel product) {
    if (_loaded) return;
    _loaded = true;
    _nameController.text = product.name;
    _descriptionController.text = product.description;
    _imageUrlController.text = product.imageUrl ?? '';
    _fixedPriceController.text = product.fixedPrice?.toString() ?? '';
    _sortOrderController.text = product.sortOrder.toString();
    _category = product.category;
    _pricingType = product.pricingType;
    _isActive = product.isActive;
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;

    final cohortId = ref.read(effectiveCohortIdProvider);
    if (cohortId == null) return;

    setState(() => _saving = true);
    try {
      final product = MileageProductModel(
        id: widget.productId ?? '',
        name: _nameController.text.trim(),
        description: _descriptionController.text.trim(),
        imageUrl: _imageUrlController.text.trim().isEmpty
            ? null
            : _imageUrlController.text.trim(),
        category: _category,
        pricingType: _pricingType,
        fixedPrice: _pricingType == MileagePricingTypes.fixed
            ? int.tryParse(_fixedPriceController.text.trim())
            : null,
        isActive: _isActive,
        sortOrder: int.tryParse(_sortOrderController.text.trim()) ?? 0,
      );

      await ref.read(mileageRepositoryProvider).saveMileageProduct(
            cohortId: cohortId,
            product: product,
          );

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(widget.isEditing ? '상품이 수정되었습니다.' : '상품이 등록되었습니다.'),
          ),
        );
        context.pop();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('저장 실패: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (widget.isEditing) {
      final products = ref.watch(allMileageProductsProvider).value ?? [];
      final product = products.where((p) => p.id == widget.productId).firstOrNull;
      if (product != null) _loadProduct(product);
    }

    return adminPageWrapper(
      child: Form(
        key: _formKey,
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  IconButton(
                    visualDensity: VisualDensity.compact,
                    onPressed: () => context.pop(),
                    icon: const Icon(Icons.arrow_back, size: 20),
                  ),
                  Text(
                    widget.isEditing ? '상품 수정' : '상품 등록',
                    style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ],
              ),
              SizedBox(height: AppSpace.s(12)),
            AdminFormSection(
              title: '기본 정보',
              children: [
                TextFormField(
                  controller: _nameController,
                  decoration: const InputDecoration(labelText: '상품명 *', border: OutlineInputBorder()),
                  validator: (v) =>
                      v == null || v.trim().isEmpty ? '상품명을 입력해 주세요.' : null,
                ),
                SizedBox(height: AppSpace.s(12)),
                TextFormField(
                  controller: _descriptionController,
                  decoration: const InputDecoration(labelText: '설명', border: OutlineInputBorder()),
                  maxLines: 2,
                ),
                SizedBox(height: AppSpace.s(12)),
                TextFormField(
                  controller: _imageUrlController,
                  decoration: const InputDecoration(labelText: '이미지 URL', border: OutlineInputBorder()),
                ),
              ],
            ),
            AdminFormSection(
              title: '가격 · 카테고리',
              children: [
                AppDropdownField<String>(
                  value: _category,
                  decoration: const InputDecoration(
                    labelText: '카테고리',
                    border: OutlineInputBorder(),
                  ),
                  items: [
                    for (final c in MileageCategories.all)
                      AppDropdownItem(
                        value: c,
                        label: MileageCategories.labelOf(c),
                      ),
                  ],
                  onChanged: (v) => setState(() => _category = v ?? _category),
                ),
                SizedBox(height: AppSpace.s(12)),
                AppDropdownField<String>(
                  value: _pricingType,
                  decoration: const InputDecoration(
                    labelText: '가격 유형',
                    border: OutlineInputBorder(),
                  ),
                  items: const [
                    AppDropdownItem(
                      value: MileagePricingTypes.fixed,
                      label: '고정가',
                    ),
                    AppDropdownItem(
                      value: MileagePricingTypes.custom,
                      label: '가격 직접 입력',
                    ),
                  ],
                  onChanged: (v) =>
                      setState(() => _pricingType = v ?? _pricingType),
                ),
                if (_pricingType == MileagePricingTypes.fixed) ...[
                  SizedBox(height: AppSpace.s(12)),
                  TextFormField(
                    controller: _fixedPriceController,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: '고정가 (M) *',
                      border: OutlineInputBorder(),
                    ),
                    validator: (v) {
                      if (_pricingType != MileagePricingTypes.fixed) return null;
                      final n = int.tryParse(v?.trim() ?? '');
                      if (n == null || n <= 0) return '올바른 가격을 입력해 주세요.';
                      return null;
                    },
                  ),
                ],
              ],
            ),
            AdminFormSection(
              title: '표시 설정',
              children: [
                TextFormField(
                  controller: _sortOrderController,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(labelText: '정렬 순서', border: OutlineInputBorder()),
                ),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('활성'),
                  subtitle: const Text('비활성 상품은 학생 교환소에 표시되지 않습니다.'),
                  value: _isActive,
                  onChanged: (v) => setState(() => _isActive = v),
                ),
              ],
            ),
            SizedBox(height: AppSpace.s(8)),
            FilledButton(
              style: mileagePrimaryButtonStyle(minHeight: 40),
              onPressed: _saving ? null : _save,
              child: _saving
                  ? const SizedBox(
                      height: 18,
                      width: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : Text(widget.isEditing ? '수정 저장' : '등록'),
            ),
          ],
        ),
      ),
      ),
    );
  }
}
