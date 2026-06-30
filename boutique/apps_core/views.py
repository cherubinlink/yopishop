# ===========================================================================
# apps_core/views_accueil.py
# Vue de la page d'accueil YopiShop
# ===========================================================================
 
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import (
    login, logout, authenticate,update_session_auth_hash,get_user_model,
)
from django.contrib.auth.decorators import login_required


from django.utils import timezone
from django.db.models import Q, Count, Avg, Prefetch, Sum
from decimal import Decimal
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.core.mail import send_mail
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.utils import timezone
from django.core.paginator import Paginator
from decimal import Decimal
from django.db import transaction

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    PasswordResetView,PasswordResetDoneView,
    PasswordResetConfirmView,PasswordResetCompleteView,
)
 
from apps_core.models import (
    Categorie, Produit, Promotion, Avis,
    Utilisateur,ProfilUtilisateur,TransactionWallet,DemandeRechargeWallet,
    Produit, ImageProduit, VarianteProduit, AttributProduit,
    Categorie, Marque, Avis, ImageAvis, ListeSouhaits,Promotion,Notification
)
from apps_marketplace.models import Boutique
from apps_contenu.models import (
    CarouselPrincipal, BannierePromotion, ConfigurationCarousel,
    Article
)
from apps_encheres.models import Enchere
from apps_remaining.models import Publicite
from apps_social.models import (
    LiveVente, Story, VideoCommerce, ProduitLive
)
from apps_core.forms import (
    InscriptionForm,ConnexionForm,ProfilBaseForm,
    ProfilAdresseForm,ProfilPreferencesForm,SousDomaineBoutiqueForm,
    ChangementMotDePasseForm,ReinitMotDePasseForm,NouveauMotDePasseForm,
    CreditWalletForm,DemandeVendeurForm,RechargeWalletForm,
    ProduitForm,ImageProduitFormSet,
    VarianteProduitFormSet,AttributProduitFormSet,FiltreCatalogueForm,
    CategorieForm,MarqueForm,AvisProduitForm,utilisateur_peut_definir_yopishop,
    PromotionForm, CodePromoForm,
)

# =============================================================================
# HELPER INTERNE
# =============================================================================
 
def _get_profil_ou_creer(utilisateur):
    """Récupère ou crée le ProfilUtilisateur."""
    profil, _ = ProfilUtilisateur.objects.get_or_create(utilisateur=utilisateur)
    return profil



def accueil(request):
    """
    Vue principale de la page d'accueil YopiShop.
    Charge : carousel, bannières, catégories, produits officiels,
             enchères actives, publicités, stories, lives, vidéos.
    Compatible MariaDB : pas de LIMIT dans les sous-requêtes IN.
    """
    now = timezone.now()
 
    # ── 1. Catégories pour le menu déroulant ─────────────────────────────────
    categories_menu = Categorie.objects.filter(
        est_active=True,
        parent__isnull=True
    ).prefetch_related(
        Prefetch(
            'sous_categories',
            queryset=Categorie.objects.filter(est_active=True).order_by('ordre', 'nom'),
            to_attr='enfants'
        )
    ).order_by('ordre', 'nom')[:5]
 
    # ── 2. Carousel principal ─────────────────────────────────────────────────
    slides_carousel = CarouselPrincipal.objects.filter(
        est_actif=True
    ).filter(
        Q(date_debut__isnull=True) | Q(date_debut__lte=now)
    ).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=now)
    ).order_by('ordre', '-date_creation')[:6]
 
    # ── 3. Configuration carousel ─────────────────────────────────────────────
    config_carousel = ConfigurationCarousel.get_config()
 
    # ── 4. Bannières promotionnelles ──────────────────────────────────────────
    bannieres = BannierePromotion.objects.filter(
        est_actif=True
    ).filter(
        Q(date_debut__isnull=True) | Q(date_debut__lte=now)
    ).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=now)
    ).select_related('produit').order_by('-priorite', '-date_creation')[:4]
 
    # ── 5. Slider mixte : Publicités + Enchères ───────────────────────────────
    publicites = Publicite.objects.filter(
        statut='active',
        date_debut__lte=now,
        date_fin__gte=now,
    ).order_by('-priorite', '-date_creation')[:8]
 
    encheres_actives = Enchere.objects.filter(
        statut='en_cours',
        date_fin__gt=now,
    ).select_related(
        'produit', 'vendeur', 'produit__categorie'
    ).prefetch_related(
        'produit__images'
    ).order_by('-nb_offres', '-nb_vues')[:8]
 
    encheres_a_venir = Enchere.objects.filter(
        statut='a_venir',
        date_debut__gt=now,
    ).select_related('produit', 'vendeur').order_by('date_debut')[:4]
 
    # Construction du slider intercalé pub + enchères
    pubs_liste     = [{'type': 'pub',     'objet': p} for p in publicites]
    encheres_liste = [{'type': 'enchere', 'objet': e} for e in encheres_actives]
    slider_pub_enchere_intercale = []
    for i in range(max(len(pubs_liste), len(encheres_liste))):
        if i < len(pubs_liste):
            slider_pub_enchere_intercale.append(pubs_liste[i])
        if i < len(encheres_liste):
            slider_pub_enchere_intercale.append(encheres_liste[i])
 
    # ── 6. Produits YopiShop Officiel ─────────────────────────────────────────
    produits_yopishop = Produit.objects.filter(
        est_actif=True,
        est_produit_yopishop=True,
        quantite_stock__gt=0,
    ).select_related(
        'categorie', 'vendeur', 'ville'
    ).prefetch_related('images').order_by('-nb_ventes', '-est_vedette')[:12]
 
    # ── 7. Produits vedettes ──────────────────────────────────────────────────
    produits_vedettes = Produit.objects.filter(
        est_actif=True,
        est_vedette=True,
    ).select_related('categorie', 'vendeur').prefetch_related('images')[:8]
 
    # ── 8. Produits récents ───────────────────────────────────────────────────
    produits_recents = Produit.objects.filter(
        est_actif=True,
    ).select_related('categorie', 'vendeur').prefetch_related('images') \
     .order_by('-date_creation')[:16]
 
    # ── 9. Produits par catégorie ─────────────────────────────────────────────
    top_categories = Categorie.objects.filter(
        est_active=True,
        parent__isnull=True
    ).annotate(nb_produits=Count('produits')).order_by('-nb_produits')[:4]
 
    produits_par_categorie = {}
    for cat in top_categories:
        produits_par_categorie[cat] = Produit.objects.filter(
            est_actif=True,
            categorie=cat,
        ).select_related('vendeur').prefetch_related('images').order_by('-nb_ventes')[:6]
 
    # ── 10. Stories actives ───────────────────────────────────────────────────
    stories = Story.objects.filter(
        date_expiration__gt=now,
    ).select_related(
        'auteur', 'produit_lie'
    ).prefetch_related('vues').order_by('-date_creation')[:12]
 
    # IDs stories vues — ✅ CORRIGÉ : évaluer stories en liste avant le filtre IN
    stories_vues_ids = set()
    if request.user.is_authenticated:
        try:
            from apps_social.models import VueStory
            # ✅ list() évite LIMIT dans sous-requête MariaDB
            stories_ids = list(stories.values_list('id', flat=True))
            stories_vues_ids = set(
                VueStory.objects.filter(
                    utilisateur=request.user,
                    story_id__in=stories_ids       # ← liste Python, pas queryset
                ).values_list('story_id', flat=True)
            )
        except (ModuleNotFoundError, Exception):
            stories_vues_ids = set()
 
    # ── 11. Lives en cours ────────────────────────────────────────────────────
    lives_en_cours = LiveVente.objects.filter(
        statut='en_cours'
    ).select_related('vendeur').prefetch_related(
        Prefetch(
            'produits_live',
            queryset=ProduitLive.objects.filter(
                est_disponible=True
            ).select_related('produit').prefetch_related('produit__images')[:3],
            to_attr='produits_preview'
        )
    ).order_by('-nb_participants_actuels')[:4]
 
    lives_a_venir = LiveVente.objects.filter(
        statut='planifie',
        date_debut__gt=now,
    ).select_related('vendeur').order_by('date_debut')[:4]
 
    # ── 12. Vidéos courtes (ShopTok) ──────────────────────────────────────────
    videos_commerce = VideoCommerce.objects.filter(
        est_publie=True
    ).select_related('auteur').prefetch_related(
        'produits_video__produit__images'
    ).order_by('-nb_vues', '-date_creation')[:8]
 
    # ── 13. Promotions actives (bannière flash) ───────────────────────────────
    promotions_flash = Promotion.objects.filter(
        statut='active',
        date_debut__lte=now,
        date_fin__gte=now,
    ).order_by('-priorite')[:3]
 
    # ── 14. Blog / Articles récents ───────────────────────────────────────────
    articles_recents = Article.objects.filter(
        statut='publie',
        date_publication__lte=now,
    ).select_related('auteur', 'categorie').order_by('-date_publication')[:3]
 
    # ── 15. Boutiques vedettes ────────────────────────────────────────────────
    boutiques_vedettes = Boutique.objects.filter(
        statut='active',
        est_vedette=True,
    ).select_related('vendeur').order_by('-note_moyenne')[:6]
 
    # ── 16. Compteurs stats ───────────────────────────────────────────────────
    stats = {
        'nb_produits': Produit.objects.filter(est_actif=True).count(),
        'nb_vendeurs': Boutique.objects.filter(statut='active').count(),
        'nb_encheres': Enchere.objects.filter(statut='en_cours').count(),
        'nb_lives':    LiveVente.objects.filter(statut='en_cours').count(),
    }
 
    # ── 17. Produits en promotion ─────────────────────────────────────────────
    # ✅ CORRIGÉ : évaluer les IDs en listes Python avant le filtre IN
    produits_promo = []
    if promotions_flash.exists():
        # Évaluation en listes plates — évite LIMIT dans sous-requête
        promo_ids = list(
            promotions_flash.values_list('produits', flat=True)
        )
        cat_ids = list(
            promotions_flash.values_list('categories', flat=True)
        )
        # Nettoyer les None éventuels
        promo_ids = [i for i in promo_ids if i is not None]
        cat_ids   = [i for i in cat_ids   if i is not None]
 
        filtre = Q()
        if promo_ids:
            filtre |= Q(id__in=promo_ids)
        if cat_ids:
            filtre |= Q(categorie_id__in=cat_ids)
 
        if filtre:
            produits_promo = Produit.objects.filter(
                est_actif=True
            ).filter(filtre).select_related(
                'categorie', 'vendeur'
            ).prefetch_related('images')[:12]
 
    context = {
        # Navigation
        'categories_menu':        categories_menu,
 
        # Carousel
        'slides_carousel':        slides_carousel,
        'config_carousel':        config_carousel,
        'bannieres':              bannieres,
 
        # Slider pub + enchères
        'slider_pub_enchere':     slider_pub_enchere_intercale,
        'publicites':             publicites,
        'encheres_actives':       encheres_actives,
        'encheres_a_venir':       encheres_a_venir,
 
        # Produits
        'produits_yopishop':      produits_yopishop,
        'produits_vedettes':      produits_vedettes,
        'produits_recents':       produits_recents,
        'produits_par_categorie': produits_par_categorie,
        'produits_promo':         produits_promo,
 
        # Social
        'stories':                stories,
        'stories_vues_ids':       stories_vues_ids,
        'lives_en_cours':         lives_en_cours,
        'lives_a_venir':          lives_a_venir,
        'videos_commerce':        videos_commerce,
 
        # Promotions
        'promotions_flash':       promotions_flash,
 
        # Blog
        'articles_recents':       articles_recents,
 
        # Boutiques
        'boutiques_vedettes':     boutiques_vedettes,
 
        # Stats
        'stats':                  stats,
 
        # Meta
        'page_titre': 'YopiShop — Le meilleur du commerce en ligne',
        'now':        now,
    }
 
    return render(request, 'apps_core/accueil.html', context)




# =============================================================================
# INSCRIPTION 
# =============================================================================
 
