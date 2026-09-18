import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/date_utils.dart';
import '../../../../shared/models/resume_model.dart';
import '../../../../shared/providers/cohort_providers.dart';
import '../../../../shared/providers/lms_providers.dart';
import '../../../../core/theme/app_space.dart';

/// 이력서 항목 아래에 붙는 댓글.
///
/// 옆에 붙은 사이드바 대신 **그 항목 바로 밑에서** 읽고 쓴다. 어느 대목에 대한 말인지
/// 눈을 옮겨 맞출 필요가 없고, 강사가 섹션을 고를 일도 없다 — 연 자리가 곧 섹션이다.
///
/// 읽음은 **펼쳐서 화면에 보인 것만** 넘어간다. 접힌 채로는 줄지 않는다.
class SectionFeedbackThread extends ConsumerStatefulWidget {
  const SectionFeedbackThread({
    super.key,
    required this.resume,
    required this.sectionKey,
    required this.expanded,
    required this.onToggle,
  });

  final ResumeModel resume;
  final String sectionKey;
  final bool expanded;
  final VoidCallback onToggle;

  @override
  ConsumerState<SectionFeedbackThread> createState() =>
      _SectionFeedbackThreadState();
}

/// 작성 시각 오름차순. 시각이 아직 없는 글(방금 보내 서버 시각을 기다리는 글)은 맨 아래로 둔다.
int _byCreatedAt(ResumeFeedbackModel a, ResumeFeedbackModel b) {
  final at = a.createdAt, bt = b.createdAt;
  if (at == null && bt == null) return 0;
  if (at == null) return 1;
  if (bt == null) return -1;
  return at.compareTo(bt);
}

class _SectionFeedbackThreadState extends ConsumerState<SectionFeedbackThread> {
  final _input = TextEditingController();
  bool _sending = false;

  /// 이미 읽음으로 넘긴 피드백. 다시 넘기지 않는다.
  ///
  /// 읽음 처리는 그리는 중에 예약된다. 쓰기가 막히거나(권한) 스트림이 늦으면 안 읽음이
  /// 그대로 남아, 다시 그릴 때마다 같은 쓰기를 또 보낸다. 이력서 편집 화면은 키 입력마다
  /// 다시 그리므로 글자 하나에 쓰기 한 번이 나간다.
  final Set<String> _marked = {};

  /// 지금 답글을 달려는 피드백. 비어 있으면 실을 새로 여는 글이다.
  ResumeFeedbackModel? _replyTo;
  final FocusNode _inputFocus = FocusNode();

  @override
  void dispose() {
    _input.dispose();
    _inputFocus.dispose();
    super.dispose();
  }

  void _startReply(ResumeFeedbackModel target) {
    setState(() => _replyTo = target);
    _inputFocus.requestFocus();
  }

  /// 내가 쓴 글인가. 지우기는 자기 글에만 준다.
  bool _isMine(ResumeFeedbackModel item) {
    final uid = ref.read(currentUserSyncProvider)?.uid;
    return uid != null && uid.isNotEmpty && item.authorId == uid;
  }

