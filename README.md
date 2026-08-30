# NFL Analytics FR 🏈

**Analyse avancée des données NFL (National Football League) en français.**

Une application Streamlit pour explorer les statistiques, les performances et les insights des équipes et joueurs de la NFL, basée sur des données play-by-play complètes.

---

## 📊 Fonctionnalités

### 🏠 [Page d'accueil](app/views/0_Accueil.py)
- Vue d'ensemble des statistiques globales (nombre de plays, matchs, équipes, saisons)
- Leaders de la ligue (passing yards, rushing yards, receiving yards, sacks, interceptions)
- Leaders analytiques (EPA/Play, Success Rate, Offensive/Defensive EPA)
- Derniers matchs joués

### 📅 [Matchs](app/views/3_Matchs.py)
- Détail d'un match : score, drives, win probability
- Play-by-play complet avec EPA, success rate, et métriques avancées
- Visualisation de la progression du score et de la win probability

### 🏈 [Équipes](app/views/1_Equipes.py)
- Fiche complète par équipe : bilan (V/D/N), EPA offensif/défensif
- Classement dans la ligue
- Leaders offensifs (QB, RB, WR)
- Calendrier et résultats des matchs
- Tendances EPA par semaine

### 👤 [Joueurs](app/views/2_Joueurs.py)
- Recherche et fiche détaillée par joueur
- Statistiques complètes (passing, rushing, receiving, pression, défense)
- EPA par saison et tendance hebdomadaire
- Bio (taille, poids, position, équipe)

### 🏆 [Classements](app/views/4_Classements.py)
- Meilleurs joueurs (QB, RB, WR) par saison ou par semaine
- Meilleurs équipes (offense, défense) par saison ou par semaine
- Filtres par semaine et par type de classement

### 📈 [Analytics](app/views/5_Analytics.py)
- Visualisation EPA offensif vs défensif pour toutes les équipes
- Comparaison des performances par saison

### ⚖️ [Comparer](app/views/6_Comparer.py)
- Comparaison de plusieurs équipes sur plusieurs années
- Analyse offensive ou défensive

### 📱 [Cartes Sociales](app/views/8_Cartes_Sociales.py)
- Génération de cartes partagables avec les stats des joueurs
- Variantes cumulées (semaine 1 → semaine sélectionnée)

### ℹ️ [À propos](app/views/7_A_propos.py)
- Source des données et méthodologie
- Formulaire de feedback

### Navigation
`app/Accueil.py` est un routeur minimal : il définit l'ordre, le titre et
l'icône de chaque page via `st.navigation()` (Streamlit 1.36+), plutôt que
de laisser l'ordre dépendre des préfixes numériques des noms de fichiers.
Pour réordonner les pages ou changer un titre/icône, tout se passe dans ce
seul fichier — voir son docstring avant de toucher aux `url_path` (les liens
internes de `queries.py` en dépendent).

---

## 🚀 Installation et exécution

### Prérequis
- Python **3.9+** (recommandé : 3.10 ou 3.11)
- Git
- ~5 Go d'espace disque (pour les données brutes et la base DuckDB)

### 1. Cloner le dépôt
```bash
git clone https://github.com/beuh4/nfl-analytics.git
cd nfl-analytics
```

### 2. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 3. Reconstruire la base de données (nécessaire avant la première exécution)

La base de données **DuckDB** (`database/nfl.duckdb`) doit être générée à partir des données brutes.
Exécutez les scripts dans cet ordre (depuis la racine du projet) :

```bash
# 1. Télécharger les données statiques (calendrier, scores, équipes, joueurs)
python scripts/fetch_static.py

# 2. Télécharger les rosters (effectifs) saison par saison
python scripts/fetch_rosters.py

# 3. Télécharger le play-by-play complet (LE PLUS LONG : plusieurs minutes)
python scripts/fetch_plays.py

# 4. Charger les données dans DuckDB
python scripts/load_duckdb.py

# 5. (Optionnel) Valider la cohérence des EPA
python scripts/validate_epa.py
```

> ⚠️ **Note** : Le script `fetch_plays.py` peut prendre **plusieurs minutes** (voire heures selon votre connexion) car il télécharge toutes les données play-by-play depuis 2015.

### 4. Exécuter l'application
```bash
streamlit run app/Accueil.py
```

