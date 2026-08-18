# Pipeline d'ingestion — ordre d'exécution

Ces scripts reconstruisent `database/nfl.duckdb` à partir des sources
nflverse. À exécuter **dans cet ordre**, depuis la racine du projet :

```powershell
python scripts/fetch_static.py
python scripts/fetch_rosters.py
python scripts/fetch_plays.py
python scripts/load_duckdb.py
python scripts/validate_epa.py
```

## Automatisation

Depuis `.github/workflows/update_data.yml`, ce pipeline tourne automatiquement
les vendredis, lundis et mardis à 13h00 UTC (9h ET) — lendemains des matchs
du jeudi, dimanche et lundi respectivement. Pas de run les autres jours :
Git LFS stocke une copie complète de la base à chaque push (pas de diff
binaire), donc pousser sans nouveau match ne ferait que consommer du quota
LFS pour rien. Déclenchement manuel possible à tout moment depuis l'onglet
**Actions** du repo GitHub (bouton "Run workflow") — utile pour les rares
matchs du samedi en fin de saison, non couverts par le cron.

Le workflow exécute les 4 premières étapes ci-dessus dans l'ordre, puis
`scripts/validate_pipeline.py` — pas `validate_epa.py` : celui-ci fait de
vraies assertions et sort en erreur si un contrôle échoue (table vide,
colonne critique cassée, EPA hors plage plausible). Si la validation
échoue, le job s'arrête là : `database/nfl.duckdb` n'est ni commité ni
poussé, la version en production (celle de la veille) reste inchangée.
Si elle passe, la base est commitée et poussée — ce qui déclenche le
redéploiement automatique sur Streamlit Cloud (qui surveille le repo).

## Détail de chaque étape

1. **fetch_static.py** — télécharge `games` (calendrier, scores), `players`
   (référentiel d'identifiants) et `teams` (couleurs, logos). Rapide.

2. **fetch_rosters.py** — télécharge les rosters saison par saison (bio,
   photo). Nécessaire pour les pages joueurs et les cartes Social Cards.

3. **fetch_plays.py** — télécharge le play-by-play complet, saison par
   saison. **L'étape la plus longue** (plusieurs minutes) — c'est la
   table `plays`, source de vérité de toute l'app.

4. **load_duckdb.py** — charge tous les fichiers `.parquet` produits par
   les trois scripts précédents dans `database/nfl.duckdb`. Rapide.

5. **validate_epa.py** — vérifie que les EPA calculés sur une saison
   connue correspondent à un classement d'équipes plausible (contrôle de
   cohérence, pas une étape obligatoire du pipeline).

## Changement de saison (nouvelle saison NFL en septembre)

Toutes les plages de saisons (`SEASONS = list(range(...))`) sont pilotées
par `app/constants.py` — `FIRST_SEASON` et `CURRENT_SEASON`. Changer
`CURRENT_SEASON` à cet endroit suffit ; les 3 scripts de fetch se
resynchronisent automatiquement, ce qui évite la dérive trouvée lors de
l'audit (`fetch_plays.py` et `fetch_static.py` s'étaient arrêtés à 2025
pendant que `fetch_rosters.py` allait déjà jusqu'à 2026 — chacun avait
son propre `range()` codé en dur, jamais mis à jour ensemble).

## Scripts de diagnostic (`check_*.py`, `validate_source.py`, `validate_epa.py`)

Pas partie du pipeline automatisé — utilisés ponctuellement pendant le
développement pour vérifier une hypothèse sur les données (colonnes
disponibles, couleurs d'équipe, cohérence des logos...). Peuvent être
ignorés en usage normal. `validate_pipeline.py` est différent : c'est la
porte de sécurité du workflow d'ingestion (voir plus haut), pas un script
de diagnostic manuel.

## `keep_awake.py` — empêcher la mise en veille de l'app

Streamlit Community Cloud endort toute app sans trafic depuis 12h.
`.github/workflows/keep_awake.yml` visite l'app toutes les 6 heures via
un vrai navigateur headless (Playwright) — un simple curl ne suffit pas :
Streamlit a besoin d'une vraie connexion WebSocket pour compter une
visite comme trafic, et réveiller une app déjà endormie nécessite de
cliquer le bouton "Yes, get this app back up!", impossible avec une
requête HTTP simple. Complètement indépendant du pipeline de données
(qui ne tourne que vendredi/lundi/mardi — bien trop espacé pour ça).

L'URL de l'app est en dur dans le workflow (`APP_URL`) — à corriger si
elle change.

