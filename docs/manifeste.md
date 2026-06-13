# Un cluster de recherche, raconté

Ceci est le **récit d'ingénierie** d'un cluster Kubernetes de recherche
hyperconvergé : pourquoi il existe, comment il est bâti, et ce qu'il produit. Il
se lit comme un article — contexte, objectif, données, méthode, trajectoire,
résultats — et s'adresse à un **lecteur néophyte**. Les termes techniques sont
des **liens** : un mot-clé renvoie à sa définition (le
[glossaire](glossaire.md)), à la décision qui le fonde (un [ADR](decisions/)) ou
à la brique concernée ([composants](composants.md)).

> 🔰 **Comprendre vs faire.** Ce récit **explique** (le pourquoi, l'ensemble).
> Pour **faire** pas à pas — installer, opérer — suivez le
> [parcours de démarrage](demarrage.md).
>
> **Valeurs génériques**
> ([ADR 0023](decisions/0023-plateforme-exemple-generique.md)). Les hôtes, IP et
> noms cités (`cp1`, `node1`, `10.0.0.0/22`…) sont des **exemples** : ce dépôt
> est un catalogue de topologies réutilisables, pas l'infrastructure d'un
> déploiement particulier. Les briques nommées (Ceph, Cilium, Dagster…) sont en
> revanche les vraies décisions techniques.

[[toc]]

## Contexte et état de l'art

Un laboratoire de recherche produit et consomme des données : il faut les
stocker, les transformer, les tracer, et faire tourner du calcul à côté. Or ces
gestes se déroulent aujourd'hui dans un environnement bien plus hostile et
disputé qu'il y a dix ans. Le **paysage des menaces** s'est intensifié : sur la
période juillet 2023 – juin 2024, l'ENISA a recensé plus de 11 000 incidents de
cybersécurité dans l'Union européenne, le rançongiciel et le déni de service en
représentant à eux seuls plus de la moitié [[1]](#références) ; le coût moyen
mondial d'une violation de données atteignait 4,88 millions de dollars en 2024,
en hausse de 10 % sur un an [[2]](#références). La recherche n'est pas un
dommage collatéral mais une **cible** : Microsoft la classe deuxième secteur le
plus visé par les acteurs étatiques en 2024 [[3]](#références), et en France
l'ANSSI note que l'enseignement supérieur représente 12 % des victimes de
rançongiciels qu'elle a connues en 2024 [[4]](#références). La chaîne
d'approvisionnement logicielle est elle-même devenue un vecteur : la porte
dérobée glissée dans la bibliothèque _xz/liblzma_ début 2024, notée au score de
gravité maximal (CVSS 10,0), n'a été découverte que par chance avant d'atteindre
les distributions stables [[5]](#références).

L'**intelligence artificielle** amplifie ce mouvement des deux côtés. Comme
arme, elle abaisse la barrière d'entrée des attaquants et augmente le volume et
l'impact des attaques — le centre britannique NCSC le juge « quasi certain » à
l'horizon de deux ans [[6]](#références). Comme moteur, elle fait exploser la
demande de calcul : le calcul d'entraînement des modèles de pointe croît d'un
facteur d'environ 4 à 5 par an, soit un doublement tous les cinq à six mois
[[7]](#références) ; et le stock de texte public exploitable pour entraîner ces
modèles pourrait être épuisé entre 2026 et 2032 [[8]](#références), ce qui fait
des **corpus de données** une ressource convoitée.

Cette demande de calcul nourrit une **compétition mondiale sur les data
centers**, dont l'enjeu est autant énergétique que géopolitique. En 2024, les
data centers consommaient environ 1,5 % de l'électricité mondiale (415 TWh), une
consommation que l'Agence internationale de l'énergie voit plus que doubler
d'ici 2030 [[9]](#références) ; l'investissement mondial dans ces
infrastructures a quasi doublé depuis 2022 pour approcher 500 milliards de
dollars en 2024 [[9]](#références). Cette capacité est très **concentrée** : les
États-Unis pèsent 45 % de la consommation électrique des data centers, devant la
Chine (25 %) et l'Europe (15 %) [[10]](#références). Surtout, trois fournisseurs
américains captent désormais 70 % du marché cloud européen, tandis que la part
des acteurs européens est retombée de 29 % (2017) à 15 % (2022)
[[11]](#références). Or l'hébergement chez un opérateur de droit américain
n'échappe pas au **CLOUD Act**, qui l'oblige à livrer les données qu'il contrôle
« qu'elles soient situées à l'intérieur ou à l'extérieur des États-Unis »
[[12]](#références) — la localisation des serveurs en Europe ne suffit donc pas.

Ces contraintes orientent déjà l'architecture. Trois besoins — **stocker**
(conserver de gros volumes durablement et de façon résiliente), **calculer**
(exécuter des traitements près des données) et **faire transiter** (déplacer les
données sans les exposer) — peuvent être servis par plusieurs modèles : le
**cloud public** (élastique mais externalisé et soumis à une juridiction
étrangère), le **cloud souverain** de confiance (qualifié mais au catalogue
restreint et plus coûteux), l'**on-premise** (maîtrise complète contre charge
d'exploitation) ou l'**hybride / edge**. Aucun de ces problèmes — menace,
dépendance, coût du calcul, fragilité de la chaîne — n'est neuf pour la
recherche : ils structurent depuis vingt ans des champs entiers de
l'informatique, dont la suite de cette section résume comment ils les abordent
et quelles perspectives ils dégagent.

**Stocker de façon résiliente.** Le champ s'est construit sur une tension
théorique — le théorème **CAP**, conjecturé par Brewer puis prouvé par Gilbert
et Lynch [[18]](#références), établit qu'un système distribué ne peut garantir
simultanément cohérence, disponibilité et tolérance au partitionnement. Les
systèmes fondateurs ont tranché ce compromis différemment, de _Google File
System_ [[19]](#références) à _Dynamo_ chez Amazon [[20]](#références), tandis
que [Ceph](glossaire.md#ceph) introduisait un placement déterministe sans
annuaire central [[21]](#références). La tension pratique — durer sans payer 200
% de surcoût de réplication — a relancé la recherche sur l'**erasure coding** :
les codes régénérants de Dimakis _et al._ [[22]](#références) caractérisent le
compromis entre stockage et bande passante de réparation, et les _Local
Reconstruction Codes_ déployés à grande échelle [[23]](#références) en réduisent
le coût. Une synthèse récente de plus de 280 travaux [[24]](#références) montre
que les **perspectives** se déplacent vers les approches hybrides réplication +
codage et vers la minimisation de la bande passante de réparation, y compris sur
des architectures de mémoire désagrégée.

**Tracer et reproduire.** Deux lignées convergent : une lignée _bases de données
/ workflows scientifiques_, qui formalise la **provenance** (le modèle W3C
**PROV** [[25]](#références), précédé des cadres fondateurs de Buneman _et al._
[[26]](#références)), et une lignée _science computationnelle_, qui érige la
**reproductibilité** en standard de publication [[27]](#références). Les
**principes FAIR** [[28]](#références) ont donné un cadre mondial à la gestion
des données réutilisables, étendu depuis au logiciel et aux workflows. Les
chercheurs soulignent toutefois un écart persistant entre « artefact disponible
» et « résultat réellement reproduit », et la **dette technique** propre aux
pipelines de données [[29]](#références). La **perspective** active est la
capture _automatique et de bout en bout_ de la provenance dans des pipelines
hétérogènes [[30]](#références) — l'enjeu même du
[_lineage_](composants.md#marquez-et-openlineage-lineage) de ce projet.

**Sécuriser et rester souverain.** La **souveraineté numérique** est traitée par
les sciences sociales comme un concept _contesté_, sans définition juridique
stable [[31]](#références), dont les initiatives concrètes (Gaia-X,
_International Data Spaces_) révèlent la tension entre souveraineté et
interopérabilité [[32]](#références). Côté cryptographie, les fondations
existent mais restent coûteuses : le chiffrement **homomorphe** de Gentry
[[33]](#références) et le calcul **multipartite sécurisé** [[34]](#références)
permettent en théorie de calculer sans révéler les données, au prix d'un surcoût
qui freine encore le passage à l'échelle. Sur le plan opérationnel, le
**zero-trust** — concept né chez un analyste, puis formalisé par le NIST
[[13]](#références) — et la sécurité de la **chaîne d'approvisionnement
logicielle** [[35]](#références) déplacent l'enjeu du théorique vers
l'_adoption_ : une garantie vérifiable n'a de valeur que si producteurs et
consommateurs l'implémentent.

**Calculer à la bonne échelle.** Face à la centralisation cloud, la recherche
déplace le curseur vers la périphérie : l'_edge computing_ [[36]](#références)
et le _fog computing_ rapprochent le calcul de la donnée pour la latence, la vie
privée et la résilience hors-ligne. La notion industrielle de _data gravity_ —
la donnée « attire » les traitements et devient coûteuse à déplacer — trouve sa
traduction savante dans le problème du **placement des données**. Enfin, la
**soutenabilité** devient un objet de recherche à part entière : après une
recalibration des estimations de consommation [[37]](#références), des travaux
sur l'ordonnancement _carbon-aware_ [[38]](#références) montrent qu'on peut
décaler les charges flexibles selon l'intensité carbone du réseau électrique.

**Une convergence.** Ces champs partagent un dénominateur : le **contrôle** —
juridique sur la donnée (souveraineté), sur sa durabilité (résilience), sur le
_comment_ d'un résultat (provenance), sur l'empreinte (soutenabilité). Deux
ponts ressortent. D'abord, « garder le calcul près de la donnée » sert _à la
fois_ la latence, la conformité et la soutenabilité — c'est le point de
convergence le plus net. Ensuite, la provenance vérifiable est une même idée
appliquée à deux objets : tracer comment un résultat scientifique est produit
(reproductibilité) et comment un artefact logiciel est construit (sécurité de la
chaîne). Une plateforme souveraine, résiliente et reproductible n'est donc pas
une juxtaposition de briques, mais la réponse cohérente à un faisceau de
questions que la recherche traite ensemble.

## Objectif

Plutôt que de louer ces capacités dans un nuage public, ce projet construit une
**plateforme souveraine** sur quelques serveurs : on en garde la maîtrise (coût,
confidentialité, juridiction, disponibilité) au prix d'avoir à l'opérer
soi-même. L'objectif n'est pas de livrer « un cluster » mais de **démontrer une
plateforme de données reproductible**, dont chaque décision est tracée et chaque
résultat rejouable. Concrètement, le projet vise à :

1. **Fournir un socle complet** — calcul, stockage distribué (bloc, fichier,
   objet), réseau, exposition de services, observabilité — utilisable par des
   développeurs qui n'ont **pas** à connaître l'infrastructure sous-jacente.
2. **Porter une chaîne DataOps** de bout en bout : orchestration de pipelines,
   base de données managée, traçabilité de l'origine des données (_lineage_).
3. **Rester un catalogue réutilisable**, pas une instance unique : plusieurs
   topologies déclarées, une activée par déploiement, valeurs génériques
   ([ADR 0023](decisions/0023-plateforme-exemple-generique.md)).
4. **Prouver, pas affirmer** : un résultat ne compte que s'il est reproductible
   à partir du code seul — principe-chapeau du dépôt
   ([ADR 0052](decisions/0052-reproductibilite-des-resultats.md)).

La frontière est nette : ce dépôt fournit le **contenant** (le socle générique)
; le **contenu** métier (pipelines, jeux de données d'un projet) vit ailleurs,
dans le dépôt applicatif.

## Données

Pour donner corps à la plateforme, prenons quatre sources de données ouvertes,
représentatives par leur diversité de volumétrie et de cadence (chiffres relevés
en juin 2026 ; ces sources grandissent en continu).

- **OpenAlex** — catalogue bibliographique ouvert (successeur de Microsoft
  Academic Graph). Environ **316 millions d'œuvres**, 118 millions d'auteurs ;
  le snapshot complet pèse **~330 Go compressés (~1,6 To décompressés)** en JSON
  Lines, et le snapshot public gratuit est **rafraîchi trimestriellement** (flux
  mensuels et changements quotidiens en offre payante) [[14]](#références).
- **Wikipedia** — dumps de la Wikimedia Foundation. ~7,2 millions d'articles
  pour la seule édition anglaise (~68 millions tous langages confondus). Le dump
  des révisions courantes fait ~25 Go compressés (>105 Go décompressés) ; le
  dump avec **historique complet atteint ~31 To décompressés**. Cadence
  **mensuelle** [[15]](#références).
- **GDELT** — base mondiale d'événements médiatiques, mise à jour **toutes les
  15 minutes**, 24h/24. Un audit officiel de 2021 dénombrait ~564 millions
  d'enregistrements d'événements et plus de 8 000 milliards de _datapoints_
  cumulés, en CSV et via BigQuery [[16]](#références).
- **OpenData ESR** — données ouvertes de l'Enseignement supérieur et de la
  Recherche français. Quelques **centaines de jeux** tabulaires (effectifs,
  diplômes, insertion, brevets…), de volumétrie modeste (du Ko à quelques
  dizaines de Mo), mis à jour **majoritairement une fois par an**, exposés via
  une API OpenDataSoft [[17]](#références).

Ces quatre sources, mises côte à côte, **posent des défis** que toute la suite
du récit cherche à relever. D'abord la **volumétrie** : conserver l'historique
Wikipedia et plusieurs snapshots OpenAlex amène d'emblée à plusieurs dizaines de
téraoctets, ce qui impose un stockage distribué et des formats colonnaires
compressés. Ensuite l'**hétérogénéité radicale des cadences** : faire cohabiter
un micro-batch toutes les 15 minutes (GDELT) avec un dump mensuel massif
(Wikipedia), un snapshot trimestriel (OpenAlex) et un rafraîchissement annuel
(ESR) sur un même plan d'orchestration est un piège architectural. Enfin la
**mise à jour incrémentale** : OpenAlex publie des fusions et suppressions
d'identifiants qu'un simple ajout en fin de table ignorerait, et l'historique
Wikipedia n'offre aucun delta natif — chaque cycle re-télécharge des téraoctets
inchangés faute d'une logique de capture des changements.

## Méthode

## Le voyage parcouru

## Résultats

## Références

1. ENISA, _Threat Landscape 2024_, 2024.
   <https://www.enisa.europa.eu/publications/enisa-threat-landscape-2024>
2. IBM (avec Ponemon Institute), _Cost of a Data Breach Report 2024_, 2024.
   <https://newsroom.ibm.com/2024-07-30-ibm-report-escalating-data-breach-disruption-pushes-costs-to-new-highs>
3. Microsoft, _Digital Defense Report 2024_, 2024.
   <https://www.microsoft.com/en-us/security/security-insider/threat-landscape/microsoft-digital-defense-report-2024>
4. ANSSI / CERT-FR, _Panorama de la cybermenace 2024_, 2025.
   <https://cyber.gouv.fr/actualites/panorama-de-la-cybermenace-2024-mobilisation-et-vigilance-face-aux-attaquants/>
5. NIST National Vulnerability Database, _CVE-2024-3094 (xz/liblzma)_, 2024.
   <https://nvd.nist.gov/vuln/detail/cve-2024-3094>
6. UK NCSC, _The near-term impact of AI on the cyber threat_, 2024.
   <https://www.ncsc.gov.uk/report/impact-of-ai-on-cyber-threat>
7. Epoch AI, _Training compute of frontier AI models grows by 4-5x per
   year_, 2024.
   <https://epoch.ai/blog/training-compute-of-frontier-ai-models-grows-by-4-5x-per-year>
8. Epoch AI, _Will we run out of data? Limits of LLM scaling based on
   human-generated data_, 2024.
   <https://epoch.ai/publications/will-we-run-out-of-data-limits-of-llm-scaling-based-on-human-generated-data>
9. IEA, _Energy and AI (World Energy Outlook Special Report)_, 2025.
   <https://www.iea.org/reports/energy-and-ai/executive-summary>
10. IEA, _Energy and AI_, 2025 (répartition géographique).
    <https://www.iea.org/reports/energy-and-ai/executive-summary>
11. Synergy Research Group, _European cloud providers' local market
    share_, 2025.
    <https://www.srgresearch.com/articles/european-cloud-providers-local-market-share-now-holds-steady-at-15>
12. 18 U.S. Code § 2713 (CLOUD Act), 2018, via Legal Information Institute
    (Cornell Law School). <https://www.law.cornell.edu/uscode/text/18/2713>
13. NIST, _SP 800-207 Zero Trust Architecture_, 2020.
    <https://www.nist.gov/news-events/news/2020/08/zero-trust-architecture-nist-publishes-sp-800-207>
14. OpenAlex, _Documentation — data snapshot_, 2026.
    <https://developers.openalex.org/download>
15. Wikimedia Foundation, _Data dumps_, 2026. <https://dumps.wikimedia.org/>
16. The GDELT Project, _Data_, 2021-2026.
    <https://www.gdeltproject.org/data.html>
17. Ministère de l'Enseignement supérieur et de la Recherche, _données ouvertes
    ESR_, 2026. <https://data.enseignementsup-recherche.gouv.fr/>
18. S. Gilbert, N. Lynch, _Brewer's conjecture and the feasibility of
    consistent, available, partition-tolerant web services_, ACM SIGACT
    News, 2002. DOI
    [10.1145/564585.564601](https://doi.org/10.1145/564585.564601).
19. S. Ghemawat, H. Gobioff, S.-T. Leung, _The Google File System_, SOSP, 2003.
    DOI [10.1145/945445.945450](https://doi.org/10.1145/945445.945450).
20. G. DeCandia _et al._, _Dynamo: Amazon's Highly Available Key-value Store_,
    SOSP, 2007. DOI
    [10.1145/1294261.1294281](https://doi.org/10.1145/1294261.1294281).
21. S. A. Weil _et al._, _Ceph: A Scalable, High-Performance Distributed File
    System_, OSDI, 2006.
22. A. G. Dimakis _et al._, _Network Coding for Distributed Storage Systems_,
    IEEE Trans. Information Theory, 2010. DOI
    [10.1109/TIT.2010.2054295](https://doi.org/10.1109/TIT.2010.2054295).
23. C. Huang _et al._, _Erasure Coding in Windows Azure Storage_, USENIX
    ATC, 2012.
24. Z. Shen _et al._, _A Survey of the Past, Present, and Future of Erasure
    Coding for Storage Systems_, ACM Trans. on Storage, 2025. DOI
    [10.1145/3708994](https://doi.org/10.1145/3708994).
25. L. Moreau, P. Missier (éds.), _PROV-DM: The PROV Data Model_, W3C
    Recommendation, 2013. <https://www.w3.org/TR/prov-dm/>
26. P. Buneman, S. Khanna, W.-C. Tan, _Why and Where: A Characterization of Data
    Provenance_, ICDT, 2001. DOI
    [10.1007/3-540-44503-X_20](https://doi.org/10.1007/3-540-44503-X_20).
27. R. D. Peng, _Reproducible Research in Computational Science_, Science, 2011.
    DOI [10.1126/science.1213847](https://doi.org/10.1126/science.1213847).
28. M. D. Wilkinson _et al._, _The FAIR Guiding Principles for scientific data
    management and stewardship_, Scientific Data, 2016. DOI
    [10.1038/sdata.2016.18](https://doi.org/10.1038/sdata.2016.18).
29. D. Sculley _et al._, _Hidden Technical Debt in Machine Learning Systems_,
    NeurIPS, 2015.
30. M. Schlegel, K.-U. Sattler, _Capturing end-to-end provenance for machine
    learning pipelines_, Information Systems, 2025. DOI
    [10.1016/j.is.2024.102495](https://doi.org/10.1016/j.is.2024.102495).
31. S. Couture, S. Toupin, _What does the notion of « sovereignty » mean when
    referring to the digital?_, New Media & Society, 2019. DOI
    [10.1177/1461444819865984](https://doi.org/10.1177/1461444819865984).
32. B. Otto, M. Jarke, _Designing a multi-sided data platform: findings from the
    International Data Spaces case_, Electronic Markets, 2019. DOI
    [10.1007/s12525-019-00362-x](https://doi.org/10.1007/s12525-019-00362-x).
33. C. Gentry, _Fully Homomorphic Encryption Using Ideal Lattices_, STOC, 2009.
    DOI [10.1145/1536414.1536440](https://doi.org/10.1145/1536414.1536440).
34. O. Goldreich, S. Micali, A. Wigderson, _How to Play ANY Mental Game_,
    STOC, 1987. DOI [10.1145/28395.28420](https://doi.org/10.1145/28395.28420).
35. S. Torres-Arias _et al._, _in-toto: Providing Farm-to-Table Guarantees for
    Bits and Bytes_, USENIX Security, 2019.
36. W. Shi _et al._, _Edge Computing: Vision and Challenges_, IEEE Internet of
    Things Journal, 2016. DOI
    [10.1109/JIOT.2016.2579198](https://doi.org/10.1109/JIOT.2016.2579198).
37. E. Masanet _et al._, _Recalibrating global data center energy-use
    estimates_, Science, 2020. DOI
    [10.1126/science.aba3758](https://doi.org/10.1126/science.aba3758).
38. P. Wiesner _et al._, _Let's Wait Awhile: How Temporal Workload Shifting Can
    Reduce Carbon Emissions in the Cloud_, Middleware, 2021. DOI
    [10.1145/3464298.3493399](https://doi.org/10.1145/3464298.3493399).
