# ===========================================================================
# app_marketplace/admin.py
# Administration Django — App Marketplace
#
# COMPATIBILITÉ MYSQL :
#   - show_full_result_count=False sur toutes les grandes tables
#   - JSONField (permissions, flags_fraude, reponse_passerelle) RETIRÉ de
#     list_display / search_fields → erreurs MySQL < 8.0.17 sur JSON
#   - raw_id_fields sur toutes les FK vers Utilisateur/Produit/Commande
#     (évite le SELECT * coûteux au chargement du formulaire)
#   - list_select_related partout pour éviter les requêtes N+1
#   - autocomplete_fields uniquement vers des modèles ayant search_fields
# ===========================================================================

from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from django.db.models import Sum, Count, Avg, Q
from django.contrib import messages
from django.urls import reverse

from apps_marketplace.models import (
    Boutique, DocumentKYC, EmployeBoutique, DemandeVendeur, AvisVendeur,
    Panier, ArticlePanier, Commande, ArticleCommande,
    CodePromo,
    Operateur, NumeroVersement, PlanPaiement, TranchePaiement, Paiement,
    MethodeLivraison, Livraison, HistoriqueLivraison,
    Retour,
    GroupeAchat, ParticipantGroupeAchat,
)


# ===========================================================================
# INLINES
# ===========================================================================

class DocumentKYCInline(admin.TabularInline):
    model   = DocumentKYC
    extra   = 0
    fields  = ('type_document', 'apercu_fichier', 'statut', 'date_envoi')
    readonly_fields = ('apercu_fichier', 'date_envoi')

    def apercu_fichier(self, obj):
        if obj.fichier:
            return format_html('<a href="{}" target="_blank">📄 Voir le fichier</a>', obj.fichier.url)
        return "—"
    apercu_fichier.short_description = "Fichier"


class EmployeBoutiqueInline(admin.TabularInline):
    model   = EmployeBoutique
    extra   = 0
    fields  = ('utilisateur', 'role', 'est_actif')
    raw_id_fields = ('utilisateur',)


class ArticlePanierInline(admin.TabularInline):
    model   = ArticlePanier
    extra   = 0
    fields  = ('produit', 'variante', 'quantite', 'prix', 'prix_type')
    raw_id_fields = ('produit', 'variante')


class ArticleCommandeInline(admin.TabularInline):
    model   = ArticleCommande
    extra   = 0
    fields  = ('produit', 'quantite', 'prix_unitaire', 'prix_total',
               'taux_commission_applique', 'commission_boutique', 'boutique')
    readonly_fields = ('prix_total', 'taux_commission_applique', 'commission_boutique')
    raw_id_fields   = ('produit', 'variante', 'enchere', 'boutique')


class PaiementInline(admin.TabularInline):
    model   = Paiement
    extra   = 0
    fields  = ('methode', 'montant', 'statut', 'date_creation')
    readonly_fields = ('date_creation',)
    show_change_link = True


class TranchePaiementInline(admin.TabularInline):
    model   = TranchePaiement
    extra   = 0
    fields  = ('numero_tranche', 'montant', 'date_echeance', 'statut', 'date_paiement')


class HistoriqueLivraisonInline(admin.TabularInline):
    model   = HistoriqueLivraison
    extra   = 0
    fields  = ('statut', 'description', 'localisation', 'date_evenement')
    readonly_fields = ('date_evenement',)


class ParticipantGroupeAchatInline(admin.TabularInline):
    model   = ParticipantGroupeAchat
    extra   = 0
    fields  = ('utilisateur', 'quantite', 'a_confirme', 'date_adhesion')
    readonly_fields = ('date_adhesion',)
    raw_id_fields   = ('utilisateur', 'commande')


# ===========================================================================
# SECTION 1 — BOUTIQUES
# ===========================================================================

