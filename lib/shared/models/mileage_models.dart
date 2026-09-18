import 'package:cloud_firestore/cloud_firestore.dart';

import '../../core/constants/mileage_constants.dart';
import '../../core/utils/date_utils.dart';

class MileageCartItemModel {
  const MileageCartItemModel({
    required this.productId,
    required this.productName,
    required this.category,
    required this.pricingType,
    required this.unitPrice,
    this.quantity = 1,
    this.purchaseLink,
  });

  final String productId;
  final String productName;
  final String category;
  final String pricingType;
  final int unitPrice;
  final int quantity;
  final String? purchaseLink;

  int get subtotal => unitPrice * quantity;

  factory MileageCartItemModel.fromMap(Map<String, dynamic> data) {
    return MileageCartItemModel(
      productId: data['productId'] as String? ?? '',
      productName: data['productName'] as String? ?? '',
      category: data['category'] as String? ?? '',
      pricingType: data['pricingType'] as String? ?? MileagePricingTypes.fixed,
      unitPrice: (data['unitPrice'] as num?)?.toInt() ?? 0,
      quantity: (data['quantity'] as num?)?.toInt() ?? 1,
      purchaseLink: data['purchaseLink'] as String?,
    );
  }

  Map<String, dynamic> toMap() => {
        'productId': productId,
        'productName': productName,
        'category': category,
        'pricingType': pricingType,
        'unitPrice': unitPrice,
        'quantity': quantity,
        if (purchaseLink != null && purchaseLink!.isNotEmpty)
          'purchaseLink': purchaseLink,
        'subtotal': subtotal,
      };
}

class PurchaseRequestItemModel {
  const PurchaseRequestItemModel({
    required this.productId,
    required this.productName,
    required this.category,
    required this.pricingType,
    required this.unitPrice,
    required this.quantity,
    this.purchaseLink,
  });

  final String productId;
  final String productName;
  final String category;
  final String pricingType;
  final int unitPrice;
  final int quantity;
  final String? purchaseLink;

  int get subtotal => unitPrice * quantity;

  factory PurchaseRequestItemModel.fromMap(Map<String, dynamic> data) {
    return PurchaseRequestItemModel(
      productId: data['productId'] as String? ?? '',
      productName: data['productName'] as String? ?? '',
      category: data['category'] as String? ?? '',
      pricingType: data['pricingType'] as String? ?? MileagePricingTypes.fixed,
      unitPrice: (data['unitPrice'] as num?)?.toInt() ?? 0,
      quantity: (data['quantity'] as num?)?.toInt() ?? 1,
      purchaseLink: data['purchaseLink'] as String?,
    );
  }

  Map<String, dynamic> toMap() => {
        'productId': productId,
        'productName': productName,
        'category': category,
        'pricingType': pricingType,
        'unitPrice': unitPrice,
        'quantity': quantity,
        if (purchaseLink != null && purchaseLink!.isNotEmpty)
          'purchaseLink': purchaseLink,
        'subtotal': subtotal,
      };
}

class MileageSettingsModel {
  const MileageSettingsModel({
    required this.categoryLimits,
    required this.accrualRules,
    this.updatedAt,
    this.updatedBy,
  });

  final Map<String, int> categoryLimits;
  final Map<String, int> accrualRules;
  final DateTime? updatedAt;
  final String? updatedBy;

  int limitFor(String category) =>
      categoryLimits[category] ??
      MileageDefaults.categoryLimits[category] ??
      0;

  int accrualFor(String recordType) =>
      accrualRules[recordType] ??
      MileageDefaults.accrualRules[recordType] ??
      0;

  factory MileageSettingsModel.defaults() => MileageSettingsModel(
        categoryLimits: Map<String, int>.from(MileageDefaults.categoryLimits),
        accrualRules: Map<String, int>.from(MileageDefaults.accrualRules),
      );

  factory MileageSettingsModel.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    if (!doc.exists) return MileageSettingsModel.defaults();
    final data = doc.data()!;
    return MileageSettingsModel(
      categoryLimits: _intMap(data['categoryLimits']),
      accrualRules: _intMap(data['accrualRules']),
      updatedAt: AppDateUtils.timestampToDateTime(data['updatedAt']),
      updatedBy: data['updatedBy'] as String?,
    );
  }

  Map<String, dynamic> toFirestore({String? updatedBy}) => {
        'categoryLimits': categoryLimits,
        'accrualRules': accrualRules,
        if (updatedBy != null) 'updatedBy': updatedBy,
        'updatedAt': FieldValue.serverTimestamp(),
      };

  static Map<String, int> _intMap(dynamic raw) {
    if (raw is! Map) {
      return Map<String, int>.from(MileageDefaults.categoryLimits);
    }
    return raw.map(
      (key, value) => MapEntry(key.toString(), (value as num?)?.toInt() ?? 0),
    );
  }
}

class MileageProductModel {
  const MileageProductModel({
    required this.id,
    required this.name,
    required this.category,
    required this.pricingType,
    this.description = '',
    this.imageUrl,
    this.fixedPrice,
    this.isActive = true,
    this.sortOrder = 0,
    this.createdAt,
    this.updatedAt,
  });

