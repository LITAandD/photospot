import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Svg, { Circle, Path } from 'react-native-svg';
import { colors, fonts } from '@/theme';

export function BrandMark() {
  return <View accessible accessibilityLabel="포토스팟" style={s.row}>
    <View style={s.icon}>
      <Svg width={24} height={24} viewBox="0 0 24 24" aria-hidden>
        <Path d="M8 3H5a2 2 0 0 0-2 2v3m13-5h3a2 2 0 0 1 2 2v3M3 16v3a2 2 0 0 0 2 2h3m13-5v3a2 2 0 0 1-2 2h-3" stroke={colors.onSecondary} strokeWidth={1.8} fill="none" strokeLinecap="round"/>
        <Circle cx={12} cy={12} r={4} stroke={colors.onSecondary} strokeWidth={1.8} fill="none"/>
      </Svg>
    </View>
    <Text style={s.name}>photospot<Text style={{ color: colors.secondary }}>.</Text></Text>
  </View>;
}

const s = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  icon: { width: 36, height: 36, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.secondary },
  name: { fontFamily: fonts.semibold, fontSize: 23, letterSpacing: -1, color: colors.ink },
});
