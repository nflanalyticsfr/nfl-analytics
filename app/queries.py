"""
queries.py — couche d'accès aux données pour NFL Analytics.

Toute l'app lit exclusivement via ce module : aucune page ne doit ouvrir
une connexion DuckDB ou écrire de SQL directement. Ça centralise les
requêtes, facilite les corrections transverses (ex. jointure rosters,
migration st.iframe) et évite la duplication de logique déjà rencontrée
plusieurs fois au fil du projet.

Organisation du fichier (dans l'ordre) :
    1. Connexion
    2. Utilitaires génériques (couleurs, saisons, traductions)
    3. Teams — vue saison
    4. Teams — classement hebdomadaire avec mouvement (▲/▼ vs semaine précédente)
    5. Players — bio et statistiques saison
    6. Players — tendances hebdomadaires
    7. Games
    8. Classements saison complète (Rankings > onglet Saison, Home)
    9. Classements hebdomadaires (Rankings > onglet Semaine)
    10. Social Cards — variantes cumulées (semaine 1 → semaine sélectionnée)
    11. Home — page d'accueil
    12. Rendu visuel (HTML / iframe)

Convention de nommage :
    get_*      → requête SQL, retourne un DataFrame pandas
    render_*   → affiche directement un composant Streamlit (pas de retour utile)
    *_week     → portée une seule semaine
    *_season   → portée saison complète
    *_cumulative_through_week / get_social_* → portée semaine 1 → semaine N incluse
"""

import duckdb
import pandas as pd
import re
import streamlit as st
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "nfl.duckdb"


# ──────────────────────────────────────────────────────────────────────────────
# CONNEXION
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def get_connection():
    """Connexion DuckDB en lecture seule, réutilisée pour toute la session (voir cache_resource)."""
    # read_only=True évite un conflit de verrou si un job d'ingestion
    # écrit sur le fichier pendant qu'un utilisateur consulte l'app.
    return duckdb.connect(str(DB_PATH), read_only=True)


# ──────────────────────────────────────────────────────────────────────────────
# UTILITAIRES GÉNÉRIQUES
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_available_seasons():
    """Liste des saisons présentes en base, pour peupler les sélecteurs."""
    con = get_connection()
    df = con.execute("SELECT DISTINCT season FROM plays ORDER BY season").fetchdf()
    return df["season"].tolist()

@st.cache_data(ttl=3600)
def get_weeks_for_season(season: int):
    """Liste des semaines jouées pour une saison donnée."""
    con = get_connection()
    df = con.execute(
        "SELECT DISTINCT week FROM plays WHERE season = ? ORDER BY week", [season]
    ).fetchdf()
    return df["week"].tolist()


# ─────────────────────────────────────────────────────────────
# Requêtes hebdomadaires (Weekly Recap)
# ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_team_colors():
    """Couleur officielle par équipe (abréviation -> hex), pour l'identité visuelle des graphiques et tableaux."""
    con = get_connection()
    df = con.execute("SELECT team_abbr, team_color FROM teams").fetchdf()
    return dict(zip(df["team_abbr"], df["team_color"]))

@st.cache_data(ttl=3600)
def get_team_logos():
    """URL du logo ESPN par équipe (abréviation -> URL)."""
    con = get_connection()
    df = con.execute("SELECT team_abbr, team_logo_espn FROM teams").fetchdf()
    return dict(zip(df["team_abbr"], df["team_logo_espn"]))

def couleur_texte_contraste(hex_color: str) -> str:
    """Calcule si un texte noir ou blanc est plus lisible sur un fond hexadécimal donné.
    Formule de luminance perçue ITU-R BT.601 : au-dessus de 0.6, le fond est
    jugé clair (texte noir), en dessous, sombre (texte blanc)."""
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#000000" if luminance > 0.6 else "#ffffff"

def convertir_taille_poids(height_val, weight_val):
    """Convertit taille (pouces ou format '6-2') et poids (livres) en
    mètres et kilogrammes. Retourne (None, None) si non convertible."""
    metres = None
    try:
        inches = float(height_val)
        metres = round(inches * 0.0254, 2)
    except (TypeError, ValueError):
        if isinstance(height_val, str) and "-" in height_val:
            try:
                pieds, pouces = height_val.split("-")
                total_pouces = int(pieds) * 12 + int(pouces)
                metres = round(total_pouces * 0.0254, 2)
            except ValueError:
                metres = None

    poids_kg = None
    try:
        poids_kg = round(float(weight_val) * 0.453592)
    except (TypeError, ValueError):
        poids_kg = None

    return metres, poids_kg

def traduire_surface(valeur: str) -> str:
    """Traduit le type de surface du terrain (donnée source en anglais) en français lisible."""
    if not isinstance(valeur, str):
        return "—"
    return TRADUCTION_SURFACE.get(valeur.lower(), valeur.capitalize())


# ──────────────────────────────────────────────────────────────────────────────
# TEAMS — VUE SAISON
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_all_teams():
    """Seules les 32 équipes actives sont retenues : celles ayant joué lors
    de la saison la plus récente en base. Filtre les franchises historiques
    (ex. St. Louis Rams, Oakland Raiders) qui existent dans le référentiel
    teams mais n'ont plus joué sous ce nom depuis leur déménagement."""
    con = get_connection()
    query = """
        WITH equipes_actives AS (
            SELECT DISTINCT posteam AS team_abbr FROM plays
            WHERE season = (SELECT MAX(season) FROM plays)
        )
        SELECT t.team_abbr, t.team_name
        FROM teams t
        JOIN equipes_actives e ON t.team_abbr = e.team_abbr
        ORDER BY t.team_name
    """
    df = con.execute(query).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_all_teams_records(season: int):
    """Bilan V/D/N de toutes les équipes pour une saison, calculé depuis
    la table games (un match compte pour les deux équipes via UNION ALL)."""
    con = get_connection()
    query = """
        WITH normalized AS (
            SELECT home_team AS team, home_score AS team_score, away_score AS opp_score
            FROM games WHERE season = ?
            UNION ALL
            SELECT away_team AS team, away_score AS team_score, home_score AS opp_score
            FROM games WHERE season = ?
        )
        SELECT team,
            SUM(CASE WHEN team_score > opp_score THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN team_score < opp_score THEN 1 ELSE 0 END) AS losses,
            SUM(CASE WHEN team_score = opp_score THEN 1 ELSE 0 END) AS ties
        FROM normalized
        WHERE team_score IS NOT NULL AND opp_score IS NOT NULL
        GROUP BY team
    """
    df = con.execute(query, [season, season]).fetchdf()
    total = df["wins"] + df["losses"] + df["ties"]
    df["win_pct"] = ((df["wins"] + 0.5 * df["ties"]) / total.replace(0, 1)).fillna(0)
    return df

