import streamlit as st
import sys
from io import BytesIO
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from queries import (
    get_available_seasons, get_weeks_for_season, get_all_teams, get_team_colors, get_team_logos,
    get_team_weekly_movement, get_team_epa_offense_defense,
    get_player_weekly_movement, get_player_bio,
    get_top_qb_season_yards, get_top_rb_season_yards, get_top_wr_season_yards,
    get_top_qb_season_epa, get_top_rb_season_epa, get_top_wr_season_epa,
    get_top_teams_offense_yards_season,
    get_team_epa_cumulative_through_week, get_player_epa_cumulative_through_week,
    get_social_top_qb_week, get_social_top_rb_week, get_social_top_wr_week,
    get_social_best_offense_week, get_social_best_defense_week, render_global_search, render_footer, render_header,
)
from social_cards import (
    generer_carte_joueur, generer_carte_equipe, generer_podium_image,
    generer_power_tiers_image, _formatter_valeur,
)
from styles import PAGE_FONT_CSS

st.set_page_config(page_title="Cartes sociales", layout="wide")
st.markdown(PAGE_FONT_CSS, unsafe_allow_html=True)
render_header()
render_global_search()
st.title("Générateur de visuels — Instagram")
st.caption("Génère un visuel carré (1080×1080), avec rang et évolution vs semaine précédente.")

type_carte = st.radio("Type de carte", ["Joueur", "Équipe", "Podium", "Power Tiers"], horizontal=True, key="type_carte_select")

seasons = sorted(get_available_seasons(), reverse=True)
colors = get_team_colors()
logos = get_team_logos()

# ─────────────────────────────────────────────────────────────
# Carte Joueur
# ─────────────────────────────────────────────────────────────
if type_carte == "Joueur":
    season = st.selectbox("Saison", seasons, index=0, key="joueur_season")
    weeks = sorted(get_weeks_for_season(season), reverse=True)
    week = st.selectbox("Semaine", weeks, index=0, key="joueur_week")

    poste = st.radio("Poste", ["QB", "RB", "WR"], horizontal=True, key="joueur_poste")
    role_map = {"QB": "passing", "RB": "rushing", "WR": "receiving"}
    label_map = {"QB": "EPA/DROPBACK", "RB": "EPA/COURSE", "WR": "EPA/CIBLE"}
    role = role_map[poste]

    classement = get_player_weekly_movement(season, week, role)
    if classement.empty:
        st.warning("Aucun joueur qualifié pour ce poste cette semaine.")
        st.stop()

    options = [f"#{int(r['rank'])} — {r['player']} ({r['team']})" for _, r in classement.iterrows()]
    choix = st.selectbox("Joueur", options, key=f"joueur_select_{season}_{week}_{role}")
    idx = options.index(choix)
    ligne = classement.iloc[idx]

    bio = get_player_bio(ligne["player_id"], season)
    if bio.empty:
        st.warning("Bio indisponible pour ce joueur.")
        st.stop()
    bio = bio.iloc[0]

    evolution = ligne["evolution"] if ligne["rank_precedent"] == ligne["rank_precedent"] else None

    cumul_stat = get_player_epa_cumulative_through_week(ligne["player_id"], season, week, role)
    if not cumul_stat.empty and cumul_stat["epa_per_play"].iloc[0] == cumul_stat["epa_per_play"].iloc[0]:
        valeur_affichee = f"{cumul_stat['epa_per_play'].iloc[0]:.3f}"
    else:
        valeur_affichee = f"{ligne['epa_per_play']:.3f}"

    if st.button("Générer le visuel", key="generer_joueur"):
        img = generer_carte_joueur(
            nom=bio["player_name"], poste=bio["position"], team_abbr=ligne["team"],
            team_color=colors.get(ligne["team"], "#374151"), logo_url=logos.get(ligne["team"], ""),
            photo_url=bio["headshot_url"], stat_label=label_map[poste], stat_value=valeur_affichee,
            rang=int(ligne["rank"]), evolution=evolution,
        )
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        st.image(img, width=400)
        st.download_button("Télécharger le PNG", buffer.getvalue(),
                            file_name=f"{bio['player_name'].replace(' ', '_')}_S{week}.png",
                            mime="image/png", key="dl_joueur")

# ─────────────────────────────────────────────────────────────
# Carte Équipe
# ─────────────────────────────────────────────────────────────
elif type_carte == "Équipe":
    season = st.selectbox("Saison", seasons, index=0, key="equipe_season")
    weeks = sorted(get_weeks_for_season(season), reverse=True)
    week = st.selectbox("Semaine", weeks, index=0, key="equipe_week")

    teams_df = get_all_teams()
    team_name = st.selectbox("Équipe", teams_df["team_name"], key="equipe_select")
    team_abbr = teams_df[teams_df["team_name"] == team_name]["team_abbr"].iloc[0]

    df_cumul = get_team_epa_cumulative_through_week(season, week)
    df_off = df_cumul.sort_values("epa_offense", ascending=False).reset_index(drop=True)
    df_def = df_cumul.sort_values("epa_defense", ascending=True).reset_index(drop=True)

    if team_abbr not in df_cumul["team"].values:
        st.warning("Données indisponibles pour cette équipe/saison.")
        st.stop()

    rang_off_saison = df_off[df_off["team"] == team_abbr].index[0] + 1
    rang_def_saison = df_def[df_def["team"] == team_abbr].index[0] + 1
    epa_off_saison = df_cumul[df_cumul["team"] == team_abbr]["epa_offense"].iloc[0]
    epa_def_saison = df_cumul[df_cumul["team"] == team_abbr]["epa_defense"].iloc[0]

    mouvement = get_team_weekly_movement(season, week)
    rang_semaine, evolution_semaine = None, None
    if not mouvement.empty and team_abbr in mouvement["team"].values:
        ligne_mvt = mouvement[mouvement["team"] == team_abbr].iloc[0]
        rang_semaine = int(ligne_mvt["rank"])
        evolution_semaine = ligne_mvt["evolution"] if ligne_mvt["rank_precedent"] == ligne_mvt["rank_precedent"] else None

    if st.button("Générer le visuel", key="generer_equipe"):
        img = generer_carte_equipe(
            team_name=team_name, season=season, team_color=colors.get(team_abbr, "#374151"),
            logo_url=logos.get(team_abbr, ""), rang_off=rang_off_saison, epa_off=epa_off_saison,
            rang_def=rang_def_saison, epa_def=epa_def_saison,
            rang_semaine=rang_semaine, evolution_semaine=evolution_semaine,
        )
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        st.image(img, width=400)
        st.download_button("Télécharger le PNG", buffer.getvalue(),
                            file_name=f"{team_abbr}_S{week}.png", mime="image/png", key="dl_equipe")

