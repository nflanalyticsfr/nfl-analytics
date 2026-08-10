"""
Constantes partagées entre les pages de l'app et les scripts d'ingestion.

Ces valeurs ne changent qu'une fois par an (nouvelle saison NFL). Les
centraliser ici évite le type d'incohérence trouvé lors de l'audit :
`fetch_plays.py` et `fetch_static.py` s'étaient arrêtés à 2025 alors que
`fetch_rosters.py` allait déjà jusqu'à 2026 — les trois scripts avaient
chacun leur propre `range(...)` codé en dur, jamais mis à jour ensemble.

À la bascule de saison (généralement fin août / début septembre), il
suffit de changer CURRENT_SEASON ici puis de relancer le pipeline
d'ingestion (voir scripts/README.md) pour que toute l'app et tous les
scripts soient synchronisés.
"""

FIRST_SEASON = 2015
CURRENT_SEASON = 2026

# Équipe pré-sélectionnée sur la page Teams quand aucune n'est indiquée
# dans l'URL (?team=...).
DEFAULT_TEAM = "MIA"  # Miami Dolphins
