
# ===========================================================================
# app_enchere/views.py
# Vues — Section 1 : Enchère de base
#
# Couvre :
#   PUBLIC
#     - encheres_liste        : liste/filtres (type, statut, recherche)
#     - enchere_detail        : page enchère + historique des offres
#     - ajax_placer_offre     : enchérir (AJAX, gère extension auto)
#     - ajax_achat_immediat   : achat immédiat (Buy It Now)
#     - ajax_toggle_like      : like/unlike social
#     - ajax_partager         : incrémente le compteur de partages
#     - ajax_etat_enchere     : polling temps réel (prix, temps restant)
#   VENDEUR
#     - mes_encheres          : liste des enchères du vendeur
#     - creer_enchere         : création (produit limité au vendeur)
#     - modifier_enchere      : édition (avant le début)
#     - annuler_enchere       : annulation
#     - terminer_enchere_manuelle : clôture anticipée par le vendeur
#   SYSTÈME / ADMIN
#     - admin_encheres_liste
#     - cron_terminer_encheres_expirees : tâche de fond
# ===========================================================================
 
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.core.paginator import Paginator
from django.db.models import Q, Max, Sum, Count
from django.db import transaction
from django.utils import timezone
from decimal import Decimal, InvalidOperation
 
from .models import (
    Enchere, OffreEnchere, ConfigSmartBid, EnchereFlash, 
    EnchereGroupe, ParticipantEnchereGroupe,AppelOffre, OffreVendeur
)
from apps_core.models import Produit, Categorie


# ---------------------------------------------------------------------------
# Constantes partagées
# ---------------------------------------------------------------------------
 
DUREES_CLASSIQUES = [
    (1,   '1 heure'),
    (2,   '2 heures'),
    (3,   '3 heures'),
    (6,   '6 heures'),
    (12,  '12 heures'),
    (24,  '24 heures'),
    (48,  '48 heures'),
]
 
DUREES_FLASH = [
    (5,   '⚡ 5 min'),
    (10,  '⚡ 10 min'),
    (30,  '⚡ 30 min'),
    (60,  '⚡ 1 heure'),
    (120, '⚡ 2 heures'),
]

# =============================================================================
# HELPERS
# =============================================================================
 
def _produits_eligibles_enchere(user):
    """
    Produits du vendeur pouvant être mis aux enchères :
    ses propres produits actifs avec autorise_enchere=True, et qui
    n'ont pas déjà une enchère associée (OneToOne).
    """
    return Produit.objects.filter(
        vendeur=user, est_actif=True, autorise_enchere=True, enchere__isnull=True
    ).select_related('categorie')
 
 
def _peut_gerer_enchere(user, enchere):
    return user.is_staff or enchere.vendeur == user
 
 
def _meilleure_offre(enchere):
    """Retourne la meilleure offre active de l'enchère, ou None."""
    return enchere.offres.order_by('-montant', 'date_creation').first()


 
# =============================================================================
# PUBLIC — Liste et détail
# =============================================================================
 
def encheres_liste(request):
    """
    Liste publique des enchères avec filtres.
    GET params : type, statut, q, tri
    """
    now = timezone.now()
 
    qs = Enchere.objects.select_related('produit', 'vendeur').filter(
        statut__in=['a_venir', 'en_cours', 'prolongee']
    )
 
    type_filtre = request.GET.get('type', '')
    if type_filtre:
        qs = qs.filter(type_enchere=type_filtre)
 
    statut_filtre = request.GET.get('statut', '')
    if statut_filtre:
        qs = qs.filter(statut=statut_filtre)
 
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(Q(titre__icontains=q) | Q(description__icontains=q))
 
    tri = request.GET.get('tri', 'fin_proche')
    if tri == 'fin_proche':
        qs = qs.order_by('date_fin')
    elif tri == 'recent':
        qs = qs.order_by('-date_creation')
    elif tri == 'prix_asc':
        qs = qs.order_by('prix_actuel')
    elif tri == 'prix_desc':
        qs = qs.order_by('-prix_actuel')
    elif tri == 'populaire':
        qs = qs.order_by('-nb_offres', '-nb_vues')
 
    paginator = Paginator(qs, 20)
    encheres  = paginator.get_page(request.GET.get('page', 1))
 
    # Enchères en cours mises en avant
    en_vedette = Enchere.objects.filter(
        statut__in=['en_cours', 'prolongee'], date_fin__gt=now
    ).order_by('-nb_offres')[:4]
 
    context = {
        'encheres':    encheres,
        'en_vedette':  en_vedette,
        'type_filtre': type_filtre,
        'statut_filtre': statut_filtre,
        'q':           q,
        'tri':         tri,
        'types':       Enchere.TYPE_CHOICES,
        'statuts':     Enchere.STATUT_CHOICES,
        'page_titre':  'Enchères — YopiShop',
    }
    return render(request, 'apps_enchere/encheres_liste.html', context)



 
# ===========================================================================
# VUE : Détail d'une enchère
# ===========================================================================
 
def enchere_detail(request, pk):
    enchere = get_object_or_404(
        Enchere.objects.select_related(
            'produit', 'vendeur', 'gagnant',
            'config_flash', 'config_groupe',
        ),
        pk=pk
    )
 
    if not request.user.is_authenticated or request.user != enchere.vendeur:
        Enchere.objects.filter(pk=pk).update(nb_vues=enchere.nb_vues + 1)
 
    offres_recentes = enchere.offres.select_related('encherisseur').order_by(
        '-montant', '-date_creation'
    )[:20]
 
    meilleure_offre   = offres_recentes.first() if offres_recentes else None
    je_suis_meilleur  = (
        request.user.is_authenticated and meilleure_offre and
        meilleure_offre.encherisseur == request.user
    )
 
    ma_derniere_offre = None
    smart_bid_actif   = None
    user_a_like       = False
 
    # ── Données Groupe ──
    config_groupe          = getattr(enchere, 'config_groupe', None)
    ma_participation_groupe = None
    participants_groupe     = []
    nb_participants_confirmes = 0
    quantite_restante       = None
    progression_groupe      = 0
 
    if config_groupe:
        participants_groupe = config_groupe.participants.select_related(
            'utilisateur'
        ).order_by('-a_confirme', '-date_adhesion')
 
        nb_participants_confirmes = participants_groupe.filter(a_confirme=True).count()
        quantite_reservee         = sum(
            p.quantite_souhaitee for p in participants_groupe.filter(a_confirme=True)
        )
        quantite_restante = max(0, config_groupe.quantite_totale - quantite_reservee)
 
        if config_groupe.nb_participants_min > 0:
            progression_groupe = min(
                100,
                round(nb_participants_confirmes / config_groupe.nb_participants_min * 100)
            )
 
        if request.user.is_authenticated:
            ma_participation_groupe = participants_groupe.filter(
                utilisateur=request.user
            ).first()
 
    if request.user.is_authenticated:
        ma_derniere_offre = enchere.offres.filter(
            encherisseur=request.user
        ).order_by('-montant').first()
        smart_bid_actif = _get_smart_bid(request.user, enchere)
        user_a_like     = request.session.get(f'enchere_like_{pk}', False)
 
    offre_minimum = enchere.prix_actuel + enchere.increment_minimum
 
    context = {
        'enchere':             enchere,
        'offres_recentes':     offres_recentes,
        'meilleure_offre':     meilleure_offre,
        'je_suis_meilleur':    je_suis_meilleur,
        'ma_derniere_offre':   ma_derniere_offre,
        'offre_minimum':       offre_minimum,
        'est_active':          enchere.est_active(),
        'smart_bid_actif':     smart_bid_actif,
        'user_a_like':         user_a_like,
        # ── Groupe ──
        'config_groupe':             config_groupe,
        'participants_groupe':        participants_groupe,
        'ma_participation_groupe':    ma_participation_groupe,
        'nb_participants_confirmes':  nb_participants_confirmes,
        'quantite_restante':          quantite_restante,
        'progression_groupe':         progression_groupe,
        'page_titre':                 enchere.titre,
    }
    return render(request, 'apps_enchere/enchere_detail.html', context)
 
 



# =============================================================================
# AJAX — Enchérir / Achat immédiat / Social
# =============================================================================
 
@login_required
@require_POST
@transaction.atomic
def ajax_placer_offre(request, pk):
    """
    Place une offre sur l'enchère (AJAX).
    Verrouille la ligne pour éviter les conditions de course (concurrent bids).
    """
    enchere = get_object_or_404(
        Enchere.objects.select_for_update(), pk=pk
    )
 
    if not enchere.est_active():
        return JsonResponse({'success': False, 'message': "Cette enchère n'est pas active."}, status=400)
 
    if enchere.vendeur == request.user:
        return JsonResponse({'success': False, 'message': "Vous ne pouvez pas enchérir sur votre propre produit."}, status=400)
 
    try:
        montant = Decimal(request.POST.get('montant', '0'))
    except (InvalidOperation, TypeError):
        return JsonResponse({'success': False, 'message': "Montant invalide."}, status=400)
 
    montant_minimum = enchere.prix_actuel + enchere.increment_minimum
    if montant < montant_minimum:
        return JsonResponse({
            'success': False,
            'message': f"L'offre doit être d'au moins {montant_minimum:,.0f} {enchere.devise}.",
            'montant_minimum': float(montant_minimum),
        }, status=400)
 
    # Créer l'offre (le modèle OffreEnchere est dans la même app, import local)
    from .models import OffreEnchere
    offre = OffreEnchere.objects.create(
        enchere=enchere,
        encherisseur=request.user,
        montant=montant,
    )
 
    enchere.mettre_a_jour_prix(montant)
    prolongee = enchere.verifier_extension()
 
    # Points de gamification
    try:
        request.user.points_fidelite = (request.user.points_fidelite or 0) + enchere.points_participation
        request.user.save(update_fields=['points_fidelite'])
    except Exception:
        pass
 
    # Notifier l'ancien meilleur enchérisseur qu'il a été surenchéri
    try:
        from apps_core.views_notifications import creer_notification
        offres_precedentes = enchere.offres.exclude(pk=offre.pk).exclude(
            encherisseur=request.user
        ).order_by('-montant').first()
        if offres_precedentes:
            creer_notification(
                utilisateur=offres_precedentes.encherisseur,
                type_notification='enchere',
                titre="Vous avez été surenchéri !",
                message=f"Une nouvelle offre de {montant:,.0f} {enchere.devise} a été placée sur « {enchere.titre} ».",
                lien=f"/encheres/{enchere.pk}/",
            )
    except Exception:
        pass
 
    return JsonResponse({
        'success':          True,
        'message':          "Offre placée avec succès !",
        'prix_actuel':      float(enchere.prix_actuel),
        'nb_offres':        enchere.nb_offres,
        'prolongee':        prolongee,
        'nouvelle_date_fin': enchere.date_fin.isoformat(),
        'montant_min_suivant': float(enchere.prix_actuel + enchere.increment_minimum),
        'points_gagnes':    enchere.points_participation,
    })
 
 
