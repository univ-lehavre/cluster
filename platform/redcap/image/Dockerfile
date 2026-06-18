# Image REDCap **maison** : PHP/Apache officiel + extensions REDCap + le code source.
#
# POURQUOI maison : REDCap (https://projectredcap.org) est un logiciel TIERS sous
# licence propriétaire (REDCap_License.txt) — il n'existe PAS d'image officielle
# publique redistribuable. On dérive donc `FROM php:8.3-apache` (multi-arch, ADR 0006)
# en y ajoutant (1) les extensions PHP que REDCap exige (mysqli/pdo_mysql/gd/zip/
# intl/…), (2) le code source REDCap copié AU BUILD depuis un contexte LOCAL.
#
# CODE SOURCE NON VERSIONNÉ : le PHP vit sous `apps/redcap/source/redcap/` (gitignoré,
# cf. .gitignore) ; il n'est JAMAIS commité. Le rôle platform-build-images copie ce
# `src_context` node-side puis build ici (build_all_arch : amd64 prod + arm64 banc),
# publié en `registry:80/redcap:<tag>`. Référence par TAG (image buildée localement,
# pas un upstream mutable — ADR 0006 ne vise que les images tirées d'un registre tiers).
#
# Build (depuis ce dossier, le code REDCap attendu sous ./source/redcap/) :
#   docker buildx build --platform linux/amd64,linux/arm64 \
#     -t <registry-interne>/redcap:v17.1.3 --push .
FROM php:8.3-apache@sha256:954d6198d9877b396382aa8a93d8be4832ab4908a7dc64f58dcc4be2833b8e29

# Extensions PHP requises par REDCap 17 (cf. Installation_Instructions.txt) :
#   mysqli + pdo_mysql (base MariaDB) ; gd (graphiques/PDF) ; zip (import/export) ;
#   intl + mbstring + gettext (i18n) ; opcache (perf). `docker-php-ext-install` compile
#   contre les libs système installées juste avant (libpng/zip/icu).
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    libpng-dev libjpeg-dev libfreetype6-dev libzip-dev libicu-dev libonig-dev \
  && docker-php-ext-configure gd --with-freetype --with-jpeg \
  && docker-php-ext-install -j"$(nproc)" mysqli pdo_mysql gd zip intl mbstring gettext opcache \
  && a2enmod rewrite \
  && rm -rf /var/lib/apt/lists/*

# Le webroot REDCap : `source/redcap/` contient index.php, install.php, database.php,
# redcap_v17.1.3/, etc. Copié dans le DocumentRoot Apache (/var/www/html).
COPY source/redcap/ /var/www/html/

# REDCap écrit dans /var/www/html/temp et /var/www/html/edocs (uploads). www-data
# (uid 33) est l'utilisateur Apache de l'image officielle ; il doit pouvoir y écrire.
RUN chown -R www-data:www-data /var/www/html/temp /var/www/html/edocs 2>/dev/null || true
