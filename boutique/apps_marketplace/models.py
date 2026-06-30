# ===========================================================================
# app_marketplace/models.py
# Application : Marketplace Multi-vendeurs
#
# ADAPTATIONS vendeur sans boutique :
#   - Boutique.logo           → null=True, blank=True
#   - Boutique.type_boutique  → 'individuelle' | 'pro' | 'yopishop'
#   - Boutique.est_auto_creee → True si créée automatiquement
#   - AvisBoutique remplacé par AvisVendeur (boutique nullable)
#   - ArticleCommande.save()  → commission calculée même sans boutique
#   - GroupeAchat             → achat groupé Pinduoduo style
# ===========================================================================
 
from django.db import models
from django.core.validators import (MinValueValidator, MaxValueValidator,FileExtensionValidator)
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError
import uuid


# =============================================================================
# SECTION 1 : BOUTIQUES VENDEURS
# =============================================================================
 
class Boutique(models.Model):
    """
    Mini-site vendeur avec sous-domaine personnalisé.
    Ex : mode.yopishop.com, electronique.yopishop.com
 
    ADAPTATION :
      - logo nullable (vendeurs individuels n'ont pas forcément de logo)
      - type_boutique : individuelle | pro | yopishop
      - est_auto_creee : True si créée par signal Django (vendeur individuel)
    """
 
    STATUT_CHOICES = [
        ('en_attente', 'En attente de validation'),
        ('active',     'Active'),
        ('suspendue',  'Suspendue'),
        ('fermee',     'Fermée'),
    ]
    PLAN_CHOICES = [
        ('gratuit',    '🆓 Gratuit'),
        ('starter',    '🚀 Starter'),
        ('pro',        '💼 Pro'),
        ('enterprise', '🏢 Enterprise'),
    ]
    TYPE_BOUTIQUE_CHOICES = [
        ('individuelle', 'Individuelle (auto-créée)'),
        ('pro',          'Professionnelle'),
        ('yopishop',     'YopiShop Officiel'),
    ]
 
    id       = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendeur  = models.OneToOneField('apps_core.Utilisateur',
                                     on_delete=models.CASCADE,
                                     related_name='boutique')
 
    # ── Type et statut ────────────────────────────────────────────────────────
    type_boutique  = models.CharField(max_length=15, choices=TYPE_BOUTIQUE_CHOICES,
                                       default='pro',
                                       verbose_name="Type de boutique")
    est_auto_creee = models.BooleanField(
        default=False,
        verbose_name="Boutique auto-créée",
        help_text="True si créée automatiquement lors de la 1ère mise en vente"
    )
 
    # ── Identité ─────────────────────────────────────────────────────────────
    nom          = models.CharField(max_length=200, unique=True)
    slug         = models.SlugField(max_length=200, unique=True)
    sous_domaine = models.CharField(max_length=100, unique=True,
                                     help_text="Ex: mode → mode.yopishop.com")
    description  = models.TextField()
 
    # ── Visuels (logo nullable pour vendeurs individuels) ─────────────────────
    logo             = models.ImageField(
        upload_to='boutiques/logos/',
        null=True,           # ← ADAPTATION : nullable
        blank=True,
        verbose_name="Logo (optionnel)"
    )
    banniere         = models.ImageField(upload_to='boutiques/bannieres/',
                                          null=True, blank=True)
    couleur_primaire   = models.CharField(max_length=7, default='#FF6B00')
    couleur_secondaire = models.CharField(max_length=7, default='#1A1A2E')
 
    # ── Contact ───────────────────────────────────────────────────────────────
    email     = models.EmailField()
    telephone = models.CharField(max_length=20, blank=True)
    adresse   = models.TextField(blank=True)
    ville     = models.CharField(max_length=100, blank=True)
    pays      = models.CharField(max_length=100, default='Cameroun')
 
    # ── Réseaux sociaux ───────────────────────────────────────────────────────
    site_web  = models.URLField(blank=True, null=True)
    facebook  = models.CharField(max_length=200, blank=True, null=True)
    instagram = models.CharField(max_length=200, blank=True, null=True)
    tiktok    = models.CharField(max_length=200, blank=True, null=True)
    whatsapp  = models.CharField(max_length=20,  blank=True, null=True)
 
    # ── Paramètres commerciaux ───────────────────────────────────────────────
    delai_traitement  = models.PositiveIntegerField(default=2, help_text="Jours ouvrés")
    politique_retour  = models.TextField(blank=True)
    conditions_vente  = models.TextField(blank=True)
    taux_commission   = models.DecimalField(
        max_digits=5, decimal_places=2, default=10,
        help_text="% prélevé par YopiShop sur chaque vente"
    )
 
    # ── Plan / abonnement ────────────────────────────────────────────────────
    plan          = models.CharField(max_length=20, choices=PLAN_CHOICES, default='gratuit')
    date_fin_plan = models.DateTimeField(null=True, blank=True)
 
    # ── KYC ───────────────────────────────────────────────────────────────────
    numero_registre_commerce = models.CharField(max_length=100, blank=True, null=True)
    numero_tva               = models.CharField(max_length=50,  blank=True, null=True)
    kyc_statut               = models.CharField(
        max_length=20, default='non_soumis',
        choices=[
            ('non_soumis', 'Non soumis'),
            ('en_attente', 'En cours de vérification'),
            ('valide',     'KYC Validé ✅'),
            ('refuse',     'KYC Refusé ❌'),
        ]
    )
    kyc_valide_par = models.ForeignKey('apps_core.Utilisateur', null=True, blank=True,
                                        on_delete=models.SET_NULL,
                                        related_name='boutiques_kyc_validees')
    kyc_date       = models.DateTimeField(null=True, blank=True)
 
    # ── Statistiques ─────────────────────────────────────────────────────────
    note_moyenne     = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    nombre_avis      = models.PositiveIntegerField(default=0)
    nombre_ventes    = models.PositiveIntegerField(default=0)
    chiffre_affaires = models.DecimalField(max_digits=14, decimal_places=2, default=0)
 
    # ── Statut ────────────────────────────────────────────────────────────────
    statut           = models.CharField(max_length=20, choices=STATUT_CHOICES,
                                         default='en_attente')
    est_verifiee     = models.BooleanField(default=False)
    est_vedette      = models.BooleanField(default=False)
 
    # ── YopiFulfillment ───────────────────────────────────────────────────────
    utilise_fulfillment = models.BooleanField(default=False)
 
    date_creation     = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
 
    class Meta:
        verbose_name = "Boutique"
        ordering     = ['-date_creation']
        db_table     = 'marketplace_boutique'
 
    def __str__(self):
        return self.nom
 
    def peut_vendre(self):
        return self.statut == 'active' and self.vendeur.is_active
 
    def est_individuelle(self):
        return self.type_boutique == 'individuelle'
 
    def url_mini_site(self):
        return f"https://{self.sous_domaine}.yopishop.com"
 
    def recalculer_stats(self):
        avis = self.avis_vendeur.filter(est_approuve=True)
        if avis.exists():
            from django.db.models import Avg
            self.note_moyenne = round(avis.aggregate(Avg('note'))['note__avg'], 2)
            self.nombre_avis  = avis.count()
            self.save(update_fields=['note_moyenne', 'nombre_avis'])
 
 
