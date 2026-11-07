const { app, BrowserWindow, globalShortcut, screen, ipcMain } = require('electron');
const path = require('path');
const WebSocket = require('ws');

const BRAIN_URL = 'ws://127.0.0.1:8765/ws/overlay';
const RECONNECT_MS = 1000;
const HOTKEY = 'Control+Alt+Space';

let windows = []; // one per display, same order as screen.getAllDisplays()
let lastCursor = null; // { x, y, label } in global screen points
let lastStep = null;
let socket = null;

function createWindow(display) {
  const win = new BrowserWindow({
    ...display.bounds,
    transparent: true,
    frame: false,
    hasShadow: false,
    focusable: false,
    acceptFirstMouse: true,
    skipTaskbar: true,
    roundedCorners: false,
    resizable: false,
    movable: false,
    type: 'panel',
    alwaysOnTop: true,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false,
    },
  });
  win.setAlwaysOnTop(true, 'screen-saver');
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  win.setIgnoreMouseEvents(true, { forward: true });
  win.setBounds(display.bounds);
  win.loadFile(path.join(__dirname, 'index.html'));
  win.once('ready-to-show', () => win.showInactive());
  win.display = display;
  return win;
}

function rebuildWindows() {
  for (const win of windows) win.destroy();
  windows = screen.getAllDisplays().map(createWindow);
  if (lastCursor) {
    const win = windows[0];
    win.webContents.once('did-finish-load', () => {
      moveCursor(lastCursor);
      if (lastStep) showStep(lastStep);
    });
  }
}

function displayWindowFor(x, y) {
  const target = screen.getDisplayNearestPoint({ x: Math.round(x), y: Math.round(y) });
  return windows.find((w) => w.display.id === target.id) || windows[0];
}

function broadcast(msg) {
  for (const win of windows) win.webContents.send('brain', msg);
}

function moveCursor({ x, y, label }) {
  lastCursor = { x, y, label };
  const win = displayWindowFor(x, y);
  const { x: ox, y: oy } = win.display.bounds;
  for (const other of windows) {
    if (other !== win) other.webContents.send('brain', { type: 'clear' });
  }
  win.webContents.send('brain', { type: 'cursor', x: x - ox, y: y - oy, label: label || '' });
}

// The panel follows the pink cursor; before the first cursor it opens at the user's mouse.
function showStep(msg) {
  lastStep = msg;
  let win;
  let step = { type: 'step', text: msg.text || '', mode: msg.mode, state: msg.state };
  if (lastCursor) {
    win = displayWindowFor(lastCursor.x, lastCursor.y);
  } else {
    const { x, y } = screen.getCursorScreenPoint();
    win = displayWindowFor(x, y);
    const { x: ox, y: oy } = win.display.bounds;
    step = { ...step, x: x - ox, y: y - oy };
    for (const other of windows) {
      if (other !== win) other.webContents.send('brain', { type: 'clear' });
    }
  }
  win.webContents.send('brain', step);
}

function setListening(on) {
  if (!on) {
    broadcast({ type: 'listening', on: false });
    return;
  }
  const { x, y } = screen.getCursorScreenPoint();
  const win = displayWindowFor(x, y);
  const { x: ox, y: oy } = win.display.bounds;
  for (const other of windows) {
    if (other !== win) other.webContents.send('brain', { type: 'listening', on: false });
  }
  win.webContents.send('brain', { type: 'listening', on: true, x: x - ox, y: y - oy });
}

function send(msg) {
  if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(msg));
}

let pendingHidden = 0;
ipcMain.on('hidden', () => {
  if (pendingHidden > 0 && --pendingHidden === 0) send({ type: 'hidden' });
});

const PANEL_MESSAGES = new Set(['next', 'mode', 'mic', 'stop']);
ipcMain.on('panel', (_event, msg) => {
  if (msg && PANEL_MESSAGES.has(msg.type)) send(msg);
});

// Click-through everywhere except while the pointer is over the panel.
ipcMain.on('interactive', (event, on) => {
  const win = BrowserWindow.fromWebContents(event.sender);
  if (win && !win.isDestroyed()) win.setIgnoreMouseEvents(!on, { forward: true });
});

function handleMessage(msg) {
  switch (msg.type) {
    case 'cursor':
      moveCursor(msg);
      break;
    case 'step':
      showStep(msg);
      break;
    case 'hide':
      pendingHidden = windows.length;
      broadcast({ type: 'hide' });
      break;
    case 'show':
      broadcast({ type: 'show' });
      break;
    case 'clear':
      lastCursor = null;
      lastStep = null;
      broadcast({ type: 'clear' });
      break;
    case 'listening':
      setListening(Boolean(msg.on));
      break;
    default:
      break;
  }
}

function connect() {
  socket = new WebSocket(BRAIN_URL);
  socket.on('open', () => send({ type: 'hello' }));
  socket.on('message', (data) => {
    try {
      handleMessage(JSON.parse(data.toString()));
    } catch (err) {
      console.error('bad message', err.message);
    }
  });
  socket.on('error', () => {});
  socket.on('close', () => {
    socket = null;
    setTimeout(connect, RECONNECT_MS);
  });
}

app.whenReady().then(() => {
  if (app.dock) app.dock.hide();
  rebuildWindows();
  screen.on('display-added', rebuildWindows);
  screen.on('display-removed', rebuildWindows);
  screen.on('display-metrics-changed', rebuildWindows);
  connect();
  if (!globalShortcut.register(HOTKEY, () => send({ type: 'hotkey' }))) {
    console.error(`could not register ${HOTKEY}`);
  }
});

app.on('will-quit', () => globalShortcut.unregisterAll());

app.on('window-all-closed', () => {});
