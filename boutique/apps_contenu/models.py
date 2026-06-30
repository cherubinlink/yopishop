# ===========================================================================
# app_contenu/models.py
# Application : Blog, Carousel, Bannières promotionnelles
# ===========================================================================
 
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.urls import reverse
from decimal import Decimal



# =============================================================================
# SECTION 1 : CAROUSEL (conservé et amélioré depuis l'ancien projet)
# =============================================================================
 
class CarouselPrincipal(models.Model):
    """Slides du carousel principal de la page d'accueil"""
    POSITION_CHOICES = [
        ('gauche', 'Image à gauche'),
        ('droite', 'Image à droite'),
        ('centre', 'Image centrée'),
    ]
 
    titre_petit     = models.CharField(max_length=200, verbose_name="Petit titre")
    titre_principal = models.CharField(max_length=300, verbose_name="Titre principal")
    description     = models.TextField(max_length=500, verbose_name="Description")
 
    # Image
    image           = models.ImageField(upload_to='carousel/principal/')
    image_mobile    = models.ImageField(upload_to='carousel/principal/mobile/',
                                         null=True, blank=True,
                                         help_text="Version optimisée mobile")
    image_alt       = models.CharField(max_length=200, blank=True)
    position_image  = models.CharField(max_length=10, choices=POSITION_CHOICES, default='gauche')
 
    # Couleurs personnalisables
    couleur_fond        = models.CharField(max_length=7, default='#1A1A2E')
    couleur_titre       = models.CharField(max_length=7, default='#FFFFFF')
    couleur_bouton      = models.CharField(max_length=7, default='#FF6B00')
 
    # Bouton d'action
    texte_bouton    = models.CharField(max_length=50, default='Shop Now')
    lien_bouton     = models.CharField(max_length=500)
    ouvrir_nouvel_onglet = models.BooleanField(default=False)
 
    # Badge / étiquette
    texte_badge     = models.CharField(max_length=50, blank=True,
                                        help_text="Ex: NOUVEAUTÉ, -50%, EXCLU")
    couleur_badge   = models.CharField(max_length=7, default='#FF3300')
 
    # Affichage
    ordre           = models.PositiveIntegerField(default=0)
    est_actif       = models.BooleanField(default=True)
 
    # Dates de publication
    date_debut      = models.DateTimeField(null=True, blank=True)
    date_fin        = models.DateTimeField(null=True, blank=True)
 
    # Statistiques
    nb_vues         = models.PositiveIntegerField(default=0)
    nb_clics        = models.PositiveIntegerField(default=0)
 
    date_creation   = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
 
    class Meta:
        verbose_name = "Slide du carousel principal"
        verbose_name_plural = "Slides du carousel principal"
        ordering = ['ordre', '-date_creation']
        db_table = 'contenu_carousel_principal'
 
    def __str__(self):
        return self.titre_principal
 
    def est_visible(self):
        if not self.est_actif:
            return False
        maintenant = timezone.now()
        if self.date_debut and maintenant < self.date_debut:
            return False
        if self.date_fin and maintenant > self.date_fin:
            return False
        return True
 
    def taux_clic(self):
        if self.nb_vues == 0:
            return 0
        return round(self.nb_clics / self.nb_vues * 100, 2)
 
 
