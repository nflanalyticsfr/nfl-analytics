import streamlit as st
import plotly.graph_objects as go
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from queries import (
    get_available_seasons, get_team_epa_offense_defense, get_team_logos,
    style_dataframe, render_table,
    get_passing_leaderboard_season, get_rushing_leaderboard_season, get_receiving_leaderboard_season,
    get_passing_leaderboard_epa_season, get_rushing_leaderboard_epa_season, get_receiving_leaderboard_epa_season,
    get_defense_leaderboard_season, render_global_search, render_footer,
)
from styles import PAGE_FONT_CSS

st.set_page_config(page_title="Analytics", layout="wide")
st.markdown(PAGE_FONT_CSS, unsafe_allow_html=True)
render_global_search()
st.title("Analytics")

# ═══════════════════════════════════════════════════════════════════════
# CONSTANTES — quadrant EPA équipe (onglet PRO)
# ═══════════════════════════════════════════════════════════════════════
AXE_MIN = -0.20
AXE_MAX = 0.20
LOGO_SIZE = 0.022
FIGURE_HEIGHT = 700


# ═══════════════════════════════════════════════════════════════════════
# HELPERS — quadrant EPA équipe
# ═══════════════════════════════════════════════════════════════════════
def add_quadrant_background(fig):
    """Découpage visuel du graphique en 4 zones : Elite, Défense forte,
    Attaque forte, Reconstruction."""
    zones = [
        (0, AXE_MAX, AXE_MIN, 0),
        (AXE_MIN, 0, AXE_MIN, 0),
        (0, AXE_MAX, 0, AXE_MAX),
        (AXE_MIN, 0, 0, AXE_MAX),
    ]
    for x0, x1, y0, y1 in zones:
        fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1, line_width=0, layer="below")


def add_net_epa_lines(fig):
    """Diagonales de Net EPA (attaque - défense), fixes pour comparaison entre saisons."""
    for level in [-0.15, -0.10, -0.05, 0, 0.05, 0.10, 0.15]:
        fig.add_shape(
            type="line", x0=AXE_MIN, y0=AXE_MIN - level, x1=AXE_MAX, y1=AXE_MAX - level,
            line=dict(color="lightgray", width=1, dash="dot"), layer="below",
        )
        fig.add_annotation(x=0.18, y=0.18 - level, text=f"Net {level:+.2f}", showarrow=False, font=dict(size=10))


def add_quadrant_labels(fig):
    labels = [
        (0.13, -0.13, "Elite<br>Attaque + Défense"),
        (-0.13, -0.13, "Défense dominante"),
        (0.13, 0.13, "Attaque dominante"),
        (-0.13, 0.13, "Reconstruction"),
    ]
    for x, y, text in labels:
        fig.add_annotation(x=x, y=y, text=f"<b>{text}</b>", showarrow=False, font=dict(size=13))


def add_team_hover(fig, df):
    """Trace invisible utilisée uniquement pour le hover (les logos affichés
    en dessous ne portent pas de tooltip)."""
    fig.add_trace(go.Scatter(
        x=df["epa_offense"], y=df["epa_defense"], mode="markers",
        marker=dict(size=50, opacity=0),
        customdata=df[["team_name", "plays_offense", "plays_defense"]],
        hovertemplate=(
            "<b>%{customdata[0]}</b><br><br>"
            "EPA attaque : %{x:.3f}<br>"
            "EPA défense : %{y:.3f}<br><br>"
            "Actions offensives : %{customdata[1]}<br>"
            "Actions défensives : %{customdata[2]}<extra></extra>"
        ),
        showlegend=False,
    ))


def add_team_logos(fig, df):
    for _, row in df.iterrows():
        logo = row["logo_url"]
        if isinstance(logo, str) and logo:
            fig.add_layout_image(dict(
                source=logo, xref="x", yref="y",
                x=row["epa_offense"], y=row["epa_defense"],
                sizex=LOGO_SIZE, sizey=LOGO_SIZE,
                xanchor="center", yanchor="middle", layer="above",
            ))


