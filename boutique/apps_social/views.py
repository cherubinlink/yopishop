
# ===========================================================================
# apps_social/views_profil.py
# Vues — Section 1 : Profil Social + Abonnements
#
# Couvre :
#   PUBLIC
#     - profil_public          : page publique @username
#     - abonnes_liste          : liste des abonnés
#     - abonnements_liste      : liste des abonnements
#   UTILISATEUR CONNECTÉ
#     - mon_profil_social      : édition de son propre profil social
#     - ajax_toggle_abonnement : s'abonner / se désabonner (AJAX)
#     - mes_abonnes            : ses propres abonnés
#     - mes_abonnements        : ses propres abonnements
#     - ajax_suggestions       : suggestions d'abonnement
#   ADMIN
#     - admin_profils_liste    : tous les profils + stats
# ===========================================================================


from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count, Avg, F
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
 
from apps_social.models import (
    ProfilSocial, AbonnementSocial,LiveVente, ProduitLive, 
    ReservationLive, ChatLive, ParticipantLive,Story, VueStory,
    VideoCommerce, ProduitVideo, CommentaireVideo, ProgrammeInfluenceur,
    ConversionInfluenceur
)
from apps_core.models import (
    Utilisateur, Produit
)




# =============================================================================
# HELPERS
# =============================================================================
 
def _get_or_create_profil(user):
    """Retourne le profil social d'un utilisateur, le crée si inexistant."""
    profil, _ = ProfilSocial.objects.get_or_create(utilisateur=user)
    return profil
 
 
def _est_abonne(user, cible):
    """Vérifie si user suit cible."""
    if not user.is_authenticated:
        return False
    return AbonnementSocial.objects.filter(abonne=user, suivi=cible).exists()



# =============================================================================
# PUBLIC
# =============================================================================
 
def profil_public(request, username):
    """
    Page publique d'un profil social (@username).
    """
    utilisateur = get_object_or_404(Utilisateur, username=username)
    profil      = _get_or_create_profil(utilisateur)

    est_proprietaire = request.user.is_authenticated and request.user == utilisateur
    if not profil.est_public and not est_proprietaire and not request.user.is_staff:
        return render(request, 'apps_social/profil_prive.html', {
            'profil':     profil,
            'page_titre': f"@{username} — Profil privé",
        })

    je_suis = _est_abonne(request.user, utilisateur)

    publications = []
    try:
        from .models import Publication
        publications_qs = Publication.objects.filter(
            auteur=utilisateur, est_archive=False
        ).order_by('-date_creation')
        paginator = Paginator(publications_qs, 12)
        publications = paginator.get_page(request.GET.get('page', 1))
    except Exception:
        pass

    # Produits de la boutique (NOUVEAU)
    produits_boutique = []
    if utilisateur.peut_vendre:
        from apps_core.models import Produit  # adapte le chemin si besoin
        produits_boutique = Produit.objects.filter(
            vendeur=utilisateur, est_actif=True
        ).select_related('categorie').order_by('-date_creation')[:12]

    abonnes_communs = []
    if request.user.is_authenticated and not est_proprietaire:
        abonnes_communs = AbonnementSocial.objects.filter(
            suivi=utilisateur,
            abonne__in=AbonnementSocial.objects.filter(
                abonne=request.user
            ).values('suivi')
        ).select_related('abonne')[:5]

    return render(request, 'apps_social/profil_public.html', {
        'profil':             profil,
        'utilisateur':        utilisateur,
        'publications':       publications,
        'produits_boutique':  produits_boutique,   # NOUVEAU
        'je_suis':            je_suis,
        'est_proprietaire':   est_proprietaire,
        'abonnes_communs':    abonnes_communs,
        'page_titre':         f"@{username}",
    })


def abonnes_liste(request, username):
    """Liste publique des abonnés d'un utilisateur."""
    utilisateur = get_object_or_404(Utilisateur, username=username)
    profil      = _get_or_create_profil(utilisateur)
 
    if not profil.est_public and not (request.user.is_authenticated and request.user == utilisateur):
        messages.error(request, "Ce profil est privé.")
        return redirect('apps_social:profil_public', username=username)
 
    qs = AbonnementSocial.objects.filter(
        suivi=utilisateur
    ).select_related('abonne').order_by('-date_abonnement')
 
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(abonne__username__icontains=q)
 
    paginator = Paginator(qs, 24)
    abonnes   = paginator.get_page(request.GET.get('page', 1))
 
    return render(request, 'apps_social/abonnes_liste.html', {
        'profil':      profil,
        'utilisateur': utilisateur,
        'abonnes':     abonnes,
        'q':           q,
        'page_titre':  f"Abonnés de @{username}",
    })

@login_required
def modifier_profil_social(request):
    """
    Formulaire d'édition du profil social : avatar, bannière,
    biographie, lien externe, visibilité du compte.
    """
    profil      = _get_or_create_profil(request.user)
    utilisateur = request.user

    if request.method == 'POST':
        biographie = request.POST.get('biographie', '').strip()[:300]
        lien_bio   = request.POST.get('lien_bio', '').strip()
        est_public = request.POST.get('est_public') == 'on'

        erreurs = []

        # Lien externe : validation simple
        if lien_bio and not lien_bio.startswith(('http://', 'https://')):
            lien_bio = f"https://{lien_bio}"

        # Avatar
        avatar = request.FILES.get('avatar')
        if avatar:
            if avatar.size > 5 * 1024 * 1024:
                erreurs.append("L'avatar ne doit pas dépasser 5 Mo.")
            elif not avatar.content_type.startswith('image/'):
                erreurs.append("L'avatar doit être une image.")
            else:
                utilisateur.avatar = avatar

        # Bannière
        banniere = request.FILES.get('banniere')
        if banniere:
            if banniere.size > 8 * 1024 * 1024:
                erreurs.append("La bannière ne doit pas dépasser 8 Mo.")
            elif not banniere.content_type.startswith('image/'):
                erreurs.append("La bannière doit être une image.")
            else:
                utilisateur.banniere = banniere

        # Suppression avatar/bannière si demandé
        if request.POST.get('supprimer_avatar') == '1':
            utilisateur.avatar.delete(save=False)
            utilisateur.avatar = None
        if request.POST.get('supprimer_banniere') == '1':
            utilisateur.banniere.delete(save=False)
            utilisateur.banniere = None

        if erreurs:
            for e in erreurs:
                messages.error(request, e)
            return render(request, 'apps_social/modifier_profil_social.html', {
                'profil':      profil,
                'utilisateur': utilisateur,
                'page_titre':  'Modifier mon profil',
            })

        utilisateur.save()
        profil.biographie = biographie
        profil.lien_bio   = lien_bio
        profil.est_public = est_public
        profil.save()

        messages.success(request, "Profil mis à jour avec succès.")
        return redirect('apps_social:profil_public', username=utilisateur.username)

    return render(request, 'apps_social/modifier_profil_social.html', {
        'profil':      profil,
        'utilisateur': utilisateur,
        'page_titre':  'Modifier mon profil',
    })



# =============================================================================
# UTILISATEUR CONNECTÉ
# =============================================================================
 
@login_required
def mon_profil_social(request):
    """Édition du profil social de l'utilisateur connecté."""
    profil = _get_or_create_profil(request.user)

    if request.method == 'POST':
        biographie = request.POST.get('biographie', '').strip()[:300]
        lien_bio   = request.POST.get('lien_bio', '').strip()
        est_public = request.POST.get('est_public') == 'on'

        profil.biographie = biographie
        profil.lien_bio   = lien_bio
        profil.est_public = est_public
        profil.save()

        messages.success(request, "Profil social mis à jour.")
        return redirect('apps_social:profil_public', username=request.user.username)

    # Produits de la boutique (si l'utilisateur peut vendre)
    produits_boutique = []
    if request.user.peut_vendre:
        from apps_core.models import Produit  # adapte le chemin d'import si besoin
        produits_boutique = Produit.objects.filter(
            vendeur=request.user,
            est_actif=True,
        ).select_related('categorie').order_by('-date_creation')[:12]

    return render(request, 'apps_social/mon_profil_social.html', {
        'profil':            profil,
        'produits_boutique': produits_boutique,
        'page_titre':        'Mon profil social',
    })

@login_required
@require_POST
@transaction.atomic
def ajax_toggle_abonnement(request, username):
    """
    S'abonner / se désabonner d'un utilisateur (AJAX).
    Met à jour les compteurs nb_abonnes / nb_abonnements sur ProfilSocial.
    """
    cible = get_object_or_404(Utilisateur, username=username)
 
    if cible == request.user:
        return JsonResponse({
            'success': False,
            'message': "Vous ne pouvez pas vous abonner à vous-même."
        }, status=400)
 
    abonnement = AbonnementSocial.objects.filter(
        abonne=request.user, suivi=cible
    ).first()
 
    if abonnement:
        # Se désabonner
        abonnement.delete()
        je_suis = False
        message = f"Vous ne suivez plus @{cible.username}."
 
        # Mettre à jour les compteurs
        ProfilSocial.objects.filter(utilisateur=cible).update(
            nb_abonnes=max(0, (
                ProfilSocial.objects.filter(utilisateur=cible).values_list('nb_abonnes', flat=True).first() or 1
            ) - 1)
        )
        ProfilSocial.objects.filter(utilisateur=request.user).update(
            nb_abonnements=max(0, (
                ProfilSocial.objects.filter(utilisateur=request.user).values_list('nb_abonnements', flat=True).first() or 1
            ) - 1)
        )
    else:
        # S'abonner
        AbonnementSocial.objects.create(abonne=request.user, suivi=cible)
        je_suis = True
        message = f"Vous suivez maintenant @{cible.username}."
 
        # Mettre à jour les compteurs
        profil_cible, _ = ProfilSocial.objects.get_or_create(utilisateur=cible)
        profil_cible.nb_abonnes = AbonnementSocial.objects.filter(suivi=cible).count()
        profil_cible.save(update_fields=['nb_abonnes'])
 
        profil_user, _ = ProfilSocial.objects.get_or_create(utilisateur=request.user)
        profil_user.nb_abonnements = AbonnementSocial.objects.filter(abonne=request.user).count()
        profil_user.save(update_fields=['nb_abonnements'])
 
        # Notification à la cible
        
        from apps_core.views_notifications import creer_notification
        creer_notification(
            utilisateur=cible,
            type_notification='social',
            titre=f"@{request.user.username} vous suit !",
            message=f"{request.user.username} s'est abonné à votre profil.",
            lien=f"/social/@{request.user.username}/",
        )
        
 
    # Compter après modification
    nb_abonnes = AbonnementSocial.objects.filter(suivi=cible).count()
 
    return JsonResponse({
        'success':    True,
        'je_suis':    je_suis,
        'message':    message,
        'nb_abonnes': nb_abonnes,
        'label_btn':  "Ne plus suivre" if je_suis else "Suivre",
    })

 