# =============================================================================
class DocumentKYC(models.Model):
    """Documents de vérification d'identité KYC."""
 
    TYPE_CHOICES = [
        ('cni',                  "Carte nationale d'identité"),
        ('passeport',            'Passeport'),
        ('registre_commerce',    'Registre de commerce'),
        ('justificatif_domicile','Justificatif de domicile'),
        ('rib',                  'RIB / Relevé bancaire'),
        ('autre',                'Autre'),
    ]
    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('valide',     'Validé'),
        ('refuse',     'Refusé'),
    ]
 
    boutique        = models.ForeignKey(Boutique, on_delete=models.CASCADE,
                                         related_name='documents_kyc')
    type_document   = models.CharField(max_length=30, choices=TYPE_CHOICES)
    fichier         = models.FileField(upload_to='kyc/%Y/%m/')
    description     = models.CharField(max_length=200, blank=True)
    statut          = models.CharField(max_length=20, choices=STATUT_CHOICES,
                                        default='en_attente')
    commentaire_admin   = models.TextField(blank=True)
    date_envoi          = models.DateTimeField(auto_now_add=True)
    date_verification   = models.DateTimeField(null=True, blank=True)
 
    class Meta:
        verbose_name = "Document KYC"
        db_table     = 'marketplace_document_kyc'
 
    def __str__(self):
        return f"{self.get_type_document_display()} — {self.boutique.nom}"


# =============================================================================
class EmployeBoutique(models.Model):
    """Collaborateurs d'une boutique professionnelle."""
 
    ROLE_CHOICES = [
        ('gestionnaire', 'Gestionnaire (accès complet)'),
        ('vendeur',      'Vendeur (produits + commandes)'),
        ('livreur',      'Livreur'),
        ('comptable',    'Comptable (finances)'),
        ('support',      'Support client'),
    ]
 
    boutique      = models.ForeignKey(Boutique, on_delete=models.CASCADE,
                                       related_name='employes')
    utilisateur   = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                       related_name='emplois_boutique')
    role          = models.CharField(max_length=20, choices=ROLE_CHOICES)
    est_actif     = models.BooleanField(default=True)
    permissions   = models.JSONField(default=dict, blank=True)
    date_embauche = models.DateTimeField(auto_now_add=True)
    date_fin      = models.DateTimeField(null=True, blank=True)
 
    class Meta:
        verbose_name    = "Employé boutique"
        unique_together = ['boutique', 'utilisateur']
        db_table        = 'marketplace_employe_boutique'
 
    def __str__(self):
        return (f"{self.utilisateur.username} — {self.boutique.nom} "
                f"({self.get_role_display()})")
 
 
