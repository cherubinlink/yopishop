# ===========================================================================
# app_social/models.py
# Application : Réseau Social Commerce (TikTok + Instagram + E-commerce)
# Inclut : Lives, Stories, Vidéos courtes, Influenceurs, Feed social
# ===========================================================================
 
from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta
import uuid


# =============================================================================
# SECTION 1 : PROFIL SOCIAL
# =============================================================================
 
class ProfilSocial(models.Model):
    """Extension sociale d'un utilisateur — abonnés, abonnements, contenu"""
    utilisateur     = models.OneToOneField('apps_core.Utilisateur', on_delete=models.CASCADE,
                                            related_name='profil_social')
    biographie      = models.TextField(max_length=300, blank=True)
    lien_bio        = models.URLField(blank=True)
    nb_abonnes      = models.PositiveIntegerField(default=0)
    nb_abonnements  = models.PositiveIntegerField(default=0)
    nb_publications = models.PositiveIntegerField(default=0)
    est_verifie     = models.BooleanField(default=False, help_text="Compte certifié ✓")
    est_public      = models.BooleanField(default=True)
 
    class Meta:
        db_table = 'social_profil'
 
    def __str__(self):
        return f"@{self.utilisateur.username}"
 
 
class AbonnementSocial(models.Model):
    """Abonnement entre utilisateurs (follow)"""
    abonne      = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                     related_name='abonnements')
    suivi       = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                     related_name='abonnes')
    date_abonnement = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        unique_together = ['abonne', 'suivi']
        db_table = 'social_abonnement'
 
    def __str__(self):
        return f"{self.abonne.username} → {self.suivi.username}"
 
 
# =============================================================================
# SECTION 2 : LIVE SHOPPING
# =============================================================================
 
class LiveVente(models.Model):
    """
    Session Live Shopping — TikTok Live + eBay style.
    Inclut : stream vidéo, chat temps réel, enchères live, achats instantanés.
    """
    STATUT_CHOICES = [
        ('planifie', '📅 Planifié'),
        ('en_cours', '🔴 En direct'),
        ('termine',  '✅ Terminé'),
        ('annule',   '❌ Annulé'),
    ]
    TYPE_CHOICES = [
        ('vente',      'Vente directe'),
        ('enchere',    'Enchères en direct'),
        ('mixte',      'Vente + Enchères'),
        ('decouverte', 'Découverte produits'),
    ]

    STREAM_CHOICES = [
        ('hors_ligne', '⚫ Hors ligne'),
        ('connexion',  '🟡 Connexion en cours'),
        ('diffusion',  '🔴 En diffusion'),
        ('erreur',     '⚠️ Erreur de connexion'),
        ('termine',    '⏹️ Diffusion terminée'),
    ]
 
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    titre           = models.CharField(max_length=200)
    description     = models.TextField()
    vendeur         = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                         related_name='lives_vendeur')
    type_live       = models.CharField(max_length=15, choices=TYPE_CHOICES, default='mixte')
 
    # Co-animateurs / influenceurs invités
    co_animateurs   = models.ManyToManyField('apps_core.Utilisateur', blank=True,
                                              related_name='lives_co_animes')
 
    # Planification
    date_debut      = models.DateTimeField()
    duree_jours     = models.PositiveIntegerField(default=0)
    duree_heures    = models.PositiveIntegerField(default=1)
    date_fin_reelle = models.DateTimeField(null=True, blank=True)
 
    # Médias
    image_couverture = models.ImageField(upload_to='lives/couvertures/')
    url_stream      = models.URLField(blank=True, help_text="RTMP / HLS stream URL")
    url_replay      = models.URLField(blank=True, help_text="URL vidéo replay après le live")
 
    # Slider produits
    delai_defilement    = models.PositiveIntegerField(default=30,
                                                       validators=[MinValueValidator(10)])
    defilement_auto     = models.BooleanField(default=True)

    # ... dans la classe LiveVente, à côté de url_stream ...
    stream_statut  = models.CharField(max_length=20, choices=STREAM_CHOICES, default='hors_ligne')
    stream_demarre = models.BooleanField(default=False)
 
    # Interaction
    autoriser_chat      = models.BooleanField(default=True)
    autoriser_questions = models.BooleanField(default=True)
    autoriser_reactions = models.BooleanField(default=True)
 
    # Statut et stats
    statut              = models.CharField(max_length=15, choices=STATUT_CHOICES, default='planifie')
    nb_vues_total       = models.PositiveIntegerField(default=0)
    nb_participants_actuels = models.PositiveIntegerField(default=0)
    nb_participants_max = models.PositiveIntegerField(default=0)
    chiffre_affaires_live = models.DecimalField(max_digits=14, decimal_places=2, default=0)
 
    date_creation   = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
 
    class Meta:
        verbose_name = "Live Vente"
        ordering = ['-date_debut']
        db_table = 'social_live_vente'
 
    def __str__(self):
        return f"🔴 {self.titre} — {self.vendeur.username}"
 
    def est_en_cours(self):
        return self.statut == 'en_cours' and self.date_debut <= timezone.now()
 
    def date_fin_prevue(self):
        return self.date_debut + timedelta(days=self.duree_jours, hours=self.duree_heures)
 
 
