# ===========================================================================
# apps_social/admin.py
# ===========================================================================

from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import (
    ProfilSocial, AbonnementSocial,
    Story, VueStory,
    VideoCommerce, ProduitVideo, CommentaireVideo,
    ProgrammeInfluenceur, ConversionInfluenceur,
    Publication, MediaPublication, LikePublication, CommentairePublication,
)


# ═══════════════════════════════════════════════════════════
# INLINES
# ═══════════════════════════════════════════════════════════

class VueStoryInline(admin.TabularInline):
    model           = VueStory
    extra           = 0
    readonly_fields = ('utilisateur', 'date_vue')
    fields          = ('utilisateur', 'date_vue')
    max_num         = 50

    def has_add_permission(self, request, obj=None):
        return False


class ProduitVideoInline(admin.TabularInline):
    model  = ProduitVideo
    extra  = 0
    fields = ('produit', 'timestamp_apparition', 'position_x', 'position_y', 'texte_bouton')


class CommentaireVideoInline(admin.TabularInline):
    model           = CommentaireVideo
    extra           = 0
    readonly_fields = ('auteur', 'date_creation', 'nb_likes')
    fields          = ('auteur', 'contenu', 'parent', 'nb_likes', 'date_creation')
    ordering        = ('-date_creation',)
    max_num         = 20

    def has_add_permission(self, request, obj=None):
        return False


class ConversionInfluenceurInline(admin.TabularInline):
    model           = ConversionInfluenceur
    extra           = 0
    readonly_fields = ('utilisateur_converti', 'commande', 'montant_commande',
                       'commission_gagnee', 'est_payee', 'date_conversion')
    fields          = ('utilisateur_converti', 'commande', 'montant_commande',
                       'commission_gagnee', 'est_payee', 'date_conversion')
    ordering        = ('-date_conversion',)
    max_num         = 30

    def has_add_permission(self, request, obj=None):
        return False


class LikePublicationInline(admin.TabularInline):
    model           = LikePublication
    extra           = 0
    readonly_fields = ('utilisateur', 'date_like')
    fields          = ('utilisateur', 'date_like')
    max_num         = 30

    def has_add_permission(self, request, obj=None):
        return False


class CommentairePublicationInline(admin.TabularInline):
    model           = CommentairePublication
    extra           = 0
    readonly_fields = ('auteur', 'date_creation', 'nb_likes')
    fields          = ('auteur', 'contenu', 'parent', 'nb_likes', 'date_creation')
    ordering        = ('date_creation',)
    max_num         = 30

    def has_add_permission(self, request, obj=None):
        return False


class MediaPublicationInline(admin.TabularInline):
    model  = MediaPublication
    extra  = 1
    fields = ('type_media', 'fichier', 'ordre')


# ═══════════════════════════════════════════════════════════
# PROFIL SOCIAL
# ═══════════════════════════════════════════════════════════

