# ===========================================================================
# app_enchere/admin.py
# Administration Django — App Enchère (Sections 1 à 7)
#
# MODÈLES COUVERTS :
#   Section 1 : Enchere
#   Section 2 : OffreEnchere, ConfigSmartBid
#   Section 3 : EnchereFlash
#   Section 4 : EnchereGroupe, ParticipantEnchereGroupe
#   Section 5 : AppelOffre, OffreVendeur
#   Section 6 : BattleAuction, SupportBattle
#   Section 7 : InteractionSocialeEnchere
#
# PRÉCAUTIONS MYSQL :
#   - show_full_result_count=False sur les grandes tables
#   - JSONField (specifications sur AppelOffre) exclu de list_display/search_fields
#   - raw_id_fields sur toutes les FK volumineuses
#   - list_select_related partout pour éviter les N+1
# ===========================================================================

from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from django.db.models import Sum, Count

from .models import (
    # Section 1
    Enchere,
    # Section 2
    OffreEnchere, ConfigSmartBid,
    # Section 3
    EnchereFlash,
    # Section 4
    EnchereGroupe, ParticipantEnchereGroupe,
    # Section 5
    AppelOffre, OffreVendeur,
    # Section 6
    BattleAuction, SupportBattle,
    # Section 7
    InteractionSocialeEnchere,
)


# ===========================================================================
# INLINES
# ===========================================================================

class OffreEnchereInline(admin.TabularInline):
    model   = OffreEnchere
    extra   = 0
    fields  = ('encherisseur', 'montant', 'est_offre_auto', 'est_achat_immediat', 'date_creation')
    readonly_fields = ('date_creation',)
    raw_id_fields   = ('encherisseur',)
    show_change_link = True
    ordering = ('-montant',)


class ConfigSmartBidInline(admin.TabularInline):
    model   = ConfigSmartBid
    extra   = 0
    fields  = ('utilisateur', 'prix_max', 'strategie', 'priorite', 'est_active', 'depense_jour')
    readonly_fields = ('depense_jour', 'date_activation')
    raw_id_fields   = ('utilisateur',)


class EnchereFlashInline(admin.StackedInline):
    model       = EnchereFlash
    extra       = 0
    fields      = ('duree_minutes', 'extension_par_offre_secondes',
                   'afficher_timer_geant', 'couleur_urgence', 'nb_acheteurs_max')
    can_delete  = False


class EnchereGroupeInline(admin.StackedInline):
    model       = EnchereGroupe
    extra       = 0
    fields      = ('quantite_totale', 'quantite_min_par_participant',
                   'quantite_max_par_participant', 'nb_participants_min', 'nb_participants_max')
    can_delete  = False


class ParticipantGroupeInline(admin.TabularInline):
    model   = ParticipantEnchereGroupe
    extra   = 0
    fields  = ('utilisateur', 'quantite_souhaitee', 'montant_offert', 'a_confirme', 'commande', 'date_adhesion')
    readonly_fields = ('date_adhesion',)
    raw_id_fields   = ('utilisateur', 'commande')


class OffreVendeurInline(admin.TabularInline):
    model   = OffreVendeur
    extra   = 0
    fields  = ('vendeur', 'montant', 'delai_livraison', 'garantie', 'est_selectionnee', 'date_soumission')
    readonly_fields = ('date_soumission',)
    raw_id_fields   = ('vendeur',)
    ordering = ('montant',)


class SupportBattleInline(admin.TabularInline):
    model   = SupportBattle
    extra   = 0
    fields  = ('utilisateur', 'camp', 'date_choix')
    readonly_fields = ('date_choix',)
    raw_id_fields   = ('utilisateur',)


class InteractionSocialeInline(admin.TabularInline):
    model   = InteractionSocialeEnchere
    extra   = 0
    fields  = ('utilisateur', 'type_interaction', 'contenu', 'plateforme_partage', 'date_creation')
    readonly_fields = ('date_creation',)
    raw_id_fields   = ('utilisateur',)
    ordering = ('-date_creation',)


# ===========================================================================
# SECTION 1 — ENCHÈRE PRINCIPALE
# ===========================================================================

