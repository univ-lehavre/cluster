"""Couche d'exécution isolée : lance UNE phase via ansible-runner (P5, ADR 0063 G5).

C'est le **seul** module du dépôt qui importe `ansible_runner` (frontière pur/I-O
nette, ADR 0017). Il **lance** un playbook et **lit** le résultat exposé (`rc`,
`status`) — il ne réimplémente **aucune** convergence : pas de retry, pas de
backoff, pas d'idempotence maison (ADR 0063 G1 ; Ansible/run-phases.sh s'en
chargent). La façade `next --apply` n'appelle QUE `launch_phase`, jamais
`ansible_runner.run` directement, ce qui rend P5 testable sans cluster (on
_stubbe_ `launch_phase` ou `_runner_run`).

`launch_phase` invoque le MÊME playbook avec les MÊMES `-e` dérivés
(`derive_run_params`, P2) et la MÊME cible que `run-phases.sh` (ADR 0063 G3) :
inventaire et `private_data_dir` sont fournis par l'appelant (jamais codés en dur),
`ANSIBLE_CONFIG`/`KUBECONFIG`/`EXPECTED_TARGET_KIND` posés dans l'environnement du
run comme le fait `lib.sh`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RunResult:
    """Résultat exposé d'un run ansible-runner. On consomme `rc`/`status` ; on n'en
    dérive aucun verdict (ADR 0063 G1)."""

    rc: int
    status: str  # 'successful' | 'failed' | 'timeout' | …


class RunnerUnavailable(RuntimeError):
    """`ansible-runner` introuvable à l'exécution (mappé en erreur d'usage)."""


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
    target_kind: str = "lima",
) -> RunResult:
    """Lance UN playbook via ansible-runner ; renvoie (rc, status).

    `playbook` : chemin relatif à `private_data_dir/project` (ex.
    `bootstrap/dataops.yaml`). `extravars` : le faisceau `-e` dérivé. `inventory`
    et `private_data_dir` sont fournis par l'appelant (jamais ambiants — ADR 0063
    G3). On pose `ANSIBLE_CONFIG`/`KUBECONFIG`/`EXPECTED_TARGET_KIND` comme `lib.sh`
    (sinon roles_path / interpréteur / garde-fou de cible non chargés).
    """
    envvars: dict[str, str] = {"EXPECTED_TARGET_KIND": target_kind}
    if ansible_config:
        envvars["ANSIBLE_CONFIG"] = ansible_config
    if kubeconfig:
        envvars["KUBECONFIG"] = kubeconfig
    result = _runner_run(
        private_data_dir=private_data_dir,
        playbook=playbook,
        inventory=inventory,
        extravars=extravars,
        envvars=envvars,
    )
    return RunResult(rc=getattr(result, "rc", 1), status=getattr(result, "status", "unknown"))
