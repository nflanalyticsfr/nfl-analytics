import streamlit as st
import plotly.graph_objects as go
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from queries import (
    get_available_seasons, get_weeks_for_season, get_games_for_week, get_game_info,
    get_team_colors, get_team_logos, get_game_win_probability, get_game_epa_cumulative,
    get_game_score_progression, get_game_drives, get_game_top_performer, get_game_play_by_play,
    render_game_performers, traduire_surface, style_dataframe, render_table,
    render_global_search, render_footer, render_header,
)
from styles import PAGE_FONT_CSS

st.set_page_config(page_title="Matchs", layout="wide")

st.markdown(PAGE_FONT_CSS, unsafe_allow_html=True)
render_header()
render_global_search()

st.title("Matchs")

seasons = sorted(get_available_seasons(), reverse=True)

# Un lien entrant (?game=...) encode saison et semaine dans le game_id
# (convention nflverse "saison_semaine_visiteur_domicile"). Sans ça, les
# selectbox Saison/Semaine restent sur leur valeur par défaut (dernière
# saison/semaine) et le match ciblé, absent de cette liste-là, serait
# ignoré silencieusement plus bas.
initial_game_id = st.query_params.get("game")
season_cible, week_cible = None, None
if initial_game_id:
    morceaux = initial_game_id.split("_")
    if len(morceaux) >= 2 and morceaux[0].isdigit() and morceaux[1].isdigit():
        season_cible, week_cible = int(morceaux[0]), int(morceaux[1])

col_season, col_week, col_match = st.columns([1, 1, 2])

with col_season:
    index_season = seasons.index(season_cible) if season_cible in seasons else 0
    season = st.selectbox("Saison", seasons, index=index_season, key="game_season")

with col_week:
    weeks = sorted(get_weeks_for_season(season), reverse=True)
    index_week = weeks.index(week_cible) if week_cible in weeks else 0
    week = st.selectbox("Semaine", weeks, index=index_week, key="game_week")

games = get_games_for_week(season, week)
if games.empty:
    st.info("Aucun match programmé pour cette semaine.")
    st.stop()

options_match = [
    f"{row['away_team']} @ {row['home_team']}"
    + (f" ({int(row['away_score'])}-{int(row['home_score'])})" if row["home_score"] == row["home_score"] else "")
    for _, row in games.iterrows()
]

index_defaut = 0
if initial_game_id and initial_game_id in games["game_id"].values:
    index_defaut = int(games[games["game_id"] == initial_game_id].index[0])

with col_match:
    match_choisi = st.selectbox("Match", options_match, index=index_defaut, key="game_select")

game_id = games.iloc[options_match.index(match_choisi)]["game_id"]
st.query_params["game"] = game_id

st.divider()

# ─── En-tête du match (commun aux deux onglets, reste hors tabs) ───
info = get_game_info(game_id)
if info.empty:
    st.error("Match introuvable.")
    st.stop()
info = info.iloc[0]

colors = get_team_colors()
logos = get_team_logos()

col_away, col_score, col_home = st.columns([2, 1, 2])
with col_away:
    st.markdown(f"""
    <div style="text-align:center;">
        <img src="{logos.get(info['away_team'], '')}" height="70"><br>
        <span style="font-size:20px;font-weight:700;color:{colors.get(info['away_team'], '#374151')};">{info['away_team']}</span>
    </div>
    """, unsafe_allow_html=True)

with col_score:
    score_display = (
        f"{int(info['away_score'])} – {int(info['home_score'])}"
        if info["home_score"] == info["home_score"] else "À venir"
    )
    st.markdown(f"""
    <div style="text-align:center;padding-top:15px;">
        <div style="font-size:32px;font-weight:800;font-family:'Space Mono',monospace;">{score_display}</div>
        <div style="font-size:12px;color:#64748B;">Semaine {int(info['week'])} · {info['gameday']}</div>
    </div>
    """, unsafe_allow_html=True)

with col_home:
    st.markdown(f"""
    <div style="text-align:center;">
        <img src="{logos.get(info['home_team'], '')}" height="70"><br>
        <span style="font-size:20px;font-weight:700;color:{colors.get(info['home_team'], '#374151')};">{info['home_team']}</span>
    </div>
    """, unsafe_allow_html=True)

def info_bloc(label, valeur):
    return f"""
    <div style="text-align:center;">
        <div style="font-size:11px;color:#94A3B8;text-transform:uppercase;letter-spacing:0.05em;">{label}</div>
        <div style="font-size:15px;font-weight:600;color:#1E293B;margin-top:2px;">{valeur}</div>
    </div>
    """

stade = info["stadium"] if isinstance(info["stadium"], str) else "—"
surface = traduire_surface(info["surface"])

if info["temp"] == info["temp"]:
    temp_f = info["temp"]
    temp_c = round((temp_f - 32) * 5 / 9)
    meteo = f"{temp_c}°C <span style='font-size:11px;color:#94A3B8;'>({int(temp_f)}°F)</span>"
else:
    meteo = "—"

prolongation = "Oui" if info["overtime"] == 1 else "Non"

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown(info_bloc("Stade", stade), unsafe_allow_html=True)
with col2:
    st.markdown(info_bloc("Surface", surface), unsafe_allow_html=True)