@login_required
@require_POST
@transaction.atomic
def ajax_achat_immediat(request, pk):
    """Achat immédiat (Buy It Now) — termine l'enchère instantanément."""
    enchere = get_object_or_404(Enchere.objects.select_for_update(), pk=pk)
 
    if not enchere.est_active():
        return JsonResponse({'success': False, 'message': "Cette enchère n'est pas active."}, status=400)
 
    if not enchere.prix_achat_immediat:
        return JsonResponse({'success': False, 'message': "Achat immédiat non disponible."}, status=400)
 
    if enchere.vendeur == request.user:
        return JsonResponse({'success': False, 'message': "Vous ne pouvez pas acheter votre propre produit."}, status=400)
 
    from .models import OffreEnchere
    OffreEnchere.objects.create(
        enchere=enchere, encherisseur=request.user,
        montant=enchere.prix_achat_immediat, est_achat_immediat=True,
    )
 
    enchere.prix_actuel = enchere.prix_achat_immediat
    enchere.gagnant = request.user
    enchere.statut = 'terminee'
    enchere.save()
    enchere._creer_commande_gagnant()
 
    try:
        from apps_core.views_notifications import creer_notification
        creer_notification(
            utilisateur=enchere.vendeur,
            type_notification='enchere',
            titre="Achat immédiat effectué !",
            message=f"« {enchere.titre} » a été acheté immédiatement par {request.user.username} "
                    f"pour {enchere.prix_actuel:,.0f} {enchere.devise}.",
            lien=f"/encheres/{enchere.pk}/",
        )
    except Exception:
        pass
 
    return JsonResponse({
        'success': True,
        'message': "Achat immédiat réussi ! Votre commande a été créée.",
        'redirect_url': '/commandes/',
    })
 
 
@login_required
@require_POST
def ajax_toggle_like(request, pk):
    """Like/unlike une enchère (social)."""
    enchere = get_object_or_404(Enchere, pk=pk)
    session_key = f'enchere_like_{pk}'
 
    if request.session.get(session_key):
        Enchere.objects.filter(pk=pk).update(nb_likes=max(0, enchere.nb_likes - 1))
        request.session[session_key] = False
        liked = False
    else:
        Enchere.objects.filter(pk=pk).update(nb_likes=enchere.nb_likes + 1)
        request.session[session_key] = True
        liked = True
 
    enchere.refresh_from_db(fields=['nb_likes'])
    return JsonResponse({'success': True, 'liked': liked, 'nb_likes': enchere.nb_likes})
 
 
@require_POST
def ajax_partager(request, pk):
    """Incrémente le compteur de partages."""
    enchere = get_object_or_404(Enchere, pk=pk)
    Enchere.objects.filter(pk=pk).update(nb_partages=enchere.nb_partages + 1)
    return JsonResponse({'success': True, 'nb_partages': enchere.nb_partages + 1})
 
 
@require_GET
def ajax_etat_enchere(request, pk):
    """
    Polling temps réel : prix actuel, temps restant, dernière offre.
    Utilisé en JS toutes les 2-5s sur la page détail.
    """
    enchere = get_object_or_404(Enchere, pk=pk)
    meilleure = _meilleure_offre(enchere)
 
    return JsonResponse({
        'statut':              enchere.statut,
        'prix_actuel':         float(enchere.prix_actuel),
        'nb_offres':           enchere.nb_offres,
        'date_fin':            enchere.date_fin.isoformat(),
        'temps_restant_secondes': max(0, int((enchere.date_fin - timezone.now()).total_seconds())),
        'est_active':          enchere.est_active(),
        'meilleur_enchérisseur': meilleure.encherisseur.username if meilleure else None,
        'montant_min_suivant': float(enchere.prix_actuel + enchere.increment_minimum),
    })

# =============================================================================
# VENDEUR — Gestion (produits limités au vendeur)
# =============================================================================
 
@login_required
def mes_encheres(request):
    """Liste des enchères créées par le vendeur connecté."""
    if not request.user.peut_vendre:
        messages.warning(request, "Réservé aux vendeurs.")
        return redirect('apps_core:tableau_de_bord')
 
    qs = Enchere.objects.filter(
        vendeur=request.user
    ).select_related('produit', 'gagnant').order_by('-date_creation')
 
    statut = request.GET.get('statut', '')
    if statut:
        qs = qs.filter(statut=statut)
 
    paginator = Paginator(qs, 15)
    encheres  = paginator.get_page(request.GET.get('page', 1))
 
    return render(request, 'apps_enchere/mes_encheres.html', {
        'encheres':   encheres,
        'statut':     statut,
        'statuts':    Enchere.STATUT_CHOICES,
        'page_titre': 'Mes enchères',
    })




@login_required
def creer_enchere(request):
    """
    Création d'une enchère.
    Types supportés :
      - 'classique' → enchère standard
      - 'flash'     → durée courte + timer géant (crée EnchereFlash)
      - 'groupe'    → lot partagé entre plusieurs acheteurs (crée EnchereGroupe)
    """
    if not request.user.peut_vendre:
        messages.warning(request, "Vous devez être vendeur pour créer une enchère.")
        return redirect('apps_core:devenir_vendeur')
 
    mes_produits = _produits_eligibles_enchere(request.user)
 
    if not mes_produits.exists():
        messages.info(
            request,
            "Aucun produit éligible. Activez « Autoriser les enchères » "
            "sur un produit actif sans enchère existante."
        )
        return redirect('apps_core:mes_produits')
 
    if request.method == 'POST':
        produit_id = request.POST.get('produit')
        produit = mes_produits.filter(pk=produit_id).first()
        if not produit:
            messages.error(
                request,
                "Produit invalide : vous ne pouvez enchérir que sur "
                "vos propres produits éligibles."
            )
            return redirect('apps_enchere:creer_enchere')
 
        try:
            type_enchere     = request.POST.get('type_enchere', 'classique')
            titre            = request.POST.get('titre', '').strip() or produit.titre
            description      = request.POST.get('description', '').strip() or produit.description_courte
            prix_depart      = Decimal(request.POST.get('prix_depart', '0'))
            prix_reserve_str = request.POST.get('prix_reserve', '').strip()
            prix_achat_str   = request.POST.get('prix_achat_immediat', '').strip()
            increment        = Decimal(request.POST.get('increment_minimum', '500'))
            extension_auto   = request.POST.get('extension_automatique') == 'on'
 
            if prix_depart <= 0:
                raise ValueError("Le prix de départ doit être positif.")
 
            prix_reserve        = Decimal(prix_reserve_str) if prix_reserve_str else None
            prix_achat_immediat = Decimal(prix_achat_str)   if prix_achat_str   else None
 
            if prix_achat_immediat and prix_achat_immediat <= prix_depart:
                raise ValueError(
                    "Le prix d'achat immédiat doit être supérieur au prix de départ."
                )
 
            # ── Durée selon le type ──
            date_debut = timezone.now()
 
            if type_enchere == 'flash':
                duree_minutes = int(request.POST.get('duree_minutes', 30))
                if duree_minutes not in [5, 10, 30, 60, 120]:
                    duree_minutes = 30
                date_fin = date_debut + timezone.timedelta(minutes=duree_minutes)
 
            elif type_enchere == 'groupe':
                duree_heures = int(request.POST.get('duree_heures', 24))
                if duree_heures < 1 or duree_heures > 48:
                    raise ValueError("Durée invalide pour une enchère groupe (1h à 48h).")
                date_fin = date_debut + timezone.timedelta(hours=duree_heures)
 
            else:  # classique
                duree_heures = int(request.POST.get('duree_heures', 24))
                if duree_heures < 1 or duree_heures > 48:
                    raise ValueError("Durée invalide (1h à 48h).")
                date_fin = date_debut + timezone.timedelta(hours=duree_heures)
 
        except (ValueError, InvalidOperation, TypeError) as e:
            messages.error(request, f"Erreur de saisie : {e}")
            return redirect('apps_enchere:creer_enchere')
 
        # ── Création de l'enchère principale ──
        enchere = Enchere.objects.create(
            produit=produit,
            vendeur=request.user,
            type_enchere=type_enchere,
            titre=titre,
            description=description,
            prix_depart=prix_depart,
            prix_reserve=prix_reserve,
            prix_actuel=prix_depart,
            prix_achat_immediat=prix_achat_immediat,
            date_debut=date_debut,
            date_fin=date_fin,
            increment_minimum=increment,
            extension_automatique=extension_auto,
            statut='en_cours',
        )
 
        image = request.FILES.get('image_couverture')
        if image:
            enchere.image_couverture = image
            enchere.save(update_fields=['image_couverture'])
 
        # ── Config Flash ──
        if type_enchere == 'flash':
            try:
                extension_sec    = int(request.POST.get('extension_par_offre_secondes', 30))
                timer_geant      = request.POST.get('afficher_timer_geant') == 'on'
                couleur_urgence  = request.POST.get('couleur_urgence', '#FF0000').strip() or '#FF0000'
                nb_max_str       = request.POST.get('nb_acheteurs_max', '').strip()
                nb_acheteurs_max = int(nb_max_str) if nb_max_str else None
 
                EnchereFlash.objects.create(
                    enchere=enchere,
                    duree_minutes=duree_minutes,
                    extension_par_offre_secondes=max(0, min(120, extension_sec)),
                    afficher_timer_geant=timer_geant,
                    couleur_urgence=couleur_urgence,
                    nb_acheteurs_max=nb_acheteurs_max,
                )
            except (ValueError, TypeError):
                pass
 
        # ── Config Groupe ──
        elif type_enchere == 'groupe':
            try:
                qte_totale      = int(request.POST.get('quantite_totale', 0))
                qte_min_pp      = int(request.POST.get('quantite_min_par_participant', 1))
                qte_max_pp_str  = request.POST.get('quantite_max_par_participant', '').strip()
                nb_part_min     = int(request.POST.get('nb_participants_min', 2))
                nb_part_max_str = request.POST.get('nb_participants_max', '').strip()
 
                if qte_totale < 1:
                    raise ValueError("La quantité totale doit être ≥ 1.")
                if qte_min_pp < 1:
                    raise ValueError("La quantité minimum par participant doit être ≥ 1.")
                if nb_part_min < 2:
                    raise ValueError("Il faut au moins 2 participants.")
 
                qte_max_pp  = int(qte_max_pp_str)  if qte_max_pp_str  else None
                nb_part_max = int(nb_part_max_str)  if nb_part_max_str else None
 
                if qte_max_pp and qte_max_pp < qte_min_pp:
                    raise ValueError("La quantité max par participant doit être ≥ quantité min.")
                if nb_part_max and nb_part_max < nb_part_min:
                    raise ValueError("Le nb max de participants doit être ≥ nb min.")
 
                EnchereGroupe.objects.create(
                    enchere=enchere,
                    quantite_totale=qte_totale,
                    quantite_min_par_participant=qte_min_pp,
                    quantite_max_par_participant=qte_max_pp,
                    nb_participants_min=nb_part_min,
                    nb_participants_max=nb_part_max,
                )
            except (ValueError, TypeError) as e:
                # Supprimer l'enchère créée si la config groupe échoue
                enchere.delete()
                messages.error(request, f"Erreur configuration groupe : {e}")
                return redirect('apps_enchere:creer_enchere')
 
        messages.success(request, f"Enchère « {enchere.titre} » créée et lancée !")
        return redirect('apps_enchere:enchere_detail', pk=enchere.pk)
 
    return render(request, 'apps_enchere/enchere_form.html', {
        'mes_produits': mes_produits,
        'types':        Enchere.TYPE_CHOICES,
        'mode':         'creation',
        'page_titre':   'Créer une enchère',
        'durees':       DUREES_CLASSIQUES,
        'flash_durees': DUREES_FLASH,
    })
 
 
 
 

