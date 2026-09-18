import 'dart:math';

import '../models/project_team_model.dart';

/// 학생을 4~5명 팀으로 랜덤 분할
abstract final class ProjectTeamRandomizer {
  /// 반환: 팀별 memberId 목록
  static List<List<String>> partitionMembers(
    List<String> userIds, {
    Random? random,
  }) {
    if (userIds.isEmpty) return const [];
    final ids = [...userIds]..shuffle(random ?? Random());
    final sizes = teamSizes(ids.length);
    final result = <List<String>>[];
    var offset = 0;
    for (final size in sizes) {
      result.add(ids.sublist(offset, offset + size));
      offset += size;
    }
    return result;
  }

  /// 가능한 한 팀당 [minMembers]~[maxMembers]가 되도록 인원 분배.
  /// 완전 분할이 불가능하면(예: 6명) 5+1처럼 나머지를 마지막 팀에 둡니다.
  static List<int> teamSizes(int n) {
    if (n <= 0) return const [];
    if (n <= ProjectTeamModel.maxMembers) return [n];

    final minTeams = (n + ProjectTeamModel.maxMembers - 1) ~/
        ProjectTeamModel.maxMembers;
    final maxTeams = n ~/ ProjectTeamModel.minMembers;

    if (minTeams <= maxTeams) {
      final teamCount = minTeams;
      final sizes = List<int>.filled(teamCount, ProjectTeamModel.minMembers);
      var leftover = n - ProjectTeamModel.minMembers * teamCount;
      for (var i = 0; i < leftover; i++) {
        sizes[i] += 1;
      }
      return sizes;
    }

    // 4~5로만 나누기 어려운 인원(6, 7, 11 …): 5명씩 채우고 나머지
    final sizes = <int>[];
    var remaining = n;
    while (remaining > 0) {
      if (remaining <= ProjectTeamModel.maxMembers) {
        sizes.add(remaining);
        break;
      }
      final take = ProjectTeamModel.maxMembers;
      sizes.add(take);
      remaining -= take;
    }
    return sizes;
  }
}
