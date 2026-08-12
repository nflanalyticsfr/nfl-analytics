import streamlit as st
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from queries import (
    get_all_teams, get_seasons_for_team, get_team_colors, get_team_logos,
    get_team_epa_offense_defense, get_team_epa_by_week, get_all_teams_records, get_team_schedule,
    get_team_qb_leaders, get_team_rb_leaders, get_team_wr_leaders, get_team_defensive_summary,
    get_team_qb_leaders_yards, get_team_rb_leaders_yards, get_team_wr_leaders_yards,
    get_all_teams_defensive_summary, get_team_rank_label,
    render_podium, render_global_search,
)
from constants import DEFAULT_TEAM
from styles import PAGE_FONT_CSS
import plotly.graph_objects as go

st.set_page_config(page_title="Equipes", layout="wide")

st.markdown(PAGE_FONT_CSS, unsafe_allow_html=True)
render_global_search()

teams_df = get_all_teams()
team_name_to_abbr = dict(zip(teams_df["team_name"], teams_df["team_abbr"]))
abbr_to_name = {v: k for k, v in team_name_to_abbr.items()}

# Identifiant équipe piloté par l'URL (?team=MIA) — équivalent fonctionnel
# d'une route dédiée, dans les limites de Streamlit Cloud.
# L'équipe n'est initialisée depuis l'URL qu'une seule fois (première visite
# de session). Ensuite, le key= dédié garde son état indépendamment du
# widget Saison, qui a son propre key — plus de couplage accidentel entre
# les deux sélections.
if "select_team" not in st.session_state:
    initial_abbr = st.query_params.get("team", DEFAULT_TEAM)
    if initial_abbr not in abbr_to_name:
        # Repli ultime si DEFAULT_TEAM n'est pas dans la liste des équipes
        # actives (ne devrait pas arriver, mais évite un crash silencieux).
        initial_abbr = teams_df["team_abbr"].iloc[0]
    st.session_state["select_team"] = abbr_to_name[initial_abbr]

col_select, col_season = st.columns([2, 1])
with col_select:
    team_name = st.selectbox("Équipe", teams_df["team_name"], key="select_team")
    team_abbr = team_name_to_abbr[team_name]
    st.query_params["team"] = team_abbr

with col_season:
    seasons = get_seasons_for_team(team_abbr)
    # key inclut team_abbr : changer d'équipe réinitialise logiquement la
    # saison à la plus récente disponible pour cette équipe, sans jamais
    # affecter la sélection d'équipe elle-même.
    season = st.selectbox("Saison", seasons, index=len(seasons) - 1, key=f"select_season_{team_abbr}")

colors = get_team_colors()
logos = get_team_logos()
couleur_equipe = colors.get(team_abbr, "#374151")
logo_url = logos.get(team_abbr, "")

# ─── En-tête équipe (bilan) — commun aux deux onglets, reste hors tabs ───
records = get_all_teams_records(season)
record_row = records[records["team"] == team_abbr]
if not record_row.empty:
    wins = int(record_row["wins"].iloc[0])
    losses = int(record_row["losses"].iloc[0])
    ties = int(record_row["ties"].iloc[0])
else:
    wins = losses = ties = 0

team_info = teams_df[teams_df["team_abbr"] == team_abbr].iloc[0]

