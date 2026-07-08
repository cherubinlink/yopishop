"""
Signaux centralisant la création automatique de notifications.
Chaque signal réagit à un événement métier et appelle creer_notification().
"""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Avis, Produit, Notification
from apps_core.views import creer_notification


# ─────────────────────────────────────────────────────────────────────────
# AVIS — notifier le vendeur qu'il a reçu un nouvel avis
# ─────────────────────────────────────────────────────────────────────────
@receiver(post_save, sender=Avis)
def notifier_nouvel_avis(sender, instance, created, **kwargs):
    if not created:
        return
    creer_notification(
        utilisateur=instance.produit.vendeur,
        type_notification='commande',  # ajoute un type 'avis' aux TYPE_CHOICES si tu veux le distinguer
        titre="Nouvel avis reçu",
        message=(
            f"{instance.utilisateur.username} a laissé un avis "
            f"{instance.note}★ sur « {instance.produit.titre} »."
        ),
        lien=f"/produits/{instance.produit.slug}/#avis",
    )


# ─────────────────────────────────────────────────────────────────────────
# STOCK FAIBLE — notifier le vendeur quand le stock passe sous le seuil
# ─────────────────────────────────────────────────────────────────────────
@receiver(pre_save, sender=Produit)
def notifier_stock_faible(sender, instance, **kwargs):
    if not instance.pk:
        return  # création, rien à comparer

    try:
        ancien = Produit.objects.get(pk=instance.pk)
    except Produit.DoesNotExist:
        return

    stock_avant = ancien.quantite_stock
    stock_apres = instance.quantite_stock
    seuil       = instance.alerte_stock_min

    # Le stock vient de passer sous le seuil d'alerte
    if stock_avant > seuil >= stock_apres:
        creer_notification(
            utilisateur=instance.vendeur,
            type_notification='alerte_stock',
            titre="Stock faible",
            message=(
                f"Il ne reste que {stock_apres} unité(s) de « {instance.titre} ». "
                f"Pensez à réapprovisionner."
            ),
            lien=f"/vendeur/produits/{instance.pk}/modifier/",  # adapte l'URL réelle
        )


# ─────────────────────────────────────────────────────────────────────────
# GABARIT — adapte avec tes vrais modèles Commande / Paiement / Enchere
# Décommente et adapte les imports en haut du fichier une fois prêt.
# ─────────────────────────────────────────────────────────────────────────
#
from apps_marketplace.models import Commande, Paiement

@receiver(post_save, sender=Commande)
def notifier_commande(sender, instance, created, **kwargs):
    if not created:
        return

    # Notification client
    creer_notification(
        utilisateur=instance.utilisateur,
        type_notification='commande',
        titre="Commande confirmée",
        message=f"Votre commande #{instance.numero_commande} a été confirmée.",
        lien=f"/commandes/{instance.id}/",
    )

    # Notification des vendeurs
    vendeurs_notifies = set()

    for article in instance.articles.select_related("produit__vendeur"):
        vendeur = article.produit.vendeur

        if vendeur.pk in vendeurs_notifies:
            continue

        vendeurs_notifies.add(vendeur.pk)

        creer_notification(
            utilisateur=vendeur,
            type_notification='commande',
            titre="Nouvelle commande reçue",
            message=f"Une nouvelle commande contient vos produits.",
            lien=f"/vendeur/commandes/{instance.id}/",
        )

@receiver(post_save, sender=Paiement)
def notifier_paiement(sender, instance, created, **kwargs):
    if created and instance.statut == 'reussi':
        creer_notification(
            utilisateur=instance.utilisateur,
            type_notification='paiement',
            titre="Paiement confirmé",
            message=f"Votre paiement de {instance.montant} {instance.devise} a été validé.",
            lien=f"/compte/paiements/{instance.id}/",
        )