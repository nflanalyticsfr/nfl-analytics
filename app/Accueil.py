"""Point d'entrée de l'app (Main file path sur Streamlit Cloud).

Routeur minimal : st.set_page_config ne peut être appelé qu'une seule fois
par session, donc c'est centralisé ici plutôt que répété sur chaque page
(c'était le cas avant, chaque page appelait son propre set_page_config).
Contenu de la page d'accueil elle-même déplacé vers views/0_Accueil.py.

ATTENTION — le dossier s'appelle "views/", pas "pages/", et c'est
volontaire, pas cosmétique : Streamlit traite tout dossier nommé
littéralement "pages" à côté du script principal comme un signal
d'auto-détection legacy (mécanisme "_mpa_v1"). Dès qu'il existe, Streamlit
scanne ce dossier ET traite Accueil.py lui-même comme une page — les DEUX
donnent le même slug "Accueil" une fois les préfixes numériques retirés
(Accueil.py → "Accueil", 0_Accueil.py → "Accueil") → collision, et
St.set_page_config/st.navigation ci-dessous ne sont même jamais exécutés
(l'auto-détection court-circuite complètement l'exécution du script). Ne
JAMAIS renommer "views/" en "pages/", même si ça semble plus intuitif.

IMPORTANT — url_path : tous les liens internes de l'app (_lien_equipe,
_lien_joueur, _lien_match, render_navigation_card, render_page_link dans
queries.py) sont des <a href="..."> en dur qui pointent vers ces slugs
exacts (ex. href="Equipes?team=MIA"). Ne pas changer une valeur url_path
ci-dessous sans grep "_attrs_lien(" et mettre à jour queries.py en même
temps, sinon les liens internes cassent silencieusement (pas d'erreur,
juste un lien mort).

Ordre d'affichage dans la sidebar = ordre de la liste ci-dessous. Pour
réordonner les pages, il suffit de changer l'ordre de la liste — les noms
de fichiers (et leurs préfixes numériques, conservés pour l'historique git
et le tri dans l'explorateur de fichiers) n'ont plus d'effet sur l'ordre
ni sur l'URL depuis cette migration vers st.navigation().
"""
import streamlit as st

st.set_page_config(page_title="NFL Analytics FR", layout="wide", page_icon="🏈")

pages = [
    st.Page("views/0_Accueil.py", title="Accueil", icon="🏠", default=True),
    st.Page("views/3_Matchs.py", title="Matchs", icon="📅", url_path="Matchs"),
    st.Page("views/1_Equipes.py", title="Équipes", icon="🏈", url_path="Equipes"),
    st.Page("views/2_Joueurs.py", title="Joueurs", icon="👤", url_path="Joueurs"),
    st.Page("views/4_Classements.py", title="Classements", icon="🏆", url_path="Classements"),
    st.Page("views/5_Analytics.py", title="Analytics", icon="📈", url_path="Analytics"),
    st.Page("views/6_Comparer.py", title="Comparer", icon="⚖️", url_path="Comparer"),
    st.Page("views/8_Cartes_Sociales.py", title="Cartes Sociales", icon="📱", url_path="Cartes_Sociales"),
    st.Page("views/7_A_propos.py", title="À propos", icon="ℹ️", url_path="A_propos"),
]

st.navigation(pages).run()
