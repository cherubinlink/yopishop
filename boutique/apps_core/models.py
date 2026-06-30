# ===========================================================================
# apps_core/models.py
# Application socle — référencée par toutes les autres applications
# Contient : Utilisateurs, Géographie, Catalogue Produits, Promotions,
#            Avis, Favoris, Notifications
#
# ADAPTATIONS vendeur sans boutique :
#   - Utilisateur.type_vendeur → 'individuel' | 'pro' | 'yopishop'
#   - Utilisateur.a_boutique (property)
#   - Produit.est_produit_yopishop (badge officiel)
# ===========================================================================
 
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError
import uuid
from django.utils.text import slugify
from django.urls import reverse
from django.db.models import Sum, F, Avg
from datetime import timedelta, date


# =============================================================================
# SECTION 1 : GESTION UTILISATEURS
# =============================================================================
 
class Utilisateur(AbstractUser):
    """
    Utilisateur personnalisé — socle de toute la plateforme YopiShop.
    Supporte : acheteur, vendeur individuel, vendeur pro, livreur,
               influenceur, prestataire de services, admin.
 
    ADAPTATION : champ type_vendeur pour distinguer vendeur avec/sans boutique.
    """
 
    # ── Rôles généraux ───────────────────────────────────────────────────────
    ROLE_CHOICES = [
        ('acheteur',     'Acheteur'),
        ('vendeur',      'Vendeur'),
        ('livreur',      'Livreur'),
        ('influenceur',  'Influenceur'),
        ('prestataire',  'Prestataire de services'),
        ('admin',        'Administrateur'),
        ('super_admin',  'Super Administrateur'),
    ]
 
    # ── Type vendeur (NOUVEAU) ────────────────────────────────────────────────
    TYPE_VENDEUR_CHOICES = [
        ('aucun',       'Pas vendeur'),
        ('individuel',  'Vendeur individuel (sans boutique dédiée)'),
        ('pro',         'Vendeur pro (avec boutique complète)'),
        ('yopishop',    'YopiShop Officiel (plateforme)'),
    ]
 
    # Informations personnelles
    telephone           = models.CharField(max_length=20, blank=True, verbose_name="Téléphone")
    date_naissance      = models.DateField(null=True, blank=True, verbose_name="Date de naissance")
    avatar              = models.ImageField(upload_to='avatars/', null=True, blank=True,
                                             verbose_name="Avatar")
    bio                 = models.TextField(max_length=500, blank=True,
                            verbose_name="Biographie courte")
 
    # Localisation
    adresse     = models.TextField(blank=True, verbose_name="Adresse")
    ville       = models.ForeignKey('Ville', null=True, blank=True,
                    on_delete=models.SET_NULL,related_name='utilisateurs',verbose_name="Ville")
    code_postal = models.CharField(max_length=10, blank=True, verbose_name="Code postal")
    pays        = models.ForeignKey('Pays', null=True, blank=True,
                    on_delete=models.SET_NULL,related_name='utilisateurs',verbose_name="Pays")
 
    # Rôle et statut
    role            = models.CharField(max_length=20, choices=ROLE_CHOICES,
                        default='acheteur', verbose_name="Rôle")
    type_vendeur    = models.CharField(max_length=15, choices=TYPE_VENDEUR_CHOICES,
                        default='aucun', verbose_name="Type de vendeur")
    est_verifie     = models.BooleanField(default=False, verbose_name="Email vérifié")
    kyc_valide      = models.BooleanField(default=False, verbose_name="KYC validé")
 
    # Influenceur
    est_influenceur             = models.BooleanField(default=False,
        verbose_name="Est influenceur")
    taux_commission_influenceur = models.DecimalField(max_digits=5, decimal_places=2,
        default=5,verbose_name="Commission influenceur (%)")
 
    # YopiPay Wallet
    solde_wallet = models.DecimalField(max_digits=12, decimal_places=2, default=0,
        verbose_name="Solde YopiPay (XAF)")
 
    # Sous-domaine boutique (ex: mode → mode.yopishop.com)
    sous_domaine = models.CharField(max_length=100, blank=True, unique=True,
         null=True, verbose_name="Sous-domaine boutique")
 
    # Produit officiel YopiShop
    est_produit_yopishop = models.BooleanField(default=False,
        verbose_name="Compte YopiShop officiel")
 
    # Métadonnées
    date_creation           = models.DateTimeField(auto_now_add=True)
    date_modification       = models.DateTimeField(auto_now=True)
    derniere_connexion_ip   = models.GenericIPAddressField(null=True, blank=True)
 
    class Meta:
        verbose_name        = "Utilisateur"
        verbose_name_plural = "Utilisateurs"
        db_table            = 'core_utilisateur'
 
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
 
    # ── Properties ───────────────────────────────────────────────────────────
 
    @property
    def age(self):
        if not self.date_naissance:
            return None
        today = date.today()
        return today.year - self.date_naissance.year - (
            (today.month, today.day) < (self.date_naissance.month, self.date_naissance.day)
        )
 
    @property
    def nom_complet(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username
 
    @property
    def a_boutique(self):
        """True si l'utilisateur possède une boutique (créée ou auto-créée)."""
        try:
            return self.boutique is not None
        except Exception:
            return False
 
    @property
    def peut_vendre(self):
        """True si l'utilisateur peut publier des produits."""
        return self.type_vendeur in ('individuel', 'pro', 'yopishop')
 
    def profil_vendeur_display(self):
        """Retourne la boutique si elle existe, sinon l'utilisateur lui-même."""
        if self.a_boutique:
            return self.boutique
        return self
 
    def taux_commission_effectif(self):
        """Retourne le taux de commission applicable."""
        if self.type_vendeur == 'yopishop':
            return Decimal('0')
        if self.a_boutique:
            return self.boutique.taux_commission
        if self.type_vendeur == 'individuel':
            return Decimal('15')
        return Decimal('10')
 
    # ── Wallet ────────────────────────────────────────────────────────────────
 
    def crediter_wallet(self, montant, description=''):
        self.solde_wallet += Decimal(str(montant))
        self.save(update_fields=['solde_wallet'])
        TransactionWallet.objects.create(
            utilisateur=self, montant=montant,
            type_transaction='credit', description=description,
            solde_apres=self.solde_wallet,
        )
 
    def debiter_wallet(self, montant, description=''):
        montant = Decimal(str(montant))
        if self.solde_wallet < montant:
            raise ValidationError("Solde YopiPay insuffisant.")
        self.solde_wallet -= montant
        self.save(update_fields=['solde_wallet'])
        TransactionWallet.objects.create(
            utilisateur=self, montant=montant,
            type_transaction='debit', description=description,
            solde_apres=self.solde_wallet,
        )
 
 
# =============================================================================
class ProfilUtilisateur(models.Model):
    """Profil étendu — statistiques, gamification, préférences."""
 
    utilisateur     = models.OneToOneField(Utilisateur, on_delete=models.CASCADE,
                                            related_name='profil')
    note_moyenne    = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    est_vendeur     = models.BooleanField(default=False)
    vendeur_verifie = models.BooleanField(default=False)
 
    # Gamification
    points_total = models.PositiveIntegerField(default=0, verbose_name="Points totaux")
    niveau       = models.CharField(max_length=20, default='bronze',
                        choices=[
                            ('bronze',  '🥉 Bronze'),
                            ('argent',  '🥈 Argent'),
                            ('or',      '🥇 Or'),
                            ('platine', '💎 Platine'),
                            ('diamant', '💠 Diamant'),
                        ])
 
    # Préférences
    langue_preference   = models.CharField(max_length=10, default='fr')
    devise_preference   = models.CharField(max_length=10, default='XAF')
    notifications_email = models.BooleanField(default=True)
    notifications_sms   = models.BooleanField(default=True)
    notifications_push  = models.BooleanField(default=True)
 
    class Meta:
        verbose_name = "Profil utilisateur"
        db_table     = 'core_profil_utilisateur'
 
    def __str__(self):
        return f"Profil de {self.utilisateur.username}"
 
    def recalculer_niveau(self):
        p = self.points_total
        if p >= 50000:   self.niveau = 'diamant'
        elif p >= 20000: self.niveau = 'platine'
        elif p >= 5000:  self.niveau = 'or'
        elif p >= 1000:  self.niveau = 'argent'
        else:            self.niveau = 'bronze'
        self.save(update_fields=['niveau'])
 
 
# =============================================================================
class TransactionWallet(models.Model):
    """Historique des mouvements du wallet YopiPay."""
 
    TYPE_CHOICES = [
        ('credit',        'Crédit'),
        ('debit',         'Débit'),
        ('remboursement', 'Remboursement'),
        ('commission',    'Commission plateforme'),
        ('bonus',         'Bonus / Récompense'),
        ('retrait',       'Retrait vers mobile money'),
    ]
 
    utilisateur      = models.ForeignKey(Utilisateur, on_delete=models.CASCADE,
                        related_name='transactions_wallet')
    montant          = models.DecimalField(max_digits=12, decimal_places=2)
    type_transaction = models.CharField(max_length=20, choices=TYPE_CHOICES)
    description      = models.CharField(max_length=500, blank=True)
    reference        = models.CharField(max_length=100, blank=True)
    solde_apres      = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    date_creation    = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        verbose_name = "Transaction wallet"
        ordering     = ['-date_creation']
        db_table     = 'core_transaction_wallet'
 
    def __str__(self):
        return f"{self.type_transaction} {self.montant} XAF — {self.utilisateur.username}"

# =============================================================================
# MODÈLE : Demande de recharge (à ajouter dans models.py)
# =============================================================================
 
class DemandeRechargeWallet(models.Model):
    """
    Demande de recharge soumise par l'utilisateur.
    Un admin valide ensuite et crédite le wallet.
    """
    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('validee',    'Validée'),
        ('rejetee',    'Rejetée'),
    ]
    METHODE_CHOICES = [
        ('orange_money',   'Orange Money'),
        ('mtn_momo',       'MTN MoMo'),
        ('wave',           'Wave'),
        ('carte_bancaire', 'Carte bancaire'),
    ]
 
    utilisateur       = models.ForeignKey(
        'Utilisateur', on_delete=models.CASCADE,
        related_name='demandes_recharge'
    )
    montant           = models.DecimalField(max_digits=12, decimal_places=2)
    methode           = models.CharField(max_length=30, choices=METHODE_CHOICES)
    numero_expediteur = models.CharField(max_length=30, blank=True)
    preuve_paiement   = models.ImageField(
        upload_to='recharges/', null=True, blank=True
    )
    statut            = models.CharField(
        max_length=20, choices=STATUT_CHOICES, default='en_attente'
    )
    note_admin        = models.TextField(blank=True)
    date_creation     = models.DateTimeField(auto_now_add=True)
    date_traitement   = models.DateTimeField(null=True, blank=True)
 
    class Meta:
        verbose_name = "Demande de recharge"
        ordering     = ['-date_creation']
        db_table     = 'core_demande_recharge'
 
    def __str__(self):
        return f"{self.utilisateur.username} — {self.montant} XAF ({self.statut})"


