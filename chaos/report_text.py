"""Textes de la page du rapport (le reste est calculé par build_report.py à partir des mesures)."""

HERO = """
<header class="hero">
  <p class="eyebrow">Audit de résilience · campagne de chaos engineering</p>
  <h1>Comment AMM INNOV cassait, et ce qui tient désormais</h1>
  <p class="lede">Chaque dépendance de l'application de suivi des AMM a été coupée, figée, ralentie ou
  saturée dans un laboratoire jetable, sous trafic, avec contrôle des invariants métier après chaque
  panne. Puis les mêmes tests ont été rejoués, à l'identique, sur le code corrigé.</p>
  <div class="dossier">
    <span>Date <b>18/09/2026</b></span>
    <span>Code d'origine <b>6351395</b></span>
    <span>Branche <b>Alamine/resilience-chaos-audit-d91d74</b></span>
    <span>Données <b>1 600 AMM · 15 pays · 394 scans</b></span>
    <span>Topologie <b>Railway reproduite</b></span>
  </div>
</header>
<section id="verdict" class="prose">
  <div class="section-head"><p class="eyebrow">Verdict</p><h2>Aucune donnée perdue quand une dépendance tombe franchement. Trois fragilités quand elle ralentit ou disparaît à moitié.</h2></div>
  <p>PostgreSQL tué, backend tué, stockage coupé, coupures TCP en pleine transaction : les transactions
  s'annulaient proprement et les invariants restaient intacts. En revanche :</p>
  <p><b>1. Une dépendance accessoire lente faisait tomber le cœur.</b> Redis ne sert qu'au temps réel,
  au throttle de connexion et à la file des tâches, mais chaque écriture l'attendait dans sa
  transaction : Redis figé, les écritures prenaient 25 s, gardaient leur connexion PostgreSQL, et à
  40 utilisateurs les lectures échouaient à leur tour. Redis coupé, personne ne pouvait se connecter.</p>
  <p><b>2. Le travail asynchrone se perdait en silence.</b> Worker tué : e-mails d'alerte perdus,
  analyse de dossier « en cours » à vie. API Gmail en panne plus de 7 s : alertes réglementaires
  jamais envoyées.</p>
  <p><b>3. Les écritures concurrentes et partielles n'étaient pas protégées.</b> Mises à jour perdues,
  huit versions « courantes » d'un scan, dix renouvellements pour un double envoi — et, disque plein,
  dix AMM modifiées sans trace dans l'historique d'audit.</p>
  <p>Les corrections restent simples : délais bornés, un disjoncteur pour Redis, verrous de ligne, un
  balayeur de rattrapage, résolution DNS dynamique dans nginx. Aucune brique d'infrastructure ajoutée.</p>
</section>
"""