def inscription(request):
    """
    Inscription directe — le compte est actif immédiatement.
 
    GET  → affiche le formulaire
    POST → crée le compte + connexion auto → tableau de bord
           (email de bienvenue envoyé en arrière-plan, sans bloquer)
    """
    if request.user.is_authenticated:
        return redirect('apps_core:tableau_de_bord')
 
    if request.method == 'POST':
        form = InscriptionForm(request.POST)
 
        if form.is_valid():
            # ── 1. Créer le compte ───────────────────────────────────────────
            user = form.save()
 
            # ── 2. Créer le profil automatiquement ──────────────────────────
            ProfilUtilisateur.objects.get_or_create(utilisateur=user)
 
            # ── 3. Connexion immédiate ───────────────────────────────────────
            login(
                request,
                user,
                backend='django.contrib.auth.backends.ModelBackend'
            )
 
            # ── 4. Email de bienvenue (optionnel, non bloquant) ──────────────
            _envoyer_email_bienvenue_async(request, user)
 
            # ── 5. Message de succès ─────────────────────────────────────────
            messages.success(
                request,
                f"🎉 Bienvenue sur YopiShop, {user.first_name or user.username} ! "
                f"Votre compte est actif."
            )
 
            # ── 6. Redirection ───────────────────────────────────────────────
            next_url = request.POST.get('next', '').strip()
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect('apps_core:tableau_de_bord')
 
        else:
            # Afficher les erreurs du formulaire
            messages.error(
                request,
                "Veuillez corriger les erreurs ci-dessous."
            )
    else:
        form = InscriptionForm()
    
    context =  {
        'form':       form,
        'next':       request.GET.get('next', ''),
        'page_titre': 'Créer un compte — YopiShop',
    }
 
    return render(request, 'apps_core/auth/inscription.html',context)
 
 
# =============================================================================
# EMAIL DE BIENVENUE (optionnel, en arrière-plan)
# =============================================================================
 
def _envoyer_email_bienvenue_async(request, user):
    """
    Envoie l'email de bienvenue dans un thread séparé.
    → Ne bloque JAMAIS l'inscription si l'email échoue.
    → Contient un lien de vérification optionnel.
    """
    try:
        uid   = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        lien_verification = request.build_absolute_uri(
            f"/compte/verifier-email/{uid}/{token}/"
        )
 
        def envoyer():
            try:
                send_mail(
                    subject="🛍️ Bienvenue sur YopiShop !",
                    message=(
                        f"Bonjour {user.first_name or user.username},\n\n"
                        f"Votre compte YopiShop est créé et actif !\n\n"
                        f"Vous pouvez commencer à acheter dès maintenant.\n\n"
                        f"--- Optionnel ---\n"
                        f"Pour activer le badge '✅ Email vérifié' et bénéficier de "
                        f"fonctionnalités supplémentaires, vérifiez votre email ici :\n"
                        f"{lien_verification}\n\n"
                        f"Ce lien expire dans 48h — vous pouvez ignorer ce message si "
                        f"vous ne souhaitez pas vérifier votre email maintenant.\n\n"
                        f"L'équipe YopiShop"
                    ),
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@yopishop.com'),
                    recipient_list=[user.email],
                    fail_silently=True,
                )
            except Exception:
                pass   # Silencieux — l'email est optionnel
 
        # Thread daemon : s'arrête automatiquement si le serveur s'arrête
        t = threading.Thread(target=envoyer, daemon=True)
        t.start()
 
    except Exception:
        pass   # Silencieux dans tous les cas
 
 
# =============================================================================
# VÉRIFICATION EMAIL (optionnelle, accessible depuis le profil)
# =============================================================================
 
def verifier_email(request, uidb64, token):
    """
    Valide le lien de vérification email.
    Active le badge est_verifie sur l'utilisateur.
 
    Cette étape est OPTIONNELLE — l'utilisateur peut utiliser son
    compte sans avoir vérifié son email.
    """
    from django.utils.http import urlsafe_base64_decode
    from django.utils.encoding import force_str
 
    try:
        uid  = force_str(urlsafe_base64_decode(uidb64))
        user = Utilisateur.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, Utilisateur.DoesNotExist):
        user = None
 
    if user and default_token_generator.check_token(user, token):
        # Activer le badge vérifié
        user.est_verifie = True
        user.save(update_fields=['est_verifie'])
 
        messages.success(
            request,
            "✅ Email vérifié ! Vous bénéficiez maintenant du badge de confiance."
        )
        if request.user.is_authenticated:
            return redirect('apps_core:tableau_de_bord')
        return redirect('apps_core:connexion')
 
    # Lien invalide ou expiré — pas grave, la vérification est optionnelle
    messages.warning(
        request,
        "Ce lien de vérification est invalide ou a expiré. "
        "Vous pouvez en demander un nouveau depuis votre profil."
    )
    if request.user.is_authenticated:
        return redirect('apps_core:profil')
    return redirect('apps_core:connexion')
 
 
def renvoyer_email_verification(request):
    """
    Renvoie un email de vérification si l'utilisateur le souhaite.
    Accessible depuis le profil.
    """
    from django.contrib.auth.decorators import login_required
 
    if not request.user.is_authenticated:
        return redirect('apps_core:connexion')
 
    if request.user.est_verifie:
        messages.info(request, "Votre email est déjà vérifié.")
    else:
        _envoyer_email_bienvenue_async(request, request.user)
        messages.success(
            request,
            "Un email de vérification a été envoyé à "
            f"{request.user.email}."
        )
    return redirect('apps_core:profil')
 
# =============================================================================
# CONNEXION / DÉCONNEXION
# =============================================================================
 
def connexion(request):
    """
    GET  → formulaire de connexion
    POST → authentifie et redirige vers next ou tableau de bord
    """
    if request.user.is_authenticated:
        return redirect('apps_core:tableau_de_bord')
 
    next_url = request.GET.get('next', '')
 
    if request.method == 'POST':
        form = ConnexionForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
 
            # Gestion "Se souvenir de moi"
            if not form.cleaned_data.get('se_souvenir'):
                request.session.set_expiry(0)   # Expire à la fermeture du navigateur
            else:
                request.session.set_expiry(60 * 60 * 24 * 30)   # 30 jours
 
            # Enregistrer l'IP de connexion
            ip = _get_client_ip(request)
            user.derniere_connexion_ip = ip
            user.save(update_fields=['derniere_connexion_ip'])
 
            login(request, user)
            messages.success(request, f"Bienvenue, {user.first_name or user.username} !")
 
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect('apps_core:tableau_de_bord')
        else:
            messages.error(request, "Email ou mot de passe incorrect.")
    else:
        form = ConnexionForm(request)
    
    context = {
        'form':       form,
        'next':       next_url,
        'page_titre': 'Connexion — YopiShop',
    }
 
    return render(request, 'apps_core/auth/connexion.html', context)
 
 
def deconnexion(request):
    """Déconnecte l'utilisateur et redirige vers l'accueil."""
    if request.user.is_authenticated:
        messages.info(request, "Vous avez été déconnecté.")
    logout(request)
    return redirect('apps_core:accueil')
 
 
def _get_client_ip(request):
    """Extrait l'IP réelle du client (supporte les proxies)."""
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')
 
 
# =============================================================================
# TABLEAU DE BORD
# =============================================================================
 
@login_required
def tableau_de_bord(request):
    """
    Page principale du compte utilisateur.
    Charge : profil, stats commandes, wallet, notifications récentes.
    """
    user   = request.user
    profil = _get_profil_ou_creer(user)
 
    # Imports locaux pour éviter les imports circulaires
    try:
        from apps_marketplace.models import Commande
        commandes_recentes = Commande.objects.filter(
            utilisateur=user
        ).select_related('ville_livraison').order_by('-date_creation')[:5]
        nb_commandes_total   = Commande.objects.filter(utilisateur=user).count()
        nb_commandes_encours = Commande.objects.filter(
            utilisateur=user,
            statut__in=['en_attente', 'confirmee', 'en_traitement', 'expediee']
        ).count()
    except Exception:
        commandes_recentes   = []
        nb_commandes_total   = 0
        nb_commandes_encours = 0
 
    # Notifications non lues
    from apps_core.models import Notification
    notifications = Notification.objects.filter(
        utilisateur=user, est_lu=False
    ).order_by('-date_creation')[:5]
    nb_notifs_non_lues = Notification.objects.filter(
        utilisateur=user, est_lu=False
    ).count()
 
    # Transactions wallet récentes
    transactions_recentes = TransactionWallet.objects.filter(
        utilisateur=user
    ).order_by('-date_creation')[:4]
 
    context = {
        'user':                  user,
        'profil':                profil,
        'commandes_recentes':    commandes_recentes,
        'nb_commandes_total':    nb_commandes_total,
        'nb_commandes_encours':  nb_commandes_encours,
        'notifications':         notifications,
        'nb_notifs_non_lues':    nb_notifs_non_lues,
        'transactions_recentes': transactions_recentes,
        'page_titre':            'Mon tableau de bord — YopiShop',
    }
    return render(request, 'apps_core/tableau_de_bord.html', context)
 
 
# =============================================================================
# PROFIL
# =============================================================================
 
@login_required
def profil(request):
    """Affiche le profil complet de l'utilisateur connecté."""
    user   = request.user
    profil = _get_profil_ou_creer(user)
 
    context = {
        'user':        user,
        'profil':      profil,
        'page_titre':  f"Mon profil — {user.username}",
    }
    return render(request, 'apps_core/profil.html', context)
 
 
@login_required
def modifier_profil(request):
    """
    Modification des informations de base du profil.
    Gère avatar, nom, email, téléphone, date de naissance, bio.
    """
    user = request.user
 
    if request.method == 'POST':
        form = ProfilBaseForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "Votre profil a été mis à jour.")
            return redirect('apps_core:profil')
        else:
            messages.error(request, "Veuillez corriger les erreurs ci-dessous.")
    else:
        form = ProfilBaseForm(instance=user)
    
    context = {
        'form':       form,
        'page_titre': 'Modifier mon profil',
    }
 
    return render(request, 'apps_core/modifier_profil.html', context)
 
 
@login_required
def modifier_adresse(request):
    """Modification de l'adresse et de la localisation."""
    user = request.user
 
    if request.method == 'POST':
        form = ProfilAdresseForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "Adresse mise à jour.")
            return redirect('apps_core:profil')
    else:
        form = ProfilAdresseForm(instance=user)
    
    context = {
        'form':       form,
        'page_titre': 'Modifier mon adresse',
    }
 
    return render(request, 'apps_core/modifier_adresse.html', context)
 
 
@login_required
def modifier_preferences(request):
    """Modification des préférences (langue, devise, notifications)."""
    profil = _get_profil_ou_creer(request.user)
 
    if request.method == 'POST':
        form = ProfilPreferencesForm(request.POST, instance=profil)
        if form.is_valid():
            form.save()
            messages.success(request, "Préférences enregistrées.")
            return redirect('apps_core:profil')
    else:
        form = ProfilPreferencesForm(instance=profil)
    
    context = {
        'form':       form,
        'page_titre': 'Mes préférences',
    }
 
    return render(request, 'apps_core/modifier_preferences.html', context)
 
 
@login_required
def modifier_sous_domaine(request):
    """Modification du sous-domaine boutique."""
    user = request.user
    if not user.peut_vendre:
        messages.warning(request, "Vous devez être vendeur pour configurer un sous-domaine.")
        return redirect('apps_core:profil')
 
    if request.method == 'POST':
        form = SousDomaineBoutiqueForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            sd = form.cleaned_data['sous_domaine']
            messages.success(request, f"Sous-domaine configuré : {sd}.yopishop.com")
            return redirect('apps_core:profil')
    else:
        form = SousDomaineBoutiqueForm(instance=user)
    
    context = {
        'form':       form,
        'page_titre': 'Mon sous-domaine boutique',
    }
 
    return render(request, 'apps_core/modifier_sous_domaine.html', context)
 
 
@login_required
def supprimer_avatar(request):
    """Supprime l'avatar de l'utilisateur."""
    if request.method == 'POST':
        user = request.user
        if user.avatar:
            user.avatar.delete(save=False)
            user.avatar = None
            user.save(update_fields=['avatar'])
            messages.success(request, "Avatar supprimé.")
        return redirect('apps_core:modifier_profil')
    return redirect('apps_core:profil')
 
 
