import { useRouter } from "expo-router";
import React, { useEffect } from "react";
import { ActivityIndicator, View } from "react-native";

import { colors } from "@/theme";

/** 네이버 인가 후 앱으로 돌아오는 주소 (photospot://oauth/naver). 코드는 브라우저 세션이 받아 처리하므로 이 화면은 바로 닫는다 */
export default function NaverReturn() {
  const router = useRouter();
  useEffect(() => { if (router.canGoBack()) router.back(); else router.replace("/"); }, [router]);
  return <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.bg }}><ActivityIndicator color={colors.ink} /></View>;
}
