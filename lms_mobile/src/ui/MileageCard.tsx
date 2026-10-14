import { MaterialIcons } from '@expo/vector-icons';
import { Pressable, Text, View } from 'react-native';
import Svg, { Circle, Defs, LinearGradient, Rect, Stop } from 'react-native-svg';

/**
 * 마일리지 카드 — 웹 `features/mileage/MileageCreditCard.tsx` 와 같은 신용카드 모양.
 * 남색 그라데이션 바탕 · 얇은 동심원 결 · PLAYDATA 워터마크 · 금색 칩. 비율은 신용카드(1.586:1).
 * 웹의 마우스 기울기 효과는 터치 화면이라 넣지 않았다.
 */
const START = '#0369a1';
const END = '#0f172a';
const LABEL = 'rgba(199, 214, 238, 0.58)';

export function MileageCard({ balance, holderName, width }: { balance: number; holderName?: string; width: number }) {
  const height = Math.round(width / 1.586);
  const holder = holderName && holderName.trim() ? holderName : 'PLAYDATA MEMBER';
  const rings = Array.from({ length: 16 }, (_, i) => (i + 1) * 26);
  return (
    <View
      style={{
        width,
        height,
        borderRadius: 16,
        overflow: 'hidden',
        shadowColor: '#0284c7',
        shadowOpacity: 0.35,
        shadowRadius: 16,
        shadowOffset: { width: 0, height: 10 },
        elevation: 8,
        backgroundColor: END,
      }}
      accessibilityRole="summary"
      accessibilityLabel={`보유 마일리지 ${balance.toLocaleString('ko-KR')} 포인트`}
    >
      <Svg width={width} height={height} style={{ position: 'absolute', top: 0, left: 0 }}>
        <Defs>
          <LinearGradient id="mileageBg" x1="0" y1="0" x2="1" y2="1">
            <Stop offset="0" stopColor={START} />
            <Stop offset="0.45" stopColor={END} />
            <Stop offset="1" stopColor={END} />
          </LinearGradient>
        </Defs>
        <Rect x={0} y={0} width={width} height={height} fill="url(#mileageBg)" />
        {rings.map((r) => (
          <Circle key={r} cx={width * 0.75} cy={height * 0.24} r={r} stroke="rgba(255,255,255,0.035)" strokeWidth={1} fill="none" />
        ))}
      </Svg>

      {/* 바탕을 가로지르는 워터마크 */}
      <Text
        style={{
          position: 'absolute',
          left: -6,
          bottom: -14,
          fontSize: Math.round(width * 0.15),
          fontWeight: '800',
          color: 'rgba(255,255,255,0.045)',
          transform: [{ rotate: '-16deg' }],
        }}
        numberOfLines={1}
      >
        PLAYDATA
      </Text>

      <View style={{ flex: 1, paddingTop: 16, paddingHorizontal: 18, paddingBottom: 14 }}>
        <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 8, marginBottom: 14 }}>
          <View style={{ flex: 1 }}>
            <Text style={{ color: '#fff', fontSize: 14, fontWeight: '800', letterSpacing: 0.2 }}>PLAYDATA</Text>
            <Text style={{ color: 'rgba(199, 214, 238, 0.72)', fontSize: 10, fontWeight: '500', letterSpacing: 3 }}>MILEAGE</Text>
          </View>
          <Chip />
          <MaterialIcons name="contactless" size={20} color="rgba(255,255,255,0.8)" style={{ marginTop: 4 }} />
        </View>

        <Text style={{ color: LABEL, fontSize: 9, fontWeight: '500', letterSpacing: 1.3 }}>TOTAL POINTS</Text>
        <Text style={{ color: '#fff', fontSize: 25, fontWeight: '700', marginTop: 2 }} numberOfLines={1} adjustsFontSizeToFit>
          {balance.toLocaleString('ko-KR')} P
        </Text>

        <View style={{ flexDirection: 'row', alignItems: 'flex-end', marginTop: 'auto', paddingTop: 14 }}>
          <View style={{ flex: 1 }}>
            <Text style={{ color: LABEL, fontSize: 9, fontWeight: '500', letterSpacing: 1.3 }}>CARD HOLDER</Text>
            <Text style={{ color: '#fff', fontSize: 12, fontWeight: '600' }} numberOfLines={1}>{holder}</Text>
          </View>
          <View style={{ alignItems: 'flex-end' }}>
            <Text style={{ color: LABEL, fontSize: 9, fontWeight: '500', letterSpacing: 1.3 }}>VALID THRU</Text>
            <Text style={{ color: '#fff', fontSize: 12, fontWeight: '600' }}>--/--</Text>
          </View>
        </View>
      </View>
    </View>
  );
}

