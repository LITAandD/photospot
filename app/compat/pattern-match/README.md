# Reviewed build-tool pattern matcher

This is a small adapter over `minimatch@11.0.9` (`minimatch-engine` npm alias), not a vendored or renamed picomatch implementation. Minimatch 11 uses `@isaacs/nonrecursive-glob-match` instead of converting glob input to backtracking regular expressions. It is installed through the existing `picomatch` import name only for compatibility with pinned build tools.

Reviewed callers: anymatch 3.1.3, jest-util 29.7.0, Expo CLI 55.0.37, Expo metro-config 55.0.27, and the local micromatch list-selection adapter. The consumer guard checks versions, source hashes and the complete lockfile list of picomatch dependents. Unknown options throw; `parse`, `makeRe`, regex/capture APIs are deliberately absent. New callers or options require review.

Supported behavior includes path predicates, array alternatives, leading negation state used by Jest, ignored paths, callbacks used by list selection, dotfiles, case sensitivity and Windows separator normalization. Small syntax translations preserve the existing frozen Micromatch fixtures, including its non-expanded numeric ranges and bare parenthesis groups. Pattern length and nesting are bounded; adversarial repeated extglobs run in a timeout-protected regression test. This is not an unrestricted implementation of the Picomatch API.

The lockfile preserves all unrelated Expo/React and reviewed-exception package versions and integrity values. Only the three registry picomatch installations are removed. The new engine's metadata and hashes come from a separate npm install of the pinned version; ordinary `npm ci` validates the resulting lock. Never use a whole-tree `npm audit fix --force` for this migration. Future dependency updates must pass the existing compatibility, advisory identity/path/expiry and three-platform runtime-source-map checks.

Original implementation: MIT. Upstream engine: [Minimatch 11.0.9](https://github.com/isaacs/minimatch/tree/v11.0.9), BlueOak-1.0.0; installed packages retain their license files. [Advisory removed](https://github.com/advisories/GHSA-fc5q-39xc-vjpf).
