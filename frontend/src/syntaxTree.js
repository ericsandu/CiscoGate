const META_PREFIX = '_';

function hasOwn(object, key) {
  return Object.prototype.hasOwnProperty.call(object, key);
}

/**
 * The current backend returns its complete trie. The frontend only needs command
 * structure, so translation strings and role metadata are dropped immediately.
 */
export function toSyntaxOnlyTree(rawTree) {
  function visit(node) {
    if (!node || typeof node !== 'object' || Array.isArray(node)) return node;

    const clean = {};
    const isLeaf = hasOwn(node, '_translate') || hasOwn(node, '_enters_mode') || hasOwn(node, '_exits_mode');

    for (const [key, value] of Object.entries(node)) {
      if (key === '_translate' || key === '_allowed_roles') continue;
      if (key.startsWith(META_PREFIX)) {
        if (key === '_enters_mode' || key === '_exits_mode') clean[key] = value;
        continue;
      }
      clean[key] = visit(value);
    }

    if (isLeaf) clean._leaf = true;
    return clean;
  }

  return visit(rawTree || { modes: {} });
}

function literalKey(node, token) {
  if (!node) return null;
  if (hasOwn(node, token)) return token;

  const normalized = token.toLowerCase();
  return Object.keys(node).find(
    (key) => !key.startsWith(META_PREFIX) && key.toLowerCase() === normalized,
  ) || null;
}

export function parseCommand(tree, mode, command) {
  const tokens = command.trim().split(/\s+/).filter(Boolean);
  if (!tokens.length) return { matched: false, tokens: [] };

  let node = tree?.modes?.[mode] || {};
  const templateTokens = [];
  const variables = [];

  for (const token of tokens) {
    const key = literalKey(node, token);
    if (key) {
      templateTokens.push(key);
      node = node[key];
      continue;
    }

    if (node && hasOwn(node, '<VAR>')) {
      templateTokens.push('<VAR>');
      variables.push(token);
      node = node['<VAR>'];
      continue;
    }

    return { matched: false, tokens };
  }

  if (!node?._leaf) return { matched: false, tokens };

  let nextMode = mode;
  if (node._enters_mode) nextMode = node._enters_mode;
  if (node._exits_mode) nextMode = 'exec';

  return {
    matched: true,
    template: templateTokens.join(' '),
    variables,
    nextMode,
  };
}

export function getSuggestions(tree, mode, line) {
  const endsWithSpace = /\s$/.test(line);
  const tokens = line.trim().split(/\s+/).filter(Boolean);
  const partial = endsWithSpace ? '' : (tokens.pop() || '');
  let node = tree?.modes?.[mode] || {};

  for (const token of tokens) {
    const key = literalKey(node, token);
    if (key) node = node[key];
    else if (node && hasOwn(node, '<VAR>')) node = node['<VAR>'];
    else return { suggestions: [], partial };
  }

  const normalizedPartial = partial.toLowerCase();
  const suggestions = Object.keys(node || {})
    .filter((key) => !key.startsWith(META_PREFIX))
    .filter((key) => key === '<VAR>' || key.toLowerCase().startsWith(normalizedPartial));

  return { suggestions, partial };
}
