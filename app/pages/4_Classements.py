import streamlit as st
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from queries import (
    get_available_seasons, get_weeks_for_season, style_dataframe, render_table, render_podium, render_team_podium,
    get_top_qb_week, get_top_rb_week, get_top_wr_week,
    get_best_offense_week, get_best_defense_week, get_biggest_surprises_week,
    get_explosive_plays_week, get_turnover_battle_week, get_pressure_leaders_week,
    get_top_qb_season_yards, get_top_rb_season_yards, get_top_wr_season_yards,
    get_top_teams_offense_yards_season, get_top_qb_season_epa, get_top_rb_season_epa,
    get_team_weekly_movement, get_player_weekly_movement, render_ranking_with_movement,
    get_top_wr_season_epa, get_team_epa_offense_defense, render_global_search, render_footer,
)
from styles import PAGE_FONT_CSS

st.set_page_config(page_title="Classements", layout="wide")
st.markdown(PAGE_FONT_CSS, unsafe_allow_html=True)
render_global_search()
st.title("Classements")

# ─── Sélecteurs saison + semaine — communs aux deux onglets, reste hors tabs ───
seasons = get_available_seasons()
col_season, col_week = st.columns(2)
with col_season:
    selected_season = st.selectbox("Saison", seasons, index=len(seasons) - 1, key="rankings_season")
with col_week:
    weeks = get_weeks_for_season(selected_season)
    week = st.selectbox("Semaine", weeks, index=len(weeks) - 1, key=f"rankings_week_{selected_season}")

st.divider()

onglet_overview, onglet_avance = st.tabs(["Overview", "Advanced Analytics ⭐ PRO"])

# ═══════════════════════════════════════════════════════════════════════
# OVERVIEW — accès libre : comptages bruts (yards, plays explosifs,
# turnovers), pas de métrique EPA.
# ═══════════════════════════════════════════════════════════════════════
with onglet_overview:
    onglet_semaine, onglet_saison = st.tabs(["Cette semaine", "Cette saison"])

    with onglet_semaine:
        st.subheader("Plays explosifs")
        top_teams, top_plays = get_explosive_plays_week(selected_season, week)
        col1, col2 = st.columns(2)
        with col1:
            st.write("Équipes — nombre de plays explosifs")
            render_table(style_dataframe(top_teams))
        with col2:
            st.write("Top 5 plays de la semaine")
            render_table(style_dataframe(top_plays))

        st.divider()
        st.subheader("Bataille des turnovers")
        render_table(style_dataframe(get_turnover_battle_week(selected_season, week)))

    with onglet_saison:
        st.caption("Pour la saison en cours, les statistiques reflètent uniquement les semaines déjà jouées.")

        st.subheader("Statistiques brutes — Yards")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.write("Top 3 QB — Yards lancés")
            render_podium(get_top_qb_season_yards(selected_season), metric_col="yards", decimals=0, season=selected_season)
        with col2:
            st.write("Top 3 RB — Yards parcourus")
            render_podium(get_top_rb_season_yards(selected_season), metric_col="yards", decimals=0, season=selected_season)
        with col3:
            st.write("Top 3 Receveurs — Yards attrapés")
            render_podium(get_top_wr_season_yards(selected_season), metric_col="yards", decimals=0, season=selected_season)

        st.divider()
        st.subheader("Top 3 Équipes — Yards offensifs totaux")
        render_team_podium(get_top_teams_offense_yards_season(selected_season), metric_col="yards", decimals=0)

