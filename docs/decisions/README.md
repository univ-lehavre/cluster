# Architecture Decision Records (ADR)

Trace **pourquoi** chaque choix de conception du cluster — pas le _comment_
(couvert par les README/RUNBOOK), mais le contexte, l'alternative écartée et les
conséquences assumées.

Format léger inspiré de Michael Nygard :

- **Contexte** — ce qui a forcé une décision.
- **Décision** — ce qui a été acté.
- **Statut** — Accepted / Superseded by `NNNN` / Deprecated.
- **Conséquences** — gain, prix à payer, garde-fous à connaître.

## Index

| #    | Titre                                                                               | Statut   |
| ---- | ----------------------------------------------------------------------------------- | -------- |
| 0001 | Réplication ×3 pour les workloads bloc (vs EC)                                      | À écrire |
| 0002 | Control plane unique avec `--control-plane-endpoint`                                | À écrire |
| 0003 | Pas de chiffrement Ceph — sécurité déléguée à Tailscale                             | À écrire |
| 0004 | Erasure coding 2+1 réservé au datalake                                              | À écrire |
| 0005 | CRI = `containerd.io` depuis le dépôt Docker                                        | À écrire |
| 0006 | Matrice de versions et politique de bump                                            | À écrire |
| 0007 | Hyperconvergence : control plane portant OSDs                                       | À écrire |
| 0008 | `metadataDevice` NVMe unique — SPOF par nœud assumé                                 | À écrire |
| 0009 | Pourquoi 4 nœuds ?                                                                  | À écrire |
| 0010 | [Dashboard Kubernetes en `cluster-admin`](0010-dashboard-cluster-admin.md)          | Accepted |
| 0011 | [Registry interne HTTP sans authentification](0011-registry-http-sans-auth.md)      | Accepted |
| 0012 | [RStudio sans authentification (`DISABLE_AUTH=true`)](0012-rstudio-disable-auth.md) | Accepted |
