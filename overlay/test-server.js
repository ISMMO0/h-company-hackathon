// Fake brain: serves ws://127.0.0.1:8765/ws/overlay and moves the cursor every 2 s.
const { WebSocketServer } = require('ws');

const LABELS = ['Click File', 'Click Export', 'Choose PNG', 'Click Save', 'Cliquez ici'];
const WIDTH = Number(process.argv[2]) || 1440;
const HEIGHT = Number(process.argv[3]) || 900;

const wss = new WebSocketServer({ host: '127.0.0.1', port: 8765, path: '/ws/overlay' });
console.log('fake brain on ws://127.0.0.1:8765/ws/overlay');

wss.on('connection', (ws) => {
  console.log('overlay connected');
  ws.on('message', (data) => console.log('<-', data.toString()));
  ws.on('close', () => console.log('overlay disconnected'));
  let i = 0;
  const timer = setInterval(() => {
    const msg = {
      type: 'cursor',
      x: Math.round(Math.random() * WIDTH),
      y: Math.round(Math.random() * HEIGHT),
      label: LABELS[i++ % LABELS.length],
    };
    console.log('->', JSON.stringify(msg));
    ws.send(JSON.stringify(msg));
  }, 2000);
  ws.on('close', () => clearInterval(timer));
});