@admin.register(Enchere)
class EnchereAdmin(admin.ModelAdmin):
    list_display = (
        'titre_display', 'vendeur', 'type_badge', 'statut_badge',
        'prix_actuel_display', 'nb_offres', 'nb_vues',
        'date_debut', 'date_fin_display',
    )
    list_display_links = ('titre_display',)
    list_filter = (
        'statut', 'type_enchere', 'devise',
        ('date_creation', admin.DateFieldListFilter),
    )
    search_fields = ('titre', 'vendeur__username', 'produit__titre')
    raw_id_fields = ('produit', 'vendeur', 'gagnant')
    list_select_related = ('produit', 'vendeur', 'gagnant')
    readonly_fields = ('id', 'nb_offres', 'nb_vues', 'nb_likes', 'nb_partages', 'date_creation')
    date_hierarchy = 'date_creation'
    list_per_page = 30
    show_full_result_count = False

    fieldsets = (
        ("Identité", {
            'fields': ('id', 'produit', 'vendeur', 'type_enchere', 'titre', 'description', 'image_couverture')
        }),
        ("Prix", {
            'fields': ('prix_depart', 'prix_reserve', 'prix_actuel', 'prix_achat_immediat',
                       'increment_minimum', 'devise')
        }),
        ("Planning", {
            'fields': ('date_debut', 'date_fin', 'statut', 'extension_automatique', 'duree_extension_secondes')
        }),
        ("Gagnant", {
            'fields': ('gagnant',),
        }),
        ("Stats (lecture seule)", {
            'fields': ('nb_offres', 'nb_vues', 'nb_likes', 'nb_partages'),
        }),
        ("Gamification", {
            'fields': ('points_participation',),
            'classes': ('collapse',),
        }),
    )

    inlines = [
        EnchereFlashInline,
        EnchereGroupeInline,
        OffreEnchereInline,
        ConfigSmartBidInline,
        InteractionSocialeInline,
    ]

    actions = ['terminer_encheres', 'annuler_encheres']

    def titre_display(self, obj):
        return format_html('<strong>{}</strong>', obj.titre[:45])
    titre_display.short_description = "Titre"
    titre_display.admin_order_field = 'titre'

    def type_badge(self, obj):
        couleurs = {
            'classique': ('#7C6FFF', '#1a1050'),
            'flash':     ('#FF4F5E', '#2a0a0e'),
            'groupe':    ('#00C896', '#0a2a22'),
            'inversee':  ('#F5A623', '#2a1a00'),
            'battle':    ('#FF4F5E', '#2a0a0e'),
        }
        bg, color = couleurs.get(obj.type_enchere, ('#6B7399', '#111535'))
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;border-radius:99px;font-size:11px;font-weight:700">{}</span>',
            bg, color, obj.get_type_enchere_display()
        )
    type_badge.short_description = "Type"
    type_badge.admin_order_field = 'type_enchere'

    def statut_badge(self, obj):
        c = {
            'en_cours': '#FF4F5E', 'prolongee': '#7C6FFF',
            'terminee': '#00C896', 'annulee':   '#6B7399',
            'a_venir':  '#F5A623',
        }.get(obj.statut, '#999')
        return format_html(
            '<span style="color:{};font-weight:700">● {}</span>', c, obj.get_statut_display()
        )
    statut_badge.short_description = "Statut"
    statut_badge.admin_order_field = 'statut'

    def prix_actuel_display(self, obj):
        return format_html('<strong style="color:#F5A623">{:,.0f} {}</strong>', obj.prix_actuel, obj.devise)
    prix_actuel_display.short_description = "Prix actuel"
    prix_actuel_display.admin_order_field = 'prix_actuel'

    def date_fin_display(self, obj):
        now = timezone.now()
        if obj.date_fin < now and obj.statut in ('en_cours', 'prolongee'):
            return format_html('<span style="color:#FF4F5E">{} ⚠️</span>', obj.date_fin.strftime('%d/%m %H:%M'))
        return obj.date_fin.strftime('%d/%m/%Y %H:%M')
    date_fin_display.short_description = "Fin"
    date_fin_display.admin_order_field = 'date_fin'

    @admin.action(description="✅ Terminer les enchères sélectionnées")
    def terminer_encheres(self, request, queryset):
        n = 0
        for enc in queryset.filter(statut__in=['en_cours', 'prolongee']):
            enc.terminer()
            n += 1
        self.message_user(request, f"{n} enchère(s) terminée(s).")

    @admin.action(description="❌ Annuler les enchères sélectionnées")
    def annuler_encheres(self, request, queryset):
        n = queryset.filter(statut__in=['en_cours', 'prolongee', 'a_venir']).update(statut='annulee')
        self.message_user(request, f"{n} enchère(s) annulée(s).")


