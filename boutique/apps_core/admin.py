
# ===========================================================================
# apps_core/admin.py
# Administration Django — Application socle (apps_core)
#
# COMPATIBILITÉ MYSQL :
#   - Pas de JSONField dans list_display (MySQL < 5.7 ne supporte pas JSON)
#   - search_fields sans '__' sur JSONField
#   - list_select_related pour éviter les N+1 queries
#   - show_full_result_count = False sur les grands tableaux (perf MySQL)
#   - Pas de list_display sur ImageField (cause erreur sans Pillow)
#   - autocomplete_fields pour les FK (évite SELECT * sur grandes tables)
#   - raw_id_fields en fallback quand autocomplete non disponible
# ===========================================================================


 
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html, mark_safe
from django.utils.translation import gettext_lazy as _
from django.db.models import Count, Avg, Sum, Q 
from django.utils import timezone
from django.urls import reverse
from django.contrib import messages
 
from .models import (
    Utilisateur,ProfilUtilisateur,TransactionWallet,Pays,
    Region,Ville,Quartier,Categorie,Marque,
    Produit,ImageProduit,VarianteProduit,AttributProduit,
    Promotion,ImageAvis,Avis,ListeSouhaits,Notification,DemandeRechargeWallet,
)

# ===========================================================================
# CONFIGURATION ADMIN SITE
# ===========================================================================
 
admin.site.site_header  = "🛍️ YopiShop Administration"
admin.site.site_title   = "YopiShop Admin"
admin.site.index_title  = "Tableau de bord — Administration YopiShop"

# ===========================================================================
# INLINES
# ===========================================================================
 
class ProfilUtilisateurInline(admin.StackedInline):
    """Profil affiché directement dans la fiche utilisateur."""
    model               = ProfilUtilisateur
    can_delete          = False
    verbose_name_plural = "Profil étendu"
    fields              = (
        'est_vendeur', 'vendeur_verifie',
        'niveau', 'points_total', 'note_moyenne',
        'langue_preference', 'devise_preference',
        'notifications_email', 'notifications_sms', 'notifications_push',
    )
    readonly_fields = ('note_moyenne',)
 
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('utilisateur')
 
 
class ImageProduitInline(admin.TabularInline):
    """Images directement dans la fiche produit."""
    model          = ImageProduit
    extra          = 1
    max_num        = 10
    fields         = ('image', 'apercu_image', 'texte_alternatif', 'est_principale', 'ordre')
    readonly_fields = ('apercu_image',)
 
    def apercu_image(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:60px;width:60px;'
                'object-fit:cover;border-radius:6px;border:1px solid #444"/>',
                obj.image.url
            )
        return "—"
    apercu_image.short_description = "Aperçu"
 
 
class VarianteProduitInline(admin.TabularInline):
    """Variantes directement dans la fiche produit."""
    model   = VarianteProduit
    extra   = 0
    fields  = ('nom', 'valeur', 'prix_supplementaire', 'stock', 'sku_variante', 'est_active')
 
 
class AttributProduitInline(admin.TabularInline):
    """Attributs techniques dans la fiche produit."""
    model   = AttributProduit
    extra   = 0
    fields  = ('nom', 'valeur', 'unite', 'ordre')
 
 
class RegionInline(admin.TabularInline):
    """Régions dans la fiche pays."""
    model   = Region
    extra   = 0
    fields  = ('nom', 'code', 'est_actif')
    show_change_link = True
 
 
class VilleInline(admin.TabularInline):
    """Villes dans la fiche région."""
    model   = Ville
    extra   = 0
    fields  = ('nom', 'code_postal', 'frais_livraison_defaut', 'est_actif')
    show_change_link = True
 
 
class QuartierInline(admin.TabularInline):
    """Quartiers dans la fiche ville."""
    model   = Quartier
    extra   = 0
    fields  = ('nom', 'frais_livraison_supplement')


class TransactionWalletInline(admin.TabularInline):
    """Transactions wallet dans la fiche utilisateur."""
    model           = TransactionWallet
    extra           = 0
    max_num         = 0       # lecture seule — pas d'ajout depuis l'inline
    can_delete      = False
    fields          = ('type_transaction', 'montant', 'solde_apres', 'description', 'date_creation')
    readonly_fields = ('type_transaction', 'montant', 'solde_apres', 'description', 'date_creation')
 
    def has_add_permission(self, request, obj=None):
        return False


# ===========================================================================
# UTILISATEUR
# ===========================================================================
 