# ===========================================================================
# VUE : Modifier une enchère existante
# ===========================================================================
 
@login_required
def modifier_enchere(request, pk):
    """
    Modification d'une enchère existante.
    - Si des offres ou participants existent → champs sensibles figés.
    - Config Flash/Groupe modifiables si aucune offre/participant.
    """
    enchere = get_object_or_404(Enchere, pk=pk, vendeur=request.user)
 
    if enchere.statut not in ('en_cours', 'prolongee', 'planifiee'):
        messages.error(request, "Cette enchère ne peut plus être modifiée.")
        return redirect('apps_enchere:enchere_detail', pk=pk)
 
    a_des_offres    = enchere.nb_offres > 0
    est_flash       = enchere.type_enchere == 'flash'
    est_groupe      = enchere.type_enchere == 'groupe'
    config_flash    = getattr(enchere, 'config_flash',  None)
    config_groupe   = getattr(enchere, 'config_groupe', None)
 
    # Vérifier les participants groupe
    a_des_participants = False
    if est_groupe and config_groupe:
        a_des_participants = config_groupe.participants.filter(a_confirme=True).exists()
 
    fige = a_des_offres or a_des_participants
 
    if request.method == 'POST':
        try:
            titre       = request.POST.get('titre', '').strip()
            description = request.POST.get('description', '').strip()
 
            if not titre:
                raise ValueError("Le titre est requis.")
 
            # Champs figés si offres ou participants
            if not fige:
                prix_depart_str  = request.POST.get('prix_depart', '').strip()
                prix_reserve_str = request.POST.get('prix_reserve', '').strip()
                type_enchere     = request.POST.get('type_enchere', enchere.type_enchere)
                prix_depart      = Decimal(prix_depart_str) if prix_depart_str else enchere.prix_depart
                if prix_depart <= 0:
                    raise ValueError("Le prix de départ doit être positif.")
                prix_reserve = Decimal(prix_reserve_str) if prix_reserve_str else None
            else:
                prix_depart  = enchere.prix_depart
                prix_reserve = enchere.prix_reserve
                type_enchere = enchere.type_enchere
 
            # Toujours modifiables
            prix_achat_str      = request.POST.get('prix_achat_immediat', '').strip()
            prix_achat_immediat = Decimal(prix_achat_str) if prix_achat_str else None
            if prix_achat_immediat and prix_achat_immediat <= enchere.prix_actuel:
                raise ValueError(
                    f"Le prix d'achat immédiat doit dépasser le prix actuel "
                    f"({enchere.prix_actuel:,.0f} {enchere.devise})."
                )
 
            increment      = Decimal(request.POST.get('increment_minimum', str(enchere.increment_minimum)))
            extension_auto = request.POST.get('extension_automatique') == 'on'
 
            # Extension de durée (classique et groupe seulement)
            if not est_flash:
                heures_sup_str = request.POST.get('heures_supplementaires', '').strip()
                if heures_sup_str:
                    heures_sup = int(heures_sup_str)
                    if 1 <= heures_sup <= 48:
                        enchere.date_fin += timezone.timedelta(hours=heures_sup)
 
            enchere.titre               = titre
            enchere.description         = description
            enchere.prix_depart         = prix_depart
            enchere.prix_reserve        = prix_reserve
            enchere.prix_achat_immediat = prix_achat_immediat
            enchere.increment_minimum   = increment
            enchere.extension_automatique = extension_auto
            enchere.type_enchere        = type_enchere
 
            enchere.save(update_fields=[
                'titre', 'description', 'prix_depart', 'prix_reserve',
                'prix_achat_immediat', 'increment_minimum',
                'extension_automatique', 'type_enchere', 'date_fin',
            ])
 
            image = request.FILES.get('image_couverture')
            if image:
                enchere.image_couverture = image
                enchere.save(update_fields=['image_couverture'])
 
            # Mise à jour config Flash
            if type_enchere == 'flash' and not fige:
                try:
                    extension_sec   = int(request.POST.get('extension_par_offre_secondes', 30))
                    timer_geant     = request.POST.get('afficher_timer_geant') == 'on'
                    couleur_urgence = request.POST.get('couleur_urgence', '#FF0000').strip() or '#FF0000'
                    nb_max_str      = request.POST.get('nb_acheteurs_max', '').strip()
                    nb_acheteurs_max = int(nb_max_str) if nb_max_str else None
 
                    if config_flash:
                        config_flash.extension_par_offre_secondes = max(0, min(120, extension_sec))
                        config_flash.afficher_timer_geant = timer_geant
                        config_flash.couleur_urgence = couleur_urgence
                        config_flash.nb_acheteurs_max = nb_acheteurs_max
                        config_flash.save()
                    else:
                        duree_minutes = int(request.POST.get('duree_minutes', 30))
                        EnchereFlash.objects.create(
                            enchere=enchere,
                            duree_minutes=duree_minutes,
                            extension_par_offre_secondes=max(0, min(120, extension_sec)),
                            afficher_timer_geant=timer_geant,
                            couleur_urgence=couleur_urgence,
                            nb_acheteurs_max=nb_acheteurs_max,
                        )
                except (ValueError, TypeError):
                    pass
 
            # Mise à jour config Groupe
            elif type_enchere == 'groupe' and not fige:
                try:
                    qte_totale      = int(request.POST.get('quantite_totale', 0))
                    qte_min_pp      = int(request.POST.get('quantite_min_par_participant', 1))
                    qte_max_pp_str  = request.POST.get('quantite_max_par_participant', '').strip()
                    nb_part_min     = int(request.POST.get('nb_participants_min', 2))
                    nb_part_max_str = request.POST.get('nb_participants_max', '').strip()
 
                    qte_max_pp  = int(qte_max_pp_str)  if qte_max_pp_str  else None
                    nb_part_max = int(nb_part_max_str)  if nb_part_max_str else None
 
                    if config_groupe:
                        config_groupe.quantite_totale               = qte_totale
                        config_groupe.quantite_min_par_participant   = qte_min_pp
                        config_groupe.quantite_max_par_participant   = qte_max_pp
                        config_groupe.nb_participants_min            = nb_part_min
                        config_groupe.nb_participants_max            = nb_part_max
                        config_groupe.save()
                    else:
                        EnchereGroupe.objects.create(
                            enchere=enchere,
                            quantite_totale=qte_totale,
                            quantite_min_par_participant=qte_min_pp,
                            quantite_max_par_participant=qte_max_pp,
                            nb_participants_min=nb_part_min,
                            nb_participants_max=nb_part_max,
                        )
                except (ValueError, TypeError) as e:
                    messages.warning(request, f"Enchère mise à jour mais erreur config groupe : {e}")
 
            messages.success(request, f"Enchère « {enchere.titre} » mise à jour.")
            return redirect('apps_enchere:enchere_detail', pk=pk)
 
        except (ValueError, InvalidOperation, TypeError) as e:
            messages.error(request, f"Erreur : {e}")
 
    return render(request, 'apps_enchere/enchere_form.html', {
        'enchere':       enchere,
        'config_flash':  config_flash,
        'config_groupe': config_groupe,
        'types':         Enchere.TYPE_CHOICES,
        'a_des_offres':  a_des_offres,
        'a_des_participants': a_des_participants,
        'fige':          fige,
        'est_flash':     est_flash,
        'est_groupe':    est_groupe,
        'mode':          'edition',
        'page_titre':    f"Modifier — {enchere.titre}",
        'durees':        DUREES_CLASSIQUES,
        'flash_durees':  DUREES_FLASH,
    })
 
 
@login_required
@require_POST
def annuler_enchere(request, pk):
    """Annule une enchère (vendeur ou admin)."""
    enchere = get_object_or_404(Enchere, pk=pk)
 
    if not _peut_gerer_enchere(request.user, enchere):
        messages.error(request, "Action non autorisée.")
        return redirect('apps_enchere:mes_encheres')
 
    if enchere.statut == 'terminee':
        messages.error(request, "Impossible d'annuler une enchère déjà terminée.")
        return redirect('apps_enchere:enchere_detail', pk=pk)
 
    enchere.statut = 'annulee'
    enchere.save(update_fields=['statut'])
 
    try:
        from apps_core.views_notifications import creer_notification_masse
        participants = [o.encherisseur for o in enchere.offres.all().distinct()]
        if participants:
            creer_notification_masse(
                utilisateurs_qs=set(participants),
                type_notification='enchere',
                titre="Enchère annulée",
                message=f"L'enchère « {enchere.titre} » a été annulée par le vendeur.",
                lien=f"/encheres/{enchere.pk}/",
            )
    except Exception:
        pass
 
    messages.success(request, "Enchère annulée.")
    return redirect('apps_enchere:mes_encheres')
 
 
@login_required
@require_POST
def terminer_enchere_manuelle(request, pk):
    """Le vendeur clôture l'enchère immédiatement (avant la date de fin)."""
    enchere = get_object_or_404(Enchere, pk=pk)
 
    if not _peut_gerer_enchere(request.user, enchere):
        messages.error(request, "Action non autorisée.")
        return redirect('apps_enchere:mes_encheres')
 
    if enchere.statut not in ('en_cours', 'prolongee'):
        messages.error(request, "Cette enchère ne peut pas être clôturée maintenant.")
        return redirect('apps_enchere:enchere_detail', pk=pk)
 
    enchere.date_fin = timezone.now()
    enchere.save(update_fields=['date_fin'])
    enchere.terminer()
 
    if enchere.gagnant:
        try:
            from apps_core.views_notifications import creer_notification
            creer_notification(
                utilisateur=enchere.gagnant,
                type_notification='enchere',
                titre="🎉 Vous avez remporté l'enchère !",
                message=f"Félicitations ! Vous avez remporté « {enchere.titre} » "
                        f"pour {enchere.prix_actuel:,.0f} {enchere.devise}.",
                lien='/commandes/',
            )
        except Exception:
            pass
        messages.success(request, f"Enchère clôturée. Gagnant : {enchere.gagnant.username}.")
    else:
        messages.info(request, "Enchère clôturée sans offre gagnante.")
 
    return redirect('apps_enchere:mes_encheres')


@require_GET
def ajax_etat_enchere(request, pk):
    enchere   = get_object_or_404(Enchere, pk=pk)
    meilleure = _meilleure_offre(enchere)

    # ← Récupérer les 20 dernières offres pour l'historique
    offres_qs = enchere.offres.select_related('encherisseur').order_by(
        '-montant', '-date_creation'
    )[:20]

    offres_data = [{
        'encherisseur': o.encherisseur.username,
        'montant':      float(o.montant),
        'est_auto':     o.est_offre_auto,
        'est_immediat': o.est_achat_immediat,
        'date':         o.date_creation.strftime('%d/%m/%Y %H:%M'),
    } for o in offres_qs]

    return JsonResponse({
        'statut':                  enchere.statut,
        'prix_actuel':             float(enchere.prix_actuel),
        'nb_offres':               enchere.nb_offres,
        'date_fin':                enchere.date_fin.isoformat(),
        'temps_restant_secondes':  max(0, int((enchere.date_fin - timezone.now()).total_seconds())),
        'est_active':              enchere.est_active(),
        'meilleur_encherisseur':   meilleure.encherisseur.username if meilleure else None,
        'montant_min_suivant':     float(enchere.prix_actuel + enchere.increment_minimum),
        'offres':                  offres_data,   # ← ajouté
    })