@login_required
def mes_abonnes(request):
    """Liste de ses propres abonnés."""
    qs = AbonnementSocial.objects.filter(
        suivi=request.user
    ).select_related('abonne').order_by('-date_abonnement')
 
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(abonne__username__icontains=q)
 
    # Parmi mes abonnés, lesquels je suis en retour
    mes_suivis = set(
        AbonnementSocial.objects.filter(
            abonne=request.user
        ).values_list('suivi_id', flat=True)
    )
 
    paginator = Paginator(qs, 24)
    abonnes   = paginator.get_page(request.GET.get('page', 1))
 
    return render(request, 'apps_social/mes_abonnes.html', {
        'abonnes':    abonnes,
        'mes_suivis': mes_suivis,
        'q':          q,
        'page_titre': 'Mes abonnés',
    })



@login_required
def mes_abonnements(request):
    """Liste des comptes que l'utilisateur suit."""
    qs = AbonnementSocial.objects.filter(
        abonne=request.user
    ).select_related('suivi').order_by('-date_abonnement')
 
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(suivi__username__icontains=q)
 
    paginator   = Paginator(qs, 24)
    abonnements = paginator.get_page(request.GET.get('page', 1))
 
    return render(request, 'apps_social/mes_abonnements.html', {
        'abonnements': abonnements,
        'q':           q,
        'page_titre':  'Mes abonnements',
    })


 
@login_required
@require_GET
def ajax_suggestions(request):
    """
    Suggestions d'abonnement (AJAX).
    Algorithme : vendeurs que les gens que je suis suivent aussi,
    mais que je ne suis pas encore.
    """
    mes_suivis_ids = AbonnementSocial.objects.filter(
        abonne=request.user
    ).values_list('suivi_id', flat=True)
 
    # Personnes suivies par mes abonnements
    suggestions_ids = AbonnementSocial.objects.filter(
        abonne__in=mes_suivis_ids
    ).exclude(
        suivi=request.user
    ).exclude(
        suivi__in=mes_suivis_ids
    ).values_list('suivi_id', flat=True).distinct()[:10]
 
    suggestions = Utilisateur.objects.filter(
        pk__in=suggestions_ids
    ).select_related('profil_social')[:6]
 
    data = [{
        'username':     u.username,
        'nom_complet':  u.get_full_name() or u.username,
        'avatar_url':   u.avatar.url if hasattr(u, 'avatar') and u.avatar else '',
        'nb_abonnes':   getattr(getattr(u, 'profil_social', None), 'nb_abonnes', 0),
        'est_verifie':  getattr(getattr(u, 'profil_social', None), 'est_verifie', False),
        'profil_url':   f"/social/@{u.username}/",
    } for u in suggestions]
 
    return JsonResponse({'suggestions': data})

 
# =============================================================================
# ADMIN
# =============================================================================
 
@login_required
def admin_profils_liste(request):
    """Vue admin de tous les profils sociaux."""
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')
 
    qs = ProfilSocial.objects.select_related('utilisateur').order_by(
        '-nb_abonnes', '-nb_publications'
    )
 
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(
            Q(utilisateur__username__icontains=q) |
            Q(utilisateur__email__icontains=q) |
            Q(biographie__icontains=q)
        )
 
    est_verifie = request.GET.get('verifie', '')
    if est_verifie == '1':
        qs = qs.filter(est_verifie=True)
    elif est_verifie == '0':
        qs = qs.filter(est_verifie=False)
 
    est_public = request.GET.get('public', '')
    if est_public == '1':
        qs = qs.filter(est_public=True)
    elif est_public == '0':
        qs = qs.filter(est_public=False)
 
    stats = {
        'total':    ProfilSocial.objects.count(),
        'verifies': ProfilSocial.objects.filter(est_verifie=True).count(),
        'prives':   ProfilSocial.objects.filter(est_public=False).count(),
        'abonnements_total': AbonnementSocial.objects.count(),
    }
 
    paginator = Paginator(qs, 30)
    profils   = paginator.get_page(request.GET.get('page', 1))
 
    return render(request, 'apps_social/admin/profils_liste.html', {
        'profils':      profils,
        'stats':        stats,
        'q':            q,
        'est_verifie':  est_verifie,
        'est_public':   est_public,
        'page_titre':   'Gestion des profils sociaux',
    })


@login_required
@require_POST
def admin_toggle_verifie(request, username):
    """Certifier / décertifier un profil (admin uniquement)."""
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)
 
    profil = get_object_or_404(ProfilSocial, utilisateur__username=username)
    profil.est_verifie = not profil.est_verifie
    profil.save(update_fields=['est_verifie'])
 
    return JsonResponse({
        'success':     True,
        'est_verifie': profil.est_verifie,
        'message':     f"@{username} {'certifié ✓' if profil.est_verifie else 'décertifié'}.",
    })


 
# =============================================================================
# HELPERS
# =============================================================================

def _produits_du_vendeur(user):
    """Produits actifs appartenant au vendeur connecté."""
    return Produit.objects.filter(
        vendeur=user, est_actif=True
    ).select_related('categorie').order_by('titre')


def _peut_gerer_live(user, live):
    return user.is_staff or live.vendeur == user


def _enregistrer_participant(user, live):
    """Crée ou récupère la participation d'un utilisateur à un live."""
    participant, created = ParticipantLive.objects.get_or_create(
        live=live, utilisateur=user,
        defaults={'date_entree': timezone.now()}
    )
    if not created and participant.date_sortie:
        participant.date_sortie = None
        participant.est_connecte = True
        participant.save(update_fields=['date_sortie', 'est_connecte'])
    return participant, created


# =============================================================================
# PUBLIC — Liste et détail
# =============================================================================

def lives_liste(request):
    """Liste publique des lives actifs et planifiés."""
    now = timezone.now()

    en_cours = LiveVente.objects.filter(
        statut='en_cours'
    ).select_related('vendeur').annotate(
        nb_actifs=Count('participants', filter=Q(participants__date_sortie__isnull=True))
    ).order_by('-nb_actifs')

    planifies = LiveVente.objects.filter(
        statut='planifie', date_debut__gt=now
    ).select_related('vendeur').order_by('date_debut')

    replays = LiveVente.objects.filter(
        statut='termine'
    ).exclude(
        url_replay=''
    ).select_related('vendeur').order_by('-date_fin_reelle')

    paginator = Paginator(replays, 12)
    replays   = paginator.get_page(request.GET.get('page', 1))

    q = request.GET.get('q', '')
    if q:
        en_cours = en_cours.filter(
            Q(titre__icontains=q) | Q(vendeur__username__icontains=q)
        )
        planifies = planifies.filter(
            Q(titre__icontains=q) | Q(vendeur__username__icontains=q)
        )

    return render(request, 'apps_social/lives/lives_liste.html', {
        'en_direct':  en_cours,   # nom de variable de contexte conservé pour le template existant
        'planifies':  planifies,
        'replays':    replays,
        'q':          q,
        'page_titre': 'Lives — YopiShop',
    })


def live_detail(request, pk):
    """Page d'un live en cours ou passé."""
    live = get_object_or_404(
        LiveVente.objects.select_related('vendeur'),
        pk=pk
    )

    if not request.user.is_authenticated or request.user != live.vendeur:
        LiveVente.objects.filter(pk=pk).update(nb_vues_total=live.nb_vues_total + 1)

    produits_live = live.produits_live.filter(
        est_disponible=True
    ).select_related('produit').order_by('ordre')

    commentaires = live.messages.exclude(
        type_message='reaction'
    ).select_related('utilisateur').order_by('-date_creation')[:50]

    nb_participants_actifs = live.participants.filter(
        date_sortie__isnull=True
    ).count()

    ma_participation = None
    if request.user.is_authenticated:
        ma_participation = live.participants.filter(
            utilisateur=request.user
        ).first()

    est_proprietaire = (
        request.user.is_authenticated and request.user == live.vendeur
    )

    return render(request, 'apps_social/lives/live_detail.html', {
        'live':                   live,
        'produits_live':          produits_live,
        'commentaires':           commentaires,
        'nb_participants_actifs': nb_participants_actifs,
        'ma_participation':       ma_participation,
        'est_proprietaire':       est_proprietaire,
        'est_active':             live.statut == 'en_cours',
        'page_titre':             live.titre,
    })


def replay_detail(request, pk):
    """Page de replay d'un live terminé (le replay vit directement sur LiveVente)."""
    live = get_object_or_404(
        LiveVente.objects.select_related('vendeur'),
        pk=pk, statut='termine'
    )
    if not live.url_replay:
        raise Http404("Ce replay n'est pas disponible.")

    LiveVente.objects.filter(pk=pk).update(nb_vues_total=live.nb_vues_total + 1)

    return render(request, 'apps_social/lives/replay_detail.html', {
        'live':       live,
        'page_titre': f"Replay — {live.titre}",
    })



# =============================================================================
# AJAX PUBLIC — Chat, Réactions, Achat, Participants
# =============================================================================

@login_required
@require_POST
def ajax_rejoindre_live(request, pk):
    """L'utilisateur entre dans le live."""
    live = get_object_or_404(LiveVente, pk=pk, statut='en_cours')

    if live.nb_participants_max:
        nb_actifs = live.participants.filter(date_sortie__isnull=True).count()
        if nb_actifs >= live.nb_participants_max:
            return JsonResponse({
                'success': False,
                'message': f"Live complet ({live.nb_participants_max} participants max)."
            }, status=400)

    participant, created = _enregistrer_participant(request.user, live)

    return JsonResponse({
        'success':   True,
        'created':   created,
        'nb_actifs': live.participants.filter(date_sortie__isnull=True).count(),
    })


@login_required
@require_POST
def ajax_quitter_live(request, pk):
    """L'utilisateur quitte le live."""
    live        = get_object_or_404(LiveVente, pk=pk)
    participant = ParticipantLive.objects.filter(
        live=live, utilisateur=request.user, date_sortie__isnull=True
    ).first()

    if participant:
        participant.date_sortie  = timezone.now()
        participant.est_connecte = False
        participant.save(update_fields=['date_sortie', 'est_connecte'])

    return JsonResponse({
        'success':   True,
        'nb_actifs': live.participants.filter(date_sortie__isnull=True).count(),
    })


