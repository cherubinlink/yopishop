
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
from django.db.models import Q, Max, Sum
from django.db import transaction
from django.utils import timezone
from decimal import Decimal, InvalidOperation
 
from .models import (
    Enchere, OffreEnchere, ConfigSmartBid, EnchereFlash
)
from apps_core.models import Produit


 
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



def enchere_detail(request, pk):
    enchere = get_object_or_404(
        Enchere.objects.select_related('produit', 'vendeur', 'gagnant'),
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
    if request.user.is_authenticated:
        ma_derniere_offre = enchere.offres.filter(
            encherisseur=request.user
        ).order_by('-montant').first()

    # Smart Bid actif de l'utilisateur sur cette enchère
    smart_bid_actif = None
    user_a_like     = False
    if request.user.is_authenticated:
        smart_bid_actif = _get_smart_bid(request.user, enchere)
        user_a_like     = request.session.get(f'enchere_like_{pk}', False)

    offre_minimum = enchere.prix_actuel + enchere.increment_minimum

    context = {
        'enchere':           enchere,
        'offres_recentes':   offres_recentes,      # ← renommé
        'meilleure_offre':   meilleure_offre,
        'je_suis_meilleur':  je_suis_meilleur,
        'ma_derniere_offre': ma_derniere_offre,
        'offre_minimum':     offre_minimum,        # ← ajouté
        'est_active':        enchere.est_active(),
        'smart_bid_actif':   smart_bid_actif,      # ← ajouté
        'user_a_like':       user_a_like,          # ← ajouté
        'page_titre':        enchere.titre,
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
    if not request.user.peut_vendre:
        messages.warning(request, "Vous devez être vendeur pour créer une enchère.")
        return redirect('apps_core:devenir_vendeur')

    mes_produits = _produits_eligibles_enchere(request.user)

    if not mes_produits.exists():
        messages.info(request, "Aucun produit éligible.")
        return redirect('apps_core:mes_produits')

    if request.method == 'POST':
        produit_id = request.POST.get('produit')
        produit    = mes_produits.filter(pk=produit_id).first()
        if not produit:
            messages.error(request, "Produit invalide.")
            return redirect('apps_enchere:creer_enchere')

        try:
            type_enchere  = request.POST.get('type_enchere', 'classique')
            titre         = request.POST.get('titre', '').strip() or produit.titre
            description   = request.POST.get('description', '').strip() or produit.description_courte
            prix_depart   = Decimal(request.POST.get('prix_depart', '0'))
            prix_reserve  = request.POST.get('prix_reserve', '').strip()
            prix_achat    = request.POST.get('prix_achat_immediat', '').strip()
            increment     = Decimal(request.POST.get('increment_minimum', '500'))
            extension_auto = request.POST.get('extension_automatique') == 'on'

            # ── Flash ou durée classique ──────────────────────────────────
            est_flash    = request.POST.get('est_flash') == '1'
            duree_minutes = int(request.POST.get('duree_minutes', 30)) if est_flash else None
            duree_heures  = int(request.POST.get('duree_heures', 24))           if not est_flash else None

            if prix_depart <= 0:
                raise ValueError("Le prix de départ doit être positif.")

            if est_flash:
                durees_valides = [c[0] for c in EnchereFlash.DUREE_CHOICES]
                if duree_minutes not in durees_valides:
                    raise ValueError("Durée flash invalide.")
            else:
                if duree_heures < 1 or duree_heures > 720:
                    raise ValueError("Durée invalide (1h–30 jours).")

            prix_reserve_dec    = Decimal(prix_reserve) if prix_reserve else None
            prix_achat_immediat = Decimal(prix_achat)   if prix_achat   else None

            if prix_achat_immediat and prix_achat_immediat <= prix_depart:
                raise ValueError("Le prix d'achat immédiat doit être > prix de départ.")

        except (ValueError, InvalidOperation, TypeError) as e:
            messages.error(request, f"Erreur de saisie : {e}")
            return redirect('apps_enchere:creer_enchere')

        date_debut = timezone.now()
        if est_flash:
            date_fin = date_debut + timezone.timedelta(minutes=duree_minutes)
        else:
            date_fin = date_debut + timezone.timedelta(hours=duree_heures)

        with transaction.atomic():
            enchere = Enchere.objects.create(
                produit=produit,
                vendeur=request.user,
                type_enchere=type_enchere,
                titre=titre,
                description=description,
                prix_depart=prix_depart,
                prix_reserve=prix_reserve_dec,
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

            # ── Créer la config Flash si besoin ───────────────────────────
            if est_flash:
                EnchereFlash.objects.create(
                    enchere=enchere,
                    duree_minutes=duree_minutes,
                    extension_par_offre_secondes=int(
                        request.POST.get('extension_par_offre_secondes', 30)
                    ),
                    afficher_timer_geant=request.POST.get('afficher_timer_geant') == 'on',
                    couleur_urgence=request.POST.get('couleur_urgence', '#FF0000'),
                    nb_acheteurs_max=(
                        int(request.POST.get('nb_acheteurs_max'))
                        if request.POST.get('nb_acheteurs_max', '').strip()
                        else None
                    ),
                )

        messages.success(request, f"Enchère « {enchere.titre} » créée et lancée !")
        return redirect('apps_enchere:enchere_detail', pk=enchere.pk)

    return render(request, 'apps_enchere/enchere_form.html', {
        'mes_produits':    mes_produits,
        'types':           Enchere.TYPE_CHOICES,
        'durees_flash':    EnchereFlash.DUREE_CHOICES,
        # Durées des enchères classiques (en heures)
        'durees_classiques': [
            (1, '1 heure'),
            (2, '2 heures'),
            (3, '3 heures'),
            (4, '4 heures'),
            (5, '5 heures'),
            (6, '6 heures'),
            (7, '7 heures'),
            (8, '8 heures'),
            (9, '9 heures'),
            (10, '10 heures'),
            (11, '11 heures'),
            (12, '12 heures'),
            (24, '1 jour'),
            (48, '2 jours'),
            (72, '3 jours'),
            (168, '7 jours'),
            (336, '14 jours'),
            (720, '30 jours'),
        ],
        'mode':            'creation',
        'page_titre':      'Créer une enchère',
    })

 
 
@login_required
def modifier_enchere(request, pk):
    enchere = get_object_or_404(Enchere, pk=pk)

    if not _peut_gerer_enchere(request.user, enchere):
        messages.error(request, "Vous ne pouvez modifier que vos propres enchères.")
        return redirect('apps_enchere:mes_encheres')

    if enchere.nb_offres > 0:
        messages.warning(request, "Impossible de modifier une enchère avec des offres.")
        return redirect('apps_enchere:enchere_detail', pk=pk)

    # Config Flash existante
    config_flash = getattr(enchere, 'config_flash', None)

    if request.method == 'POST':
        try:
            enchere.titre       = request.POST.get('titre', enchere.titre).strip()
            enchere.description = request.POST.get('description', enchere.description).strip()

            increment_str = request.POST.get('increment_minimum', '')
            if increment_str:
                enchere.increment_minimum = Decimal(increment_str)

            prix_achat_str = request.POST.get('prix_achat_immediat', '').strip()
            enchere.prix_achat_immediat = Decimal(prix_achat_str) if prix_achat_str else None

            enchere.extension_automatique = request.POST.get('extension_automatique') == 'on'

            # Durée — flash ou classique
            if config_flash:
                duree_minutes = int(request.POST.get('duree_flash', config_flash.duree_minutes))
                durees_valides = [c[0] for c in EnchereFlash.DUREE_CHOICES]
                if duree_minutes not in durees_valides:
                    raise ValueError("Durée flash invalide.")
                enchere.date_fin = timezone.now() + timezone.timedelta(minutes=duree_minutes)

                # Mettre à jour la config flash
                config_flash.duree_minutes             = duree_minutes
                config_flash.extension_par_offre_secondes = int(
                    request.POST.get('extension_par_offre_secondes', config_flash.extension_par_offre_secondes)
                )
                config_flash.afficher_timer_geant = request.POST.get('afficher_timer_geant') == 'on'
                config_flash.couleur_urgence      = request.POST.get('couleur_urgence', config_flash.couleur_urgence)
                nb_max = request.POST.get('nb_acheteurs_max', '').strip()
                config_flash.nb_acheteurs_max     = int(nb_max) if nb_max else None
                config_flash.save()
            else:
                duree_heures = request.POST.get('duree_heures', '')
                if duree_heures:
                    enchere.date_fin = timezone.now() + timezone.timedelta(hours=int(duree_heures))

            enchere.save()
            messages.success(request, "Enchère mise à jour.")
            return redirect('apps_enchere:enchere_detail', pk=pk)

        except (ValueError, InvalidOperation, TypeError) as e:
            messages.error(request, f"Erreur : {e}")

    return render(request, 'apps_enchere/enchere_form.html', {
        'enchere':      enchere,
        'config_flash': config_flash,
        'durees_flash': EnchereFlash.DUREE_CHOICES,
        # Durées des enchères classiques (en heures)
        'durees_classiques': [
            (1, '1 heure'),
            (2, '2 heures'),
            (3, '3 heures'),
            (4, '4 heures'),
            (5, '5 heures'),
            (6, '6 heures'),
            (7, '7 heures'),
            (8, '8 heures'),
            (9, '9 heures'),
            (10, '10 heures'),
            (11, '11 heures'),
            (12, '12 heures'),
            (24, '1 jour'),
            (48, '2 jours'),
            (72, '3 jours'),
            (168, '7 jours'),
            (336, '14 jours'),
            (720, '30 jours'),
        ],
        'mode':         'edition',
        'page_titre':   f"Modifier — {enchere.titre}",
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
 
 
 

 
 