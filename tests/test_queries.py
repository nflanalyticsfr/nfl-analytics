"""
Tests unitaires pour les fonctions de queries.py.

Ces tests vérifient que :
- Les fonctions retournent les bonnes colonnes.
- Les fonctions gèrent correctement les paramètres.
- Les calculs (EPA, success rate, etc.) sont cohérents.

Note : Ces tests nécessitent que la base DuckDB (database/nfl.duckdb) soit présente.
"""

import pytest
import sys
from pathlib import Path

# Ajouter le chemin vers app/ pour importer queries
sys.path.append(str(Path(__file__).resolve().parent.parent / "app"))

# Importer les fonctions à tester
from queries import (
    get_connection,
    get_available_seasons,
    get_weeks_for_season,
    get_team_colors,
    get_team_logos,
    get_all_teams,
    get_all_teams_records,
    get_team_epa_offense_defense,
    get_player_search_list,
    get_games_for_week,
    get_home_stats,
    get_home_current_season,
    couleur_texte_contraste,
    convertir_taille_poids,
)


# ───────────────────────────────────────────────────────────────────────────────
# Fixtures
# ───────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def connection():
    """Retourne une connexion DuckDB pour les tests."""
    return get_connection()


@pytest.fixture
def sample_season():
    """Retourne une saison valide pour les tests (la plus récente disponible)."""
    seasons = get_available_seasons()
    if not seasons:
        pytest.skip("Aucune saison disponible dans la base de données.")
    return max(seasons)  # Dernière saison disponible


# ───────────────────────────────────────────────────────────────────────────────
# Tests pour les utilitaires
# ───────────────────────────────────────────────────────────────────────────────

class TestUtilitaires:
    """Tests pour les fonctions utilitaires."""

    def test_get_available_seasons_retourne_liste(self):
        """Vérifie que get_available_seasons retourne une liste non vide."""
        seasons = get_available_seasons()
        assert isinstance(seasons, list)
        assert len(seasons) > 0

    def test_get_available_seasons_ordonnee(self):
        """Vérifie que les saisons sont retournées dans l'ordre croissant."""
        seasons = get_available_seasons()
        assert seasons == sorted(seasons)

    def test_get_weeks_for_season_retourne_liste(self, sample_season):
        """Vérifie que get_weeks_for_season retourne une liste non vide."""
        weeks = get_weeks_for_season(sample_season)
        assert isinstance(weeks, list)
        assert len(weeks) > 0

    def test_get_team_colors_retourne_dict(self):
        """Vérifie que get_team_colors retourne un dictionnaire non vide."""
        colors = get_team_colors()
        assert isinstance(colors, dict)
        assert len(colors) > 0
        # Vérifier que les clés sont des abréviations d'équipes (3 lettres)
        for team_abbr in colors.keys():
            assert isinstance(team_abbr, str)
            assert len(team_abbr) <= 3

    def test_get_team_logos_retourne_dict(self):
        """Vérifie que get_team_logos retourne un dictionnaire non vide."""
        logos = get_team_logos()
        assert isinstance(logos, dict)
        assert len(logos) > 0
        # Vérifier que les valeurs sont des URLs
        for logo_url in logos.values():
            assert isinstance(logo_url, str)
            assert logo_url.startswith("http")

    def test_couleur_texte_contraste_noir(self):
        """Vérifie que couleur_texte_contraste retourne du noir pour un fond clair."""
        assert couleur_texte_contraste("#FFFFFF") == "#000000"  # Blanc -> Noir
        assert couleur_texte_contraste("#F0F0F0") == "#000000"  # Gris clair -> Noir

    def test_couleur_texte_contraste_blanc(self):
        """Vérifie que couleur_texte_contraste retourne du blanc pour un fond sombre."""
        assert couleur_texte_contraste("#000000") == "#ffffff"  # Noir -> Blanc
        assert couleur_texte_contraste("#1A1A1A") == "#ffffff"  # Gris foncé -> Blanc

    def test_convertir_taille_poids_pouces(self):
        """Vérifie la conversion de la taille en pouces vers mètres."""
        metres, _ = convertir_taille_poids(72, None)  # 6 pieds = 72 pouces
        assert metres is not None
        assert abs(metres - 1.8288) < 0.01  # 72 pouces = 1.8288 mètres

    def test_convertir_taille_poids_format_pieds_pouces(self):
        """Vérifie la conversion de la taille au format '6-2' vers mètres."""
        metres, _ = convertir_taille_poids("6-2", None)  # 6 pieds 2 pouces = 74 pouces
        assert metres is not None
        assert abs(metres - 1.8796) < 0.01  # 74 pouces = 1.8796 mètres

    def test_convertir_taille_poids_livres(self):
        """Vérifie la conversion du poids en livres vers kilogrammes.

        poids_kg est arrondi au kg entier (round() sans ndigits) : c'est
        volontaire, c'est ce qui est affiché tel quel dans la fiche joueur
        (f"{poids_kg} kg"), une précision décimale n'aurait aucun sens pour
        un poids de joueur listé de toute façon approximatif.
        """
        _, kg = convertir_taille_poids(None, 200)  # 200 livres
        assert kg is not None
        assert kg == 91  # 200 livres = 90.7184 kg, arrondi à 91 kg