@login_required
@require_POST
def ajax_poster_commentaire(request, pk):
    try:
        live = get_object_or_404(LiveVente, pk=pk, statut='en_cours')

        if not live.autoriser_chat:
            return JsonResponse({'success': False, 'message': "Le chat est désactivé."}, status=400)

        contenu = request.POST.get('contenu', '').strip()
        if not contenu or len(contenu) > 300:
            return JsonResponse({'success': False, 'message': "Message invalide (1-300 caractères)."}, status=400)

        est_question = request.POST.get('est_question') == '1'
        if est_question and not live.autoriser_questions:
            return JsonResponse({'success': False, 'message': "Les questions sont désactivées."}, status=400)

        message = ChatLive.objects.create(
            live=live,
            utilisateur=request.user,
            contenu=contenu,
            type_message='question' if est_question else 'message',
        )

        ParticipantLive.objects.filter(live=live, utilisateur=request.user).update(
            nb_messages=F('nb_messages') + 1
        )

    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Erreur ajax_poster_commentaire pk=%s", pk)
        return JsonResponse({'success': False, 'message': f"Erreur : {e}"}, status=400)

    return JsonResponse({
        'success': True,
        'commentaire': {
            'pk':       message.pk,
            'username': request.user.username,
            'contenu':  message.contenu,
            'type':     message.type_message,
            'date':     message.date_creation.strftime('%H:%M:%S'),
        }
    })

@login_required
@require_POST
def ajax_reaction(request, pk):
    """
    Envoyer une réaction emoji dans le live.
    Stockée comme un ChatLive de type 'reaction' (pas de modèle dédié).
    """
    live  = get_object_or_404(LiveVente, pk=pk, statut='en_cours')

    if not live.autoriser_reactions:
        return JsonResponse({'success': False, 'message': "Les réactions sont désactivées."}, status=400)

    emoji = request.POST.get('emoji', '❤️')
    EMOJIS_VALIDES = ['❤️', '🔥', '👏', '😍', '💰', '🎉']
    if emoji not in EMOJIS_VALIDES:
        emoji = '❤️'

    ChatLive.objects.create(
        live=live,
        utilisateur=request.user,
        contenu=emoji,
        type_message='reaction',
        emoji_reaction=emoji,
    )

    ParticipantLive.objects.filter(live=live, utilisateur=request.user).update(
        nb_reactions=F('nb_reactions') + 1
    )

    return JsonResponse({'success': True, 'emoji': emoji})


@login_required
@require_POST
@transaction.atomic
def ajax_acheter_live(request, pk):
    live            = get_object_or_404(LiveVente, pk=pk, statut='en_cours')
    produit_live_pk = request.POST.get('produit_live_pk')

    try:
        produit_live = get_object_or_404(
            ProduitLive.objects.select_for_update().select_related('produit'),
            pk=produit_live_pk, live=live, est_disponible=True
        )

        try:
            quantite = int(request.POST.get('quantite', 1))
            if quantite < 1:
                raise ValueError()
        except (ValueError, TypeError):
            quantite = 1

        if quantite > produit_live.stock_disponible():
            return JsonResponse({
                'success': False,
                'message': f"Stock insuffisant ({produit_live.stock_disponible()} restant(s))."
            }, status=400)

        prix_unitaire = produit_live.prix_final()
        montant_total = prix_unitaire * quantite

        from apps_marketplace.models import Commande, ArticleCommande
        adresse = getattr(request.user, 'adresse', '') or 'Adresse à compléter'
        commande = Commande.objects.create(
            utilisateur=request.user,
            source='live',
            adresse_facturation=adresse,
            adresse_livraison=adresse,
            sous_total=montant_total,
            montant_total=montant_total,
            notes=f"Achat live : {live.titre}",
        )
        ArticleCommande.objects.create(
            commande=commande,
            produit=produit_live.produit,
            quantite=quantite,
            prix_unitaire=prix_unitaire,
        )

        reservation = ReservationLive.objects.create(
            produit_live=produit_live,
            utilisateur=request.user,
            quantite=quantite,
            prix_unitaire=prix_unitaire,
            statut='confirmee',
            commande=commande,
        )

        ProduitLive.objects.filter(pk=produit_live.pk).update(
            quantite_vendue=F('quantite_vendue') + quantite
        )
        LiveVente.objects.filter(pk=pk).update(
            chiffre_affaires_live=F('chiffre_affaires_live') + montant_total
        )
        ParticipantLive.objects.filter(live=live, utilisateur=request.user).update(
            montant_achats=F('montant_achats') + montant_total,
            a_effectue_achat=True,
        )

    except Exception as e:
        # log complet côté serveur pour debug, réponse JSON propre côté client
        import logging
        logging.getLogger(__name__).exception("Erreur ajax_acheter_live pk=%s", pk)
        return JsonResponse({
            'success': False,
            'message': f"Erreur lors de l'achat : {e}"
        }, status=400)  # 400, jamais 500 non catché

    return JsonResponse({
        'success':     True,
        'message':     f"Commande créée ! {quantite}x {produit_live.produit.titre}",
        'commande_pk': str(commande.pk),
        'montant':     float(montant_total),
    })


@require_GET
def ajax_etat_live(request, pk):
    """Polling état du live — participants, produit actif, CA, messages récents."""
    live = get_object_or_404(LiveVente, pk=pk)

    nb_actifs = live.participants.filter(date_sortie__isnull=True).count()

    produit_actuel = live.produits_live.filter(
        est_disponible=True
    ).select_related('produit').order_by('ordre').first()

    derniers_messages = [{
        'username': m.utilisateur.username,
        'contenu':  m.contenu,
        'type':     m.type_message,
        'date':     m.date_creation.strftime('%H:%M:%S'),
        'epingle':  m.est_epingle,
    } for m in live.messages.exclude(type_message='reaction').select_related('utilisateur').order_by('-date_creation')[:8]]

    return JsonResponse({
        'statut':         live.statut,
        'stream_statut':   live.stream_statut,
        'est_active':     live.statut == 'en_cours',
        'nb_actifs':      nb_actifs,
        'nb_vues':        live.nb_vues_total,
        'ca_genere':      float(live.chiffre_affaires_live or 0),
        'produit_actuel': {
            'pk':           produit_actuel.pk,
            'titre':        produit_actuel.produit.titre,
            'prix_live':    float(produit_actuel.prix_final()),
            'prix_normal':  float(produit_actuel.produit.prix),
            'qte_restante': produit_actuel.stock_disponible(),
        } if produit_actuel else None,
        'derniers_commentaires': derniers_messages,
        'doit_recharger': live.statut in ('termine', 'annule'),
    })

# =============================================================================
# VENDEUR — Gestion des lives
# =============================================================================

@login_required
def mes_lives(request):
    """Historique des lives du vendeur connecté."""
    if not request.user.peut_vendre:
        messages.warning(request, "Réservé aux vendeurs.")
        return redirect('apps_core:tableau_de_bord')

    qs = LiveVente.objects.filter(vendeur=request.user).order_by('-date_debut')

    statut = request.GET.get('statut', '')
    if statut:
        qs = qs.filter(statut=statut)

    stats = {
        'total':      qs.count(),
        'en_direct':  qs.filter(statut='en_cours').count(),
        'ca_total':   LiveVente.objects.filter(vendeur=request.user)
                        .aggregate(s=Sum('chiffre_affaires_live'))['s'] or 0,
        'vues_total': LiveVente.objects.filter(vendeur=request.user)
                        .aggregate(s=Sum('nb_vues_total'))['s'] or 0,
    }

    paginator = Paginator(qs, 15)
    lives     = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'apps_social/lives/mes_lives.html', {
        'lives':      lives,
        'stats':      stats,
        'statut':     statut,
        'statuts':    LiveVente.STATUT_CHOICES,
        'page_titre': 'Mes lives',
    })


@login_required
def creer_live(request):
    """
    Création d'un live.
    RÈGLE MÉTIER : seuls les produits du vendeur connecté sont proposés.
    """
    if not request.user.peut_vendre:
        messages.warning(request, "Vous devez être vendeur pour créer un live.")
        return redirect('apps_core:devenir_vendeur')

    mes_produits = _produits_du_vendeur(request.user)

    if request.method == 'POST':
        titre       = request.POST.get('titre', '').strip()
        description = request.POST.get('description', '').strip()
        date_debut_str = request.POST.get('date_debut', '').strip()

        autoriser_chat      = request.POST.get('autoriser_chat') == 'on'
        autoriser_questions = request.POST.get('autoriser_questions') == 'on'
        autoriser_reactions = request.POST.get('autoriser_reactions') == 'on'
        nb_max_str  = request.POST.get('nb_participants_max', '').strip()
        duree_jours_str  = request.POST.get('duree_jours', '0').strip()
        duree_heures_str = request.POST.get('duree_heures', '1').strip()

        image_couverture = request.FILES.get('image_couverture')

        if not titre:
            messages.error(request, "Le titre est requis.")
            return redirect('apps_social:creer_live')
        if not image_couverture:
            messages.error(request, "Une image de couverture est requise.")
            return redirect('apps_social:creer_live')

        try:
            from django.utils.dateparse import parse_datetime
            date_debut   = parse_datetime(date_debut_str) if date_debut_str else timezone.now()
            nb_max       = int(nb_max_str) if nb_max_str else 0
            duree_jours  = int(duree_jours_str or 0)
            duree_heures = int(duree_heures_str or 1)
        except (ValueError, TypeError):
            messages.error(request, "Date ou nombre invalide.")
            return redirect('apps_social:creer_live')

        live = LiveVente.objects.create(
            vendeur=request.user,
            titre=titre,
            description=description,
            date_debut=date_debut,
            duree_jours=duree_jours,
            duree_heures=duree_heures,
            statut='planifie',
            image_couverture=image_couverture,
            autoriser_chat=autoriser_chat,
            autoriser_questions=autoriser_questions,
            autoriser_reactions=autoriser_reactions,
            nb_participants_max=nb_max,
        )

        # Produits sélectionnés
        produits_ids = request.POST.getlist('produits')
        for i, produit_id in enumerate(produits_ids):
            produit = mes_produits.filter(pk=produit_id).first()
            if not produit:
                continue  # ignore tout produit n'appartenant pas au vendeur

            prix_live_str = request.POST.get(f'prix_live_{produit_id}', '').strip()
            try:
                prix_live = Decimal(prix_live_str) if prix_live_str else None
            except Exception:
                prix_live = None

            qte_str = request.POST.get(f'quantite_{produit_id}', '').strip()
            try:
                quantite_live = int(qte_str) if qte_str else produit.quantite_stock
            except Exception:
                quantite_live = produit.quantite_stock

            ProduitLive.objects.create(
                live=live,
                produit=produit,
                prix_live=prix_live,
                quantite_live=max(quantite_live, 1),
                ordre=i,
            )

        messages.success(request, f"Live « {live.titre} » créé !")
        return redirect('apps_social:live_detail', pk=live.pk)

    return render(request, 'apps_social/lives/live_form.html', {
        'mes_produits': mes_produits,
        'mode':         'creation',
        'page_titre':   'Créer un live',
    })


