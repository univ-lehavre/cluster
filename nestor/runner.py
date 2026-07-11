"""Couche d'exécution isolée : lance UNE phase via ansible-runner (P5, ADR 0063 G5).

C'est le **seul** module du dépôt qui importe `ansible_runner` (frontière pur/I-O
nette, ADR 0017). Il **lance** un playbook et **lit** le résultat exposé (`rc`,
`status`, et `changed` depuis `result.stats`). Il ne réimplémente **aucune
convergence** : pas de retry, pas de backoff (Ansible converge). Il fournit en
revanche une **vérification d'idempotence** (`launch_phase_idempotent` : lancer 2×
et constater `changed=0` au rejeu) — ce N'EST PAS de la convergence maison mais une
PREUVE (ADR 0052), portée de `run-phases.sh:run_ansible_phase` vers Python (qui lit
`changed` nativement dans `result.stats`, là où le bash grepait le PLAY RECAP).

La façade n'appelle QUE `launch_phase`/`launch_phase_idempotent`, jamais
`ansible_runner.run` directement, ce qui rend tout testable sans cluster (on _stubbe_
`_runner_run` renvoyant un faux objet à `.stats`).

`launch_phase` invoque le MÊME playbook avec les MÊMES `-e` dérivés
(`derive_run_params`, P2) et la MÊME cible que `run-phases.sh` (ADR 0063 G3) :
inventaire et `private_data_dir` sont fournis par l'appelant (jamais codés en dur),
`ANSIBLE_CONFIG`/`KUBECONFIG`/`EXPECTED_STACK_ID` posés dans l'environnement du
run comme le fait `lib.sh`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Artefacts persistés par ansible-runner dans <private_data_dir>/env/ et RÉUTILISÉS
# au run suivant : si on ne les purge pas, les extravars/cmdline d'un run PRÉCÉDENT
# (ex. la VIP `control_plane_host_ip` d'un run HA) CONTAMINENT un run mono-nœud
# (drift constaté : /etc/hosts pointé sur la VIP .40). On les supprime AVANT chaque
# lancement pour que SEULS les paramètres passés en kwargs comptent (ADR 0063 G3 :
# rien d'ambiant ; même esprit que le `limit` passé en kwarg, pas via cmdline).
_RUNNER_ENV_RESIDUALS = ("extravars", "envvars", "cmdline", "settings", "passwords")


def _purge_runner_env(private_data_dir: str) -> None:
    """Supprime les artefacts env/* d'un run ansible-runner PRÉCÉDENT (anti-contamination)."""
    env_dir = os.path.join(private_data_dir, "env")
    for name in _RUNNER_ENV_RESIDUALS:
        path = os.path.join(env_dir, name)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass  # déjà absent = l'état voulu (nettoyage idempotent), rien à faire
        except OSError:  # pragma: no cover - droits/FS ; on ne bloque pas le run
            pass


@dataclass
class RunResult:
    """Résultat exposé d'un run ansible-runner. `rc`/`status` bruts ; `changed` = somme
    des tâches `changed` du PLAY RECAP (depuis `result.stats`), ou None si illisible."""

    rc: int
    status: str  # 'successful' | 'failed' | 'timeout' | …
    changed: int | None = None


@dataclass
class IdempotenceResult:
    """Verdict du double-passage : déploiement + rejeu prouvant `changed=0`."""

    deployed: RunResult  # 1er passage (déploie)
    replayed: RunResult | None  # 2e passage (rejeu) ; None si le 1er a échoué
    verdict: str  # 'ok' | 'skip' | 'fail'
    message: str

    @property
    def ok(self) -> bool:
        return self.verdict == "ok"


class RunnerUnavailable(RuntimeError):
    """`ansible-runner` introuvable à l'exécution (mappé en erreur d'usage)."""


def classify_idempotence(changed: int | None) -> tuple[str, str]:
    """Verdict d'idempotence à partir du `changed` du rejeu (PUR). Portage fidèle de
    dataops-assert.sh:classify_idempotence (mêmes 3 cas, mêmes messages d'esprit) :

    0 → ok (rejeu sans changement) ; None → skip (récap illisible, non mesuré) ;
    > 0 → fail (idempotence cassée : `changed_when` fautif ? ADR 0051)."""
    if changed == 0:
        return "ok", "Idempotence : rejeu sans changement (changed=0)"
    if changed is None:
        return "skip", "Idempotence : récap Ansible illisible (rejeu non mesuré)"
    return (
        "fail",
        f"Idempotence CASSÉE : {changed} tâche(s) changed au rejeu "
        "(changed_when fautif ? ADR 0051)",
    )


def _stats_changed(result) -> int | None:
    """Somme des tâches `changed` d'un run ansible-runner, ou None si `stats` absent.

    `result.stats` = {'changed': {host: n}, 'ok': {...}, …} après le PLAY RECAP, ou
    None si le run a échoué avant (pas de recap) — d'où le None → skip."""
    stats = getattr(result, "stats", None)
    if not stats:
        return None
    changed = stats.get("changed")
    if changed is None:
        return None
    try:
        return sum(int(v) for v in changed.values())
    except (TypeError, ValueError, AttributeError):  # pragma: no cover - stats malformé
        return None


def _runner_run(**kwargs):
    """Indirection autour de `ansible_runner.run` (import LOCAL).

    Import local : la lib n'est chargée que lorsqu'on lance réellement (pas quand
    `next` est lu sans `--apply`), et un `ImportError` se mappe proprement en
    RunnerUnavailable. Point d'injection unique pour les tests (monkeypatch).
    """
    try:
        import ansible_runner
    except ImportError as exc:  # pragma: no cover - dépendance épinglée, garde-fou
        raise RunnerUnavailable(
            "ansible-runner introuvable (dépendance P5, ADR 0063) — `uv sync`"
        ) from exc
    return ansible_runner.run(**kwargs)


def launch_phase(
    playbook: str,
    extravars: dict,
    private_data_dir: str,
    inventory: str,
    *,
    ansible_config: str | None = None,
    kubeconfig: str | None = None,
    stack_id: str = "",
    limit: str | None = None,
) -> RunResult:
    """Lance UN playbook via ansible-runner ; renvoie (rc, status).

    `playbook` : chemin relatif à `private_data_dir/project` (ex.
    `bootstrap/dataops.yaml`). `extravars` : le faisceau `-e` dérivé. `inventory`
    et `private_data_dir` sont fournis par l'appelant (jamais ambiants — ADR 0063
    G3). On pose `ANSIBLE_CONFIG`/`KUBECONFIG`/`EXPECTED_STACK_ID` comme `lib.sh`
    (sinon roles_path / interpréteur / garde-fou de cible non chargés).

    `limit` : restreint le play à un sous-ensemble d'hôtes (ha-3cp promeut UN CP à
    la fois). Passé via le kwarg `limit` d'ansible-runner — PAS via `cmdline`, qui
    persisterait dans `env/cmdline` et fausserait les runs suivants.
    """
    # Purge les artefacts env/* d'un run PRÉCÉDENT : sinon ansible-runner réutilise
    # ses extravars persistés (ex. la VIP d'un run HA) et contamine ce run (ADR 0046).
    _purge_runner_env(private_data_dir)
    envvars: dict[str, str] = {"EXPECTED_STACK_ID": stack_id}
    if ansible_config:
        envvars["ANSIBLE_CONFIG"] = ansible_config
    if kubeconfig:
        envvars["KUBECONFIG"] = kubeconfig
    kwargs = dict(
        private_data_dir=private_data_dir,
        playbook=playbook,
        inventory=inventory,
        extravars=extravars,
        envvars=envvars,
    )
    if limit:
        kwargs["limit"] = limit
    result = _runner_run(**kwargs)
    return RunResult(
        rc=getattr(result, "rc", 1),
        status=getattr(result, "status", "unknown"),
        changed=_stats_changed(result),
    )


def launch_phase_idempotent(
    playbook: str,
    extravars: dict,
    private_data_dir: str,
    inventory: str,
    *,
    ansible_config: str | None = None,
    kubeconfig: str | None = None,
    stack_id: str = "",
    limit: str | None = None,
) -> IdempotenceResult:
    """Lance un playbook puis le REJOUE pour PROUVER l'idempotence (ADR 0052).

    Portage Python du double-passage de `run-phases.sh:run_ansible_phase` : 1er passage
    déploie (si rc≠0 → pas de rejeu, verdict `fail`) ; 2e passage = rejeu, dont le
    `changed` (lu nativement dans `result.stats`) doit valoir 0. Verdict via
    `classify_idempotence`. PAS de convergence maison : on lance 2× et on CONSTATE."""
    deployed = launch_phase(
        playbook,
        extravars,
        private_data_dir,
        inventory,
        ansible_config=ansible_config,
        kubeconfig=kubeconfig,
        stack_id=stack_id,
        limit=limit,
    )
    if deployed.rc != 0:
        return IdempotenceResult(
            deployed=deployed,
            replayed=None,
            verdict="fail",
            message=f"{playbook} : échec du déploiement (rc={deployed.rc})",
        )
    replayed = launch_phase(
        playbook,
        extravars,
        private_data_dir,
        inventory,
        ansible_config=ansible_config,
        kubeconfig=kubeconfig,
        stack_id=stack_id,
        limit=limit,
    )
    if replayed.rc != 0:
        return IdempotenceResult(
            deployed=deployed,
            replayed=replayed,
            verdict="fail",
            message=f"{playbook} : échec du rejeu d'idempotence (rc={replayed.rc})",
        )
    verdict, message = classify_idempotence(replayed.changed)
    return IdempotenceResult(deployed, replayed, verdict, message)