@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    """
    Admin Utilisateur — étend UserAdmin de Django.
    Compatible MySQL : pas de JSONField dans list_display.
    """
 
    # ── Colonnes du listing ──────────────────────────────────────────────────
    list_display = (
        'username', 'nom_complet_display', 'email',
        'role', 'type_vendeur_badge', 'est_verifie',
        'kyc_valide', 'solde_wallet_display', 'date_creation',
    )
    list_display_links = ('username', 'nom_complet_display')
    list_filter = (
        'role', 'type_vendeur', 'est_verifie', 'kyc_valide',
        'est_influenceur', 'is_active', 'is_staff',
        ('date_creation', admin.DateFieldListFilter),
    )
    search_fields = (
        'username', 'email', 'first_name', 'last_name',
        'telephone', 'sous_domaine',
    )
    ordering        = ('-date_creation',)
    date_hierarchy  = 'date_creation'
    list_per_page   = 30
    list_select_related = True
    show_full_result_count = False   # perf MySQL sur grande table
 
    # ── Champs en lecture seule ──────────────────────────────────────────────
    readonly_fields = (
        'date_creation', 'date_modification',
        'derniere_connexion_ip', 'last_login',
        'solde_wallet_display', 'a_boutique_display',
    )
 
    # ── Formulaire (fieldsets) ───────────────────────────────────────────────
    fieldsets = (
        (_("Identifiants"), {
            'fields': ('username', 'password')
        }),
        (_("Informations personnelles"), {
            'fields': (
                'first_name', 'last_name', 'email',
                'telephone', 'date_naissance', 'avatar', 'bio',
            )
        }),
        (_("Localisation"), {
            'fields': ('adresse', 'ville', 'pays', 'code_postal'),
            'classes': ('collapse',),
        }),
        (_("Rôle & Type vendeur"), {
            'fields': (
                'role', 'type_vendeur',
                'est_verifie', 'kyc_valide',
                'est_influenceur', 'taux_commission_influenceur',
                'sous_domaine', 'est_produit_yopishop',
            )
        }),
        (_("YopiPay Wallet"), {
            'fields': ('solde_wallet', 'solde_wallet_display'),
            'classes': ('collapse',),
        }),
        (_("Permissions Django"), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'classes': ('collapse',),
        }),
        (_("Métadonnées"), {
            'fields': ('last_login', 'date_creation', 'date_modification', 'derniere_connexion_ip'),
            'classes': ('collapse',),
        }),
    )
 
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'username', 'email', 'password1', 'password2',
                'first_name', 'last_name', 'role', 'type_vendeur',
            ),
        }),
    )
 
    # ── Inlines ──────────────────────────────────────────────────────────────
    inlines = [ProfilUtilisateurInline, TransactionWalletInline]
 
    # ── Autocomplete pour FK (évite SELECT * sur Ville / Pays) ──────────────
    autocomplete_fields = []   # Ville et Pays n'ont pas search_fields définis ici
 
    # ── Actions personnalisées ───────────────────────────────────────────────
    actions = [
        'marquer_verifie', 'marquer_kyc_valide',
        'activer_comptes', 'desactiver_comptes',
        'passer_en_vendeur_individuel',
    ]
 
    # ── Méthodes d'affichage ─────────────────────────────────────────────────
 
    def nom_complet_display(self, obj):
        return obj.nom_complet or "—"
    nom_complet_display.short_description = "Nom complet"
    nom_complet_display.admin_order_field = 'first_name'
 
    def type_vendeur_badge(self, obj):
        couleurs = {
            'aucun':      ('#6B7399', '—'),
            'individuel': ('#F5A623', '🛒 Individuel'),
            'pro':        ('#7C6FFF', '💼 Pro'),
            'yopishop':   ('#00C896', '✅ YopiShop'),
        }
        couleur, label = couleurs.get(obj.type_vendeur, ('#999', obj.type_vendeur))
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:12px;font-size:11px;font-weight:600">{}</span>',
            couleur, label
        )
    type_vendeur_badge.short_description = "Type vendeur"
    type_vendeur_badge.admin_order_field = 'type_vendeur'
 
    def solde_wallet_display(self, obj):
        couleur = '#00C896' if obj.solde_wallet > 0 else '#6B7399'
        # ✅ Formater le nombre AVANT de passer à format_html
        solde_formate = "{:,.0f}".format(float(obj.solde_wallet or 0))
        return format_html(
            '<strong style="color:{}">{} XAF</strong>',
            couleur, solde_formate
        )
    solde_wallet_display.short_description = "Solde wallet"
 
    def a_boutique_display(self, obj):
        if obj.a_boutique:
            return format_html('<span style="color:#00C896">✅ Oui</span>')
        return format_html('<span style="color:#FF4F5E">❌ Non</span>')
    a_boutique_display.short_description = "A une boutique"


    # ── Actions ──────────────────────────────────────────────────────────────
 
    @admin.action(description="✅ Marquer comme vérifiés (email)")
    def marquer_verifie(self, request, queryset):
        n = queryset.update(est_verifie=True)
        self.message_user(request, f"{n} utilisateur(s) marqué(s) comme vérifiés.", messages.SUCCESS)
 
    @admin.action(description="🔐 Valider le KYC")
    def marquer_kyc_valide(self, request, queryset):
        n = queryset.update(kyc_valide=True)
        self.message_user(request, f"KYC validé pour {n} utilisateur(s).", messages.SUCCESS)
 
    @admin.action(description="▶️ Activer les comptes")
    def activer_comptes(self, request, queryset):
        n = queryset.update(is_active=True)
        self.message_user(request, f"{n} compte(s) activé(s).", messages.SUCCESS)
 
    @admin.action(description="⏸️ Désactiver les comptes")
    def desactiver_comptes(self, request, queryset):
        n = queryset.filter(is_staff=False, is_superuser=False).update(is_active=False)
        self.message_user(request, f"{n} compte(s) désactivé(s) (admins exclus).", messages.WARNING)
 
    @admin.action(description="🛒 Passer en vendeur individuel")
    def passer_en_vendeur_individuel(self, request, queryset):
        n = queryset.filter(type_vendeur='aucun').update(type_vendeur='individuel')
        self.message_user(request, f"{n} utilisateur(s) passé(s) en vendeur individuel.", messages.SUCCESS)


