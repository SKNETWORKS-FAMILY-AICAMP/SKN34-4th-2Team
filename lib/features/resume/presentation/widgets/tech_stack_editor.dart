import 'package:flutter/material.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../shared/models/resume_content.dart';
import '../../../../shared/models/tech_skill_level.dart';
import 'skill_catalog.dart';
import '../../../../core/theme/app_space.dart';

/// 기술스택을 태그로 고르고, 숙련도를 설명이 달린 단계로 정하는 편집기.
///
/// - 위: 선택한 기술 태그. 태그를 누르면 그 기술의 숙련도 선택 영역이 열린다.
/// - 아래: 후보 태그. 검색으로 거르고, 후보에 없으면 직접 입력해 추가한다.
/// - 숙련도는 숫자가 아니라 단계 이름과 한 줄 설명을 가로로 늘어놓아 고른다.
class TechStackEditor extends StatefulWidget {
  const TechStackEditor({
    super.key,
    required this.items,
    required this.readOnly,
    required this.onChanged,
  });

  final List<ResumeTechStackItem> items;
  final bool readOnly;
  final ValueChanged<List<ResumeTechStackItem>> onChanged;

  @override
  State<TechStackEditor> createState() => _TechStackEditorState();
}

class _TechStackEditorState extends State<TechStackEditor> {
  /// 한 페이지에 보여줄 후보 수. 187개를 한 번에 펼치면 화면이 길어져 고르기 어렵다.
  static const _pageSize = 40;

  final TextEditingController _search = TextEditingController();
  String _query = '';
  String? _activeId;
  int _page = 0;

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  bool _has(String name) =>
      widget.items.any((item) => SkillCatalog.sameSkill(item.name, name));

  void _add(String rawName) {
    final name = SkillCatalog.canonical(rawName);
    if (name.isEmpty || _has(name)) return;
    final item = ResumeTechStackItem(id: newResumeItemId(), name: name);
    widget.onChanged([...widget.items, item]);
    setState(() {
      _activeId = item.id;
      _query = '';
      _search.clear();
    });
  }

  void _remove(ResumeTechStackItem item) {
    widget.onChanged(widget.items.where((x) => x.id != item.id).toList());
    if (_activeId == item.id) setState(() => _activeId = null);
  }

  void _setLevel(ResumeTechStackItem item, String level) {
    widget.onChanged([
      for (final x in widget.items)
        if (x.id == item.id) x.copyWith(level: level) else x,
    ]);
  }

  @override
  Widget build(BuildContext context) {
    final filled = widget.items.where((item) => item.isFilled).toList();

    if (widget.readOnly) {
      if (filled.isEmpty) {
        return Text('미작성', style: TextStyle(color: AppColors.textHint));
      }
      return Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [for (final item in filled) _SkillTag(item: item)],
      );
    }