class ProduitLive(models.Model):
    """Produit présenté dans un live avec prix spécial"""
    live            = models.ForeignKey(LiveVente, related_name='produits_live', on_delete=models.CASCADE)
    produit         = models.ForeignKey('apps_core.Produit', on_delete=models.CASCADE)
    ordre           = models.PositiveIntegerField(default=0)
 
    # Prix live
    prix_live       = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    reduction_pourcentage = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                                 validators=[MinValueValidator(0)])
 
    # Stock dédié
    quantite_live       = models.PositiveIntegerField()
    quantite_vendue     = models.PositiveIntegerField(default=0)
    quantite_reservee   = models.PositiveIntegerField(default=0)
 
    # Présentation
    description_live    = models.TextField(blank=True)
    points_forts        = models.TextField(blank=True, help_text="Séparés par virgules")
    temps_presentation  = models.PositiveIntegerField(default=60, help_text="Secondes")
 
    # État
    est_presente        = models.BooleanField(default=False)
    heure_presentation  = models.DateTimeField(null=True, blank=True)
    est_disponible      = models.BooleanField(default=True)
 
    date_ajout          = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        ordering = ['ordre']
        unique_together = ['live', 'produit']
        db_table = 'social_produit_live'
 
    def __str__(self):
        return f"{self.produit.titre} (Live: {self.live.titre})"
 
    def prix_final(self):
        prix_normal = self.produit.prix
        prix_promo  = self.produit.prix_promotionnel   # <-- sans ()

        candidats = [prix_normal]

        if self.prix_live and self.prix_live > 0:
            candidats.append(self.prix_live)

        if self.reduction_pourcentage > 0:
            reduction = (self.reduction_pourcentage / Decimal("100")) * prix_normal
            candidats.append(prix_normal - reduction)

        if prix_promo < prix_normal:
            candidats.append(prix_promo)

        return min(candidats).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )
 
    def stock_disponible(self):
        return self.quantite_live - self.quantite_vendue - self.quantite_reservee
 
    def est_epuise(self):
        return self.stock_disponible() <= 0
 
 
class ChatLive(models.Model):
    """Messages temps réel du chat live"""
    TYPE_CHOICES = [
        ('message',   '💬 Message'),
        ('question',  '❓ Question'),
        ('reponse',   '✅ Réponse vendeur'),
        ('systeme',   '🔔 Système'),
        ('achat',     '🛒 Notification achat'),
        ('reaction',  '🎉 Réaction'),
    ]
 
    live            = models.ForeignKey(LiveVente, related_name='messages', on_delete=models.CASCADE)
    utilisateur     = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE)
    contenu         = models.TextField(max_length=500)
    type_message    = models.CharField(max_length=15, choices=TYPE_CHOICES, default='message')
    produit_concerne = models.ForeignKey(ProduitLive, null=True, blank=True, on_delete=models.SET_NULL)
    message_parent  = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE,
                                         related_name='reponses')
    est_epingle     = models.BooleanField(default=False)
    emoji_reaction  = models.CharField(max_length=10, blank=True)
    date_creation   = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        ordering = ['date_creation']
        db_table = 'social_chat_live'
 
    def __str__(self):
        return f"{self.utilisateur.username}: {self.contenu[:40]}"
 
 