# ===========================================================================
# PROFIL UTILISATEUR
# ===========================================================================
 
@admin.register(ProfilUtilisateur)
class ProfilUtilisateurAdmin(admin.ModelAdmin):
    list_display    = ('utilisateur', 'niveau_badge', 'points_total', 'est_vendeur',
                       'vendeur_verifie', 'note_moyenne')
    list_filter     = ('niveau', 'est_vendeur', 'vendeur_verifie')
    search_fields   = ('utilisateur__username', 'utilisateur__email')
    readonly_fields = ('utilisateur', 'note_moyenne')
    list_select_related = ('utilisateur',)
    list_per_page   = 40
    show_full_result_count = False
 
    def niveau_badge(self, obj):
        couleurs = {
            'bronze':  '#CD7F32',
            'argent':  '#C0C0C0',
            'or':      '#FFD700',
            'platine': '#E5E4E2',
            'diamant': '#7C6FFF',
        }
        labels = {
            'bronze': '🥉 Bronze', 'argent': '🥈 Argent',
            'or': '🥇 Or', 'platine': '💎 Platine', 'diamant': '💠 Diamant',
        }
        c = couleurs.get(obj.niveau, '#999')
        l = labels.get(obj.niveau, obj.niveau)
        return format_html(
            '<span style="background:{};color:#000;padding:2px 8px;'
            'border-radius:12px;font-size:11px;font-weight:700">{}</span>', c, l
        )
    niveau_badge.short_description = "Niveau"
    niveau_badge.admin_order_field = 'niveau'


# ===========================================================================
# TRANSACTIONS WALLET
# ===========================================================================
 
@admin.register(TransactionWallet)
class TransactionWalletAdmin(admin.ModelAdmin):
    list_display    = ('utilisateur', 'type_badge', 'montant_display',
                       'solde_apres', 'description', 'date_creation')
    list_filter     = ('type_transaction', ('date_creation', admin.DateFieldListFilter))
    search_fields   = ('utilisateur__username', 'reference', 'description')
    raw_id_fields   = ('utilisateur',)
    readonly_fields = ('date_creation',)
    ordering        = ('-date_creation',)
    list_per_page   = 50
    date_hierarchy  = 'date_creation'
    show_full_result_count = False
 
    def has_add_permission(self, request):
        return False   # Les transactions se créent via le code, pas l'admin
 
    def has_change_permission(self, request, obj=None):
        return False   # Immuable
 
    def type_badge(self, obj):
        c = {'credit': '#00C896', 'debit': '#FF4F5E',
             'remboursement': '#F5A623', 'commission': '#7C6FFF',
             'bonus': '#FFD700', 'retrait': '#6B7399'}.get(obj.type_transaction, '#999')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 7px;'
            'border-radius:10px;font-size:11px">{}</span>',
            c, obj.get_type_transaction_display()
        )
    type_badge.short_description = "Type"
 
    def montant_display(self, obj):
        c = '#00C896' if obj.type_transaction in ('credit', 'bonus') else '#FF4F5E'
        sign = '+' if obj.type_transaction in ('credit', 'bonus') else '-'
        return format_html('<strong style="color:{}">{}{:,.0f} XAF</strong>', c, sign, obj.montant)
    montant_display.short_description = "Montant"
    montant_display.admin_order_field = 'montant'


