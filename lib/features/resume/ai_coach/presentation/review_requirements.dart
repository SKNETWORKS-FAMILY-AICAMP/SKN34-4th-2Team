import 'package:flutter/material.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../core/theme/app_space.dart';

/// 공고 맞춤 첨삭의 대화 단계. 서버(review_workflow._review_stage)와 번호를 맞춘다.
/// 문장 다듬기를 한 카드로 먼저 적용하고, 그 뒤 질문으로 사실을 받는다.
const kReviewStageLabels = ['문장 다듬기', '공고 요건 확인', '경험 보완', '지원동기', '자기소개서'];

/// 공고 요건 확인 단계 번호. 공고 없는 첨삭이면 단계 줄에서 뺀다.
const kRequirementStage = 2;

String reviewStageLabel(int? stage) =>
    stage != null && stage >= 1 && stage <= kReviewStageLabels.length
    ? kReviewStageLabels[stage - 1]
    : '';

/// 서버 응답 `requirement_map`의 한 줄. 점수가 아니라 근거가 있는지만 담는다.
class ReviewRequirementRow {
  const ReviewRequirementRow({
    required this.id,
    required this.group,
    required this.label,
    required this.status,
    this.postingQuote = '',
    this.evidencePaths = const [],
    this.evidenceQuotes = const [],
    this.source = 'none',
    this.kind = 'skill',
    this.kindBasis = '',
  });

  factory ReviewRequirementRow.fromMap(Map map) => ReviewRequirementRow(
    id: map['id'] as String? ?? '',
    group: map['group'] as String? ?? 'must',
    label: map['label'] as String? ?? '',
    status: map['status'] as String? ?? 'unconfirmed',
    postingQuote: map['posting_quote'] as String? ?? '',
    evidencePaths: (map['evidence_paths'] as List? ?? const [])
        .whereType<String>()
        .toList(),
    evidenceQuotes: (map['evidence_quotes'] as List? ?? const [])
        .whereType<String>()
        .toList(),
    source: map['source'] as String? ?? 'none',
    kind: map['kind'] as String? ?? 'skill',
    kindBasis: map['kind_basis'] as String? ?? '',
  );

  final String id;

  /// must(필수) · preferred(우대) · task(주요 업무)
  final String group;
  final String label;

  /// met(근거 있음) · partial(일부) · unconfirmed(확인 필요) · absent(해당 없음)
  final String status;
  final String postingQuote;
  final List<String> evidencePaths;
  final List<String> evidenceQuotes;
  final String source;

  /// skill(기술·경험·업무) · eligibility(경력 연수·학력·전공·면허·근무 조건 같은 지원 자격).
  /// 지원 자격은 이력서 문장으로 고칠 게 없어 질문하지 않고 "확인만" 줄에 따로 보인다.
  final String kind;

  /// 지원 자격으로 본 근거. "공고 조건: 신입", "학력·전공 조건".
  final String kindBasis;

  bool get isEligibility => kind == 'eligibility';

  bool get isOpen => status == 'unconfirmed' || status == 'partial';

  Map<String, dynamic> toMap() => {
    'id': id,
    'group': group,
    'label': label,
    'status': status,
    'posting_quote': postingQuote,
    'evidence_paths': evidencePaths,
    'evidence_quotes': evidenceQuotes,
    'source': source,
    'kind': kind,
    'kind_basis': kindBasis,
  };
}

/// 서버 응답 `star_checks`의 한 줄. 경험 항목에 상황·과제·행동·결과가 원문에 있는지.
class ReviewStarCheck {
  const ReviewStarCheck({
    required this.fieldPath,
    this.present = const [],
    this.reason = '',
  });

  factory ReviewStarCheck.fromMap(Map map) => ReviewStarCheck(
    fieldPath: map['field_path'] as String? ?? '',
    present: (map['present'] as List? ?? const []).whereType<String>().toList(),
    reason: map['reason'] as String? ?? '',
  );

  final String fieldPath;
  final List<String> present;

  /// 빠진 요소를 알리는 한 문장. 모두 있으면 빈 문자열.
  final String reason;

  bool has(String element) => present.contains(element);