# =============================================================================
class DemandeVendeur(models.Model):
    """Candidature pour devenir vendeur pro."""
 
    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('en_cours',   'En cours de traitement'),
        ('approuvee',  'Approuvée'),
        ('refusee',    'Refusée'),
    ]
 
    utilisateur          = models.OneToOneField('apps_core.Utilisateur',
                                                 on_delete=models.CASCADE,
                                                 related_name='demande_vendeur')
    motivation           = models.TextField()
    experience_commerce  = models.TextField()
    types_produits       = models.TextField()
    volume_estime        = models.CharField(max_length=20, choices=[
                               ('1-10',  '1–10 produits'),
                               ('11-50', '11–50 produits'),
                               ('51-100','51–100 produits'),
                               ('100+',  '+100 produits'),
                           ])
    a_entreprise         = models.BooleanField(default=False)
    nom_entreprise       = models.CharField(max_length=200, blank=True)
    statut               = models.CharField(max_length=20, choices=STATUT_CHOICES,
                                             default='en_attente')
    commentaire_admin    = models.TextField(blank=True)
    traite_par           = models.ForeignKey('apps_core.Utilisateur', null=True, blank=True,
                                              on_delete=models.SET_NULL,
                                              related_name='demandes_traitees')
    date_demande         = models.DateTimeField(auto_now_add=True)
    date_traitement      = models.DateTimeField(null=True, blank=True)
 
    class Meta:
        verbose_name = "Demande vendeur"
        ordering     = ['-date_demande']
        db_table     = 'marketplace_demande_vendeur'
 
    def __str__(self):
        return f"Demande de {self.utilisateur.username}"
 
    def approuver(self, admin_user):
        self.statut         = 'approuvee'
        self.date_traitement = timezone.now()
        self.traite_par     = admin_user
        self.save()
        # Passer le vendeur en mode 'pro'
        self.utilisateur.type_vendeur = 'pro'
        self.utilisateur.save(update_fields=['type_vendeur'])
        profil = self.utilisateur.profil
        profil.est_vendeur = True
        profil.save()
 
    def refuser(self, admin_user, commentaire):
        self.statut           = 'refusee'
        self.commentaire_admin = commentaire
        self.date_traitement  = timezone.now()
        self.traite_par       = admin_user
        self.save()
 


# =============================================================================
class AvisVendeur(models.Model):
    """
    Avis client sur un vendeur — fonctionne avec OU sans boutique.
 
    ADAPTATION : remplace AvisBoutique.
      - vendeur   : toujours rempli (vendeur individuel ou pro)
      - boutique  : nullable (NULL pour vendeurs individuels)
    """
 
    vendeur     = models.ForeignKey('apps_core.Utilisateur',
                                     on_delete=models.CASCADE,
                                     related_name='avis_recus',
                                     verbose_name="Vendeur")
    boutique    = models.ForeignKey(Boutique,
                    on_delete=models.CASCADE,
                    null=True,      # ← ADAPTATION
                    blank=True,
                    related_name='avis_vendeur',
                    verbose_name="Boutique (optionnel)")
    utilisateur = models.ForeignKey('apps_core.Utilisateur',
                                     on_delete=models.CASCADE,
                                     related_name='avis_donnes')
    commande    = models.ForeignKey('Commande', on_delete=models.CASCADE)
 
    note               = models.PositiveIntegerField(
                             validators=[MinValueValidator(1), MaxValueValidator(5)])
    commentaire        = models.TextField()
    note_communication = models.PositiveIntegerField(
                             default=5, validators=[MinValueValidator(1), MaxValueValidator(5)])
    note_expedition    = models.PositiveIntegerField(
                             default=5, validators=[MinValueValidator(1), MaxValueValidator(5)])
    note_emballage     = models.PositiveIntegerField(
                             default=5, validators=[MinValueValidator(1), MaxValueValidator(5)])
    est_approuve       = models.BooleanField(default=True)
    reponse_vendeur    = models.TextField(blank=True)
    date_creation      = models.DateTimeField(auto_now_add=True)
    date_modification  = models.DateTimeField(auto_now=True)
 
    class Meta:
        verbose_name    = "Avis vendeur"
        unique_together = ['vendeur', 'utilisateur', 'commande']
        db_table        = 'marketplace_avis_vendeur'
 
    def __str__(self):
        return f"{self.utilisateur.username} → {self.vendeur.username} : {self.note}★"
 
    def save(self, *args, **kwargs):
        # Auto-lier la boutique si le vendeur en a une et qu'elle n'est pas renseignée
        if not self.boutique_id and self.vendeur.a_boutique:
            self.boutique = self.vendeur.boutique
        super().save(*args, **kwargs)


# =============================================================================
# SECTION 2 : PANIER ET COMMANDES
# =============================================================================
 
class Panier(models.Model):
    utilisateur       = models.ForeignKey('apps_core.Utilisateur',
                            on_delete=models.CASCADE,
                            related_name='paniers',
                            null=True, blank=True)
    cle_session       = models.CharField(max_length=255, null=True, blank=True)
    date_creation     = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
 
    class Meta:
        db_table = 'marketplace_panier'
 
    def __str__(self):
        if self.utilisateur:
            return f"Panier de {self.utilisateur.username}"
        return f"Panier anonyme ({self.cle_session})"
 
    def total(self):
        return sum(a.sous_total() for a in self.articles.all())
 
 
# =============================================================================
class ArticlePanier(models.Model):
    TYPE_PRIX_CHOICES = [
        ('normal', 'Prix normal'),
        ('promo',  'Promotion'),
        ('live',   'Prix live'),
        ('groupe', 'Achat groupé'),
    ]
 
    panier       = models.ForeignKey(Panier, related_name='articles',
                    on_delete=models.CASCADE)
    produit      = models.ForeignKey('apps_core.Produit', on_delete=models.CASCADE)
    variante     = models.ForeignKey('apps_core.VarianteProduit', null=True, blank=True,
                    on_delete=models.SET_NULL)
    quantite     = models.PositiveIntegerField(default=1)
    prix         = models.DecimalField(max_digits=12, decimal_places=2)
    prix_type    = models.CharField(max_length=10, choices=TYPE_PRIX_CHOICES, default='normal')
    produit_live = models.ForeignKey('apps_social.ProduitLive', null=True, blank=True,
                    on_delete=models.SET_NULL)
    groupe_achat = models.ForeignKey('GroupeAchat', null=True, blank=True,
                    on_delete=models.SET_NULL)
    date_creation = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        unique_together = ['panier', 'produit', 'variante']
        db_table        = 'marketplace_article_panier'
 
    def __str__(self):
        return f"{self.produit.titre} x{self.quantite}"
 
    def sous_total(self):
        return self.quantite * self.prix
 
    def economie_unitaire(self):
        prix_normal = self.produit.prix
        return prix_normal - self.prix if self.prix < prix_normal else Decimal(0)
 
    def economie_totale(self):
        return self.economie_unitaire() * self.quantite
 
 