@login_required
def modifier_live(request, pk):
    """Modifier un live avant son lancement."""
    live = get_object_or_404(LiveVente, pk=pk)

    if not _peut_gerer_live(request.user, live):
        messages.error(request, "Vous ne pouvez modifier que vos propres lives.")
        return redirect('apps_social:mes_lives')

    if live.statut == 'en_cours':
        messages.warning(request, "Impossible de modifier un live en cours.")
        return redirect('apps_social:live_detail', pk=pk)

    mes_produits = _produits_du_vendeur(request.user)

    if request.method == 'POST':
        live.titre       = request.POST.get('titre', live.titre).strip()
        live.description = request.POST.get('description', live.description).strip()
        live.autoriser_chat      = request.POST.get('autoriser_chat') == 'on'
        live.autoriser_questions = request.POST.get('autoriser_questions') == 'on'
        live.autoriser_reactions = request.POST.get('autoriser_reactions') == 'on'

        nb_max_str = request.POST.get('nb_participants_max', '').strip()
        live.nb_participants_max = int(nb_max_str) if nb_max_str else 0

        image_couverture = request.FILES.get('image_couverture')
        if image_couverture:
            live.image_couverture = image_couverture

        live.save()
        messages.success(request, "Live mis à jour.")
        return redirect('apps_social:live_detail', pk=pk)

    return render(request, 'apps_social/lives/live_form.html', {
        'live':         live,
        'mes_produits': mes_produits,
        'mode':         'edition',
        'page_titre':   f"Modifier — {live.titre}",
    })


@login_required
@require_POST
def demarrer_live(request, pk):
    """Passe un live de 'planifie' à 'en_cours' (le stream reste 'connexion' jusqu'au signal encodeur)."""
    live = get_object_or_404(LiveVente, pk=pk)

    if not _peut_gerer_live(request.user, live):
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)

    if live.statut != 'planifie':
        return JsonResponse({'success': False, 'message': f"Statut invalide : {live.statut}"}, status=400)

    live.statut         = 'en_cours'
    live.date_debut     = timezone.now()
    live.stream_demarre = True
    live.stream_statut  = 'connexion'
    live.save(update_fields=['statut', 'date_debut', 'stream_demarre', 'stream_statut'])

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': "🔴 Live démarré ! En attente de connexion du flux…"})

    messages.success(request, "Live démarré !")
    return redirect('apps_social:live_detail', pk=pk)

@csrf_exempt  # le serveur de streaming n'a pas de session Django ni de cookie CSRF
@require_POST
def webhook_stream_statut(request, pk):
    """
    Callback appelé par le serveur de streaming pour signaler
    la connexion/déconnexion réelle de l'encodeur.
    À sécuriser avec un token secret partagé (voir note plus bas).
    """
    live = get_object_or_404(LiveVente, pk=pk)

    token_recu = request.headers.get('X-Stream-Secret', '')
    if token_recu != settings.STREAM_WEBHOOK_SECRET:
        return JsonResponse({'success': False}, status=403)

    nouveau_statut = request.POST.get('stream_statut', '')
    if nouveau_statut not in dict(LiveVente.STREAM_CHOICES):
        return JsonResponse({'success': False, 'message': 'Statut invalide'}, status=400)

    live.stream_statut = nouveau_statut
    live.save(update_fields=['stream_statut'])

    return JsonResponse({'success': True})


@login_required
@require_POST
def terminer_live(request, pk):
    """Clôture un live et calcule le CA final (réservé au vendeur ou à un admin)."""
    live = get_object_or_404(LiveVente, pk=pk)

    if not _peut_gerer_live(request.user, live):
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)

    if live.statut != 'en_cours':
        return JsonResponse({'success': False, 'message': "Ce live ne peut pas être terminé."}, status=400)

    now = timezone.now()

    ca_final = ReservationLive.objects.filter(
        produit_live__live=live, statut='confirmee'
    ).aggregate(total=Sum('montant_total'))['total'] or Decimal('0')

    live.statut             = 'termine'
    live.date_fin_reelle    = now
    live.chiffre_affaires_live = ca_final
    live.save()

    ParticipantLive.objects.filter(
        live=live, date_sortie__isnull=True
    ).update(date_sortie=now, est_connecte=False)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'message': f"Live terminé. CA : {ca_final:,.0f} FCFA",
            'ca':      float(ca_final),
        })

    messages.success(request, f"Live terminé. CA généré : {ca_final:,.0f} FCFA.")
    return redirect('apps_social:mes_lives')


@login_required
@require_POST
def ajouter_produit_live(request, pk):
    """Ajoute un produit à un live. Le produit doit appartenir au vendeur du live."""
    live = get_object_or_404(LiveVente, pk=pk)

    if not _peut_gerer_live(request.user, live):
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)

    produit_id = request.POST.get('produit_id')
    produit = _produits_du_vendeur(live.vendeur).filter(pk=produit_id).first()
    if not produit:
        return JsonResponse({
            'success': False,
            'message': "Produit invalide : vous ne pouvez ajouter que vos propres produits."
        }, status=400)

    if live.produits_live.filter(produit=produit).exists():
        return JsonResponse({'success': False, 'message': "Ce produit est déjà dans le live."}, status=400)

    try:
        prix_live_str = request.POST.get('prix_live', '').strip()
        prix_live     = Decimal(prix_live_str) if prix_live_str else None
    except Exception:
        prix_live = None

    try:
        qte_str       = request.POST.get('quantite', '').strip()
        quantite_live = int(qte_str) if qte_str else produit.quantite_stock
    except Exception:
        quantite_live = produit.quantite_stock

    ordre = live.produits_live.count()
    pl = ProduitLive.objects.create(
        live=live,
        produit=produit,
        prix_live=prix_live,
        quantite_live=max(quantite_live, 1),
        ordre=ordre,
        est_disponible=True,
    )

    return JsonResponse({
        'success':          True,
        'message':          f"« {produit.titre} » ajouté au live.",
        'produit_live_pk':  pl.pk,
        'titre':            produit.titre,
        'prix_live':        float(pl.prix_final()),
        'prix_normal':      float(produit.prix),
    })


@login_required
@require_POST
def retirer_produit_live(request, produit_live_pk):
    """Retire un produit du live (désactivation seulement si des ventes existent)."""
    pl = get_object_or_404(ProduitLive, pk=produit_live_pk)

    if not _peut_gerer_live(request.user, pl.live):
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)

    if ReservationLive.objects.filter(produit_live=pl).exists():
        pl.est_disponible = False
        pl.save(update_fields=['est_disponible'])
        msg = "Produit désactivé (des ventes existent)."
    else:
        pl.delete()
        msg = "Produit retiré du live."

    return JsonResponse({'success': True, 'message': msg})


@login_required
@require_POST
def toggle_produit_actif(request, produit_live_pk):
    """Active / désactive un produit dans le live (AJAX)."""
    pl = get_object_or_404(ProduitLive, pk=produit_live_pk)

    if not _peut_gerer_live(request.user, pl.live):
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)

    pl.est_disponible = not pl.est_disponible
    pl.save(update_fields=['est_disponible'])

    return JsonResponse({
        'success':       True,
        'est_actif':     pl.est_disponible,
        'message':       f"Produit {'activé' if pl.est_disponible else 'désactivé'}.",
    })



# =============================================================================
# ADMIN
# =============================================================================

@login_required
def admin_lives_liste(request):
    """Vue admin de tous les lives."""
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')

    qs = LiveVente.objects.select_related('vendeur').order_by('-date_debut')

    statut = request.GET.get('statut', '')
    if statut:
        qs = qs.filter(statut=statut)

    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(Q(titre__icontains=q) | Q(vendeur__username__icontains=q))

    stats = {
        'total':      LiveVente.objects.count(),
        'en_direct':  LiveVente.objects.filter(statut='en_cours').count(),
        'ca_total':   LiveVente.objects.aggregate(s=Sum('chiffre_affaires_live'))['s'] or 0,
        'vues_total': LiveVente.objects.aggregate(s=Sum('nb_vues_total'))['s'] or 0,
    }

    paginator = Paginator(qs, 25)
    lives     = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'apps_social/admin/lives_liste.html', {
        'lives':      lives,
        'stats':      stats,
        'statut':     statut,
        'q':          q,
        'statuts':    LiveVente.STATUT_CHOICES,
        'page_titre': 'Gestion des lives',
    })


@login_required
@require_POST
def admin_terminer_live(request, pk):
    """Termine un live abusif (admin uniquement — pas de suspension, action définitive)."""
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)

    live  = get_object_or_404(LiveVente, pk=pk)
    motif = request.POST.get('motif', '').strip()

    if live.statut != 'en_cours':
        msg = "Ce live n'est pas en cours."
    else:
        live.statut          = 'termine'
        live.date_fin_reelle = timezone.now()
        live.save(update_fields=['statut', 'date_fin_reelle'])
        msg = f"Live « {live.titre} » terminé par un administrateur."

        try:
            from apps_core.views_notifications import creer_notification
            creer_notification(
                utilisateur=live.vendeur,
                type_notification='systeme',
                titre="Live terminé par un administrateur",
                message=f"Votre live « {live.titre} » a été terminé.{' Motif : ' + motif if motif else ''}",
            )
        except Exception:
            pass

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': msg, 'statut': live.statut})

    messages.warning(request, msg)
    return redirect('apps_social:admin_lives_liste')



# =============================================================================
# HELPERS
# =============================================================================
 
def _stories_actives():
    """QuerySet de base : stories non expirées."""
    return Story.objects.filter(
        date_expiration__gt=timezone.now()
    ).select_related('auteur', 'produit_lie')
 
 
def _stories_vues_ids(user):
    """IDs des stories déjà vues par l'utilisateur."""
    if not user.is_authenticated:
        return set()
    return set(
        VueStory.objects.filter(
            utilisateur=user
        ).values_list('story_id', flat=True)
    )
 
 