  Map<String, dynamic> toMap() => {
    'field_path': fieldPath,
    'present': present,
    'missing': [
      for (final element in kStarElements.keys)
        if (!present.contains(element)) element,
    ],
    'reason': reason,
  };
}

/// 서버(app.models.STAR_ELEMENTS)와 같은 순서.
const kStarElements = {
  'situation': '상황',
  'task': '과제',
  'action': '행동',
  'result': '결과',
};

Map<String, ReviewStarCheck> starChecksByPath(Object? raw) => {
  for (final check in (raw as List? ?? const []).whereType<Map>().map(
    ReviewStarCheck.fromMap,
  ))
    if (check.fieldPath.isNotEmpty) check.fieldPath: check,
};

/// 경험 항목 밑의 STAR 네 칸. 빠진 칸은 주황으로, 있는 칸은 초록으로 보인다.
class ReviewStarCells extends StatelessWidget {
  const ReviewStarCells({super.key, required this.check});

  final ReviewStarCheck check;

  @override
  Widget build(BuildContext context) {
    final warn = AppColors.isDark ? AppColors.warning : const Color(0xFFB45309);
    final cells = Wrap(
      spacing: AppSpace.s(4),
      runSpacing: AppSpace.s(4),
      children: [
        for (final entry in kStarElements.entries)
          Semantics(
            label: '${entry.value} ${check.has(entry.key) ? '있음' : '빠짐'}',
            child: Container(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpace.s(6),
                vertical: AppSpace.s(2),
              ),
              decoration: BoxDecoration(
                color: (check.has(entry.key) ? AppColors.success : warn)
                    .withValues(alpha: 0.10),
                borderRadius: BorderRadius.circular(5),
              ),
              child: Text(
                check.has(entry.key) ? '${entry.value} ✓' : '${entry.value} 빠짐',
                style: TextStyle(
                  fontSize: 10,
                  fontWeight: FontWeight.w700,
                  color: check.has(entry.key) ? AppColors.success : warn,
                ),
              ),
            ),
          ),
      ],
    );
    return Padding(
      padding: EdgeInsets.only(top: AppSpace.s(6)),
      child: check.reason.isEmpty
          ? cells
          : Tooltip(message: check.reason, child: cells),
    );
  }
}

String requirementGroupLabel(String group) => switch (group) {
  'must' => '필수',
  'preferred' => '우대',
  _ => '주요 업무',
};

String requirementStatusLabel(String status) => switch (status) {
  'met' => '근거 있음',
  'partial' => '일부만 있음',
  'absent' => '해당 없음',
  _ => '확인 필요',
};

({Color fg, Color bg, IconData icon}) requirementStatusStyle(String status) =>
    switch (status) {
      'met' => (
        fg: AppColors.success,
        bg: AppColors.success.withValues(alpha: 0.10),
        icon: Icons.check_rounded,
      ),
      'partial' => (
        fg: AppColors.isDark ? AppColors.warning : const Color(0xFFB45309),
        bg: AppColors.warning.withValues(alpha: 0.14),
        icon: Icons.change_history_rounded,
      ),
      'absent' => (
        fg: AppColors.textSecondary,
        bg: AppColors.textSecondary.withValues(alpha: 0.10),
        icon: Icons.remove_rounded,
      ),
      _ => (
        // 확인 필요는 "물어볼 차례"라는 뜻이라 강조색이 아니라 뜻이 있는 파랑을 쓴다.
        fg: AppColors.info,
        bg: AppColors.info.withValues(alpha: 0.10),
        icon: Icons.help_outline_rounded,
      ),
    };

/// 대화 위에 붙는 공고 요건 대조 줄. 칩을 누르면 근거가 있는 이력서 항목으로 옮겨 간다.
class ReviewRequirementStrip extends StatefulWidget {
  const ReviewRequirementStrip({
    super.key,
    required this.rows,
    required this.onTapRow,
  });

  final List<ReviewRequirementRow> rows;
  final ValueChanged<ReviewRequirementRow> onTapRow;

  @override
  State<ReviewRequirementStrip> createState() => _ReviewRequirementStripState();
}

