import type { PlaceDetail } from "@photospot/client";
import { photoAllowsModifications } from "@photospot/client";
import React, { useEffect, useState } from "react";
import { Image, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { Button } from '@/components/ui';
import Svg, { G, Path } from "react-native-svg";
import { colors, fonts } from "@/theme";
import { containedImage, localPressPoint, measuredPerson, photoPoint, poseLayout, validPersonReference,
  MIN_POSE_SCALE, MAX_POSE_SCALE, type PersonReference } from "@/pose-layout";
import { POSES, POSE_GROUPS, type Pose } from '@/poses';

type Photo = PlaceDetail["photos"][number];
const POSITIONS = [{ x: 1 / 3, label: "왼쪽" }, { x: 0.5, label: "중앙" }, { x: 2 / 3, label: "오른쪽" }];

/** A separate vector guide: the source photo and its attribution stay intact. */
function ChalkPerson({ pose, mirrored = false }: { pose: Pose; mirrored?: boolean }) {
  return <Svg width="100%" height="100%" viewBox="0 0 100 176" aria-hidden>
    <G fill="none" strokeLinecap="round" strokeLinejoin="round" transform={mirrored ? 'translate(100 0) scale(-1 1)' : undefined}>
      {pose.paths.map((d, i) => <G key={i}>
        <Path d={d} stroke="#18201F" strokeWidth={6} opacity={0.45} />
        <Path d={d} stroke="#FFFFFF" strokeWidth={3.1} opacity={0.94} />
        <Path d={d} stroke="#FFFFFF" strokeWidth={1.2} opacity={0.65} strokeDasharray="2 3 5 2" transform="translate(0.9 -0.65)" />
      </G>)}
    </G>
  </Svg>;
}

export function PlacePoseGuide({ photo, name, onBack }: { photo?: Photo; name?: string; onBack: () => void }) {
  const [poseIndex, setPoseIndex] = useState(0);
  const [mirrored, setMirrored] = useState(false);
  const [position, setPosition] = useState(1);
  const [visible, setVisible] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const [frame, setFrame] = useState({ width: 0, height: 0 });
  const [size, setSize] = useState({ width: photo?.width ?? 0, height: photo?.height ?? 0 });
  const [multiplier, setMultiplier] = useState(1);
  const [manualReference, setManualReference] = useState<PersonReference | null>(null);
  const [measuring, setMeasuring] = useState(false);
  const [head, setHead] = useState<{ x: number; y: number } | null>(null);
  const [measurementError, setMeasurementError] = useState(false);
  const [headPercent, setHeadPercent] = useState('66');
  const [footPercent, setFootPercent] = useState('90');
  useEffect(() => {
    let active = true;
    setLoaded(false); setFailed(false);
    setSize({ width: photo?.width ?? 0, height: photo?.height ?? 0 });
    setMultiplier(1); setManualReference(null); setMeasuring(false); setHead(null);
    setMeasurementError(false);
    if (photo && !(photo.width && photo.height)) Image.getSize(photo.url,
      (width, height) => { if (active) setSize({ width, height }); }, () => {});
    return () => { active = false; };
  }, [photo?.url, photo?.width, photo?.height]);

  // Keep the sketch inside the actual image, excluding contain-mode letterboxing.
  const image = containedImage(frame, size);
  const ready = loaded && !failed && image.width > 0;
  const allowGuide = photoAllowsModifications(photo);
  const pose = POSES[poseIndex];
  const reference = manualReference ?? (validPersonReference(photo?.pose_reference) ? photo.pose_reference : null);
  const guide = poseLayout(image, reference, multiplier, POSITIONS[position].x, pose.foot, pose.headY);
  const resetSize = () => {
    setMultiplier(1); setManualReference(null); setMeasuring(false); setHead(null); setMeasurementError(false);
  };
  const measure = (x: number, y: number) => {
    const point = photoPoint(image, x, y);
    if (!point) return;
    if (!head) { setHead(point); return; }
    const measured = measuredPerson(head.y, point.y);
    if (!measured) { setMeasurementError(true); return; }
    setManualReference(measured); setMultiplier(1); setMeasuring(false); setHead(null); setMeasurementError(false);
  };

  return <View testID="place-pose-guide" style={s.root}>
    {!allowGuide ? <Pressable onPress={onBack} accessibilityRole="button" accessibilityLabel="목록으로" style={{ padding: 16 }}><Text style={s.toggleText}>‹ 목록으로</Text></Pressable> : null}
    <View testID="pose-photo-frame" style={s.photoFrame} onLayout={(e) => setFrame(e.nativeEvent.layout)}>
      {photo && !failed ? <Image testID="pose-place-photo" source={{ uri: photo.url }} accessibilityLabel={`${name ?? "장소"} 대표 사진`}
        style={StyleSheet.absoluteFill} resizeMode="contain" onLoad={() => setLoaded(true)} onError={() => setFailed(true)} />
        : <Text style={s.placeholder}>{photo ? "사진을 불러올 수 없어요" : "대표 사진 준비 중"}</Text>}
      {ready && allowGuide && visible && !measuring ? <View testID="chalk-pose" pointerEvents="none" accessible accessibilityRole="image"
        accessibilityLabel={`촬영 포즈 예시: 사진 ${POSITIONS[position].label}, ${pose.description}${mirrored ? ', 좌우 반전' : ''}`}
        style={{ position: "absolute", width: guide.width, height: guide.height, left: guide.left, top: guide.top }}>
        <ChalkPerson pose={pose} mirrored={mirrored} />
      </View> : null}
      {allowGuide ? <Pressable onPress={onBack} accessibilityRole="button" accessibilityLabel="목록으로" style={s.back}><Text style={s.backText}>‹</Text></Pressable> : null}
      {ready && allowGuide ? <View pointerEvents="none" style={s.badge}><Text style={s.badgeText}>{visible ? "촬영 팁 · 포즈 예시" : "대표 사진"}</Text></View> : null}
      {ready && allowGuide && visible && measuring ? <Pressable testID="pose-measure-surface" style={StyleSheet.absoluteFill}
        accessible={false} focusable={false}
        accessibilityLabel={head ? "같은 사람의 발끝을 눌러 주세요" : "기준으로 삼을 사람의 머리 끝을 눌러 주세요"}
        onPress={(e) => {
          const target = e.currentTarget as unknown as { getBoundingClientRect?: () => { left: number; top: number } };
          const point = localPressPoint(e.nativeEvent, target?.getBoundingClientRect?.());
          if (point) measure(point.x, point.y);
        }}>
        {head ? <View pointerEvents="none" style={[s.measurePoint, { left: image.left + image.width * head.x - 6,
          top: image.top + image.height * head.y - 6 }]} /> : null}
      </Pressable> : null}
    </View>
    {ready && !allowGuide ? <Text testID="photo-original-notice" style={s.empty}>작가의 이용 조건에 따라 자르거나 스케치를 겹치지 않은 사진입니다.</Text> : ready ? <View style={s.controls}>
      <View style={s.controlHeader}>
        <Text style={s.title}>스케치로 보는 촬영 팁</Text>
        <Pressable accessibilityRole="button" aria-expanded={visible} accessibilityState={{ expanded: visible }} onPress={() => { setVisible(!visible); setMeasuring(false); setHead(null); }} hitSlop={8} style={s.toggle}>
          <Text style={s.toggleText}>{visible ? "스케치 숨기기" : "스케치 보기"}</Text>
        </Pressable>
      </View>
      {visible ? <>
        <View style={s.poseGroups}>
          {POSE_GROUPS.map(group => <Pressable key={group.id} accessibilityRole="button" accessibilityLabel={`${group.label} 포즈 모음`}
            aria-pressed={pose.group === group.id} accessibilityState={{ selected: pose.group === group.id }}
            onPress={() => { if (pose.group !== group.id) setPoseIndex(POSES.findIndex(option => option.group === group.id)); }}
            style={[s.chip, s.groupChip, pose.group === group.id && s.selected]}>
            <Text style={[s.chipText, pose.group === group.id && s.selectedText]}>{group.label}</Text>
          </Pressable>)}
        </View>
        <View style={s.poseOptions}>
          {POSES.map((option, i) => option.group === pose.group ? <Pressable key={option.id}
            accessibilityRole="button" accessibilityLabel={`${option.label} 포즈`} accessibilityHint={option.description}
            aria-pressed={poseIndex === i} accessibilityState={{ selected: poseIndex === i }} onPress={() => setPoseIndex(i)}
            style={[s.poseCard, poseIndex === i && s.poseCardSelected]}>
            <View accessible={false} pointerEvents="none" style={s.posePreview}><ChalkPerson pose={option} mirrored={mirrored} /></View>
            <Text style={[s.poseLabel, poseIndex === i && s.poseLabelSelected]}>{option.label}</Text>
          </Pressable> : null)}
        </View>
        <View style={s.controlHeader}>
          <Text accessibilityLiveRegion="polite" style={s.scaleHint}>{pose.label} · {POSES.length}가지 포즈</Text>
          <Pressable accessibilityRole="button" accessibilityLabel="스케치 좌우 반전" aria-pressed={mirrored} accessibilityState={{ selected: mirrored }}
            onPress={() => setMirrored(value => !value)} style={s.toggle}>
            <Text style={s.toggleText}>{mirrored ? '좌우 반전 켜짐' : '좌우 반전'}</Text>
          </Pressable>
        </View>
        <View style={s.row}><Text style={s.rowLabel}>위치</Text>
          {POSITIONS.map((option, i) => <Pressable key={option.label} accessibilityRole="button" accessibilityLabel={`스케치 ${option.label} 배치`}
            aria-pressed={position === i} accessibilityState={{ selected: position === i }} onPress={() => setPosition(i)} style={[s.chip, position === i && s.selected]}>
            <Text style={[s.chipText, position === i && s.selectedText]}>{option.label}</Text>
          </Pressable>)}
        </View>
        <View style={s.row}><Text style={s.rowLabel}>크기</Text>
          <Pressable accessibilityRole="button" accessibilityLabel="포즈 스케치 작게" disabled={multiplier <= MIN_POSE_SCALE || measuring}
            onPress={() => setMultiplier(v => Math.max(MIN_POSE_SCALE, v / 1.2))} style={s.chip}><Text style={s.chipText}>− 작게</Text></Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel="포즈 스케치 크기 초기화" onPress={resetSize} style={s.chip}><Text style={s.chipText}>초기화</Text></Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel="포즈 스케치 크게" disabled={multiplier >= MAX_POSE_SCALE || measuring}
            onPress={() => setMultiplier(v => Math.min(MAX_POSE_SCALE, v * 1.2))} style={s.chip}><Text style={s.chipText}>+ 크게</Text></Pressable>
        </View>
        <View style={s.controlHeader}>
          <Text testID="pose-scale-status" accessibilityLiveRegion="polite" style={s.scaleHint}>
            {measuring ? (measurementError ? "머리·발끝은 0~100%로, 발끝이 머리보다 최소 1.5% 아래인지 확인해 주세요." : head ? "같은 사람의 발끝을 눌러 주세요." : "사진 속 머리·발끝을 누르거나 아래 수치를 입력해 주세요.")
              : `${manualReference ? "선택한 인물 기준" : reference ? "사진 속 인물 기준" : "기본 크기"} · 사진 높이의 ${Math.round(guide.bodyHeight / image.height * 100)}%`}
          </Text>
          <Pressable accessibilityRole="button" accessibilityLabel={measuring ? "인물 크기 맞추기 취소" : "사진 속 사람 크기에 맞추기"}
            onPress={() => {
              setMeasuring(!measuring); setHead(null); setMeasurementError(false);
              setHeadPercent(String(Math.round(((reference?.foot_y ?? 0.9) - (reference?.height_ratio ?? 0.24)) * 1000) / 10));
              setFootPercent(String(Math.round((reference?.foot_y ?? 0.9) * 1000) / 10));
            }} style={s.toggle}>
            <Text style={s.toggleText}>{measuring ? "맞추기 취소" : "인물에 맞추기"}</Text>
          </Pressable>
        </View>
        {measuring ? <View style={{ gap: 10 }}>
          <Text style={s.scaleHint}>사진 위쪽을 0%, 아래쪽을 100%로 보아 머리와 발끝의 높이를 입력해요. 키보드로도 맞출 수 있어요.</Text>
          <TextInput accessibilityLabel="인물 머리 위치 (%)" keyboardType="decimal-pad" value={headPercent} onChangeText={setHeadPercent} style={s.measureInput} />
          <TextInput accessibilityLabel="인물 발끝 위치 (%)" keyboardType="decimal-pad" value={footPercent} onChangeText={setFootPercent} style={s.measureInput} />
          <Button title="입력한 인물 크기 적용" onPress={() => {
            const measured = headPercent.trim() && footPercent.trim() ? measuredPerson(Number(headPercent) / 100, Number(footPercent) / 100) : null;
            if (!measured) { setMeasurementError(true); return; }
            setManualReference(measured); setMultiplier(1); setMeasuring(false); setHead(null); setMeasurementError(false);
          }} />
        </View> : null}
      </> : null}
    </View> : <Text style={s.empty}>{failed ? "사진을 불러오면 포즈 가이드를 볼 수 있어요." : photo ? "사진을 불러오는 중…" : "사진이 등록되면 스케치 촬영 팁을 볼 수 있어요."}</Text>}
  </View>;
}

const s = StyleSheet.create({
  root: { backgroundColor: colors.card },
  photoFrame: { width: "100%", aspectRatio: 4 / 3, maxHeight: 440, backgroundColor: "#DFE3E2", overflow: "hidden" },
  placeholder: { margin: "auto", color: colors.muted, fontFamily: fonts.body, fontSize: 13 },
  back: { position: "absolute", top: 12, left: 12, width: 44, height: 44, borderRadius: 22, backgroundColor: "rgba(255,255,255,0.92)", alignItems: "center", justifyContent: "center" },
  backText: { fontSize: 26, color: colors.ink },
  badge: { position: "absolute", right: 12, top: 16, borderRadius: 12, paddingVertical: 6, paddingHorizontal: 10, backgroundColor: "rgba(23,29,29,0.68)" },
  badgeText: { color: "#FFFFFF", fontFamily: fonts.body, fontSize: 11 },
  controls: { paddingHorizontal: 24, paddingVertical: 16, gap: 10, borderBottomWidth: 1, borderColor: colors.line },
  controlHeader: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 8 },
  title: { color: colors.ink, fontFamily: fonts.semibold, fontSize: 14 },
  toggle: { minHeight: 44, minWidth: 44, justifyContent: "center" },
  toggleText: { fontFamily: fonts.body, fontSize: 11, color: colors.accentInk, textDecorationLine: "underline" },
  row: { flexDirection: "row", alignItems: "center", gap: 6, flexWrap: "wrap" },
  rowLabel: { fontFamily: fonts.body, fontSize: 11, color: colors.muted, width: 28 },
  poseGroups: { flexDirection: 'row', gap: 6 },
  groupChip: { flex: 1 },
  poseOptions: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  poseCard: { flex: 1, minWidth: 64, minHeight: 108, padding: 4, gap: 4, borderRadius: 12,
    borderWidth: 2, borderColor: '#63736E', backgroundColor: '#35443F', alignItems: 'center', justifyContent: 'center' },
  poseCardSelected: { borderColor: colors.accent, backgroundColor: '#203E33' },
  posePreview: { width: 40, height: 70 },
  poseLabel: { color: '#FFFFFF', fontFamily: fonts.body, fontSize: 10, textAlign: 'center' },
  poseLabelSelected: { fontFamily: fonts.semibold, textDecorationLine: 'underline' },
  chip: { minHeight: 44, paddingHorizontal: 12, borderRadius: 20, borderWidth: 1, borderColor: colors.lineStrong, alignItems: "center", justifyContent: "center" },
  selected: { backgroundColor: colors.accentSoft, borderColor: colors.accent },
  chipText: { fontFamily: fonts.body, fontSize: 12, color: colors.muted },
  selectedText: { color: colors.accentInk, fontFamily: fonts.semibold },
  scaleHint: { color: colors.muted, fontFamily: fonts.body, fontSize: 11 },
  measurePoint: { position: "absolute", width: 12, height: 12, borderRadius: 6, borderWidth: 2, borderColor: "#FFFFFF", backgroundColor: colors.accent },
  measureInput: { minHeight: 44, padding: 10, borderWidth: 1, borderColor: colors.lineStrong, borderRadius: 8, color: colors.ink, fontFamily: fonts.body },
  empty: { padding: 20, fontFamily: fonts.body, fontSize: 12, color: colors.muted },
});