# =============================================================================
class Commande(models.Model):
    STATUT_CHOICES = [
        ('en_attente',    'En attente'),
        ('confirmee',     'Confirmée'),
        ('en_traitement', 'En traitement'),
        ('expediee',      'Expédiée'),
        ('livree',        'Livrée'),
        ('annulee',       'Annulée'),
        ('remboursee',    'Remboursée'),
    ]
    STATUT_PAIEMENT_CHOICES = [
        ('en_attente',               'En attente'),
        ('payee',                    'Payée'),
        ('echec',                    'Échec'),
        ('a_livraison',              'Paiement à la livraison'),
        ('remboursee',               'Remboursée'),
        ('partiellement_remboursee', 'Partiellement remboursée'),
        ('en_verification',          'En vérification'),
    ]
    SOURCE_CHOICES = [
        ('web',     'Site web'),
        ('mobile',  'Application mobile'),
        ('live',    'Live Shopping'),
        ('enchere', 'Enchère'),
        ('groupe',  'Achat groupé'),
        ('b2b',     'B2B'),
        ('pos',     'Point de vente physique'),
    ]
 
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    numero_commande = models.CharField(max_length=50, unique=True)
    utilisateur     = models.ForeignKey('apps_core.Utilisateur',
                        on_delete=models.CASCADE,
                        related_name='commandes')
    boutique        = models.ForeignKey(Boutique, null=True, blank=True,
                        on_delete=models.SET_NULL,
                        related_name='commandes',
                        help_text="Boutique principale (null si vendeur individuel)")
    source          = models.CharField(max_length=15, choices=SOURCE_CHOICES, default='web')
 
    # Adresses
    adresse_facturation = models.TextField()
    adresse_livraison   = models.TextField()
    ville_livraison     = models.ForeignKey('apps_core.Ville', null=True, blank=True,
                            on_delete=models.PROTECT,
                            related_name='commandes')
    quartier_livraison  = models.ForeignKey('apps_core.Quartier', null=True, blank=True,
                            on_delete=models.SET_NULL)
 
    # Montants
    sous_total        = models.DecimalField(max_digits=12, decimal_places=2)
    montant_taxe      = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    frais_livraison   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    montant_reduction = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    montant_total     = models.DecimalField(max_digits=12, decimal_places=2)
    devise            = models.CharField(max_length=10, default='XAF')
 
    # Promotions
    promotions_appliquees = models.ManyToManyField('apps_core.Promotion', blank=True)
    code_promo            = models.ForeignKey('CodePromo', null=True, blank=True,
                               on_delete=models.SET_NULL,
                               related_name='commandes')
    livraison_gratuite    = models.BooleanField(default=False)
 
    # Statuts
    statut          = models.CharField(max_length=20, choices=STATUT_CHOICES,
                        default='en_attente')
    statut_paiement = models.CharField(max_length=25, choices=STATUT_PAIEMENT_CHOICES,
                        default='en_attente')
 
    # Paiement fractionné
    est_paiement_fractionne = models.BooleanField(default=False)
    nombre_tranches         = models.PositiveIntegerField(default=1)
 
    # Dates
    date_creation     = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    date_expedition   = models.DateTimeField(null=True, blank=True)
    date_livraison    = models.DateTimeField(null=True, blank=True)
 
    notes                  = models.TextField(blank=True)
    instructions_livraison = models.TextField(blank=True)
 
    class Meta:
        verbose_name = "Commande"
        ordering     = ['-date_creation']
        db_table     = 'marketplace_commande'
 
    def __str__(self):
        return f"Commande {self.numero_commande}"
 
    def save(self, *args, **kwargs):
        if not self.numero_commande:
            import random, string
            prefix = self.source[:3].upper()
            suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            self.numero_commande = f"YPI-{prefix}-{suffix}"
        super().save(*args, **kwargs)
 
    def calculer_total(self):
        self.sous_total   = sum(a.prix_total for a in self.articles.all())
        self.montant_total = self.sous_total + self.frais_livraison - self.montant_reduction
        self.save(update_fields=['sous_total', 'montant_total'])
        return self.montant_total
    
    @property
    def est_commande_yopishop(self):
        return not self.articles.exclude(
            produit__est_produit_yopishop=True
        ).exists()
 
 