class _ReviewRequirementStripState extends State<ReviewRequirementStrip> {
  bool _expanded = true;

  @override
  Widget build(BuildContext context) {
    final groups = ['must', 'preferred'];
    final judged = widget.rows.where((row) => !row.isEligibility).toList();
    final eligibility = widget.rows.where((row) => row.isEligibility).toList();
    String count(String group) {
      final rows = judged.where((row) => row.group == group).toList();
      if (rows.isEmpty) return '';
      final met = rows.where((row) => row.status == 'met').length;
      return '${requirementGroupLabel(group)} $met/${rows.length}';
    }

    final summary = groups
        .map(count)
        .where((text) => text.isNotEmpty)
        .join(' · ');
    return Container(
      width: double.infinity,
      padding: EdgeInsets.fromLTRB(
        AppSpace.s(20),
        AppSpace.s(8),
        AppSpace.s(12),
        AppSpace.s(_expanded ? 12 : 8),
      ),
      decoration: BoxDecoration(
        color: AppColors.surface,
        border: Border(bottom: BorderSide(color: AppColors.border)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Text(
                '공고 요건 대조',
                style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
              ),
              SizedBox(width: AppSpace.s(8)),
              Flexible(
                child: Text(
                  '$summary 근거 확인',
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: 12,
                    color: AppColors.textSecondary,
                  ),
                ),
              ),
              const Spacer(),
              TextButton.icon(
                onPressed: () => setState(() => _expanded = !_expanded),
                style: TextButton.styleFrom(
                  visualDensity: VisualDensity.compact,
                  textStyle: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                icon: Icon(
                  _expanded
                      ? Icons.expand_less_rounded
                      : Icons.expand_more_rounded,
                  size: 18,
                ),
                label: Text(_expanded ? '접기' : '펼치기'),
              ),
            ],
          ),
          if (_expanded)
            for (final group in groups)
              if (judged.any((row) => row.group == group))
                Padding(
                  padding: EdgeInsets.only(top: AppSpace.s(6)),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      SizedBox(
                        width: 32,
                        child: Padding(
                          padding: EdgeInsets.only(top: AppSpace.s(5)),
                          child: Text(
                            requirementGroupLabel(group),
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                              color: AppColors.textSecondary,
                            ),
                          ),
                        ),
                      ),
                      Expanded(
                        child: Wrap(
                          spacing: AppSpace.s(6),
                          runSpacing: AppSpace.s(6),
                          children: [
                            for (final row in judged.where(
                              (row) => row.group == group,
                            ))
                              _RequirementChip(
                                row: row,
                                onTap: () => widget.onTapRow(row),
                              ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
          if (_expanded && eligibility.isNotEmpty)
            Padding(
              padding: EdgeInsets.only(top: AppSpace.s(8)),
              child: Tooltip(
                message: [
                  for (final row in eligibility)
                    '${row.label}: ${row.kindBasis.isEmpty ? '지원 자격' : row.kindBasis}',
                ].join('\n'),
                child: Text.rich(
                  TextSpan(
                    children: [
                      const TextSpan(
                        text: '지원 자격 · 확인만  ',
                        style: TextStyle(fontWeight: FontWeight.w700),
                      ),
                      TextSpan(
                        text: eligibility.map((row) => row.label).join(' · '),
                      ),
                    ],
                  ),
                  key: const ValueKey('review-eligibility-line'),
                  style: TextStyle(
                    fontSize: 11.5,
                    color: AppColors.textSecondary,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _RequirementChip extends StatelessWidget {
  const _RequirementChip({required this.row, required this.onTap});

  final ReviewRequirementRow row;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final style = requirementStatusStyle(row.status);
    return Tooltip(
      message:
          '${requirementStatusLabel(row.status)} · 공고: ${row.postingQuote}',
      child: Material(
        color: style.bg,
        borderRadius: BorderRadius.circular(8),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(8),
          child: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpace.s(8),
              vertical: AppSpace.s(4),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(style.icon, size: 14, color: style.fg),
                SizedBox(width: AppSpace.s(4)),
                Text(
                  row.label,
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: style.fg,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// ① 문장 다듬기 → ② 공고 요건 확인 → ③ 경험 보완 → ④ 지원동기 → ⑤ 자기소개서.
/// [currentStage]가 6 이상이면 모두 끝난 것이다.
class ReviewStageBar extends StatelessWidget {
  const ReviewStageBar({
    super.key,
    required this.currentStage,
    this.includeRequirementStage = true,
  });

  final int currentStage;
  final bool includeRequirementStage;

  @override
  Widget build(BuildContext context) {
    final stages = [
      for (var index = 1; index <= kReviewStageLabels.length; index++)
        if (includeRequirementStage || index != kRequirementStage) index,
    ];
    return Container(
      width: double.infinity,
      padding: EdgeInsets.symmetric(
        horizontal: AppSpace.s(16),
        vertical: AppSpace.s(7),
      ),
      decoration: BoxDecoration(
        color: AppColors.surface,
        border: Border(bottom: BorderSide(color: AppColors.border)),
      ),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          children: [
            for (var i = 0; i < stages.length; i++) ...[
              if (i > 0)
                Container(
                  width: 10,
                  height: 1,
                  margin: EdgeInsets.symmetric(horizontal: AppSpace.s(4)),
                  color: AppColors.border,
                ),
              _StagePill(
                number: i + 1,
                label: reviewStageLabel(stages[i]),
                state: stages[i] < currentStage
                    ? _StageState.done
                    : stages[i] == currentStage
                    ? _StageState.now
                    : _StageState.waiting,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

enum _StageState { waiting, now, done }

class _StagePill extends StatelessWidget {
  const _StagePill({
    required this.number,
    required this.label,
    required this.state,
  });

  final int number;
  final String label;
  final _StageState state;

  @override
  Widget build(BuildContext context) {
    final now = state == _StageState.now;
    final done = state == _StageState.done;
    final fg = now
        ? AppColors.primary
        : done
        ? AppColors.success
        : AppColors.textHint;
    return Semantics(
      label:
          '$label ${now
              ? '진행 중'
              : done
              ? '완료'
              : '대기'}',
      child: Container(
        padding: EdgeInsets.fromLTRB(
          AppSpace.s(4),
          AppSpace.s(3),
          AppSpace.s(9),
          AppSpace.s(3),
        ),
        decoration: BoxDecoration(
          color: now ? AppColors.primaryLight : Colors.transparent,
          borderRadius: BorderRadius.circular(99),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 17,
              height: 17,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: now
                    ? AppColors.primary
                    : done
                    ? AppColors.success
                    : AppColors.surfaceVariant,
              ),
              child: done
                  ? const Icon(
                      Icons.check_rounded,
                      size: 12,
                      color: Colors.white,
                    )
                  : Text(
                      '$number',
                      style: TextStyle(
                        fontSize: 10,
                        fontWeight: FontWeight.w700,
                        color: now ? Colors.white : AppColors.textSecondary,
                      ),
                    ),
            ),
            SizedBox(width: AppSpace.s(5)),
            Text(
              label,
              style: TextStyle(
                fontSize: 11.5,
                fontWeight: now ? FontWeight.w700 : FontWeight.w500,
                color: fg,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// 질문 말풍선·수정안 카드 위에 붙는 작은 표시. 요건에 연결되면 "필수 · Git 협업", 아니면 단계 이름.
class ReviewItemTag extends StatelessWidget {
  const ReviewItemTag({
    super.key,
    required this.text,
    required this.requirementGroup,
  });

  final String text;

  /// 요건에 연결되지 않았으면 null.
  final String? requirementGroup;

  @override
  Widget build(BuildContext context) {
    final linked = requirementGroup != null;
    final fg = linked
        ? (requirementGroup == 'must'
              ? AppColors.info
              : const Color(0xFFB45309))
        : AppColors.textSecondary;
    return Container(
      margin: EdgeInsets.only(bottom: AppSpace.s(5)),
      padding: EdgeInsets.symmetric(
        horizontal: AppSpace.s(7),
        vertical: AppSpace.s(2),
      ),
      decoration: BoxDecoration(
        color: fg.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        text,
        style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: fg),
      ),
    );
  }
}
