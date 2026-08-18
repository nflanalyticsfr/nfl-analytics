"""
Visite l'app pour l'empêcher de passer en veille. Streamlit Community
Cloud endort toute app sans trafic depuis 12h (seuil documenté,
récemment réduit depuis 24h).

Un simple curl ne suffit pas ici : Streamlit a besoin d'une vraie
connexion WebSocket pour compter une visite comme du trafic, et si l'app
est déjà endormie, la réveiller nécessite de cliquer le bouton
"Yes, get this app back up!" — impossible avec une simple requête HTTP.
D'où Playwright plutôt qu'un requests.get().

Appelé par .github/workflows/keep_awake.yml toutes les 6 heures (marge
confortable sous le seuil de 12h).
"""
import os

from playwright.sync_api import sync_playwright

URL = os.environ.get("APP_URL", "https://nfl-analytics-fr.streamlit.app")

with sync_playwright() as p:
    navigateur = p.chromium.launch()
    page = navigateur.new_page()
    page.goto(URL, timeout=60000)
    page.wait_for_timeout(3000)

    # Si l'app dormait, un bouton de réveil apparaît — on le cherche et on
    # clique dessus. S'il n'apparaît pas (app déjà éveillée), on passe.
    try:
        bouton = page.get_by_text("get this app back up", exact=False)
        if bouton.is_visible(timeout=3000):
            bouton.click()
            print("App endormie détectée — clic sur le bouton de réveil, attente du redémarrage...")
            page.wait_for_timeout(15000)
        else:
            print("App déjà éveillée.")
    except Exception:
        print("Pas de bouton de réveil détecté (app déjà éveillée).")

    print(f"Visite effectuée : {URL}")
    navigateur.close()
