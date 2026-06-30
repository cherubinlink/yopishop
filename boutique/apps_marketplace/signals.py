# =============================================================================
# SECTION 8 : SIGNAL AUTO-CRÉATION BOUTIQUE (dans signals.py)
# =============================================================================
# Ce code doit être placé dans app_marketplace/signals.py
# et enregistré dans app_marketplace/apps.py → ready()
#
# ── app_marketplace/signals.py ───────────────────────────────────────────────
#
from django.db.models.signals import post_save,  pre_save
from django.dispatch import receiver
from apps_core.models import Produit
from apps_marketplace.models import Boutique
from django.utils.text import slugify
import uuid
from decimal import Decimal
from django.contrib.auth import get_user_model
import logging

from .models import Commande, ArticleCommande

logger = logging.getLogger(__name__)
User = get_user_model()


@receiver(post_save, sender=Produit)
def auto_creer_boutique_individuelle(sender, instance, created, **kwargs):
#     """
#     Crée automatiquement une boutique minimale pour un vendeur individuel
#     ou YopiShop qui publie son premier produit sans avoir de boutique.
#     """
    if not created:
        return
    vendeur = instance.vendeur
    if vendeur.a_boutique:
        return  # Boutique déjà existante
    if vendeur.type_vendeur not in ('individuel', 'yopishop'):
        return  # Acheteur ou autre : ne pas créer de boutique
#
    slug_base    = slugify(vendeur.get_full_name() or vendeur.username)
    uid_suffix   = str(uuid.uuid4())[:6]
    sous_domaine = f"{slug_base}-{uid_suffix}"
#
    Boutique.objects.create(
        vendeur       = vendeur,
        nom           = f"Boutique de {vendeur.nom_complet}",
        slug          = f"{slug_base}-{uid_suffix}",
        sous_domaine  = sous_domaine,
        description   = "Vendeur individuel sur YopiShop.",
        email         = vendeur.email or '',
        telephone     = vendeur.telephone or '',
        adresse       = vendeur.adresse or '',
        ville         = vendeur.ville.nom if vendeur.ville else '',
        politique_retour  = "Contactez le vendeur directement.",
        type_boutique     = 'individuelle',
        est_auto_creee    = True,
        statut            = 'active',  # Pas de validation manuelle pour individuel
        taux_commission   = Decimal('15'),
    )


@receiver(pre_save, sender=Commande)
def commande_pre_save(sender, instance, **kwargs):
    """
    Mémorise l'ancien statut avant modification
    pour comparer dans post_save.
    """
    if instance.pk:
        try:
            instance._ancien_statut = Commande.objects.get(pk=instance.pk).statut
        except Commande.DoesNotExist:
            instance._ancien_statut = None
    else:
        instance._ancien_statut = None


@receiver(post_save, sender=Commande)
def commande_post_save(sender, instance, created, **kwargs):
    """
    Déclenche les transactions wallet quand une commande passe à 'livree'.
    """
    if created:
        return

    ancien  = getattr(instance, '_ancien_statut', None)
    nouveau = instance.statut

    # On traite uniquement la transition → 'livree'
    if nouveau != 'livree' or ancien == 'livree':
        return

    _crediter_vendeurs_apres_livraison(instance)


