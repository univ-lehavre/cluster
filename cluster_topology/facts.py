"""Parsing du CONTRAT MACHINE du banc (`run-phases.sh facts`) — pur (ADR 0017/0049).

Le banc imprime ses faits réels en KEY=VALUE (`run-phases.sh facts` → `emit_facts`) :
l'IP user-v2 du CP primaire, son interface L2, et la VIP/VIP_IFACE si la topo est HA.
Ce module PARSE cette sortie en dict — c'est le pont qui permet à `topology.py` de
DEMANDER les faits à bash (Python pilote, bash fournit) au lieu que bash calcule puis
passe ces valeurs en flags (sens inversé). Pur : aucune I/O, aucun subprocess (la
collecte = la façade qui lance `run-phases.sh facts`).
"""

from __future__ import annotations

# Clés attendues du contrat (les seules retenues — le bruit éventuel est ignoré).
_KNOWN_KEYS = {"CP_IP", "L2_IFACE", "VIP", "VIP_IFACE"}


def parse_facts(stdout: str) -> dict[str, str]:
    """Parse la sortie KEY=VALUE de `run-phases.sh facts` en dict. PUR.

    Ne retient que les clés connues du contrat (`CP_IP`, `L2_IFACE`, `VIP`,
    `VIP_IFACE`) : toute ligne sans `=`, vide, ou de clé inconnue (log/bruit mêlé)
    est IGNORÉE — robuste à une sortie un peu bavarde. Les valeurs sont strippées.
    `VIP`/`VIP_IFACE` sont absents en non-HA (le banc ne les émet pas)."""
    facts: dict[str, str] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key in _KNOWN_KEYS:
            facts[key] = value.strip()
    return facts
