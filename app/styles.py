"""
Feuilles de style partagées, séparées du code Python des pages.

HOME_CSS ne contient aucune valeur dynamique (pas d'interpolation) —
c'est un bloc statique, donc une simple chaîne plutôt qu'un f-string.
Les valeurs de statistiques (stats['total_plays'], etc.) restent
injectées directement dans Accueil.py, à l'endroit où le HTML du hero est
construit, puisqu'elles dépendent des données chargées à l'exécution.
"""

HOME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&family=Space+Mono:wght@400;700&display=swap');

html, body, [class*="css"] { font-family: 'Manrope', sans-serif; }

.block-container { padding-top: 4rem !important; padding-bottom: 2rem !important; }
[data-testid="stVerticalBlock"] { gap: 0.6rem; }
hr { margin: 0.6rem 0 !important; }
h1, h2, h3 { margin-top: 0.2rem !important; margin-bottom: 0.3rem !important; }

[data-testid="stMetric"] {
    background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 10px;
    padding: 10px 14px !important;
}
[data-testid="stMetricLabel"] { font-size: 11px !important; color: #64748B !important; }
[data-testid="stMetricValue"] { font-size: 22px !important; }
.hero-banner {
    position: relative; overflow: hidden;
    background: linear-gradient(180deg, #0F172A 0%, #111C33 100%);
    background-image:
        repeating-linear-gradient(90deg, rgba(255,255,255,0.05) 0px, rgba(255,255,255,0.05) 1px, transparent 1px, transparent 64px),
        linear-gradient(180deg, #0F172A 0%, #111C33 100%);
    border-radius: 16px; padding: 18px 32px 0; margin-bottom: 0; text-align: center;
}
.hero-eyebrow { font-family: 'Space Mono', monospace; font-size: 11px; letter-spacing: 0.14em; color: #EA580C; text-transform: uppercase; margin-bottom: 4px; }
.hero-title { font-weight: 800; font-size: clamp(1.3rem, 2.6vw, 1.8rem); color: #CBD5E1 !important; margin: 0 0 3px; letter-spacing: -0.02em; }
.hero-tagline { font-size: 13px; color: #94A3B8; margin: 0 0 12px; }

.stat-strip {
    display: flex; justify-content: center; gap: 36px;
    background: #111C33; padding: 10px 32px; border-radius: 0 0 16px 16px;
    margin-bottom: 24px; flex-wrap: wrap;
}
.stat-item { text-align: center; }
.stat-value { font-family: 'Space Mono', monospace; font-size: 17px; font-weight: 700; color: #EA580C; }
.stat-label { font-size: 10px; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.06em; margin-top: 1px; }

.nav-card {
    background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 12px;
    padding: 16px 18px; height: 100%; box-sizing: border-box;
    transition: border-color 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
}
.nav-card:hover {
    border-color: #EA580C; transform: translateY(-2px);
    box-shadow: 0 4px 14px rgba(234, 88, 12, 0.14);
}
.nav-card-icon { font-size: 22px; margin-bottom: 6px; }
.nav-card-title { font-weight: 700; font-size: 15px; color: #1E293B !important; margin-bottom: 4px; text-decoration: none !important; }
.nav-card-desc { font-size: 12.5px; color: #64748B !important; line-height: 1.4; margin: 0; text-decoration: none !important; }
.nav-card-link, .nav-card-link:link, .nav-card-link:visited, .nav-card-link:hover, .nav-card-link:active {
    display: block; cursor: pointer; text-decoration: none !important; color: inherit !important;
}

.text-link-wrap, .text-link-wrap:link, .text-link-wrap:visited, .text-link-wrap:hover, .text-link-wrap:active {
    display: inline-block; text-decoration: none !important; margin-top: 6px;
}
.text-link { font-size: 13px; font-weight: 600; color: #475569 !important; transition: color 0.15s ease; text-decoration: none !important; }
.text-link-wrap:hover .text-link { color: #EA580C !important; }
</style>
"""

# Style minimal réutilisé par les autres pages (import Manrope, sans le hero).
# Évite de dupliquer ce bloc de 4 lignes dans chaque fichier app/views/*.py.
PAGE_FONT_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Manrope', sans-serif; }

.block-container { padding-top: 4rem !important; padding-bottom: 2rem !important; }
[data-testid="stVerticalBlock"] { gap: 0.6rem; }
hr { margin: 0.6rem 0 !important; }
h1, h2, h3 { margin-top: 0.2rem !important; margin-bottom: 0.3rem !important; }

[data-testid="stMetric"] {
    background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 10px;
    padding: 10px 14px !important;
}
[data-testid="stMetricLabel"] { font-size: 11px !important; color: #64748B !important; }
[data-testid="stMetricValue"] { font-size: 22px !important; }
</style>
"""
