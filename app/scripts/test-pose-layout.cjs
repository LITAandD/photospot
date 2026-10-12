const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const mod = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync(require('node:path').resolve(__dirname, '../src/pose-layout.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, { module: mod, exports: mod.exports });
const { containedImage, poseLayout, photoPoint, localPressPoint, measuredPerson, validPersonReference } = mod.exports;
const near = (a, b) => assert.ok(Math.abs(a - b) < 1e-6, `${a} != ${b}`);
const reference = { height_ratio: 145 / 640, foot_y: 565 / 640 };

for (const frame of [{ width: 390, height: 292.5 }, { width: 780, height: 440 }, { width: 320, height: 240 }]) {
  const image = containedImage(frame, { width: 960, height: 640 });
  for (const foot of [160, 157, 159]) {
    const guide = poseLayout(image, reference, 1, 0.5, foot);
    near(guide.bodyHeight / image.height, reference.height_ratio);
    near((guide.footY - image.top) / image.height, reference.foot_y);
    assert.ok(guide.left >= image.left && guide.top >= image.top);
    assert.ok(guide.left + guide.width <= image.left + image.width);
    assert.ok(guide.top + guide.height <= image.top + image.height);
  }
}
const wide = containedImage({ width: 400, height: 300 }, { width: 1600, height: 600 });
near(wide.top, 75);
assert.equal(photoPoint(wide, 50, 10), null); // Letterbox must not change the measurement.
assert.equal(photoPoint(wide, 50, 290), null);
near(photoPoint(wide, 200, 150).y, 0.5);
const webPoint = localPressPoint({ clientX: 320, clientY: 230 }, { left: 120, top: 80 });
near(webPoint.x, 200); near(webPoint.y, 150);
near(photoPoint(wide, webPoint.x, webPoint.y).y, 0.5);
const nativePoint = localPressPoint({ locationX: 200, locationY: 150 });
near(nativePoint.x, webPoint.x); near(nativePoint.y, webPoint.y);
assert.equal(localPressPoint({}), null);
assert.equal(measuredPerson(0.8, 0.4), null);
assert.equal(measuredPerson(-0.1, 0.5), null);
assert.equal(measuredPerson(0.5, 0.501), null);
assert.equal(validPersonReference({ height_ratio: NaN, foot_y: 0.8 }), false);
const measured = measuredPerson(0.3, 0.7);
near(measured.height_ratio, 0.4);
near(poseLayout(wide, measured).footY, wide.top + wide.height * 0.7);
near(poseLayout(wide, null).bodyHeight / wide.height, 0.24); // Honest fallback, not 58%.
assert.ok(poseLayout(wide, reference, 0.8).bodyHeight < poseLayout(wide, reference, 1.2).bodyHeight);
for (const photo of [{ width: 300, height: 1500 }, { width: 1500, height: 300 }]) {
  const image = containedImage({ width: 400, height: 300 }, photo);
  for (const x of [1 / 3, 0.5, 2 / 3]) {
    const guide = poseLayout(image, { height_ratio: 0.95, foot_y: 0.99 }, 3.5, x);
    assert.ok(guide.left >= image.left && guide.top >= image.top);
    assert.ok(guide.left + guide.width <= image.left + image.width + 1e-6);
    assert.ok(guide.top + guide.height <= image.top + image.height + 1e-6);
  }
}
assert.equal(poseLayout(containedImage({ width: 0, height: 0 }, { width: 960, height: 640 }), reference).height, 0);
console.log('Pose proportions passed: person height, foot alignment, SVG margins, resize, letterboxing, calibration and bounds.');