L'application sera accessible à l'adresse : [http://localhost:8501](http://localhost:8501)

---

## 📂 Structure du projet

```
nfl-analytics/
├── app/                          # Application Streamlit
│   ├── Accueil.py                # Routeur (Main file path Streamlit Cloud) — ordre/titres/icônes des pages via st.navigation()
│   ├── constants.py              # Constantes partagées (saisons, équipe par défaut)
│   ├── queries.py                # Couche d'accès aux données (requêtes DuckDB)
│   ├── styles.py                 # Feuilles de style CSS
│   ├── social_cards.py           # Génération des cartes sociales (Pillow)
│   └── views/                    # Pages Streamlit (nommé "views/", pas "pages/" — voir docstring d'Accueil.py : un dossier "pages/" est auto-détecté par Streamlit et court-circuite st.navigation())
│       ├── 0_Accueil.py
│       ├── 1_Equipes.py
│       ├── 2_Joueurs.py
│       ├── 3_Matchs.py
│       ├── 4_Classements.py
│       ├── 5_Analytics.py
│       ├── 6_Comparer.py
│       ├── 7_A_propos.py
│       └── 8_Cartes_Sociales.py
│
├── database/                     # Base de données
│   └── nfl.duckdb                # Base DuckDB (exclue de Git, voir .gitignore)
│
├── scripts/                      # Scripts ETL (Extract-Transform-Load)
│   ├── fetch_static.py           # Télécharge les données statiques
│   ├── fetch_rosters.py          # Télécharge les rosters
│   ├── fetch_plays.py            # Télécharge le play-by-play
│   ├── load_duckdb.py            # Charge les données dans DuckDB
│   ├── validate_epa.py           # Valide la cohérence des EPA
│   └── README.md                 # Documentation du pipeline
│
├── .gitignore                    # Exclut les fichiers volumineux (nfl.duckdb, data/)
├── requirements.txt              # Dépendances Python
└── README.md                     # Ce fichier
```

---

## 🔧 Configuration

### Changer de saison
Les saisons analysées sont définies dans `app/constants.py` :
```python
FIRST_SEASON = 2015  # Première saison à inclure
CURRENT_SEASON = 2026  # Saison en cours (à mettre à jour chaque année)
```

Pour ajouter une nouvelle saison (ex: 2026) :
1. Mettre à jour `CURRENT_SEASON` dans `constants.py`.
2. Relancer le pipeline ETL (voir [Reconstruire la base de données](#3-reconstruire-la-base-de-données)).

### Équipes par défaut
L'équipe sélectionnée par défaut sur la page `Équipes` est définie par :
```python
DEFAULT_TEAM = "ARI"  # Arizona Cardinals
```

---

## 📊 Sources des données

Les données sont téléchargées depuis **[nflverse](https://nflverse.com/)** via la librairie Python **[nfl_data_py](https://github.com/cooperdff/nfl_data_py)**.

### Données incluses
| Table | Description | Source |
|-------|-------------|--------|
| `games` | Calendrier, scores, dates des matchs | `nfl_data_py.pbp_data` |
| `plays` | Play-by-play complet (toutes les actions) | `nfl_data_py.pbp_data` |
| `teams` | Référentiel des équipes (noms, couleurs, logos) | `nfl_data_py.teams_data` |
| `players` | Référentiel des joueurs (noms, IDs) | `nfl_data_py.players_data` |
| `rosters` | Effectifs saison par saison (bio, photos) | `nfl_data_py.roster_data` |

### Métriques clés
- **EPA (Expected Points Added)** : Impact d'une action sur le score attendu.
- **Success Rate** : Pourcentage de plays réussis (EPA > 0).
- **Win Probability (WP)** : Probabilité de victoire avant/après une action.
- **WPA (Win Probability Added)** : Impact d'une action sur la probabilité de victoire.

---

## 🛠️ Technologies utilisées

| Composant | Technologie | Version |
|-----------|-------------|---------|
| **Frontend** | [Streamlit](https://streamlit.io/) | 1.60.0 |
| **Backend** | Python | 3.9+ |
| **Base de données** | [DuckDB](https://duckdb.org/) | 1.5.5 |
| **Data** | [nfl_data_py](https://github.com/cooperdff/nfl_data_py) | 0.3.3 |
| **Visualisation** | [Plotly](https://plotly.com/python/), [Altair](https://altair-viz.github.io/) | 6.9.0, 6.2.2 |
| **Styles** | CSS personnalisé + [Google Fonts](https://fonts.google.com/) | - |

---

## 🤝 Contribution

Les contributions sont les bienvenues ! Voici comment contribuer :

1. **Ouvrir une issue** : Pour signaler un bug ou proposer une nouvelle fonctionnalité.
2. **Forker le dépôt** : Créer une branche pour vos modifications.
3. **Soumettre une Pull Request** : Expliquez clairement vos changements.

### Bonnes pratiques
- Respecter le style de code existant (PEP 8).
- Ajouter des tests pour les nouvelles fonctionnalités.
- Documenter votre code avec des commentaires.
- Mettre à jour le `README.md` si nécessaire.

---

## 📜 Licence

Ce projet est sous licence **MIT**. Voir le fichier [LICENSE](LICENSE) pour plus de détails.

---

## 🙏 Remerciements

- **[nflverse](https://nflverse.com/)** pour les données ouvertes et la communauté.
- **[Streamlit](https://streamlit.io/)** pour le framework incroyable.
- **[DuckDB](https://duckdb.org/)** pour la base de données légère et performante.

---

## 📬 Contact

Pour toute question ou feedback, n'hésitez pas à :
- Ouvrir une **issue** sur GitHub.
- Remplir le [formulaire de feedback](https://docs.google.com/forms/d/e/TON_LIEN_ICI/viewform) (lien à mettre à jour).