# ===========================================================================
# SECTION 2 — OFFRES ET SMART BID
# ===========================================================================

@admin.register(OffreEnchere)
class OffreEnchereAdmin(admin.ModelAdmin):
    list_display = (
        'enchere', 'encherisseur', 'montant_display',
        'est_offre_auto', 'est_achat_immediat', 'date_creation',
    )
    list_filter  = ('est_offre_auto', 'est_achat_immediat', ('date_creation', admin.DateFieldListFilter))
    search_fields = ('enchere__titre', 'encherisseur__username')
    raw_id_fields = ('enchere', 'encherisseur')
    list_select_related = ('enchere', 'encherisseur')
    readonly_fields = ('date_creation',)
    date_hierarchy = 'date_creation'
    list_per_page = 50
    show_full_result_count = False

    def montant_display(self, obj):
        return format_html('<strong style="color:#F5A623">{:,.0f} {}</strong>', obj.montant, obj.enchere.devise)
    montant_display.short_description = "Montant"
    montant_display.admin_order_field = 'montant'


@admin.register(ConfigSmartBid)
class ConfigSmartBidAdmin(admin.ModelAdmin):
    list_display = (
        'utilisateur', 'enchere', 'prix_max_display',
        'strategie', 'priorite', 'est_active_badge', 'depense_jour', 'date_activation','est_active',
    )
    list_filter  = ('est_active', 'strategie')
    search_fields = ('utilisateur__username', 'enchere__titre')
    raw_id_fields = ('utilisateur', 'enchere')
    list_select_related = ('utilisateur', 'enchere')
    readonly_fields = ('date_activation', 'depense_jour')
    list_editable = ('est_active',)
    list_per_page = 40
    show_full_result_count = False

    def prix_max_display(self, obj):
        return format_html('{:,.0f} FCFA', obj.prix_max)
    prix_max_display.short_description = "Budget max"
    prix_max_display.admin_order_field = 'prix_max'

    def est_active_badge(self, obj):
        c = '#00C896' if obj.est_active else '#6B7399'
        return format_html('<span style="color:{}">●</span> {}', c, "Actif" if obj.est_active else "Inactif")
    est_active_badge.short_description = "Statut"
    est_active_badge.admin_order_field = 'est_active'


# ===========================================================================
# SECTION 3 — ENCHÈRE FLASH
# ===========================================================================

@admin.register(EnchereFlash)
class EnchereFlashAdmin(admin.ModelAdmin):
    list_display = (
        'enchere', 'duree_minutes', 'extension_par_offre_secondes',
        'afficher_timer_geant', 'couleur_urgence_display', 'nb_acheteurs_max',
        'statut_enchere',
    )
    list_filter  = ('duree_minutes', 'afficher_timer_geant')
    search_fields = ('enchere__titre', 'enchere__vendeur__username')
    raw_id_fields = ('enchere',)
    list_select_related = ('enchere', 'enchere__vendeur')
    list_per_page = 30
    show_full_result_count = False

    def couleur_urgence_display(self, obj):
        return format_html(
            '<span style="background:{};display:inline-block;width:18px;height:18px;border-radius:4px;vertical-align:middle"></span> {}',
            obj.couleur_urgence, obj.couleur_urgence
        )
    couleur_urgence_display.short_description = "Couleur urgence"

    def statut_enchere(self, obj):
        c = {'en_cours': '#FF4F5E', 'terminee': '#00C896'}.get(obj.enchere.statut, '#6B7399')
        return format_html('<span style="color:{};font-weight:700">●</span> {}', c, obj.enchere.get_statut_display())
    statut_enchere.short_description = "Statut"


