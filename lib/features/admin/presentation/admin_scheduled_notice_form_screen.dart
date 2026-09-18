import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/utils/date_utils.dart';
import '../../../core/widgets/app_dropdown.dart';
import '../../../shared/models/scheduled_notice_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../hub/presentation/widgets/board_ui.dart';
import '../../../core/theme/app_space.dart';

/// 관리자 — 예약 공지 작성/수정
class AdminScheduledNoticeFormScreen extends ConsumerStatefulWidget {
  const AdminScheduledNoticeFormScreen({super.key, this.scheduledId});

  final String? scheduledId;

  @override
  ConsumerState<AdminScheduledNoticeFormScreen> createState() =>
      _AdminScheduledNoticeFormScreenState();
}

class _AdminScheduledNoticeFormScreenState
    extends ConsumerState<AdminScheduledNoticeFormScreen> {
  final _titleController = TextEditingController();
  final _contentController = TextEditingController();
  var _isFavorite = false;
  var _repeatType = ScheduleRepeatType.daily;
  var _publishTime = const TimeOfDay(hour: 9, minute: 0);
  var _publishAt = DateTime.now().add(const Duration(days: 1));
  var _weekday = DateTime.monday;
  var _isActive = true;
  var _loading = false;
  var _initialized = false;

  bool get _isEdit => widget.scheduledId != null;

  @override
  void dispose() {
    _titleController.dispose();
    _contentController.dispose();
    super.dispose();
  }

  void _loadScheduled(List<ScheduledNoticeModel> items) {
    if (_initialized || widget.scheduledId == null) return;
    final item = items.where((n) => n.id == widget.scheduledId).firstOrNull;
    if (item == null) return;
    _titleController.text = item.title;
    _contentController.text = item.content;
    _isFavorite = item.isFavorite;
    _repeatType = item.repeatType;
    _weekday = item.weekday;
    _isActive = item.isActive;
    final parts = item.publishTime.split(':');
    _publishTime = TimeOfDay(
      hour: int.tryParse(parts.first) ?? 9,
      minute: parts.length > 1 ? (int.tryParse(parts[1]) ?? 0) : 0,
    );
    if (item.publishAt != null) _publishAt = item.publishAt!;
    _initialized = true;
  }

  String get _publishTimeString {
    final h = _publishTime.hour.toString().padLeft(2, '0');
    final m = _publishTime.minute.toString().padLeft(2, '0');
    return '$h:$m';
  }

  Future<void> _pickOnceDateTime() async {
    final date = await showDatePicker(
      context: context,
      initialDate: _publishAt,
      firstDate: DateTime.now(),
      lastDate: DateTime.now().add(const Duration(days: 365 * 2)),
    );
    if (date == null || !mounted) return;
    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(_publishAt),
    );
    if (time == null) return;
    setState(() {
      _publishAt = DateTime(
        date.year,
        date.month,
        date.day,
        time.hour,
        time.minute,
      );
    });
  }

  Future<void> _pickPublishTime() async {
    final time = await showTimePicker(
      context: context,
      initialTime: _publishTime,
    );
    if (time != null) setState(() => _publishTime = time);
  }

  Future<void> _save() async {
    final title = _titleController.text.trim();
    final content = _contentController.text.trim();
    if (title.isEmpty || content.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('제목과 내용을 입력해 주세요.')),
      );
      return;
    }

    final user = ref.read(currentUserSyncProvider);
    final cohortId = ref.read(effectiveCohortIdProvider);
    if (user == null || cohortId == null) return;

    setState(() => _loading = true);
    try {
      final repo = ref.read(lmsRepositoryProvider);
      final scheduled = ScheduledNoticeModel(
        id: widget.scheduledId ?? '',
        title: title,
        content: content,
        authorName: user.displayName,
        isFavorite: _isFavorite,
        repeatType: _repeatType,
        publishTime: _publishTimeString,
        publishAt: _repeatType == ScheduleRepeatType.once ? _publishAt : null,
        weekday: _weekday,
        isActive: _isActive,
      );

      if (_isEdit) {
        await repo.updateScheduledNotice(
          cohortId: cohortId,
          scheduled: scheduled,
          authorId: user.uid,
          authorName: user.displayName,
        );
      } else {
        await repo.createScheduledNotice(
          cohortId: cohortId,
          scheduled: scheduled,
          authorId: user.uid,
          authorName: user.displayName,
        );
      }

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(_isEdit ? '예약이 수정되었습니다.' : '예약이 등록되었습니다.')),
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
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheduled = ref.watch(scheduledNoticesProvider);
    scheduled.whenData(_loadScheduled);

    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(
        elevation: 0,
        scrolledUnderElevation: 0,
        backgroundColor: AppColors.surface,
        foregroundColor: AppColors.textPrimary,
        title: Text(
          _isEdit ? '예약 수정' : '예약 공지 등록',
          style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 16),
        ),
        bottom: PreferredSize(
          preferredSize: Size.fromHeight(1),
          child: Divider(height: 1, color: AppColors.border),
        ),
        actions: [
          IconButton(
            tooltip: _isFavorite ? '즐겨찾기 해제' : '게시 시 즐겨찾기',
            onPressed: () => setState(() => _isFavorite = !_isFavorite),
            icon: Icon(
              _isFavorite ? Icons.star_rounded : Icons.star_outline_rounded,
              color: _isFavorite ? BoardUi.favorite : AppColors.textHint,
            ),
          ),
          Padding(
            padding: EdgeInsets.only(right: AppSpace.s(16)),
            child: FilledButton(
              onPressed: _loading ? null : _save,
              style: BoardUi.primaryButtonStyle(),
              child: _loading
                  ? SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    )
                  : Text(_isEdit ? '예약 수정' : '예약 등록'),
            ),
          ),
        ],
      ),
      body: Align(
        alignment: Alignment.topCenter,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: BoardUi.contentMaxWidth),
          child: ListView(
            padding: EdgeInsets.fromLTRB(AppSpace.s(32), AppSpace.s(24), AppSpace.s(32), AppSpace.s(32)),
            children: [
              TextField(
                controller: _titleController,
                decoration: InputDecoration(
                  hintText: '예약 공지 제목을 입력하세요',
                  border: InputBorder.none,
                  enabledBorder: UnderlineInputBorder(
                    borderSide: BorderSide(color: AppColors.border),
                  ),
                  focusedBorder: UnderlineInputBorder(
                    borderSide: BorderSide(color: AppColors.primary, width: 2),
                  ),
                ),
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                ),
              ),
              SizedBox(height: AppSpace.s(16)),
              TextField(
                controller: _contentController,
                decoration: const InputDecoration(
                  hintText: '자동 게시될 공지 내용을 작성하세요.',
                  alignLabelWithHint: true,
                  border: OutlineInputBorder(),
                ),
                minLines: 6,
                maxLines: 12,
              ),
              SizedBox(height: AppSpace.s(28)),
              const Text(
                '게시 일정',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 15),
              ),
              SizedBox(height: AppSpace.s(12)),
              SegmentedButton<ScheduleRepeatType>(
                segments: ScheduleRepeatType.values
                    .map((t) => ButtonSegment(value: t, label: Text(t.label)))
                    .toList(),
                selected: {_repeatType},
                onSelectionChanged: (s) =>
                    setState(() => _repeatType = s.first),
              ),
              SizedBox(height: AppSpace.s(16)),
              if (_repeatType == ScheduleRepeatType.once)
                _SchedulePickerTile(
                  title: '게시 일시',
                  value: AppDateUtils.formatDateTime(_publishAt),
                  icon: Icons.calendar_today_outlined,
                  onTap: _pickOnceDateTime,
                )
              else ...[
                _SchedulePickerTile(
                  title: '게시 시간',
                  value: _publishTimeString,
                  icon: Icons.access_time,
                  onTap: _pickPublishTime,
                ),
                if (_repeatType == ScheduleRepeatType.weekly) ...[
                  SizedBox(height: AppSpace.s(12)),
                  AppDropdownField<int>(
                    value: _weekday,
                    decoration: const InputDecoration(
                      labelText: '요일',
                      border: OutlineInputBorder(),
                    ),
                    items: const [
                      AppDropdownItem(value: DateTime.monday, label: '월요일'),
                      AppDropdownItem(value: DateTime.tuesday, label: '화요일'),
                      AppDropdownItem(value: DateTime.wednesday, label: '수요일'),
                      AppDropdownItem(value: DateTime.thursday, label: '목요일'),
                      AppDropdownItem(value: DateTime.friday, label: '금요일'),
                      AppDropdownItem(value: DateTime.saturday, label: '토요일'),
                      AppDropdownItem(value: DateTime.sunday, label: '일요일'),
                    ],
                    onChanged: (v) {
                      if (v != null) setState(() => _weekday = v);
                    },
                  ),
                ],
              ],
              SizedBox(height: AppSpace.s(20)),
              Container(
                decoration: BoxDecoration(
                  color: BoardUi.listBackground,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: AppColors.border),
                ),
                child: SwitchListTile(
                  value: _isActive,
                  onChanged: (v) => setState(() => _isActive = v),
                  title: const Text(
                    '예약 활성화',
                    style: TextStyle(fontWeight: FontWeight.w600),
                  ),
                  subtitle: Text(
                    '비활성화하면 자동 게시가 중지됩니다.',
                    style: TextStyle(
                      fontSize: 12,
                      color: AppColors.textSecondary,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SchedulePickerTile extends StatelessWidget {
  const _SchedulePickerTile({
    required this.title,
    required this.value,
    required this.icon,
    required this.onTap,
  });

  final String title;
  final String value;
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: EdgeInsets.symmetric(vertical: AppSpace.s(8)),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: TextStyle(
                      fontSize: 13,
                      color: AppColors.textSecondary,
                    ),
                  ),
                  SizedBox(height: AppSpace.s(4)),
                  Text(
                    value,
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),
            Icon(icon, color: AppColors.textHint),
          ],
        ),
      ),
    );
  }
}