# =============================================================================
# ADMIN / SYSTÈME
# =============================================================================
 

@login_required
def admin_encheres_liste(request):
    """Vue admin de toutes les enchères de la plateforme."""
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')
 
    qs = Enchere.objects.select_related('produit', 'vendeur', 'gagnant').order_by('-date_creation')
 
    statut = request.GET.get('statut', '')
    if statut:
        qs = qs.filter(statut=statut)
 
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(Q(titre__icontains=q) | Q(vendeur__username__icontains=q))
 
    stats = {
        'a_venir':   Enchere.objects.filter(statut='a_venir').count(),
        'en_cours':  Enchere.objects.filter(statut__in=['en_cours', 'prolongee']).count(),
        'terminee':  Enchere.objects.filter(statut='terminee').count(),
        'annulee':   Enchere.objects.filter(statut='annulee').count(),
    }
 
    paginator = Paginator(qs, 30)
    encheres  = paginator.get_page(request.GET.get('page', 1))
 
    return render(request, 'apps_enchere/admin_encheres_liste.html', {
        'encheres':   encheres,
        'stats':      stats,
        'statut':     statut,
        'q':          q,
        'statuts':    Enchere.STATUT_CHOICES,
        'page_titre': 'Gestion des enchères',
    })
 
 
@login_required
def cron_terminer_encheres_expirees(request):
    """
    Vue déclenchable manuellement par un admin (ou via tâche planifiée/webhook)
    pour terminer toutes les enchères dont la date de fin est dépassée.
    """
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')
 
    now = timezone.now()
    encheres_a_clore = Enchere.objects.filter(
        statut__in=['en_cours', 'prolongee'], date_fin__lte=now
    )
 
    nb_terminees = 0
    for enchere in encheres_a_clore:
        enchere.terminer()
        nb_terminees += 1
        if enchere.gagnant:
            try:
                from apps_core.views_notifications import creer_notification
                creer_notification(
                    utilisateur=enchere.gagnant,
                    type_notification='enchere',
                    titre="🎉 Vous avez remporté l'enchère !",
                    message=f"Vous avez remporté « {enchere.titre} » pour {enchere.prix_actuel:,.0f} {enchere.devise}.",
                    lien='/commandes/',
                )
            except Exception:
                pass
 
    messages.success(request, f"{nb_terminees} enchère(s) clôturée(s).")
    return redirect('apps_enchere:admin_encheres_liste')
 


# =============================================================================
# HELPERS
# =============================================================================
 
def _get_smart_bid(user, enchere):
    """Retourne le ConfigSmartBid actif d'un user sur une enchère, ou None."""
    return ConfigSmartBid.objects.filter(
        utilisateur=user, enchere=enchere, est_active=True
    ).first()
 
 
def _executer_smart_bid(config, enchere):
    """
    Exécute un Smart Bid selon sa stratégie.
    Retourne (offre_creee, montant) ou (None, None) si conditions non remplies.
    """
    if not config.peut_encherir(enchere.prix_actuel):
        return None, None
 
    montant = config.calculer_prochain_montant(enchere.prix_actuel)
    if montant is None:
        return None, None
 
    # Vérifier que l'utilisateur n'est pas déjà le meilleur enchérisseur
    meilleure = enchere.offres.order_by('-montant').first()
    if meilleure and meilleure.encherisseur == config.utilisateur:
        return None, None  # déjà en tête, inutile de renchérir
 
    try:
        offre = OffreEnchere.objects.create(
            enchere=enchere,
            encherisseur=config.utilisateur,
            montant=montant,
            est_offre_auto=True,
            montant_max_auto=config.prix_max,
            budget_journalier=config.budget_journalier,
            priorite_achat=config.priorite,
        )
        # Mettre à jour la dépense journalière
        config.depense_jour = (config.depense_jour or Decimal('0')) + montant
        config.save(update_fields=['depense_jour'])
 
        return offre, montant
    except Exception:
        return None, None


# =============================================================================
# HISTORIQUE DES OFFRES — Acheteur
# =============================================================================
 
@login_required
def mes_offres(request):
    """
    Liste de toutes les offres placées par l'utilisateur connecté.
    Permet de suivre ses enchères en cours et passées.
    """
    qs = OffreEnchere.objects.filter(
        encherisseur=request.user
    ).select_related('enchere', 'enchere__produit').order_by('-date_creation')
 
    # Filtres
    statut = request.GET.get('statut', '')
    if statut == 'en_cours':
        qs = qs.filter(enchere__statut__in=['en_cours', 'prolongee'])
    elif statut == 'gagnees':
        qs = qs.filter(enchere__gagnant=request.user)
    elif statut == 'perdues':
        qs = qs.filter(
            enchere__statut='terminee'
        ).exclude(enchere__gagnant=request.user)
 
    # Stats globales
    stats = {
        'total':      OffreEnchere.objects.filter(encherisseur=request.user).count(),
        'en_cours':   OffreEnchere.objects.filter(
                          encherisseur=request.user,
                          enchere__statut__in=['en_cours', 'prolongee']
                      ).values('enchere').distinct().count(),
        'gagnees':    Enchere.objects.filter(gagnant=request.user).count(),
        'depense_totale': OffreEnchere.objects.filter(
                              encherisseur=request.user,
                              enchere__gagnant=request.user
                          ).aggregate(s=Sum('montant'))['s'] or 0,
    }
 
    # Enchères où l'utilisateur est actuellement le meilleur enchérisseur
    encheres_en_tete = Enchere.objects.filter(
        statut__in=['en_cours', 'prolongee'],
        offres__encherisseur=request.user
    ).distinct()
 
    en_tete_ids = set()
    for enc in encheres_en_tete:
        meilleure = enc.offres.order_by('-montant').first()
        if meilleure and meilleure.encherisseur == request.user:
            en_tete_ids.add(enc.pk)
 
    paginator = Paginator(qs, 20)
    offres    = paginator.get_page(request.GET.get('page', 1))
 
    return render(request, 'apps_enchere/mes_offres.html', {
        'offres':      offres,
        'stats':       stats,
        'statut':      statut,
        'en_tete_ids': en_tete_ids,
        'page_titre':  'Mes offres',
    })


@require_GET
def offres_enchere(request, pk):
    """
    Historique public des offres d'une enchère — chargé en AJAX
    ou affiché dans un onglet de la page détail.
    """
    enchere = get_object_or_404(Enchere, pk=pk)
 
    offres = enchere.offres.select_related('encherisseur').order_by(
        '-montant', '-date_creation'
    )[:50]
 
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        data = [{
            'encherisseur': o.encherisseur.username,
            'montant':      float(o.montant),
            'est_auto':     o.est_offre_auto,
            'date':         o.date_creation.strftime('%d/%m/%Y %H:%M:%S'),
        } for o in offres]
        return JsonResponse({'offres': data, 'nb_total': enchere.nb_offres})
 
    return render(request, 'apps_enchere/offres_enchere.html', {
        'enchere':    enchere,
        'offres':     offres,
        'page_titre': f"Offres — {enchere.titre}",
    })


# =============================================================================
# SMART BID IA
# =============================================================================
 
@login_required
def configurer_smart_bid(request, pk):
    """
    Activation ou modification du Smart Bid IA sur une enchère.
    L'utilisateur définit son budget max, sa stratégie et son budget journalier.
    """
    enchere = get_object_or_404(Enchere, pk=pk)
 
    if not enchere.est_active():
        messages.error(request, "Cette enchère n'est plus active.")
        return redirect('apps_enchere:enchere_detail', pk=pk)
 
    if enchere.vendeur == request.user:
        messages.error(request, "Vous ne pouvez pas configurer un Smart Bid sur votre propre enchère.")
        return redirect('apps_enchere:enchere_detail', pk=pk)
 
    # Config existante
    config_existante = ConfigSmartBid.objects.filter(
        utilisateur=request.user, enchere=enchere
    ).first()
 
    STRATEGIES = [
        ('progressive', 'Progressive — enchérit au minimum nécessaire'),
        ('aggressive',  'Agressive — surenchérit pour décourager les autres'),
        ('last_second', 'Dernière seconde — snipe dans les 60 dernières secondes'),
    ]
 
    if request.method == 'POST':
        try:
            prix_max_str        = request.POST.get('prix_max', '').strip()
            budget_jour_str     = request.POST.get('budget_journalier', '').strip()
            strategie           = request.POST.get('strategie', 'progressive')
            priorite            = int(request.POST.get('priorite', 5))
 
            if not prix_max_str:
                raise ValueError("Le budget maximum est requis.")
 
            prix_max = Decimal(prix_max_str)
            montant_min_requis = enchere.prix_actuel + enchere.increment_minimum
 
            if prix_max < montant_min_requis:
                raise ValueError(
                    f"Le budget max doit être d'au moins {montant_min_requis:,.0f} {enchere.devise} "
                    f"(prix actuel + incrément minimum)."
                )
 
            budget_journalier = Decimal(budget_jour_str) if budget_jour_str else None
            priorite = max(1, min(10, priorite))
            if strategie not in [s[0] for s in STRATEGIES]:
                strategie = 'progressive'
 
            if config_existante:
                config_existante.prix_max         = prix_max
                config_existante.budget_journalier = budget_journalier
                config_existante.strategie        = strategie
                config_existante.priorite         = priorite
                config_existante.est_active       = True
                config_existante.depense_jour     = Decimal('0')
                config_existante.save()
                config = config_existante
                messages.success(request, "Smart Bid mis à jour et réactivé.")
            else:
                config = ConfigSmartBid.objects.create(
                    utilisateur=request.user,
                    enchere=enchere,
                    prix_max=prix_max,
                    budget_journalier=budget_journalier,
                    strategie=strategie,
                    priorite=priorite,
                )
                messages.success(request, f"Smart Bid activé ! Budget max : {prix_max:,.0f} {enchere.devise}.")
 
            # Exécuter immédiatement si la stratégie le permet
            enchere.refresh_from_db()
            offre, montant = _executer_smart_bid(config, enchere)
            if offre:
                messages.info(request, f"Première offre automatique placée : {montant:,.0f} {enchere.devise}.")
 
            return redirect('apps_enchere:enchere_detail', pk=pk)
 
        except (ValueError, InvalidOperation) as e:
            messages.error(request, f"Erreur : {e}")
 
    context = {
        'enchere':          enchere,
        'config_existante': config_existante,
        'strategies':       STRATEGIES,
        'montant_min':      enchere.prix_actuel + enchere.increment_minimum,
        'page_titre':       f"Smart Bid — {enchere.titre}",
    }
    return render(request, 'apps_enchere/smart_bid_form.html', context)



