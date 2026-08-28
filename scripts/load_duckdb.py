import duckdb
from pathlib import Path

DB_PATH = Path("database/nfl.duckdb")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

con = duckdb.connect(str(DB_PATH))

print("Chargement plays...")
con.execute("""
    CREATE OR REPLACE TABLE plays AS
    SELECT * FROM read_parquet('data/seasons/*.parquet', union_by_name=true)
""")

print("Chargement games...")
con.execute("""
    CREATE OR REPLACE TABLE games AS
    SELECT * FROM read_parquet('data/static/games.parquet', union_by_name=true)
""")

print("Chargement players...")
con.execute("""
    CREATE OR REPLACE TABLE players AS
    SELECT * FROM read_parquet('data/static/players.parquet', union_by_name=true)
""")

print("Chargement teams...")
con.execute("""
    CREATE OR REPLACE TABLE teams AS
    SELECT * FROM read_parquet('data/static/teams.parquet', union_by_name=true)
""")

print("Chargement rosters (headshots)...")
con.execute("""
    CREATE OR REPLACE TABLE rosters AS
    SELECT * FROM read_parquet('data/static/rosters.parquet', union_by_name=true)
""")

print("Chargement ngs_rushing (Rush Yards Over Expected)...")
con.execute("""
    CREATE OR REPLACE TABLE ngs_rushing AS
    SELECT * FROM read_parquet('data/seasons_ngs_rushing/*.parquet', union_by_name=true)
""")

for table in ["plays", "games", "players", "teams", "rosters", "ngs_rushing"]:
    count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"  {table} : {count} lignes")

con.close()
print(f"Base créée : {DB_PATH}")