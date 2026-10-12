export const POSE_GROUPS = [
  { id: 'standing', label: '서 있기' },
  { id: 'moving', label: '움직임' },
  { id: 'seated', label: '앉기' },
] as const;
export type PoseGroup = typeof POSE_GROUPS[number]['id'];
export type Pose = {
  id: string; group: PoseGroup; label: string; description: string;
  /** Head and ground in the shared 100 × 176 drawing, using the same body scale. */
  headY: number; foot: number; paths: string[];
};

const head = (x = 49, y = 12, profile = false) => profile
  ? `M${x} ${y} C${x - 14} ${y - 1} ${x - 15} ${y + 19} ${x - 2} ${y + 23} L${x + 7} ${y + 20} L${x + 7} ${y + 14} L${x + 12} ${y + 12} L${x + 7} ${y + 8} Q${x + 8} ${y} ${x} ${y} Z`
  : `M${x} ${y} C${x - 14} ${y - 1} ${x - 15} ${y + 20} ${x - 2} ${y + 23} C${x + 12} ${y + 26} ${x + 16} ${y + 3} ${x + 2} ${y} Z`;

export const POSES: Pose[] = [
  {
    id: 'relaxed', group: 'standing', label: '자연스럽게',
    description: '한쪽 팔을 허리에 대고 한쪽 다리를 살짝 굽힌 전신 포즈', headY: 12, foot: 160,
    paths: [head(), 'M49 35 Q45 54 50 72 L48 100',
      'M47 47 Q34 53 31 68 L39 83 M49 47 L65 60 L52 76',
      'M48 100 Q44 125 40 150 L32 160 M48 100 L61 128 L51 153 L59 159'],
  },
  {
    id: 'profile', group: 'standing', label: '옆모습',
    description: '몸과 얼굴을 옆으로 돌리고 두 손을 가볍게 모은 포즈', headY: 12, foot: 160,
    paths: [head(46, 12, true), 'M45 35 Q40 64 46 99',
      'M44 47 L56 72 L67 78 M43 50 L49 77 L67 78',
      'M46 99 L43 128 L43 158 L56 160 M46 99 L54 128 L59 155 L72 157'],
  },
  {
    id: 'look-back', group: 'standing', label: '뒤돌아보기',
    description: '등을 보인 채 어깨 너머로 얼굴을 돌려 바라보는 포즈', headY: 12, foot: 160,
    paths: [head(55, 12, true), 'M52 35 L45 48 Q39 72 46 100',
      'M45 48 L30 56 L27 81 L34 92 M45 48 L63 53 L68 80 L62 90',
      'M46 100 L36 130 L34 157 L25 160 M46 100 L54 128 L59 157 L69 160',
      'M34 54 Q46 64 59 54'],
  },
  {
    id: 'crossed-legs', group: 'standing', label: '다리 교차',
    description: '두 손을 뒤로 모으고 한쪽 다리를 다른 다리 앞으로 교차한 포즈', headY: 12, foot: 160,
    paths: [head(), 'M49 35 Q53 66 49 100',
      'M48 47 L30 67 L45 84 M50 47 L68 67 L53 84',
      'M49 100 L56 129 L37 158 L27 160 M49 100 L43 128 L59 158 L70 160'],
  },
  {
    id: 'step', group: 'moving', label: '한 걸음',
    description: '팔과 다리를 앞뒤로 벌려 자연스럽게 걷는 전신 포즈', headY: 12, foot: 157,
    paths: [head(), 'M49 35 Q48 65 54 99',
      'M49 47 L34 66 L22 57 M49 48 L65 62 L73 80',
      'M54 99 L34 129 L21 154 L11 157 M54 99 L66 124 L76 153 L87 157'],
  },
  {
    id: 'open', group: 'moving', label: '팔 벌리기',
    description: '두 팔을 양옆으로 펴고 두 발을 벌린 전신 포즈', headY: 12, foot: 159,
    paths: [head(), 'M49 35 Q47 64 50 99',
      'M48 47 L28 50 L9 38 M50 47 L70 43 L90 29',
      'M50 99 L39 128 L30 155 L20 159 M50 99 L61 128 L69 155 L79 159'],
  },
  {
    id: 'wave', group: 'moving', label: '손 흔들기',
    description: '한 손을 얼굴 옆으로 높이 들어 인사하고 반대 손은 허리에 둔 포즈', headY: 12, foot: 160,
    paths: [head(), 'M49 35 Q46 64 50 100',
      'M48 47 L28 54 L18 26 M18 26 L12 21 M18 26 L18 18 M18 26 L24 21',
      'M50 48 L68 65 L52 79',
      'M50 100 L40 129 L37 157 L27 160 M50 100 L60 129 L66 157 L76 160'],
  },
  {
    id: 'hair', group: 'moving', label: '머리 넘기기',
    description: '고개 옆으로 손을 올려 머리를 넘기고 한쪽 무릎을 편안하게 굽힌 포즈', headY: 12, foot: 160,
    paths: [head(), 'M49 35 Q44 65 49 100',
      'M48 47 L28 43 L37 19 M50 48 L67 66 L61 88',
      'M49 100 L40 129 L37 157 L27 160 M49 100 L63 125 L51 155 L60 160'],
  },
  {
    id: 'bench', group: 'seated', label: '걸터앉기',
    description: '벤치나 낮은 턱에 걸터앉아 손을 무릎 위에 얹은 포즈', headY: 52, foot: 160,
    paths: [head(42, 52), 'M42 75 Q37 101 43 126',
      'M41 87 L58 105 L69 127 M41 87 L30 108 L47 128',
      'M43 126 L72 128 L74 157 L86 160 M43 126 L48 135 L46 158 L35 160'],
  },
  {
    id: 'side-seat', group: 'seated', label: '옆으로 앉기',
    description: '옆을 향해 앉아 두 발을 앞으로 내밀고 풍경을 바라보는 포즈', headY: 52, foot: 160,
    paths: [head(33, 52, true), 'M32 75 Q27 104 34 127',
      'M32 87 L47 108 L64 126 M31 89 L38 114 L57 130',
      'M34 127 L66 127 L80 156 L92 158 M34 127 L58 135 L65 158 L77 160'],
  },
  {
    id: 'floor', group: 'seated', label: '바닥에 앉기',
    description: '바닥에 편안하게 앉아 다리를 접고 양손을 무릎에 둔 포즈', headY: 55, foot: 160,
    paths: [head(49, 55), 'M49 78 Q47 105 50 130',
      'M48 89 L32 111 L23 140 M50 89 L67 111 L77 140',
      'M50 130 Q26 122 17 142 Q21 154 65 158 L76 160',
      'M50 130 Q74 123 83 142 Q74 155 37 158 L25 160'],
  },
  {
    id: 'crouch', group: 'seated', label: '쪼그려 앉기',
    description: '무릎을 굽혀 낮게 앉고 한쪽 팔을 무릎 위에 가볍게 올린 포즈', headY: 70, foot: 160,
    paths: [head(46, 70, true), 'M44 93 Q32 108 35 131',
      'M42 101 L56 115 L74 120 M40 103 L30 127 L38 142',
      'M35 131 L71 118 L59 156 L75 160 M35 131 L46 121 L40 157 L27 160'],
  },
];