@admin.register(Boutique)
class BoutiqueAdmin(admin.ModelAdmin):
    list_display = (
        'nom', 'vendeur_display', 'type_boutique_badge', 'statut_badge',
        'plan', 'kyc_badge', 'note_moyenne_display',
        'nombre_ventes', 'taux_commission', 'est_verifiee', 'est_vedette',
        'date_creation',
    )
    list_display_links = ('nom',)
    list_filter = (
        'statut', 'type_boutique', 'plan', 'kyc_statut',
        'est_verifiee', 'est_vedette', 'est_auto_creee',
        ('date_creation', admin.DateFieldListFilter),
    )
    search_fields = ('nom', 'slug', 'sous_domaine', 'email', 'vendeur__username', 'vendeur__email')
    raw_id_fields = ('vendeur', 'kyc_valide_par')
    list_select_related = ('vendeur',)
    list_per_page = 30
    show_full_result_count = False
    date_hierarchy = 'date_creation'

    readonly_fields = (
        'id', 'note_moyenne', 'nombre_avis', 'nombre_ventes', 'chiffre_affaires',
        'date_creation', 'date_modification', 'url_apercu',
    )

    fieldsets = (
        ("Identité", {
            'fields': ('id', 'vendeur', 'type_boutique', 'est_auto_creee',
                       'nom', 'slug', 'sous_domaine', 'description', 'url_apercu')
        }),
        ("Visuels", {
            'fields': ('logo', 'banniere', 'couleur_primaire', 'couleur_secondaire'),
            'classes': ('collapse',),
        }),
        ("Contact", {
            'fields': ('email', 'telephone', 'adresse', 'ville', 'pays'),
        }),
        ("Réseaux sociaux", {
            'fields': ('site_web', 'facebook', 'instagram', 'tiktok', 'whatsapp'),
            'classes': ('collapse',),
        }),
        ("Paramètres commerciaux", {
            'fields': ('delai_traitement', 'taux_commission', 'politique_retour', 'conditions_vente'),
        }),
        ("Plan & Abonnement", {
            'fields': ('plan', 'date_fin_plan'),
        }),
        ("KYC", {
            'fields': ('numero_registre_commerce', 'numero_tva', 'kyc_statut',
                       'kyc_valide_par', 'kyc_date'),
        }),
        ("Statut & Visibilité", {
            'fields': ('statut', 'est_verifiee', 'est_vedette', 'utilise_fulfillment'),
        }),
        ("Statistiques (lecture seule)", {
            'fields': ('note_moyenne', 'nombre_avis', 'nombre_ventes', 'chiffre_affaires'),
        }),
        ("Métadonnées", {
            'fields': ('date_creation', 'date_modification'),
            'classes': ('collapse',),
        }),
    )

    inlines = [DocumentKYCInline, EmployeBoutiqueInline]
    actions = ['activer_boutiques', 'suspendre_boutiques', 'marquer_vedette', 'marquer_verifiee']

    def vendeur_display(self, obj):
        return format_html('<span title="{}">{}</span>', obj.vendeur.email, obj.vendeur.username)
    vendeur_display.short_description = "Vendeur"
    vendeur_display.admin_order_field = 'vendeur__username'

    def type_boutique_badge(self, obj):
        c = {'individuelle': '#6B7399', 'pro': '#7C6FFF', 'yopishop': '#00C896'}.get(obj.type_boutique, '#999')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px">{}</span>',
            c, obj.get_type_boutique_display()
        )
    type_boutique_badge.short_description = "Type"
    type_boutique_badge.admin_order_field = 'type_boutique'

    def statut_badge(self, obj):
        c = {'active': '#00C896', 'en_attente': '#F5A623', 'suspendue': '#FF4F5E', 'fermee': '#6B7399'}.get(obj.statut, '#999')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px">{}</span>',
            c, obj.get_statut_display()
        )
    statut_badge.short_description = "Statut"
    statut_badge.admin_order_field = 'statut'

    def kyc_badge(self, obj):
        c = {'valide': '#00C896', 'en_attente': '#F5A623', 'refuse': '#FF4F5E', 'non_soumis': '#6B7399'}.get(obj.kyc_statut, '#999')
        return format_html('<span style="color:{};font-weight:700">●</span> {}', c, obj.get_kyc_statut_display())
    kyc_badge.short_description = "KYC"
    kyc_badge.admin_order_field = 'kyc_statut'

    def note_moyenne_display(self, obj):
        return format_html('⭐ {} ({})', obj.note_moyenne, obj.nombre_avis)
    note_moyenne_display.short_description = "Note"
    note_moyenne_display.admin_order_field = 'note_moyenne'

    def url_apercu(self, obj):
        if obj.pk:
            return format_html('<a href="{}" target="_blank">{}</a>', obj.url_mini_site(), obj.url_mini_site())
        return "—"
    url_apercu.short_description = "URL mini-site"

    @admin.action(description="✅ Activer les boutiques sélectionnées")
    def activer_boutiques(self, request, queryset):
        n = queryset.update(statut='active')
        self.message_user(request, f"{n} boutique(s) activée(s).", messages.SUCCESS)

    @admin.action(description="⛔ Suspendre les boutiques sélectionnées")
    def suspendre_boutiques(self, request, queryset):
        n = queryset.update(statut='suspendue')
        self.message_user(request, f"{n} boutique(s) suspendue(s).", messages.WARNING)

    @admin.action(description="⭐ Marquer en vedette")
    def marquer_vedette(self, request, queryset):
        n = queryset.update(est_vedette=True)
        self.message_user(request, f"{n} boutique(s) mise(s) en vedette.", messages.SUCCESS)

    @admin.action(description="✅ Marquer comme vérifiée")
    def marquer_verifiee(self, request, queryset):
        n = queryset.update(est_verifiee=True)
        self.message_user(request, f"{n} boutique(s) vérifiée(s).", messages.SUCCESS)


