"""
Règles de codification automatique EVAM (fonctions pures, sans accès à
la base : utilisées par les modèles ET par les migrations de renommage).

Produit fini : FAMILLE + PARFUM + FORMAT + UNITÉ DE VENTE
    Eau, 70 cl, Pack de 8                  -> EAU70P8
    Eau, 100 cl, Carton de 12              -> EAU100C12
    Jus, Grenadine, 70 cl, Pack de 8       -> JUSGRE70P8
    Yaourt, Fraise, 125 g, Pot             -> YAOFRA125POT
  - famille / parfum : 3 premières lettres, sans accents ;
  - parfum omis s'il est absent ou « Nature » (facultatif pour l'eau) ;
  - format : le nombre seul (70 cl -> 70, 125 g -> 125) ;
  - unité de vente : initiale + nombre (Pack de 8 -> P8, Carton de 12 -> C12),
    ou, sans nombre, le mot s'il fait 3 lettres au plus (Pot -> POT),
    sinon son initiale (Unité -> U).

Code fiscal : EV-FISC-{PRODUIT}-{TVA}
    EV-FISC-YAO-18, EV-FISC-JUS-18, EV-FISC-EAU-0 (exonéré : TVA 0)
"""

import re
import unicodedata
from decimal import Decimal

PARFUMS_NEUTRES = {"NATURE"}


def _ascii_majuscules(texte):
    return unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode().upper()


def sigle(texte, longueur=3):
    """3 premières lettres du premier mot (Yaourt -> YAO, Jus EVAM sucré -> JUS)."""
    mots = re.findall(r"[A-Z]+", _ascii_majuscules(texte))
    if not mots:
        raise ValueError(f"Impossible de tirer un sigle de « {texte} ».")
    return mots[0][:longueur]


def nombre_du_format(valeur):
    """70 cl -> 70 ; 125 g -> 125 ; 1,5 L -> 15."""
    trouve = re.search(r"\d+(?:[.,]\d+)?", valeur or "")
    if not trouve:
        raise ValueError(f"Le format « {valeur} » ne contient pas de nombre.")
    return re.sub(r"[.,]", "", trouve.group())


def code_unite_vente(nom):
    """Pack de 8 -> P8 ; Carton de 12 -> C12 ; Pot -> POT ; Unité -> U."""
    texte = _ascii_majuscules(nom)
    mots = re.findall(r"[A-Z]+", texte)
    if not mots:
        raise ValueError(f"Impossible de coder l'unité de vente « {nom} ».")
    nombre = re.search(r"\d+", texte)
    if nombre:
        return mots[0][0] + nombre.group()
    return mots[0] if len(mots[0]) <= 3 else mots[0][0]


def parfum_code(parfum):
    """Sigle du parfum, ou chaîne vide si absent / neutre (Nature)."""
    if not parfum or _ascii_majuscules(parfum).strip() in PARFUMS_NEUTRES:
        return ""
    return sigle(parfum)


def code_produit_fini(famille, format_valeur, unite_vente, parfum=None):
    return sigle(famille) + parfum_code(parfum) + nombre_du_format(format_valeur) + code_unite_vente(unite_vente)


def code_fiscal_base(famille_fiscale, taux_tva, exonere):
    """EV-FISC-YAO-18 ; exonéré ou TVA nulle -> EV-FISC-EAU-0."""
    tva = Decimal("0") if exonere else Decimal(str(taux_tva or 0))
    tva_texte = f"{tva.normalize():f}".replace(".", "_")
    return f"EV-FISC-{sigle(famille_fiscale)}-{tva_texte}"
