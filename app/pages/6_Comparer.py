import streamlit as st
import plotly.graph_objects as go
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from queries import get_all_teams, get_team_epa_by_season_multi, get_team_colors, couleur_texte_contraste, style_dataframe, render_table, render_global_search, render_footer, render_header
from styles import PAGE_FONT_CSS

st.set_page_config(page_title="Comparer", layout="wide")
st.markdown(PAGE_FONT_CSS, unsafe_allow_html=True)
render_header()
render_global_search()
st.title("Évolution EPA par équipe — saison par saison")

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

metric = st.radio("Métrique", ["epa_offense", "epa_defense"], horizontal=True)

df = get_team_epa_by_season_multi(team_abbrs)

fig = go.Figure()
for team in team_abbrs:
    df_team = df[df["team"] == team]
    fig.add_trace(go.Scatter(
        x=df_team["season"], y=df_team[metric],
        mode="lines+markers", name=team,
        line=dict(color=colors.get(team, "#1f77b4"), width=3),
    ))

fig.add_hline(y=0, line_dash="dash", line_color="gray")
fig.update_layout(xaxis_title="Saison", yaxis_title="EPA par play", height=600)
fig.update_xaxes(dtick=1)

st.plotly_chart(fig, width='stretch')
render_table(style_dataframe(df))
render_footer()
