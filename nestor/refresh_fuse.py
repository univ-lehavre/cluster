"""Fusion par ÉDITION TEXTE d'un `topology.yaml` pour `nestor refresh` (ADR 0076 §4).

`refresh` ÉDITE le fichier en place — il ne le RÉGÉNÈRE pas (différence nette avec
`discover -o` qui produit un fichier neuf). On préserve commentaires, `catalog.status`,
ordre des clés et valeurs non détectables (`max_replicas`, exposition implicite) : seules
les LIGNES concernées par un ajout du plan sont touchées. Édition au grain texte (pas de
re-dump YAML qui perdrait les commentaires — seul pyyaml est dispo, il ne round-trip pas).

PUR : prend le texte source + le plan, renvoie le texte fusionné (ne lit/écrit aucun
fichier — la façade gère l'I/O). Ne gère que les AJOUTS du plan (nœuds, couches, backend) :
les absences sont SIGNALÉES, jamais appliquées sans `--prune` (ADR 0076 §3, v2).

Hypothèses de format (vérifiées par `stack validate` en amont) : indentation à 2 espaces,
`storage.backend` sur sa ligne, `nodes:` en bloc (`- name:` / `roles:`), `layers:` en
liste inline (`[a, b]`) ou absent. Si un cas sort de ces formes, `fuse_topology` lève
`FuseError` plutôt que de corrompre le fichier (fail-closed — l'opérateur édite à la main).
"""

from __future__ import annotations

from nestor.refresh_plan import RefreshPlan


class FuseError(ValueError):
    """Le fichier n'a pas une forme éditable sûrement (l'opérateur tranche à la main)."""


def _replace_backend(lines: list[str], new_backend: str) -> list[str]:
    """Remplace la valeur de `storage.backend` SUR SA LIGNE, indentation préservée.

    Cherche la clé `backend:` à 2 espaces d'indentation sous `storage:`. Lève FuseError
    si introuvable (forme inattendue) — on ne devine pas où l'écrire."""
    out = list(lines)
    in_storage = False
    for i, line in enumerate(out):
        stripped = line.strip()
        # Entrée dans le bloc `storage:` (clé de 1er niveau, non indentée).
        if line.rstrip() == "storage:":
            in_storage = True
            continue
        if in_storage:
            # Clé `backend:` indentée sous storage (2 espaces).
            if stripped.startswith("backend:"):
                indent = line[: len(line) - len(line.lstrip())]
                comment = ""
                if "#" in line:  # préserve un commentaire de fin de ligne
                    comment = "  " + line[line.index("#") :].rstrip()
                out[i] = f"{indent}backend: {new_backend}{comment}\n"
                return out
            # Sortie du bloc storage : une clé de 1er niveau (non indentée, non vide).
            if line and not line.startswith(" ") and not line.startswith("#"):
                break
    raise FuseError("clé `storage.backend` introuvable — forme de fichier inattendue")


def _node_block(name: str, roles: list[str], indent: str = "  ") -> list[str]:
    """Rend un nœud en bloc YAML (même style que les nœuds existants, 2 espaces)."""
    block = [f"{indent}- name: {name}\n", f"{indent}  roles:\n"]
    block += [f"{indent}    - {role}\n" for role in roles]
    return block


def _append_nodes(lines: list[str], plan: RefreshPlan) -> list[str]:
    """Ajoute les nœuds du plan À LA FIN du bloc `nodes:` (préserve le reste)."""
    if not plan.nodes_to_add:
        return lines
    out = list(lines)
    # Repère le bloc `nodes:` (clé de 1er niveau) et la fin de ses entrées.
    start = next((i for i, ln in enumerate(out) if ln.rstrip() == "nodes:"), None)
    if start is None:
        raise FuseError("clé `nodes:` introuvable — forme de fichier inattendue")
    # Fin du bloc = première ligne de 1er niveau (non indentée, non vide/commentaire)
    # APRÈS `nodes:` — on insère juste avant.
    end = len(out)
    for i in range(start + 1, len(out)):
        ln = out[i]
        if ln.strip() and not ln.startswith(" ") and not ln.startswith("#"):
            end = i
            break
    block: list[str] = []
    for nc in plan.nodes_to_add:
        block += _node_block(nc.name, nc.roles)
    return out[:end] + block + out[end:]