@admin.register(DocumentKYC)
class DocumentKYCAdmin(admin.ModelAdmin):
    list_display = ('boutique', 'type_document', 'lien_fichier', 'statut_badge', 'date_envoi', 'date_verification')
    list_filter  = ('statut', 'type_document', ('date_envoi', admin.DateFieldListFilter))
    search_fields = ('boutique__nom', 'description')
    raw_id_fields = ('boutique',)
    list_select_related = ('boutique',)
    readonly_fields = ('date_envoi',)
    list_per_page = 40
    show_full_result_count = False
    actions = ['valider_documents', 'refuser_documents']

    def lien_fichier(self, obj):
        if obj.fichier:
            return format_html('<a href="{}" target="_blank">📄 Voir</a>', obj.fichier.url)
        return "—"
    lien_fichier.short_description = "Fichier"

    def statut_badge(self, obj):
        c = {'valide': '#00C896', 'en_attente': '#F5A623', 'refuse': '#FF4F5E'}.get(obj.statut, '#999')
        return format_html('<span style="background:{};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px">{}</span>', c, obj.get_statut_display())
    statut_badge.short_description = "Statut"
    statut_badge.admin_order_field = 'statut'

    @admin.action(description="✅ Valider les documents sélectionnés")
    def valider_documents(self, request, queryset):
        n = queryset.update(statut='valide', date_verification=timezone.now())
        self.message_user(request, f"{n} document(s) validé(s).", messages.SUCCESS)

    @admin.action(description="❌ Refuser les documents sélectionnés")
    def refuser_documents(self, request, queryset):
        n = queryset.update(statut='refuse', date_verification=timezone.now())
        self.message_user(request, f"{n} document(s) refusé(s).", messages.WARNING)


@admin.register(EmployeBoutique)
class EmployeBoutiqueAdmin(admin.ModelAdmin):
    # ⚠️ MySQL : champ `permissions` (JSONField) volontairement absent
    # de list_display/search_fields.
    list_display  = ('utilisateur', 'boutique', 'role', 'est_actif', 'date_embauche')
    list_filter   = ('role', 'est_actif')
    search_fields = ('utilisateur__username', 'boutique__nom')
    raw_id_fields = ('utilisateur', 'boutique')
    list_select_related = ('utilisateur', 'boutique')
    readonly_fields = ('date_embauche',)
    list_per_page = 40
    show_full_result_count = False


@admin.register(DemandeVendeur)
class DemandeVendeurAdmin(admin.ModelAdmin):
    list_display = ('utilisateur', 'statut_badge', 'volume_estime', 'a_entreprise', 'date_demande', 'traite_par')
    list_filter  = ('statut', 'volume_estime', 'a_entreprise')
    search_fields = ('utilisateur__username', 'utilisateur__email', 'nom_entreprise')
    raw_id_fields = ('utilisateur', 'traite_par')
    list_select_related = ('utilisateur', 'traite_par')
    readonly_fields = ('date_demande',)
    date_hierarchy = 'date_demande'
    list_per_page = 30
    show_full_result_count = False
    actions = ['approuver_demandes', 'refuser_demandes']

    def statut_badge(self, obj):
        c = {'approuvee': '#00C896', 'en_attente': '#F5A623', 'en_cours': '#7C6FFF', 'refusee': '#FF4F5E'}.get(obj.statut, '#999')
        return format_html('<span style="background:{};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px">{}</span>', c, obj.get_statut_display())
    statut_badge.short_description = "Statut"
    statut_badge.admin_order_field = 'statut'

    @admin.action(description="✅ Approuver les demandes sélectionnées")
    def approuver_demandes(self, request, queryset):
        n = 0
        for demande in queryset.filter(statut__in=['en_attente', 'en_cours']):
            demande.approuver(request.user)
            n += 1
        self.message_user(request, f"{n} demande(s) approuvée(s).", messages.SUCCESS)

    @admin.action(description="❌ Refuser les demandes sélectionnées")
    def refuser_demandes(self, request, queryset):
        n = 0
        for demande in queryset.filter(statut__in=['en_attente', 'en_cours']):
            demande.refuser(request.user, "Refusé en masse depuis l'admin.")
            n += 1
        self.message_user(request, f"{n} demande(s) refusée(s).", messages.WARNING)


@admin.register(AvisVendeur)
class AvisVendeurAdmin(admin.ModelAdmin):
    list_display = ('vendeur', 'utilisateur', 'note_etoiles', 'boutique', 'est_approuve', 'date_creation')
    list_filter  = ('note', 'est_approuve', ('date_creation', admin.DateFieldListFilter))
    search_fields = ('vendeur__username', 'utilisateur__username', 'commentaire')
    raw_id_fields = ('vendeur', 'boutique', 'utilisateur', 'commande')
    list_select_related = ('vendeur', 'boutique', 'utilisateur')
    readonly_fields = ('date_creation', 'date_modification')
    list_editable = ('est_approuve',)
    list_per_page = 40
    show_full_result_count = False

    def note_etoiles(self, obj):
        return format_html('<span style="color:#F5A623">{}</span>', '★' * obj.note + '☆' * (5 - obj.note))
    note_etoiles.short_description = "Note"
    note_etoiles.admin_order_field = 'note'


