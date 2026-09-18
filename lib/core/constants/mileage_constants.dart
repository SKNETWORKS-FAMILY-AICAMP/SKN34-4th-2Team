/// 마일리지 CMS — 카테고리·상태·타입 상수
abstract final class MileageCategories {
  static const gifticon = 'gifticon';
  static const book = 'book';
  static const onlineCourse = 'onlineCourse';

  static const all = [gifticon, book, onlineCourse];

  static const labels = {
    gifticon: '기프티콘',
    book: '도서',
    onlineCourse: '인터넷 강의',
  };

  static String labelOf(String category) =>
      labels[category] ?? category;
}

abstract final class MileagePricingTypes {
  static const fixed = 'fixed';
  static const custom = 'custom';
}

abstract final class PurchaseRequestStatus {
  static const pending = 'pending';
  static const approved = 'approved';
  static const rejected = 'rejected';
  static const modifyRequested = 'modify_requested';
  static const cancelled = 'cancelled';

  static const all = [
    pending,
    approved,
    rejected,
    modifyRequested,
    cancelled,
  ];

  static const labels = {
    pending: '대기',
    approved: '승인',
    rejected: '반려',
    modifyRequested: '수정 요청',
    cancelled: '취소',
  };

  /// 한도 계산에 포함되는 상태
  static const limitStatuses = [pending, approved, modifyRequested];
}

abstract final class MileageTransactionTypes {
  static const accrual = 'accrual';
  static const redemption = 'redemption';
  static const expiry = 'expiry';
  static const adminAdjust = 'admin_adjust';
}

/// 기수 mileageSettings 기본값
abstract final class MileageDefaults {
  static const categoryLimits = {
    MileageCategories.gifticon: 200000,
    MileageCategories.book: 100000,
    MileageCategories.onlineCourse: 200000,
  };

  static const accrualRules = <String, int>{};
}
