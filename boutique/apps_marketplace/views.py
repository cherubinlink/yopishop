# ===========================================================================
# app_marketplace/views_boutiques.py
# Vues — App Marketplace : Boutiques, KYC, Employés, AvisVendeur, DemandeVendeur
#
# RÈGLES MÉTIER :
#   - Boutique.est_auto_creee : créée par signal, non supprimable
#   - Vendeur individuel : peut vendre sans boutique dédiée
#   - DemandeVendeur : déjà gérée en partie dans apps_core/views_utilisateurs.py
#     → Ici on ajoute la gestion admin (approuver/refuser) et le dashboard vendeur
#   - AvisVendeur : lié à une commande (une seule par vendeur/acheteur/commande)
# ===========================================================================

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.utils import timezone
from django.db.models import Q, Avg, Count, Prefetch, Sum
from django.core.paginator import Paginator
from django.db import transaction
from decimal import Decimal
import uuid as uuid_lib

from apps_marketplace.models import (
    Boutique, DocumentKYC, EmployeBoutique,
    AvisVendeur, DemandeVendeur,Panier,
    ArticlePanier, Commande, ArticleCommande, CodePromo,
    Paiement, PlanPaiement, TranchePaiement,
    Operateur, NumeroVersement,Retour,GroupeAchat, ParticipantGroupeAchat,
)
from apps_marketplace.forms import (
    BoutiqueCreerForm, BoutiqueEditerForm,DocumentKYCForm, 
    EmployeBoutiqueForm,AvisVendeurForm, ReponseVendeurForm,CodePromoForm
)
from apps_core.models import Produit, VarianteProduit, Ville, Quartier


# =============================================================================
# HELPERS
# =============================================================================

def _get_boutique_du_vendeur(user):
    """Retourne la boutique du vendeur ou None."""
    try:
        return user.boutique
    except Exception:
        return None


def _peut_gerer_boutique(user, boutique):
    """Vérifie si l'user peut modifier la boutique."""
    if user.is_staff or user.is_superuser:
        return True
    return boutique.vendeur == user


# =============================================================================
# LISTE PUBLIQUE DES BOUTIQUES
# =============================================================================

def boutiques_liste(request):
    """
    Page publique — liste de toutes les boutiques actives.
    Filtres : q (recherche), ville, plan, tri.
    """
    qs = Boutique.objects.filter(
        statut='active'
    ).select_related('vendeur').order_by('-est_vedette', '-note_moyenne')

    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(description__icontains=q) | Q(ville__icontains=q))

    ville = request.GET.get('ville', '')
    if ville:
        qs = qs.filter(ville__icontains=ville)

    tri = request.GET.get('tri', 'vedette')
    if tri == 'recent':
        qs = qs.order_by('-date_creation')
    elif tri == 'note':
        qs = qs.order_by('-note_moyenne', '-nombre_avis')
    elif tri == 'ventes':
        qs = qs.order_by('-nombre_ventes')

    paginator = Paginator(qs, 24)
    boutiques = paginator.get_page(request.GET.get('page', 1))

    context = {
        'boutiques':     boutiques,
        'q':             q,
        'ville':         ville,
        'tri':           tri,
        'nb_resultats':  paginator.count,
        'page_titre':    'Toutes les boutiques — YopiShop',
    }
    return render(request, 'apps_marketplace/boutiques/boutiques_liste.html', context)


def boutique_detail(request, slug):
    """Page publique d'une boutique — produits, avis, infos."""
    boutique = get_object_or_404(
        Boutique.objects.select_related('vendeur'),
        slug=slug,
    )

    if boutique.statut != 'active':
        if not (request.user.is_authenticated and (
            request.user == boutique.vendeur or request.user.is_staff
        )):
            messages.warning(request, "Cette boutique n'est pas disponible.")
            return redirect('apps_marketplace:boutiques_liste')

    # Produits actifs de la boutique
    from apps_core.models import Produit, ListeSouhaits
    produits = Produit.objects.filter(
        vendeur=boutique.vendeur, est_actif=True
    ).select_related('categorie').prefetch_related('images').order_by('-date_creation')

    paginator = Paginator(produits, 20)
    produits_page = paginator.get_page(request.GET.get('page', 1))

    # Avis
    avis_qs = AvisVendeur.objects.filter(
        vendeur=boutique.vendeur, est_approuve=True
    ).select_related('utilisateur').order_by('-date_creation')

    avis_stats = avis_qs.aggregate(
        moyenne=Avg('note'),
        total=Count('id'),
        moy_comm=Avg('note_communication'),
        moy_exp=Avg('note_expedition'),
        moy_emb=Avg('note_emballage'),
    )

    # Favoris
    favoris_ids = set()
    if request.user.is_authenticated:
        liste = ListeSouhaits.objects.filter(utilisateur=request.user).first()
        if liste:
            favoris_ids = set(liste.produits.values_list('id', flat=True))

    context = {
        'boutique':       boutique,
        'produits':       produits_page,
        'avis_liste':     avis_qs[:5],
        'avis_stats':     avis_stats,
        'favoris_ids':    favoris_ids,
        'nb_produits':    paginator.count,
        'page_titre':     f"{boutique.nom} — YopiShop",
    }
    return render(request, 'apps_marketplace/boutiques/boutique_detail.html', context)


# =============================================================================
# CRÉATION / ÉDITION BOUTIQUE
# =============================================================================

@login_required
def creer_boutique(request):
    """
    Création d'une boutique professionnelle.
    Seul un utilisateur avec type_vendeur != 'aucun' peut créer une boutique.
    Si l'user a déjà une boutique auto-créée, redirige vers l'édition.
    """
    user = request.user

    if not user.peut_vendre:
        messages.warning(request, "Vous devez être vendeur pour créer une boutique.")
        return redirect('apps_core:devenir_vendeur')

    # Boutique déjà existante (même auto-créée) → éditer
    boutique_existante = _get_boutique_du_vendeur(user)
    if boutique_existante:
        if boutique_existante.est_auto_creee:
            messages.info(
                request,
                "Vous avez une boutique auto-créée. Complétez-la ici pour la convertir en boutique pro."
            )
            return redirect('apps_marketplace:editer_boutique', slug=boutique_existante.slug)
        messages.info(request, "Vous avez déjà une boutique.")
        return redirect('apps_marketplace:dashboard_vendeur')

    if request.method == 'POST':
        form = BoutiqueCreerForm(request.POST, request.FILES)
        if form.is_valid():
            boutique = form.save(commit=False)
            boutique.vendeur = user
            boutique.slug    = form.cleaned_data['sous_domaine']
            boutique.statut  = 'en_attente'
            boutique.save()

            # Passer le vendeur en type 'pro' s'il était 'individuel'
            if user.type_vendeur == 'individuel':
                user.type_vendeur = 'pro'
                user.save(update_fields=['type_vendeur'])

            messages.success(
                request,
                f"Boutique « {boutique.nom} » créée ! "
                "Elle sera activée après vérification de notre équipe (24–48h)."
            )
            return redirect('apps_marketplace:dashboard_vendeur')
        else:
            messages.error(request, "Veuillez corriger les erreurs ci-dessous.")
    else:
        form = BoutiqueCreerForm()

    return render(request, 'apps_marketplace/boutiques/boutique_form.html', {
        'form':       form,
        'mode':       'creation',
        'page_titre': 'Créer ma boutique',
    })


@login_required
def editer_boutique(request, slug):
    """Édition d'une boutique par son propriétaire."""
    boutique = get_object_or_404(Boutique, slug=slug)

    if not _peut_gerer_boutique(request.user, boutique):
        messages.error(request, "Vous n'avez pas la permission de modifier cette boutique.")
        return redirect('apps_marketplace:boutique_detail', slug=slug)

    if request.method == 'POST':
        form = BoutiqueEditerForm(request.POST, request.FILES, instance=boutique)
        if form.is_valid():
            form.save()
            # Marquer comme boutique pro si elle était auto-créée
            if boutique.est_auto_creee:
                boutique.est_auto_creee = False
                boutique.type_boutique  = 'pro'
                boutique.save(update_fields=['est_auto_creee', 'type_boutique'])
            messages.success(request, "Boutique mise à jour avec succès.")
            return redirect('apps_marketplace:dashboard_vendeur')
        else:
            messages.error(request, "Veuillez corriger les erreurs ci-dessous.")
    else:
        form = BoutiqueEditerForm(instance=boutique)

    return render(request, 'apps_marketplace/boutiques/boutique_form.html', {
        'form':       form,
        'boutique':   boutique,
        'mode':       'edition',
        'page_titre': f"Modifier — {boutique.nom}",
    })


@login_required
@require_POST
def toggle_statut_boutique(request, slug):
    """Active ou suspend une boutique (admin seulement, AJAX)."""
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)

    boutique       = get_object_or_404(Boutique, slug=slug)
    nouveau_statut = request.POST.get('statut', '')

    statuts_valides = ['active', 'suspendue', 'en_attente', 'fermee']
    if nouveau_statut not in statuts_valides:
        return JsonResponse({'success': False, 'message': 'Statut invalide'}, status=400)

    boutique.statut = nouveau_statut
    boutique.save(update_fields=['statut'])

    return JsonResponse({
        'success': True,
        'statut':  boutique.statut,
        'label':   boutique.get_statut_display(),
    })


# =============================================================================
# DASHBOARD VENDEUR
# =============================================================================

@login_required
def dashboard_vendeur(request):
    """
    Tableau de bord principal du vendeur.
    Accessible aux vendeurs individuels (sans boutique) et pro.
    """
    user = request.user

    if not user.peut_vendre:
        messages.warning(request, "Vous devez être vendeur pour accéder à ce tableau de bord.")
        return redirect('apps_core:devenir_vendeur')

    boutique = _get_boutique_du_vendeur(user)

    # Statistiques produits
    from apps_core.models import Produit
    produits_stats = {
        'total':    Produit.objects.filter(vendeur=user).count(),
        'actifs':   Produit.objects.filter(vendeur=user, est_actif=True).count(),
        'rupture':  Produit.objects.filter(vendeur=user, quantite_stock=0).count(),
    }

    # Statistiques commandes
    commandes_stats = {'total': 0, 'en_cours': 0, 'montant_mois': 0}
    commandes_recentes = []
    try:
        from apps_marketplace.models import Commande
        from django.utils import timezone
        debut_mois = timezone.now().replace(day=1, hour=0, minute=0, second=0)

        commandes_qs = Commande.objects.filter(
            articles__produit__vendeur=user
        ).distinct()

        commandes_stats['total']      = commandes_qs.count()
        commandes_stats['en_cours']   = commandes_qs.filter(
            statut__in=['confirmee', 'en_traitement', 'expediee']
        ).count()
        commandes_stats['montant_mois'] = commandes_qs.filter(
            date_creation__gte=debut_mois, statut='livree'
        ).count()

        commandes_recentes = commandes_qs.order_by('-date_creation')[:5]
    except Exception:
        pass

    # Avis reçus
    avis_recents = AvisVendeur.objects.filter(
        vendeur=user, est_approuve=True
    ).select_related('utilisateur').order_by('-date_creation')[:5]

    avis_stats = AvisVendeur.objects.filter(
        vendeur=user, est_approuve=True
    ).aggregate(moyenne=Avg('note'), total=Count('id'))

    context = {
        'boutique':          boutique,
        'produits_stats':    produits_stats,
        'commandes_stats':   commandes_stats,
        'commandes_recentes': commandes_recentes,
        'avis_recents':      avis_recents,
        'avis_stats':        avis_stats,
        'page_titre':        'Mon tableau de bord vendeur',
    }
    return render(request, 'apps_marketplace/boutiques/dashboard_vendeur.html', context)


# =============================================================================
# KYC — Documents de vérification
# =============================================================================

@login_required
def kyc_documents(request):
    """Liste et upload des documents KYC de la boutique."""
    boutique = _get_boutique_du_vendeur(request.user)

    if not boutique:
        messages.warning(request, "Vous devez avoir une boutique pour soumettre des documents KYC.")
        return redirect('apps_marketplace:creer_boutique')

    documents = DocumentKYC.objects.filter(boutique=boutique).order_by('-date_envoi')

    if request.method == 'POST':
        form = DocumentKYCForm(request.POST, request.FILES)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.boutique = boutique
            doc.save()
            messages.success(request, "Document soumis. Notre équipe le vérifiera sous 48h.")
            return redirect('apps_marketplace:kyc_documents')
        else:
            messages.error(request, "Erreur lors de l'upload.")
    else:
        form = DocumentKYCForm()

    context = {
        'boutique':    boutique,
        'documents':   documents,
        'form':        form,
        'page_titre':  'Mes documents KYC',
    }
    return render(request, 'apps_marketplace/boutiques/kyc_documents.html', context)


@login_required
@require_POST
def supprimer_document_kyc(request, pk):
    """Supprime un document KYC non encore validé."""
    boutique = _get_boutique_du_vendeur(request.user)
    doc = get_object_or_404(DocumentKYC, pk=pk, boutique=boutique)

    if doc.statut == 'valide':
        messages.error(request, "Impossible de supprimer un document déjà validé.")
    else:
        doc.fichier.delete(save=False)
        doc.delete()
        messages.success(request, "Document supprimé.")

    return redirect('apps_marketplace:kyc_documents')


# =============================================================================
# ADMIN KYC — Validation des documents
# =============================================================================

@login_required
def admin_kyc_liste(request):
    """Liste admin des documents KYC à traiter."""
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')

    statut = request.GET.get('statut', 'en_attente')
    docs = DocumentKYC.objects.filter(
        statut=statut
    ).select_related('boutique', 'boutique__vendeur').order_by('-date_envoi')

    paginator = Paginator(docs, 20)
    documents = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'apps_marketplace/boutiques/kyc_liste.html', {
        'documents':  documents,
        'statut':     statut,
        'page_titre': 'Gestion KYC',
    })


