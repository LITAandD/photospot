'use strict';
// A deliberately limited compatibility surface, NOT a renamed/vendored picomatch.
// Minimatch 11 uses nonrecursive glob matching, not generated backtracking regexes.
// Caller versions and source hashes are checked in test-compat-consumers.cjs.
const { Minimatch } = require('minimatch-engine');
const supported = new Set(['dot', 'nocase', 'windows', 'ignore', 'onResult', 'onMatch', 'onIgnore',
  'nonegate', 'noext', 'noextglob', 'nobrace', 'noglobstar', 'matchBase', 'basename', 'maxLength',
  'failglob', 'nonull', 'nullglob', 'unescape', 'returnIndex']);

function translate(pattern, options) {
  let result = '', depth = 0, inClass = false;
  for (let i = 0; i < pattern.length; i++) {
    const c = pattern[i];
    if (c === '\\') { result += c + (pattern[++i] || ''); continue; }
    if (c === '[') inClass = true;
    if (!inClass && (c === '(' || c === '{') && ++depth > 64) throw new SyntaxError('Glob nesting limit exceeded');
    if (!inClass && (c === ')' || c === '}')) depth = Math.max(0, depth - 1);
    // Picomatch's ordinary (a|b) groups are glob alternations, not literal parentheses.
    if (!inClass && c === '(' && !/[!?+*@]/.test(pattern[i - 1] || ' ')) result += '@';
    result += c;
    if (c === ']') inClass = false;
  }
  // Preserve the existing non-expanded numeric-range behavior of our micromatch adapter.
  if (!options.nobrace) result = result.replace(/(?<!\\)\{(\d+)\.\.(\d+)\}/g, '[$1-$2]');
  // A leading negative extglob may match a dotfile in picomatch; don't allow
  // unrelated hidden directories through globstars when preserving that behavior.
  if (!options.dot && !options.noext && !options.noextglob) {
    result = result.split('/').map(part => part.startsWith('!(') ? `@(${part}|.${part})` : part).join('/');
  }
  return result;
}

function patternMatch(glob, options = {}, returnState = false) {
  for (const key of Object.keys(options)) {
    if (!supported.has(key)) throw new TypeError(`Unreviewed glob option: ${key}`);
  }
  if (Array.isArray(glob)) {
    const matchers = glob.map(p => patternMatch(p, options, returnState));
    return input => matchers.some(m => m(input));
  }
  if (typeof glob !== 'string' || !glob) throw new TypeError('Expected pattern to be a non-empty string');
  if (glob.length > Math.min(options.maxLength ?? 65536, 65536)) throw new SyntaxError('Glob length limit exceeded');
  let pattern = glob, negated = false;
  if (!options.nonegate) {
    while (pattern.startsWith('!') && !pattern.startsWith('!(')) {
      negated = !negated; pattern = pattern.slice(1);
    }
  }
  const state = { negated, negatedExtglob: pattern.startsWith('!(') };
  const windows = options.windows ?? process.platform === 'win32';
  const compiled = new Minimatch(translate(pattern, options), {
    dot: !!options.dot, nocase: !!options.nocase, nonegate: true, nocomment: true,
    noext: !!(options.noext || options.noextglob), nobrace: !!options.nobrace,
    noglobstar: !!options.noglobstar, platform: 'linux', optimizationLevel: 0,
    preserveMultipleSlashes: true,
  });
  const ignored = options.ignore ? patternMatch(options.ignore, { ...options, ignore: null,
    onResult: null, onMatch: null, onIgnore: null }) : () => false;
  const matcher = (input, returnObject = false) => {
    if (typeof input !== 'string') throw new TypeError('Expected input to be a string');
    const output = windows ? input.replace(/\\/g, '/') : input;
    const subject = options.matchBase || options.basename ? output.slice(output.lastIndexOf('/') + 1) : output;
    const matched = compiled.match(subject);
    const result = { glob, state, input, output, isMatch: !!input && (negated ? !matched : matched) };
    options.onResult?.(result);
    if (result.isMatch && ignored(input)) { options.onIgnore?.(result); result.isMatch = false; }
    else if (result.isMatch) options.onMatch?.(result);
    return returnObject ? result : result.isMatch;
  };
  if (returnState) matcher.state = state;
  return matcher;
}
module.exports = patternMatch;
