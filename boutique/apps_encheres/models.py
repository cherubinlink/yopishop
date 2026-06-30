# ===========================================================================
# app_enchere/models.py
# Application : Système d'Enchères Avancé
# Inclut : Smart Bid IA, Flash, Vidéo Live, Groupe, Inversée,
#          Battle Auction, Sociales, Gamifiées, Estimation IA
# ===========================================================================
 
from django.db import models, transaction
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP
import uuid


# =============================================================================
# SECTION 1 : ENCHÈRE DE BASE
# =============================================================================
 
class Enchere(models.Model):
    """
    Enchère principale — supporte tous les types innovants.
    """
    TYPE_CHOICES = [
        ('classique',   'Classique'),
        ('flash',       '⚡ Flash (durée limitée)'),
        ('video_live',  '📹 Vidéo Live'),
        ('groupe',      '👥 Groupe (lot partageable)'),
        ('inversee',    '🔄 Inversée (vendeurs en compétition)'),
        ('battle',      '⚔️ Battle Auction (2 produits vs)'),
        ('services',    '🔧 Services / Projets'),
        ('stock_entier', '📦 Stock entier (B2B)'),
        ('objectif',    '🎯 À objectif'),
    ]
    STATUT_CHOICES = [
        ('a_venir',   'À venir'),
        ('en_cours',  '🔴 En cours'),
        ('terminee',  '✅ Terminée'),
        ('annulee',   '❌ Annulée'),
        ('prolongee', '⏳ Prolongée'),
    ]
 
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    produit         = models.OneToOneField('apps_core.Produit', on_delete=models.CASCADE,
                                            related_name='enchere', null=True, blank=True)
    vendeur         = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                         related_name='encheres_vendeur')
    type_enchere    = models.CharField(max_length=20, choices=TYPE_CHOICES, default='classique')
 
    titre           = models.CharField(max_length=200)
    description     = models.TextField()
    image_couverture = models.ImageField(upload_to='encheres/couvertures/', null=True, blank=True)
 
    # Prix
    prix_depart         = models.DecimalField(max_digits=12, decimal_places=2)
    prix_reserve        = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                               help_text="Prix minimum secret")
    prix_actuel         = models.DecimalField(max_digits=12, decimal_places=2)
    prix_achat_immediat = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    prix_achat_immediat_initial = models.DecimalField(max_digits=12, decimal_places=2,
                                                       null=True, blank=True, editable=False)
    devise              = models.CharField(max_length=10, default='XAF')
 
    # Dates
    date_debut  = models.DateTimeField()
    date_fin    = models.DateTimeField()
 
    # Paramètres
    increment_minimum       = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('500'))
    extension_automatique   = models.BooleanField(default=True,
                                                   help_text="Prolonge si enchère dans les 30 dernières secondes")
    duree_extension_secondes = models.PositiveIntegerField(default=30,
                                                            help_text="Secondes ajoutées lors d'une extension")
    nb_prolongations        = models.PositiveIntegerField(default=0)
    nb_prolongations_max    = models.PositiveIntegerField(default=10)
 
    statut      = models.CharField(max_length=15, choices=STATUT_CHOICES, default='a_venir')
    gagnant     = models.ForeignKey('apps_core.Utilisateur', null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name='encheres_gagnees')
 
    # Objectif (type objectif)
    montant_objectif    = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    action_si_non_atteint = models.CharField(max_length=20, default='annuler',
                                              choices=[
                                                  ('annuler',   'Annuler'),
                                                  ('prolonger', 'Prolonger automatiquement'),
                                                  ('vente_directe', 'Basculer en vente directe'),
                                              ])
 
    # Estimation IA
    prix_estime_ia  = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                           verbose_name="Prix estimé par l'IA")
    facteurs_estimation = models.JSONField(default=dict, blank=True,
                                            help_text="Facteurs pris en compte par l'IA")
 
    # Gamification
    points_participation    = models.PositiveIntegerField(default=5,
                                                           help_text="Points gagnés en enchérissant")
    points_victoire         = models.PositiveIntegerField(default=50)
 
    # Stats sociales
    nb_vues         = models.PositiveIntegerField(default=0)
    nb_likes        = models.PositiveIntegerField(default=0)
    nb_partages     = models.PositiveIntegerField(default=0)
    nb_offres       = models.PositiveIntegerField(default=0)
 
    # Live stream associé
    live            = models.ForeignKey('apps_social.LiveVente', null=True, blank=True,
                                         on_delete=models.SET_NULL, related_name='encheres_live')
 
    date_creation   = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
 
    class Meta:
        verbose_name = "Enchère"
        ordering = ['-date_creation']
        db_table = 'enchere_enchere'
 
    def __str__(self):
        return f"[{self.get_type_enchere_display()}] {self.titre}"
 
    def est_active(self):
        now = timezone.now()
        return self.statut == 'en_cours' and self.date_debut <= now <= self.date_fin
 
    def save(self, *args, **kwargs):
        if not self.pk and self.prix_achat_immediat:
            self.prix_achat_immediat_initial = self.prix_achat_immediat
        super().save(*args, **kwargs)
 
    def mettre_a_jour_prix(self, nouveau_prix):
        """Met à jour le prix actuel et ajuste le prix d'achat immédiat si dépassé"""
        self.prix_actuel = nouveau_prix
        self.nb_offres += 1
        if self.prix_achat_immediat and nouveau_prix >= self.prix_achat_immediat:
            self.prix_achat_immediat = nouveau_prix + Decimal('10000')
        self.save()
 
    def verifier_extension(self):
        """Prolonge l'enchère si une offre vient d'être placée dans les dernières secondes"""
        if not self.extension_automatique:
            return False
        if self.nb_prolongations >= self.nb_prolongations_max:
            return False
        secondes_restantes = (self.date_fin - timezone.now()).total_seconds()
        if 0 < secondes_restantes <= self.duree_extension_secondes:
            from datetime import timedelta
            self.date_fin += timedelta(seconds=self.duree_extension_secondes)
            self.nb_prolongations += 1
            self.statut = 'prolongee'
            self.save()
            return True
        return False
 
    def terminer(self):
        """Finalise l'enchère et crée la commande du gagnant"""
        if self.statut in ['terminee', 'annulee']:
            return
        self.statut = 'terminee'
        meilleure = self.offres.order_by('-montant', '-date_creation').first()
        if meilleure:
            self.gagnant = meilleure.encherisseur
        self.save()
        if self.gagnant and self.produit:
            self._creer_commande_gagnant()
 
    @transaction.atomic
    def _creer_commande_gagnant(self):
        from apps_marketplace.models import Commande, ArticleCommande
        existe = Commande.objects.filter(
            articles__enchere=self, utilisateur=self.gagnant
        ).exists()
        if existe:
            return
        commande = Commande.objects.create(
            utilisateur=self.gagnant,
            source='enchere',
            adresse_facturation='À compléter',
            adresse_livraison='À compléter',
            sous_total=self.prix_actuel,
            montant_total=self.prix_actuel,
            frais_livraison=Decimal('0'),
        )
        ArticleCommande.objects.create(
            commande=commande, produit=self.produit,
            quantite=1, prix_unitaire=self.prix_actuel,
            prix_total=self.prix_actuel, enchere=self,
        )
        return commande