class ParticipantLive(models.Model):
    live            = models.ForeignKey(LiveVente, related_name='participants', on_delete=models.CASCADE)
    utilisateur     = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE)
    date_entree     = models.DateTimeField(auto_now_add=True)
    date_sortie     = models.DateTimeField(null=True, blank=True)
    est_connecte    = models.BooleanField(default=True)
    nb_messages     = models.PositiveIntegerField(default=0)
    nb_questions    = models.PositiveIntegerField(default=0)
    nb_reactions    = models.PositiveIntegerField(default=0)
    a_effectue_achat = models.BooleanField(default=False)
    montant_achats  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
 
    # Source d'entrée (influence tracking)
    invite_par      = models.ForeignKey('apps_core.Utilisateur', null=True, blank=True,
                                         on_delete=models.SET_NULL, related_name='participants_invites')
 
    class Meta:
        unique_together = ['live', 'utilisateur']
        db_table = 'social_participant_live'
 
    def __str__(self):
        return f"{self.utilisateur.username} — {self.live.titre}"
 
 
class ReservationLive(models.Model):
    """Réservation temporaire d'un produit pendant le live"""
    STATUT_CHOICES = [
        ('en_attente', '⏳ En attente'),
        ('confirmee',  '✅ Confirmée'),
        ('expiree',    '⌛ Expirée'),
        ('annulee',    '❌ Annulée'),
    ]
 
    produit_live    = models.ForeignKey(ProduitLive, related_name='reservations', on_delete=models.CASCADE)
    utilisateur     = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE)
    quantite        = models.PositiveIntegerField(default=1)
    prix_unitaire   = models.DecimalField(max_digits=12, decimal_places=2)
    montant_total   = models.DecimalField(max_digits=12, decimal_places=2)
    statut          = models.CharField(max_length=15, choices=STATUT_CHOICES, default='en_attente')
    date_reservation = models.DateTimeField(auto_now_add=True)
    date_expiration = models.DateTimeField()
    commande        = models.ForeignKey('apps_marketplace.Commande', null=True, blank=True,
                                         on_delete=models.SET_NULL)
 
    class Meta:
        verbose_name = "Réservation live"
        db_table = 'social_reservation_live'
 
    def __str__(self):
        return f"{self.utilisateur.username} — {self.produit_live.produit.titre}"
 
    def est_expiree(self):
        return timezone.now() > self.date_expiration and self.statut == 'en_attente'
 
    def save(self, *args, **kwargs):
        if not self.pk:
            self.montant_total = self.prix_unitaire * self.quantite
            self.date_expiration = self.produit_live.live.date_fin_prevue()
        super().save(*args, **kwargs)


# =============================================================================
# SECTION 3 : STORIES (24h)
# =============================================================================
 
class Story(models.Model):
    """Stories — disparaissent après 24h"""
    TYPE_CHOICES = [
        ('image',   '📸 Image'),
        ('video',   '🎥 Vidéo'),
        ('produit', '🛒 Produit'),
        ('offre',   '🏷️ Offre spéciale'),
    ]
 
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    auteur          = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                         related_name='stories')
    type_story      = models.CharField(max_length=10, choices=TYPE_CHOICES, default='image')
 
    # Médias
    media           = models.FileField(upload_to='stories/%Y/%m/')
    miniature       = models.ImageField(upload_to='stories/miniatures/', null=True, blank=True)
    texte           = models.CharField(max_length=200, blank=True)
    couleur_fond    = models.CharField(max_length=7, default='#000000')
 
    # Lien produit / offre
    produit_lie     = models.ForeignKey('apps_core.Produit', null=True, blank=True,
                                         on_delete=models.SET_NULL, related_name='stories')
    bouton_action   = models.CharField(max_length=50, blank=True, help_text="Texte du CTA")
    lien_action     = models.URLField(blank=True)
 
    # Stats
    nb_vues         = models.PositiveIntegerField(default=0)
    nb_clics        = models.PositiveIntegerField(default=0)
 
    date_creation   = models.DateTimeField(auto_now_add=True)
    date_expiration = models.DateTimeField()
 
    class Meta:
        ordering = ['-date_creation']
        db_table = 'social_story'
 
    def __str__(self):
        return f"Story de {self.auteur.username} ({self.get_type_story_display()})"
 
    def save(self, *args, **kwargs):
        if not self.date_expiration:
            self.date_expiration = timezone.now() + timedelta(hours=24)
        super().save(*args, **kwargs)
 
    def est_active(self):
        return timezone.now() < self.date_expiration
 
    def est_expiree(self):
        return timezone.now() >= self.date_expiration
 
 
class VueStory(models.Model):
    story           = models.ForeignKey(Story, on_delete=models.CASCADE, related_name='vues')
    utilisateur     = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE)
    date_vue        = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        unique_together = ['story', 'utilisateur']
        db_table = 'social_vue_story'
 

