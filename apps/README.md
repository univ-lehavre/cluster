# Applications

Charges applicatives déployées sur le cluster (calcul / services de recherche).

| Application            | Rôle                                                       |
| ---------------------- | ---------------------------------------------------------- |
| [`rstudio/`](rstudio/) | RStudio Server (image `rocker`) sur PVC RBD — cf. ADR 0012 |

> Les exemples de validation du stockage (WordPress/MySQL) vivent sous
> [`storage/ceph/wordpress/`](../storage/ceph/wordpress/), pas ici.

Vue d'ensemble du dépôt : [README racine](../README.md) ·
[Par où commencer](../docs/demarrage.md).
