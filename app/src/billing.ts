import Constants, { ExecutionEnvironment } from 'expo-constants';
import { Platform } from 'react-native';
import type { PurchasesPackage } from 'react-native-purchases';
import { api } from '@/api';

export type StorePackage = PurchasesPackage;
const key = Platform.OS === 'ios' ? process.env.EXPO_PUBLIC_REVENUECAT_IOS_KEY : process.env.EXPO_PUBLIC_REVENUECAT_ANDROID_KEY;
export const storeAvailable = !!key && Constants.executionEnvironment !== ExecutionEnvironment.StoreClient;
let configured = false;
let configuredUser: string | null = null;
async function sdk() {
  if (!storeAvailable) throw new Error('스토어 결제는 설정이 완료된 설치형 앱에서 이용할 수 있어요');
  const session = await api.session();
  if (!session.billing_configured) throw new Error('스토어 결제를 준비 중이에요');
  const Purchases = (require('react-native-purchases') as typeof import('react-native-purchases')).default;
  if (!configured) { Purchases.configure({ apiKey: key!, appUserID: session.user_id }); configured = true; configuredUser = session.user_id; }
  else if (configuredUser !== session.user_id) { await Purchases.logIn(session.user_id); configuredUser = session.user_id; }
  return Purchases;
}
export async function storePackages() {
  const offerings = await (await sdk()).getOfferings();
  return {
    tips: (offerings.all['tips']?.availablePackages ?? []).filter(p => !p.product.subscriptionPeriod),
    plus: (offerings.all['plus']?.availablePackages ?? []).filter(p => !!p.product.subscriptionPeriod),
  };
}
export async function buyPackage(pkg: StorePackage) {
  const Purchases = await sdk();
  await Purchases.purchasePackage(pkg);
  // Never grant privileges from client purchase results or a client-supplied user id.
  try { return await api.syncBilling(); }
  catch { throw new Error('스토어 구매는 완료됐지만 서버 확인이 지연되고 있어요. 다시 결제하지 말고 구매 상태 다시 확인을 눌러 주세요'); }
}
export async function restorePurchases() {
  await (await sdk()).restorePurchases();
  return api.syncBilling();
}
