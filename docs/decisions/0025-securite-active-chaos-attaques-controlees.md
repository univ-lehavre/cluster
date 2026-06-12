# 0025 — Sécurité active : chaos engineering + attaques contrôlées (chaîne détection→alerte→réaction)

## Contexte

Le dépôt valide sa sécurité par **15 scénarios**
([`test/scenarios/`](../../test/scenarios/)) qui exercent la **défense passive**
: PSA **rejette** un pod dangereux (10), NetworkPolicy **coupe** l'egress (11),
`securityContext` contraint le runtime (12), WireGuard **chiffre** le trafic
pod-to-pod (14), etcd **chiffre** les Secrets at-rest (15). Tous posent une
contrainte et vérifient qu'elle **est en place**.

Une reconnaissance de la posture sécurité a établi deux manques structurels :

1. **Aucun scénario n'exerce _offensivement_ la défense.** On vérifie qu'une
   NetworkPolicy existe, jamais qu'une **tentative d'exfiltration** est bel et
   bien coupée _en passant à l'acte_. La différence n'est pas cosmétique : une
   défense déclarée mais inopérante (policy non appliquée par le CNI, PSA en
   `warn` au lieu d'`enforce`) passe les tests passifs et échoue face à une
   attaque réelle.

2. **La chaîne « détection → alerte → réaction » a un trou sur le maillon
   _alerte_.** L'inventaire des détecteurs hôte
   ([`bootstrap/security/`](../../bootstrap/security/)) montre que :

   | Maillon       | fail2ban (jail sshd)              | auditd (règles)                | PSA / NetworkPolicy           |
   | ------------- | --------------------------------- | ------------------------------ | ----------------------------- |
   | **Détection** | ✅ repère 3 échecs SSH            | ✅ journalise les événements   | ✅ webhook d'admission / drop |
   | **Alerte**    | ❌ pas de notification temps réel | ❌ journal local, pas d'alerte | ❌ aucune alerte              |
   | **Réaction**  | ✅ bannit l'IP                    | — (passif)                     | ✅ rejette / coupe            |

   Le rôle [`alert`](../../bootstrap/security/roles/alert/) se borne aujourd'hui
   à rediriger les mails `root` via `/etc/aliases` (postfix) — il ne **branche
   pas** les détecteurs sur une destination d'alerte. Et il n'existe **aucune
   détection comportementale runtime** (shell dans un pod, exec inattendu,
   montage sensible) : ni Falco ni Tetragon, comme le constate la
   [note runtime/admission](../audit/2026-05-29/note-runtime-admission.md).

Le modèle de menace reste celui rappelé par
[ADR 0003](0003-pas-de-chiffrement-ceph-tailscale.md) et
[ADR 0019](0019-durcissement-reseau-cilium.md) : cluster **mono-tenant** de
recherche, **réseau privé isolé** `10.0.0.0/22`, **mono-admin**, pas de données
réglementées. On ne cherche pas une posture « banque » ; on cherche à **prouver
que les défenses déjà en place fonctionnent sous attaque**, et à **cartographier
les trous** de la chaîne d'alerte pour les combler (le maillon alerte hôte est
l'objet de l'issue #131, séparée).

La question posée ici est : **comment valider activement la sécurité sans
introduire de risque** — ni pour une infrastructure réelle, ni pour des tiers ?

## Décision

Adopter une démarche de **sécurité active** structurée autour du triptyque
**Détection → Alerte → Réaction (D/A/R)**, matérialisée par deux familles de
scénarios qui s'ajoutent à la suite existante, **et strictement bornée par des
garde-fous éthiques**.

### 1. Deux familles de scénarios (16 → 22)

- **Attaques contrôlées** — on _passe à l'acte_ contre une défense et on asserte
  les trois maillons D/A/R :
  - **16** brute-force SSH → **fail2ban bannit** la source ;
  - **17** pod d'évasion (`hostPath: /`, `hostPID`, `hostIPC`) → **PSA rejette**
    à l'admission (vecteurs **non couverts** par le 10, qui traite
    `privileged`/`hostNetwork`) ;
  - **18** exfiltration réseau → **NetworkPolicy/Cilium coupe** le canal.