    final active = filled.cast<ResumeTechStackItem?>().firstWhere(
      (item) => item!.id == _activeId,
      orElse: () => null,
    );
    // 검색 결과 전체를 페이지로 나눈다. 검색어가 바뀌면 첫 페이지로 돌아간다.
    final matches = SkillCatalog.search(_query).toList();
    final pageCount = matches.isEmpty ? 1 : (matches.length / _pageSize).ceil();
    final page = _page.clamp(0, pageCount - 1);
    final suggestions = matches.skip(page * _pageSize).take(_pageSize).toList();
    final trimmedQuery = _query.trim();
    final canAddCustom =
        trimmedQuery.isNotEmpty &&
        !_has(trimmedQuery) &&
        !matches.any((s) => SkillCatalog.sameSkill(s, trimmedQuery));

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _Label('선택한 기술'),
        SizedBox(height: AppSpace.s(6)),
        if (filled.isEmpty)
          Text(
            '아래에서 태그를 고르거나 직접 입력해 추가하세요.',
            style: TextStyle(fontSize: 13, color: AppColors.textHint),
          )
        else
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final item in filled)
                _SkillTag(
                  item: item,
                  selected: item.id == _activeId,
                  onTap: () => setState(
                    () => _activeId = _activeId == item.id ? null : item.id,
                  ),
                  onDeleted: () => _remove(item),
                ),
            ],
          ),
        if (active != null) ...[
          SizedBox(height: AppSpace.s(12)),
          _LevelPicker(
            item: active,
            onChanged: (level) => _setLevel(active, level),
          ),
        ],
        SizedBox(height: AppSpace.s(18)),
        const _Label('기술 추가'),
        SizedBox(height: AppSpace.s(6)),
        TextField(
          controller: _search,
          decoration: InputDecoration(
            hintText: '기술 검색 또는 직접 입력 후 Enter',
            prefixIcon: const Icon(Icons.search, size: 20),
            suffixIcon: _query.isEmpty
                ? null
                : IconButton(
                    icon: const Icon(Icons.close, size: 18),
                    onPressed: () => setState(() {
                      _query = '';
                      _page = 0;
                      _search.clear();
                    }),
                  ),
            isDense: true,
          ),
          onChanged: (value) => setState(() {
            _query = value;
            _page = 0;
          }),
          onSubmitted: (value) {
            if (value.trim().isEmpty) return;
            // 지금 보이는 페이지가 아니라 검색 결과 전체에서 가장 가까운 것을 고른다.
            final match = matches.isNotEmpty ? matches.first : value;
            _add(SkillCatalog.sameSkill(match, value) ? match : value);
          },
        ),
        SizedBox(height: AppSpace.s(10)),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            if (canAddCustom)
              ActionChip(
                avatar: const Icon(Icons.add, size: 16),
                label: Text("'$trimmedQuery' 추가"),
                onPressed: () => _add(trimmedQuery),
              ),
            for (final name in suggestions)
              FilterChip(
                label: Text(name),
                selected: _has(name),
                showCheckmark: false,
                onSelected: (selected) {
                  if (selected) {
                    _add(name);
                  } else {
                    final item = widget.items.firstWhere(
                      (x) => SkillCatalog.sameSkill(x.name, name),
                    );
                    _remove(item);
                  }
                },
              ),
            if (suggestions.isEmpty && !canAddCustom)
              Text(
                '검색 결과가 없습니다.',
                style: TextStyle(fontSize: 13, color: AppColors.textHint),
              ),
          ],
        ),
        if (matches.length > _pageSize)
          Padding(
            padding: EdgeInsets.only(top: AppSpace.s(6)),
            child: Row(
              children: [
                TextButton.icon(
                  onPressed: page > 0
                      ? () => setState(() => _page = page - 1)
                      : null,
                  icon: const Icon(Icons.chevron_left, size: 18),
                  label: const Text('이전'),
                  style: TextButton.styleFrom(
                    visualDensity: VisualDensity.compact,
                  ),
                ),
                SizedBox(width: AppSpace.s(4)),
                Text(
                  '${page + 1} / $pageCount 페이지 · 전체 ${matches.length}개',
                  style: TextStyle(fontSize: 11, color: AppColors.textHint),
                ),
                SizedBox(width: AppSpace.s(4)),
                TextButton.icon(
                  onPressed: page < pageCount - 1
                      ? () => setState(() => _page = page + 1)
                      : null,
                  icon: const Icon(Icons.chevron_right, size: 18),
                  label: const Text('다음'),
                  // 아이콘을 글자 뒤에 두려고 방향을 뒤집는다.
                  iconAlignment: IconAlignment.end,
                  style: TextButton.styleFrom(
                    visualDensity: VisualDensity.compact,
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

/// 선택한 기술 태그. 숙련도가 있으면 "Python · 중급"처럼 같이 보여준다.
class _SkillTag extends StatelessWidget {
  const _SkillTag({
    required this.item,
    this.selected = false,
    this.onTap,
    this.onDeleted,
  });

  final ResumeTechStackItem item;
  final bool selected;
  final VoidCallback? onTap;
  final VoidCallback? onDeleted;

  @override
  Widget build(BuildContext context) {
    final level = item.level.trim();
    final label = level.isEmpty
        ? item.name.trim()
        : '${item.name.trim()} · $level';
    if (onTap == null && onDeleted == null) {
      return Chip(
        label: Text(label),
        // `height`를 비워 두면 줄 높이가 글꼴 몫대로 잡혀, 받침 있는 한글이
        // 위아래로 잘린다. 기본값(12)보다 큰 글씨를 쓰므로 더 도드라진다.
        labelStyle: const TextStyle(
          fontSize: 13,
          fontWeight: FontWeight.w600,
          height: 1.35,
        ),
        backgroundColor: AppColors.primaryLight,
        side: BorderSide.none,
        visualDensity: VisualDensity.compact,
      );
    }
    return InputChip(
      label: Text(label),
      labelStyle: TextStyle(
        fontSize: 13,
        fontWeight: FontWeight.w600,
        height: 1.35,
        color: selected ? Colors.white : AppColors.textPrimary,
      ),
      labelPadding: EdgeInsets.symmetric(horizontal: AppSpace.s(6), vertical: AppSpace.s(3)),
      selected: selected,
      showCheckmark: false,
      selectedColor: AppColors.primary,
      backgroundColor: AppColors.primaryLight,
      deleteIconColor: selected ? Colors.white : AppColors.textSecondary,
      side: BorderSide.none,
      onPressed: onTap,
      onDeleted: onDeleted,
      tooltip: level.isEmpty ? '눌러서 숙련도 선택' : '숙련도: $level',
    );
  }
}

/// 숙련도 단계를 설명과 함께 가로로 늘어놓고 고르게 한다.
class _LevelPicker extends StatelessWidget {
  const _LevelPicker({required this.item, required this.onChanged});

  final ResumeTechStackItem item;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    final current = item.level.trim();
    final known = techSkillLevelOf(current);

    return Container(
      padding: EdgeInsets.all(AppSpace.s(12)),
      decoration: BoxDecoration(
        border: Border.all(color: AppColors.border),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                '${item.name.trim()} 숙련도',
                style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                ),
              ),
              SizedBox(width: AppSpace.s(8)),
              Text(
                '(선택) 같은 단계를 다시 누르면 지워집니다',
                style: TextStyle(fontSize: 11, color: AppColors.textHint),
              ),
            ],
          ),
          if (current.isNotEmpty && known == null)
            Padding(
              padding: EdgeInsets.only(top: AppSpace.s(4)),
              child: Text(
                "기존 값 '$current'은(는) 단계 목록에 없습니다. 아래에서 다시 고르면 바뀝니다.",
                style: TextStyle(fontSize: 11, color: AppColors.warning),
              ),
            ),
          SizedBox(height: AppSpace.s(10)),
          LayoutBuilder(
            builder: (context, constraints) {
              final wide = constraints.maxWidth >= 560;
              final tiles = [
                for (final level in techSkillLevels)
                  _LevelTile(
                    level: level,
                    selected: known?.label == level.label,
                    horizontal: !wide,
                    onTap: () => onChanged(
                      known?.label == level.label ? '' : level.label,
                    ),
                  ),
              ];
              if (wide) {
                // 설명 길이가 달라도 타일 높이를 맞추기 위해 IntrinsicHeight로 감싼다.
                // Column 안이라 세로 제약이 없어서 stretch만으로는 높이를 정할 수 없다.
                return IntrinsicHeight(
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      for (var i = 0; i < tiles.length; i++) ...[
                        if (i > 0) SizedBox(width: AppSpace.s(6)),
                        Expanded(child: tiles[i]),
                      ],
                    ],
                  ),
                );
              }
              return Column(
                children: [
                  for (var i = 0; i < tiles.length; i++) ...[
                    if (i > 0) SizedBox(height: AppSpace.s(6)),
                    tiles[i],
                  ],
                ],
              );
            },
          ),
        ],
      ),
    );
  }
}