# =============================================================================
# SECTION 2 : OFFRES D'ENCHÈRES
# =============================================================================
 
class OffreEnchere(models.Model):
    """Offre placée sur une enchère (manuelle ou automatique via IA)"""
    enchere         = models.ForeignKey(Enchere, related_name='offres', on_delete=models.CASCADE)
    encherisseur    = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                         related_name='offres_enchere')
    montant         = models.DecimalField(max_digits=12, decimal_places=2)
 
    # Smart Bid IA
    est_offre_auto  = models.BooleanField(default=False,
                                           verbose_name="Offre automatique (Smart Bid)")
    montant_max_auto = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                            help_text="Budget max pour le Smart Bid")
    budget_journalier = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    priorite_achat  = models.PositiveIntegerField(default=5,
                                                   validators=[MinValueValidator(1)],
                                                   help_text="1=basse, 10=haute")
 
    # Achat immédiat
    est_achat_immediat = models.BooleanField(default=False)
 
    date_creation   = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        ordering = ['-montant', '-date_creation']
        unique_together = ['enchere', 'encherisseur', 'montant']
        db_table = 'enchere_offre'
 
    def __str__(self):
        type_offre = "🤖 Auto" if self.est_offre_auto else "👤 Manuel"
        return f"{type_offre} — {self.encherisseur.username}: {self.montant} XAF"
 
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.enchere.mettre_a_jour_prix(self.montant)
        self.enchere.verifier_extension()
 
 