class BannierePromotion(models.Model):
    """Bannière de promotion latérale (style iPad Mini / offre du jour)"""
    TYPE_PRODUIT_CHOICES = [
        ('smartphone',  'SmartPhone'),
        ('laptop',      'Laptop'),
        ('tablet',      'Tablette'),
        ('accessoire',  'Accessoire'),
        ('vetement',    'Vêtement'),
        ('electromenager', 'Électroménager'),
        ('autre',       'Autre'),
    ]
 
    # Lien optionnel avec un produit existant
    produit         = models.ForeignKey('apps_core.Produit', on_delete=models.CASCADE,
                                         related_name='bannieres_promo', null=True, blank=True,
                                         help_text="Lier à un produit ou remplir manuellement")
 
    type_produit    = models.CharField(max_length=20, choices=TYPE_PRODUIT_CHOICES, default='smartphone')
    nom_produit     = models.CharField(max_length=200)
 
    # Image de fond
    image_fond      = models.ImageField(upload_to='carousel/banniere/')
    image_alt       = models.CharField(max_length=200, blank=True)
 
    # Prix
    prix_original   = models.DecimalField(max_digits=10, decimal_places=2)
    prix_promo      = models.DecimalField(max_digits=10, decimal_places=2)
    montant_economie = models.DecimalField(max_digits=10, decimal_places=2,
                                            null=True, blank=True,
                                            help_text="Calculé automatiquement si vide")
    devise          = models.CharField(max_length=10, default='XAF')
 
    # Texte
    titre_offre     = models.CharField(max_length=100, default='Promotion du jour')
    sous_titre      = models.CharField(max_length=200, blank=True)
 
    # Bouton
    texte_bouton    = models.CharField(max_length=50, default='Ajouter au panier')
    lien_bouton     = models.CharField(max_length=500)
 
    # Affichage
    est_actif       = models.BooleanField(default=True)
    priorite        = models.PositiveIntegerField(default=0)
 
    # Dates
    date_debut      = models.DateTimeField(null=True, blank=True)
    date_fin        = models.DateTimeField(null=True, blank=True)
 
    # Stats
    nb_clics        = models.PositiveIntegerField(default=0)
 
    date_creation   = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
 
    class Meta:
        verbose_name = "Bannière de promotion"
        verbose_name_plural = "Bannières de promotion"
        ordering = ['-priorite', '-date_creation']
        db_table = 'contenu_banniere_promotion'
 
    def __str__(self):
        return f"{self.nom_produit} — {self.titre_offre}"
 
    def save(self, *args, **kwargs):
        if not self.montant_economie:
            self.montant_economie = self.prix_original - self.prix_promo
        if self.produit:
            self.nom_produit = self.produit.titre
            if not self.prix_original:
                self.prix_original = self.produit.prix
        super().save(*args, **kwargs)
 
    def pourcentage_reduction(self):
        if self.prix_original and self.prix_original > 0:
            return round(((self.prix_original - self.prix_promo) / self.prix_original) * 100, 1)
        return 0
 
    def est_visible(self):
        if not self.est_actif:
            return False
        maintenant = timezone.now()
        if self.date_debut and maintenant < self.date_debut:
            return False
        if self.date_fin and maintenant > self.date_fin:
            return False
        return True
 
 
class ConfigurationCarousel(models.Model):
    """Configuration globale du carousel (singleton)"""
    # Carousel principal
    vitesse_transition  = models.PositiveIntegerField(default=3000, help_text="ms")
    auto_play           = models.BooleanField(default=True)
    afficher_fleches    = models.BooleanField(default=True)
    afficher_points     = models.BooleanField(default=True)
    boucle              = models.BooleanField(default=True)
    effet_transition    = models.CharField(max_length=10,
                                            choices=[('slide', 'Glissement'), ('fade', 'Fondu')],
                                            default='slide')
 
    # Bannière latérale
    afficher_banniere_laterale  = models.BooleanField(default=True)
    rotation_banniere           = models.BooleanField(default=False)
    duree_banniere              = models.PositiveIntegerField(default=5000, help_text="ms")
 
    # Personnalisation avancée
    hauteur_carousel_desktop    = models.PositiveIntegerField(default=500, help_text="px")
    hauteur_carousel_mobile     = models.PositiveIntegerField(default=300, help_text="px")
    afficher_compteur_slides    = models.BooleanField(default=False)
 
    derniere_modification = models.DateTimeField(auto_now=True)
 
    class Meta:
        verbose_name = "Configuration du carousel"
        verbose_name_plural = "Configuration du carousel"
        db_table = 'contenu_config_carousel'
 
    def __str__(self):
        return f"Config Carousel (maj: {self.derniere_modification.strftime('%d/%m/%Y')})"
 
    @classmethod
    def get_config(cls):
        config, _ = cls.objects.get_or_create(pk=1)
        return config
 
 
