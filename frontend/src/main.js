import { FitAddon } from '@xterm/addon-fit';
import { Terminal } from '@xterm/xterm';
import '@xterm/xterm/css/xterm.css';
import { encryptForProxy } from './crypto.js';
import { getSuggestions, parseCommand, toSyntaxOnlyTree } from './syntaxTree.js';
import './styles.css';

const elements = {
  form: document.querySelector('#connection-form'),
  syntax: document.querySelector('#syntax'),
  target: document.querySelector('#target'),
  port: document.querySelector('#port'),
  username: document.querySelector('#username'),
  password: document.querySelector('#password'),
  proxyId: document.querySelector('#proxy-id'),
  connect: document.querySelector('#connect-button'),
  disconnect: document.querySelector('#disconnect-button'),
  clear: document.querySelector('#clear-button'),
  statusDot: document.querySelector('#status-dot'),
  statusText: document.querySelector('#connection-status'),
  mode: document.querySelector('#mode-value'),
  session: document.querySelector('#session-value'),
  modal: document.querySelector('#variable-modal'),
  tokenList: document.querySelector('#token-list'),
  cancelVariable: document.querySelector('#cancel-variable-button'),
  sendVariable: document.querySelector('#send-variable-button'),
};

const fitAddon = new FitAddon();
const terminal = new Terminal({
  cursorBlink: true,
  fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", monospace',
  fontSize: 14,
  lineHeight: 1.25,
  scrollback: 3000,
  theme: {
    background: '#06090d',
    foreground: '#d6e0eb',
    cursor: '#45e6a8',
    cursorAccent: '#06090d',
    selectionBackground: '#27463c',
    black: '#11161d',
    brightBlack: '#536072',
    green: '#45e6a8',
    brightGreen: '#7af0c0',
    yellow: '#ffc857',
    red: '#ff6b7a',
    cyan: '#5ed7e8',
  },
});
terminal.loadAddon(fitAddon);
terminal.open(document.querySelector('#terminal-container'));
fitAddon.fit();

const state = {
  socket: null,
  syntaxTree: { modes: {} },
  currentLine: '',
  currentMode: 'exec',
  history: [],
  historyIndex: 0,
  sessionId: null,
  deviceOs: null,
  pendingPayload: null,
  pendingUnknownCommand: null,
  awaitingCliDecision: false,
  pendingPreviousMode: null,
};

function setStatus(text, type = 'idle') {
  elements.statusText.textContent = text;
  elements.statusDot.className = `status-dot status-${type}`;
}

function setMode(mode) {
  state.currentMode = mode || 'exec';
  elements.mode.textContent = state.currentMode;
}

