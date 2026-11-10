import { useRouter } from 'expo-router';
import { Button, Muted, Screen, Title } from '@/components/ui';
import { useNoIndex } from '@/hooks';

export default function NotFound() {
  const router = useRouter();
  // SPA 라우트는 서버가 200으로 답하므로 문서 안에서 noindex 를 알린다
  useNoIndex(true, '페이지를 찾을 수 없어요 · 포토스팟');
  return <Screen>
    <Title>페이지를 찾을 수 없어요</Title>
    <Muted>주소가 잘못되었거나 더 이상 제공되지 않는 페이지예요.</Muted>
    <Button title="처음으로 돌아가기" onPress={() => router.replace('/')} />
  </Screen>;
}
