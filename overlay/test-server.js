// Fake brain: serves ws://127.0.0.1:8765/ws/overlay and replays, in a loop: idle (the pink cursor
// follows the mouse), a speech-start `pulse`, a question answered with an `answer` card (sources +
// offer), a push-to-talk session with growing `transcript`, a task (cursor + step with a `why` +
// plan, a chat line now and then) with the mic open (`mic` on, a `pulse` and tentative cursor moves
// while the person talks, the `heard` line, mic off and on again), a `paused` step, the last steps,
// then `clear`. Logs everything the overlay sends back (hello/hotkey/next/mode/mic/stop/followup).
const { WebSocketServer } = require('ws');

const LABELS = ['Click File', 'Click Export', 'Choose PNG', 'Click Save', 'Cliquez ici'];
const STEPS = [
  { text: 'Click the File menu in the top-left corner of the window', state: 'waiting', why: 'Export lives in the File menu' },
  { text: 'Click Export', state: 'thinking' },
  { text: 'Choose PNG as the format, then keep the default size and quality', state: 'acting', why: 'PNG keeps the transparency' },
  { text: 'Click Save', state: 'waiting' },
  { text: 'All done: the image is exported.', state: 'done' },
];
const ANSWER = {
  type: 'answer',
  text: 'Pink Mamma is the most-cited Italian restaurant in Paris: a Big Mamma trattoria in Pigalle, '
    + 'known for its truffle pasta and the queue outside. Book ahead, or try Popolare near Réaumur.',
  sources: [
    { title: 'Le Fooding', url: 'https://lefooding.com/' },
    { title: 'Time Out Paris', url: 'https://www.timeout.com/paris' },
    { title: 'Big Mamma', url: 'https://www.bigmammagroup.com/' },
  ],
  offer: 'Want me to show it on Maps?',
};
const WIDTH = Number(process.argv[2]) || 1440;
const HEIGHT = Number(process.argv[3]) || 900;

function plan(current) {
  return {
    type: 'plan',
    steps: STEPS.map((step, i) => ({
      text: step.text,
      status: i < current ? 'done' : i === current ? 'current' : 'todo',
    })),
  };
}

// The script: [{ delay (ms), msgs }], played in order and looped.
const SCRIPT = [];
const after = (delay, ...msgs) => SCRIPT.push({ delay, msgs });
const step = (i) => after(2000, { type: 'cursor', label: LABELS[i] }, { type: 'step', ...STEPS[i] }, plan(i));
const talk = (text) => {
  after(1500, { type: 'listening', on: true });
  const words = text.split(' ');
  words.forEach((_, i) => after(400, { type: 'transcript', text: words.slice(0, i + 1).join(' ') }));
  after(1500, { type: 'listening', on: false }, { type: 'chat', who: 'you', text });
};
// Open mic mid-task: the person starts speaking (pulse), the cursor guesses the target while the
// words come in (tentative), then the sentence lands in the `heard` line.
const openMic = (text, ...guesses) => {
  after(1500, { type: 'pulse' });
  guesses.forEach((label) => after(700, { type: 'cursor', label, tentative: true }));
  after(1000, { type: 'mic', on: true, heard: text }, { type: 'chat', who: 'you', text });
};

after(3000); // idle
after(0, { type: 'pulse' }); // speech start while idle: the ring shows next to the mouse
talk('what is the best Italian restaurant in Paris');
after(1500, ANSWER);
after(8000); // the card stays until ×, 30 s, Show me / Do it, or the next step / listening
talk('show me how to export this as a PNG');
after(500, { type: 'chat', who: 'shadow', text: 'Sure, I will guide you through it.' });
step(0);
after(500, { type: 'mic', on: true });
step(1);
openMic('actually keep the default quality', 'Quality?', 'Default quality');
after(500, { type: 'chat', who: 'shadow', text: 'OK, keeping the defaults.' });
after(2000, { type: 'step', text: 'Paused, I will pick up when you are back', state: 'paused' });
step(2);
after(1000, { type: 'mic', on: false });
step(3);
after(1000, { type: 'mic', on: true });
openMic('where is the save button', 'Save?');
step(4);
after(3000, { type: 'clear' });

const wss = new WebSocketServer({ host: '127.0.0.1', port: 8765, path: '/ws/overlay' });
console.log('fake brain on ws://127.0.0.1:8765/ws/overlay');

wss.on('connection', (ws) => {
  console.log('overlay connected');
  let mode = 'guide';
  ws.on('message', (data) => {
    console.log('<-', data.toString());
    const msg = JSON.parse(data.toString());
    if (msg.type === 'mode') mode = msg.mode;
  });

  const send = (msg) => {
    if (msg.type === 'cursor') {
      msg = { ...msg, x: Math.round(Math.random() * WIDTH), y: Math.round(Math.random() * HEIGHT) };
    }
    if (msg.type === 'step') msg = { mode, ...msg };
    console.log('->', JSON.stringify(msg));
    ws.send(JSON.stringify(msg));
  };

  let i = 0;
  let timer = null;
  const play = () => {
    const { delay, msgs } = SCRIPT[i];
    timer = setTimeout(() => {
      msgs.forEach(send);
      i = (i + 1) % SCRIPT.length;
      play();
    }, delay);
  };
  play();
  ws.on('close', () => {
    clearTimeout(timer);
    console.log('overlay disconnected');
  });
});
