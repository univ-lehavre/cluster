"""Orchestration du socle k8s (`bootstrap` : k8s + CRI + CNI) en Python (ADR 0017/0049).

Migration incrémentale de `phase_bootstrap`/`bootstrap_node_sequence` (run-phases.sh)
vers Python, sur le MÊME moule que le moteur de chemin (`path.run_path`) : la LOGIQUE
(séquence ordonnée des
playbooks, extravars) est PURE et testable sans banc ; l'I/O réelle (lancer un
playbook, écrire l'inventaire, poser la CNI, récupérer le kubeconfig) est INJECTÉE
par la façade — qui la branche sur `runner.launch_phase` (Ansible) et les briques
bash irréductibles (limactl/CNI, ADR 0049).

Le socle de BASE = checks → cri → kubeadm → control-planes → initialisation →
join-workers (les 6 playbooks de bootstrap_node_sequence), chacun avec
`-e control_plane_ip=<cp_ip>`. La CNI (Cilium dans la VM via cni.sh) et l'inventaire
(write_inventory byte-stable) restent du bash APPELÉ — Python orchestre, ne réécrit
ni limactl ni le script CNI guest.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Les 6 playbooks du socle, dans l'ORDRE de dépendance (transcription fidèle de
# lib.sh:bootstrap_node_sequence). Relatifs au répertoire bootstrap/ (private_data_dir).
_BOOTSTRAP_PLAYBOOKS = [
    "checks.yaml",
    "cri.yaml",
    "kubeadm.yaml",
    "control-planes.yaml",
    "initialisation.yaml",
    "join-workers.yaml",
]


class BootstrapError(RuntimeError):
    """Une étape du socle a échoué (playbook KO, CNI KO, gate non tenue)."""


@dataclass
class BootstrapStep:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class BootstrapResult:
    built: bool
    steps: list[BootstrapStep] = field(default_factory=list)


def bootstrap_playbooks(*, has_workers: bool = True) -> list[str]:
    """Séquence ORDONNÉE des playbooks du socle (pure). Copie défensive.

    `has_workers=False` (topologie à control unique, sans worker) OMET
    `join-workers.yaml` : il n'y a aucun worker à joindre, donc le play
    `Workers join the cluster` ne matcherait aucun hôte (`skipping: no hosts
    matched`) — du bruit inutile. La DÉCISION de sauter ce playbook est portée
    EN PYTHON (qui connaît la topologie), pas en bash qui lance tout en aveugle."""
    if has_workers:
        return list(_BOOTSTRAP_PLAYBOOKS)
    return [pb for pb in _BOOTSTRAP_PLAYBOOKS if pb != "join-workers.yaml"]


def inventory_has_workers(inventory_text: str) -> bool:
    """`True` si le groupe `workers` de l'inventaire a ≥1 hôte (pur, sans I/O).

    Lit le rendu de `write_inventory` (lib.sh) : un groupe sans worker s'écrit
    `workers:\\n  hosts: {}` (mapping vide), avec workers `workers:\\n  hosts:\\n
    <vm>:`. On cherche, sous la clé `workers:` de 1er niveau, un `hosts:` non vide.
    Tolérant au bruit (commentaires, autres groupes) — c'est un signal, pas un
    parseur YAML complet (l'inventaire est byte-stable, généré par nous)."""
    lines = inventory_text.splitlines()
    in_workers = False
    for i, raw in enumerate(lines):
        if raw.startswith("workers:"):
            in_workers = True
            continue
        if in_workers:
            # Fin du groupe workers dès qu'on retombe en colonne 0 (autre clé).
            if raw and not raw[0].isspace() and not raw.startswith("#"):
                break
            stripped = raw.strip()
            if stripped == "hosts: {}":
                return False  # mapping vide explicite → aucun worker
            if stripped == "hosts:":
                # Worker présent ssi la ligne suivante non vide est un hôte indenté.
                for nxt in lines[i + 1 :]:
                    if not nxt.strip() or nxt.strip().startswith("#"):
                        continue
                    return nxt[0].isspace() and nxt.strip().endswith(":")
                return False
    return False


def bootstrap_extravars(cp_ip: str) -> dict:
    """Extravars `-e` communs aux playbooks du socle (pure).

    `control_plane_ip` = l'IP user-v2 réelle du CP primaire (advertiseAddress) — le
    seul `-e` que bootstrap_node_sequence passe aujourd'hui (`-e control_plane_ip=…`)."""
    return {"control_plane_ip": cp_ip}


def run_bootstrap(
    cp_ip: str,
    *,
    launch,
    run_cni,
    has_workers: bool = True,
    sleep=None,
):
    """Orchestre le socle k8s : playbooks en séquence + CNI. Logique testable.

    `launch(playbook, extravars)` : lance UN playbook (façade → runner.launch_phase) ;
    doit renvoyer un objet à `.rc`/`.status` (RunResult). `run_cni()` : pose la CNI
    (façade → brique bash run-phases.sh, ADR 0049). `has_workers` : voir
    `bootstrap_playbooks` — un control unique sans worker OMET `join-workers.yaml`.
    `sleep` : inutilisé ici (signature homogène avec path.run_path ; réservé à
    d'éventuelles gates futures).

    L'inventaire, le kubeconfig et la dérivation de cp_ip/iface restent à la façade
    (briques bash byte-stables / limactl) — Python n'orchestre que l'enchaînement
    Ansible + le déclenchement CNI. Lève BootstrapError au 1er échec (fail-fast,
    comme le `die` du bash)."""
    _ = sleep
    extravars = bootstrap_extravars(cp_ip)
    steps: list[BootstrapStep] = []
    for pb in bootstrap_playbooks(has_workers=has_workers):
        result = launch(pb, extravars)
        ok = getattr(result, "rc", 1) == 0
        steps.append(BootstrapStep(pb, ok, getattr(result, "status", "")))
        if not ok:
            raise BootstrapError(
                f"socle : playbook `{pb}` en échec (rc={getattr(result, 'rc', '?')})"
            )
    # CNI (Cilium dans la VM) : brique bash appelée (ADR 0049). Échec → BootstrapError.
    if run_cni() != 0:
        raise BootstrapError("socle : CNI (run_cni) en échec")
    steps.append(BootstrapStep("cni", True, "Cilium posé"))
    return BootstrapResult(built=True, steps=steps)
