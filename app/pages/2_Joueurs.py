import streamlit as st
import plotly.graph_objects as go
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from queries import (
    get_available_seasons, get_team_colors, get_team_logos,
    get_player_search_list, get_player_bio, get_player_passing_season,
    get_player_pressure_season, get_player_rushing_season, get_player_receiving_season,
    get_player_weekly_trend, get_player_games_played, convertir_taille_poids,
    get_qb_full_rankings, get_rb_full_rankings, get_wr_full_rankings, get_def_full_rankings, get_rank_label,
    get_player_defensive_season, get_player_defensive_weekly_trend,
    render_global_search, render_footer, render_header,
)
from styles import PAGE_FONT_CSS

st.set_page_config(page_title="Joueurs", layout="wide")

st.markdown(PAGE_FONT_CSS, unsafe_allow_html=True)
render_header()
render_global_search()

st.title("Joueurs")

seasons = sorted(get_available_seasons(), reverse=True)

# Un lien entrant (?player=...&season=...) doit présélectionner la bonne
# saison : sans ça, un joueur absent de la saison affichée par défaut
# (la plus récente) ne serait pas retrouvé plus bas et le filtre retomberait
# silencieusement sur le premier joueur de la liste.
season_cible = st.query_params.get("season")
season_cible = int(season_cible) if season_cible and season_cible.isdigit() else None
index_season = seasons.index(season_cible) if season_cible in seasons else 0
season = st.selectbox("Saison", seasons, index=index_season, key="player_season")

if "player_filters_reset" not in st.session_state:
    st.session_state["player_filters_reset"] = 0
suffixe_reset = st.session_state["player_filters_reset"]

joueurs = get_player_search_list(season)

col_search, col_team, col_raz = st.columns([2, 1, 1])

with col_search:
    recherche = st.text_input(
        "Rechercher un joueur", placeholder="Ex : Mahomes", key=f"player_search_box_{suffixe_reset}"
    )

# La recherche filtre d'abord — les options du filtre équipe reflètent
# ensuite seulement les équipes des joueurs trouvés, pas la liste complète
# (sinon chercher "watt" laissait un filtre équipe avec les 32 équipes,
# alors que 3-4 seulement ont un joueur nommé Watt).
joueurs_recherche = (
    joueurs[joueurs["player_name"].str.contains(recherche, case=False, na=False)]
    if recherche else joueurs
)

with col_team:
    equipes_dispo = ["Toutes"] + sorted(joueurs_recherche["team"].dropna().unique().tolist())
    filtre_equipe = st.selectbox(
        "Filtrer par équipe", equipes_dispo, key=f"player_team_filter_{suffixe_reset}"
    )

with col_raz:
    st.write("")
    if st.button("Réinitialiser les filtres", key="reset_player_filters"):
        # Changer la clé des widgets (plutôt que vider leur session_state)
        # force Streamlit à les recréer à neuf — vider juste la clé ne
        # garantit pas toujours que text_input se réaffiche vide.
        st.session_state["player_filters_reset"] += 1
        st.rerun()

joueurs_filtres = (
    joueurs_recherche if filtre_equipe == "Toutes" else joueurs_recherche[joueurs_recherche["team"] == filtre_equipe]
)

if joueurs_filtres.empty:
    st.warning("Aucun joueur trouvé pour ce filtre.")
    st.stop()

initial_id = st.query_params.get("player")
noms = joueurs_filtres["player_name"].tolist()
index_defaut = 0
if initial_id and initial_id in joueurs_filtres["player_id"].values:
    nom_initial = joueurs_filtres[joueurs_filtres["player_id"] == initial_id]["player_name"].iloc[0]
    if nom_initial in noms:
        index_defaut = noms.index(nom_initial)

nom_choisi = st.selectbox("Joueur", noms, index=index_defaut, key="player_select")
player_id = joueurs_filtres[joueurs_filtres["player_name"] == nom_choisi]["player_id"].iloc[0]
st.query_params["player"] = player_id

st.divider()

# ─── Bio (commune aux deux onglets, reste hors tabs) ───
bio = get_player_bio(player_id, season)
if bio.empty:
    st.error("Aucune information disponible pour ce joueur.")
    st.stop()
