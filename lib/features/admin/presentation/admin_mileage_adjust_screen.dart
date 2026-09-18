import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/utils/date_utils.dart';
import '../../../core/widgets/app_dropdown.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/models/user_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../../shared/providers/mileage_providers.dart';
import '../../mileage/theme/mileage_theme.dart';
import 'widgets/admin_page_layout.dart';
import '../../../core/theme/app_space.dart';

/// 관리자 — 마일리지 수동 지급/차감
class AdminMileageAdjustScreen extends ConsumerStatefulWidget {
  const AdminMileageAdjustScreen({super.key});

  @override
  ConsumerState<AdminMileageAdjustScreen> createState() =>
      _AdminMileageAdjustScreenState();
}

class _AdminMileageAdjustScreenState
    extends ConsumerState<AdminMileageAdjustScreen> {
  UserModel? _selectedStudent;
  final _amountController = TextEditingController();
  final _reasonController = TextEditingController();
  final _searchController = TextEditingController();
  String _searchQuery = '';
  bool _isGrant = true;
  bool _submitting = false;

  @override
  void dispose() {
    _amountController.dispose();
    _reasonController.dispose();
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final cohortId = ref.read(effectiveCohortIdProvider);
    final student = _selectedStudent;
    if (cohortId == null || student == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('학생을 선택해 주세요.')),
      );
      return;
    }

    final amountRaw = int.tryParse(_amountController.text.trim());
    if (amountRaw == null || amountRaw <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('올바른 금액을 입력해 주세요.')),
      );
      return;
    }

    final reason = _reasonController.text.trim();
    if (reason.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('사유를 입력해 주세요.')),
      );
      return;
    }

    final amount = _isGrant ? amountRaw : -amountRaw;

    setState(() => _submitting = true);
    try {
      await ref
          .read(mileageFunctionsServiceProvider)
          .adjustMileage(
            cohortId: cohortId,
            userId: student.uid,
            amount: amount,
            reason: reason,
          );

      _amountController.clear();
      _reasonController.clear();

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              _isGrant ? '마일리지를 지급했습니다.' : '마일리지를 차감했습니다.',
            ),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('처리 실패: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final studentsAsync = ref.watch(cohortStudentsProvider);
    final transactionsAsync = ref.watch(adminRecentMileageTransactionsProvider);

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
                  '마일리지 지급/차감',
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                ),
              ],
            ),
            SizedBox(height: AppSpace.s(16)),
            AdminFormSection(
              title: '학생 선택',
              children: [
                TextField(
                  controller: _searchController,
                  decoration: const InputDecoration(
                    labelText: '학생 검색 (이름)',
                    border: OutlineInputBorder(),
                    prefixIcon: Icon(Icons.search),
                  ),
                  onChanged: (v) => setState(() => _searchQuery = v.trim()),
                ),
                SizedBox(height: AppSpace.s(12)),
                studentsAsync.when(
                  loading: () => const LinearProgressIndicator(),
                  error: (e, _) => Text(e.toString()),
                  data: (students) {
                    final filtered = students.where((s) {
                      if (_searchQuery.isEmpty) return true;
                      return s.displayName.toLowerCase().contains(
                        _searchQuery.toLowerCase(),
                      );
                    }).toList();

                    if (_searchQuery.isNotEmpty) {
                      if (filtered.isEmpty) {
                        return Padding(
                          padding: EdgeInsets.symmetric(
                            vertical: AppSpace.s(8),
                          ),
                          child: const Text('검색 결과가 없습니다.'),
                        );
                      }
                      return Container(
                        constraints: const BoxConstraints(maxHeight: 240),
                        decoration: BoxDecoration(
                          color: AppColors.surface,
                          border: Border.all(color: AppColors.border),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: ListView.separated(
                          shrinkWrap: true,
                          padding: EdgeInsets.symmetric(
                            vertical: AppSpace.s(4),
                          ),
                          itemCount: filtered.length,
                          separatorBuilder: (_, _) => Divider(
                            height: 1,
                            color: AppColors.border,
                          ),
                          itemBuilder: (_, index) {
                            final student = filtered[index];
                            final selected =
                                _selectedStudent?.uid == student.uid;
                            return ListTile(
                              dense: true,
                              selected: selected,
                              selectedTileColor: AppColors.primaryLight,
                              leading: CircleAvatar(
                                radius: 16,
                                backgroundColor: AppColors.primaryLight,
                                child: Text(
                                  student.displayName.isEmpty
                                      ? '?'
                                      : student.displayName.substring(0, 1),
                                  style: TextStyle(
                                    color: AppColors.primary,
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                              ),
                              title: Text(
                                student.displayName,
                                style: const TextStyle(
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              trailing: Text(
                                formatMileageM(student.mileageBalance),
                                style: TextStyle(
                                  color: AppColors.textSecondary,
                                ),
                              ),
                              onTap: () => setState(() {
                                _selectedStudent = student;
                                _searchController.clear();
                                _searchQuery = '';
                              }),
                            );
                          },
                        ),
                      );
                    }

                    if (students.isEmpty) {
                      return const Text('학생이 없습니다.');
                    }

                    return AppDropdownField<String>(
                      value:
                          _selectedStudent != null &&
                              students.any(
                                (s) => s.uid == _selectedStudent!.uid,
                              )
                          ? _selectedStudent!.uid
                          : null,
                      decoration: const InputDecoration(
                        labelText: '학생 *',
                        border: OutlineInputBorder(),
                      ),
                      items: [
                        for (final s in students)
                          AppDropdownItem(
                            value: s.uid,
                            label:
                                '${s.displayName} (${formatMileageM(s.mileageBalance)})',
                          ),
                      ],
                      onChanged: (uid) {
                        if (uid == null) return;
                        setState(() {
                          _selectedStudent = students.firstWhere(
                            (s) => s.uid == uid,
                          );
                        });
                      },
                    );
                  },
                ),
              ],
            ),
            AdminFormSection(
              title: '지급/차감',
              children: [
                SegmentedButton<bool>(
                  segments: const [
                    ButtonSegment(value: true, label: Text('지급')),
                    ButtonSegment(value: false, label: Text('차감')),
                  ],
                  selected: {_isGrant},
                  style: const ButtonStyle(
                    visualDensity: VisualDensity.compact,
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  ),
                  onSelectionChanged: (s) => setState(() => _isGrant = s.first),
                ),
                SizedBox(height: AppSpace.s(12)),
                TextField(
                  controller: _amountController,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(
                    labelText: '금액 (M) *',
                    border: OutlineInputBorder(),
                  ),
                ),
                SizedBox(height: AppSpace.s(12)),
                TextField(
                  controller: _reasonController,
                  decoration: const InputDecoration(
                    labelText: '사유 *',
                    border: OutlineInputBorder(),
                  ),
                  maxLines: 2,
                ),
                SizedBox(height: AppSpace.s(12)),
                FilledButton(
                  style: mileagePrimaryButtonStyle(minHeight: AppSpace.row(40)),
                  onPressed: _submitting ? null : _submit,
                  child: _submitting
                      ? const SizedBox(
                          height: 20,
                          width: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : Text(_isGrant ? '지급하기' : '차감하기'),
                ),
              ],
            ),
            SizedBox(height: AppSpace.s(8)),
            const Text(
              '최근 마일리지 내역',
              style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold),
            ),
            SizedBox(height: AppSpace.s(8)),
            transactionsAsync.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => ErrorView(message: e.toString()),
              data: (list) {
                if (list.isEmpty) {
                  return const Text('거래 내역이 없습니다.');
                }
                final nameById = {
                  for (final s
                      in studentsAsync.asData?.value ?? const <UserModel>[])
                    s.uid: s.displayName,
                };
                return ListView.separated(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  itemCount: list.length,
                  separatorBuilder: (_, _) => const Divider(),
                  itemBuilder: (_, i) {
                    final tx = list[i];
                    final storedName = tx.userDisplayName.trim();
                    final joinedName = nameById[tx.userId]?.trim() ?? '';
                    final displayName = storedName.isNotEmpty
                        ? storedName
                        : joinedName.isNotEmpty
                        ? joinedName
                        : '알 수 없는 학생';
                    final createdAt = tx.createdAt != null
                        ? AppDateUtils.formatDateTime(tx.createdAt!)
                        : '';
                    return ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(
                        displayName,
                        style: const TextStyle(fontWeight: FontWeight.w600),
                      ),
                      subtitle: Text(
                        [
                          tx.reason,
                          if (createdAt.isNotEmpty) createdAt,
                        ].join('\n'),
                      ),
                      trailing: Text(
                        formatMileageSigned(tx.amount),
                        style: TextStyle(
                          fontWeight: FontWeight.bold,
                          color: tx.amount >= 0
                              ? AppColors.success
                              : AppColors.error,
                        ),
                      ),
                    );
                  },
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}