class ConfigSmartBid(models.Model):
    """
    Configuration du Smart Bid IA pour un utilisateur sur une enchère.
    L'IA enchérit automatiquement de façon progressive pour éviter de surpayer.
    """
    utilisateur     = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                         related_name='smart_bids')
    enchere         = models.ForeignKey(Enchere, on_delete=models.CASCADE,
                                         related_name='smart_bids')
    prix_max        = models.DecimalField(max_digits=12, decimal_places=2,
                                          verbose_name="Budget maximum absolu")
    budget_journalier = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    priorite        = models.PositiveIntegerField(default=5)
    strategie       = models.CharField(max_length=20, default='progressive',
                                        choices=[
                                            ('progressive', 'Progressive (évite surpayer)'),
                                            ('aggressive',  'Agressive (s\'impose rapidement)'),
                                            ('last_second', 'Dernière seconde (snipe)'),
                                        ])
    est_active      = models.BooleanField(default=True)
    depense_jour    = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    date_activation = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        unique_together = ['utilisateur', 'enchere']
        verbose_name = "Config Smart Bid"
        db_table = 'enchere_config_smart_bid'
 
    def __str__(self):
        return f"SmartBid {self.utilisateur.username} sur {self.enchere.titre} (max: {self.prix_max})"
 
    def peut_encherir(self, prix_actuel):
        """Vérifie si le Smart Bid peut encore enchérir"""
        if not self.est_active:
            return False
        prochain = prix_actuel + self.enchere.increment_minimum
        if prochain > self.prix_max:
            return False
        if self.budget_journalier and self.depense_jour >= self.budget_journalier:
            return False
        return True
 
    def calculer_prochain_montant(self, prix_actuel):
        """Calcule le montant optimal selon la stratégie IA"""
        increment = self.enchere.increment_minimum
        if self.strategie == 'progressive':
            # Enchérit au minimum nécessaire
            return prix_actuel + increment
        elif self.strategie == 'aggressive':
            # Enchérit plus haut pour décourager
            return min(prix_actuel + increment * 3, self.prix_max)
        elif self.strategie == 'last_second':
            # N'enchérit que dans les 60 dernières secondes
            secondes_restantes = (self.enchere.date_fin - timezone.now()).total_seconds()
            if secondes_restantes <= 60:
                return min(prix_actuel + increment, self.prix_max)
            return None
        return prix_actuel + increment


# =============================================================================
# SECTION 3 : ENCHÈRE FLASH
# =============================================================================
 
class EnchereFlash(models.Model):
    """
    Enchère flash avec timer géant et extension automatique.
    Durées : 5 min, 10 min, 30 min, 1h.
    """
    DUREE_CHOICES = [
        (5,   '⚡ 5 minutes'),
        (10,  '⚡ 10 minutes'),
        (30,  '⚡ 30 minutes'),
        (60,  '⚡ 1 heure'),
        (120, '⚡ 2 heures'),
    ]
 
    enchere         = models.OneToOneField(Enchere, on_delete=models.CASCADE,
                                            related_name='config_flash')
    duree_minutes   = models.PositiveIntegerField(choices=DUREE_CHOICES, default=30)
    extension_par_offre_secondes = models.PositiveIntegerField(default=30,
                                    help_text="Secondes ajoutées à chaque offre dans la dernière minute")
    afficher_timer_geant = models.BooleanField(default=True)
    couleur_urgence = models.CharField(max_length=7, default='#FF0000',
                                        help_text="Couleur du timer quand < 60s")
    nb_acheteurs_max = models.PositiveIntegerField(null=True, blank=True,
                                                    help_text="Limite optionnelle de participants")
 
    class Meta:
        verbose_name = "Config Enchère Flash"
        db_table = 'enchere_flash'
 
    def __str__(self):
        return f"Flash {self.duree_minutes}min — {self.enchere.titre}"
 


