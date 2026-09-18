import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../../core/theme/app_space.dart';

/// 드롭다운/팝업 메뉴 공통 패널 스타일 — 떠 있는 박스감 줄이고 트리거에 붙는 느낌.
abstract final class AppMenuStyles {
  static MenuStyle get panel => MenuStyle(
    backgroundColor: WidgetStatePropertyAll(AppColors.surface),
    elevation: const WidgetStatePropertyAll(2),
    shadowColor: WidgetStatePropertyAll(
      Colors.black.withValues(alpha: 0.06),
    ),
    shape: WidgetStatePropertyAll(
      RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(10),
        side: BorderSide(color: AppColors.border),
      ),
    ),
    padding: WidgetStatePropertyAll(
      EdgeInsets.symmetric(vertical: AppSpace.s(4)),
    ),
    visualDensity: VisualDensity.compact,
  );

  /// 트리거와 동일한 너비로 메뉴를 고정.
  static MenuStyle matchedPanel(double width) {
    final w = width.clamp(1.0, 2000.0);
    return panel.copyWith(
      minimumSize: WidgetStatePropertyAll(Size(w, 0)),
      maximumSize: WidgetStatePropertyAll(Size(w, 360)),
    );
  }

  static PopupMenuThemeData get popupTheme => PopupMenuThemeData(
    color: AppColors.surface,
    elevation: 2,
    shadowColor: Colors.black.withValues(alpha: 0.06),
    shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(10),
      side: BorderSide(color: AppColors.border),
    ),
    textStyle: TextStyle(
      fontSize: 13,
      color: AppColors.textPrimary,
    ),
  );
}

class AppDropdownItem<T> {
  const AppDropdownItem({
    required this.value,
    required this.label,
    this.child,
    this.enabled = true,
  });

  final T value;
  final String label;
  final Widget? child;
  final bool enabled;

  Widget get display =>
      child ??
      Text(
        label,
        overflow: TextOverflow.ellipsis,
        maxLines: 1,
        style: TextStyle(fontSize: 14, color: AppColors.textPrimary),
      );
}

Widget _menuItem({
  required double width,
  required bool selected,
  required VoidCallback? onPressed,
  required Widget child,
  EdgeInsetsGeometry? padding,
}) {
  padding ??= EdgeInsets.symmetric(
    horizontal: AppSpace.s(12),
    vertical: AppSpace.s(10),
  );
  return MenuItemButton(
    onPressed: onPressed,
    style: ButtonStyle(
      minimumSize: WidgetStatePropertyAll(Size(width, 40)),
      maximumSize: WidgetStatePropertyAll(Size(width, 64)),
      backgroundColor: WidgetStateProperty.resolveWith((states) {
        if (selected) return AppColors.primaryLight;
        if (states.contains(WidgetState.hovered) ||
            states.contains(WidgetState.focused)) {
          return AppColors.surfaceVariant;
        }
        return Colors.transparent;
      }),
      padding: WidgetStatePropertyAll(padding),
      visualDensity: VisualDensity.compact,
      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
    ),
    child: Align(
      alignment: Alignment.centerLeft,
      widthFactor: 1,
      child: child,
    ),
  );
}

/// 트리거와 메뉴 너비를 강제로 동일하게 맞추는 MenuAnchor.
class _MatchedMenuAnchor extends StatefulWidget {
  const _MatchedMenuAnchor({
    required this.trigger,
    required this.menuChildren,
    this.forceWidth,
  });

  final Widget Function(BuildContext context, MenuController controller)
  trigger;
  final List<Widget> Function(double width) menuChildren;
  final double? forceWidth;

  @override
  State<_MatchedMenuAnchor> createState() => _MatchedMenuAnchorState();
}

class _MatchedMenuAnchorState extends State<_MatchedMenuAnchor> {
  final _key = GlobalKey();
  double _measured = 0;

  double get _width {
    final forced = widget.forceWidth;
    if (forced != null && forced.isFinite && forced > 0) return forced;
    return _measured;
  }