# ===========================================================================
# SECTION 2 — PANIER & COMMANDES
# ===========================================================================

@admin.register(Panier)
class PanierAdmin(admin.ModelAdmin):
    list_display = ('id', 'utilisateur_display', 'nb_articles', 'total_display', 'date_modification')
    search_fields = ('utilisateur__username', 'cle_session')
    raw_id_fields = ('utilisateur',)
    list_select_related = ('utilisateur',)
    readonly_fields = ('date_creation', 'date_modification')
    inlines = [ArticlePanierInline]
    list_per_page = 40
    show_full_result_count = False

    def utilisateur_display(self, obj):
        return obj.utilisateur.username if obj.utilisateur else f"Anonyme ({obj.cle_session[:12]}…)"
    utilisateur_display.short_description = "Utilisateur"

    def nb_articles(self, obj):
        return obj.articles.count()
    nb_articles.short_description = "Articles"

    def total_display(self, obj):
        return format_html('<strong>{:,.0f} XAF</strong>', obj.total())
    total_display.short_description = "Total"


@admin.register(Commande)
class CommandeAdmin(admin.ModelAdmin):
    list_display = (
        'numero_commande', 'utilisateur_display', 'boutique', 'source',
        'statut_badge', 'statut_paiement_badge', 'montant_total_display', 'date_creation',
    )
    list_display_links = ('numero_commande',)
    list_filter = (
        'statut', 'statut_paiement', 'source', 'livraison_gratuite',
        'est_paiement_fractionne',
        ('date_creation', admin.DateFieldListFilter),
    )
    search_fields = ('numero_commande', 'utilisateur__username', 'utilisateur__email')
    raw_id_fields = ('utilisateur', 'boutique', 'ville_livraison', 'quartier_livraison', 'code_promo')
    filter_horizontal = ('promotions_appliquees',)
    list_select_related = ('utilisateur', 'boutique', 'ville_livraison')
    readonly_fields = ('id', 'numero_commande', 'date_creation', 'date_modification')
    date_hierarchy = 'date_creation'
    list_per_page = 30
    show_full_result_count = False

    fieldsets = (
        ("Identité", {'fields': ('id', 'numero_commande', 'utilisateur', 'boutique', 'source')}),
        ("Adresses", {'fields': ('adresse_facturation', 'adresse_livraison', 'ville_livraison', 'quartier_livraison')}),
        ("Montants", {'fields': ('sous_total', 'montant_taxe', 'frais_livraison', 'montant_reduction', 'montant_total', 'devise')}),
        ("Promotions", {'fields': ('promotions_appliquees', 'code_promo', 'livraison_gratuite'), 'classes': ('collapse',)}),
        ("Statuts", {'fields': ('statut', 'statut_paiement')}),
        ("Paiement fractionné", {'fields': ('est_paiement_fractionne', 'nombre_tranches'), 'classes': ('collapse',)}),
        ("Dates", {'fields': ('date_creation', 'date_modification', 'date_expedition', 'date_livraison')}),
        ("Notes", {'fields': ('notes', 'instructions_livraison'), 'classes': ('collapse',)}),
    )

    inlines = [ArticleCommandeInline, PaiementInline]
    actions = ['marquer_confirmee', 'marquer_expediee', 'marquer_livree', 'marquer_annulee']

    def utilisateur_display(self, obj):
        return obj.utilisateur.username
    utilisateur_display.short_description = "Client"
    utilisateur_display.admin_order_field = 'utilisateur__username'

    def statut_badge(self, obj):
        c = {
            'livree': '#00C896', 'expediee': '#7C6FFF', 'confirmee': '#F5A623',
            'en_traitement': '#F5A623', 'en_attente': '#6B7399',
            'annulee': '#FF4F5E', 'remboursee': '#FF4F5E',
        }.get(obj.statut, '#999')
        return format_html('<span style="background:{};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px">{}</span>', c, obj.get_statut_display())
    statut_badge.short_description = "Statut"
    statut_badge.admin_order_field = 'statut'

    def statut_paiement_badge(self, obj):
        c = {'payee': '#00C896', 'en_attente': '#F5A623', 'echec': '#FF4F5E', 'en_verification': '#7C6FFF'}.get(obj.statut_paiement, '#6B7399')
        return format_html('<span style="color:{}">●</span> {}', c, obj.get_statut_paiement_display())
    statut_paiement_badge.short_description = "Paiement"
    statut_paiement_badge.admin_order_field = 'statut_paiement'

    def montant_total_display(self, obj):
        return format_html('<strong style="color:#F5A623">{:,.0f} {}</strong>', obj.montant_total, obj.devise)
    montant_total_display.short_description = "Total"
    montant_total_display.admin_order_field = 'montant_total'

    @admin.action(description="✅ Marquer comme confirmée")
    def marquer_confirmee(self, request, queryset):
        n = queryset.update(statut='confirmee')
        self.message_user(request, f"{n} commande(s) confirmée(s).", messages.SUCCESS)

    @admin.action(description="🚚 Marquer comme expédiée")
    def marquer_expediee(self, request, queryset):
        n = queryset.update(statut='expediee', date_expedition=timezone.now())
        self.message_user(request, f"{n} commande(s) expédiée(s).", messages.SUCCESS)

    @admin.action(description="📦 Marquer comme livrée")
    def marquer_livree(self, request, queryset):
        n = queryset.update(statut='livree', date_livraison=timezone.now())
        self.message_user(request, f"{n} commande(s) livrée(s).", messages.SUCCESS)

    @admin.action(description="❌ Marquer comme annulée")
    def marquer_annulee(self, request, queryset):
        n = queryset.update(statut='annulee')
        self.message_user(request, f"{n} commande(s) annulée(s).", messages.WARNING)