# =============================================================================
class ArticleCommande(models.Model):
    """
    Article d'une commande.
 
    ADAPTATION : commission calculée même si boutique=None.
    Logique centralisée dans save() selon type_vendeur.
    """
 
    commande      = models.ForeignKey(Commande, related_name='articles',
                       on_delete=models.CASCADE)
    produit       = models.ForeignKey('apps_core.Produit', on_delete=models.CASCADE)
    variante      = models.ForeignKey('apps_core.VarianteProduit', null=True, blank=True,
                       on_delete=models.SET_NULL)
    quantite      = models.PositiveIntegerField()
    prix_unitaire = models.DecimalField(max_digits=12, decimal_places=2)
    prix_total    = models.DecimalField(max_digits=12, decimal_places=2)
 
    enchere       = models.ForeignKey('apps_encheres.Enchere', null=True, blank=True,
                       on_delete=models.SET_NULL)
    boutique      = models.ForeignKey(Boutique, null=True, blank=True,
                       on_delete=models.SET_NULL,
                       help_text="Null si vendeur individuel")
    wallet_credite = models.BooleanField(
        default=False,
        verbose_name="Wallet vendeur crédité",
        help_text="True quand les fonds ont été versés au(x) vendeur(s)"
    )
 
    # Commission calculée automatiquement (ADAPTATION)
    commission_boutique = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name="Commission YopiShop",
        help_text="Calculée selon type_vendeur si boutique absente"
    )
    taux_commission_applique = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        verbose_name="Taux appliqué (%)"
    )
 
    class Meta:
        verbose_name = "Article de commande"
        db_table     = 'marketplace_article_commande'
 
    def __str__(self):
        return f"{self.produit.titre} x{self.quantite}"
 
    def save(self, *args, **kwargs):
        self.prix_total = self.prix_unitaire * self.quantite
 
        # ── Commission centralisée (ADAPTATION) ──────────────────────────────
        vendeur = self.produit.vendeur
 
        if self.boutique:
            # Vendeur pro avec boutique → taux de la boutique
            taux = self.boutique.taux_commission
        elif vendeur.type_vendeur == 'individuel':
            # Vendeur individuel sans boutique → taux fixe 15%
            taux = Decimal('15')
        elif vendeur.type_vendeur == 'yopishop':
            # YopiShop ne se prélève pas de commission sur ses propres ventes
            taux = Decimal('0')
        else:
            # Fallback
            taux = Decimal('10')
 
        self.taux_commission_applique = taux
        self.commission_boutique = (
            self.prix_total * taux / Decimal(100)
        ).quantize(Decimal('0.01'))
 
        # Auto-lier la boutique si disponible et non encore renseignée
        if not self.boutique_id and vendeur.a_boutique:
            self.boutique = vendeur.boutique
 
        super().save(*args, **kwargs)
 

# =============================================================================
# SECTION 3 : CODES PROMO
# =============================================================================
 
class CodePromo(models.Model):
    TYPE_REDUCTION_CHOICES = [
        ('pourcentage',        'Pourcentage'),
        ('montant_fixe',       'Montant fixe'),
        ('livraison_gratuite', 'Livraison gratuite'),
    ]
    STATUT_CHOICES = [
        ('actif',   'Actif'),
        ('inactif', 'Inactif'),
        ('expire',  'Expiré'),
        ('epuise',  'Épuisé'),
    ]
    TYPE_CIBLE_CHOICES = [
        ('public',        'Tous les utilisateurs'),
        ('prive',         'Utilisateurs spécifiques'),
        ('premier_achat', 'Premier achat'),
        ('vip',           'Clients VIP'),
    ]
 
    id                         = models.UUIDField(primary_key=True, default=uuid.uuid4,
                                   editable=False)
    code                       = models.CharField(max_length=50, unique=True)
    nom                        = models.CharField(max_length=200)
    description                = models.TextField(blank=True)
    type_reduction             = models.CharField(max_length=20, choices=TYPE_REDUCTION_CHOICES)
    valeur_reduction           = models.DecimalField(max_digits=10, decimal_places=2)
    montant_max_reduction      = models.DecimalField(max_digits=10, decimal_places=2,
                                  null=True, blank=True)
    montant_min_commande       = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    type_cible                 = models.CharField(max_length=20, choices=TYPE_CIBLE_CHOICES,
                                   default='public')
    utilisateurs_cibles        = models.ManyToManyField('apps_core.Utilisateur', blank=True,
                                    related_name='codes_promo_disponibles')
    categories_ciblees         = models.ManyToManyField('apps_core.Categorie', blank=True)
    produits_cibles            = models.ManyToManyField('apps_core.Produit', blank=True)
    limite_utilisation_globale = models.PositiveIntegerField(null=True, blank=True)
    limite_par_utilisateur     = models.PositiveIntegerField(default=1)
    nombre_utilisations        = models.PositiveIntegerField(default=0)
    date_debut                 = models.DateTimeField()
    date_fin                   = models.DateTimeField()
    statut                     = models.CharField(max_length=20, choices=STATUT_CHOICES,
                                   default='actif')
    cumulable                  = models.BooleanField(default=False)
    createur                   = models.ForeignKey('apps_core.Utilisateur',
                                    on_delete=models.SET_NULL, null=True,
                                    related_name='codes_promo_crees')
    date_creation              = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        verbose_name = "Code promo"
        ordering     = ['-date_creation']
        db_table     = 'marketplace_code_promo'
 
    def __str__(self):
        return f"{self.code} — {self.nom}"
 
    def est_valide(self):
        return (self.statut == 'actif'
                and self.date_debut <= timezone.now() <= self.date_fin)
 
    def calculer_reduction(self, montant):
        if montant < self.montant_min_commande:
            return Decimal(0)
        if self.type_reduction == 'pourcentage':
            r = (self.valeur_reduction / Decimal(100)) * montant
        elif self.type_reduction == 'montant_fixe':
            r = self.valeur_reduction
        else:
            return Decimal(0)
        if self.montant_max_reduction:
            r = min(r, self.montant_max_reduction)
        return min(r, montant).quantize(Decimal('0.01'))


