import 'dart:async';
import 'dart:math' as math;

import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../shared/models/assessment_model.dart';
import '../../../../shared/models/curriculum_sheet_model.dart';
import '../../../../shared/providers/cohort_providers.dart';
import '../../../../shared/providers/lms_providers.dart';
import '../../../assessments/data/assessment_functions_service.dart';
import '../../../../core/theme/app_space.dart';

enum _MixPreset { mcHeavy, balanced, moreSa }

String _friendlyFunctionsError(Object e) {
  if (e is FirebaseFunctionsException) {
    final details = e.details;
    if (details is Map) {
      final nested = details['message']?.toString().trim();
      if (nested != null &&
          nested.isNotEmpty &&
          nested.toUpperCase() != 'INTERNAL') {
        return nested;
      }
    }
    final m = e.message?.trim();
    if (m != null && m.isNotEmpty && !m.toUpperCase().startsWith('INTERNAL')) {
      return m;
    }
    // code만 internal이어도 message에 한글 상세가 있으면 우선
    if (m != null && m.contains('AI')) return m;
    return '문제 생성 서버 오류가 발생했습니다. '
        '문항 수를 줄이거나 잠시 후 다시 시도해 주세요.'
        '${e.message != null && e.message!.isNotEmpty ? "\n(${e.message})" : " (${e.code})"}';
  }
  return '$e';
}

/// 목표 문항 수 → AI 생성 수(여유분) + 유형 비율
({int mc, int sa}) _planGeneration({
  required int targetCount,
  required _MixPreset mix,
  int? overrideMc,
  int? overrideSa,
}) {
  if (overrideMc != null || overrideSa != null) {
    return (mc: overrideMc ?? 0, sa: overrideSa ?? 0);
  }
  final generateTotal = (targetCount * 1.75).round().clamp(targetCount, 40);
  final mcRatio = switch (mix) {
    _MixPreset.mcHeavy => 0.8,
    _MixPreset.balanced => 0.7,
    _MixPreset.moreSa => 0.6,
  };
  var mc = (generateTotal * mcRatio).round();
  var sa = generateTotal - mc;
  if (sa < 1 && generateTotal >= 2) {
    sa = 1;
    mc = generateTotal - 1;
  }
  if (mc < 1) mc = generateTotal;
  return (mc: mc, sa: sa);
}

/// Step1: 범위 + 시험 규모 → AI 초안 생성
class CurriculumAiGenerateDialog extends ConsumerStatefulWidget {
  const CurriculumAiGenerateDialog({super.key});

  @override
  ConsumerState<CurriculumAiGenerateDialog> createState() =>
      _CurriculumAiGenerateDialogState();
}

