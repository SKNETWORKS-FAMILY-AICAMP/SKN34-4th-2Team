import 'dart:math';

import '../models/project_team_model.dart';
import '../models/seating_layout_model.dart';

/// 팀 단위로 **상하좌우 인접** 좌석에 배정
abstract final class TeamSeatingAssigner {
  /// 반환: seatId → userId
  static Map<String, String> assign({
    required SeatingLayoutModel layout,
    required List<ProjectTeamModel> teams,
    Random? random,
  }) {
    final rng = random ?? Random();
    final activeTeams = teams
        .where((t) => t.memberIds.isNotEmpty)
        .map(
          (t) => t.copyWith(memberIds: [...t.memberIds]..shuffle(rng)),
        )
        .toList()
      ..shuffle(rng);

    final byId = {
      for (final c in layout.seatCells) c.seatId: c,
    };
    final adj = _adjacency(layout);
    final free = byId.keys.toSet();
    final result = <String, String>{};

    for (final team in activeTeams) {
      final need = team.memberIds.length;
      if (need == 0 || free.isEmpty) continue;

      final seats = _findNearbyCluster(
        byId: byId,
        adj: adj,
        free: free,
        need: need,
        rng: rng,
      );
      for (var i = 0; i < seats.length && i < need; i++) {
        result[seats[i]] = team.memberIds[i];
        free.remove(seats[i]);
      }
    }

    return result;
  }

  /// 가능한 한 붙어 있는 [need]석을 고른다.
  static List<String> _findNearbyCluster({
    required Map<String, SeatingCell> byId,
    required Map<String, List<String>> adj,
    required Set<String> free,
    required int need,
    required Random rng,
  }) {
    // 1) 같은 groupId(책상) 안에서 먼저 찾기
    final byGroup = <String, List<String>>{};
    for (final id in free) {
      final gid = byId[id]?.groupId;
      if (gid == null || gid.isEmpty) continue;
      byGroup.putIfAbsent(gid, () => []).add(id);
    }
    final groupIds = byGroup.keys.toList()..shuffle(rng);
    for (final gid in groupIds) {
      final pool = byGroup[gid]!;
      if (pool.length < need) continue;
      final cluster = _compactConnectedSubset(
        candidates: pool.toSet(),
        adj: adj,
        byId: byId,
        need: need,
        rng: rng,
      );
      if (cluster != null) return cluster;
    }

    // 2) 전체 빈 좌석의 연결 요소에서 콤팩트한 덩어리
    final components = _connectedComponents(adj, free)
      ..sort((a, b) => b.length.compareTo(a.length));
    for (final comp in components) {
      if (comp.length < need) continue;
      final cluster = _compactConnectedSubset(
        candidates: comp.toSet(),
        adj: adj,
        byId: byId,
        need: need,
        rng: rng,
      );
      if (cluster != null) return cluster;
    }

    // 3) 한 덩어리에 부족하면: 큰 덩어리 + 가장 가까운 다른 덩어리
    return _fillAcrossComponents(
      components: components,
      adj: adj,
      byId: byId,
      need: need,
      rng: rng,
    );
  }

  /// candidates 안에서 연결되며 bounding-box가 작은 [need]석
  static List<String>? _compactConnectedSubset({
    required Set<String> candidates,
    required Map<String, List<String>> adj,
    required Map<String, SeatingCell> byId,
    required int need,
    required Random rng,
  }) {
    if (candidates.length < need) return null;

    List<String>? best;
    var bestScore = 1 << 30;
    final seeds = candidates.toList()..shuffle(rng);

    for (final seed in seeds) {
      final taken = _bfsTake(
        start: seed,
        allowed: candidates,
        adj: adj,
        limit: need,
      );
      if (taken.length < need) continue;
      final score = _bboxScore(taken, byId);
      if (score < bestScore) {
        bestScore = score;
        best = taken;
        if (bestScore <= need) break; // 한 줄/한 칸에 가깝게 모인 경우
      }
    }
    return best;
  }