@login_required
def mes_smart_bids(request):
    """Liste de tous les Smart Bids actifs et passés de l'utilisateur."""
    configs = ConfigSmartBid.objects.filter(
        utilisateur=request.user
    ).select_related('enchere', 'enchere__produit').order_by('-date_activation')
 
    filtre = request.GET.get('filtre', '')
    if filtre == 'actifs':
        configs = configs.filter(est_active=True, enchere__statut__in=['en_cours', 'prolongee'])
    elif filtre == 'inactifs':
        configs = configs.filter(est_active=False)
 
    stats = {
        'total':  configs.count(),
        'actifs': ConfigSmartBid.objects.filter(
                      utilisateur=request.user, est_active=True,
                      enchere__statut__in=['en_cours', 'prolongee']
                  ).count(),
        'offres_auto': OffreEnchere.objects.filter(
                           encherisseur=request.user, est_offre_auto=True
                       ).count(),
    }
 
    paginator = Paginator(configs, 15)
    smart_bids = paginator.get_page(request.GET.get('page', 1))
 
    return render(request, 'apps_enchere/mes_smart_bids.html', {
        'smart_bids': smart_bids,
        'stats':      stats,
        'filtre':     filtre,
        'page_titre': 'Mes Smart Bids',
    })


@login_required
@require_POST
def desactiver_smart_bid(request, pk):
    """Désactive un Smart Bid (l'utilisateur arrête les enchères automatiques)."""
    config = get_object_or_404(
        ConfigSmartBid, pk=pk, utilisateur=request.user
    )
    config.est_active = False
    config.save(update_fields=['est_active'])
 
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': 'Smart Bid désactivé.'})
 
    messages.success(request, f"Smart Bid désactivé sur « {config.enchere.titre} ».")
    return redirect('apps_enchere:mes_smart_bids')
 
 
@login_required
@require_GET
def ajax_smart_bid_status(request, pk):
    """
    Retourne l'état en temps réel du Smart Bid sur une enchère.
    Utilisé en polling depuis la page détail enchère.
    """
    enchere = get_object_or_404(Enchere, pk=pk)
    config  = _get_smart_bid(request.user, enchere)
 
    if not config:
        return JsonResponse({'actif': False})
 
    meilleure = enchere.offres.order_by('-montant').first()
    je_suis_meilleur = meilleure and meilleure.encherisseur == request.user
 
    return JsonResponse({
        'actif':            config.est_active,
        'prix_max':         float(config.prix_max),
        'strategie':        config.strategie,
        'peut_encherir':    config.peut_encherir(enchere.prix_actuel),
        'depense_jour':     float(config.depense_jour or 0),
        'budget_journalier': float(config.budget_journalier) if config.budget_journalier else None,
        'je_suis_meilleur': je_suis_meilleur,
        'prochain_montant': float(
            config.calculer_prochain_montant(enchere.prix_actuel) or 0
        ),
    })


# =============================================================================
# ADMIN
# =============================================================================
 
@login_required
def admin_offres_liste(request):
    """Vue admin de toutes les offres de la plateforme."""
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')
 
    qs = OffreEnchere.objects.select_related(
        'enchere', 'encherisseur'
    ).order_by('-date_creation')
 
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(
            Q(encherisseur__username__icontains=q) |
            Q(enchere__titre__icontains=q)
        )
 
    est_auto = request.GET.get('auto', '')
    if est_auto == '1':
        qs = qs.filter(est_offre_auto=True)
    elif est_auto == '0':
        qs = qs.filter(est_offre_auto=False)
 
    stats = {
        'total':      OffreEnchere.objects.count(),
        'auto':       OffreEnchere.objects.filter(est_offre_auto=True).count(),
        'immediates': OffreEnchere.objects.filter(est_achat_immediat=True).count(),
        'volume':     OffreEnchere.objects.aggregate(s=Sum('montant'))['s'] or 0,
    }
 
    paginator = Paginator(qs, 30)
    offres    = paginator.get_page(request.GET.get('page', 1))
 
    return render(request, 'apps_enchere/admin_offres_liste.html', {
        'offres':    offres,
        'stats':     stats,
        'q':         q,
        'est_auto':  est_auto,
        'page_titre': 'Gestion des offres',
    })
 
 
@login_required
def admin_smart_bids(request):
    """Vue admin de tous les Smart Bids configurés sur la plateforme."""
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')
 
    qs = ConfigSmartBid.objects.select_related(
        'utilisateur', 'enchere', 'enchere__produit'
    ).order_by('-date_activation')
 
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(
            Q(utilisateur__username__icontains=q) |
            Q(enchere__titre__icontains=q)
        )
 
    actif = request.GET.get('actif', '')
    if actif == '1':
        qs = qs.filter(est_active=True)
    elif actif == '0':
        qs = qs.filter(est_active=False)
 
    stats = {
        'total':  ConfigSmartBid.objects.count(),
        'actifs': ConfigSmartBid.objects.filter(est_active=True).count(),
        'offres_auto': OffreEnchere.objects.filter(est_offre_auto=True).count(),
    }
 
    paginator  = Paginator(qs, 25)
    smart_bids = paginator.get_page(request.GET.get('page', 1))
 
    return render(request, 'apps_enchere/admin_smart_bids.html', {
        'smart_bids': smart_bids,
        'stats':      stats,
        'q':          q,
        'actif':      actif,
        'page_titre': 'Gestion des Smart Bids',
    })
 


# =============================================================================
# SYSTÈME — Tâche planifiée Smart Bid
# =============================================================================
 
@login_required
def cron_executer_smart_bids(request):
    """
    Exécute tous les Smart Bids actifs sur les enchères en cours.
    Déclenchable manuellement par un admin ou via un webhook/cron externe.
 
    Algorithme :
      1. Récupère toutes les enchères actives ayant des Smart Bids actifs
      2. Pour chaque Smart Bid, vérifie s'il doit enchérir
      3. Si oui, place l'offre automatique
      4. Notifie les autres enchérisseurs surpassés
    """
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')
 
    encheres_actives = Enchere.objects.filter(
        statut__in=['en_cours', 'prolongee'],
        smart_bids__est_active=True
    ).distinct().prefetch_related('smart_bids__utilisateur')
 
    nb_offres_placees = 0
    nb_configs_verifiees = 0
 
    for enchere in encheres_actives:
        # Trier par priorité décroissante
        configs = enchere.smart_bids.filter(est_active=True).order_by('-priorite')
 
        for config in configs:
            nb_configs_verifiees += 1
 
            # Vérifier si c'est déjà le meilleur enchérisseur
            meilleure = enchere.offres.order_by('-montant').first()
            if meilleure and meilleure.encherisseur == config.utilisateur:
                continue  # déjà en tête
 
            with transaction.atomic():
                enchere_locked = Enchere.objects.select_for_update().get(pk=enchere.pk)
                offre, montant = _executer_smart_bid(config, enchere_locked)
 
            if offre:
                nb_offres_placees += 1
 
                # Notifier l'ancien meilleur enchérisseur
                if meilleure and meilleure.encherisseur != config.utilisateur:
                    try:
                        from apps_core.views_notifications import creer_notification
                        creer_notification(
                            utilisateur=meilleure.encherisseur,
                            type_notification='enchere',
                            titre="Vous avez été surenchéri par un Smart Bid !",
                            message=f"Un Smart Bid a placé une offre de {montant:,.0f} {enchere.devise} "
                                    f"sur « {enchere.titre} ».",
                            lien=f"/encheres/{enchere.pk}/",
                        )
                    except Exception:
                        pass
 
                # Désactiver si budget épuisé
                config.refresh_from_db(fields=['depense_jour'])
                if config.budget_journalier and config.depense_jour >= config.budget_journalier:
                    config.est_active = False
                    config.save(update_fields=['est_active'])
                    try:
                        from apps_core.views_notifications import creer_notification
                        creer_notification(
                            utilisateur=config.utilisateur,
                            type_notification='enchere',
                            titre="Smart Bid suspendu — budget journalier atteint",
                            message=f"Votre Smart Bid sur « {enchere.titre} » a été suspendu car "
                                    f"votre budget journalier de {config.budget_journalier:,.0f} FCFA est atteint.",
                            lien=f"/encheres/{enchere.pk}/",
                        )
                    except Exception:
                        pass
 
    messages.success(
        request,
        f"{nb_offres_placees} offre(s) automatique(s) placée(s) "
        f"sur {nb_configs_verifiees} Smart Bid(s) vérifiés."
    )
    return redirect('apps_enchere:admin_encheres_liste')



# =============================================================================
# HELPERS
# =============================================================================
 
def _produits_eligibles_flash(user):
    """
    Produits du vendeur éligibles à une enchère flash :
    actifs, sans enchère existante (OneToOne), autorise_enchere=True.
    """
    return Produit.objects.filter(
        vendeur=user, est_actif=True,
        autorise_enchere=True, enchere__isnull=True
    ).select_related('categorie')
 
 
def _peut_gerer_flash(user, enchere_flash):
    return user.is_staff or enchere_flash.enchere.vendeur == user
 
 
def _secondes_restantes(enchere):
    return max(0, int((enchere.date_fin - timezone.now()).total_seconds()))



# =============================================================================
# PUBLIC
# =============================================================================
 
def flash_liste(request):
    """
    Liste publique des enchères flash actives,
    triées par urgence (date_fin la plus proche d'abord).
    """
    now = timezone.now()
 
    qs = EnchereFlash.objects.filter(
        enchere__statut__in=['en_cours', 'prolongee'],
        enchere__date_fin__gt=now,
        enchere__type_enchere='flash',
    ).select_related(
        'enchere', 'enchere__produit', 'enchere__vendeur'
    ).order_by('enchere__date_fin')
 
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(enchere__titre__icontains=q)
 
    duree = request.GET.get('duree', '')
    if duree:
        try:
            qs = qs.filter(duree_minutes=int(duree))
        except (ValueError, TypeError):
            pass
 
    paginator   = Paginator(qs, 16)
    flash_list  = paginator.get_page(request.GET.get('page', 1))
 
    # Classement par urgence (< 5 min)
    ultra_urgentes = qs.filter(enchere__date_fin__lte=now + timezone.timedelta(minutes=5))
 
    return render(request, 'apps_enchere/flash/flash_liste.html', {
        'flash_list':     flash_list,
        'ultra_urgentes': ultra_urgentes,
        'q':              q,
        'duree':          duree,
        'durees':         EnchereFlash.DUREE_CHOICES,
        'nb_actives':     paginator.count,
        'page_titre':     'Enchères Flash ⚡ — YopiShop',
    })
 
 
def flash_detail(request, pk):
    """
    Page détail d'une enchère flash.
    Affiche le grand timer, les offres récentes et le formulaire d'enchère.
    """
    flash = get_object_or_404(
        EnchereFlash.objects.select_related(
            'enchere', 'enchere__produit', 'enchere__vendeur', 'enchere__gagnant'
        ),
        pk=pk
    )
    enchere = flash.enchere
 
    # Incrémenter les vues
    if not request.user.is_authenticated or request.user != enchere.vendeur:
        Enchere.objects.filter(pk=enchere.pk).update(nb_vues=enchere.nb_vues + 1)
 
    offres = enchere.offres.select_related('encherisseur').order_by(
        '-montant', '-date_creation'
    )[:20]
 
    meilleure_offre  = offres.first() if offres else None
    je_suis_meilleur = (
        request.user.is_authenticated and meilleure_offre and
        meilleure_offre.encherisseur == request.user
    )
 
    montant_min_suivant = enchere.prix_actuel + enchere.increment_minimum
    secondes_restantes  = _secondes_restantes(enchere)
    est_urgente         = secondes_restantes < 60  # < 1 min = mode urgence
 
    # Limite participants
    nb_acheteurs_uniques = enchere.offres.values('encherisseur').distinct().count()
    capacite_atteinte    = (
        flash.nb_acheteurs_max is not None and
        nb_acheteurs_uniques >= flash.nb_acheteurs_max
    )
    peut_participer = (
        request.user.is_authenticated and
        enchere.est_active() and
        enchere.vendeur != request.user and
        not capacite_atteinte
    )
 
    return render(request, 'apps_enchere/flash/flash_detail.html', {
        'flash':                flash,
        'enchere':              enchere,
        'offres':               offres,
        'meilleure_offre':      meilleure_offre,
        'je_suis_meilleur':     je_suis_meilleur,
        'montant_min_suivant':  montant_min_suivant,
        'secondes_restantes':   secondes_restantes,
        'est_urgente':          est_urgente,
        'nb_acheteurs_uniques': nb_acheteurs_uniques,
        'capacite_atteinte':    capacite_atteinte,
        'peut_participer':      peut_participer,
        'est_active':           enchere.est_active(),
        'page_titre':           f"⚡ {enchere.titre}",
    })

 
