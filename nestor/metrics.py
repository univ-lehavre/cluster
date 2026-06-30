"""Exposition des métriques DÉJÀ consignées (P6, ADR 0056 §8.8).

L'outil **LIT et EXPOSE** les métriques écrites dans `runs-history.yaml` (durée
totale, durées par phase, `cpu_core_s`, `ram_peak_mib`, `ram_mean_mib`) — il **ne
les réinvente pas** et n'en mesure aucune de neuf (l'échantillonnage Prometheus +
l'append d'un run sont un geste du BANC, historiquement `metrology.sh` ; ce script
a été retiré, ADR 0101 — l'auto-consignation Python reste à câbler, cf. le STUB
`record` de `path.py`). Module PUR : il met en forme des `Run` déjà chargés
(history.py), aucune I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from nestor.history import Run


@dataclass
class RunMetrics:
    """Vue métrique d'un run : identité + agrégats consignés (ou None si absents)."""

    run_id: str
    objectif: str  # profil / topologie (objectif d'infra, exig. 11)
    total_s: int | None
    phases: dict[str, int]
    cpu_core_s: int | None
    ram_peak_mib: int | None
    ram_mean_mib: int | None

    @property
    def has_metrics(self) -> bool:
        """Le run porte-t-il le bloc `metriques` ? (échantillonné si monitoring déployé)."""
        return any(
            getattr(self, k) is not None for k in ("cpu_core_s", "ram_peak_mib", "ram_mean_mib")
        )


def metrics_of(run: Run) -> RunMetrics:
    """Extrait la vue métrique d'un Run (pur, aucune dérivation nouvelle)."""
    m = run.metriques or {}
    return RunMetrics(
        run_id=run.id,
        objectif=run.objectif,
        total_s=run.total_s,
        phases=dict(run.phases or {}),
        cpu_core_s=m.get("cpu_core_s"),
        ram_peak_mib=m.get("ram_peak_mib"),
        ram_mean_mib=m.get("ram_mean_mib"),
    )


def _fmt_dur(seconds: int | None) -> str:
    """Durée lisible `<m>m<ss>s` (parité metro_fmt_dur, ex-metrology.sh). `?` si absente."""
    if seconds is None:
        return "?"
    return f"{seconds // 60}m{seconds % 60:02d}s"


def format_metrics(rm: RunMetrics) -> str:
    """Bloc texte lisible des métriques d'un run (durées + ressources consignées)."""
    lines = [f"run {rm.run_id} — {rm.objectif}"]
    lines.append(f"  durée totale  : {_fmt_dur(rm.total_s)}")
    if rm.phases:
        détail = ", ".join(f"{nom} {_fmt_dur(sec)}" for nom, sec in rm.phases.items())
        lines.append(f"  par phase     : {détail}")
    if rm.has_metrics:
        lines.append(
            f"  ressources    : cpu_core_s={rm.cpu_core_s if rm.cpu_core_s is not None else '?'}"
            f" · ram_peak={rm.ram_peak_mib if rm.ram_peak_mib is not None else '?'} MiB"
            f" · ram_mean={rm.ram_mean_mib if rm.ram_mean_mib is not None else '?'} MiB"
        )
    else:
        lines.append("  ressources    : non échantillonnées (monitoring absent au run)")
    return "\n".join(lines)
