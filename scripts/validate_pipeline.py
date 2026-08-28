"""
Contrôle de cohérence automatisé, exécuté après chaque reconstruction de
database/nfl.duckdb par le pipeline d'ingestion
(.github/workflows/update_data.yml).

Contrairement à validate_epa.py (script de diagnostic manuel, saison figée
à 2023, affiche un tableau pour un humain, ne peut rien bloquer), ce
script fait de vraies assertions et sort avec un code d'erreur non nul en
cas d'échec. C'est la porte de sécurité qui empêche le pipeline
de committer et déployer une base corrompue : si un check échoue, le job
GitHub Actions échoue et database/nfl.duckdb n'est ni commité ni poussé —
la base en production reste celle de la veille.

Les vérifications qui portent sur "la saison la plus récente" (colonnes
critiques, EPA plausible) utilisent MAX(season) trouvé dans les données,
pas CURRENT_SEASON directement : avant le coup d'envoi de la saison,
CURRENT_SEASON existe dans app/constants.py mais n'a encore aucune ligne
dans plays, ce qui est normal et ne doit pas faire échouer le pipeline.
Un écart entre les deux est seulement signalé, pas bloquant.
"""
import sys
from pathlib import Path

import duckdb

sys.path.append(str(Path(__file__).resolve().parent.parent / "app"))
from constants import CURRENT_SEASON

DB_PATH = "database/nfl.duckdb"
ERREURS = []


def echec(message):
    ERREURS.append(message)
    print(f"ÉCHEC : {message}")


def ok(message):
    print(f"OK : {message}")


con = duckdb.connect(DB_PATH, read_only=True)

# ─── Tables non vides ───
for table in ["plays", "games", "players", "teams", "rosters"]:
    count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    if count == 0:
        echec(f"table '{table}' vide")
    else:
        ok(f"{table} : {count:,} lignes")

# ─── Au moins 32 équipes ───
# La source teams_colors_logos.csv inclut légitimement des franchises
# historiques en plus des 32 actuelles (Oakland/Las Vegas, San Diego/LA
# Chargers, St. Louis/LA Rams, anciens noms de Washington...) — utile pour
# mapper correctement les vieilles données play-by-play qui référencent
# ces anciens codes. Un total > 32 est donc normal, seul un total < 32
# indiquerait une vraie perte de données.
nb_teams = con.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
if nb_teams < 32:
    echec(f"table 'teams' ne contient que {nb_teams} équipes, 32 minimum attendues")
else:
    ok(f"{nb_teams} équipes présentes (32 actuelles + variantes historiques éventuelles)")

# ─── Saison la plus récente réellement disponible ───
derniere_saison = con.execute("SELECT MAX(season) FROM plays").fetchone()[0]
if derniere_saison is None:
    echec("table 'plays' vide, aucune saison disponible")
    con.close()
    print(f"\n{len(ERREURS)} vérification(s) en échec — la base n'est pas commitée.")
    sys.exit(1)

ok(f"dernière saison disponible dans plays : {derniere_saison}")
if derniere_saison < CURRENT_SEASON:
    print(
        f"NOTE : CURRENT_SEASON={CURRENT_SEASON} dans app/constants.py, mais aucune "
        f"donnée play-by-play au-delà de {derniere_saison}. Normal avant le coup "
        f"d'envoi de la saison {CURRENT_SEASON} — à surveiller une fois les premiers "
        f"matchs joués (ce n'est PAS bloquant ici, juste informatif)."
    )

# ─── Colonnes critiques pas majoritairement nulles sur la dernière saison ───
# Si nflverse renomme/retire une colonne en amont, elle apparaîtrait ici
# comme quasi entièrement vide plutôt que de faire planter le fetch.
for col in ["epa", "posteam", "defteam"]:
    taux_non_nul = con.execute(
        f"SELECT COUNT({col}) * 1.0 / NULLIF(COUNT(*), 0) FROM plays WHERE season = ?",
        [derniere_saison],
    ).fetchone()[0]
    if taux_non_nul is None or taux_non_nul < 0.5:
        echec(
            f"colonne '{col}' majoritairement vide sur la saison {derniere_saison} "
            f"({(taux_non_nul or 0):.0%} de valeurs non nulles) — schéma nflverse "
            f"probablement changé en amont"
        )
    else:
        ok(f"colonne '{col}' : {taux_non_nul:.0%} de valeurs non nulles")

# ─── EPA moyen par équipe dans une plage plausible ───
# En NFL, l'EPA/play moyen d'une équipe se situe presque toujours entre
# -0.3 et +0.3. Une valeur hors de [-0.5, 0.5] indique presque certainement
# une erreur d'unité ou une colonne mal alignée plutôt qu'une vraie
# performance d'équipe.
df_epa = con.execute(
    """
    SELECT posteam, AVG(epa) AS epa_moy
    FROM plays
    WHERE season = ? AND play_type IN ('pass', 'run') AND posteam IS NOT NULL
    GROUP BY posteam
    """,
    [derniere_saison],
).fetchdf()

if df_epa.empty:
    echec(f"impossible de calculer l'EPA par équipe pour {derniere_saison} (aucune ligne pass/run)")
else:
    hors_plage = df_epa[(df_epa["epa_moy"] < -0.5) | (df_epa["epa_moy"] > 0.5)]
    if not hors_plage.empty:
        echec(f"EPA moyen hors plage plausible [-0.5, 0.5] pour : {hors_plage['posteam'].tolist()}")
    else:
        ok(
            f"EPA moyen par équipe dans une plage plausible "
            f"({df_epa['epa_moy'].min():.3f} à {df_epa['epa_moy'].max():.3f})"
        )

# ─── ngs_rushing (RYOE) — informatif, non bloquant ───
# Contrairement à plays/games/players/teams/rosters, ngs_rushing n'est pas
# une dépendance dure de l'app (RYOE est un enrichissement d'une colonne
# parmi d'autres sur Analytics > PRO > Course, pas une donnée dont le reste
# de l'app dépend). Un échec ici ne doit pas bloquer tout le rebuild
# quotidien juste parce que l'API Next Gen Stats a eu un problème
# ponctuel — on log seulement, sans ajouter à ERREURS.
nb_ngs = con.execute("SELECT COUNT(*) FROM ngs_rushing").fetchone()[0]
if nb_ngs == 0:
    print(
        "NOTE : table 'ngs_rushing' vide — RYOE n'apparaîtra pas dans "
        "Analytics > PRO > Course tant que le prochain run n'aura pas "
        "réussi à récupérer les données Next Gen Stats (non bloquant)."
    )
else:
    ok(f"ngs_rushing : {nb_ngs:,} lignes")

con.close()

print()
if ERREURS:
    print(f"{len(ERREURS)} vérification(s) en échec — la base n'est pas commitée.")
    sys.exit(1)
else:
    print("Toutes les vérifications sont passées.")
    sys.exit(0)
