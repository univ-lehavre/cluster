# 0088 — Signer les releases : tarball source + cosign keyless + provenance SLSA

## Statut

Accepted (2026-06-19). Le code est livré et mergé (`release.yml` : job
`sign-release` cosign keyless + job `provenance` SLSA).

## Contexte

Les tags de release ne sont pas signés (`git tag -v v2.38.0` → « cannot verify a
non-tag object ») et release-please ne signe rien. Le check OpenSSF
`Signed-Releases` est **rouge** (audit du 2026-06-16,
[notations-cyber](../audit/2026-06-16-audit-notations-cyber.md), issue #366). Il
est **distinct** de `Code-Review` (mono-mainteneur assumé, SAFEGUARDS.md) : pour
qui **consomme** une version figée du dépôt, une release signée est une garantie
d'intégrité vérifiable, indépendante du nombre de mainteneurs.

Deux faits cadrent la décision :

1. **Le check exige un ARTEFACT signé, pas un tag signé.** `Signed-Releases`
   inspecte les **assets** attachés à une GitHub Release et cherche des
   signatures (`.sig`, `.intoto.jsonl`). Or les releases du dépôt n'ont **aucun
   asset** (`gh release view --json assets` → `[]`). Signer le tag git ne verdit
   donc pas le check : il faut **publier un artefact** et le signer.
2. **Ce dépôt est de l'IaC qu'on clone, pas un binaire qu'on installe.** Un
   artefact n'a de sens que s'il fige une **version citable** du code. Le dépôt
   l'est déjà (DOI Zenodo, `CITATION.cff`) : une archive source par release est
   l'artefact naturel — la même chose que l'archive auto-générée par GitHub pour
   un tag, mais **publiée comme asset stable et signé**.

Le mécanisme de signature est tranché en amont : **cosign keyless (Sigstore)**
plutôt que GPG. Motif (issue #366) : en mono-mainteneur, le keyless via **OIDC
GitHub Actions** évite toute **gestion de clé** (pas de clé privée à stocker en
secret, à faire tourner, à révoquer) ; l'identité du signataire est le workflow
lui-même, attestée par Sigstore (transparency log Rekor). C'est aussi ce que
l'écosystème OpenSSF valorise.

## Décision

À chaque release, **publier une archive source `.tar.gz`, la signer en cosign
keyless, et générer une provenance SLSA**, le tout attaché comme assets de la
GitHub Release.

Modalités :

- **Artefact = archive source de la version.** Une `.tar.gz` du dépôt au tag de
  release (équivalent de l'archive GitHub, mais asset stable et signé). C'est ce
  que fige le DOI ; aucune compilation (pas de binaire à produire — IaC).
- **Signature = cosign keyless / OIDC.** Le job de release obtient un jeton OIDC
  (`id-token: write`), `cosign sign-blob` produit `.sig` + certificat ; aucune
  clé à gérer. Action et binaire **SHA-pinnés**
  ([ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)).
- **Provenance SLSA.** Une attestation `.intoto.jsonl` lie l'artefact au commit,
  au workflow et au déclencheur (générateur SLSA officiel, SHA-pinné). Élève la
  release au niveau **SLSA Build L3** côté supply-chain (#349).
- **Déclenchement = à la publication de la release**
  (`release: { types: [published] }`), pas dans le job release-please : la
  release doit exister pour qu'on y attache des assets. Job séparé,
  `permissions` au strict nécessaire (`contents: write` pour l'upload,
  `id-token: write` pour l'OIDC) — moindre privilège, cohérent avec le top-level
  `contents: read` (#435).
- **Vérification documentée côté consommateur** (RUNBOOK / README) :
  `cosign verify-blob --certificate-identity-regexp … --certificate-oidc-issuer https://token.actions.githubusercontent.com …`
  — une release n'a de valeur de preuve que si le consommateur sait la vérifier.

## Conséquences

- Le check `Signed-Releases` **passe au vert** dès la première release portant
  les assets signés — observable au prochain run Scorecard sur `main`, pas
  mesuré ici. La release gagne une **chaîne de confiance vérifiable** (intégrité
  - provenance), au-delà du seul score.
- **Le badge `Signed-Releases` reste à la doctrine d'affichage**
  ([ADR 0080](0080-notations-et-badges-readme.md)) : pas de badge dédié tant que
  Scorecard (qui l'agrège) n'est pas vert sur ce point ; le signal vit dans le
  badge Scorecard global.
- **Prix à payer** : chaque release publie 3 assets (archive, `.sig`/cert,
  provenance) ; un job de plus dans `release.yml` (post-publication). Dépendance
  à Sigstore (Fulcio/Rekor) au moment de signer — service public OpenSSF, panne
  rare et non bloquante pour le code (seule la signature échouerait, à rejouer).
- **Vérifiabilité réelle** : la provenance SLSA n'a de valeur que si elle est
  vérifiée — d'où la doc consommateur **obligatoire** (sinon c'est un asset
  décoratif, travers que borne
  [ADR 0052](0052-reproductibilite-des-resultats.md)).

## Alternatives écartées

- **Tags git signés GPG** (`git tag -s`). Écarté : impose une clé privée à gérer
  en CI (stockage secret, rotation, révocation) — friction en mono-mainteneur ;
  et surtout **ne verdit pas le check**, qui regarde les assets de release, pas
  la signature du tag.
- **Ne rien publier, signer le tag seul.** Écarté : sans asset,
  `Signed-Releases` reste rouge (cf. Contexte §1) — l'effort ne produirait pas
  le signal visé.
- **Assumer `Signed-Releases` N/A** (comme `Code-Review`). Écarté :
  contrairement à la revue par les pairs (structurellement liée au
  mono-mainteneur), la signature de release **ne dépend pas du nombre de
  mainteneurs** et apporte un gain net au consommateur (intégrité vérifiable) —
  critère 2, [ADR 0061](0061-posture-adoption-bonnes-pratiques.md).
