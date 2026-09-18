import 'package:cloud_firestore/cloud_firestore.dart';

import '../../core/constants/mileage_constants.dart';
import '../models/domain_models.dart';
import '../models/mileage_models.dart';

/// 마일리지 CMS Firestore Repository
class MileageRepository {
  MileageRepository(this._firestore);

  final FirebaseFirestore _firestore;

  CollectionReference<Map<String, dynamic>> cohortSub(
    String cohortId,
    String subcollection,
  ) {
    return _firestore
        .collection('cohorts')
        .doc(cohortId)
        .collection(subcollection);
  }

  // ── Settings ──

  Stream<MileageSettingsModel> watchMileageSettings(String cohortId) {
    return cohortSub(cohortId, 'mileageSettings')
        .doc('config')
        .snapshots()
        .map((doc) => MileageSettingsModel.fromFirestore(doc));
  }

  Future<void> saveMileageSettings(
    String cohortId,
    MileageSettingsModel settings, {
    required String updatedBy,
  }) async {
    await cohortSub(cohortId, 'mileageSettings').doc('config').set(
          settings.toFirestore(updatedBy: updatedBy),
          SetOptions(merge: true),
        );
  }

  // ── Products ──

  Stream<List<MileageProductModel>> watchMileageProducts(String cohortId) {
    return cohortSub(cohortId, 'mileageProducts')
        .orderBy('sortOrder')
        .snapshots()
        .map((snap) => snap.docs
            .map(MileageProductModel.fromFirestore)
            .where((p) => p.isActive)
            .toList());
  }

  Stream<List<MileageProductModel>> watchAllMileageProducts(String cohortId) {
    return cohortSub(cohortId, 'mileageProducts')
        .orderBy('sortOrder')
        .snapshots()
        .map((snap) =>
            snap.docs.map(MileageProductModel.fromFirestore).toList());
  }

  Future<String> saveMileageProduct({
    required String cohortId,
    required MileageProductModel product,
  }) async {
    final ref = product.id.isNotEmpty
        ? cohortSub(cohortId, 'mileageProducts').doc(product.id)
        : cohortSub(cohortId, 'mileageProducts').doc();
    final toSave = product.id.isEmpty
        ? product.copyWithId(ref.id)
        : product;
    await ref.set(
      toSave.toFirestore(isCreate: product.id.isEmpty),
      SetOptions(merge: product.id.isNotEmpty),
    );
    return ref.id;
  }

  Future<void> deleteMileageProduct(String cohortId, String productId) async {
    await cohortSub(cohortId, 'mileageProducts').doc(productId).delete();
  }

  // ── Cart ──

  Stream<MileageCartModel> watchMileageCart(String cohortId, String userId) {
    return cohortSub(cohortId, 'mileageCart').doc(userId).snapshots().map(
      (doc) {
        if (!doc.exists) return MileageCartModel(userId: userId);
        return MileageCartModel.fromFirestore(doc);
      },
    );
  }

  Future<void> saveMileageCart({
    required String cohortId,
    required String userId,
    required List<MileageCartItemModel> items,
  }) async {
    await cohortSub(cohortId, 'mileageCart').doc(userId).set({
      'items': items.map((e) => e.toMap()).toList(),
      'updatedAt': FieldValue.serverTimestamp(),
    });
  }

  Future<void> clearMileageCart(String cohortId, String userId) async {
    await cohortSub(cohortId, 'mileageCart').doc(userId).set({
      'items': [],
      'updatedAt': FieldValue.serverTimestamp(),
    });
  }

  // ── Purchase Requests ──

  Stream<List<PurchaseRequestModel>> watchMyPurchaseRequests(
    String cohortId,
    String userId,
  ) {
    return cohortSub(cohortId, 'purchaseRequests')
        .where('userId', isEqualTo: userId)
        .orderBy('createdAt', descending: true)
        .snapshots()
        .map((snap) =>
            snap.docs.map(PurchaseRequestModel.fromFirestore).toList());
  }

  Stream<List<PurchaseRequestModel>> watchAllPurchaseRequests(String cohortId) {
    return cohortSub(cohortId, 'purchaseRequests')
        .orderBy('createdAt', descending: true)
        .snapshots()
        .map((snap) =>
            snap.docs.map(PurchaseRequestModel.fromFirestore).toList());
  }

  // ── Transactions ──

  Stream<List<MileageTransactionModel>> watchMyMileageTransactions(
    String cohortId,
    String userId,
  ) {
    return cohortSub(cohortId, 'mileageTransactions')
        .where('userId', isEqualTo: userId)
        .orderBy('createdAt', descending: true)
        .limit(100)
        .snapshots()
        .map((s) => s.docs.map(MileageTransactionModel.fromFirestore).toList());
  }

  Stream<List<MileageTransactionModel>> watchRecentMileageTransactions(
    String cohortId, {
    int limit = 30,
  }) {
    return cohortSub(cohortId, 'mileageTransactions')
        .orderBy('createdAt', descending: true)
        .limit(limit)
        .snapshots()
        .map((s) => s.docs.map(MileageTransactionModel.fromFirestore).toList());
  }

  /// 카테고리별 사용량 집계 (학생 본인)
  Future<List<MileageCategoryUsageModel>> computeCategoryUsage({
    required String cohortId,
    required String userId,
    required MileageSettingsModel settings,
  }) async {
    final snap = await cohortSub(cohortId, 'purchaseRequests')
        .where('userId', isEqualTo: userId)
        .get();

    final usage = <String, ({int approved, int pending, int modifyRequested})>{
      for (final c in MileageCategories.all)
        c: (approved: 0, pending: 0, modifyRequested: 0),
    };

    for (final doc in snap.docs) {
      final req = PurchaseRequestModel.fromFirestore(doc);
      for (final item in req.items) {
        final cat = item.category;
        if (!usage.containsKey(cat)) continue;
        final amount = item.subtotal;
        final current = usage[cat]!;
        switch (req.status) {
          case PurchaseRequestStatus.approved:
            usage[cat] = (
              approved: current.approved + amount,
              pending: current.pending,
              modifyRequested: current.modifyRequested,
            );
          case PurchaseRequestStatus.pending:
            usage[cat] = (
              approved: current.approved,
              pending: current.pending + amount,
              modifyRequested: current.modifyRequested,
            );
          case PurchaseRequestStatus.modifyRequested:
            usage[cat] = (
              approved: current.approved,
              pending: current.pending,
              modifyRequested: current.modifyRequested + amount,
            );
          default:
            break;
        }
      }
    }

    return MileageCategories.all
        .map(
          (cat) => MileageCategoryUsageModel(
            category: cat,
            limit: settings.limitFor(cat),
            approved: usage[cat]!.approved,
            pending: usage[cat]!.pending,
            modifyRequested: usage[cat]!.modifyRequested,
          ),
        )
        .toList();
  }
}

extension _MileageProductCopy on MileageProductModel {
  MileageProductModel copyWithId(String id) => MileageProductModel(
        id: id,
        name: name,
        description: description,
        imageUrl: imageUrl,
        category: category,
        pricingType: pricingType,
        fixedPrice: fixedPrice,
        isActive: isActive,
        sortOrder: sortOrder,
        createdAt: createdAt,
        updatedAt: updatedAt,
      );
}
