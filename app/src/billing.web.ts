import type { PurchasesPackage } from 'react-native-purchases';
export type StorePackage = PurchasesPackage;
export const storeAvailable = false;
export async function storePackages(): Promise<{ tips: StorePackage[]; plus: StorePackage[] }> { return { tips: [], plus: [] }; }
export async function buyPackage(_pkg: StorePackage): Promise<never> { throw new Error('후원과 구독은 설치형 Android·iOS 앱에서 이용해 주세요'); }
export async function restorePurchases(): Promise<never> { throw new Error('구매한 스토어의 앱에서 복원해 주세요'); }