# =============================================================================
# SECTION 2 : GÉOGRAPHIE
# =============================================================================
 
class Pays(models.Model):
    nom           = models.CharField(max_length=100, unique=True, verbose_name="Nom")
    code          = models.CharField(max_length=3,   unique=True, verbose_name="Code ISO")
    indicatif_tel = models.CharField(max_length=10,  verbose_name="Indicatif téléphonique")
    devise        = models.CharField(max_length=10,  default='XAF', verbose_name="Devise")
    est_actif     = models.BooleanField(default=True)
 
    class Meta:
        verbose_name = "Pays"
        ordering     = ['nom']
        db_table     = 'core_pays'
 
    def __str__(self):
        return self.nom
 
 
class Region(models.Model):
    pays      = models.ForeignKey(Pays, on_delete=models.CASCADE, related_name='regions')
    nom       = models.CharField(max_length=100)
    code      = models.CharField(max_length=10, blank=True)
    est_actif = models.BooleanField(default=True)
 
    class Meta:
        verbose_name    = "Région"
        unique_together = ['pays', 'nom']
        db_table        = 'core_region'
 
    def __str__(self):
        return f"{self.nom} ({self.pays.nom})"
 
 
class Ville(models.Model):
    region                 = models.ForeignKey(Region, on_delete=models.CASCADE,
                                                related_name='villes')
    nom                    = models.CharField(max_length=100)
    code_postal            = models.CharField(max_length=10, blank=True)
    latitude               = models.DecimalField(max_digits=9,  decimal_places=6,
                                                  null=True, blank=True)
    longitude              = models.DecimalField(max_digits=9,  decimal_places=6,
                                                  null=True, blank=True)
    frais_livraison_defaut = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    est_actif              = models.BooleanField(default=True)
 
    class Meta:
        verbose_name    = "Ville"
        unique_together = ['region', 'nom']
        db_table        = 'core_ville'
 
    def __str__(self):
        return f"{self.nom} — {self.region.nom}"
 
    @property
    def pays(self):
        return self.region.pays
 
 
