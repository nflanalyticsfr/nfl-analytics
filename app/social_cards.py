from PIL import Image, ImageDraw, ImageFont, ImageOps
import requests
from io import BytesIO

CANVAS_SIZE = 1080


def _charger_police(taille, gras=False):
    chemins_possibles = [
        "app/assets/fonts/Manrope-Bold.ttf" if gras else "app/assets/fonts/Manrope-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if gras else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for chemin in chemins_possibles:
        try:
            return ImageFont.truetype(chemin, taille)
        except (OSError, IOError):
            continue
    try:
        return ImageFont.load_default(size=taille)
    except TypeError:
        return ImageFont.load_default()


def _charger_image_url(url, taille=None):
    try:
        response = requests.get(url, timeout=5)
        img = Image.open(BytesIO(response.content)).convert("RGBA")
        if taille:
            img = img.resize(taille, Image.LANCZOS)
        return img
    except Exception:
        return None


def _hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def _cercle_net(img, diametre):
    """Découpe un cercle net et anti-aliasé, cadré sans déformation.
    Supersampling 4x avant downscale : évite les bords crénelés d'un
    masque tracé directement à la taille finale."""
    facteur = 4
    taille_super = diametre * facteur

    img_cadree = ImageOps.fit(
        img.convert("RGB"), (taille_super, taille_super),
        method=Image.LANCZOS, centering=(0.5, 0.35),
    ).convert("RGBA")

    mask = Image.new("L", (taille_super, taille_super), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, taille_super, taille_super), fill=255)
    img_cadree.putalpha(mask)

    return img_cadree.resize((diametre, diametre), Image.LANCZOS)


def _dessiner_badge_rang(draw, centre, rang, rayon=48):
    x, y = centre
    draw.ellipse((x - rayon, y - rayon, x + rayon, y + rayon), fill=(15, 23, 42))
    police = _charger_police(int(rayon * 0.9), gras=True)
    draw.text((x, y), f"#{rang}", font=police, fill="white", anchor="mm")


def _dessiner_badge_evolution(draw, centre, evolution, rayon=42):
    x, y = centre

    if evolution is None or evolution != evolution:
        draw.ellipse((x - rayon, y - rayon, x + rayon, y + rayon), fill=(100, 116, 139))
        police = _charger_police(20, gras=True)
        draw.text((x, y), "NEW", font=police, fill="white", anchor="mm")
        return

    if evolution == 0:
        draw.ellipse((x - rayon, y - rayon, x + rayon, y + rayon), fill=(100, 116, 139))
        police = _charger_police(30, gras=True)
        draw.text((x, y), "-", font=police, fill="white", anchor="mm")
        return

    monte = evolution > 0
    couleur = (22, 163, 74) if monte else (220, 38, 38)
    draw.ellipse((x - rayon, y - rayon, x + rayon, y + rayon), fill=couleur)

    # Triangle dessiné à la main : évite tout risque de glyphe manquant
    # selon la police disponible sur le serveur.
    tri_largeur, tri_hauteur = 13, 11
    tri_centre_y = y - 14
    if monte:
        points = [
            (x, tri_centre_y - tri_hauteur * 0.6),
            (x - tri_largeur, tri_centre_y + tri_hauteur * 0.5),
            (x + tri_largeur, tri_centre_y + tri_hauteur * 0.5),
        ]
    else:
        points = [
            (x, tri_centre_y + tri_hauteur * 0.6),
            (x - tri_largeur, tri_centre_y - tri_hauteur * 0.5),
            (x + tri_largeur, tri_centre_y - tri_hauteur * 0.5),
        ]
    draw.polygon(points, fill="white")

    police = _charger_police(int(rayon * 0.55), gras=True)
    draw.text((x, y + 16), str(int(abs(evolution))), font=police, fill="white", anchor="mm")