def configure_team_axes(fig):
    fig.update_xaxes(range=[AXE_MIN, AXE_MAX], zeroline=True)
    fig.update_yaxes(range=[AXE_MAX, AXE_MIN], zeroline=True)
    fig.update_layout(
        height=FIGURE_HEIGHT,
        xaxis_title="EPA offensif par action (droite = meilleure attaque)",
        yaxis_title="EPA défensif par action (haut = meilleure défense)",
        margin=dict(l=40, r=40, t=50, b=40),
        autosize=True,
        dragmode=False,
        hovermode="closest",
    )


def build_team_chart(df):
    fig = go.Figure()
    add_quadrant_background(fig)
    add_net_epa_lines(fig)
    add_quadrant_labels(fig)
    add_team_hover(fig, df)
    add_team_logos(fig, df)
    configure_team_axes(fig)
    return fig


# ═══════════════════════════════════════════════════════════════════════
# HELPERS — leaderboards joueurs (classiques et EPA)
# ═══════════════════════════════════════════════════════════════════════
def config_entier(label):
    return st.column_config.NumberColumn(label, format="%d")


def config_decimal(label):
    return st.column_config.NumberColumn(label, format="%.1f")


def afficher_leaderboard(df, colonnes_entieres, colonnes_decimales):
    """Affichage générique des classements joueurs (tri par colonne, largeur
    auto, colonne image) via st.dataframe natif."""
    if df.empty:
        st.info("Aucune donnée disponible avec ces filtres.")
        return

    configuration = {
        "photo_url": st.column_config.ImageColumn("Photo", width="small"),
        "Player": st.column_config.TextColumn("Joueur", width="medium"),
        "team": st.column_config.TextColumn("Équipe", width="small"),
    }
    for colonne in colonnes_entieres:
        if colonne in df.columns:
            configuration[colonne] = config_entier(colonne)
    for colonne in colonnes_decimales:
        if colonne in df.columns:
            configuration[colonne] = config_decimal(colonne)

    ordre_colonnes = ["photo_url", "Player", "team"]
    ordre_colonnes += [c for c in df.columns if c not in ordre_colonnes and c != "player_id"]

    st.dataframe(
        df, column_config=configuration, column_order=ordre_colonnes,
        hide_index=True, width='stretch', height=650,
    )


def filtre_passe(key):
    return st.number_input("Tentatives de passe minimum", min_value=0, value=100, step=25, key=key)


def filtre_course(key):
    return st.number_input("Tentatives de course minimum", min_value=0, value=50, step=10, key=key)


def filtre_reception(key):
    return st.number_input("Cibles minimum", min_value=0, value=40, step=10, key=key)


# ═══════════════════════════════════════════════════════════════════════
# SÉLECTEUR SAISON — commun aux deux onglets, reste hors tabs
# ═══════════════════════════════════════════════════════════════════════
seasons = get_available_seasons()
season = st.selectbox("Saison", seasons, index=len(seasons) - 1, key="analytics_season")

st.divider()

onglet_overview, onglet_avance = st.tabs(["Overview", "Advanced Analytics ⭐ PRO"])

