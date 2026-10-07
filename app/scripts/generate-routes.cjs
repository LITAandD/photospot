// Expo's route generator is also run in CI, where Metro has not been started yet.
const fs = require("node:fs");
const path = require("node:path");
const requireContext = require("expo-router/build/testing-library/require-context-ponyfill").default;
const { getTypedRoutesDeclarationFile } = require("expo-router/build/typed-routes/generate");
const { EXPO_ROUTER_CTX_IGNORE } = require("expo-router/_ctx-shared");
const root = path.resolve(__dirname, "..");
const context = requireContext(path.join(root, "app"), true, EXPO_ROUTER_CTX_IGNORE);
fs.mkdirSync(path.join(root, ".expo/types"), { recursive: true });
fs.writeFileSync(path.join(root, ".expo/types/router.d.ts"), getTypedRoutesDeclarationFile(context));