@require_GET
def ajax_etat_flash(request, pk):
    """
    Polling rapide (toutes les 2s) — prix, timer, offres récentes.
    Retourne aussi un flag `doit_recharger` si l'enchère vient de se terminer.
    """
    flash   = get_object_or_404(EnchereFlash, pk=pk)
    enchere = flash.enchere
 
    meilleure = enchere.offres.select_related('encherisseur').order_by('-montant').first()
    secondes  = _secondes_restantes(enchere)
 
    # 5 dernières offres pour le widget live
    dernières_offres = [{
        'username': o.encherisseur.username,
        'montant':  float(o.montant),
        'est_auto': o.est_offre_auto,
        'date':     o.date_creation.strftime('%H:%M:%S'),
    } for o in enchere.offres.select_related('encherisseur').order_by('-date_creation')[:5]]
 
    return JsonResponse({
        'statut':              enchere.statut,
        'prix_actuel':         float(enchere.prix_actuel),
        'nb_offres':           enchere.nb_offres,
        'secondes_restantes':  secondes,
        'date_fin':            enchere.date_fin.isoformat(),
        'est_active':          enchere.est_active(),
        'est_urgente':         secondes < 60,
        'est_critique':        secondes < 10,
        'couleur_urgence':     flash.couleur_urgence,
        'afficher_timer_geant': flash.afficher_timer_geant,
        'montant_min_suivant': float(enchere.prix_actuel + enchere.increment_minimum),
        'meilleur':            meilleure.encherisseur.username if meilleure else None,
        'doit_recharger':      enchere.statut in ('terminee', 'annulee'),
        'dernieres_offres':    dernières_offres,
    })


# =============================================================================
# VENDEUR — Création / Annulation
# =============================================================================
 
@login_required
def creer_enchere_flash(request):
    """
    Wizard de création d'une enchère flash.
    Étape unique : formulaire combiné Enchere + EnchereFlash.
 
    RÈGLE MÉTIER :
      - Le produit doit appartenir au vendeur connecté (vérification double
        GET + POST via _produits_eligibles_flash).
      - La durée détermine la date_fin automatiquement (pas de saisie manuelle).
      - L'extension automatique par offre est activée d'office sur les flash.
    """
    if not request.user.peut_vendre:
        messages.warning(request, "Vous devez être vendeur pour créer une enchère flash.")
        return redirect('apps_core:devenir_vendeur')
 
    mes_produits = _produits_eligibles_flash(request.user)
 
    if not mes_produits.exists():
        messages.info(
            request,
            "Aucun produit éligible. Activez « Autoriser les enchères » sur un produit "
            "actif sans enchère existante."
        )
        return redirect('apps_core:mes_produits')
 
    if request.method == 'POST':
        produit_id = request.POST.get('produit')
        # ── Vérification stricte : produit du vendeur uniquement ──────────
        produit = mes_produits.filter(pk=produit_id).first()
        if not produit:
            messages.error(
                request,
                "Produit invalide : vous ne pouvez créer une enchère que sur "
                "vos propres produits éligibles."
            )
            return redirect('apps_enchere:creer_enchere_flash')
 
        try:
            titre       = request.POST.get('titre', '').strip() or produit.titre
            description = request.POST.get('description', '').strip() or getattr(produit, 'description_courte', '')
            prix_depart = Decimal(request.POST.get('prix_depart', '0'))
            prix_achat_str = request.POST.get('prix_achat_immediat', '').strip()
            increment   = Decimal(request.POST.get('increment_minimum', '500'))
            duree_min   = int(request.POST.get('duree_minutes', 30))
            extension_s = int(request.POST.get('extension_par_offre_secondes', 30))
            couleur     = request.POST.get('couleur_urgence', '#FF0000').strip()
            nb_max_str  = request.POST.get('nb_acheteurs_max', '').strip()
            timer_geant = request.POST.get('afficher_timer_geant') == 'on'
 
            if prix_depart <= 0:
                raise ValueError("Le prix de départ doit être positif.")
 
            durees_valides = [d[0] for d in EnchereFlash.DUREE_CHOICES]
            if duree_min not in durees_valides:
                raise ValueError(f"Durée invalide. Choisissez parmi : {durees_valides}")
 
            prix_achat_immediat = Decimal(prix_achat_str) if prix_achat_str else None
            if prix_achat_immediat and prix_achat_immediat <= prix_depart:
                raise ValueError("Le prix d'achat immédiat doit être supérieur au prix de départ.")
 
            nb_acheteurs_max = int(nb_max_str) if nb_max_str else None
            if nb_acheteurs_max is not None and nb_acheteurs_max < 1:
                raise ValueError("Le nombre maximum d'acheteurs doit être positif.")
 
            if not (3 <= len(couleur) <= 7 and couleur.startswith('#')):
                couleur = '#FF0000'
 
        except (ValueError, InvalidOperation, TypeError) as e:
            messages.error(request, f"Erreur de saisie : {e}")
            return redirect('apps_enchere:creer_enchere_flash')
 
        with transaction.atomic():
            date_debut = timezone.now()
            date_fin   = date_debut + timezone.timedelta(minutes=duree_min)
 
            enchere = Enchere.objects.create(
                produit=produit,
                vendeur=request.user,
                type_enchere='flash',
                titre=titre,
                description=description,
                prix_depart=prix_depart,
                prix_actuel=prix_depart,
                prix_achat_immediat=prix_achat_immediat,
                date_debut=date_debut,
                date_fin=date_fin,
                increment_minimum=increment,
                # Extension auto toujours activée sur les flash
                extension_automatique=True,
                duree_extension_secondes=extension_s,
                statut='en_cours',
            )
 
            image = request.FILES.get('image_couverture')
            if image:
                enchere.image_couverture = image
                enchere.save(update_fields=['image_couverture'])
 
            flash = EnchereFlash.objects.create(
                enchere=enchere,
                duree_minutes=duree_min,
                extension_par_offre_secondes=extension_s,
                afficher_timer_geant=timer_geant,
                couleur_urgence=couleur,
                nb_acheteurs_max=nb_acheteurs_max,
            )
 
        messages.success(
            request,
            f"⚡ Enchère flash « {enchere.titre} » lancée pour {duree_min} minutes !"
        )
        return redirect('app_enchere:flash_detail', pk=flash.pk)
 
    return render(request, 'apps_enchere/flash/flash_form.html', {
        'mes_produits': mes_produits,
        'durees':       EnchereFlash.DUREE_CHOICES,
        'page_titre':   '⚡ Créer une enchère flash',
    })
 
 
@login_required
@require_POST
def annuler_flash(request, pk):
    """Annule une enchère flash (vendeur ou admin)."""
    flash   = get_object_or_404(EnchereFlash, pk=pk)
    enchere = flash.enchere
 
    if not _peut_gerer_flash(request.user, flash):
        messages.error(request, "Action non autorisée.")
        return redirect('apps_enchere:mes_encheres')
 
    if enchere.statut == 'terminee':
        messages.error(request, "Impossible d'annuler une enchère déjà terminée.")
        return redirect('apps_enchere:flash_detail', pk=pk)
 
    enchere.statut = 'annulee'
    enchere.save(update_fields=['statut'])
 
    # Notifier les participants
    try:
        from apps_core.views_notifications import creer_notification_masse
        participants = list({o.encherisseur for o in enchere.offres.all()})
        if participants:
            creer_notification_masse(
                utilisateurs_qs=participants,
                type_notification='enchere',
                titre="⚡ Enchère flash annulée",
                message=f"L'enchère flash « {enchere.titre} » a été annulée par le vendeur.",
                lien=f"/encheres/flash/{flash.pk}/",
            )
    except Exception:
        pass
 
    messages.success(request, "Enchère flash annulée.")
    return redirect('apps_enchere:mes_encheres')



# =============================================================================
# ADMIN
# =============================================================================
 
@login_required
def admin_flash_liste(request):
    """Vue admin de toutes les enchères flash de la plateforme."""
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')
 
    qs = EnchereFlash.objects.select_related(
        'enchere', 'enchere__produit', 'enchere__vendeur', 'enchere__gagnant'
    ).order_by('-enchere__date_creation')
 
    statut = request.GET.get('statut', '')
    if statut:
        qs = qs.filter(enchere__statut=statut)
 
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(
            Q(enchere__titre__icontains=q) |
            Q(enchere__vendeur__username__icontains=q)
        )
 
    now = timezone.now()
    stats = {
        'total':    EnchereFlash.objects.count(),
        'actives':  EnchereFlash.objects.filter(
                        enchere__statut__in=['en_cours', 'prolongee'],
                        enchere__date_fin__gt=now
                    ).count(),
        'urgentes': EnchereFlash.objects.filter(
                        enchere__statut__in=['en_cours', 'prolongee'],
                        enchere__date_fin__lte=now + timezone.timedelta(minutes=5),
                        enchere__date_fin__gt=now
                    ).count(),
        'terminees': EnchereFlash.objects.filter(enchere__statut='terminee').count(),
    }
 
    paginator  = Paginator(qs, 25)
    flash_list = paginator.get_page(request.GET.get('page', 1))
 
    return render(request, 'app_enchere/flash/admin_flash_liste.html', {
        'flash_list': flash_list,
        'stats':      stats,
        'statut':     statut,
        'q':          q,
        'statuts':    Enchere.STATUT_CHOICES,
        'page_titre': 'Gestion des enchères flash ⚡',
    })


# =============================================================================
# HELPERS
# =============================================================================
 
def _peut_gerer_groupe_enchere(user, config_groupe):
    return user.is_staff or config_groupe.enchere.vendeur == user
 
 
def _quantite_reservee(config_groupe):
    """Total des quantités confirmées par les participants."""
    return config_groupe.participants.filter(
        a_confirme=True
    ).aggregate(total=Sum('quantite_souhaitee'))['total'] or 0
 
 
def _places_restantes(config_groupe):
    return config_groupe.quantite_totale - _quantite_reservee(config_groupe)



# ===========================================================================
# VUE AJAX : Rejoindre / Quitter une enchère groupe
# ===========================================================================
 
