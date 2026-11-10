import React, { useState } from 'react';
import { Image, Linking, Pressable, StyleSheet, Text, View } from 'react-native';
import { colors, fonts } from '@/theme';

// Existing catalog photographs, reusable under KOGL type 1. No personal scoring is implied.
export function PhotoShowcase({ compact = false, height = 340 }: { compact?: boolean; height?: number }) {
  const [linkError, setLinkError] = useState(false);
  const open = (url: string) => { setLinkError(false); Linking.openURL(url).catch(() => setLinkError(true)); };
  return <View style={{ gap: 10 }}>
    <View style={[s.photos, { height }]}>
      <View style={s.mainPhoto}>
        <Image source={require('../../assets/photography/p-ark-interior.png')} style={s.image}
          resizeMode="cover" accessibilityLabel="피아크의 바다를 향한 창과 계단식 실내 공간"/>
        <View style={s.caption}><Text style={s.place}>공간의 선을 따라</Text><Text style={s.location}>부산 · 피아크</Text></View>
      </View>
      {!compact ? <View style={s.side}>
        <View style={s.tag}><View style={s.dot}/><Text style={s.tagText}>다음 사진의 배경</Text></View>
        <View style={s.sidePhoto}>
          <Image source={require('../../assets/photography/momos-window.png')} style={s.image}
            resizeMode="cover" accessibilityLabel="모모스 영도 카페의 창가 좌석과 항구 풍경"/>
          <View style={s.caption}><Text style={s.place}>빛이 머무는 곳</Text><Text style={s.location}>부산 · 모모스 영도</Text></View>
        </View>
      </View> : null}
    </View>
    <View style={s.credit}>
      <Text style={s.creditText}>사진: 부산관광공사 글로벌마케팅팀 · 하이픈그룹 (2024){'\n'}공공누리 제1유형 · 화면에 맞춰 크롭</Text>
      <View style={s.links}>
        <Pressable accessibilityRole="link" accessibilityLabel="피아크 사진 출처" style={s.creditLink} onPress={()=>open('https://www.visitbusan.net/archive/dataSearch/view.nm?dataSid=METADATA015272')}><Text style={s.linkText}>피아크 출처 ↗</Text></Pressable>
        {!compact ? <Pressable accessibilityRole="link" accessibilityLabel="모모스 사진 출처" style={s.creditLink} onPress={()=>open('https://www.visitbusan.net/archive/dataSearch/view.nm?dataSid=METADATA013508')}><Text style={s.linkText}>모모스 출처 ↗</Text></Pressable> : null}
        <Pressable accessibilityRole="link" style={s.creditLink} onPress={()=>open('https://www.kogl.or.kr/info/licenseType1.do')}><Text style={s.linkText}>이용 조건 ↗</Text></Pressable>
      </View>
      {linkError ? <Text accessibilityRole="alert" style={s.creditText}>출처를 열지 못했어요. 다시 시도해 주세요.</Text> : null}
    </View>
  </View>;
}

const s = StyleSheet.create({
  image: { ...StyleSheet.absoluteFillObject, width: '100%', height: '100%' },
  photos: { height: 340, flexDirection: 'row', gap: 12 },
  mainPhoto: { flex: 1.3, borderRadius: 24, overflow: 'hidden', backgroundColor: colors.accentSoft },
  side: { flex: 1, paddingTop: 14, paddingBottom: 24, gap: 18 },
  sidePhoto: { flex: 1, borderRadius: 24, overflow: 'hidden', backgroundColor: colors.accentSoft },
  caption: { position: 'absolute', left: 10, right: 10, bottom: 10, padding: 12, gap: 4, borderRadius: 14, backgroundColor: 'rgba(36,33,31,0.88)' },
  place: { fontFamily: fonts.semibold, fontSize: 13, color: '#FFFFFF' },
  location: { fontFamily: fonts.body, fontSize: 10, color: colors.bg },
  tag: { flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start', gap: 6, paddingVertical: 9, paddingHorizontal: 8, borderRadius: 20, backgroundColor: colors.secondary },
  tagText: { fontFamily: fonts.medium, fontSize: 10, color: colors.onSecondary },
  dot: { width: 5, height: 5, borderRadius: 3, backgroundColor: colors.onSecondary },
  credit: { gap: 0 },
  creditText: { fontFamily: fonts.body, fontSize: 10, color: colors.muted, lineHeight: 16 },
  links: { flexDirection: 'row', flexWrap: 'wrap', gap: 14 },
  creditLink: { minHeight: 44, justifyContent: 'center' },
  linkText: { fontFamily: fonts.body, fontSize: 10, color: colors.accentInk, textDecorationLine: 'underline' },
});