def generer_carte_joueur(nom, poste, team_abbr, team_color, logo_url, photo_url,
                          stat_label, stat_value, rang=None, evolution=None):
    couleur_rgb = _hex_to_rgb(team_color)
    img = Image.new("RGB", (CANVAS_SIZE, CANVAS_SIZE), couleur_rgb)
    draw = ImageDraw.Draw(img)

    overlay_h = 380
    draw.rectangle([0, CANVAS_SIZE - overlay_h, CANVAS_SIZE, CANVAS_SIZE], fill=(15, 23, 42))

    logo = _charger_image_url(logo_url, (140, 140))
    if logo:
        img.paste(logo, (CANVAS_SIZE - 180, 60), logo)

    photo_brute = _charger_image_url(photo_url)
    if photo_brute:
        photo = _cercle_net(photo_brute, 420)
        img.paste(photo, (330, 140), photo)

    if rang is not None:
        _dessiner_badge_rang(draw, (110, 110), rang)
    if evolution is not None or rang is not None:
        _dessiner_badge_evolution(draw, (110, 210), evolution)

    police_titre = _charger_police(64, gras=True)
    police_sous = _charger_police(36)
    police_stat = _charger_police(96, gras=True)
    police_label = _charger_police(32)

    draw.text((CANVAS_SIZE // 2, CANVAS_SIZE - overlay_h + 40), nom,
              font=police_titre, fill="white", anchor="mm")
    draw.text((CANVAS_SIZE // 2, CANVAS_SIZE - overlay_h + 95), f"{poste} · {team_abbr}",
              font=police_sous, fill="#94A3B8", anchor="mm")
    draw.text((CANVAS_SIZE // 2, CANVAS_SIZE - 160), str(stat_value),
              font=police_stat, fill="#EA580C", anchor="mm")
    draw.text((CANVAS_SIZE // 2, CANVAS_SIZE - 80), stat_label.upper(),
              font=police_label, fill="#94A3B8", anchor="mm")

    return img

COULEURS_RANG_HEX = ["#FBBF24", "#CBD5E1", "#D97706"]  # or / argent / bronze


def generer_podium_image(entries, titre, sous_titre=None):
    """entries : liste de 1 à 3 dicts avec les clés :
    rang, nom, sous_texte, team_color, logo_url, valeur (str déjà formatée),
    photo_url (optionnel — absent pour un podium d'équipes)."""
    img = Image.new("RGB", (CANVAS_SIZE, CANVAS_SIZE), (15, 23, 42))
    draw = ImageDraw.Draw(img)

    police_titre = _charger_police(52, gras=True)
    police_sous_titre = _charger_police(26)
    draw.text((CANVAS_SIZE // 2, 80), titre, font=police_titre, fill="white", anchor="mm")
    if sous_titre:
        draw.text((CANVAS_SIZE // 2, 130), sous_titre.upper(), font=police_sous_titre, fill="#94A3B8", anchor="mm")

    n = len(entries)
    entries_triees = sorted(entries, key=lambda e: e["rang"])
    ordre_affichage = [1, 0, 2][:n] if n >= 3 else list(range(n))

    hauteurs = [400, 320, 260]
    espacement = 300
    x_centre = CANVAS_SIZE // 2
    positions_x = {
        3: [x_centre - espacement, x_centre, x_centre + espacement],
        2: [x_centre - espacement // 2, x_centre + espacement // 2],
        1: [x_centre],
    }
    y_base = 980

    police_nom = _charger_police(28, gras=True)
    police_sous = _charger_police(20)
    police_valeur = _charger_police(32, gras=True)
    police_rang = _charger_police(24, gras=True)

    for position, i in enumerate(ordre_affichage):
        entree = entries_triees[i]
        rang = entree["rang"]
        x = positions_x[n][position]
        hauteur_barre = hauteurs[rang - 1] if rang <= 3 else 200
        couleur_equipe_rgb = _hex_to_rgb(entree["team_color"])

        avatar_diam = 130
        avatar_y = y_base - hauteur_barre - avatar_diam - 100

        photo_url = entree.get("photo_url")
        if photo_url:
            photo_brute = _charger_image_url(photo_url)
            if photo_brute:
                avatar = _cercle_net(photo_brute, avatar_diam)
                img.paste(avatar, (x - avatar_diam // 2, avatar_y), avatar)
            else:
                draw.ellipse((x - avatar_diam // 2, avatar_y, x + avatar_diam // 2, avatar_y + avatar_diam),
                              fill=couleur_equipe_rgb)
            logo_mini = _charger_image_url(entree.get("logo_url"), (44, 44))
            if logo_mini:
                lx, ly = x + avatar_diam // 2 - 32, avatar_y + avatar_diam - 32
                draw.ellipse((lx - 4, ly - 4, lx + 48, ly + 48), fill="white")
                img.paste(logo_mini, (lx, ly), logo_mini)
        else:
            logo = _charger_image_url(entree.get("logo_url"), (avatar_diam - 20, avatar_diam - 20))
            draw.ellipse((x - avatar_diam // 2, avatar_y, x + avatar_diam // 2, avatar_y + avatar_diam), fill="white")
            if logo:
                img.paste(logo, (x - (avatar_diam - 20) // 2, avatar_y + 10), logo)

        badge_rayon = 24
        badge_y = avatar_y - 6
        couleur_badge = _hex_to_rgb(COULEURS_RANG_HEX[rang - 1]) if rang <= 3 else (100, 116, 139)
        draw.ellipse((x - badge_rayon, badge_y - badge_rayon, x + badge_rayon, badge_y + badge_rayon), fill=couleur_badge)
        draw.text((x, badge_y), str(rang), font=police_rang, fill=(31, 41, 55), anchor="mm")

        nom_y = avatar_y + avatar_diam + 34
        draw.text((x, nom_y), entree["nom"], font=police_nom, fill="white", anchor="mm")
        draw.text((x, nom_y + 30), entree.get("sous_texte", ""), font=police_sous, fill="#94A3B8", anchor="mm")
        draw.text((x, nom_y + 62), entree["valeur"], font=police_valeur, fill="#EA580C", anchor="mm")

        barre_largeur = 220
        draw.rectangle([x - barre_largeur // 2, y_base - hauteur_barre, x + barre_largeur // 2, y_base],
                        fill=couleur_equipe_rgb)

    return img


def _formatter_valeur(valeur, decimals):
    return f"{valeur:,.0f}" if decimals == 0 else f"{valeur:.{decimals}f}"

def generer_carte_equipe(team_name, season, team_color, logo_url, rang_off, epa_off,
                          rang_def, epa_def, rang_semaine=None, evolution_semaine=None):
    img = Image.new("RGB", (CANVAS_SIZE, CANVAS_SIZE), (15, 23, 42))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, CANVAS_SIZE, 90], fill=_hex_to_rgb(team_color))

    logo = _charger_image_url(logo_url, (320, 320))
    if logo:
        img.paste(logo, (CANVAS_SIZE // 2 - 160, 160), logo)

    if rang_semaine is not None:
        _dessiner_badge_rang(draw, (110, 150), rang_semaine)
    if evolution_semaine is not None or rang_semaine is not None:
        _dessiner_badge_evolution(draw, (110, 250), evolution_semaine)

    police_titre = _charger_police(70, gras=True)
    police_label = _charger_police(30)
    police_stat = _charger_police(56, gras=True)

    draw.text((CANVAS_SIZE // 2, 550), team_name, font=police_titre, fill="white", anchor="mm")
    draw.text((CANVAS_SIZE // 2, 610), f"Saison {season}", font=police_label, fill="#94A3B8", anchor="mm")

    draw.text((CANVAS_SIZE // 4, 780), f"#{rang_off}", font=police_stat, fill="#EA580C", anchor="mm")
    draw.text((CANVAS_SIZE // 4, 850), "EPA OFFENSE", font=police_label, fill="#94A3B8", anchor="mm")
    draw.text((CANVAS_SIZE // 4, 890), f"{epa_off:.3f}", font=police_label, fill="white", anchor="mm")

    draw.text((3 * CANVAS_SIZE // 4, 780), f"#{rang_def}", font=police_stat, fill="#EA580C", anchor="mm")
    draw.text((3 * CANVAS_SIZE // 4, 850), "EPA DÉFENSE", font=police_label, fill="#94A3B8", anchor="mm")
    draw.text((3 * CANVAS_SIZE // 4, 890), f"{epa_def:.3f}", font=police_label, fill="white", anchor="mm")

    return img


COULEURS_QUADRANT = {
    "elite": (34, 197, 94),              # vert — attaque + défense fortes
    "defense": (59, 130, 246),           # bleu — défense dominante
    "attaque": (234, 88, 12),            # orange — attaque dominante
    "reconstruction": (100, 116, 139),   # gris — reconstruction
}
POWER_TIERS_AXE_MIN, POWER_TIERS_AXE_MAX = -0.20, 0.20


def generer_power_tiers_image(df_teams, season):
    """df_teams : colonnes team, epa_offense, epa_defense, logo_url (issu
    de get_team_epa_offense_defense + get_team_logos, comme sur
    Analytics > Advanced Analytics PRO > Équipe).

    Version statique carrée de l'idée du graphique Power Tiers interactif :
    logos d'équipe positionnés par EPA attaque/défense, quadrants teintés.
    Pensée pour Instagram, pas pour l'exploration — pas de hover, pas de
    lignes de Net EPA (trop chargé à l'échelle d'un post), juste les 4
    zones et les 32 logos. Axe Y inversé comme sur la version interactive :
    plus haut = défense plus stingy (epa_defense plus négatif)."""
    img = Image.new("RGB", (CANVAS_SIZE, CANVAS_SIZE), (15, 23, 42))

    marge_haut, taille_graph = 190, 760
    x0 = (CANVAS_SIZE - taille_graph) // 2
    y0 = marge_haut
    x1, y1 = x0 + taille_graph, y0 + taille_graph

    def px_x(epa_off):
        return x0 + (epa_off - POWER_TIERS_AXE_MIN) / (POWER_TIERS_AXE_MAX - POWER_TIERS_AXE_MIN) * taille_graph

    def px_y(epa_def):
        return y0 + (epa_def - POWER_TIERS_AXE_MIN) / (POWER_TIERS_AXE_MAX - POWER_TIERS_AXE_MIN) * taille_graph

    zx, zy = px_x(0), px_y(0)

    # Quadrants teintés — alpha faible pour rester lisible sous les logos
    overlay = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)
    alpha = 40
    draw_overlay.rectangle([zx, y0, x1, zy], fill=COULEURS_QUADRANT["elite"] + (alpha,))
    draw_overlay.rectangle([x0, y0, zx, zy], fill=COULEURS_QUADRANT["defense"] + (alpha,))
    draw_overlay.rectangle([zx, zy, x1, y1], fill=COULEURS_QUADRANT["attaque"] + (alpha,))
    draw_overlay.rectangle([x0, zy, zx, y1], fill=COULEURS_QUADRANT["reconstruction"] + (alpha,))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Axes zéro + cadre
    draw.line([(zx, y0), (zx, y1)], fill=(71, 85, 105), width=2)
    draw.line([(x0, zy), (x1, zy)], fill=(71, 85, 105), width=2)
    draw.rectangle([x0, y0, x1, y1], outline=(51, 65, 85), width=2)

    # Étiquettes de quadrant
    police_quadrant = _charger_police(20, gras=True)
    draw.text(((zx + x1) / 2, y0 + 22), "ELITE", font=police_quadrant, fill="white", anchor="mm")
    draw.text(((x0 + zx) / 2, y0 + 22), "DÉFENSE DOMINANTE", font=police_quadrant, fill="white", anchor="mm")
    draw.text(((zx + x1) / 2, y1 - 22), "ATTAQUE DOMINANTE", font=police_quadrant, fill="white", anchor="mm")
    draw.text(((x0 + zx) / 2, y1 - 22), "RECONSTRUCTION", font=police_quadrant, fill="white", anchor="mm")

    # Logos d'équipe positionnés par EPA
    taille_logo = 58
    for _, row in df_teams.iterrows():
        logo = _charger_image_url(row["logo_url"], (taille_logo, taille_logo))
        if logo:
            cx, cy = px_x(row["epa_offense"]), px_y(row["epa_defense"])
            img.paste(logo, (int(cx - taille_logo / 2), int(cy - taille_logo / 2)), logo)

    # Titre, sous-titre, étiquette d'axe X
    police_titre = _charger_police(58, gras=True)
    police_sous = _charger_police(28)
    police_axe = _charger_police(20)
    draw.text((CANVAS_SIZE // 2, 68), "NFL POWER TIERS", font=police_titre, fill="white", anchor="mm")
    draw.text((CANVAS_SIZE // 2, 122), f"Saison {season} · EPA attaque vs défense",
              font=police_sous, fill="#94A3B8", anchor="mm")
    draw.text((CANVAS_SIZE // 2, y1 + 28), "EPA OFFENSIF →", font=police_axe, fill="#94A3B8", anchor="mm")

    # Étiquette d'axe Y (verticale — dessinée à part puis pivotée)
    label_y = Image.new("RGBA", (320, 40), (0, 0, 0, 0))
    ImageDraw.Draw(label_y).text((160, 20), "EPA DÉFENSIF (haut = meilleure défense)",
                                  font=police_axe, fill="#94A3B8", anchor="mm")
    label_y = label_y.rotate(90, expand=True)
    img.paste(label_y, (18, int((y0 + y1) / 2 - label_y.height / 2)), label_y)

    police_watermark = _charger_police(22, gras=True)
    draw.text((CANVAS_SIZE // 2, CANVAS_SIZE - 26), "NFL ANALYTICS FR",
              font=police_watermark, fill="#EA580C", anchor="mm")

    return img