# =============================================================================
# ADMIN (à ajouter dans admin.py) — pour valider les demandes depuis l'admin
# =============================================================================
@admin.register(DemandeRechargeWallet)
class DemandeRechargeAdmin(admin.ModelAdmin):
    list_display  = ('utilisateur', 'montant', 'methode', 'statut', 'date_creation')
    list_filter   = ('statut', 'methode')
    search_fields = ('utilisateur__username', 'utilisateur__email', 'reference')
    list_editable = ('statut',)
    actions       = ['valider_demandes']
 
    @admin.action(description="✅ Valider et créditer les wallets")
    def valider_demandes(self, request, queryset):
        from django.utils import timezone
        validated = 0
        for demande in queryset.filter(statut='en_attente'):
            user = demande.utilisateur
            # Créditer le wallet
            user.solde_wallet = (user.solde_wallet or 0) + demande.montant
            user.save(update_fields=['solde_wallet'])
            # Créer la transaction
            TransactionWallet.objects.create(
                utilisateur       = user,
                montant           = demande.montant,
                type_transaction  = 'credit',
                description       = f"Recharge via {demande.get_methode_display()}",
                solde_apres       = user.solde_wallet,
            )
            # Mettre à jour la demande
            demande.statut         = 'validee'
            demande.date_traitement = timezone.now()
            demande.save(update_fields=['statut', 'date_traitement'])
            validated += 1
        self.message_user(request, f"{validated} recharge(s) validée(s) et créditée(s).")



# ===========================================================================
# GÉOGRAPHIE
# ===========================================================================
 
@admin.register(Pays)
class PaysAdmin(admin.ModelAdmin):
    list_display    = ('nom', 'code', 'indicatif_tel', 'devise', 'nb_regions', 'est_actif')
    list_filter     = ('est_actif', 'devise')
    search_fields   = ('nom', 'code')
    list_editable   = ('est_actif',)
    inlines         = [RegionInline]
    list_per_page   = 30
 
    def nb_regions(self, obj):
        return obj.regions.count()
    nb_regions.short_description = "Régions"
 
    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _nb_regions=Count('regions')
        )
 
 
@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display    = ('nom', 'pays', 'code', 'nb_villes', 'est_actif')
    list_filter     = ('pays', 'est_actif')
    search_fields   = ('nom', 'code', 'pays__nom')
    list_select_related = ('pays',)
    inlines         = [VilleInline]
    autocomplete_fields = ['pays']
    list_per_page   = 40
    show_full_result_count = False
 
    def nb_villes(self, obj):
        return obj.villes.count()
    nb_villes.short_description = "Villes"
 
 
@admin.register(Ville)
class VilleAdmin(admin.ModelAdmin):
    list_display    = ('nom', 'region', 'pays_display', 'code_postal',
                       'frais_livraison_defaut', 'nb_quartiers', 'est_actif')
    list_filter     = ('region__pays', 'est_actif')
    search_fields   = ('nom', 'code_postal', 'region__nom', 'region__pays__nom')
    list_select_related = ('region', 'region__pays')
    list_editable   = ('frais_livraison_defaut', 'est_actif')
    inlines         = [QuartierInline]
    list_per_page   = 50
    show_full_result_count = False
 
    def pays_display(self, obj):
        return obj.region.pays.nom
    pays_display.short_description = "Pays"
    pays_display.admin_order_field = 'region__pays__nom'
 
    def nb_quartiers(self, obj):
        return obj.quartiers.count()
    nb_quartiers.short_description = "Quartiers"
 
 
@admin.register(Quartier)
class QuartierAdmin(admin.ModelAdmin):
    list_display    = ('nom', 'ville', 'frais_livraison_supplement')
    list_filter     = ('ville__region__pays',)
    search_fields   = ('nom', 'ville__nom')
    list_select_related = ('ville',)
    raw_id_fields   = ('ville',)
    list_per_page   = 60
    show_full_result_count = False
 

# ===========================================================================
# CATALOGUE — CATÉGORIES
# ===========================================================================
 
@admin.register(Categorie)
class CategorieAdmin(admin.ModelAdmin):
    list_display    = (
        'nom', 'slug', 'parent', 'nb_produits',
        'nb_sous_categories', 'ordre', 'est_active',
    )
    list_filter     = ('est_active', 'parent')
    search_fields   = ('nom', 'slug', 'description')
    prepopulated_fields = {'slug': ('nom',)}
    list_editable   = ('ordre', 'est_active')
    ordering        = ('ordre', 'nom')
    list_per_page   = 40
 
    def nb_produits(self, obj):
        return obj.produits.filter(est_actif=True).count()
    nb_produits.short_description = "Produits actifs"
 
    def nb_sous_categories(self, obj):
        return obj.sous_categories.count()
    nb_sous_categories.short_description = "Sous-catégories"
 
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('parent').annotate(
            _nb_produits=Count('produits', filter=Q(produits__est_actif=True))
        )