# =============================================================================
# MOT DE PASSE
# =============================================================================
 
@login_required
def changer_mot_de_passe(request):
    """Changement de mot de passe pour un utilisateur connecté."""
    if request.method == 'POST':
        form = ChangementMotDePasseForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)   # Garde la session active
            messages.success(request, "Mot de passe modifié avec succès.")
            return redirect('apps_core:profil')
        else:
            messages.error(request, "Veuillez corriger les erreurs.")
    else:
        form = ChangementMotDePasseForm(request.user)
    context = {
        'form':       form,
        'page_titre': 'Changer mon mot de passe',
    }
 
    return render(request, 'apps_core/auth/changer_mot_de_passe.html', context)
 
 
# Vues basées sur les classes de Django pour la réinitialisation mot de passe
class ReinitMotDePasseView(PasswordResetView):
    template_name   = 'apps_core/auth/reinit_mdp.html'
    form_class      = ReinitMotDePasseForm
    email_template_name = 'apps_core/emails/reinit_mdp_email.txt'
    subject_template_name = 'apps_core/emails/reinit_mdp_sujet.txt'
    success_url     = '/compte/reinitialisation-envoye/'
    extra_context   = {'page_titre': 'Réinitialiser mon mot de passe'}
 
 
class ReinitMotDePasseEnvoyeView(PasswordResetDoneView):
    template_name = 'apps_core/auth/reinit_mdp_envoye.html'
    extra_context = {'page_titre': 'Email envoyé'}
 
 
class ConfirmerNouveauMdpView(PasswordResetConfirmView):
    template_name  = 'apps_core/auth/nouveau_mdp.html'
    form_class     = NouveauMotDePasseForm
    success_url    = '/compte/reinitialisation-terminee/'
    extra_context  = {'page_titre': 'Nouveau mot de passe'}
 
 
class ReinitTermineeView(PasswordResetCompleteView):
    template_name = 'apps_core/auth/reinit_terminee.html'
    extra_context = {'page_titre': 'Mot de passe réinitialisé'}
 
 
# =============================================================================
# WALLET YOPIPAY
# =============================================================================
 
@login_required
def wallet(request):
    """
    Vue principale du wallet YopiPay.
    Affiche le solde, l'historique paginé des transactions.
    """
    user = request.user
 
    # Filtrage par type
    type_filtre = request.GET.get('type', '')
    qs = TransactionWallet.objects.filter(utilisateur=user)
    if type_filtre:
        qs = qs.filter(type_transaction=type_filtre)
    qs = qs.order_by('-date_creation')
 
    paginator    = Paginator(qs, 20)
    page_num     = request.GET.get('page', 1)
    transactions = paginator.get_page(page_num)
 
    # Statistiques wallet
    stats_wallet = TransactionWallet.objects.filter(utilisateur=user).aggregate(
        total_credite=Sum(
            'montant',
            filter=Q(type_transaction__in=['credit', 'bonus', 'remboursement'])
        ),
        total_debite=Sum(
            'montant',
            filter=Q(type_transaction='debit')
        ),
        nb_transactions=Count('id'),
    )
 
    # Demandes de recharge récentes
    demandes_recentes = DemandeRechargeWallet.objects.filter(
        utilisateur=user
    ).order_by('-date_creation')[:5]
 
    # Formulaire vide pour le modal
    form_recharge = RechargeWalletForm()
 
    context = {
        'user':              user,
        'transactions':      transactions,
        'type_filtre':       type_filtre,
        'stats_wallet':      stats_wallet,
        'types_choices':     TransactionWallet.TYPE_CHOICES,
        'demandes_recentes': demandes_recentes,
        'form_recharge':     form_recharge,
        'page_titre':        'Mon Wallet YopiPay',
    }
    return render(request, 'apps_core/wallet.html', context)


# =============================================================================
# VUE : recharger_wallet (à ajouter dans views.py)
# =============================================================================
 
@login_required
@require_POST
def recharger_wallet(request):
    """
    Traite la demande de recharge soumise depuis le modal du wallet.
    Crée une DemandeRechargeWallet en attente de validation admin.
    """
    form = RechargeWalletForm(request.POST, request.FILES)
 
    if form.is_valid():
        demande             = form.save(commit=False)
        demande.utilisateur = request.user
        demande.statut      = 'en_attente'
        demande.save()
 
        messages.success(
            request,
            f"✅ Demande de recharge de {demande.montant:.0f} XAF envoyée ! "
            f"Elle sera validée par un administrateur sous 24h."
        )
    else:
        # Récupérer les erreurs pour les afficher
        erreurs = []
        for field, errs in form.errors.items():
            for err in errs:
                erreurs.append(err)
        messages.error(
            request,
            "❌ Erreur : " + " — ".join(erreurs) if erreurs else "Formulaire invalide."
        )
 
    return redirect('apps_core:wallet')
 
 
@login_required
def historique_transactions(request):
    """Historique complet des transactions avec export possible."""
    qs = TransactionWallet.objects.filter(
        utilisateur=request.user
    ).order_by('-date_creation')
 
    paginator    = Paginator(qs, 30)
    page_num     = request.GET.get('page', 1)
    transactions = paginator.get_page(page_num)

    context = {
        'transactions': transactions,
        'page_titre':   'Historique des transactions',
    }
 
    return render(request, 'apps_core/historique.html', context)
 
 
# =============================================================================
# PROFIL PUBLIC VENDEUR
# =============================================================================
 
def profil_vendeur_public(request, username):
    """
    Profil public d'un vendeur (accessible par tous).
    Affiche : boutique ou infos vendeur individuel, produits, avis.
    """
    vendeur = get_object_or_404(
        Utilisateur,
        username=username,
        is_active=True,
    )
 
    if not vendeur.peut_vendre:
        from django.http import Http404
        raise Http404
 
    # Produits actifs du vendeur
    produits = vendeur.produits.filter(
        est_actif=True
    ).select_related('categorie').prefetch_related('images').order_by('-date_creation')[:12]
 
    # Avis reçus (si apps_marketplace disponible)
    avis = []
    try:
        from apps_marketplace.models import AvisVendeur
        avis = AvisVendeur.objects.filter(
            vendeur=vendeur, est_approuve=True
        ).select_related('utilisateur').order_by('-date_creation')[:10]
    except Exception:
        pass
 
    context = {
        'vendeur':     vendeur,
        'profil':      _get_profil_ou_creer(vendeur),
        'produits':    produits,
        'avis':        avis,
        'page_titre':  f"Boutique de {vendeur.username} — YopiShop",
    }
    return render(request, 'apps_core/profil_vendeur_public.html', context)
 
 
# =============================================================================
# DEVENIR VENDEUR
# =============================================================================
 
@login_required
def devenir_vendeur(request):
    """
    Formulaire de candidature pour devenir vendeur pro.
    Si l'utilisateur est déjà vendeur, redirige vers son dashboard.
    """
    user = request.user
 
    # Déjà vendeur pro
    if user.type_vendeur == 'pro':
        messages.info(request, "Vous êtes déjà un vendeur pro.")
        try:
            return redirect('apps_marketplace:dashboard_vendeur')
        except Exception:
            return redirect('apps_core:tableau_de_bord')
 
    # Candidature déjà soumise
    try:
        from apps_marketplace.models import DemandeVendeur
        demande_existante = DemandeVendeur.objects.filter(utilisateur=user).first()
    except Exception:
        demande_existante = None
 
    if request.method == 'POST':
        form = DemandeVendeurForm(request.POST)
        if form.is_valid():
            try:
                from apps_marketplace.models import DemandeVendeur
                DemandeVendeur.objects.create(
                    utilisateur=user,
                    motivation=form.cleaned_data['motivation'],
                    experience_commerce=form.cleaned_data.get('experience_commerce', ''),
                    types_produits=form.cleaned_data['types_produits'],
                    volume_estime=form.cleaned_data['volume_estime'],
                    a_entreprise=form.cleaned_data.get('a_entreprise', False),
                    nom_entreprise=form.cleaned_data.get('nom_entreprise', ''),
                )
                messages.success(
                    request,
                    "Votre candidature a été soumise ! Nous vous contacterons sous 48h."
                )
            except Exception as e:
                messages.error(request, f"Erreur lors de la soumission : {e}")
            return redirect('apps_core:tableau_de_bord')
    else:
        form = DemandeVendeurForm()
    
    context = {
        'form':             form,
        'demande_existante': demande_existante,
        'page_titre':       'Devenir vendeur sur YopiShop',
    }
 
    return render(request, 'apps_core/devenir_vendeur.html', context)
 
 
# =============================================================================
# NOTIFICATIONS
# =============================================================================
 
@login_required
def notifications(request):
    """Liste de toutes les notifications de l'utilisateur."""
    from apps_core.models import Notification
 
    qs = Notification.objects.filter(
        utilisateur=request.user
    ).order_by('-date_creation')
 
    paginator     = Paginator(qs, 20)
    page_num      = request.GET.get('page', 1)
    notifications = paginator.get_page(page_num)
 
    # Marquer toutes comme lues si demandé
    if request.GET.get('tout_lire'):
        Notification.objects.filter(
            utilisateur=request.user, est_lu=False
        ).update(est_lu=True)
        messages.success(request, "Toutes les notifications ont été marquées comme lues.")
        return redirect('apps_core:notifications')
    
    context = {
        'notifications': notifications,
        'page_titre':    'Mes notifications',
    }
 
    return render(request, 'apps_core/liste_notifications.html', context)
 
 
@login_required
@require_POST
def marquer_notification_lue(request, pk):
    """Marque une notification spécifique comme lue (AJAX ou redirect)."""
    from apps_core.models import Notification
    notif = get_object_or_404(Notification, pk=pk, utilisateur=request.user)
    notif.est_lu = True
    notif.save(update_fields=['est_lu'])
 
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})
    return redirect(notif.lien or 'apps_core:notifications')



# =============================================================================
# HELPER INTERNE — création de notification (réutilisable par d'autres apps)
# =============================================================================
 
def creer_notification(utilisateur, type_notification, titre, message,
                        lien='', canal='in_app', donnees_extra=None):
    """
    Helper pour créer une notification depuis n'importe quelle vue/signal.
 
    Usage :
        from apps_core.views_notifications import creer_notification
        creer_notification(
            utilisateur=commande.utilisateur,
            type_notification='commande',
            titre="Commande confirmée",
            message=f"Votre commande #{commande.numero} a été confirmée.",
            lien=f"/commandes/{commande.id}/",
        )
    """
    return Notification.objects.create(
        utilisateur=utilisateur,
        type_notification=type_notification,
        titre=titre,
        message=message,
        lien=lien,
        canal=canal,
        donnees_extra=donnees_extra or {},
    )
 
 
def creer_notification_masse(utilisateurs_qs, type_notification, titre, message,
                              lien='', canal='in_app'):
    """Crée la même notification pour plusieurs utilisateurs (bulk_create)."""
    notifs = [
        Notification(
            utilisateur=u,
            type_notification=type_notification,
            titre=titre,
            message=message,
            lien=lien,
            canal=canal,
        )
        for u in utilisateurs_qs
    ]
    return Notification.objects.bulk_create(notifs)
 
 
# =============================================================================
# LISTE FILTRÉE (complète la vue `notifications` déjà existante)
# =============================================================================
 
@login_required
def notifications_filtrees(request):
    """
    Liste des notifications avec filtres avancés.
    GET params : type, canal, lu (true/false), q
    """
    from apps_core.models import Notification

    qs = Notification.objects.filter(utilisateur=request.user)
 
    type_filtre = request.GET.get('type', '')
    if type_filtre:
        qs = qs.filter(type_notification=type_filtre)
 
    canal_filtre = request.GET.get('canal', '')
    if canal_filtre:
        qs = qs.filter(canal=canal_filtre)
 
    lu_filtre = request.GET.get('lu', '')
    if lu_filtre == 'true':
        qs = qs.filter(est_lu=True)
    elif lu_filtre == 'false':
        qs = qs.filter(est_lu=False)
 
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(Q(titre__icontains=q) | Q(message__icontains=q))
 
    qs = qs.order_by('-date_creation')
 
    paginator = Paginator(qs, 20)
    notifications = paginator.get_page(request.GET.get('page', 1))
 
    # Compteurs pour les badges de filtre
    base_qs = Notification.objects.filter(utilisateur=request.user)
    compteurs_type = {
        code: base_qs.filter(type_notification=code).count()
        for code, _ in Notification.TYPE_CHOICES
    }
 
    context = {
        'notifications':   notifications,
        'type_filtre':     type_filtre,
        'canal_filtre':    canal_filtre,
        'lu_filtre':       lu_filtre,
        'q':               q,
        'types':           Notification.TYPE_CHOICES,
        'canaux':          Notification.CANAL_CHOICES,
        'compteurs_type':  compteurs_type,
        'nb_non_lues':     base_qs.filter(est_lu=False).count(),
        'page_titre':      'Mes notifications',
    }
    return render(request, 'apps_core/notifications_filtrees.html', context)
 
 