@admin.register(ProfilSocial)
class ProfilSocialAdmin(admin.ModelAdmin):
    list_display  = (
        'utilisateur_link', 'nb_abonnes_fmt', 'nb_abonnements',
        'nb_publications', 'verifie_badge', 'est_public',
    )
    list_filter   = ('est_verifie', 'est_public')
    search_fields = ('utilisateur__username', 'utilisateur__email', 'biographie')
    readonly_fields = ('nb_abonnes', 'nb_abonnements', 'nb_publications')
    ordering      = ('-nb_abonnes',)
    list_per_page = 40
    actions       = ['certifier_comptes', 'retirer_certification']

    fieldsets = (
        ('👤 Utilisateur', {
            'fields': ('utilisateur',),
        }),
        ('📝 Profil', {
            'fields': ('biographie', 'lien_bio', 'est_public'),
        }),
        ('✅ Certification', {
            'fields': ('est_verifie',),
        }),
        ('📊 Statistiques', {
            'fields': ('nb_abonnes', 'nb_abonnements', 'nb_publications'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Utilisateur', ordering='utilisateur__username')
    def utilisateur_link(self, obj):
        url = f'/admin/apps_core/utilisateur/{obj.utilisateur.pk}/change/'
        return format_html('<a href="{}">@{}</a>', url, obj.utilisateur.username)

    @admin.display(description='Abonnés', ordering='nb_abonnes')
    def nb_abonnes_fmt(self, obj):
        n = obj.nb_abonnes
        if n >= 1_000_000:
            txt = f'{n/1_000_000:.1f}M'
        elif n >= 1_000:
            txt = f'{n/1_000:.1f}K'
        else:
            txt = str(n)
        color = '#10B981' if n >= 10_000 else '#F59E0B' if n >= 1_000 else '#64748B'
        return format_html('<strong style="color:{}">{}</strong>', color, txt)

    @admin.display(description='✓ Vérifié', boolean=True)
    def verifie_badge(self, obj):
        return obj.est_verifie

    @admin.action(description='✅ Certifier les comptes sélectionnés')
    def certifier_comptes(self, request, queryset):
        updated = queryset.update(est_verifie=True)
        self.message_user(request, f'{updated} compte(s) certifié(s).')

    @admin.action(description='❌ Retirer la certification')
    def retirer_certification(self, request, queryset):
        updated = queryset.update(est_verifie=False)
        self.message_user(request, f'{updated} certification(s) retirée(s).')


# ═══════════════════════════════════════════════════════════
# ABONNEMENT SOCIAL
# ═══════════════════════════════════════════════════════════

@admin.register(AbonnementSocial)
class AbonnementSocialAdmin(admin.ModelAdmin):
    list_display  = ('abonne_link', 'suivi_link', 'date_abonnement')
    search_fields = ('abonne__username', 'suivi__username')
    readonly_fields = ('date_abonnement',)
    ordering      = ('-date_abonnement',)
    date_hierarchy = 'date_abonnement'
    list_per_page = 100

    @admin.display(description='Abonné', ordering='abonne__username')
    def abonne_link(self, obj):
        url = f'/admin/apps_core/utilisateur/{obj.abonne.pk}/change/'
        return format_html('<a href="{}">@{}</a>', url, obj.abonne.username)

    @admin.display(description='Suit', ordering='suivi__username')
    def suivi_link(self, obj):
        url = f'/admin/apps_core/utilisateur/{obj.suivi.pk}/change/'
        return format_html('<a href="{}">@{}</a>', url, obj.suivi.username)


# ═══════════════════════════════════════════════════════════
# STORY
# ═══════════════════════════════════════════════════════════

@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
    list_display  = (
        'auteur_link', 'type_story', 'statut_badge',
        'nb_vues', 'nb_clics', 'produit_lie',
        'date_creation', 'date_expiration',
    )
    list_filter   = ('type_story',)
    search_fields = ('auteur__username', 'texte')
    readonly_fields = ('id', 'date_creation', 'nb_vues', 'nb_clics')
    ordering      = ('-date_creation',)
    date_hierarchy = 'date_creation'
    list_per_page = 50
    inlines       = [VueStoryInline]
    actions       = ['expirer_stories']

    fieldsets = (
        ('🔑 Identification', {
            'fields': ('id', 'auteur', 'type_story'),
        }),
        ('🎨 Contenu', {
            'fields': ('media', 'miniature', 'texte', 'couleur_fond'),
        }),
        ('🛒 Commerce', {
            'fields': ('produit_lie', 'bouton_action', 'lien_action'),
            'classes': ('collapse',),
        }),
        ('📅 Durée de vie', {
            'fields': ('date_creation', 'date_expiration'),
        }),
        ('📊 Statistiques', {
            'fields': ('nb_vues', 'nb_clics'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Auteur', ordering='auteur__username')
    def auteur_link(self, obj):
        url = f'/admin/apps_core/utilisateur/{obj.auteur.pk}/change/'
        return format_html('<a href="{}">@{}</a>', url, obj.auteur.username)

    @admin.display(description='Statut')
    def statut_badge(self, obj):
        if obj.est_active():
            return format_html(
                '<span style="background:#10B981;color:#fff;padding:.18rem .55rem;border-radius:99px;font-size:.72rem;font-weight:700">'
                '● Active</span>'
            )
        return format_html(
            '<span style="background:#64748B;color:#fff;padding:.18rem .55rem;border-radius:99px;font-size:.72rem;font-weight:700">'
            'Expirée</span>'
        )

    @admin.action(description='⏰ Expirer immédiatement les stories sélectionnées')
    def expirer_stories(self, request, queryset):
        updated = queryset.update(date_expiration=timezone.now())
        self.message_user(request, f'{updated} story(ies) expirée(s).')


@admin.register(VueStory)
class VueStoryAdmin(admin.ModelAdmin):
    list_display  = ('story_link', 'utilisateur_link', 'date_vue')
    search_fields = ('story__auteur__username', 'utilisateur__username')
    readonly_fields = ('date_vue',)
    ordering      = ('-date_vue',)
    list_per_page = 100

    @admin.display(description='Story')
    def story_link(self, obj):
        return f"Story de @{obj.story.auteur.username}"

    @admin.display(description='Utilisateur')
    def utilisateur_link(self, obj):
        url = f'/admin/apps_core/utilisateur/{obj.utilisateur.pk}/change/'
        return format_html('<a href="{}">@{}</a>', url, obj.utilisateur.username)


# ═══════════════════════════════════════════════════════════
# VIDEO COMMERCE
# ═══════════════════════════════════════════════════════════

@admin.register(VideoCommerce)
class VideoCommerceAdmin(admin.ModelAdmin):
    list_display  = (
        'titre_court', 'auteur_link',
        'nb_vues_fmt', 'nb_likes', 'nb_commentaires',
        'nb_achats', 'ca_fmt',
        'est_publie', 'est_mis_en_avant', 'date_creation',
    )
    list_filter   = ('est_publie', 'est_mis_en_avant')
    search_fields = ('titre', 'auteur__username', 'hashtags', 'description')
    readonly_fields = (
        'id', 'date_creation',
        'nb_vues', 'nb_likes', 'nb_partages', 'nb_commentaires',
        'nb_achats', 'chiffre_affaires',
    )
    ordering      = ('-date_creation',)
    date_hierarchy = 'date_creation'
    list_per_page = 30
    save_on_top   = True
    inlines       = [ProduitVideoInline, CommentaireVideoInline]
    actions       = ['mettre_en_avant', 'retirer_mise_en_avant', 'depublier']

    fieldsets = (
        ('🔑 Identification', {
            'fields': ('id', 'auteur', 'titre', 'description'),
        }),
        ('🎬 Médias', {
            'fields': ('video', 'miniature', 'duree_secondes'),
        }),
        ('#️⃣ Hashtags', {
            'fields': ('hashtags',),
            'classes': ('collapse',),
        }),
        ('⚙️ Publication', {
            'fields': ('est_publie', 'est_mis_en_avant'),
        }),
        ('📊 Statistiques', {
            'fields': (
                'nb_vues', 'nb_likes', 'nb_partages',
                'nb_commentaires', 'nb_achats', 'chiffre_affaires',
                'date_creation',
            ),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Titre', ordering='titre')
    def titre_court(self, obj):
        titre = obj.titre[:45] + '…' if len(obj.titre) > 45 else obj.titre
        return format_html('📹 {}', titre)

    @admin.display(description='Auteur', ordering='auteur__username')
    def auteur_link(self, obj):
        url = f'/admin/apps_core/utilisateur/{obj.auteur.pk}/change/'
        return format_html('<a href="{}">@{}</a>', url, obj.auteur.username)

    @admin.display(description='Vues', ordering='nb_vues')
    def nb_vues_fmt(self, obj):
        n = obj.nb_vues
        txt = f'{n/1_000_000:.1f}M' if n >= 1_000_000 else f'{n/1_000:.1f}K' if n >= 1_000 else str(n)
        color = '#10B981' if n >= 10_000 else '#F59E0B' if n >= 1_000 else '#64748B'
        return format_html('<strong style="color:{}">{}</strong>', color, txt)

    @admin.display(description='CA généré', ordering='chiffre_affaires')
    def ca_fmt(self, obj):
        if obj.chiffre_affaires > 0:
            return format_html(
                '<strong style="color:#10B981">{:,.0f} F</strong>',
                obj.chiffre_affaires,
            )
        return '—'

    @admin.action(description='⭐ Mettre en avant les vidéos sélectionnées')
    def mettre_en_avant(self, request, queryset):
        updated = queryset.update(est_mis_en_avant=True)
        self.message_user(request, f'{updated} vidéo(s) mise(s) en avant.')

    @admin.action(description='✖️ Retirer la mise en avant')
    def retirer_mise_en_avant(self, request, queryset):
        updated = queryset.update(est_mis_en_avant=False)
        self.message_user(request, f'{updated} vidéo(s) retirée(s) de la mise en avant.')

    @admin.action(description='🚫 Dépublier les vidéos sélectionnées')
    def depublier(self, request, queryset):
        updated = queryset.update(est_publie=False)
        self.message_user(request, f'{updated} vidéo(s) dépubliée(s).')


@admin.register(ProduitVideo)
class ProduitVideoAdmin(admin.ModelAdmin):
    list_display  = ('video_link', 'produit_link', 'timestamp_apparition', 'texte_bouton')
    search_fields = ('video__titre', 'produit__titre')
    ordering      = ('video', 'timestamp_apparition')
    list_per_page = 50

    @admin.display(description='Vidéo')
    def video_link(self, obj):
        return obj.video.titre[:35]

    @admin.display(description='Produit')
    def produit_link(self, obj):
        return obj.produit.titre[:35]


@admin.register(CommentaireVideo)
class CommentaireVideoAdmin(admin.ModelAdmin):
    list_display  = (
        'auteur_link', 'video_link', 'apercu_contenu',
        'nb_likes', 'est_reponse', 'date_creation',
    )
    search_fields = ('auteur__username', 'video__titre', 'contenu')
    readonly_fields = ('date_creation', 'nb_likes')
    ordering      = ('-date_creation',)
    date_hierarchy = 'date_creation'
    list_per_page = 50
    actions       = ['supprimer_commentaires']

    @admin.display(description='Auteur')
    def auteur_link(self, obj):
        url = f'/admin/apps_core/utilisateur/{obj.auteur.pk}/change/'
        return format_html('<a href="{}">@{}</a>', url, obj.auteur.username)

    @admin.display(description='Vidéo')
    def video_link(self, obj):
        return obj.video.titre[:35]

    @admin.display(description='Commentaire')
    def apercu_contenu(self, obj):
        txt = obj.contenu[:60] + '…' if len(obj.contenu) > 60 else obj.contenu
        return format_html('<span title="{}">{}</span>', obj.contenu, txt)

    @admin.display(description='Réponse', boolean=True)
    def est_reponse(self, obj):
        return obj.parent is not None

    @admin.action(description='🗑️ Supprimer les commentaires sélectionnés')
    def supprimer_commentaires(self, request, queryset):
        count = queryset.count()
        queryset.delete()
        self.message_user(request, f'{count} commentaire(s) supprimé(s).')


# ═══════════════════════════════════════════════════════════
# PROGRAMME INFLUENCEUR
# ═══════════════════════════════════════════════════════════

@admin.register(ProgrammeInfluenceur)
class ProgrammeInfluenceurAdmin(admin.ModelAdmin):
    list_display  = (
        'influenceur_link', 'niveau_badge', 'statut_badge',
        'taux_commission', 'code_parrainage',
        'nb_conversions', 'ca_genere_fmt',
        'commissions_en_attente_fmt', 'date_adhesion',
    )
    list_filter   = ('statut', 'niveau')
    search_fields = ('influenceur__username', 'code_parrainage')
    readonly_fields = (
        'date_adhesion', 'nb_clics', 'nb_conversions',
        'chiffre_affaires_genere', 'commissions_gagnees', 'commissions_payees',
    )
    ordering      = ('-date_adhesion',)
    date_hierarchy = 'date_adhesion'
    list_per_page = 30
    save_on_top   = True
    inlines       = [ConversionInfluenceurInline]
    actions       = ['valider_candidatures', 'suspendre_influenceurs', 'reactiver_influenceurs']

    fieldsets = (
        ('👤 Influenceur', {
            'fields': ('influenceur', 'niveau', 'statut'),
        }),
        ('💰 Commission', {
            'fields': ('taux_commission', 'code_parrainage', 'lien_affiliation'),
        }),
        ('📅 Dates', {
            'fields': ('date_adhesion', 'date_validation'),
        }),
        ('📊 Statistiques', {
            'fields': (
                'nb_clics', 'nb_conversions',
                'chiffre_affaires_genere',
                'commissions_gagnees', 'commissions_payees',
            ),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Influenceur', ordering='influenceur__username')
    def influenceur_link(self, obj):
        url = f'/admin/apps_core/utilisateur/{obj.influenceur.pk}/change/'
        return format_html('<a href="{}">@{}</a>', url, obj.influenceur.username)

    @admin.display(description='Niveau')
    def niveau_badge(self, obj):
        colors = {
            'nano':  ('#64748B', '#fff'),
            'micro': ('#6366F1', '#fff'),
            'macro': ('#F59E0B', '#0A0B1A'),
            'mega':  ('#10B981', '#fff'),
        }
        bg, fg = colors.get(obj.niveau, ('#64748B', '#fff'))
        return format_html(
            '<span style="background:{};color:{};padding:.18rem .55rem;border-radius:99px;font-size:.72rem;font-weight:700">{}</span>',
            bg, fg, obj.get_niveau_display(),
        )

    @admin.display(description='Statut')
    def statut_badge(self, obj):
        colors = {
            'candidature': ('#F59E0B', '#0A0B1A'),
            'actif':       ('#10B981', '#fff'),
            'suspendu':    ('#EF4444', '#fff'),
            'termine':     ('#64748B', '#fff'),
        }
        bg, fg = colors.get(obj.statut, ('#64748B', '#fff'))
        return format_html(
            '<span style="background:{};color:{};padding:.18rem .55rem;border-radius:99px;font-size:.72rem;font-weight:700">{}</span>',
            bg, fg, obj.get_statut_display(),
        )

    @admin.display(description='CA généré', ordering='chiffre_affaires_genere')
    def ca_genere_fmt(self, obj):
        return format_html(
            '<strong style="color:#10B981">{:,.0f} F</strong>',
            obj.chiffre_affaires_genere,
        )

    @admin.display(description='Commissions en attente')
    def commissions_en_attente_fmt(self, obj):
        montant = obj.commissions_en_attente()
        color = '#EF4444' if montant > 0 else '#64748B'
        return format_html(
            '<strong style="color:{}">{:,.0f} F</strong>',
            color, montant,
        )

    @admin.action(description='✅ Valider les candidatures sélectionnées')
    def valider_candidatures(self, request, queryset):
        updated = queryset.filter(statut='candidature').update(
            statut='actif', date_validation=timezone.now()
        )
        self.message_user(request, f'{updated} candidature(s) validée(s).')

    @admin.action(description='⏸️ Suspendre les influenceurs sélectionnés')
    def suspendre_influenceurs(self, request, queryset):
        updated = queryset.filter(statut='actif').update(statut='suspendu')
        self.message_user(request, f'{updated} influenceur(s) suspendu(s).')

    @admin.action(description='▶️ Réactiver les influenceurs sélectionnés')
    def reactiver_influenceurs(self, request, queryset):
        updated = queryset.filter(statut='suspendu').update(statut='actif')
        self.message_user(request, f'{updated} influenceur(s) réactivé(s).')


@admin.register(ConversionInfluenceur)
class ConversionInfluenceurAdmin(admin.ModelAdmin):
    list_display  = (
        'influenceur_link', 'utilisateur_converti_link',
        'commande_link', 'montant_commande_fmt',
        'commission_fmt', 'est_payee', 'date_conversion',
    )
    list_filter   = ('est_payee',)
    search_fields = (
        'influenceur__influenceur__username',
        'utilisateur_converti__username',
        'commande__numero_commande',
    )
    readonly_fields = ('date_conversion',)
    ordering      = ('-date_conversion',)
    date_hierarchy = 'date_conversion'
    list_per_page = 50
    actions       = ['marquer_payees']

    @admin.display(description='Influenceur')
    def influenceur_link(self, obj):
        url = f'/admin/apps_core/utilisateur/{obj.influenceur.influenceur.pk}/change/'
        return format_html('<a href="{}">@{}</a>', url, obj.influenceur.influenceur.username)

    @admin.display(description='Client converti')
    def utilisateur_converti_link(self, obj):
        url = f'/admin/apps_core/utilisateur/{obj.utilisateur_converti.pk}/change/'
        return format_html('<a href="{}">@{}</a>', url, obj.utilisateur_converti.username)

    @admin.display(description='Commande')
    def commande_link(self, obj):
        return format_html(
            '<code style="color:#6366F1">{}</code>',
            obj.commande.numero_commande,
        )

    @admin.display(description='Montant commande', ordering='montant_commande')
    def montant_commande_fmt(self, obj):
        return format_html('{:,.0f} F', obj.montant_commande)

    @admin.display(description='Commission', ordering='commission_gagnee')
    def commission_fmt(self, obj):
        color = '#10B981' if obj.est_payee else '#F59E0B'
        return format_html(
            '<strong style="color:{}">{:,.0f} F</strong>',
            color, obj.commission_gagnee,
        )

    @admin.action(description='✅ Marquer comme payées')
    def marquer_payees(self, request, queryset):
        updated = queryset.filter(est_payee=False).update(est_payee=True)
        self.message_user(request, f'{updated} commission(s) marquée(s) comme payée(s).')


# ═══════════════════════════════════════════════════════════
# PUBLICATION / FEED
# ═══════════════════════════════════════════════════════════

@admin.register(MediaPublication)
class MediaPublicationAdmin(admin.ModelAdmin):
    list_display  = ('type_media', 'fichier', 'ordre')
    list_filter   = ('type_media',)
    ordering      = ('ordre',)


@admin.register(Publication)
class PublicationAdmin(admin.ModelAdmin):
    list_display  = (
        'apercu_contenu', 'auteur_link', 'type_publication',
        'nb_vues_fmt', 'nb_likes', 'nb_commentaires', 'nb_partages',
        'est_publie', 'date_creation',
    )
    list_filter   = ('type_publication', 'est_publie')
    search_fields = ('auteur__username', 'contenu')
    readonly_fields = (
        'id', 'date_creation',
        'nb_likes', 'nb_commentaires', 'nb_partages', 'nb_vues',
    )
    ordering      = ('-date_creation',)
    date_hierarchy = 'date_creation'
    list_per_page = 40
    save_on_top   = True
    filter_horizontal = ('medias', 'produits_tagués')
    inlines       = [LikePublicationInline, CommentairePublicationInline]
    actions       = ['depublier_publications', 'republier_publications']

    fieldsets = (
        ('🔑 Identification', {
            'fields': ('id', 'auteur', 'type_publication'),
        }),
        ('📝 Contenu', {
            'fields': ('contenu', 'medias', 'produits_tagués'),
        }),
        ('⚙️ Publication', {
            'fields': ('est_publie',),
        }),
        ('📊 Statistiques', {
            'fields': ('nb_vues', 'nb_likes', 'nb_commentaires', 'nb_partages', 'date_creation'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Contenu')
    def apercu_contenu(self, obj):
        icons = {
            'produit':  '🛒',
            'avis':     '⭐',
            'unboxing': '📦',
            'tutoriel': '📚',
            'promo':    '🏷️',
            'general':  '💬',
        }
        icon = icons.get(obj.type_publication, '💬')
        txt  = obj.contenu[:55] + '…' if len(obj.contenu) > 55 else obj.contenu
        return format_html('{} <span title="{}">{}</span>', icon, obj.contenu, txt)

    @admin.display(description='Auteur', ordering='auteur__username')
    def auteur_link(self, obj):
        url = f'/admin/apps_core/utilisateur/{obj.auteur.pk}/change/'
        return format_html('<a href="{}">@{}</a>', url, obj.auteur.username)

    @admin.display(description='Vues', ordering='nb_vues')
    def nb_vues_fmt(self, obj):
        n   = obj.nb_vues
        txt = f'{n/1_000:.1f}K' if n >= 1_000 else str(n)
        return format_html('<span style="color:#64748B">{}</span>', txt)

    @admin.action(description='🚫 Dépublier les publications sélectionnées')
    def depublier_publications(self, request, queryset):
        updated = queryset.update(est_publie=False)
        self.message_user(request, f'{updated} publication(s) dépubliée(s).')

    @admin.action(description='✅ Republier les publications sélectionnées')
    def republier_publications(self, request, queryset):
        updated = queryset.update(est_publie=True)
        self.message_user(request, f'{updated} publication(s) republiée(s).')


@admin.register(LikePublication)
class LikePublicationAdmin(admin.ModelAdmin):
    list_display  = ('utilisateur_link', 'publication_apercu', 'date_like')
    search_fields = ('utilisateur__username', 'publication__contenu')
    readonly_fields = ('date_like',)
    ordering      = ('-date_like',)
    list_per_page = 100

    @admin.display(description='Utilisateur')
    def utilisateur_link(self, obj):
        url = f'/admin/apps_core/utilisateur/{obj.utilisateur.pk}/change/'
        return format_html('<a href="{}">@{}</a>', url, obj.utilisateur.username)

    @admin.display(description='Publication')
    def publication_apercu(self, obj):
        return obj.publication.contenu[:40]


@admin.register(CommentairePublication)
class CommentairePublicationAdmin(admin.ModelAdmin):
    list_display  = (
        'auteur_link', 'publication_apercu',
        'apercu_contenu', 'nb_likes',
        'est_reponse', 'date_creation',
    )
    search_fields = ('auteur__username', 'publication__contenu', 'contenu')
    readonly_fields = ('date_creation', 'nb_likes')
    ordering      = ('-date_creation',)
    date_hierarchy = 'date_creation'
    list_per_page = 50
    actions       = ['supprimer_commentaires']

    @admin.display(description='Auteur', ordering='auteur__username')
    def auteur_link(self, obj):
        url = f'/admin/apps_core/utilisateur/{obj.auteur.pk}/change/'
        return format_html('<a href="{}">@{}</a>', url, obj.auteur.username)

    @admin.display(description='Publication')
    def publication_apercu(self, obj):
        return obj.publication.contenu[:35]

    @admin.display(description='Commentaire')
    def apercu_contenu(self, obj):
        txt = obj.contenu[:60] + '…' if len(obj.contenu) > 60 else obj.contenu
        return format_html('<span title="{}">{}</span>', obj.contenu, txt)

    @admin.display(description='Réponse', boolean=True)
    def est_reponse(self, obj):
        return obj.parent is not None

    @admin.action(description='🗑️ Supprimer les commentaires sélectionnés')
    def supprimer_commentaires(self, request, queryset):
        count = queryset.count()
        queryset.delete()
        self.message_user(request, f'{count} commentaire(s) supprimé(s).')