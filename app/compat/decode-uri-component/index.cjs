// query-string 7 expects require() to return a callable function. The patched
// upstream release is ESM; Node >=22.13 and Metro can load its default export.
// Keep upstream decoding unchanged, including its bounded malformed-input path.
module.exports = require('decode-uri-component-upstream').default;