def _marquer_vue_interne(story, user):
    """Enregistre une vue et incrémente le compteur."""
    if not user.is_authenticated:
        return
    _, created = VueStory.objects.get_or_create(story=story, utilisateur=user)
    if created:
        Story.objects.filter(pk=story.pk).update(nb_vues=story.nb_vues + 1)
 


# =============================================================================
# PUBLIC
# =============================================================================
 
def stories_feed(request):
    """
    Feed des stories : stories des personnes que l'utilisateur suit.
    Si non connecté : stories publiques les plus récentes.
    """
    now = timezone.now()
 
    if request.user.is_authenticated:
        # Personnes suivies
        from .models import AbonnementSocial
        suivis_ids = AbonnementSocial.objects.filter(
            abonne=request.user
        ).values_list('suivi_id', flat=True)
 
        # Stories des suivis + les siennes
        qs = _stories_actives().filter(
            Q(auteur__in=suivis_ids) | Q(auteur=request.user)
        )
    else:
        qs = _stories_actives()
 
    # Grouper par auteur (une "bulle" par auteur, stories non vues en premier)
    auteurs_ids = qs.values_list('auteur_id', flat=True).distinct()
    vues_ids    = _stories_vues_ids(request.user)
 
    # Construire les bulles auteur
    from apps_core.models import Utilisateur
    auteurs = Utilisateur.objects.filter(
        pk__in=auteurs_ids
    ).select_related('profil_social').distinct()
 
    bulles = []
    for auteur in auteurs:
        stories_auteur = qs.filter(auteur=auteur).order_by('date_creation')
        nb_non_vues    = stories_auteur.exclude(pk__in=vues_ids).count()
        bulles.append({
            'auteur':       auteur,
            'stories':      list(stories_auteur),
            'nb_non_vues':  nb_non_vues,
            'a_non_vues':   nb_non_vues > 0,
            'premiere_pk':  stories_auteur.first().pk if stories_auteur.exists() else None,
        })
 
    # Trier : non vues d'abord
    bulles.sort(key=lambda b: (-b['nb_non_vues'], -len(b['stories'])))
 
    return render(request, 'apps_social/stories/stories_feed.html', {
        'bulles':    bulles,
        'vues_ids':  vues_ids,
        'page_titre': 'Stories',
    })


def stories_utilisateur(request, username):
    """Stories actives d'un utilisateur spécifique."""
    from apps_core.models import Utilisateur
    auteur  = get_object_or_404(Utilisateur, username=username)
    stories = _stories_actives().filter(auteur=auteur).order_by('date_creation')
    vues_ids = _stories_vues_ids(request.user)
 
    return render(request, 'apps_social/stories/stories_utilisateur.html', {
        'auteur':    auteur,
        'stories':   stories,
        'vues_ids':  vues_ids,
        'page_titre': f"Stories de @{username}",
    })



def story_viewer(request, pk):
    """
    Visionneuse plein écran d'une story.
    Enregistre la vue, affiche le produit lié si présent.
    Retourne la story précédente/suivante pour la navigation.
    """
    story = get_object_or_404(Story, pk=pk)
 
    if story.est_expiree():
        messages.info(request, "Cette story a expiré.")
        return redirect('apps_social:stories_feed')
 
    # Enregistrer la vue
    _marquer_vue_interne(story, request.user)
 
    # Navigation : story précédente / suivante du même auteur
    stories_auteur = list(
        _stories_actives().filter(
            auteur=story.auteur
        ).order_by('date_creation').values_list('pk', flat=True)
    )
    idx_actuel  = stories_auteur.index(story.pk) if story.pk in stories_auteur else -1
    story_prev  = stories_auteur[idx_actuel - 1] if idx_actuel > 0 else None
    story_next  = stories_auteur[idx_actuel + 1] if idx_actuel < len(stories_auteur) - 1 else None
 
    # Vues de cette story (pour le propriétaire)
    vues = []
    est_proprio = request.user.is_authenticated and request.user == story.auteur
    if est_proprio:
        vues = story.vues.select_related('utilisateur').order_by('-date_vue')[:50]
 
    return render(request, 'apps_social/stories/story_viewer.html', {
        'story':       story,
        'story_prev':  story_prev,
        'story_next':  story_next,
        'vues':        vues,
        'est_proprio': est_proprio,
        'temps_restant': max(0, int(
            (story.date_expiration - timezone.now()).total_seconds()
        )),
        'page_titre':  f"Story de @{story.auteur.username}",
    })

 
# =============================================================================
# UTILISATEUR CONNECTÉ
# =============================================================================
 
@login_required
def creer_story(request):
    """
    Publier une story (image/vidéo/produit/offre).
    Durée fixe : 24h à partir de la création.
    """
    if request.method == 'POST':
        type_story   = request.POST.get('type_story', 'image')
        texte        = request.POST.get('texte', '').strip()[:200]
        couleur_fond = request.POST.get('couleur_fond', '#000000').strip()
        bouton_action = request.POST.get('bouton_action', '').strip()[:50]
        lien_action  = request.POST.get('lien_action', '').strip()
        produit_id   = request.POST.get('produit_lie')
        media        = request.FILES.get('media')
        miniature    = request.FILES.get('miniature')
 
        if not media:
            messages.error(request, "Un fichier média est requis.")
            return redirect('apps_social:creer_story')
 
        # Valider le type
        types_valides = [t[0] for t in Story.TYPE_CHOICES]
        if type_story not in types_valides:
            type_story = 'image'
 
        # Vérifier couleur
        if not (couleur_fond.startswith('#') and len(couleur_fond) in (4, 7)):
            couleur_fond = '#000000'
 
        # Produit lié — doit appartenir à l'utilisateur
        produit_lie = None
        if produit_id:
            produit_lie = Produit.objects.filter(
                pk=produit_id, vendeur=request.user, est_actif=True
            ).first()
 
        story = Story.objects.create(
            auteur=request.user,
            type_story=type_story,
            media=media,
            texte=texte,
            couleur_fond=couleur_fond,
            bouton_action=bouton_action,
            lien_action=lien_action,
            produit_lie=produit_lie,
            date_expiration=timezone.now() + timedelta(hours=24),
        )
 
        if miniature:
            story.miniature = miniature
            story.save(update_fields=['miniature'])
 
        messages.success(request, "Story publiée ! Elle disparaîtra dans 24h.")
        return redirect('apps_social:story_viewer', pk=story.pk)
 
    # Produits du vendeur pour le type 'produit'
    mes_produits = []
    if request.user.peut_vendre:
        mes_produits = Produit.objects.filter(
            vendeur=request.user, est_actif=True
        ).order_by('titre')[:50]
 
    return render(request, 'apps_social/stories/story_form.html', {
        'types':        Story.TYPE_CHOICES,
        'mes_produits': mes_produits,
        'page_titre':   'Créer une story',
    })


@login_required
@require_POST
def supprimer_story(request, pk):
    """L'auteur supprime sa story avant expiration."""
    story = get_object_or_404(Story, pk=pk, auteur=request.user)
    story.delete()
 
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': 'Story supprimée.'})
 
    messages.success(request, "Story supprimée.")
    return redirect('apps_social:mes_stories')
 
 
@login_required
def mes_stories(request):
    """Stories actives et récemment expirées de l'utilisateur."""
    now = timezone.now()
 
    actives = Story.objects.filter(
        auteur=request.user,
        date_expiration__gt=now
    ).order_by('-date_creation')
 
    expirees = Story.objects.filter(
        auteur=request.user,
        date_expiration__lte=now
    ).order_by('-date_creation')[:20]
 
    stats = {
        'actives':    actives.count(),
        'vues_total': Story.objects.filter(auteur=request.user).aggregate(
            s=__import__('django.db.models', fromlist=['Sum']).Sum('nb_vues')
        )['s'] or 0,
        'clics_total': Story.objects.filter(auteur=request.user).aggregate(
            s=__import__('django.db.models', fromlist=['Sum']).Sum('nb_clics')
        )['s'] or 0,
    }
 
    return render(request, 'apps_social/stories/mes_stories.html', {
        'actives':    actives,
        'expirees':   expirees,
        'stats':      stats,
        'page_titre': 'Mes stories',
    })


# =============================================================================
# AJAX
# =============================================================================
 
@require_POST
def ajax_marquer_vue(request, pk):
    """Enregistre qu'un utilisateur a vu une story (AJAX)."""
    story = get_object_or_404(Story, pk=pk)
 
    if story.est_expiree():
        return JsonResponse({'success': False, 'message': 'Story expirée.'}, status=410)
 
    _marquer_vue_interne(story, request.user)
    story.refresh_from_db(fields=['nb_vues'])
 
    return JsonResponse({
        'success':  True,
        'nb_vues':  story.nb_vues,
        'expiree':  story.est_expiree(),
    })
 
 
@require_POST
def ajax_clic_action(request, pk):
    """Incrémente le compteur de clics sur le CTA d'une story."""
    story = get_object_or_404(Story, pk=pk)
    Story.objects.filter(pk=pk).update(nb_clics=story.nb_clics + 1)
    return JsonResponse({'success': True, 'nb_clics': story.nb_clics + 1})
 
 
@require_GET
def ajax_stories_feed(request):
    """
    Retourne les stories actives pour la barre de stories (JSON).
    Utilisé dans la navbar / homepage pour afficher les bulles.
    """
    now = timezone.now()
    vues_ids = _stories_vues_ids(request.user)
 
    if request.user.is_authenticated:
        from .models import AbonnementSocial
        suivis_ids = AbonnementSocial.objects.filter(
            abonne=request.user
        ).values_list('suivi_id', flat=True)
        auteurs_ids = Story.objects.filter(
            date_expiration__gt=now
        ).filter(
            Q(auteur__in=suivis_ids) | Q(auteur=request.user)
        ).values_list('auteur_id', flat=True).distinct()
    else:
        auteurs_ids = Story.objects.filter(
            date_expiration__gt=now
        ).values_list('auteur_id', flat=True).distinct()[:20]
 
    from apps_core.models import Utilisateur
    auteurs = Utilisateur.objects.filter(pk__in=auteurs_ids).select_related('profil_social')
 
    data = []
    for auteur in auteurs:
        stories = Story.objects.filter(
            auteur=auteur, date_expiration__gt=now
        ).order_by('date_creation')
        if not stories.exists():
            continue
        premiere = stories.first()
        data.append({
            'username':      auteur.username,
            'avatar_url':    auteur.avatar.url if hasattr(auteur, 'avatar') and auteur.avatar else '',
            'est_verifie':   getattr(getattr(auteur, 'profil_social', None), 'est_verifie', False),
            'a_non_vues':    stories.exclude(pk__in=vues_ids).exists(),
            'nb_stories':    stories.count(),
            'premiere_pk':   str(premiere.pk),
            'viewer_url':    f"/stories/{premiere.pk}/",
        })
 
    return JsonResponse({'stories': data, 'total': len(data)})