  Future<void> _delete(ResumeFeedbackModel item) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('글 삭제'),
        content: const Text('지운 글은 되돌릴 수 없습니다. 삭제할까요?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('취소'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: Text('삭제', style: TextStyle(color: AppColors.error)),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;

    final cohortId = ref.read(effectiveCohortIdProvider);
    if (cohortId == null) return;
    try {
      await ref
          .read(lmsRepositoryProvider)
          .deleteResumeFeedback(
            cohortId: cohortId,
            resumeId: widget.resume.id,
            feedbackId: item.id,
          );
      // 답글을 달던 글이 사라졌으면 대상도 함께 놓는다.
      if (mounted && _replyTo?.id == item.id) {
        setState(() => _replyTo = null);
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('삭제 실패: $error')),
        );
      }
    }
  }

  Future<void> _markRead(List<ResumeFeedbackModel> unread) async {
    final ids = [
      for (final f in unread)
        if (_marked.add(f.id)) f.id,
    ];
    if (ids.isEmpty) return;
    final cohortId = ref.read(effectiveCohortIdProvider);
    if (cohortId == null) return;
    await ref
        .read(lmsRepositoryProvider)
        .markResumeFeedbackRead(
          cohortId: cohortId,
          resumeId: widget.resume.id,
          feedbackIds: ids,
          asReviewer: ref.read(canReviewResumesProvider),
          viewerId: ref.read(currentUserSyncProvider)?.uid,
        );
  }

  Future<void> _send() async {
    final text = _input.text.trim();
    if (text.isEmpty || _sending) return;
    final user = ref.read(currentUserSyncProvider);
    final cohortId = ref.read(effectiveCohortIdProvider);
    if (user == null || cohortId == null) return;

    setState(() => _sending = true);
    try {
      await ref
          .read(lmsRepositoryProvider)
          .addResumeFeedback(
            cohortId: cohortId,
            resumeId: widget.resume.id,
            authorId: user.uid,
            authorName: user.displayName,
            feedback: ResumeFeedbackModel(
              id: '',
              sectionKey: widget.sectionKey,
              content: text,
              authorName: user.displayName,
              authorId: user.uid,
              parentId: _replyTo?.id ?? '',
            ),
          );
      _input.clear();
      if (mounted) setState(() => _replyTo = null);
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('등록 실패: $error')),
        );
      }
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final all = ref
        .watch(resumeFeedbackProvider(widget.resume.id))
        .maybeWhen(
          data: (list) => list,
          orElse: () => const <ResumeFeedbackModel>[],
        );
    // 대화처럼 오래된 글이 위, 새 글이 아래로 오게 시간순으로 놓는다. 스트림은 최신순으로 온다.
    final items = [
      for (final f in all)
        if (f.sectionKey == widget.sectionKey) f,
    ]..sort(_byCreatedAt);
    final asReviewer = ref.watch(canReviewResumesProvider);
    final unread = unreadFeedback(
      items,
      widget.resume,
      asReviewer: asReviewer,
      viewerId: ref.watch(currentUserSyncProvider)?.uid,
    );

    if (widget.expanded && unread.isNotEmpty) {
      // 화면에 보였으니 읽은 것이다. 그리는 중에 쓰지 않도록 프레임 뒤로 미룬다.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _markRead(unread);
      });
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(height: AppSpace.s(8)),
        _ThreadChip(
          count: items.length,
          unread: unread.length,
          open: widget.expanded,
          onTap: widget.onToggle,
        ),
        if (widget.expanded) ...[
          SizedBox(height: AppSpace.s(8)),
          _panel(items, unread, asReviewer),
        ],
      ],
    );
  }

  Widget _panel(
    List<ResumeFeedbackModel> items,
    List<ResumeFeedbackModel> unread,
    bool asReviewer,
  ) {
    final unreadIds = {for (final f in unread) f.id};
    return Container(
      width: double.infinity,
      padding: EdgeInsets.fromLTRB(AppSpace.s(14), AppSpace.s(12), AppSpace.s(14), AppSpace.s(12)),
      decoration: BoxDecoration(
        color: AppColors.tint(const Color(0xFFFBFCFE)),
        border: Border.all(color: AppColors.border),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (items.isEmpty)
            Text(
              '아직 이 항목에 남긴 피드백이 없습니다.',
              style: TextStyle(fontSize: 12.5, color: AppColors.textHint),
            )
          else
            // 첫 글과 그 답글을 묶어 그린다. 부모를 찾지 못한 답글(부모가 지워진
            // 경우)은 첫 글로 올라와 화면에서 사라지지 않게 한다.
            for (final item in threadRoots(items))
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _Comment(
                    item: item,
                    isNew: unreadIds.contains(item.id),
                    mine: item.isReplyOn(widget.resume) != asReviewer,
                    onReply: () => _startReply(item),
                    onDelete: _isMine(item) ? () => _delete(item) : null,
                  ),
                  for (final reply in threadRepliesTo(items, item.id))
                    Padding(
                      padding: EdgeInsets.only(left: AppSpace.s(22)),
                      child: _Comment(
                        item: reply,
                        isNew: unreadIds.contains(reply.id),
                        mine: reply.isReplyOn(widget.resume) != asReviewer,
                        onDelete: _isMine(reply) ? () => _delete(reply) : null,
                      ),
                    ),
                ],
              ),
          SizedBox(height: AppSpace.s(10)),
          _composer(asReviewer),
        ],
      ),
    );
  }

  Widget _composer(bool asReviewer) {
    final target = _replyTo;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // 누구에게 답하는지 입력칸 위에 밝힌다. 실이 길어지면 쓰는 사람도 헷갈린다.
        if (target != null)
          Padding(
            padding: EdgeInsets.only(bottom: AppSpace.s(6)),
            child: Row(
              children: [
                Flexible(
                  child: Text(
                    '${target.authorName}님의 글에 답글',
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 11.5,
                      fontWeight: FontWeight.w600,
                      color: AppColors.primary,
                    ),
                  ),
                ),
                SizedBox(width: AppSpace.s(8)),
                InkWell(
                  onTap: () => setState(() => _replyTo = null),
                  child: Text(
                    '취소',
                    style: TextStyle(
                      fontSize: 11.5,
                      color: AppColors.textSecondary,
                    ),
                  ),
                ),
              ],
            ),
          ),
        _composerRow(asReviewer, target),
      ],
    );
  }

  Widget _composerRow(bool asReviewer, ResumeFeedbackModel? target) {
    return Row(
      children: [
        Expanded(
          child: TextField(
            controller: _input,
            focusNode: _inputFocus,
            minLines: 1,
            maxLines: 4,
            enabled: !_sending,
            textInputAction: TextInputAction.newline,
            style: const TextStyle(fontSize: 13),
            decoration: InputDecoration(
              isDense: true,
              filled: true,
              fillColor: AppColors.surface,
              hintText: target != null
                  ? '${target.authorName}님에게 답글을 적어 주세요'
                  : (asReviewer
                        ? '이 항목에 대한 피드백을 적어 주세요'
                        : '이 항목에 대해 남길 말을 적어 주세요'),
              hintStyle: TextStyle(fontSize: 12.5, color: AppColors.textHint),
              contentPadding: EdgeInsets.symmetric(
                horizontal: AppSpace.s(13),
                vertical: AppSpace.s(10),
              ),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(20),
                borderSide: BorderSide(color: AppColors.border),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(20),
                borderSide: BorderSide(color: AppColors.border),
              ),
            ),
          ),
        ),
        SizedBox(width: AppSpace.s(8)),
        IconButton.filled(
          tooltip: '등록',
          onPressed: _sending ? null : _send,
          icon: _sending
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.send, size: 17),
        ),
      ],
    );
  }
}