# =============================================================================
# MARQUER TOUTES COMME LUES (action groupée explicite)
# =============================================================================
 
@login_required
@require_POST
def marquer_toutes_lues(request):
    """
    Marque toutes les notifications (ou un type spécifique) comme lues.
    POST /compte/notifications/tout-marquer-lu/
    Body optionnel : type=commande (pour ne marquer qu'un type)
    """
    qs = Notification.objects.filter(utilisateur=request.user, est_lu=False)
 
    type_filtre = request.POST.get('type', '')
    if type_filtre:
        qs = qs.filter(type_notification=type_filtre)
 
    nb = qs.update(est_lu=True)
 
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'nb_marquees': nb})
 
    messages.success(request, f"{nb} notification(s) marquée(s) comme lue(s).")
    return redirect('apps_core:notifications')
 
 
# =============================================================================
# SUPPRESSION
# =============================================================================
 
@login_required
@require_POST
def supprimer_notification(request, pk):
    """Supprime une notification spécifique."""
    notif = get_object_or_404(Notification, pk=pk, utilisateur=request.user)
    notif.delete()
 
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})
 
    messages.success(request, "Notification supprimée.")
    return redirect('apps_core:notifications')
 
 
@login_required
@require_POST
def supprimer_notifications_lues(request):
    """Supprime toutes les notifications déjà lues (nettoyage)."""
    nb, _ = Notification.objects.filter(
        utilisateur=request.user, est_lu=True
    ).delete()
 
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'nb_supprimees': nb})
 
    messages.success(request, f"{nb} notification(s) lue(s) supprimée(s).")
    return redirect('apps_core:notifications')
 
 
@login_required
@require_POST
def supprimer_toutes_notifications(request):
    """Supprime absolument toutes les notifications de l'utilisateur."""
    nb, _ = Notification.objects.filter(utilisateur=request.user).delete()
 
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'nb_supprimees': nb})
 
    messages.success(request, f"Toutes vos notifications ont été supprimées ({nb}).")
    return redirect('apps_core:notifications')
 
 
# =============================================================================
# AJAX — Polling temps réel (badge navbar)
# =============================================================================
 
@login_required
@require_GET
def ajax_compteur_notifications(request):
    """
    Retourne le nombre de notifications non lues.
    Utilisé en polling JS toutes les 30-60s pour mettre à jour le badge.
    GET /compte/notifications/ajax/compteur/
    """
    nb = Notification.objects.filter(utilisateur=request.user, est_lu=False).count()
    return JsonResponse({'nb_non_lues': nb})
 
 
@login_required
@require_GET
def ajax_dernieres_notifications(request):
    """
    Retourne les 5 dernières notifications pour le dropdown navbar.
    GET /compte/notifications/ajax/dernieres/
    """
    notifs = Notification.objects.filter(
        utilisateur=request.user
    ).order_by('-date_creation')[:5]
 
    data = [{
        'id':        n.id,
        'type':      n.type_notification,
        'type_display': n.get_type_notification_display(),
        'titre':     n.titre,
        'message':   n.message[:80],
        'lien':      n.lien,
        'est_lu':    n.est_lu,
        'date':      n.date_creation.strftime('%d/%m/%Y %H:%M'),
        'il_y_a':    _temps_relatif(n.date_creation),
    } for n in notifs]
 
    nb_non_lues = Notification.objects.filter(utilisateur=request.user, est_lu=False).count()
 
    return JsonResponse({
        'notifications': data,
        'nb_non_lues':   nb_non_lues,
    })
 
 
def _temps_relatif(date):
    """Formatte une date en 'il y a X min/h/j' (FR)."""
    from django.utils import timezone
    delta = timezone.now() - date
    secondes = delta.total_seconds()
 
    if secondes < 60:
        return "à l'instant"
    elif secondes < 3600:
        return f"il y a {int(secondes // 60)} min"
    elif secondes < 86400:
        return f"il y a {int(secondes // 3600)} h"
    elif secondes < 604800:
        return f"il y a {int(secondes // 86400)} j"
    else:
        return date.strftime('%d/%m/%Y')
 
 
# =============================================================================
# PARAMÈTRES DE NOTIFICATIONS (lié à ProfilUtilisateur)
# =============================================================================
 
@login_required
@require_POST
def toggle_canal_notification(request):
    """
    Active/désactive un canal de notification (email/sms/push) en un clic.
    POST /compte/notifications/toggle-canal/  body: canal=email
    """
    from .models import ProfilUtilisateur
 
    canal = request.POST.get('canal', '')
    profil, _ = ProfilUtilisateur.objects.get_or_create(utilisateur=request.user)
 
    champ_map = {
        'email': 'notifications_email',
        'sms':   'notifications_sms',
        'push':  'notifications_push',
    }
    champ = champ_map.get(canal)
    if not champ:
        return JsonResponse({'success': False, 'message': 'Canal invalide'}, status=400)
 
    nouvelle_valeur = not getattr(profil, champ)
    setattr(profil, champ, nouvelle_valeur)
    profil.save(update_fields=[champ])
 
    return JsonResponse({'success': True, 'canal': canal, 'actif': nouvelle_valeur})
 
 
 
# =============================================================================
# API AJAX — Vérifications en temps réel
# =============================================================================
 
@require_GET
def ajax_verifier_username(request):
    """
    Vérifie si un nom d'utilisateur est disponible.
    Utilisé lors de l'inscription en temps réel.
    GET /compte/ajax/username/?q=monnom
    """
    username = request.GET.get('q', '').strip()
    if len(username) < 3:
        return JsonResponse({'disponible': False, 'message': 'Minimum 3 caractères'})
 
    existe = Utilisateur.objects.filter(username__iexact=username).exists()
    # Exclure l'utilisateur actuel si connecté
    if request.user.is_authenticated:
        existe = Utilisateur.objects.filter(
            username__iexact=username
        ).exclude(pk=request.user.pk).exists()
 
    return JsonResponse({
        'disponible': not existe,
        'message':    'Disponible' if not existe else 'Déjà utilisé',
    })
 
 
@require_GET
def ajax_verifier_email(request):
    """
    Vérifie si un email est disponible.
    GET /compte/ajax/email/?q=test@test.com
    """
    email = request.GET.get('q', '').lower().strip()
    if not email or '@' not in email:
        return JsonResponse({'disponible': False, 'message': 'Email invalide'})
 
    existe = Utilisateur.objects.filter(email=email).exists()
    if request.user.is_authenticated:
        existe = Utilisateur.objects.filter(email=email).exclude(pk=request.user.pk).exists()
 
    return JsonResponse({
        'disponible': not existe,
        'message':    'Disponible' if not existe else 'Email déjà utilisé',
    })
 
 
@require_GET
def ajax_verifier_sous_domaine(request):
    """
    Vérifie si un sous-domaine est disponible.
    GET /compte/ajax/sous-domaine/?q=mon-shop
    """
    import re
    val = request.GET.get('q', '').lower().strip()
 
    if not re.match(r'^[a-z0-9-]{3,50}$', val):
        return JsonResponse({'disponible': False, 'message': 'Format invalide'})
 
    reserved = ['www', 'api', 'admin', 'shop', 'app', 'mail', 'ftp', 'yopishop']
    if val in reserved:
        return JsonResponse({'disponible': False, 'message': 'Réservé par la plateforme'})
 
    existe = Utilisateur.objects.filter(sous_domaine=val).exists()
    if request.user.is_authenticated:
        existe = Utilisateur.objects.filter(sous_domaine=val).exclude(pk=request.user.pk).exists()
 
    return JsonResponse({
        'disponible': not existe,
        'message':    f'{val}.yopishop.com disponible' if not existe else 'Déjà pris',
        'url_preview': f'https://{val}.yopishop.com' if not existe else '',
    })
 
 
@login_required
@require_GET
def ajax_solde_wallet(request):
    """
    Retourne le solde actuel du wallet.
    GET /compte/ajax/wallet/solde/
    """
    return JsonResponse({
        'solde':    float(request.user.solde_wallet),
        'devise':   'XAF',
        'formate':  f"{request.user.solde_wallet:,.0f} XAF",
    })
 
 
# =============================================================================
# SUPPRESSION DE COMPTE
# =============================================================================
 
@login_required
def supprimer_compte(request):
    """
    Permet à l'utilisateur de supprimer son propre compte.
    Nécessite confirmation par mot de passe.
    """
    if request.method == 'POST':
        mdp = request.POST.get('password', '')
        user = request.user
 
        if not user.check_password(mdp):
            messages.error(request, "Mot de passe incorrect.")
            return render(request, 'apps_core/supprimer_compte.html', {
                'page_titre': 'Supprimer mon compte',
            })
 
        # Déconnecter avant suppression
        logout(request)
        user.is_active = False   # Désactivation douce (pas suppression physique)
        user.save(update_fields=['is_active'])
 
        messages.info(request, "Votre compte a été désactivé. Contactez le support pour une suppression définitive.")
        return redirect('apps_core:accueil')
 
    return render(request, 'apps_core/supprimer_compte.html', {
        'page_titre': 'Supprimer mon compte',
    })



# =============================================================================
# CATALOGUE PUBLIC
# =============================================================================
 
def catalogue(request):
    """
    Page catalogue principale avec filtres et recherche.
    GET params : q, categorie, marque, prix_min, prix_max, etat,
                  type_produit, en_stock, vedette, yopishop, tri, vendeur
    """
    form = FiltreCatalogueForm(request.GET or None)
 
    qs = Produit.objects.filter(est_actif=True).select_related(
        'categorie', 'marque', 'vendeur', 'ville'
    ).prefetch_related('images')
 
    # ── Filtre par vendeur (lien depuis profil public) ────────────────────────
    vendeur_filtre = request.GET.get('vendeur', '')
    if vendeur_filtre == 'yopishop':
        qs = qs.filter(est_produit_yopishop=True)
    elif vendeur_filtre:
        qs = qs.filter(vendeur__username=vendeur_filtre)
 
    if form.is_valid():
        data = form.cleaned_data
 
        if data.get('q'):
            qs = qs.filter(
                Q(titre__icontains=data['q']) |
                Q(description_courte__icontains=data['q']) |
                Q(reference__icontains=data['q']) |
                Q(categorie__nom__icontains=data['q'])
            )
 
        if data.get('categorie'):
            # Inclure les sous-catégories
            cat = data['categorie']
            sous_cats = Categorie.objects.filter(parent=cat).values_list('id', flat=True)
            qs = qs.filter(Q(categorie=cat) | Q(categorie_id__in=sous_cats))
 
        if data.get('marque'):
            qs = qs.filter(marque=data['marque'])
 
        if data.get('prix_min') is not None:
            qs = qs.filter(prix__gte=data['prix_min'])
 
        if data.get('prix_max') is not None:
            qs = qs.filter(prix__lte=data['prix_max'])
 
        if data.get('etat'):
            qs = qs.filter(etat=data['etat'])
 
        if data.get('type_produit'):
            qs = qs.filter(type_produit=data['type_produit'])
 
        if data.get('en_stock'):
            qs = qs.filter(quantite_stock__gt=0)
 
        if data.get('vedette'):
            qs = qs.filter(est_vedette=True)
 
        if data.get('yopishop'):
            qs = qs.filter(est_produit_yopishop=True)
 
        # Tri
        tri = data.get('tri') or 'recent'
        if tri == 'prix_asc':
            qs = qs.order_by('prix')
        elif tri == 'prix_desc':
            qs = qs.order_by('-prix')
        elif tri == 'populaire':
            qs = qs.order_by('-nb_ventes', '-nb_vues')
        elif tri == 'note':
            qs = qs.order_by('-note_moyenne', '-nb_ventes')
        else:
            qs = qs.order_by('-date_creation')
    else:
        qs = qs.order_by('-date_creation')
 
    # Pagination
    paginator = Paginator(qs, 24)
    page_num  = request.GET.get('page', 1)
    produits  = paginator.get_page(page_num)
 
    # Catégories pour le menu latéral
    categories_menu = Categorie.objects.filter(
        est_active=True, parent__isnull=True
    ).prefetch_related('sous_categories').order_by('ordre', 'nom')
 
    # Favoris de l'utilisateur (pour afficher les cœurs pleins)
    favoris_ids = set()
    if request.user.is_authenticated:
        liste = ListeSouhaits.objects.filter(utilisateur=request.user).first()
        if liste:
            favoris_ids = set(liste.produits.values_list('id', flat=True))
 
    context = {
        'form':             form,
        'produits':         produits,
        'categories_menu':  categories_menu,
        'favoris_ids':      favoris_ids,
        'nb_resultats':     paginator.count,
        'vendeur_filtre':   vendeur_filtre,
        'page_titre':       'Catalogue — YopiShop',
    }
    return render(request, 'apps_core/catalogue/catalogue.html', context)