@login_required
@require_POST
def admin_kyc_valider(request, pk):
    """Valide ou refuse un document KYC (admin)."""
    if not request.user.is_staff:
        return JsonResponse({'success': False}, status=403)

    doc    = get_object_or_404(DocumentKYC, pk=pk)
    action = request.POST.get('action', '')

    if action == 'valider':
        doc.statut             = 'valide'
        doc.date_verification  = timezone.now()
        doc.commentaire_admin  = request.POST.get('commentaire', '')
        doc.save()

        # Vérifier si tous les docs requis sont validés → mettre à jour le KYC boutique
        boutique = doc.boutique
        if not DocumentKYC.objects.filter(boutique=boutique, statut='en_attente').exists():
            boutique.kyc_statut    = 'valide'
            boutique.est_verifiee  = True
            boutique.kyc_valide_par = request.user
            boutique.kyc_date      = timezone.now()
            boutique.save(update_fields=['kyc_statut', 'est_verifiee', 'kyc_valide_par', 'kyc_date'])

        msg = f"Document KYC validé pour {doc.boutique.nom}."
        messages.success(request, msg)
        return JsonResponse({'success': True, 'message': msg})

    elif action == 'refuser':
        doc.statut            = 'refuse'
        doc.commentaire_admin = request.POST.get('commentaire', 'Refusé par l\'admin.')
        doc.date_verification = timezone.now()
        doc.save()

        doc.boutique.kyc_statut = 'refuse'
        doc.boutique.save(update_fields=['kyc_statut'])

        msg = f"Document KYC refusé pour {doc.boutique.nom}."
        messages.warning(request, msg)
        return JsonResponse({'success': True, 'message': msg})

    return JsonResponse({'success': False, 'message': 'Action inconnue'}, status=400)


# =============================================================================
# EMPLOYÉS BOUTIQUE
# =============================================================================

@login_required
def employes_boutique(request):
    """Gestion des employés de ma boutique."""
    boutique = _get_boutique_du_vendeur(request.user)

    if not boutique or boutique.type_boutique not in ('pro', 'yopishop'):
        messages.warning(request, "Fonctionnalité réservée aux boutiques professionnelles.")
        return redirect('apps_marketplace:dashboard_vendeur')

    employes = EmployeBoutique.objects.filter(
        boutique=boutique
    ).select_related('utilisateur').order_by('-date_embauche')

    if request.method == 'POST':
        form = EmployeBoutiqueForm(request.POST)
        if form.is_valid():
            employe_user = form.employe_user
            # Vérifier doublon
            if EmployeBoutique.objects.filter(boutique=boutique, utilisateur=employe_user).exists():
                messages.warning(request, "Cet utilisateur est déjà employé dans votre boutique.")
            else:
                employe = form.save(commit=False)
                employe.boutique    = boutique
                employe.utilisateur = employe_user
                employe.save()
                messages.success(request, f"{employe_user.username} ajouté comme {employe.get_role_display()}.")
            return redirect('apps_marketplace:employes_boutique')
        else:
            messages.error(request, "Erreur dans le formulaire.")
    else:
        form = EmployeBoutiqueForm()

    return render(request, 'apps_marketplace/boutiques/employes_boutique.html', {
        'boutique':  boutique,
        'employes':  employes,
        'form':      form,
        'page_titre': 'Mon équipe',
    })


@login_required
@require_POST
def toggle_employe(request, pk):
    """Active/désactive un employé (AJAX)."""
    boutique = _get_boutique_du_vendeur(request.user)
    employe  = get_object_or_404(EmployeBoutique, pk=pk, boutique=boutique)

    employe.est_actif = not employe.est_actif
    employe.save(update_fields=['est_actif'])

    return JsonResponse({'success': True, 'est_actif': employe.est_actif})


@login_required
@require_POST
def supprimer_employe(request, pk):
    """Retire un employé de la boutique."""
    boutique = _get_boutique_du_vendeur(request.user)
    employe  = get_object_or_404(EmployeBoutique, pk=pk, boutique=boutique)
    nom      = employe.utilisateur.username
    employe.delete()
    messages.success(request, f"{nom} a été retiré de votre équipe.")
    return redirect('apps_marketplace:employes_boutique')


# =============================================================================
# AVIS VENDEUR
# =============================================================================

@login_required
@require_POST
def ajouter_avis_vendeur(request, commande_pk):
    """Ajoute un avis sur le vendeur après une commande."""
    try:
        from apps_marketplace.models import Commande
        commande = get_object_or_404(Commande, pk=commande_pk, utilisateur=request.user)
    except Exception:
        messages.error(request, "Commande introuvable.")
        return redirect('apps_core:tableau_de_bord')

    # Vérifier pas déjà noté
    vendeur = commande.articles.first().produit.vendeur if commande.articles.exists() else None
    if not vendeur:
        messages.error(request, "Vendeur introuvable.")
        return redirect('apps_core:tableau_de_bord')

    if AvisVendeur.objects.filter(vendeur=vendeur, utilisateur=request.user, commande=commande).exists():
        messages.warning(request, "Vous avez déjà laissé un avis pour cette commande.")
        return redirect('apps_core:tableau_de_bord')

    form = AvisVendeurForm(request.POST)
    if form.is_valid():
        avis = form.save(commit=False)
        avis.vendeur     = vendeur
        avis.utilisateur = request.user
        avis.commande    = commande
        if vendeur.a_boutique:
            avis.boutique = vendeur.boutique
        avis.save()

        # Recalculer les stats
        if vendeur.a_boutique:
            vendeur.boutique.recalculer_stats()

        messages.success(request, "Merci pour votre avis !")
    else:
        messages.error(request, "Erreur dans le formulaire d'avis.")

    return redirect('apps_core:tableau_de_bord')


@login_required
def mes_avis_recus(request):
    """Liste des avis reçus par le vendeur connecté."""
    if not request.user.peut_vendre:
        return redirect('apps_core:tableau_de_bord')

    avis_qs = AvisVendeur.objects.filter(
        vendeur=request.user
    ).select_related('utilisateur', 'commande').order_by('-date_creation')

    statut = request.GET.get('statut', '')
    if statut == 'non_repondu':
        avis_qs = avis_qs.filter(reponse_vendeur='')
    elif statut == 'repondu':
        avis_qs = avis_qs.exclude(reponse_vendeur='')

    paginator = Paginator(avis_qs, 15)
    avis      = paginator.get_page(request.GET.get('page', 1))

    stats = AvisVendeur.objects.filter(
        vendeur=request.user, est_approuve=True
    ).aggregate(
        moyenne=Avg('note'), total=Count('id'),
        moy_comm=Avg('note_communication'),
        moy_exp=Avg('note_expedition'),
        moy_emb=Avg('note_emballage'),
    )

    return render(request, 'apps_marketplace/boutiques/mes_avis.html', {
        'avis':       avis,
        'stats':      stats,
        'statut':     statut,
        'page_titre': 'Mes avis reçus',
    })


@login_required
@require_POST
def repondre_avis_vendeur(request, pk):
    """Le vendeur répond à un avis (AJAX ou redirect)."""
    avis = get_object_or_404(AvisVendeur, pk=pk, vendeur=request.user)
    form = ReponseVendeurForm(request.POST, instance=avis)

    if form.is_valid():
        form.save()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'reponse': avis.reponse_vendeur})
        messages.success(request, "Réponse publiée.")
    else:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False})
        messages.error(request, "Erreur.")

    return redirect('apps_marketplace:mes_avis_recus')


# =============================================================================
# DEMANDES VENDEUR — Gestion admin
# =============================================================================

@login_required
def admin_demandes_vendeur(request):
    """Liste admin des demandes vendeur."""
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')

    statut = request.GET.get('statut', 'en_attente')
    qs = DemandeVendeur.objects.filter(
        statut=statut
    ).select_related('utilisateur').order_by('-date_demande')

    paginator = Paginator(qs, 20)
    demandes  = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'apps_marketplace/boutiques/admin_demandes_vendeur.html', {
        'demandes':  demandes,
        'statut':    statut,
        'page_titre': 'Demandes vendeur',
    })


@login_required
def admin_demande_detail(request, pk):
    """Détail d'une demande vendeur + actions (admin)."""
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')

    demande = get_object_or_404(DemandeVendeur.objects.select_related('utilisateur'), pk=pk)

    if request.method == 'POST':
        action     = request.POST.get('action', '')
        commentaire = request.POST.get('commentaire', '')

        if action == 'approuver':
            demande.approuver(request.user)
            messages.success(request, f"Candidature de {demande.utilisateur.username} approuvée.")
        elif action == 'refuser':
            if not commentaire:
                messages.error(request, "Un motif de refus est requis.")
                return redirect('apps_marketplace:admin_demande_detail', pk=pk)
            demande.refuser(request.user, commentaire)
            messages.warning(request, f"Candidature de {demande.utilisateur.username} refusée.")
        elif action == 'en_cours':
            demande.statut          = 'en_cours'
            demande.date_traitement = timezone.now()
            demande.traite_par      = request.user
            demande.save()
            messages.info(request, "Demande marquée en cours d'examen.")

        return redirect('apps_marketplace:admin_demandes_vendeur')

    return render(request, 'apps_marketplace/boutiques/admin_demande_detail.html', {
        'demande':    demande,
        'page_titre': f"Demande — {demande.utilisateur.username}",
    })


# =============================================================================
# AJAX
# =============================================================================

@require_GET
def ajax_verifier_sous_domaine_boutique(request):
    """
    Vérifie si un sous-domaine boutique est disponible.
    GET /boutiques/ajax/sous-domaine/?q=mon-shop
    """
    import re
    val = request.GET.get('q', '').lower().strip()

    if not re.match(r'^[a-z0-9-]{3,50}$', val):
        return JsonResponse({'disponible': False, 'message': 'Format invalide'})

    reserved = ['www', 'api', 'admin', 'app', 'mail', 'ftp', 'yopishop']
    if val in reserved:
        return JsonResponse({'disponible': False, 'message': 'Sous-domaine réservé'})

    existe = Boutique.objects.filter(sous_domaine=val).exists()
    if request.user.is_authenticated:
        existe = Boutique.objects.filter(sous_domaine=val).exclude(
            vendeur=request.user
        ).exists()

    return JsonResponse({
        'disponible':  not existe,
        'message':     f'{val}.yopishop.com disponible ✓' if not existe else 'Déjà pris',
        'url_preview': f'https://{val}.yopishop.com' if not existe else '',
    })


@login_required
@require_GET
def ajax_stats_vendeur(request):
    """Retourne les stats rapides du vendeur (JSON pour dashboard)."""
    user = request.user
    if not user.peut_vendre:
        return JsonResponse({'error': 'Non autorisé'}, status=403)

    from apps_core.models import Produit
    data = {
        'nb_produits':  Produit.objects.filter(vendeur=user, est_actif=True).count(),
        'note_moyenne': float(
            AvisVendeur.objects.filter(vendeur=user, est_approuve=True)
            .aggregate(m=Avg('note'))['m'] or 0
        ),
        'nb_avis': AvisVendeur.objects.filter(vendeur=user, est_approuve=True).count(),
        'solde_wallet': float(user.solde_wallet),
    }
    return JsonResponse(data)



# =============================================================================
# HELPERS
# =============================================================================
 
def _get_or_create_panier(request):
    """
    Retourne le panier de l'utilisateur connecté, ou un panier anonyme
    basé sur la clé de session.
    """
    if request.user.is_authenticated:
        panier, _ = Panier.objects.get_or_create(utilisateur=request.user)
        return panier
 
    if not request.session.session_key:
        request.session.create()
    cle = request.session.session_key
 
    panier, _ = Panier.objects.get_or_create(
        utilisateur=None, cle_session=cle
    )
    return panier
 
 
def _fusionner_paniers(request, user):
    """
    À la connexion : fusionne le panier anonyme (session) avec le panier
    de l'utilisateur nouvellement connecté.
    """
    cle = request.session.session_key
    if not cle:
        return
    try:
        panier_anonyme = Panier.objects.get(utilisateur=None, cle_session=cle)
    except Panier.DoesNotExist:
        return
 
    panier_user, _ = Panier.objects.get_or_create(utilisateur=user)
 
    for article in panier_anonyme.articles.all():
        existant = ArticlePanier.objects.filter(
            panier=panier_user, produit=article.produit, variante=article.variante
        ).first()
        if existant:
            existant.quantite += article.quantite
            existant.save(update_fields=['quantite'])
        else:
            article.panier = panier_user
            article.save(update_fields=['panier'])
 
    panier_anonyme.delete()
 
 
def _nb_articles_panier(panier):
    return panier.articles.aggregate(total=Sum('quantite'))['total'] or 0



# =============================================================================
# PANIER
# =============================================================================
 
def voir_panier(request):
    panier   = _get_or_create_panier(request)
    articles = panier.articles.select_related(
        'produit', 'variante', 'produit__categorie', 'produit__vendeur'
    ).prefetch_related('produit__images').order_by('-date_creation')

    sous_total = panier.total()
    nb         = _nb_articles_panier(panier)

    # ← Maintenir la session à jour
    request.session['nb_panier'] = nb
    request.session.modified = True

    context = {
        'panier':      panier,
        'articles':    articles,
        'sous_total':  sous_total,
        'nb_articles': nb,
        'page_titre':  'Mon panier',
    }
    return render(request, 'apps_marketplace/panier/panier.html', context)
 
 
@require_POST
def ajouter_au_panier(request, produit_id):
    produit = get_object_or_404(Produit, pk=produit_id, est_actif=True)

    if not produit.est_en_stock():
        return JsonResponse(
            {'success': False, 'message': 'Produit en rupture de stock.'},
            status=400
        )

    quantite = int(request.POST.get('quantite', 1))
    if quantite < 1:
        quantite = 1
    if quantite < produit.quantite_min_commande:
        quantite = produit.quantite_min_commande

    variante_id = request.POST.get('variante_id')
    variante = None
    if variante_id:
        variante = VarianteProduit.objects.filter(
            pk=variante_id, produit=produit, est_active=True
        ).first()

    panier = _get_or_create_panier(request)

    
    prix_unitaire = produit.prix_promotionnel
    if variante:
        prix_unitaire += variante.prix_supplementaire

    article, created = ArticlePanier.objects.get_or_create(
        panier=panier, produit=produit, variante=variante,
        defaults={
            'quantite':   quantite,
            'prix':       prix_unitaire,
            'prix_type':  'normal',
        },
    )
    if not created:
        article.quantite += quantite
        article.prix = prix_unitaire
        article.save(update_fields=['quantite', 'prix'])

    nb = _nb_articles_panier(panier)

    # ← Synchroniser le badge navbar via la session
    request.session['nb_panier'] = nb
    request.session.modified = True

    return JsonResponse({
        'success':     True,
        'message':     f"« {produit.titre} » ajouté au panier.",
        'nb_articles': nb,
        'sous_total':  float(panier.total()),
    })