class _CurriculumAiGenerateDialogState
    extends ConsumerState<CurriculumAiGenerateDialog> {
  var _generating = false;
  String? _error;
  late final TextEditingController _searchCtrl;
  late final TextEditingController _mcOverrideCtrl;
  late final TextEditingController _saOverrideCtrl;
  String _query = '';
  int? _rangeStart;
  int? _rangeEnd;
  var _pickingStart = true;
  var _targetCount = 20;
  var _mix = _MixPreset.mcHeavy;
  var _showAdvanced = false;
  String? _progressHint;
  int _genMc = 0;
  int _genSa = 0;

  static const _targetPresets = [10, 15, 20, 25];

  @override
  void initState() {
    super.initState();
    _searchCtrl = TextEditingController();
    _mcOverrideCtrl = TextEditingController();
    _saOverrideCtrl = TextEditingController();
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    _mcOverrideCtrl.dispose();
    _saOverrideCtrl.dispose();
    super.dispose();
  }

  (int, int)? get _resolvedRange {
    final start = _rangeStart;
    final end = _rangeEnd;
    if (start == null || end == null) return null;
    return (start <= end ? start : end, start <= end ? end : start);
  }

  bool _isDayInRange(int day) {
    final range = _resolvedRange;
    if (range == null) return false;
    return day >= range.$1 && day <= range.$2;
  }

  CurriculumRowModel? _rowForDay(List<CurriculumRowModel> rows, int? day) {
    if (day == null) return null;
    for (final r in rows) {
      if (r.dayIndex == day) return r;
    }
    return null;
  }

  void _onRowTap(int dayIndex) {
    setState(() {
      _error = null;
      if (_pickingStart) {
        _rangeStart = dayIndex;
        _pickingStart = false;
      } else {
        _rangeEnd = dayIndex;
      }
    });
  }

  void _clearRange() {
    setState(() {
      _rangeStart = null;
      _rangeEnd = null;
      _pickingStart = true;
      _error = null;
    });
  }

  void _applySearchAsRange(List<CurriculumRowModel> filtered) {
    if (filtered.isEmpty) {
      setState(() => _error = '검색 결과가 없습니다.');
      return;
    }
    final days = filtered.map((r) => r.dayIndex).toList()..sort();
    setState(() {
      _rangeStart = days.first;
      _rangeEnd = days.last;
      _pickingStart = false;
      _error = null;
    });
  }

  List<CurriculumRowModel> _filteredRows(List<CurriculumRowModel> rows) {
    final q = _query.trim().toLowerCase();
    if (q.isEmpty) return rows;
    return rows.where((r) {
      return r.subject.toLowerCase().contains(q) ||
          r.topic.toLowerCase().contains(q) ||
          r.detail.toLowerCase().contains(q) ||
          r.dateLabel.toLowerCase().contains(q) ||
          '${r.dayIndex}'.contains(q);
    }).toList();
  }

  Future<void> _generate() async {
    final sheet = ref.read(latestCurriculumSheetProvider).asData?.value;
    if (sheet == null) {
      setState(() => _error = '먼저 커리큘럼 CSV를 등록하세요.');
      return;
    }
    final cohortId = ref.read(effectiveCohortIdProvider);
    if (cohortId == null) {
      setState(() => _error = '기수 정보가 없습니다.');
      return;
    }
    final range = _resolvedRange;
    if (range == null) {
      setState(() => _error = '시작일과 종료일을 모두 선택해 주세요.');
      return;
    }

    final overrideMc = _showAdvanced
        ? int.tryParse(_mcOverrideCtrl.text.trim())
        : null;
    final overrideSa = _showAdvanced
        ? int.tryParse(_saOverrideCtrl.text.trim())
        : null;
    final plan = _planGeneration(
      targetCount: _targetCount,
      mix: _mix,
      overrideMc: overrideMc,
      overrideSa: overrideSa,
    );

    setState(() {
      _generating = true;
      _error = null;
      _genMc = plan.mc;
      _genSa = plan.sa;
      _progressHint =
          '목표 $_targetCount문항 · AI 초안 객관식 ${plan.mc} · 단답 ${plan.sa}';
    });

    try {
      final result = await ref
          .read(assessmentFunctionsServiceProvider)
          .generateAssessmentQuestions(
            cohortId: cohortId,
            sheetId: sheet.id,
            dayFrom: range.$1,
            dayTo: range.$2,
            mcCount: plan.mc,
            saCount: plan.sa,
          );
      if (!mounted) return;
      Navigator.pop(
        context,
        GenerateAssessmentResult(
          questions: result.questions,
          logId: result.logId,
          promptVersion: result.promptVersion,
          model: result.model,
          rowCount: result.rowCount,
          targetCount: _targetCount,
          sheetId: sheet.id,
          dayFrom: range.$1,
          dayTo: range.$2,
        ),
      );
    } catch (e) {
      setState(() {
        _generating = false;
        _progressHint = null;
        _error = _friendlyFunctionsError(e);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final sheetAsync = ref.watch(latestCurriculumSheetProvider);
    final sheet = sheetAsync.asData?.value;
    final screenH = MediaQuery.sizeOf(context).height;
    final dialogH = sheet == null ? 280.0 : (screenH * 0.9).clamp(520.0, 860.0);
    final allRows = sheet?.rows ?? const <CurriculumRowModel>[];
    final filtered = _filteredRows(allRows);
    final range = _resolvedRange;
    final startRow = _rowForDay(allRows, _rangeStart);
    final endRow = _rowForDay(allRows, _rangeEnd);
    final inRangeCount = range == null
        ? 0
        : allRows
              .where((r) => r.dayIndex >= range.$1 && r.dayIndex <= range.$2)
              .length;
    final canGenerate = sheet != null && !_generating && _resolvedRange != null;

    final overrideMc = _showAdvanced
        ? int.tryParse(_mcOverrideCtrl.text.trim())
        : null;
    final overrideSa = _showAdvanced
        ? int.tryParse(_saOverrideCtrl.text.trim())
        : null;
    final plan = _planGeneration(
      targetCount: _targetCount,
      mix: _mix,
      overrideMc: overrideMc,
      overrideSa: overrideSa,
    );
    final planUsesOverride = overrideMc != null || overrideSa != null;
    final mixLabel = switch (_mix) {
      _MixPreset.mcHeavy => '객관식 위주',
      _MixPreset.balanced => '균형',
      _MixPreset.moreSa => '단답 위주',
    };

    return Dialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      insetPadding: EdgeInsets.symmetric(horizontal: AppSpace.s(16), vertical: AppSpace.s(12)),
      child: SizedBox(
        width: 760,
        height: dialogH,
        child: Padding(
          padding: EdgeInsets.fromLTRB(AppSpace.s(20), AppSpace.s(16), AppSpace.s(20), AppSpace.s(12)),
          child: sheetAsync.isLoading
              ? const Center(child: CircularProgressIndicator())
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const _StepHeader(
                      title: '문제 생성 AI',
                      subtitle: '단원을 고르고, 이번 시험에 몇 문제 낼지만 정하세요.',
                      stepLabel: '1 · 범위 & 규모',
                    ),
                    if (_error != null) ...[
                      SizedBox(height: AppSpace.s(8)),
                      _ErrorBanner(message: _error!),
                    ],
                    if (sheet == null)
                      Expanded(
                        child: Center(
                          child: Text(
                            '등록된 커리큘럼이 없습니다.\n커리큘럼 메뉴에서 CSV를 업로드하세요.',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              color: AppColors.textSecondary,
                              height: 1.5,
                            ),
                          ),
                        ),
                      )
                    else if (_generating)
                      Expanded(
                        child: _AiGeneratingPanel(
                          targetCount: _targetCount,
                          mcCount: _genMc,
                          saCount: _genSa,
                          summaryHint: _progressHint,
                        ),
                      )
                    else ...[
                      SizedBox(height: AppSpace.s(8)),
                      Expanded(
                        child: CustomScrollView(
                          slivers: [
                            SliverToBoxAdapter(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.stretch,
                                children: [
                                  Text(
                                    sheet.title,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(
                                      fontSize: 13,
                                      color: AppColors.textSecondary,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                  SizedBox(height: AppSpace.s(12)),
                                  TextField(
                                    controller: _searchCtrl,
                                    enabled: !_generating,
                                    onChanged: (v) =>
                                        setState(() => _query = v),
                                    decoration: InputDecoration(
                                      hintText: '주제·교과목 검색 (예: 딥러닝)',
                                      prefixIcon: const Icon(
                                        Icons.search_rounded,
                                      ),
                                      filled: true,
                                      fillColor: AppColors.surfaceVariant,
                                      border: OutlineInputBorder(
                                        borderRadius: BorderRadius.circular(12),
                                        borderSide: BorderSide.none,
                                      ),
                                      suffixIcon: _query.isEmpty
                                          ? null
                                          : IconButton(
                                              tooltip: '검색 결과로 구간 설정',
                                              onPressed: _generating
                                                  ? null
                                                  : () => _applySearchAsRange(
                                                      filtered,
                                                    ),
                                              icon: const Icon(
                                                Icons
                                                    .playlist_add_check_rounded,
                                              ),
                                            ),
                                    ),
                                  ),
                                  if (_query.isNotEmpty) ...[
                                    SizedBox(height: AppSpace.s(4)),
                                    Align(
                                      alignment: Alignment.centerLeft,
                                      child: TextButton(
                                        onPressed: _generating
                                            ? null
                                            : () =>
                                                  _applySearchAsRange(filtered),
                                        child: Text(
                                          '검색 ${filtered.length}건으로 구간 잡기',
                                        ),
                                      ),
                                    ),
                                  ],
                                  SizedBox(height: AppSpace.s(12)),
                                  Row(
                                    children: [
                                      Expanded(
                                        child: _RangeSlot(
                                          label: '시작',
                                          day: _rangeStart,
                                          topic: startRow?.topic,
                                          active: _pickingStart,
                                          onTap: _generating
                                              ? null
                                              : () => setState(
                                                  () => _pickingStart = true,
                                                ),
                                        ),
                                      ),
                                      Padding(
                                        padding: EdgeInsets.symmetric(
                                          horizontal: AppSpace.s(8),
                                        ),
                                        child: Icon(
                                          Icons.arrow_forward_rounded,
                                          size: 18,
                                          color: AppColors.textHint,
                                        ),
                                      ),
                                      Expanded(
                                        child: _RangeSlot(
                                          label: '종료',
                                          day: _rangeEnd,
                                          topic: endRow?.topic,
                                          active: !_pickingStart,
                                          onTap: _generating
                                              ? null
                                              : () => setState(
                                                  () => _pickingStart = false,
                                                ),
                                        ),
                                      ),
                                      SizedBox(width: AppSpace.s(4)),
                                      TextButton(
                                        onPressed: _generating
                                            ? null
                                            : _clearRange,
                                        child: const Text('초기화'),
                                      ),
                                    ],
                                  ),
                                  if (range != null) ...[
                                    SizedBox(height: AppSpace.s(10)),
                                    Container(
                                      padding: EdgeInsets.symmetric(
                                        horizontal: AppSpace.s(12),
                                        vertical: AppSpace.s(10),
                                      ),
                                      decoration: BoxDecoration(
                                        color: AppColors.primaryLight,
                                        borderRadius: BorderRadius.circular(12),
                                      ),
                                      child: Text(
                                        '선택 구간 D${range.$1}~D${range.$2} · ${inRangeCount}차시',
                                        style: TextStyle(
                                          fontSize: 13,
                                          fontWeight: FontWeight.w700,
                                          color: AppColors.primaryDark,
                                        ),
                                      ),
                                    ),
                                  ],
                                  SizedBox(height: AppSpace.s(18)),
                                  const Text(
                                    '이번 평가 문항 수',
                                    style: TextStyle(
                                      fontWeight: FontWeight.w700,
                                      fontSize: 13,
                                    ),
                                  ),
                                  SizedBox(height: AppSpace.s(8)),
                                  Wrap(
                                    spacing: 8,
                                    runSpacing: 8,
                                    children: [
                                      for (final n in _targetPresets)
                                        ChoiceChip(
                                          label: Text('$n문항'),
                                          selected: _targetCount == n,
                                          onSelected: _generating
                                              ? null
                                              : (_) => setState(
                                                  () => _targetCount = n,
                                                ),
                                          selectedColor: AppColors.primaryLight,
                                          checkmarkColor: AppColors.primaryDark,
                                          labelStyle: TextStyle(
                                            fontWeight: FontWeight.w700,
                                            color: _targetCount == n
                                                ? AppColors.primaryDark
                                                : AppColors.textPrimary,
                                          ),
                                        ),
                                    ],
                                  ),
                                  SizedBox(height: AppSpace.s(12)),
                                  const Text(
                                    '유형 비중',
                                    style: TextStyle(
                                      fontWeight: FontWeight.w700,
                                      fontSize: 13,
                                    ),
                                  ),
                                  SizedBox(height: AppSpace.s(8)),
                                  SegmentedButton<_MixPreset>(
                                    style: ButtonStyle(
                                      visualDensity: VisualDensity.compact,
                                      backgroundColor:
                                          WidgetStateProperty.resolveWith(
                                            (states) {
                                              if (states.contains(
                                                WidgetState.selected,
                                              )) {
                                                return AppColors.primaryLight;
                                              }
                                              return Colors.white;
                                            },
                                          ),
                                      foregroundColor:
                                          WidgetStateProperty.resolveWith(
                                            (states) {
                                              if (states.contains(
                                                WidgetState.selected,
                                              )) {
                                                return AppColors.primaryDark;
                                              }
                                              return AppColors.textPrimary;
                                            },
                                          ),
                                      side: WidgetStatePropertyAll(
                                        BorderSide(
                                          color: AppColors.border.withValues(
                                            alpha: 0.9,
                                          ),
                                        ),
                                      ),
                                    ),
                                    segments: const [
                                      ButtonSegment(
                                        value: _MixPreset.mcHeavy,
                                        label: Text('객관식 위주'),
                                      ),
                                      ButtonSegment(
                                        value: _MixPreset.balanced,
                                        label: Text('균형'),
                                      ),
                                      ButtonSegment(
                                        value: _MixPreset.moreSa,
                                        label: Text('단답 위주'),
                                      ),
                                    ],
                                    selected: {_mix},
                                    onSelectionChanged: _generating
                                        ? null
                                        : (s) => setState(() => _mix = s.first),
                                  ),
                                  SizedBox(height: AppSpace.s(12)),
                                  Container(
                                    padding: EdgeInsets.fromLTRB(
                                      AppSpace.s(14),
                                      AppSpace.s(12),
                                      AppSpace.s(14),
                                      AppSpace.s(12),
                                    ),
                                    decoration: BoxDecoration(
                                      color: AppColors.tint(
                                        const Color(0xFFF8FAFC),
                                      ),
                                      borderRadius: BorderRadius.circular(12),
                                      border: Border.all(
                                        color: AppColors.border,
                                      ),
                                    ),
                                    child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          '시험 $_targetCount문항 · $mixLabel',
                                          style: TextStyle(
                                            fontSize: 13,
                                            fontWeight: FontWeight.w800,
                                            color: AppColors.textPrimary,
                                          ),
                                        ),
                                        SizedBox(height: AppSpace.s(4)),
                                        Text(
                                          planUsesOverride
                                              ? 'AI 초안 객관식 ${plan.mc} · 단답 ${plan.sa}'
                                                    ' (직접 지정 · 총 ${plan.mc + plan.sa}개)'
                                              : 'AI 초안 객관식 ${plan.mc} · 단답 ${plan.sa}'
                                                    ' (여유분 포함 총 ${plan.mc + plan.sa}개)',
                                          style: TextStyle(
                                            fontSize: 12,
                                            height: 1.4,
                                            color: AppColors.textSecondary,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                  Align(
                                    alignment: Alignment.centerLeft,
                                    child: TextButton.icon(
                                      onPressed: _generating
                                          ? null
                                          : () => setState(
                                              () => _showAdvanced =
                                                  !_showAdvanced,
                                            ),
                                      icon: Icon(
                                        _showAdvanced
                                            ? Icons.expand_less
                                            : Icons.tune_rounded,
                                        size: 18,
                                      ),
                                      label: Text(
                                        _showAdvanced ? '고급 옵션 숨기기' : '고급 옵션',
                                      ),
                                    ),
                                  ),
                                  if (_showAdvanced) ...[
                                    Text(
                                      '비우면 위 비중으로 자동 계산합니다.',
                                      style: TextStyle(
                                        fontSize: 12,
                                        color: AppColors.textSecondary,
                                      ),
                                    ),
                                    SizedBox(height: AppSpace.s(8)),
                                    Row(
                                      children: [
                                        Expanded(
                                          child: TextField(
                                            controller: _mcOverrideCtrl,
                                            keyboardType: TextInputType.number,
                                            enabled: !_generating,
                                            onChanged: (_) => setState(() {}),
                                            decoration: InputDecoration(
                                              labelText: '객관식 생성 수',
                                              hintText: '예: 24',
                                              helperText: 'AI가 만들 객관식 개수',
                                              filled: true,
                                              fillColor:
                                                  AppColors.surfaceVariant,
                                              border: OutlineInputBorder(),
                                            ),
                                          ),
                                        ),
                                        SizedBox(width: AppSpace.s(10)),
                                        Expanded(
                                          child: TextField(
                                            controller: _saOverrideCtrl,
                                            keyboardType: TextInputType.number,
                                            enabled: !_generating,
                                            onChanged: (_) => setState(() {}),
                                            decoration: InputDecoration(
                                              labelText: '단답 생성 수',
                                              hintText: '예: 8',
                                              helperText: 'AI가 만들 단답 개수',
                                              filled: true,
                                              fillColor:
                                                  AppColors.surfaceVariant,
                                              border: OutlineInputBorder(),
                                            ),
                                          ),
                                        ),
                                      ],
                                    ),
                                    SizedBox(height: AppSpace.s(8)),
                                  ],
                                  SizedBox(height: AppSpace.s(8)),
                                  Text(
                                    '커리큘럼 ${_pickingStart ? "시작일" : "종료일"} 선택 · ${filtered.length}행',
                                    style: const TextStyle(
                                      fontWeight: FontWeight.w700,
                                      fontSize: 13,
                                    ),
                                  ),
                                  SizedBox(height: AppSpace.s(8)),
                                ],
                              ),
                            ),
                            if (filtered.isEmpty)
                              SliverToBoxAdapter(
                                child: Padding(
                                  padding: EdgeInsets.symmetric(vertical: AppSpace.s(24)),
                                  child: Text(
                                    '검색 결과가 없습니다.',
                                    style: TextStyle(
                                      color: AppColors.textSecondary,
                                    ),
                                  ),
                                ),
                              )
                            else
                              SliverList.separated(
                                itemCount: filtered.length,
                                separatorBuilder: (_, _) =>
                                    SizedBox(height: AppSpace.s(10)),
                                itemBuilder: (context, i) {
                                  final row = filtered[i];
                                  final inRange = _isDayInRange(row.dayIndex);
                                  final isStart = row.dayIndex == _rangeStart;
                                  final isEnd = row.dayIndex == _rangeEnd;
                                  return Material(
                                    color: inRange
                                        ? AppColors.primaryLight
                                        : AppColors.surface,
                                    borderRadius: BorderRadius.circular(12),
                                    child: InkWell(
                                      borderRadius: BorderRadius.circular(12),
                                      onTap: _generating
                                          ? null
                                          : () => _onRowTap(row.dayIndex),
                                      child: Container(
                                        padding: EdgeInsets.fromLTRB(
                                          AppSpace.s(14),
                                          AppSpace.s(14),
                                          AppSpace.s(14),
                                          AppSpace.s(14),
                                        ),
                                        decoration: BoxDecoration(
                                          borderRadius: BorderRadius.circular(
                                            12,
                                          ),
                                          border: Border.all(
                                            color: isStart || isEnd
                                                ? AppColors.primary
                                                : AppColors.border,
                                            width: isStart || isEnd ? 1.5 : 1,
                                          ),
                                        ),
                                        child: Row(
                                          children: [
                                            SizedBox(
                                              width: 56,
                                              child: Text(
                                                'D${row.dayIndex}',
                                                style: const TextStyle(
                                                  fontWeight: FontWeight.w800,
                                                  fontSize: 14,
                                                ),
                                              ),
                                            ),
                                            Expanded(
                                              child: Column(
                                                crossAxisAlignment:
                                                    CrossAxisAlignment.start,
                                                children: [
                                                  Text(
                                                    row.topic.isEmpty
                                                        ? '(내용 없음)'
                                                        : row.topic,
                                                    maxLines: 2,
                                                    overflow:
                                                        TextOverflow.ellipsis,
                                                    style: const TextStyle(
                                                      fontWeight:
                                                          FontWeight.w700,
                                                      fontSize: 14,
                                                      height: 1.35,
                                                    ),
                                                  ),
                                                  SizedBox(height: AppSpace.s(4)),
                                                  Text(
                                                    [
                                                      if (row
                                                          .subject
                                                          .isNotEmpty)
                                                        row.subject,
                                                      if (row
                                                          .dateLabel
                                                          .isNotEmpty)
                                                        row.dateLabel,
                                                    ].join(' · '),
                                                    maxLines: 1,
                                                    overflow:
                                                        TextOverflow.ellipsis,
                                                    style: TextStyle(
                                                      fontSize: 12,
                                                      color: AppColors
                                                          .textSecondary,
                                                    ),
                                                  ),
                                                ],
                                              ),
                                            ),
                                            if (isStart || isEnd) ...[
                                              SizedBox(width: AppSpace.s(8)),
                                              Container(
                                                padding:
                                                    EdgeInsets.symmetric(
                                                      horizontal: AppSpace.s(8),
                                                      vertical: AppSpace.s(4),
                                                    ),
                                                decoration: BoxDecoration(
                                                  color: AppColors.primary,
                                                  borderRadius:
                                                      BorderRadius.circular(
                                                        999,
                                                      ),
                                                ),
                                                child: Text(
                                                  isStart && isEnd
                                                      ? '단독'
                                                      : isStart
                                                      ? '시작'
                                                      : '종료',
                                                  style: TextStyle(
                                                    color: Colors.white,
                                                    fontSize: 11,
                                                    fontWeight: FontWeight.w700,
                                                  ),
                                                ),
                                              ),
                                            ],
                                          ],
                                        ),
                                      ),
                                    ),
                                  );
                                },
                              ),
                            SliverToBoxAdapter(
                              child: SizedBox(height: AppSpace.s(8)),
                            ),
                          ],
                        ),
                      ),
                    ],
                    SizedBox(height: AppSpace.s(10)),
                    SafeArea(
                      top: false,
                      child: Row(
                        children: [
                          TextButton(
                            onPressed: _generating
                                ? null
                                : () => Navigator.pop(context),
                            child: const Text('취소'),
                          ),
                          const Spacer(),
                          FilledButton(
                            onPressed: canGenerate ? _generate : null,
                            style: FilledButton.styleFrom(
                              backgroundColor: AppColors.primary,
                              foregroundColor: Colors.white,
                              shape: const StadiumBorder(),
                              padding: EdgeInsets.symmetric(
                                horizontal: AppSpace.s(22),
                                vertical: AppSpace.s(14),
                              ),
                            ),
                            child: Text(
                              _generating ? '생성 중…' : '초안 만들기',
                              style: const TextStyle(
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
        ),
      ),
    );
  }
}

/// Step2: 초안 검토 · 선택 · 부분 재생성
class AssessmentAiReviewDialog extends ConsumerStatefulWidget {
  const AssessmentAiReviewDialog({
    super.key,
    required this.initial,
  });

  final GenerateAssessmentResult initial;

  @override
  ConsumerState<AssessmentAiReviewDialog> createState() =>
      _AssessmentAiReviewDialogState();
}

class _AssessmentAiReviewDialogState
    extends ConsumerState<AssessmentAiReviewDialog> {
  late List<AssessmentQuestionModel> _drafts;
  late String? _logId;
  late String? _promptVersion;
  final _selected = <int>{};
  final _regenBusy = <int>{};
  String? _error;
  var _submitting = false;
  var _regenerating = false;

  int get _target => widget.initial.targetCount ?? _drafts.length.clamp(1, 20);

  @override
  void initState() {
    super.initState();
    _drafts = List.of(widget.initial.questions);
    _logId = widget.initial.logId;
    _promptVersion = widget.initial.promptVersion;
  }

  void _toggle(int index) {
    if (_regenBusy.contains(index) || _regenerating) return;
    setState(() {
      _error = null;
      if (_selected.contains(index)) {
        _selected.remove(index);
      } else {
        _selected.add(index);
      }
    });
  }

  Future<void> _regenerateSelected() async {
    if (_selected.isEmpty) {
      setState(() => _error = '다시 만들 문항을 먼저 골라 주세요.');
      return;
    }
    final cohortId = ref.read(effectiveCohortIdProvider);
    final sheetId = widget.initial.sheetId;
    final dayFrom = widget.initial.dayFrom;
    final dayTo = widget.initial.dayTo;
    if (cohortId == null ||
        sheetId == null ||
        dayFrom == null ||
        dayTo == null) {
      setState(() => _error = '재생성에 필요한 구간 정보가 없습니다.');
      return;
    }

    final indices = _selected.toList()..sort();
    final replaceOf = [
      for (final i in indices)
        {
          'draftId': _drafts[i].aiDraftId ?? _drafts[i].id,
          'type': _drafts[i].type.value,
          if (_drafts[i].sourceDay != null) 'sourceDay': _drafts[i].sourceDay,
          if (_drafts[i].sourceTopic != null)
            'sourceTopic': _drafts[i].sourceTopic,
          'promptPreview': _drafts[i].prompt.length > 100
              ? _drafts[i].prompt.substring(0, 100)
              : _drafts[i].prompt,
        },
    ];

    setState(() {
      _regenerating = true;
      _error = null;
      _regenBusy
        ..clear()
        ..addAll(indices);
    });

    try {
      // 기존 선택분은 discarded로 남김 (실패해도 재생성은 진행)
      final oldLogId = _logId;
      if (oldLogId != null) {
        try {
          await ref
              .read(assessmentFunctionsServiceProvider)
              .recordAiQuestionFeedback(
                cohortId: cohortId,
                logId: oldLogId,
                promptVersion: _promptVersion,
                items: [
                  for (final i in indices)
                    {
                      'draftId': _drafts[i].aiDraftId ?? _drafts[i].id,
                      'outcome': 'discarded',
                      if (_drafts[i].sourceDay != null)
                        'sourceDay': _drafts[i].sourceDay,
                      if (_drafts[i].sourceTopic != null)
                        'sourceTopic': _drafts[i].sourceTopic,
                    },
                ],
              );
        } catch (_) {}
      }

      final result = await ref
          .read(assessmentFunctionsServiceProvider)
          .generateAssessmentQuestions(
            cohortId: cohortId,
            sheetId: sheetId,
            dayFrom: dayFrom,
            dayTo: dayTo,
            mcCount: 0,
            saCount: 0,
            parentLogId: oldLogId,
            replaceOf: replaceOf,
          );

      if (!mounted) return;
      final fresh = result.questions;
      setState(() {
        for (var k = 0; k < indices.length; k++) {
          final at = indices[k];
          if (k < fresh.length) {
            _drafts[at] = fresh[k];
          }
        }
        // 남은 새 문항이 있으면 끝에 추가
        if (fresh.length > indices.length) {
          _drafts.addAll(fresh.skip(indices.length));
        }
        _logId = result.logId ?? _logId;
        _promptVersion = result.promptVersion ?? _promptVersion;
        _selected.clear();
        _regenBusy.clear();
        _regenerating = false;
      });
    } catch (e) {
      setState(() {
        _regenerating = false;
        _regenBusy.clear();
        _error = _friendlyFunctionsError(e);
      });
    }
  }

  Future<void> _confirm() async {
    if (_selected.isEmpty) {
      setState(() => _error = '평가에 넣을 문항을 1개 이상 선택해 주세요.');
      return;
    }
    final indices = _selected.toList()..sort();
    final selected = [for (final i in indices) _drafts[i]];

    final cohortId = ref.read(effectiveCohortIdProvider);
    if (cohortId != null) {
      setState(() => _submitting = true);
      try {
        final byLog = <String, List<Map<String, dynamic>>>{};
        for (var i = 0; i < _drafts.length; i++) {
          final q = _drafts[i];
          final lid = q.aiLogId ?? _logId;
          if (lid == null) continue;
          byLog.putIfAbsent(lid, () => []).add({
            'draftId': q.aiDraftId ?? q.id,
            'outcome': _selected.contains(i) ? 'adopted' : 'discarded',
            if (q.sourceDay != null) 'sourceDay': q.sourceDay,
            if (q.sourceTopic != null) 'sourceTopic': q.sourceTopic,
          });
        }
        final svc = ref.read(assessmentFunctionsServiceProvider);
        for (final entry in byLog.entries) {
          await svc.recordAiQuestionFeedback(
            cohortId: cohortId,
            logId: entry.key,
            promptVersion: _promptVersion,
            items: entry.value,
          );
        }
      } catch (_) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('채택 피드백 저장에 실패했습니다. (출제는 계속됩니다)'),
            ),
          );
        }
      } finally {
        if (mounted) setState(() => _submitting = false);
      }
    }

    if (!mounted) return;
    Navigator.pop(context, selected);
  }

  @override
  Widget build(BuildContext context) {
    final screenH = MediaQuery.sizeOf(context).height;
    final mc = _drafts
        .where((q) => q.type == AssessmentQuestionType.multipleChoice)
        .length;
    final sa = _drafts.length - mc;
    final under = _selected.length < _target;
    final over = _selected.length > _target;

    return Dialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      insetPadding: EdgeInsets.symmetric(horizontal: AppSpace.s(20), vertical: AppSpace.s(16)),
      child: SizedBox(
        width: 760,
        height: (screenH * 0.88).clamp(560.0, 820.0),
        child: Column(
          children: [
            Padding(
              padding: EdgeInsets.fromLTRB(AppSpace.s(22), AppSpace.s(20), AppSpace.s(22), AppSpace.s(0)),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const _StepHeader(
                    title: '초안 검토',
                    subtitle: '마음에 드는 문항을 고르세요. 별로인 것은 선택한 뒤 다시 만들 수 있습니다.',
                    stepLabel: '2 · 검토 & 출제',
                  ),
                  SizedBox(height: AppSpace.s(12)),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      _MetaChip(
                        label: '초안 ${_drafts.length}',
                        detail: '객관 $mc · 단답 $sa',
                      ),
                      _MetaChip(
                        label: '목표 $_target',
                        detail: '선택 ${_selected.length}',
                        emphasize: !under && !over,
                      ),
                      if (under)
                        const _MetaChip(
                          label: '목표보다 적음',
                          detail: '그래도 추가 가능',
                          tone: _ChipTone.warn,
                        ),
                      if (over)
                        const _MetaChip(
                          label: '목표보다 많음',
                          detail: '필요하면 줄이세요',
                          tone: _ChipTone.warn,
                        ),
                    ],
                  ),
                  if (_error != null) ...[
                    SizedBox(height: AppSpace.s(10)),
                    _ErrorBanner(message: _error!),
                  ],
                ],
              ),
            ),
            SizedBox(height: AppSpace.s(12)),
            Expanded(
              child: ListView.separated(
                padding: EdgeInsets.fromLTRB(AppSpace.s(22), AppSpace.s(0), AppSpace.s(22), AppSpace.s(12)),
                itemCount: _drafts.length,
                separatorBuilder: (_, _) => SizedBox(height: AppSpace.s(8)),
                itemBuilder: (context, i) {
                  final q = _drafts[i];
                  final selected = _selected.contains(i);
                  final busy = _regenBusy.contains(i);
                  final typeLabel =
                      q.type == AssessmentQuestionType.multipleChoice
                      ? '객관식'
                      : '단답';
                  return Opacity(
                    opacity: busy ? 0.55 : 1,
                    child: Material(
                      color: selected ? AppColors.primaryLight : AppColors.surface,
                      borderRadius: BorderRadius.circular(14),
                      child: InkWell(
                        onTap: busy ? null : () => _toggle(i),
                        borderRadius: BorderRadius.circular(14),
                        child: Container(
                          padding: EdgeInsets.fromLTRB(AppSpace.s(12), AppSpace.s(12), AppSpace.s(12), AppSpace.s(12)),
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(14),
                            border: Border.all(
                              color: selected
                                  ? AppColors.primary
                                  : AppColors.border,
                              width: selected ? 1.6 : 1,
                            ),
                          ),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Checkbox(
                                value: selected,
                                onChanged: busy ? null : (_) => _toggle(i),
                              ),
                              SizedBox(width: AppSpace.s(4)),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Wrap(
                                      spacing: 6,
                                      runSpacing: 6,
                                      crossAxisAlignment:
                                          WrapCrossAlignment.center,
                                      children: [
                                        Text(
                                          'Q${i + 1}',
                                          style: const TextStyle(
                                            fontWeight: FontWeight.w800,
                                            fontSize: 13,
                                          ),
                                        ),
                                        _TinyBadge(
                                          text: '$typeLabel · ${q.points}점',
                                        ),
                                        if (q.sourceDay != null)
                                          _TinyBadge(
                                            text: 'Day ${q.sourceDay}',
                                            color: AppColors.primaryLight,
                                            textColor: AppColors.primaryDark,
                                          ),
                                        if (q.sourceTopic != null &&
                                            q.sourceTopic!.isNotEmpty)
                                          _TinyBadge(
                                            text: q.sourceTopic!,
                                          ),
                                        if (busy)
                                          _TinyBadge(
                                            text: '다시 만드는 중…',
                                            color: AppColors.tint(
                                              const Color(0xFFFFF7ED),
                                            ),
                                            textColor: const Color(0xFF9A3412),
                                          ),
                                      ],
                                    ),
                                    SizedBox(height: AppSpace.s(8)),
                                    Text(
                                      q.prompt,
                                      maxLines: 4,
                                      overflow: TextOverflow.ellipsis,
                                      style: TextStyle(
                                        fontSize: 13,
                                        height: 1.45,
                                        color: AppColors.textPrimary,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  );
                },
              ),
            ),
            Container(
              padding: EdgeInsets.fromLTRB(AppSpace.s(16), AppSpace.s(12), AppSpace.s(16), AppSpace.s(14)),
              decoration: BoxDecoration(
                color: AppColors.surface,
                border: Border(
                  top: BorderSide(color: AppColors.border),
                ),
              ),
              child: Row(
                children: [
                  OutlinedButton.icon(
                    onPressed:
                        (_regenerating || _submitting || _selected.isEmpty)
                        ? null
                        : _regenerateSelected,
                    icon: _regenerating
                        ? const SizedBox(
                            width: 14,
                            height: 14,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.autorenew_rounded, size: 18),
                    label: Text(
                      _selected.isEmpty
                          ? '선택 후 다시 생성'
                          : '선택한 ${_selected.length}문항 다시 생성',
                    ),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppColors.primaryDark,
                      side: BorderSide(color: AppColors.primary),
                      shape: const StadiumBorder(),
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpace.s(14),
                        vertical: AppSpace.s(12),
                      ),
                    ),
                  ),
                  const Spacer(),
                  TextButton(
                    onPressed: (_regenerating || _submitting)
                        ? null
                        : () => Navigator.pop(context),
                    child: const Text('취소'),
                  ),
                  SizedBox(width: AppSpace.s(6)),
                  FilledButton(
                    onPressed: (_regenerating || _submitting) ? null : _confirm,
                    style: FilledButton.styleFrom(
                      backgroundColor: AppColors.primary,
                      foregroundColor: Colors.white,
                      shape: const StadiumBorder(),
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpace.s(20),
                        vertical: AppSpace.s(14),
                      ),
                    ),
                    child: _submitting
                        ? SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          )
                        : Text(
                            _selected.isEmpty
                                ? '평가에 추가'
                                : '평가에 ${_selected.length}문항 추가',
                            style: const TextStyle(fontWeight: FontWeight.w700),
                          ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

enum _ChipTone { normal, warn }

/// 문제 생성 대기 — 단계 문구 · 경과 시간 · soft progress
class _AiGeneratingPanel extends StatefulWidget {
  const _AiGeneratingPanel({
    required this.targetCount,
    required this.mcCount,
    required this.saCount,
    this.summaryHint,
  });

  final int targetCount;
  final int mcCount;
  final int saCount;
  final String? summaryHint;

  @override
  State<_AiGeneratingPanel> createState() => _AiGeneratingPanelState();
}

class _AiGeneratingPanelState extends State<_AiGeneratingPanel>
    with SingleTickerProviderStateMixin {
  static const _phases = <String>[
    '선택한 커리큘럼 구간을 읽고 있어요',
    '객관식 초안을 만들고 있어요',
    '단답형 초안을 다듬고 있어요',
    '문항 난이도와 표현을 점검하는 중이에요',
    '거의 다 됐어요. 조금만 기다려 주세요',
  ];

  late final AnimationController _pulse;
  Timer? _tick;
  Timer? _phaseTimer;
  var _elapsedSec = 0;
  var _phaseIndex = 0;
  var _progress = 0.08;

  @override
  void initState() {
    super.initState();
    _pulse = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1400),
    )..repeat(reverse: true);

    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted) return;
      setState(() {
        _elapsedSec += 1;
        // 실제 진행률은 없음 → 느리게 90%까지 접근
        final t = _elapsedSec / 55.0;
        _progress = (0.08 + (1 - math.exp(-t)) * 0.82).clamp(0.08, 0.92);
      });
    });

    _phaseTimer = Timer.periodic(const Duration(seconds: 4), (_) {
      if (!mounted) return;
      setState(() {
        _phaseIndex = (_phaseIndex + 1) % _phases.length;
      });
    });
  }

  @override
  void dispose() {
    _tick?.cancel();
    _phaseTimer?.cancel();
    _pulse.dispose();
    super.dispose();
  }

  String get _elapsedLabel {
    final m = _elapsedSec ~/ 60;
    final s = _elapsedSec % 60;
    if (m <= 0) return '${s}초 경과';
    return '$m분 ${s.toString().padLeft(2, '0')}초 경과';
  }

  @override
  Widget build(BuildContext context) {
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 420),
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: AppSpace.s(12)),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              AnimatedBuilder(
                animation: _pulse,
                builder: (context, child) {
                  final t = Curves.easeInOut.transform(_pulse.value);
                  final scale = 0.94 + t * 0.08;
                  final glow = 0.18 + t * 0.28;
                  return Transform.scale(
                    scale: scale,
                    child: Container(
                      width: 88,
                      height: 88,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        gradient: LinearGradient(
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                          colors: [AppColors.primary, AppColors.sidebar],
                        ),
                        boxShadow: [
                          BoxShadow(
                            color: AppColors.primary.withValues(alpha: glow),
                            blurRadius: 22,
                            spreadRadius: 2,
                          ),
                        ],
                      ),
                      child: child,
                    ),
                  );
                },
                child: Icon(
                  Icons.auto_awesome_rounded,
                  color: Colors.white,
                  size: 40,
                ),
              ),
              SizedBox(height: AppSpace.s(28)),
              Text(
                'AI가 문제를 만들고 있어요',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 20,
                  fontWeight: FontWeight.w800,
                  color: AppColors.textPrimary,
                ),
              ),
              SizedBox(height: AppSpace.s(10)),
              AnimatedSwitcher(
                duration: const Duration(milliseconds: 420),
                switchInCurve: Curves.easeOut,
                switchOutCurve: Curves.easeIn,
                child: Text(
                  _phases[_phaseIndex],
                  key: ValueKey(_phaseIndex),
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 14,
                    height: 1.45,
                    color: AppColors.textSecondary,
                  ),
                ),
              ),
              SizedBox(height: AppSpace.s(22)),
              ClipRRect(
                borderRadius: BorderRadius.circular(999),
                child: LinearProgressIndicator(
                  value: _progress,
                  minHeight: 8,
                  backgroundColor: AppColors.surfaceVariant,
                  color: AppColors.primary,
                ),
              ),
              SizedBox(height: AppSpace.s(10)),
              Text(
                '${(_progress * 100).round()}% · $_elapsedLabel',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  color: AppColors.textHint,
                ),
              ),
              SizedBox(height: AppSpace.s(22)),
              Container(
                width: double.infinity,
                padding: EdgeInsets.fromLTRB(AppSpace.s(16), AppSpace.s(14), AppSpace.s(16), AppSpace.s(14)),
                decoration: BoxDecoration(
                  color: AppColors.tint(const Color(0xFFF8FAFC)),
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: AppColors.border),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      widget.summaryHint ??
                          '시험 ${widget.targetCount}문항 · 초안 객관식 ${widget.mcCount} · 단답 ${widget.saCount}',
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: AppColors.textPrimary,
                      ),
                    ),
                    SizedBox(height: AppSpace.s(6)),
                    Text(
                      '보통 20~60초 정도 걸려요. 창을 닫지 말고 기다려 주세요.',
                      style: TextStyle(
                        fontSize: 12,
                        height: 1.4,
                        color: AppColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _StepHeader extends StatelessWidget {
  const _StepHeader({
    required this.title,
    required this.subtitle,
    required this.stepLabel,
  });

  final String title;
  final String subtitle;
  final String stepLabel;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          padding: EdgeInsets.symmetric(horizontal: AppSpace.s(10), vertical: AppSpace.s(4)),
          decoration: BoxDecoration(
            color: AppColors.primaryLight,
            borderRadius: BorderRadius.circular(999),
          ),
          child: Text(
            stepLabel,
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w800,
              color: AppColors.primaryDark,
            ),
          ),
        ),
        SizedBox(height: AppSpace.s(10)),
        Text(
          title,
          style: TextStyle(
            fontSize: 20,
            fontWeight: FontWeight.w800,
            letterSpacing: -0.3,
            color: AppColors.textPrimary,
          ),
        ),
        SizedBox(height: AppSpace.s(6)),
        Text(
          subtitle,
          style: TextStyle(
            fontSize: 13,
            height: 1.45,
            color: AppColors.textSecondary,
          ),
        ),
      ],
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.message});
  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.fromLTRB(AppSpace.s(12), AppSpace.s(10), AppSpace.s(12), AppSpace.s(10)),
      decoration: BoxDecoration(
        color: AppColors.tint(const Color(0xFFFEF2F2)),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.tint(const Color(0xFFFECACA))),
      ),
      child: Text(
        message,
        maxLines: 5,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          color: AppColors.error,
          fontSize: 13,
          height: 1.4,
        ),
      ),
    );
  }
}

