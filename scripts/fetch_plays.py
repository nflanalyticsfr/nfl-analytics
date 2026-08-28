import nfl_data_py as nfl
import nflreadpy as nflread
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import traceback

# BUG CORRIGÉ LORS DE L'AUDIT : ce fichier utilisait `range(2015, 2026)`,
# qui exclut 2026 (comportement standard de range en Python) — la saison
# en cours n'était donc jamais téléchargée par ce script, contrairement à
# fetch_rosters.py qui, lui, allait bien jusqu'à 2026. Utiliser les
# constantes partagées évite que ce type de désynchronisation se reproduise.
sys.path.append(str(Path(__file__).resolve().parent.parent / "app"))
from constants import FIRST_SEASON, CURRENT_SEASON

SEASONS = list(range(FIRST_SEASON, CURRENT_SEASON + 1))

COLONNES_PLAYS = [
    "play_id", "game_id", "season", "week", "season_type",
    "posteam", "defteam", "posteam_type", "home_team", "away_team",
    "down", "ydstogo", "yardline_100", "goal_to_go",
    "qtr", "game_half", "game_seconds_remaining", "half_seconds_remaining", "quarter_seconds_remaining",
    "score_differential",
    "play_type", "pass", "rush", "qb_dropback", "qb_kneel", "qb_spike", "aborted_play",
    "epa", "qb_epa", "success", "wp", "wpa", "ep",
    "complete_pass", "incomplete_pass", "interception",
    "air_yards", "yards_after_catch", "air_epa", "yac_epa",
    "pass_location", "pass_length", "cp", "cpoe",
    "rushing_yards", "run_location", "run_gap", "qb_scramble",
    "defense_coverage_type", "defense_man_zone_type", "was_pressure",
    "qb_hit", "sack", "number_of_pass_rushers", "defenders_in_box",
    "shotgun", "no_huddle", "offense_formation", "offense_personnel", "defense_personnel",
    "passer_player_id", "passer_player_name",
    "rusher_player_id", "rusher_player_name",
    "receiver_player_id", "receiver_player_name",
    "yards_gained", "touchdown", "first_down",
    "passing_yards", "receiving_yards", 
    "fumble", "fumble_lost",
    "penalty", "penalty_team", "penalty_yards",
    "solo_tackle_1_player_id", "solo_tackle_1_player_name",
    "solo_tackle_2_player_id", "solo_tackle_2_player_name",
    "assist_tackle_1_player_id", "assist_tackle_1_player_name",
    "assist_tackle_2_player_id", "assist_tackle_2_player_name",
    "assist_tackle_3_player_id", "assist_tackle_3_player_name",
    "assist_tackle_4_player_id", "assist_tackle_4_player_name",
    "tackle_for_loss_1_player_id", "tackle_for_loss_1_player_name",
    "tackle_for_loss_2_player_id", "tackle_for_loss_2_player_name",
    "sack_player_id", "sack_player_name",
    "half_sack_1_player_id", "half_sack_1_player_name",
    "half_sack_2_player_id", "half_sack_2_player_name",
    "qb_hit_1_player_id", "qb_hit_1_player_name",
    "qb_hit_2_player_id", "qb_hit_2_player_name",
    "interception_player_id", "interception_player_name",
    "pass_defense_1_player_id", "pass_defense_1_player_name",
    "pass_defense_2_player_id", "pass_defense_2_player_name",
    "forced_fumble_player_1_player_id", "forced_fumble_player_1_player_name",
    "forced_fumble_player_2_player_id", "forced_fumble_player_2_player_name",
    "desc",
    "drive", "drive_play_count", "fixed_drive_result",
    "drive_start_yard_line", "drive_time_of_possession",
    "drive_ended_with_score", "drive_inside20",
    "total_home_score", "total_away_score",
]

COLONNES_PLAYS = list(dict.fromkeys(COLONNES_PLAYS))

