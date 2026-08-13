import streamlit as st
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from styles import PAGE_FONT_CSS
from queries import render_global_search, render_footer

st.set_page_config(page_title="A propos", layout="wide")
st.markdown(PAGE_FONT_CSS, unsafe_allow_html=True)
render_global_search()
st.title("A propos")

st.write("""
NFL Analytics est un projet indépendant d'exploration des statistiques NFL,
construit avec Python, DuckDB et Streamlit.
""")

st.subheader("Source des données")
st.write("""
Toutes les données proviennent du projet [nflverse](https://github.com/nflverse),
via la librairie `nfl_data_py`, sous licence CC-BY. Les métriques EPA, CPOE et
de pression sont calculées par nflverse à partir du play-by-play officiel.
""")

st.divider()

with st.container(border=True):
    st.subheader("Un avis à partager ?")
    st.write("Ce projet est en phase de test. Tes retours m'aident à savoir quoi améliorer en priorité.")
    st.link_button("Donner mon avis", "https://docs.google.com/forms/d/e/1FAIpQLSdEDhXjqpZjaKdjrIXozICa3qRP9qvOj0pNRtt5L8GMemIPiw/viewform", icon="📝")
render_footer()
