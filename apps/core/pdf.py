"""
Génération des documents imprimables en PDF (ReportLab, sans dépendance
système) : facture, avoir, bon de livraison, bon de commande fournisseur,
reçu de caisse, bon de sortie des matières, bon de transfert.

Chaque document a la même mise en page :
- en-tête : logo et identité de l'entreprise, titre, numéro et date ;
- bloc du tiers (client, fournisseur, lieu...) et informations utiles ;
- tableau des lignes, totaux, montant en lettres si c'est un montant ;
- zone de signatures ;
- pied de page sur chaque page : mentions légales (RCCM, IFU, capital,
  banque...), date d'édition, « Page x / y ».
L'identité vient de ParametreEntreprise (paramétrable, logo compris).
"""

from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO

from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as canvas_module
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

MARGE = 15 * mm
LARGEUR_UTILE = A4[0] - 2 * MARGE
GRIS = colors.HexColor("#5B6B70")
GRIS_CLAIR = colors.HexColor("#E6ECEE")

STYLE = ParagraphStyle("normal", fontName="Helvetica", fontSize=9, leading=12)
STYLE_PETIT = ParagraphStyle("petit", parent=STYLE, fontSize=7.5, leading=9.5, textColor=GRIS)
STYLE_GRAS = ParagraphStyle("gras", parent=STYLE, fontName="Helvetica-Bold")
STYLE_DROITE = ParagraphStyle("droite", parent=STYLE, alignment=TA_RIGHT)
STYLE_ENTREPRISE = ParagraphStyle("entreprise", parent=STYLE, fontName="Helvetica-Bold", fontSize=13, leading=16)


# --- Formats --------------------------------------------------------------

def nombre(valeur, decimales=None):
    """1234567.5 -> « 1 234 567,50 » ; entier -> sans décimales ; None -> « - »."""
    if valeur is None:
        return "-"
    valeur = Decimal(valeur)
    if decimales is None:
        decimales = 0 if valeur == valeur.to_integral_value() else (2 if valeur * 100 == (valeur * 100).to_integral_value() else 3)
    quantum = Decimal(1).scaleb(-decimales)
    texte = f"{valeur.quantize(quantum, ROUND_HALF_UP):,.{decimales}f}"
    return texte.replace(",", "\xa0").replace(".", ",")


def montant(valeur):
    return nombre(valeur) if valeur is not None else "-"


def date_fr(valeur):
    if valeur is None:
        return "-"
    if hasattr(valeur, "hour"):
        valeur = timezone.localtime(valeur) if timezone.is_aware(valeur) else valeur
        return valeur.strftime("%d/%m/%Y %H:%M")
    return valeur.strftime("%d/%m/%Y")


UNITES = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze",
          "treize", "quatorze", "quinze", "seize", "dix-sept", "dix-huit", "dix-neuf"]
DIZAINES = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}


def _moins_de_cent(n):
    if n < 20:
        return UNITES[n]
    dizaine, unite = divmod(n, 10)
    if dizaine in (7, 9):
        base = "soixante" if dizaine == 7 else "quatre-vingt"
        reste = 10 + unite
        liaison = " et " if dizaine == 7 and unite == 1 else "-"
        return base + liaison + UNITES[reste]
    if dizaine == 8:
        return "quatre-vingts" if unite == 0 else "quatre-vingt-" + UNITES[unite]
    base = DIZAINES[dizaine]
    if unite == 0:
        return base
    return base + (" et un" if unite == 1 else "-" + UNITES[unite])


def _moins_de_mille(n):
    centaines, reste = divmod(n, 100)
    if centaines == 0:
        return _moins_de_cent(reste)
    debut = "cent" if centaines == 1 else UNITES[centaines] + " cent" + ("s" if reste == 0 else "")
    return debut if reste == 0 else f"{debut} {_moins_de_cent(reste)}"


