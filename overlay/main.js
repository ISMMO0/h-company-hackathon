const { app, BrowserWindow, globalShortcut, Menu, Tray, screen, shell, ipcMain } = require('electron');
const path = require('path');
const WebSocket = require('ws');

const BRAIN_URL = 'ws://127.0.0.1:8765/ws/overlay';
const RECONNECT_MS = 1000;
const HOTKEY = 'Control+Alt+Space';
const STOP_HOTKEY = 'Control+Alt+X';

const FOLLOW_MS = 16; // ~60 fps
const FOLLOW_OFFSET = 16;
const GLIDE_MS = 400;

let windows = []; // one per display, same order as screen.getAllDisplays()
let lastCursor = null; // { x, y, label } in global screen points
let lastStep = null;
let hidden = false;
let socket = null;
let cursorWin = null; // the window currently drawing the pink cursor
let followTimer = null; // idle follow (see below)
let lastFollow = null;
let glideUntil = 0;

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
  win.webContents.on('did-finish-load', () => { lastFollow = null; });
  win.display = display;
  return win;
}

function rebuildWindows() {
  for (const win of windows) win.destroy();
  cursorWin = null;
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

// Idle follow: while no task runs the pink cursor sits next to the real mouse and tracks it.
function followTick() {
  if (hidden) return;
  const { x, y } = screen.getCursorScreenPoint();
  if (lastFollow && lastFollow.x === x && lastFollow.y === y) return;
  lastFollow = { x, y };
  const win = displayWindowFor(x, y);
  if (cursorWin && cursorWin !== win && !cursorWin.isDestroyed()) {
    cursorWin.webContents.send('brain', { type: 'clear' });
  }
  cursorWin = win;
  const { x: ox, y: oy } = win.display.bounds;
  win.webContents.send('brain', {
    type: 'follow',
    x: x - ox + FOLLOW_OFFSET,
    y: y - oy + FOLLOW_OFFSET,
    glide: Date.now() < glideUntil,
  });
}

let followEnabled = true; // menu bar: "Hide pink cursor when idle"
let tray = null;

function startFollow(glide) {
  if (followTimer || !followEnabled) return;
  glideUntil = glide ? Date.now() + GLIDE_MS : 0;
  lastFollow = null;
  followTimer = setInterval(followTick, FOLLOW_MS);
}

function stopFollow() {
  clearInterval(followTimer);
  followTimer = null;
}

function moveCursor({ x, y, label, tentative }) {
  stopFollow();
  lastCursor = { x, y, label, tentative };
  const win = displayWindowFor(x, y);
  cursorWin = win;
  const { x: ox, y: oy } = win.display.bounds;
  for (const other of windows) {
    if (other !== win) other.webContents.send('brain', { type: 'clear' });
  }
  win.webContents.send('brain', {
    type: 'cursor', x: x - ox, y: y - oy, label: label || '', tentative: Boolean(tentative),
  });
}

// The panel follows the pink cursor; before the first cursor it opens at the user's mouse.
function showStep(msg) {
  stopFollow();
  lastStep = msg;
  let win;
  let step = { type: 'step', text: msg.text || '', why: msg.why || '', mode: msg.mode, state: msg.state };
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

// Listening during a task happens in the panel where it is; otherwise the panel opens at the
// mouse (where the idle pink cursor sits) and the idle follow resumes when listening ends.
function setListening(on) {
  if (lastCursor || lastStep) {
    broadcast({ type: 'listening', on });
    return;
  }
  if (!on) {
    broadcast({ type: 'listening', on: false });
    startFollow(false);
    return;
  }
  stopFollow();
  const { x, y } = screen.getCursorScreenPoint();
  const win = displayWindowFor(x, y);
  const { x: ox, y: oy } = win.display.bounds;
  for (const other of windows) {
    if (other !== win) other.webContents.send('brain', { type: 'listening', on: false });
  }
  win.webContents.send('brain', {
    type: 'listening', on: true, x: x - ox + FOLLOW_OFFSET, y: y - oy + FOLLOW_OFFSET,
  });
}

// The answer card opens at the mouse when no task runs, else next to the panel where it is.
function showAnswer(msg) {
  if (lastCursor || lastStep) {
    broadcast(msg);
    return;
  }
  const { x, y } = screen.getCursorScreenPoint();
  const win = displayWindowFor(x, y);
  const { x: ox, y: oy } = win.display.bounds;
  win.webContents.send('brain', { ...msg, x: x - ox + FOLLOW_OFFSET, y: y - oy + FOLLOW_OFFSET });
}

function send(msg) {
  if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(msg));
}

let pendingHidden = 0;
ipcMain.on('hidden', () => {
  if (pendingHidden > 0 && --pendingHidden === 0) send({ type: 'hidden' });
});

const PANEL_MESSAGES = new Set(['next', 'mode', 'mic', 'stop', 'hotkey', 'followup']);
ipcMain.on('panel', (_event, msg) => {
  if (msg && PANEL_MESSAGES.has(msg.type)) send(msg);
});

// Answer card sources open in the default browser, never inside the overlay.
ipcMain.on('open', (_event, url) => {
  if (typeof url === 'string' && /^https?:\/\//.test(url)) shell.openExternal(url);
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
      hidden = true;
      pendingHidden = windows.length;
      broadcast({ type: 'hide' });
      break;
    case 'show':
      hidden = false;
      lastFollow = null;
      broadcast({ type: 'show' });
      break;
    case 'clear':
      lastCursor = null;
      lastStep = null;
      broadcast({ type: 'clear', keepCursor: true }); // it glides back to the mouse
      startFollow(true);
      break;
    case 'listening':
      setListening(Boolean(msg.on));
      break;
    case 'answer':
      showAnswer(msg);
      break;
    case 'theme': // cursor + panel accent color picked on the control page
    case 'pulse': // only the display showing the pink cursor draws anything
    case 'mic':
    case 'transcript':
    case 'plan':
    case 'chat':
      broadcast(msg);
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

// Menu bar icon: the always-available way to talk, stop, hide or quit.
function buildTray() {
  tray = new Tray(path.join(__dirname, 'tray.png'));
  tray.setToolTip('Shadow Cursor');
  const menu = Menu.buildFromTemplate([
    { label: 'Talk / Send (⌃⌥Space)', click: () => send({ type: 'hotkey' }) },
    { label: 'Stop / Cancel (⌃⌥X)', click: () => send({ type: 'stop' }) },
    { type: 'separator' },
    {
      label: 'Show pink cursor when idle', type: 'checkbox', checked: true,
      click: (item) => {
        followEnabled = item.checked;
        if (followEnabled) startFollow(false);
        else {
          stopFollow();
          if (!lastCursor && !lastStep) broadcast({ type: 'clear' });
        }
      },
    },
    { label: 'Open step log', click: () => shell.openExternal('http://127.0.0.1:8765') },
    { type: 'separator' },
    { label: 'Quit Shadow Cursor', click: () => app.quit() },
  ]);
  tray.setContextMenu(menu);
}

app.whenReady().then(() => {
  if (app.dock) app.dock.hide();
  buildTray();
  rebuildWindows();
  startFollow(false);
  screen.on('display-added', rebuildWindows);
  screen.on('display-removed', rebuildWindows);
  screen.on('display-metrics-changed', rebuildWindows);
  connect();
  if (!globalShortcut.register(HOTKEY, () => send({ type: 'hotkey' }))) {
    console.error(`could not register ${HOTKEY}`);
  }
  if (!globalShortcut.register(STOP_HOTKEY, () => send({ type: 'stop' }))) {
    console.error(`could not register ${STOP_HOTKEY}`);
  }
});

app.on('will-quit', () => globalShortcut.unregisterAll());

app.on('window-all-closed', () => {});