@require_POST
def modifier_quantite_panier(request, article_id):
    """Modifie la quantité d'un article du panier (AJAX)."""
    panier = _get_or_create_panier(request)
    article = get_object_or_404(ArticlePanier, pk=article_id, panier=panier)
 
    action = request.POST.get('action', '')
    if action == 'increment':
        article.quantite += 1
    elif action == 'decrement':
        article.quantite = max(1, article.quantite - 1)
    else:
        try:
            nouvelle_qte = int(request.POST.get('quantite', article.quantite))
            article.quantite = max(1, nouvelle_qte)
        except (TypeError, ValueError):
            pass
 
    # Limiter au stock disponible
    stock = article.produit.quantite_fulfillment if article.produit.en_fulfillment else article.produit.quantite_stock
    if article.quantite > stock:
        article.quantite = stock
        message = "Quantité limitée au stock disponible."
    else:
        message = ""
 
    article.save(update_fields=['quantite'])
 
    return JsonResponse({
        'success':     True,
        'quantite':    article.quantite,
        'sous_total':  float(article.sous_total()),
        'panier_total': float(panier.total()),
        'nb_articles': _nb_articles_panier(panier),
        'message':     message,
    })
 

 
@require_POST
def retirer_du_panier(request, article_id):
    """Retire un article du panier (AJAX)."""
    panier = _get_or_create_panier(request)
    article = get_object_or_404(ArticlePanier, pk=article_id, panier=panier)
    article.delete()
 
    return JsonResponse({
        'success':      True,
        'nb_articles':  _nb_articles_panier(panier),
        'panier_total': float(panier.total()),
    })
 
 
@require_POST
def vider_panier(request):
    """Vide complètement le panier."""
    panier = _get_or_create_panier(request)
    panier.articles.all().delete()
 
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})
 
    messages.success(request, "Votre panier a été vidé.")
    return redirect('apps_marketplace:voir_panier')
 
 
@require_GET
def ajax_compteur_panier(request):
    """Retourne le nombre d'articles dans le panier (badge navbar)."""
    panier = _get_or_create_panier(request)
    return JsonResponse({'nb_articles': _nb_articles_panier(panier)})
 


@login_required
def passer_commande(request):
    panier   = _get_or_create_panier(request)
    articles = panier.articles.select_related(
        'produit', 'produit__vendeur', 'produit__vendeur__boutique', 'variante'
    )

    if not articles.exists():
        messages.warning(request, "Votre panier est vide.")
        return redirect('apps_marketplace:voir_panier')

    villes    = Ville.objects.filter(est_actif=True).select_related('region')
    quartiers = Quartier.objects.select_related('ville').order_by('ville__nom', 'nom')

    def _est_produit_yopishop(article):
        p = article.produit
        vendeur = p.vendeur
        if vendeur.type_vendeur == 'yopishop':
            return True
        if p.est_produit_yopishop:
            return True
        if vendeur.a_boutique and vendeur.boutique.type_boutique == 'yopishop':
            return True
        return False

    est_bnpl_eligible = all(_est_produit_yopishop(art) for art in articles)

    sous_total  = panier.total()
    montant_3x  = (sous_total / 3).quantize(Decimal('1'))
    montant_6x  = (sous_total / 6).quantize(Decimal('1'))
    montant_12x = (sous_total / 12).quantize(Decimal('1'))

    if request.method == 'POST':
        adresse_facturation = request.POST.get('adresse_facturation', '').strip()
        adresse_livraison   = request.POST.get('adresse_livraison', '').strip()
        ville_id            = request.POST.get('ville_livraison')
        quartier_id         = request.POST.get('quartier_livraison')
        source               = request.POST.get('source', 'web')
        instructions         = request.POST.get('instructions_livraison', '').strip()
        notes                = request.POST.get('notes', '').strip()
        mode_paiement        = request.POST.get('mode_paiement', 'comptant')
        nb_tranches_choisi   = request.POST.get('nb_tranches', '3')  # ← NOUVEAU

        if not adresse_facturation or not adresse_livraison:
            messages.error(request, "Veuillez renseigner les adresses.")
            return redirect('apps_marketplace:passer_commande')

        if mode_paiement == 'bnpl' and not est_bnpl_eligible:
            messages.error(request, "Le paiement fractionné est réservé aux produits YopiShop.")
            return redirect('apps_marketplace:passer_commande')

        # ── Valider le nombre de tranches choisi ──
        try:
            nb_tranches_choisi = int(nb_tranches_choisi)
            if nb_tranches_choisi not in (3, 6, 12):
                nb_tranches_choisi = 3
        except (ValueError, TypeError):
            nb_tranches_choisi = 3

        ville    = Ville.objects.filter(pk=ville_id).first()    if ville_id    else None
        quartier = Quartier.objects.filter(pk=quartier_id).first() if quartier_id else None

        with transaction.atomic():
            frais_livraison = Decimal('0')
            if ville:
                frais_set = set()
                for art in articles:
                    frais = art.produit.calculer_frais_livraison(ville, quartier)
                    if frais is not None:
                        frais_set.add(frais)
                frais_livraison = max(frais_set) if frais_set else Decimal('0')
        

            vendeurs = {a.produit.vendeur for a in articles}
            boutique_principale = None
            if len(vendeurs) == 1:
                v = next(iter(vendeurs))
                if v.a_boutique:
                    boutique_principale = v.boutique

            est_paiement_fractionne = (mode_paiement == 'bnpl')

            # ==========================================================
            # APPLICATION DU CODE PROMO
            # ==========================================================
            code_promo = None
            montant_reduction = Decimal("0")

            code_promo_id = request.session.get("code_promo_id")

            if code_promo_id:

                code_promo = CodePromo.objects.filter(
                    pk=code_promo_id
                ).first()

                if code_promo:

                    ok, _ = _verifier_eligibilite(
                        code_promo,
                        request.user,
                        sous_total
                    )

                    if ok:

                        if code_promo.type_reduction == "livraison_gratuite":
                            frais_livraison = Decimal("0")

                        else:
                            montant_reduction = code_promo.calculer_reduction(
                                sous_total
                            )

                    else:
                        code_promo = None

            commande = Commande.objects.create(
                utilisateur=request.user,
                boutique=boutique_principale,
                source=source,
                adresse_facturation=adresse_facturation,
                adresse_livraison=adresse_livraison,
                ville_livraison=ville,
                quartier_livraison=quartier,
                sous_total=sous_total,
                frais_livraison=frais_livraison,
                montant_total=sous_total + frais_livraison,
                notes=notes,
                instructions_livraison=instructions,
                est_paiement_fractionne=est_paiement_fractionne,
                nombre_tranches=nb_tranches_choisi if est_paiement_fractionne else 1,
            )

            for art in articles:
                ArticleCommande.objects.create(
                    commande=commande,
                    produit=art.produit,
                    variante=art.variante,
                    quantite=art.quantite,
                    prix_unitaire=art.prix,
                )
                produit = art.produit
                if produit.en_fulfillment:
                    produit.quantite_fulfillment = max(0, produit.quantite_fulfillment - art.quantite)
                    produit.save(update_fields=['quantite_fulfillment'])
                else:
                    produit.quantite_stock = max(0, produit.quantite_stock - art.quantite)
                    produit.save(update_fields=['quantite_stock'])
                Produit.objects.filter(pk=produit.pk).update(
                    nb_ventes=produit.nb_ventes + art.quantite
                )

            commande.calculer_total()

            # ==========================================================
            # Enregistrer l'utilisation du code promo
            # ==========================================================
            if code_promo:

                code_promo.nombre_utilisations += 1

                code_promo.save(update_fields=["nombre_utilisations"])

                request.session.pop('code_promo_id', None)
                request.session.pop('code_promo_code', None)
                request.session.pop('livraison_gratuite', None)
                
            # ── NOUVEAU : créer immédiatement le PlanPaiement si BNPL ──
            plan = None
            if est_paiement_fractionne:
                montant_total_plan  = commande.montant_total  # 0% d'intérêt par défaut
                montant_par_tranche = (montant_total_plan / nb_tranches_choisi).quantize(Decimal('1'))

                plan = PlanPaiement.objects.create(
                    commande=commande,
                    montant_total=montant_total_plan,
                    nombre_tranches=nb_tranches_choisi,
                    montant_par_tranche=montant_par_tranche,
                    taux_interet=Decimal('0'),
                )

                from dateutil.relativedelta import relativedelta
                import datetime
                date_base = commande.date_creation.date()
                for i in range(1, nb_tranches_choisi + 1):
                    date_echeance = datetime.datetime.combine(
                        date_base + relativedelta(months=i), datetime.time(23, 59)
                    )
                    TranchePaiement.objects.create(
                        plan_paiement=plan,
                        numero_tranche=i,
                        montant=montant_par_tranche,
                        date_echeance=date_echeance,
                    )

            panier.articles.all().delete()

        request.session['nb_panier'] = 0
        request.session.modified = True

        messages.success(request, f"Commande {commande.numero_commande} créée !")

        if mode_paiement == 'bnpl':
            messages.info(
                request,
                f"Votre plan de paiement {nb_tranches_choisi}× est prêt. "
                "Vous pouvez payer votre première tranche dès maintenant."
            )
            return redirect('apps_marketplace:mon_plan_paiement', commande_pk=commande.pk)

        return redirect('apps_marketplace:commande_confirmation', pk=commande.pk)

    context = {
        'panier':            panier,
        'articles':          articles,
        'sous_total':        sous_total,
        'montant_3x':        montant_3x,
        'montant_6x':        montant_6x,
        'montant_12x':       montant_12x,
        'villes':            villes,
        'quartiers':         quartiers,
        'est_bnpl_eligible': est_bnpl_eligible,
        'page_titre':        'Finaliser ma commande',
    }
    return render(request, 'apps_marketplace/commandes/checkout.html', context)
 

@login_required
def commande_confirmation(request, pk):
    """Page de confirmation après création de commande."""
    commande = get_object_or_404(
        Commande.objects.prefetch_related('articles__produit'),
        pk=pk, utilisateur=request.user
    )
    return render(request, 'apps_marketplace/commandes/confirmation.html', {
        'commande':   commande,
        'page_titre': f"Commande {commande.numero_commande} confirmée",
    })



# =============================================================================
# MES COMMANDES (acheteur)
# =============================================================================
 
@login_required
def mes_commandes(request):
    """Liste des commandes de l'utilisateur connecté."""
    qs = Commande.objects.filter(
        utilisateur=request.user
    ).prefetch_related('articles__produit').order_by('-date_creation')
 
    statut = request.GET.get('statut', '')
    if statut:
        qs = qs.filter(statut=statut)
 
    paginator = Paginator(qs, 15)
    commandes = paginator.get_page(request.GET.get('page', 1))
 
    return render(request, 'apps_marketplace/commandes/mes_commandes.html', {
        'commandes':  commandes,
        'statut':     statut,
        'statuts':    Commande.STATUT_CHOICES,
        'page_titre': 'Mes commandes',
    })
 
 
@login_required
def commande_detail(request, pk):
    """Détail d'une commande pour l'acheteur."""
    commande = get_object_or_404(
        Commande.objects.prefetch_related(
            'articles__produit', 'articles__produit__vendeur', 'articles__variante'
        ).select_related('ville_livraison', 'quartier_livraison', 'boutique'),
        pk=pk,
    )
 
    # Vérifier les droits : acheteur, vendeur d'un article, ou admin
    est_acheteur = commande.utilisateur == request.user
    est_vendeur_concerne = commande.articles.filter(produit__vendeur=request.user).exists()
    if not (est_acheteur or est_vendeur_concerne or request.user.is_staff):
        messages.error(request, "Vous n'avez pas accès à cette commande.")
        return redirect('apps_core:tableau_de_bord')
 
    return render(request, 'apps_marketplace/commandes/commande_detail.html', {
        'commande':    commande,
        'est_acheteur': est_acheteur,
        'page_titre':  f"Commande {commande.numero_commande}",
    })
 
 
@login_required
@require_POST
def annuler_commande(request, pk):
    """L'acheteur annule sa commande (si pas encore expédiée)."""
    commande = get_object_or_404(Commande, pk=pk, utilisateur=request.user)
 
    if commande.statut in ('expediee', 'livree'):
        messages.error(request, "Impossible d'annuler une commande déjà expédiée.")
        return redirect('apps_marketplace:commande_detail', pk=pk)
 
    with transaction.atomic():
        # Remettre le stock
        for art in commande.articles.select_related('produit'):
            produit = art.produit
            if produit.en_fulfillment:
                produit.quantite_fulfillment += art.quantite
                produit.save(update_fields=['quantite_fulfillment'])
            else:
                produit.quantite_stock += art.quantite
                produit.save(update_fields=['quantite_stock'])
 
        commande.statut = 'annulee'
        commande.save(update_fields=['statut'])
 
    messages.success(request, f"Commande {commande.numero_commande} annulée.")
    return redirect('apps_marketplace:mes_commandes')
 

 
# =============================================================================
# COMMANDES REÇUES (vendeur)
# =============================================================================
 
@login_required
def commandes_recues(request):
    """Liste des commandes contenant des produits du vendeur connecté."""
    if not request.user.peut_vendre:
        messages.warning(request, "Réservé aux vendeurs.")
        return redirect('apps_core:tableau_de_bord')
 
    qs = Commande.objects.filter(
        articles__produit__vendeur=request.user
    ).distinct().prefetch_related('articles__produit').order_by('-date_creation')
 
    statut = request.GET.get('statut', '')
    if statut:
        qs = qs.filter(statut=statut)
 
    paginator = Paginator(qs, 20)
    commandes = paginator.get_page(request.GET.get('page', 1))
 
    stats = {
        'total':     Commande.objects.filter(articles__produit__vendeur=request.user).distinct().count(),
        'en_attente': qs.filter(statut='en_attente').count(),
        'en_cours':  qs.filter(statut__in=['confirmee', 'en_traitement', 'expediee']).count(),
        'livrees':   qs.filter(statut='livree').count(),
    }
 
    return render(request, 'apps_marketplace/commandes/commandes_recues.html', {
        'commandes':  commandes,
        'stats':      stats,
        'statut':     statut,
        'statuts':    Commande.STATUT_CHOICES,
        'page_titre': 'Commandes reçues',
    })
 
 
