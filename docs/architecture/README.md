# Architecture

Vues d'ensemble transverses : elles **relient** plusieurs décisions (ADR) en un
récit cohérent, là où chaque ADR ne traite qu'un choix isolé. **Les ADR restent
la source de vérité** (immuables, datés) ; ces pages sont des **cartes de
lecture** par thème, qui pointent vers eux.

## Vues par domaine (décisions thématiques)

| Page                                                                       | Domaine — ADR reliés                                                                        |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| [`decisions-stockage.md`](decisions-stockage.md)                           | Stockage : Rook-Ceph, ×3 vs EC 2+1, SPOF NVMe, sauvegarde (0018, 0001, 0004, 0008, 0013)    |
| [`decisions-plan-de-controle.md`](decisions-plan-de-controle.md)           | Plan de contrôle & cycle de vie (0009, 0002, 0007, 0014, 0015)                              |
| [`decisions-securite-acces.md`](decisions-securite-acces.md)               | Sécurité & accès : modèle de menace, compromis assumés (0003, 0019, 0014, 0011, 0012, 0010) |
| [`decisions-plateforme-gitops.md`](decisions-plateforme-gitops.md)         | Plateforme & GitOps : observabilité, Argo CD (0016, 0022)                                   |
| [`decisions-conventions-outillage.md`](decisions-conventions-outillage.md) | Conventions : CRI, versions/pinning, scripts (0005, 0006, 0017)                             |
| [`exposition-reseau.md`](exposition-reseau.md)                             | Réseau : eBPF → IP → L2 → Gateway → TLS (0003, 0019, 0020, 0021, 0022)                      |

## Transverse

| Page                                           | Contenu                                                                      |
| ---------------------------------------------- | ---------------------------------------------------------------------------- |
| [`validation-banc.md`](validation-banc.md)     | Historique et évolution des campagnes de test sur le banc                    |
| [`matrice-catalogue.md`](matrice-catalogue.md) | Axes du catalogue, couverture des scénarios et des builds (matrice ADR 0023) |

Les **définitions** des termes sont dans le [glossaire](../glossaire.md) ; les
**décisions** détaillées et datées dans les [ADR](../decisions/).