# =============================================================================
# ADMIN
# =============================================================================
 
@login_required
def admin_stories_liste(request):
    """Vue admin de toutes les stories (modération)."""
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')
 
    now = timezone.now()
    qs  = Story.objects.select_related('auteur', 'produit_lie').order_by('-date_creation')
 
    type_filtre = request.GET.get('type', '')
    if type_filtre:
        qs = qs.filter(type_story=type_filtre)
 
    statut = request.GET.get('statut', '')
    if statut == 'actives':
        qs = qs.filter(date_expiration__gt=now)
    elif statut == 'expirees':
        qs = qs.filter(date_expiration__lte=now)
 
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(
            Q(auteur__username__icontains=q) | Q(texte__icontains=q)
        )
 
    stats = {
        'total':    Story.objects.count(),
        'actives':  Story.objects.filter(date_expiration__gt=now).count(),
        'expirees': Story.objects.filter(date_expiration__lte=now).count(),
        'produits': Story.objects.filter(type_story__in=['produit', 'offre']).count(),
    }
 
    paginator = Paginator(qs, 30)
    stories   = paginator.get_page(request.GET.get('page', 1))
 
    return render(request, 'apps_social/admin/stories_liste.html', {
        'stories':     stories,
        'stats':       stats,
        'type_filtre': type_filtre,
        'statut':      statut,
        'q':           q,
        'types':       Story.TYPE_CHOICES,
        'page_titre':  'Modération des stories',
    })


@login_required
@require_POST
def admin_supprimer_story(request, pk):
    """Suppression admin d'une story (contenu abusif)."""
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)
 
    story = get_object_or_404(Story, pk=pk)
    auteur_username = story.auteur.username
    story.delete()
 
    try:
        from apps_core.views_notifications import creer_notification
        creer_notification(
            utilisateur=story.auteur,
            type_notification='systeme',
            titre="Votre story a été supprimée",
            message="Une de vos stories a été retirée par notre équipe de modération.",
        )
    except Exception:
        pass
 
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': f"Story de @{auteur_username} supprimée."})
 
    messages.success(request, f"Story de @{auteur_username} supprimée.")
    return redirect('apps_social:admin_stories_liste')


# =============================================================================
# SYSTÈME — Nettoyage des stories expirées
# =============================================================================
 
@login_required
def cron_nettoyer_stories(request):
    """
    Supprime les stories expirées depuis plus de 24h supplémentaires.
    Garde un délai de grâce de 24h pour les propriétaires.
    Déclenchable manuellement par un admin ou via cron externe.
    """
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')
 
    seuil = timezone.now() - timedelta(hours=24)  # expirées depuis 24h+
    qs    = Story.objects.filter(date_expiration__lt=seuil)
    nb    = qs.count()
    qs.delete()
 
    messages.success(request, f"{nb} story(ies) expirée(s) supprimée(s).")
    return redirect('apps_social:admin_stories_liste')


# =============================================================================
# HELPERS
# =============================================================================

def _peut_gerer_video(user, video):
    return user.is_staff or video.auteur == user


def _produits_du_vendeur_video(user):
    return Produit.objects.filter(vendeur=user, est_actif=True).order_by('titre')


# =============================================================================
# PUBLIC — Feed & détail
# =============================================================================

def videos_feed(request):
    """
    Feed vertical façon TikTok. Charge un premier lot de vidéos ;
    le scroll infini est géré par ajax_videos_suivantes.
    """
    qs = VideoCommerce.objects.filter(est_publie=True).select_related('auteur').order_by(
        '-est_mis_en_avant', '-date_creation'
    )

    hashtag = request.GET.get('hashtag', '').strip()
    if hashtag:
        qs = qs.filter(hashtags__icontains=hashtag)

    videos = list(qs[:5])

    return render(request, 'apps_social/videos/videos_feed.html', {
        'videos':     videos,
        'hashtag':    hashtag,
        'page_titre': 'ShopTok — Vidéos',
    })


def video_detail(request, pk):
    """Permalien direct vers une vidéo (partage, lien externe)."""
    video = get_object_or_404(
        VideoCommerce.objects.select_related('auteur'),
        pk=pk, est_publie=True
    )

    if not request.user.is_authenticated or request.user != video.auteur:
        VideoCommerce.objects.filter(pk=pk).update(nb_vues=F('nb_vues') + 1)

    produits_video = video.produits_video.select_related('produit').order_by('timestamp_apparition')

    commentaires = video.commentaires.filter(
        parent__isnull=True
    ).select_related('auteur').prefetch_related('reponses__auteur').order_by('-date_creation')[:30]

    return render(request, 'apps_social/videos/video_detail.html', {
        'video':           video,
        'produits_video':  produits_video,
        'commentaires':    commentaires,
        'est_proprietaire': request.user.is_authenticated and request.user == video.auteur,
        'page_titre':      video.titre,
    })


@require_GET
def ajax_videos_suivantes(request):
    """
    Scroll infini du feed. GET params : apres=<uuid dernière vidéo vue>, hashtag=<filtre>.
    """
    qs = VideoCommerce.objects.filter(est_publie=True).select_related('auteur').order_by(
        '-est_mis_en_avant', '-date_creation'
    )

    hashtag = request.GET.get('hashtag', '').strip()
    if hashtag:
        qs = qs.filter(hashtags__icontains=hashtag)

    apres_pk = request.GET.get('apres', '')
    if apres_pk:
        derniere = VideoCommerce.objects.filter(pk=apres_pk).first()
        if derniere:
            qs = qs.filter(date_creation__lt=derniere.date_creation)

    videos = qs[:5]

    data = [{
        'pk':             str(v.pk),
        'titre':          v.titre,
        'description':    v.description,
        'video_url':      v.video.url,
        'miniature_url':  v.miniature.url,
        'hashtags':       v.hashtags,
        'nb_vues':        v.nb_vues,
        'nb_likes':       v.nb_likes,
        'nb_commentaires': v.nb_commentaires,
        'nb_partages':    v.nb_partages,
        'auteur': {
            'username':   v.auteur.username,
            'avatar_url': v.auteur.avatar.url if v.auteur.avatar else '',
        },
    } for v in videos]

    return JsonResponse({'videos': data, 'a_plus': len(videos) == 5})


# =============================================================================
# AJAX PUBLIC — Interactions
# =============================================================================

@login_required
@require_POST
def ajax_liker_video(request, pk):
    """
    Like d'une vidéo. NOTE : pas de modèle par utilisateur (pas de LikeVideo),
    donc pas de vrai toggle ni de déduplication fiable — protection best-effort via session.
    """
    video = get_object_or_404(VideoCommerce, pk=pk, est_publie=True)

    deja_like = request.session.get(f'video_like_{pk}', False)
    if deja_like:
        return JsonResponse({'success': False, 'message': 'Déjà aimé.'}, status=400)

    VideoCommerce.objects.filter(pk=pk).update(nb_likes=F('nb_likes') + 1)
    request.session[f'video_like_{pk}'] = True

    video.refresh_from_db(fields=['nb_likes'])
    return JsonResponse({'success': True, 'nb_likes': video.nb_likes})


@login_required
@require_POST
def ajax_commenter_video(request, pk):
    """Poster un commentaire (ou une réponse si parent_pk fourni)."""
    video = get_object_or_404(VideoCommerce, pk=pk, est_publie=True)

    contenu = request.POST.get('contenu', '').strip()
    if not contenu or len(contenu) > 300:
        return JsonResponse({'success': False, 'message': "Commentaire invalide (1-300 caractères)."}, status=400)

    parent = None
    parent_pk = request.POST.get('parent_pk', '')
    if parent_pk:
        parent = CommentaireVideo.objects.filter(pk=parent_pk, video=video).first()

    commentaire = CommentaireVideo.objects.create(
        video=video, auteur=request.user, contenu=contenu, parent=parent
    )

    VideoCommerce.objects.filter(pk=pk).update(nb_commentaires=F('nb_commentaires') + 1)

    return JsonResponse({
        'success': True,
        'commentaire': {
            'pk':         commentaire.pk,
            'username':   request.user.username,
            'contenu':    commentaire.contenu,
            'parent_pk':  parent.pk if parent else None,
            'date':       commentaire.date_creation.strftime('%d/%m/%Y %H:%M'),
        }
    })


@login_required
@require_POST
def ajax_liker_commentaire(request, pk):
    """Like d'un commentaire (même limite que ajax_liker_video : pas de modèle par utilisateur)."""
    commentaire = get_object_or_404(CommentaireVideo, pk=pk)

    session_key = f'comm_like_{pk}'
    if request.session.get(session_key, False):
        return JsonResponse({'success': False, 'message': 'Déjà aimé.'}, status=400)

    CommentaireVideo.objects.filter(pk=pk).update(nb_likes=F('nb_likes') + 1)
    request.session[session_key] = True

    commentaire.refresh_from_db(fields=['nb_likes'])
    return JsonResponse({'success': True, 'nb_likes': commentaire.nb_likes})


@require_POST
def ajax_partager_video(request, pk):
    """Enregistre un partage (pas besoin d'être connecté)."""
    video = get_object_or_404(VideoCommerce, pk=pk, est_publie=True)
    VideoCommerce.objects.filter(pk=pk).update(nb_partages=F('nb_partages') + 1)

    lien = request.build_absolute_uri(
        reverse('apps_social:video_detail', kwargs={'pk': video.pk})
    )
    return JsonResponse({'success': True, 'lien': lien})