OUTPUT_DIR = Path("data/seasons")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def fetch_season(season: int) -> tuple[int, str, Exception | None]:
    """Télécharge les données play-by-play pour une saison donnée.
    
    Retourne :
        tuple de (season, message, exception) où exception est None si succès.
    """
    try:
        print(f"Téléchargement saison {season}...")
        df = nfl.import_pbp_data([season])

        # Avant le coup d'envoi d'une saison (ou si nflverse n'a pas encore
        # publié), l'API renvoie un DataFrame vide (0 ligne, 0 colonne). Le
        # sauvegarder en parquet produit un fichier sans schéma, qui fait
        # planter load_duckdb.py : read_parquet(..., union_by_name=true) ne
        # sait pas fusionner un fichier sans aucune colonne avec les autres.
        # On saute simplement l'écriture — cette saison sera absente du
        # dossier data/seasons/ et donc ignorée par load_duckdb.py jusqu'à
        # ce qu'un prochain run la trouve réellement disponible.
        if df.empty:
            message = (
                f"  Aucune donnée disponible pour {season} (saison pas encore "
                f"commencée, ou pas encore publiée par nflverse) — fichier "
                f"parquet non créé pour cette saison."
            )
            print(message)
            return (season, message, None)

        presentes = [c for c in COLONNES_PLAYS if c in df.columns]
        absentes = [c for c in COLONNES_PLAYS if c not in df.columns]

        # BUG CORRIGÉ LORS DE L'AUDIT : nfl_data_py (déprécié par nflverse au
        # profit de nflreadpy, plus aucune mise à jour prévue) ne renvoie plus
        # les colonnes cp/cpoe depuis un certain temps, sans lever d'erreur —
        # elles disparaissent juste silencieusement de df.columns. On les
        # récupère via nflreadpy (source officiellement recommandée) et on les
        # rejoint sur (game_id, play_id). On garde nfl_data_py comme source
        # principale malgré la dépréciation : il fournit encore correctement
        # les colonnes de participation (was_pressure, defense_coverage_type,
        # formations...) que nflreadpy seul ne renvoie pas dans load_pbp().
        if "cp" in absentes or "cpoe" in absentes:
            print(f"  cp/cpoe absentes de nfl_data_py pour {season}, récupération via nflreadpy...")
            try:
                cpoe_df = (
                    nflread.load_pbp(season)
                    .select(["game_id", "play_id", "cp", "cpoe"])
                    .to_pandas()
                )
                cpoe_df["game_id"] = cpoe_df["game_id"].astype(str)
                cpoe_df["play_id"] = cpoe_df["play_id"].astype(float)
                df["game_id"] = df["game_id"].astype(str)
                df["play_id"] = df["play_id"].astype(float)
                df = df.merge(cpoe_df, on=["game_id", "play_id"], how="left")
                presentes = [c for c in COLONNES_PLAYS if c in df.columns]
                absentes = [c for c in COLONNES_PLAYS if c not in df.columns]
            except Exception as e:
                print(f"  Échec récupération cp/cpoe via nflreadpy pour {season} : {e}")

        if absentes:
            print(f"  Colonnes absentes pour {season} : {absentes}")

        df = df[presentes]

        output_path = OUTPUT_DIR / f"{season}.parquet"
        df.to_parquet(output_path, index=False)
        message = f"  Sauvegardé : {output_path} ({len(df)} lignes)"
        print(message)
        return (season, message, None)
    except Exception as e:
        error_msg = f"  Échec pour {season} : {e}"
        print(error_msg)
        # Imprimer la trace complète pour le débogage
        traceback.print_exc()
        return (season, error_msg, e)


if __name__ == "__main__":
    # Nombre maximal de threads (par défaut : nombre de CPU * 5 pour les tâches I/O-bound)
    MAX_WORKERS = min(8, len(SEASONS))  # Limiter à 8 pour éviter de surcharger l'API
    
    print(f"Téléchargement des saisons {FIRST_SEASON}-{CURRENT_SEASON} en parallèle (max {MAX_WORKERS} threads)...")
    print(f"Saisons à traiter : {SEASONS}")
    
    # Utiliser ThreadPoolExecutor pour paralléliser les téléchargements
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Soumettre toutes les tâches
        futures = {executor.submit(fetch_season, season): season for season in SEASONS}
        
        # Attendre la fin de toutes les tâches et gérer les résultats
        success_count = 0
        failure_count = 0
        
        for future in as_completed(futures):
            season, message, error = future.result()
            if error is None:
                success_count += 1
            else:
                failure_count += 1
    
    print(f"\nRésumé : {success_count} saisons téléchargées, {failure_count} échecs.")
    if failure_count > 0:
        print("Certaines saisons ont échoué. Vérifiez les messages d'erreur ci-dessus.")
