import { useRouter } from 'expo-router';
import { Button, Muted, Screen, Title } from '@/components/ui';

export default function NotFound() {
  const router = useRouter();
  return <Screen>
    <Title>페이지를 찾을 수 없어요</Title>
    <Muted>주소가 잘못되었거나 더 이상 제공되지 않는 페이지예요.</Muted>
    <Button title="처음으로 돌아가기" onPress={() => router.replace('/')} />
  </Screen>;
}