def en_lettres(n):
    """Nombre entier en toutes lettres (orthographe traditionnelle) : 1 250 000 -> « un million deux cent cinquante mille »."""
    n = int(n)
    if n == 0:
        return "zéro"
    morceaux = []
    for valeur, singulier, pluriel in ((10**9, "milliard", "milliards"), (10**6, "million", "millions")):
        quotient, n = divmod(n, valeur)
        if quotient:
            morceaux.append(f"{en_lettres(quotient)} {singulier if quotient == 1 else pluriel}")
    milliers, n = divmod(n, 1000)
    if milliers:
        texte = _moins_de_mille(milliers)
        if texte.endswith(("cents", "vingts")):
            texte = texte[:-1]   # « deux cent mille », « quatre-vingt mille »
        morceaux.append("mille" if milliers == 1 else f"{texte} mille")
    if n:
        morceaux.append(_moins_de_mille(n))
    return " ".join(morceaux)


def montant_en_lettres(valeur, devise="francs CFA"):
    valeur = Decimal(valeur or 0).quantize(Decimal("0.01"), ROUND_HALF_UP)
    entier, centimes = int(valeur), int((valeur - int(valeur)) * 100)
    texte = f"{en_lettres(entier)} {devise}"
    if centimes:
        texte += f" et {en_lettres(centimes)} centimes"
    return texte[0].upper() + texte[1:]


# --- Mise en page ---------------------------------------------------------

def _couleur(entreprise):
    try:
        return colors.HexColor(entreprise.couleur)
    except (ValueError, TypeError):
        return colors.HexColor("#0A6676")


def _logo(entreprise):
    if not entreprise.logo:
        return None
    try:
        lecteur = ImageReader(BytesIO(bytes(entreprise.logo)))
        largeur, hauteur = lecteur.getSize()
        echelle = min(38 * mm / largeur, 24 * mm / hauteur)
        return Image(BytesIO(bytes(entreprise.logo)), width=largeur * echelle, height=hauteur * echelle)
    except Exception:
        return None   # logo illisible : le document reste imprimable


def mentions_legales(entreprise):
    morceaux = [entreprise.raison_sociale + (f" {entreprise.forme_juridique}" if entreprise.forme_juridique else "")]
    if entreprise.capital:
        morceaux.append(f"au capital de {entreprise.capital}")
    if entreprise.rccm:
        morceaux.append(f"RCCM {entreprise.rccm}")
    if entreprise.ifu:
        morceaux.append(f"IFU {entreprise.ifu}")
    if entreprise.regime_fiscal:
        morceaux.append(entreprise.regime_fiscal)
    if entreprise.centre_impots:
        morceaux.append(f"Centre des impôts : {entreprise.centre_impots}")
    lignes = [" - ".join(morceaux)]
    contact = [x for x in (entreprise.adresse, entreprise.ville, entreprise.telephone and f"Tél. {entreprise.telephone}",
                           entreprise.email, entreprise.site_web) if x]
    if contact:
        lignes.append(" - ".join(contact))
    if entreprise.banque:
        lignes.append(f"Banque : {entreprise.banque}")
    if entreprise.mentions_pied_de_page:
        lignes.extend(entreprise.mentions_pied_de_page.splitlines())
    return lignes