@login_required
@require_POST
def ajax_rejoindre_enchere_groupe(request, pk):
    """L'utilisateur réserve une quantité dans l'enchère groupe."""
    enchere = get_object_or_404(Enchere, pk=pk, type_enchere='groupe')
    config  = getattr(enchere, 'config_groupe', None)
 
    if not config:
        return JsonResponse({'success': False, 'message': 'Configuration groupe introuvable.'}, status=400)
 
    if not enchere.est_active():
        return JsonResponse({'success': False, 'message': 'Cette enchère n\'est plus active.'}, status=400)
 
    if enchere.vendeur == request.user:
        return JsonResponse({'success': False, 'message': 'Vous ne pouvez pas participer à votre propre enchère.'}, status=400)
 
    # Vérifier si déjà participant
    if config.participants.filter(utilisateur=request.user).exists():
        return JsonResponse({'success': False, 'message': 'Vous participez déjà à cette enchère.'}, status=400)
 
    try:
        qte_souhaitee  = int(request.POST.get('quantite_souhaitee', config.quantite_min_par_participant))
        montant_offert = Decimal(request.POST.get('montant_offert', str(enchere.prix_actuel)))
 
        if qte_souhaitee < config.quantite_min_par_participant:
            raise ValueError(f"Quantité minimum : {config.quantite_min_par_participant}")
        if config.quantite_max_par_participant and qte_souhaitee > config.quantite_max_par_participant:
            raise ValueError(f"Quantité maximum : {config.quantite_max_par_participant}")
        if montant_offert < enchere.prix_actuel:
            raise ValueError(f"Montant minimum : {enchere.prix_actuel:,.0f} {enchere.devise}")
 
        # Vérifier la quantité restante
        qte_reservee = sum(
            p.quantite_souhaitee
            for p in config.participants.filter(a_confirme=True)
        )
        if qte_souhaitee > (config.quantite_totale - qte_reservee):
            raise ValueError(
                f"Quantité insuffisante. Restant : {config.quantite_totale - qte_reservee}"
            )
 
        # Vérifier la limite de participants
        nb_confirmes = config.participants.filter(a_confirme=True).count()
        if config.nb_participants_max and nb_confirmes >= config.nb_participants_max:
            raise ValueError("Le nombre maximum de participants est atteint.")
 
        participant = ParticipantEnchereGroupe.objects.create(
            enchere_groupe=config,
            utilisateur=request.user,
            quantite_souhaitee=qte_souhaitee,
            montant_offert=montant_offert,
            a_confirme=True,
        )
 
        nb_confirmes_new = config.participants.filter(a_confirme=True).count()
        progression      = min(100, round(nb_confirmes_new / config.nb_participants_min * 100))
 
        return JsonResponse({
            'success':       True,
            'message':       f"Vous participez pour {qte_souhaitee} unité(s) à {montant_offert:,.0f} {enchere.devise}.",
            'nb_participants': nb_confirmes_new,
            'progression':   progression,
        })
 
    except (ValueError, InvalidOperation, TypeError) as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)
 
 
@login_required
@require_POST
def ajax_quitter_enchere_groupe(request, pk):
    """L'utilisateur se retire de l'enchère groupe."""
    enchere = get_object_or_404(Enchere, pk=pk, type_enchere='groupe')
    config  = getattr(enchere, 'config_groupe', None)
 
    if not config:
        return JsonResponse({'success': False, 'message': 'Configuration groupe introuvable.'}, status=400)
 
    participant = config.participants.filter(utilisateur=request.user).first()
    if not participant:
        return JsonResponse({'success': False, 'message': 'Vous ne participez pas à cette enchère.'}, status=400)
 
    if participant.commande:
        return JsonResponse({'success': False, 'message': 'Impossible de se retirer : commande déjà créée.'}, status=400)
 
    participant.delete()
 
    nb_confirmes = config.participants.filter(a_confirme=True).count()
    progression  = min(100, round(nb_confirmes / config.nb_participants_min * 100))
 
    return JsonResponse({
        'success':         True,
        'message':         'Vous avez quitté cette enchère groupe.',
        'nb_participants': nb_confirmes,
        'progression':     progression,
    })


# =============================================================================
# HELPERS
# =============================================================================

def _est_ouvert(ao):
    return ao.statut == 'ouvert' and timezone.now() < ao.date_limite


def _peut_gerer_ao(user, ao):
    return user.is_staff or ao.acheteur == user


# =============================================================================
# PUBLIC
# =============================================================================
 
def appels_offre_liste(request):
    """
    Liste publique des appels d'offre ouverts.
    Filtres : categorie, b2b, q.
    """
    now = timezone.now()
    qs  = AppelOffre.objects.filter(
        statut='ouvert', date_limite__gt=now
    ).select_related('acheteur', 'categorie').annotate(
        nb_offres=Count('offres_vendeurs')
    ).order_by('date_limite')
 
    categorie_id = request.GET.get('categorie', '')
    if categorie_id:
        qs = qs.filter(categorie_id=categorie_id)
 
    b2b = request.GET.get('b2b', '')
    if b2b == '1':
        qs = qs.filter(est_b2b=True)
    elif b2b == '0':
        qs = qs.filter(est_b2b=False)
 
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(
            Q(titre__icontains=q) | Q(description__icontains=q)
        )
 
    categories   = Categorie.objects.filter(est_active=True).order_by('nom')
    paginator    = Paginator(qs, 20)
    appels_offre = paginator.get_page(request.GET.get('page', 1))
 
    return render(request, 'apps_enchere/inversee/appels_offre_liste.html', {
        'appels_offre': appels_offre,
        'categories':   categories,
        'categorie_id': categorie_id,
        'b2b':          b2b,
        'q':            q,
        'nb_resultats': paginator.count,
        'page_titre':   'Appels d\'offre — YopiShop',
    })


def appel_offre_detail(request, pk):
    """
    Page détail d'un appel d'offre.
    L'acheteur voit toutes les offres classées par prix.
    Les vendeurs ne voient que la meilleure offre (prix masqué pour les autres).
    """
    ao = get_object_or_404(
        AppelOffre.objects.select_related('acheteur', 'categorie', 'offre_gagnante'),
        pk=pk
    )
 
    est_acheteur = request.user.is_authenticated and ao.acheteur == request.user
    est_admin    = request.user.is_authenticated and request.user.is_staff
 
    # L'acheteur et l'admin voient toutes les offres classées par prix
    if est_acheteur or est_admin:
        offres = ao.offres_vendeurs.select_related('vendeur').order_by('montant')
    else:
        # Les autres vendeurs voient seulement la meilleure offre (anonymisée)
        offres = ao.offres_vendeurs.select_related('vendeur').order_by('montant')[:1]
 
    meilleure_offre = ao.offres_vendeurs.order_by('montant').first()
    mon_offre       = None
    if request.user.is_authenticated:
        mon_offre = ao.offres_vendeurs.filter(vendeur=request.user).first()
 
    peut_soumettre = (
        request.user.is_authenticated and
        request.user.peut_vendre and
        ao.acheteur != request.user and
        _est_ouvert(ao) and
        mon_offre is None
    )
 
    return render(request, 'apps_enchere/inversee/appel_offre_detail.html', {
        'ao':             ao,
        'offres':         offres,
        'meilleure_offre': meilleure_offre,
        'mon_offre':      mon_offre,
        'est_acheteur':   est_acheteur,
        'est_admin':      est_admin,
        'est_ouvert':     _est_ouvert(ao),
        'peut_soumettre': peut_soumettre,
        'nb_offres':      ao.offres_vendeurs.count(),
        'page_titre':     ao.titre,
    })


@require_GET
def ajax_etat_appel_offre(request, pk):
    """Polling — nb offres, meilleure offre, temps restant."""
    ao = get_object_or_404(AppelOffre, pk=pk)
 
    meilleure = ao.offres_vendeurs.order_by('montant').first()
    secondes  = max(0, int((ao.date_limite - timezone.now()).total_seconds()))
 
    return JsonResponse({
        'statut':           ao.statut,
        'est_ouvert':       _est_ouvert(ao),
        'nb_offres':        ao.offres_vendeurs.count(),
        'meilleure_offre':  float(meilleure.montant) if meilleure else None,
        'seconds_restants': secondes,
        'date_limite':      ao.date_limite.isoformat(),
        'doit_recharger':   ao.statut in ('adjuge', 'annule', 'ferme'),
    })


# =============================================================================
# ACHETEUR
# =============================================================================
 
@login_required
def creer_appel_offre(request):
    """L'acheteur publie un besoin avec budget max."""
    if request.method == 'POST':
        try:
            titre       = request.POST.get('titre', '').strip()
            description = request.POST.get('description', '').strip()
            categorie_id = request.POST.get('categorie')
            budget_max  = Decimal(request.POST.get('budget_max', '0'))
            quantite    = int(request.POST.get('quantite', 1))
            duree_jours = int(request.POST.get('duree_jours', 7))
            est_b2b     = request.POST.get('est_b2b') == 'on'
 
            if not titre:
                raise ValueError("Le titre est requis.")
            if budget_max <= 0:
                raise ValueError("Le budget maximum doit être positif.")
            if quantite < 1:
                raise ValueError("La quantité doit être ≥ 1.")
            if duree_jours < 1 or duree_jours > 90:
                raise ValueError("Durée invalide (1 à 90 jours).")
 
            categorie = get_object_or_404(Categorie, pk=categorie_id)
 
        except (ValueError, InvalidOperation, TypeError) as e:
            messages.error(request, f"Erreur : {e}")
            return redirect('apps_enchere:creer_appel_offre')
 
        ao = AppelOffre.objects.create(
            acheteur=request.user,
            titre=titre,
            description=description,
            categorie=categorie,
            budget_max=budget_max,
            quantite=quantite,
            date_limite=timezone.now() + timezone.timedelta(days=duree_jours),
            est_b2b=est_b2b,
        )
 
        messages.success(request, f"Appel d'offre « {ao.titre} » publié !")
        return redirect('apps_enchere:appel_offre_detail', pk=ao.pk)
 
    categories = Categorie.objects.filter(est_active=True).order_by('nom')
    return render(request, 'apps_enchere/inversee/appel_offre_form.html', {
        'categories': categories,
        'mode':       'creation',
        'page_titre': 'Publier un appel d\'offre',
    })
 


@login_required
def mes_appels_offre(request):
    """Liste des appels d'offre créés par l'utilisateur connecté."""
    qs = AppelOffre.objects.filter(
        acheteur=request.user
    ).select_related('categorie', 'offre_gagnante').annotate(
        nb_offres=Count('offres_vendeurs')
    ).order_by('-date_creation')
 
    statut = request.GET.get('statut', '')
    if statut:
        qs = qs.filter(statut=statut)
 
    stats = {
        'total':   AppelOffre.objects.filter(acheteur=request.user).count(),
        'ouverts': AppelOffre.objects.filter(acheteur=request.user, statut='ouvert').count(),
        'adjuges': AppelOffre.objects.filter(acheteur=request.user, statut='adjuge').count(),
    }
 
    paginator    = Paginator(qs, 15)
    appels_offre = paginator.get_page(request.GET.get('page', 1))
 
    return render(request, 'apps_enchere/inversee/mes_appels_offre.html', {
        'appels_offre': appels_offre,
        'stats':        stats,
        'statut':       statut,
        'statuts':      AppelOffre.STATUT_CHOICES,
        'page_titre':   'Mes appels d\'offre',
    })