# ─────────────────────────────────────────────────────────────
# Podium
# ─────────────────────────────────────────────────────────────
elif type_carte == "Podium":
    season = st.selectbox("Saison", seasons, index=0, key="podium_season")
    portee = st.radio("Portée", ["Semaine", "Saison"], horizontal=True, key="podium_portee")

    if portee == "Semaine":
        weeks = sorted(get_weeks_for_season(season), reverse=True)
        week = st.selectbox("Semaine", weeks, index=0, key="podium_week")

        categories = {
            "Top 3 QB — EPA/Dropback": (get_social_top_qb_week(season, week), "epa_per_play", 3, False),
            "Top 3 RB — EPA/Course": (get_social_top_rb_week(season, week), "epa_per_play", 3, False),
            "Top 3 Receveurs — EPA/Cible": (get_social_top_wr_week(season, week), "epa_per_play", 3, False),
            "Top 3 Attaques — EPA": (get_social_best_offense_week(season, week), "epa_offense", 3, True),
            "Top 3 Défenses — EPA Concédé": (get_social_best_defense_week(season, week), "epa_allowed", 3, True),
        }
        libelle_periode = f"Semaine {week} — Saison {season}"
    else:
        categories = {
            "Top 3 QB — Yards": (get_top_qb_season_yards(season), "yards", 0, False),
            "Top 3 QB — EPA/Dropback": (get_top_qb_season_epa(season), "epa_per_play", 3, False),
            "Top 3 RB — Yards": (get_top_rb_season_yards(season), "yards", 0, False),
            "Top 3 RB — EPA/Course": (get_top_rb_season_epa(season), "epa_per_play", 3, False),
            "Top 3 Receveurs — Yards": (get_top_wr_season_yards(season), "yards", 0, False),
            "Top 3 Receveurs — EPA/Cible": (get_top_wr_season_epa(season), "epa_per_play", 3, False),
            "Top 3 Équipes — Yards Offensifs": (get_top_teams_offense_yards_season(season), "yards", 0, True),
        }
        libelle_periode = f"Saison {season}"

    nom_categorie = st.selectbox("Catégorie", list(categories.keys()), key="podium_categorie")
    df_categorie, colonne_valeur, decimales, est_equipe = categories[nom_categorie]

    if df_categorie.empty:
        st.warning("Aucune donnée disponible pour cette catégorie.")
        st.stop()

    df_categorie = df_categorie.head(3).reset_index(drop=True)

    if st.button("Générer le podium", key="generer_podium"):
        entries = []
        for idx, row in df_categorie.iterrows():
            team = row["team"]
            entree = {
                "rang": idx + 1,
                "team_color": colors.get(team, "#374151"),
                "logo_url": logos.get(team, ""),
                "valeur": _formatter_valeur(row[colonne_valeur], decimales),
            }
            if est_equipe:
                entree["nom"] = team
                entree["sous_texte"] = ""
            else:
                entree["nom"] = row["player"]
                entree["sous_texte"] = team
                entree["photo_url"] = row.get("photo_url")
            entries.append(entree)

        img = generer_podium_image(entries, titre=nom_categorie, sous_titre=libelle_periode)
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        st.image(img, width=400)
        st.download_button(
            "Télécharger le PNG", buffer.getvalue(),
            file_name=f"podium_{nom_categorie.replace(' ', '_').replace('—', '')}_{season}.png",
            mime="image/png", key="dl_podium",
        )

# ─────────────────────────────────────────────────────────────
# Power Tiers — équivalent statique du graphique Analytics > PRO > Équipe
# ─────────────────────────────────────────────────────────────
else:
    season = st.selectbox("Saison", seasons, index=len(seasons) - 1, key="power_tiers_season")

    df_teams = get_team_epa_offense_defense(season)
    df_teams["logo_url"] = df_teams["team"].map(logos)

    if df_teams.empty:
        st.warning("Aucune donnée disponible pour cette saison.")
        st.stop()

    if st.button("Générer le visuel", key="generer_power_tiers"):
        img = generer_power_tiers_image(df_teams, season)
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        st.image(img, width=400)
        st.download_button("Télécharger le PNG", buffer.getvalue(),
                            file_name=f"power_tiers_{season}.png", mime="image/png", key="dl_power_tiers")

render_footer()