@login_required
@require_POST
def changer_statut_commande(request, pk):
    commande = get_object_or_404(Commande, pk=pk)

    if not commande.articles.filter(
        produit__vendeur=request.user
    ).exists() and not request.user.is_staff:
        return JsonResponse(
            {'success': False, 'message': 'Non autorisé'}, status=403
        )

    nouveau_statut = request.POST.get('statut', '')
    statuts_valides = [c[0] for c in Commande.STATUT_CHOICES]
    if nouveau_statut not in statuts_valides:
        return JsonResponse(
            {'success': False, 'message': 'Statut invalide'}, status=400
        )

    # Vérifier qu'on ne crédite pas deux fois (déjà livrée)
    if nouveau_statut == 'livree' and commande.statut == 'livree':
        return JsonResponse(
            {'success': False, 'message': 'Commande déjà livrée.'}, status=400
        )

    commande.statut = nouveau_statut

    if nouveau_statut == 'expediee' and not commande.date_expedition:
        commande.date_expedition = timezone.now()
    elif nouveau_statut == 'livree' and not commande.date_livraison:
        commande.date_livraison = timezone.now()

    # .save() déclenche pre_save → post_save → _crediter_vendeurs_apres_livraison
    commande.save()

    return JsonResponse({
        'success': True,
        'statut':  commande.statut,
        'label':   commande.get_statut_display(),
    })

# =============================================================================
# ADMIN — Vue globale des commandes
# =============================================================================
 
@login_required
def admin_commandes_liste(request):
    """Liste admin de toutes les commandes de la plateforme."""
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')
 
    qs = Commande.objects.select_related('utilisateur', 'boutique').order_by('-date_creation')
 
    statut = request.GET.get('statut', '')
    if statut:
        qs = qs.filter(statut=statut)
 
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(Q(numero_commande__icontains=q) | Q(utilisateur__username__icontains=q))
 
    paginator = Paginator(qs, 30)
    commandes = paginator.get_page(request.GET.get('page', 1))
 
    stats = {
        'total':       Commande.objects.count(),
        'ca_total':    Commande.objects.filter(statut='livree').aggregate(s=Sum('montant_total'))['s'] or 0,
        'en_attente':  Commande.objects.filter(statut='en_attente').count(),
        'commission_totale': ArticleCommande.objects.aggregate(s=Sum('commission_boutique'))['s'] or 0,
    }
 
    return render(request, 'apps_marketplace/admin_commandes_liste.html', {
        'commandes':  commandes,
        'stats':      stats,
        'statut':     statut,
        'q':          q,
        'statuts':    Commande.STATUT_CHOICES,
        'page_titre': 'Toutes les commandes',
    })



 
# =============================================================================
# HELPERS
# =============================================================================
 
def _peut_gerer_code(user, code):
    """True si l'user peut modifier/supprimer ce code."""
    return user.is_staff or user.is_superuser or code.createur == user
 
 
def _verifier_eligibilite(code, user, montant, panier=None):
    """
    Retourne (True, None) si le code est applicable,
    (False, 'message d'erreur') sinon.
    """
    now = timezone.now()
 
    if not code.est_valide():
        return False, "Ce code promo est invalide, expiré ou inactif."
 
    if montant < code.montant_min_commande:
        return False, f"Montant minimum requis : {code.montant_min_commande:,.0f} FCFA"
 
    # Limite d'utilisation globale
    if code.limite_utilisation_globale is not None:
        if code.nombre_utilisations >= code.limite_utilisation_globale:
            return False, "Ce code promo a atteint sa limite d'utilisation."
 
    # Limite par utilisateur
    if user.is_authenticated and code.limite_par_utilisateur:
        nb_user = Commande.objects.filter(code_promo=code, utilisateur=user).count()
        if nb_user >= code.limite_par_utilisateur:
            return False, f"Vous avez déjà utilisé ce code {nb_user} fois."
 
    # Ciblage utilisateurs spécifiques
    if code.type_cible == 'prive':
        if not user.is_authenticated or not code.utilisateurs_cibles.filter(pk=user.pk).exists():
            return False, "Ce code est réservé à des utilisateurs spécifiques."
 
    if code.type_cible == 'premier_achat':
        if not user.is_authenticated:
            return False, "Connectez-vous pour utiliser ce code."
        if Commande.objects.filter(utilisateur=user).exists():
            return False, "Ce code est réservé au premier achat uniquement."
 
    if code.type_cible == 'vip':
        if not user.is_authenticated or not getattr(user, 'est_vip', False):
            return False, "Ce code est réservé aux clients VIP."
 
    return True, None
 
 
# =============================================================================
# AJAX — Usage côté panier/checkout
# =============================================================================
 
@require_GET
def ajax_verifier_code_promo(request):
    """
    Vérifie un code promo et retourne la réduction calculée.
    GET /codes-promo/ajax/verifier/?code=YOPI20&montant=15000
    """
    code_str = request.GET.get('code', '').strip().upper()
    montant  = request.GET.get('montant', '0')
 
    if not code_str:
        return JsonResponse({'valide': False, 'message': 'Code vide.'})
 
    try:
        montant = Decimal(str(montant))
    except Exception:
        montant = Decimal('0')
 
    try:
        code = CodePromo.objects.get(code=code_str)
    except CodePromo.DoesNotExist:
        return JsonResponse({'valide': False, 'message': 'Code introuvable.'})
 
    ok, erreur = _verifier_eligibilite(code, request.user, montant)
    if not ok:
        return JsonResponse({'valide': False, 'message': erreur})
 
    if code.type_reduction == 'livraison_gratuite':
        return JsonResponse({
            'valide':           True,
            'code':             code.code,
            'nom':              code.nom,
            'type_reduction':   code.type_reduction,
            'reduction':        0,
            'livraison_gratuite': True,
            'message':          '🚚 Livraison gratuite appliquée !',
        })
 
    reduction = code.calculer_reduction(montant)
    return JsonResponse({
        'valide':             True,
        'code':               code.code,
        'nom':                code.nom,
        'type_reduction':     code.type_reduction,
        'valeur_reduction':   float(code.valeur_reduction),
        'reduction':          float(reduction),
        'reduction_fmt':      f"{reduction:,.0f} FCFA",
        'nouveau_total':      float(montant - reduction),
        'livraison_gratuite': False,
        'message':            f"Code appliqué — {reduction:,.0f} FCFA de réduction",
    })
 
 
@require_POST
def ajax_appliquer_code(request):
    """
    Applique un code promo à la session de l'utilisateur.
    POST /codes-promo/ajax/appliquer/  body: code=YOPI20&montant=15000
    """
    code_str = request.POST.get('code', '').strip().upper()
    montant  = Decimal(str(request.POST.get('montant', '0')))
 
    if not code_str:
        return JsonResponse({'success': False, 'message': 'Code vide.'})
 
    try:
        code = CodePromo.objects.get(code=code_str)
    except CodePromo.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Code introuvable.'})
 
    ok, erreur = _verifier_eligibilite(code, request.user, montant)
    if not ok:
        return JsonResponse({'success': False, 'message': erreur})
 
    # Stocker en session
    request.session['code_promo_id']    = str(code.id)
    request.session['code_promo_code']  = code.code
    request.session['livraison_gratuite'] = (code.type_reduction == 'livraison_gratuite')
    request.session.modified = True
 
    reduction = code.calculer_reduction(montant) if code.type_reduction != 'livraison_gratuite' else Decimal('0')
 
    return JsonResponse({
        'success':          True,
        'code':             code.code,
        'nom':              code.nom,
        'reduction':        float(reduction),
        'livraison_gratuite': code.type_reduction == 'livraison_gratuite',
        'message':          f"✅ Code « {code.code} » appliqué.",
    })


@require_POST
def ajax_retirer_code(request):
    """Retire le code promo de la session."""
    request.session.pop('code_promo_id',       None)
    request.session.pop('code_promo_code',     None)
    request.session.pop('livraison_gratuite',  None)
    request.session.modified = True
    return JsonResponse({'success': True, 'message': "Code promo retiré."})



# =============================================================================
# GESTION — Vendeur / Admin
# =============================================================================
 
@login_required
def mes_codes_promo(request):
    """
    Liste des codes promo créés par le vendeur connecté.
    Admins voient tous les codes.
    """
    if not (request.user.peut_vendre or request.user.is_staff):
        messages.warning(request, "Réservé aux vendeurs.")
        return redirect('apps_core:tableau_de_bord')
 
    now = timezone.now()
 
    if request.user.is_staff:
        qs = CodePromo.objects.select_related('createur').order_by('-date_creation')
    else:
        qs = CodePromo.objects.filter(createur=request.user).order_by('-date_creation')
 
    statut = request.GET.get('statut', '')
    if statut:
        qs = qs.filter(statut=statut)
 
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(nom__icontains=q))
 
    stats = {
        'total':   qs.count(),
        'actifs':  qs.filter(statut='actif', date_debut__lte=now, date_fin__gte=now).count(),
        'expires': qs.filter(Q(statut='expire') | Q(date_fin__lt=now)).count(),
    }
 
    paginator  = Paginator(qs, 20)
    codes_promo = paginator.get_page(request.GET.get('page', 1))
 
    return render(request, 'apps_marketplace/codes_promo/mes_codes_promo.html', {
        'codes_promo': codes_promo,
        'stats':       stats,
        'statut':      statut,
        'q':           q,
        'statuts':     CodePromo.STATUT_CHOICES,
        'page_titre':  'Mes codes promo',
    })
 
 
@login_required
def creer_code_promo(request):
    """Création d'un code promo."""
    from apps_marketplace.forms import CodePromoForm
 
    if not (request.user.peut_vendre or request.user.is_staff):
        messages.warning(request, "Réservé aux vendeurs.")
        return redirect('apps_core:tableau_de_bord')
 
    if request.method == 'POST':
        form = CodePromoForm(request.POST, user=request.user)
        if form.is_valid():
            code = form.save(commit=False)
            code.createur = request.user
            code.save()
            form.save_m2m()
            messages.success(request, f"Code « {code.code} » créé.")
            return redirect('apps_marketplace:mes_codes_promo')
        else:
            messages.error(request, "Veuillez corriger les erreurs.")
    else:
        form = CodePromoForm(user=request.user)
 
    return render(request, 'apps_marketplace/codes_promo/code_promo_form.html', {
        'form':       form,
        'mode':       'creation',
        'page_titre': 'Créer un code promo',
    })
 
 
@login_required
def modifier_code_promo(request, pk):
    """Modification d'un code promo existant."""
    from apps_marketplace.forms import CodePromoForm
 
    code = get_object_or_404(CodePromo, pk=pk)
 
    if not _peut_gerer_code(request.user, code):
        messages.error(request, "Vous ne pouvez pas modifier ce code.")
        return redirect('apps_marketplace:mes_codes_promo')
 
    if request.method == 'POST':
        form = CodePromoForm(request.POST, instance=code, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f"Code « {code.code} » mis à jour.")
            return redirect('apps_marketplace:mes_codes_promo')
        else:
            messages.error(request, "Veuillez corriger les erreurs.")
    else:
        form = CodePromoForm(instance=code, user=request.user)
 
    return render(request, 'apps_marketplace/codes_promo/code_promo_form.html', {
        'form':       form,
        'code':       code,
        'mode':       'edition',
        'page_titre': f"Modifier — {code.code}",
    })
 
 
@login_required
@require_POST
def supprimer_code_promo(request, pk):
    """Suppression d'un code promo."""
    code = get_object_or_404(CodePromo, pk=pk)
 
    if not _peut_gerer_code(request.user, code):
        messages.error(request, "Vous ne pouvez pas supprimer ce code.")
        return redirect('apps_marketplace:mes_codes_promo')
 
    # Empêcher la suppression si des commandes l'utilisent
    if Commande.objects.filter(code_promo=code).exists():
        messages.error(request, "Impossible de supprimer : ce code a déjà été utilisé sur des commandes.")
        return redirect('apps_marketplace:mes_codes_promo')
 
    libelle = code.code
    code.delete()
    messages.success(request, f"Code « {libelle} » supprimé.")
    return redirect('apps_marketplace:mes_codes_promo')
 
 
@login_required
@require_POST
def toggle_statut_code_promo(request, pk):
    """Active/désactive rapidement un code promo (AJAX)."""
    code = get_object_or_404(CodePromo, pk=pk)
 
    if not _peut_gerer_code(request.user, code):
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)
 
    nouveau = request.POST.get('statut', '')
    statuts_valides = [c[0] for c in CodePromo.STATUT_CHOICES]
    if nouveau not in statuts_valides:
        # Toggle simple actif/inactif si pas de statut précisé
        nouveau = 'inactif' if code.statut == 'actif' else 'actif'
 
    code.statut = nouveau
    code.save(update_fields=['statut'])
 
    return JsonResponse({
        'success': True,
        'statut':  code.statut,
        'label':   code.get_statut_display(),
    })
 
 
@login_required
def stats_code_promo(request, pk):
    """Statistiques d'utilisation d'un code promo."""
    code = get_object_or_404(CodePromo, pk=pk)
 
    if not _peut_gerer_code(request.user, code):
        messages.error(request, "Accès non autorisé.")
        return redirect('apps_marketplace:mes_codes_promo')
 
    commandes = Commande.objects.filter(code_promo=code).select_related(
        'utilisateur'
    ).order_by('-date_creation')
 
    nb_utilisations = commandes.count()
    montant_total_reduction = commandes.aggregate(
        total=Sum('montant_reduction')
    )['total'] or Decimal('0')
 
    ca_genere = commandes.aggregate(
        total=Sum('montant_total')
    )['total'] or Decimal('0')
 
    taux = 0
    if code.limite_utilisation_globale and code.limite_utilisation_globale > 0:
        taux = min(100, round((nb_utilisations / code.limite_utilisation_globale) * 100))
 
    paginator = Paginator(commandes, 20)
    commandes_page = paginator.get_page(request.GET.get('page', 1))
 
    return render(request, 'apps_marketplace/codes_promo/stats_code_promo.html', {
        'code':                   code,
        'commandes':              commandes_page,
        'nb_utilisations':        nb_utilisations,
        'montant_total_reduction': montant_total_reduction,
        'ca_genere':              ca_genere,
        'taux_utilisation':       taux,
        'page_titre':             f"Stats — {code.code}",
    })
 
 
# =============================================================================
# ADMIN — Vue globale
# =============================================================================
 