def produit_detail(request, slug):
    """
    Page détail d'un produit.
    Incrémente le compteur de vues, charge images/variantes/attributs/avis.
    """
    produit = get_object_or_404(
        Produit.objects.select_related('categorie', 'marque', 'vendeur', 'ville', 'quartier')
                        .prefetch_related(
                            Prefetch('images', queryset=ImageProduit.objects.order_by('ordre')),
                            Prefetch('variantes', queryset=VarianteProduit.objects.filter(est_active=True)),
                            Prefetch('attributs', queryset=AttributProduit.objects.order_by('ordre')),
                        ),
        slug=slug,
    )
 
    # Visibilité : produit inactif visible seulement par son vendeur ou admin
    if not produit.est_actif:
        if not request.user.is_authenticated or (
            request.user != produit.vendeur and not request.user.is_staff
        ):
            raise Http404("Ce produit n'est plus disponible.")
 
    # Incrémenter les vues (hors propriétaire)
    if not request.user.is_authenticated or request.user != produit.vendeur:
        Produit.objects.filter(pk=produit.pk).update(nb_vues=produit.nb_vues + 1)
 
    # Avis approuvés
    avis_qs = Avis.objects.filter(
        produit=produit, est_approuve=True
    ).select_related('utilisateur').prefetch_related('images').order_by('-date_creation')
 
    avis_stats = avis_qs.aggregate(
        moyenne=Avg('note'),
        total=Count('id'),
    )
 
    # Répartition des notes (5★ → 1★)
    repartition_notes = {}
    for n in range(5, 0, -1):
        repartition_notes[n] = avis_qs.filter(note=n).count()
 
    # L'utilisateur a-t-il déjà laissé un avis ?
    avis_utilisateur = None
    peut_laisser_avis = False
    if request.user.is_authenticated:
        avis_utilisateur = Avis.objects.filter(produit=produit, utilisateur=request.user).first()
        # Idéalement vérifier achat confirmé ; ici on autorise si pas déjà fait
        peut_laisser_avis = avis_utilisateur is None and request.user != produit.vendeur
 
    # Produits similaires (même catégorie)
    produits_similaires = Produit.objects.filter(
        categorie=produit.categorie, est_actif=True
    ).exclude(pk=produit.pk).select_related('vendeur').prefetch_related('images')[:8]
 
    # Favoris
    est_favori = False
    if request.user.is_authenticated:
        liste = ListeSouhaits.objects.filter(utilisateur=request.user).first()
        if liste:
            est_favori = liste.produits.filter(pk=produit.pk).exists()
 
    context = {
        'produit':              produit,
        'avis_liste':           avis_qs[:10],
        'avis_stats':           avis_stats,
        'repartition_notes':    repartition_notes,
        'avis_utilisateur':     avis_utilisateur,
        'peut_laisser_avis':    peut_laisser_avis,
        'produits_similaires':  produits_similaires,
        'est_favori':           est_favori,
        'form_avis':            AvisProduitForm() if peut_laisser_avis else None,
        'page_titre':           f"{produit.titre} — YopiShop",
    }
    return render(request, 'apps_core/catalogue/produit_detail.html', context)


def categorie_detail(request, slug):
    """
    Affiche tous les produits actifs d'une catégorie (et de ses sous-catégories).
 
    GET params supportés :
      tri        : recent | prix_asc | prix_desc | populaire | note
      prix_min   : float
      prix_max   : float
      etat       : neuf | comme_neuf | bon_etat | correct | mauvais
      en_stock   : 1
      vedette    : 1
      marque     : int (pk de Marque)
      page       : int
    """
 
    # ── 1. Catégorie demandée ─────────────────────────────────────────────────
    categorie = get_object_or_404(
        Categorie.objects.prefetch_related('sous_categories'),
        slug=slug,
        est_active=True,
    )
 
    # ── 2. Catégories parentes (fil d'Ariane) ─────────────────────────────────
    breadcrumb = []
    _cat = categorie
    while _cat is not None:
        breadcrumb.insert(0, _cat)
        _cat = _cat.parent
 
    # ── 3. IDs : catégorie + toutes ses sous-catégories ──────────────────────
    sous_cat_ids = list(
        categorie.sous_categories.filter(est_active=True).values_list('id', flat=True)
    )
    cat_ids = [categorie.id] + sous_cat_ids
 
    # ── 4. Queryset de base ───────────────────────────────────────────────────
    qs = Produit.objects.filter(
        est_actif=True,
        categorie_id__in=cat_ids,
    ).select_related(
        'categorie', 'marque', 'vendeur', 'ville'
    ).prefetch_related(
        Prefetch('images', queryset=ImageProduit.objects.order_by('ordre'))
    )
 
    # ── 5. Filtres GET ────────────────────────────────────────────────────────
    prix_min  = request.GET.get('prix_min', '').strip()
    prix_max  = request.GET.get('prix_max', '').strip()
    etat      = request.GET.get('etat', '').strip()
    en_stock  = request.GET.get('en_stock', '').strip()
    vedette   = request.GET.get('vedette', '').strip()
    marque_id = request.GET.get('marque', '').strip()
    q         = request.GET.get('q', '').strip()
    tri       = request.GET.get('tri', 'recent').strip()
 
    if q:
        qs = qs.filter(
            Q(titre__icontains=q) |
            Q(description_courte__icontains=q) |
            Q(reference__icontains=q)
        )
 
    if prix_min:
        try:
            qs = qs.filter(prix__gte=float(prix_min))
        except ValueError:
            pass
 
    if prix_max:
        try:
            qs = qs.filter(prix__lte=float(prix_max))
        except ValueError:
            pass
 
    if etat:
        qs = qs.filter(etat=etat)
 
    if en_stock == '1':
        qs = qs.filter(quantite_stock__gt=0)
 
    if vedette == '1':
        qs = qs.filter(est_vedette=True)
 
    if marque_id:
        try:
            qs = qs.filter(marque_id=int(marque_id))
        except ValueError:
            pass
 
    # ── 6. Tri ────────────────────────────────────────────────────────────────
    TRI_MAP = {
        'prix_asc':  ('prix',),
        'prix_desc': ('-prix',),
        'populaire': ('-nb_ventes', '-nb_vues'),
        'note':      ('-note_moyenne', '-nb_ventes'),
        'recent':    ('-date_creation',),
    }
    qs = qs.order_by(*TRI_MAP.get(tri, ('-date_creation',)))
 
    # ── 7. Agrégats pour la sidebar ───────────────────────────────────────────
    stats = qs.aggregate(
        nb_produits = Count('id'),
        prix_min_db = Min('prix'),
        prix_max_db = Max('prix'),
    )
 
    # Marques disponibles dans cette catégorie
    marques_disponibles = (
        qs.exclude(marque__isnull=True)
          .values('marque__id', 'marque__nom')
          .annotate(nb=Count('id'))
          .order_by('marque__nom')
    )
 
    # ── 8. Pagination ─────────────────────────────────────────────────────────
    paginator = Paginator(qs, 24)
    page_num  = request.GET.get('page', 1)
    produits  = paginator.get_page(page_num)
 
    # ── 9. Sous-catégories actives (pour les pills) ───────────────────────────
    sous_categories = categorie.sous_categories.filter(
        est_active=True
    ).annotate(
        nb_produits=Count('produits', filter=Q(produits__est_actif=True))
    ).order_by('ordre', 'nom')
 
    # ── 10. Favoris utilisateur ───────────────────────────────────────────────
    favoris_ids = set()
    if request.user.is_authenticated:
        liste = ListeSouhaits.objects.filter(utilisateur=request.user).first()
        if liste:
            favoris_ids = set(liste.produits.values_list('id', flat=True))
 
    # ── 11. Menu catégories (sidebar globale) ─────────────────────────────────
    categories_menu = Categorie.objects.filter(
        est_active=True, parent__isnull=True
    ).prefetch_related('sous_categories').order_by('ordre', 'nom')
 
    # ── 12. Contexte ──────────────────────────────────────────────────────────
    context = {
        'categorie':           categorie,
        'sous_categories':     sous_categories,
        'breadcrumb':          breadcrumb,
        'produits':            produits,
        'categories_menu':     categories_menu,
        'marques_disponibles': marques_disponibles,
        'favoris_ids':         favoris_ids,
        'stats':               stats,
 
        # Filtres actifs (pour les conserver dans le template)
        'filtre_q':         q,
        'filtre_tri':       tri,
        'filtre_prix_min':  prix_min,
        'filtre_prix_max':  prix_max,
        'filtre_etat':      etat,
        'filtre_en_stock':  en_stock,
        'filtre_vedette':   vedette,
        'filtre_marque':    marque_id,
 
        'nb_resultats':    paginator.count,
        'page_titre':      f"{categorie.nom} — YopiShop",
 
        # Choix pour les filtres
        'etat_choices': Produit.ETAT_CHOICES,
        'tri_choices': [
            ('recent',    'Plus récents'),
            ('populaire', 'Plus populaires'),
            ('note',      'Mieux notés'),
            ('prix_asc',  'Prix croissant'),
            ('prix_desc', 'Prix décroissant'),
        ],
    }
    return render(request, 'apps_core/catalogue/categorie_detail.html', context)
 
 


# =============================================================================
# GESTION VENDEUR — CRUD PRODUITS
# =============================================================================
 
@login_required
def mes_produits(request):
    """Liste des produits du vendeur connecté, avec filtres rapides."""
    if not request.user.peut_vendre:
        messages.warning(request, "Vous devez être vendeur pour accéder à cette page.")
        return redirect('apps_core:devenir_vendeur')
 
    qs = Produit.objects.filter(vendeur=request.user).select_related(
        'categorie', 'marque'
    ).prefetch_related('images').order_by('-date_creation')
 
    statut = request.GET.get('statut', '')
    if statut == 'actif':
        qs = qs.filter(est_actif=True)
    elif statut == 'inactif':
        qs = qs.filter(est_actif=False)
    elif statut == 'rupture':
        qs = qs.filter(quantite_stock=0)
    elif statut == 'vedette':
        qs = qs.filter(est_vedette=True)
 
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(Q(titre__icontains=q) | Q(reference__icontains=q) | Q(sku__icontains=q))
 
    paginator = Paginator(qs, 20)
    produits  = paginator.get_page(request.GET.get('page', 1))
 
    stats = {
        'total':    Produit.objects.filter(vendeur=request.user).count(),
        'actifs':   Produit.objects.filter(vendeur=request.user, est_actif=True).count(),
        'inactifs': Produit.objects.filter(vendeur=request.user, est_actif=False).count(),
        'rupture':  Produit.objects.filter(vendeur=request.user, quantite_stock=0).count(),
    }

    context = {
        'produits':   produits,
        'stats':      stats,
        'statut':     statut,
        'q':          q,
        'page_titre': 'Mes produits',
    }
 
    return render(request, 'apps_core/catalogue/mes_produits.html', context)
 
 
