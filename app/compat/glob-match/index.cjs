'use strict';
// List selection semantics adapted from micromatch 4.0.8 (MIT; see LICENSE).
// Only the APIs used by our pinned Metro/Jest consumers are provided. No brace
// expansion/AST implementation is included. Picomatch handles pattern matching.
const picomatch = require('picomatch');

function match(list, patterns, options) {
  patterns = [].concat(patterns);
  list = [].concat(list);
  const omit = new Set(), keep = new Set(), items = new Set();
  let negatives = 0;
  const onResult = state => {
    items.add(state.output);
    if (options?.onResult) options.onResult(state);
  };
  for (const pattern of patterns) {
    const isMatch = picomatch(String(pattern), { ...options, onResult }, true);
    const negated = isMatch.state.negated || isMatch.state.negatedExtglob;
    if (negated) negatives++;
    for (const item of list) {
      const result = isMatch(item, true);
      if (!(negated ? !result.isMatch : result.isMatch)) continue;
      if (negated) omit.add(result.output);
      else { omit.delete(result.output); keep.add(result.output); }
    }
  }
  const result = (negatives === patterns.length ? [...items] : [...keep]).filter(item => !omit.has(item));
  if (result.length === 0) {
    if (options?.failglob) throw new Error(`No matches found for "${patterns.join(', ')}"`);
    if (options?.nonull || options?.nullglob) return options.unescape ? patterns.map(p => p.replace(/\\/g, '')) : patterns;
  }
  return result;
}
match.some = (list, patterns, options) => [].concat(patterns).some(pattern => {
  const isMatch = picomatch(String(pattern), options);
  return [].concat(list).some(item => isMatch(item));
});
match.any = match.isMatch = (input, patterns, options) => picomatch(patterns, options)(input);
match.matcher = (pattern, options) => picomatch(pattern, options);
match.match = match;
module.exports = match;