- **Chaos engineering** — on dégrade volontairement l'infrastructure et on
  vérifie qu'elle **survit et se rétablit** :
  - **19** perte de paquets / partition réseau (`tc netem`) ;
  - **20** kill aléatoire de pods ;
  - **21** saturation CPU / mémoire (les `limits` doivent contenir l'impact).
- **Bouclage de l'alerte** — **22** vérifie de bout en bout que les détecteurs
  **alertent réellement** vers le puits mail de test
  ([Mailpit](../../platform/mailpit/)).

### 2. Triptyque D/A/R comme grille d'assertion

Chaque scénario offensif distingue explicitement, dans ses logs, trois maillons
:

- **`[D]` Détection** — l'événement adverse est **repéré** par un capteur (log
  fail2ban, message d'admission API, drop Hubble) ;
- **`[A]` Alerte** — une **notification part** vers Mailpit. Ce maillon **dépend
  de l'issue #131** (brancher l'alerting hôte sur Mailpit/Mailgun) : tant
  qu'elle n'est pas livrée, l'assertion d'alerte est **best-effort / non
  bloquante** (WARN), activable en dur par variable (`ALERT_CHECK=1` /
  `STRICT_ALERT=1`, calqués sur le `STRICT_OPTIN=1` du scénario 13) ;
- **`[R]` Réaction** — la défense **agit** (ban, rejet, coupure). C'est
  l'assertion **bloquante** : un scénario échoue si la réaction n'a pas lieu.

Ce découpage transforme « la défense est-elle configurée ? » en « la défense
**fonctionne-t-elle** sous attaque, et **le sait-on** (alerte) ? ».

### 3. Garde-fous éthiques — **banc isolé jetable UNIQUEMENT**

La sécurité active manipule des techniques offensives (brute-force, évasion,
exfiltration) et destructives (partition, kill, saturation). Elle n'est légitime
que **strictement encadrée** :

1. **Banc isolé jetable UNIQUEMENT.** Les scénarios 16-22 ne tournent **JAMAIS**
   contre une topologie réelle, une production, ni un nœud qui n'est pas un banc
   de test reconstructible. Cibles autorisées : banc Lima/kubeadm
   (`test/spikes/banc-lima-kubeadm/`), banc Vagrant `192.168.67.0/24`, ou tout
   cluster **explicitement marqué jetable**.
