# Mailpit

**Puits SMTP + UI web** : destination mail de **test** de la plateforme. Capture
les mails d'alerte (Alertmanager du [monitoring](../kube-prometheus-stack/), et
à terme la couche durcissement hôte) pour **valider la chaîne d'alerting de bout
en bout** sur le banc, sans relais externe.

Addon **autonome** (namespace `mail`) — transverse : sert le monitoring K8s
**et**, plus tard, le hardening hôte (destination mail unifiée).

## Fichiers

| Fichier        | Rôle                                                  |
| -------------- | ----------------------------------------------------- |
| `mailpit.yaml` | Deployment Mailpit (SMTP `1025`, UI `8025`) + Service |
| `gateway.yaml` | exposition de l'UI (Gateway Cilium + TLS interne)     |

## Déploiement

```bash
kubectl apply -f platform/mailpit/mailpit.yaml
kubectl apply -f platform/mailpit/gateway.yaml   # UI sur mailpit.cluster.lan
kubectl -n mail rollout status deploy/mailpit
```

Vérifier les mails capturés :

```bash
kubectl -n mail port-forward deploy/mailpit 8025:8025   # puis http://localhost:8025
# ou via l'API : GET http://mailpit.mail.svc.cluster.local/api/v1/messages
```

## Rôle exact : test, pas relais

Mailpit **capture** les mails, il ne **relaie pas** vers une vraie boîte. C'est
un **puits de test** :

- **Banc** : Alertmanager (`smtp_smarthost: mailpit.mail.svc:1025`) y envoie ses
  alertes → on les consulte dans l'UI. Une OSD coupée → alerte → mail capturé.
- **Prod** : le smarthost d'Alertmanager est surchargé vers un service type
  **Mailgun** (`smtp.mailgun.org:587` + auth via Secret), config locale non
  versionnée
  ([ADR 0023](../../docs/decisions/0023-plateforme-exemple-generique.md)).
  Mailpit n'est pas déployé en prod, ou sert d'environnement de test.

## Adaptations

- Image épinglée par digest d'index multi-arch
  ([ADR 0006](../../docs/decisions/0006-matrice-de-versions-et-politique-de-bump.md)).
- Durci : `runAsNonRoot`, `readOnlyRootFilesystem` (base SQLite en `/tmp` via
  `emptyDir`), `drop ALL`, `seccompProfile: RuntimeDefault`.
- Stockage **en mémoire/`/tmp`** (jetable) — aucun secret réel, jamais de vraies
  clés (banc).