st.markdown(f"""
<div style="display:flex;align-items:center;gap:20px;padding:10px 0;">
    <img src="{logo_url}" height="80">
    <div>
        <div style="font-size:32px;font-weight:800;color:{couleur_equipe};">{team_info['team_name']}</div>
        <div style="font-size:16px;color:#64748B;">
            {wins}-{losses}{'-' + str(ties) if ties else ''} · Saison {season}
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

st.divider()

onglet_overview, onglet_avance = st.tabs(["Overview", "Advanced Analytics ⭐ PRO"])

# ═══════════════════════════════════════════════════════════════════════
# OVERVIEW — accès libre : ce qu'on trouverait sur un site de consultation
# classique (bilan, calendrier, leaders en yards, stats défensives brutes).
# ═══════════════════════════════════════════════════════════════════════
with onglet_overview:

    # ─── Derniers et prochains matchs ───
    schedule = get_team_schedule(team_abbr, season)
    derniers = schedule[schedule["joue"]].tail(5).sort_values("week", ascending=False)
    prochains = schedule[~schedule["joue"]].sort_values("week")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Derniers matchs")
        if derniers.empty:
            st.info("Aucun match joué cette saison.")
        else:
            for _, row in derniers.iterrows():
                resultat = "V" if row["team_score"] > row["opp_score"] else ("D" if row["team_score"] < row["opp_score"] else "N")
                lieu = "vs" if row["domicile"] else "@"
                st.write(f"S{row['week']} — {resultat} {lieu} {row['opponent']} · {int(row['team_score'])}-{int(row['opp_score'])}")

    with col2:
        st.subheader(f"Prochains matchs ({len(prochains)})" if not prochains.empty else "Prochains matchs")
        if prochains.empty:
            st.info("Aucun match à venir programmé.")
        else:
            for _, row in prochains.iterrows():
                lieu = "vs" if row["domicile"] else "@"
                st.write(f"S{row['week']} — {lieu} {row['opponent']} · {row['gameday']}")

    st.divider()

    # ─── Leaders offensifs — Yards (stats "classiques") ───
    st.subheader("Leaders offensifs — Yards")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.write("Passing — Yards lancés")
        render_podium(get_team_qb_leaders_yards(team_abbr, season), metric_col="yards", decimals=0, season=season)
    with col2:
        st.write("Courses — Yards parcourus")
        render_podium(get_team_rb_leaders_yards(team_abbr, season), metric_col="yards", decimals=0, season=season)
    with col3:
        st.write("Réception — Yards attrapés")
        render_podium(get_team_wr_leaders_yards(team_abbr, season), metric_col="yards", decimals=0, season=season)

    st.divider()

    # ─── Résumé défensif — comptages bruts (turnovers, sacks) + classement ligue ───
    st.subheader("Résumé défensif")
    def_summary = get_team_defensive_summary(team_abbr, season)
    classement_def = get_all_teams_defensive_summary(season)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "Interceptions", int(def_summary["interceptions"].iloc[0]),
        get_team_rank_label(classement_def, team_abbr, "interceptions"),
    )
    col2.metric(
        "Fumbles forcés", int(def_summary["fumbles_forces"].iloc[0]),
        get_team_rank_label(classement_def, team_abbr, "fumbles_forces"),
    )
    col3.metric(
        "Sacks", f"{def_summary['sacks'].iloc[0]:.0f}",
        get_team_rank_label(classement_def, team_abbr, "sacks"),
    )
    col4.metric(
        "Taux de pression",
        f"{def_summary['taux_pression'].iloc[0]:.1%}" if def_summary['taux_pression'].iloc[0] is not None else "—",
        get_team_rank_label(classement_def, team_abbr, "taux_pression"),
    )

# ═══════════════════════════════════════════════════════════════════════
# ADVANCED ANALYTICS — tout ce qui repose sur l'EPA. Aucun paiement n'est
# en place : le contenu reste visible, seulement étiqueté comme futur
# contenu payant, pour mesurer l'intérêt avant d'ouvrir les abonnements.
# ═══════════════════════════════════════════════════════════════════════
with onglet_avance:
    st.caption("⭐ Ces statistiques feront partie de **NFL Analytics Pro** — en accès libre pour l'instant.")

    df_epa_ligue = get_team_epa_offense_defense(season)
    df_epa_ligue_off = df_epa_ligue.sort_values("epa_offense", ascending=False).reset_index(drop=True)
    rang_offense = df_epa_ligue_off[df_epa_ligue_off["team"] == team_abbr].index[0] + 1 if team_abbr in df_epa_ligue_off["team"].values else None

    df_epa_ligue_def = df_epa_ligue.sort_values("epa_defense", ascending=True).reset_index(drop=True)
    rang_defense = df_epa_ligue_def[df_epa_ligue_def["team"] == team_abbr].index[0] + 1 if team_abbr in df_epa_ligue_def["team"].values else None

    equipe_row = df_epa_ligue[df_epa_ligue["team"] == team_abbr]
    nb_equipes_classees = len(df_epa_ligue)

    col_epa_off, col_epa_def = st.columns(2)
    with col_epa_off:
        st.metric(
            "EPA Offense",
            f"{equipe_row['epa_offense'].iloc[0]:.3f}" if not equipe_row.empty else "—",
            f"#{rang_offense} / {nb_equipes_classees} en ligue" if rang_offense else None,
        )
    with col_epa_def:
        st.metric(
            "EPA Défense (concédé)",
            f"{equipe_row['epa_defense'].iloc[0]:.3f}" if not equipe_row.empty else "—",
            f"#{rang_defense} / {nb_equipes_classees} en ligue" if rang_defense else None,
        )

    st.divider()

    # ─── Leaders offensifs — EPA ───
    st.subheader("Leaders offensifs — EPA")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.write("Passing — EPA/dropback")
        render_podium(get_team_qb_leaders(team_abbr, season), metric_col="epa_per_play", season=season)
    with col2:
        st.write("Courses — EPA/course")
        render_podium(get_team_rb_leaders(team_abbr, season), metric_col="epa_per_play", season=season)
    with col3:
        st.write("Réception — EPA/cible")
        render_podium(get_team_wr_leaders(team_abbr, season), metric_col="epa_per_play", season=season)

    st.divider()

    # ─── Tendance EPA semaine par semaine ───
    st.subheader("Tendance EPA — semaine par semaine")
    df_weekly = get_team_epa_by_week(team_abbr, season)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_weekly["week"], y=df_weekly["epa_offense"], mode="lines+markers",
        name="EPA Offense", line=dict(color=couleur_equipe, width=3),
    ))
    fig.add_trace(go.Scatter(
        x=df_weekly["week"], y=df_weekly["epa_defense"], mode="lines+markers",
        name="EPA Defense", line=dict(color=couleur_equipe, width=2, dash="dot"),
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(xaxis_title="Semaine", yaxis_title="EPA par play", height=400)
    fig.update_xaxes(dtick=1)
    st.plotly_chart(fig, width='stretch', key=f"epa_trend_team_{team_abbr}_{season}")