@admin.register(ArticleCommande)
class ArticleCommandeAdmin(admin.ModelAdmin):
    list_display = ('commande', 'produit', 'quantite', 'prix_total_display', 'taux_commission_applique', 'commission_display', 'boutique')
    search_fields = ('commande__numero_commande', 'produit__titre')
    raw_id_fields = ('commande', 'produit', 'variante', 'enchere', 'boutique')
    list_select_related = ('commande', 'produit', 'boutique')
    readonly_fields = ('prix_total', 'taux_commission_applique', 'commission_boutique')
    list_per_page = 50
    show_full_result_count = False

    def prix_total_display(self, obj):
        return format_html('{:,.0f} XAF', obj.prix_total)
    prix_total_display.short_description = "Total"
    prix_total_display.admin_order_field = 'prix_total'

    def commission_display(self, obj):
        return format_html('<span style="color:#00C896">{:,.0f} XAF</span>', obj.commission_boutique)
    commission_display.short_description = "Commission"
    commission_display.admin_order_field = 'commission_boutique'


# ===========================================================================
# SECTION 3 — CODES PROMO
# ===========================================================================

@admin.register(CodePromo)
class CodePromoAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'nom', 'type_reduction', 'valeur_reduction',
        'statut_badge', 'utilisation_display', 'date_debut', 'date_fin',
    )
    list_filter  = ('statut', 'type_reduction', 'type_cible', 'cumulable')
    search_fields = ('code', 'nom')
    filter_horizontal = ('utilisateurs_cibles', 'categories_ciblees', 'produits_cibles')
    raw_id_fields = ('createur',)
    readonly_fields = ('id', 'nombre_utilisations', 'date_creation')
    date_hierarchy = 'date_creation'
    list_per_page = 30
    show_full_result_count = False
    actions = ['activer_codes', 'desactiver_codes']

    fieldsets = (
        ("Identité", {'fields': ('id', 'code', 'nom', 'description', 'createur')}),
        ("Réduction", {'fields': ('type_reduction', 'valeur_reduction', 'montant_max_reduction', 'montant_min_commande')}),
        ("Ciblage", {'fields': ('type_cible', 'utilisateurs_cibles', 'categories_ciblees', 'produits_cibles'), 'classes': ('collapse',)}),
        ("Limites", {'fields': ('limite_utilisation_globale', 'limite_par_utilisateur', 'nombre_utilisations')}),
        ("Période", {'fields': ('date_debut', 'date_fin')}),
        ("Statut", {'fields': ('statut', 'cumulable')}),
        ("Métadonnées", {'fields': ('date_creation',), 'classes': ('collapse',)}),
    )

    def statut_badge(self, obj):
        c = {'actif': '#00C896', 'inactif': '#6B7399', 'expire': '#FF4F5E', 'epuise': '#F5A623'}.get(obj.statut, '#999')
        return format_html('<span style="background:{};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px">{}</span>', c, obj.get_statut_display())
    statut_badge.short_description = "Statut"
    statut_badge.admin_order_field = 'statut'

    def utilisation_display(self, obj):
        if obj.limite_utilisation_globale:
            return f"{obj.nombre_utilisations} / {obj.limite_utilisation_globale}"
        return f"{obj.nombre_utilisations} / ∞"
    utilisation_display.short_description = "Utilisations"

    @admin.action(description="✅ Activer les codes sélectionnés")
    def activer_codes(self, request, queryset):
        n = queryset.update(statut='actif')
        self.message_user(request, f"{n} code(s) activé(s).", messages.SUCCESS)

    @admin.action(description="⛔ Désactiver les codes sélectionnés")
    def desactiver_codes(self, request, queryset):
        n = queryset.update(statut='inactif')
        self.message_user(request, f"{n} code(s) désactivé(s).", messages.WARNING)


