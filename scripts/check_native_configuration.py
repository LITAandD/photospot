"""Check generated native config with public CI-only provider identifiers; no sign-in/build."""
import argparse
from pathlib import Path
import plistlib
import xml.etree.ElementTree as ET


def check(root, android_only=False):
    android = '{http://schemas.android.com/apk/res/android}'
    manifest = ET.parse(root / 'android/app/src/main/AndroidManifest.xml').getroot()
    main = next(a for a in manifest.findall('./application/activity') if a.get(android + 'name') == '.MainActivity')
    assert main.get(android + 'launchMode') == 'singleTop', 'Payment return must reuse MainActivity'
    schemes = {d.get(android + 'scheme') for d in manifest.findall('.//intent-filter/data')}
    assert 'photospot' in schemes, 'Missing application deep-link scheme'
    assert 'kakao00000000000000000000000000000000' in schemes, 'Kakao callback plugin did not run'
    if android_only:
        return
    candidates = list((root / 'ios').glob('*/Info.plist'))
    assert len(candidates) == 1, 'Expected one generated iOS application'
    with candidates[0].open('rb') as source:
        info = plistlib.load(source)
    schemes = {s for item in info.get('CFBundleURLTypes', []) for s in item.get('CFBundleURLSchemes', [])}
    assert {'photospot', 'com.googleusercontent.apps.ci-ios', 'kakao00000000000000000000000000000000'} <= schemes
    assert info.get('NSLocationWhenInUseUsageDescription') and info.get('NSPhotoLibraryUsageDescription')
    entitlement_files = list(candidates[0].parent.glob('*.entitlements'))
    assert len(entitlement_files) == 1
    with entitlement_files[0].open('rb') as source:
        assert 'Default' in plistlib.load(source).get('com.apple.developer.applesignin', [])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    parser.add_argument('--android-only', action='store_true')
    args = parser.parse_args()
    check(args.project, args.android_only)
    print('Generated native callback, payment-return and permission configuration passed; not a signed/device build.')
