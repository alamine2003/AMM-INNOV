// Clients WebSocket qui se comportent comme la SPA (frontend/src/realtime/useRealtime.ts) :
// reconnexion exponentielle 1 s → 30 s, SANS jitter (JITTER=1 pour la version corrigée).
// Mesure : connexions tentées/réussies, messages reçus (amplification des événements).
//
//   docker run --rm --network amm-lab_lab -v $PWD/chaos:/data grafana/k6:1.3.0 run \
//     -e CLIENTS=300 -e DURATION=120 /data/k6/websockets.js
import ws from 'k6/ws';
import { sleep } from 'k6';
import { SharedArray } from 'k6/data';
import { Counter } from 'k6/metrics';

const WS = __ENV.WS || 'ws://nginx/ws/';
const JITTER = __ENV.JITTER === '1';
const users = new SharedArray('users', () => JSON.parse(open('/data/results/tokens.json')));
const attempts = new Counter('ws_attempts');
const opened = new Counter('ws_opened');
const failed = new Counter('ws_failed');
const messages = new Counter('ws_messages');

export const options = {
  scenarios: {
    clients: {
      executor: 'per-vu-iterations',
      vus: Number(__ENV.CLIENTS || 100),
      iterations: 1,
      maxDuration: `${Number(__ENV.DURATION || 120) + 60}s`,
    },
  },
};

export default function () {
  const u = users[(__VU - 1) % users.length];
  const deadline = Date.now() + Number(__ENV.DURATION || 120) * 1000;
  let failures = 0;
  // étalement initial des connexions (ouverture d'onglets), comme en vrai
  sleep(Math.random() * 5);
  while (Date.now() < deadline) {
    attempts.add(1, { second: String(Math.floor(Date.now() / 1000)) });
    let wasOpen = false;
    const res = ws.connect(WS, { headers: { 'Sec-WebSocket-Protocol': `amm.jwt, ${u.token}` } }, (socket) => {
      socket.on('open', () => {
        wasOpen = true;
        failures = 0;
        opened.add(1);
      });
      socket.on('message', () => messages.add(1));
      socket.setTimeout(() => socket.close(), Math.max(1000, deadline - Date.now()));
    });
    if (!wasOpen || !res || res.status !== 101) failed.add(1);
    if (Date.now() >= deadline) break;
    failures += 1;
    let delay = Math.min(30000, 1000 * 2 ** (failures - 1));
    if (JITTER) delay = delay / 2 + Math.random() * (delay / 2);
    sleep(Math.min(delay, Math.max(0, deadline - Date.now())) / 1000);
  }
}