# ===========================================================================
# SECTION 4 — PAIEMENTS
# ===========================================================================

@admin.register(Operateur)
class OperateurAdmin(admin.ModelAdmin):
    list_display = ('nom', 'code', 'logo_apercu', 'est_actif')
    list_editable = ('est_actif',)
    search_fields = ('nom', 'code')
    list_per_page = 30

    def logo_apercu(self, obj):
        if obj.logo:
            return format_html('<img src="{}" style="height:28px;width:28px;object-fit:contain;border-radius:4px"/>', obj.logo.url)
        return "—"
    logo_apercu.short_description = "Logo"


@admin.register(NumeroVersement)
class NumeroVersementAdmin(admin.ModelAdmin):
    list_display = ('numero', 'operateur', 'pays', 'nom_compte', 'est_actif', 'date_creation')
    list_filter  = ('operateur', 'pays', 'est_actif')
    search_fields = ('numero', 'nom_compte')
    raw_id_fields = ('pays', 'operateur')
    list_select_related = ('pays', 'operateur')
    readonly_fields = ('date_creation',)
    list_editable = ('est_actif',)
    list_per_page = 30


@admin.register(PlanPaiement)
class PlanPaiementAdmin(admin.ModelAdmin):
    list_display = ('commande', 'nombre_tranches', 'montant_total_display', 'montant_paye_display', 'montant_restant_display', 'est_active')
    raw_id_fields = ('commande',)
    list_select_related = ('commande',)
    readonly_fields = ('date_creation',)
    inlines = [TranchePaiementInline]
    list_per_page = 30
    show_full_result_count = False

    def montant_total_display(self, obj):
        return format_html('{:,.0f} XAF', obj.montant_total)
    montant_total_display.short_description = "Total"

    def montant_paye_display(self, obj):
        return format_html('<span style="color:#00C896">{:,.0f} XAF</span>', obj.montant_paye())
    montant_paye_display.short_description = "Payé"

    def montant_restant_display(self, obj):
        c = '#FF4F5E' if obj.montant_restant() > 0 else '#00C896'
        return format_html('<span style="color:{}">{:,.0f} XAF</span>', c, obj.montant_restant())
    montant_restant_display.short_description = "Restant"


@admin.register(TranchePaiement)
class TranchePaiementAdmin(admin.ModelAdmin):
    list_display = ('plan_paiement', 'numero_tranche', 'montant_display', 'date_echeance', 'statut_badge', 'est_en_retard_display')
    list_filter  = ('statut',)
    raw_id_fields = ('plan_paiement', 'paiement')
    list_select_related = ('plan_paiement',)
    readonly_fields = ('date_creation',)
    list_per_page = 40
    show_full_result_count = False

    def montant_display(self, obj):
        return format_html('{:,.0f} XAF', obj.montant)
    montant_display.short_description = "Montant"

    def statut_badge(self, obj):
        c = {'payee': '#00C896', 'en_attente': '#F5A623', 'en_retard': '#FF4F5E', 'annulee': '#6B7399'}.get(obj.statut, '#999')
        return format_html('<span style="background:{};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px">{}</span>', c, obj.get_statut_display())
    statut_badge.short_description = "Statut"

    def est_en_retard_display(self, obj):
        return "⚠️ Oui" if obj.est_en_retard() else "—"
    est_en_retard_display.short_description = "En retard"