bio = bio.iloc[0]

colors = get_team_colors()
logos = get_team_logos()
couleur_equipe = colors.get(bio["team"], "#374151")
logo_url = logos.get(bio["team"], "")
photo_url = bio["headshot_url"]

col_photo, col_info = st.columns([1, 3])
with col_photo:
    if isinstance(photo_url, str) and photo_url:
        st.markdown(
            f'<img src="{photo_url}" style="width:140px;height:140px;border-radius:50%;'
            f'object-fit:cover;border:4px solid {couleur_equipe};">',
            unsafe_allow_html=True,
        )
    else:
        initiales = "".join([p[0] for p in bio["player_name"].split(" ") if p])[:2].upper()
        st.markdown(
            f'<div style="width:140px;height:140px;border-radius:50%;background:{couleur_equipe};'
            f'display:flex;align-items:center;justify-content:center;color:white;'
            f'font-weight:700;font-size:44px;">{initiales}</div>',
            unsafe_allow_html=True,
        )

with col_info:
    st.markdown(f"""
    <div style="font-size:32px;font-weight:800;color:{couleur_equipe};">{bio['player_name']}</div>
    <div style="font-size:16px;color:#64748B;display:flex;align-items:center;gap:8px;margin-top:4px;">
        <img src="{logo_url}" height="24">{bio['team']} · {bio['position']}
    </div>
    """, unsafe_allow_html=True)

    metres, poids_kg = convertir_taille_poids(bio["height"], bio["weight"])
    age = int(bio["age"]) if bio["age"] == bio["age"] else "—"
    matchs = get_player_games_played(player_id, season)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Âge", age)
    col2.metric("Taille", f"{metres:.2f} m" if metres else "—")
    col3.metric("Poids", f"{poids_kg} kg" if poids_kg else "—")
    col4.metric("Matchs joués", matchs)

    # Texte simple, pas st.metric : évite la troncature sur les noms longs.
    universite = bio["college"] if isinstance(bio["college"], str) and bio["college"] else "—"
    experience = f"{int(bio['years_exp'])} ans" if bio["years_exp"] == bio["years_exp"] else "—"
    st.write(f"**Université :** {universite}  ·  **Expérience :** {experience}")

st.divider()

# ─── Données communes, calculées une seule fois, réutilisées dans les deux onglets ───
passing = get_player_passing_season(player_id, season)
rushing = get_player_rushing_season(player_id, season)
receiving = get_player_receiving_season(player_id, season)
defense = get_player_defensive_season(player_id, season)

a_passing = not passing.empty and passing["dropbacks"].iloc[0] and passing["dropbacks"].iloc[0] > 0
a_rushing = not rushing.empty and rushing["courses"].iloc[0] and rushing["courses"].iloc[0] > 0
a_receiving = not receiving.empty and receiving["cibles"].iloc[0] and receiving["cibles"].iloc[0] > 0
a_defense = not defense.empty and (
    defense["tacles_totaux"].iloc[0] + defense["sacks_totaux"].iloc[0]
    + defense["interceptions"].iloc[0] + defense["passes_defendues"].iloc[0]
    + defense["fumbles_forces"].iloc[0]
) > 0

roles_actifs = []
if a_passing:
    roles_actifs.append(("passing", "Passing"))
if a_rushing:
    roles_actifs.append(("rushing", "Rushing"))
if a_receiving:
    roles_actifs.append(("receiving", "Receiving"))

onglet_overview, onglet_avance = st.tabs(["Overview", "Advanced Analytics ⭐ PRO"])