class Quartier(models.Model):
    ville                      = models.ForeignKey(Ville, on_delete=models.CASCADE,
                                                    related_name='quartiers')
    nom                        = models.CharField(max_length=100)
    latitude                   = models.DecimalField(max_digits=9, decimal_places=6,
                                                      null=True, blank=True)
    longitude                  = models.DecimalField(max_digits=9, decimal_places=6,
                                                      null=True, blank=True)
    frais_livraison_supplement = models.DecimalField(max_digits=10, decimal_places=2, default=0)
 
    class Meta:
        verbose_name = "Quartier"
        db_table     = 'core_quartier'
 
    def __str__(self):
        return f"{self.nom} — {self.ville.nom}"



# =============================================================================
# SECTION 3 : CATALOGUE PRODUITS
# =============================================================================
 
class Categorie(models.Model):
    nom         = models.CharField(max_length=100)
    slug        = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    image       = models.ImageField(upload_to='categories/', null=True, blank=True)
    parent      = models.ForeignKey('self', null=True, blank=True,
                                     on_delete=models.CASCADE,
                                     related_name='sous_categories')
    est_active  = models.BooleanField(default=True)
    ordre       = models.PositiveIntegerField(default=0)
    date_creation = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        verbose_name = "Catégorie"
        ordering     = ['ordre', 'nom']
        db_table     = 'core_categorie'
 
    def __str__(self):
        return self.nom
 
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nom)
        super().save(*args, **kwargs)
 
 
