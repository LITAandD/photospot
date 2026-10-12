export type PersonReference = { height_ratio: number; foot_y: number };
type Size = { width: number; height: number };
type Rect = Size & { left: number; top: number };

export const DEFAULT_PERSON: PersonReference = { height_ratio: 0.24, foot_y: 0.9 };
export const MIN_POSE_SCALE = 0.2;
export const MAX_POSE_SCALE = 3.5;
const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

export function validPersonReference(value?: PersonReference | null): value is PersonReference {
  return !!value && Number.isFinite(value.height_ratio) && Number.isFinite(value.foot_y)
    && value.height_ratio >= 0.015 && value.height_ratio <= value.foot_y && value.foot_y <= 1;
}

export function containedImage(frame: Size, photo: Size): Rect {
  if (![frame.width, frame.height, photo.width, photo.height].every(v => Number.isFinite(v) && v > 0)) {
    return { left: 0, top: 0, width: 0, height: 0 };
  }
  const scale = Math.min(frame.width / photo.width, frame.height / photo.height);
  const width = photo.width * scale, height = photo.height * scale;
  return { left: (frame.width - width) / 2, top: (frame.height - height) / 2, width, height };
}

/** Measure head to feet within the photo, never within its letterboxing. */
export function photoPoint(image: Rect, x: number, y: number): { x: number; y: number } | null {
  if (!image.width || !image.height || !Number.isFinite(x) || !Number.isFinite(y)
      || x < image.left || x > image.left + image.width || y < image.top || y > image.top + image.height) return null;
  return { x: (x - image.left) / image.width, y: (y - image.top) / image.height };
}

/** RN Web Pressable supplies a MouseEvent, while native supplies local touch coordinates. */
export function localPressPoint(event: { clientX?: number; clientY?: number; locationX?: number; locationY?: number },
  bounds?: { left: number; top: number }) {
  if (bounds && Number.isFinite(event.clientX) && Number.isFinite(event.clientY)) {
    return { x: event.clientX! - bounds.left, y: event.clientY! - bounds.top };
  }
  return Number.isFinite(event.locationX) && Number.isFinite(event.locationY)
    ? { x: event.locationX!, y: event.locationY! } : null;
}

export function measuredPerson(headY: number, footY: number): PersonReference | null {
  const reference = { height_ratio: footY - headY, foot_y: footY };
  return headY >= 0 && validPersonReference(reference) ? reference : null;
}

/** SVG whitespace is excluded: the drawn head-to-foot height matches the person. */
export function poseLayout(image: Rect, reference: PersonReference | null | undefined, multiplier = 1, x = 0.5, foot = 160) {
  const person = validPersonReference(reference) ? reference : DEFAULT_PERSON;
  const head = 12, viewHeight = 176, viewWidth = 100;
  const bodyUnits = foot - head;
  const factor = Number.isFinite(multiplier) ? clamp(multiplier, MIN_POSE_SCALE, MAX_POSE_SCALE) : 1;
  // Cap the entire SVG at the photo edges, preserving the reference's ground level
  // wherever there is enough space for the small head/foot margins.
  const height = Math.max(0, Math.min(image.height * person.height_ratio * factor * viewHeight / bodyUnits,
    image.height, image.width * viewHeight / viewWidth));
  const width = height * viewWidth / viewHeight;
  const top = clamp(image.top + image.height * person.foot_y - height * foot / viewHeight,
    image.top, image.top + image.height - height);
  const left = clamp(image.left + image.width * x - width / 2, image.left, image.left + image.width - width);
  return { left, top, width, height, bodyHeight: height * bodyUnits / viewHeight,
    footY: top + height * foot / viewHeight };
}
