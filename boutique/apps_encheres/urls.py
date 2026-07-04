from django.urls import path 
from apps_encheres import views

app_name = 'apps_enchere'


urlpatterns = [

    
    # =========================================================================
    # PUBLIC
    # =========================================================================
 
    path('encheres/', views.encheres_liste, name='encheres_liste'),
    path('encheres/<uuid:pk>/', views.enchere_detail, name='enchere_detail'),
 
    # =========================================================================
    # AJAX — Enchérir / Achat immédiat / Social
    # =========================================================================
 
    path('encheres/<uuid:pk>/offre/', views.ajax_placer_offre, name='ajax_placer_offre'),
    path('encheres/<uuid:pk>/achat-immediat/', views.ajax_achat_immediat, name='ajax_achat_immediat'),
    path('encheres/<uuid:pk>/like/', views.ajax_toggle_like, name='ajax_toggle_like'),
    path('encheres/<uuid:pk>/partager/', views.ajax_partager, name='ajax_partager'),
    path('encheres/<uuid:pk>/ajax-etat/', views.ajax_etat_enchere, name='ajax_etat_enchere'),
 
    # =========================================================================
    # VENDEUR
    # =========================================================================
 
    path('vendeur/encheres/', views.mes_encheres, name='mes_encheres'),
    path('vendeur/encheres/creer/', views.creer_enchere, name='creer_enchere'),
    path('vendeur/encheres/<uuid:pk>/modifier/', views.modifier_enchere, name='modifier_enchere'),
    path('vendeur/encheres/<uuid:pk>/annuler/', views.annuler_enchere, name='annuler_enchere'),
    path('vendeur/encheres/<uuid:pk>/terminer/', views.terminer_enchere_manuelle, name='terminer_enchere_manuelle'),
 
    # =========================================================================
    # ADMIN / SYSTÈME
    # =========================================================================
 
    path('admin/encheres/', views.admin_encheres_liste, name='admin_encheres_liste'),
    path('admin/encheres/cron-terminer-expirees/', views.cron_terminer_encheres_expirees, name='cron_terminer_encheres_expirees'),

    path('encheres/mes-offres/',views.mes_offres,name='mes_offres',),
    path('encheres/smart-bids/',views.mes_smart_bids,name='mes_smart_bids',), 
    path('encheres/admin/offres/',views.admin_offres_liste,name='admin_offres_liste',),
    path('encheres/admin/smart-bids/',views.admin_smart_bids,name='admin_smart_bids',),
    path('encheres/admin/cron/smart-bids/',views.cron_executer_smart_bids,name='cron_executer_smart_bids',),
    path('encheres/<uuid:pk>/smart-bid/',views.configurer_smart_bid,name='configurer_smart_bid',),
    path('encheres/<uuid:pk>/smart-bid/status/',views.ajax_smart_bid_status,name='ajax_smart_bid_status',),
    path('encheres/smart-bids/<int:pk>/desactiver/',views.desactiver_smart_bid,name='desactiver_smart_bid',),


    # =========================================================================
    # PUBLIC
    # =========================================================================

    # Liste des appels d'offres
    path('appels-offre/',views.appels_offre_liste,name='appels_offre_liste'),

    # Détail d'un appel d'offre
    path('appels-offre/<uuid:pk>/',views.appel_offre_detail, name='appel_offre_detail'),

    # Etat AJAX
    path('appels-offre/<uuid:pk>/ajax/',views.ajax_etat_appel_offre,name='ajax_etat_appel_offre'),


    # =========================================================================
    # ACHETEUR
    # =========================================================================

    # Publier un appel d'offre
    path('appels-offre/creer/',views.creer_appel_offre,name='creer_appel_offre'),

    # Mes appels d'offre
    path('appels-offre/mes/',views.mes_appels_offre,name='mes_appels_offre'),

    # Adjuger une offre
    path('appels-offre/<uuid:pk>/adjuger/',views.adjuger_appel_offre,name='adjuger_appel_offre'),

    # Annuler
    path('appels-offre/<uuid:pk>/annuler/',views.annuler_appel_offre,name='annuler_appel_offre'),


    # =========================================================================
    # VENDEUR
    # =========================================================================

    # Soumettre une offre
    path('appels-offre/<uuid:ao_pk>/soumettre/',views.soumettre_offre_vendeur,name='soumettre_offre_vendeur'),

    # Modifier son offre
    path('offres/<int:offre_pk>/modifier/',views.modifier_offre_vendeur,name='modifier_offre_vendeur'),

    # Retirer son offre
    path('offres/<int:offre_pk>/retirer/',views.retirer_offre_vendeur,name='retirer_offre_vendeur'),

    # Mes offres
    path('offres/mes/',views.mes_offres_vendeur,name='mes_offres_vendeur'),

    # =========================================================================
    # ADMIN
    # =========================================================================

    # Administration des appels d'offre
    path('admin/appels-offre/',views.admin_appels_offre_liste,name='admin_appels_offre_liste'),

    
    # =========================================================================
    # PUBLIC
    # =========================================================================
 
    # Liste de toutes les battles actives
    path('encheres/battle/',views.battles_liste,name='battles_liste',),
 
    # Page détail d'une battle (2 camps côte à côte)
    path('encheres/battle/<uuid:pk>/',views.battle_detail,name='battle_detail',),
 
    # Choisir son camp (AJAX POST)
    path('encheres/battle/<uuid:pk>/camp/',views.ajax_choisir_camp,name='ajax_choisir_camp',),
 
    # Polling temps réel (AJAX GET)
    path('encheres/battle/<uuid:pk>/ajax-etat/',views.ajax_etat_battle,name='ajax_etat_battle',),
 
    # =========================================================================
    # ADMIN
    # =========================================================================
 
    # Créer une battle (2 enchères existantes)
    path('admin/encheres/battle/creer/',views.creer_battle,name='creer_battle',),
 
    # Liste admin de toutes les battles
    path('admin/encheres/battle/',views.admin_battles_liste,name='admin_battles_liste',),
 
    # Terminer manuellement une battle (POST / AJAX)
    path('admin/encheres/battle/<uuid:pk>/terminer/',views.admin_terminer_battle,name='admin_terminer_battle',),

 
    
]