# =============================================================================
# SECTION 4 : PAIEMENTS
# =============================================================================
 
class Operateur(models.Model):
    nom       = models.CharField(max_length=100)
    logo      = models.ImageField(upload_to='operateurs/', null=True, blank=True)
    code      = models.CharField(max_length=20, blank=True)
    est_actif = models.BooleanField(default=True)
 
    class Meta:
        db_table = 'marketplace_operateur'
 
    def __str__(self):
        return self.nom
 
 
class NumeroVersement(models.Model):
    pays         = models.ForeignKey('apps_core.Pays', on_delete=models.CASCADE,
                      related_name='numeros')
    operateur    = models.ForeignKey(Operateur, on_delete=models.CASCADE,
                                      related_name='numeros')
    numero       = models.CharField(max_length=50)
    nom_compte   = models.CharField(max_length=100, blank=True)
    description  = models.CharField(max_length=255, blank=True, null=True)
    est_actif    = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        db_table = 'marketplace_numero_versement'
 
    def __str__(self):
        return f"{self.numero} ({self.operateur.nom} — {self.pays.nom})"
 
 
class PlanPaiement(models.Model):
    """Paiement fractionné BNPL (Buy Now Pay Later)."""
 
    commande            = models.OneToOneField(Commande, on_delete=models.CASCADE,
                           related_name='plan_paiement')
    montant_total       = models.DecimalField(max_digits=12, decimal_places=2)
    nombre_tranches     = models.PositiveIntegerField(default=3)
    montant_par_tranche = models.DecimalField(max_digits=10, decimal_places=2)
    taux_interet        = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    est_active          = models.BooleanField(default=True)
    date_creation       = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        verbose_name = "Plan de paiement"
        db_table     = 'marketplace_plan_paiement'
 
    def __str__(self):
        return f"Plan {self.nombre_tranches}x — {self.commande.numero_commande}"
 
    def montant_paye(self):
        return sum(t.montant for t in self.tranches.filter(statut='payee'))
 
    def montant_restant(self):
        return self.montant_total - self.montant_paye()
 
    def est_complet(self):
        return self.montant_restant() <= 0

    @property
    def prochaine_tranche(self):
        return self.tranches.filter(
            statut__in=["en_attente", "en_retard"]
        ).order_by("numero_tranche").first()
 
 
class TranchePaiement(models.Model):
    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('payee',      'Payée'),
        ('en_retard',  'En retard'),
        ('annulee',    'Annulée'),
    ]
 
    plan_paiement  = models.ForeignKey(PlanPaiement, on_delete=models.CASCADE,
                                        related_name='tranches')
    numero_tranche = models.PositiveIntegerField()
    montant        = models.DecimalField(max_digits=10, decimal_places=2)
    date_echeance  = models.DateTimeField()
    date_paiement  = models.DateTimeField(null=True, blank=True)
    statut         = models.CharField(max_length=20, choices=STATUT_CHOICES,
                       default='en_attente')
    paiement       = models.ForeignKey('Paiement', null=True, blank=True,
                        on_delete=models.SET_NULL, related_name='tranche')
    date_creation  = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        ordering = ['numero_tranche']
        db_table = 'marketplace_tranche_paiement'
 
    def __str__(self):
        return f"Tranche {self.numero_tranche}/{self.plan_paiement.nombre_tranches}"
 
    def est_en_retard(self):
        return self.statut != 'payee' and timezone.now() > self.date_echeance
 
 