class Marque(models.Model):
    nom         = models.CharField(max_length=100)
    slug        = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    logo        = models.ImageField(upload_to='marques/', null=True, blank=True)
    est_active  = models.BooleanField(default=True)
 
    class Meta:
        verbose_name = "Marque"
        db_table     = 'core_marque'
 
    def __str__(self):
        return self.nom
 
 
class Produit(models.Model):
    """
    Produit central — supporte vente directe, enchères, live, B2B, services.
 
    ADAPTATION :
      - est_produit_yopishop : badge officiel YopiShop dans les listings
      - Le champ vendeur pointe vers Utilisateur (pas vers Boutique) → OK pour
        vendeurs individuels et pour YopiShop lui-même.
    """
 
    TYPE_PRODUIT_CHOICES = [
        ('physique',  'Produit physique'),
        ('numerique', 'Produit numérique'),
        ('service',   'Service'),
        ('formation', 'Formation'),
        ('lot',       'Lot / Gros (B2B)'),
    ]
    ETAT_CHOICES = [
        ('neuf',       'Neuf'),
        ('comme_neuf', 'Comme neuf'),
        ('bon_etat',   'Bon état'),
        ('correct',    'État correct'),
        ('mauvais',    'Mauvais état'),
    ]
 
    # Identité
    id                 = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    titre              = models.CharField(max_length=200)
    slug               = models.SlugField(unique=True, max_length=220)
    description        = models.TextField()
    description_courte = models.TextField(max_length=500)
    reference          = models.CharField(max_length=100, unique=True)
 
    # Classification
    type_produit = models.CharField(max_length=20, choices=TYPE_PRODUIT_CHOICES,
                                     default='physique')
    categorie    = models.ForeignKey(Categorie, on_delete=models.CASCADE,
                                      related_name='produits')
    marque       = models.ForeignKey(Marque, null=True, blank=True,
                                      on_delete=models.SET_NULL,
                                      related_name='produits')
    vendeur      = models.ForeignKey(Utilisateur, on_delete=models.CASCADE,
                                      related_name='produits',
                                      verbose_name="Vendeur")
 
    # Prix
    prix       = models.DecimalField(max_digits=12, decimal_places=2)
    prix_achat = models.DecimalField(max_digits=12, decimal_places=2,
                                      null=True, blank=True)
    devise     = models.CharField(max_length=10, default='XAF')
 
    # Stock
    quantite_stock    = models.PositiveIntegerField(default=0)
    alerte_stock_min  = models.PositiveIntegerField(default=5)
    sku               = models.CharField(max_length=100, blank=True)
 
    # Caractéristiques physiques
    etat       = models.CharField(max_length=20, choices=ETAT_CHOICES, default='neuf')
    poids      = models.DecimalField(max_digits=8, decimal_places=2,
                                      null=True, blank=True, help_text="En kg")
    dimensions = models.CharField(max_length=100, blank=True, help_text="LxlxH en cm")
 
    # Localisation
    ville            = models.ForeignKey(Ville, null=True, on_delete=models.PROTECT,
                                          related_name='produits')
    quartier         = models.ForeignKey(Quartier, null=True, blank=True,
                                          on_delete=models.SET_NULL,
                                          related_name='produits')
    adresse_complete = models.TextField(blank=True)
 
    # Options de vente
    est_actif               = models.BooleanField(default=True)
    est_vedette             = models.BooleanField(default=False)
    autorise_enchere        = models.BooleanField(default=False)
    autorise_vente_directe  = models.BooleanField(default=True)
    autorise_achat_groupe   = models.BooleanField(default=False)
    est_b2b                 = models.BooleanField(default=False)
    quantite_min_commande   = models.PositiveIntegerField(default=1)
 
    # Badge YopiShop officiel (NOUVEAU)
    est_produit_yopishop = models.BooleanField(
        default=False,
        verbose_name="Produit YopiShop Officiel",
        help_text="Affiche le badge ✅ YopiShop dans les listings"
    )
 
    # Livraison
    livraison_disponible        = models.BooleanField(default=True)
    livraison_locale_uniquement = models.BooleanField(default=False)
    retrait_sur_place           = models.BooleanField(default=False)
 
    # YopiFulfillment
    en_fulfillment       = models.BooleanField(default=False,
                                                verbose_name="Géré par YopiFulfillment")
    quantite_fulfillment = models.PositiveIntegerField(default=0)
 
    # Réalité augmentée
    modele_3d_url = models.URLField(blank=True, verbose_name="URL modèle 3D / AR")
 
    # SEO
    titre_meta       = models.CharField(max_length=200, blank=True)
    description_meta = models.TextField(max_length=300, blank=True)
 
    # Statistiques
    nb_vues      = models.PositiveIntegerField(default=0)
    nb_ventes    = models.PositiveIntegerField(default=0)
    note_moyenne = models.DecimalField(max_digits=3, decimal_places=2, default=0)
 
    date_creation     = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
 
    class Meta:
        verbose_name = "Produit"
        indexes = [
            models.Index(fields=['ville', 'est_actif']),
            models.Index(fields=['vendeur', 'ville']),
            models.Index(fields=['categorie', 'est_actif']),
            models.Index(fields=['est_vedette', 'est_actif']),
        ]
        db_table = 'core_produit'
 
    def __str__(self):
        return self.titre
 
    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.titre)
            self.slug = f"{base}-{str(self.id)[:8]}" if self.id else base
        # Marquer automatiquement les produits du compte YopiShop officiel
        if self.vendeur.type_vendeur == 'yopishop':
            self.est_produit_yopishop = True
        super().save(*args, **kwargs)
 
    def est_en_stock(self):
        stock = self.quantite_fulfillment if self.en_fulfillment else self.quantite_stock
        return stock > 0

    @property
    def image_principale(self):
        img = self.images.filter(est_principale=True).first() or self.images.first()
        return img.image.url if img else None
        
    @property
    def prix_promotionnel(self):
        """Retourne le prix après la meilleure promotion active."""
        now = timezone.now()
        promos = Promotion.objects.filter(
            statut='active',
            date_debut__lte=now,
            date_fin__gte=now
        ).filter(
            models.Q(produits=self) | models.Q(categories=self.categorie)
        ).order_by('-priorite')
 
        promo = promos.first()
        if not promo:
            return self.prix
 
        if promo.type_promotion == 'pourcentage':
            reduction = (promo.valeur_reduction / Decimal(100)) * self.prix
        elif promo.type_promotion == 'montant_fixe':
            reduction = promo.valeur_reduction
        else:
            return self.prix
 
        if promo.montant_max_reduction:
            reduction = min(reduction, promo.montant_max_reduction)
 
        return max(
            Decimal(0),
            (self.prix - reduction).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        )
 
    def calculer_frais_livraison(self, ville_destination, quartier_destination=None):
        if not self.livraison_disponible:
            return None
        if self.livraison_locale_uniquement and ville_destination.id != self.ville_id:
            return None
        if ville_destination.id == self.ville_id:
            frais = Decimal('0')
            if quartier_destination:
                frais += quartier_destination.frais_livraison_supplement
            return frais
        if ville_destination.region_id == self.ville.region_id:
            return ville_destination.frais_livraison_defaut
        return ville_destination.frais_livraison_defaut * Decimal('1.5')
 
 