# ═══════════════════════════════════════════════════════════════════════
# OVERVIEW — accès libre : leaderboards classiques (yards, TD, rate...),
# ce qu'on trouverait sur un site de stats NFL classique.
# ═══════════════════════════════════════════════════════════════════════
with onglet_overview:
    st.caption("Classements saison complète avec filtres de volume minimum.")

    pass_tab, rush_tab, rec_tab, idp_tab = st.tabs(["Passe", "Course", "Réception", "IDP"])

    with pass_tab:
        st.subheader("Passeurs — saison complète")
        minimum = filtre_passe("ov_min_passe")
        df = get_passing_leaderboard_season(season)
        afficher_leaderboard(
            df[df["Att"] >= minimum],
            colonnes_entieres=["Yds Passe", "Att", "Cmp", "TD", "INT", "1st", "20+", "40+", "Lng", "Sck", "SckY"],
            colonnes_decimales=["Yds/Att", "Cmp%", "Rate", "1st%"],
        )

    with rush_tab:
        st.subheader("Coureurs — saison complète")
        minimum = filtre_course("ov_min_course")
        df = get_rushing_leaderboard_season(season)
        afficher_leaderboard(
            df[df["Att"] >= minimum],
            colonnes_entieres=["Yds Course", "Att", "TD", "20+", "40+", "Lng", "Rush 1st", "Rush FUM"],
            colonnes_decimales=["Rush 1st%"],
        )

    with rec_tab:
        st.subheader("Receveurs — saison complète")
        minimum = filtre_reception("ov_min_reception")
        df = get_receiving_leaderboard_season(season)
        afficher_leaderboard(
            df[df["Cibles"] >= minimum],
            colonnes_entieres=["Rec", "Yds", "TD", "20+", "40+", "LNG", "Rec 1st", "Rec FUM", "Cibles"],
            colonnes_decimales=["1st%", "Rec YAC/R"],
        )

    with idp_tab:
        st.subheader("IDP (Individual Defensive Players) — saison complète")
        st.caption("Tacles, TFL, sacks, pressions, INT, passes défendues, fumbles forcés — toutes positions défensives confondues.")
        minimum = st.number_input("Actions défensives minimum", min_value=0, value=10, step=5, key="ov_min_idp")
        df = get_defense_leaderboard_season(season)
        afficher_leaderboard(
            df[df["Tacles"] + df["TFL"] + df["Sacks"] + df["Pressions"] + df["INT"] + df["PD"] + df["FF"] >= minimum] if not df.empty else df,
            colonnes_entieres=["Tacles", "TFL", "Sacks", "Pressions", "INT", "PD", "FF"],
            colonnes_decimales=[],
        )

# ═══════════════════════════════════════════════════════════════════════
# ADVANCED ANALYTICS — tout ce qui repose sur l'EPA : Power Tiers équipe
# et leaderboards joueurs en EPA. Aucun paiement en place, contenu visible,
# juste étiqueté comme futur payant.
# ═══════════════════════════════════════════════════════════════════════
with onglet_avance:
    st.caption("⭐ Ces statistiques feront partie de **NFL Analytics Pro** — en accès libre pour l'instant.")

    tab_team, tab_players = st.tabs(["Équipe", "Joueurs"])

    with tab_team:
        st.subheader("NFL Power Tiers")
        st.caption("Qui domine réellement la ligue : attaque, défense ou les deux.")

        df_team = get_team_epa_offense_defense(season)
        logos = get_team_logos()
        df_team["logo_url"] = df_team["team"].map(logos)

        fig = build_team_chart(df_team)
        st.plotly_chart(fig, width='stretch', key=f"power_tiers_{season}")

        st.subheader("Détails équipes")
        render_table(style_dataframe(df_team.drop(columns=["logo_url"])))

    with tab_players:
        st.caption("Classements saison complète en EPA — filtres de volume minimum.")

        pass_tab_epa, rush_tab_epa, rec_tab_epa = st.tabs(["Passe", "Course", "Réception"])

        with pass_tab_epa:
            st.subheader("Passeurs — EPA saison complète")
            minimum = filtre_passe("pro_min_passe")
            df = get_passing_leaderboard_epa_season(season)
            afficher_leaderboard(
                df[df["Dropbacks"] >= minimum] if not df.empty else df,
                colonnes_entieres=["Dropbacks", "Pressions subies", "Sacks subis"],
                colonnes_decimales=["EPA/Dropback", "CPOE", "Air Yds Moy.", "Taux pression"],
            )

        with rush_tab_epa:
            st.subheader("Coureurs — EPA saison complète")
            minimum = filtre_course("pro_min_course")
            df = get_rushing_leaderboard_epa_season(season)
            afficher_leaderboard(
                df[df["Att"] >= minimum] if not df.empty else df,
                colonnes_entieres=["Att", "Yds Course"],
                colonnes_decimales=["EPA/Course"],
            )

        with rec_tab_epa:
            st.subheader("Receveurs — EPA saison complète")
            minimum = filtre_reception("pro_min_reception")
            df = get_receiving_leaderboard_epa_season(season)
            afficher_leaderboard(
                df[df["Cibles"] >= minimum] if not df.empty else df,
                colonnes_entieres=["Cibles", "Rec", "Yds"],
                colonnes_decimales=["EPA/Cible", "Air Yds Moy.", "YAC Moy."],
            )

render_footer()
