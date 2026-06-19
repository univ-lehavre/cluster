# 2026-06-19 — Évaluation Kubescape (framework NSA) : adoption ?

| Champ        | Contenu                                                                                                                                                                                                                                                                                                            |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Date**     | 2026-06-19                                                                                                                                                                                                                                                                                                         |
| **Type**     | revue d'adoption — un scanner de conformité K8s « Scorecard-like » (Kubescape) apporte-t-il un **gain net** vs l'outillage IaC déjà posé (Trivy `config`, Kyverno CLI prévu, PSA) ? Preuve = scan réel + évaluation multi-angle adversariale.                                                                      |
| **Fonde**    | _réflexion_ — aucune décision d'adoption. Le refus se trace ici (ADR 0058) ; un ADR ne serait requis que pour _adopter_.                                                                                                                                                                                           |
| **Prolonge** | l'[audit notations-cyber](2026-06-16-audit-notations-cyber.md) (volet « Scorecard-like orientés infrastructure ») et l'[audit CNCF/Kyverno](2026-06-15-audit-cncf-kyverno.md) (qui a déjà attribué le créneau « validation statique » à Kyverno, [ADR 0075](../decisions/0075-kyverno-cli-statique-ci.md)).        |
| **Verdict**  | **NE PAS CÂBLER Kubescape** : gain net de détection nul (redondance ~75-80 % avec Trivy `config`), tension avec ADR 0061/0075. Le scan révèle toutefois une **vraie dette** : resource limits CPU/mémoire non posées sur les workloads maison — à corriger dans le **code** (manifestes), pas par un nouvel outil. |

## Méthode

Scan réel `kubescape scan framework nsa platform/ storage/ apps/` (kubescape
4.0.9, manifestes statiques, sans cluster), puis évaluation multi-angle (gain
net / redondance / faisabilité CI / doctrine) avec passe adversariale. Les
gravités et le verdict sont ceux **après** réfutation (méthode ADR 0058 §3).

## Constat brut (à ne pas confondre avec une note)

Score de conformité **NSA = 80 %** (262 ressources, 49 en échec). Contrôles à
bas score :

| Contrôle Kubescape (NSA)           | Score | Lecture                                                                                                                  |
| ---------------------------------- | ----- | ------------------------------------------------------------------------------------------------------------------------ |
| Ensure CPU limits set              | 15 %  | **dette réelle** (33/39) — _mais_ déjà détecté par Trivy `KSV-0011` en LOW (cf. ci-dessous)                              |
| Non-root containers                | 38 %  | partiellement assumé (rstudio/wordpress/redcap) ; déjà `KSV-0012` (MEDIUM)                                               |
| Ensure memory limits set           | 44 %  | **dette réelle** (22/39) — déjà `KSV-0018` en LOW                                                                        |
| Automatic mapping of SA            | 51 %  | déjà couvert par Trivy/PSA                                                                                               |
| Immutable container filesystem     | 69 %  | déjà `KSV-0014` ; exceptions ADR pour workloads à compromis                                                              |
| HostNetwork access                 | 97 %  | **compromis assumé** : gateway hostNetwork ([ADR 0020](../decisions/0020-exposition-reseau-tout-cilium.md))              |
| Applications credentials in config | 97 %  | **faux positif** : fichiers `*.example` (valeurs de test, [ADR 0023](../decisions/0023-plateforme-exemple-generique.md)) |

> Le « 80 % » **n'est pas affichable**
> ([ADR 0080](../decisions/0080-notations-et-badges-readme.md)) : il mélange
> dette réelle, compromis tracés en ADR (comptés en défauts par l'outil) et
> bruit de granularité de règle. Aucun badge, aucun score figé au README.

## Pourquoi ne pas câbler (3 points)

1. **Gain net de détection = nul.** La prémisse « CPU/mémoire limits non
   couverts par Trivy » est **empiriquement fausse** : `trivy config` émet
   `KSV-0011` (cpu) et `KSV-0018` (memory), vérifié par scan. Ce n'est pas un
   trou de détection mais un **choix de seuil** : ces findings sont LOW, sous le
   gate `--severity HIGH,CRITICAL` ([`ci.yml`](../../.github/workflows/ci.yml)).
   Kubescape ne ferait que réexposer sous un autre nom ce que Trivy émet déjà.
2. **Redondance élevée (~75-80 %).** Les contrôles NSA mappent sur des `KSV-*`
   déjà actifs (host\*, securityContext, RBAC, rootfs, limits, credentials),
   dont une partie déjà allowlistée par chemin dans
   [`.trivyignore.yaml`](../../.trivyignore.yaml). Le seul contrôle « nouveau »
   (NetworkPolicy default-deny par namespace) est **non pertinent** : le dépôt
   route par Cilium
   ([ADR 0020](../decisions/0020-exposition-reseau-tout-cilium.md)) sans
   doctrine default-deny. Coût de diversité non compensé (2ᵉ binaire, 2ᵉ grille
   d'exceptions pour les **mêmes** compromis assumés) — contre
   [ADR 0061](../decisions/0061-posture-adoption-bonnes-pratiques.md)
   (critère 2) et
   [ADR 0049](../decisions/0049-doctrine-choix-outil-par-action.md) (un outil
   par action).
3. **Empilement contre une décision tenue.** Le créneau « validation statique de
   manifestes » est déjà attribué à **Kyverno CLI**
   ([ADR 0075](../decisions/0075-kyverno-cli-statique-ci.md)). Son §Contexte
   tranche déjà ce pattern : « Trivy détecte mais en LOW, sous le gate → c'est
   le créneau Kyverno, pas un nouvel outil. » Adopter Kubescape contredirait ce
   précédent écrit. **Réserve factuelle** : ADR 0075 est encore `Proposed` et
   Kyverno **n'est pas câblé en CI** (grep nul `kyverno` dans `ci.yml` au
   2026-06-19) — la couverture Kyverno est _prévue_, pas effective.

## Vrais gaps → corriger le CODE, pas ajouter un outil

(Principe « corriger le code, pas l'état »,
[ADR 0046](../decisions/0046-corriger-le-code-pas-l-etat.md).)

1. **Resource limits CPU (33/39) et mémoire (22/39) non posées** sur les
   workloads maison. Dette réelle. Correctif retenu : **poser les
   `resources.limits`/`requests`** dans les manifestes maison (pas les bundles
   vendored). À terme, une `ClusterPolicy` Kyverno `require-resource-limits` les
   gardera (une fois ADR 0075 `Accepted` et Kyverno câblé) — application du
   précédent §1.b.
2. **Non-root / privilege-escalation / rootfs immuable** : déjà
   `KSV-0012/0001/0014`. Durcir = corriger les `securityContext` des manifestes
   maison ; garder les exceptions ADR pour les workloads à compromis assumé
   (rstudio, wordpress, redcap).
3. **NetworkPolicy ingress/egress** : **non-gap** ici (Cilium, ADR 0020). Ne
   rien faire sauf décision d'architecture explicite via nouvel ADR.

## Limites

Scan **statique** de manifestes (pas de cluster) : Kubescape évalue le YAML, pas
l'état runtime. Le score 80 % est un instantané de ce passage, non re-noté en
continu (ADR 0058). Évaluation faite avec kubescape 4.0.9 (Homebrew).
