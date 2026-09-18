/// 챗봇 답을 화면에 그릴 조각으로 나눈다.
///
/// 모델은 강조에 `**별표**`를 쓰고 항목에 `- `를 붙인다. 말풍선이 글자를 그대로 그리는
/// 동안에는 그게 화면에 별표로 나왔다. "**엠클라우독은 진입조건이 더 낮고**"처럼 읽혀
/// 오히려 읽기 나빴다.
///
/// 서식을 쓰지 말라고 이를 수도 있었다. 그러면 항목이 줄글로 뭉쳐서 더 나빠진다.
/// 비교나 준비 순서처럼 **나란한 것을 나란히 보여 주는 답**이 많아 항목이 필요하다.
/// 그래서 읽어서 그린다.
///
/// 마크다운을 다 읽지는 않는다. **굵게**와 항목 줄만 본다. 표도 링크도 코드도 챗봇
/// 답에 나오지 않고, 나오더라도 글자 그대로 두는 편이 낫다.
library;

/// 한 줄 안의 글자 조각. 굵은지 아닌지만 다르다.
class ChatSpan {
  const ChatSpan(this.text, {this.bold = false});

  final String text;
  final bool bold;

  @override
  bool operator ==(Object other) =>
      other is ChatSpan && other.text == text && other.bold == bold;

  @override
  int get hashCode => Object.hash(text, bold);

  @override
  String toString() => bold ? '**$text**' : text;
}

/// 한 덩어리. 항목이면 앞에 점을 찍고 들여쓴다.
class ChatBlock {
  const ChatBlock(this.spans, {this.bullet = false});

  final List<ChatSpan> spans;
  final bool bullet;

  /// 서식을 걷어 낸 글. 가려낼 때 쓴다.
  String get plain => spans.map((s) => s.text).join();

  @override
  String toString() => '${bullet ? "• " : ""}$plain';
}

const _bullets = ['- ', '• ', '* ', '– '];

/// 답 한 편을 덩어리로 나눈다. 빈 줄은 덩어리 사이 여백이므로 버린다.
List<ChatBlock> parseChatText(String text) {
  final blocks = <ChatBlock>[];
  for (final raw in text.split('\n')) {
    var body = raw.trim();
    if (body.isEmpty) continue;
    var bullet = false;
    for (final marker in _bullets) {
      // 점 하나만 있던 줄은 다듬고 나면 기호만 남는다. 그것도 항목이되 내용이 없다.
      if (body == marker.trim()) {
        bullet = true;
        body = '';
        break;
      }
      if (body.startsWith(marker)) {
        bullet = true;
        body = body.substring(marker.length).trim();
        break;
      }
    }
    if (body.isEmpty) continue;
    blocks.add(ChatBlock(parseChatSpans(body), bullet: bullet));
  }
  return blocks;
}

/// 한 줄을 굵은 조각과 보통 조각으로 나눈다.
///
/// 짝이 안 맞는 별표는 글자로 둔다. 지우면 사용자가 쓴 별표까지 사라진다.
List<ChatSpan> parseChatSpans(String line) {
  final spans = <ChatSpan>[];
  var rest = line;
  while (true) {
    final open = rest.indexOf('**');
    if (open < 0) break;
    final close = rest.indexOf('**', open + 2);
    if (close < 0) break;
    if (open > 0) spans.add(ChatSpan(rest.substring(0, open)));
    final inner = rest.substring(open + 2, close);
    if (inner.isNotEmpty) spans.add(ChatSpan(inner, bold: true));
    rest = rest.substring(close + 2);
  }
  if (rest.isNotEmpty) spans.add(ChatSpan(rest));
  return spans;
}
