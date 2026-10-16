// Reviewed exceptions are explicit and expiring; never accept a finding by count.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const hash = value => crypto.createHash('sha256').update(value).digest('hex');
const read = file => JSON.parse(fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, ''));
const stable = value => JSON.stringify(value);
const unique = values => [...new Set(values)].sort();

function graph(lock) {
  if (lock.lockfileVersion < 2 || !lock.packages?.['']) throw new Error('Unsupported or missing npm lockfile');
  const packages = lock.packages;
  const resolve = (from, name) => {
    let dir = from;
    while (true) {
      const candidate = [dir, 'node_modules', name].filter(Boolean).join('/');
      if (packages[candidate]) return candidate;
      if (!dir) return null;
      dir = path.posix.dirname(dir);
      if (dir === '.') dir = '';
    }
  };
  const edges = [], reached = new Set(['']), pending = [''];
  while (pending.length) {
    const from = pending.shift(), pkg = packages[from];
    const meta = pkg.link ? packages[pkg.resolved] : pkg;
    if (!meta) throw new Error(`Missing linked package metadata: ${from}`);
    const kinds = ['dependencies', 'optionalDependencies', 'peerDependencies', ...(from === '' ? ['devDependencies'] : [])];
    for (const kind of kinds) {
      for (const name of Object.keys(meta[kind] || {}).sort()) {
        const to = resolve(from, name);
        if (!to) continue; // Optional/peer packages need not be installed; npm ci validates required packages.
        edges.push({ from, to, name, kind });
        if (!reached.has(to)) { reached.add(to); pending.push(to); }
      }
    }
  }
  const label = node => `${node || '(app)'}@${packages[node].version || 'link'}`;
  return { packages, edges, reached, label };
}

function dependencyEvidence(g, nodes) {
  const ancestors = new Set(nodes), pending = [...nodes];
  while (pending.length) {
    const to = pending.pop();
    for (const edge of g.edges.filter(e => e.to === to)) {
      if (!ancestors.has(edge.from)) { ancestors.add(edge.from); pending.push(edge.from); }
    }
  }
  const edges = g.edges.filter(e => ancestors.has(e.from) && ancestors.has(e.to));
  const serialized = unique(edges.map(e => stable([g.label(e.from), e.kind, e.name, g.label(e.to)])));
  // A short human-readable path accompanies the digest of ALL ancestor edges.
  const paths = [], seen = new Set(['']), queue = [{ node: '', chain: [] }];
  while (queue.length) {
    const { node, chain } = queue.shift();
    if (nodes.includes(node)) paths.push(chain.join(' > '));
    for (const e of edges.filter(e => e.from === node)) {
      if (!seen.has(e.to)) { seen.add(e.to); queue.push({ node: e.to, chain: [...chain, `${e.name}@${g.packages[e.to].version}`] }); }
    }
  }
  return { path_sha256: hash(stable(serialized)), representative_paths: paths.sort() };
}

function inventory(audit, lock) {
  if (audit.error || audit.auditReportVersion !== 2 || !audit.metadata?.vulnerabilities ||
      !audit.vulnerabilities || typeof audit.vulnerabilities !== 'object') throw new Error('Invalid/incomplete npm audit response');
  if (Object.keys(audit.vulnerabilities).length !== audit.metadata.vulnerabilities.total) throw new Error('Audit totals do not match findings');
  const g = graph(lock), entries = new Map();
  for (const [name, finding] of Object.entries(audit.vulnerabilities)) {
    if (!Array.isArray(finding.via) || !finding.via.length || !Array.isArray(finding.nodes) || !finding.nodes.length) {
      throw new Error(`Incomplete finding: ${name}`);
    }
    for (const via of finding.via) {
      if (typeof via === 'string') {
        if (!audit.vulnerabilities[via]) throw new Error(`Unresolved advisory dependency: ${via}`);
        continue;
      }
      const id = /^https:\/\/github.com\/advisories\/(GHSA-[a-z0-9-]+)$/.exec(via.url || '')?.[1];
      if (!id || via.name !== name || !['info', 'low', 'moderate', 'high', 'critical'].includes(via.severity) || !via.range) {
        throw new Error(`Unrecognized advisory: ${name}`);
      }
      const nodes = unique(finding.nodes);
      const installations = nodes.map(node => {
        if (!g.packages[node]?.version || !g.reached.has(node)) throw new Error(`Finding is absent from dependency graph: ${node}`);
        return { node, version: g.packages[node].version };
      });
      entries.set(`${name}:${id}`, { id, package: name, severity: via.severity, range: via.range, installations,
        ...dependencyEvidence(g, nodes) });
    }
  }
  if (Object.keys(audit.vulnerabilities).length && !entries.size) throw new Error('Audit has no identifiable root advisories');
  return [...entries.values()].sort((a, b) => `${a.package}:${a.id}`.localeCompare(`${b.package}:${b.id}`, 'en'));
}

