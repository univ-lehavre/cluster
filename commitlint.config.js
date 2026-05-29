module.exports = {
  extends: ['@commitlint/config-conventional'],

  // Ce repo a une racine git « fork » avec un historique antérieur à
  // l'adoption des Conventional Commits (commits en français, sans type
  // ni scope, parfois > 100 colonnes). Le job CI commitlint scrute toute
  // la PR ; ces messages ne peuvent pas être rewrités sans refaire toute
  // l'histoire publique.
  //
  // Plutôt qu'une liste de subjects littérals (fragile), on filtre :
  // tout commit dont le subject n'a PAS la forme `type(scope?): ...` est
  // considéré comme historique pré-CC et ignoré. Les commits CC
  // (`feat:`, `fix(scope):`, `feat!:`, etc.) restent évalués
  // normalement contre les règles de @commitlint/config-conventional
  // (subject-case, header-max-length, body-max-line-length, etc.).
  ignores: [
    (commit) => {
      // Première ligne du commit message.
      const subject = commit.split('\n')[0] || ''
      // Conventional Commits header pattern (type optionnel scope, ! pour
      // breaking, suivi de `: …`) — identique à celui posé par le parser
      // de config-conventional.
      const ccPattern = /^[a-z]+(\([^)]*\))?!?: .+$/i
      // Les commits Conventional → on les valide normalement (ne pas ignorer).
      // Les autres (historique pré-CC) → on les ignore.
      return !ccPattern.test(subject)
    },
  ],
}