@st.cache_data(ttl=3600)
def get_team_epa_offense_defense(season: int):
    """EPA offensif et défensif par équipe pour une saison donnée."""
    con = get_connection()
    query = """
        WITH offense AS (
            SELECT posteam AS team, AVG(epa) AS epa_offense, COUNT(*) AS plays_offense
            FROM plays
            WHERE season = ? AND play_type IN ('pass', 'run') AND posteam IS NOT NULL
            GROUP BY posteam
        ),
        defense AS (
            SELECT defteam AS team, AVG(epa) AS epa_defense, COUNT(*) AS plays_defense
            FROM plays
            WHERE season = ? AND play_type IN ('pass', 'run') AND defteam IS NOT NULL
            GROUP BY defteam
        )
        SELECT
            o.team,
            t.team_name,
            t.team_color,
            o.epa_offense,
            d.epa_defense,
            o.plays_offense,
            d.plays_defense
        FROM offense o
        JOIN defense d ON o.team = d.team
        LEFT JOIN teams t ON o.team = t.team_abbr
        ORDER BY o.epa_offense DESC
    """
    df = con.execute(query, [season, season]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_team_epa_by_week(team: str, season: int):
    """EPA offensif/défensif semaine par semaine pour une équipe et une saison."""
    con = get_connection()
    query = """
        SELECT
            week,
            AVG(CASE WHEN posteam = ? THEN epa END) AS epa_offense,
            AVG(CASE WHEN defteam = ? THEN epa END) AS epa_defense
        FROM plays
        WHERE play_type IN ('pass', 'run')
          AND season = ?
          AND (posteam = ? OR defteam = ?)
        GROUP BY week
        ORDER BY week
    """
    df = con.execute(query, [team, team, season, team, team]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_team_epa_by_season_multi(teams: list[str]):
    """EPA offensif/défensif saison par saison, pour plusieurs équipes en parallèle."""
    con = get_connection()
    placeholders = ", ".join(["?"] * len(teams))
    query = f"""
        WITH offense AS (
            SELECT season, posteam AS team, AVG(epa) AS epa_offense
            FROM plays
            WHERE play_type IN ('pass', 'run') AND posteam IN ({placeholders})
            GROUP BY season, posteam
        ),
        defense AS (
            SELECT season, defteam AS team, AVG(epa) AS epa_defense
            FROM plays
            WHERE play_type IN ('pass', 'run') AND defteam IN ({placeholders})
            GROUP BY season, defteam
        )
        SELECT o.season, o.team, o.epa_offense, d.epa_defense
        FROM offense o
        JOIN defense d ON o.season = d.season AND o.team = d.team
        ORDER BY o.season, o.team
    """
    df = con.execute(query, teams + teams).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_seasons_for_team(team: str):
    """Saisons où une équipe donnée a joué (utile pour une franchise ayant changé de nom/ville)."""
    con = get_connection()
    query = """
        SELECT DISTINCT season FROM plays
        WHERE posteam = ? OR defteam = ?
        ORDER BY season
    """
    df = con.execute(query, [team, team]).fetchdf()
    return df["season"].tolist()

@st.cache_data(ttl=3600)
def get_team_schedule(team: str, season: int):
    """Calendrier complet d'une équipe pour une saison, normalisé du point
    de vue de cette équipe (team_score/opp_score plutôt que home/away).
    Sert à la fois pour le bilan, les derniers matchs et les prochains matchs."""
    con = get_connection()
    query = """
        SELECT
            week, gameday,
            CASE WHEN home_team = ? THEN away_team ELSE home_team END AS opponent,
            CASE WHEN home_team = ? THEN TRUE ELSE FALSE END AS domicile,
            CASE WHEN home_team = ? THEN home_score ELSE away_score END AS team_score,
            CASE WHEN home_team = ? THEN away_score ELSE home_score END AS opp_score
        FROM games
        WHERE season = ? AND (home_team = ? OR away_team = ?)
        ORDER BY week
    """
    df = con.execute(query, [team, team, team, team, season, team, team]).fetchdf()
    df["joue"] = df["team_score"].notna() & df["opp_score"].notna()
    return df

@st.cache_data(ttl=3600)
def get_team_defensive_summary(team: str, season: int):
    """Résumé défensif au niveau équipe. Pas de détail par joueur :
    sack_player_id et les colonnes de tackle ne sont pas dans le schéma."""
    con = get_connection()
    query = """
        SELECT
            COUNT(*) FILTER (WHERE interception = 1) AS interceptions,
            COUNT(*) FILTER (WHERE fumble_lost = 1) AS fumbles_forces,
            SUM(CAST(sack AS DOUBLE)) AS sacks,
            ROUND(
                SUM(COALESCE(CAST(was_pressure AS DOUBLE), 0)) * 1.0
                / NULLIF(SUM(CASE WHEN pass = 1 THEN 1 ELSE 0 END), 0),
                3
            ) AS taux_pression
        FROM plays
        WHERE season = ? AND defteam = ?
    """
    df = con.execute(query, [season, team]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_all_teams_defensive_summary(season: int):
    """Résumé défensif de toutes les équipes pour une saison — base du
    classement affiché à côté de chaque KPI sur la page Teams."""
    con = get_connection()
    query = """
        SELECT
            defteam AS team,
            COUNT(*) FILTER (WHERE interception = 1) AS interceptions,
            COUNT(*) FILTER (WHERE fumble_lost = 1) AS fumbles_forces,
            SUM(CAST(sack AS DOUBLE)) AS sacks,
            ROUND(
                SUM(COALESCE(CAST(was_pressure AS DOUBLE), 0)) * 1.0
                / NULLIF(SUM(CASE WHEN pass = 1 THEN 1 ELSE 0 END), 0),
                3
            ) AS taux_pression
        FROM plays
        WHERE season = ? AND defteam IS NOT NULL
        GROUP BY defteam
    """
    df = con.execute(query, [season]).fetchdf()
    return df


@st.cache_data(ttl=3600)
def get_team_rank_label(df_all_teams, team_abbr: str, metric_col: str) -> str | None:
    """'#3 / 32' pour un KPI défensif donné, classé du plus fort au plus
    faible (plus d'INT/sacks/pression = meilleure défense). None si
    l'équipe est absente du classement."""
    if df_all_teams.empty or team_abbr not in df_all_teams["team"].values:
        return None
    df_sorted = df_all_teams.sort_values(metric_col, ascending=False).reset_index(drop=True)
    idx = df_sorted[df_sorted["team"] == team_abbr].index
    if len(idx) == 0:
        return None
    rang = idx[0] + 1
    total = len(df_sorted)
    return f"#{rang} / {total}"

@st.cache_data(ttl=3600)
def get_team_qb_leaders(team: str, season: int, min_dropbacks: int = 20):
    """Top 3 QB d'une équipe sur une saison, classés par EPA/dropback."""
    con = get_connection()
    query = """
        SELECT p.passer_player_name AS player, p.posteam AS team,
               ANY_VALUE(p.passer_player_id) AS player_id,
               ROUND(AVG(p.epa), 3) AS epa_per_play, COUNT(*) AS dropbacks,
               ANY_VALUE(r.headshot_url) AS photo_url
        FROM plays p
        LEFT JOIN rosters r ON p.passer_player_id = r.player_id AND r.season = p.season
        WHERE p.season = ? AND p.posteam = ? AND p.qb_dropback = 1 AND p.passer_player_id IS NOT NULL
        GROUP BY p.passer_player_name, p.posteam
        HAVING COUNT(*) >= ?
        ORDER BY epa_per_play DESC
        LIMIT 3
    """
    df = con.execute(query, [season, team, min_dropbacks]).fetchdf()
    return df

TRADUCTION_SURFACE = {
    "grass": "Pelouse naturelle",
    "fieldturf": "Gazon synthétique (FieldTurf)",
    "turf": "Gazon synthétique",
    "astroturf": "Gazon synthétique (AstroTurf)",
    "sportturf": "Gazon synthétique (SportTurf)",
    "matrixturf": "Gazon synthétique (MatrixTurf)",
    "a_turf": "Gazon synthétique",
    "dessograss": "Pelouse hybride (Desso GrassMaster)",
}

@st.cache_data(ttl=3600)
def get_team_rb_leaders(team: str, season: int, min_carries: int = 10):
    """Top 3 RB d'une équipe sur une saison, classés par EPA/course."""
    con = get_connection()
    query = """
        SELECT p.rusher_player_name AS player, p.posteam AS team,
               ANY_VALUE(p.rusher_player_id) AS player_id,
               ROUND(AVG(p.epa), 3) AS epa_per_play, COUNT(*) AS carries,
               ANY_VALUE(r.headshot_url) AS photo_url
        FROM plays p
        LEFT JOIN rosters r ON p.rusher_player_id = r.player_id AND r.season = p.season
        WHERE p.season = ? AND p.posteam = ? AND p.rush = 1 AND p.rusher_player_id IS NOT NULL
        GROUP BY p.rusher_player_name, p.posteam
        HAVING COUNT(*) >= ?
        ORDER BY epa_per_play DESC
        LIMIT 3
    """
    df = con.execute(query, [season, team, min_carries]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_team_wr_leaders(team: str, season: int, min_targets: int = 10):
    """Top 3 receveurs d'une équipe sur une saison, classés par EPA/cible."""
    con = get_connection()
    query = """
        SELECT p.receiver_player_name AS player, p.posteam AS team,
               ANY_VALUE(p.receiver_player_id) AS player_id,
               ROUND(AVG(p.epa), 3) AS epa_per_play, COUNT(*) AS targets,
               ANY_VALUE(r.headshot_url) AS photo_url
        FROM plays p
        LEFT JOIN rosters r ON p.receiver_player_id = r.player_id AND r.season = p.season
        WHERE p.season = ? AND p.posteam = ? AND p.pass = 1 AND p.receiver_player_id IS NOT NULL
        GROUP BY p.receiver_player_name, p.posteam
        HAVING COUNT(*) >= ?
        ORDER BY epa_per_play DESC
        LIMIT 3
    """
    df = con.execute(query, [season, team, min_targets]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_team_qb_leaders_yards(team: str, season: int, min_dropbacks: int = 20):
    """Top 3 QB d'une équipe sur une saison, classés par yards lancés (vue « stats classiques »)."""
    con = get_connection()
    query = """
        SELECT p.passer_player_name AS player, p.posteam AS team,
               ANY_VALUE(p.passer_player_id) AS player_id,
               SUM(p.passing_yards) AS yards, COUNT(*) AS dropbacks,
               ANY_VALUE(r.headshot_url) AS photo_url
        FROM plays p
        LEFT JOIN rosters r ON p.passer_player_id = r.player_id AND r.season = p.season
        WHERE p.season = ? AND p.posteam = ? AND p.qb_dropback = 1 AND p.passer_player_id IS NOT NULL
        GROUP BY p.passer_player_name, p.posteam
        HAVING COUNT(*) >= ?
        ORDER BY yards DESC
        LIMIT 3
    """
    df = con.execute(query, [season, team, min_dropbacks]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_team_rb_leaders_yards(team: str, season: int, min_carries: int = 10):
    """Top 3 RB d'une équipe sur une saison, classés par yards parcourus."""
    con = get_connection()
    query = """
        SELECT p.rusher_player_name AS player, p.posteam AS team,
               ANY_VALUE(p.rusher_player_id) AS player_id,
               SUM(p.rushing_yards) AS yards, COUNT(*) AS carries,
               ANY_VALUE(r.headshot_url) AS photo_url
        FROM plays p
        LEFT JOIN rosters r ON p.rusher_player_id = r.player_id AND r.season = p.season
        WHERE p.season = ? AND p.posteam = ? AND p.rush = 1 AND p.rusher_player_id IS NOT NULL
        GROUP BY p.rusher_player_name, p.posteam
        HAVING COUNT(*) >= ?
        ORDER BY yards DESC
        LIMIT 3
    """
    df = con.execute(query, [season, team, min_carries]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_team_wr_leaders_yards(team: str, season: int, min_targets: int = 10):
    """Top 3 receveurs d'une équipe sur une saison, classés par yards attrapés."""
    con = get_connection()
    query = """
        SELECT p.receiver_player_name AS player, p.posteam AS team,
               ANY_VALUE(p.receiver_player_id) AS player_id,
               SUM(p.receiving_yards) AS yards, COUNT(*) AS targets,
               ANY_VALUE(r.headshot_url) AS photo_url
        FROM plays p
        LEFT JOIN rosters r ON p.receiver_player_id = r.player_id AND r.season = p.season
        WHERE p.season = ? AND p.posteam = ? AND p.pass = 1 AND p.receiver_player_id IS NOT NULL
        GROUP BY p.receiver_player_name, p.posteam
        HAVING COUNT(*) >= ?
        ORDER BY yards DESC
        LIMIT 3
    """
    df = con.execute(query, [season, team, min_targets]).fetchdf()
    return df

# ─────────────────────────────────────────────────────────────
# Traduction des colonnes et style des tableaux
# ─────────────────────────────────────────────────────────────

TRADUCTIONS_COLONNES = {
    "team": "Équipe",
    "team_name": "Nom",
    "epa_offense": "EPA Offense",
    "epa_defense": "EPA Défense",
    "epa_allowed": "EPA Concédé",
    "epa_per_play": "EPA/Play",
    "plays_offense": "Jeux Off.",
    "plays_defense": "Jeux Déf.",
    "week": "Semaine",
    "season": "Saison",
    "player": "Joueur",
    "dropbacks": "Dropbacks",
    "carries": "Courses",
    "targets": "Cibles",
    "plays": "Plays",
    "yards": "Yards",
    "moyenne_saison": "Moyenne Saison",
    "cette_semaine": "Cette Semaine",
    "ecart": "Écart",
    "explosive_plays": "Jeux Explosifs",
    "play_type": "Type de Jeu",
    "yards_gained": "Yards",
    "epa": "EPA",
    "takeaways": "Prises",
    "giveaways": "Pertes",
    "differentiel": "Différentiel",
    "pressures": "Pressions",
    "pass_plays": "Plays Passe",
    "taux_pression": "Taux Pression",
    "qtr": "Quart-temps",
    "down": "Down",
    "ydstogo": "À Franchir",
    "yardline_100": "Position",
    "drive": "Drive",
    "desc": "Description",
    "resultat": "Résultat",
    "depart": "Départ",
    "possession": "Possession",
    "score_marque": "Score Marqué",
    "points_marques": "Points Marqués",
    "score_domicile": "Score Domicile",
    "score_exterieur": "Score Extérieur",
}


# ──────────────────────────────────────────────────────────────────────────────
# TEAMS — CLASSEMENT HEBDOMADAIRE AVEC MOUVEMENT
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_team_epa_rank_week(season: int, week: int):
    """Classement EPA offensif de toutes les équipes pour une semaine précise (base du calcul d'évolution)."""
    con = get_connection()
    query = """
        SELECT posteam AS team, AVG(epa) AS epa_offense
        FROM plays
        WHERE season = ? AND week = ? AND play_type IN ('pass', 'run') AND posteam IS NOT NULL
        GROUP BY posteam
    """
    df = con.execute(query, [season, week]).fetchdf()
    if df.empty:
        return df
    df = df.sort_values(["epa_offense", "team"], ascending=[False, True]).reset_index(drop=True)
    df["rank"] = df.index + 1
    return df

@st.cache_data(ttl=3600)
def get_team_weekly_movement(season: int, week: int):
    """Classement EPA offensif de la semaine, avec évolution de rang vs
    la semaine précédente de la même saison."""
    current = get_team_epa_rank_week(season, week)
    if current.empty:
        return current
    prev_map = {}
    if week > 1:
        previous = get_team_epa_rank_week(season, week - 1)
        if not previous.empty:
            prev_map = dict(zip(previous["team"], previous["rank"]))
    current["rank_precedent"] = current["team"].map(prev_map)
    current["evolution"] = current["rank_precedent"] - current["rank"]
    return current

@st.cache_data(ttl=3600)
def get_team_epa_cumulative_through_week(season: int, week: int):
    """EPA offensif/défensif moyen depuis la semaine 1 jusqu'à la semaine
    sélectionnée incluse — pas la saison entière."""
    con = get_connection()
    query = """
        WITH offense AS (
            SELECT posteam AS team, AVG(epa) AS epa_offense
            FROM plays
            WHERE season = ? AND week <= ? AND play_type IN ('pass', 'run') AND posteam IS NOT NULL
            GROUP BY posteam
        ),
        defense AS (
            SELECT defteam AS team, AVG(epa) AS epa_defense
            FROM plays
            WHERE season = ? AND week <= ? AND play_type IN ('pass', 'run') AND defteam IS NOT NULL
            GROUP BY defteam
        )
        SELECT o.team, o.epa_offense, d.epa_defense
        FROM offense o JOIN defense d ON o.team = d.team
    """
    df = con.execute(query, [season, week, season, week]).fetchdf()
    return df


# ──────────────────────────────────────────────────────────────────────────────
# PLAYERS — BIO ET STATISTIQUES SAISON
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_player_search_list(season: int):
    """Liste des joueurs ayant au moins une statistique qualifiante — offensive
    (passe, course, réception) ou défensive (tacle, sack, INT, PD, FF) — sur
    la saison."""
    con = get_connection()
    query = """
        WITH candidats AS (
            SELECT DISTINCT passer_player_id AS player_id FROM plays
                WHERE season = ? AND qb_dropback = 1 AND passer_player_id IS NOT NULL
            UNION
            SELECT DISTINCT rusher_player_id AS player_id FROM plays
                WHERE season = ? AND rush = 1 AND rusher_player_id IS NOT NULL
            UNION
            SELECT DISTINCT receiver_player_id AS player_id FROM plays
                WHERE season = ? AND pass = 1 AND receiver_player_id IS NOT NULL
            UNION SELECT DISTINCT solo_tackle_1_player_id FROM plays WHERE season = ? AND solo_tackle_1_player_id IS NOT NULL
            UNION SELECT DISTINCT solo_tackle_2_player_id FROM plays WHERE season = ? AND solo_tackle_2_player_id IS NOT NULL
            UNION SELECT DISTINCT assist_tackle_1_player_id FROM plays WHERE season = ? AND assist_tackle_1_player_id IS NOT NULL
            UNION SELECT DISTINCT assist_tackle_2_player_id FROM plays WHERE season = ? AND assist_tackle_2_player_id IS NOT NULL
            UNION SELECT DISTINCT sack_player_id FROM plays WHERE season = ? AND sack_player_id IS NOT NULL
            UNION SELECT DISTINCT half_sack_1_player_id FROM plays WHERE season = ? AND half_sack_1_player_id IS NOT NULL
            UNION SELECT DISTINCT interception_player_id FROM plays WHERE season = ? AND interception_player_id IS NOT NULL
            UNION SELECT DISTINCT pass_defense_1_player_id FROM plays WHERE season = ? AND pass_defense_1_player_id IS NOT NULL
            UNION SELECT DISTINCT forced_fumble_player_1_player_id FROM plays WHERE season = ? AND forced_fumble_player_1_player_id IS NOT NULL
        )
        SELECT c.player_id,
               ANY_VALUE(r.player_name) AS player_name,
               ANY_VALUE(r.team) AS team,
               ANY_VALUE(r.position) AS position
        FROM candidats c
        LEFT JOIN rosters r ON c.player_id = r.player_id AND r.season = ?
        WHERE c.player_id IS NOT NULL
        GROUP BY c.player_id
        ORDER BY player_name
    """
    params = [season] * 13
    df = con.execute(query, params).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_player_bio(player_id: str, season: int):
    """Bio du joueur telle qu'au moment de la saison donnée. Si absente
    (joueur non présent au roster cette saison précise), repli sur la
    saison connue la plus proche."""
    con = get_connection()
    query = """
        SELECT player_name, team, position, age, height, weight,
               college, jersey_number, years_exp, headshot_url
        FROM rosters
        WHERE player_id = ? AND season = ?
    """
    df = con.execute(query, [player_id, season]).fetchdf()
    if df.empty:
        query_fallback = """
            SELECT player_name, team, position, age, height, weight,
                   college, jersey_number, years_exp, headshot_url
            FROM rosters
            WHERE player_id = ?
            ORDER BY ABS(season - ?) ASC
            LIMIT 1
        """
        df = con.execute(query_fallback, [player_id, season]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_player_games_played(player_id: str, season: int):
    """Nombre de matchs joués par un joueur sur une saison (compte les game_id distincts où il apparaît)."""
    con = get_connection()
    query = """
        SELECT COUNT(DISTINCT game_id) AS matchs
        FROM plays
        WHERE season = ?
          AND (passer_player_id = ? OR rusher_player_id = ? OR receiver_player_id = ?)
    """
    df = con.execute(query, [season, player_id, player_id, player_id]).fetchdf()
    return int(df["matchs"].iloc[0]) if not df.empty else 0

@st.cache_data(ttl=3600)
def get_player_passing_season(player_id: str, season: int):
    """Statistiques de passe (yards, TD, INT, EPA, CPOE, air yards) d'un joueur sur une saison entière."""
    con = get_connection()
    query = """
        SELECT
            COUNT(*) FILTER (WHERE pass = 1) AS tentatives,
            COUNT(*) FILTER (WHERE complete_pass = 1) AS completions,
            SUM(passing_yards) AS yards,
            COUNT(*) FILTER (WHERE complete_pass = 1 AND touchdown = 1) AS td,
            COUNT(*) FILTER (WHERE interception = 1) AS interceptions,
            ROUND(AVG(epa) FILTER (WHERE qb_dropback = 1), 3) AS epa_per_play,
            ROUND(AVG(cpoe) FILTER (WHERE pass = 1), 1) AS cpoe,
            ROUND(AVG(air_yards) FILTER (WHERE pass = 1), 1) AS air_yards_moy,
            COUNT(*) FILTER (WHERE qb_dropback = 1) AS dropbacks
        FROM plays
        WHERE season = ? AND passer_player_id = ?
    """
    df = con.execute(query, [season, player_id]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_player_rushing_season(player_id: str, season: int):
    """Statistiques de course (yards, TD, EPA) d'un joueur sur une saison entière."""
    con = get_connection()
    query = """
        SELECT
            COUNT(*) FILTER (WHERE rush = 1) AS courses,
            SUM(rushing_yards) AS yards,
            COUNT(*) FILTER (WHERE rush = 1 AND touchdown = 1) AS td,
            ROUND(AVG(epa) FILTER (WHERE rush = 1), 3) AS epa_per_play
        FROM plays
        WHERE season = ? AND rusher_player_id = ?
    """
    df = con.execute(query, [season, player_id]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_player_receiving_season(player_id: str, season: int):
    """Statistiques de réception (cibles, yards, TD, EPA, air yards, YAC) d'un joueur sur une saison entière."""
    con = get_connection()
    query = """
        SELECT
            COUNT(*) FILTER (WHERE pass = 1) AS cibles,
            COUNT(*) FILTER (WHERE complete_pass = 1) AS receptions,
            SUM(receiving_yards) AS yards,
            COUNT(*) FILTER (WHERE complete_pass = 1 AND touchdown = 1) AS td,
            ROUND(AVG(epa) FILTER (WHERE pass = 1), 3) AS epa_per_play,
            ROUND(AVG(air_yards) FILTER (WHERE pass = 1), 1) AS air_yards_moy,
            ROUND(AVG(yards_after_catch) FILTER (WHERE complete_pass = 1), 1) AS yac_moy
        FROM plays
        WHERE season = ? AND receiver_player_id = ?
    """
    df = con.execute(query, [season, player_id]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_player_pressure_season(player_id: str, season: int):
    """Pression subie par un QB sur la saison : dropbacks pressés, sacks subis, taux de pression."""
    con = get_connection()
    query = """
        SELECT
            COUNT(*) FILTER (WHERE qb_dropback = 1) AS dropbacks,
            SUM(COALESCE(CAST(was_pressure AS DOUBLE), 0)) AS pressions_subies,
            SUM(CAST(sack AS DOUBLE)) AS sacks_subis,
            ROUND(
                SUM(COALESCE(CAST(was_pressure AS DOUBLE), 0)) * 1.0
                / NULLIF(COUNT(*) FILTER (WHERE qb_dropback = 1), 0),
                3
            ) AS taux_pression
        FROM plays
        WHERE season = ? AND passer_player_id = ?
    """
    df = con.execute(query, [season, player_id]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_player_defensive_season(player_id: str, season: int):
    """Statistiques défensives individuelles cumulées sur la saison (tacles, sacks, INT, passes défendues, fumbles forcés)."""
    con = get_connection()
    query = """
        SELECT
            COUNT(*) FILTER (WHERE solo_tackle_1_player_id = ? OR solo_tackle_2_player_id = ?) AS tacles_solo,
            COUNT(*) FILTER (WHERE assist_tackle_1_player_id = ? OR assist_tackle_2_player_id = ?
                              OR assist_tackle_3_player_id = ? OR assist_tackle_4_player_id = ?) AS tacles_assistes,
            COUNT(*) FILTER (WHERE tackle_for_loss_1_player_id = ? OR tackle_for_loss_2_player_id = ?) AS tacles_pour_perte,
            COUNT(*) FILTER (WHERE sack_player_id = ?) AS sacks_pleins,
            COUNT(*) FILTER (WHERE half_sack_1_player_id = ? OR half_sack_2_player_id = ?) AS demi_sacks,
            COUNT(*) FILTER (WHERE qb_hit_1_player_id = ? OR qb_hit_2_player_id = ?) AS pressions_qb,
            COUNT(*) FILTER (WHERE interception_player_id = ?) AS interceptions,
            COUNT(*) FILTER (WHERE pass_defense_1_player_id = ? OR pass_defense_2_player_id = ?) AS passes_defendues,
            COUNT(*) FILTER (WHERE forced_fumble_player_1_player_id = ? OR forced_fumble_player_2_player_id = ?) AS fumbles_forces
        FROM plays
        WHERE season = ?
    """
    params = [player_id] * 18 + [season]
    df = con.execute(query, params).fetchdf()
    if not df.empty:
        df["tacles_totaux"] = df["tacles_solo"] + df["tacles_assistes"]
        df["sacks_totaux"] = df["sacks_pleins"] + df["demi_sacks"] * 0.5
    return df

@st.cache_data(ttl=3600)
def get_player_season_epa(player_id: str, season: int, role: str):
    """EPA moyen d'un joueur sur la saison entière, pour un rôle donné (passing/rushing/receiving)."""
    colonne_id = {"passing": "passer_player_id", "rushing": "rusher_player_id", "receiving": "receiver_player_id"}[role]
    filtre = {"passing": "qb_dropback = 1", "rushing": "rush = 1", "receiving": "pass = 1"}[role]
    con = get_connection()
    query = f"""
        SELECT ROUND(AVG(epa), 3) AS epa_per_play
        FROM plays
        WHERE season = ? AND {colonne_id} = ? AND {filtre}
    """
    df = con.execute(query, [season, player_id]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_qb_full_rankings(season: int, min_dropbacks: int = 100):
    """Classement complet des QB qualifiés sur la saison — sert de base à
    get_rank_label pour chaque stat individuelle (tentatives, complétions,
    yards, TD, INT, EPA, CPOE, air yards, pression subie)."""
    con = get_connection()
    query = """
        SELECT passer_player_id AS player_id,
               COUNT(*) FILTER (WHERE pass = 1) AS tentatives,
               COUNT(*) FILTER (WHERE complete_pass = 1) AS completions,
               SUM(passing_yards) AS yards,
               COUNT(*) FILTER (WHERE complete_pass = 1 AND touchdown = 1) AS td,
               COUNT(*) FILTER (WHERE interception = 1) AS interceptions,
               ROUND(AVG(epa) FILTER (WHERE qb_dropback = 1), 3) AS epa_per_play,
               ROUND(AVG(cpoe) FILTER (WHERE pass = 1), 1) AS cpoe,
               ROUND(AVG(air_yards) FILTER (WHERE pass = 1), 1) AS air_yards_moy,
               SUM(COALESCE(CAST(was_pressure AS DOUBLE), 0)) FILTER (WHERE qb_dropback = 1) AS pressions_subies,
               SUM(CAST(sack AS DOUBLE)) AS sacks_subis,
               ROUND(
                   SUM(COALESCE(CAST(was_pressure AS DOUBLE), 0)) FILTER (WHERE qb_dropback = 1) * 1.0
                   / NULLIF(COUNT(*) FILTER (WHERE qb_dropback = 1), 0),
                   3
               ) AS taux_pression
        FROM plays
        WHERE season = ? AND passer_player_id IS NOT NULL
        GROUP BY passer_player_id
        HAVING COUNT(*) FILTER (WHERE qb_dropback = 1) >= ?
    """
    df = con.execute(query, [season, min_dropbacks]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_rb_full_rankings(season: int, min_carries: int = 50):
    """Classement complet des RB qualifiés sur la saison — sert de base à
    get_rank_label (yards, TD, EPA)."""
    con = get_connection()
    query = """
        SELECT rusher_player_id AS player_id,
               COUNT(*) FILTER (WHERE rush = 1) AS courses,
               SUM(rushing_yards) AS yards,
               COUNT(*) FILTER (WHERE rush = 1 AND touchdown = 1) AS td,
               ROUND(AVG(epa) FILTER (WHERE rush = 1), 3) AS epa_per_play
        FROM plays
        WHERE season = ? AND rusher_player_id IS NOT NULL
        GROUP BY rusher_player_id
        HAVING COUNT(*) FILTER (WHERE rush = 1) >= ?
    """
    df = con.execute(query, [season, min_carries]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_wr_full_rankings(season: int, min_targets: int = 30):
    """Classement complet des receveurs qualifiés sur la saison — sert de
    base à get_rank_label (cibles, réceptions, yards, TD, EPA, air yards, YAC)."""
    con = get_connection()
    query = """
        SELECT receiver_player_id AS player_id,
               COUNT(*) FILTER (WHERE pass = 1) AS cibles,
               COUNT(*) FILTER (WHERE complete_pass = 1) AS receptions,
               SUM(receiving_yards) AS yards,
               COUNT(*) FILTER (WHERE complete_pass = 1 AND touchdown = 1) AS td,
               ROUND(AVG(epa) FILTER (WHERE pass = 1), 3) AS epa_per_play,
               ROUND(AVG(air_yards) FILTER (WHERE pass = 1), 1) AS air_yards_moy,
               ROUND(AVG(yards_after_catch) FILTER (WHERE complete_pass = 1), 1) AS yac_moy
        FROM plays
        WHERE season = ? AND receiver_player_id IS NOT NULL
        GROUP BY receiver_player_id
        HAVING COUNT(*) FILTER (WHERE pass = 1) >= ?
    """
    df = con.execute(query, [season, min_targets]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_def_full_rankings(season: int, min_actions: int = 10):
    """Classement complet des défenseurs qualifiés sur la saison — sert de
    base à get_rank_label (tacles, tacles pour perte, sacks, pressions,
    INT, passes défendues, fumbles forcés). Généralisation à toute la ligue
    de get_player_defensive_season.

    Contrairement aux autres classements, il n'y a pas UNE colonne
    'defender_player_id' dans plays : chaque type d'action défensive vit
    dans sa propre colonne (solo_tackle_1_player_id, sack_player_id,
    interception_player_id, ...). On empile (UNION ALL) chaque colonne
    comme une ligne 'ce joueur a fait cette action', puis on regroupe par
    joueur — même schéma dénormalisé que get_player_defensive_season, mais
    tous les joueurs à la fois plutôt qu'un seul passé en paramètre."""
    con = get_connection()
    # (colonne source, catégorie, poids) — demi-sack compte pour 0.5, comme
    # get_player_defensive_season (sacks_pleins + demi_sacks * 0.5).
    colonnes = [
        ("solo_tackle_1_player_id", "tacles", 1), ("solo_tackle_2_player_id", "tacles", 1),
        ("assist_tackle_1_player_id", "tacles", 1), ("assist_tackle_2_player_id", "tacles", 1),
        ("assist_tackle_3_player_id", "tacles", 1), ("assist_tackle_4_player_id", "tacles", 1),
        ("tackle_for_loss_1_player_id", "tfl", 1), ("tackle_for_loss_2_player_id", "tfl", 1),
        ("sack_player_id", "sacks", 1),
        ("half_sack_1_player_id", "sacks", 0.5), ("half_sack_2_player_id", "sacks", 0.5),
        ("qb_hit_1_player_id", "pressions", 1), ("qb_hit_2_player_id", "pressions", 1),
        ("interception_player_id", "interceptions", 1),
        ("pass_defense_1_player_id", "pd", 1), ("pass_defense_2_player_id", "pd", 1),
        ("forced_fumble_player_1_player_id", "ff", 1), ("forced_fumble_player_2_player_id", "ff", 1),
    ]
    branches = " UNION ALL ".join(
        f"SELECT {col} AS player_id, '{cat}' AS categorie, {poids} AS poids "
        f"FROM plays WHERE season = ? AND {col} IS NOT NULL"
        for col, cat, poids in colonnes
    )
    query = f"""
        WITH actions AS ({branches})
        SELECT player_id,
               SUM(poids) FILTER (WHERE categorie = 'tacles') AS tacles_totaux,
               SUM(poids) FILTER (WHERE categorie = 'tfl') AS tacles_pour_perte,
               SUM(poids) FILTER (WHERE categorie = 'sacks') AS sacks_totaux,
               SUM(poids) FILTER (WHERE categorie = 'pressions') AS pressions_qb,
               SUM(poids) FILTER (WHERE categorie = 'interceptions') AS interceptions,
               SUM(poids) FILTER (WHERE categorie = 'pd') AS passes_defendues,
               SUM(poids) FILTER (WHERE categorie = 'ff') AS fumbles_forces,
               SUM(poids) AS volume_total
        FROM actions
        GROUP BY player_id
        HAVING SUM(poids) >= ?
    """
    params = [season] * len(colonnes) + [min_actions]
    df = con.execute(query, params).fetchdf()
    for col in ["tacles_totaux", "tacles_pour_perte", "sacks_totaux", "pressions_qb",
                "interceptions", "passes_defendues", "fumbles_forces"]:
        df[col] = df[col].fillna(0)
    return df

@st.cache_data(ttl=3600)
def get_rank_label(df_rankings, player_id: str, metric_col: str, ascending: bool = False):
    """Retourne '#3 / 24' si le joueur est qualifié pour ce classement,
    None sinon (échantillon trop petit ou stat non applicable).
    ascending=True pour les stats où moins vaut mieux (ex. interceptions
    lancées par un QB) — sinon le meilleur joueur serait classé dernier."""
    if df_rankings.empty or player_id not in df_rankings["player_id"].values:
        return None
    df_sorted = df_rankings.sort_values(metric_col, ascending=ascending).reset_index(drop=True)
    idx = df_sorted[df_sorted["player_id"] == player_id].index
    if len(idx) == 0:
        return None
    rang = idx[0] + 1
    total = len(df_sorted)
    return f"#{rang} / {total}"


# ──────────────────────────────────────────────────────────────────────────────
# PLAYERS — TENDANCES HEBDOMADAIRES
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_player_weekly_trend(player_id: str, season: int, role: str):
    """role : 'passing', 'rushing' ou 'receiving' — détermine la colonne
    d'identifiant et le filtre de type de jeu à utiliser."""
    con = get_connection()
    colonne_id = {
        "passing": "passer_player_id",
        "rushing": "rusher_player_id",
        "receiving": "receiver_player_id",
    }[role]
    filtre_type = {
        "passing": "qb_dropback = 1",
        "rushing": "rush = 1",
        "receiving": "pass = 1",
    }[role]
    query = f"""
        SELECT week, ROUND(AVG(epa), 3) AS epa_per_play, COUNT(*) AS volume
        FROM plays
        WHERE season = ? AND {colonne_id} = ? AND {filtre_type}
        GROUP BY week
        ORDER BY week
    """
    df = con.execute(query, [season, player_id]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_player_defensive_weekly_trend(player_id: str, season: int):
    """Volume défensif hebdomadaire (tacles + sacks + PD + FF + INT) —
    l'EPA n'est pas attribuable à un défenseur individuel dans nflverse
    (crédité au niveau de l'équipe défensive, pas du joueur), donc on suit
    un indicateur de volume plutôt qu'une métrique EPA ici."""
    con = get_connection()
    query = """
        SELECT week,
            COUNT(*) FILTER (WHERE solo_tackle_1_player_id = ? OR solo_tackle_2_player_id = ?
                              OR assist_tackle_1_player_id = ? OR assist_tackle_2_player_id = ?
                              OR assist_tackle_3_player_id = ? OR assist_tackle_4_player_id = ?
                              OR sack_player_id = ? OR half_sack_1_player_id = ? OR half_sack_2_player_id = ?
                              OR interception_player_id = ?
                              OR pass_defense_1_player_id = ? OR pass_defense_2_player_id = ?
                              OR forced_fumble_player_1_player_id = ? OR forced_fumble_player_2_player_id = ?
                             ) AS volume_defensif
        FROM plays
        WHERE season = ?
        GROUP BY week
        ORDER BY week
    """
    params = [player_id] * 14 + [season]
    df = con.execute(query, params).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_player_epa_rank_week(season: int, week: int, role: str, min_plays: int = 5):
    """Classement EPA de tous les joueurs qualifiés à un rôle donné, pour une semaine précise."""
    con = get_connection()
    colonne_id = {"passing": "passer_player_id", "rushing": "rusher_player_id", "receiving": "receiver_player_id"}[role]
    nom_col = {"passing": "passer_player_name", "rushing": "rusher_player_name", "receiving": "receiver_player_name"}[role]
    filtre = {"passing": "qb_dropback = 1", "rushing": "rush = 1", "receiving": "pass = 1"}[role]
    query = f"""
        SELECT {colonne_id} AS player_id, ANY_VALUE({nom_col}) AS player, ANY_VALUE(posteam) AS team,
               ROUND(AVG(epa), 3) AS epa_per_play, COUNT(*) AS volume
        FROM plays
        WHERE season = ? AND week = ? AND {filtre} AND {colonne_id} IS NOT NULL
        GROUP BY {colonne_id}
        HAVING COUNT(*) >= ?
    """
    df = con.execute(query, [season, week, min_plays]).fetchdf()
    if df.empty:
        return df
    df = df.sort_values(["epa_per_play", "player_id"], ascending=[False, True]).reset_index(drop=True)
    df["rank"] = df.index + 1
    return df

@st.cache_data(ttl=3600)
def get_player_weekly_movement(season: int, week: int, role: str, min_plays: int = 5):
    """Classement EPA hebdomadaire d'un joueur avec évolution de rang vs la semaine précédente."""
    current = get_player_epa_rank_week(season, week, role, min_plays)
    if current.empty:
        return current
    prev_map = {}
    if week > 1:
        previous = get_player_epa_rank_week(season, week - 1, role, min_plays)
        if not previous.empty:
            prev_map = dict(zip(previous["player_id"], previous["rank"]))
    current["rank_precedent"] = current["player_id"].map(prev_map)
    current["evolution"] = current["rank_precedent"] - current["rank"]
    return current

@st.cache_data(ttl=3600)
def get_player_epa_cumulative_through_week(player_id: str, season: int, week: int, role: str):
    """EPA moyen d'un joueur du début de saison jusqu'à une semaine donnée incluse (pas la saison complète)."""
    colonne_id = {"passing": "passer_player_id", "rushing": "rusher_player_id", "receiving": "receiver_player_id"}[role]
    filtre = {"passing": "qb_dropback = 1", "rushing": "rush = 1", "receiving": "pass = 1"}[role]
    con = get_connection()
    query = f"""
        SELECT ROUND(AVG(epa), 3) AS epa_per_play
        FROM plays
        WHERE season = ? AND week <= ? AND {colonne_id} = ? AND {filtre}
    """
    df = con.execute(query, [season, week, player_id]).fetchdf()
    return df


# ──────────────────────────────────────────────────────────────────────────────
# GAMES
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_games_for_week(season: int, week: int):
    """Liste des matchs programmés pour une saison et une semaine données."""
    con = get_connection()
    query = """
        SELECT game_id, week, gameday, home_team, away_team, home_score, away_score
        FROM games
        WHERE season = ? AND week = ?
        ORDER BY gameday
    """
    df = con.execute(query, [season, week]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_game_info(game_id: str):
    """Informations générales d'un match : score, stade, surface, météo, prolongation."""
    con = get_connection()
    query = """
        SELECT season, week, gameday, home_team, away_team, home_score, away_score,
               roof, surface, temp, wind, stadium, home_coach, away_coach, overtime
        FROM games WHERE game_id = ?
    """
    df = con.execute(query, [game_id]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_game_win_probability(game_id: str):
    """Win probability du point de vue de l'équipe à domicile, reconstruite
    depuis wp (probabilité de l'équipe en possession) selon qui a le ballon."""
    con = get_connection()
    query = """
        SELECT play_id,
               CASE WHEN posteam = home_team THEN wp ELSE 1 - wp END AS home_wp
        FROM plays
        WHERE game_id = ? AND wp IS NOT NULL
        ORDER BY play_id
    """
    df = con.execute(query, [game_id]).fetchdf()
    df["progression"] = range(1, len(df) + 1)
    return df

@st.cache_data(ttl=3600)
def get_game_epa_cumulative(game_id: str):
    """EPA cumulé de chaque équipe au fil du match, jeu après jeu — sert au graphique de momentum."""
    con = get_connection()
    query = """
        SELECT play_id, posteam,
               SUM(epa) OVER (PARTITION BY posteam ORDER BY play_id) AS epa_cumule
        FROM plays
        WHERE game_id = ? AND posteam IS NOT NULL AND epa IS NOT NULL
        ORDER BY play_id
    """
    df = con.execute(query, [game_id]).fetchdf()
    df["progression"] = df.groupby("posteam").cumcount() + 1
    return df

@st.cache_data(ttl=3600)
def get_game_score_progression(game_id: str):
    """Écart de score du point de vue de l'équipe à domicile, reconstruit
    depuis score_differential (qui est du point de vue de l'équipe en
    possession, donc inversé quand c'est l'équipe visiteuse qui l'a)."""
    con = get_connection()
    query = """
        SELECT play_id,
               CASE WHEN posteam = home_team THEN score_differential ELSE -score_differential END AS ecart_domicile
        FROM plays
        WHERE game_id = ? AND score_differential IS NOT NULL
        ORDER BY play_id
    """
    df = con.execute(query, [game_id]).fetchdf()
    df["progression"] = range(1, len(df) + 1)
    return df

@st.cache_data(ttl=3600)
def get_game_drives(game_id: str):
    """Résumé des drives d'un match : résultat, position de départ, possession, score marqué."""
    con = get_connection()
    query = """
        WITH bounds AS (
            SELECT drive, ANY_VALUE(posteam) AS team,
                   MAX(drive_play_count) AS plays,
                   ANY_VALUE(fixed_drive_result) AS resultat,
                   ANY_VALUE(drive_start_yard_line) AS depart,
                   ANY_VALUE(drive_time_of_possession) AS possession,
                   MIN(play_id) AS first_play_id,
                   MAX(play_id) AS last_play_id
            FROM plays
            WHERE game_id = ? AND drive IS NOT NULL
            GROUP BY drive
        )
        SELECT b.drive, b.team, b.plays, b.resultat, b.depart, b.possession,
               p_start.total_home_score AS home_avant, p_start.total_away_score AS away_avant,
               p_end.total_home_score AS score_domicile, p_end.total_away_score AS score_exterieur
        FROM bounds b
        JOIN plays p_start ON p_start.game_id = ? AND p_start.play_id = b.first_play_id
        JOIN plays p_end ON p_end.game_id = ? AND p_end.play_id = b.last_play_id
        ORDER BY b.drive
    """
    df = con.execute(query, [game_id, game_id, game_id]).fetchdf()

    if not df.empty:
        # Points marqués sur ce drive = variation du total de points (les deux
        # équipes confondues) entre le début et la fin du drive — fonctionne
        # même en cas de score défensif (pick-six, etc.).
        df["points_marques"] = (
            (df["score_domicile"] + df["score_exterieur"])
            - (df["home_avant"] + df["away_avant"])
        ).fillna(0).astype(int)
        df["plays"] = df["plays"].fillna(0).astype(int)
        df["score_domicile"] = df["score_domicile"].fillna(0).astype(int)
        df["score_exterieur"] = df["score_exterieur"].fillna(0).astype(int)
        df = df.drop(columns=["home_avant", "away_avant"])

    return df

@st.cache_data(ttl=3600)
def get_game_top_performer(game_id: str, team: str, season: int, role: str):
    """role : 'passing', 'rushing' ou 'receiving'."""
    con = get_connection()
    colonnes = {
        "passing": ("passer_player_name", "passer_player_id", "passing_yards", "qb_dropback = 1", "QB"),
        "rushing": ("rusher_player_name", "rusher_player_id", "rushing_yards", "rush = 1", "RB"),
        "receiving": ("receiver_player_name", "receiver_player_id", "receiving_yards", "pass = 1", "REC"),
    }
    nom_col, id_col, yards_col, filtre, poste_defaut = colonnes[role]
    query = f"""
        SELECT p.{nom_col} AS player, ANY_VALUE(p.{id_col}) AS player_id,
               SUM(p.{yards_col}) AS yards, ROUND(AVG(p.epa), 3) AS epa_per_play,
               ANY_VALUE(r.headshot_url) AS photo_url,
               COALESCE(ANY_VALUE(r.position), '{poste_defaut}') AS position
        FROM plays p
        LEFT JOIN rosters r ON p.{id_col} = r.player_id AND r.season = ?
        WHERE p.game_id = ? AND p.posteam = ? AND p.{filtre} AND p.{id_col} IS NOT NULL
        GROUP BY p.{nom_col}
        ORDER BY yards DESC
        LIMIT 1
    """
    df = con.execute(query, [season, game_id, team]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_game_play_by_play(game_id: str, quarter: int | None = None):
    """Play-by-play textuel d'un match, avec filtre optionnel par quart-temps."""
    con = get_connection()
    if quarter:
        query = """
            SELECT qtr, down, ydstogo, yardline_100, "desc", ROUND(epa, 3) AS epa, posteam
            FROM plays
            WHERE game_id = ? AND "desc" IS NOT NULL AND qtr = ?
            ORDER BY play_id
        """
        df = con.execute(query, [game_id, quarter]).fetchdf()
    else:
        query = """
            SELECT qtr, down, ydstogo, yardline_100, "desc", ROUND(epa, 3) AS epa, posteam
            FROM plays
            WHERE game_id = ? AND "desc" IS NOT NULL
            ORDER BY play_id
        """
        df = con.execute(query, [game_id]).fetchdf()
    return df


# ──────────────────────────────────────────────────────────────────────────────
# CLASSEMENTS SAISON COMPLÈTE (Rankings > onglet Saison, Home)
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_top_qb_season_yards(season: int, min_dropbacks: int = 100):
    """Top 3 QB de la ligue sur une saison, classés par yards lancés."""
    con = get_connection()
    query = """
        SELECT p.passer_player_name AS player, p.posteam AS team,
               ANY_VALUE(p.passer_player_id) AS player_id,
               SUM(p.passing_yards) AS yards, COUNT(*) AS dropbacks,
               ANY_VALUE(r.headshot_url) AS photo_url
        FROM plays p
        LEFT JOIN rosters r ON p.passer_player_id = r.player_id AND r.season = p.season
        WHERE p.season = ? AND p.qb_dropback = 1 AND p.passer_player_id IS NOT NULL
        GROUP BY p.passer_player_name, p.posteam
        HAVING COUNT(*) >= ?
        ORDER BY yards DESC
        LIMIT 3
    """
    df = con.execute(query, [season, min_dropbacks]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_top_rb_season_yards(season: int, min_carries: int = 50):
    """Top 3 RB de la ligue sur une saison, classés par yards parcourus."""
    con = get_connection()
    query = """
        SELECT p.rusher_player_name AS player, p.posteam AS team,
               ANY_VALUE(p.rusher_player_id) AS player_id,
               SUM(p.rushing_yards) AS yards, COUNT(*) AS carries,
               ANY_VALUE(r.headshot_url) AS photo_url
        FROM plays p
        LEFT JOIN rosters r ON p.rusher_player_id = r.player_id AND r.season = p.season
        WHERE p.season = ? AND p.rush = 1 AND p.rusher_player_id IS NOT NULL
        GROUP BY p.rusher_player_name, p.posteam
        HAVING COUNT(*) >= ?
        ORDER BY yards DESC
        LIMIT 3
    """
    df = con.execute(query, [season, min_carries]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_top_wr_season_yards(season: int, min_targets: int = 30):
    """Top 3 receveurs de la ligue sur une saison, classés par yards attrapés."""
    con = get_connection()
    query = """
        SELECT p.receiver_player_name AS player, p.posteam AS team,
               ANY_VALUE(p.receiver_player_id) AS player_id,
               SUM(p.receiving_yards) AS yards, COUNT(*) AS targets,
               ANY_VALUE(r.headshot_url) AS photo_url
        FROM plays p
        LEFT JOIN rosters r ON p.receiver_player_id = r.player_id AND r.season = p.season
        WHERE p.season = ? AND p.pass = 1 AND p.receiver_player_id IS NOT NULL
        GROUP BY p.receiver_player_name, p.posteam
        HAVING COUNT(*) >= ?
        ORDER BY yards DESC
        LIMIT 3
    """
    df = con.execute(query, [season, min_targets]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_top_teams_offense_yards_season(season: int):
    """Top 3 équipes de la ligue sur une saison, classées par total de yards offensifs."""
    con = get_connection()
    query = """
        SELECT posteam AS team, SUM(yards_gained) AS yards, COUNT(*) AS plays
        FROM plays
        WHERE season = ? AND play_type IN ('pass', 'run') AND posteam IS NOT NULL
        GROUP BY posteam
        ORDER BY yards DESC
        LIMIT 3
    """
    df = con.execute(query, [season]).fetchdf()
    return df


# ─────────────────────────────────────────────────────────────
# Requêtes annuelles (Annual Recap) — EPA sur la saison entière
# ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_top_qb_season_epa(season: int, min_dropbacks: int = 100):
    """Top 3 QB de la ligue sur une saison, classés par EPA/dropback."""
    con = get_connection()
    query = """
        SELECT p.passer_player_name AS player, p.posteam AS team,
               ANY_VALUE(p.passer_player_id) AS player_id,
               ROUND(AVG(p.epa), 3) AS epa_per_play, COUNT(*) AS dropbacks,
               ANY_VALUE(r.headshot_url) AS photo_url
        FROM plays p
        LEFT JOIN rosters r ON p.passer_player_id = r.player_id AND r.season = p.season
        WHERE p.season = ? AND p.qb_dropback = 1 AND p.passer_player_id IS NOT NULL
        GROUP BY p.passer_player_name, p.posteam
        HAVING COUNT(*) >= ?
        ORDER BY epa_per_play DESC
        LIMIT 3
    """
    df = con.execute(query, [season, min_dropbacks]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_top_rb_season_epa(season: int, min_carries: int = 50):
    """Top 3 RB de la ligue sur une saison, classés par EPA/course."""
    con = get_connection()
    query = """
        SELECT p.rusher_player_name AS player, p.posteam AS team,
               ANY_VALUE(p.rusher_player_id) AS player_id,
               ROUND(AVG(p.epa), 3) AS epa_per_play, COUNT(*) AS carries,
               ANY_VALUE(r.headshot_url) AS photo_url
        FROM plays p
        LEFT JOIN rosters r ON p.rusher_player_id = r.player_id AND r.season = p.season
        WHERE p.season = ? AND p.rush = 1 AND p.rusher_player_id IS NOT NULL
        GROUP BY p.rusher_player_name, p.posteam
        HAVING COUNT(*) >= ?
        ORDER BY epa_per_play DESC
        LIMIT 3
    """
    df = con.execute(query, [season, min_carries]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_top_wr_season_epa(season: int, min_targets: int = 30):
    """Top 3 receveurs de la ligue sur une saison, classés par EPA/cible."""
    con = get_connection()
    query = """
        SELECT p.receiver_player_name AS player, p.posteam AS team,
               ANY_VALUE(p.receiver_player_id) AS player_id,
               ROUND(AVG(p.epa), 3) AS epa_per_play, COUNT(*) AS targets,
               ANY_VALUE(r.headshot_url) AS photo_url
        FROM plays p
        LEFT JOIN rosters r ON p.receiver_player_id = r.player_id AND r.season = p.season
        WHERE p.season = ? AND p.pass = 1 AND p.receiver_player_id IS NOT NULL
        GROUP BY p.receiver_player_name, p.posteam
        HAVING COUNT(*) >= ?
        ORDER BY epa_per_play DESC
        LIMIT 3
    """
    df = con.execute(query, [season, min_targets]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_passing_leaderboard_season(season: int, min_attempts: int = 50):
    """Tableau complet des passeurs de la ligue sur une saison — colonnes
    façon site de stats NFL classique (tentatives, complétions, TD, INT,
    passer rating, sacks encaissés...), pas un top 3. Utilisé sur
    Analytics > Joueurs > Passe."""
    con = get_connection()
    query = """
        WITH base AS (
            SELECT
                p.passer_player_name AS player, p.posteam AS team,
                ANY_VALUE(p.passer_player_id) AS player_id,
                ANY_VALUE(r.headshot_url) AS photo_url,
                SUM(p.passing_yards) AS pass_yds,
                COUNT(*) AS att,
                SUM(p.complete_pass) AS cmp,
                SUM(p.touchdown) AS td,
                SUM(p.interception) AS interceptions,
                SUM(p.first_down) AS first_downs,
                SUM(CASE WHEN p.passing_yards >= 20 THEN 1 ELSE 0 END) AS twenty_plus,
                SUM(CASE WHEN p.passing_yards >= 40 THEN 1 ELSE 0 END) AS forty_plus,
                MAX(p.passing_yards) AS lng
            FROM plays p
            LEFT JOIN rosters r ON p.passer_player_id = r.player_id AND r.season = p.season
            WHERE p.season = ? AND p.pass = 1 AND p.passer_player_id IS NOT NULL
            GROUP BY p.passer_player_name, p.posteam
            HAVING COUNT(*) >= ?
        ),
        sacks AS (
            SELECT passer_player_id, COUNT(*) AS sck, SUM(-yards_gained) AS scky
            FROM plays
            WHERE season = ? AND sack = 1
            GROUP BY passer_player_id
        )
        SELECT b.*, COALESCE(s.sck, 0) AS sck, COALESCE(s.scky, 0) AS scky
        FROM base b
        LEFT JOIN sacks s ON b.player_id = s.passer_player_id
        ORDER BY b.pass_yds DESC
    """
    df = con.execute(query, [season, min_attempts, season]).fetchdf()
    if df.empty:
        return df

    # Yds/Att, Cmp%, 1st% et le passer rating (formule NFL officielle à 4
    # composantes, chacune plafonnée entre 0 et 2.375) sont dérivés ici en
    # pandas plutôt qu'en SQL — bien plus lisible que l'équivalent en CASE/
    # LEAST/GREATEST imbriqués.
    df["yds_att"] = (df["pass_yds"] / df["att"]).round(1)
    df["cmp_pct"] = (df["cmp"] / df["att"] * 100).round(1)
    df["first_pct"] = (df["first_downs"] / df["att"] * 100).round(1)

    a = (((df["cmp"] / df["att"]) - 0.3) * 5).clip(0, 2.375)
    b = (((df["pass_yds"] / df["att"]) - 3) * 0.25).clip(0, 2.375)
    c = ((df["td"] / df["att"]) * 20).clip(0, 2.375)
    d = (2.375 - ((df["interceptions"] / df["att"]) * 25)).clip(0, 2.375)
    df["rate"] = (((a + b + c + d) / 6) * 100).round(1)

    df = df.rename(columns={
        "player": "Player", "pass_yds": "Yds Passe", "yds_att": "Yds/Att", "att": "Att",
        "cmp": "Cmp", "cmp_pct": "Cmp%", "td": "TD", "interceptions": "INT", "rate": "Rate",
        "first_downs": "1st", "first_pct": "1st%", "twenty_plus": "20+",
        "forty_plus": "40+", "lng": "Lng", "sck": "Sck", "scky": "SckY",
    })
    colonnes = ["player_id", "photo_url", "Player", "team", "Yds Passe", "Yds/Att", "Att", "Cmp",
                "Cmp%", "TD", "INT", "Rate", "1st", "1st%", "20+", "40+", "Lng", "Sck", "SckY"]
    return df[colonnes]

@st.cache_data(ttl=3600)
def get_rushing_leaderboard_season(season: int, min_attempts: int = 30):
    """Tableau complet des coureurs de la ligue sur une saison. Utilisé sur
    Analytics > Joueurs > Course."""
    con = get_connection()
    query = """
        SELECT
            p.rusher_player_name AS player, p.posteam AS team,
            ANY_VALUE(p.rusher_player_id) AS player_id,
            ANY_VALUE(r.headshot_url) AS photo_url,
            SUM(p.rushing_yards) AS rush_yds,
            COUNT(*) AS att,
            SUM(p.touchdown) AS td,
            SUM(CASE WHEN p.rushing_yards >= 20 THEN 1 ELSE 0 END) AS twenty_plus,
            SUM(CASE WHEN p.rushing_yards >= 40 THEN 1 ELSE 0 END) AS forty_plus,
            MAX(p.rushing_yards) AS lng,
            SUM(p.first_down) AS first_downs,
            SUM(p.fumble) AS fum
        FROM plays p
        LEFT JOIN rosters r ON p.rusher_player_id = r.player_id AND r.season = p.season
        WHERE p.season = ? AND p.rush = 1 AND p.rusher_player_id IS NOT NULL
        GROUP BY p.rusher_player_name, p.posteam
        HAVING COUNT(*) >= ?
        ORDER BY rush_yds DESC
    """
    df = con.execute(query, [season, min_attempts]).fetchdf()
    if df.empty:
        return df

    df["first_pct"] = (df["first_downs"] / df["att"] * 100).round(1)
    df = df.rename(columns={
        "player": "Player", "rush_yds": "Yds Course", "att": "Att", "td": "TD",
        "twenty_plus": "20+", "forty_plus": "40+", "lng": "Lng",
        "first_downs": "Rush 1st", "first_pct": "Rush 1st%", "fum": "Rush FUM",
    })
    colonnes = ["player_id", "photo_url", "Player", "team", "Yds Course", "Att", "TD", "20+",
                "40+", "Lng", "Rush 1st", "Rush 1st%", "Rush FUM"]
    return df[colonnes]

@st.cache_data(ttl=3600)
def get_receiving_leaderboard_season(season: int, min_targets: int = 20):
    """Tableau complet des receveurs de la ligue sur une saison. Utilisé sur
    Analytics > Joueurs > Réception."""
    con = get_connection()
    query = """
        SELECT
            p.receiver_player_name AS player, p.posteam AS team,
            ANY_VALUE(p.receiver_player_id) AS player_id,
            ANY_VALUE(r.headshot_url) AS photo_url,
            SUM(p.complete_pass) AS rec,
            SUM(p.receiving_yards) AS yds,
            SUM(p.touchdown) AS td,
            SUM(CASE WHEN p.receiving_yards >= 20 THEN 1 ELSE 0 END) AS twenty_plus,
            SUM(CASE WHEN p.receiving_yards >= 40 THEN 1 ELSE 0 END) AS forty_plus,
            MAX(p.receiving_yards) AS lng,
            SUM(p.first_down) AS first_downs,
            SUM(CASE WHEN p.complete_pass = 1 THEN p.fumble ELSE 0 END) AS fum,
            SUM(CASE WHEN p.complete_pass = 1 THEN p.yards_after_catch ELSE 0 END) AS yac_total,
            COUNT(*) AS tgts
        FROM plays p
        LEFT JOIN rosters r ON p.receiver_player_id = r.player_id AND r.season = p.season
        WHERE p.season = ? AND p.pass = 1 AND p.receiver_player_id IS NOT NULL
        GROUP BY p.receiver_player_name, p.posteam
        HAVING COUNT(*) >= ?
        ORDER BY yds DESC
    """
    df = con.execute(query, [season, min_targets]).fetchdf()
    if df.empty:
        return df

    rec_sans_zero = df["rec"].replace(0, pd.NA)
    df["first_pct"] = (df["first_downs"] / rec_sans_zero * 100).round(1)
    df["yac_r"] = (df["yac_total"] / rec_sans_zero).round(1)
    df = df.rename(columns={
        "player": "Player", "rec": "Rec", "yds": "Yds", "td": "TD",
        "twenty_plus": "20+", "forty_plus": "40+", "lng": "LNG",
        "first_downs": "Rec 1st", "first_pct": "1st%", "fum": "Rec FUM",
        "yac_r": "Rec YAC/R", "tgts": "Cibles",
    })
    colonnes = ["player_id", "photo_url", "Player", "team", "Rec", "Yds", "TD", "20+", "40+",
                "LNG", "Rec 1st", "1st%", "Rec FUM", "Rec YAC/R", "Cibles"]
    return df[colonnes]

@st.cache_data(ttl=3600)
def get_passing_leaderboard_epa_season(season: int, min_dropbacks: int = 100):
    """Version EPA du leaderboard passeurs — mêmes joueurs que
    get_passing_leaderboard_season, mais colonnes EPA/dropback, CPOE, air
    yards et pression subie plutôt que yards/TD/rate. Généralisation à toute
    la ligue de get_player_passing_season + get_player_pressure_season.
    Utilisé sur Analytics > Advanced Analytics PRO > Joueurs > Passe."""
    con = get_connection()
    query = """
        SELECT
            p.passer_player_name AS player, p.posteam AS team,
            ANY_VALUE(p.passer_player_id) AS player_id,
            ANY_VALUE(r.headshot_url) AS photo_url,
            COUNT(*) FILTER (WHERE p.qb_dropback = 1) AS dropbacks,
            ROUND(AVG(p.epa) FILTER (WHERE p.qb_dropback = 1), 3) AS epa_per_play,
            ROUND(AVG(p.cpoe) FILTER (WHERE p.pass = 1), 1) AS cpoe,
            ROUND(AVG(p.air_yards) FILTER (WHERE p.pass = 1), 1) AS air_yards_moy,
            SUM(COALESCE(CAST(p.was_pressure AS DOUBLE), 0)) FILTER (WHERE p.qb_dropback = 1) AS pressions_subies,
            SUM(CAST(p.sack AS DOUBLE)) AS sacks_subis
        FROM plays p
        LEFT JOIN rosters r ON p.passer_player_id = r.player_id AND r.season = p.season
        WHERE p.season = ? AND p.passer_player_id IS NOT NULL
        GROUP BY p.passer_player_name, p.posteam
        HAVING COUNT(*) FILTER (WHERE p.qb_dropback = 1) >= ?
        ORDER BY epa_per_play DESC
    """
    df = con.execute(query, [season, min_dropbacks]).fetchdf()
    if df.empty:
        return df

    df["taux_pression"] = (df["pressions_subies"] / df["dropbacks"]).round(3)
    df = df.rename(columns={
        "player": "Player", "dropbacks": "Dropbacks", "epa_per_play": "EPA/Dropback",
        "cpoe": "CPOE", "air_yards_moy": "Air Yds Moy.", "pressions_subies": "Pressions subies",
        "taux_pression": "Taux pression", "sacks_subis": "Sacks subis",
    })
    colonnes = ["player_id", "photo_url", "Player", "team", "EPA/Dropback", "CPOE",
                "Air Yds Moy.", "Dropbacks", "Pressions subies", "Taux pression", "Sacks subis"]
    return df[colonnes]

@st.cache_data(ttl=3600)
def get_rushing_leaderboard_epa_season(season: int, min_attempts: int = 30):
    """Version EPA du leaderboard coureurs. Généralisation à toute la ligue
    de get_player_rushing_season. Utilisé sur Analytics > Advanced Analytics
    PRO > Joueurs > Course."""
    con = get_connection()
    query = """
        SELECT
            p.rusher_player_name AS player, p.posteam AS team,
            ANY_VALUE(p.rusher_player_id) AS player_id,
            ANY_VALUE(r.headshot_url) AS photo_url,
            COUNT(*) FILTER (WHERE p.rush = 1) AS courses,
            SUM(p.rushing_yards) AS yards,
            ROUND(AVG(p.epa) FILTER (WHERE p.rush = 1), 3) AS epa_per_play
        FROM plays p
        LEFT JOIN rosters r ON p.rusher_player_id = r.player_id AND r.season = p.season
        WHERE p.season = ? AND p.rusher_player_id IS NOT NULL
        GROUP BY p.rusher_player_name, p.posteam
        HAVING COUNT(*) FILTER (WHERE p.rush = 1) >= ?
        ORDER BY epa_per_play DESC
    """
    df = con.execute(query, [season, min_attempts]).fetchdf()
    if df.empty:
        return df

    df = df.rename(columns={
        "player": "Player", "courses": "Att", "yards": "Yds Course", "epa_per_play": "EPA/Course",
    })
    colonnes = ["player_id", "photo_url", "Player", "team", "EPA/Course", "Att", "Yds Course"]
    return df[colonnes]

@st.cache_data(ttl=3600)
def get_receiving_leaderboard_epa_season(season: int, min_targets: int = 20):
    """Version EPA du leaderboard receveurs. Généralisation à toute la ligue
    de get_player_receiving_season. Utilisé sur Analytics > Advanced
    Analytics PRO > Joueurs > Réception."""
    con = get_connection()
    query = """
        SELECT
            p.receiver_player_name AS player, p.posteam AS team,
            ANY_VALUE(p.receiver_player_id) AS player_id,
            ANY_VALUE(r.headshot_url) AS photo_url,
            COUNT(*) FILTER (WHERE p.pass = 1) AS cibles,
            COUNT(*) FILTER (WHERE p.complete_pass = 1) AS receptions,
            SUM(p.receiving_yards) AS yards,
            ROUND(AVG(p.epa) FILTER (WHERE p.pass = 1), 3) AS epa_per_play,
            ROUND(AVG(p.air_yards) FILTER (WHERE p.pass = 1), 1) AS air_yards_moy,
            ROUND(AVG(p.yards_after_catch) FILTER (WHERE p.complete_pass = 1), 1) AS yac_moy
        FROM plays p
        LEFT JOIN rosters r ON p.receiver_player_id = r.player_id AND r.season = p.season
        WHERE p.season = ? AND p.receiver_player_id IS NOT NULL
        GROUP BY p.receiver_player_name, p.posteam
        HAVING COUNT(*) FILTER (WHERE p.pass = 1) >= ?
        ORDER BY epa_per_play DESC
    """
    df = con.execute(query, [season, min_targets]).fetchdf()
    if df.empty:
        return df

    df = df.rename(columns={
        "player": "Player", "cibles": "Cibles", "receptions": "Rec", "yards": "Yds",
        "epa_per_play": "EPA/Cible", "air_yards_moy": "Air Yds Moy.", "yac_moy": "YAC Moy.",
    })
    colonnes = ["player_id", "photo_url", "Player", "team", "EPA/Cible", "Air Yds Moy.",
                "YAC Moy.", "Cibles", "Rec", "Yds"]
    return df[colonnes]


# ──────────────────────────────────────────────────────────────────────────────
# CLASSEMENTS HEBDOMADAIRES (Rankings > onglet Semaine)
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_top_qb_week(season: int, week: int, min_dropbacks: int = 10):
    """Top 3 QB de la ligue sur une semaine précise, classés par EPA/dropback."""
    con = get_connection()
    query = """
        SELECT p.passer_player_name AS player, p.posteam AS team,
               ANY_VALUE(p.passer_player_id) AS player_id,
               ROUND(AVG(p.epa), 3) AS epa_per_play, COUNT(*) AS dropbacks,
               ANY_VALUE(r.headshot_url) AS photo_url
        FROM plays p
        LEFT JOIN rosters r ON p.passer_player_id = r.player_id AND r.season = p.season
        WHERE p.season = ? AND p.week = ? AND p.qb_dropback = 1 AND p.passer_player_id IS NOT NULL
        GROUP BY p.passer_player_name, p.posteam
        HAVING COUNT(*) >= ?
        ORDER BY epa_per_play DESC
        LIMIT 3
    """
    df = con.execute(query, [season, week, min_dropbacks]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_top_rb_week(season: int, week: int, min_carries: int = 5):
    """Top 3 RB de la ligue sur une semaine précise, classés par EPA/course."""
    con = get_connection()
    query = """
        SELECT p.rusher_player_name AS player, p.posteam AS team,
               ANY_VALUE(p.rusher_player_id) AS player_id,
               ROUND(AVG(p.epa), 3) AS epa_per_play, COUNT(*) AS carries,
               ANY_VALUE(r.headshot_url) AS photo_url
        FROM plays p
        LEFT JOIN rosters r ON p.rusher_player_id = r.player_id AND r.season = p.season
        WHERE p.season = ? AND p.week = ? AND p.rush = 1 AND p.rusher_player_id IS NOT NULL
        GROUP BY p.rusher_player_name, p.posteam
        HAVING COUNT(*) >= ?
        ORDER BY epa_per_play DESC
        LIMIT 3
    """
    df = con.execute(query, [season, week, min_carries]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_top_wr_week(season: int, week: int, min_targets: int = 3):
    """Top 3 receveurs de la ligue sur une semaine précise, classés par EPA/cible."""
    con = get_connection()
    query = """
        SELECT p.receiver_player_name AS player, p.posteam AS team,
               ANY_VALUE(p.receiver_player_id) AS player_id,
               ROUND(AVG(p.epa), 3) AS epa_per_play, COUNT(*) AS targets,
               ANY_VALUE(r.headshot_url) AS photo_url
        FROM plays p
        LEFT JOIN rosters r ON p.receiver_player_id = r.player_id AND r.season = p.season
        WHERE p.season = ? AND p.week = ? AND p.pass = 1 AND p.receiver_player_id IS NOT NULL
        GROUP BY p.receiver_player_name, p.posteam
        HAVING COUNT(*) >= ?
        ORDER BY epa_per_play DESC
        LIMIT 3
    """
    df = con.execute(query, [season, week, min_targets]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_best_offense_week(season: int, week: int):
    """Les 3 attaques les plus efficaces (EPA) sur une semaine précise."""
    con = get_connection()
    query = """
        SELECT posteam AS team, ROUND(AVG(epa), 3) AS epa_offense, COUNT(*) AS plays
        FROM plays
        WHERE season = ? AND week = ? AND play_type IN ('pass', 'run') AND posteam IS NOT NULL
        GROUP BY posteam
        ORDER BY epa_offense DESC
        LIMIT 3
    """
    df = con.execute(query, [season, week]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_best_defense_week(season: int, week: int):
    """Les 3 défenses ayant concédé le moins d'EPA sur une semaine précise."""
    con = get_connection()
    query = """
        SELECT defteam AS team, ROUND(AVG(epa), 3) AS epa_allowed, COUNT(*) AS plays
        FROM plays
        WHERE season = ? AND week = ? AND play_type IN ('pass', 'run') AND defteam IS NOT NULL
        GROUP BY defteam
        ORDER BY epa_allowed ASC
        LIMIT 3
    """
    df = con.execute(query, [season, week]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_biggest_surprises_week(season: int, week: int):
    """Compare l'EPA de la semaine à la moyenne du reste de la saison,
    pour repérer les équipes qui sortent nettement du lot (en bien ou en mal)."""
    con = get_connection()
    query = """
        WITH season_avg AS (
            SELECT posteam AS team, AVG(epa) AS avg_season
            FROM plays
            WHERE season = ? AND week != ? AND play_type IN ('pass', 'run') AND posteam IS NOT NULL
            GROUP BY posteam
        ),
        week_epa AS (
            SELECT posteam AS team, AVG(epa) AS avg_week
            FROM plays
            WHERE season = ? AND week = ? AND play_type IN ('pass', 'run') AND posteam IS NOT NULL
            GROUP BY posteam
        )
        SELECT w.team,
               ROUND(s.avg_season, 3) AS moyenne_saison,
               ROUND(w.avg_week, 3) AS cette_semaine,
               ROUND(w.avg_week - s.avg_season, 3) AS ecart
        FROM week_epa w
        JOIN season_avg s ON w.team = s.team
        ORDER BY ecart DESC
    """
    df = con.execute(query, [season, week, season, week]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_explosive_plays_week(season: int, week: int):
    """Seuils : 20+ yards en passe, 10+ yards en course — standard NFL
    pour qualifier un jeu d'explosif."""
    con = get_connection()
    team_query = """
        SELECT posteam AS team, COUNT(*) AS explosive_plays
        FROM plays
        WHERE season = ? AND week = ?
          AND ((pass = 1 AND yards_gained >= 20) OR (rush = 1 AND yards_gained >= 10))
        GROUP BY posteam
        ORDER BY explosive_plays DESC
        LIMIT 5
    """
    top_teams = con.execute(team_query, [season, week]).fetchdf()

    plays_query = """
        SELECT COALESCE(passer_player_name, rusher_player_name) AS player,
               posteam AS team, play_type, yards_gained, ROUND(epa, 3) AS epa
        FROM plays
        WHERE season = ? AND week = ?
          AND ((pass = 1 AND yards_gained >= 20) OR (rush = 1 AND yards_gained >= 10))
        ORDER BY yards_gained DESC
        LIMIT 5
    """
    top_plays = con.execute(plays_query, [season, week]).fetchdf()
    return top_teams, top_plays

@st.cache_data(ttl=3600)
def get_turnover_battle_week(season: int, week: int):
    """Différentiel de turnovers (prises - pertes) par équipe sur une semaine précise."""
    con = get_connection()
    query = """
        WITH giveaways AS (
            SELECT posteam AS team, COUNT(*) AS giveaways
            FROM plays
            WHERE season = ? AND week = ? AND (interception = 1 OR fumble_lost = 1)
            GROUP BY posteam
        ),
        takeaways AS (
            SELECT defteam AS team, COUNT(*) AS takeaways
            FROM plays
            WHERE season = ? AND week = ? AND (interception = 1 OR fumble_lost = 1)
            GROUP BY defteam
        )
        SELECT COALESCE(g.team, t.team) AS team,
               COALESCE(t.takeaways, 0) AS takeaways,
               COALESCE(g.giveaways, 0) AS giveaways,
               COALESCE(t.takeaways, 0) - COALESCE(g.giveaways, 0) AS differentiel
        FROM giveaways g
        FULL OUTER JOIN takeaways t ON g.team = t.team
        ORDER BY differentiel DESC
    """
    df = con.execute(query, [season, week, season, week]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_pressure_leaders_week(season: int, week: int):
    """Équipes générant le plus de pression défensive sur une semaine précise."""
    con = get_connection()
    # CAST(... AS DOUBLE) plutôt que CASE WHEN was_pressure THEN :
    # la colonne peut être stockée en DOUBLE (0.0/1.0/NaN) après passage
    # par parquet, pas en booléen strict — DuckDB refuse sinon la comparaison.
    query = """
        SELECT defteam AS team,
               SUM(COALESCE(CAST(was_pressure AS DOUBLE), 0)) AS pressures,
               COUNT(*) AS pass_plays,
               ROUND(SUM(COALESCE(CAST(was_pressure AS DOUBLE), 0)) * 1.0 / COUNT(*), 3) AS taux_pression
        FROM plays
        WHERE season = ? AND week = ? AND pass = 1 AND defteam IS NOT NULL
        GROUP BY defteam
        ORDER BY pressures DESC
        LIMIT 5
    """
    df = con.execute(query, [season, week]).fetchdf()
    return df


# ─────────────────────────────────────────────────────────────
# Requêtes annuelles (Annual Recap) — stats brutes (yards)
# ─────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
# SOCIAL CARDS — VARIANTES CUMULÉES (semaine 1 → semaine sélectionnée)
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_social_top_qb_week(season: int, week: int, min_dropbacks_week: int = 10):
    """Top 3 QB de la semaine (sélection), avec EPA cumulé depuis le début de saison (affichage) — pour Social Cards."""
    con = get_connection()
    query = """
        WITH weekly AS (
            SELECT passer_player_id AS player_id, passer_player_name AS player, posteam AS team,
                   AVG(epa) AS epa_week
            FROM plays
            WHERE season = ? AND week = ? AND qb_dropback = 1 AND passer_player_id IS NOT NULL
            GROUP BY passer_player_id, passer_player_name, posteam
            HAVING COUNT(*) >= ?
        ),
        cumul AS (
            SELECT passer_player_id AS player_id, ROUND(AVG(epa), 3) AS epa_per_play
            FROM plays
            WHERE season = ? AND week <= ? AND qb_dropback = 1 AND passer_player_id IS NOT NULL
            GROUP BY passer_player_id
        )
        SELECT w.player, w.team, c.epa_per_play, r.headshot_url AS photo_url
        FROM weekly w
        JOIN cumul c ON w.player_id = c.player_id
        LEFT JOIN rosters r ON w.player_id = r.player_id AND r.season = ?
        ORDER BY w.epa_week DESC
        LIMIT 3
    """
    df = con.execute(query, [season, week, min_dropbacks_week, season, week, season]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_social_top_rb_week(season: int, week: int, min_carries_week: int = 5):
    """Top 3 RB de la semaine (sélection), avec EPA cumulé depuis le début de saison (affichage) — pour Social Cards."""
    con = get_connection()
    query = """
        WITH weekly AS (
            SELECT rusher_player_id AS player_id, rusher_player_name AS player, posteam AS team,
                   AVG(epa) AS epa_week
            FROM plays
            WHERE season = ? AND week = ? AND rush = 1 AND rusher_player_id IS NOT NULL
            GROUP BY rusher_player_id, rusher_player_name, posteam
            HAVING COUNT(*) >= ?
        ),
        cumul AS (
            SELECT rusher_player_id AS player_id, ROUND(AVG(epa), 3) AS epa_per_play
            FROM plays
            WHERE season = ? AND week <= ? AND rush = 1 AND rusher_player_id IS NOT NULL
            GROUP BY rusher_player_id
        )
        SELECT w.player, w.team, c.epa_per_play, r.headshot_url AS photo_url
        FROM weekly w
        JOIN cumul c ON w.player_id = c.player_id
        LEFT JOIN rosters r ON w.player_id = r.player_id AND r.season = ?
        ORDER BY w.epa_week DESC
        LIMIT 3
    """
    df = con.execute(query, [season, week, min_carries_week, season, week, season]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_social_top_wr_week(season: int, week: int, min_targets_week: int = 3):
    """Top 3 receveurs de la semaine (sélection), avec EPA cumulé depuis le début de saison (affichage) — pour Social Cards."""
    con = get_connection()
    query = """
        WITH weekly AS (
            SELECT receiver_player_id AS player_id, receiver_player_name AS player, posteam AS team,
                   AVG(epa) AS epa_week
            FROM plays
            WHERE season = ? AND week = ? AND pass = 1 AND receiver_player_id IS NOT NULL
            GROUP BY receiver_player_id, receiver_player_name, posteam
            HAVING COUNT(*) >= ?
        ),
        cumul AS (
            SELECT receiver_player_id AS player_id, ROUND(AVG(epa), 3) AS epa_per_play
            FROM plays
            WHERE season = ? AND week <= ? AND pass = 1 AND receiver_player_id IS NOT NULL
            GROUP BY receiver_player_id
        )
        SELECT w.player, w.team, c.epa_per_play, r.headshot_url AS photo_url
        FROM weekly w
        JOIN cumul c ON w.player_id = c.player_id
        LEFT JOIN rosters r ON w.player_id = r.player_id AND r.season = ?
        ORDER BY w.epa_week DESC
        LIMIT 3
    """
    df = con.execute(query, [season, week, min_targets_week, season, week, season]).fetchdf()
    return df

@st.cache_data(ttl=3600)
def get_social_best_offense_week(season: int, week: int):
    """Meilleure attaque de la semaine (sélection), avec EPA cumulé depuis le début de saison (affichage) — pour Social Cards."""
    con = get_connection()
    query = """
        WITH weekly AS (
            SELECT posteam AS team, AVG(epa) AS epa_week
            FROM plays
            WHERE season = ? AND week = ? AND play_type IN ('pass', 'run') AND posteam IS NOT NULL
            GROUP BY posteam
        ),
        cumul AS (
            SELECT posteam AS team, ROUND(AVG(epa), 3) AS epa_offense
            FROM plays
            WHERE season = ? AND week <= ? AND play_type IN ('pass', 'run') AND posteam IS NOT NULL
            GROUP BY posteam
        )
        SELECT w.team, c.epa_offense
        FROM weekly w JOIN cumul c ON w.team = c.team
        ORDER BY w.epa_week DESC
        LIMIT 3
    """
    df = con.execute(query, [season, week, season, week]).fetchdf()
    return df

# NOTE AUDIT : une deuxième définition de cette fonction existait plus bas dans
# l'ancien fichier et utilisait une moyenne saison complète au lieu du cumul
# semaine 1 → semaine sélectionnée. Elle écrasait silencieusement celle-ci
# (Python garde la dernière définition d'une fonction dupliquée), ce qui cassait
# la cohérence avec les 4 fonctions sœurs ci-dessus. Supprimée lors de l'audit.
@st.cache_data(ttl=3600)
def get_social_best_defense_week(season: int, week: int):
    """Meilleure défense de la semaine (sélection), avec EPA cumulé depuis le début de saison (affichage) — pour Social Cards."""
    con = get_connection()
    query = """
        WITH weekly AS (
            SELECT defteam AS team, AVG(epa) AS epa_week
            FROM plays
            WHERE season = ? AND week = ? AND play_type IN ('pass', 'run') AND defteam IS NOT NULL
            GROUP BY defteam
        ),
        cumul AS (
            SELECT defteam AS team, ROUND(AVG(epa), 3) AS epa_allowed
            FROM plays
            WHERE season = ? AND week <= ? AND play_type IN ('pass', 'run') AND defteam IS NOT NULL
            GROUP BY defteam
        )
        SELECT w.team, c.epa_allowed
        FROM weekly w JOIN cumul c ON w.team = c.team
        ORDER BY w.epa_week ASC
        LIMIT 3
    """
    df = con.execute(query, [season, week, season, week]).fetchdf()
    return df


# ──────────────────────────────────────────────────────────────────────────────
# HOME — PAGE D'ACCUEIL
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_home_stats():
    """Chiffres réels de la base, pour le bandeau de la page d'accueil."""
    con = get_connection()
    seasons = con.execute(
        "SELECT MIN(season) AS min_s, MAX(season) AS max_s, COUNT(DISTINCT season) AS n_seasons FROM plays"
    ).fetchdf().iloc[0]
    total_plays = con.execute("SELECT COUNT(*) AS n FROM plays").fetchdf()["n"].iloc[0]
    total_games = con.execute(
        "SELECT COUNT(*) AS n FROM games WHERE home_score IS NOT NULL AND away_score IS NOT NULL"
    ).fetchdf()["n"].iloc[0]
    total_teams = con.execute("SELECT COUNT(*) AS n FROM teams").fetchdf()["n"].iloc[0]
    total_players = con.execute("SELECT COUNT(DISTINCT player_id) AS n FROM rosters").fetchdf()["n"].iloc[0]
    return {
        "saison_min": int(seasons["min_s"]),
        "saison_max": int(seasons["max_s"]),
        "nb_saisons": int(seasons["n_seasons"]),
        "total_plays": int(total_plays),
        "total_games": int(total_games),
        "total_teams": int(total_teams),
        "total_players": int(total_players),
    }

@st.cache_data(ttl=3600)
def get_home_current_season():
    """Saison la plus récente ayant au moins un match joué (évite de
    pointer sur une saison à venir sans résultats, comme 2026 mi-année)."""
    con = get_connection()
    query = """
        SELECT MAX(season) AS season FROM games
        WHERE home_score IS NOT NULL AND away_score IS NOT NULL
    """
    df = con.execute(query).fetchdf()
    return int(df["season"].iloc[0])

@st.cache_data(ttl=3600)
def get_home_top_teams(season: int, limit: int = 7):
    """Top équipes de la saison en cours, pour l'aperçu affiché sur la page d'accueil."""
    con = get_connection()
    query = """
        SELECT posteam AS team, AVG(epa) AS epa_offense
        FROM plays
        WHERE season = ? AND play_type IN ('pass', 'run') AND posteam IS NOT NULL
        GROUP BY posteam
        ORDER BY epa_offense DESC
        LIMIT ?
    """
    df = con.execute(query, [season, limit]).fetchdf()
    return df

# Position réelle lue depuis rosters (pas déduite du rôle offensif) : un
# receveur de passes peut être WR, TE ou RB selon le joueur — hardcoder 'WR'
# affichait à tort des tight ends comme WR, corrigé via COALESCE(ANY_VALUE(...)).
@st.cache_data(ttl=3600)
def get_home_top_players(season: int, poste: str | None = None, limit: int = 5):
    """Top joueurs offensifs par yards bruts. """
    con = get_connection()

    qb_sql = """
        SELECT p.passer_player_name AS player, p.posteam AS team,
               COALESCE(ANY_VALUE(r.position), 'QB') AS position,
               SUM(p.passing_yards) AS yards, ANY_VALUE(r.headshot_url) AS photo_url
        FROM plays p
        LEFT JOIN rosters r ON p.passer_player_id = r.player_id AND r.season = p.season
        WHERE p.season = ? AND p.qb_dropback = 1 AND p.passer_player_id IS NOT NULL
        GROUP BY p.passer_player_name, p.posteam
        HAVING COUNT(*) >= 100
    """
    rb_sql = """
        SELECT p.rusher_player_name AS player, p.posteam AS team,
               COALESCE(ANY_VALUE(r.position), 'RB') AS position,
               SUM(p.rushing_yards) AS yards, ANY_VALUE(r.headshot_url) AS photo_url
        FROM plays p
        LEFT JOIN rosters r ON p.rusher_player_id = r.player_id AND r.season = p.season
        WHERE p.season = ? AND p.rush = 1 AND p.rusher_player_id IS NOT NULL
        GROUP BY p.rusher_player_name, p.posteam
        HAVING COUNT(*) >= 50
    """
    wr_sql = """
        SELECT p.receiver_player_name AS player, p.posteam AS team,
               COALESCE(ANY_VALUE(r.position), 'REC') AS position,
               SUM(p.receiving_yards) AS yards, ANY_VALUE(r.headshot_url) AS photo_url
        FROM plays p
        LEFT JOIN rosters r ON p.receiver_player_id = r.player_id AND r.season = p.season
        WHERE p.season = ? AND p.pass = 1 AND p.receiver_player_id IS NOT NULL
        GROUP BY p.receiver_player_name, p.posteam
        HAVING COUNT(*) >= 30
    """

    blocs = {"QB": qb_sql, "RB": rb_sql, "WR": wr_sql}

    if poste and poste in blocs:
        query = f"SELECT * FROM ({blocs[poste]}) ORDER BY yards DESC LIMIT ?"
        df = con.execute(query, [season, limit]).fetchdf()
    else:
        query = f"""
            WITH qb AS ({qb_sql}), rb AS ({rb_sql}), wr AS ({wr_sql})
            SELECT * FROM qb
            UNION ALL SELECT * FROM rb
            UNION ALL SELECT * FROM wr
            ORDER BY yards DESC
            LIMIT ?
        """
        df = con.execute(query, [season, season, season, limit]).fetchdf()

    return df

@st.cache_data(ttl=3600)
def get_home_recent_games(season: int, limit: int = 7):
    """Derniers matchs joués de la saison en cours, pour l'aperçu affiché sur la page d'accueil."""
    con = get_connection()
    query = """
        SELECT game_id, week, gameday, home_team, away_team, home_score, away_score
        FROM games
        WHERE season = ? AND home_score IS NOT NULL AND away_score IS NOT NULL
        ORDER BY gameday DESC
        LIMIT ?
    """
    df = con.execute(query, [season, limit]).fetchdf()
    return df


@st.cache_data(ttl=3600)
def get_season_sacks_leader(season: int):
    """Joueur ayant cumulé le plus de sacks (pleins + 0,5 x demi-sacks
    partagés) sur la saison entière — pour le panneau League Leaders."""
    con = get_connection()
    query = """
        WITH sacks_pleins AS (
            SELECT sack_player_id AS player_id, COUNT(*) AS n
            FROM plays WHERE season = ? AND sack_player_id IS NOT NULL
            GROUP BY sack_player_id
        ),
        demi_sacks AS (
            SELECT player_id, COUNT(*) AS n FROM (
                SELECT half_sack_1_player_id AS player_id FROM plays WHERE season = ? AND half_sack_1_player_id IS NOT NULL
                UNION ALL
                SELECT half_sack_2_player_id AS player_id FROM plays WHERE season = ? AND half_sack_2_player_id IS NOT NULL
            ) t GROUP BY player_id
        ),
        total AS (
            SELECT COALESCE(sp.player_id, ds.player_id) AS player_id,
                   COALESCE(sp.n, 0) + COALESCE(ds.n, 0) * 0.5 AS sacks
            FROM sacks_pleins sp
            FULL OUTER JOIN demi_sacks ds ON sp.player_id = ds.player_id
        )
        SELECT t.player_id, r.player_name AS player, r.team, r.headshot_url AS photo_url, t.sacks
        FROM total t
        LEFT JOIN rosters r ON t.player_id = r.player_id AND r.season = ?
        ORDER BY t.sacks DESC
        LIMIT 1
    """
    df = con.execute(query, [season, season, season, season]).fetchdf()
    return df


@st.cache_data(ttl=3600)
def get_season_interceptions_leader(season: int):
    """Joueur ayant intercepté le plus de passes (défensif) sur la saison —
    pour le panneau League Leaders."""
    con = get_connection()
    query = """
        WITH total AS (
            SELECT interception_player_id AS player_id, COUNT(*) AS interceptions
            FROM plays
            WHERE season = ? AND interception_player_id IS NOT NULL
            GROUP BY interception_player_id
        )
        SELECT t.player_id, r.player_name AS player, r.team, r.headshot_url AS photo_url, t.interceptions
        FROM total t
        LEFT JOIN rosters r ON t.player_id = r.player_id AND r.season = ?
        ORDER BY t.interceptions DESC
        LIMIT 1
    """
    df = con.execute(query, [season, season]).fetchdf()
    return df


@st.cache_data(ttl=3600)
def get_season_success_rate_leader(season: int, min_dropbacks: int = 100):
    """QB avec le meilleur taux de jeux réussis (success rate) sur ses
    dropbacks, saison entière — pour le panneau Analytics Leaders."""
    con = get_connection()
    query = """
        SELECT p.passer_player_name AS player, p.posteam AS team,
               ANY_VALUE(p.passer_player_id) AS player_id,
               ROUND(AVG(CAST(p.success AS DOUBLE)), 3) AS success_rate,
               ANY_VALUE(r.headshot_url) AS photo_url
        FROM plays p
        LEFT JOIN rosters r ON p.passer_player_id = r.player_id AND r.season = p.season
        WHERE p.season = ? AND p.qb_dropback = 1 AND p.passer_player_id IS NOT NULL
        GROUP BY p.passer_player_name, p.posteam
        HAVING COUNT(*) >= ?
        ORDER BY success_rate DESC
        LIMIT 1
    """
    df = con.execute(query, [season, min_dropbacks]).fetchdf()
    return df
# ──────────────────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────────────
# LIENS CLIQUABLES — équipe / joueur / match vers leur page dédiée
# ──────────────────────────────────────────────────────────────────────────────

# _attrs_lien : stopPropagation empêche le routeur interne de Streamlit
# (React) d'intercepter le clic gauche avant qu'il n'atteigne le lien —
# c'était le premier problème (clic droit fonctionnait, clic gauche non).
# preventDefault + window.location.href pilotent ensuite la navigation
# nous-mêmes plutôt que de laisser le comportement par défaut du navigateur
# décider — c'était le deuxième problème (le clic gauche finissait par
# ouvrir un nouvel onglet plutôt que de naviguer dans le même). Le clic
# droit ("ouvrir dans un nouvel onglet") continue de fonctionner normalement
# puisqu'il n'utilise pas ce onclick.
def _attrs_lien(href):
    return (
        f'href="{href}" '
        f'onmousedown="event.stopPropagation();" '
        f"onclick=\"event.stopPropagation();event.preventDefault();window.location.href='{href}';\""
    )

def _lien_equipe(contenu_html, abbr):
    """Enrobe un fragment HTML d'un lien vers la fiche équipe (Equipes).
    Le slug d'URL suit le nom du fichier de page (pages/1_Equipes.py) —
    si ce fichier est renommé, ce href doit être mis à jour en conséquence."""
    if not abbr or (isinstance(abbr, float) and abbr != abbr):
        return contenu_html
    href = f"Equipes?team={abbr}"
    return f'<a {_attrs_lien(href)} style="text-decoration:none;color:inherit;">{contenu_html}</a>'

def _lien_joueur(contenu_html, player_id, season=None):
    """Enrobe un fragment HTML d'un lien vers la fiche joueur (Joueurs).
    season est inclus quand disponible pour que la page Joueurs présélectionne
    la bonne saison (sinon un joueur absent de la saison affichée par défaut
    ne serait pas retrouvé). Slug d'URL lié au nom de pages/2_Joueurs.py."""
    if not isinstance(player_id, str) or not player_id:
        return contenu_html
    href = f"Joueurs?player={player_id}"
    if season:
        href += f"&season={season}"
    return f'<a {_attrs_lien(href)} style="text-decoration:none;color:inherit;">{contenu_html}</a>'

def _lien_match(contenu_html, game_id):
    """Enrobe un fragment HTML d'un lien vers la fiche match (Matchs).
    game_id encode déjà saison et semaine (convention nflverse
    'saison_semaine_visiteur_domicile'), donc la page Matchs peut s'y
    présélectionner sans paramètre supplémentaire. Slug d'URL lié au nom
    de pages/3_Matchs.py."""
    if not game_id or (isinstance(game_id, float) and game_id != game_id):
        return contenu_html
    href = f"Matchs?game={game_id}"
    return f'<a {_attrs_lien(href)} style="text-decoration:none;color:inherit;">{contenu_html}</a>'

def _aplatir_html(html):
    """Aplatit un fragment HTML multi-lignes en une seule ligne avant de
    l'envoyer à st.markdown(unsafe_allow_html=True).

    st.markdown passe d'abord par un parseur Markdown avant d'injecter le
    HTML. Dès qu'une ligne vide apparaît dans le fragment (systématique
    quand on concatène plusieurs blocs f-string en boucle avec +=) suivie
    d'une ligne indentée de 4 espaces ou plus (l'indentation naturelle du
    code Python), Markdown considère cette ligne vide comme la fin du bloc
    HTML en cours et traite la ligne suivante comme un bloc de code indenté
    — affiché en texte brut au lieu d'être rendu comme du HTML. Aplatir en
    une seule ligne élimine à la fois les lignes vides et l'indentation,
    donc le problème à la racine."""
    return re.sub(r"\s+", " ", html).strip()


def render_navigation_card(icon, title, description, slug):
    """Carte de navigation cliquable sur toute sa surface (utilisée sur
    Accueil), pas seulement sur un lien 'Ouvrir' au survol. Même mécanisme
    _attrs_lien que _lien_equipe/_lien_joueur/_lien_match (stopPropagation
    + preventDefault + window.location.href) pour rester dans le même
    onglet. slug = nom de page sans préfixe numérique ni extension
    (ex. 'Equipes', 'Joueurs') — pas de paramètre de requête ici, contrairement
    aux liens vers une fiche précise, puisqu'on navigue vers la page en
    général."""
    contenu = (
        f'<div class="nav-card">'
        f'<div class="nav-card-icon">{icon}</div>'
        f'<div class="nav-card-title">{title}</div>'
        f'<div class="nav-card-desc">{description}</div>'
        f'</div>'
    )
    html = f'<a {_attrs_lien(slug)} class="nav-card-link">{contenu}</a>'
    st.markdown(_aplatir_html(html), unsafe_allow_html=True)


def render_page_link(icon, label, slug):
    """Petit lien texte (icône + libellé) vers une page de l'app, stylé
    dans la palette du site — pas le bleu souligné par défaut de
    st.page_link. Même mécanisme _attrs_lien que le reste des liens
    internes. slug = nom de page sans préfixe numérique ni extension."""
    contenu = f'<span class="text-link">{icon} {label} →</span>'
    html = f'<a {_attrs_lien(slug)} class="text-link-wrap">{contenu}</a>'
    st.markdown(_aplatir_html(html), unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# RECHERCHE GLOBALE — barre affichée en haut de chaque page
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_global_search_index():
    """Index plat de tous les joueurs ayant figuré à un roster, toutes
    saisons confondues (dédupliqué par player_id, équipe/poste les plus
    récents retenus via ARG_MAX(saison)). Contrairement à
    get_player_search_list, aucun filtre sur les stats qualifiantes : la
    recherche globale doit pouvoir retrouver n'importe quel joueur connu,
    pas seulement ceux ayant produit une statistique suivie sur la saison
    en cours."""
    con = get_connection()
    query = """
        SELECT player_id, ANY_VALUE(player_name) AS nom,
               ARG_MAX(team, season) AS team,
               ARG_MAX(position, season) AS position,
               MAX(season) AS derniere_saison
        FROM rosters
        WHERE player_name IS NOT NULL
        GROUP BY player_id
    """
    df = con.execute(query).fetchdf()
    return df


def render_global_search():
    """Barre de recherche équipe/joueur, appelée en haut de chaque page.
    Un clic sur un résultat mène directement à la fiche correspondante
    (via les mêmes liens _lien_equipe/_lien_joueur que le reste de l'app),
    saison la plus récente du joueur présélectionnée automatiquement."""
    requete = st.text_input(
        "Recherche", placeholder="🔍 Rechercher une équipe ou un joueur…",
        key="recherche_globale", label_visibility="collapsed",
    )
    if not requete or len(requete.strip()) < 2:
        return

    q = requete.strip().lower()

    equipes = get_all_teams()
    equipes_trouvees = equipes[
        equipes["team_name"].str.lower().str.contains(q, na=False)
        | equipes["team_abbr"].str.lower().str.contains(q, na=False)
    ].head(5)

    joueurs = get_global_search_index()
    joueurs_trouves = joueurs[joueurs["nom"].str.lower().str.contains(q, na=False)].head(8)

    if equipes_trouvees.empty and joueurs_trouves.empty:
        st.caption("Aucun résultat.")
        return

    lignes = []
    for _, row in equipes_trouvees.iterrows():
        contenu = f'🏈 <b>{row["team_name"]}</b>'
        lignes.append(f'<div style="padding:6px 10px;">{_lien_equipe(contenu, row["team_abbr"])}</div>')
    for _, row in joueurs_trouves.iterrows():
        poste = f' · {row["position"]}' if row["position"] else ""
        equipe = row["team"] if isinstance(row["team"], str) and row["team"] else "?"
        contenu = f'👤 <b>{row["nom"]}</b> — {equipe}{poste}'
        saison = int(row["derniere_saison"]) if pd.notna(row["derniere_saison"]) else None
        lignes.append(f'<div style="padding:6px 10px;">{_lien_joueur(contenu, row["player_id"], season=saison)}</div>')

    html = (
        '<div style="border:1px solid #e5e7eb;border-radius:8px;padding:4px;margin-bottom:12px;">'
        + "".join(lignes) + "</div>"
    )
    st.markdown(_aplatir_html(html), unsafe_allow_html=True)


# Traduction des noms de colonnes techniques vers un affichage lisible en
# français. EPA reste tel quel (acronyme reconnu, pas de traduction utile).

def style_dataframe(df, team_col="team", decimals=3, couleur_unique=None,
                     show_team_logos=True, player_col=None, integer_cols=None):
    """Applique couleur de ligne (par équipe), contraste de texte, arrondi
    des décimales, logo d'équipe, traduction des colonnes, et style des en-têtes.

    couleur_unique : à utiliser quand le tableau ne concerne qu'une seule
    équipe (ex. page 2), donc pas de colonne "team" par ligne à mapper.
    player_col : nom de la colonne joueur, si une colonne "photo_url" est
    présente dans df, pour combiner photo + nom dans la même cellule.
    integer_cols : colonnes techniquement stockées en float (à cause de
    valeurs NaN ailleurs dans la table source, ex. down/qtr/drive absents
    sur les kickoffs) mais qui représentent des entiers — formatées sans
    décimale, avec un tiret "—" à la place de NaN plutôt que le texte
    "nan" brut.
    """
    df = df.reset_index(drop=True).copy()

    if couleur_unique is not None:
        fonds = [couleur_unique] * len(df)
        affichage = df.copy()
    elif "team_color" in df.columns:
        fonds = df["team_color"].tolist()
        affichage = df.drop(columns=["team_color"])
    elif team_col in df.columns:
        colors = get_team_colors()
        fonds = [colors.get(t, "#1f77b4") for t in df[team_col]]
        affichage = df.copy()
    else:
        fonds = ["#f0f0f0"] * len(df)
        affichage = df.copy()

    textes = [couleur_texte_contraste(c) for c in fonds]

    def colorer_ligne(row):
        i = row.name
        return [f"background-color: {fonds[i]}; color: {textes[i]}"] * len(row)

    integer_cols = integer_cols or []
    numeric_cols = affichage.select_dtypes(include="float").columns.tolist()
    numeric_cols = [c for c in numeric_cols if c not in integer_cols]

    if show_team_logos and team_col in affichage.columns:
        logos = get_team_logos()

        def _cell_avec_logo(abbr):
            url = logos.get(abbr)
            if url:
                contenu = (
                    f'<span style="white-space:nowrap;">'
                    f'<span style="display:inline-block;background:white;border-radius:50%;'
                    f'padding:2px;margin-right:6px;line-height:0;">'
                    f'<img src="{url}" height="18" style="display:block;">'
                    f'</span>{abbr}'
                    f'</span>'
                )
            else:
                contenu = abbr
            return _lien_equipe(contenu, abbr)

        affichage[team_col] = affichage[team_col].apply(_cell_avec_logo)

    if player_col and player_col in affichage.columns and "photo_url" in affichage.columns:
        a_player_id = "player_id" in affichage.columns

        def _cell_avec_photo(row):
            url = row["photo_url"]
            nom = row[player_col]
            if isinstance(url, str) and url:
                contenu = (
                    f'<span style="white-space:nowrap;">'
                    f'<img src="{url}" height="28" style="vertical-align:middle;margin-right:6px;border-radius:50%;">{nom}'
                    f'</span>'
                )
            else:
                contenu = nom
            if a_player_id:
                return _lien_joueur(contenu, row.get("player_id"))
            return contenu

        affichage[player_col] = affichage.apply(_cell_avec_photo, axis=1)
        colonnes_techniques = [c for c in ("photo_url", "player_id") if c in affichage.columns]
        affichage = affichage.drop(columns=colonnes_techniques)

    affichage = affichage.rename(columns=TRADUCTIONS_COLONNES)
    format_dict = {TRADUCTIONS_COLONNES.get(col, col): f"{{:.{decimals}f}}" for col in numeric_cols}

    def _format_entier(valeur):
        return "—" if pd.isna(valeur) else f"{int(valeur)}"

    for col in integer_cols:
        renamed = TRADUCTIONS_COLONNES.get(col, col)
        if renamed in affichage.columns:
            format_dict[renamed] = _format_entier

    header_styles = [
        {"selector": "th", "props": [
            ("background-color", "#111827"),
            ("color", "white"),
            ("font-weight", "600"),
            ("text-align", "left"),
            ("padding", "10px 14px"),
            ("border-bottom", "2px solid #374151"),
        ]},
        {"selector": "td", "props": [
            ("padding", "8px 14px"),
        ]},
        {"selector": "table", "props": [
            ("border-collapse", "collapse"),
            ("width", "100%"),
        ]},
    ]

    return (
        affichage.style
        .apply(colorer_ligne, axis=1)
        .format(format_dict)
        .set_table_styles(header_styles)
        .hide(axis="index")
    )

# st.dataframe() ignore le style des en-têtes (set_table_styles) d'un Styler —
# il ne respecte que les couleurs cellule par cellule. D'où le rendu HTML brut.
# Contrepartie assumée : pas de tri interactif au clic sur une colonne.
def render_table(styled_df):
    """Affiche un Styler pandas en HTML brut. Nécessaire car st.dataframe()
    ignore le style des en-têtes (set_table_styles) d'un Styler — il ne
    respecte que les couleurs cellule par cellule. Contrepartie : pas de
    tri interactif au clic sur une colonne."""
    html = styled_df.to_html()
    st.markdown(_aplatir_html(f'<div style="overflow-x:auto;">{html}</div>'), unsafe_allow_html=True)

def render_podium(df, metric_col, decimals=3, season=None):
    """Podium HTML pour un top 3 de joueurs : 1er au centre (plus haut), 2e à
    gauche, 3e à droite. Utilise photo_url si présente dans df, sinon un avatar
    avec les initiales du joueur, coloré aux couleurs de l'équipe.

    season : saison à laquelle appartiennent ces données, transmise au lien
    joueur pour que la page Players se présélectionne sur la bonne saison.
    """
    if df.empty:
        st.info("Aucune donnée disponible.")
        return

    colors = get_team_colors()
    logos = get_team_logos()

    couleurs_rang = ["#FBBF24", "#CBD5E1", "#D97706"]
    hauteurs = [130, 100, 80]
    ordre_affichage = [1, 0, 2] if len(df) >= 3 else list(range(len(df)))

    blocs = ""
    for i in ordre_affichage:
        if i >= len(df):
            continue
        row = df.iloc[i]
        rang = i + 1
        nom = row.get("player", "")
        team = row.get("team", "")
        player_id = row.get("player_id") if "player_id" in df.columns else None
        valeur = row.get(metric_col, 0)
        couleur_equipe = colors.get(team, "#374151")
        logo_url = logos.get(team, "")
        photo_url = row.get("photo_url") if "photo_url" in df.columns else None

        if isinstance(photo_url, str) and photo_url:
            avatar = (
                f'<img src="{photo_url}" style="width:70px;height:70px;'
                f'border-radius:50%;object-fit:cover;border:3px solid {couleur_equipe};'
                f'box-shadow:0 2px 8px rgba(0,0,0,0.3);">'
            )
        else:
            initiales = "".join([p[0] for p in nom.split(".") if p])[:2].upper() if nom else "?"
            avatar = (
                f'<div style="width:70px;height:70px;border-radius:50%;background:{couleur_equipe};'
                f'display:flex;align-items:center;justify-content:center;color:white;'
                f'font-weight:700;font-size:22px;border:3px solid {couleur_equipe};'
                f'box-shadow:0 2px 8px rgba(0,0,0,0.3);">{initiales}</div>'
            )

        logo_html = (
            f'<img src="{logo_url}" height="18" style="vertical-align:middle;margin-right:4px;">'
            if logo_url else ""
        )

        avatar_lien = _lien_joueur(avatar, player_id, season)
        nom_lien = _lien_joueur(
            f'<div style="margin-top:8px;font-weight:600;text-align:center;font-size:14px;color:#1E293B;">{nom}</div>',
            player_id, season,
        )
        equipe_lien = _lien_equipe(f'{logo_html}{team}', team)

        blocs += f"""
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:flex-end;margin:0 10px;width:120px;">
            <div style="width:28px;height:28px;border-radius:50%;background:{couleurs_rang[rang-1]};
                        display:flex;align-items:center;justify-content:center;color:#1F2937;
                        font-weight:800;font-size:14px;margin-bottom:8px;">{rang}</div>
            {avatar_lien}
            {nom_lien}
            <div style="font-size:12px;color:#64748B;">{equipe_lien}</div>
            <div style="margin-top:6px;font-weight:700;font-size:16px;color:#1E293B;">{valeur:,.{decimals}f}</div>
            <div style="width:100%;height:{hauteurs[rang-1]}px;
                        background:linear-gradient(180deg, {couleur_equipe}, {couleur_equipe}dd);
                        border-radius:8px 8px 0 0;margin-top:10px;"></div>
        </div>
        """

    st.markdown(
        _aplatir_html(
            f'<div style="display:flex;align-items:flex-end;justify-content:center;'
            f'padding:20px 0;font-family:\'Manrope\',\'Segoe UI\',sans-serif;">{blocs}</div>'
        ),
        unsafe_allow_html=True,
    )

def render_team_podium(df, metric_col, decimals=0):
    """Podium HTML pour un top 3 d'équipes (pas de joueur individuel) :
    logo d'équipe en grand format au centre de l'avatar, nom de l'équipe
    en dessous. Même structure visuelle que render_podium, adaptée aux
    entités équipe."""
    if df.empty:
        st.info("Aucune donnée disponible.")
        return

    colors = get_team_colors()
    logos = get_team_logos()

    couleurs_rang = ["#FBBF24", "#CBD5E1", "#D97706"]
    hauteurs = [130, 100, 80]
    ordre_affichage = [1, 0, 2] if len(df) >= 3 else list(range(len(df)))

    blocs = ""
    for i in ordre_affichage:
        if i >= len(df):
            continue
        row = df.iloc[i]
        rang = i + 1
        team = row.get("team", "")
        valeur = row.get(metric_col, 0)
        couleur_equipe = colors.get(team, "#374151")
        logo_url = logos.get(team, "")

        if logo_url:
            avatar = (
                f'<div style="width:70px;height:70px;border-radius:50%;background:white;'
                f'display:flex;align-items:center;justify-content:center;'
                f'border:3px solid {couleur_equipe};box-shadow:0 2px 8px rgba(0,0,0,0.3);">'
                f'<img src="{logo_url}" style="width:50px;height:50px;object-fit:contain;"></div>'
            )
        else:
            avatar = (
                f'<div style="width:70px;height:70px;border-radius:50%;background:{couleur_equipe};'
                f'display:flex;align-items:center;justify-content:center;color:white;'
                f'font-weight:700;font-size:18px;border:3px solid {couleur_equipe};'
                f'box-shadow:0 2px 8px rgba(0,0,0,0.3);">{team}</div>'
            )

        avatar_lien = _lien_equipe(avatar, team)
        nom_lien = _lien_equipe(
            f'<div style="margin-top:8px;font-weight:600;text-align:center;font-size:14px;color:#1E293B;">{team}</div>',
            team,
        )

        blocs += f"""
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:flex-end;margin:0 10px;width:120px;">
            <div style="width:28px;height:28px;border-radius:50%;background:{couleurs_rang[rang-1]};
                        display:flex;align-items:center;justify-content:center;color:#1F2937;
                        font-weight:800;font-size:14px;margin-bottom:8px;">{rang}</div>
            {avatar_lien}
            {nom_lien}
            <div style="margin-top:6px;font-weight:700;font-size:16px;color:#1E293B;">{valeur:,.{decimals}f}</div>
            <div style="width:100%;height:{hauteurs[rang-1]}px;
                        background:linear-gradient(180deg, {couleur_equipe}, {couleur_equipe}dd);
                        border-radius:8px 8px 0 0;margin-top:10px;"></div>
        </div>
        """

    st.markdown(
        _aplatir_html(
            f'<div style="display:flex;align-items:flex-end;justify-content:center;'
            f'padding:20px 0;font-family:\'Manrope\',\'Segoe UI\',sans-serif;">{blocs}</div>'
        ),
        unsafe_allow_html=True,
    )

def render_top_teams_list(df, metric_col="epa_offense", decimals=3):
    """Affiche un classement d'équipes sous forme de liste HTML compacte (logo, valeur), utilisé sur Home."""
    if df.empty:
        st.info("Aucune donnée disponible.")
        return

    colors = get_team_colors()
    logos = get_team_logos()

    rows_html = ""
    for i, row in df.reset_index(drop=True).iterrows():
        team = row["team"]
        couleur = colors.get(team, "#374151")
        logo = logos.get(team, "")
        valeur = row[metric_col]
        rows_html += f"""
        <div style="display:flex;align-items:center;gap:14px;padding:12px 18px;border-bottom:1px solid #E2E8F0;">
            <div style="width:24px;height:24px;border-radius:50%;background:{couleur};color:white;
                        display:flex;align-items:center;justify-content:center;font-weight:800;font-size:13px;">{i+1}</div>
            <img src="{logo}" height="28">
            <div style="flex:1;font-weight:600;color:#1E293B;">{team}</div>
            <div style="font-weight:800;color:{couleur};font-family:'Space Mono',monospace;">{valeur:.{decimals}f}</div>
        </div>
        """

    st.markdown(
        _aplatir_html(
            f'<div style="background:#F8FAFC;border-radius:12px;overflow:hidden;border:1px solid #E2E8F0;'
            f'font-family:\'Manrope\',sans-serif;">{rows_html}</div>'
        ),
        unsafe_allow_html=True,
    )

def render_top_players_list(df):
    """Affiche un classement de joueurs sous forme de liste HTML compacte (photo, poste, yards), utilisé sur Home."""
    if df.empty:
        st.info("Aucune donnée disponible.")
        return

    colors = get_team_colors()
    logos = get_team_logos()

    rows_html = ""
    for i, row in df.reset_index(drop=True).iterrows():
        team = row["team"]
        couleur = colors.get(team, "#374151")
        logo = logos.get(team, "")
        photo = row.get("photo_url")
        nom = row["player"]
        position = row["position"]
        valeur = row["yards"]

        if isinstance(photo, str) and photo:
            avatar = (
                f'<img src="{photo}" style="width:32px;height:32px;border-radius:50%;'
                f'object-fit:cover;border:2px solid {couleur};">'
            )
        else:
            initiales = "".join([p[0] for p in nom.split(".") if p])[:2].upper() if nom else "?"
            avatar = (
                f'<div style="width:32px;height:32px;border-radius:50%;background:{couleur};color:white;'
                f'display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px;">{initiales}</div>'
            )

        rows_html += f"""
        <div style="display:flex;align-items:center;gap:12px;padding:12px 18px;border-bottom:1px solid #E2E8F0;">
            <div style="width:22px;height:22px;border-radius:50%;background:{couleur};color:white;
                        display:flex;align-items:center;justify-content:center;font-weight:800;font-size:12px;flex-shrink:0;">{i+1}</div>
            {avatar}
            <div style="flex:1;min-width:0;">
                <div style="font-weight:600;color:#1E293B;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{nom}</div>
                <div style="font-size:11px;color:#64748B;display:flex;align-items:center;gap:4px;">
                    <img src="{logo}" height="12">{team} · {position}
                </div>
            </div>
            <div style="font-weight:800;color:{couleur};font-family:'Space Mono',monospace;font-size:14px;">{int(valeur):,}</div>
        </div>
        """

    st.markdown(
        _aplatir_html(
            f'<div style="background:#F8FAFC;border-radius:12px;overflow:hidden;border:1px solid #E2E8F0;'
            f'font-family:\'Manrope\',sans-serif;">{rows_html}</div>'
        ),
        unsafe_allow_html=True,
    )

def render_recent_games_list(df):
    """Affiche les derniers matchs sous forme de liste HTML compacte (logos, score), utilisé sur Home."""
    if df.empty:
        st.info("Aucun match disponible.")
        return

    logos = get_team_logos()

    rows_html = ""
    for _, row in df.iterrows():
        home_logo = logos.get(row["home_team"], "")
        away_logo = logos.get(row["away_team"], "")
        game_id = row.get("game_id") if "game_id" in df.columns else None
        contenu_ligne = f"""
        <div style="display:flex;align-items:center;justify-content:space-between;padding:12px 18px;border-bottom:1px solid #E2E8F0;">
            <div style="font-size:12px;color:#94A3B8;width:40px;">S{int(row['week'])}</div>
            <div style="display:flex;align-items:center;gap:8px;flex:1;justify-content:flex-end;">
                <span style="font-weight:600;color:#1E293B;">{row['away_team']}</span>
                <img src="{away_logo}" height="22">
            </div>
            <div style="font-weight:800;font-size:16px;color:#1E293B;padding:0 16px;font-family:'Space Mono',monospace;">
                {int(row['away_score'])} – {int(row['home_score'])}
            </div>
            <div style="display:flex;align-items:center;gap:8px;flex:1;">
                <img src="{home_logo}" height="22">
                <span style="font-weight:600;color:#1E293B;">{row['home_team']}</span>
            </div>
        </div>
        """
        rows_html += _lien_match(contenu_ligne, game_id)

    st.markdown(
        _aplatir_html(
            f'<div style="background:#F8FAFC;border-radius:12px;overflow:hidden;border:1px solid #E2E8F0;'
            f'font-family:\'Manrope\',sans-serif;">{rows_html}</div>'
        ),
        unsafe_allow_html=True,
    )

def render_game_performers(performers: list, couleur_equipe: str, season=None):
    """performers : liste de (label_role, dataframe) pour une équipe.
    season : transmis au lien joueur pour présélectionner la bonne saison
    sur la page Players."""
    rows_html = ""
    for label, df in performers:
        if df.empty:
            continue
        row = df.iloc[0]
        photo = row.get("photo_url")
        nom = row["player"]
        player_id = row.get("player_id") if "player_id" in df.columns else None
        position = row["position"]
        yards = int(row["yards"]) if row["yards"] == row["yards"] else 0
        epa = row["epa_per_play"]

        if isinstance(photo, str) and photo:
            avatar = (
                f'<img src="{photo}" style="width:36px;height:36px;border-radius:50%;'
                f'object-fit:cover;border:2px solid {couleur_equipe};">'
            )
        else:
            initiales = "".join([p[0] for p in nom.split(".") if p])[:2].upper() if nom else "?"
            avatar = (
                f'<div style="width:36px;height:36px;border-radius:50%;background:{couleur_equipe};color:white;'
                f'display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;">{initiales}</div>'
            )

        avatar = _lien_joueur(avatar, player_id, season)
        bloc_nom = _lien_joueur(
            f'<div style="font-weight:600;color:#1E293B;font-size:14px;">{nom}</div>',
            player_id, season,
        )

        rows_html += f"""
        <div style="display:flex;align-items:center;gap:12px;padding:10px 14px;border-bottom:1px solid #E2E8F0;">
            {avatar}
            <div style="flex:1;min-width:0;">
                {bloc_nom}
                <div style="font-size:11px;color:#64748B;">{position} · {label}</div>
            </div>
            <div style="text-align:right;">
                <div style="font-weight:800;color:{couleur_equipe};font-family:'Space Mono',monospace;font-size:14px;">{yards} yds</div>
                <div style="font-size:11px;color:#64748B;">EPA {epa:.3f}</div>
            </div>
        </div>
        """

    if not rows_html:
        rows_html = '<div style="padding:14px;color:#94A3B8;font-size:13px;">Aucune donnée disponible.</div>'

    st.markdown(
        _aplatir_html(
            f'<div style="background:#F8FAFC;border-radius:12px;overflow:hidden;border:1px solid #E2E8F0;'
            f'font-family:\'Manrope\',sans-serif;">{rows_html}</div>'
        ),
        unsafe_allow_html=True,
    )

def render_ranking_with_movement(df, value_col, decimals=3, is_player=False, season=None):
    """Vert = progression vs semaine précédente, rouge = recul, NEW = pas
    classé la semaine d'avant (nouveau qualifié ou retour de blessure).

    season : transmis au lien joueur (quand is_player=True) pour que la page
    Players se présélectionne sur la bonne saison."""
    if df.empty:
        st.info("Aucune donnée disponible.")
        return

    colors = get_team_colors()
    logos = get_team_logos()

    rows_html = ""
    for _, row in df.head(10).iterrows():
        team = row["team"]
        couleur = colors.get(team, "#374151")
        logo = logos.get(team, "")
        rang = int(row["rank"])
        valeur = row[value_col]
        evolution = row.get("evolution")

        if evolution != evolution:
            badge = '<span style="color:#94A3B8;font-size:11px;font-weight:700;">NEW</span>'
        elif evolution > 0:
            badge = f'<span style="color:#16A34A;font-size:12px;font-weight:700;">▲ {int(evolution)}</span>'
        elif evolution < 0:
            badge = f'<span style="color:#DC2626;font-size:12px;font-weight:700;">▼ {int(abs(evolution))}</span>'
        else:
            badge = '<span style="color:#94A3B8;font-size:12px;">–</span>'

        nom_affiche = f"{row['player']} · {team}" if is_player else team
        logo_lien = _lien_equipe(f'<img src="{logo}" height="20">', team)
        nom_div = f'<div style="flex:1;min-width:0;font-weight:600;color:#1E293B;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{nom_affiche}</div>'
        if is_player:
            nom_div = _lien_joueur(nom_div, row.get("player_id"), season)
        else:
            nom_div = _lien_equipe(nom_div, team)

        rows_html += f"""
        <div style="display:flex;align-items:center;gap:10px;padding:10px 16px;border-bottom:1px solid #E2E8F0;">
            <div style="width:20px;font-weight:800;color:{couleur};font-size:14px;">{rang}</div>
            {logo_lien}
            {nom_div}
            <div style="width:44px;text-align:center;">{badge}</div>
            <div style="width:60px;text-align:right;font-weight:800;color:{couleur};font-family:'Space Mono',monospace;font-size:13px;">{valeur:.{decimals}f}</div>
        </div>
        """

    st.markdown(
        _aplatir_html(
            f'<div style="background:#F8FAFC;border-radius:12px;overflow:hidden;border:1px solid #E2E8F0;'
            f'font-family:\'Manrope\',sans-serif;">{rows_html}</div>'
        ),
        unsafe_allow_html=True,
    )

def render_insight_leaders(entries):
    """Affiche une liste "qui domine sur quoi" : une ligne par métrique,
    chacune montrant SON propre leader — pas un tableau classé sur une
    seule métrique. Pensé pour un coup d'œil rapide sur la page d'accueil.

    entries : liste de dicts {label, name, team (abréviation ou None),
    value (déjà formaté en string), photo_url (optionnel), player_id
    (optionnel — présent seulement quand l'entrée désigne un joueur), season
    (optionnel — saison de l'entrée, pour présélectionner la page Players)}."""
    colors = get_team_colors()
    logos = get_team_logos()

    rows_html = ""
    for e in entries:
        team = e.get("team")
        couleur = colors.get(team, "#374151") if team else "#374151"
        logo = logos.get(team, "") if team else ""
        photo = e.get("photo_url")
        player_id = e.get("player_id")
        season = e.get("season")

        if isinstance(photo, str) and photo:
            avatar = (
                f'<img src="{photo}" style="width:30px;height:30px;border-radius:50%;'
                f'object-fit:cover;border:2px solid {couleur};flex-shrink:0;">'
            )
        elif logo:
            avatar = f'<img src="{logo}" height="26" style="flex-shrink:0;">'
        else:
            avatar = '<div style="width:30px;flex-shrink:0;"></div>'

        nom = e.get("name") or "—"
        nom_div = f'<div style="flex:1;min-width:0;font-weight:600;color:#1E293B;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{nom}</div>'
        if player_id:
            avatar = _lien_joueur(avatar, player_id, season)
            nom_div = _lien_joueur(nom_div, player_id, season)
        elif team:
            avatar = _lien_equipe(avatar, team)
            nom_div = _lien_equipe(nom_div, team)

        rows_html += f"""
        <div style="display:flex;align-items:center;gap:12px;padding:10px 16px;border-bottom:1px solid #E2E8F0;">
            <div style="width:100px;flex-shrink:0;font-size:11px;color:#94A3B8;text-transform:uppercase;letter-spacing:0.04em;">{e['label']}</div>
            {avatar}
            {nom_div}
            <div style="font-weight:800;color:{couleur};font-family:'Space Mono',monospace;font-size:14px;flex-shrink:0;">{e['value']}</div>
        </div>
        """

    st.markdown(
        _aplatir_html(
            f'<div style="background:#F8FAFC;border-radius:12px;overflow:hidden;border:1px solid #E2E8F0;'
            f'font-family:\'Manrope\',sans-serif;">{rows_html}</div>'
        ),
        unsafe_allow_html=True,
    )