# =============================================================================
# SECTION 4 : ENCHÈRE EN GROUPE
# =============================================================================
 
class EnchereGroupe(models.Model):
    """
    Plusieurs personnes se partagent un lot.
    Ex : 100 cartons partagés entre 5 acheteurs.
    """
    enchere         = models.OneToOneField(Enchere, on_delete=models.CASCADE,
                                            related_name='config_groupe')
    quantite_totale = models.PositiveIntegerField(help_text="Quantité totale du lot")
    quantite_min_par_participant = models.PositiveIntegerField(default=1)
    quantite_max_par_participant = models.PositiveIntegerField(null=True, blank=True)
    nb_participants_min = models.PositiveIntegerField(default=2)
    nb_participants_max = models.PositiveIntegerField(null=True, blank=True)
 
    class Meta:
        verbose_name = "Config Enchère Groupe"
        db_table = 'enchere_groupe_config'
 
    def __str__(self):
        return f"Groupe {self.quantite_totale} unités — {self.enchere.titre}"
 
 
class ParticipantEnchereGroupe(models.Model):
    """Participant à une enchère de groupe"""
    enchere_groupe  = models.ForeignKey(EnchereGroupe, on_delete=models.CASCADE,
                                         related_name='participants')
    utilisateur     = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE)
    quantite_souhaitee = models.PositiveIntegerField(default=1)
    montant_offert  = models.DecimalField(max_digits=12, decimal_places=2)
    a_confirme      = models.BooleanField(default=False)
    commande        = models.ForeignKey('apps_marketplace.Commande', null=True, blank=True,
                                         on_delete=models.SET_NULL)
    date_adhesion   = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        unique_together = ['enchere_groupe', 'utilisateur']
        db_table = 'enchere_participant_groupe'
 
    def __str__(self):
        return f"{self.utilisateur.username} — {self.quantite_souhaitee} unités"


# =============================================================================
# SECTION 5 : ENCHÈRE INVERSÉE
# =============================================================================
 
class AppelOffre(models.Model):
    """
    Enchère inversée — le client publie un besoin,
    les vendeurs proposent leurs prix (le plus bas gagne).
    """
    STATUT_CHOICES = [
        ('ouvert',    'Ouvert aux offres'),
        ('ferme',     'Fermé'),
        ('adjuge',    'Adjugé'),
        ('annule',    'Annulé'),
    ]
 
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    acheteur        = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                         related_name='appels_offre')
    titre           = models.CharField(max_length=200)
    description     = models.TextField()
    categorie       = models.ForeignKey('apps_core.Categorie', on_delete=models.CASCADE)
    budget_max      = models.DecimalField(max_digits=12, decimal_places=2)
    specifications  = models.JSONField(default=dict, help_text="Specs techniques JSON")
    quantite        = models.PositiveIntegerField(default=1)
    est_b2b         = models.BooleanField(default=False)
 
    date_limite     = models.DateTimeField()
    statut          = models.CharField(max_length=15, choices=STATUT_CHOICES, default='ouvert')
    offre_gagnante  = models.ForeignKey('OffreVendeur', null=True, blank=True,
                                         on_delete=models.SET_NULL, related_name='appels_gagnes')
 
    date_creation   = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        verbose_name = "Appel d'offre"
        ordering = ['-date_creation']
        db_table = 'enchere_appel_offre'
 
    def __str__(self):
        return f"AO: {self.titre} (budget: {self.budget_max} XAF)"
 
    def meilleure_offre(self):
        return self.offres_vendeurs.order_by('montant').first()
 
 
class OffreVendeur(models.Model):
    """Offre d'un vendeur en réponse à un appel d'offre"""
    appel_offre     = models.ForeignKey(AppelOffre, on_delete=models.CASCADE,
                                         related_name='offres_vendeurs')
    vendeur         = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                         related_name='offres_vendeur')
    montant         = models.DecimalField(max_digits=12, decimal_places=2)
    description     = models.TextField()
    delai_livraison = models.PositiveIntegerField(help_text="Jours")
    garantie        = models.CharField(max_length=100, blank=True)
    pieces_jointes  = models.FileField(upload_to='offres_vendeurs/', null=True, blank=True)
    est_selectionnee = models.BooleanField(default=False)
    date_soumission = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        unique_together = ['appel_offre', 'vendeur']
        ordering = ['montant']
        db_table = 'enchere_offre_vendeur'
 
    def __str__(self):
        return f"{self.vendeur.username}: {self.montant} XAF"