# ===========================================================================
# CATALOGUE — MARQUES
# ===========================================================================
 
@admin.register(Marque)
class MarqueAdmin(admin.ModelAdmin):
    list_display    = ('nom', 'slug', 'logo_apercu', 'nb_produits', 'est_active')
    list_filter     = ('est_active',)
    search_fields   = ('nom', 'slug')
    prepopulated_fields = {'slug': ('nom',)}
    list_editable   = ('est_active',)
    list_per_page   = 40
 
    def logo_apercu(self, obj):
        if obj.logo:
            return format_html(
                '<img src="{}" style="height:32px;width:32px;'
                'object-fit:contain;border-radius:4px"/>',
                obj.logo.url
            )
        return "—"
    logo_apercu.short_description = "Logo"
 
    def nb_produits(self, obj):
        return obj.produits.count()
    nb_produits.short_description = "Produits"


# ===========================================================================
# CATALOGUE — PRODUITS
# ===========================================================================
 
@admin.register(Produit)
class ProduitAdmin(admin.ModelAdmin):
    """
    Admin Produit — le plus complet.
    Précautions MySQL :
      - raw_id_fields sur FK avec beaucoup de données (vendeur, ville)
      - Pas de JSONField dans list_display
      - autocomplete pour categorie et marque
      - show_full_result_count=False
    """
 
    list_display = (
        'titre', 'categorie', 'vendeur_display', 'type_produit',
        'prix_display', 'stock_display', 'etat',
        'badges_display', 'note_moyenne', 'nb_vues', 'est_actif',
    )
    list_display_links  = ('titre',)
    list_filter = (
        'est_actif', 'est_vedette', 'est_b2b',
        'est_produit_yopishop', 'en_fulfillment',
        'type_produit', 'etat',
        'autorise_enchere', 'autorise_achat_groupe',
        ('date_creation', admin.DateFieldListFilter),
        'categorie',
    )
    search_fields = (
        'titre', 'slug', 'reference', 'sku',
        'description_courte',
        'vendeur__username', 'vendeur__email',
        'categorie__nom',
    )
    ordering        = ('-date_creation',)
    date_hierarchy  = 'date_creation'
    list_per_page   = 30
    show_full_result_count = False
    list_select_related   = ('categorie', 'marque', 'vendeur', 'ville')
 
    # FK volumineuses → raw_id pour éviter SELECT * au chargement
    raw_id_fields = ('vendeur', 'ville', 'quartier')
 
    # FK légères → autocomplete (requires search_fields sur l'admin cible)
    # Activé après que CategorieAdmin et MarqueAdmin ont search_fields
    autocomplete_fields = ('categorie', 'marque')
 
    readonly_fields = (
        'id', 'slug', 'nb_vues', 'nb_ventes', 'note_moyenne',
        'date_creation', 'date_modification',
        'image_principale_apercu',
    )
 
    fieldsets = (
        ("Identité", {
            'fields': (
                'id', 'titre', 'slug', 'reference', 'sku',
                'description_courte', 'description',
            )
        }),
        ("Classification", {
            'fields': ('type_produit', 'categorie', 'marque', 'etat', 'poids', 'dimensions')
        }),
        ("Vendeur", {
            'fields': ('vendeur',)
        }),
        ("Prix & Stock", {
            'fields': (
                'prix', 'prix_achat', 'devise',
                'quantite_stock', 'alerte_stock_min',
            )
        }),
        ("Options de vente", {
            'fields': (
                'est_actif', 'est_vedette', 'est_b2b',
                'est_produit_yopishop',
                'autorise_enchere', 'autorise_vente_directe', 'autorise_achat_groupe',
                'quantite_min_commande',
            ),
            'classes': ('wide',),
        }),
        ("Livraison", {
            'fields': (
                'ville', 'quartier', 'adresse_complete',
                'livraison_disponible', 'livraison_locale_uniquement', 'retrait_sur_place',
            ),
            'classes': ('collapse',),
        }),
        ("YopiFulfillment", {
            'fields': ('en_fulfillment', 'quantite_fulfillment'),
            'classes': ('collapse',),
        }),
        ("Réalité Augmentée", {
            'fields': ('modele_3d_url',),
            'classes': ('collapse',),
        }),
        ("SEO", {
            'fields': ('titre_meta', 'description_meta'),
            'classes': ('collapse',),
        }),
        ("Statistiques (lecture seule)", {
            'fields': ('nb_vues', 'nb_ventes', 'note_moyenne', 'date_creation', 'date_modification'),
            'classes': ('collapse',),
        }),
        ("Image principale", {
            'fields': ('image_principale_apercu',),
        }),
    )
 
    inlines = [ImageProduitInline, VarianteProduitInline, AttributProduitInline]
 
    actions = [
        'activer_produits', 'desactiver_produits',
        'marquer_vedette', 'retirer_vedette',
        'marquer_yopishop_officiel',
        'activer_enchere', 'desactiver_enchere',
    ]
 
    # ── Méthodes d'affichage ─────────────────────────────────────────────────
 
    def vendeur_display(self, obj):
        nom = obj.vendeur.boutique.nom if obj.vendeur.a_boutique else obj.vendeur.username
        return format_html('<span title="{}">{}</span>', obj.vendeur.email, nom)
    vendeur_display.short_description = "Vendeur"
    vendeur_display.admin_order_field = 'vendeur__username'
 
    def prix_display(self, obj):
    # ✅ Pré-formater le nombre AVANT de passer à format_html
        prix_formate = f"{obj.prix:,.0f} XAF"
        return format_html(
            '<strong style="color:#F5A623">{}</strong>',
            prix_formate          # ← une seule variable, pas de formatage inline
        )

    prix_display.short_description = "Prix"
    prix_display.admin_order_field = 'prix'
 
    def stock_display(self, obj):
        stock = obj.quantite_fulfillment if obj.en_fulfillment else obj.quantite_stock
        alerte = obj.alerte_stock_min or 0

        if stock == 0:
            couleur = '#FF4F5E'
            label   = "Épuisé"
        elif stock <= alerte:
            couleur = '#F5A623'
            label   = str(stock)
        else:
            couleur = '#00C896'
            label   = str(stock)

        return format_html(
            '<span style="color:{};font-weight:700">{}</span>',
            couleur,
            label
        )

    stock_display.short_description = "Stock"
    stock_display.admin_order_field = 'quantite_stock'
 
    def badges_display(self, obj):
        badges = []
        if obj.est_produit_yopishop:
            badges.append(
                '<span style="background:#00C896;color:#fff;'
                'padding:1px 6px;border-radius:8px;font-size:10px">✅ Officiel</span>'
            )
        if obj.est_vedette:
            badges.append(
                '<span style="background:#FFD700;color:#000;'
                'padding:1px 6px;border-radius:8px;font-size:10px">⭐ Vedette</span>'
            )
        if obj.autorise_enchere:
            badges.append(
                '<span style="background:#FF4F5E;color:#fff;'
                'padding:1px 6px;border-radius:8px;font-size:10px">🔨 Enchère</span>'
            )
        if obj.en_fulfillment:
            badges.append(
                '<span style="background:#7C6FFF;color:#fff;'
                'padding:1px 6px;border-radius:8px;font-size:10px">📦 FBA</span>'
            )
        # ✅ mark_safe car le HTML est construit en interne, pas depuis user input
        return mark_safe(' '.join(badges)) if badges else "—"

    badges_display.short_description = "Badges"
 
    def image_principale_apercu(self, obj):
        try:
            url = obj.image_principale()
        except Exception:
            url = None

        if url:
            return format_html(
                '<img src="{}" style="max-height:200px;max-width:300px;'
                'object-fit:contain;border-radius:8px"/>',
                url
            )
        return "Aucune image"

    image_principale_apercu.short_description = "Image principale"
 
    # ── Actions ──────────────────────────────────────────────────────────────
 
    @admin.action(description="▶️ Activer les produits")
    def activer_produits(self, request, queryset):
        n = queryset.update(est_actif=True)
        self.message_user(request, f"{n} produit(s) activé(s).", messages.SUCCESS)
 
    @admin.action(description="⏸️ Désactiver les produits")
    def desactiver_produits(self, request, queryset):
        n = queryset.update(est_actif=False)
        self.message_user(request, f"{n} produit(s) désactivé(s).", messages.WARNING)
 
    @admin.action(description="⭐ Marquer en vedette")
    def marquer_vedette(self, request, queryset):
        n = queryset.update(est_vedette=True)
        self.message_user(request, f"{n} produit(s) mis en vedette.", messages.SUCCESS)
 
    @admin.action(description="☆ Retirer de la vedette")
    def retirer_vedette(self, request, queryset):
        n = queryset.update(est_vedette=False)
        self.message_user(request, f"{n} produit(s) retirés de la vedette.", messages.SUCCESS)
 
    @admin.action(description="✅ Marquer comme Produits YopiShop Officiels")
    def marquer_yopishop_officiel(self, request, queryset):
        n = queryset.update(est_produit_yopishop=True)
        self.message_user(request, f"{n} produit(s) marqué(s) comme officiels.", messages.SUCCESS)
 
    @admin.action(description="🔨 Activer les enchères")
    def activer_enchere(self, request, queryset):
        n = queryset.update(autorise_enchere=True)
        self.message_user(request, f"Enchères activées pour {n} produit(s).", messages.SUCCESS)
 
    @admin.action(description="🚫 Désactiver les enchères")
    def desactiver_enchere(self, request, queryset):
        n = queryset.update(autorise_enchere=False)
        self.message_user(request, f"Enchères désactivées pour {n} produit(s).", messages.WARNING)
 
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'categorie', 'marque', 'vendeur', 'ville'
        )


