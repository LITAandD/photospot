const { expo } = require("./app.json");
const { releaseIssues } = require('./scripts/release-config.cjs');

module.exports = () => {
  const production = process.env.APP_VARIANT === "production" || process.env.EAS_BUILD_PROFILE === "production";
  if (production) {
    const issues = releaseIssues(process.env, expo);
    if (issues.length) throw new Error('Release configuration blocked:\n- ' + issues.join('\n- '));
  }
  const plugins = expo.plugins.filter((p) => !String(Array.isArray(p) ? p[0] : p).startsWith("@react-native"));
  plugins.push('./plugins/with-billing-launch-mode');
  if (process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID) {
    const iosId = process.env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID;
    if (production && !iosId) throw new Error("Google login on iOS requires EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID");
    plugins.push(["@react-native-google-signin/google-signin", iosId ? { iosUrlScheme: iosId.split(".").reverse().join(".") } : {}]);
  }
  if (process.env.EXPO_PUBLIC_KAKAO_NATIVE_APP_KEY) plugins.push(["@react-native-seoul/kakao-login", { kakaoAppKey: process.env.EXPO_PUBLIC_KAKAO_NATIVE_APP_KEY }]);
  if (process.env.EXPO_PUBLIC_NAVER_CLIENT_ID) {
    if (production && !process.env.EXPO_PUBLIC_NAVER_CLIENT_SECRET) throw new Error("Naver SDK requires its client secret");
    plugins.push(["@react-native-seoul/naver-login", { urlScheme: "photospot" }]);
  }
  return { ...expo, plugins, extra: { ...expo.extra, apiBaseUrl: process.env.EXPO_PUBLIC_API_BASE_URL,
    ...(process.env.EAS_PROJECT_ID ? { eas: { projectId: process.env.EAS_PROJECT_ID } } : {}) } };
};
