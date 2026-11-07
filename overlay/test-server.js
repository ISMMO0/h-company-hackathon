// Fake brain: serves ws://127.0.0.1:8765/ws/overlay, moves the cursor every 2 s and sends a
// step for the panel with each move. Logs everything the overlay sends back (next/mode/mic/stop).
const { WebSocketServer } = require('ws');

const LABELS = ['Click File', 'Click Export', 'Choose PNG', 'Click Save', 'Cliquez ici'];
const STEPS = [
  { text: 'Click the File menu in the top-left corner of the window', state: 'waiting' },
  { text: 'Click Export', state: 'thinking' },
  { text: 'Choose PNG as the format, then keep the default size and quality', state: 'acting' },
  { text: 'Click Save', state: 'waiting' },
  { text: 'All done: the image is exported.', state: 'done' },
];
const WIDTH = Number(process.argv[2]) || 1440;
const HEIGHT = Number(process.argv[3]) || 900;

const wss = new WebSocketServer({ host: '127.0.0.1', port: 8765, path: '/ws/overlay' });
console.log('fake brain on ws://127.0.0.1:8765/ws/overlay');

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
  let i = 0;
  const timer = setInterval(() => {
    const cursor = {
      type: 'cursor',
      x: Math.round(Math.random() * WIDTH),
      y: Math.round(Math.random() * HEIGHT),
      label: LABELS[i % LABELS.length],
    };
    const step = { type: 'step', mode, ...STEPS[i % STEPS.length] };
    i++;
    for (const msg of [cursor, step]) {
      console.log('->', JSON.stringify(msg));
      ws.send(JSON.stringify(msg));
    }
  }, 2000);
  ws.on('close', () => clearInterval(timer));
});