@login_required
def admin_codes_promo_liste(request):
    """Vue admin de tous les codes promo de la plateforme."""
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')
 
    qs = CodePromo.objects.select_related('createur').annotate(
        nb_commandes=Count('commandes')
    ).order_by('-date_creation')
 
    statut = request.GET.get('statut', '')
    if statut:
        qs = qs.filter(statut=statut)
 
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(nom__icontains=q) | Q(createur__username__icontains=q))
 
    paginator   = Paginator(qs, 30)
    codes_promo = paginator.get_page(request.GET.get('page', 1))
 
    stats = {
        'total':             CodePromo.objects.count(),
        'actifs':            CodePromo.objects.filter(statut='actif').count(),
        'total_reductions':  Commande.objects.aggregate(s=Sum('montant_reduction'))['s'] or 0,
    }
 
    return render(request, 'app_marketplace/admin/codes_promo_liste.html', {
        'codes_promo': codes_promo,
        'stats':       stats,
        'statut':      statut,
        'q':           q,
        'statuts':     CodePromo.STATUT_CHOICES,
        'page_titre':  'Gestion des codes promo',
    })




# =============================================================================
# HELPERS
# =============================================================================
 
def _est_commande_yopishop(commande):
    """
    Vérifie si une commande est éligible au BNPL (paiement fractionné).
    Règle : boutique principale de type 'yopishop' OU tous les articles
    appartiennent à un vendeur type_vendeur == 'yopishop'.
    """
    if commande.boutique and commande.boutique.type_boutique == 'yopishop':
        return True
    # Vérifier les articles
    articles = commande.articles.select_related('produit__vendeur').all()
    if not articles.exists():
        return False
    return all(a.produit.vendeur.type_vendeur == 'yopishop' for a in articles)
 
 
def _operateurs_disponibles(pays_id=None):
    """Retourne les opérateurs actifs, optionnellement filtrés par pays."""
    qs = Operateur.objects.filter(est_actif=True)
    if pays_id:
        qs = qs.filter(numeros__pays_id=pays_id, numeros__est_actif=True).distinct()
    return qs



# =============================================================================
# PAIEMENTS — Côté acheteur
# =============================================================================
 
@login_required
def mes_paiements(request):
    qs = Paiement.objects.filter(
        commande__utilisateur=request.user
    ).select_related('commande', 'tranche_paiement').order_by('-date_creation')

    statut = request.GET.get('statut', '')
    if statut:
        qs = qs.filter(statut=statut)

    # ← Plans BNPL de l'utilisateur
    plans_bnpl = PlanPaiement.objects.filter(
        commande__utilisateur=request.user
    ).select_related('commande').prefetch_related('tranches').order_by('-date_creation')

    paginator = Paginator(qs, 20)
    paiements = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'apps_marketplace/paiements/mes_paiements.html', {
        'paiements':   paiements,
        'plans_bnpl':  plans_bnpl,
        'statut':      statut,
        'statuts':     Paiement.STATUT_CHOICES,
        'page_titre':  'Mes paiements',
    })
 
 
@login_required
def paiement_detail(request, pk):
    """Détail d'un paiement pour l'acheteur ou l'admin."""
    paiement = get_object_or_404(
        Paiement.objects.select_related('commande', 'commande__utilisateur', 'valide_par'),
        pk=pk,
    )
 
    # Droits : acheteur concerné ou admin
    if paiement.commande.utilisateur != request.user and not request.user.is_staff:
        messages.error(request, "Vous n'avez pas accès à ce paiement.")
        return redirect('apps_core:tableau_de_bord')
 
    return render(request, 'apps_marketplace/paiements/paiement_detail.html', {
        'paiement':   paiement,
        'page_titre': f"Paiement — {paiement.commande.numero_commande}",
    })
 
 
@login_required
def initier_paiement(request, commande_pk):
    """
    Page de paiement d'une commande.
    Affiche les numéros de versement disponibles + formulaire de preuve.
    """
    commande = get_object_or_404(Commande, pk=commande_pk, utilisateur=request.user)
 
    if commande.statut_paiement == 'payee':
        messages.info(request, "Cette commande est déjà payée.")
        return redirect('apps_marketplace:commande_detail', pk=commande.pk)
 
    # Opérateurs disponibles (numéros officiels YopiShop)
    numeros_versement = NumeroVersement.objects.filter(
        est_actif=True
    ).select_related('operateur', 'pays').order_by('operateur__nom')
 
    # Paiements déjà soumis pour cette commande
    paiements_existants = Paiement.objects.filter(commande=commande).order_by('-date_creation')
 
    # Plan BNPL si commande YopiShop
    plan_paiement = None
    tranches = []
    if _est_commande_yopishop(commande):
        try:
            plan_paiement = commande.plan_paiement
            tranches = plan_paiement.tranches.all()
        except PlanPaiement.DoesNotExist:
            pass
 
    context = {
        'commande':            commande,
        'numeros_versement':   numeros_versement,
        'paiements_existants': paiements_existants,
        'plan_paiement':       plan_paiement,
        'tranches':            tranches,
        'methodes':            Paiement.METHODE_CHOICES,
        'est_yopishop':        _est_commande_yopishop(commande),
        'page_titre':          f"Payer — Commande {commande.numero_commande}",
    }
    return render(request, 'apps_marketplace/paiements/initier_paiement.html', context)
 
 
@login_required
@require_POST
def soumettre_preuve_paiement(request, commande_pk):
    """
    L'acheteur soumet une preuve de paiement (capture d'écran).
    Crée un objet Paiement avec statut 'en_verification'.
    Optionnel : lier à une tranche (si BNPL).
    """
    commande = get_object_or_404(Commande, pk=commande_pk, utilisateur=request.user)
 
    if commande.statut_paiement == 'payee':
        messages.info(request, "Cette commande est déjà entièrement payée.")
        return redirect('apps_marketplace:commande_detail', pk=commande.pk)
 
    methode            = request.POST.get('methode', '')
    numero_expediteur  = request.POST.get('numero_expediteur', '').strip()
    message_client     = request.POST.get('message_client', '').strip()
    tranche_id         = request.POST.get('tranche_id')
    preuve             = request.FILES.get('preuve_paiement')
 
    if not methode:
        messages.error(request, "Veuillez sélectionner une méthode de paiement.")
        return redirect('apps_marketplace:initier_paiement', commande_pk=commande_pk)
 
    # Montant : tranche ou total restant
    montant = commande.montant_total
    tranche = None
    if tranche_id:
        tranche = TranchePaiement.objects.filter(
            pk=tranche_id, plan_paiement__commande=commande, statut='en_attente'
        ).first()
        if tranche:
            montant = tranche.montant
 
    paiement = Paiement.objects.create(
        commande=commande,
        methode=methode,
        montant=montant,
        statut='en_verification',
        preuve_paiement=preuve,
        numero_expediteur=numero_expediteur,
        message_client=message_client,
        tranche_paiement=tranche,
    )
 
    # Passer la commande en 'en_verification'
    commande.statut_paiement = 'en_verification'
    commande.save(update_fields=['statut_paiement'])
 
    messages.success(
        request,
        "Preuve de paiement soumise. Notre équipe validera votre paiement sous 24h."
    )
    return redirect('apps_marketplace:paiement_detail', pk=paiement.pk)
 
 
# =============================================================================
# PLAN DE PAIEMENT BNPL — YopiShop uniquement
# =============================================================================
 
@login_required
def mon_plan_paiement(request, commande_pk):
    """
    Affiche le plan de paiement fractionné d'une commande YopiShop.
    Accessible par l'acheteur ou l'admin.
    """
    commande = get_object_or_404(Commande, pk=commande_pk)
 
    if commande.utilisateur != request.user and not request.user.is_staff:
        messages.error(request, "Accès non autorisé.")
        return redirect('apps_core:tableau_de_bord')
 
    if not _est_commande_yopishop(commande):
        messages.error(request, "Le paiement fractionné est réservé aux commandes YopiShop.")
        return redirect('apps_marketplace:commande_detail', pk=commande_pk)
 
    try:
        plan = commande.plan_paiement
    except PlanPaiement.DoesNotExist:
        messages.error(request, "Aucun plan de paiement pour cette commande.")
        return redirect('apps_marketplace:commande_detail', pk=commande_pk)
 
    tranches = plan.tranches.all()
 
    return render(request, 'apps_marketplace/paiements/plan_paiement.html', {
        'commande':  commande,
        'plan':      plan,
        'tranches':  tranches,
        'page_titre': f"Plan de paiement — {commande.numero_commande}",
    })
 
 
# =============================================================================
# ADMIN — Validation des paiements
# =============================================================================
 
@login_required
def admin_paiements_liste(request):
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')

    qs = Paiement.objects.select_related(
        'commande', 'commande__utilisateur'
    ).order_by('-date_creation')

    statut = request.GET.get('statut', 'en_verification')
    if statut:
        qs = qs.filter(statut=statut)

    est_suspect = request.GET.get('suspect', '')
    if est_suspect == '1':
        qs = qs.filter(est_suspect=True)

    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(
            Q(commande__numero_commande__icontains=q) |
            Q(commande__utilisateur__username__icontains=q) |
            Q(reference_paiement__icontains=q) |
            Q(numero_expediteur__icontains=q)
        )

    # ← Commandes BNPL sans plan encore configuré
    commandes_bnpl_sans_plan = Commande.objects.filter(
        est_paiement_fractionne=True,
    ).exclude(
        pk__in=PlanPaiement.objects.values_list('commande_id', flat=True)
    ).select_related('utilisateur').order_by('-date_creation')

    stats = {
        'en_verification':   Paiement.objects.filter(statut='en_verification').count(),
        'suspects':          Paiement.objects.filter(est_suspect=True).count(),
        'completes_jour':    Paiement.objects.filter(
            statut='complete', date_validation__date=timezone.now().date()
        ).count(),
        'ca_valide':         Paiement.objects.filter(statut='complete').aggregate(
            s=Sum('montant')
        )['s'] or 0,
        'bnpl_sans_plan':    commandes_bnpl_sans_plan.count(),
    }

    paginator = Paginator(qs, 25)
    paiements = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'apps_marketplace/paiements/paiements_liste.html', {
        'paiements':               paiements,
        'commandes_bnpl_sans_plan': commandes_bnpl_sans_plan[:10],
        'stats':                   stats,
        'statut':                  statut,
        'est_suspect':             est_suspect,
        'q':                       q,
        'statuts':                 Paiement.STATUT_CHOICES,
        'page_titre':              'Gestion des paiements',
    })
 
 
@login_required
@require_POST
def admin_valider_paiement(request, pk):
    """Valide un paiement (admin). Utilise la méthode Paiement.valider()."""
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)
 
    paiement    = get_object_or_404(Paiement, pk=pk)
    commentaire = request.POST.get('commentaire', '')
 
    if not paiement.peut_etre_valide():
        return JsonResponse({'success': False, 'message': 'Ce paiement ne peut plus être validé.'})
 
    ok = paiement.valider(request.user, commentaire)
    if ok:
        # Notification à l'acheteur (si disponible)
        try:
            from apps_core.views_notifications import creer_notification
            creer_notification(
                utilisateur=paiement.commande.utilisateur,
                type_notification='paiement',
                titre="Paiement validé ✅",
                message=f"Votre paiement de {paiement.montant:,.0f} FCFA pour la commande "
                        f"{paiement.commande.numero_commande} a été validé.",
                lien=f"/commandes/{paiement.commande.pk}/",
            )
        except Exception:
            pass
 
        msg = f"Paiement de {paiement.montant:,.0f} FCFA validé."
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': msg})
        messages.success(request, msg)
    else:
        msg = "Échec de la validation."
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': msg})
        messages.error(request, msg)
 
    return redirect('apps_marketplace:admin_paiements_liste')
 
 
@login_required
@require_POST
def admin_rejeter_paiement(request, pk):
    """Rejette un paiement (admin). Utilise la méthode Paiement.rejeter()."""
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)
 
    paiement = get_object_or_404(Paiement, pk=pk)
    motif    = request.POST.get('motif', '').strip()
 
    if not motif:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Un motif de rejet est requis.'})
        messages.error(request, "Un motif de rejet est requis.")
        return redirect('apps_marketplace:admin_paiements_liste')
 
    ok = paiement.rejeter(request.user, motif)
    if ok:
        # Notification à l'acheteur
        try:
            from apps_core.views_notifications import creer_notification
            creer_notification(
                utilisateur=paiement.commande.utilisateur,
                type_notification='paiement',
                titre="Paiement rejeté ❌",
                message=f"Votre paiement pour la commande {paiement.commande.numero_commande} "
                        f"a été rejeté. Motif : {motif}",
                lien=f"/commandes/{paiement.commande.pk}/payer/",
            )
        except Exception:
            pass
 
        msg = "Paiement rejeté."
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': msg})
        messages.warning(request, msg)
    else:
        msg = "Échec du rejet."
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': msg})
        messages.error(request, msg)
 
    return redirect('apps_marketplace:admin_paiements_liste')
 
 
@login_required
@require_POST
def admin_marquer_suspect(request, pk):
    """Marque un paiement comme suspect (AJAX)."""
    if not request.user.is_staff:
        return JsonResponse({'success': False}, status=403)
 
    paiement = get_object_or_404(Paiement, pk=pk)
    paiement.est_suspect = not paiement.est_suspect
    paiement.save(update_fields=['est_suspect'])
    return JsonResponse({'success': True, 'est_suspect': paiement.est_suspect})
 
 
# =============================================================================
# ADMIN — Plan de paiement BNPL (YopiShop uniquement)
# =============================================================================
 
