// Fake brain: serves ws://127.0.0.1:8765/ws/overlay and replays a 5-step task every 2 s:
// cursor + step + plan on each move, a chat line now and then, "Listening…" during step 2,
// then `clear` and a 6 s idle pause (the pink cursor follows the mouse). Logs everything the
// overlay sends back (hello/next/mode/mic/stop).
const { WebSocketServer } = require('ws');

const LABELS = ['Click File', 'Click Export', 'Choose PNG', 'Click Save', 'Cliquez ici'];
const STEPS = [
  { text: 'Click the File menu in the top-left corner of the window', state: 'waiting' },
  { text: 'Click Export', state: 'thinking' },
  { text: 'Choose PNG as the format, then keep the default size and quality', state: 'acting' },
  { text: 'Click Save', state: 'waiting' },
  { text: 'All done: the image is exported.', state: 'done' },
];
const CHAT = [
  { who: 'you', text: 'Export this as a PNG' },
  { who: 'shadow', text: 'Sure, I will guide you through it.' },
  { who: 'you', text: 'Actually keep the default quality' },
  { who: 'shadow', text: 'OK, keeping the defaults.' },
];
const IDLE_TICKS = 3; // 2 s each
const WIDTH = Number(process.argv[2]) || 1440;
const HEIGHT = Number(process.argv[3]) || 900;

const wss = new WebSocketServer({ host: '127.0.0.1', port: 8765, path: '/ws/overlay' });
console.log('fake brain on ws://127.0.0.1:8765/ws/overlay');

function plan(current) {
  return STEPS.map((step, i) => ({
    text: step.text,
    status: i < current ? 'done' : i === current ? 'current' : 'todo',
  }));
}

wss.on('connection', (ws) => {
  console.log('overlay connected');
  let mode = 'guide';
  ws.on('message', (data) => {
    console.log('<-', data.toString());
    const msg = JSON.parse(data.toString());
    if (msg.type === 'mode') mode = msg.mode;
    if (['next', 'mic', 'stop'].includes(msg.type)) console.log(`   panel button: ${msg.type}`);
  });
  ws.on('close', () => console.log('overlay disconnected'));

  const send = (msg) => {
    console.log('->', JSON.stringify(msg));
    ws.send(JSON.stringify(msg));
  };

  let i = 0;
  const timer = setInterval(() => {
    const tick = i++ % (STEPS.length + 1 + IDLE_TICKS);
    if (tick === STEPS.length) return send({ type: 'clear' });
    if (tick > STEPS.length) return; // idle: the pink cursor follows the mouse
    send({
      type: 'cursor',
      x: Math.round(Math.random() * WIDTH),
      y: Math.round(Math.random() * HEIGHT),
      label: LABELS[tick],
    });
    send({ type: 'step', mode, ...STEPS[tick] });
    send({ type: 'plan', steps: plan(tick) });
    if (CHAT[tick]) send({ type: 'chat', ...CHAT[tick] });
    if (tick === 1) send({ type: 'listening', on: true });
    if (tick === 2) send({ type: 'listening', on: false });
  }, 2000);
  ws.on('close', () => clearInterval(timer));
});