@admin.register(Paiement)
class PaiementAdmin(admin.ModelAdmin):
    """
    ⚠️ MySQL : flags_fraude et reponse_passerelle sont des JSONField
    volontairement absents de list_display/search_fields.
    """
    list_display = (
        'commande', 'methode', 'montant_display', 'statut_badge',
        'score_fraude_display', 'apercu_preuve', 'date_creation',
    )
    list_display_links = ('commande',)
    list_filter = ('statut', 'methode', 'est_suspect', ('date_creation', admin.DateFieldListFilter))
    search_fields = ('commande__numero_commande', 'reference_paiement', 'numero_expediteur', 'id_transaction')
    raw_id_fields = ('commande', 'tranche_paiement', 'valide_par')
    list_select_related = ('commande', 'valide_par')
    readonly_fields = ('date_creation', 'date_completion', 'apercu_preuve')
    date_hierarchy = 'date_creation'
    list_per_page = 30
    show_full_result_count = False

    fieldsets = (
        ("Commande & Montant", {'fields': ('commande', 'methode', 'montant', 'tranche_paiement')}),
        ("Statut", {'fields': ('statut',)}),
        ("Preuve manuelle", {'fields': ('preuve_paiement', 'apercu_preuve', 'numero_expediteur', 'message_client')}),
        ("Validation admin", {'fields': ('valide_par', 'date_validation', 'commentaire_admin', 'motif_rejet')}),
        ("Anti-fraude", {'fields': ('score_fraude', 'est_suspect'), 'classes': ('collapse',)}),
        ("Technique", {'fields': ('id_transaction',), 'classes': ('collapse',)}),
        ("Dates", {'fields': ('date_creation', 'date_completion')}),
    )

    actions = ['valider_paiements', 'rejeter_paiements']

    def montant_display(self, obj):
        return format_html('<strong>{:,.0f} XAF</strong>', obj.montant)
    montant_display.short_description = "Montant"
    montant_display.admin_order_field = 'montant'

    def statut_badge(self, obj):
        c = {
            'complete': '#00C896', 'en_attente': '#F5A623', 'en_verification': '#7C6FFF',
            'echec': '#FF4F5E', 'rejete': '#FF4F5E', 'annule': '#6B7399', 'rembourse': '#6B7399',
        }.get(obj.statut, '#999')
        return format_html('<span style="background:{};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px">{}</span>', c, obj.get_statut_display())
    statut_badge.short_description = "Statut"
    statut_badge.admin_order_field = 'statut'

    def score_fraude_display(self, obj):
        c = '#FF4F5E' if obj.est_suspect else '#00C896'
        return format_html('<span style="color:{}">{}</span>', c, obj.score_fraude)
    score_fraude_display.short_description = "Score fraude"
    score_fraude_display.admin_order_field = 'score_fraude'

    def apercu_preuve(self, obj):
        if obj.preuve_paiement:
            return format_html('<a href="{}" target="_blank">📄 Voir la preuve</a>', obj.preuve_paiement.url)
        return "—"
    apercu_preuve.short_description = "Preuve"

    @admin.action(description="✅ Valider les paiements sélectionnés")
    def valider_paiements(self, request, queryset):
        n = 0
        for p in queryset.filter(statut__in=['en_attente', 'en_verification']):
            if p.valider(request.user, "Validé en masse depuis l'admin."):
                n += 1
        self.message_user(request, f"{n} paiement(s) validé(s).", messages.SUCCESS)

    @admin.action(description="❌ Rejeter les paiements sélectionnés")
    def rejeter_paiements(self, request, queryset):
        n = 0
        for p in queryset.filter(statut__in=['en_attente', 'en_verification']):
            if p.rejeter(request.user, "Rejeté en masse depuis l'admin."):
                n += 1
        self.message_user(request, f"{n} paiement(s) rejeté(s).", messages.WARNING)


# ===========================================================================
# SECTION 5 — LIVRAISON
# ===========================================================================

@admin.register(MethodeLivraison)
class MethodeLivraisonAdmin(admin.ModelAdmin):
    list_display = ('nom', 'type_livraison', 'prix_display', 'delai_min', 'delai_max', 'est_active')
    list_filter  = ('type_livraison', 'est_active')
    search_fields = ('nom',)
    list_editable = ('est_active',)
    list_per_page = 30

    def prix_display(self, obj):
        return format_html('{:,.0f} XAF', obj.prix)
    prix_display.short_description = "Prix"
    prix_display.admin_order_field = 'prix'


@admin.register(Livraison)
class LivraisonAdmin(admin.ModelAdmin):
    list_display = (
        'commande', 'methode_livraison', 'livreur_display', 'statut_badge',
        'numero_suivi', 'date_livraison_prevue',
    )
    list_filter  = ('statut', 'methode_livraison')
    search_fields = ('commande__numero_commande', 'numero_suivi', 'transporteur')
    raw_id_fields = ('commande', 'livreur')
    list_select_related = ('commande', 'methode_livraison', 'livreur')
    readonly_fields = ('date_creation', 'date_modification', 'derniere_position_maj')
    list_per_page = 30
    show_full_result_count = False
    inlines = [HistoriqueLivraisonInline]

    fieldsets = (
        ("Commande", {'fields': ('commande', 'methode_livraison', 'livreur')}),
        ("Suivi", {'fields': ('numero_suivi', 'transporteur', 'statut')}),
        ("Géolocalisation", {'fields': ('livreur_latitude', 'livreur_longitude', 'derniere_position_maj'), 'classes': ('collapse',)}),
        ("Estimation", {'fields': ('delai_estime_minutes', 'itineraire_url'), 'classes': ('collapse',)}),
        ("Dates", {'fields': ('date_expedition', 'date_livraison_prevue', 'date_livraison_reelle')}),
        ("Preuves", {'fields': ('signature_client', 'photo_livraison', 'notes'), 'classes': ('collapse',)}),
    )

    def livreur_display(self, obj):
        return obj.livreur.username if obj.livreur else "—"
    livreur_display.short_description = "Livreur"

    def statut_badge(self, obj):
        c = {
            'livree': '#00C896', 'en_livraison': '#7C6FFF', 'en_transit': '#7C6FFF',
            'expediee': '#F5A623', 'prise_en_charge': '#F5A623', 'en_preparation': '#6B7399',
            'echec': '#FF4F5E', 'retournee': '#FF4F5E',
        }.get(obj.statut, '#999')
        return format_html('<span style="background:{};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px">{}</span>', c, obj.get_statut_display())
    statut_badge.short_description = "Statut"
    statut_badge.admin_order_field = 'statut'