class Paiement(models.Model):
    METHODE_CHOICES = [
        ('orange_money',   'Orange Money'),
        ('mtn_momo',       'MTN MoMo'),
        ('wave',           'Wave'),
        ('carte_bancaire', 'Carte bancaire'),
        ('paypal',         'PayPal'),
        ('wallet_yopi',    'YopiPay Wallet'),
        ('livraison',      'Paiement à la livraison'),
        ('virement',       'Virement bancaire'),
    ]
    STATUT_CHOICES = [
        ('en_attente',      'En attente'),
        ('en_verification', 'En vérification'),
        ('complete',        'Complété'),
        ('echec',           'Échec'),
        ('annule',          'Annulé'),
        ('rembourse',       'Remboursé'),
        ('rejete',          'Rejeté'),
    ]
 
    commande           = models.ForeignKey(Commande, related_name='paiements',
                           on_delete=models.CASCADE)
    methode            = models.CharField(max_length=25, choices=METHODE_CHOICES)
    montant            = models.DecimalField(max_digits=12, decimal_places=2)
    statut             = models.CharField(max_length=20, choices=STATUT_CHOICES,
                           default='en_attente')
    tranche_paiement   = models.ForeignKey(TranchePaiement, null=True, blank=True,
                            on_delete=models.SET_NULL,
                            related_name='paiements')
    reference_paiement = models.CharField(max_length=200, blank=True, null=True)
 
    # Preuve manuelle
    preuve_paiement    = models.ImageField(
        upload_to='preuves_paiement/%Y/%m/',
        blank=True, null=True,
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'pdf'])]
    )
    numero_expediteur  = models.CharField(max_length=20, blank=True, null=True)
    message_client     = models.TextField(blank=True, null=True)
 
    # Validation admin
    valide_par         = models.ForeignKey('apps_core.Utilisateur',
                            on_delete=models.SET_NULL,
                            null=True, blank=True,
                            related_name='paiements_valides')
    date_validation    = models.DateTimeField(null=True, blank=True)
    commentaire_admin  = models.TextField(blank=True, null=True)
    motif_rejet        = models.TextField(blank=True, null=True)
 
    # IA Anti-fraude
    score_fraude  = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                         help_text="0=sûr, 100=très suspect")
    est_suspect   = models.BooleanField(default=False)
    flags_fraude  = models.JSONField(default=list, blank=True)
 
    id_transaction      = models.CharField(max_length=255, blank=True)
    reponse_passerelle  = models.JSONField(default=dict)
    date_creation       = models.DateTimeField(auto_now_add=True)
    date_completion     = models.DateTimeField(null=True, blank=True)
 
    class Meta:
        ordering = ['-date_creation']
        db_table = 'marketplace_paiement'
 
    def __str__(self):
        return f"Paiement {self.montant} XAF — {self.get_methode_display()}"
 
    def peut_etre_valide(self):
        return self.statut in ['en_attente', 'en_verification']
 
    def valider(self, admin_user, commentaire=''):
        if not self.peut_etre_valide():
            return False
        self.statut          = 'complete'
        self.valide_par      = admin_user
        self.date_validation = timezone.now()
        self.commentaire_admin = commentaire
        self.date_completion = timezone.now()
        self.save()
        if self.tranche_paiement:
            self.tranche_paiement.statut        = 'payee'
            self.tranche_paiement.date_paiement = timezone.now()
            self.tranche_paiement.save()
            if self.tranche_paiement.plan_paiement.est_complet():
                self.commande.statut_paiement = 'payee'
                self.commande.statut          = 'confirmee'
                self.commande.save()
        return True
 
    def rejeter(self, admin_user, motif):
        if not self.peut_etre_valide():
            return False
        self.statut          = 'rejete'
        self.valide_par      = admin_user
        self.date_validation = timezone.now()
        self.motif_rejet     = motif
        self.save()
        return True
 


# =============================================================================
# SECTION 5 : LIVRAISON
# =============================================================================
 
class MethodeLivraison(models.Model):
    TYPE_CHOICES = [
        ('standard',     'Standard'),
        ('express',      'Express'),
        ('jour_meme',    'Jour même'),
        ('programmee',   'Programmée'),
        ('point_relais', 'Point relais'),
    ]
 
    nom            = models.CharField(max_length=100)
    description    = models.TextField()
    type_livraison = models.CharField(max_length=15, choices=TYPE_CHOICES, default='standard')
    prix           = models.DecimalField(max_digits=8, decimal_places=2)
    delai_min      = models.PositiveIntegerField(help_text="Jours")
    delai_max      = models.PositiveIntegerField(help_text="Jours")
    est_active     = models.BooleanField(default=True)
 
    class Meta:
        db_table = 'marketplace_methode_livraison'
 
    def __str__(self):
        return f"{self.nom} ({self.get_type_livraison_display()})"
 
 
class Livraison(models.Model):
    STATUT_CHOICES = [
        ('en_preparation',  'En préparation'),
        ('prise_en_charge', 'Prise en charge'),
        ('expediee',        'Expédiée'),
        ('en_transit',      'En transit'),
        ('en_livraison',    'En cours de livraison'),
        ('livree',          'Livrée'),
        ('echec',           'Échec livraison'),
        ('retournee',       'Retournée'),
    ]
 
    commande              = models.OneToOneField(Commande, on_delete=models.CASCADE,
                                  related_name='livraison')
    methode_livraison     = models.ForeignKey(MethodeLivraison, on_delete=models.CASCADE)
    livreur               = models.ForeignKey('apps_core.Utilisateur', null=True, blank=True,
                                on_delete=models.SET_NULL,
                                related_name='livraisons')
    numero_suivi          = models.CharField(max_length=100, blank=True)
    transporteur          = models.CharField(max_length=100, blank=True)
    statut                = models.CharField(max_length=20, choices=STATUT_CHOICES,
                                  default='en_preparation')
 
    # Géolocalisation temps réel
    livreur_latitude      = models.DecimalField(max_digits=9, decimal_places=6,
                                 null=True, blank=True)
    livreur_longitude     = models.DecimalField(max_digits=9, decimal_places=6,
                                null=True, blank=True)
    derniere_position_maj = models.DateTimeField(null=True, blank=True)
 
    # Estimation IA
    delai_estime_minutes  = models.PositiveIntegerField(null=True, blank=True)
    itineraire_url        = models.URLField(blank=True)
 
    # Dates
    date_expedition        = models.DateTimeField(null=True, blank=True)
    date_livraison_prevue  = models.DateTimeField(null=True, blank=True)
    date_livraison_reelle  = models.DateTimeField(null=True, blank=True)
 
    notes           = models.TextField(blank=True)
    signature_client = models.ImageField(upload_to='signatures/',      null=True, blank=True)
    photo_livraison  = models.ImageField(upload_to='photos_livraison/', null=True, blank=True)
 
    date_creation     = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
 
    class Meta:
        db_table = 'marketplace_livraison'
 
    def __str__(self):
        return f"Livraison — {self.commande.numero_commande}"
 
 