function makeSessionId() {
  return crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function promptText() {
  const deviceNames = { cisco_ios: 'Cisco', fortios: 'FortiGate' };
  const name = deviceNames[state.deviceOs] || 'Device';

  if (elements.syntax.value === 'fortios') {
    if (state.currentMode === 'global_config') return `${name} (global) # `;
    if (state.currentMode === 'interface_config') return `${name} (interface) # `;
    return `${name} # `;
  }

  if (state.currentMode === 'global_config') return `${name}(config)# `;
  if (state.currentMode === 'interface_config') return `${name}(config-if)# `;
  return `${name}> `;
}

function writePrompt() {
  terminal.write(`\x1b[1;32m${promptText()}\x1b[0m`);
}

function writeSystem(message, type = 'info') {
  const color = type === 'error'
    ? '\x1b[1;31m'
    : type === 'warning'
      ? '\x1b[1;33m'
      : '\x1b[1;36m';
  terminal.write(`\r\n${color}[System]\x1b[0m ${message}\r\n`);
}

function normalizeOutput(value) {
  return String(value ?? '').replace(/\r?\n/g, '\r\n');
}

function redrawLine(nextLine) {
  while (state.currentLine.length) {
    terminal.write('\b \b');
    state.currentLine = state.currentLine.slice(0, -1);
  }
  state.currentLine = nextLine;
  terminal.write(nextLine);
}

async function loadSyntaxTree() {
  try {
    const response = await fetch(`/api/syntax-tree?syntax=${encodeURIComponent(elements.syntax.value)}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.syntaxTree = toSyntaxOnlyTree(await response.json());
  } catch (error) {
    state.syntaxTree = { modes: {} };
    writeSystem(`Arborele de sintaxă nu a putut fi încărcat: ${error.message}`, 'warning');
  }
}

function showSuggestions() {
  const { suggestions } = getSuggestions(
    state.syntaxTree,
    state.currentMode,
    state.currentLine,
  );

  terminal.write('\r\n');
  if (!suggestions.length) {
    terminal.write('\x1b[2m  Nicio sugestie disponibilă.\x1b[0m\r\n');
  } else {
    for (const suggestion of suggestions) {
      const display = suggestion === '<VAR>'
        ? '<VAR>  [introdu o valoare]'
        : suggestion;
      terminal.write(`  \x1b[36m${display}\x1b[0m\r\n`);
    }
  }

  writePrompt();
  terminal.write(state.currentLine);
}

function completeToken() {
  const { suggestions, partial } = getSuggestions(
    state.syntaxTree,
    state.currentMode,
    state.currentLine,
  );
  const literalSuggestions = suggestions.filter((item) => item !== '<VAR>');

  if (literalSuggestions.length !== 1) {
    showSuggestions();
    return;
  }

  const completion = literalSuggestions[0].slice(partial.length);
  state.currentLine += `${completion} `;
  terminal.write(`${completion} `);
}

function socketIsOpen() {
  return state.socket?.readyState === WebSocket.OPEN;
}

async function makeCommandPayload(template, variables, rawCommand = null) {
  const secret = elements.proxyId.value.trim() || state.sessionId || 'direct-connect';
  const plaintext = template === 'PASSTHROUGH' ? rawCommand : variables;

  return {
    action: 'execute_command',
    template,
    e2e_vars: await encryptForProxy(plaintext, secret),
  };
}

function openVariableModal(command) {
  state.pendingUnknownCommand = command;
  elements.tokenList.replaceChildren();

  command.trim().split(/\s+/).filter(Boolean).forEach((token, index) => {
    const label = document.createElement('label');
    label.className = 'token-chip';

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.value = String(index);

    const text = document.createElement('span');
    text.textContent = token;

    label.append(checkbox, text);
    elements.tokenList.append(label);
  });

  elements.modal.classList.remove('hidden');
}

function closeVariableModal() {
  elements.modal.classList.add('hidden');
  state.pendingUnknownCommand = null;
  terminal.focus();
}

async function sendTemplatedUnknownCommand() {
  if (!state.pendingUnknownCommand || !socketIsOpen()) return;

  const tokens = state.pendingUnknownCommand.trim().split(/\s+/).filter(Boolean);
  const selected = new Set(
    [...elements.tokenList.querySelectorAll('input:checked')]
      .map((input) => Number(input.value)),
  );
  const variables = [];
  const templateTokens = tokens.map((token, index) => {
    if (!selected.has(index)) return token;
    variables.push(token);
    return '<VAR>';
  });

  const payload = await makeCommandPayload(templateTokens.join(' '), variables);
  state.pendingPayload = payload;
  state.socket.send(JSON.stringify(payload));
  elements.modal.classList.add('hidden');
  state.pendingUnknownCommand = null;
  terminal.focus();
}

async function submitCommand(command) {
  const trimmed = command.trim();
  if (!trimmed) {
    writePrompt();
    return;
  }

  if (!socketIsOpen()) {
    writeSystem('Conectează mai întâi frontend-ul la backend.', 'error');
    writePrompt();
    return;
  }

  state.history.push(command);
  state.historyIndex = state.history.length;

  if (trimmed === 'clear') {
    terminal.clear();
    writePrompt();
    return;
  }

  if (state.deviceOs && state.deviceOs === elements.syntax.value) {
    const payload = await makeCommandPayload('PASSTHROUGH', [], command);
    state.pendingPayload = payload;
    state.socket.send(JSON.stringify(payload));
    return;
  }

  const parsed = parseCommand(state.syntaxTree, state.currentMode, command);
  if (!parsed.matched) {
    openVariableModal(command);
    return;
  }

  const payload = await makeCommandPayload(parsed.template, parsed.variables);
  state.pendingPayload = payload;
  state.pendingPreviousMode = state.currentMode;
  state.socket.send(JSON.stringify(payload));
  setMode(parsed.nextMode);
}

function handleCliDecision(line) {
  if (line.trim() === '1' && state.pendingPayload) {
    state.socket.send(JSON.stringify({
      action: 'prompt_llm',
      template: state.pendingPayload.template,
      e2e_vars: state.pendingPayload.e2e_vars,
    }));
    writeSystem('Cererea a fost trimisă motorului AI.');
  } else {
    writeSystem('Comanda a fost anulată.', 'warning');
  }

  state.pendingPayload = null;
  state.awaitingCliDecision = false;
}

function detectDeviceOsFromLegacyMessage(message) {
  const match = String(message).match(/Detected OS:\s*(cisco_ios|fortios)/i);
  if (!match) return;
  state.deviceOs = match[1].toLowerCase();
  setStatus(`Echipament ${state.deviceOs}`, 'connected');
}

function handleBackendMessage(event) {
  let message;
  try {
    message = JSON.parse(event.data);
  } catch {
    terminal.write(normalizeOutput(event.data));
    return;
  }

  if (message.action === 'stream_output') {
    const output = String(message.data ?? '');
    detectDeviceOsFromLegacyMessage(output);
    terminal.write(normalizeOutput(output));
    if (!/\r?\n$/.test(output)) terminal.write('\r\n');
    state.pendingPayload = null;
    state.pendingPreviousMode = null;
    writePrompt();
    return;
  }

  if (message.action === 'cli_prompt') {
    if (state.pendingPreviousMode) setMode(state.pendingPreviousMode);
    state.pendingPreviousMode = null;
    state.awaitingCliDecision = true;
    state.currentLine = '';
    terminal.write(`\r\n\x1b[1;33m${normalizeOutput(message.data || message.message)}\x1b[0m\r\nSelect: `);
    return;
  }

  // Optional structured event for when the backend later exposes connection state.
  if (message.action === 'connection_state') {
    if (message.device_os) state.deviceOs = message.device_os;
    if (message.current_mode) setMode(message.current_mode);

    if (message.status === 'connected') setStatus(message.message || 'Conectat', 'connected');
    else if (message.status === 'waiting') setStatus(message.message || 'Așteaptă proxy', 'connecting');
    else if (message.status === 'error') {
      setStatus('Eroare conexiune', 'error');
      writeSystem(message.message || 'Conexiunea a eșuat.', 'error');
    }
  }
}

function disconnect({ announce = true } = {}) {
  if (state.socket) {
    state.socket.onclose = null;
    state.socket.close();
  }

  state.socket = null;
  state.deviceOs = null;
  state.pendingPayload = null;
  state.pendingPreviousMode = null;
  state.awaitingCliDecision = false;
  elements.connect.disabled = false;
  elements.disconnect.disabled = true;
  setStatus('Deconectat', 'idle');

  if (announce) {
    writeSystem('Sesiunea WebSocket a fost închisă.', 'warning');
    writePrompt();
  }
}

terminal.onData(async (data) => {
  if (!elements.modal.classList.contains('hidden')) return;

  if (data === '\r') {
    terminal.write('\r\n');
    const line = state.currentLine;
    state.currentLine = '';

    if (state.awaitingCliDecision && /^[12]$/.test(line.trim())) {
      handleCliDecision(line);
      writePrompt();
    } else {
      await submitCommand(line);
    }
    return;
  }

  if (data === '\u007f') {
    if (state.currentLine.length) {
      state.currentLine = state.currentLine.slice(0, -1);
      terminal.write('\b \b');
    }
    return;
  }

  if (data === '\t') {
    completeToken();
    return;
  }

  if (data === '?') {
    showSuggestions();
    return;
  }

  if (data === '\u0003') {
    terminal.write('^C\r\n');
    state.currentLine = '';
    state.pendingPayload = null;
    state.pendingPreviousMode = null;
    writePrompt();
    return;
  }

  if (data === '\x1b[A') {
    if (state.historyIndex > 0) state.historyIndex -= 1;
    redrawLine(state.history[state.historyIndex] || '');
    return;
  }

  if (data === '\x1b[B') {
    if (state.historyIndex < state.history.length) state.historyIndex += 1;
    redrawLine(state.history[state.historyIndex] || '');
    return;
  }

  if (/^[\x20-\x7E]+$/.test(data)) {
    state.currentLine += data;
    terminal.write(data);
  }
});

elements.form.addEventListener('submit', async (event) => {
  event.preventDefault();

  if (state.socket && state.socket.readyState !== WebSocket.CLOSED) {
    disconnect({ announce: false });
  }

  await loadSyntaxTree();
  setMode('exec');
  state.sessionId = makeSessionId();
  elements.session.textContent = state.sessionId;
  elements.connect.disabled = true;
  setStatus('Se conectează la backend…', 'connecting');

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const query = new URLSearchParams({
    syntax: elements.syntax.value,
    role: 'auto',
  });

  state.socket = new WebSocket(
    `${protocol}//${window.location.host}/ws/frontend/${state.sessionId}?${query}`,
  );

  state.socket.addEventListener('open', () => {
    elements.disconnect.disabled = false;
    setStatus('Backend conectat', 'connected');

    // This is the initial connection schema defined by the integration guide.
    // The original backend currently receives but does not process this action.
    state.socket.send(JSON.stringify({
      action: 'connect',
      proxy_id: elements.proxyId.value.trim(),
      target: elements.target.value.trim(),
      port: Number(elements.port.value),
      user: elements.username.value,
      password: elements.password.value,
    }));

    terminal.clear();
    terminal.writeln('\x1b[1;32mCiscoGate Unified Network Console\x1b[0m');
    terminal.writeln('\x1b[2mWebSocket deschis. Datele de conectare au fost trimise către backend.\x1b[0m');
    terminal.writeln('\x1b[2mTastează ? pentru sugestii sau Tab pentru completare.\x1b[0m\r\n');
    writePrompt();
    terminal.focus();
  });

  state.socket.addEventListener('message', handleBackendMessage);

  state.socket.addEventListener('error', () => {
    setStatus('Eroare WebSocket', 'error');
    elements.connect.disabled = false;
    writeSystem('Nu s-a putut deschide WebSocket-ul către backend.', 'error');
  });

  state.socket.addEventListener('close', () => {
    state.socket = null;
    setStatus('Deconectat', 'idle');
    elements.connect.disabled = false;
    elements.disconnect.disabled = true;
  });
});

elements.syntax.addEventListener('change', async () => {
  await loadSyntaxTree();
  setMode('exec');
});

elements.clear.addEventListener('click', () => {
  terminal.clear();
  writePrompt();
  terminal.focus();
});

elements.disconnect.addEventListener('click', () => disconnect());
elements.cancelVariable.addEventListener('click', () => {
  closeVariableModal();
  writeSystem('Comanda a fost anulată.', 'warning');
  writePrompt();
});
elements.sendVariable.addEventListener('click', sendTemplatedUnknownCommand);
window.addEventListener('resize', () => fitAddon.fit());

await loadSyntaxTree();
terminal.writeln('\x1b[1;32mCiscoGate Unified Network Console\x1b[0m');
terminal.writeln('\x1b[2mCompletează formularul din stânga pentru a începe.\x1b[0m\r\n');
writePrompt();
terminal.focus();
