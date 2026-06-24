# Mailpit

**Puits SMTP + UI web** : destination mail de **test** de la plateforme. Capture
les mails d'alerte (Alertmanager du
[monitoring](/cluster/platform/kube-prometheus-stack/), et à terme la couche
durcissement hôte) pour **valider la chaîne d'alerting de bout en bout** sur le
banc, sans relais externe.

Addon **autonome** (namespace `mail`) — transverse : sert le monitoring K8s
**et**, plus tard, le hardening hôte (destination mail unifiée).

## Fichiers

| Fichier         | Rôle                                                                                                                         |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `mailpit.yaml`  | Deployment (SMTP `1025` en `hostPort` pour le relais hôte #131, UI `8025`) + Service ClusterIP (SMTP `1025`, UI `80`→`8025`) |
| `nodeport.yaml` | Service NodePort de l'UI (port HTTP only) — UI consultable hors-cluster (ADR 0092), observée par le portail                  |

## Déploiement

```bash
kubectl apply -f platform/mailpit/mailpit.yaml
kubectl apply -f platform/mailpit/nodeport.yaml
kubectl -n mail rollout status deploy/mailpit
```

**Exposition L4** (`NodePort`,
[ADR 0092](/cluster/docs/decisions/0092-exposition-hostport-l4/)) : l'UI Mailpit
s'atteint par `http://<IP-nœud>:<nodePort>` (port auto, observé par le portail),
comme les autres UI de plateforme. Mailpit sert de **puits SMTP** : il capture
les notifications d'Alertmanager (`smtp_smarthost mailpit.mail:1025`, #489) —
son UI doit donc être consultable pour **lire les alertes**. Ce n'est pas un
vrai relais (boîte de test, pas d'envoi sortant). Seul son SMTP `1025` est aussi
exposé sur le nœud (`hostPort`, pour le relais postfix hôte, cf. plus bas).

Vérifier les mails capturés (alternatives au NodePort) :

```bash
kubectl -n mail port-forward deploy/mailpit 8025:8025   # puis http://localhost:8025
# ou via l'API : GET http://mailpit.mail.svc.cluster.local/api/v1/messages
```

## Rôle exact : test, pas relais

Mailpit **capture** les mails, il ne **relaie pas** vers une vraie boîte. C'est
un **puits de test** :

- **Banc ET prod** : Alertmanager (`smtp_smarthost: mailpit.mail.svc:1025`) y
  envoie ses alertes → on les consulte dans l'UI (NodePort via le portail). Une
  OSD coupée → alerte → mail capturé. C'est le mode retenu sur dirqual (#489) :
  un puits simple, sans relais externe à gérer.
- **Variante prod (optionnelle)** : si un envoi mail réel est requis, surcharger
  le smarthost d'Alertmanager vers un fournisseur SMTP externe (vendeur-neutre :
  Brevo, Mailgun, Amazon SES… `:587` + auth via Secret), config locale non
  versionnée
  ([ADR 0023](/cluster/docs/decisions/0023-plateforme-exemple-generique/)). Dans
  ce cas Mailpit peut rester comme environnement de test.

## Accès depuis l'HÔTE (relais postfix du hardening, #131)

Le postfix des nœuds (alertes fail2ban/auditd/smartd) tourne **hors du réseau
pods** : il ne peut joindre ni le Service ClusterIP `mailpit.mail.svc:1025` ni
le DNS `*.svc.cluster.local`. D'où un **`hostPort: 1025`** sur le pod mailpit
([ADR 0071](/cluster/docs/decisions/0071-exposition-gateway-hostnetwork/)) : le
postfix, qui tourne **sur le nœud**, joint le SMTP sur `NodeIP:1025` — routé en
eBPF par Cilium, **sans Service LoadBalancer ni LB-IPAM**.

```bash
# IP du nœud (banc mono-CP = InternalIP du control-plane) :
kubectl get nodes -l node-role.kubernetes.io/control-plane \
  -o 'jsonpath={.items[0].status.addresses[?(@.type=="InternalIP")].address}'
# puis pointer le postfix hôte : MAIL_SMARTHOST=[<NodeIP>]:1025
#   (cf. bootstrap/security/.env-example + rôle alert)
```

**Banc uniquement** : en prod, le smarthost postfix est le **même fournisseur
SMTP externe** qu'Alertmanager (vendeur-neutre, `:587` + auth) — ni `hostPort`
ni LoadBalancer SMTP.

## Adaptations

- Image épinglée par digest d'index multi-arch
  ([ADR 0006](/cluster/docs/decisions/0006-matrice-de-versions-et-politique-de-bump/)).
- Durci : `runAsNonRoot`, `readOnlyRootFilesystem` (base SQLite en `/tmp` via
  `emptyDir`), `drop ALL`, `seccompProfile: RuntimeDefault`.
- Stockage **en mémoire/`/tmp`** (jetable) — aucun secret réel, jamais de vraies
  clés (banc).