class ImageProduit(models.Model):
    produit          = models.ForeignKey(Produit, related_name='images',
                                          on_delete=models.CASCADE)
    image            = models.ImageField(upload_to='produits/')
    texte_alternatif = models.CharField(max_length=200, blank=True)
    est_principale   = models.BooleanField(default=False)
    ordre            = models.PositiveIntegerField(default=0)
 
    class Meta:
        ordering = ['ordre']
        db_table = 'core_image_produit'
 
    def __str__(self):
        return f"Image de {self.produit.titre}"
 
 
class VarianteProduit(models.Model):
    """Variantes : couleur, taille, mémoire, etc."""
    produit              = models.ForeignKey(Produit, on_delete=models.CASCADE,
                                              related_name='variantes')
    nom                  = models.CharField(max_length=100, help_text="Ex: Couleur, Taille")
    valeur               = models.CharField(max_length=100, help_text="Ex: Rouge, XL, 256Go")
    prix_supplementaire  = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stock                = models.PositiveIntegerField(default=0)
    sku_variante         = models.CharField(max_length=100, blank=True)
    image                = models.ImageField(upload_to='variantes/', null=True, blank=True)
    est_active           = models.BooleanField(default=True)
 
    class Meta:
        verbose_name = "Variante produit"
        db_table     = 'core_variante_produit'
 
    def __str__(self):
        return f"{self.produit.titre} — {self.nom}: {self.valeur}"
 
    @property
    def prix_total(self):
        return self.produit.prix + self.prix_supplementaire
 
 
