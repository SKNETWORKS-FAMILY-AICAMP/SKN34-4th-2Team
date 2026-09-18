import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/app_colors.dart';
import '../../../shared/models/alert_popup_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../hub/presentation/widgets/board_ui.dart';
import '../../../core/theme/app_space.dart';

/// 관리자 — 알림 팝업 작성/수정
class AdminAlertPopupFormScreen extends ConsumerStatefulWidget {
  const AdminAlertPopupFormScreen({super.key, this.popupId});

  final String? popupId;

  @override
  ConsumerState<AdminAlertPopupFormScreen> createState() =>
      _AdminAlertPopupFormScreenState();
}

class _AdminAlertPopupFormScreenState
    extends ConsumerState<AdminAlertPopupFormScreen> {
  final _titleController = TextEditingController();
  final _contentController = TextEditingController();
  final _linkController = TextEditingController();
  final _sortController = TextEditingController(text: '0');
  var _isActive = true;
  var _useTimeWindow = false;
  var _startTime = const TimeOfDay(hour: 8, minute: 30);
  var _endTime = const TimeOfDay(hour: 18, minute: 0);
  var _loading = false;
  var _initialized = false;

  bool get _isEdit => widget.popupId != null;

  @override
  void dispose() {
    _titleController.dispose();
    _contentController.dispose();
    _linkController.dispose();
    _sortController.dispose();
    super.dispose();
  }

  TimeOfDay _parseTime(String? raw, TimeOfDay fallback) {
    if (raw == null || raw.isEmpty) return fallback;
    final parts = raw.split(':');
    return TimeOfDay(
      hour: int.tryParse(parts.first) ?? fallback.hour,
      minute: parts.length > 1
          ? (int.tryParse(parts[1]) ?? fallback.minute)
          : fallback.minute,
    );
  }

  String _formatTime(TimeOfDay t) {
    final h = t.hour.toString().padLeft(2, '0');
    final m = t.minute.toString().padLeft(2, '0');
    return '$h:$m';
  }

  void _load(List<AlertPopupModel> list) {
    if (_initialized || widget.popupId == null) return;
    final popup = list.where((p) => p.id == widget.popupId).firstOrNull;
    if (popup == null) return;
    _titleController.text = popup.title;
    _contentController.text = popup.content;
    _linkController.text = popup.linkUrl ?? '';
    _sortController.text = '${popup.sortOrder}';
    _isActive = popup.isActive;
    _useTimeWindow = popup.hasTimeWindow;
    _startTime = _parseTime(popup.startTime, _startTime);
    _endTime = _parseTime(popup.endTime, _endTime);
    _initialized = true;
  }

  Future<void> _pickStart() async {
    final picked = await showTimePicker(
      context: context,
      initialTime: _startTime,
    );
    if (picked != null) setState(() => _startTime = picked);
  }

  Future<void> _pickEnd() async {
    final picked = await showTimePicker(
      context: context,
      initialTime: _endTime,
    );
    if (picked != null) setState(() => _endTime = picked);
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
      final link = _linkController.text.trim();
      final popup = AlertPopupModel(
        id: widget.popupId ?? '',
        title: title,
        content: content,
        authorName: user.displayName,
        isActive: _isActive,
        sortOrder: int.tryParse(_sortController.text.trim()) ?? 0,
        linkUrl: link.isEmpty ? null : link,
        startTime: _useTimeWindow ? _formatTime(_startTime) : null,
        endTime: _useTimeWindow ? _formatTime(_endTime) : null,
      );

      if (_isEdit) {
        await repo.updateAlertPopup(
          cohortId: cohortId,
          popup: popup,
          authorId: user.uid,
          authorName: user.displayName,
        );
      } else {
        await repo.createAlertPopup(
          cohortId: cohortId,
          popup: popup,
          authorId: user.uid,
          authorName: user.displayName,
        );
      }

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(_isEdit ? '알림 팝업이 수정되었습니다.' : '알림 팝업이 등록되었습니다.'),
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
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final popups = ref.watch(alertPopupsAdminProvider);
    popups.whenData(_load);

    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(
        title: Text(_isEdit ? '알림 팝업 수정' : '알림 팝업 등록'),
        actions: [
          Padding(
            padding: EdgeInsets.only(right: AppSpace.s(8)),
            child: FilledButton(
              onPressed: _loading ? null : _save,
              style: BoardUi.primaryButtonStyle(),
              child: _loading
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('저장'),
            ),
          ),
        ],
      ),
      body: ListView(
        padding: EdgeInsets.all(AppSpace.s(24)),
        children: [
          Text(
            '활성 팝업은 학생 대시보드에 바로 뜹니다. 시간 구간을 끄면 하루 종일 표시됩니다.',
            style: TextStyle(fontSize: 13, color: AppColors.textSecondary),
          ),
          SizedBox(height: AppSpace.s(20)),
          TextField(
            controller: _titleController,
            decoration: const InputDecoration(
              labelText: '제목',
              hintText: '예: 오늘 예외 출결 제출',
            ),
          ),
          SizedBox(height: AppSpace.s(16)),
          TextField(
            controller: _contentController,
            minLines: 5,
            maxLines: 12,
            decoration: const InputDecoration(
              labelText: '내용',
              hintText: '매일 꼭 해야 할 일을 적어 주세요.',
              alignLabelWithHint: true,
            ),
          ),
          SizedBox(height: AppSpace.s(16)),
          TextField(
            controller: _linkController,
            decoration: const InputDecoration(
              labelText: '링크 (선택)',
              hintText: 'https://forms.gle/...',
            ),
            keyboardType: TextInputType.url,
          ),
          SizedBox(height: AppSpace.s(20)),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('표시 시간 설정'),
            subtitle: Text(
              _useTimeWindow
                  ? '${_formatTime(_startTime)} ~ ${_formatTime(_endTime)} 사이에만 표시'
                  : '하루 종일 로그인 시 표시',
              style: const TextStyle(fontSize: 12),
            ),
            value: _useTimeWindow,
            onChanged: (v) => setState(() => _useTimeWindow = v),
          ),
          if (_useTimeWindow) ...[
            SizedBox(height: AppSpace.s(8)),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _pickStart,
                    icon: const Icon(Icons.schedule, size: 18),
                    label: Text('시작 ${_formatTime(_startTime)}'),
                  ),
                ),
                SizedBox(width: AppSpace.s(12)),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _pickEnd,
                    icon: const Icon(Icons.schedule, size: 18),
                    label: Text('종료 ${_formatTime(_endTime)}'),
                  ),
                ),
              ],
            ),
            SizedBox(height: AppSpace.s(8)),
            Builder(
              builder: (context) {
                final preview = AlertPopupModel(
                  id: '',
                  title: '',
                  content: '',
                  authorName: '',
                  startTime: _formatTime(_startTime),
                  endTime: _formatTime(_endTime),
                );
                final visible = preview.isVisibleAt(DateTime.now());
                final now = TimeOfDay.now();
                final nowLabel =
                    '${now.hour.toString().padLeft(2, '0')}:${now.minute.toString().padLeft(2, '0')}';
                return Text(
                  visible
                      ? '지금($nowLabel) 학생에게 표시됩니다.'
                      : '지금($nowLabel)은 표시 구간 밖입니다. 구간 안에 로그인하거나, 앱을 켠 채로 시작 시각이 되면 뜹니다.',
                  style: TextStyle(
                    fontSize: 12,
                    color: visible ? const Color(0xFF16A34A) : AppColors.warning,
                    fontWeight: FontWeight.w600,
                  ),
                );
              },
            ),
          ],
          SizedBox(height: AppSpace.s(16)),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _sortController,
                  decoration: const InputDecoration(
                    labelText: '표시 순서 (작을수록 먼저)',
                  ),
                  keyboardType: TextInputType.number,
                ),
              ),
              SizedBox(width: AppSpace.s(16)),
              const Text('활성'),
              Switch(
                value: _isActive,
                onChanged: (v) => setState(() => _isActive = v),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
