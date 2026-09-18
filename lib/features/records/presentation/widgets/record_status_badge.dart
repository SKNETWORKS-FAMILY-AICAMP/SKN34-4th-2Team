import 'package:flutter/material.dart';

import '../../../../shared/widgets/status_badge.dart';

class RecordStatusBadge extends StatelessWidget {
  const RecordStatusBadge({super.key, required this.status});

  final String status;

  @override
  Widget build(BuildContext context) {
    return switch (status) {
      'approved' => StatusBadge.success('승인'),
      'rejected' => StatusBadge.error('반려'),
      _ => StatusBadge.warning('대기'),
    };
  }
}