def _add_layers(lines: list[str], plan: RefreshPlan) -> list[str]:
    """Ajoute les couches du plan à la clé `layers:` (inline) — ou la CRÉE si absente.

    `layers:` est une liste inline (`[a, b]`, forme produite par discover). Si la clé
    existe, on étend la liste ; sinon on insère une nouvelle clé de 1er niveau AVANT
    `storage:` (ordre lisible : nodes → layers → storage)."""
    if not plan.layers_to_add:
        return lines
    out = list(lines)
    idx = next((i for i, ln in enumerate(out) if ln.rstrip().startswith("layers:")), None)
    if idx is not None:
        line = out[idx].rstrip("\n")
        if "[" in line and "]" in line:
            inner = line[line.index("[") + 1 : line.rindex("]")].strip()
            existing = [x.strip() for x in inner.split(",") if x.strip()]
            merged = existing + [layer for layer in plan.layers_to_add if layer not in existing]
            indent = out[idx][: len(out[idx]) - len(out[idx].lstrip())]
            out[idx] = f"{indent}layers: [{', '.join(merged)}]\n"
            return out
        raise FuseError("clé `layers:` présente mais pas en liste inline `[…]` — édition manuelle")
    # Clé absente : insérer `layers: [..]` juste avant `storage:` (ou à défaut, en fin).
    insert_at = next((i for i, ln in enumerate(out) if ln.rstrip() == "storage:"), len(out))
    new_line = f"layers: [{', '.join(plan.layers_to_add)}]\n"
    return out[:insert_at] + [new_line] + out[insert_at:]


def fuse_topology(source: str, plan: RefreshPlan) -> str:
    """Applique les AJOUTS du plan au texte `source`, renvoie le texte fusionné (PUR).

    N'applique que `nodes_to_add` / `layers_to_add` / `backend_change`. Les absences du
    plan sont ignorées ici (signalées par la façade, retirées seulement via --prune).
    Lève `FuseError` si le fichier sort des formes éditables sûrement (jamais de
    corruption silencieuse). Idempotent : rejouer sur un fichier déjà à jour (plan vide)
    renvoie le texte inchangé."""
    if not plan.has_additions:
        return source
    lines = source.splitlines(keepends=True)
    lines = _append_nodes(lines, plan)
    lines = _add_layers(lines, plan)
    if plan.backend_change:
        lines = _replace_backend(lines, plan.backend_change[1])
    return "".join(lines)


def prunable_layers(source: str, plan: RefreshPlan) -> list[str]:
    """Couches `layers_absent` RÉELLEMENT présentes dans la liste inline `layers:` du
    fichier (PUR). `--prune` ne retire QUE ce qui est LITTÉRALEMENT déclaré : les
    `layers_absent` du plan sont au grain phase résolu, or `layers:` peut porter des
    alias (`dataops`) — pruner une phase résolue absente du littéral serait un no-op
    trompeur. On intersecte donc avec les jetons réellement écrits. Vide → rien à pruner."""
    absent = set(plan.layers_absent)
    if not absent:
        return []
    for ln in source.splitlines():
        s = ln.strip()
        if s.startswith("layers:") and "[" in s and "]" in s:
            inner = s[s.index("[") + 1 : s.rindex("]")]
            present = [x.strip() for x in inner.split(",") if x.strip()]
            return [x for x in present if x in absent]
    return []


def prune_topology(source: str, plan: RefreshPlan) -> str:
    """Retire du texte les couches `layers_absent` LITTÉRALEMENT présentes dans `layers:`
    (PUR, ADR 0076 §3). Inverse de `_add_layers` : édite la liste inline en place. Si la
    liste devient VIDE, on la rend `layers: []` (clé conservée, intention explicite). Ne
    touche RIEN d'autre (nœuds absents non prunés : une absence de nœud peut être une
    panne, pas un retrait voulu — §3). Idempotent. Lève FuseError sur forme inattendue."""
    to_remove = set(prunable_layers(source, plan))
    if not to_remove:
        return source
    lines = source.splitlines(keepends=True)
    idx = next((i for i, ln in enumerate(lines) if ln.rstrip().startswith("layers:")), None)
    if idx is None:
        return source
    line = lines[idx].rstrip("\n")
    if "[" not in line or "]" not in line:
        raise FuseError("clé `layers:` présente mais pas en liste inline `[…]` — édition manuelle")
    inner = line[line.index("[") + 1 : line.rindex("]")]
    kept = [x.strip() for x in inner.split(",") if x.strip() and x.strip() not in to_remove]
    indent = lines[idx][: len(lines[idx]) - len(lines[idx].lstrip())]
    lines[idx] = f"{indent}layers: [{', '.join(kept)}]\n"
    return "".join(lines)