# ───────────────────────────────────────────────────────────────────────────────
# Tests pour les équipes
# ───────────────────────────────────────────────────────────────────────────────

class TestEquipes:
    """Tests pour les fonctions liées aux équipes."""

    def test_get_all_teams_retourne_dataframe(self):
        """Vérifie que get_all_teams retourne un DataFrame non vide."""
        df = get_all_teams()
        assert df is not None
        assert len(df) > 0
        # Vérifier les colonnes attendues
        assert "team_abbr" in df.columns
        assert "team_name" in df.columns

    def test_get_all_teams_32_equipes(self):
        """Vérifie que get_all_teams retourne les 32 équipes actives."""
        df = get_all_teams()
        assert len(df) == 32  # 32 équipes actives en NFL

    def test_get_all_teams_records_retourne_dataframe(self, sample_season):
        """Vérifie que get_all_teams_records retourne un DataFrame avec les bonnes colonnes."""
        df = get_all_teams_records(sample_season)
        assert df is not None
        assert len(df) > 0
        # Vérifier les colonnes attendues
        assert "wins" in df.columns
        assert "losses" in df.columns
        assert "ties" in df.columns
        assert "win_pct" in df.columns

    def test_get_team_epa_offense_defense_retourne_dataframe(self, sample_season):
        """Vérifie que get_team_epa_offense_defense retourne un DataFrame avec les bonnes colonnes."""
        df = get_team_epa_offense_defense(sample_season)
        assert df is not None
        assert len(df) > 0
        # Vérifier les colonnes attendues
        assert "team" in df.columns
        assert "team_name" in df.columns
        assert "epa_offense" in df.columns
        assert "epa_defense" in df.columns


# ───────────────────────────────────────────────────────────────────────────────
# Tests pour les joueurs
# ───────────────────────────────────────────────────────────────────────────────

class TestJoueurs:
    """Tests pour les fonctions liées aux joueurs."""

    def test_get_player_search_list_retourne_dataframe(self, sample_season):
        """Vérifie que get_player_search_list retourne un DataFrame non vide."""
        df = get_player_search_list(sample_season)
        assert df is not None
        assert len(df) > 0
        # Vérifier les colonnes attendues
        assert "player_id" in df.columns
        assert "player_name" in df.columns


# ───────────────────────────────────────────────────────────────────────────────
# Tests pour les matchs
# ───────────────────────────────────────────────────────────────────────────────

class TestMatchs:
    """Tests pour les fonctions liées aux matchs."""

    def test_get_games_for_week_retourne_dataframe(self, sample_season):
        """Vérifie que get_games_for_week retourne un DataFrame non vide pour la semaine 1."""
        df = get_games_for_week(sample_season, 1)
        assert df is not None
        assert len(df) > 0
        # Vérifier les colonnes attendues
        assert "game_id" in df.columns
        assert "home_team" in df.columns
        assert "away_team" in df.columns


# ───────────────────────────────────────────────────────────────────────────────
# Tests pour la page d'accueil
# ───────────────────────────────────────────────────────────────────────────────

class TestAccueil:
    """Tests pour les fonctions de la page d'accueil."""

    def test_get_home_stats_retourne_dict(self):
        """Vérifie que get_home_stats retourne un dictionnaire avec les bonnes clés."""
        stats = get_home_stats()
        assert isinstance(stats, dict)
        # Vérifier les clés attendues
        assert "total_plays" in stats
        assert "total_games" in stats
        assert "total_teams" in stats
        assert "nb_saisons" in stats
        assert "saison_min" in stats
        assert "saison_max" in stats

    def test_get_home_current_season_retourne_int(self):
        """Vérifie que get_home_current_season retourne un entier."""
        season = get_home_current_season()
        assert isinstance(season, int)
        assert season > 2000  # Une saison NFL valide


# ───────────────────────────────────────────────────────────────────────────────
# Tests d'intégrité des données
# ───────────────────────────────────────────────────────────────────────────────

class TestIntegrite:
    """Tests pour vérifier l'intégrité des données."""

    def test_equipes_presentes_dans_teams(self):
        """Vérifie que toutes les équipes retournées par get_all_teams sont dans la table teams."""
        df_teams = get_all_teams()
        team_abbrs = df_teams["team_abbr"].tolist()
        
        # Récupérer toutes les abréviations d'équipes depuis la table teams
        con = get_connection()
        df_all_teams = con.execute("SELECT team_abbr FROM teams").fetchdf()
        all_abbrs = df_all_teams["team_abbr"].tolist()
        
        # Vérifier que toutes les abréviations sont valides
        for abbr in team_abbrs:
            assert abbr in all_abbrs, f"Abréviation d'équipe invalide : {abbr}"

    def test_saisons_dans_plays(self, sample_season):
        """Vérifie que la saison retournée par get_available_seasons est présente dans plays."""
        seasons = get_available_seasons()
        con = get_connection()
        df_plays_seasons = con.execute("SELECT DISTINCT season FROM plays").fetchdf()
        plays_seasons = df_plays_seasons["season"].tolist()
        
        for season in seasons:
            assert season in plays_seasons, f"Saison {season} non trouvée dans plays"