# ===========================================================================
# IMAGES AVIS (standalone — peu utilisé directement)
# ===========================================================================
 
@admin.register(ImageAvis)
class ImageAvisAdmin(admin.ModelAdmin):
    list_display  = ('id', 'apercu', 'date_creation')
    readonly_fields = ('date_creation', 'apercu')
    list_per_page = 40
 
    def apercu(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:50px;width:50px;'
                'object-fit:cover;border-radius:6px"/>',
                obj.image.url
            )
        return "—"
    apercu.short_description = "Aperçu"


# ===========================================================================
# AVIS PRODUITS
# ===========================================================================
 
@admin.register(Avis)
class AvisAdmin(admin.ModelAdmin):
    list_display    = (
        'produit_display', 'utilisateur', 'note_etoiles',
        'est_achat_verifie', 'est_approuve', 'votes_utiles', 'date_creation',
    )
    list_filter     = (
        'note', 'est_approuve', 'est_achat_verifie',
        ('date_creation', admin.DateFieldListFilter),
    )
    search_fields   = (
        'titre', 'commentaire',
        'utilisateur__username', 'produit__titre',
    )
    raw_id_fields   = ('produit', 'utilisateur')
    readonly_fields = ('date_creation', 'date_modification')
    list_editable   = ('est_approuve',)
    ordering        = ('-date_creation',)
    date_hierarchy  = 'date_creation'
    list_per_page   = 40
    list_select_related = ('produit', 'utilisateur')
    show_full_result_count = False
 
    actions = ['approuver_avis', 'rejeter_avis']
 
    def produit_display(self, obj):
        return format_html(
            '<a href="{}">{}</a>',
            reverse('admin:apps_core_produit_change', args=[obj.produit.pk]),
            obj.produit.titre[:40]
        )
    produit_display.short_description = "Produit"
    produit_display.admin_order_field = 'produit__titre'
 
    def note_etoiles(self, obj):
        etoiles = '★' * obj.note + '☆' * (5 - obj.note)
        couleurs = {1: '#FF4F5E', 2: '#FF8C00', 3: '#F5A623', 4: '#7C6FFF', 5: '#00C896'}
        c = couleurs.get(obj.note, '#999')
        return format_html('<span style="color:{};font-size:14px">{}</span>', c, etoiles)
    note_etoiles.short_description = "Note"
    note_etoiles.admin_order_field = 'note'
 
    @admin.action(description="✅ Approuver les avis sélectionnés")
    def approuver_avis(self, request, queryset):
        n = queryset.update(est_approuve=True)
        self.message_user(request, f"{n} avis approuvé(s).", messages.SUCCESS)
 
    @admin.action(description="❌ Rejeter les avis sélectionnés")
    def rejeter_avis(self, request, queryset):
        n = queryset.update(est_approuve=False)
        self.message_user(request, f"{n} avis rejeté(s).", messages.WARNING)


