from django.urls import path 
from apps_social import views


app_name = 'apps_social'


urlpatterns = [

    
    # =========================================================================
    # MON PROFIL — utilisateur connecté
    # =========================================================================
 
    # Édition de son propre profil social
    path('social/profil/editer/',views.mon_profil_social,name='mon_profil_social',),
 
    # Mes abonnés (liste avec recherche)
    path('social/mes-abonnes/',views.mes_abonnes,name='mes_abonnes',),
 
    # Mes abonnements (liste avec recherche)
    path('social/mes-abonnements/',views.mes_abonnements,name='mes_abonnements',),
 
    # Suggestions d'abonnement (AJAX GET)
    path('social/ajax/suggestions/',views.ajax_suggestions,name='ajax_suggestions',),
 
    # =========================================================================
    # PROFIL PUBLIC — @username
    # =========================================================================
 
    # Page profil publique
    path('social/@<str:username>/',views.profil_public,name='profil_public',),
 
    # Liste des abonnés d'un profil
    path('social/@<str:username>/abonnes/',views.abonnes_liste,name='abonnes_liste',),

    path('social/profil/modifier/', views.modifier_profil_social, name='modifier_profil_social'),
 
    # =========================================================================
    # AJAX — Abonnement (s'abonner / se désabonner)
    # =========================================================================
 
    # Toggle suivre/ne plus suivre (POST AJAX)
    path('social/@<str:username>/suivre/',views.ajax_toggle_abonnement,name='ajax_toggle_abonnement',),
 
    # =========================================================================
    # ADMIN
    # =========================================================================
 
    # Liste admin de tous les profils sociaux
    path('admin/social/profils/',views.admin_profils_liste,name='admin_profils_liste',),
 
    # Certifier / décertifier un profil (POST AJAX)
    path('admin/social/profils/@<str:username>/verifie/',views.admin_toggle_verifie,name='admin_toggle_verifie',),

    # =============================================================================
    # LIVES PUBLICS
    # =============================================================================
    path('lives/', views.lives_liste, name='lives_liste'),
    path('lives/<uuid:pk>/', views.live_detail, name='live_detail'),
    path('replays/<uuid:pk>/', views.replay_detail, name='replay_detail'),

    # =============================================================================
    # AJAX LIVE
    # =============================================================================
    path('lives/<uuid:pk>/rejoindre/',views.ajax_rejoindre_live,name='ajax_rejoindre_live'),
    path('lives/<uuid:pk>/quitter/',views.ajax_quitter_live,name='ajax_quitter_live'),
    path('lives/<uuid:pk>/commentaire/',views.ajax_poster_commentaire,name='ajax_poster_commentaire'),
    path('lives/<uuid:pk>/reaction/',views.ajax_reaction,name='ajax_reaction'),
    path('lives/<uuid:pk>/acheter/',views.ajax_acheter_live,name='ajax_acheter_live'),
    path('lives/<uuid:pk>/etat/',views.ajax_etat_live,name='ajax_etat_live'),
    path('social/lives/<uuid:pk>/webhook-stream/', views.webhook_stream_statut, name='webhook_stream_statut'),

    # =============================================================================
    # GESTION DES LIVES (VENDEUR)
    # =============================================================================
    path('mes-lives/', views.mes_lives, name='mes_lives'),
    path('lives/creer/', views.creer_live, name='creer_live'),
    path('lives/<uuid:pk>/modifier/', views.modifier_live, name='modifier_live'),
    path('lives/<uuid:pk>/demarrer/', views.demarrer_live, name='demarrer_live'),
    path('lives/<uuid:pk>/terminer/', views.terminer_live, name='terminer_live'),

    path('lives/<uuid:pk>/ajouter-produit/',views.ajouter_produit_live,name='ajouter_produit_live'),
    path('produit-live/<int:produit_live_pk>/retirer/',views.retirer_produit_live,name='retirer_produit_live'),
    path('produit-live/<int:produit_live_pk>/toggle/',views.toggle_produit_actif,name='toggle_produit_actif'),

    # =============================================================================
    # ADMIN LIVES
    # =============================================================================
    path('admin/lives/', views.admin_lives_liste, name='admin_lives_liste'),
    path('admin/social/lives/<uuid:pk>/terminer/', views.admin_terminer_live, name='admin_terminer_live'),

    # =============================================================================
    # STORIES PUBLIQUES
    # =============================================================================

    path('stories/', views.stories_feed, name='stories_feed'),
    path('stories/utilisateur/<str:username>/', views.stories_utilisateur, name='stories_utilisateur'),
    path('stories/<uuid:pk>/', views.story_viewer, name='story_viewer'),

    # =============================================================================
    # GESTION DES STORIES
    # =============================================================================

    path('stories/creer/', views.creer_story, name='creer_story'),
    path('mes-stories/', views.mes_stories, name='mes_stories'),
    path('stories/<uuid:pk>/supprimer/', views.supprimer_story, name='supprimer_story'),

    # =============================================================================
    # AJAX STORIES
    # =============================================================================

    path('stories/<uuid:pk>/marquer-vue/', views.ajax_marquer_vue, name='ajax_marquer_vue'),
    path('stories/<uuid:pk>/clic-action/', views.ajax_clic_action, name='ajax_clic_action'),
    path('stories/ajax/feed/', views.ajax_stories_feed, name='ajax_stories_feed'),

    # =============================================================================
    # ADMIN STORIES
    # =============================================================================

    path('admin/stories/', views.admin_stories_liste, name='admin_stories_liste'),
    path('admin/stories/<uuid:pk>/supprimer/', views.admin_supprimer_story, name='admin_supprimer_story'),

    # =============================================================================
    # MAINTENANCE
    # =============================================================================

    path('admin/stories/nettoyer/', views.cron_nettoyer_stories, name='cron_nettoyer_stories'),

    # =========================================================================
    # SHOPTOK — Vidéos courtes
    # =========================================================================

    # Feed public
    path('videos/', views.videos_feed, name='videos_feed'),
    path('videos/ajax/suivantes/', views.ajax_videos_suivantes, name='ajax_videos_suivantes'),
    path('videos/<uuid:pk>/', views.video_detail, name='video_detail'),

    # Interactions AJAX
    path('videos/<uuid:pk>/liker/', views.ajax_liker_video, name='ajax_liker_video'),
    path('videos/<uuid:pk>/commenter/', views.ajax_commenter_video, name='ajax_commenter_video'),
    path('videos/<uuid:pk>/commentaires/', views.ajax_commentaires_video, name='ajax_commentaires_video'),
    path('videos/commentaires/<int:pk>/liker/', views.ajax_liker_commentaire, name='ajax_liker_commentaire'),
    path('videos/<uuid:pk>/partager/', views.ajax_partager_video, name='ajax_partager_video'),
    path('videos/<uuid:pk>/produits/<int:produit_video_pk>/acheter/', views.ajax_acheter_produit_video, name='ajax_acheter_produit_video'),

    # Vendeur — gestion
    path('mes-videos/', views.mes_videos, name='mes_videos'),
    path('videos/creer/', views.creer_video, name='creer_video'),
    path('videos/<uuid:pk>/modifier/', views.modifier_video, name='modifier_video'),
    path('videos/<uuid:pk>/supprimer/', views.supprimer_video, name='supprimer_video'),
    path('videos/<uuid:pk>/produits/ajouter/', views.ajouter_produit_video, name='ajouter_produit_video'),
    path('videos/produits/<int:produit_video_pk>/retirer/', views.retirer_produit_video, name='retirer_produit_video'),

    # Admin
    path('admin/videos/', views.admin_videos_liste, name='admin_videos_liste'),
    path('admin/videos/<uuid:pk>/vedette/', views.admin_toggle_vedette, name='admin_toggle_vedette'),
    path('admin/videos/<uuid:pk>/publie/', views.admin_toggle_publie, name='admin_toggle_publie'),

    # =========================================================================
    # PROGRAMME INFLUENCEURS
    # =========================================================================

    # Candidature & espace personnel
    path('influenceur/devenir/', views.devenir_influenceur, name='devenir_influenceur'),
    path('influenceur/mon-espace/', views.mon_espace_influenceur, name='mon_espace_influenceur'),

    # Lien de parrainage public (court, hors préfixe /social/ si possible — voir note plus bas)
    path('r/<str:code>/', views.suivre_lien_affiliation, name='suivre_lien_affiliation'),

    # Admin — gestion des programmes
    path('admin/influenceurs/', views.admin_influenceurs_liste, name='admin_influenceurs_liste'),
    path('admin/influenceurs/<int:pk>/statut/', views.admin_changer_statut_influenceur, name='admin_changer_statut_influenceur'),
    path('admin/influenceurs/<int:pk>/conversions/', views.admin_conversions_influenceur, name='admin_conversions_influenceur'),

    # Admin — paiement des commissions
    path('admin/influenceurs/conversions/<int:pk>/payer/', views.admin_marquer_commission_payee, name='admin_marquer_commission_payee'),
    path('admin/influenceurs/<int:pk>/payer-tout/', views.admin_payer_toutes_commissions, name='admin_payer_toutes_commissions'),

    
]