with col3:
    st.markdown(info_bloc("Météo", meteo), unsafe_allow_html=True)
with col4:
    st.markdown(info_bloc("Prolongation", prolongation), unsafe_allow_html=True)

st.divider()

onglet_resume, onglet_analyse = st.tabs(["Résumé", "Analyse ⭐ PRO"])

# ═══════════════════════════════════════════════════════════════════════
# RÉSUMÉ — accès libre : score, leaders, drives, play-by-play.
# ═══════════════════════════════════════════════════════════════════════
with onglet_resume:

    st.subheader("Meilleurs joueurs")
    col_away, col_home = st.columns(2)
    for col, team in [(col_away, info["away_team"]), (col_home, info["home_team"])]:
        with col:
            logo = logos.get(team, "")
            couleur = colors.get(team, "#374151")
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
                f'<img src="{logo}" height="24"><span style="font-weight:700;color:{couleur};">{team}</span></div>',
                unsafe_allow_html=True,
            )
            qb = get_game_top_performer(game_id, team, season, "passing")
            rb = get_game_top_performer(game_id, team, season, "rushing")
            wr = get_game_top_performer(game_id, team, season, "receiving")
            render_game_performers([("Passing", qb), ("Rushing", rb), ("Receiving", wr)], couleur, season=season)

    st.divider()

    st.subheader("Progression du score")
    score_df = get_game_score_progression(game_id)
    if not score_df.empty:
        fig_score = go.Figure()
        fig_score.add_trace(go.Scatter(
            x=score_df["progression"], y=score_df["ecart_domicile"],
            mode="lines", line=dict(color=colors.get(info["home_team"], "#374151"), width=2),
        ))
        fig_score.add_hline(y=0, line_dash="dash", line_color="gray")
        fig_score.update_layout(
            xaxis_title="Progression du match",
            yaxis_title=f"Écart ({info['home_team']} positif)",
            height=350,
        )
        st.plotly_chart(fig_score, width='stretch', key=f"score_{game_id}")
    else:
        st.info("Données de score indisponibles pour ce match.")

    st.divider()

    st.subheader("Résumé des drives")
    drives = get_game_drives(game_id)
    if not drives.empty:
        render_table(style_dataframe(drives, team_col="team", integer_cols=["drive"]))
    else:
        st.info("Données de drives indisponibles pour ce match.")

    st.divider()

    st.subheader("Play-by-play")
    quarts_dispo = ["Tous", 1, 2, 3, 4, 5]
    quart_choisi = st.selectbox("Filtrer par quart-temps", quarts_dispo, key=f"quarter_{game_id}")
    filtre_quart = None if quart_choisi == "Tous" else quart_choisi

    pbp = get_game_play_by_play(game_id, quarter=filtre_quart)
    if not pbp.empty:
        render_table(style_dataframe(pbp, team_col="posteam", integer_cols=["qtr", "down", "ydstogo", "yardline_100"]))
    else:
        st.info("Play-by-play indisponible pour ce match.")

# ═══════════════════════════════════════════════════════════════════════
# ANALYSE — Win Probability, EPA cumulé. Aucun paiement n'est en place :
# contenu visible, juste étiqueté comme futur payant.
# ═══════════════════════════════════════════════════════════════════════
with onglet_analyse:
    st.caption("⭐ Ces analyses feront partie de **NFL Analytics Pro** — en accès libre pour l'instant.")

    st.subheader("Win Probability")
    wp_df = get_game_win_probability(game_id)
    if not wp_df.empty:
        fig_wp = go.Figure()
        fig_wp.add_trace(go.Scatter(
            x=wp_df["progression"], y=wp_df["home_wp"] * 100,
            mode="lines", fill="tozeroy",
            line=dict(color=colors.get(info["home_team"], "#374151"), width=2),
            name=info["home_team"],
        ))
        fig_wp.add_hline(y=50, line_dash="dash", line_color="gray")
        fig_wp.update_layout(
            xaxis_title="Progression du match", yaxis_title=f"Probabilité de victoire — {info['home_team']} (%)",
            yaxis_range=[0, 100], height=350,
        )
        st.plotly_chart(fig_wp, width='stretch', key=f"wp_{game_id}")
    else:
        st.info("Données de win probability indisponibles pour ce match.")

    st.divider()

    st.subheader("EPA cumulé du match")
    epa_df = get_game_epa_cumulative(game_id)
    if not epa_df.empty:
        fig_epa = go.Figure()
        for team in epa_df["posteam"].unique():
            df_team = epa_df[epa_df["posteam"] == team]
            fig_epa.add_trace(go.Scatter(
                x=df_team["progression"], y=df_team["epa_cumule"],
                mode="lines", name=team,
                line=dict(color=colors.get(team, "#374151"), width=2),
            ))
        fig_epa.add_hline(y=0, line_dash="dash", line_color="gray")
        fig_epa.update_layout(xaxis_title="Progression du match", yaxis_title="EPA cumulé", height=350)
        st.plotly_chart(fig_epa, width='stretch', key=f"epa_{game_id}")
    else:
        st.info("Données EPA indisponibles pour ce match.")

render_footer()