SECTIONS = """
<section id="cascade">
  <div class="section-head"><p class="eyebrow">Cascades</p><h2>La panne ne sort plus de son couloir</h2>
  <p class="muted">Latence au 95ᵉ centile pendant la panne, avant (gris) et après (violet). Le temps réel
  part désormais après le commit, borné à 1 s, derrière un disjoncteur : sans Redis, l'application
  fonctionne, seul le rafraîchissement instantané attend le polling de 60 s.</p></div>
  <figure>{{BARS}}<figcaption>Mesures de la sonde (10 à 40 utilisateurs simulés) pendant l'injection.</figcaption></figure>
</section>

<section id="capacite">
  <div class="section-head"><p class="eyebrow">Capacité mesurée</p><h2>Premier goulot : le processus web unique</h2>
  <p class="muted">Charge k6 dans le réseau du laboratoire, 60 s par palier, utilisateurs avec 0,5 à 1,5 s de
  réflexion. PostgreSQL : ≤ 35 % de CPU avec un processus web, ≤ 49 % avec deux ; aucun N+1 sur les 12 endpoints audités.</p></div>
  <figure>{{LOAD_CHART}}
    <div class="legend"><span><i style="background:var(--before)"></i>avant</span><span><i style="background:var(--after)"></i>après, 1 processus</span><span><i style="background:var(--pass)"></i>après, 2 processus</span></div>
    <figcaption>Débit servi selon le nombre d'utilisateurs simultanés. Au-delà du plafond, rien n'échoue : tout attend.</figcaption></figure>
  {{CAPACITY_TABLE}}
</section>

<section id="incidents">
  <div class="section-head"><p class="eyebrow">Incidents critiques</p><h2>Ce qui a cédé, pourquoi, et ce qui a changé</h2></div>
  <div class="incidents">
    <div class="incident"><div class="top"><span class="code">I1 · s03c</span><h3>Redis figé faisait tomber les lectures</h3><span class="stamp FAILURE">critique</span></div>
      <p><span class="lbl">Cause</span>trois publications Redis par écriture, dans la transaction, connexion du pool tenue, 5 s de délai implicite chacune.</p>
      <p><span class="lbl">Correction</span>publication après commit, bornée à 1 s, derrière un disjoncteur (un autre protège la file des tâches) ; délais Redis à 1 s.</p></div>
    <div class="incident"><div class="top"><span class="code">I2 · s03a</span><h3>Redis coupé : connexion impossible</h3><span class="stamp FAILURE">critique</span></div>
      <p><span class="lbl">Cause</span>throttle anti force brute sur le cache Redis, sans repli.</p>
      <p><span class="lbl">Correction</span>repli en mémoire locale : la protection reste active, par processus.</p></div>
    <div class="incident"><div class="top"><span class="code">I4 · s15, s09</span><h3>Mise à jour perdue, modification sans historique</h3><span class="stamp FAILURE">critique</span></div>
      <p><span class="lbl">Cause</span><code>PATCH</code> en autocommit : UPDATE, historique et alertes dans trois transactions ; relecture sans verrou.</p>
      <p><span class="lbl">Correction</span>modification atomique, ligne AMM verrouillée avant d'être relue ; ordre de verrouillage unique AMM → renouvellement → document.</p></div>
    <div class="incident"><div class="top"><span class="code">I6 · s12b</span><h3>Worker tué : tâches perdues, dossier bloqué à vie</h3><span class="stamp FAILURE">critique</span></div>
      <p><span class="lbl">Cause</span>acquittement avant exécution ; aucune reprise de ce que la base déclare « à faire ».</p>
      <p><span class="lbl">Correction</span><code>acks_late</code>, balayeur toutes les 5 min (e-mails, analyses, aperçus), analyses orphelines libérées.</p></div>
    <div class="incident"><div class="top"><span class="code">I7 · s13</span><h3>Alertes perdues quand Gmail flanche</h3><span class="stamp FAILURE">critique</span></div>
      <p><span class="lbl">Cause</span>3 relances en 7 s puis abandon muet.</p>
      <p><span class="lbl">Correction</span>relances jusqu'à ~15 min puis rattrapage (~5 h couvertes), tentatives et dernière erreur tracées, <code>Message-ID</code> stable contre les doublons.</p></div>
    <div class="incident"><div class="top"><span class="code">I10 · s16, s11c</span><h3>nginx : API coupée sans reprise</h3><span class="stamp FAILURE">critique</span></div>
      <p><span class="lbl">Cause</span>noms résolus une fois au démarrage : Grafana absent = nginx ne démarre pas ; backend redémarré avec une nouvelle IP = nginx vise l'ancienne.</p>
      <p><span class="lbl">Correction</span><code>resolver</code> + <code>server … resolve</code> ; l'entrypoint retente la migration au lieu de boucler en redémarrages.</p></div>
    <div class="incident"><div class="top"><span class="code">I11 · s11a</span><h3>SIGTERM : backend vivant mais sourd</h3><span class="stamp FAILURE">critique</span></div>
      <p><span class="lbl">Cause</span>Daphne cessait d'écouter sans se terminer : conteneur « running », jamais redémarré.</p>
      <p><span class="lbl">Correction</span>uvicorn en un seul processus aussi, arrêt gracieux borné.</p></div>
    <div class="incident"><div class="top"><span class="code">I12 · I13</span><h3>Stockage et archives épuisaient le web</h3><span class="stamp PARTIAL">majeur</span></div>
      <p><span class="lbl">Cause</span>connexion PostgreSQL tenue pendant la lecture S3 ; ZIP et scans en mémoire (872 Mio puis mort du processus).</p>
      <p><span class="lbl">Correction</span>connexion et transaction rendues avant tout appel S3, erreurs S3 en 503, délais S3 ; archive ZIP envoyée bloc par bloc par un itérateur asynchrone (sous ASGI, Django relisait tout itérateur synchrone en mémoire) et scans lus depuis S3 sans les 10 fils de boto3 : 8 archives simultanées tiennent à 350 Mio, sans erreur pour les autres utilisateurs. Quatre essais, chacun rejoué.</p></div>
  </div>
  <p class="muted">Détail complet (reproduction, gravité, corrections minimale et architecturale, tests de non-régression) : <code>docs/audit-resilience/RAPPORT.md</code>.
  Une relecture du diff et le rejeu ont trouvé 10 défauts dans les corrections elles-mêmes (verrou tenu pendant l'upload, sonde ignorant <code>sslmode</code>, archive « en flux » que Django relisait en entier sous ASGI…), corrigés avant la mesure finale.</p>
</section>

<section id="reprise">
  <div class="section-head"><p class="eyebrow">Reprise</p><h2>Temps de reprise et perte de données par panne</h2>
  <p class="muted">MTTR mesuré en laboratoire (retour d'une réponse correcte après la fin de la panne). RPO : données confirmées à l'utilisateur puis perdues.</p></div>
  {{RECOVERY_TABLE}}
</section>

<section id="observabilite">
  <div class="section-head"><p class="eyebrow">Observabilité</p><h2>Quoi, quand, pourquoi, qui, combien de temps : lu dans les journaux</h2>
  <p class="muted">Redis coupé 30 s sous trafic, code corrigé. Chaque ligne est un extrait réel des journaux JSON du backend.</p></div>
  {{OBSERVABILITY}}
</section>

<section id="architecture">
  <div class="section-head"><p class="eyebrow">Architecture</p><h2>Même topologie, autre façon d'attendre</h2></div>
  <div class="grid2">
    <figure><figcaption><b>Avant</b></figcaption>
<pre class="mermaid">
flowchart TB
  WEB["web · 1 processus Daphne"] -- "SQL · pool 20 / 10 s" --> PG[("PostgreSQL · aucun délai")]
  WEB -- "publish ×3 DANS la transaction" --> RD[("Redis · 4 rôles")]
  WEB -- "upload dans la transaction · 60 s" --> S3[("S3")]
  WK["worker · acks précoces"] --> RD
  WK -- "3 relances en 7 s" --> GM["Gmail"]
</pre></figure>
    <figure><figcaption><b>Après</b></figcaption>
<pre class="mermaid">
flowchart TB
  WEB["web · uvicorn, arrêt gracieux"] -- "SQL · connect 5 s · statement 30 s · lock 10 s" --> PG[("PostgreSQL")]
  WEB -. "après commit · ≤ 1 s · disjoncteur" .-> RD[("Redis · délais 1 s")]
  WEB -. "connexion rendue · 3 s / 10 s" .-> S3[("S3")]
  WK["worker · acks tardifs · rattrapage /5 min"] --> RD
  WK -. "30 s → 8 min, puis rattrapage" .-> GM["Gmail"]
  GF["Grafana · v_ops_backlog"] --> PG
</pre></figure>
  </div>
</section>

<section id="changements">
  <div class="section-head"><p class="eyebrow">Changements</p><h2>Par priorité</h2></div>
  <div class="cols">
    <div class="col"><span class="stamp FAILURE">Critique</span><ul>
      <li>Temps réel après commit, borné, disjoncteur</li><li>Délais Redis, PostgreSQL, S3</li>
      <li>Connexion possible sans Redis</li><li><code>PATCH</code> atomiques et verrouillés</li>
      <li>Acks tardifs et balayeur de rattrapage</li><li>E-mails : relances longues et suivi</li>
      <li>nginx : DNS dynamique</li><li>uvicorn à la place de Daphne</li></ul></div>
    <div class="col"><span class="stamp PARTIAL">Important</span><ul>
      <li>Version courante unique ; décisions idempotentes</li><li>Uploads et téléchargements sans connexion tenue pendant S3 ; archive ZIP en flux</li>
      <li>Alerte et notification atomiques ; purge sûre</li><li>Journaux JSON + X-Request-ID, compteurs de dégradation, <code>check_integrity</code> nocturne</li>
      <li><em>À configurer</em> : alertes Grafana sur <code>v_ops_backlog</code>, sonde externe, sauvegardes managées, persistance du Redis Railway, <code>WEB_CONCURRENCY=2</code></li></ul></div>
    <div class="col"><span class="stamp SUCCESS">Amélioration</span><ul>
      <li>503 JSON avec <code>Retry-After</code></li><li>Jitter WebSocket, fin de l'amplification</li>
      <li>Jeton OAuth partagé, délai Gmail 10 s</li><li><em>Non fait</em> : alerte disque et sauvegardes hors du disque (serveur unique)</li></ul></div>
    <div class="col"><span class="stamp NA">Non nécessaire</span><ul>
      <li>Cache applicatif</li><li>Rate limiting global, délestage</li><li>Cloisons de pools, file e-mail dédiée</li>
      <li>Réplication, failover PostgreSQL</li></ul></div>
  </div>
</section>

<section id="limites">
  <div class="section-head"><p class="eyebrow">Limites restantes</p><h2>Où l'application peut encore tomber</h2></div>
  <ul class="limits">
    <li><b>Processus web unique.</b> Un crash coupe tout le monde ~2 s ; au-delà de ~250 utilisateurs actifs par processus, la latence monte (aucune erreur, mais 7,5 s de médiane à 1 000). Deux processus portent le plafond de 151,5 à 239,9 req/s mais ne protègent pas d'un crash du conteneur (s01 rejoué : 276 erreurs contre 227) ; deux répliques, recommandées, n'ont pas été mesurées.</li>
    <li><b>PostgreSQL absent = application absente.</b> Les requêtes échouent proprement (503) mais après 10 s d'attente du pool. Une base <em>figée</em> (processus gelé) retient les requêtes jusqu'au délai du client ou de nginx : <code>statement_timeout</code> est appliqué par le serveur, qui ne répond plus.</li>
    <li><b>Écritures sérialisées par AMM.</b> Le verrou qui supprime les mises à jour perdues fait attendre deux écritures simultanées sur la même AMM. Invisible à latence normale ; avec PostgreSQL à +500 ms par aller-retour, les écritures passent de 6,5 à 11,8 s au p95 (s02c), de 1,6 à 2,0 s à +100 ms : la justesse coûte du temps quand la base est déjà malade.</li>
    <li><b>Redis lent mais pas en panne.</b> Le disjoncteur ne s'ouvre que sur échec : Redis à +500 ms laisse la connexion à ~4 s et les écritures à ~1 s.</li>
    <li><b>E-mails au moins une fois.</b> Une réponse Gmail perdue après envoi donne un doublon (atténué par <code>Message-ID</code>). Une panne Gmail de plus de ~5 h abandonne l'e-mail, visible dans <code>v_ops_backlog</code>.</li>
    <li><b>Beat embarqué dans le worker.</b> Ne pas passer le worker à 2 répliques sans séparer beat : les tâches planifiées partiraient en double.</li>
    <li><b>Disque (serveur unique).</b> Rien n'alerte avant 100 % ; les sauvegardes sont sur le même disque que la base.</li>
    <li><b>Mesures.</b> Laboratoire Docker Desktop, tests de 40 à 60 s, une autre pile en parallèle : ordres de grandeur, pas une certification de capacité Railway. Aucune fuite mémoire n'a été cherchée au-delà de quelques minutes.</li>
  </ul>
</section>

<section id="methode" class="prose">
  <div class="section-head"><p class="eyebrow">Méthode</p><h2>Reproductible, mesurable, réversible</h2></div>
  <p>Pile Docker jetable isolée (<code>chaos/docker-compose.lab.yml</code>), dépendances jointes à travers toxiproxy,
  faux service Gmail pilotable, état de référence restauré avant chaque scénario, trafic simulé pendant chaque
  panne, 12 invariants vérifiés après chaque test par <code>manage.py check_integrity</code> (livré, et lancé
  chaque nuit). Code d'origine figé pour rejouer « avant » à l'identique.</p>
  <p>Deux défauts de l'outillage ont été corrigés en cours de route et sont signalés par transparence : le
  vérificateur manquait les fourches de versions (tri imposé entré dans le <code>GROUP BY</code>) ; un premier
  essai « disque plein » a écrit 92,7 Go sur le disque de la VM Docker (surcouche défaite par une
  restauration) — supprimés immédiatement, disque jamais au-delà de 15 %, garde-fou ajouté.</p>
</section>
"""

FOOTER = """Rapport complet : <code>docs/audit-resilience/RAPPORT.md</code> · cartographie :
<code>docs/audit-resilience/01-cartographie.md</code> · outillage et résultats bruts : <code>chaos/</code>."""