@login_required
@require_POST
@transaction.atomic
def adjuger_appel_offre(request, pk):
    """
    L'acheteur sélectionne une offre gagnante et crée la commande.
    Crée automatiquement une Commande + ArticleCommande.
    """
    ao = get_object_or_404(AppelOffre, pk=pk, acheteur=request.user)
 
    if ao.statut != 'ouvert':
        messages.error(request, "Cet appel d'offre n'est plus ouvert.")
        return redirect('apps_enchere:appel_offre_detail', pk=pk)
 
    offre_id = request.POST.get('offre_id')
    offre    = get_object_or_404(OffreVendeur, pk=offre_id, appel_offre=ao)
 
    # Vérifier que l'offre respecte le budget
    if offre.montant > ao.budget_max:
        messages.error(request, f"Cette offre ({offre.montant:,.0f} FCFA) dépasse votre budget ({ao.budget_max:,.0f} FCFA).")
        return redirect('apps_enchere:appel_offre_detail', pk=pk)
 
    # Créer la commande
    from apps_marketplace.models import Commande, ArticleCommande
    adresse = getattr(request.user, 'adresse', '') or 'Adresse à compléter'
 
    commande = Commande.objects.create(
        utilisateur=request.user,
        source='b2b' if ao.est_b2b else 'web',
        adresse_facturation=adresse,
        adresse_livraison=adresse,
        sous_total=offre.montant,
        montant_total=offre.montant,
        notes=f"Appel d'offre : {ao.titre}",
    )
 
    # Clôturer l'AO
    offre.est_selectionnee = True
    offre.save(update_fields=['est_selectionnee'])
 
    ao.statut        = 'adjuge'
    ao.offre_gagnante = offre
    ao.save()
 
    # Notifier le vendeur gagnant
    try:
        from apps_core.views_notifications import creer_notification
        creer_notification(
            utilisateur=offre.vendeur,
            type_notification='commande',
            titre="🎉 Votre offre a été retenue !",
            message=f"Votre proposition de {offre.montant:,.0f} FCFA pour « {ao.titre} » a été sélectionnée.",
            lien='/commandes/',
        )
        # Notifier les autres vendeurs (refus)
        from apps_core.views_notifications import creer_notification_masse
        perdants = [o.vendeur for o in ao.offres_vendeurs.exclude(pk=offre.pk)]
        if perdants:
            creer_notification_masse(
                utilisateurs_qs=perdants,
                type_notification='enchere',
                titre="Appel d'offre clôturé",
                message=f"L'appel d'offre « {ao.titre} » a été attribué à un autre vendeur.",
                lien=f"/encheres/inversee/{ao.pk}/",
            )
    except Exception:
        pass
 
    messages.success(request, f"Offre de {offre.vendeur.username} retenue ! Commande #{commande.numero_commande} créée.")
    return redirect('apps_enchere:appel_offre_detail', pk=pk)
 

@login_required
@require_POST
def annuler_appel_offre(request, pk):
    """L'acheteur annule son appel d'offre."""
    ao = get_object_or_404(AppelOffre, pk=pk, acheteur=request.user)
 
    if ao.statut == 'adjuge':
        messages.error(request, "Impossible d'annuler un appel d'offre déjà adjugé.")
        return redirect('apps_enchere:appel_offre_detail', pk=pk)
 
    ao.statut = 'annule'
    ao.save(update_fields=['statut'])
 
    # Notifier les vendeurs ayant soumis une offre
    try:
        from apps_core.views_notifications import creer_notification_masse
        vendeurs = [o.vendeur for o in ao.offres_vendeurs.all()]
        if vendeurs:
            creer_notification_masse(
                utilisateurs_qs=vendeurs,
                type_notification='enchere',
                titre="Appel d'offre annulé",
                message=f"L'appel d'offre « {ao.titre} » a été annulé par l'acheteur.",
                lien=f"/encheres/inversee/{ao.pk}/",
            )
    except Exception:
        pass
 
    messages.success(request, "Appel d'offre annulé.")
    return redirect('apps_enchere:mes_appels_offre')



# =============================================================================
# VENDEUR
# =============================================================================
 
@login_required
@require_POST
def soumettre_offre_vendeur(request, ao_pk):
    """Le vendeur soumet son prix pour un appel d'offre."""
    ao = get_object_or_404(AppelOffre, pk=ao_pk)
 
    if not request.user.peut_vendre:
        return JsonResponse({'success': False, 'message': "Réservé aux vendeurs."}, status=403)
 
    if ao.acheteur == request.user:
        return JsonResponse({'success': False, 'message': "Vous ne pouvez pas répondre à votre propre AO."}, status=400)
 
    if not _est_ouvert(ao):
        return JsonResponse({'success': False, 'message': "Cet appel d'offre est fermé."}, status=400)
 
    if ao.offres_vendeurs.filter(vendeur=request.user).exists():
        return JsonResponse({'success': False, 'message': "Vous avez déjà soumis une offre pour cet AO."}, status=400)
 
    try:
        montant         = Decimal(request.POST.get('montant', '0'))
        description     = request.POST.get('description', '').strip()
        delai_livraison = int(request.POST.get('delai_livraison', 7))
        garantie        = request.POST.get('garantie', '').strip()
 
        if montant <= 0:
            raise ValueError("Le montant doit être positif.")
        if montant > ao.budget_max:
            raise ValueError(f"Votre offre dépasse le budget maximum ({ao.budget_max:,.0f} FCFA).")
        if not description:
            raise ValueError("La description est requise.")
        if delai_livraison < 1:
            raise ValueError("Le délai de livraison doit être ≥ 1 jour.")
 
    except (ValueError, InvalidOperation, TypeError) as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)
 
    piece = request.FILES.get('pieces_jointes')
    offre = OffreVendeur.objects.create(
        appel_offre=ao,
        vendeur=request.user,
        montant=montant,
        description=description,
        delai_livraison=delai_livraison,
        garantie=garantie,
        pieces_jointes=piece,
    )
 
    # Notifier l'acheteur
    try:
        from apps_core.views_notifications import creer_notification
        creer_notification(
            utilisateur=ao.acheteur,
            type_notification='enchere',
            titre="Nouvelle offre sur votre appel d'offre",
            message=f"{request.user.username} a proposé {montant:,.0f} FCFA pour « {ao.titre} ».",
            lien=f"/encheres/inversee/{ao.pk}/",
        )
    except Exception:
        pass
 
    return JsonResponse({
        'success':  True,
        'message':  f"Offre de {montant:,.0f} FCFA soumise avec succès.",
        'offre_id': offre.pk,
        'montant':  float(offre.montant),
        'nb_offres': ao.offres_vendeurs.count(),
    })


@login_required
@require_POST
def modifier_offre_vendeur(request, offre_pk):
    """Le vendeur modifie son offre avant clôture de l'AO."""
    offre = get_object_or_404(OffreVendeur, pk=offre_pk, vendeur=request.user)
 
    if not _est_ouvert(offre.appel_offre):
        messages.error(request, "L'appel d'offre est clôturé, modification impossible.")
        return redirect('apps_enchere:appel_offre_detail', pk=offre.appel_offre.pk)
 
    try:
        montant = Decimal(request.POST.get('montant', str(offre.montant)))
        if montant <= 0:
            raise ValueError("Montant invalide.")
        if montant > offre.appel_offre.budget_max:
            raise ValueError(f"Dépasse le budget maximum ({offre.appel_offre.budget_max:,.0f} FCFA).")
 
        offre.montant          = montant
        offre.description      = request.POST.get('description', offre.description).strip()
        offre.delai_livraison  = int(request.POST.get('delai_livraison', offre.delai_livraison))
        offre.garantie         = request.POST.get('garantie', offre.garantie).strip()
 
        piece = request.FILES.get('pieces_jointes')
        if piece:
            offre.pieces_jointes = piece
 
        offre.save()
        messages.success(request, "Offre mise à jour.")
 
    except (ValueError, InvalidOperation, TypeError) as e:
        messages.error(request, f"Erreur : {e}")
 
    return redirect('apps_enchere:appel_offre_detail', pk=offre.appel_offre.pk)
 


@login_required
@require_POST
def retirer_offre_vendeur(request, offre_pk):
    """Le vendeur retire sa proposition avant clôture."""
    offre = get_object_or_404(OffreVendeur, pk=offre_pk, vendeur=request.user)
 
    if not _est_ouvert(offre.appel_offre):
        messages.error(request, "L'appel d'offre est clôturé.")
        return redirect('apps_enchere:appel_offre_detail', pk=offre.appel_offre.pk)
 
    ao_pk = offre.appel_offre.pk
    offre.delete()
    messages.success(request, "Votre offre a été retirée.")
    return redirect('apps_enchere:appel_offre_detail', pk=ao_pk)


@login_required
def mes_offres_vendeur(request):
    """Liste de toutes les offres soumises par le vendeur."""
    if not request.user.peut_vendre:
        messages.warning(request, "Réservé aux vendeurs.")
        return redirect('apps_core:tableau_de_bord')
 
    qs = OffreVendeur.objects.filter(
        vendeur=request.user
    ).select_related('appel_offre', 'appel_offre__acheteur', 'appel_offre__categorie').order_by('-date_soumission')
 
    statut = request.GET.get('statut', '')
    if statut:
        qs = qs.filter(appel_offre__statut=statut)
 
    stats = {
        'total':       OffreVendeur.objects.filter(vendeur=request.user).count(),
        'en_attente':  OffreVendeur.objects.filter(
                           vendeur=request.user, appel_offre__statut='ouvert'
                       ).count(),
        'retenues':    OffreVendeur.objects.filter(
                           vendeur=request.user, est_selectionnee=True
                       ).count(),
    }
 
    paginator = Paginator(qs, 15)
    offres    = paginator.get_page(request.GET.get('page', 1))
 
    return render(request, 'apps_enchere/inversee/mes_offres_vendeur.html', {
        'offres':   offres,
        'stats':    stats,
        'statut':   statut,
        'statuts':  AppelOffre.STATUT_CHOICES,
        'page_titre': 'Mes offres vendeur',
    })



# =============================================================================
# ADMIN
# =============================================================================
 
@login_required
def admin_appels_offre_liste(request):
    """Vue admin de tous les appels d'offre."""
    if not request.user.is_staff:
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('apps_core:accueil')
 
    qs = AppelOffre.objects.select_related(
        'acheteur', 'categorie', 'offre_gagnante'
    ).annotate(nb_offres=Count('offres_vendeurs')).order_by('-date_creation')
 
    statut = request.GET.get('statut', '')
    if statut:
        qs = qs.filter(statut=statut)
 
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(Q(titre__icontains=q) | Q(acheteur__username__icontains=q))
 
    now = timezone.now()
    stats = {
        'total':    AppelOffre.objects.count(),
        'ouverts':  AppelOffre.objects.filter(statut='ouvert', date_limite__gt=now).count(),
        'adjuges':  AppelOffre.objects.filter(statut='adjuge').count(),
        'annules':  AppelOffre.objects.filter(statut='annule').count(),
        'expirees': AppelOffre.objects.filter(statut='ouvert', date_limite__lte=now).count(),
    }
 
    paginator    = Paginator(qs, 25)
    appels_offre = paginator.get_page(request.GET.get('page', 1))
 
    return render(request, 'apps_enchere/inversee/admin_appels_offre_liste.html', {
        'appels_offre': appels_offre,
        'stats':        stats,
        'statut':       statut,
        'q':            q,
        'statuts':      AppelOffre.STATUT_CHOICES,
        'page_titre':   'Gestion des appels d\'offre',
    })
 
 
 
 
 
 

 
 
 

 
 