# ═══════════════════════════════════════════════════════════════════════
# OVERVIEW — accès libre : statistiques "classiques" (yards, TD, tacles...)
# ═══════════════════════════════════════════════════════════════════════
with onglet_overview:

    if a_passing:
        st.subheader("Passing")
        p = passing.iloc[0]
        classement_qb = get_qb_full_rankings(season)
        col1, col2, col3 = st.columns(3)
        col1.metric("Tentatives", int(p["tentatives"]), get_rank_label(classement_qb, player_id, "tentatives"))
        col2.metric("Complétions", int(p["completions"]), get_rank_label(classement_qb, player_id, "completions"))
        col3.metric("Yards", f"{int(p['yards']):,}" if p["yards"] == p["yards"] else "—",
                    get_rank_label(classement_qb, player_id, "yards"))
        col4, col5 = st.columns(2)
        col4.metric("TD", int(p["td"]), get_rank_label(classement_qb, player_id, "td"))
        col5.metric("INT", int(p["interceptions"]),
                    get_rank_label(classement_qb, player_id, "interceptions", ascending=True))
        st.divider()

    if a_rushing:
        st.subheader("Rushing")
        r = rushing.iloc[0]
        classement_rb = get_rb_full_rankings(season)
        col1, col2, col3 = st.columns(3)
        col1.metric("Courses", int(r["courses"]), get_rank_label(classement_rb, player_id, "courses"))
        col2.metric("Yards", f"{int(r['yards']):,}" if r["yards"] == r["yards"] else "—",
                    get_rank_label(classement_rb, player_id, "yards"))
        col3.metric("TD", int(r["td"]), get_rank_label(classement_rb, player_id, "td"))
        st.divider()

    if a_receiving:
        st.subheader("Receiving")
        rc = receiving.iloc[0]
        classement_wr = get_wr_full_rankings(season)
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Cibles", int(rc["cibles"]), get_rank_label(classement_wr, player_id, "cibles"))
        col2.metric("Réceptions", int(rc["receptions"]), get_rank_label(classement_wr, player_id, "receptions"))
        col3.metric("Yards", f"{int(rc['yards']):,}" if rc["yards"] == rc["yards"] else "—",
                    get_rank_label(classement_wr, player_id, "yards"))
        col4.metric("TD", int(rc["td"]), get_rank_label(classement_wr, player_id, "td"))
        st.divider()

    if a_defense:
        st.subheader("Defense")
        d = defense.iloc[0]
        classement_def = get_def_full_rankings(season)
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Tacles (total)", int(d["tacles_totaux"]),
                    get_rank_label(classement_def, player_id, "tacles_totaux"))
        col2.metric("Tacles pour perte", int(d["tacles_pour_perte"]),
                    get_rank_label(classement_def, player_id, "tacles_pour_perte"))
        col3.metric("Sacks", f"{d['sacks_totaux']:.1f}",
                    get_rank_label(classement_def, player_id, "sacks_totaux"))
        col4.metric("Pressions QB", int(d["pressions_qb"]),
                    get_rank_label(classement_def, player_id, "pressions_qb"))

        col1, col2, col3 = st.columns(3)
        col1.metric("Interceptions", int(d["interceptions"]),
                    get_rank_label(classement_def, player_id, "interceptions"))
        col2.metric("Passes défendues", int(d["passes_defendues"]),
                    get_rank_label(classement_def, player_id, "passes_defendues"))
        col3.metric("Fumbles forcés", int(d["fumbles_forces"]),
                    get_rank_label(classement_def, player_id, "fumbles_forces"))
        st.divider()

    if a_defense:
        st.subheader("Tendance défensive — semaine par semaine")
        st.caption("Volume (tacles + sacks + interceptions + passes défendues + fumbles forcés).")
        df_def_trend = get_player_defensive_weekly_trend(player_id, season)
        fig_def = go.Figure()
        fig_def.add_trace(go.Bar(
            x=df_def_trend["week"], y=df_def_trend["volume_defensif"],
            marker_color=couleur_equipe, name="Volume défensif",
        ))
        fig_def.update_layout(xaxis_title="Semaine", yaxis_title="Actions défensives", height=400)
        fig_def.update_xaxes(dtick=1)
        st.plotly_chart(fig_def, width='stretch', key=f"defense_trend_{player_id}_{season}")

    if not a_passing and not a_rushing and not a_receiving and not a_defense:
        st.info("Aucune statistique disponible pour ce joueur sur cette saison.")