@login_required
def admin_creer_plan_paiement(request, commande_pk):
    if not request.user.is_staff:
        messages.error(request, "Réservé aux administrateurs YopiShop.")
        return redirect('apps_core:accueil')

    commande = get_object_or_404(Commande, pk=commande_pk)

    if not _est_commande_yopishop(commande):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Non éligible au BNPL.'})
        messages.error(request, "Réservé aux commandes YopiShop.")
        return redirect('apps_marketplace:commande_detail', pk=commande_pk)

    if hasattr(commande, 'plan_paiement'):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Plan déjà existant.'})
        messages.warning(request, "Cette commande a déjà un plan.")
        return redirect('apps_marketplace:mon_plan_paiement', commande_pk=commande_pk)

    if request.method == 'POST':
        try:
            nombre_tranches = int(request.POST.get('nombre_tranches', 3))
            taux_interet    = Decimal(request.POST.get('taux_interet', '0'))

            if nombre_tranches < 2 or nombre_tranches > 12:
                raise ValueError("Nombre de tranches invalide (2-12).")

            montant_avec_interet = commande.montant_total * (1 + taux_interet / 100)
            montant_par_tranche  = (montant_avec_interet / nombre_tranches).quantize(Decimal('1'))

            plan = PlanPaiement.objects.create(
                commande=commande,
                montant_total=montant_avec_interet,
                nombre_tranches=nombre_tranches,
                montant_par_tranche=montant_par_tranche,
                taux_interet=taux_interet,
            )

            from dateutil.relativedelta import relativedelta
            import datetime
            date_base = commande.date_creation.date()
            for i in range(1, nombre_tranches + 1):
                date_echeance = datetime.datetime.combine(
                    date_base + relativedelta(months=i), datetime.time(23, 59)
                )
                TranchePaiement.objects.create(
                    plan_paiement=plan,
                    numero_tranche=i,
                    montant=montant_par_tranche,
                    date_echeance=date_echeance,
                )

            commande.nombre_tranches = nombre_tranches
            commande.save(update_fields=['nombre_tranches'])

            # Notifier l'acheteur
            try:
                from apps_core.views_notifications import creer_notification
                creer_notification(
                    utilisateur=commande.utilisateur,
                    type_notification='paiement',
                    titre="📅 Votre plan de paiement est prêt",
                    message=(
                        f"Votre plan de paiement {nombre_tranches}× "
                        f"de {montant_par_tranche:,.0f} FCFA/mois a été configuré "
                        f"pour la commande {commande.numero_commande}."
                    ),
                    lien=f"/commandes/{commande.pk}/plan-paiement/",
                )
            except Exception:
                pass

            msg = f"Plan {nombre_tranches}× créé pour {commande.numero_commande}."

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': msg,
                    'plan_url': f"/commandes/{commande.pk}/plan-paiement/",
                })

            messages.success(request, msg)
            return redirect('apps_marketplace:mon_plan_paiement', commande_pk=commande_pk)

        except (ValueError, TypeError) as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': str(e)})
            messages.error(request, f"Erreur : {e}")

    return render(request, 'apps_marketplace/paiements/creer_plan.html', {
        'commande':   commande,
        'page_titre': f"Plan de paiement — {commande.numero_commande}",
    })
 
 
# =============================================================================
# ADMIN — Opérateurs et Numéros de versement (YopiShop uniquement)
# =============================================================================
 
@login_required
def admin_operateurs(request):
    """
    Gestion des opérateurs de paiement — admin uniquement.
    Ces opérateurs sont les partenaires officiels de YopiShop
    (Orange Money, MTN MoMo, Wave, etc.).
    """
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')
 
    operateurs = Operateur.objects.annotate(
        nb_numeros=Count('numeros')
    ).order_by('nom')
 
    if request.method == 'POST':
        action = request.POST.get('action', '')
 
        if action == 'creer':
            nom      = request.POST.get('nom', '').strip()
            code     = request.POST.get('code', '').strip().upper()
            est_actif = request.POST.get('est_actif') == 'on'
            logo      = request.FILES.get('logo')
 
            if nom:
                op = Operateur.objects.create(nom=nom, code=code, est_actif=est_actif)
                if logo:
                    op.logo = logo
                    op.save(update_fields=['logo'])
                messages.success(request, f"Opérateur « {nom} » créé.")
            else:
                messages.error(request, "Le nom est requis.")
 
        elif action == 'toggle':
            pk = request.POST.get('pk')
            op = get_object_or_404(Operateur, pk=pk)
            op.est_actif = not op.est_actif
            op.save(update_fields=['est_actif'])
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'est_actif': op.est_actif})
 
        elif action == 'supprimer':
            pk = request.POST.get('pk')
            op = get_object_or_404(Operateur, pk=pk)
            if op.numeros.exists():
                messages.error(request, "Impossible de supprimer : des numéros sont associés.")
            else:
                op.delete()
                messages.success(request, "Opérateur supprimé.")
 
        return redirect('apps_marketplace:admin_operateurs')
 
    return render(request, 'apps_marketplace/paiements/operateurs.html', {
        'operateurs': operateurs,
        'page_titre': 'Gestion des opérateurs',
    })
 
 
@login_required
def admin_numeros_versement(request):
    """
    Gestion des numéros de versement officiels YopiShop — admin uniquement.
    Ces numéros sont affichés aux acheteurs pour qu'ils sachent où
    envoyer leur paiement (Mobile Money, virement...).
    """
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')
 
    numeros = NumeroVersement.objects.select_related(
        'operateur', 'pays'
    ).order_by('operateur__nom', 'pays__nom')
 
    operateurs_actifs = Operateur.objects.filter(est_actif=True)
 
    from apps_core.models import Pays
    pays_disponibles = Pays.objects.filter(est_actif=True)
 
    if request.method == 'POST':
        action = request.POST.get('action', '')
 
        if action == 'creer':
            operateur_pk = request.POST.get('operateur')
            pays_pk      = request.POST.get('pays')
            numero       = request.POST.get('numero', '').strip()
            nom_compte   = request.POST.get('nom_compte', '').strip()
            description  = request.POST.get('description', '').strip()
 
            if not (operateur_pk and pays_pk and numero):
                messages.error(request, "Opérateur, pays et numéro sont requis.")
            else:
                op   = get_object_or_404(Operateur, pk=operateur_pk)
                pays = get_object_or_404(Pays, pk=pays_pk)
                NumeroVersement.objects.create(
                    operateur=op, pays=pays, numero=numero,
                    nom_compte=nom_compte, description=description,
                )
                messages.success(request, f"Numéro {numero} ({op.nom}) créé.")
 
        elif action == 'toggle':
            pk = request.POST.get('pk')
            nv = get_object_or_404(NumeroVersement, pk=pk)
            nv.est_actif = not nv.est_actif
            nv.save(update_fields=['est_actif'])
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'est_actif': nv.est_actif})
 
        elif action == 'supprimer':
            pk = request.POST.get('pk')
            nv = get_object_or_404(NumeroVersement, pk=pk)
            nv.delete()
            messages.success(request, "Numéro supprimé.")
 
        return redirect('apps_marketplace:admin_numeros_versement')
 
    return render(request, 'apps_marketplace/paiements/numeros_versement.html', {
        'numeros':           numeros,
        'operateurs_actifs': operateurs_actifs,
        'pays_disponibles':  pays_disponibles,
        'page_titre':        'Numéros de versement YopiShop',
    })
 
 
# =============================================================================
# AJAX — Usage public
# =============================================================================
 
@require_GET
def ajax_numeros_versement(request):
    """
    Retourne les numéros de versement actifs (JSON) pour le checkout.
    Optionnel : ?pays_id=1 pour filtrer par pays.
    GET /paiements/ajax/numeros-versement/
    """
    pays_id = request.GET.get('pays_id')
    qs = NumeroVersement.objects.filter(est_actif=True).select_related('operateur', 'pays')
    if pays_id:
        qs = qs.filter(pays_id=pays_id)
 
    data = [{
        'id':           nv.pk,
        'numero':       nv.numero,
        'nom_compte':   nv.nom_compte,
        'operateur':    nv.operateur.nom,
        'operateur_code': nv.operateur.code,
        'pays':         nv.pays.nom,
        'description':  nv.description or '',
        'logo_url':     nv.operateur.logo.url if nv.operateur.logo else '',
    } for nv in qs]
 
    return JsonResponse({'numeros': data})
 
 
@require_GET
def ajax_operateurs_actifs(request):
    """Retourne les opérateurs actifs en JSON pour le select de méthode de paiement."""
    ops = Operateur.objects.filter(est_actif=True).order_by('nom')
    data = [{
        'id':       op.pk,
        'nom':      op.nom,
        'code':     op.code,
        'logo_url': op.logo.url if op.logo else '',
    } for op in ops]
    return JsonResponse({'operateurs': data})
 
 
@login_required
@require_GET
def ajax_plan_paiement(request, commande_pk):
    """
    Retourne le résumé du plan de paiement d'une commande (JSON).
    Utilisé dans le checkout pour afficher les tranches en temps réel.
    """
    commande = get_object_or_404(Commande, pk=commande_pk, utilisateur=request.user)
 
    if not _est_commande_yopishop(commande):
        return JsonResponse({'disponible': False, 'message': 'Non éligible au paiement fractionné.'})
 
    try:
        plan = commande.plan_paiement
        tranches = [{
            'numero':        t.numero_tranche,
            'montant':       float(t.montant),
            'date_echeance': t.date_echeance.strftime('%d/%m/%Y'),
            'statut':        t.statut,
            'label':         t.get_statut_display(),
        } for t in plan.tranches.all()]
 
        return JsonResponse({
            'disponible':        True,
            'nombre_tranches':   plan.nombre_tranches,
            'montant_par_tranche': float(plan.montant_par_tranche),
            'taux_interet':      float(plan.taux_interet),
            'montant_paye':      float(plan.montant_paye()),
            'montant_restant':   float(plan.montant_restant()),
            'est_complet':       plan.est_complet(),
            'tranches':          tranches,
        })
 
    except PlanPaiement.DoesNotExist:
        return JsonResponse({'disponible': False, 'message': 'Aucun plan de paiement.'})


 
# =============================================================================
# HELPERS
# =============================================================================
 
def _peut_voir_retour(user, retour):
    """Vérifie si l'user peut accéder à ce retour."""
    if user.is_staff:
        return True
    if retour.utilisateur == user:
        return True
    # Vendeur du produit concerné
    return retour.article_commande.produit.vendeur == user



# =============================================================================
# ACHETEUR
# =============================================================================
 
@login_required
def mes_retours(request):
    """Liste de toutes mes demandes de retour."""
    qs = Retour.objects.filter(
        utilisateur=request.user
    ).select_related(
        'commande', 'article_commande__produit'
    ).order_by('-date_demande')
 
    statut = request.GET.get('statut', '')
    if statut:
        qs = qs.filter(statut=statut)
 
    paginator = Paginator(qs, 15)
    retours   = paginator.get_page(request.GET.get('page', 1))
 
    return render(request, 'apps_marketplace/retours/mes_retours.html', {
        'retours':    retours,
        'statut':     statut,
        'statuts':    Retour.STATUT_CHOICES,
        'page_titre': 'Mes retours',
    })
 
 
@login_required
def demander_retour(request, commande_pk, article_pk):
    """
    Soumet une demande de retour pour un article d'une commande livrée.
    L'acheteur joint une description et optionnellement des photos.
    """
    commande = get_object_or_404(Commande, pk=commande_pk, utilisateur=request.user)
    article  = get_object_or_404(ArticleCommande, pk=article_pk, commande=commande)
 
    # Vérifications
    if commande.statut not in ('livree', 'remboursee'):
        messages.error(request, "Vous ne pouvez demander un retour que sur une commande livrée.")
        return redirect('apps_marketplace:commande_detail', pk=commande.pk)
 
    # Quantité déjà retournée pour cet article
    deja_retourne = Retour.objects.filter(
        article_commande=article,
        utilisateur=request.user,
        statut__in=['demande', 'approuve', 'en_cours', 'complete'],
    ).aggregate(
        total=Sum('quantite')
    )['total'] or 0
 
    retour_existant = Retour.objects.filter(
        article_commande=article,
        utilisateur=request.user,
        statut__in=['demande', 'approuve', 'en_cours'],
    ).first()
 
    if retour_existant:
        messages.warning(request, "Une demande de retour est déjà en cours pour cet article.")
        return redirect('apps_marketplace:retour_detail', pk=retour_existant.pk)
 
    if request.method == 'POST':
        raison      = request.POST.get('raison', '')
        description = request.POST.get('description', '').strip()
        quantite_str = request.POST.get('quantite', '1')
 
        # Validations
        raisons_valides = [r[0] for r in Retour.RAISON_CHOICES]
        if raison not in raisons_valides:
            messages.error(request, "Veuillez sélectionner une raison valide.")
            return redirect('apps_marketplace:demander_retour', commande_pk=commande_pk, article_pk=article_pk)
 
        if len(description) < 20:
            messages.error(request, "La description doit contenir au moins 20 caractères.")
            return redirect('apps_marketplace:demander_retour', commande_pk=commande_pk, article_pk=article_pk)
 
        try:
            quantite = int(quantite_str)
            if quantite < 1 or quantite > article.quantite:
                raise ValueError()
        except (ValueError, TypeError):
            messages.error(request, f"Quantité invalide (1 à {article.quantite}).")
            return redirect('apps_marketplace:demander_retour', commande_pk=commande_pk, article_pk=article_pk)
 
        retour = Retour.objects.create(
            commande=commande,
            article_commande=article,
            utilisateur=request.user,
            raison=raison,
            description=description,
            quantite=quantite,
        )
 
        # Notification au vendeur
        try:
            from apps_core.views_notifications import creer_notification
            creer_notification(
                utilisateur=article.produit.vendeur,
                type_notification='commande',
                titre="Nouvelle demande de retour",
                message=f"{request.user.username} a soumis une demande de retour pour "
                        f"« {article.produit.titre} » (commande {commande.numero_commande}).",
                lien=f"/vendeur/retours/{retour.pk}/",
            )
        except Exception:
            pass
 
        messages.success(request, "Votre demande de retour a été soumise. Nous la traiterons sous 48h.")
        return redirect('apps_marketplace:retour_detail', pk=retour.pk)
 
    context = {
        'commande':    commande,
        'article':     article,
        'raisons':     Retour.RAISON_CHOICES,
        'page_titre':  'Demander un retour',
    }
    return render(request, 'apps_marketplace/retours/demander_retour.html', context)



@login_required
def retour_detail(request, pk):
    """Détail et suivi d'un retour."""
    retour = get_object_or_404(
        Retour.objects.select_related('commande', 'article_commande__produit', 'utilisateur'),
        pk=pk
    )
 
    if not _peut_voir_retour(request.user, retour):
        messages.error(request, "Vous n'avez pas accès à ce retour.")
        return redirect('apps_core:tableau_de_bord')
 
    return render(request, 'app_marketplace/retours/retour_detail.html', {
        'retour':     retour,
        'page_titre': f"Retour — {retour.commande.numero_commande}",
    })
 
 
@login_required
@require_POST
def annuler_retour(request, pk):
    """L'acheteur annule sa demande (seulement si statut == 'demande')."""
    retour = get_object_or_404(Retour, pk=pk, utilisateur=request.user)
 
    if retour.statut != 'demande':
        messages.error(request, "Vous ne pouvez annuler qu'une demande en attente.")
        return redirect('apps_marketplace:retour_detail', pk=pk)
 
    retour.statut = 'refuse'
    retour.notes_admin = "Annulé par l'acheteur."
    retour.date_traitement = timezone.now()
    retour.save()
 
    messages.success(request, "Demande de retour annulée.")
    return redirect('apps_marketplace:mes_retours')


 