@login_required
def ajouter_produit(request):
    """
    Création d'un nouveau produit.
 
    Le champ est_produit_yopishop n'apparaît dans le formulaire que pour :
      - les admins/super admins (is_staff / is_superuser)
      - les comptes type_vendeur == 'yopishop'
    Cf. ProduitForm.__init__ et utilisateur_peut_definir_yopishop().
    """
    if not request.user.peut_vendre:
        messages.warning(request, "Vous devez être vendeur pour ajouter un produit.")
        return redirect('apps_core:devenir_vendeur')
 
    if request.method == 'POST':
        form = ProduitForm(request.POST, request.FILES, user=request.user)
 
        if form.is_valid():
            with transaction.atomic():
                produit = form.save(commit=False)
                produit.vendeur = request.user
 
                # Génération référence unique si absente
                if not produit.reference:
                    import uuid as uuid_lib
                    produit.reference = f"YS-{uuid_lib.uuid4().hex[:10].upper()}"
 
                produit.save()
 
                # Formsets liés
                images_formset    = ImageProduitFormSet(request.POST, request.FILES, instance=produit, prefix='images')
                variantes_formset = VarianteProduitFormSet(request.POST, request.FILES, instance=produit, prefix='variantes')
                attributs_formset = AttributProduitFormSet(request.POST, instance=produit, prefix='attributs')
 
                for fs in (images_formset, variantes_formset, attributs_formset):
                    if fs.is_valid():
                        fs.save()
 
                # S'assurer qu'au moins une image est marquée principale
                if produit.images.exists() and not produit.images.filter(est_principale=True).exists():
                    first_img = produit.images.first()
                    first_img.est_principale = True
                    first_img.save(update_fields=['est_principale'])
 
            messages.success(request, f"Le produit « {produit.titre} » a été créé avec succès.")
            return redirect('apps_core:produit_detail', slug=produit.slug)
        else:
            messages.error(request, "Veuillez corriger les erreurs ci-dessous.")
            images_formset    = ImageProduitFormSet(request.POST, request.FILES, prefix='images')
            variantes_formset = VarianteProduitFormSet(request.POST, request.FILES, prefix='variantes')
            attributs_formset = AttributProduitFormSet(request.POST, prefix='attributs')
 
    else:
        form = ProduitForm(user=request.user)
        images_formset    = ImageProduitFormSet(prefix='images')
        variantes_formset = VarianteProduitFormSet(prefix='variantes')
        attributs_formset = AttributProduitFormSet(prefix='attributs')
    
    context = {
        'form':              form,
        'images_formset':    images_formset,
        'variantes_formset': variantes_formset,
        'attributs_formset': attributs_formset,
        'mode':              'creation',
        'peut_yopishop':     utilisateur_peut_definir_yopishop(request.user),
        'page_titre':        'Ajouter un produit',
    }
 
    return render(request, 'apps_core/catalogue/produit_form.html', context)


@login_required
def modifier_produit(request, slug):
    """
    Modification d'un produit existant.
    Seul le vendeur propriétaire ou un admin peut modifier.
    """
    produit = get_object_or_404(Produit, slug=slug)
 
    if produit.vendeur != request.user and not request.user.is_staff:
        messages.error(request, "Vous n'avez pas la permission de modifier ce produit.")
        return redirect('apps_core:produit_detail', slug=produit.slug)
 
    if request.method == 'POST':
        form = ProduitForm(request.POST, request.FILES, instance=produit, user=request.user)
 
        if form.is_valid():
            with transaction.atomic():
                produit = form.save()
 
                images_formset    = ImageProduitFormSet(request.POST, request.FILES, instance=produit, prefix='images')
                variantes_formset = VarianteProduitFormSet(request.POST, request.FILES, instance=produit, prefix='variantes')
                attributs_formset = AttributProduitFormSet(request.POST, instance=produit, prefix='attributs')
 
                for fs in (images_formset, variantes_formset, attributs_formset):
                    if fs.is_valid():
                        fs.save()
 
                # Garantir une image principale
                if produit.images.exists() and not produit.images.filter(est_principale=True).exists():
                    first_img = produit.images.first()
                    first_img.est_principale = True
                    first_img.save(update_fields=['est_principale'])
 
            messages.success(request, f"Le produit « {produit.titre} » a été mis à jour.")
            return redirect('apps_core:produit_detail', slug=produit.slug)
        else:
            messages.error(request, "Veuillez corriger les erreurs ci-dessous.")
            images_formset    = ImageProduitFormSet(request.POST, request.FILES, instance=produit, prefix='images')
            variantes_formset = VarianteProduitFormSet(request.POST, request.FILES, instance=produit, prefix='variantes')
            attributs_formset = AttributProduitFormSet(request.POST, instance=produit, prefix='attributs')
 
    else:
        form = ProduitForm(instance=produit, user=request.user)
        images_formset    = ImageProduitFormSet(instance=produit, prefix='images')
        variantes_formset = VarianteProduitFormSet(instance=produit, prefix='variantes')
        attributs_formset = AttributProduitFormSet(instance=produit, prefix='attributs')
    
    context = {
        'form':              form,
        'images_formset':    images_formset,
        'variantes_formset': variantes_formset,
        'attributs_formset': attributs_formset,
        'mode':              'edition',
        'produit':           produit,
        'peut_yopishop':     utilisateur_peut_definir_yopishop(request.user),
        'page_titre':        f"Modifier — {produit.titre}",
    }
 
    return render(request, 'apps_core/catalogue/produit_form.html', context)

@login_required
@require_POST
def supprimer_produit(request, slug):
    """Suppression (ou désactivation) d'un produit par son propriétaire/admin."""
    produit = get_object_or_404(Produit, slug=slug)
 
    if produit.vendeur != request.user and not request.user.is_staff:
        messages.error(request, "Action non autorisée.")
        return redirect('apps_core:produit_detail', slug=produit.slug)
 
    titre = produit.titre
 
    # Si le produit a déjà des ventes, on désactive plutôt que supprimer
    if produit.nb_ventes > 0:
        produit.est_actif = False
        produit.save(update_fields=['est_actif'])
        messages.info(request, f"« {titre} » a été désactivé (des ventes existent déjà, suppression impossible).")
    else:
        produit.delete()
        messages.success(request, f"« {titre} » a été supprimé.")
 
    return redirect('apps_core:mes_produits')


@login_required
@require_POST
def toggle_actif_produit(request, slug):
    """Active/désactive rapidement un produit (AJAX)."""
    produit = get_object_or_404(Produit, slug=slug)
 
    if produit.vendeur != request.user and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)
 
    produit.est_actif = not produit.est_actif
    produit.save(update_fields=['est_actif'])
 
    return JsonResponse({'success': True, 'est_actif': produit.est_actif})
 
 
@login_required
@require_POST
def toggle_vedette_produit(request, slug):
    """Active/désactive le statut 'vedette' (AJAX)."""
    produit = get_object_or_404(Produit, slug=slug)
 
    if produit.vendeur != request.user and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)
 
    produit.est_vedette = not produit.est_vedette
    produit.save(update_fields=['est_vedette'])
 
    return JsonResponse({'success': True, 'est_vedette': produit.est_vedette})


@login_required
@require_POST
def toggle_yopishop_produit(request, slug):
    """
    Active/désactive le badge 'Produit YopiShop Officiel' (AJAX).
    RÉSERVÉ aux admins et aux comptes type_vendeur == 'yopishop'.
    """
    if not utilisateur_peut_definir_yopishop(request.user):
        return JsonResponse({
            'success': False,
            'message': "Seuls les administrateurs et le compte YopiShop Officiel peuvent modifier ce badge."
        }, status=403)
 
    produit = get_object_or_404(Produit, slug=slug)
    produit.est_produit_yopishop = not produit.est_produit_yopishop
    produit.save(update_fields=['est_produit_yopishop'])
 
    return JsonResponse({'success': True, 'est_produit_yopishop': produit.est_produit_yopishop})


# =============================================================================
# CATÉGORIES — PUBLIC
# =============================================================================
 
def categories_liste(request):
    """Liste de toutes les catégories actives (page publique)."""
    categories = Categorie.objects.filter(
        est_active=True, parent__isnull=True
    ).prefetch_related(
        Prefetch('sous_categories', queryset=Categorie.objects.filter(est_active=True))
    ).annotate(
        nb_produits=Count('produits', filter=Q(produits__est_actif=True))
    ).order_by('ordre', 'nom')

    context = {
        'categories':  categories,
        'page_titre':  'Toutes les catégories',
    }
 
    return render(request, 'apps_core/catalogue/categories_liste.html', context)
 
 
def categorie_detail(request, slug):
    """Page d'une catégorie : produits filtrés."""
    categorie = get_object_or_404(Categorie, slug=slug, est_active=True)
 
    # Rediriger vers le catalogue avec le filtre catégorie pré-rempli
    from django.urls import reverse
    from django.http import HttpResponseRedirect
    return HttpResponseRedirect(f"{reverse('apps_core:catalogue')}?categorie={categorie.slug}")


# =============================================================================
# CATÉGORIES — GESTION (admin / vendeurs habilités)
# =============================================================================
 
@login_required
def gerer_categories(request):
    """Liste de gestion des catégories — admins uniquement."""
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')
 
    categories = Categorie.objects.select_related('parent').annotate(
        nb_produits=Count('produits')
    ).order_by('ordre', 'nom')

    context = {
        'categories':  categories,
        'page_titre':  'Gestion des catégories',
    }
 
    return render(request, 'apps_core/catalogue/gerer_categories.html', context)
 
 
@login_required
def ajouter_categorie(request):
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')
 
    if request.method == 'POST':
        form = CategorieForm(request.POST, request.FILES)
        if form.is_valid():
            cat = form.save()
            messages.success(request, f"Catégorie « {cat.nom} » créée.")
            return redirect('apps_core:gerer_categories')
    else:
        form = CategorieForm()
    
    context = {
        'form': form, 'mode': 'creation', 'page_titre': 'Ajouter une catégorie',
    }
 
    return render(request, 'apps_core/catalogue/categorie_form.html', context)


@login_required
def modifier_categorie(request, slug):
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')
 
    categorie = get_object_or_404(Categorie, slug=slug)
 
    if request.method == 'POST':
        form = CategorieForm(request.POST, request.FILES, instance=categorie)
        if form.is_valid():
            form.save()
            messages.success(request, f"Catégorie « {categorie.nom} » mise à jour.")
            return redirect('apps_core:gerer_categories')
    else:
        form = CategorieForm(instance=categorie)
    
    context = {
        'form': form, 'mode': 'edition', 'categorie': categorie,
        'page_titre': f"Modifier — {categorie.nom}",
    }
 
    return render(request, 'apps_core/catalogue/categorie_form.html', context)
 
 
@login_required
@require_POST
def supprimer_categorie(request, slug):
    if not request.user.is_staff:
        return JsonResponse({'success': False}, status=403)
 
    categorie = get_object_or_404(Categorie, slug=slug)
    if categorie.produits.exists():
        messages.error(request, "Impossible de supprimer : des produits sont rattachés à cette catégorie.")
    else:
        categorie.delete()
        messages.success(request, "Catégorie supprimée.")
    return redirect('apps_core:gerer_categories')


# =============================================================================
# MARQUES
# =============================================================================
 
def marques_liste(request):
    """Liste publique des marques actives."""
    marques = Marque.objects.filter(est_active=True).annotate(
        nb_produits=Count('produits', filter=Q(produits__est_actif=True))
    ).order_by('nom')

    context = {
        'marques':    marques,
        'page_titre': 'Toutes les marques',
    }
 
    return render(request, 'apps_core/catalogue/marques_liste.html', context)
 
 
@login_required
def gerer_marques(request):
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')
 
    marques = Marque.objects.annotate(nb_produits=Count('produits')).order_by('nom')

    context = {
        'marques': marques, 'page_titre': 'Gestion des marques',
    }
 
    return render(request, 'apps_core/catalogue/gerer_marques.html', context)
 
 