class _LevelTile extends StatelessWidget {
  const _LevelTile({
    required this.level,
    required this.selected,
    required this.horizontal,
    required this.onTap,
  });

  final TechSkillLevel level;
  final bool selected;

  /// 좁은 화면에서는 단계 이름과 설명을 한 줄에 나란히 둔다.
  final bool horizontal;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final label = Text(
      level.label,
      style: TextStyle(
        fontSize: 13,
        fontWeight: FontWeight.w700,
        color: selected ? Colors.white : AppColors.textPrimary,
      ),
    );
    final description = Text(
      level.description,
      style: TextStyle(
        fontSize: 11,
        height: 1.3,
        color: selected ? Colors.white70 : AppColors.textSecondary,
      ),
    );
    return Material(
      color: selected ? AppColors.primary : AppColors.surfaceVariant,
      borderRadius: BorderRadius.circular(8),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: Container(
          padding: EdgeInsets.symmetric(horizontal: AppSpace.s(10), vertical: AppSpace.s(9)),
          decoration: BoxDecoration(
            border: Border.all(
              color: selected ? AppColors.primary : AppColors.border,
            ),
            borderRadius: BorderRadius.circular(8),
          ),
          child: horizontal
              ? Row(
                  children: [
                    SizedBox(width: 48, child: label),
                    SizedBox(width: AppSpace.s(8)),
                    Expanded(child: description),
                  ],
                )
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [label, SizedBox(height: AppSpace.s(3)), description],
                ),
        ),
      ),
    );
  }
}

class _Label extends StatelessWidget {
  const _Label(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
    );
  }
}