  void _measure() {
    if (widget.forceWidth != null) return;
    final box = _key.currentContext?.findRenderObject() as RenderBox?;
    if (box == null || !box.hasSize) return;
    final next = box.size.width;
    if ((next - _measured).abs() > 0.5) {
      setState(() => _measured = next);
    }
  }

  @override
  Widget build(BuildContext context) {
    final width = _width;
    return MenuAnchor(
      crossAxisUnconstrained: false,
      style: width > 0
          ? AppMenuStyles.matchedPanel(width)
          : AppMenuStyles.panel,
      alignmentOffset: const Offset(0, 2),
      builder: (context, controller, _) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) _measure();
        });
        return KeyedSubtree(
          key: _key,
          child: widget.trigger(context, controller),
        );
      },
      menuChildren: width > 0 ? widget.menuChildren(width) : const [],
    );
  }
}

/// 폼 필드형 드롭다운 — 메뉴 너비가 필드와 같고 아래로 펼쳐짐.
class AppDropdownField<T> extends StatelessWidget {
  const AppDropdownField({
    super.key,
    required this.items,
    required this.onChanged,
    this.value,
    this.decoration = const InputDecoration(),
    this.isDense = false,
    this.enabled = true,
  });

  final T? value;
  final List<AppDropdownItem<T>> items;
  final ValueChanged<T?>? onChanged;
  final InputDecoration decoration;
  final bool isDense;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final selected = _findSelected();
    final canOpen = enabled && onChanged != null && items.isNotEmpty;

    Widget trigger(BuildContext context, MenuController controller) {
      final open = controller.isOpen;
      return Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(10),
          onTap: canOpen
              ? () {
                  if (open) {
                    controller.close();
                  } else {
                    controller.open();
                  }
                }
              : null,
          child: InputDecorator(
            isFocused: open,
            isEmpty: selected == null,
            decoration: decoration.copyWith(
              isDense: isDense || (decoration.isDense ?? false),
              enabled: canOpen,
              suffixIcon: Icon(
                open
                    ? Icons.keyboard_arrow_up_rounded
                    : Icons.keyboard_arrow_down_rounded,
                size: 20,
                color: AppColors.textSecondary,
              ),
            ),
            child: selected != null
                ? selected.display
                : Text(
                    decoration.hintText ?? '',
                    style: TextStyle(
                      fontSize: isDense ? 13 : 14,
                      color: AppColors.textHint,
                    ),
                  ),
          ),
        ),
      );
    }

    List<Widget> menus(double width) => [
      for (final item in items)
        _menuItem(
          width: width,
          selected: value == item.value,
          onPressed: item.enabled && onChanged != null
              ? () => onChanged!(item.value)
              : null,
          child: item.display,
        ),
    ];

    return LayoutBuilder(
      builder: (context, constraints) {
        final maxW = constraints.maxWidth;
        final force = maxW.isFinite && maxW < double.infinity && maxW > 0
            ? maxW
            : null;
        return _MatchedMenuAnchor(
          forceWidth: force,
          trigger: trigger,
          menuChildren: menus,
        );
      },
    );
  }

  AppDropdownItem<T>? _findSelected() {
    if (value == null) return null;
    for (final item in items) {
      if (item.value == value) return item;
    }
    return null;
  }
}

/// 테이블·인라인용 컴팩트 드롭다운 — 트리거 너비에 메뉴를 맞춤.
class AppDropdownInline<T> extends StatelessWidget {
  const AppDropdownInline({
    super.key,
    required this.items,
    required this.onChanged,
    this.value,
    this.hint,
    this.isExpanded = false,
    this.fontSize = 13,
    this.enabled = true,
  });

  final T? value;
  final List<AppDropdownItem<T>> items;
  final ValueChanged<T?>? onChanged;
  final String? hint;
  final bool isExpanded;
  final double fontSize;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final selected = _findSelected();
    final canOpen = enabled && onChanged != null && items.isNotEmpty;