# ═══════════════════════════════════════════════════════════════════════
# ADVANCED ANALYTICS — tout ce qui repose sur l'EPA (efficacité, pas
# volume). Aucun paiement en place, contenu visible, juste étiqueté comme
# futur payant.
# ═══════════════════════════════════════════════════════════════════════
with onglet_avance:
    st.caption("⭐ Ces statistiques feront partie de **NFL Analytics Pro** — en accès libre pour l'instant.")

    onglet_semaine_pro, onglet_saison_pro = st.tabs(["Cette semaine", "Cette saison"])

    with onglet_semaine_pro:
        st.subheader("Top 3 — EPA de la semaine")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.write("QB — EPA/dropback")
            render_podium(get_top_qb_week(selected_season, week), metric_col="epa_per_play", season=selected_season)
        with col2:
            st.write("RB — EPA/course")
            render_podium(get_top_rb_week(selected_season, week), metric_col="epa_per_play", season=selected_season)
        with col3:
            st.write("Receveurs — EPA/cible")
            render_podium(get_top_wr_week(selected_season, week), metric_col="epa_per_play", season=selected_season)

        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Meilleure attaque de la semaine")
            render_table(style_dataframe(get_best_offense_week(selected_season, week)))
        with col2:
            st.subheader("Meilleure défense de la semaine")
            render_table(style_dataframe(get_best_defense_week(selected_season, week)))

        st.divider()
        st.subheader("Équipes qui sortent du lot vs leur moyenne saison")
        df_surprises = get_biggest_surprises_week(selected_season, week)
        col1, col2 = st.columns(2)
        with col1:
            st.write("Plus forte surperformance")
            render_table(style_dataframe(df_surprises.head(3)))
        with col2:
            st.write("Plus forte contre-performance")
            render_table(style_dataframe(df_surprises.tail(3)))

        st.divider()
        st.subheader("Pressions générées")
        if selected_season < 2023:
            st.caption("Donnée de pression partiellement disponible avant 2023.")
        render_table(style_dataframe(get_pressure_leaders_week(selected_season, week)))

        st.divider()
        st.subheader("Classement de la semaine — avec évolution")
        st.caption("▲ progression / ▼ recul vs semaine précédente · classé par EPA")

        col1, col2 = st.columns(2)
        with col1:
            st.write("**Équipes — EPA Offensif**")
            render_ranking_with_movement(get_team_weekly_movement(selected_season, week), value_col="epa_offense")
        with col2:
            st.write("**QB — EPA/Dropback**")
            render_ranking_with_movement(get_player_weekly_movement(selected_season, week, "passing"), value_col="epa_per_play", is_player=True, season=selected_season)

        st.write("")
        col3, col4 = st.columns(2)
        with col3:
            st.write("**RB — EPA/Course**")
            render_ranking_with_movement(get_player_weekly_movement(selected_season, week, "rushing"), value_col="epa_per_play", is_player=True, season=selected_season)
        with col4:
            st.write("**Receveurs — EPA/Cible**")
            render_ranking_with_movement(get_player_weekly_movement(selected_season, week, "receiving"), value_col="epa_per_play", is_player=True, season=selected_season)

    with onglet_saison_pro:
        st.caption("Pour la saison en cours, les statistiques reflètent uniquement les semaines déjà jouées.")

        st.subheader("Performance EPA")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.write("Top 3 QB — EPA/dropback")
            render_podium(get_top_qb_season_epa(selected_season), metric_col="epa_per_play", decimals=3, season=selected_season)
        with col2:
            st.write("Top 3 RB — EPA/course")
            render_podium(get_top_rb_season_epa(selected_season), metric_col="epa_per_play", decimals=3, season=selected_season)
        with col3:
            st.write("Top 3 Receveurs — EPA/cible")
            render_podium(get_top_wr_season_epa(selected_season), metric_col="epa_per_play", decimals=3, season=selected_season)

        st.divider()
        col1, col2 = st.columns(2)
        df_teams_epa = get_team_epa_offense_defense(selected_season)
        with col1:
            st.write("Top 3 Attaques — EPA offensif")
            render_team_podium(df_teams_epa.nlargest(3, "epa_offense").reset_index(drop=True), metric_col="epa_offense", decimals=3)
        with col2:
            st.write("Top 3 Défenses — EPA concédé le plus bas")
            render_team_podium(df_teams_epa.nsmallest(3, "epa_defense").reset_index(drop=True), metric_col="epa_defense", decimals=3)

render_footer()