# =============================================================================
# VENDEUR
# =============================================================================
 
@login_required
def retours_recus(request):
    """Retours sur les produits du vendeur connecté."""
    if not request.user.peut_vendre:
        messages.warning(request, "Réservé aux vendeurs.")
        return redirect('apps_core:tableau_de_bord')
 
    qs = Retour.objects.filter(
        article_commande__produit__vendeur=request.user
    ).select_related(
        'commande', 'article_commande__produit', 'utilisateur'
    ).order_by('-date_demande')
 
    statut = request.GET.get('statut', '')
    if statut:
        qs = qs.filter(statut=statut)
 
    paginator = Paginator(qs, 15)
    retours   = paginator.get_page(request.GET.get('page', 1))
 
    stats = {
        'total':    qs.count(),
        'demandes': Retour.objects.filter(
            article_commande__produit__vendeur=request.user, statut='demande'
        ).count(),
        'en_cours': Retour.objects.filter(
            article_commande__produit__vendeur=request.user, statut__in=['approuve', 'en_cours']
        ).count(),
    }
 
    return render(request, 'apps_marketplace/retours/retours_recus.html', {
        'retours':    retours,
        'stats':      stats,
        'statut':     statut,
        'statuts':    Retour.STATUT_CHOICES,
        'page_titre': 'Retours reçus',
    })
 
 
# =============================================================================
# ADMIN
# =============================================================================
 
@login_required
def admin_retours_liste(request):
    """Vue admin de toutes les demandes de retour."""
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')
 
    qs = Retour.objects.select_related(
        'commande', 'article_commande__produit', 'utilisateur'
    ).order_by('-date_demande')
 
    statut = request.GET.get('statut', 'demande')
    if statut:
        qs = qs.filter(statut=statut)
 
    raison = request.GET.get('raison', '')
    if raison:
        qs = qs.filter(raison=raison)
 
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(
            Q(commande__numero_commande__icontains=q) |
            Q(utilisateur__username__icontains=q) |
            Q(article_commande__produit__titre__icontains=q)
        )
 
    stats = {
        'total':    Retour.objects.count(),
        'demandes': Retour.objects.filter(statut='demande').count(),
        'approuves': Retour.objects.filter(statut='approuve').count(),
        'completes': Retour.objects.filter(statut='complete').count(),
    }
 
    paginator = Paginator(qs, 25)
    retours   = paginator.get_page(request.GET.get('page', 1))
 
    return render(request, 'apps_marketplace/retours/admin_retours_liste.html', {
        'retours':  retours,
        'stats':    stats,
        'statut':   statut,
        'raison':   raison,
        'q':        q,
        'statuts':  Retour.STATUT_CHOICES,
        'raisons':  Retour.RAISON_CHOICES,
        'page_titre': 'Gestion des retours',
    })
 
 
@login_required
def admin_retour_detail(request, pk):
    """Détail admin d'un retour + actions (approuver/refuser/compléter)."""
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')
 
    retour = get_object_or_404(
        Retour.objects.select_related(
            'commande', 'article_commande__produit',
            'article_commande__produit__vendeur', 'utilisateur'
        ),
        pk=pk
    )
 
    if request.method == 'POST':
        return admin_traiter_retour(request, pk)
 
    return render(request, 'apps_marketplace/retours/admin_retour_detail.html', {
        'retour':     retour,
        'statuts':    Retour.STATUT_CHOICES,
        'page_titre': f"Retour #{retour.pk} — {retour.utilisateur.username}",
    })
 
 
@login_required
@require_POST
def admin_traiter_retour(request, pk):
    """
    Traite une demande de retour (admin).
    Actions : approuver, refuser, en_cours, complete.
    Supporte AJAX et redirect classique.
    """
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)
 
    retour = get_object_or_404(Retour, pk=pk)
    action = request.POST.get('action', '')
    notes  = request.POST.get('notes_admin', '').strip()
 
    # Mapping actions → statuts
    action_map = {
        'approuver': 'approuve',
        'refuser':   'refuse',
        'en_cours':  'en_cours',
        'complete':  'complete',
    }
 
    if action not in action_map:
        msg = "Action inconnue."
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': msg})
        messages.error(request, msg)
        return redirect('apps_marketplace:admin_retour_detail', pk=pk)
 
    # Validation : refus nécessite un motif
    if action == 'refuser' and not notes:
        msg = "Un motif de refus est requis."
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': msg})
        messages.error(request, msg)
        return redirect('apps_marketplace:admin_retour_detail', pk=pk)
 
    nouveau_statut = action_map[action]
    retour.statut         = nouveau_statut
    retour.notes_admin    = notes
    retour.date_traitement = timezone.now()
 
    # Montant de remboursement si complété
    if action == 'complete':
        montant_str = request.POST.get('montant_remboursement', '')
        if montant_str:
            try:
                retour.montant_remboursement = Decimal(montant_str)
            except Exception:
                pass
 
        # Rembourser via wallet si montant défini
        if retour.montant_remboursement and retour.montant_remboursement > 0:
            acheteur = retour.utilisateur
            try:
                acheteur.solde_wallet += retour.montant_remboursement
                acheteur.save(update_fields=['solde_wallet'])
                from apps_core.models import TransactionWallet
                TransactionWallet.objects.create(
                    utilisateur=acheteur,
                    type_transaction='remboursement',
                    montant=retour.montant_remboursement,
                    solde_apres=acheteur.solde_wallet,
                    description=f"Remboursement retour #{retour.pk} — {retour.commande.numero_commande}",
                )
            except Exception:
                pass
 
    retour.save()
 
    # Notification acheteur
    labels_notif = {
        'approuve': ("Retour approuvé ✅", "Votre demande de retour a été approuvée."),
        'refuse':   ("Retour refusé ❌", f"Votre demande de retour a été refusée. {notes}"),
        'en_cours': ("Retour en cours 📦", "Votre retour est en cours de traitement."),
        'complete': ("Remboursement effectué 💰",
                     f"Votre retour est complété. Remboursement : {retour.montant_remboursement or 0:,.0f} FCFA."),
    }
    try:
        from apps_core.views_notifications import creer_notification
        titre_notif, msg_notif = labels_notif.get(nouveau_statut, ("Retour mis à jour", ""))
        creer_notification(
            utilisateur=retour.utilisateur,
            type_notification='commande',
            titre=titre_notif,
            message=msg_notif,
            lien=f"/retours/{retour.pk}/",
        )
    except Exception:
        pass
 
    label_display = dict(Retour.STATUT_CHOICES).get(nouveau_statut, nouveau_statut)
    msg_ok = f"Retour #{retour.pk} → {label_display}."
 
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': msg_ok, 'statut': nouveau_statut})
 
    messages.success(request, msg_ok)
    return redirect('apps_marketplace:admin_retours_liste')
 
 
# =============================================================================
# AJAX
# =============================================================================
 
@login_required
@require_GET
def ajax_statut_retour(request, pk):
    """Retourne le statut actuel d'un retour (polling côté client)."""
    retour = get_object_or_404(Retour, pk=pk)
 
    if not _peut_voir_retour(request.user, retour):
        return JsonResponse({'error': 'Non autorisé'}, status=403)
 
    return JsonResponse({
        'statut':          retour.statut,
        'label':           retour.get_statut_display(),
        'date_traitement': retour.date_traitement.strftime('%d/%m/%Y %H:%M') if retour.date_traitement else None,
        'montant_remboursement': float(retour.montant_remboursement) if retour.montant_remboursement else None,
    })

 
# =============================================================================
# HELPERS
# =============================================================================
 
def _produits_du_vendeur(user):
    """
    Retourne les produits sur lesquels l'utilisateur peut créer un groupe
    d'achat : uniquement SES propres produits actifs, qui autorisent
    l'achat groupé.
    """
    return Produit.objects.filter(
        vendeur=user, est_actif=True, autorise_achat_groupe=True
    ).select_related('categorie')
 
 
def _peut_gerer_groupe(user, groupe):
    """Le créateur du groupe ou un admin peut le gérer."""
    return user.is_staff or groupe.createur == user
 

 
# =============================================================================
# PUBLIC — Découverte
# =============================================================================
 
def groupes_actifs(request):
    """Liste publique des groupes d'achat ouverts (en cours de remplissage)."""
    now = timezone.now()
 
    qs = GroupeAchat.objects.filter(
        statut='ouvert', date_expiration__gt=now
    ).select_related('produit', 'createur').annotate(
        nb_participants=Count('participants', filter=Q(participants__a_confirme=True))
    ).order_by('-date_creation')
 
    categorie = request.GET.get('categorie', '')
    if categorie:
        qs = qs.filter(produit__categorie__slug=categorie)
 
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(produit__titre__icontains=q)
 
    paginator = Paginator(qs, 16)
    groupes   = paginator.get_page(request.GET.get('page', 1))
 
    context = {
        'groupes':    groupes,
        'q':          q,
        'categorie':  categorie,
        'page_titre': 'Achats groupés — YopiShop',
    }
    return render(request, 'apps_marketplace/groupe_achat/groupes_actifs.html', context)


def groupe_detail(request, pk):
    """Page détail d'un groupe d'achat avec bouton rejoindre."""
    groupe = get_object_or_404(
        GroupeAchat.objects.select_related('produit', 'createur').prefetch_related(
            'participants__utilisateur'
        ),
        pk=pk
    )
 
    participants_confirmes = groupe.participants.filter(a_confirme=True).select_related('utilisateur')
    nb_confirmes = participants_confirmes.count()
 
    deja_participant = False
    ma_participation = None
    if request.user.is_authenticated:
        ma_participation = groupe.participants.filter(utilisateur=request.user).first()
        deja_participant = ma_participation is not None
 
    progression = 0
    if groupe.nb_participants_min > 0:
        progression = min(100, round((nb_confirmes / groupe.nb_participants_min) * 100))
 
    context = {
        'groupe':                groupe,
        'participants_confirmes': participants_confirmes,
        'nb_confirmes':          nb_confirmes,
        'progression':           progression,
        'deja_participant':      deja_participant,
        'ma_participation':      ma_participation,
        'est_expire':            timezone.now() > groupe.date_expiration,
        'page_titre':            f"Achat groupé — {groupe.produit.titre}",
    }
    return render(request, 'apps_marketplace/groupe_achat/groupe_detail.html', context)

 
@login_required
@require_POST
def ajax_rejoindre_groupe(request, pk):
    """L'utilisateur rejoint un groupe d'achat (AJAX)."""
    groupe = get_object_or_404(GroupeAchat, pk=pk)
 
    if groupe.statut != 'ouvert':
        return JsonResponse({'success': False, 'message': 'Ce groupe n\'accepte plus de participants.'})
 
    if timezone.now() > groupe.date_expiration:
        return JsonResponse({'success': False, 'message': 'Ce groupe a expiré.'})
 
    if groupe.createur == request.user:
        return JsonResponse({'success': False, 'message': 'Vous êtes le créateur de ce groupe.'})
 
    if groupe.nb_participants_max:
        nb_actuel = groupe.participants.filter(a_confirme=True).count()
        if nb_actuel >= groupe.nb_participants_max:
            return JsonResponse({'success': False, 'message': 'Ce groupe a atteint sa capacité maximale.'})
 
    quantite = int(request.POST.get('quantite', groupe.quantite_par_participant))
    if quantite < 1:
        quantite = groupe.quantite_par_participant
 
    participant, created = ParticipantGroupeAchat.objects.get_or_create(
        groupe=groupe, utilisateur=request.user,
        defaults={'quantite': quantite, 'a_confirme': True},
    )
    if not created:
        return JsonResponse({'success': False, 'message': 'Vous participez déjà à ce groupe.'})
 
    nb_confirmes = groupe.participants.filter(a_confirme=True).count()
    devient_complet = nb_confirmes >= groupe.nb_participants_min
 
    if devient_complet and groupe.statut == 'ouvert':
        groupe.statut = 'complet'
        groupe.save(update_fields=['statut'])
 
        # Notifier tous les participants que le groupe est complet
        try:
            from apps_core.views_notifications import creer_notification_masse
            participants_users = [p.utilisateur for p in groupe.participants.filter(a_confirme=True)]
            creer_notification_masse(
                utilisateurs_qs=participants_users,
                type_notification='promotion',
                titre="🎉 Groupe d'achat complet !",
                message=f"Le groupe pour « {groupe.produit.titre} » a atteint son objectif. "
                        f"Prix débloqué : {groupe.prix_groupe:,.0f} FCFA !",
                lien=f"/achats-groupes/{groupe.pk}/",
            )
        except Exception:
            pass
 
    return JsonResponse({
        'success':        True,
        'message':        f"Vous avez rejoint le groupe ! ({nb_confirmes}/{groupe.nb_participants_min})",
        'nb_confirmes':   nb_confirmes,
        'nb_min':         groupe.nb_participants_min,
        'progression':    min(100, round((nb_confirmes / groupe.nb_participants_min) * 100)),
        'devient_complet': devient_complet,
        'prix_actuel':    float(groupe.prix_actuel),   # ✅ sans parenthèses
    })
 
 
@login_required
@require_POST
def ajax_quitter_groupe(request, pk):
    """L'utilisateur quitte un groupe (uniquement si pas encore complet)."""
    groupe = get_object_or_404(GroupeAchat, pk=pk)
    participant = ParticipantGroupeAchat.objects.filter(groupe=groupe, utilisateur=request.user).first()
 
    if not participant:
        return JsonResponse({'success': False, 'message': 'Vous ne participez pas à ce groupe.'})
 
    if groupe.statut != 'ouvert':
        return JsonResponse({'success': False, 'message': 'Impossible de quitter un groupe déjà complet ou traité.'})
 
    participant.delete()
 
    nb_confirmes = groupe.participants.filter(a_confirme=True).count()
    return JsonResponse({
        'success':      True,
        'message':      "Vous avez quitté le groupe.",
        'nb_confirmes': nb_confirmes,
        'nb_min':       groupe.nb_participants_min,
    })

 
# =============================================================================
# VENDEUR — Gestion des groupes sur SES produits uniquement
# =============================================================================
 
