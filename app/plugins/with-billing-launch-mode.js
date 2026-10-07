const { withAndroidManifest, AndroidConfig } = require('@expo/config-plugins');
module.exports = config => withAndroidManifest(config, result => {
  const activity = AndroidConfig.Manifest.getMainActivityOrThrow(result.modResults);
  activity.$['android:launchMode'] = 'singleTop';
  return result;
});