def _crediter_vendeurs_apres_livraison(commande):
    """
    Pour chaque article de la commande :
      - Crédite le vendeur du montant net (prix_total - commission)
      - Crédite le compte YopiShop de la commission
    Gère les vendeurs individuels (sans boutique) et les vendeurs pro.
    """
    # Récupérer le compte YopiShop (type_vendeur='yopishop')
    compte_yopishop = User.objects.filter(
        type_vendeur='yopishop', is_active=True
    ).first()

    articles = commande.articles.select_related(
        'produit__vendeur', 'boutique'
    ).all()

    for art in articles:
        vendeur    = art.produit.vendeur
        commission = art.commission_boutique
        montant_net = art.prix_total - commission

        # ── Créditer le vendeur ──────────────────────────────────────────
        if montant_net > 0:
            try:
                vendeur.crediter_wallet(
                    montant=montant_net,
                    description=(
                        f"Vente — {art.produit.titre} x{art.quantite} "
                        f"(commande {commande.numero_commande})"
                    )
                )
                logger.info(
                    f"[WALLET] Vendeur {vendeur.username} crédité "
                    f"de {montant_net} XAF (commande {commande.numero_commande})"
                )
            except Exception as e:
                logger.error(
                    f"[WALLET] Erreur crédit vendeur {vendeur.username} : {e}"
                )

        # ── Créditer YopiShop de la commission ───────────────────────────
        if commission > 0 and compte_yopishop:
            try:
                compte_yopishop.crediter_wallet(
                    montant=commission,
                    description=(
                        f"Commission {art.taux_commission_applique}% — "
                        f"{art.produit.titre} "
                        f"(commande {commande.numero_commande}, "
                        f"vendeur {vendeur.username})"
                    )
                )
                logger.info(
                    f"[WALLET] Commission {commission} XAF créditée "
                    f"sur compte YopiShop (commande {commande.numero_commande})"
                )
            except Exception as e:
                logger.error(
                    f"[WALLET] Erreur crédit commission YopiShop : {e}"
                )

        # ── Créer la TransactionWallet de commission côté vendeur ─────────
        # (ligne de débit de commission dans l'historique du vendeur)
        if commission > 0:
            from apps_core.models import TransactionWallet
            TransactionWallet.objects.create(
                utilisateur=vendeur,
                montant=commission,
                type_transaction='commission',
                description=(
                    f"Commission YopiShop {art.taux_commission_applique}% "
                    f"— commande {commande.numero_commande}"
                ),
                solde_apres=vendeur.solde_wallet,
            )

    # ── Notification au(x) vendeur(s) ────────────────────────────────────
    vendeurs_notifies = set()
    for art in articles:
        vendeur = art.produit.vendeur
        if vendeur.pk in vendeurs_notifies:
            continue
        vendeurs_notifies.add(vendeur.pk)

        montant_total_vendeur = sum(
            (a.prix_total - a.commission_boutique)
            for a in articles
            if a.produit.vendeur_id == vendeur.pk
        )

        try:
            from apps_core.views_notifications import creer_notification
            creer_notification(
                utilisateur=vendeur,
                type_notification='paiement',
                titre="💰 Paiement reçu sur votre wallet",
                message=(
                    f"{montant_total_vendeur:,.0f} FCFA ont été crédités sur "
                    f"votre YopiPay pour la commande {commande.numero_commande}."
                ),
                lien=f"/wallet/",
            )
        except Exception as e:
            logger.error(f"[NOTIF] Erreur notification vendeur : {e}")


def _crediter_vendeurs_apres_livraison(commande):
    # ← Garde anti-double exécution
    if commande.wallet_credite:
        logger.warning(
            f"[WALLET] Wallet déjà crédité pour commande {commande.numero_commande}"
        )
        return

    # ... tout le code de crédit ...

    # Marquer comme traité
    Commande.objects.filter(pk=commande.pk).update(wallet_credite=True)
    logger.info(
        f"[WALLET] Commande {commande.numero_commande} — wallets crédités ✓"
    )


@receiver(pre_save, sender=Commande)
def commande_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._ancien_statut = Commande.objects.get(pk=instance.pk).statut
        except Commande.DoesNotExist:
            instance._ancien_statut = None
    else:
        instance._ancien_statut = None


@receiver(post_save, sender=Commande)
def commande_post_save(sender, instance, created, **kwargs):
    if created:
        return

    ancien  = getattr(instance, '_ancien_statut', None)
    nouveau = instance.statut

    if nouveau != 'livree' or ancien == 'livree':
        return

    # ← BNPL : vérifier que toutes les tranches sont payées
    if instance.est_paiement_fractionne:
        try:
            plan = instance.plan_paiement
            if not plan.est_complet():
                # Annuler le passage à 'livree' et remettre à 'expediee'
                Commande.objects.filter(pk=instance.pk).update(statut='expediee')
                import logging
                logging.getLogger(__name__).warning(
                    f"[BNPL] Commande {instance.numero_commande} : "
                    f"passage à 'livree' bloqué — tranches non toutes payées."
                )
                return
        except PlanPaiement.DoesNotExist:
            # Pas de plan encore → bloquer aussi
            Commande.objects.filter(pk=instance.pk).update(statut='expediee')
            return

    _crediter_vendeurs_apres_livraison(instance)
