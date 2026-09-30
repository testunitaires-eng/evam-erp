"""
Journal de TOUTES les actions du système (cahier des charges §16.1).

Plutôt que d'écrire une ligne de journal à la main à chaque endroit (et
d'en oublier), on écoute toutes les écritures en base des modèles
métier (apps.*) :
- création     : toutes les valeurs du document ;
- modification : uniquement les champs changés, avant -> après ;
- suppression  : les valeurs du document supprimé ;
- listes (ex : agents affectés à un OF) : ajouts / retraits ;
plus les connexions (réussies ou échouées, voir apps/comptes/views.py).
Chaque ligne indique qui, quand, depuis quelle adresse IP et par quelle
requête. Quelle que soit la voie (écran, action métier, admin Django,
traitement automatique), rien n'échappe au journal. Les mots de passe ne
sont jamais écrits.
"""

from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save

from .historique import _courant, utilisateur_courant

# Modèles qui ne sont pas des actions métier (le journal lui-même, ses
# dérivés techniques) : non journalisés, pour éviter boucles et bruit.
EXCLUS = {
    "comptes.journalaction", "core.historique", "core.notification", "core.sequencenumerotation",
}
CHAMPS_IGNORES = {"last_login"}          # mis à jour à chaque connexion : bruit
CHAMPS_SECRETS = {"password"}            # jamais écrit en clair

MODULES = {
    "referentiel": "REFERENTIEL", "achats": "ACHATS", "stocks": "STOCKS", "production": "PRODUCTION",
    "qualite": "QUALITE", "commercial": "COMMERCIAL", "reclamations": "COMMERCIAL", "caisse": "CAISSE",
    "distribution": "DISTRIBUTION", "couts": "COUTS", "comptabilite": "COMPTABILITE", "fiscalite": "COMPTABILITE",
    "reporting": "COMPTABILITE", "comptes": "ADMINISTRATION", "core": "ADMINISTRATION",
}


def _suivi(modele):
    meta = modele._meta
    return modele.__module__.startswith("apps.") and f"{meta.app_label}.{meta.model_name}" not in EXCLUS


def _champs(instance):
    return [
        champ for champ in instance._meta.concrete_fields
        if champ.name not in CHAMPS_IGNORES and not getattr(champ, "auto_now", False)
    ]


def _texte(instance, champ, valeur):
    """Valeur lisible : libellé des listes de choix, nom de l'objet lié, Oui/Non."""
    if champ.name in CHAMPS_SECRETS:
        return "(masqué)"
    if valeur is None or valeur == "":
        return "—"
    if champ.is_relation:
        objet = None
        # Objet lié déjà chargé en mémoire : pas de nouvelle requête.
        if getattr(instance, champ.attname, None) == valeur and champ.is_cached(instance):
            objet = champ.get_cached_value(instance)
        if objet is None:
            objet = champ.related_model._default_manager.filter(pk=valeur).first()
        return f"{objet} (#{valeur})" if objet is not None else f"#{valeur}"
    if champ.choices:
        return str(dict(champ.flatchoices).get(valeur, valeur))
    if isinstance(valeur, bool):
        return "Oui" if valeur else "Non"
    return str(valeur)


def _instantane(instance):
    return {champ.attname: getattr(instance, champ.attname) for champ in _champs(instance)}


def _lignes(instance, valeurs, noms=None):
    return "\n".join(
        f"{champ.verbose_name} : {_texte(instance, champ, valeurs[champ.attname])}"
        for champ in _champs(instance)
        if (noms is None or champ.attname in noms) and champ.attname in valeurs
    )


def _reference(instance):
    for attribut in ("numero", "numero_lot", "code", "username"):
        valeur = getattr(instance, attribut, None)
        if valeur:
            return str(valeur)
    return str(instance.pk)


def journaliser(instance, action, ancienne="", nouvelle="", motif="", utilisateur=None, module=None):
    from apps.comptes.models import JournalAction
    requete = getattr(_courant, "requete", None)
    adresse_ip = None
    if requete is not None:
        transmise = requete.META.get("HTTP_X_FORWARDED_FOR", "")
        adresse_ip = (transmise.split(",")[0].strip() if transmise else requete.META.get("REMOTE_ADDR")) or None
    meta = instance._meta if instance is not None else None
    JournalAction.objects.create(
        utilisateur=utilisateur or utilisateur_courant(),
        module=module or (MODULES.get(meta.app_label, "ADMINISTRATION") if meta else "ADMINISTRATION"),
        action=action[:100],
        document_type=f"{meta.app_label}.{meta.model_name}" if meta else "",
        document_id=_reference(instance)[:100] if instance is not None else "",
        ancienne_valeur=ancienne, nouvelle_valeur=nouvelle, motif=motif,
        adresse_ip=adresse_ip,
        requete=f"{requete.method} {requete.path}"[:255] if requete is not None else "",
    )


def avant_enregistrement(sender, instance, raw=False, **kwargs):
    if raw or not _suivi(sender) or instance._state.adding or instance.pk is None:
        return
    avant = sender._default_manager.filter(pk=instance.pk).values(*[c.attname for c in _champs(instance)]).first()
    instance._journal_avant = avant


def apres_enregistrement(sender, instance, created, raw=False, **kwargs):
    if raw or not _suivi(sender):
        return
    nom = sender._meta.verbose_name
    if created:
        journaliser(instance, f"Création : {nom}", nouvelle=_lignes(instance, _instantane(instance)))
        return
    avant = getattr(instance, "_journal_avant", None)
    if avant is None:
        return
    apres = _instantane(instance)
    changes = {attname for attname, valeur in apres.items() if avant.get(attname) != valeur}
    instance._journal_avant = apres
    if not changes:
        return
    libelles = ", ".join(sorted(str(c.verbose_name) for c in _champs(instance) if c.attname in changes))
    journaliser(
        instance, f"Modification : {nom} ({libelles})"[:100],
        ancienne=_lignes(instance, avant, changes), nouvelle=_lignes(instance, apres, changes),
    )


def apres_suppression(sender, instance, **kwargs):
    if not _suivi(sender):
        return
    journaliser(instance, f"Suppression : {sender._meta.verbose_name}", ancienne=_lignes(instance, _instantane(instance)))


def liste_modifiee(sender, instance, action, reverse, model, pk_set, **kwargs):
    """Relations multiples (ex : agents affectés à un OF) : ajouts et retraits."""
    if reverse or action not in ("post_add", "post_remove", "pre_clear") or not _suivi(type(instance)):
        return
    champ = next((c for c in type(instance)._meta.many_to_many if c.remote_field.through is sender), None)
    libelle = champ.verbose_name if champ else "liste"
    if action == "pre_clear":
        elements = list(getattr(instance, champ.name).all()) if champ else []
        if elements:
            journaliser(instance, f"Retrait : {libelle}"[:100], ancienne=", ".join(map(str, elements)))
        return
    elements = ", ".join(str(o) for o in model._default_manager.filter(pk__in=pk_set or []))
    if action == "post_add":
        journaliser(instance, f"Ajout : {libelle}"[:100], nouvelle=elements)
    else:
        journaliser(instance, f"Retrait : {libelle}"[:100], ancienne=elements)


def brancher():
    pre_save.connect(avant_enregistrement, dispatch_uid="journal_pre_save")
    post_save.connect(apres_enregistrement, dispatch_uid="journal_post_save")
    post_delete.connect(apres_suppression, dispatch_uid="journal_post_delete")
    m2m_changed.connect(liste_modifiee, dispatch_uid="journal_m2m")