/**
 * 폰 대시보드용 작은 마일리지 칸 — 크기 · 여백은 옆의 「오늘 출결」 칸(StatTile)과 똑같고
 * 바탕만 신용카드(남색 그라데이션 · 동심원 결 · 금색 칩)로 입힌다.
 */
export function MileageTile({ balance, onPress }: { balance: number; onPress?: () => void }) {
  const rings = Array.from({ length: 10 }, (_, i) => (i + 1) * 22);
  return (
    <View style={{ flex: 1 }}>
      <Pressable
        onPress={onPress}
        disabled={!onPress}
        accessibilityRole={onPress ? 'button' : undefined}
        accessibilityLabel={`마일리지 ${balance.toLocaleString('ko-KR')} 포인트`}
        style={({ pressed }) => ({ flex: 1, borderRadius: 14, overflow: 'hidden', backgroundColor: END, opacity: pressed ? 0.9 : 1 })}
      >
        <Svg width="100%" height="100%" style={{ position: 'absolute', top: 0, left: 0 }}>
          <Defs>
            <LinearGradient id="tileBg" x1="0" y1="0" x2="1" y2="1">
              <Stop offset="0" stopColor={START} />
              <Stop offset="0.6" stopColor={END} />
              <Stop offset="1" stopColor={END} />
            </LinearGradient>
          </Defs>
          <Rect x={0} y={0} width="100%" height="100%" fill="url(#tileBg)" />
          {rings.map((r) => (
            <Circle key={r} cx="80%" cy={8} r={r} stroke="rgba(255,255,255,0.045)" strokeWidth={1} fill="none" />
          ))}
        </Svg>
        <View style={{ padding: 16, gap: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', height: 36 }}>
            <Chip width={36} height={27} />
            <MaterialIcons name="contactless" size={20} color="rgba(255,255,255,0.8)" />
          </View>
          <View style={{ gap: 2 }}>
            <Text style={{ color: 'rgba(199, 214, 238, 0.85)', fontSize: 13 }} numberOfLines={1}>마일리지</Text>
            <Text style={{ color: '#fff', fontSize: 18, fontWeight: '700', letterSpacing: -0.2 }} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.6}>
              {balance.toLocaleString('ko-KR')} P
            </Text>
          </View>
        </View>
      </Pressable>
    </View>
  );
}

/** 금색 IC 칩 — 안쪽 가로선이 접점 */
function Chip({ width = 40, height = 30 }: { width?: number; height?: number }) {
  return (
    <Svg width={width} height={height} viewBox="0 0 40 30">
      <Defs>
        <LinearGradient id="chipGold" x1="0" y1="0" x2="1" y2="1">
          <Stop offset="0" stopColor="#e8c547" />
          <Stop offset="0.5" stopColor="#c9a227" />
          <Stop offset="1" stopColor="#f0d875" />
        </LinearGradient>
      </Defs>
      <Rect x={0.5} y={0.5} width={39} height={29} rx={6} fill="url(#chipGold)" stroke="#b8860b" strokeWidth={0.5} />
      {[6, 12, 18, 24].map((y) => (
        <Rect key={y} x={4} y={y} width={32} height={1} fill="rgba(120, 82, 10, 0.55)" />
      ))}
    </Svg>
  );
}