@login_required
@require_POST
@transaction.atomic
def ajax_acheter_produit_video(request, pk, produit_video_pk):
    """Achat direct d'un produit tagué dans la vidéo."""
    video = get_object_or_404(VideoCommerce, pk=pk, est_publie=True)
    pv = get_object_or_404(
        ProduitVideo.objects.select_related('produit'),
        pk=produit_video_pk, video=video
    )
    produit = pv.produit

    try:
        quantite = int(request.POST.get('quantite', 1))
        if quantite < 1:
            raise ValueError()
    except (ValueError, TypeError):
        quantite = 1

    if quantite > produit.quantite_stock:
        return JsonResponse({
            'success': False,
            'message': f"Stock insuffisant ({produit.quantite_stock} restant(s))."
        }, status=400)

    montant_total = produit.prix * quantite

    try:
        from apps_marketplace.models import Commande, ArticleCommande
        adresse = getattr(request.user, 'adresse', '') or 'Adresse à compléter'
        commande = Commande.objects.create(
            utilisateur=request.user,
            source='video',
            adresse_facturation=adresse,
            adresse_livraison=adresse,
            sous_total=montant_total,
            montant_total=montant_total,
            notes=f"Achat depuis la vidéo : {video.titre}",
        )
        ArticleCommande.objects.create(
            commande=commande,
            produit=produit,
            quantite=quantite,
            prix_unitaire=produit.prix,
        )
    except Exception as e:
        return JsonResponse({'success': False, 'message': f"Erreur commande : {e}"}, status=500)

    VideoCommerce.objects.filter(pk=pk).update(
        nb_achats=F('nb_achats') + 1,
        chiffre_affaires=F('chiffre_affaires') + montant_total,
    )

    return JsonResponse({
        'success':     True,
        'message':     f"Commande créée ! {quantite}x {produit.titre}",
        'commande_pk': str(commande.pk),
        'montant':     float(montant_total),
    })


@require_GET
def ajax_commentaires_video(request, pk):
    """Charge plus de commentaires (pagination du panneau commentaires)."""
    video = get_object_or_404(VideoCommerce, pk=pk, est_publie=True)

    qs = video.commentaires.filter(parent__isnull=True).select_related('auteur').order_by('-date_creation')

    paginator = Paginator(qs, 15)
    page = paginator.get_page(request.GET.get('page', 1))

    data = [{
        'pk':        c.pk,
        'username':  c.auteur.username,
        'contenu':   c.contenu,
        'nb_likes':  c.nb_likes,
        'date':      c.date_creation.strftime('%d/%m/%Y %H:%M'),
        'reponses': [{
            'pk':       r.pk,
            'username': r.auteur.username,
            'contenu':  r.contenu,
            'nb_likes': r.nb_likes,
        } for r in c.reponses.select_related('auteur').order_by('date_creation')],
    } for c in page]

    return JsonResponse({
        'commentaires': data,
        'a_plus':       page.has_next(),
        'page':         page.number,
    })


# =============================================================================
# VENDEUR — Gestion des vidéos
# =============================================================================

@login_required
def mes_videos(request):
    """Vidéos publiées par l'utilisateur connecté."""
    qs = VideoCommerce.objects.filter(auteur=request.user).order_by('-date_creation')

    stats = {
        'total':       qs.count(),
        'vues_total':  qs.aggregate(s=Sum('nb_vues'))['s'] or 0,
        'likes_total': qs.aggregate(s=Sum('nb_likes'))['s'] or 0,
        'ca_total':    qs.aggregate(s=Sum('chiffre_affaires'))['s'] or 0,
    }

    paginator = Paginator(qs, 15)
    videos = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'apps_social/videos/mes_videos.html', {
        'videos':     videos,
        'stats':      stats,
        'page_titre': 'Mes vidéos',
    })


@login_required
def creer_video(request):
    """Publication d'une nouvelle vidéo ShopTok."""
    if not request.user.peut_vendre:
        messages.warning(request, "Vous devez être vendeur pour publier une vidéo shoppable.")
        return redirect('apps_core:devenir_vendeur')

    mes_produits = _produits_du_vendeur_video(request.user)

    if request.method == 'POST':
        titre       = request.POST.get('titre', '').strip()
        description = request.POST.get('description', '').strip()
        hashtags    = request.POST.get('hashtags', '').strip()
        video_file     = request.FILES.get('video')
        miniature_file = request.FILES.get('miniature')

        duree_str = request.POST.get('duree_secondes', '30').strip()
        try:
            duree_secondes = int(duree_str or 30)
        except ValueError:
            duree_secondes = 30

        if not titre:
            messages.error(request, "Le titre est requis.")
            return redirect('apps_social:creer_video')
        if not video_file:
            messages.error(request, "Le fichier vidéo est requis.")
            return redirect('apps_social:creer_video')
        if not miniature_file:
            messages.error(request, "La miniature est requise.")
            return redirect('apps_social:creer_video')

        video = VideoCommerce.objects.create(
            auteur=request.user,
            titre=titre,
            description=description,
            video=video_file,
            miniature=miniature_file,
            duree_secondes=duree_secondes,
            hashtags=hashtags,
            est_publie=True,
        )

        # Produits tagués
        produits_ids = request.POST.getlist('produits')
        for produit_id in produits_ids:
            produit = mes_produits.filter(pk=produit_id).first()
            if not produit:
                continue

            ts_str = request.POST.get(f'timestamp_{produit_id}', '0').strip()
            try:
                timestamp = int(ts_str or 0)
            except ValueError:
                timestamp = 0

            ProduitVideo.objects.create(
                video=video,
                produit=produit,
                timestamp_apparition=timestamp,
            )

        messages.success(request, f"Vidéo « {video.titre} » publiée !")
        return redirect('apps_social:video_detail', pk=video.pk)

    return render(request, 'apps_social/videos/video_form.html', {
        'mes_produits': mes_produits,
        'mode':         'creation',
        'page_titre':   'Publier une vidéo',
    })


@login_required
def modifier_video(request, pk):
    """Édition des métadonnées d'une vidéo (pas le fichier vidéo lui-même)."""
    video = get_object_or_404(VideoCommerce, pk=pk)

    if not _peut_gerer_video(request.user, video):
        messages.error(request, "Vous ne pouvez modifier que vos propres vidéos.")
        return redirect('apps_social:mes_videos')

    mes_produits = _produits_du_vendeur_video(request.user)

    if request.method == 'POST':
        video.titre       = request.POST.get('titre', video.titre).strip()
        video.description = request.POST.get('description', video.description).strip()
        video.hashtags     = request.POST.get('hashtags', video.hashtags).strip()
        video.est_publie   = request.POST.get('est_publie') == 'on'

        miniature_file = request.FILES.get('miniature')
        if miniature_file:
            video.miniature = miniature_file

        video.save()
        messages.success(request, "Vidéo mise à jour.")
        return redirect('apps_social:video_detail', pk=video.pk)

    return render(request, 'apps_social/videos/video_form.html', {
        'video':        video,
        'mes_produits': mes_produits,
        'mode':         'edition',
        'page_titre':   f"Modifier — {video.titre}",
    })


@login_required
@require_POST
def supprimer_video(request, pk):
    """Suppression définitive d'une vidéo."""
    video = get_object_or_404(VideoCommerce, pk=pk)

    if not _peut_gerer_video(request.user, video):
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)

    titre = video.titre
    video.delete()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': f"« {titre} » supprimée."})

    messages.success(request, f"« {titre} » supprimée.")
    return redirect('apps_social:mes_videos')


@login_required
@require_POST
def ajouter_produit_video(request, pk):
    """Ajoute un produit tagué à une vidéo existante."""
    video = get_object_or_404(VideoCommerce, pk=pk)

    if not _peut_gerer_video(request.user, video):
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)

    produit_id = request.POST.get('produit_id')
    produit = _produits_du_vendeur_video(video.auteur).filter(pk=produit_id).first()
    if not produit:
        return JsonResponse({
            'success': False,
            'message': "Produit invalide : vous ne pouvez taguer que vos propres produits."
        }, status=400)

    if video.produits_video.filter(produit=produit).exists():
        return JsonResponse({'success': False, 'message': "Ce produit est déjà tagué."}, status=400)

    try:
        ts_str    = request.POST.get('timestamp_apparition', '0').strip()
        timestamp = int(ts_str or 0)
    except ValueError:
        timestamp = 0

    pv = ProduitVideo.objects.create(
        video=video, produit=produit, timestamp_apparition=timestamp
    )

    return JsonResponse({
        'success':         True,
        'message':         f"« {produit.titre} » tagué dans la vidéo.",
        'produit_video_pk': pv.pk,
        'titre':           produit.titre,
        'prix':            float(produit.prix),
    })


@login_required
@require_POST
def retirer_produit_video(request, produit_video_pk):
    """Retire un tag produit d'une vidéo."""
    pv = get_object_or_404(ProduitVideo, pk=produit_video_pk)

    if not _peut_gerer_video(request.user, pv.video):
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)

    pv.delete()
    return JsonResponse({'success': True, 'message': 'Produit retiré de la vidéo.'})


# =============================================================================
# ADMIN
# =============================================================================

@login_required
def admin_videos_liste(request):
    """Vue admin de toutes les vidéos ShopTok."""
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')

    qs = VideoCommerce.objects.select_related('auteur').order_by('-date_creation')

    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(Q(titre__icontains=q) | Q(auteur__username__icontains=q))

    publie = request.GET.get('publie', '')
    if publie == '1':
        qs = qs.filter(est_publie=True)
    elif publie == '0':
        qs = qs.filter(est_publie=False)

    vedette = request.GET.get('vedette', '')
    if vedette == '1':
        qs = qs.filter(est_mis_en_avant=True)

    stats = {
        'total':      VideoCommerce.objects.count(),
        'publiees':   VideoCommerce.objects.filter(est_publie=True).count(),
        'vedettes':   VideoCommerce.objects.filter(est_mis_en_avant=True).count(),
        'ca_total':   VideoCommerce.objects.aggregate(s=Sum('chiffre_affaires'))['s'] or 0,
    }

    paginator = Paginator(qs, 25)
    videos = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'apps_social/admin/videos_liste.html', {
        'videos':     videos,
        'stats':      stats,
        'q':          q,
        'publie':     publie,
        'vedette':    vedette,
        'page_titre': 'Gestion des vidéos ShopTok',
    })


@login_required
@require_POST
def admin_toggle_vedette(request, pk):
    """Met en avant / retire de la mise en avant (admin)."""
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)

    video = get_object_or_404(VideoCommerce, pk=pk)
    video.est_mis_en_avant = not video.est_mis_en_avant
    video.save(update_fields=['est_mis_en_avant'])

    return JsonResponse({
        'success':         True,
        'est_mis_en_avant': video.est_mis_en_avant,
        'message':         f"« {video.titre} » {'mise en avant' if video.est_mis_en_avant else 'retirée de la mise en avant'}.",
    })


