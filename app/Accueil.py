import streamlit as st
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
from queries import (
    get_home_stats, get_home_current_season, get_home_recent_games, render_recent_games_list,
    get_top_qb_season_yards, get_top_rb_season_yards, get_top_wr_season_yards,
    get_top_qb_season_epa, get_team_epa_offense_defense,
    get_season_sacks_leader, get_season_interceptions_leader, get_season_success_rate_leader,
    render_insight_leaders, render_global_search, render_navigation_card, render_page_link, render_footer,
)
from styles import HOME_CSS

st.set_page_config(page_title="NFL Analytics", layout="wide", page_icon="🏈")

stats = get_home_stats()

st.markdown(HOME_CSS, unsafe_allow_html=True)

st.markdown(f"""
<div class="hero-banner">
    <div class="hero-eyebrow">Play-by-play · {stats['saison_min']}–{stats['saison_max']}</div>
    <h1 class="hero-title">NFL Analytics FR</h1>
    <p class="hero-tagline">Chaque équipe. Chaque joueur. Chaque play.</p>
</div>
<div class="stat-strip">
    <div class="stat-item"><div class="stat-value">{stats['total_plays']:,}</div><div class="stat-label">Plays</div></div>
    <div class="stat-item"><div class="stat-value">{stats['total_games']:,}</div><div class="stat-label">Matchs</div></div>
    <div class="stat-item"><div class="stat-value">{stats['total_teams']}</div><div class="stat-label">Équipes</div></div>
    <div class="stat-item"><div class="stat-value">{stats['nb_saisons']}</div><div class="stat-label">Saisons</div></div>
</div>
""", unsafe_allow_html=True)

render_global_search()


# ─── Aperçu de la saison — insights, pas des tableaux ───
st.subheader("Aperçu de la saison")

home_season = get_home_current_season()
st.caption(f"Données de la saison {home_season}")


def _leader_entry(label, df, name_col, team_col, value_col, value_fmt, photo=True, season=None):
    """Construit une entrée pour render_insight_leaders à partir de la
    première ligne d'un DataFrame déjà trié — gère le cas où aucun joueur
    n'atteint encore le seuil qualifiant (ex. tout début de saison)."""
    if df.empty:
        return {"label": label, "name": "—", "team": None, "value": "—"}
    row = df.iloc[0]
    return {
        "label": label,
        "name": row[name_col],
        "team": row[team_col],
        "value": value_fmt(row[value_col]),
        "photo_url": row.get("photo_url") if photo else None,
        "player_id": row.get("player_id") if "player_id" in df.columns else None,
        "season": season,
    }


df_epa_ligue = get_team_epa_offense_defense(home_season)
df_off_epa_sorted = df_epa_ligue.sort_values("epa_offense", ascending=False)
df_def_epa_sorted = df_epa_ligue.sort_values("epa_defense", ascending=True)

league_leaders = [
    _leader_entry("Yards Passe", get_top_qb_season_yards(home_season), "player", "team", "yards", lambda v: f"{int(v):,}", season=home_season),
    _leader_entry("Yards Course", get_top_rb_season_yards(home_season), "player", "team", "yards", lambda v: f"{int(v):,}", season=home_season),
    _leader_entry("Yards Réception", get_top_wr_season_yards(home_season), "player", "team", "yards", lambda v: f"{int(v):,}", season=home_season),
    _leader_entry("Sacks", get_season_sacks_leader(home_season), "player", "team", "sacks", lambda v: f"{v:.1f}", season=home_season),
    _leader_entry("Interceptions", get_season_interceptions_leader(home_season), "player", "team", "interceptions", lambda v: f"{int(v)}", season=home_season),
]

analytics_leaders = [
    _leader_entry("EPA/Play", get_top_qb_season_epa(home_season), "player", "team", "epa_per_play", lambda v: f"{v:.3f}", season=home_season),
    _leader_entry("Taux de réussite", get_season_success_rate_leader(home_season), "player", "team", "success_rate", lambda v: f"{v:.1%}", season=home_season),
    {
        "label": "EPA Offensif",
        "name": df_off_epa_sorted.iloc[0]["team_name"] if not df_off_epa_sorted.empty else "—",
        "team": df_off_epa_sorted.iloc[0]["team"] if not df_off_epa_sorted.empty else None,
        "value": f"{df_off_epa_sorted.iloc[0]['epa_offense']:.3f}" if not df_off_epa_sorted.empty else "—",
    },
    {
        "label": "EPA Défensif",
        "name": df_def_epa_sorted.iloc[0]["team_name"] if not df_def_epa_sorted.empty else "—",
        "team": df_def_epa_sorted.iloc[0]["team"] if not df_def_epa_sorted.empty else None,
        "value": f"{df_def_epa_sorted.iloc[0]['epa_defense']:.3f}" if not df_def_epa_sorted.empty else "—",
    },
]

col_league, col_analytics, col_games = st.columns(3)

with col_league:
    st.write("**Leaders de la ligue**")
    render_insight_leaders(league_leaders)
    render_page_link("🏆", "Voir tous les classements", "Classements")

with col_analytics:
    st.write("**Leaders Analytics** ⭐")
    render_insight_leaders(analytics_leaders)
    render_page_link("📊", "Explorer les analytics", "Analytics")

with col_games:
    st.write("**Derniers matchs**")
    render_recent_games_list(get_home_recent_games(home_season))
    render_page_link("🏈", "Explorer les équipes", "Equipes")

st.divider()

# ─── Navigation principale ───
col1, col2, col3 = st.columns(3)
with col1:
    render_navigation_card(
        "🏈", "Equipes",
        "Fiche complète par équipe : bilan, EPA, classement ligue, leaders, calendrier.",
        "Equipes",
    )
with col2:
    render_navigation_card(
        "👤", "Joueurs",
        "Fiche joueur : bio, statistiques passing/rushing/receiving, EPA, pression, tendance.",
        "Joueurs",
    )
with col3:
    render_navigation_card(
        "🏟️", "Matchs",
        "Détail d'un match : score, drives, win probability, play-by-play.",
        "Matchs",
    )

col4, col5, col6 = st.columns(3)
with col4:
    render_navigation_card(
        "🏆", "Classements",
        "Meilleurs joueurs et équipes, semaine par semaine ou saison entière.",
        "Classements",
    )
with col5:
    render_navigation_card(
        "📊", "Analytics",
        "EPA offensif vs défensif, toutes les équipes de la ligue en un coup d'œil.",
        "Analytics",
    )
with col6:
    render_navigation_card(
        "⚖️", "Comparer",
        "Compare plusieurs équipes sur plusieurs années, offense ou défense.",
        "Comparer",
    )

col7, col8 = st.columns(2)
with col7:
    render_navigation_card(
        "📸", "Cartes sociales",
        "Génère des visuels prêts pour Instagram : joueur, équipe ou podium.",
        "Cartes_Sociales",
    )
with col8:
    render_navigation_card(
        "ℹ️", "A propos",
        "Source des données, méthodologie, et formulaire de retour.",
        "A_propos",
    )

st.divider()

# ─── Feedback ───
with st.container(border=True):
    st.subheader("Un avis à partager ?")
    st.write("Ce projet est en phase de test. Tes retours m'aident à savoir quoi améliorer en priorité.")
    st.link_button("Donner mon avis", "https://docs.google.com/forms/d/e/1FAIpQLSdEDhXjqpZjaKdjrIXozICa3qRP9qvOj0pNRtt5L8GMemIPiw/viewform", icon="📝")

render_footer()
