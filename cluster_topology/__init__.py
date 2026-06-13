"""cluster_topology — outil déclaratif des topologies (ADR 0056).

`topology.yaml` est la source de vérité unique d'une topologie ; ce paquet en
DÉRIVE, SANS ÉTAT, les entrées que les outils consomment déjà (inventaire
Ansible aujourd'hui ; group_vars de profil et table de nœuds Lima ensuite).
Ansible reste le moteur de convergence (ADR 0056 §7) — l'outil ne réimplémente
jamais la convergence ni un état réconcilié.

Paliers P0-P1 (plan-modele-declaratif) : modéliser (`topology.example.yaml`) +
générer les DEUX inventaires BYTE-IDENTIQUES à l'existant — prod
(`bootstrap/hosts.example.yaml`) et banc Lima (sortie de `write_inventory`,
test/lima/lib.sh). La logique (chargement, dérivation, rendu) est pure et testée
(tests/test_cluster_topology.py, ADR 0017). La DÉRIVATION de profil (group_vars
de profil : ceph_osd_expected, etc.) relève de P2.
"""

from cluster_topology.generator import render_lima_inventory, render_prod_inventory
from cluster_topology.model import Topology, load_topology

__all__ = [
    "Topology",
    "load_topology",
    "render_prod_inventory",
    "render_lima_inventory",
]