2. **Jamais de cible tierce.** Le brute-force SSH ne vise que les nœuds du banc
   ; aucun scan, aucune attaque, aucune exfiltration vers une adresse ou un hôte
   **hors du périmètre déclaré**. L'exfiltration est simulée vers une **cible
   interne déterministe** (pas l'Internet).
3. **Réversibilité obligatoire.** Toute perturbation est **retirée** au cleanup
   (`trap EXIT`) : unban fail2ban, `tc qdisc del`, suppression du pod stresseur.
   `KEEP=1` laisse l'état pour inspection — à nettoyer manuellement.
4. **Bornage des dégâts.** Le pod de saturation a des `resources.limits`
   **obligatoires** (il ne peut pas tuer le nœud) ; le netem cible **un seul**
   nœud ; le kill aléatoire **exclut le control plane** par défaut (sinon perte
   de l'API).

Ces garde-fous sont **matérialisés dans le code**, pas seulement énoncés :
chaque scénario offensif/chaos porte en tête une **garde « banc-only »** qui
refuse de s'exécuter (`exit 2`) si la cible n'est pas reconnue comme un banc (IP
dans une plage de banc, contexte kube `lima-*`/`*-banc`, ou `BANC=1` explicite).

### 4. Choix de l'outil de détection runtime — **différé**

L'ajout d'une détection comportementale runtime (**Falco** ou **Tetragon**)
**n'est pas tranché ici**. La
[note runtime/admission](../audit/2026-05-29/note-runtime-admission.md) en pose
les termes (Tetragon plaide par cohérence eBPF/Cilium ; à comparer sérieusement
à Falco) et conclut « hors V1 ». Cet ADR **acte la démarche** D/A/R et **borne**
son périmètre actuel à la détection **hôte** (fail2ban/auditd) et **Kubernetes**
(admission/NetworkPolicy) ; le choix d'un agent runtime fera l'objet d'un **ADR
dédié** quand l'axe sera priorisé. En conséquence, le maillon **`[A]` alerte
runtime** des scénarios offensifs est documenté comme **`N/A` aujourd'hui**
(seule l'alerte hôte, via #131, est testée).

## Statut

Accepted (2026-06-04).

## Conséquences

**Bénéfices.**

- **Preuve par l'acte.** On ne vérifie plus seulement la _présence_ d'une
  défense mais son _efficacité sous attaque_ — une policy non appliquée par le
  CNI ou un PSA en `warn` est désormais détecté.
- **Carte explicite des trous D/A/R.** Le triptyque rend visible que le maillon
  _alerte_ est le point faible (détection et réaction sont OK), ce qui **cadre
  et justifie l'issue #131**.
- **Résilience démontrée.** Les scénarios chaos prouvent que le cluster (réplica
  ×3 Ceph, reschedule K8s, `limits`) **encaisse** perte de paquets, kill et
  saturation — au-delà des scénarios de panne « propre » (03/04).
- **Démarche réutilisable et éthiquement cadrée** : un contributeur peut rejouer
  l'offensif sur _son_ banc jetable sans risque pour un tiers ni pour une prod.

**Prix à payer.**

- **Discipline d'exécution.** Ces scénarios sont **dangereux hors banc** : la
  garde « banc-only » et les avertissements README sont indispensables, et le
  runner les **saute par défaut** (SSH/chaos) pour ne pas les déclencher par
  inadvertance.
- **Couverture _alerte_ partielle tant que #131 n'est pas livrée** : le maillon
  `[A]` reste best-effort/WARN — assumé et explicitement gated, pas masqué.
- **Pas de détection runtime** : un comportement adverse _dans_ un pod (shell,
  exec) n'est pas détecté tant que l'ADR runtime n'est pas pris. Périmètre
  assumé (cf. §4).

**Garde-fous.**

- **Garde « banc-only » codée** dans chaque scénario (refus `exit 2` hors banc)
  ; **cleanup réversible** (`trap EXIT`) ; **`limits` obligatoires** sur le
  stresseur ; **exclusion du control plane** au kill ; **compte leurre** (jamais
  l'admin) et **IP source factice** (jamais l'opérateur) au brute-force.
- **Runner** : `needs_ssh` saute 16/19/22 sans accès fourni ; `is_destructive`
  attend `HEALTH_OK` après 19/20/21 — alignés sur la mécanique existante (13,
  03/04/05).
- **Valeurs génériques** ([ADR 0023](0023-plateforme-exemple-generique.md)) :
  cibles d'exemple (`192.168.67.x`, `10.0.0.0/22`), aucun secret réel.

## Alternatives écartées

**Déployer Falco/Tetragon maintenant pour alerter sur le runtime.** Écarté : +1
sous-système stateful à opérer sur un cluster **non-HA mono-admin**, sans
décision d'outil arbitrée (cf.
[note](../audit/2026-05-29/note-runtime-admission.md)). On **diffère** le choix
à un ADR dédié plutôt que de l'enterrer dans celui-ci.

**Lancer les scénarios offensifs/chaos sur la topologie réelle « pour être sûr
».** Écarté **catégoriquement** : c'est précisément ce que les garde-fous
interdisent — risque de ban de l'admin, de coupure réseau, d'indisponibilité. La
validation se fait sur **banc jetable**, dont c'est la raison d'être.

**Se contenter des scénarios passifs existants.** Écarté : ils ne distinguent
pas une défense _présente_ d'une défense _efficace_, et ne mesurent pas du tout
le maillon _alerte_ — les deux manques que cet ADR adresse.

**Factoriser une bibliothèque partagée entre scénarios** (netem, garde
banc-only, requête Mailpit). Écarté : romprait l'invariant du dépôt « chaque
scénario est un script autonome, lançable seul » ; on **duplique** délibérément
le petit boilerplate (le spike `clustermesh-latency` confine déjà son `tc` de la
même façon).