# ===========================================================================
# SECTION 4 — ENCHÈRE GROUPE
# ===========================================================================

@admin.register(EnchereGroupe)
class EnchereGroupeAdmin(admin.ModelAdmin):
    list_display = (
        'enchere', 'quantite_totale', 'quantite_min_par_participant',
        'nb_participants_min', 'nb_participants_max',
        'nb_participants_confirmes', 'quantite_reservee_display',
    )
    search_fields = ('enchere__titre',)
    raw_id_fields = ('enchere',)
    list_select_related = ('enchere',)
    list_per_page = 30
    inlines = [ParticipantGroupeInline]

    def nb_participants_confirmes(self, obj):
        return obj.participants.filter(a_confirme=True).count()
    nb_participants_confirmes.short_description = "Participants confirmés"

    def quantite_reservee_display(self, obj):
        reservee = obj.participants.filter(a_confirme=True).aggregate(
            s=Sum('quantite_souhaitee')
        )['s'] or 0
        restante = max(0, obj.quantite_totale - reservee)
        c = '#00C896' if restante == 0 else '#F5A623'
        return format_html(
            '<span style="color:{}">{}/{} — {} restante{}</span>',
            c, reservee, obj.quantite_totale, restante, 's' if restante > 1 else ''
        )
    quantite_reservee_display.short_description = "Progression"


@admin.register(ParticipantEnchereGroupe)
class ParticipantEnchereGroupeAdmin(admin.ModelAdmin):
    list_display = ('enchere_groupe', 'utilisateur', 'quantite_souhaitee', 'montant_display', 'a_confirme', 'commande', 'date_adhesion')
    list_filter  = ('a_confirme',)
    search_fields = ('utilisateur__username', 'enchere_groupe__enchere__titre')
    raw_id_fields = ('enchere_groupe', 'utilisateur', 'commande')
    list_select_related = ('enchere_groupe', 'utilisateur')
    readonly_fields = ('date_adhesion',)
    list_per_page = 40
    show_full_result_count = False

    def montant_display(self, obj):
        return format_html('{:,.0f} FCFA', obj.montant_offert)
    montant_display.short_description = "Montant offert"
    montant_display.admin_order_field = 'montant_offert'


# ===========================================================================
# SECTION 5 — ENCHÈRE INVERSÉE (APPEL D'OFFRE)
# ===========================================================================

@admin.register(AppelOffre)
class AppelOffreAdmin(admin.ModelAdmin):
    """
    ⚠️ MySQL : specifications (JSONField) volontairement absent de
    list_display et search_fields.
    """
    list_display = (
        'titre', 'acheteur', 'categorie', 'budget_max_display',
        'quantite', 'est_b2b', 'statut_badge',
        'nb_offres_recues', 'offre_min_display', 'date_limite',
    )
    list_filter  = ('statut', 'est_b2b', 'categorie', ('date_creation', admin.DateFieldListFilter))
    search_fields = ('titre', 'acheteur__username', 'description')
    raw_id_fields = ('acheteur', 'categorie', 'offre_gagnante')
    list_select_related = ('acheteur', 'categorie', 'offre_gagnante')
    readonly_fields = ('id', 'date_creation')
    date_hierarchy = 'date_creation'
    list_per_page = 30
    show_full_result_count = False

    inlines = [OffreVendeurInline]
    actions = ['fermer_appels_offre', 'annuler_appels_offre']

    def budget_max_display(self, obj):
        return format_html('<strong style="color:#F5A623">{:,.0f} FCFA</strong>', obj.budget_max)
    budget_max_display.short_description = "Budget max"
    budget_max_display.admin_order_field = 'budget_max'

    def statut_badge(self, obj):
        c = {
            'ouvert': '#00C896', 'ferme': '#6B7399',
            'adjuge': '#F5A623', 'annule': '#FF4F5E',
        }.get(obj.statut, '#999')
        return format_html('<span style="color:{};font-weight:700">● {}</span>', c, obj.get_statut_display())
    statut_badge.short_description = "Statut"
    statut_badge.admin_order_field = 'statut'

    def nb_offres_recues(self, obj):
        return obj.offres_vendeurs.count()
    nb_offres_recues.short_description = "Offres reçues"

    def offre_min_display(self, obj):
        meilleure = obj.offres_vendeurs.order_by('montant').first()
        if meilleure:
            return format_html('<span style="color:#00C896">{:,.0f} FCFA</span>', meilleure.montant)
        return "—"
    offre_min_display.short_description = "Meilleure offre"

    @admin.action(description="🔒 Fermer les appels d'offre sélectionnés")
    def fermer_appels_offre(self, request, queryset):
        n = queryset.filter(statut='ouvert').update(statut='ferme')
        self.message_user(request, f"{n} appel(s) d'offre fermé(s).")

    @admin.action(description="❌ Annuler les appels d'offre sélectionnés")
    def annuler_appels_offre(self, request, queryset):
        n = queryset.filter(statut__in=['ouvert', 'ferme']).update(statut='annule')
        self.message_user(request, f"{n} appel(s) d'offre annulé(s).")