@login_required
def ajouter_marque(request):
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')
 
    if request.method == 'POST':
        form = MarqueForm(request.POST, request.FILES)
        if form.is_valid():
            marque = form.save()
            messages.success(request, f"Marque « {marque.nom} » créée.")
            return redirect('apps_core:gerer_marques')
    else:
        form = MarqueForm()
    
    context = {
        'form': form, 'mode': 'creation', 'page_titre': 'Ajouter une marque',
    }
 
    return render(request, 'apps_core/catalogue/marque_form.html', context)

@login_required
def modifier_marque(request, slug):
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')
 
    marque = get_object_or_404(Marque, slug=slug)
 
    if request.method == 'POST':
        form = MarqueForm(request.POST, request.FILES, instance=marque)
        if form.is_valid():
            form.save()
            messages.success(request, f"Marque « {marque.nom} » mise à jour.")
            return redirect('apps_core:gerer_marques')
    else:
        form = MarqueForm(instance=marque)
 
    return render(request, 'apps_core/catalogue/marque_form.html', {
        'form': form, 'mode': 'edition', 'marque': marque,
        'page_titre': f"Modifier — {marque.nom}",
    })
 


# =============================================================================
# AVIS PRODUIT
# =============================================================================
 
@login_required
@require_POST
def ajouter_avis(request, slug):
    """Ajoute un avis sur un produit."""
    produit = get_object_or_404(Produit, slug=slug)
 
    if produit.vendeur == request.user:
        messages.error(request, "Vous ne pouvez pas laisser un avis sur votre propre produit.")
        return redirect('apps_core:produit_detail', slug=slug)
 
    if Avis.objects.filter(produit=produit, utilisateur=request.user).exists():
        messages.warning(request, "Vous avez déjà laissé un avis sur ce produit.")
        return redirect('apps_core:produit_detail', slug=slug)
 
    form = AvisProduitForm(request.POST, request.FILES)
    if form.is_valid():
        avis = Avis.objects.create(
            produit=produit,
            utilisateur=request.user,
            note=form.cleaned_data['note'],
            titre=form.cleaned_data['titre'],
            commentaire=form.cleaned_data['commentaire'],
        )
 
        # Gestion des images multiples
        images = request.FILES.getlist('images')
        for img in images[:5]:
            img_obj = ImageAvis.objects.create(image=img)
            avis.images.add(img_obj)
 
        # Recalcul de la note moyenne du produit
        moyenne = Avis.objects.filter(produit=produit, est_approuve=True).aggregate(m=Avg('note'))['m'] or 0
        produit.note_moyenne = round(moyenne, 2)
        produit.save(update_fields=['note_moyenne'])
 
        messages.success(request, "Merci pour votre avis !")
    else:
        messages.error(request, "Veuillez corriger les erreurs de votre avis.")
 
    return redirect('apps_core:produit_detail', slug=slug)

@login_required
@require_POST
def voter_utile_avis(request, pk):
    """Vote 'utile' sur un avis (AJAX)."""
    avis = get_object_or_404(Avis, pk=pk)
    avis.votes_utiles += 1
    avis.save(update_fields=['votes_utiles'])
    return JsonResponse({'success': True, 'votes_utiles': avis.votes_utiles})

# =============================================================================
# FAVORIS / LISTE DE SOUHAITS
# =============================================================================
 
@login_required
def favoris_liste(request):
    """Page des favoris de l'utilisateur."""
    liste, _ = ListeSouhaits.objects.get_or_create(
        utilisateur=request.user, nom='Ma liste'
    )
    produits = liste.produits.filter(est_actif=True).select_related(
        'categorie', 'vendeur'
    ).prefetch_related('images')
 
    return render(request, 'apps_core/catalogue/favoris.html', {
        'produits':   produits,
        'page_titre': 'Mes favoris',
    })
 
 
@login_required
@require_POST
def toggle_favori(request, pk):
    """Ajoute/retire un produit des favoris (AJAX)."""
    produit = get_object_or_404(Produit, pk=pk)
    liste, _ = ListeSouhaits.objects.get_or_create(
        utilisateur=request.user, nom='Ma liste'
    )
 
    if liste.produits.filter(pk=produit.pk).exists():
        liste.produits.remove(produit)
        ajoute = False
    else:
        liste.produits.add(produit)
        ajoute = True
 
    return JsonResponse({
        'success': True,
        'ajoute':  ajoute,
        'nb_favoris': liste.produits.count(),
    })

# =============================================================================
# AJAX — Recherche / Autocomplete
# =============================================================================
 
@require_GET
def ajax_recherche_produits(request):
    """
    Autocomplete de recherche produits.
    GET /catalogue/ajax/recherche/?q=iphone
    """
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'resultats': []})
 
    produits = Produit.objects.filter(
        est_actif=True, titre__icontains=q
    ).select_related('categorie')[:8]
 
    resultats = [{
        'id':         p.id,
        'titre':      p.titre,
        'slug':       p.slug,
        'prix':       float(p.prix_promotionnel()),
        'categorie':  p.categorie.nom,
        'image':      p.image_principale(),
        'url':        f"/produits/{p.slug}/",
    } for p in produits]
 
    return JsonResponse({'resultats': resultats})
 
 
@require_GET
def ajax_sous_categories(request):
    """
    Retourne les sous-catégories d'une catégorie (pour filtres dynamiques).
    GET /catalogue/ajax/sous-categories/?parent_id=5
    """
    parent_id = request.GET.get('parent_id')
    if not parent_id:
        return JsonResponse({'sous_categories': []})
 
    sous_cats = Categorie.objects.filter(
        parent_id=parent_id, est_active=True
    ).values('id', 'nom', 'slug')
 
    return JsonResponse({'sous_categories': list(sous_cats)})




# =============================================================================
# HELPERS
# =============================================================================
 
def _utilisateur_peut_gerer_promos(user):
    """Admin ou vendeur pro."""
    if not user.is_authenticated:
        return False
    return user.is_staff or user.is_superuser or getattr(user, 'type_vendeur', '') in ('pro', 'yopishop')
 
 
def _calculer_reduction(promo, montant):
    """Calcule la réduction en FCFA pour un montant donné."""
    if promo.montant_min_achat and montant < promo.montant_min_achat:
        return Decimal('0')
    if promo.type_promotion == 'pourcentage':
        r = (promo.valeur_reduction / Decimal('100')) * montant
    elif promo.type_promotion == 'montant_fixe':
        r = promo.valeur_reduction
    elif promo.type_promotion == 'livraison_gratuite':
        return None   # Signifie "livraison offerte"
    else:
        return Decimal('0')
    if promo.montant_max_reduction:
        r = min(r, promo.montant_max_reduction)
    return min(r, montant)
 
 
# =============================================================================
# PAGES PUBLIQUES
# =============================================================================
 
def promotions_liste(request):
    now = timezone.now()

    qs_actives = Promotion.objects.filter(
        statut='active',
        date_debut__lte=now,
        date_fin__gte=now,
    ).prefetch_related('categories', 'produits').order_by('-priorite', '-date_creation')

    qs_a_venir = Promotion.objects.filter(
        statut='active',
        date_debut__gt=now,
    ).prefetch_related('categories').order_by('date_debut')[:6]

    # Filtre par type
    type_filtre = request.GET.get('type', '').strip()
    if type_filtre:
        qs_actives = qs_actives.filter(type_promotion=type_filtre)

    # Filtre par catégorie — .distinct() évite les doublons sur le JOIN M2M
    cat_slug = request.GET.get('categorie', '').strip()
    if cat_slug:
        qs_actives = qs_actives.filter(categories__slug=cat_slug).distinct()

    paginator  = Paginator(qs_actives, 12)
    promotions = paginator.get_page(request.GET.get('page', 1))

    categories = Categorie.objects.filter(est_active=True).order_by('ordre', 'nom')

    # Debug temporaire — à retirer ensuite
    print(f"[PROMO DEBUG] nb actives trouvées : {qs_actives.count()}")
    print(f"[PROMO DEBUG] now = {now}")

    context = {
        'promotions':  promotions,
        'a_venir':     qs_a_venir,
        'type_filtre': type_filtre,
        'cat_slug':    cat_slug,
        'categories':  categories,
        'types':       Promotion.TYPE_CHOICES,
        'page_titre':  'Promotions & Codes promo — YopiShop',
    }
    return render(request, 'apps_core/catalogue/promotions_liste.html', context)
 
 
def promotion_detail(request, pk):
    """Détail d'une promotion — affiche les produits concernés."""
    now   = timezone.now()
    promo = get_object_or_404(
        Promotion.objects.prefetch_related('categories', 'produits'),
        pk=pk,
    )
 
    # Seule une promotion active ou les admins peuvent voir le détail
    if promo.statut != 'active' and not (request.user.is_authenticated and request.user.is_staff):
        messages.warning(request, "Cette promotion n'est pas disponible.")
        return redirect('apps_core:promotions_liste')
 
    # Produits éligibles
    produits_eligibles = Produit.objects.filter(
        est_actif=True,
    ).filter(
        Q(id__in=promo.produits.values_list('id', flat=True)) |
        Q(categorie_id__in=promo.categories.values_list('id', flat=True))
    ).select_related('categorie', 'vendeur').prefetch_related('images')[:24]
 
    est_active = (
        promo.statut == 'active'
        and promo.date_debut <= now <= promo.date_fin
    )
 
    context = {
        'promo':             promo,
        'produits_eligibles': produits_eligibles,
        'est_active':        est_active,
        'page_titre':        f"{promo.nom} — YopiShop",
    }
    return render(request, 'apps_core/catalogue/promotion_detail.html', context)
 
 
# =============================================================================
# GESTION VENDEURS / ADMINS
# =============================================================================
 
@login_required
def mes_promotions(request):
    """
    Liste de mes promotions (vendeur/admin).
    Admins voient toutes les promotions, vendeurs seulement les leurs.
    """
    if not _utilisateur_peut_gerer_promos(request.user):
        messages.warning(request, "Vous devez être vendeur pro pour gérer des promotions.")
        return redirect('apps_core:devenir_vendeur')
 
    now = timezone.now()
 
    if request.user.is_staff or request.user.is_superuser:
        qs = Promotion.objects.prefetch_related('categories', 'produits').order_by('-date_creation')
    else:
        # Vendeur : promotions liées à ses produits
        mes_produits_ids = Produit.objects.filter(vendeur=request.user).values_list('id', flat=True)
        qs = Promotion.objects.filter(
            produits__id__in=mes_produits_ids
        ).distinct().prefetch_related('categories', 'produits').order_by('-date_creation')
 
    # Filtre statut
    statut = request.GET.get('statut', '')
    if statut:
        qs = qs.filter(statut=statut)
 
    # Recherche
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(code__icontains=q))
 
    paginator  = Paginator(qs, 15)
    promotions = paginator.get_page(request.GET.get('page', 1))
 
    stats = {
        'total':     qs.count(),
        'actives':   qs.filter(statut='active', date_debut__lte=now, date_fin__gte=now).count(),
        'brouillons': qs.filter(statut='brouillon').count(),
        'expirees':  qs.filter(Q(statut='expiree') | Q(date_fin__lt=now)).count(),
    }
 
    context = {
        'promotions': promotions,
        'stats':      stats,
        'statut':     statut,
        'q':          q,
        'page_titre': 'Mes promotions',
    }
    return render(request, 'apps_core/catalogue/mes_promotions.html', context)
 
from apps_core.views import creer_notification, creer_notification_masse
User = get_user_model()

