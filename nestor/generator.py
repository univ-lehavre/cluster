"""Génération SANS ÉTAT des artefacts depuis une Topology (ADR 0056).

Palier P1 : rendre l'inventaire prod générique BYTE-IDENTIQUE à
`bootstrap/hosts.example.yaml`. Le rendu passe par un template Jinja2 versionné
(`templates/hosts.yaml.j2`) qui PORTE les commentaires pédagogiques tels quels —
ils ne sont pas devinés, ils sont la source. Éditer la prose = éditer le
template, pas le fichier généré (ADR 0056 : un fichier décrit, l'outil produit).
"""

from __future__ import annotations

import os

from jinja2 import Environment, FileSystemLoader

from nestor.model import Topology

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")


def _env() -> Environment:
    # keep_trailing_newline : préserve le \n final du template (byte-exact).
    # trim_blocks + lstrip_blocks : les blocs `{% %}` ne laissent ni ligne vide
    # ni indentation parasite — indispensable pour reproduire l'inventaire à
    # l'octet (les `{% for %}` ne doivent émettre QUE les lignes voulues).
    return Environment(
        loader=FileSystemLoader(_TEMPLATES_DIR),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
        # autoescape=False VOULU : on rend des inventaires YAML Ansible byte-exacts,
        # JAMAIS du HTML — l'auto-échappement transformerait `<`/`&`/`"` en entités
        # HTML et corromprait le YAML produit. Aucun contexte web (pas de risque XSS).
        autoescape=False,  # noqa: S701 — sortie YAML, pas HTML (cf. commentaire)
    )


def render_prod_inventory(topo: Topology) -> str:
    """Rend l'inventaire Ansible prod (= bootstrap/hosts.example.yaml).

    BYTE-IDENTIQUE attendu pour le profil prod générique (invariant P1).
    """
    template = _env().get_template("hosts.yaml.j2")
    return template.render(
        target_kind=topo.target_kind,
        control_nodes=topo.control_nodes,
        worker_nodes=topo.worker_nodes,
    )


def render_lima_inventory(topo: Topology, lima_home: str) -> str:
    """Rend l'inventaire du banc Lima (= sortie de `write_inventory`, lib.sh).

    BYTE-IDENTIQUE attendu par rapport à `write_inventory` (invariant P1, côté
    banc). `lima_home` est DÉRIVÉ DU TERRAIN (le `$HOME` du poste — chemin SSH
    `<home>/.lima/<vm>/ssh.config`), donc fourni explicitement : c'est la seule
    valeur non byte-stable de cette sortie. `workers` vide → `hosts: {}`.
    """
    template = _env().get_template("inventory-lima.yaml.j2")
    return template.render(
        control_nodes=topo.control_nodes,
        worker_nodes=topo.worker_nodes,
        lima_home=lima_home,
    )
