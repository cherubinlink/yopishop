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

 
    
]