class HistoriqueLivraison(models.Model):
    """Traçabilité étape par étape."""
 
    livraison        = models.ForeignKey(Livraison, on_delete=models.CASCADE,
                            related_name='historique')
    statut           = models.CharField(max_length=30)
    description      = models.CharField(max_length=300)
    localisation     = models.CharField(max_length=200, blank=True)
    latitude         = models.DecimalField(max_digits=9, decimal_places=6,
                            null=True, blank=True)
    longitude        = models.DecimalField(max_digits=9, decimal_places=6,
                            null=True, blank=True)
    date_evenement   = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        ordering = ['-date_evenement']
        db_table = 'marketplace_historique_livraison'
 
    def __str__(self):
        return f"{self.statut} — {self.livraison.commande.numero_commande}"
 


# =============================================================================
# SECTION 6 : RETOURS
# =============================================================================
 
class Retour(models.Model):
    RAISON_CHOICES = [
        ('defectueux',      'Produit défectueux'),
        ('non_conforme',    'Non conforme à la description'),
        ('endommage',       'Endommagé pendant le transport'),
        ('erreur_commande', 'Erreur de commande'),
        ('plus_voulu',      'Ne veut plus du produit'),
        ('autre',           'Autre'),
    ]
    STATUT_CHOICES = [
        ('demande',  'Demande soumise'),
        ('approuve', 'Approuvé'),
        ('refuse',   'Refusé'),
        ('en_cours', 'En cours'),
        ('complete', 'Complété'),
    ]
 
    commande              = models.ForeignKey(Commande, on_delete=models.CASCADE,
                                related_name='retours')
    article_commande      = models.ForeignKey(ArticleCommande, on_delete=models.CASCADE)
    utilisateur           = models.ForeignKey('apps_core.Utilisateur',
                                on_delete=models.CASCADE)
    raison                = models.CharField(max_length=20, choices=RAISON_CHOICES)
    description           = models.TextField()
    quantite              = models.PositiveIntegerField()
    photos                = models.ManyToManyField('apps_core.ImageAvis', blank=True)
    statut                = models.CharField(max_length=20, choices=STATUT_CHOICES,
                                default='demande')
    montant_remboursement = models.DecimalField(max_digits=10, decimal_places=2,
                                null=True, blank=True)
    date_demande          = models.DateTimeField(auto_now_add=True)
    date_traitement       = models.DateTimeField(null=True, blank=True)
    notes_admin           = models.TextField(blank=True)
 
    class Meta:
        verbose_name = "Retour"
        db_table     = 'marketplace_retour'
 
    def __str__(self):
        return f"Retour {self.utilisateur.username} — {self.commande.numero_commande}"
 
 
# =============================================================================
# SECTION 7 : ACHAT GROUPÉ (Pinduoduo style)
# =============================================================================
 
class GroupeAchat(models.Model):
    """
    Achat groupé — le prix baisse quand le nombre minimum de participants est atteint.
    Inspiré de Pinduoduo (Chine).
    """
 
    STATUT_CHOICES = [
        ('ouvert',  'Ouvert — en attente de participants'),
        ('complet', 'Complet — conditions remplies'),
        ('expire',  'Expiré'),
        ('traite',  'Traité — commandes créées'),
    ]
 
    id                       = models.UUIDField(primary_key=True, default=uuid.uuid4,
                                                 editable=False)
    produit                  = models.ForeignKey('apps_core.Produit',
                                                  on_delete=models.CASCADE,
                                                  related_name='groupes_achat')
    createur                 = models.ForeignKey('apps_core.Utilisateur',
                                    on_delete=models.CASCADE,
                                    related_name='groupes_crees')
    prix_normal              = models.DecimalField(max_digits=12, decimal_places=2)
    prix_groupe              = models.DecimalField(max_digits=12, decimal_places=2)
    nb_participants_min      = models.PositiveIntegerField(default=5)
    nb_participants_max      = models.PositiveIntegerField(null=True, blank=True)
    quantite_par_participant = models.PositiveIntegerField(default=1)
    statut                   = models.CharField(max_length=15, choices=STATUT_CHOICES,
                                    default='ouvert')
    lien_partage             = models.CharField(max_length=200, blank=True)
    date_expiration          = models.DateTimeField()
    date_creation            = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        verbose_name = "Groupe d'achat"
        db_table     = 'marketplace_groupe_achat'
 
    def __str__(self):
        return (f"Groupe {self.produit.titre} — "
                f"{self.participants.count()}/{self.nb_participants_min}")
    @property
    def est_complet(self):
        return self.participants.filter(a_confirme=True).count() >= self.nb_participants_min

    @property
    def prix_actuel(self):
        return self.prix_groupe if self.est_complet else self.prix_normal

    @property
    def economie(self):
        return self.prix_normal - self.prix_groupe

    @property
    def pourcentage_reduction(self):
        if self.prix_normal > 0:
            return (self.economie / self.prix_normal * 100).quantize(Decimal('0.1'))
        return Decimal(0)
 
 
class ParticipantGroupeAchat(models.Model):
    groupe        = models.ForeignKey(GroupeAchat, on_delete=models.CASCADE,
                                       related_name='participants')
    utilisateur   = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE)
    quantite      = models.PositiveIntegerField(default=1)
    a_confirme    = models.BooleanField(default=False)
    commande      = models.ForeignKey(Commande, null=True, blank=True,
                                       on_delete=models.SET_NULL)
    date_adhesion = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        unique_together = ['groupe', 'utilisateur']
        db_table        = 'marketplace_participant_groupe_achat'
 
    def __str__(self):
        return f"{self.utilisateur.username} — Groupe {self.groupe.id}"
 