# =============================================================================
# SECTION 4 : VIDÉOS COURTES (ShopTok)
# =============================================================================
 
class VideoCommerce(models.Model):
    """
    Vidéos courtes type TikTok avec achat intégré.
    Les produits apparaissent avec un bouton d'achat direct dans la vidéo.
    """
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    auteur          = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                         related_name='videos_commerce')
    titre           = models.CharField(max_length=200)
    description     = models.TextField(max_length=500, blank=True)
 
    # Médias
    video           = models.FileField(upload_to='videos/%Y/%m/')
    miniature       = models.ImageField(upload_to='videos/miniatures/')
    duree_secondes  = models.PositiveIntegerField(default=30)
 
    # Produits intégrés dans la vidéo (acheter directement)
    produits        = models.ManyToManyField('apps_core.Produit', through='ProduitVideo',
                                              related_name='videos')
 
    # Hashtags
    hashtags        = models.CharField(max_length=500, blank=True,
                                        help_text="Hashtags séparés par espaces")
 
    # Stats
    nb_vues         = models.PositiveIntegerField(default=0)
    nb_likes        = models.PositiveIntegerField(default=0)
    nb_partages     = models.PositiveIntegerField(default=0)
    nb_commentaires = models.PositiveIntegerField(default=0)
    nb_achats       = models.PositiveIntegerField(default=0,
                                                   help_text="Achats issus directement de la vidéo")
    chiffre_affaires = models.DecimalField(max_digits=14, decimal_places=2, default=0)
 
    est_publie      = models.BooleanField(default=True)
    est_mis_en_avant = models.BooleanField(default=False)
 
    date_creation   = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        verbose_name = "Vidéo Commerce"
        ordering = ['-date_creation']
        db_table = 'social_video_commerce'
 
    def __str__(self):
        return f"📹 {self.titre} — {self.auteur.username}"
 
 
class ProduitVideo(models.Model):
    """Produit intégré dans une vidéo avec timestamp"""
    video           = models.ForeignKey(VideoCommerce, on_delete=models.CASCADE,
                                         related_name='produits_video')
    produit         = models.ForeignKey('apps_core.Produit', on_delete=models.CASCADE)
    timestamp_apparition = models.PositiveIntegerField(default=0,
                                                        help_text="Seconde où le produit apparaît")
    position_x      = models.DecimalField(max_digits=5, decimal_places=2, default=50,
                                           help_text="Position X en % dans la vidéo")
    position_y      = models.DecimalField(max_digits=5, decimal_places=2, default=50,
                                           help_text="Position Y en % dans la vidéo")
    texte_bouton    = models.CharField(max_length=50, default='Acheter')
 
    class Meta:
        unique_together = ['video', 'produit']
        db_table = 'social_produit_video'
 
    def __str__(self):
        return f"{self.produit.titre} à {self.timestamp_apparition}s dans {self.video.titre}"
 
 
class CommentaireVideo(models.Model):
    video           = models.ForeignKey(VideoCommerce, on_delete=models.CASCADE,
                                         related_name='commentaires')
    auteur          = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE)
    contenu         = models.TextField(max_length=300)
    parent          = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE,
                                         related_name='reponses')
    nb_likes        = models.PositiveIntegerField(default=0)
    date_creation   = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        ordering = ['-date_creation']
        db_table = 'social_commentaire_video'
 
    def __str__(self):
        return f"{self.auteur.username}: {self.contenu[:50]}"
 
# =============================================================================
# SECTION 5 : INFLUENCEURS
# =============================================================================
 