class AttributProduit(models.Model):
    """Attributs techniques libres : RAM, processeur, autonomie, etc."""
    produit = models.ForeignKey(Produit, on_delete=models.CASCADE, related_name='attributs')
    nom     = models.CharField(max_length=100)
    valeur  = models.CharField(max_length=200)
    unite   = models.CharField(max_length=20, blank=True, help_text="Ex: Go, MHz, cm")
    ordre   = models.PositiveIntegerField(default=0)
 
    class Meta:
        ordering = ['ordre']
        db_table = 'core_attribut_produit'
 
    def __str__(self):
        return f"{self.nom}: {self.valeur}{self.unite}"
 
 
# =============================================================================
# SECTION 4 : PROMOTIONS
# =============================================================================
 
class Promotion(models.Model):
    TYPE_CHOICES = [
        ('pourcentage',         'Pourcentage'),
        ('montant_fixe',        'Montant fixe'),
        ('achetez_x_obtenez_y', 'Achetez X obtenez Y'),
        ('livraison_gratuite',  'Livraison gratuite'),
        ('bundle',              'Bundle / Pack'),
    ]
    STATUT_CHOICES = [
        ('brouillon', 'Brouillon'),
        ('active',    'Active'),
        ('expiree',   'Expirée'),
        ('en_pause',  'En pause'),
    ]
 
    nom                   = models.CharField(max_length=200)
    description           = models.TextField()
    code                  = models.CharField(max_length=50, unique=True, null=True, blank=True)
    type_promotion        = models.CharField(max_length=25, choices=TYPE_CHOICES)
    valeur_reduction      = models.DecimalField(max_digits=10, decimal_places=2)
    montant_min_achat     = models.DecimalField(max_digits=10, decimal_places=2,
                                                 null=True, blank=True)
    montant_max_reduction = models.DecimalField(max_digits=10, decimal_places=2,
                                                 null=True, blank=True)
    limite_utilisation    = models.PositiveIntegerField(null=True, blank=True)
    limite_par_utilisateur = models.PositiveIntegerField(default=1)
    date_debut            = models.DateTimeField()
    date_fin              = models.DateTimeField()
    categories            = models.ManyToManyField(Categorie, blank=True)
    produits              = models.ManyToManyField(Produit, blank=True)
    utilisateurs          = models.ManyToManyField(Utilisateur, blank=True)
    statut                = models.CharField(max_length=20, choices=STATUT_CHOICES,
                                              default='brouillon')
    priorite              = models.PositiveIntegerField(default=0)
    date_creation         = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        verbose_name = "Promotion"
        db_table     = 'core_promotion'
 
    def __str__(self):
        return self.nom
 
 