class StatistiqueCarousel(models.Model):
    """Statistiques de clics et vues sur les éléments du carousel"""
    TYPE_ELEMENT_CHOICES = [
        ('slide',    'Slide principal'),
        ('banniere', 'Bannière promotion'),
    ]
    ACTION_CHOICES = [
        ('vue',  'Vue'),
        ('clic', 'Clic'),
    ]
 
    type_element    = models.CharField(max_length=10, choices=TYPE_ELEMENT_CHOICES)
    slide_principal = models.ForeignKey(CarouselPrincipal, on_delete=models.CASCADE,
                                         null=True, blank=True, related_name='statistiques')
    banniere_promo  = models.ForeignKey(BannierePromotion, on_delete=models.CASCADE,
                                         null=True, blank=True, related_name='statistiques')
    utilisateur     = models.ForeignKey('apps_core.Utilisateur', on_delete=models.SET_NULL,
                                         null=True, blank=True)
    adresse_ip      = models.GenericIPAddressField()
    user_agent      = models.TextField()
    action          = models.CharField(max_length=5, choices=ACTION_CHOICES, default='clic')
    date_action     = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        verbose_name = "Statistique carousel"
        ordering = ['-date_action']
        db_table = 'contenu_stat_carousel'
 
    def __str__(self):
        element = self.slide_principal or self.banniere_promo
        return f"{self.action} — {element} — {self.date_action.strftime('%d/%m/%Y %H:%M')}"


# =============================================================================
# SECTION 2 : BLOG E-COMMERCE
# =============================================================================
 
class CategorieBlog(models.Model):
    nom         = models.CharField(max_length=100)
    slug        = models.SlugField(unique=True, blank=True, max_length=120)
    description = models.TextField(blank=True)
    image       = models.ImageField(upload_to='blog/categories/', blank=True, null=True)
    parent      = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True,
                                     related_name='sous_categories')
    ordre       = models.IntegerField(default=0)
    actif       = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        verbose_name = "Catégorie Blog"
        ordering = ['ordre', 'nom']
        db_table = 'contenu_categorie_blog'
 
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nom)
        super().save(*args, **kwargs)
 
    def __str__(self):
        return self.nom
 
    def get_absolute_url(self):
        return reverse('blog:categorie', kwargs={'slug': self.slug})
 
 
class Tag(models.Model):
    nom     = models.CharField(max_length=50, unique=True)
    slug    = models.SlugField(unique=True, blank=True, max_length=60)
 
    class Meta:
        ordering = ['nom']
        db_table = 'contenu_tag'
 
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nom)
        super().save(*args, **kwargs)
 
    def __str__(self):
        return self.nom
 
 