def _notifier_acheteurs_promo(promo):
    """
    Notifie les acheteurs dont des produits favoris sont couverts
    par la promotion qui vient d'être créée/activée.
    """
    from apps_core.views import creer_notification
    from django.contrib.auth import get_user_model
    User = get_user_model()

    # IDs produits directement ciblés
    produits_ids = set(promo.produits.values_list('id', flat=True))

    # IDs produits des catégories ciblées
    cats_ids = promo.categories.values_list('id', flat=True)
    if cats_ids:
        produits_ids |= set(
            Produit.objects.filter(
                categorie_id__in=cats_ids,
                est_actif=True,
            ).values_list('id', flat=True)
        )

    if not produits_ids:
        return  # Promo globale sans ciblage → pas de notif ciblée

    # Utilisateurs ayant ces produits en favoris
    try:
        from apps_core.models import Favori
        utilisateurs = (
            User.objects.filter(
                favoris__produit_id__in=produits_ids,
                is_active=True,
            )
            .distinct()
        )
    except Exception:
        return

    # ── Construire le message — Python pur, zéro tag Django ──
    if promo.type_promotion == 'pourcentage':
        detail = f"-{promo.valeur_reduction:.0f}% de réduction"
    elif promo.type_promotion == 'montant_fixe':
        detail = f"-{promo.valeur_reduction:.0f} FCFA de réduction"
    elif promo.type_promotion == 'livraison_gratuite':
        detail = "livraison gratuite"
    else:
        detail = "une offre spéciale"

    code_part = f" Code promo : {promo.code}." if promo.code else ""
    date_fin  = promo.date_fin.strftime('%d/%m/%Y')

    for user in utilisateurs:
        creer_notification(
            utilisateur=user,
            type_notification='promo',
            titre=f"🏷️ Promo sur vos favoris — {promo.nom}",
            message=(
                f"Un article dans vos favoris bénéficie de {detail}."
                f"{code_part}"
                f" Offre valable jusqu'au {date_fin}."
            ),
            lien=f"/promotions/{promo.pk}/",
        )

@login_required
def creer_promotion(request):
    """Création d'une nouvelle promotion."""
    if not _utilisateur_peut_gerer_promos(request.user):
        messages.warning(request, "Accès non autorisé.")
        return redirect('apps_core:accueil')
 
    if request.method == 'POST':
        form = PromotionForm(request.POST, user=request.user)
        if form.is_valid():
            promo = form.save(commit=False)
            promo.save()
            form.save_m2m()   # Sauvegarde les M2M (categories, produits)

            # ═══ NOTIFICATIONS ═══════════════════════════════════════════

            # 1. Notifier l'admin/staff si c'est un vendeur qui crée
            if not request.user.is_staff:
                admins = User.objects.filter(is_staff=True, is_active=True)
                creer_notification_masse(
                    utilisateurs_qs=admins,
                    type_notification='promo',
                    titre="Nouvelle promotion créée",
                    message=f"Le vendeur {request.user.get_full_name() or request.user.username} "
                            f"a créé la promotion « {promo.nom} ».",
                    lien=f"/promotions/{promo.pk}/",
                )
                
                # 2. Notifier les acheteurs qui ont des produits éligibles en favoris
            #    (uniquement si la promo est déjà active dès la création)
            if promo.statut == 'active':
                _notifier_acheteurs_promo(promo)

            # ═════════════════════════════════════════════════════════════
            messages.success(request, f"Promotion « {promo.nom} » créée avec succès.")
            return redirect('apps_core:mes_promotions')
        else:
            messages.error(request, "Veuillez corriger les erreurs ci-dessous.")
    else:
        form = PromotionForm(user=request.user)
 
    return render(request, 'apps_core/catalogue/promotion_form.html', {
        'form':       form,
        'mode':       'creation',
        'page_titre': 'Créer une promotion',
    })
 
 
@login_required
def modifier_promotion(request, pk):
    """Modification d'une promotion existante."""
    promo = get_object_or_404(Promotion, pk=pk)
 
    # Vérification des droits
    if not request.user.is_staff:
        mes_produits_ids = set(
            Produit.objects.filter(vendeur=request.user).values_list('id', flat=True)
        )
        promo_produits_ids = set(promo.produits.values_list('id', flat=True))
        if not mes_produits_ids.intersection(promo_produits_ids):
            messages.error(request, "Vous n'avez pas la permission de modifier cette promotion.")
            return redirect('apps_core:mes_promotions')
 
    if request.method == 'POST':
        form = PromotionForm(request.POST, instance=promo, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f"Promotion « {promo.nom} » mise à jour.")
            return redirect('apps_core:mes_promotions')
        else:
            messages.error(request, "Veuillez corriger les erreurs ci-dessous.")
    else:
        form = PromotionForm(instance=promo, user=request.user)
 
    return render(request, 'apps_core/catalogue/promotion_form.html', {
        'form':       form,
        'promo':      promo,
        'mode':       'edition',
        'page_titre': f"Modifier — {promo.nom}",
    })
 
 
@login_required
@require_POST
def supprimer_promotion(request, pk):
    """Suppression d'une promotion."""
    promo = get_object_or_404(Promotion, pk=pk)
 
    if not request.user.is_staff:
        messages.error(request, "Seuls les administrateurs peuvent supprimer une promotion.")
        return redirect('apps_core:mes_promotions')
 
    nom = promo.nom
    promo.delete()
    messages.success(request, f"Promotion « {nom} » supprimée.")
    return redirect('apps_core:mes_promotions')
 
 
@login_required
@require_POST
def toggle_statut_promotion(request, pk):
    """
    Bascule le statut d'une promotion : active ↔ en_pause (AJAX).
    Admins uniquement pour 'expiree'.
    """
    promo = get_object_or_404(Promotion, pk=pk)
 
    if not _utilisateur_peut_gerer_promos(request.user):
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)
 
    nouveau_statut = request.POST.get('statut', '')
    statuts_valides = ['active', 'en_pause', 'brouillon']
    if request.user.is_staff:
        statuts_valides.append('expiree')
 
    if nouveau_statut not in statuts_valides:
        return JsonResponse({'success': False, 'message': 'Statut invalide'}, status=400)
 
    promo.statut = nouveau_statut
    promo.save(update_fields=['statut'])
 
    return JsonResponse({
        'success': True,
        'statut':  promo.statut,
        'label':   promo.get_statut_display(),
    })


 
@login_required
def stats_promotion(request, pk):
    """Statistiques d'utilisation d'une promotion."""
    promo = get_object_or_404(Promotion, pk=pk)
 
    if not _utilisateur_peut_gerer_promos(request.user):
        messages.error(request, "Accès non autorisé.")
        return redirect('apps_core:mes_promotions')
 
    # Statistiques d'utilisation via les commandes (si app_marketplace disponible)
    utilisations = []
    nb_utilisations = 0
    montant_total_reduction = Decimal('0')
 
    try:
        from app_marketplace.models import Commande
        commandes = Commande.objects.filter(
            promotion=promo
        ).select_related('utilisateur').order_by('-date_creation')
 
        nb_utilisations = commandes.count()
        montant_total_reduction = commandes.aggregate(
            total=Sum('montant_reduction')
        )['total'] or Decimal('0')
        utilisations = commandes[:20]
    except Exception:
        pass
 
    taux_utilisation = 0
    if promo.limite_utilisation and promo.limite_utilisation > 0:
        taux_utilisation = min(100, round((nb_utilisations / promo.limite_utilisation) * 100))
 
    context = {
        'promo':                  promo,
        'utilisations':           utilisations,
        'nb_utilisations':        nb_utilisations,
        'montant_total_reduction': montant_total_reduction,
        'taux_utilisation':       taux_utilisation,
        'page_titre':             f"Statistiques — {promo.nom}",
    }
    return render(request, 'apps_core/catalogue/promotion_stats.html', context)
 
 
# =============================================================================
# AJAX
# =============================================================================
 
@require_GET
def ajax_verifier_code_promo(request):
    """
    Vérifie un code promo et retourne les détails.
    GET /promotions/ajax/verifier/?code=PROMO20&montant=15000
    """
    code    = request.GET.get('code', '').strip().upper()
    montant = request.GET.get('montant', '0')
 
    if not code:
        return JsonResponse({'valide': False, 'message': 'Code vide'})
 
    try:
        montant = Decimal(montant)
    except Exception:
        montant = Decimal('0')
 
    now = timezone.now()
    try:
        promo = Promotion.objects.get(
            code=code,
            statut='active',
            date_debut__lte=now,
            date_fin__gte=now,
        )
    except Promotion.DoesNotExist:
        return JsonResponse({'valide': False, 'message': 'Code invalide ou expiré'})
 
    # Vérifier limite utilisateur
    if request.user.is_authenticated and promo.limite_par_utilisateur:
        try:
            from app_marketplace.models import Commande
            nb_utilisations_user = Commande.objects.filter(
                promotion=promo, utilisateur=request.user
            ).count()
            if nb_utilisations_user >= promo.limite_par_utilisateur:
                return JsonResponse({
                    'valide': False,
                    'message': f'Vous avez déjà utilisé ce code {nb_utilisations_user} fois.'
                })
        except Exception:
            pass
 
    # Vérifier limite totale
    if promo.limite_utilisation:
        try:
            from app_marketplace.models import Commande
            nb_total = Commande.objects.filter(promotion=promo).count()
            if nb_total >= promo.limite_utilisation:
                return JsonResponse({'valide': False, 'message': 'Ce code a atteint sa limite d\'utilisation.'})
        except Exception:
            pass
 
    # Montant minimum
    if promo.montant_min_achat and montant < promo.montant_min_achat:
        return JsonResponse({
            'valide': False,
            'message': f"Achat minimum requis : {promo.montant_min_achat:,.0f} FCFA"
        })
 
    # Calculer la réduction
    reduction = _calculer_reduction(promo, montant)
 
    if reduction is None:
        # Livraison gratuite
        return JsonResponse({
            'valide':        True,
            'code':          promo.code,
            'nom':           promo.nom,
            'type':          promo.type_promotion,
            'message':       '🚚 Livraison gratuite appliquée !',
            'reduction':     0,
            'livraison_gratuite': True,
        })
 
    return JsonResponse({
        'valide':           True,
        'code':             promo.code,
        'nom':              promo.nom,
        'type':             promo.type_promotion,
        'valeur_reduction': float(promo.valeur_reduction),
        'reduction':        float(reduction),
        'reduction_fmt':    f"{reduction:,.0f} FCFA",
        'nouveau_total':    float(montant - reduction),
        'message':          f"Code appliqué — {reduction:,.0f} FCFA de réduction",
        'livraison_gratuite': False,
    })
 
 
@require_POST
@login_required
def ajax_appliquer_code_promo(request):
    """
    Applique un code promo à la session (panier).
    POST /promotions/ajax/appliquer/
    """
    form = CodePromoForm(request.POST)
    if form.is_valid():
        promo = form.promo
        request.session['code_promo_id']   = promo.pk
        request.session['code_promo_code'] = promo.code
        request.session.modified = True
 
        montant = Decimal(str(request.POST.get('montant', '0')))
        reduction = _calculer_reduction(promo, montant)
 
        return JsonResponse({
            'success':      True,
            'code':         promo.code,
            'nom':          promo.nom,
            'reduction':    float(reduction) if reduction is not None else 0,
            'livraison_gratuite': reduction is None,
            'message':      f"✅ Code « {promo.code} » appliqué avec succès.",
        })
    else:
        erreur = next(iter(form.errors.values()))[0] if form.errors else "Code invalide."
        return JsonResponse({'success': False, 'message': erreur})
 
 
@require_POST
@login_required
def ajax_retirer_code_promo(request):
    """Retire le code promo de la session."""
    request.session.pop('code_promo_id',   None)
    request.session.pop('code_promo_code', None)
    request.session.modified = True
    return JsonResponse({'success': True, 'message': "Code promo retiré."})
 
 
@require_GET
def ajax_promotions_actives_produit(request, produit_pk):
    """
    Retourne les promotions actives pour un produit donné.
    GET /promotions/ajax/produit/<pk>/
    Utilisé sur la page détail produit pour afficher le badge promo.
    """
    now = timezone.now()
    try:
        produit = Produit.objects.get(pk=produit_pk)
    except Produit.DoesNotExist:
        return JsonResponse({'promotions': []})
 
    promos = Promotion.objects.filter(
        statut='active',
        date_debut__lte=now,
        date_fin__gte=now,
    ).filter(
        Q(produits=produit) | Q(categories=produit.categorie)
    ).values('id', 'nom', 'type_promotion', 'valeur_reduction', 'code')
 
    return JsonResponse({'promotions': list(promos)})
 
 
@require_GET
def ajax_calculer_reduction(request):
    """
    Calcule la réduction pour un montant et un code promo donnés.
    GET /promotions/ajax/calculer/?code=PROMO20&montant=15000
    Identique à verifier_code_promo mais uniquement le calcul.
    """
    return ajax_verifier_code_promo(request)
 
 

 
 
 
 