# =============================================================================
# SECTION 6 : BATTLE AUCTION
# =============================================================================
 
class BattleAuction(models.Model):
    """
    Deux produits similaires en compétition simultanée.
    Ex : Samsung S25 VS iPhone 18.
    Les utilisateurs choisissent un camp et enchérissent.
    """
    STATUT_CHOICES = [
        ('a_venir',  'À venir'),
        ('en_cours', 'En cours'),
        ('termine',  'Terminé'),
    ]
 
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    titre           = models.CharField(max_length=200)
    description     = models.TextField(blank=True)
 
    enchere_a       = models.ForeignKey(Enchere, on_delete=models.CASCADE,
                                         related_name='battle_camp_a')
    enchere_b       = models.ForeignKey(Enchere, on_delete=models.CASCADE,
                                         related_name='battle_camp_b')
 
    nom_camp_a      = models.CharField(max_length=100, default='Camp A')
    nom_camp_b      = models.CharField(max_length=100, default='Camp B')
    couleur_camp_a  = models.CharField(max_length=7, default='#0066FF')
    couleur_camp_b  = models.CharField(max_length=7, default='#FF3300')
 
    date_debut      = models.DateTimeField()
    date_fin        = models.DateTimeField()
    statut          = models.CharField(max_length=15, choices=STATUT_CHOICES, default='a_venir')
 
    # Votes / supporters (sans enchère)
    nb_supporters_a = models.PositiveIntegerField(default=0)
    nb_supporters_b = models.PositiveIntegerField(default=0)
 
    date_creation   = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        verbose_name = "Battle Auction"
        db_table = 'enchere_battle_auction'
 
    def __str__(self):
        return f"⚔️ {self.nom_camp_a} VS {self.nom_camp_b}"
 
    def camp_gagnant(self):
        if self.statut != 'termine':
            return None
        if self.enchere_a.prix_actuel >= self.enchere_b.prix_actuel:
            return 'a'
        return 'b'
 
 
class SupportBattle(models.Model):
    """Un utilisateur choisit son camp dans un Battle Auction"""
    battle      = models.ForeignKey(BattleAuction, on_delete=models.CASCADE,
                                     related_name='supports')
    utilisateur = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE)
    camp        = models.CharField(max_length=1, choices=[('a', 'Camp A'), ('b', 'Camp B')])
    date_choix  = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        unique_together = ['battle', 'utilisateur']
        db_table = 'enchere_support_battle'
 
    def __str__(self):
        return f"{self.utilisateur.username} soutient Camp {self.camp.upper()}"
 


# =============================================================================
# SECTION 7 : ENCHÈRE SOCIALE
# =============================================================================
 
class InteractionSocialeEnchere(models.Model):
    """Likes, partages, commentaires sur une enchère"""
    TYPE_CHOICES = [
        ('like',      '❤️ Like'),
        ('partage',   '🔗 Partage'),
        ('commentaire', '💬 Commentaire'),
    ]
 
    enchere         = models.ForeignKey(Enchere, on_delete=models.CASCADE,
                                         related_name='interactions_sociales')
    utilisateur     = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE)
    type_interaction = models.CharField(max_length=15, choices=TYPE_CHOICES)
    contenu         = models.TextField(blank=True, help_text="Pour les commentaires")
    plateforme_partage = models.CharField(max_length=50, blank=True,
                                           help_text="WhatsApp, Facebook, etc.")
    date_creation   = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        db_table = 'enchere_interaction_sociale'
 
    def __str__(self):
        return f"{self.utilisateur.username} — {self.get_type_interaction_display()} — {self.enchere.titre}"
 

# =============================================================================
# SECTION 8 : GAMIFICATION DES ENCHÈRES
# =============================================================================
 