# ===========================================================================
# LISTE DE SOUHAITS
# ===========================================================================
 
@admin.register(ListeSouhaits)
class ListeSouhaitsAdmin(admin.ModelAdmin):
    list_display    = ('utilisateur', 'nom', 'nb_produits', 'est_publique', 'date_creation')
    list_filter     = ('est_publique',)
    search_fields   = ('nom', 'utilisateur__username')
    raw_id_fields   = ('utilisateur',)
    filter_horizontal = ('produits',)   # ManyToMany — widget horizontal plus pratique
    readonly_fields = ('date_creation',)
    list_per_page   = 40
    show_full_result_count = False
 
    def nb_produits(self, obj):
        return obj.produits.count()
    nb_produits.short_description = "Produits"


# ===========================================================================
# PROMOTIONS
# ===========================================================================
 
@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display    = (
        'nom', 'type_promotion', 'valeur_affichage',
        'statut_badge', 'date_debut', 'date_fin',
        'nb_produits_cibles', 'priorite',
    )
    list_filter     = ('statut', 'type_promotion')
    search_fields   = ('nom', 'code', 'description')
    readonly_fields = ('date_creation',)
    list_editable   = ('priorite',)
    ordering        = ('-priorite', '-date_creation')
    date_hierarchy  = 'date_creation'
    list_per_page   = 30
 
    filter_horizontal = ('categories', 'produits', 'utilisateurs')
 
    fieldsets = (
        ("Identité", {
            'fields': ('nom', 'description', 'code', 'priorite', 'statut')
        }),
        ("Type & Valeur", {
            'fields': ('type_promotion', 'valeur_reduction',
                       'montant_max_reduction', 'montant_min_achat')
        }),
        ("Dates", {
            'fields': ('date_debut', 'date_fin')
        }),
        ("Ciblage", {
            'fields': ('categories', 'produits', 'utilisateurs'),
            'classes': ('collapse',),
        }),
        ("Limites", {
            'fields': ('limite_utilisation', 'limite_par_utilisateur'),
            'classes': ('collapse',),
        }),
        ("Métadonnées", {
            'fields': ('date_creation',),
            'classes': ('collapse',),
        }),
    )
 
    actions = ['activer_promotions', 'mettre_en_pause']
 
    def valeur_affichage(self, obj):
        if obj.type_promotion == 'pourcentage':
            return format_html('<strong style="color:#F5A623">{} %</strong>', obj.valeur_reduction)
        elif obj.type_promotion == 'montant_fixe':
            return format_html('<strong style="color:#7C6FFF">{:,.0f} XAF</strong>', obj.valeur_reduction)
        elif obj.type_promotion == 'livraison_gratuite':
            return format_html('<span style="color:#00C896">🚚 Gratuite</span>')
        return str(obj.valeur_reduction)
    valeur_affichage.short_description = "Réduction"
 
    def statut_badge(self, obj):
        c = {'active': '#00C896', 'brouillon': '#6B7399',
             'expiree': '#FF4F5E', 'en_pause': '#F5A623'}.get(obj.statut, '#999')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:10px;font-size:11px">{}</span>',
            c, obj.get_statut_display()
        )
    statut_badge.short_description = "Statut"
    statut_badge.admin_order_field = 'statut'
 
    def nb_produits_cibles(self, obj):
        return obj.produits.count()
    nb_produits_cibles.short_description = "Produits ciblés"
 
    @admin.action(description="▶️ Activer les promotions")
    def activer_promotions(self, request, queryset):
        n = queryset.update(statut='active')
        self.message_user(request, f"{n} promotion(s) activée(s).", messages.SUCCESS)
 
    @admin.action(description="⏸️ Mettre en pause")
    def mettre_en_pause(self, request, queryset):
        n = queryset.update(statut='en_pause')
        self.message_user(request, f"{n} promotion(s) mise(s) en pause.", messages.WARNING)


