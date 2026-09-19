// Charge « utilisateurs réels » : chaque VU est un utilisateur connecté qui enchaîne des écrans
// avec un temps de réflexion de 0,5 à 1,5 s. Jetons pré-émis (/data/tokens.json) : la mesure
// porte sur l'API, pas sur le throttle de connexion (30/min/IP), testé à part.
//
//   docker run --rm --network amm-lab_lab -v $PWD/chaos:/data grafana/k6:1.3.0 run \
//     -e VUS=100 -e DURATION=60s --summary-export /data/results/k6-100.json /data/k6/users.js
//   MODE=spike : 10 VU → SPIKE VU en 5 s, maintien 60 s, retour à 10.
import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';
import { Counter, Trend } from 'k6/metrics';

const BASE = __ENV.BASE || 'http://nginx/api/v1';
const users = new SharedArray('users', () => JSON.parse(open('/data/results/tokens.json')));
const writes = new Counter('writes');
const serverErrors = new Counter('server_errors');
const byKind = {
  list: new Trend('t_list', true),
  detail: new Trend('t_detail', true),
  analytics: new Trend('t_analytics', true),
  alerts: new Trend('t_alerts', true),
  write: new Trend('t_write', true),
  unread: new Trend('t_unread', true),
};

const MODE = __ENV.MODE || 'steady';
export const options = MODE === 'spike'
  ? {
      scenarios: {
        spike: {
          executor: 'ramping-vus',
          startVUs: 10,
          stages: [
            { duration: '20s', target: 10 },
            { duration: '5s', target: Number(__ENV.SPIKE || 1000) },
            { duration: '60s', target: Number(__ENV.SPIKE || 1000) },
            { duration: '5s', target: 10 },
            { duration: '30s', target: 10 },
          ],
          gracefulRampDown: '30s',
        },
      },
      summaryTrendStats: ['avg', 'med', 'p(95)', 'p(99)', 'max'],
    }
  : {
      vus: Number(__ENV.VUS || 10),
      duration: __ENV.DURATION || '60s',
      summaryTrendStats: ['avg', 'med', 'p(95)', 'p(99)', 'max'],
    };

function pick(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

export default function () {
  const u = users[(__VU - 1) % users.length];
  const params = { headers: { Authorization: `Bearer ${u.token}`, 'Content-Type': 'application/json' }, timeout: '30s' };
  const amm = pick(u.amms);
  const r = Math.random();
  let kind;
  let res;
  if (r < 0.35) {
    kind = 'list';
    res = http.get(`${BASE}/amms?page=${1 + Math.floor(Math.random() * 5)}`, params);
  } else if (r < 0.55) {
    kind = 'detail';
    res = http.get(`${BASE}/amms/${amm}`, params);
  } else if (r < 0.70) {
    kind = 'analytics';
    res = http.get(`${BASE}/analytics/africa`, params);
  } else if (r < 0.80) {
    kind = 'alerts';
    res = http.get(`${BASE}/alerts?status=OPEN`, params);
  } else if (r < 0.90) {
    kind = 'unread';
    res = http.get(`${BASE}/notifications/unread-count`, params);
  } else {
    kind = 'write';
    writes.add(1);
    res = http.patch(`${BASE}/amms/${amm}`, JSON.stringify({ notes: `k6 ${Date.now()}` }), params);
  }
  byKind[kind].add(res.timings.duration);
  if (res.status === 0 || res.status >= 500) serverErrors.add(1, { kind, status: String(res.status) });
  check(res, { 'pas d\'erreur serveur': (x) => x.status > 0 && x.status < 500 });
  sleep(0.5 + Math.random());
}