@admin.register(OffreVendeur)
class OffreVendeurAdmin(admin.ModelAdmin):
    list_display = (
        'appel_offre', 'vendeur', 'montant_display',
        'delai_livraison', 'garantie', 'est_selectionnee', 'date_soumission',
    )
    list_filter  = ('est_selectionnee', ('date_soumission', admin.DateFieldListFilter))
    search_fields = ('vendeur__username', 'appel_offre__titre', 'description')
    raw_id_fields = ('appel_offre', 'vendeur')
    list_select_related = ('appel_offre', 'vendeur')
    readonly_fields = ('date_soumission',)
    list_per_page = 40
    show_full_result_count = False

    def montant_display(self, obj):
        if obj.est_selectionnee:
            return format_html('<strong style="color:#00C896">{:,.0f} FCFA 🏆</strong>', obj.montant)
        return format_html('{:,.0f} FCFA', obj.montant)
    montant_display.short_description = "Montant"
    montant_display.admin_order_field = 'montant'


# ===========================================================================
# SECTION 6 — BATTLE AUCTION
# ===========================================================================

@admin.register(BattleAuction)
class BattleAuctionAdmin(admin.ModelAdmin):
    list_display = (
        'titre', 'nom_camp_a', 'nom_camp_b',
        'statut_badge', 'score_display',
        'prix_a_display', 'prix_b_display',
        'date_fin',
    )
    list_filter  = ('statut', ('date_creation', admin.DateFieldListFilter))
    search_fields = ('titre', 'nom_camp_a', 'nom_camp_b')
    raw_id_fields = ('enchere_a', 'enchere_b')
    list_select_related = ('enchere_a', 'enchere_b', 'enchere_a__produit', 'enchere_b__produit')
    readonly_fields = ('id', 'nb_supporters_a', 'nb_supporters_b', 'date_creation')
    list_per_page = 25
    show_full_result_count = False
    inlines = [SupportBattleInline]
    actions = ['terminer_battles']

    fieldsets = (
        ("Battle", {'fields': ('id', 'titre', 'description', 'statut')}),
        ("Camp A", {'fields': ('enchere_a', 'nom_camp_a', 'couleur_camp_a')}),
        ("Camp B", {'fields': ('enchere_b', 'nom_camp_b', 'couleur_camp_b')}),
        ("Planning", {'fields': ('date_debut', 'date_fin')}),
        ("Supporters", {'fields': ('nb_supporters_a', 'nb_supporters_b'), 'classes': ('collapse',)}),
    )

    def statut_badge(self, obj):
        c = {'en_cours': '#FF4F5E', 'a_venir': '#F5A623', 'termine': '#00C896'}.get(obj.statut, '#999')
        return format_html('<span style="color:{};font-weight:700">● {}</span>', c, obj.get_statut_display())
    statut_badge.short_description = "Statut"
    statut_badge.admin_order_field = 'statut'

    def score_display(self, obj):
        total = obj.nb_supporters_a + obj.nb_supporters_b
        pct_a = round(obj.nb_supporters_a / total * 100) if total else 50
        return format_html(
            '<span style="color:{}">{}</span> {} vs {} <span style="color:{}">{}</span>',
            obj.couleur_camp_a, f"{pct_a}%",
            obj.nb_supporters_a, obj.nb_supporters_b,
            obj.couleur_camp_b, f"{100-pct_a}%",
        )
    score_display.short_description = "Score supporters"

    def prix_a_display(self, obj):
        return format_html('<span style="color:{}">{:,.0f} F</span>', obj.couleur_camp_a, obj.enchere_a.prix_actuel)
    prix_a_display.short_description = "Prix Camp A"

    def prix_b_display(self, obj):
        return format_html('<span style="color:{}">{:,.0f} F</span>', obj.couleur_camp_b, obj.enchere_b.prix_actuel)
    prix_b_display.short_description = "Prix Camp B"

    @admin.action(description="🏁 Terminer les battles sélectionnées")
    def terminer_battles(self, request, queryset):
        n = 0
        for battle in queryset.filter(statut='en_cours'):
            battle.statut   = 'termine'
            battle.date_fin = timezone.now()
            battle.save()
            for enc in [battle.enchere_a, battle.enchere_b]:
                if enc.statut in ('en_cours', 'prolongee'):
                    enc.terminer()
            n += 1
        self.message_user(request, f"{n} battle(s) terminée(s).")


