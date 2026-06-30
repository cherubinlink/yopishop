from django.urls import path
from apps_core import views as views_u
 
app_name = 'apps_core'
 
urlpatterns = [
 
    # =========================================================================
    # ACCUEIL
    # =========================================================================
    path('',views_u.accueil,name='accueil'),
 
    # =========================================================================
    # AUTHENTIFICATION
    # =========================================================================
 
    # Inscription
    path('compte/inscription/',views_u.inscription,name='inscription',),
 
    # Connexion
    path('compte/connexion/',views_u.connexion,name='connexion',),
 
    # Déconnexion
    path('compte/deconnexion/',views_u.deconnexion,name='deconnexion',),
 
    # =========================================================================
    # VÉRIFICATION EMAIL
    # =========================================================================
 
    # Vérifier email via lien (uidb64 + token)
    path('compte/verifier-email/<uidb64>/<token>/',views_u.verifier_email,name='verifier_email',),
 
    # Renvoyer l'email de vérification
    path('compte/renvoyer-verification/',views_u.renvoyer_email_verification,name='renvoyer_email_verification',),
 
    # =========================================================================
    # MOT DE PASSE — Utilisateur connecté
    # =========================================================================
 
    path('compte/mot-de-passe/changer/',views_u.changer_mot_de_passe,name='changer_mot_de_passe',),
 
    # =========================================================================
    # MOT DE PASSE — Réinitialisation (utilisateur déconnecté)
    # =========================================================================
 
    # 1. Saisir l'email
    path('compte/mot-de-passe/reinitialiser/',views_u.ReinitMotDePasseView.as_view(),name='reinit_mot_de_passe',),
 
    # 2. Email envoyé (confirmation)
    path('compte/mot-de-passe/reinitialisation-envoye/',views_u.ReinitMotDePasseEnvoyeView.as_view(),name='reinit_mot_de_passe_envoye',),
 
    # 3. Lien depuis l'email → saisir le nouveau mot de passe
    path('compte/mot-de-passe/nouveau/<uidb64>/<token>/',views_u.ConfirmerNouveauMdpView.as_view(),name='confirmer_nouveau_mdp',),
 
    # 4. Réinitialisation terminée
    path('compte/mot-de-passe/reinitialisation-terminee/',views_u.ReinitTermineeView.as_view(),name='reinit_terminee',),
 
    # =========================================================================
    # TABLEAU DE BORD
    # =========================================================================
 
    path('compte/tableau-de-bord/',views_u.tableau_de_bord,name='tableau_de_bord',),
 
    # =========================================================================
    # PROFIL
    # =========================================================================
 
    # Voir son profil
    path('compte/profil/',views_u.profil,name='profil',),
 
    # Modifier les infos de base (avatar, nom, email, bio...)
    path('compte/profil/modifier/',views_u.modifier_profil,name='modifier_profil',),
 
    # Modifier l'adresse
    path('compte/profil/adresse/',views_u.modifier_adresse,name='modifier_adresse',),
 
    # Modifier les préférences (langue, devise, notifications)
    path('compte/profil/preferences/',views_u.modifier_preferences,name='modifier_preferences',),
 
    # Modifier le sous-domaine boutique
    path('compte/profil/sous-domaine/',views_u.modifier_sous_domaine,name='modifier_sous_domaine',),
 
    # Supprimer l'avatar
    path('compte/profil/supprimer-avatar/',views_u.supprimer_avatar,name='supprimer_avatar',),
 
    # Supprimer le compte
    path('compte/profil/supprimer-compte/',views_u.supprimer_compte,name='supprimer_compte',),
 
    # =========================================================================
    # PROFIL PUBLIC VENDEUR (accessible par tous)
    # =========================================================================
 
    path('vendeurs/<str:username>/',views_u.profil_vendeur_public,name='profil_vendeur_public',),
 
    # =========================================================================
    # DEVENIR VENDEUR
    # =========================================================================
 
    path('compte/devenir-vendeur/',views_u.devenir_vendeur,name='devenir_vendeur',),
 
    # =========================================================================
    # WALLET YOPIPAY
    # =========================================================================
 
    # Vue principale wallet
    path('compte/wallet/',views_u.wallet,name='wallet',),
    path('compte/wallet/recharger/',  views_u.recharger_wallet,  name='recharger_wallet'),
   
 
    # Historique complet
    path('compte/wallet/historique/',views_u.historique_transactions,name='historique_transactions',),
 
    # =========================================================================
    # NOTIFICATIONS
    # =========================================================================
 
    # Liste des notifications
    path('compte/notifications/',views_u.notifications,name='notifications',),
 
    # Marquer une notification comme lue
    path('compte/notifications/<int:pk>/lue/',views_u.marquer_notification_lue,name='marquer_notification_lue',),
    path('compte/notifications/filters',views_u.notifications_filtrees,name='notifications_filtrees'),
    path('compte/notifications/tout-marquer-lu/',views_u.marquer_toutes_lues,name='marquer_toutes_lues'),
    path('compte/notifications/<int:pk>/supprimer/',views_u.supprimer_notification,name='supprimer_notification'),
    path('compte/notifications/supprimer-lues/',views_u.supprimer_notifications_lues,name='supprimer_notifications_lues'),
    path('compte/notifications/supprimer-toutes/',views_u.supprimer_toutes_notifications,name='supprimer_toutes_notifications'),

    # =====================================================
    # AJAX
    # =====================================================
    path('compte/notifications/ajax/compteur/',views_u.ajax_compteur_notifications,name='ajax_compteur_notifications'),
    path('compte/notifications/ajax/dernieres/',views_u.ajax_dernieres_notifications,name='ajax_dernieres_notifications'),
    path('compte/notifications/toggle-canal/',views_u.toggle_canal_notification,name='toggle_canal_notification'),
 
    # =========================================================================
    # AJAX — APIs temps réel
    # =========================================================================
 
    # Vérifier disponibilité username
    path('compte/ajax/username/',views_u.ajax_verifier_username,name='ajax_verifier_username',),
 
    # Vérifier disponibilité email
    path('compte/ajax/email/',views_u.ajax_verifier_email,name='ajax_verifier_email',),
 
    # Vérifier disponibilité sous-domaine
    path('compte/ajax/sous-domaine/',views_u.ajax_verifier_sous_domaine,name='ajax_verifier_sous_domaine',),
 
    # Solde wallet temps réel
    path('compte/ajax/wallet/solde/',views_u.ajax_solde_wallet,name='ajax_solde_wallet',),


      # =========================================================================
    # SECTION 3 — CATALOGUE PRODUITS
    # =========================================================================
 
    # ── Catalogue public ─────────────────────────────────────────────────────
    path('catalogue/', views_u.catalogue, name='catalogue'),
    path('produits/<slug:slug>/', views_u.produit_detail, name='produit_detail'),
    path('catalogue/categorie/<slug:slug>/',views_u.categorie_detail,         name='categorie_detail',),
 
    # ── Gestion vendeur : CRUD produits ─────────────────────────────────────
    path('vendeur/produits/', views_u.mes_produits, name='mes_produits'),
    path('vendeur/produits/ajouter/', views_u.ajouter_produit, name='ajouter_produit'),
    path('vendeur/produits/<slug:slug>/modifier/', views_u.modifier_produit, name='modifier_produit'),
    path('vendeur/produits/<slug:slug>/supprimer/', views_u.supprimer_produit, name='supprimer_produit'),
 
    # ── Toggles AJAX produit ─────────────────────────────────────────────────
    path('vendeur/produits/<slug:slug>/toggle-actif/', views_u.toggle_actif_produit, name='toggle_actif_produit'),
    path('vendeur/produits/<slug:slug>/toggle-vedette/', views_u.toggle_vedette_produit, name='toggle_vedette_produit'),
    path('vendeur/produits/<slug:slug>/toggle-yopishop/', views_u.toggle_yopishop_produit, name='toggle_yopishop_produit'),
 
    # ── Catégories : public ──────────────────────────────────────────────────
    path('categories/', views_u.categories_liste, name='categories_liste'),
    path('categories/<slug:slug>/', views_u.categorie_detail, name='categorie_detail'),
 
    # ── Catégories : gestion admin ──────────────────────────────────────────
    path('admin-yopishop/categories/', views_u.gerer_categories, name='gerer_categories'),
    path('admin-yopishop/categories/ajouter/', views_u.ajouter_categorie, name='ajouter_categorie'),
    path('admin-yopishop/categories/<slug:slug>/modifier/', views_u.modifier_categorie, name='modifier_categorie'),
    path('admin-yopishop/categories/<slug:slug>/supprimer/', views_u.supprimer_categorie, name='supprimer_categorie'),
 
    # ── Marques : public + gestion admin ─────────────────────────────────────
    path('marques/', views_u.marques_liste, name='marques_liste'),
    path('admin-yopishop/marques/', views_u.gerer_marques, name='gerer_marques'),
    path('admin-yopishop/marques/ajouter/', views_u.ajouter_marque, name='ajouter_marque'),
    path('admin-yopishop/marques/<slug:slug>/modifier/', views_u.modifier_marque, name='modifier_marque'),
 
    # ── Avis produit ──────────────────────────────────────────────────────────
    path('produits/<slug:slug>/avis/ajouter/', views_u.ajouter_avis, name='ajouter_avis'),
    path('avis/<int:pk>/utile/', views_u.voter_utile_avis, name='voter_utile_avis'),
 
    # ── Favoris ───────────────────────────────────────────────────────────────
    path('favoris/', views_u.favoris_liste, name='favoris'),
    path('favoris/toggle/<uuid:pk>/', views_u.toggle_favori, name='toggle_favori'),
 
    # ── AJAX recherche / sous-catégories ────────────────────────────────────
    path('catalogue/ajax/recherche/', views_u.ajax_recherche_produits, name='ajax_recherche_produits'),
    path('catalogue/ajax/sous-categories/', views_u.ajax_sous_categories, name='ajax_sous_categories'),

    # =====================================================
    # PAGES PUBLIQUES
    # =====================================================
    path('promotions/',views_u.promotions_liste,name='promotions_liste'),

    path('promotions/<int:pk>/',views_u.promotion_detail,name='promotion_detail'),

    # =====================================================
    # GESTION VENDEURS / ADMINS
    # =====================================================
    path('mes-promotions/',views_u.mes_promotions,name='mes_promotions'),

    path('mes-promotions/creer/',views_u.creer_promotion,name='creer_promotion'),

    path('mes-promotions/<int:pk>/modifier/',views_u.modifier_promotion,name='modifier_promotion'),

    path('mes-promotions/<int:pk>/supprimer/',views_u.supprimer_promotion,name='supprimer_promotion'),

    path('mes-promotions/<int:pk>/toggle-statut/',views_u.toggle_statut_promotion,name='toggle_statut_promotion'),

    path('mes-promotions/<int:pk>/stats/',views_u.stats_promotion,name='stats_promotion'),

    # =====================================================
    # AJAX
    # =====================================================
    path('promotions/ajax/verifier/',views_u.ajax_verifier_code_promo,name='ajax_verifier_code_promo'),

    path('promotions/ajax/appliquer/',views_u.ajax_appliquer_code_promo,name='ajax_appliquer_code_promo'),

    path('promotions/ajax/retirer/',views_u.ajax_retirer_code_promo,name='ajax_retirer_code_promo'),

    path('promotions/ajax/produit/<int:produit_pk>/',views_u.ajax_promotions_actives_produit,name='ajax_promotions_actives_produit'),

    path('promotions/ajax/calculer/',views_u.ajax_calculer_reduction,name='ajax_calculer_reduction'),
]