@login_required
def mes_groupes_achat(request):
    """Liste des groupes d'achat créés par le vendeur connecté."""
    if not request.user.peut_vendre:
        messages.warning(request, "Réservé aux vendeurs.")
        return redirect('apps_core:tableau_de_bord')
 
    qs = GroupeAchat.objects.filter(
        createur=request.user
    ).select_related('produit').annotate(
        nb_participants=Count('participants', filter=Q(participants__a_confirme=True))
    ).order_by('-date_creation')
 
    statut = request.GET.get('statut', '')
    if statut:
        qs = qs.filter(statut=statut)
 
    paginator = Paginator(qs, 15)
    groupes   = paginator.get_page(request.GET.get('page', 1))
 
    return render(request, 'apps_marketplace/groupe_achat/mes_groupes.html', {
        'groupes':    groupes,
        'statut':     statut,
        'statuts':    GroupeAchat.STATUT_CHOICES,
        'page_titre': 'Mes achats groupés',
    })
 
 
@login_required
def creer_groupe_achat(request):
    """
    Création d'un groupe d'achat.
 
    RÈGLE MÉTIER : le select des produits n'affiche QUE les produits
    appartenant au vendeur connecté (boutique ou individuel), actifs,
    et avec autorise_achat_groupe=True. Vérification redondante en POST
    pour empêcher toute injection d'un produit_id appartenant à un autre
    vendeur via une requête forgée.
    """
    if not request.user.peut_vendre:
        messages.warning(request, "Vous devez être vendeur pour créer un achat groupé.")
        return redirect('apps_core:devenir_vendeur')
 
    mes_produits = _produits_du_vendeur(request.user)
 
    if not mes_produits.exists():
        messages.info(
            request,
            "Aucun de vos produits n'autorise l'achat groupé pour le moment. "
            "Activez l'option « Autoriser l'achat groupé » sur un produit pour commencer."
        )
        return redirect('apps_core:mes_produits')
 
    if request.method == 'POST':
        produit_id = request.POST.get('produit')
 
        # ── Vérification stricte : le produit doit appartenir au vendeur ──
        produit = mes_produits.filter(pk=produit_id).first()
        if not produit:
            messages.error(
                request,
                "Produit invalide : vous ne pouvez créer un achat groupé que sur vos propres produits."
            )
            return redirect('apps_marketplace:creer_groupe_achat')
 
        try:
            prix_groupe              = Decimal(request.POST.get('prix_groupe', '0'))
            nb_participants_min      = int(request.POST.get('nb_participants_min', 5))
            nb_participants_max_str  = request.POST.get('nb_participants_max', '').strip()
            quantite_par_participant = int(request.POST.get('quantite_par_participant', 1))
            duree_jours              = int(request.POST.get('duree_jours', 3))
 
            if prix_groupe <= 0 or prix_groupe >= produit.prix:
                messages.error(request, "Le prix groupé doit être positif et inférieur au prix normal.")
                return redirect('apps_marketplace:creer_groupe_achat')
 
            if nb_participants_min < 2:
                messages.error(request, "Il faut au minimum 2 participants pour un achat groupé.")
                return redirect('apps_marketplace:creer_groupe_achat')
 
            nb_participants_max = int(nb_participants_max_str) if nb_participants_max_str else None
            if nb_participants_max and nb_participants_max < nb_participants_min:
                messages.error(request, "Le maximum de participants doit être ≥ au minimum.")
                return redirect('apps_marketplace:creer_groupe_achat')
 
            if duree_jours < 1 or duree_jours > 30:
                duree_jours = 3
 
        except (ValueError, TypeError):
            messages.error(request, "Données invalides. Veuillez vérifier le formulaire.")
            return redirect('apps_marketplace:creer_groupe_achat')
 
        groupe = GroupeAchat.objects.create(
            produit=produit,
            createur=request.user,
            prix_normal=produit.prix,
            prix_groupe=prix_groupe,
            nb_participants_min=nb_participants_min,
            nb_participants_max=nb_participants_max,
            quantite_par_participant=quantite_par_participant,
            date_expiration=timezone.now() + timezone.timedelta(days=duree_jours),
            lien_partage=f"groupe-{uuid_lib.uuid4().hex[:10]}",
        )
 
        messages.success(
            request,
            f"Groupe d'achat créé pour « {produit.titre} » ! "
            f"Partagez le lien pour atteindre {nb_participants_min} participants."
        )
        return redirect('apps_marketplace:groupe_detail', pk=groupe.pk)
 
    return render(request, 'apps_marketplace/groupe_achat/groupe_form.html', {
        'mes_produits': mes_produits,
        'mode':         'creation',
        'page_titre':   'Créer un achat groupé',
    })


@login_required
def modifier_groupe_achat(request, pk):
    """
    Modification d'un groupe d'achat existant.
    Seul le créateur (ou un admin) peut modifier, et uniquement si le
    groupe est encore 'ouvert' (pas de modification après complétion).
    """
    groupe = get_object_or_404(GroupeAchat, pk=pk)
 
    if not _peut_gerer_groupe(request.user, groupe):
        messages.error(request, "Vous ne pouvez modifier que vos propres groupes d'achat.")
        return redirect('apps_marketplace:mes_groupes_achat')
 
    if groupe.statut != 'ouvert':
        messages.warning(request, "Seuls les groupes encore ouverts peuvent être modifiés.")
        return redirect('apps_marketplace:groupe_detail', pk=pk)
 
    if request.method == 'POST':
        try:
            nb_participants_max_str = request.POST.get('nb_participants_max', '').strip()
            groupe.nb_participants_max = int(nb_participants_max_str) if nb_participants_max_str else None
 
            duree_jours = int(request.POST.get('duree_jours', 0))
            if duree_jours > 0:
                groupe.date_expiration = timezone.now() + timezone.timedelta(days=duree_jours)
 
            groupe.save()
            messages.success(request, "Groupe d'achat mis à jour.")
            return redirect('apps_marketplace:groupe_detail', pk=pk)
 
        except (ValueError, TypeError):
            messages.error(request, "Données invalides.")
 
    return render(request, 'apps_marketplace/groupe_achat/groupe_form.html', {
        'groupe':     groupe,
        'mode':       'edition',
        'page_titre': f"Modifier — {groupe.produit.titre}",
    })
 
 
@login_required
@require_POST
def annuler_groupe_achat(request, pk):
    """Annule un groupe d'achat (créateur ou admin)."""
    groupe = get_object_or_404(GroupeAchat, pk=pk)
 
    if not _peut_gerer_groupe(request.user, groupe):
        messages.error(request, "Action non autorisée.")
        return redirect('apps_marketplace:mes_groupes_achat')
 
    if groupe.statut == 'traite':
        messages.error(request, "Impossible d'annuler un groupe déjà traité (commandes créées).")
        return redirect('apps_marketplace:groupe_detail', pk=pk)
 
    groupe.statut = 'expire'
    groupe.save(update_fields=['statut'])
 
    # Notifier les participants
    try:
        from apps_core.views_notifications import creer_notification_masse
        participants_users = [p.utilisateur for p in groupe.participants.filter(a_confirme=True)]
        if participants_users:
            creer_notification_masse(
                utilisateurs_qs=participants_users,
                type_notification='systeme',
                titre="Achat groupé annulé",
                message=f"Le groupe d'achat pour « {groupe.produit.titre} » a été annulé par le vendeur.",
                lien=f"/achats-groupes/{groupe.pk}/",
            )
    except Exception:
        pass
 
    messages.success(request, "Groupe d'achat annulé.")
    return redirect('apps_marketplace:mes_groupes_achat')
 
 
# =============================================================================
# SYSTÈME — Finalisation des groupes complets/expirés
# =============================================================================
 
@login_required
def finaliser_groupe(request, pk):
    """
    Transforme un groupe 'complet' en commandes réelles pour chaque
    participant confirmé. Le créateur du groupe ou un admin déclenche
    cette action manuellement (peut aussi être automatisé via une tâche
    planifiée appelant la même logique).
    """
    groupe = get_object_or_404(GroupeAchat, pk=pk)
 
    if not _peut_gerer_groupe(request.user, groupe):
        messages.error(request, "Action non autorisée.")
        return redirect('apps_marketplace:mes_groupes_achat')
 
    if groupe.statut != 'complet':
        messages.error(request, "Ce groupe n'est pas encore complet.")
        return redirect('apps_marketplace:groupe_detail', pk=pk)
 
    participants = groupe.participants.filter(a_confirme=True, commande__isnull=True)
 
    nb_commandes_creees = 0
    with transaction.atomic():
        for participant in participants:
            user = participant.utilisateur
            adresse = getattr(user, 'adresse', '') or 'Adresse à compléter'
 
            commande = Commande.objects.create(
                utilisateur=user,
                boutique=groupe.produit.vendeur.boutique if groupe.produit.vendeur.a_boutique else None,
                source='groupe',
                adresse_facturation=adresse,
                adresse_livraison=adresse,
                sous_total=groupe.prix_groupe * participant.quantite,
                montant_total=groupe.prix_groupe * participant.quantite,
            )
 
            ArticleCommande.objects.create(
                commande=commande,
                produit=groupe.produit,
                quantite=participant.quantite,
                prix_unitaire=groupe.prix_groupe,
            )
            commande.calculer_total()
 
            participant.commande = commande
            participant.save(update_fields=['commande'])
            nb_commandes_creees += 1
 
        groupe.statut = 'traite'
        groupe.save(update_fields=['statut'])
 
    # Notifier les participants
    try:
        from apps_core.views_notifications import creer_notification_masse
        participants_users = [p.utilisateur for p in groupe.participants.filter(a_confirme=True)]
        creer_notification_masse(
            utilisateurs_qs=participants_users,
            type_notification='commande',
            titre="Votre achat groupé est confirmé !",
            message=f"Votre commande pour « {groupe.produit.titre} » a été créée "
                    f"au prix groupé de {groupe.prix_groupe:,.0f} FCFA.",
            lien='/commandes/',
        )
    except Exception:
        pass
 
    messages.success(request, f"{nb_commandes_creees} commande(s) créée(s) avec succès.")
    return redirect('apps_marketplace:mes_groupes_achat')
 
 
@login_required
def admin_finaliser_groupes_expires(request):
    """
    Vue admin pour traiter en masse les groupes expirés et complets.
    Les groupes 'complet' sont finalisés, les groupes 'ouvert' expirés
    passent en statut 'expire'.
    """
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')
 
    now = timezone.now()
 
    # Expirer les groupes ouverts dont la date est dépassée
    groupes_a_expirer = GroupeAchat.objects.filter(statut='ouvert', date_expiration__lt=now)
    nb_expires = groupes_a_expirer.update(statut='expire')
 
    # Lister les groupes complets en attente de finalisation
    groupes_a_finaliser = GroupeAchat.objects.filter(statut='complet').select_related('produit', 'createur')
 
    if request.method == 'POST' and request.POST.get('action') == 'finaliser_tout':
        nb_finalises = 0
        for groupe in groupes_a_finaliser:
            participants = groupe.participants.filter(a_confirme=True, commande__isnull=True)
            with transaction.atomic():
                for participant in participants:
                    user = participant.utilisateur
                    adresse = getattr(user, 'adresse', '') or 'Adresse à compléter'
                    commande = Commande.objects.create(
                        utilisateur=user,
                        boutique=groupe.produit.vendeur.boutique if groupe.produit.vendeur.a_boutique else None,
                        source='groupe',
                        adresse_facturation=adresse,
                        adresse_livraison=adresse,
                        sous_total=groupe.prix_groupe * participant.quantite,
                        montant_total=groupe.prix_groupe * participant.quantite,
                    )
                    ArticleCommande.objects.create(
                        commande=commande, produit=groupe.produit,
                        quantite=participant.quantite, prix_unitaire=groupe.prix_groupe,
                    )
                    commande.calculer_total()
                    participant.commande = commande
                    participant.save(update_fields=['commande'])
                groupe.statut = 'traite'
                groupe.save(update_fields=['statut'])
            nb_finalises += 1
 
        messages.success(request, f"{nb_finalises} groupe(s) finalisé(s), {nb_expires} groupe(s) expiré(s).")
        return redirect('apps_marketplace:admin_finaliser_groupes_expires')
 
    return render(request, 'apps_marketplace/groupe_achat/admin_finaliser_groupes.html', {
        'groupes_a_finaliser': groupes_a_finaliser,
        'nb_expires':          nb_expires,
        'page_titre':          'Finalisation des achats groupés',
    })
 
 
@login_required
def admin_groupes_liste(request):
    """Vue admin de tous les groupes d'achat de la plateforme."""
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')
 
    qs = GroupeAchat.objects.select_related('produit', 'createur').annotate(
        nb_participants=Count('participants', filter=Q(participants__a_confirme=True))
    ).order_by('-date_creation')
 
    statut = request.GET.get('statut', '')
    if statut:
        qs = qs.filter(statut=statut)
 
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(Q(produit__titre__icontains=q) | Q(createur__username__icontains=q))
 
    paginator = Paginator(qs, 25)
    groupes   = paginator.get_page(request.GET.get('page', 1))
 
    return render(request, 'apps_marketplace/groupe_achat/admin_groupes_achat_liste.html', {
        'groupes':    groupes,
        'statut':     statut,
        'q':          q,
        'statuts':    GroupeAchat.STATUT_CHOICES,
        'page_titre': 'Gestion des achats groupés',
    })
 
 
# =============================================================================
# AJAX
# =============================================================================
 
@require_GET
def ajax_statut_groupe(request, pk):
    """Retourne le statut et la progression d'un groupe (polling temps réel)."""
    groupe = get_object_or_404(GroupeAchat, pk=pk)
    nb_confirmes = groupe.participants.filter(a_confirme=True).count()
 
    return JsonResponse({
        'statut':       groupe.statut,
        'label':        groupe.get_statut_display(),
        'nb_confirmes': nb_confirmes,
        'nb_min':       groupe.nb_participants_min,
        'nb_max':       groupe.nb_participants_max,
        'progression':  min(100, round((nb_confirmes / groupe.nb_participants_min) * 100)) if groupe.nb_participants_min else 0,
        'prix_actuel':  float(groupe.prix_actuel()),
        'est_complet':  groupe.est_complet(),
        'est_expire':   timezone.now() > groupe.date_expiration,
        'temps_restant_secondes': max(0, int((groupe.date_expiration - timezone.now()).total_seconds())),
    })
 
 
 


 
 
 