class ClassementEncherisseur(models.Model):
    """Classement hebdomadaire / mensuel des enchérisseurs"""
    PERIODE_CHOICES = [
        ('semaine',  'Cette semaine'),
        ('mois',     'Ce mois'),
        ('total',    'Tout temps'),
    ]
 
    utilisateur         = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                             related_name='classements_enchere')
    periode             = models.CharField(max_length=10, choices=PERIODE_CHOICES)
    annee               = models.PositiveIntegerField()
    numero_periode      = models.PositiveIntegerField(help_text="Numéro de semaine ou mois")
    rang                = models.PositiveIntegerField()
    nb_encheres         = models.PositiveIntegerField(default=0)
    nb_victoires        = models.PositiveIntegerField(default=0)
    montant_total_enchere = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    points_gagnes       = models.PositiveIntegerField(default=0)
    trophee             = models.CharField(max_length=50, blank=True,
                                            help_text="Trophée attribué (top 3)")
 
    class Meta:
        unique_together = ['utilisateur', 'periode', 'annee', 'numero_periode']
        ordering = ['rang']
        db_table = 'enchere_classement'
 
    def __str__(self):
        return f"Rang #{self.rang} — {self.utilisateur.username} ({self.get_periode_display()})"
 
 
class SuccesEnchere(models.Model):
    """Succès / badges débloqués via les enchères"""
    utilisateur     = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                         related_name='succes_enchere')
    type_succes     = models.CharField(max_length=50)
    titre           = models.CharField(max_length=100)
    description     = models.CharField(max_length=300)
    icone           = models.CharField(max_length=10, default='🏆')
    points_bonus    = models.PositiveIntegerField(default=0)
    date_obtention  = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        db_table = 'enchere_succes'
 
    def __str__(self):
        return f"{self.icone} {self.titre} — {self.utilisateur.username}"
 


# =============================================================================
# SECTION 9 : ESTIMATION IA DES PRIX
# =============================================================================
 
class EstimationPrixIA(models.Model):
    """
    Estimation du juste prix par l'IA avant mise aux enchères.
    Basée sur : historique, état, marché, demande.
    """
    produit             = models.ForeignKey('apps_core.Produit', on_delete=models.CASCADE,
                                             related_name='estimations_ia')
    prix_estime         = models.DecimalField(max_digits=12, decimal_places=2)
    prix_min_suggere    = models.DecimalField(max_digits=12, decimal_places=2)
    prix_max_suggere    = models.DecimalField(max_digits=12, decimal_places=2)
 
    # Facteurs d'estimation
    prix_moyen_marche   = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    prix_moyen_encheres_historiques = models.DecimalField(max_digits=12, decimal_places=2,
                                                           null=True, blank=True)
    score_demande       = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                               help_text="0-10 : demande actuelle")
    facteur_etat        = models.DecimalField(max_digits=5, decimal_places=2, default=1.0,
                                               help_text="Multiplicateur selon état du produit")
    tendance_marche     = models.CharField(max_length=20, default='stable',
                                            choices=[
                                                ('hausse',  'En hausse'),
                                                ('stable',  'Stable'),
                                                ('baisse',  'En baisse'),
                                            ])
    confiance_estimation = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                                help_text="% de confiance de l'IA (0-100)")
    explication         = models.TextField(blank=True, help_text="Explication lisible de l'estimation")
 
    date_estimation     = models.DateTimeField(auto_now_add=True)
    version_modele_ia   = models.CharField(max_length=50, default='v1.0')
 
    class Meta:
        verbose_name = "Estimation IA"
        ordering = ['-date_estimation']
        db_table = 'enchere_estimation_ia'
 
    def __str__(self):
        return f"Estimation IA: {self.prix_estime} XAF — {self.produit.titre}"
 

# =============================================================================
# SECTION 10 : COMMENTAIRES ENCHÈRES
# =============================================================================
 
class CommentaireEnchere(models.Model):
    enchere         = models.ForeignKey(Enchere, related_name='commentaires',
                                         on_delete=models.CASCADE)
    utilisateur     = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE)
    contenu         = models.TextField(max_length=500)
    est_epingle     = models.BooleanField(default=False)
    parent          = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE,
                                         related_name='reponses')
    nb_likes        = models.PositiveIntegerField(default=0)
    date_creation   = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        ordering = ['-date_creation']
        db_table = 'enchere_commentaire'
 
    def __str__(self):
        return f"{self.utilisateur.username}: {self.contenu[:50]}"
 
 