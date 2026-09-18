/// 관리자 LLMOps 화면용 토큰 비용 추정치.
///
/// 실제 청구 단가가 아니라 gpt-5.6-sol 공개 가격대를 반올림한 상수다.
/// 입력/출력 1M 토큰당 USD.
abstract final class AiOpsTokenCosts {
  static const inputUsdPerMillion = 1.25;
  static const outputUsdPerMillion = 10.0;

  static double estimateUsd({int tokenIn = 0, int tokenOut = 0}) {
    return (tokenIn / 1000000) * inputUsdPerMillion +
        (tokenOut / 1000000) * outputUsdPerMillion;
  }
}