    Widget trigger(BuildContext context, MenuController controller) {
      final open = controller.isOpen;
      final label =
          selected?.display ??
          Text(
            hint ?? '',
            style: TextStyle(fontSize: fontSize, color: AppColors.textHint),
          );
      final row = Row(
        mainAxisSize: isExpanded ? MainAxisSize.max : MainAxisSize.min,
        children: [
          if (isExpanded) Expanded(child: label) else label,
          Icon(
            open
                ? Icons.keyboard_arrow_up_rounded
                : Icons.keyboard_arrow_down_rounded,
            size: 16,
            color: AppColors.textSecondary,
          ),
        ],
      );
      return InkWell(
        onTap: canOpen
            ? () {
                if (open) {
                  controller.close();
                } else {
                  controller.open();
                }
              }
            : null,
        borderRadius: BorderRadius.circular(6),
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: AppSpace.s(4), vertical: AppSpace.s(2)),
          child: DefaultTextStyle.merge(
            style: TextStyle(fontSize: fontSize, color: AppColors.textPrimary),
            child: row,
          ),
        ),
      );
    }

    List<Widget> menus(double width) => [
      for (final item in items)
        _menuItem(
          width: width,
          selected: value == item.value,
          onPressed: item.enabled && onChanged != null
              ? () => onChanged!(item.value)
              : null,
          padding: EdgeInsets.symmetric(horizontal: AppSpace.s(10), vertical: AppSpace.s(8)),
          child: DefaultTextStyle.merge(
            style: TextStyle(fontSize: fontSize),
            child: item.display,
          ),
        ),
    ];

    final menu = LayoutBuilder(
      builder: (context, constraints) {
        final maxW = constraints.maxWidth;
        final force = maxW.isFinite && maxW < double.infinity && maxW > 0
            ? maxW
            : null;
        return _MatchedMenuAnchor(
          forceWidth: force,
          trigger: trigger,
          menuChildren: menus,
        );
      },
    );

    if (isExpanded) {
      return SizedBox(width: double.infinity, child: menu);
    }
    return menu;
  }

  AppDropdownItem<T>? _findSelected() {
    if (value == null) return null;
    for (final item in items) {
      if (item.value == value) return item;
    }
    return null;
  }
}

class AppMenuAction<T> {
  const AppMenuAction({
    required this.value,
    required this.label,
    this.danger = false,
    this.enabled = true,
  });

  final T value;
  final String label;
  final bool danger;
  final bool enabled;
}

/// ⋯ 아이콘 액션 메뉴 — 패널 스타일만 통일 (너비는 내용에 맞춤).
class AppIconMenu<T> extends StatelessWidget {
  const AppIconMenu({
    super.key,
    required this.items,
    required this.onSelected,
    this.icon = const Icon(Icons.more_vert),
    this.tooltip,
    this.iconSize,
    this.color,
    this.padding,
  });

  final List<AppMenuAction<T>> items;
  final ValueChanged<T> onSelected;
  final Widget icon;
  final String? tooltip;
  final double? iconSize;
  final Color? color;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) {
    return MenuAnchor(
      style: AppMenuStyles.panel,
      alignmentOffset: const Offset(0, 2),
      builder: (context, controller, _) {
        return IconButton(
          tooltip: tooltip,
          padding: padding,
          constraints: padding != null
              ? const BoxConstraints(minWidth: 32, minHeight: 32)
              : null,
          iconSize: iconSize,
          color: color,
          icon: icon,
          onPressed: items.isEmpty
              ? null
              : () {
                  if (controller.isOpen) {
                    controller.close();
                  } else {
                    controller.open();
                  }
                },
        );
      },
      menuChildren: [
        for (final item in items)
          MenuItemButton(
            onPressed: item.enabled ? () => onSelected(item.value) : null,
            style: ButtonStyle(
              backgroundColor: WidgetStateProperty.resolveWith((states) {
                if (states.contains(WidgetState.hovered) ||
                    states.contains(WidgetState.focused)) {
                  return AppColors.surfaceVariant;
                }
                return Colors.transparent;
              }),
              padding: WidgetStatePropertyAll(
                EdgeInsets.symmetric(horizontal: AppSpace.s(14), vertical: AppSpace.s(10)),
              ),
            ),
            child: Text(
              item.label,
              style: TextStyle(
                fontSize: 13,
                color: item.danger ? AppColors.error : AppColors.textPrimary,
              ),
            ),
          ),
      ],
    );
  }
}