/// 항목 머리에 붙는 알약. 접혀 있을 때 여기만 보인다.
class _ThreadChip extends StatelessWidget {
  const _ThreadChip({
    required this.count,
    required this.unread,
    required this.open,
    required this.onTap,
  });

  final int count;
  final int unread;
  final bool open;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final has = count > 0;
    return Align(
      alignment: Alignment.centerLeft,
      child: Material(
        color: has ? AppColors.tint(const Color(0xFFF4F8FF)) : AppColors.surface,
        borderRadius: BorderRadius.circular(20),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(20),
          child: Container(
            padding: EdgeInsets.symmetric(horizontal: AppSpace.s(11), vertical: AppSpace.s(5)),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(20),
              border: Border.all(
                color: has
                    ? AppColors.tint(const Color(0xFFC9DBFF))
                    : AppColors.border,
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (unread > 0) ...[
                  Container(
                    width: 6,
                    height: 6,
                    decoration: BoxDecoration(
                      color: AppColors.error,
                      shape: BoxShape.circle,
                    ),
                  ),
                  SizedBox(width: AppSpace.s(6)),
                ],
                Icon(
                  Icons.mode_comment_outlined,
                  size: 14,
                  color: has ? AppColors.primary : AppColors.textSecondary,
                ),
                SizedBox(width: AppSpace.s(5)),
                Text(
                  has ? '피드백 $count' : '피드백',
                  style: TextStyle(
                    fontSize: 11.5,
                    fontWeight: has ? FontWeight.w500 : FontWeight.w400,
                    color: has ? AppColors.primary : AppColors.textSecondary,
                  ),
                ),
                SizedBox(width: AppSpace.s(3)),
                Icon(
                  open ? Icons.expand_less : Icons.expand_more,
                  size: 15,
                  color: has ? AppColors.primary : AppColors.textSecondary,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Comment extends StatelessWidget {
  const _Comment({
    required this.item,
    required this.isNew,
    required this.mine,
    this.onReply,
    this.onDelete,
  });

  /// 이 글에 답글 달기. 답글에는 주지 않는다 — 답글의 답글은 만들지 않는다.
  final VoidCallback? onReply;

  /// 이 글 지우기. 자기가 쓴 글에만 준다.
  final VoidCallback? onDelete;

  final ResumeFeedbackModel item;
  final bool isNew;

  /// 내가 쓴 글인가. 내 글은 안 읽음 표시가 붙지 않는다.
  final bool mine;

  @override
  Widget build(BuildContext context) {
    final initial = item.authorName.characters.isEmpty
        ? '?'
        : item.authorName.characters.last;
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpace.s(10)),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 26,
            height: 26,
            decoration: BoxDecoration(
              color: mine
                  ? AppColors.tint(const Color(0xFFEAF7EE))
                  : AppColors.primaryLight,
              shape: BoxShape.circle,
            ),
            alignment: Alignment.center,
            child: Text(
              initial,
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w700,
                color: mine ? AppColors.success : AppColors.primary,
              ),
            ),
          ),
          SizedBox(width: AppSpace.s(9)),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Flexible(
                      child: Text(
                        item.authorName,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                    SizedBox(width: AppSpace.s(7)),
                    if (item.createdAt != null)
                      Text(
                        AppDateUtils.formatDateTime(item.createdAt!),
                        style: TextStyle(
                          fontSize: 10.5,
                          color: AppColors.textHint,
                        ),
                      ),
                    if (isNew) ...[
                      SizedBox(width: AppSpace.s(7)),
                      Container(
                        padding: EdgeInsets.symmetric(
                          horizontal: AppSpace.s(5),
                          vertical: AppSpace.s(1),
                        ),
                        decoration: BoxDecoration(
                          color: AppColors.tint(const Color(0xFFFDECEC)),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(
                          '새 글',
                          style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                            color: AppColors.error,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
                SizedBox(height: AppSpace.s(2)),
                Text(
                  item.content,
                  style: TextStyle(
                    fontSize: 12.5,
                    height: 1.55,
                    color: AppColors.textSecondary,
                  ),
                ),
                if (onReply != null || onDelete != null)
                  Padding(
                    padding: EdgeInsets.symmetric(vertical: AppSpace.s(3)),
                    child: Row(
                      children: [
                        if (onReply != null)
                          InkWell(
                            onTap: onReply,
                            child: Text(
                              '답글',
                              style: TextStyle(
                                fontSize: 11.5,
                                fontWeight: FontWeight.w600,
                                color: AppColors.primary,
                              ),
                            ),
                          ),
                        if (onReply != null && onDelete != null)
                          SizedBox(width: AppSpace.s(12)),
                        if (onDelete != null)
                          InkWell(
                            onTap: onDelete,
                            child: Text(
                              '삭제',
                              style: TextStyle(
                                fontSize: 11.5,
                                fontWeight: FontWeight.w600,
                                color: AppColors.textHint,
                              ),
                            ),
                          ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