class ProgrammeInfluenceur(models.Model):
    """Configuration du programme d'affiliation influenceur"""
    STATUT_CHOICES = [
        ('candidature', 'En candidature'),
        ('actif',       'Actif'),
        ('suspendu',    'Suspendu'),
        ('termine',     'Terminé'),
    ]
    NIVEAU_CHOICES = [
        ('nano',    'Nano (< 10K abonnés)'),
        ('micro',   'Micro (10K–100K)'),
        ('macro',   'Macro (100K–1M)'),
        ('mega',    'Méga (> 1M)'),
    ]
 
    influenceur         = models.OneToOneField('apps_core.Utilisateur', on_delete=models.CASCADE,
                                                related_name='programme_influenceur')
    niveau              = models.CharField(max_length=10, choices=NIVEAU_CHOICES, default='nano')
    taux_commission     = models.DecimalField(max_digits=5, decimal_places=2, default=5,
                                               help_text="% de commission sur les ventes générées")
    code_parrainage     = models.CharField(max_length=50, unique=True)
    lien_affiliation    = models.URLField(blank=True)
 
    # Statistiques
    nb_clics            = models.PositiveIntegerField(default=0)
    nb_conversions      = models.PositiveIntegerField(default=0)
    chiffre_affaires_genere = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    commissions_gagnees = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    commissions_payees  = models.DecimalField(max_digits=12, decimal_places=2, default=0)
 
    statut              = models.CharField(max_length=15, choices=STATUT_CHOICES, default='candidature')
    date_adhesion       = models.DateTimeField(auto_now_add=True)
    date_validation     = models.DateTimeField(null=True, blank=True)
 
    class Meta:
        verbose_name = "Programme influenceur"
        db_table = 'social_programme_influenceur'
 
    def __str__(self):
        return f"Influenceur {self.influenceur.username} ({self.get_niveau_display()})"
 
    def commissions_en_attente(self):
        return self.commissions_gagnees - self.commissions_payees
 
 
class ConversionInfluenceur(models.Model):
    """Traçabilité des conversions via un influenceur"""
    influenceur         = models.ForeignKey(ProgrammeInfluenceur, on_delete=models.CASCADE,
                                             related_name='conversions')
    utilisateur_converti = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE)
    commande            = models.ForeignKey('apps_marketplace.Commande', on_delete=models.CASCADE)
    montant_commande    = models.DecimalField(max_digits=12, decimal_places=2)
    commission_gagnee   = models.DecimalField(max_digits=10, decimal_places=2)
    est_payee           = models.BooleanField(default=False)
    date_conversion     = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        db_table = 'social_conversion_influenceur'
 
    def __str__(self):
        return f"{self.influenceur.influenceur.username} → {self.commission_gagnee} XAF"


# =============================================================================
# SECTION 6 : PUBLICATIONS / FEED
# =============================================================================
 
class Publication(models.Model):
    """Post dans le feed social du marketplace"""
    TYPE_CHOICES = [
        ('produit',   '🛒 Mise en avant produit'),
        ('avis',      '⭐ Avis avec photo'),
        ('unboxing',  '📦 Unboxing'),
        ('tutoriel',  '📚 Tutoriel'),
        ('promo',     '🏷️ Promotion'),
        ('general',   '💬 Post général'),
    ]
 
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    auteur          = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                         related_name='publications')
    type_publication = models.CharField(max_length=15, choices=TYPE_CHOICES, default='general')
    contenu         = models.TextField(max_length=2000)
    medias          = models.ManyToManyField('MediaPublication', blank=True)
 
    # Produits tagués
    produits_tagués = models.ManyToManyField('apps_core.Produit', blank=True,related_name='publications')
 
    # Stats
    nb_likes        = models.PositiveIntegerField(default=0)
    nb_commentaires = models.PositiveIntegerField(default=0)
    nb_partages     = models.PositiveIntegerField(default=0)
    nb_vues         = models.PositiveIntegerField(default=0)
 
    est_publie      = models.BooleanField(default=True)
    date_creation   = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        ordering = ['-date_creation']
        db_table = 'social_publication'
 
    def __str__(self):
        return f"{self.auteur.username}: {self.contenu[:60]}"
 
 
class MediaPublication(models.Model):
    TYPE_MEDIA_CHOICES = [('image', 'Image'), ('video', 'Vidéo')]
    type_media  = models.CharField(max_length=10, choices=TYPE_MEDIA_CHOICES)
    fichier     = models.FileField(upload_to='publications/%Y/%m/')
    ordre       = models.PositiveIntegerField(default=0)
 
    class Meta:
        db_table = 'social_media_publication'
 
 
class LikePublication(models.Model):
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE, related_name='likes')
    utilisateur = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE)
    date_like   = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        unique_together = ['publication', 'utilisateur']
        db_table = 'social_like_publication'
 
 
class CommentairePublication(models.Model):
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE, related_name='commentaires')
    auteur      = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE)
    contenu     = models.TextField(max_length=500)
    parent      = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE,
                                     related_name='reponses')
    nb_likes    = models.PositiveIntegerField(default=0)
    date_creation = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        ordering = ['date_creation']
        db_table = 'social_commentaire_publication'
 
    def __str__(self):
        return f"{self.auteur.username}: {self.contenu[:50]}"



 
 
 
 