# =============================================================================
# SECTION 5 : AVIS PRODUITS ET FAVORIS
# =============================================================================
 
class ImageAvis(models.Model):
    """Image jointe à un avis produit."""
    image         = models.ImageField(upload_to='avis/')
    date_creation = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        db_table = 'core_image_avis'
 
 
class Avis(models.Model):
    produit           = models.ForeignKey(Produit, related_name='avis',
                                           on_delete=models.CASCADE)
    utilisateur       = models.ForeignKey(Utilisateur, on_delete=models.CASCADE,
                                           related_name='avis')
    note              = models.PositiveIntegerField(validators=[MinValueValidator(1),
                                                                 MaxValueValidator(5)])
    titre             = models.CharField(max_length=200)
    commentaire       = models.TextField()
    est_achat_verifie = models.BooleanField(default=False)
    est_approuve      = models.BooleanField(default=True)
    votes_utiles      = models.PositiveIntegerField(default=0)
    images            = models.ManyToManyField(ImageAvis, blank=True)
    date_creation     = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
 
    class Meta:
        unique_together = ['produit', 'utilisateur']
        db_table        = 'core_avis'
 
    def __str__(self):
        return f"Avis {self.note}★ de {self.utilisateur.username}"
 
 
class ListeSouhaits(models.Model):
    utilisateur   = models.ForeignKey(Utilisateur, on_delete=models.CASCADE,
                                       related_name='listes_souhaits')
    nom           = models.CharField(max_length=100, default='Ma liste')
    est_publique  = models.BooleanField(default=False)
    produits      = models.ManyToManyField(Produit, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        db_table = 'core_liste_souhaits'
 
    def __str__(self):
        return f"{self.utilisateur.username} — {self.nom}"
 
 
# =============================================================================
# SECTION 6 : NOTIFICATIONS
# =============================================================================
 
class Notification(models.Model):
    TYPE_CHOICES = [
        ('commande',      'Commande'),
        ('paiement',      'Paiement'),
        ('enchere',       'Enchère'),
        ('promotion',     'Promotion'),
        ('live',          'Live'),
        ('social',        'Réseau social'),
        ('systeme',       'Système'),
        ('alerte_stock',  'Alerte stock'),
        ('gamification',  'Récompense / Badge'),
        ('livraison',     'Livraison'),
    ]
    CANAL_CHOICES = [
        ('push',   'Push'),
        ('email',  'Email'),
        ('sms',    'SMS'),
        ('in_app', 'In-App'),
    ]
 
    utilisateur       = models.ForeignKey(Utilisateur, on_delete=models.CASCADE,
                                           related_name='notifications')
    type_notification = models.CharField(max_length=20, choices=TYPE_CHOICES)
    titre             = models.CharField(max_length=200)
    message           = models.TextField()
    est_lu            = models.BooleanField(default=False)
    lien              = models.CharField(max_length=500, blank=True)
    canal             = models.CharField(max_length=10, choices=CANAL_CHOICES,
                                          default='in_app')
    donnees_extra     = models.JSONField(default=dict, blank=True)
    date_creation     = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        ordering = ['-date_creation']
        db_table = 'core_notification'
 
    def __str__(self):
        return f"{self.titre} → {self.utilisateur.username}"
 
 
 