# ═══════════════════════════════════════════════════════════════════════
# ADVANCED ANALYTICS — EPA, CPOE, air yards, pression. Aucun paiement
# n'est en place : contenu visible, juste étiqueté comme futur payant.
# ═══════════════════════════════════════════════════════════════════════
with onglet_avance:
    st.caption("⭐ Ces statistiques feront partie de **NFL Analytics Pro** — en accès libre pour l'instant.")

    if a_passing:
        st.subheader("Passing — EPA & efficacité")
        p = passing.iloc[0]
        classement_qb = get_qb_full_rankings(season)
        col1, col2, col3 = st.columns(3)
        col1.metric("EPA/Dropback", f"{p['epa_per_play']:.3f}",
                    get_rank_label(classement_qb, player_id, "epa_per_play"))
        col2.metric("CPOE", f"{p['cpoe']:+.1f}%" if p["cpoe"] == p["cpoe"] else "—",
                    get_rank_label(classement_qb, player_id, "cpoe"))
        col3.metric("Air Yards Moy.", f"{p['air_yards_moy']:.1f}" if p["air_yards_moy"] == p["air_yards_moy"] else "—",
                    get_rank_label(classement_qb, player_id, "air_yards_moy"))

        pression = get_player_pressure_season(player_id, season)
        if not pression.empty:
            pr = pression.iloc[0]
            st.write("**Pression subie**")
            col1, col2, col3 = st.columns(3)
            col1.metric("Dropbacks pressés", f"{pr['pressions_subies']:.0f}" if pr["pressions_subies"] == pr["pressions_subies"] else "—",
                        get_rank_label(classement_qb, player_id, "pressions_subies", ascending=True))
            col2.metric("Taux de pression", f"{pr['taux_pression']:.1%}" if pr["taux_pression"] == pr["taux_pression"] else "—",
                        get_rank_label(classement_qb, player_id, "taux_pression", ascending=True))
            col3.metric("Sacks subis", f"{pr['sacks_subis']:.0f}" if pr["sacks_subis"] == pr["sacks_subis"] else "—",
                        get_rank_label(classement_qb, player_id, "sacks_subis", ascending=True))
        st.divider()

    if a_rushing:
        st.subheader("Rushing — EPA")
        r = rushing.iloc[0]
        classement_rb = get_rb_full_rankings(season)
        st.metric("EPA/Course", f"{r['epa_per_play']:.3f}",
                  get_rank_label(classement_rb, player_id, "epa_per_play"))
        st.divider()

    if a_receiving:
        st.subheader("Receiving — EPA & profil de réception")
        rc = receiving.iloc[0]
        classement_wr = get_wr_full_rankings(season)
        col1, col2, col3 = st.columns(3)
        col1.metric("EPA/Cible", f"{rc['epa_per_play']:.3f}",
                    get_rank_label(classement_wr, player_id, "epa_per_play"))
        col2.metric("Air Yards Moy.", f"{rc['air_yards_moy']:.1f}" if rc["air_yards_moy"] == rc["air_yards_moy"] else "—",
                    get_rank_label(classement_wr, player_id, "air_yards_moy"))
        col3.metric("YAC Moy.", f"{rc['yac_moy']:.1f}" if rc["yac_moy"] == rc["yac_moy"] else "—",
                    get_rank_label(classement_wr, player_id, "yac_moy"))
        st.divider()

    if roles_actifs:
        st.subheader("Tendance EPA — semaine par semaine")
        fig = go.Figure()
        styles = [dict(width=3), dict(width=2, dash="dot"), dict(width=2, dash="dash")]
        for (role, label), style in zip(roles_actifs, styles):
            df_trend = get_player_weekly_trend(player_id, season, role)
            fig.add_trace(go.Scatter(
                x=df_trend["week"], y=df_trend["epa_per_play"], mode="lines+markers",
                name=label, line=dict(color=couleur_equipe, **style),
            ))
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        fig.update_layout(xaxis_title="Semaine", yaxis_title="EPA par play", height=400)
        fig.update_xaxes(dtick=1)
        st.plotly_chart(fig, width='stretch', key=f"epa_trend_{player_id}_{season}")
    else:
        st.info("Aucune donnée EPA hebdomadaire disponible.")

render_footer()