  final String id;
  final String name;
  final String description;
  final String? imageUrl;
  final String category;
  final String pricingType;
  final int? fixedPrice;
  final bool isActive;
  final int sortOrder;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  bool get isCustomPrice => pricingType == MileagePricingTypes.custom;

  String get categoryLabel => MileageCategories.labelOf(category);

  factory MileageProductModel.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data()!;
    return MileageProductModel(
      id: doc.id,
      name: data['name'] as String? ?? '',
      description: data['description'] as String? ?? '',
      imageUrl: data['imageUrl'] as String?,
      category: data['category'] as String? ?? MileageCategories.gifticon,
      pricingType:
          data['pricingType'] as String? ?? MileagePricingTypes.fixed,
      fixedPrice: (data['fixedPrice'] as num?)?.toInt(),
      isActive: data['isActive'] as bool? ?? true,
      sortOrder: (data['sortOrder'] as num?)?.toInt() ?? 0,
      createdAt: AppDateUtils.timestampToDateTime(data['createdAt']),
      updatedAt: AppDateUtils.timestampToDateTime(data['updatedAt']),
    );
  }

  Map<String, dynamic> toFirestore({bool isCreate = false}) => {
        'name': name,
        if (description.isNotEmpty) 'description': description,
        if (imageUrl != null && imageUrl!.isNotEmpty) 'imageUrl': imageUrl,
        'category': category,
        'pricingType': pricingType,
        if (fixedPrice != null) 'fixedPrice': fixedPrice,
        'isActive': isActive,
        'sortOrder': sortOrder,
        'updatedAt': FieldValue.serverTimestamp(),
        if (isCreate) 'createdAt': FieldValue.serverTimestamp(),
      };
}

class PurchaseRequestModel {
  const PurchaseRequestModel({
    required this.id,
    required this.userId,
    required this.userDisplayName,
    required this.items,
    required this.totalAmount,
    required this.status,
    this.studentNote,
    this.managerMemo,
    this.managerPurchaseLink,
    this.processedAt,
    this.processedBy,
    this.processedByName,
    this.createdAt,
    this.updatedAt,
  });

  final String id;
  final String userId;
  final String userDisplayName;
  final List<PurchaseRequestItemModel> items;
  final int totalAmount;
  final String status;
  final String? studentNote;
  final String? managerMemo;
  final String? managerPurchaseLink;
  final DateTime? processedAt;
  final String? processedBy;
  final String? processedByName;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  String get statusLabel =>
      PurchaseRequestStatus.labels[status] ?? status;

  String get primaryProductName =>
      items.isNotEmpty ? items.first.productName : '-';

  String? get primaryCategory =>
      items.isNotEmpty ? items.first.category : null;

  factory PurchaseRequestModel.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data()!;
    final rawItems = data['items'] as List? ?? [];
    return PurchaseRequestModel(
      id: doc.id,
      userId: data['userId'] as String? ?? '',
      userDisplayName: data['userDisplayName'] as String? ?? '',
      items: rawItems
          .whereType<Map>()
          .map((e) => PurchaseRequestItemModel.fromMap(
                Map<String, dynamic>.from(e),
              ))
          .toList(),
      totalAmount: (data['totalAmount'] as num?)?.toInt() ?? 0,
      status: data['status'] as String? ?? PurchaseRequestStatus.pending,
      studentNote: data['studentNote'] as String?,
      managerMemo: data['managerMemo'] as String?,
      managerPurchaseLink: data['managerPurchaseLink'] as String?,
      processedAt: AppDateUtils.timestampToDateTime(data['processedAt']),
      processedBy: data['processedBy'] as String?,
      processedByName: data['processedByName'] as String?,
      createdAt: AppDateUtils.timestampToDateTime(data['createdAt']),
      updatedAt: AppDateUtils.timestampToDateTime(data['updatedAt']),
    );
  }
}

class MileageCartModel {
  const MileageCartModel({
    required this.userId,
    this.items = const [],
    this.updatedAt,
  });

  final String userId;
  final List<MileageCartItemModel> items;
  final DateTime? updatedAt;

  int get totalAmount =>
      items.fold(0, (total, item) => total + item.subtotal);

  bool get isEmpty => items.isEmpty;

  factory MileageCartModel.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data() ?? {};
    final rawItems = data['items'] as List? ?? [];
    return MileageCartModel(
      userId: doc.id,
      items: rawItems
          .whereType<Map>()
          .map((e) => MileageCartItemModel.fromMap(
                Map<String, dynamic>.from(e),
              ))
          .toList(),
      updatedAt: AppDateUtils.timestampToDateTime(data['updatedAt']),
    );
  }

  Map<String, dynamic> toFirestore() => {
        'items': items.map((e) => e.toMap()).toList(),
        'updatedAt': FieldValue.serverTimestamp(),
      };
}

/// 카테고리별 한도 사용 현황 (학생 UI용)
class MileageCategoryUsageModel {
  const MileageCategoryUsageModel({
    required this.category,
    required this.limit,
    required this.approved,
    required this.pending,
    required this.modifyRequested,
  });

  final String category;
  final int limit;
  final int approved;
  final int pending;
  final int modifyRequested;

  int get used => approved + pending + modifyRequested;

  int get remaining => (limit - used).clamp(0, limit);

  String get categoryLabel => MileageCategories.labelOf(category);
}