class _CanevasNumerote(canvas_module.Canvas):
    """Pied de page sur chaque page, avec « Page x / y » (nombre total connu à la fin)."""

    def __init__(self, *args, document=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._pages = []
        self._document = document

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for etat in self._pages:
            self.__dict__.update(etat)
            self._dessiner_pied(total)
            super().showPage()
        super().save()

    def _dessiner_pied(self, total):
        document = self._document
        self.setStrokeColor(GRIS_CLAIR)
        self.line(MARGE, 22 * mm, A4[0] - MARGE, 22 * mm)
        self.setFont("Helvetica", 6.8)
        self.setFillColor(GRIS)
        y = 18.5 * mm
        for ligne in document.mentions[:4]:
            self.drawCentredString(A4[0] / 2, y, ligne[:180])
            y -= 3 * mm
        self.drawString(MARGE, 7 * mm, document.edition)
        self.drawRightString(A4[0] - MARGE, 7 * mm, f"Page {self._pageNumber} / {total}")
        if document.filigrane:
            self.saveState()
            self.setFont("Helvetica-Bold", 70)
            self.setFillColor(colors.Color(0.85, 0.1, 0.1, alpha=0.15))
            self.translate(A4[0] / 2, A4[1] / 2)
            self.rotate(35)
            self.drawCentredString(0, 0, document.filigrane)
            self.restoreState()


class DocumentPDF:
    """
    Construit un document : DocumentPDF("FACTURE", numero, date).avec_tiers(...)
    .avec_lignes(...).avec_totaux(...).avec_signatures(...).reponse(nom).
    """

    def __init__(self, titre, numero, date, utilisateur=None, filigrane=None):
        from .models import ParametreEntreprise
        self.entreprise = ParametreEntreprise.courant()
        self.couleur = _couleur(self.entreprise)
        self.titre, self.numero, self.date = titre, numero, date
        self.filigrane = filigrane
        self.mentions = mentions_legales(self.entreprise)
        par = f" par {utilisateur.get_full_name() or utilisateur.username}" if utilisateur is not None else ""
        self.edition = f"Édité le {date_fr(timezone.now())}{par}"
        self.elements = [self._en_tete(), Spacer(1, 6 * mm)]

    # -- blocs -------------------------------------------------------------
    def _en_tete(self):
        e = self.entreprise
        identite = [Paragraph(e.raison_sociale, STYLE_ENTREPRISE)]
        for ligne in (e.activite, e.adresse, e.ville, e.telephone and f"Tél. {e.telephone}", e.email,
                      " - ".join(x for x in (e.ifu and f"IFU {e.ifu}", e.rccm and f"RCCM {e.rccm}") if x)):
            if ligne:
                identite.append(Paragraph(ligne, STYLE_PETIT))
        logo = _logo(e)
        gauche = Table([[logo, identite]] if logo else [[identite]], colWidths=[42 * mm, None] if logo else [None])
        gauche.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        titre = Table([
            [Paragraph(f'<font color="white"><b>{self.titre}</b></font>', ParagraphStyle("t", parent=STYLE, fontSize=13, leading=16))],
            [Paragraph(f"<b>N° {self.numero}</b>", STYLE)],
            [Paragraph(f"Date : {date_fr(self.date)}", STYLE)],
        ], colWidths=[62 * mm])
        titre.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), self.couleur), ("BOX", (0, 0), (-1, -1), 0.8, self.couleur),
            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        tableau = Table([[gauche, titre]], colWidths=[LARGEUR_UTILE - 64 * mm, 64 * mm])
        tableau.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
        return tableau

    def avec_tiers(self, titre_gauche, lignes_gauche, titre_droite=None, lignes_droite=None):
        """Deux encadrés côte à côte : tiers (client, fournisseur...) et informations du document."""
        def encadre(titre, lignes):
            contenu = [[Paragraph(f'<font color="white"><b>{titre}</b></font>', STYLE)]]
            contenu += [[Paragraph(str(ligne), STYLE_GRAS if index == 0 else STYLE)] for index, ligne in enumerate(l for l in lignes if l)]
            bloc = Table(contenu, colWidths=[(LARGEUR_UTILE - 6 * mm) / 2])
            bloc.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (0, 0), self.couleur), ("BOX", (0, 0), (-1, -1), 0.6, self.couleur),
                ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            return bloc
        gauche = encadre(titre_gauche, lignes_gauche)
        droite = encadre(titre_droite, lignes_droite) if titre_droite else ""
        tableau = Table([[gauche, droite]], colWidths=[LARGEUR_UTILE / 2, LARGEUR_UTILE / 2])
        tableau.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                     ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
        self.elements += [tableau, Spacer(1, 6 * mm)]
        return self

    def avec_lignes(self, entetes, lignes, largeurs, colonnes_nombres=()):
        """Tableau des lignes ; largeurs en mm (la dernière colonne vide = le reste)."""
        largeurs = [l * mm if l else None for l in largeurs]
        fixe = sum(l for l in largeurs if l)
        largeurs = [l if l else LARGEUR_UTILE - fixe for l in largeurs]
        donnees = [[Paragraph(f'<font color="white"><b>{e}</b></font>', STYLE_DROITE if i in colonnes_nombres else STYLE)
                    for i, e in enumerate(entetes)]]
        for ligne in lignes:
            donnees.append([Paragraph(str(valeur), STYLE_DROITE if i in colonnes_nombres else STYLE) for i, valeur in enumerate(ligne)])
        if not lignes:
            donnees.append([Paragraph("<i>Aucune ligne</i>", STYLE)] + [""] * (len(entetes) - 1))
        tableau = Table(donnees, colWidths=largeurs, repeatRows=1)
        tableau.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), self.couleur),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F7F8")]),
            ("LINEBELOW", (0, 0), (-1, -1), 0.3, GRIS_CLAIR), ("BOX", (0, 0), (-1, -1), 0.6, self.couleur),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        self.elements += [tableau, Spacer(1, 4 * mm)]
        return self

    def avec_totaux(self, lignes, en_lettres_de=None, libelle_lettres="Arrêté le présent document à la somme de"):
        """Totaux alignés à droite ; la dernière ligne est mise en valeur."""
        donnees = [[Paragraph(libelle, STYLE_GRAS if i == len(lignes) - 1 else STYLE),
                    Paragraph(f"<b>{valeur}</b>" if i == len(lignes) - 1 else valeur, STYLE_DROITE)]
                   for i, (libelle, valeur) in enumerate(lignes)]
        tableau = Table(donnees, colWidths=[52 * mm, 38 * mm], hAlign="RIGHT")
        tableau.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -2), 0.3, GRIS_CLAIR),
            ("BACKGROUND", (0, -1), (-1, -1), GRIS_CLAIR), ("BOX", (0, -1), (-1, -1), 0.8, self.couleur),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        self.elements += [tableau, Spacer(1, 4 * mm)]
        if en_lettres_de is not None:
            self.elements += [Paragraph(f"{libelle_lettres} : <b>{montant_en_lettres(en_lettres_de)}</b>.", STYLE), Spacer(1, 4 * mm)]
        return self

    def avec_texte(self, texte, style=STYLE):
        if texte:
            for ligne in str(texte).splitlines():
                self.elements.append(Paragraph(ligne, style))
            self.elements.append(Spacer(1, 3 * mm))
        return self

    def avec_signatures(self, *libelles):
        cellules = [[Paragraph(f"<b>{l}</b>", STYLE) for l in libelles], [""] * len(libelles)]
        tableau = Table(cellules, colWidths=[LARGEUR_UTILE / len(libelles)] * len(libelles), rowHeights=[None, 22 * mm])
        tableau.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.4, GRIS_CLAIR), ("INNERGRID", (0, 0), (-1, -1), 0.4, GRIS_CLAIR),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        self.elements += [Spacer(1, 4 * mm), tableau]
        return self

    # -- rendu -------------------------------------------------------------
    def contenu(self):
        tampon = BytesIO()
        modele = SimpleDocTemplate(
            tampon, pagesize=A4, leftMargin=MARGE, rightMargin=MARGE, topMargin=MARGE, bottomMargin=27 * mm,
            title=f"{self.titre} {self.numero}", author=self.entreprise.raison_sociale,
        )
        document = self

        class Canevas(_CanevasNumerote):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, document=document, **kwargs)

        modele.build(self.elements, canvasmaker=Canevas)
        return tampon.getvalue()

    def reponse(self, nom_fichier, telecharger=False):
        """Réponse HTTP application/pdf (affichée dans le navigateur, ou téléchargée)."""
        reponse = HttpResponse(self.contenu(), content_type="application/pdf")
        disposition = "attachment" if telecharger else "inline"
        reponse["Content-Disposition"] = f'{disposition}; filename="{nom_fichier}.pdf"'
        return reponse


def telecharger(request):
    """?telecharger=1 force le téléchargement au lieu de l'affichage."""
    return request.query_params.get("telecharger") in ("1", "true", "oui")
