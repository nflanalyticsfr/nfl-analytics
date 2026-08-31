import streamlit as st
import plotly.graph_objects as go
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from queries import get_all_teams, get_team_stats_by_season_multi, get_team_colors, couleur_texte_contraste, style_dataframe, render_table, render_global_search, render_footer, render_header
from styles import PAGE_FONT_CSS

st.markdown(PAGE_FONT_CSS, unsafe_allow_html=True)
render_header()
render_global_search()
st.title("Comparer les équipes — saison par saison")

teams_df = get_all_teams()
team_name_to_abbr = dict(zip(teams_df["team_name"], teams_df["team_abbr"]))

team_names = st.multiselect(
    "Équipes",
    teams_df["team_name"],
    default=[teams_df["team_name"].iloc[0]],
)

colors = get_team_colors()

if team_names:
    # Injection de CSS ciblant les tags générés par st.multiselect,
    # dans l'ordre de sélection, pour remplacer la couleur d'accent
    # par défaut par la couleur réelle de chaque équipe.
    css_rules = ""
    for i, name in enumerate(team_names, start=1):
        abbr = team_name_to_abbr[name]
        couleur = colors.get(abbr, "#1f77b4")
        texte = couleur_texte_contraste(couleur)
        css_rules += f"""
        div[data-baseweb="tag"]:nth-of-type({i}) {{
            background-color: {couleur} !important;
            color: {texte} !important;
        }}
        div[data-baseweb="tag"]:nth-of-type({i}) svg {{
            fill: {texte} !important;
        }}
        """
    st.markdown(f"<style>{css_rules}</style>", unsafe_allow_html=True)
else:
    st.info("Sélectionne au moins une équipe.")
    st.stop()

team_abbrs = [team_name_to_abbr[name] for name in team_names]

# (colonne df, label affiché, titre axe Y, x100 pour l'affichage graphique
# uniquement — le tableau en dessous garde toujours la valeur brute, ligne
# de référence à 0 uniquement quand 0 est une valeur pivot significative)
METRIQUES = {
    "epa_offense":              ("EPA Offensif",              "EPA par play",        False, True),
    "epa_defense":               ("EPA Défensif",              "EPA par play",        False, True),
    "success_rate_offense":     ("Success Rate Offensif",     "Success Rate (%)",    True,  False),
    "success_rate_defense":      ("Success Rate Défensif",     "Success Rate (%)",    True,  False),
    "yards_per_play_offense":   ("Yards/Play Offensif",       "Yards par play",      False, False),
    "yards_per_play_defense":    ("Yards/Play Défensif",       "Yards par play",      False, False),
    "points_pour_par_match":    ("Points Marqués/Match",      "Points par match",    False, False),
    "points_contre_par_match":   ("Points Encaissés/Match",    "Points par match",    False, False),
    "turnover_diff":            ("Différentiel Turnovers",    "Turnovers forcés − perdus", False, True),
    "win_pct":                  ("Win %",                     "% de victoires",      True,  False),
}

metric = st.selectbox(
    "Métrique",
    options=list(METRIQUES.keys()),
    format_func=lambda k: METRIQUES[k][0],
)
label, y_title, en_pourcentage, ligne_zero = METRIQUES[metric]

df = get_team_stats_by_season_multi(team_abbrs)

fig = go.Figure()
for team in team_abbrs:
    df_team = df[df["team"] == team]
    y = df_team[metric] * 100 if en_pourcentage else df_team[metric]
    fig.add_trace(go.Scatter(
        x=df_team["season"], y=y,
        mode="lines+markers", name=team,
        line=dict(color=colors.get(team, "#1f77b4"), width=3),
    ))

if ligne_zero:
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
fig.update_layout(xaxis_title="Saison", yaxis_title=y_title, height=600)
fig.update_xaxes(dtick=1)

st.plotly_chart(fig, width='stretch')
render_table(style_dataframe(
    df,
    integer_cols=["wins", "losses", "ties", "turnover_diff"],
))
render_footer()