  static List<String> _fillAcrossComponents({
    required List<List<String>> components,
    required Map<String, List<String>> adj,
    required Map<String, SeatingCell> byId,
    required int need,
    required Random rng,
  }) {
    if (components.isEmpty) return const [];

    final picked = <String>[];
    final remaining = [...components];

    // 가장 큰 요소에서 가능한 만큼
    remaining.sort((a, b) => b.length.compareTo(a.length));
    final first = remaining.removeAt(0);
    final firstTake = _compactConnectedSubset(
          candidates: first.toSet(),
          adj: adj,
          byId: byId,
          need: min(need, first.length),
          rng: rng,
        ) ??
        (first.toList()..shuffle(rng)).take(min(need, first.length)).toList();
    picked.addAll(firstTake);

    while (picked.length < need && remaining.isNotEmpty) {
      final centroid = _centroid(picked, byId);
      remaining.sort((a, b) {
        final da = _distToSet(a, centroid, byId);
        final db = _distToSet(b, centroid, byId);
        return da.compareTo(db);
      });
      final next = remaining.removeAt(0);
      final want = need - picked.length;
      final more = _compactConnectedSubset(
            candidates: next.toSet(),
            adj: adj,
            byId: byId,
            need: min(want, next.length),
            rng: rng,
          ) ??
          (next.toList()..shuffle(rng)).take(min(want, next.length)).toList();
      picked.addAll(more);
    }

    return picked.take(need).toList();
  }

  static List<String> _bfsTake({
    required String start,
    required Set<String> allowed,
    required Map<String, List<String>> adj,
    required int limit,
  }) {
    if (!allowed.contains(start) || limit <= 0) return const [];
    final out = <String>[];
    final seen = <String>{start};
    final queue = <String>[start];
    while (queue.isNotEmpty && out.length < limit) {
      final cur = queue.removeAt(0);
      out.add(cur);
      for (final n in adj[cur] ?? const []) {
        if (!allowed.contains(n) || !seen.add(n)) continue;
        queue.add(n);
      }
    }
    return out;
  }

  static List<List<String>> _connectedComponents(
    Map<String, List<String>> adj,
    Set<String> nodes,
  ) {
    final seen = <String>{};
    final comps = <List<String>>[];
    for (final start in nodes) {
      if (!seen.add(start)) continue;
      final comp = <String>[];
      final queue = <String>[start];
      while (queue.isNotEmpty) {
        final cur = queue.removeAt(0);
        comp.add(cur);
        for (final n in adj[cur] ?? const []) {
          if (!nodes.contains(n) || !seen.add(n)) continue;
          queue.add(n);
        }
      }
      comps.add(comp);
    }
    return comps;
  }

  /// 상하좌우로 붙은 좌석만 이웃
  static Map<String, List<String>> _adjacency(SeatingLayoutModel layout) {
    final grid = <String, SeatingCell>{};
    for (final c in layout.seatCells) {
      grid['${c.row},${c.col}'] = c;
    }
    const deltas = [(-1, 0), (1, 0), (0, -1), (0, 1)];
    final adj = <String, List<String>>{};
    for (final c in layout.seatCells) {
      final neighbors = <String>[];
      for (final d in deltas) {
        final other = grid['${c.row + d.$1},${c.col + d.$2}'];
        if (other != null) neighbors.add(other.seatId);
      }
      adj[c.seatId] = neighbors;
    }
    return adj;
  }

  static int _bboxScore(List<String> seats, Map<String, SeatingCell> byId) {
    var minR = 1 << 20, maxR = 0, minC = 1 << 20, maxC = 0;
    for (final id in seats) {
      final c = byId[id]!;
      if (c.row < minR) minR = c.row;
      if (c.row > maxR) maxR = c.row;
      if (c.col < minC) minC = c.col;
      if (c.col > maxC) maxC = c.col;
    }
    final h = maxR - minR + 1;
    final w = maxC - minC + 1;
    // 면적 + 약간 퍼진 형태 페널티
    return h * w * 10 + (h + w);
  }

  static (double, double) _centroid(
    List<String> seats,
    Map<String, SeatingCell> byId,
  ) {
    var r = 0.0, c = 0.0;
    for (final id in seats) {
      final cell = byId[id]!;
      r += cell.row;
      c += cell.col;
    }
    final n = seats.length;
    return (r / n, c / n);
  }

  static double _distToSet(
    List<String> seats,
    (double, double) centroid,
    Map<String, SeatingCell> byId,
  ) {
    var best = double.infinity;
    for (final id in seats) {
      final cell = byId[id]!;
      final d = (cell.row - centroid.$1).abs() + (cell.col - centroid.$2).abs();
      if (d < best) best = d;
    }
    return best;
  }
}