class _RangeSlot extends StatelessWidget {
  const _RangeSlot({
    required this.label,
    required this.day,
    required this.topic,
    required this.active,
    required this.onTap,
  });

  final String label;
  final int? day;
  final String? topic;
  final bool active;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: active ? AppColors.primaryLight : AppColors.surfaceVariant,
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: EdgeInsets.fromLTRB(AppSpace.s(12), AppSpace.s(10), AppSpace.s(12), AppSpace.s(10)),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: active ? AppColors.primary : AppColors.border,
              width: active ? 1.5 : 1,
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                label,
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  color: active
                      ? AppColors.primaryDark
                      : AppColors.textSecondary,
                ),
              ),
              SizedBox(height: AppSpace.s(4)),
              Text(
                day == null ? '선택하세요' : '일수 $day',
                style: const TextStyle(
                  fontWeight: FontWeight.w800,
                  fontSize: 14,
                ),
              ),
              if (topic != null && topic!.isNotEmpty)
                Text(
                  topic!,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: 11,
                    color: AppColors.textSecondary,
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _MetaChip extends StatelessWidget {
  const _MetaChip({
    required this.label,
    required this.detail,
    this.emphasize = false,
    this.tone = _ChipTone.normal,
  });

  final String label;
  final String detail;
  final bool emphasize;
  final _ChipTone tone;

  @override
  Widget build(BuildContext context) {
    final bg = switch (tone) {
      _ChipTone.warn => AppColors.tint(const Color(0xFFFFF7ED)),
      _ChipTone.normal when emphasize => AppColors.tint(
        const Color(0xFFDCFCE7),
      ),
      _ChipTone.normal => AppColors.surfaceVariant,
    };
    final fg = switch (tone) {
      _ChipTone.warn => const Color(0xFF9A3412),
      _ChipTone.normal when emphasize => const Color(0xFF166534),
      _ChipTone.normal => AppColors.textPrimary,
    };
    return Container(
      padding: EdgeInsets.symmetric(horizontal: AppSpace.s(10), vertical: AppSpace.s(8)),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w800,
              color: fg,
            ),
          ),
          Text(
            detail,
            style: TextStyle(
              fontSize: 11,
              color: fg.withValues(alpha: 0.85),
            ),
          ),
        ],
      ),
    );
  }
}

class _TinyBadge extends StatelessWidget {
  _TinyBadge({
    required this.text,
    Color? color,
    Color? textColor,
  }) : color = color ?? AppColors.tint(const Color(0xFFF3F4F6)),
       textColor = textColor ?? AppColors.textSecondary;

  final String text;
  final Color color;
  final Color textColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(maxWidth: 180),
      padding: EdgeInsets.symmetric(horizontal: AppSpace.s(8), vertical: AppSpace.s(2)),
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        text,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w600,
          color: textColor,
        ),
      ),
    );
  }
}
