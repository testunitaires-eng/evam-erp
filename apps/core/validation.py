"""
Outils de validation partagés par tous les modules métier.

Principe appliqué dans tout le projet : AUCUN enregistrement ne doit
être écrit en base tant que toutes les règles métier ne sont pas
vérifiées. Concrètement :

- les règles de cohérence d'un modèle sont écrites dans sa méthode
  clean() (une seule source de vérité) ;
- ValidationAvantEnregistrement appelle clean() AVANT chaque save(),
  quelle que soit la voie d'entrée (API, admin Django, shell, code
  interne d'un autre module) ;
- côté API, ValidationModeleMixin (apps/core/serializers.py) appelle
  ce même clean() pendant la validation DRF pour renvoyer un 400
  propre avec le message d'erreur, avant tout appel à save().
"""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError


class ValidationAvantEnregistrement:
    """
    Mixin de modèle : appelle clean() avant toute écriture en base.

    À placer AVANT models.Model dans l'héritage, par exemple :
        class Commande(ValidationAvantEnregistrement, models.Model)

    Un save(update_fields=[...]) (mise à jour technique ciblée d'un
    champ calculé) ne relance pas la validation complète.

    Si le modèle définit verifier_suppression(), elle est appelée avant
    toute suppression (ex : ligne d'une commande déjà validée).
    """

    def save(self, *args, **kwargs):
        if not kwargs.get("update_fields"):
            self.clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        verifier = getattr(self, "verifier_suppression", None)
        if verifier is not None:
            verifier()
        return super().delete(*args, **kwargs)


# Pour les viewsets de documents historiques (mouvements, encaissements,
# sorties matières...) : création et lecture uniquement. Les modifier ou
# les supprimer après coup désynchroniserait le stock ou la caisse.
METHODES_CREATION_LECTURE = ["get", "post", "head", "options"]


def exiger_positif(valeur, champ, libelle, strict=True):
    """Lève ValidationError si valeur est absente, négative, ou nulle (si strict)."""
    if valeur is None:
        raise ValidationError({champ: f"{libelle} est obligatoire."})
    if strict and valeur <= 0:
        raise ValidationError({champ: f"{libelle} doit être strictement supérieur(e) à 0."})
    if not strict and valeur < 0:
        raise ValidationError({champ: f"{libelle} ne peut pas être négatif(ve)."})


def exiger_positif_optionnel(valeur, champ, libelle, strict=False):
    """Comme exiger_positif, mais accepte une valeur vide."""
    if valeur is not None:
        exiger_positif(valeur, champ, libelle, strict=strict)


def exiger_ordre_dates(debut, fin, champ_fin, libelle_debut, libelle_fin):
    """Lève ValidationError si fin est antérieure à debut (les deux étant renseignés)."""
    if debut and fin and fin < debut:
        raise ValidationError({champ_fin: f"{libelle_fin} ne peut pas être antérieure à {libelle_debut}."})


def exiger_pourcentage(valeur, champ, libelle):
    """Lève ValidationError si valeur n'est pas comprise entre 0 et 100."""
    if valeur is not None and not (0 <= valeur <= 100):
        raise ValidationError({champ: f"{libelle} doit être compris entre 0 et 100."})


def valeur_en_base(instance, champ):
    """
    Valeur actuellement ENREGISTRÉE en base pour ce champ (None si
    l'objet n'existe pas encore). Sert à contrôler les transitions de
    statut et le verrouillage des documents.
    """
    if instance.pk is None:
        return None
    return (
        type(instance)._default_manager.filter(pk=instance.pk)
        .values_list(champ, flat=True).first()
    )


def convertir_decimal(valeur, libelle, obligatoire=True, strict=True):
    """
    Convertit une valeur reçue dans le corps d'une requête (chaîne,
    entier, flottant) en Decimal positif. Lève ValueError avec un
    message clair sinon (les actions API interceptent ValueError et
    répondent 400).
    """
    if valeur is None or valeur == "":
        if obligatoire:
            raise ValueError(f"{libelle} est obligatoire.")
        return None
    try:
        resultat = Decimal(str(valeur))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{libelle} doit être un nombre (reçu : {valeur!r}).")
    if not resultat.is_finite():
        raise ValueError(f"{libelle} doit être un nombre (reçu : {valeur!r}).")
    if strict and resultat <= 0:
        raise ValueError(f"{libelle} doit être strictement supérieur(e) à 0.")
    if not strict and resultat < 0:
        raise ValueError(f"{libelle} ne peut pas être négatif(ve).")
    return resultat


def verifier_transition(ancien, nouveau, transitions, libelle="statut", initial=None):
    """
    Vérifie qu'un passage de statut ancien -> nouveau est autorisé.
    `transitions` : dict {statut_de_depart: {statuts_d_arrivee_autorises}}.
    `initial` : si fourni, statut obligatoire à la création (ancien is None).
    Lève ValidationError sinon.
    """
    if ancien is None:
        if initial is not None and nouveau != initial:
            raise ValidationError({
                "statut": f"À la création, le {libelle} doit être « {initial} » (reçu : « {nouveau} »)."
            })
        return
    if ancien == nouveau:
        return
    if nouveau not in transitions.get(ancien, set()):
        raise ValidationError({
            "statut": f"Passage du {libelle} « {ancien} » à « {nouveau} » non autorisé."
        })