@admin.register(SupportBattle)
class SupportBattleAdmin(admin.ModelAdmin):
    list_display = ('battle', 'utilisateur', 'camp_display', 'date_choix')
    list_filter  = ('camp',)
    search_fields = ('utilisateur__username', 'battle__titre')
    raw_id_fields = ('battle', 'utilisateur')
    list_select_related = ('battle', 'utilisateur')
    readonly_fields = ('date_choix',)
    list_per_page = 50
    show_full_result_count = False

    def camp_display(self, obj):
        if obj.camp == 'a':
            return format_html(
                '<span style="background:{};color:#fff;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:700">Camp A — {}</span>',
                obj.battle.couleur_camp_a, obj.battle.nom_camp_a
            )
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:700">Camp B — {}</span>',
            obj.battle.couleur_camp_b, obj.battle.nom_camp_b
        )
    camp_display.short_description = "Camp"
    camp_display.admin_order_field = 'camp'


# ===========================================================================
# SECTION 7 — INTERACTIONS SOCIALES
# ===========================================================================

@admin.register(InteractionSocialeEnchere)
class InteractionSocialeEnchereAdmin(admin.ModelAdmin):
    list_display = (
        'utilisateur', 'enchere', 'type_badge',
        'contenu_apercu', 'plateforme_partage', 'date_creation',
    )
    list_filter  = ('type_interaction', ('date_creation', admin.DateFieldListFilter))
    search_fields = ('utilisateur__username', 'enchere__titre', 'contenu')
    raw_id_fields = ('enchere', 'utilisateur')
    list_select_related = ('enchere', 'utilisateur')
    readonly_fields = ('date_creation',)
    date_hierarchy = 'date_creation'
    list_per_page = 50
    show_full_result_count = False
    actions = ['supprimer_commentaires_abusifs']

    def type_badge(self, obj):
        c = {
            'like':         ('#FF4F5E', '❤️'),
            'partage':      ('#7C6FFF', '🔗'),
            'commentaire':  ('#00C896', '💬'),
        }.get(obj.type_interaction, ('#999', '•'))
        couleur, emoji = c
        return format_html(
            '<span style="color:{};font-weight:700">{} {}</span>',
            couleur, emoji, obj.get_type_interaction_display()
        )
    type_badge.short_description = "Type"
    type_badge.admin_order_field = 'type_interaction'

    def contenu_apercu(self, obj):
        if obj.contenu:
            return obj.contenu[:60] + ('…' if len(obj.contenu) > 60 else '')
        return "—"
    contenu_apercu.short_description = "Contenu"

    @admin.action(description="🗑️ Supprimer les commentaires sélectionnés (modération)")
    def supprimer_commentaires_abusifs(self, request, queryset):
        n = queryset.filter(type_interaction='commentaire').count()
        queryset.filter(type_interaction='commentaire').delete()
        self.message_user(request, f"{n} commentaire(s) supprimé(s).")