import '../../../core/constants/mileage_constants.dart';
import '../../../shared/models/mileage_models.dart';

/// 관리자 시드용 기본 상품 목록
abstract final class MileageSeedProducts {
  static List<MileageProductModel> defaults() => [
        const MileageProductModel(
          id: '',
          name: '네이버페이 포인트 10,000원',
          category: MileageCategories.gifticon,
          pricingType: MileagePricingTypes.fixed,
          fixedPrice: 10000,
          sortOrder: 1,
        ),
        const MileageProductModel(
          id: '',
          name: '네이버페이 포인트 30,000원',
          category: MileageCategories.gifticon,
          pricingType: MileagePricingTypes.fixed,
          fixedPrice: 30000,
          sortOrder: 2,
        ),
        const MileageProductModel(
          id: '',
          name: '네이버페이 포인트 50,000원',
          category: MileageCategories.gifticon,
          pricingType: MileagePricingTypes.fixed,
          fixedPrice: 50000,
          sortOrder: 3,
        ),
        const MileageProductModel(
          id: '',
          name: '배달의민족 모바일 상품권 3만원권',
          category: MileageCategories.gifticon,
          pricingType: MileagePricingTypes.fixed,
          fixedPrice: 30000,
          sortOrder: 4,
        ),
        const MileageProductModel(
          id: '',
          name: '인프런 강의',
          category: MileageCategories.onlineCourse,
          pricingType: MileagePricingTypes.custom,
          sortOrder: 5,
        ),
        const MileageProductModel(
          id: '',
          name: 'yes24 도서',
          category: MileageCategories.book,
          pricingType: MileagePricingTypes.custom,
          sortOrder: 6,
        ),
      ];
}