# ===========================================================================
# NOTIFICATIONS
# ===========================================================================
 
@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display    = (
        'utilisateur', 'type_badge', 'titre',
        'canal', 'est_lu', 'date_creation',
    )
    list_filter     = ('type_notification', 'canal', 'est_lu',
                       ('date_creation', admin.DateFieldListFilter))
    search_fields   = ('titre', 'message', 'utilisateur__username')
    raw_id_fields   = ('utilisateur',)
    readonly_fields = ('date_creation',)
    list_editable   = ('est_lu',)
    ordering        = ('-date_creation',)
    date_hierarchy  = 'date_creation'
    list_per_page   = 50
    show_full_result_count = False
 
    # ⚠️ MYSQL : donnees_extra est un JSONField → ne pas l'inclure dans list_display
    # ni dans search_fields → provoque des erreurs de syntaxe SQL sur MySQL < 8
    fields = (
        'utilisateur', 'type_notification', 'titre', 'message',
        'lien', 'canal', 'est_lu',
        'date_creation',
        # 'donnees_extra',  # ← décommentez seulement si MySQL >= 8.0.17
    )
 
    def type_badge(self, obj):
        c = {
            'commande':     '#F5A623',
            'paiement':     '#00C896',
            'enchere':      '#FF4F5E',
            'promotion':    '#7C6FFF',
            'live':         '#FF4F5E',
            'gamification': '#FFD700',
            'livraison':    '#00C896',
            'systeme':      '#6B7399',
            'social':       '#FF8C00',
            'alerte_stock': '#FF4F5E',
        }.get(obj.type_notification, '#999')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 7px;'
            'border-radius:10px;font-size:11px">{}</span>',
            c, obj.get_type_notification_display()
        )
    type_badge.short_description = "Type"
    type_badge.admin_order_field = 'type_notification'
 
    @admin.action(description="✅ Marquer comme lues")
    def marquer_lues(self, request, queryset):
        n = queryset.update(est_lu=True)
        self.message_user(request, f"{n} notification(s) marquée(s) comme lues.", messages.SUCCESS)
 
    actions = ['marquer_lues']
 
 
 