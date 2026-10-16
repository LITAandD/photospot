// Expo's route generator is also run in CI, where Metro has not been started yet.
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require('node:module');
const requireContext = require("expo-router/build/testing-library/require-context-ponyfill").default;
// SDK 55 moved type generation into the CLI's router-server dependency.
// Resolve from Expo/CLI, independent of npm's hoisting layout.
const expoRequire = createRequire(require.resolve('expo/package.json'));
const cliRequire = createRequire(expoRequire.resolve('@expo/cli/package.json'));
const { getTypedRoutesDeclarationFile } = cliRequire('@expo/router-server/build/typed-routes/generate');
const { EXPO_ROUTER_CTX_IGNORE } = require("expo-router/_ctx-shared");
const root = path.resolve(__dirname, "..");
const context = requireContext(path.join(root, "app"), true, EXPO_ROUTER_CTX_IGNORE);
fs.mkdirSync(path.join(root, ".expo/types"), { recursive: true });
fs.writeFileSync(path.join(root, ".expo/types/router.d.ts"), getTypedRoutesDeclarationFile(context));
