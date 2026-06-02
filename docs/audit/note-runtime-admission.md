# Note — sécurité admission & runtime (Kyverno / Falco / Tetragon)

> **Statut : réflexion, pas une décision.** Aucune action décidée au 2026-06-02.
> Cette note compare des options pour un choix _ultérieur_ (proche Phase 7). Si
> l'une est retenue, elle fera l'objet d'un ADR dédié. Demandée pour éclairer la
> question « ajouter Falco ou Kyverno à la CI ? ».

## Le point de départ : trois axes, pas un

« Falco ou Kyverno » mélange trois préoccupations distinctes. Les séparer est la
moitié de la réponse.

| Axe                      | Quand                | Outils                            | Couvert aujourd'hui ?                          |
| ------------------------ | -------------------- | --------------------------------- | ---------------------------------------------- |
| **Posture IaC statique** | en CI, avant merge   | **Trivy** (en place), Kyverno CLI | **Oui** — `trivy config` + `.trivyignore.yaml` |
| **Admission**            | à l'`apply`, cluster | Kyverno, cosign-policy            | Non (plan 7.2 l'évoque)                        |
| **Détection runtime**    | cluster vivant       | Falco, **Tetragon**               | Non                                            |

**Conséquence : « en CI » ne concerne qu'un seul des trois.** Falco et Kyverno
en admission sont des **composants déployés sur le cluster**, pas des étapes de
CI.

## Kyverno

- **En CI (Kyverno CLI).** `kyverno apply` teste les manifestes `platform/*`
  contre des _policies maison_ avant merge. **Gain réel, coût faible**
  (statique, pas de composant runtime). **Complémentaire de Trivy**, pas
  redondant : Trivy détecte des _misconfig connues_ (catalogue KSV) ; Kyverno
  applique _nos_ règles (« toute image épinglée par digest » —
  [ADR 0006](../decisions/0006-matrice-de-versions-et-politique-de-bump.md) ; «
  pas de Service LoadBalancer hors Gateway de bordure » —
  [ADR 0020](../decisions/0020-exposition-reseau-tout-cilium.md), exactement la
  règle déjà codée à la main dans `state.sh` couche 7b). C'est le candidat « en
  CI » le plus défendable.
- **En admission (sur le cluster).** Kyverno comme webhook qui refuse les
  manifestes non conformes. Utile, mais : (a) c'est un **déploiement**, pas « la
  CI » ; (b) **recoupe le plan 7.2** (vérification de signature d'images, où
  Kyverno est déjà cité comme _option locale hors benchmark_ face à la
  cosign-policy Sigstore) ; (c) +1 composant à opérer.

## Falco vs Tetragon (détection runtime)

Axe **non couvert** aujourd'hui (shell dans un pod, montage sensible, exec
inattendu…). **N'est pas un sujet de CI.** Deux candidats :

- **Falco** — référence CNCF de la détection runtime (syscalls/eBPF + règles).
  Mais : **aucune mention** dans le plan ni les ADR ; **+1 sous-système stateful
  runtime** à exploiter sur un cluster **non-HA mono-admin** (cf. ADR 0029, «
  prix à payer » de la charge opérationnelle).
- **Tetragon** — détection runtime eBPF du **même éditeur que Cilium**. Vu le
  choix **tout-Cilium** (ADR 0020 : kube-proxy replacement, Hubble, Gateway), un
  **datapath eBPF unifié** plaide pour Tetragon plutôt que Falco par cohérence
  d'écosystème (un agent eBPF de moins, intégration Hubble). À **comparer
  sérieusement** à Falco si l'axe runtime est priorisé — ne pas choisir Falco
  par réflexe.

## Recommandation de séquencement (à valider)

1. **Le moins cher d'abord** : si on veut renforcer la CI, **Kyverno CLI en CI**
   pour _nos_ invariants (digest, exposition) — gain immédiat, zéro composant
   runtime. Candidat naturel pour une future étape.
2. **Admission** : à traiter **avec** la Phase 7.2 (signature d'images), pas
   isolément — pour décider Kyverno _vs_ cosign-policy une seule fois.
3. **Runtime (Falco/Tetragon)** : **hors V1**, à peser quand la charge
   opérationnelle des composants déjà prévus (Dagster, CNPG, Marquez) est
   absorbée. Si retenu, **comparer Tetragon à Falco** (cohérence Cilium).

**Rien n'est décidé ici.** La V1 ne dépend d'aucune de ces briques.