function checkAudit(actual, policy, today) {
  const errors = [];
  if (policy.schema_version !== 1 || !Array.isArray(policy.exceptions)) throw new Error('Invalid security policy');
  const indexed = new Map();
  for (const entry of policy.exceptions) {
    const key = `${entry.package}:${entry.id}`;
    if (indexed.has(key)) errors.push(`Duplicate exception: ${key}`);
    indexed.set(key, entry);
  }
  for (const entry of actual) {
    const key = `${entry.package}:${entry.id}`, allowed = indexed.get(key);
    if (entry.severity === 'critical') errors.push(`Critical advisory cannot be excepted: ${key}`);
    if (!allowed) { errors.push(`Unreviewed advisory: ${key}`); continue; }
    for (const field of ['severity', 'range', 'installations', 'path_sha256']) {
      if (stable(entry[field]) !== stable(allowed[field])) errors.push(`Changed ${field}: ${key}`);
    }
    const validDate = date => /^\d{4}-\d{2}-\d{2}$/.test(date || '') &&
      !Number.isNaN(Date.parse(date)) && new Date(date).toISOString().slice(0, 10) === date;
    if (!validDate(allowed.reviewed_at) || !validDate(allowed.review_after) || allowed.reviewed_at > today ||
        allowed.review_after <= today || allowed.review_after <= allowed.reviewed_at ||
        Date.parse(allowed.review_after) - Date.parse(allowed.reviewed_at) > 45 * 86400000) errors.push(`Expired/invalid review date: ${key}`);
    if (!allowed.scope || !allowed.rationale || !allowed.mitigation || !allowed.representative_paths?.length) errors.push(`Missing review evidence: ${key}`);
    if (!policy.runtime?.[entry.package]) errors.push(`Missing runtime policy: ${key}`);
  }
  return errors; // A genuinely removed advisory needs no exception; counts never substitute for identity.
}

function sourceName(source) {
  const normalized = source.replace(/\\/g, '/');
  const at = normalized.indexOf('node_modules/');
  return at < 0 ? normalized.replace(/^(\.\.\/)+/, '').replace(/^\.\//, '') : normalized.slice(at);
}

function runtimeInventory(directory, watched) {
  const foundPlatforms = new Set(), observations = Object.fromEntries(watched.map(p => [p, { platforms: [], importers: [] }]));
  const files = [];
  function walk(dir) { for (const f of fs.readdirSync(dir, { withFileTypes: true })) {
    const file = path.join(dir, f.name);
    if (f.isDirectory()) walk(file); else if (f.name.endsWith('.map')) files.push(file);
  } }
  walk(directory);
  function inspect(map, platform) {
    if (map.sections) { for (const section of map.sections) inspect(section.map, platform); return; }
    if (!Array.isArray(map.sources) || !map.sources.length || !Array.isArray(map.sourcesContent) ||
        map.sources.length !== map.sourcesContent.length || map.sourcesContent.some(s => typeof s !== 'string')) {
      throw new Error('Source map must include original source content');
    }
    foundPlatforms.add(platform);
    for (let i = 0; i < map.sources.length; i++) {
      const name = sourceName(map.sources[i]), content = map.sourcesContent[i].replace(/\r\n/g, '\n');
      for (const pkg of watched) {
        const escaped = pkg.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        if (new RegExp(`(?:^|/)node_modules/${escaped}(?:/|$)`).test(name)) observations[pkg].platforms.push(platform);
        if (new RegExp(`['"]${escaped}(?:/[^'"]*)?['"]`).test(content)) {
          observations[pkg].importers.push(stable({ source: name, sha256: hash(content) }));
        }
      }
    }
  }
  for (const file of files) {
    const relative = path.relative(directory, file).replace(/\\/g, '/');
    const platform = /^_expo\/static\/js\/(android|ios|web)\//.exec(relative)?.[1];
    if (platform) inspect(read(file), platform);
  }
  if (['web', 'android', 'ios'].some(p => !foundPlatforms.has(p))) throw new Error('Missing web/Android/iOS source maps');
  for (const obs of Object.values(observations)) {
    obs.platforms = unique(obs.platforms); obs.importers = unique(obs.importers).map(JSON.parse);
  }
  return observations;
}

function checkRuntime(actual, expected) {
  return Object.keys(expected).flatMap(pkg => ['platforms', 'importers'].filter(k =>
    stable(actual[pkg]?.[k]) !== stable(expected[pkg][k])).map(k => `Runtime ${k} changed: ${pkg}`));
}

function main() {
  const args = process.argv.slice(2), arg = name => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : null; };
  const policy = read(path.join(root, 'security/app-audit-exceptions.json'));
  let errors;
  if (arg('--maps')) {
    const observations = runtimeInventory(path.resolve(arg('--maps')), Object.keys(policy.runtime));
    errors = checkRuntime(observations, policy.runtime);
  } else {
    const output = arg('--audit') || path.join(root, 'artifacts/security/app.json');
    if (!arg('--audit')) {
      const result = spawnSync('npm', ['audit', '--json'], { cwd: path.join(root, 'app'), encoding: 'utf8',
        shell: process.platform === 'win32', windowsHide: true, timeout: 120000 });
      fs.mkdirSync(path.dirname(output), { recursive: true });
      fs.writeFileSync(output, result.stdout || '{}');
      if (result.error || ![0, 1].includes(result.status)) throw new Error('npm audit failed; inspect artifacts/security/app.json');
    }
    const audit = read(output), actual = inventory(audit, read(path.join(root, 'app/package-lock.json')));
    const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
    errors = checkAudit(actual, policy, today);
    console.log(JSON.stringify({ counts: audit.metadata.vulnerabilities, advisories: actual.map(a => `${a.package}:${a.id}`) }));
  }
  if (errors.length) throw new Error(errors.join('\n'));
  console.log('Security review gate passed. Reviewed exceptions remain unresolved vulnerabilities.');
}
module.exports = { graph, inventory, checkAudit, runtimeInventory, checkRuntime };
if (require.main === module) { try { main(); } catch (e) { console.error(e.message); process.exitCode = 1; } }