@login_required
@require_POST
def admin_toggle_publie(request, pk):
    """Publie / dépublie une vidéo (modération admin)."""
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)

    video = get_object_or_404(VideoCommerce, pk=pk)
    video.est_publie = not video.est_publie
    video.save(update_fields=['est_publie'])

    return JsonResponse({
        'success':    True,
        'est_publie': video.est_publie,
        'message':    f"« {video.titre} » {'publiée' if video.est_publie else 'dépubliée'}.",
    })



# =============================================================================
# HELPERS
# =============================================================================

def _generer_code_parrainage(user):
    """Génère un code de parrainage unique basé sur le username."""
    from django.utils.text import slugify
    import random
    import string

    base = slugify(user.username).upper().replace('-', '')[:12] or 'INF'
    while True:
        suffixe = ''.join(random.choices(string.digits, k=4))
        code = f"{base}{suffixe}"
        if not ProgrammeInfluenceur.objects.filter(code_parrainage=code).exists():
            return code


def enregistrer_conversion_influenceur(request, commande):
    """
    À appeler depuis le tunnel de commande (apps_marketplace) juste après
    la création d'une Commande confirmée.
    Lit le code d'affiliation attribué en session, crée la ConversionInfluenceur
    et met à jour les compteurs si un influenceur actif est trouvé.

    Usage :
        from apps_social.views_influenceurs import enregistrer_conversion_influenceur
        enregistrer_conversion_influenceur(request, commande)
    """
    code = request.session.get('ref_code')
    if not code:
        return None

    programme = ProgrammeInfluenceur.objects.filter(
        code_parrainage=code, statut='actif'
    ).first()
    if not programme:
        return None

    # Un influenceur ne peut pas toucher de commission sur ses propres achats
    if programme.influenceur == commande.utilisateur:
        return None

    # Évite de compter deux fois la même commande
    if ConversionInfluenceur.objects.filter(commande=commande).exists():
        return None

    commission = (programme.taux_commission / Decimal('100')) * commande.montant_total

    conversion = ConversionInfluenceur.objects.create(
        influenceur=programme,
        utilisateur_converti=commande.utilisateur,
        commande=commande,
        montant_commande=commande.montant_total,
        commission_gagnee=commission,
    )

    ProgrammeInfluenceur.objects.filter(pk=programme.pk).update(
        nb_conversions=F('nb_conversions') + 1,
        chiffre_affaires_genere=F('chiffre_affaires_genere') + commande.montant_total,
        commissions_gagnees=F('commissions_gagnees') + commission,
    )

    # Le lien d'affiliation ne compte que pour une commande (évite le farming répété)
    del request.session['ref_code']

    return conversion


# =============================================================================
# PUBLIC — Candidature & suivi du lien
# =============================================================================

@login_required
def devenir_influenceur(request):
    """Formulaire de candidature au programme influenceur."""
    if hasattr(request.user, 'programme_influenceur'):
        return redirect('apps_social:mon_espace_influenceur')

    if request.method == 'POST':
        niveau = request.POST.get('niveau', 'nano')
        if niveau not in dict(ProgrammeInfluenceur.NIVEAU_CHOICES):
            niveau = 'nano'

        code = _generer_code_parrainage(request.user)
        programme = ProgrammeInfluenceur.objects.create(
            influenceur=request.user,
            niveau=niveau,
            code_parrainage=code,
            statut='candidature',
        )
        programme.lien_affiliation = request.build_absolute_uri(
            reverse('apps_social:suivre_lien_affiliation', kwargs={'code': code})
        )
        programme.save(update_fields=['lien_affiliation'])

        messages.success(request, "Votre candidature a été envoyée ! Nous l'examinons sous peu.")
        return redirect('apps_social:mon_espace_influenceur')

    return render(request, 'apps_social/influenceurs/devenir_influenceur.html', {
        'niveaux':    ProgrammeInfluenceur.NIVEAU_CHOICES,
        'page_titre': 'Devenir influenceur',
    })


@login_required
def mon_espace_influenceur(request):
    """Tableau de bord de l'influenceur connecté."""
    programme = get_object_or_404(ProgrammeInfluenceur, influenceur=request.user)

    conversions = programme.conversions.select_related(
        'utilisateur_converti', 'commande'
    ).order_by('-date_conversion')[:20]

    taux_conversion = 0
    if programme.nb_clics:
        taux_conversion = round((programme.nb_conversions / programme.nb_clics) * 100, 1)

    return render(request, 'apps_social/influenceurs/mon_espace_influenceur.html', {
        'programme':        programme,
        'conversions':      conversions,
        'taux_conversion':  taux_conversion,
        'page_titre':       'Mon espace influenceur',
    })


def suivre_lien_affiliation(request, code):
    """
    Lien public de parrainage (/r/<code>/).
    Enregistre le clic, attribue l'affiliation en session (30 jours), puis redirige.
    """
    programme = ProgrammeInfluenceur.objects.filter(
        code_parrainage=code, statut='actif'
    ).first()

    if programme:
        ProgrammeInfluenceur.objects.filter(pk=programme.pk).update(
            nb_clics=F('nb_clics') + 1
        )
        request.session['ref_code'] = code
        request.session.set_expiry(60 * 60 * 24 * 30)  # 30 jours d'attribution

    destination = request.GET.get('next', '')
    if destination and destination.startswith('/'):
        return redirect(destination)
    return redirect('apps_core:accueil')


# =============================================================================
# ADMIN — Gestion du programme
# =============================================================================

@login_required
def admin_influenceurs_liste(request):
    """Vue admin de tous les programmes influenceurs."""
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')

    qs = ProgrammeInfluenceur.objects.select_related('influenceur').order_by('-date_adhesion')

    statut = request.GET.get('statut', '')
    if statut:
        qs = qs.filter(statut=statut)

    niveau = request.GET.get('niveau', '')
    if niveau:
        qs = qs.filter(niveau=niveau)

    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(
            Q(influenceur__username__icontains=q) | Q(code_parrainage__icontains=q)
        )

    stats = {
        'total':        ProgrammeInfluenceur.objects.count(),
        'candidatures': ProgrammeInfluenceur.objects.filter(statut='candidature').count(),
        'actifs':       ProgrammeInfluenceur.objects.filter(statut='actif').count(),
        'ca_total':     ProgrammeInfluenceur.objects.aggregate(s=Sum('chiffre_affaires_genere'))['s'] or 0,
        'commissions_dues': ProgrammeInfluenceur.objects.aggregate(
            s=Sum(F('commissions_gagnees') - F('commissions_payees'))
        )['s'] or 0,
    }

    paginator = Paginator(qs, 25)
    programmes = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'apps_social/admin/influenceurs_liste.html', {
        'programmes':  programmes,
        'stats':       stats,
        'statut':      statut,
        'niveau':      niveau,
        'q':           q,
        'statuts':     ProgrammeInfluenceur.STATUT_CHOICES,
        'niveaux':     ProgrammeInfluenceur.NIVEAU_CHOICES,
        'page_titre':  'Gestion du programme influenceurs',
    })


@login_required
@require_POST
def admin_changer_statut_influenceur(request, pk):
    """Valide / suspend / termine une candidature ou un programme actif (admin)."""
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)

    programme = get_object_or_404(ProgrammeInfluenceur, pk=pk)
    nouveau_statut = request.POST.get('statut', '')

    if nouveau_statut not in dict(ProgrammeInfluenceur.STATUT_CHOICES):
        return JsonResponse({'success': False, 'message': 'Statut invalide'}, status=400)

    programme.statut = nouveau_statut
    if nouveau_statut == 'actif' and not programme.date_validation:
        programme.date_validation = timezone.now()
    programme.save()

    try:
        from apps_core.views_notifications import creer_notification
        libelles = dict(ProgrammeInfluenceur.STATUT_CHOICES)
        creer_notification(
            utilisateur=programme.influenceur,
            type_notification='systeme',
            titre="Statut de votre programme influenceur mis à jour",
            message=f"Votre programme est maintenant : {libelles.get(nouveau_statut, nouveau_statut)}.",
            lien=reverse('apps_social:mon_espace_influenceur'),
        )
    except Exception:
        pass

    return JsonResponse({
        'success':        True,
        'statut':         programme.statut,
        'statut_display': programme.get_statut_display(),
        'message':        f"Statut de @{programme.influenceur.username} mis à jour.",
    })


@login_required
def admin_conversions_influenceur(request, pk):
    """Détail des conversions d'un influenceur donné (admin)."""
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')

    programme = get_object_or_404(
        ProgrammeInfluenceur.objects.select_related('influenceur'), pk=pk
    )

    qs = programme.conversions.select_related('utilisateur_converti', 'commande').order_by('-date_conversion')

    paye = request.GET.get('paye', '')
    if paye == '1':
        qs = qs.filter(est_payee=True)
    elif paye == '0':
        qs = qs.filter(est_payee=False)

    paginator = Paginator(qs, 30)
    conversions = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'apps_social/admin/conversions_influenceur.html', {
        'programme':    programme,
        'conversions':  conversions,
        'paye':         paye,
        'page_titre':   f"Conversions — @{programme.influenceur.username}",
    })


@login_required
@require_POST
def admin_marquer_commission_payee(request, pk):
    """Marque une conversion comme payée et met à jour le cumul payé (admin)."""
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)

    conversion = get_object_or_404(ConversionInfluenceur.objects.select_related('influenceur'), pk=pk)

    if conversion.est_payee:
        return JsonResponse({'success': False, 'message': 'Déjà marquée comme payée.'}, status=400)

    conversion.est_payee = True
    conversion.save(update_fields=['est_payee'])

    ProgrammeInfluenceur.objects.filter(pk=conversion.influenceur_id).update(
        commissions_payees=F('commissions_payees') + conversion.commission_gagnee
    )

    return JsonResponse({
        'success': True,
        'message': f"Commission de {conversion.commission_gagnee} XAF marquée comme payée.",
    })


@login_required
@require_POST
def admin_payer_toutes_commissions(request, pk):
    """Marque toutes les commissions en attente d'un influenceur comme payées d'un coup (admin)."""
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Non autorisé'}, status=403)

    programme = get_object_or_404(ProgrammeInfluenceur, pk=pk)
    conversions_impayees = programme.conversions.filter(est_payee=False)

    total = conversions_impayees.aggregate(s=Sum('commission_gagnee'))['s'] or Decimal('0')
    nb = conversions_impayees.update(est_payee=True)

    ProgrammeInfluenceur.objects.filter(pk=programme.pk).update(
        commissions_payees=F('commissions_payees') + total
    )

    return JsonResponse({
        'success': True,
        'message': f"{nb} commission(s) payée(s), total {total} XAF.",
        'total':   float(total),
    })