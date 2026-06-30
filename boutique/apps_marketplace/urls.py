# =============================================================================
# app_marketplace/urls.py
# =============================================================================
# À inclure dans votre urls.py principal :
#
#   from django.urls import path, include
#
#   urlpatterns = [
#       ...
#       path('', include('app_marketplace.urls', namespace='app_marketplace')),
#       ...
#   ]
#
# =============================================================================

from django.urls import path
from . import views as views_m

app_name = 'app_marketplace'

urlpatterns = [

    # ──────────────────────────────────────────────────────────────
    # BOUTIQUES PUBLIQUES
    # ──────────────────────────────────────────────────────────────

    # Liste de toutes les boutiques actives
    # GET /boutiques/
    path('boutiques/',views_m.boutiques_liste,name='boutiques_liste',),

    # Créer une boutique
    # GET/POST /boutiques/creer/
    path('boutiques/creer/',views_m.creer_boutique,name='creer_boutique',),


    
    # ──────────────────────────────────────────────────────────────
    # EMPLOYÉS BOUTIQUE
    # ──────────────────────────────────────────────────────────────
    # Liste + ajout d'employés
    # GET/POST /boutiques/equipe/
    path('boutiques/equipe/',views_m.employes_boutique,name='employes_boutique',),

    # Mes avis reçus (vendeur connecté)
    # GET /boutiques/mes-avis/
    path('boutiques/mes-avis/',views_m.mes_avis_recus,name='mes_avis_recus',),

    # Liste admin des KYC à traiter
    # GET /admin/kyc/
    path('admin/kyc/',views_m.admin_kyc_liste,name='admin_kyc_liste',),

    # Liste + upload documents KYC
    # GET/POST /boutiques/kyc/
    path('boutiques/kyc/',views_m.kyc_documents,name='kyc_documents',),

    
    # ──────────────────────────────────────────────────────────────
    # DASHBOARD VENDEUR
    # ──────────────────────────────────────────────────────────────
    # Tableau de bord principal
    # GET /dashboard/vendeur/
    path('dashboard/vendeur/',views_m.dashboard_vendeur,name='dashboard_vendeur',),

    # Page publique d'une boutique
    # GET /boutiques/<slug>/
    path('boutiques/<slug:slug>/',views_m.boutique_detail,name='boutique_detail',),

    # ──────────────────────────────────────────────────────────────
    # GESTION BOUTIQUE (vendeur connecté)
    # ──────────────────────────────────────────────────────────────

    

    # Éditer une boutique
    # GET/POST /boutiques/<slug>/editer/
    path('boutiques/<slug:slug>/editer/',views_m.editer_boutique,name='editer_boutique',),

    # Changer le statut d'une boutique (admin, AJAX POST)
    # POST /boutiques/<slug>/statut/
    path('boutiques/<slug:slug>/statut/',views_m.toggle_statut_boutique,name='toggle_statut_boutique',),


    # Activer/désactiver un employé (AJAX POST)
    # POST /boutiques/equipe/<pk>/toggle/
    path('boutiques/equipe/<int:pk>/toggle/',views_m.toggle_employe,name='toggle_employe',),

    # Supprimer un employé
    # POST /boutiques/equipe/<pk>/supprimer/
    path('boutiques/equipe/<int:pk>/supprimer/',views_m.supprimer_employe,name='supprimer_employe',),

    # ──────────────────────────────────────────────────────────────
    # KYC — Documents de vérification (vendeur)
    # ──────────────────────────────────────────────────────────────

    # Supprimer un document KYC
    # POST /boutiques/kyc/<pk>/supprimer/
    path('boutiques/kyc/<int:pk>/supprimer/',views_m.supprimer_document_kyc,name='supprimer_document_kyc',),

    # ──────────────────────────────────────────────────────────────
    # ADMIN KYC
    # ──────────────────────────────────────────────────────────────

   

    # Valider ou refuser un document KYC (AJAX POST)
    # POST /admin/kyc/<pk>/valider/
    path('admin/kyc/<int:pk>/valider/',views_m.admin_kyc_valider,name='admin_kyc_valider',),

    # ──────────────────────────────────────────────────────────────
    # AVIS VENDEUR
    # ──────────────────────────────────────────────────────────────

    # Ajouter un avis sur un vendeur après commande
    # POST /commandes/<commande_pk>/avis-vendeur/
    path('commandes/<int:commande_pk>/avis-vendeur/',views_m.ajouter_avis_vendeur,name='ajouter_avis_vendeur',),

   

    # Répondre à un avis reçu (POST, AJAX compatible)
    # POST /boutiques/mes-avis/<pk>/repondre/
    path('boutiques/mes-avis/<int:pk>/repondre/',views_m.repondre_avis_vendeur,name='repondre_avis_vendeur',),

    # ──────────────────────────────────────────────────────────────
    # ADMIN — DEMANDES VENDEUR
    # ──────────────────────────────────────────────────────────────

    # Liste admin des candidatures vendeur
    # GET /admin/demandes-vendeur/
    path('admin/demandes-vendeur/',views_m.admin_demandes_vendeur,name='admin_demandes_vendeur',),

    # Détail + actions sur une candidature (admin)
    # GET/POST /admin/demandes-vendeur/<pk>/
    path('admin/demandes-vendeur/<int:pk>/',views_m.admin_demande_detail,name='admin_demande_detail',),

    # ──────────────────────────────────────────────────────────────
    # AJAX
    # ──────────────────────────────────────────────────────────────

    # Vérifier disponibilité d'un sous-domaine boutique
    # GET /boutiques/ajax/sous-domaine/?q=mon-shop
    path('boutiques/ajax/sous-domaine/',views_m.ajax_verifier_sous_domaine_boutique,name='ajax_verifier_sous_domaine',),

    # Stats rapides du vendeur (dashboard, JSON)
    # GET /boutiques/ajax/stats/
    path('boutiques/ajax/stats/',views_m.ajax_stats_vendeur,name='ajax_stats_vendeur',),


    
    # =========================================================================
    # PANIER
    # =========================================================================
 
    # Voir le panier
    path('panier/',views_m.voir_panier,name='voir_panier',),
 
    # Ajouter un produit au panier (AJAX POST)
    path('panier/ajouter/<uuid:produit_id>/', views_m.ajouter_au_panier, name='ajouter_au_panier'),
 
    # Modifier la quantité d'un article (AJAX POST)
    path('panier/article/<int:article_id>/modifier/',views_m.modifier_quantite_panier,name='modifier_quantite_panier',),
 
    # Retirer un article du panier (AJAX POST)
    path('panier/article/<int:article_id>/retirer/',views_m.retirer_du_panier,name='retirer_du_panier',),
 
    # Vider le panier entièrement
    path('panier/vider/',views_m.vider_panier,name='vider_panier',),
 
    # Compteur panier pour badge navbar (AJAX GET)
    path('panier/ajax/compteur/',views_m.ajax_compteur_panier,name='ajax_compteur_panier',),
 
    # =========================================================================
    # CHECKOUT
    # =========================================================================
 
    # Finaliser la commande
    path('commande/passer/',views_m.passer_commande,name='passer_commande',),
 
    # Page de confirmation après création
    path('commande/<uuid:pk>/confirmation/',views_m.commande_confirmation,name='commande_confirmation',),
 
    # =========================================================================
    # MES COMMANDES (acheteur)
    # =========================================================================
 
    # Liste de mes commandes
    path('commandes/',views_m.mes_commandes,name='mes_commandes',),
 
    # Détail d'une commande (acheteur, vendeur concerné, ou admin)
    path('commandes/<uuid:pk>/',views_m.commande_detail,name='commande_detail',),
 
    # Annuler une commande
    path('commandes/<uuid:pk>/annuler/',views_m.annuler_commande,name='annuler_commande',),
 
    # =========================================================================
    # COMMANDES REÇUES (vendeur)
    # =========================================================================
 
    # Liste des commandes reçues par le vendeur connecté
    path('vendeur/commandes/',views_m.commandes_recues,name='commandes_recues',),
 
    # Changer le statut d'une commande (vendeur, AJAX POST)
    path('vendeur/commandes/<uuid:pk>/statut/',views_m.changer_statut_commande,name='changer_statut_commande',),
 
    # =========================================================================
    # ADMIN
    # =========================================================================
 
    # Vue globale de toutes les commandes (admin)
    path('admin/commandes/',views_m.admin_commandes_liste,name='admin_commandes_liste',),


    # =========================================================================
    # AJAX - CLIENT
    # =========================================================================

    path('codes-promo/ajax/verifier/',views_m.ajax_verifier_code_promo,name='ajax_verifier_code_promo'),

    path('codes-promo/ajax/appliquer/',views_m.ajax_appliquer_code,name='ajax_appliquer_code'),

    path('codes-promo/ajax/retirer/',views_m.ajax_retirer_code,name='ajax_retirer_code'),

    # =========================================================================
    # VENDEUR
    # =========================================================================

    path('codes-promo/',views_m.mes_codes_promo,name='mes_codes_promo'),

    path('codes-promo/creer/',views_m.creer_code_promo,name='creer_code_promo'),

    path('codes-promo/<uuid:pk>/modifier/',views_m.modifier_code_promo,name='modifier_code_promo'),

    path('codes-promo/<uuid:pk>/supprimer/',views_m.supprimer_code_promo,name='supprimer_code_promo'),

    path('codes-promo/<uuid:pk>/toggle-statut/',views_m.toggle_statut_code_promo,name='toggle_statut_code_promo'),

    path('codes-promo/<uuid:pk>/stats/',views_m.stats_code_promo,name='stats_code_promo'),

    # =========================================================================
    # ADMIN
    # =========================================================================

    path('admin/codes-promo/',views_m.admin_codes_promo_liste,name='admin_codes_promo_liste'),

    # ==========================================================
    # PAIEMENTS - ACHETEUR
    # ==========================================================

    path('paiements/',views_m.mes_paiements,name='mes_paiements'),

    path('paiements/<int:pk>/',views_m.paiement_detail,name='paiement_detail'),

    path('commandes/<uuid:commande_pk>/payer/',views_m.initier_paiement,name='initier_paiement'),

    path('commandes/<uuid:commande_pk>/soumettre-preuve/',views_m.soumettre_preuve_paiement,name='soumettre_preuve_paiement'),

    # ==========================================================
    # PLAN DE PAIEMENT BNPL
    # ==========================================================

    path('commandes/<uuid:commande_pk>/plan-paiement/',views_m.mon_plan_paiement,name='mon_plan_paiement'),
    path('commandes/<uuid:commande_pk>/ajax-plan-paiement/',views_m.ajax_plan_paiement,name='ajax_plan_paiement'),

    # ==========================================================
    # ADMIN - PAIEMENTS
    # ==========================================================

    path('admin/paiements/',views_m.admin_paiements_liste,name='admin_paiements_liste'),

    path('admin/paiements/<int:pk>/valider/',views_m.admin_valider_paiement,name='admin_valider_paiement'),

    path('admin/paiements/<int:pk>/rejeter/',views_m.admin_rejeter_paiement,name='admin_rejeter_paiement'),

    path('admin/paiements/<int:pk>/suspect/',views_m.admin_marquer_suspect,name='admin_marquer_suspect'),

    # ==========================================================
    # ADMIN - PLAN DE PAIEMENT
    # ==========================================================

    path('admin/commandes/<uuid:commande_pk>/creer-plan/',views_m.admin_creer_plan_paiement,name='admin_creer_plan_paiement'),

    # ==========================================================
    # ADMIN - OPERATEURS
    # ==========================================================

    path('admin/operateurs/',views_m.admin_operateurs,name='admin_operateurs'),

    path('admin/numeros-versement/',views_m.admin_numeros_versement,name='admin_numeros_versement'),

    # ==========================================================
    # AJAX PUBLIC
    # ==========================================================

    path('paiements/ajax/numeros-versement/',views_m.ajax_numeros_versement,name='ajax_numeros_versement'),

    path('paiements/ajax/operateurs/',views_m.ajax_operateurs_actifs,name='ajax_operateurs_actifs'),


    # =============================================================================
    # RETOURS PRODUITS
    # =============================================================================

    # ----------------------------
    # ACHETEUR
    # ----------------------------

    # Mes demandes de retour
    path('retours/',views_m.mes_retours,name='mes_retours',),

    # Demander un retour pour un article d'une commande
    path('commandes/<uuid:commande_pk>/articles/<int:article_pk>/retour/',views_m.demander_retour, name='demander_retour',),

    # Détail d'un retour
    path('retours/<uuid:pk>/',views_m.retour_detail,name='retour_detail',),

    # Annuler une demande de retour
    path('retours/<uuid:pk>/annuler/',views_m.annuler_retour,name='annuler_retour',),


    # ----------------------------
    # VENDEUR
    # ----------------------------

    # Retours reçus sur les produits du vendeur
    path('vendeur/retours/',views_m.retours_recus,name='retours_recus',),


    # ----------------------------
    # ADMIN
    # ----------------------------

    # Liste de tous les retours
    path('admin/retours/',views_m.admin_retours_liste,name='admin_retours_liste',),

    # Détail d'un retour
    path('admin/retours/<uuid:pk>/',views_m.admin_retour_detail,name='admin_retour_detail',),

    # Traitement d'un retour (Approuver / Refuser / En cours / Complété)
    path('admin/retours/<uuid:pk>/traiter/',views_m.admin_traiter_retour,name='admin_traiter_retour',),


    # ----------------------------
    # AJAX
    # ----------------------------

    # Récupération du statut d'un retour (polling)
    path('retours/<uuid:pk>/ajax/statut/',views_m.ajax_statut_retour,name='ajax_statut_retour',),

    # =========================================================================
    # PUBLIC — Découverte
    # =========================================================================
 
    path('achats-groupes/', views_m.groupes_actifs, name='groupes_actifs'),
    path('achats-groupes/<uuid:pk>/', views_m.groupe_detail, name='groupe_detail'),
 
    # Rejoindre / quitter (AJAX)
    path('achats-groupes/<uuid:pk>/rejoindre/', views_m.ajax_rejoindre_groupe, name='ajax_rejoindre_groupe'),
    path('achats-groupes/<uuid:pk>/quitter/', views_m.ajax_quitter_groupe, name='ajax_quitter_groupe'),
 
    # Polling statut temps réel
    path('achats-groupes/<uuid:pk>/ajax-statut/', views_m.ajax_statut_groupe, name='ajax_statut_groupe'),
 
    # =========================================================================
    # VENDEUR — Gestion (produits limités au vendeur connecté)
    # =========================================================================
 
    path('vendeur/achats-groupes/', views_m.mes_groupes_achat, name='mes_groupes_achat'),
    path('vendeur/achats-groupes/creer/', views_m.creer_groupe_achat, name='creer_groupe_achat'),
    path('vendeur/achats-groupes/<uuid:pk>/modifier/', views_m.modifier_groupe_achat, name='modifier_groupe_achat'),
    path('vendeur/achats-groupes/<uuid:pk>/annuler/', views_m.annuler_groupe_achat, name='annuler_groupe_achat'),
    path('vendeur/achats-groupes/<uuid:pk>/finaliser/', views_m.finaliser_groupe, name='finaliser_groupe'),
 
    # =========================================================================
    # ADMIN
    # =========================================================================
 
    path('admin/achats-groupes/', views_m.admin_groupes_liste, name='admin_groupes_liste'),
    path('admin/achats-groupes/finaliser-expires/', views_m.admin_finaliser_groupes_expires, name='admin_finaliser_groupes_expires'),

]

# from .urls_panier_commandes import panier_commandes_urlpatterns
# urlpatterns += panier_commandes_urlpatterns