# TODO

1. Renforcement de la gestion des accès
   - [x] Utiliser l’authentification par clé SSH uniquement.
   - [x] Désactiver le compte root SSH.
   - [x] Restreindre les utilisateurs autorisés à se connecter.
   - [ ] Mettre en place une gestion centralisée des accès (LDAP, SSO).
2. Durcissement de la configuration système
   - [x] Appliquer les mises à jour de sécurité automatiquement.
   - [ ] Désactiver ou désinstaller tous les services et paquets inutiles.
   - [x] Activer et configurer le pare-feu (UFW) pour n’ouvrir que les ports
         nécessaires.
   - [x] Utiliser fail2ban pour bloquer les tentatives d’intrusion.
3. Surveillance et audit
   - [x] Activer auditd avec des règles strictes.
   - [x] Centraliser les logs.
   - [ ] Mettre en place des alertes sur les événements critiques (modification
         de fichiers sensibles, élévation de privilèges, etc.).
4. Sécurisation du réseau
   - [x] Utiliser un VPN pour les accès d’administration.
   - [ ] Segmenter le réseau (VLAN, sous-réseaux) pour limiter la propagation en
         cas de compromission.
5. Gestion des secrets
   - [ ] Ne jamais stocker de secrets en clair sur le serveur.
   - [ ] Utiliser un Vault pour les mots de passe, clés, tokens.
6. Durcissement du kernel et du système
   - [ ] Activer AppArmor ou SELinux pour limiter les actions des services.
   - [ ] Activer la protection contre les attaques par symlink/hardlink
         (fs.protected_symlinks=1, fs.protected_hardlinks=1 dans sysctl).
7. Sauvegardes et plans de reprise
   - [ ] Mettre en place des sauvegardes régulières et tester leur restauration.
   - [ ] Documenter les procédures de reprise après incident.
