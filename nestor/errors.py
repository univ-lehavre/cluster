"""Exceptions de base de nestor — module-feuille SANS dépendance (casse les cycles).

`TopologyError` vivait dans `model.py`, mais `layers.py`/`profile.py` l'importaient
en top-level → cycle `layers/profile → model → (lazy) layers` (py/cyclic-import).
L'isoler ici, dans un module qui n'importe rien de nestor, rompt le cycle : tout le
monde importe l'exception sans tirer `model`. `model.py` la ré-exporte (rétrocompat).
"""

from __future__ import annotations


class TopologyError(ValueError):
    """topology.yaml invalide (champ manquant, rôle inconnu, incohérence)."""