class Article(models.Model):
    STATUT_CHOICES = [
        ('brouillon', 'Brouillon'),
        ('publie',    'Publié'),
        ('archive',   'Archivé'),
    ]
    TYPE_CHOICES = [
        ('conseil',       "Conseil d'achat"),
        ('innovation',    'Innovation technologique'),
        ('actualite',     'Actualité'),
        ('tutoriel',      'Tutoriel'),
        ('comparatif',    'Comparatif produits'),
        ('tendance',      'Tendance mode / tech'),
    ]
    ZONE_CHOICES = [
        ('local',         'Local'),
        ('international', 'International'),
        ('mixte',         'Local & International'),
    ]
 
    titre           = models.CharField(max_length=200)
    slug            = models.SlugField(unique=True, blank=True, max_length=220)
    sous_titre      = models.CharField(max_length=250, blank=True)
    extrait         = models.TextField(max_length=300)
    contenu         = models.TextField()
    image_principale = models.ImageField(upload_to='blog/articles/%Y/%m/')
    image_alt       = models.CharField(max_length=200, blank=True)
 
    auteur          = models.ForeignKey('apps_core.Utilisateur', on_delete=models.SET_NULL,
                                         null=True, related_name='articles')
    categorie       = models.ForeignKey(CategorieBlog, on_delete=models.SET_NULL,
                                         null=True, related_name='articles')
    tags            = models.ManyToManyField(Tag, blank=True, related_name='articles')
    type_article    = models.CharField(max_length=20, choices=TYPE_CHOICES, default='actualite')
    zone_geo        = models.CharField(max_length=20, choices=ZONE_CHOICES, default='mixte')
 
    # Produits liés dans l'article
    produits_lies   = models.ManyToManyField('apps_core.Produit', blank=True,
                                              related_name='articles',
                                              help_text="Produits mentionnés / recommandés")
 
    date_creation   = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    date_publication = models.DateTimeField(null=True, blank=True)
    statut          = models.CharField(max_length=20, choices=STATUT_CHOICES, default='brouillon')
 
    # SEO
    meta_description = models.CharField(max_length=160, blank=True)
    meta_keywords   = models.CharField(max_length=255, blank=True)
 
    # Stats
    vues            = models.PositiveIntegerField(default=0, editable=False)
    featured        = models.BooleanField(default=False)
 
    class Meta:
        verbose_name = "Article"
        ordering = ['-date_publication', '-date_creation']
        indexes = [
            models.Index(fields=['-date_publication', 'statut']),
            models.Index(fields=['slug']),
        ]
        db_table = 'contenu_article'
 
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.titre)
        if self.statut == 'publie' and not self.date_publication:
            self.date_publication = timezone.now()
        if not self.extrait and self.contenu:
            self.extrait = self.contenu[:297] + '...'
        if not self.meta_description and self.extrait:
            self.meta_description = self.extrait[:157] + '...'
        super().save(*args, **kwargs)
 
    def __str__(self):
        return self.titre
 
    def get_absolute_url(self):
        return reverse('blog:article_detail', kwargs={'slug': self.slug})
 
    def incrementer_vues(self):
        self.vues += 1
        self.save(update_fields=['vues'])
 
    @property
    def est_publie(self):
        return (self.statut == 'publie' and
                self.date_publication and
                self.date_publication <= timezone.now())
 
    @property
    def temps_lecture(self):
        """Retourne (minutes, secondes)"""
        nb_mots = len(self.contenu.split())
        total_sec = int((nb_mots / 250) * 60)
        return total_sec // 60, total_sec % 60
 
 
class CommentaireArticle(models.Model):
    article     = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='commentaires')
    auteur      = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE)
    contenu     = models.TextField(max_length=1000)
    parent      = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True,
                                     related_name='reponses')
    actif       = models.BooleanField(default=True)
    nb_likes    = models.PositiveIntegerField(default=0)
    date_creation = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        ordering = ['-date_creation']
        db_table = 'contenu_commentaire_article'
 
    def __str__(self):
        return f"{self.auteur.username} sur {self.article.titre}"
 


# =============================================================================
# SECTION 3 : ZONES DE LIVRAISON VENDEUR
# =============================================================================
 
class ZoneLivraisonVendeur(models.Model):
    """Zones où un vendeur accepte de livrer"""
    vendeur     = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                     related_name='zones_livraison')
    ville       = models.ForeignKey('apps_core.Ville', on_delete=models.CASCADE)
    est_active  = models.BooleanField(default=True)
    frais_personnalises = models.DecimalField(max_digits=10, decimal_places=2,
                                               null=True, blank=True,
                                               help_text="Frais spéciaux pour cette ville")
 
    class Meta:
        unique_together = ['vendeur', 'ville']
        db_table = 'contenu_zone_livraison_vendeur'
 
    def __str__(self):
        return f"{self.vendeur.username} → {self.ville.nom}"
 