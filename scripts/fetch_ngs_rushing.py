"""Télécharge les statistiques Next Gen Stats (NGS) de course, saison par
saison, pour alimenter le Rush Yards Over Expected (RYOE) affiché dans
Analytics > Advanced Analytics PRO > Joueurs > Course.

Ces données ne viennent pas du play-by-play (nfl_data_py / plays) : ce sont
des agrégats hebdomadaires calculés par la NFL à partir du tracking GPS des
joueurs (Next Gen Stats), disponibles via nflreadpy uniquement, avec
week = 0 pour le total saison régulière — c'est cette ligne qu'on garde ici,
un leaderboard saison n'ayant pas besoin du détail semaine par semaine.

Couverture : à partir de 2016 seulement (avant, pas de tracking GPS league-
wide). Les saisons antérieures à 2016 sont donc silencieusement absentes du
résultat — c'est une limite réelle de la donnée source, pas un bug.
"""
import nflreadpy as nfl
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import traceback

sys.path.append(str(Path(__file__).resolve().parent.parent / "app"))
from constants import FIRST_SEASON, CURRENT_SEASON

PREMIERE_SAISON_NGS = 2016
SEASONS = [s for s in range(FIRST_SEASON, CURRENT_SEASON + 1) if s >= PREMIERE_SAISON_NGS]

OUTPUT_DIR = Path("data/seasons_ngs_rushing")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def fetch_season(season: int) -> tuple[int, str, Exception | None]:
    """Télécharge les NGS course pour une saison donnée (total saison
    régulière uniquement, week = 0).

    Retourne :
        tuple de (season, message, exception) où exception est None si succès.
    """
    try:
        print(f"Téléchargement NGS course saison {season}...")
        df = nfl.load_nextgen_stats(season, stat_type="rushing").to_pandas()

        if df.empty:
            message = f"  Aucune donnée NGS course pour {season}."
            print(message)
            return (season, message, None)

        # week = 0 : ligne agrégée saison régulière fournie directement par
        # la NFL (pas un recalcul maison) — voir docstring du module.
        df = df[(df["week"] == 0) & (df["season_type"] == "REG")].copy()

        colonnes = [
            "season", "player_gsis_id", "player_display_name", "team_abbr",
            "rush_attempts", "expected_rush_yards", "rush_yards_over_expected",
            "rush_yards_over_expected_per_att", "rush_pct_over_expected",
        ]
        df = df[[c for c in colonnes if c in df.columns]]

        output_path = OUTPUT_DIR / f"{season}.parquet"
        df.to_parquet(output_path, index=False)
        message = f"  Sauvegardé : {output_path} ({len(df)} lignes)"
        print(message)
        return (season, message, None)
    except ValueError as e:
        # nflreadpy refuse les saisons hors de sa plage connue (ex. saison
        # pas encore commencée) — comportement attendu, pas une erreur de
        # pipeline. Cf. fetch_plays.py pour le même traitement côté pbp.
        message = f"  NGS course indisponible pour {season} : {e}"
        print(message)
        return (season, message, None)
    except Exception as e:
        error_msg = f"  Échec pour {season} : {e}"
        print(error_msg)
        traceback.print_exc()
        return (season, error_msg, e)


if __name__ == "__main__":
    MAX_WORKERS = min(8, len(SEASONS))

    print(f"Téléchargement NGS course {PREMIERE_SAISON_NGS}-{CURRENT_SEASON} en parallèle (max {MAX_WORKERS} threads)...")
    print(f"Saisons à traiter : {SEASONS}")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_season, season): season for season in SEASONS}

        success_count = 0
        failure_count = 0

        for future in as_completed(futures):
            season, message, error = future.result()
            if error is None:
                success_count += 1
            else:
                failure_count += 1

    print(f"\nRésumé : {success_count} saisons traitées, {failure_count} échecs.")
    if failure_count > 0:
        print("Certaines saisons ont échoué. Vérifiez les messages d'erreur ci-dessus.")