# ===========================================================================
# SECTION 6 — RETOURS
# ===========================================================================

@admin.register(Retour)
class RetourAdmin(admin.ModelAdmin):
    list_display = (
        'commande', 'utilisateur', 'raison', 'quantite',
        'statut_badge', 'montant_remboursement_display', 'date_demande',
    )
    list_filter  = ('statut', 'raison', ('date_demande', admin.DateFieldListFilter))
    search_fields = ('commande__numero_commande', 'utilisateur__username', 'description')
    raw_id_fields = ('commande', 'article_commande', 'utilisateur')
    filter_horizontal = ('photos',)
    list_select_related = ('commande', 'utilisateur')
    readonly_fields = ('date_demande',)
    date_hierarchy = 'date_demande'
    list_per_page = 30
    show_full_result_count = False
    actions = ['approuver_retours', 'refuser_retours']

    def statut_badge(self, obj):
        c = {'complete': '#00C896', 'approuve': '#7C6FFF', 'demande': '#F5A623', 'en_cours': '#F5A623', 'refuse': '#FF4F5E'}.get(obj.statut, '#999')
        return format_html('<span style="background:{};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px">{}</span>', c, obj.get_statut_display())
    statut_badge.short_description = "Statut"
    statut_badge.admin_order_field = 'statut'

    def montant_remboursement_display(self, obj):
        if obj.montant_remboursement:
            return format_html('{:,.0f} XAF', obj.montant_remboursement)
        return "—"
    montant_remboursement_display.short_description = "Remboursement"

    @admin.action(description="✅ Approuver les retours sélectionnés")
    def approuver_retours(self, request, queryset):
        n = queryset.filter(statut='demande').update(statut='approuve', date_traitement=timezone.now())
        self.message_user(request, f"{n} retour(s) approuvé(s).", messages.SUCCESS)

    @admin.action(description="❌ Refuser les retours sélectionnés")
    def refuser_retours(self, request, queryset):
        n = queryset.filter(statut='demande').update(statut='refuse', date_traitement=timezone.now())
        self.message_user(request, f"{n} retour(s) refusé(s).", messages.WARNING)


# ===========================================================================
# SECTION 7 — ACHAT GROUPÉ
# ===========================================================================

@admin.register(GroupeAchat)
class GroupeAchatAdmin(admin.ModelAdmin):
    list_display = (
        'produit', 'createur', 'prix_normal_display', 'prix_groupe_display',
        'progression_display', 'statut_badge', 'date_expiration',
    )
    list_filter  = ('statut', ('date_expiration', admin.DateFieldListFilter))
    search_fields = ('produit__titre', 'createur__username')
    raw_id_fields = ('produit', 'createur')
    list_select_related = ('produit', 'createur')
    readonly_fields = ('id', 'date_creation')
    list_per_page = 30
    show_full_result_count = False
    inlines = [ParticipantGroupeAchatInline]

    def prix_normal_display(self, obj):
        return format_html('{:,.0f} XAF', obj.prix_normal)
    prix_normal_display.short_description = "Prix normal"

    def prix_groupe_display(self, obj):
        return format_html('<span style="color:#00C896">{:,.0f} XAF</span> (-{}%)', obj.prix_groupe, obj.pourcentage_reduction())
    prix_groupe_display.short_description = "Prix groupe"

    def progression_display(self, obj):
        actuels = obj.participants.filter(a_confirme=True).count()
        c = '#00C896' if obj.est_complet() else '#F5A623'
        return format_html('<span style="color:{}">{} / {}</span>', c, actuels, obj.nb_participants_min)
    progression_display.short_description = "Participants"

    def statut_badge(self, obj):
        c = {'complet': '#00C896', 'ouvert': '#F5A623', 'traite': '#7C6FFF', 'expire': '#FF4F5E'}.get(obj.statut, '#999')
        return format_html('<span style="background:{};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px">{}</span>', c, obj.get_statut_display())
    statut_badge.short_description = "Statut"
    statut_badge.admin_order_field = 'statut'


@admin.register(ParticipantGroupeAchat)
class ParticipantGroupeAchatAdmin(admin.ModelAdmin):
    list_display = ('groupe', 'utilisateur', 'quantite', 'a_confirme', 'commande', 'date_adhesion')
    list_filter  = ('a_confirme',)
    search_fields = ('utilisateur__username', 'groupe__produit__titre')
    raw_id_fields = ('groupe', 'utilisateur', 'commande')
    list_select_related = ('groupe', 'utilisateur')
    readonly_fields = ('date_adhesion',)
    list_per_page = 40
    show_full_result_count = False