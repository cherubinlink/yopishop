# ===========================================================================
# app_ia/models.py
# Application : Intelligence Artificielle
# Inclut : Assistant IA, Comparateur, Anti-Fraude, Prévision stocks
# ===========================================================================
 
from django.db import models
from django.utils import timezone
import uuid


class SessionAssistantIA(models.Model):
    """Conversation avec l'assistant IA d'achat"""
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    utilisateur     = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                         related_name='sessions_ia', null=True, blank=True)
    cle_session     = models.CharField(max_length=255, blank=True)
    contexte        = models.JSONField(default=dict, help_text="Préférences, historique de la session")
    date_creation   = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
 
    class Meta:
        db_table = 'ia_session_assistant'
 
    def __str__(self):
        user = self.utilisateur.username if self.utilisateur else 'Anonyme'
        return f"Session IA — {user}"
 
 
class MessageAssistantIA(models.Model):
    """Message échangé avec l'assistant IA"""
    ROLE_CHOICES = [('user', 'Utilisateur'), ('assistant', 'Assistant IA')]
 
    session     = models.ForeignKey(SessionAssistantIA, on_delete=models.CASCADE,
                                     related_name='messages')
    role        = models.CharField(max_length=10, choices=ROLE_CHOICES)
    contenu     = models.TextField()
 
    # Produits recommandés par l'IA dans la réponse
    produits_recommandes = models.ManyToManyField('apps_core.Produit', blank=True,
                                                   related_name='recommandations_ia')
    action_detectee = models.CharField(max_length=50, blank=True,
                                        help_text="Ex: recherche, comparaison, negociation")
    donnees_action  = models.JSONField(default=dict, blank=True)
 
    tokens_utilises = models.PositiveIntegerField(default=0)
    date_creation   = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        ordering = ['date_creation']
        db_table = 'ia_message_assistant'
 
    def __str__(self):
        return f"[{self.role}] {self.contenu[:60]}"
 
 
class ComparaisonPrix(models.Model):
    """Résultat d'une comparaison intelligente entre vendeurs"""
    produit_recherche   = models.CharField(max_length=200)
    utilisateur         = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                             null=True, blank=True)
    resultats           = models.JSONField(default=list,
                                            help_text="Liste des offres comparées avec scores")
    meilleur_produit    = models.ForeignKey('apps_core.Produit', null=True, blank=True,
                                             on_delete=models.SET_NULL, related_name='meilleures_comparaisons')
    criteres            = models.JSONField(default=dict,
                                            help_text="Critères utilisés: prix, livraison, garantie, avis")
    date_creation       = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        db_table = 'ia_comparaison_prix'
 
    def __str__(self):
        return f"Comparaison: {self.produit_recherche}"
 
 
class AlerteFraude(models.Model):
    """Alerte levée par l'IA anti-fraude"""
    TYPE_CHOICES = [
        ('faux_vendeur',        'Faux vendeur détecté'),
        ('faux_avis',           'Faux avis détecté'),
        ('commande_suspecte',   'Commande suspecte'),
        ('paiement_suspect',    'Paiement suspect'),
        ('compte_suspect',      'Compte suspect'),
        ('prix_anormal',        'Prix anormalement bas'),
    ]
    STATUT_CHOICES = [
        ('ouverte',     'Ouverte'),
        ('en_cours',    'En cours de traitement'),
        ('resolue',     'Résolue'),
        ('fausse_alerte', 'Fausse alerte'),
    ]
 
    type_alerte         = models.CharField(max_length=25, choices=TYPE_CHOICES)
    utilisateur_suspect = models.ForeignKey('apps_core.Utilisateur', null=True, blank=True,
                                             on_delete=models.SET_NULL, related_name='alertes_fraude')
    produit_suspect     = models.ForeignKey('apps_core.Produit', null=True, blank=True,
                                             on_delete=models.SET_NULL)
    commande_suspecte   = models.ForeignKey('apps_marketplace.Commande', null=True, blank=True,
                                             on_delete=models.SET_NULL)
    paiement_suspect    = models.ForeignKey('apps_marketplace.Paiement', null=True, blank=True,
                                             on_delete=models.SET_NULL)
 
    score_risque        = models.DecimalField(max_digits=5, decimal_places=2,
                                               help_text="0=sûr, 100=très risqué")
    signaux_detectes    = models.JSONField(default=list,
                                           help_text="Liste des signaux suspects détectés par l'IA")
    description         = models.TextField()
 
    statut              = models.CharField(max_length=15, choices=STATUT_CHOICES, default='ouverte')
    traite_par          = models.ForeignKey('apps_core.Utilisateur', null=True, blank=True,
                                             on_delete=models.SET_NULL, related_name='alertes_traitees')
    resolution          = models.TextField(blank=True)
 
    date_creation       = models.DateTimeField(auto_now_add=True)
    date_traitement     = models.DateTimeField(null=True, blank=True)
 
    class Meta:
        verbose_name = "Alerte fraude"
        ordering = ['-score_risque', '-date_creation']
        db_table = 'ia_alerte_fraude'
 
    def __str__(self):
        return f"🚨 {self.get_type_alerte_display()} — Score: {self.score_risque}"
 
 
class PrevisionStock(models.Model):
    """Prévision IA des stocks — ruptures, pics de demande, produits populaires"""
    produit         = models.ForeignKey('apps_core.Produit', on_delete=models.CASCADE,
                                         related_name='previsions_stock')
    date_prevision  = models.DateField()
    stock_prevu     = models.IntegerField()
    ventes_prevues  = models.PositiveIntegerField()
    probabilite_rupture = models.DecimalField(max_digits=5, decimal_places=2,
                                               help_text="% probabilité de rupture")
    niveau_alerte   = models.CharField(max_length=10, default='normal',
                                        choices=[
                                            ('critique', '🔴 Critique'),
                                            ('alerte',   '🟠 Alerte'),
                                            ('normal',   '🟢 Normal'),
                                        ])
    recommandation  = models.TextField(blank=True,
                                        help_text="Recommandation IA : commander X unités avant le JJ/MM")
    facteurs        = models.JSONField(default=dict)
    date_calcul     = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        unique_together = ['produit', 'date_prevision']
        ordering = ['-probabilite_rupture']
        db_table = 'ia_prevision_stock'
 
    def __str__(self):
        return f"Prévision {self.produit.titre} — {self.date_prevision}"
 
 
class RecommandationProduit(models.Model):
    """Recommandations personnalisées IA par utilisateur"""
    utilisateur     = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                         related_name='recommandations')
    produits        = models.ManyToManyField('apps_core.Produit', through='ScoreRecommandation')
    contexte        = models.CharField(max_length=50, default='accueil',
                                        choices=[
                                            ('accueil',         'Page d\'accueil'),
                                            ('produit',         'Page produit (similaires)'),
                                            ('panier',          'Panier (compléments)'),
                                            ('post_achat',      'Post-achat'),
                                            ('email',           'Email marketing'),
                                        ])
    date_generation = models.DateTimeField(auto_now_add=True)
    est_active      = models.BooleanField(default=True)
 
    class Meta:
        db_table = 'ia_recommandation_produit'
 
    def __str__(self):
        return f"Reco {self.contexte} — {self.utilisateur.username}"


class ScoreRecommandation(models.Model):
    recommandation  = models.ForeignKey(RecommandationProduit, on_delete=models.CASCADE)
    produit         = models.ForeignKey('apps_core.Produit', on_delete=models.CASCADE)
    score           = models.DecimalField(max_digits=5, decimal_places=4)
    raison          = models.CharField(max_length=200, blank=True)
    rang            = models.PositiveIntegerField(default=1)
 
    class Meta:
        ordering = ['rang']
        db_table = 'ia_score_recommandation'
 
 
# ===========================================================================
# app_fulfillment/models.py
# Application : YopiFulfillment (inspiré Amazon FBA)
# ===========================================================================
 
class EntrepotYopi(models.Model):
    """Entrepôt YopiShop gérant le stockage des vendeurs"""
    nom         = models.CharField(max_length=200)
    adresse     = models.TextField()
    ville       = models.ForeignKey('apps_core.Ville', on_delete=models.PROTECT,
                                     related_name='entrepots')
    capacite_m2 = models.DecimalField(max_digits=10, decimal_places=2)
    capacite_unite = models.PositiveIntegerField(help_text="Nombre max d'unités stockables")
    est_actif   = models.BooleanField(default=True)
    responsable = models.ForeignKey('apps_core.Utilisateur', on_delete=models.SET_NULL,
                                     null=True, related_name='entrepots_geres')
    date_creation = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        db_table = 'fulfillment_entrepot'
 
    def __str__(self):
        return f"Entrepôt {self.nom} — {self.ville.nom}"
 
 
class StockFulfillment(models.Model):
    """Stock d'un vendeur dans un entrepôt YopiShop"""
    STATUT_CHOICES = [
        ('en_transit',   'En transit vers entrepôt'),
        ('receptionne',  'Réceptionné'),
        ('disponible',   'Disponible à la vente'),
        ('reserve',      'Réservé pour commande'),
        ('en_retour',    'En cours de retour vendeur'),
    ]
 
    vendeur     = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                     related_name='stocks_fulfillment')
    produit     = models.ForeignKey('apps_core.Produit', on_delete=models.CASCADE,
                                     related_name='stocks_fulfillment')
    entrepot    = models.ForeignKey(EntrepotYopi, on_delete=models.CASCADE,
                                     related_name='stocks')
    quantite    = models.PositiveIntegerField()
    emplacement = models.CharField(max_length=50, blank=True,
                                    help_text="Allée-Étagère-Case ex: A3-E2-C5")
    statut      = models.CharField(max_length=15, choices=STATUT_CHOICES, default='disponible')
 
    # Tarification stockage
    frais_stockage_mensuel = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    date_entree     = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
 
    class Meta:
        unique_together = ['produit', 'entrepot', 'vendeur']
        db_table = 'fulfillment_stock'
 
    def __str__(self):
        return f"{self.produit.titre} — {self.quantite} unités — {self.entrepot.nom}"
 
 
class ExpeditionFulfillment(models.Model):
    """Expédition gérée par YopiFulfillment"""
    STATUT_CHOICES = [
        ('en_attente',      'En attente'),
        ('en_preparation',  'En préparation'),
        ('emballe',         'Emballé'),
        ('expedie',         'Expédié'),
        ('livre',           'Livré'),
    ]
 
    commande        = models.ForeignKey('apps_marketplace.Commande', on_delete=models.CASCADE,
                                         related_name='expedition_fulfillment')
    entrepot        = models.ForeignKey(EntrepotYopi, on_delete=models.CASCADE)
    statut          = models.CharField(max_length=15, choices=STATUT_CHOICES, default='en_attente')
    agent_entrepot  = models.ForeignKey('apps_core.Utilisateur', null=True, blank=True,
                                         on_delete=models.SET_NULL)
    numero_suivi    = models.CharField(max_length=100, blank=True)
    frais_expedition = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    date_prise_en_charge = models.DateTimeField(null=True, blank=True)
    date_expedition = models.DateTimeField(null=True, blank=True)
    date_livraison  = models.DateTimeField(null=True, blank=True)
    notes           = models.TextField(blank=True)
 
    class Meta:
        db_table = 'fulfillment_expedition'
 
    def __str__(self):
        return f"Expédition FF — {self.commande.numero_commande}"


class EnvoiStockVendeur(models.Model):
    """Envoi de stock par un vendeur vers un entrepôt YopiFulfillment"""
    STATUT_CHOICES = [
        ('planifie',        'Planifié'),
        ('en_transit',      'En transit'),
        ('receptionne',     'Réceptionné'),
        ('controle',        'Contrôle qualité'),
        ('accepte',         'Accepté et mis en stock'),
        ('rejete',          'Rejeté'),
    ]
 
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendeur     = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                     related_name='envois_stock')
    entrepot    = models.ForeignKey(EntrepotYopi, on_delete=models.CASCADE)
    statut      = models.CharField(max_length=15, choices=STATUT_CHOICES, default='planifie')
    articles    = models.JSONField(default=list,
                                    help_text="[{produit_id, quantite, reference}]")
    nb_unites_total = models.PositiveIntegerField(default=0)
    numero_bon  = models.CharField(max_length=50, unique=True)
    date_envoi  = models.DateTimeField(null=True, blank=True)
    date_reception = models.DateTimeField(null=True, blank=True)
    notes_vendeur = models.TextField(blank=True)
    notes_entrepot = models.TextField(blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        db_table = 'fulfillment_envoi_stock'
 
    def __str__(self):
        return f"Envoi {self.numero_bon} — {self.vendeur.username}"
 
# ===========================================================================
# app_gamification/models.py
# Application : Système de Récompenses et Gamification
# ===========================================================================
 
class TypeBadge(models.Model):
    """Définition des badges disponibles"""
    code        = models.CharField(max_length=50, unique=True)
    nom         = models.CharField(max_length=100)
    description = models.CharField(max_length=300)
    icone       = models.CharField(max_length=10, default='🏅')
    image       = models.ImageField(upload_to='badges/', null=True, blank=True)
    points_bonus = models.PositiveIntegerField(default=0)
    categorie   = models.CharField(max_length=30, default='general',
                                    choices=[
                                        ('achat',       'Achat'),
                                        ('enchere',     'Enchère'),
                                        ('social',      'Social'),
                                        ('vendeur',     'Vendeur'),
                                        ('fidelite',    'Fidélité'),
                                        ('special',     'Spécial'),
                                    ])
    est_actif   = models.BooleanField(default=True)
    est_secret  = models.BooleanField(default=False, help_text="Badge caché jusqu'à obtention")
 
    class Meta:
        db_table = 'gamification_type_badge'
 
    def __str__(self):
        return f"{self.icone} {self.nom}"
 
 
class BadgeUtilisateur(models.Model):
    """Badge obtenu par un utilisateur"""
    utilisateur = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                     related_name='badges')
    badge       = models.ForeignKey(TypeBadge, on_delete=models.CASCADE)
    date_obtention = models.DateTimeField(auto_now_add=True)
    raison      = models.CharField(max_length=200, blank=True)
 
    class Meta:
        unique_together = ['utilisateur', 'badge']
        db_table = 'gamification_badge_utilisateur'
 
    def __str__(self):
        return f"{self.badge.icone} {self.badge.nom} → {self.utilisateur.username}"
 
 
class TransactionPoints(models.Model):
    """Historique des points gagnés/dépensés"""
    TYPE_CHOICES = [
        ('gain_achat',      '🛒 Achat'),
        ('gain_avis',       '⭐ Avis posté'),
        ('gain_partage',    '🔗 Partage'),
        ('gain_enchere',    '⚔️ Enchère'),
        ('gain_live',       '🔴 Participation live'),
        ('gain_parrainage', '👥 Parrainage'),
        ('gain_inscription', '🎉 Inscription'),
        ('depense_reduction', '💳 Réduction panier'),
        ('expiration',      '⏰ Expiration'),
        ('bonus_badge',     '🏅 Bonus badge'),
    ]
 
    utilisateur     = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                         related_name='transactions_points')
    type_transaction = models.CharField(max_length=25, choices=TYPE_CHOICES)
    points          = models.IntegerField(help_text="Positif=gain, Négatif=dépense")
    solde_apres     = models.PositiveIntegerField(default=0)
    description     = models.CharField(max_length=300, blank=True)
    reference_id    = models.CharField(max_length=100, blank=True,
                                        help_text="ID de l'objet source (commande, avis...)")
    date_expiration = models.DateTimeField(null=True, blank=True)
    date_creation   = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        ordering = ['-date_creation']
        db_table = 'gamification_transaction_points'
 
    def __str__(self):
        signe = '+' if self.points > 0 else ''
        return f"{signe}{self.points} pts — {self.utilisateur.username}"
 
 
class Defi(models.Model):
    """Défis / missions à accomplir pour gagner des points"""
    TYPE_CHOICES = [
        ('quotidien',   '📅 Quotidien'),
        ('hebdomadaire', '📆 Hebdomadaire'),
        ('mensuel',     '🗓️ Mensuel'),
        ('special',     '⭐ Spécial'),
    ]
    STATUT_CHOICES = [
        ('actif',   'Actif'),
        ('expire',  'Expiré'),
        ('inactif', 'Inactif'),
    ]
 
    titre           = models.CharField(max_length=200)
    description     = models.TextField()
    type_defi       = models.CharField(max_length=15, choices=TYPE_CHOICES)
    icone           = models.CharField(max_length=10, default='🎯')
    points_recompense = models.PositiveIntegerField()
    badge_recompense = models.ForeignKey(TypeBadge, null=True, blank=True,
                                          on_delete=models.SET_NULL)
 
    # Condition
    type_condition  = models.CharField(max_length=50,
                                        help_text="Ex: nb_achats, montant_depense, nb_avis")
    valeur_cible    = models.PositiveIntegerField(help_text="Valeur à atteindre")
 
    statut          = models.CharField(max_length=10, choices=STATUT_CHOICES, default='actif')
    date_debut      = models.DateTimeField()
    date_fin        = models.DateTimeField()
    date_creation   = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        db_table = 'gamification_defi'
 
    def __str__(self):
        return f"{self.icone} {self.titre}"
 
 
class ProgressionDefi(models.Model):
    """Suivi de progression d'un utilisateur sur un défi"""
    utilisateur     = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                         related_name='progressions_defis')
    defi            = models.ForeignKey(Defi, on_delete=models.CASCADE,
                                         related_name='progressions')
    valeur_actuelle = models.PositiveIntegerField(default=0)
    est_complete    = models.BooleanField(default=False)
    date_completion = models.DateTimeField(null=True, blank=True)
 
    class Meta:
        unique_together = ['utilisateur', 'defi']
        db_table = 'gamification_progression_defi'
 
    def __str__(self):
        return f"{self.utilisateur.username} — {self.defi.titre}: {self.valeur_actuelle}/{self.defi.valeur_cible}"
 
    @property
    def pourcentage(self):
        if self.defi.valeur_cible == 0:
            return 100
        return min(100, int(self.valeur_actuelle / self.defi.valeur_cible * 100))
 
 
class ProgrammeParrainage(models.Model):
    """Programme de parrainage — chaque parrain gagne des points"""
    parrain         = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                         related_name='filleuls')
    filleul         = models.OneToOneField('apps_core.Utilisateur', on_delete=models.CASCADE,
                                            related_name='parrain')
    code_parrainage = models.CharField(max_length=50)
    points_parrain_gagnes = models.PositiveIntegerField(default=0)
    points_filleul_gagnes = models.PositiveIntegerField(default=0)
    premier_achat_effectue = models.BooleanField(default=False)
    date_parrainage = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        db_table = 'gamification_parrainage'
 
    def __str__(self):
        return f"{self.parrain.username} → {self.filleul.username}"
 

# ===========================================================================
# app_services/models.py
# Application : Place de Services (Fiverr style)
# ===========================================================================
 
class ServiceFreelance(models.Model):
    """Service proposé par un prestataire"""
    CATEGORIE_CHOICES = [
        ('dev_web',     '💻 Développement web'),
        ('design',      '🎨 Design graphique'),
        ('reparation',  '🔧 Réparation'),
        ('livraison',   '🚚 Livraison'),
        ('formation',   '📚 Formation'),
        ('marketing',   '📢 Marketing digital'),
        ('redaction',   '✍️ Rédaction'),
        ('photo_video', '📸 Photo / Vidéo'),
        ('autre',       '⚙️ Autre'),
    ]
    STATUT_CHOICES = [
        ('actif',    'Actif'),
        ('pause',    'En pause'),
        ('archive',  'Archivé'),
    ]
 
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    prestataire     = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                         related_name='services')
    categorie       = models.CharField(max_length=20, choices=CATEGORIE_CHOICES)
    titre           = models.CharField(max_length=200)
    slug            = models.SlugField(unique=True)
    description     = models.TextField()
    image_couverture = models.ImageField(upload_to='services/couvertures/')
 
    # Tarifs (3 niveaux : Basique, Standard, Premium)
    prix_basique    = models.DecimalField(max_digits=10, decimal_places=2)
    desc_basique    = models.TextField()
    delai_basique   = models.PositiveIntegerField(help_text="Jours")
 
    prix_standard   = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    desc_standard   = models.TextField(blank=True)
    delai_standard  = models.PositiveIntegerField(null=True, blank=True)
 
    prix_premium    = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    desc_premium    = models.TextField(blank=True)
    delai_premium   = models.PositiveIntegerField(null=True, blank=True)
 
    # Stats
    note_moyenne    = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    nb_commandes    = models.PositiveIntegerField(default=0)
    nb_avis         = models.PositiveIntegerField(default=0)
 
    statut          = models.CharField(max_length=10, choices=STATUT_CHOICES, default='actif')
    date_creation   = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        verbose_name = "Service freelance"
        ordering = ['-nb_commandes']
        db_table = 'services_service_freelance'
 
    def __str__(self):
        return f"{self.titre} — {self.prestataire.username}"
 
 
class CommandeService(models.Model):
    """Commande d'un service freelance"""
    STATUT_CHOICES = [
        ('en_attente',      'En attente de confirmation'),
        ('acceptee',        'Acceptée'),
        ('en_cours',        'En cours'),
        ('livraison',       'Livraison soumise'),
        ('revision',        'Révision demandée'),
        ('terminee',        'Terminée'),
        ('annulee',         'Annulée'),
        ('litige',          'Litige ouvert'),
    ]
    NIVEAU_CHOICES = [('basique', 'Basique'), ('standard', 'Standard'), ('premium', 'Premium')]
 
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    service         = models.ForeignKey(ServiceFreelance, on_delete=models.CASCADE,
                                         related_name='commandes')
    client          = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                         related_name='commandes_service')
    niveau          = models.CharField(max_length=10, choices=NIVEAU_CHOICES, default='basique')
    prix            = models.DecimalField(max_digits=10, decimal_places=2)
    delai_jours     = models.PositiveIntegerField()
    instructions    = models.TextField(help_text="Brief du client")
    statut          = models.CharField(max_length=15, choices=STATUT_CHOICES, default='en_attente')
    nb_revisions    = models.PositiveIntegerField(default=0)
    date_limite     = models.DateTimeField(null=True, blank=True)
    date_creation   = models.DateTimeField(auto_now_add=True)
    date_completion = models.DateTimeField(null=True, blank=True)
 
    class Meta:
        db_table = 'services_commande_service'
 
    def __str__(self):
        return f"Service: {self.service.titre} — {self.client.username}"
 
 
class LivraisonService(models.Model):
    """Fichier(s) livré(s) par le prestataire"""
    commande    = models.ForeignKey(CommandeService, on_delete=models.CASCADE,
                                     related_name='livraisons')
    message     = models.TextField()
    fichiers    = models.FileField(upload_to='livraisons_service/%Y/%m/', null=True, blank=True)
    est_finale  = models.BooleanField(default=False)
    date_envoi  = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        db_table = 'services_livraison_service'
 
    def __str__(self):
        return f"Livraison {'finale' if self.est_finale else 'partielle'} — {self.commande.id}"
 

# ===========================================================================
# app_b2b/models.py
# Application : Marketplace B2B (Grossistes, Fabricants, Distributeurs)
# ===========================================================================
 
class ProfilB2B(models.Model):
    """Profil professionnel d'une entreprise sur YopiShop B2B"""
    TYPE_CHOICES = [
        ('grossiste',       'Grossiste'),
        ('fabricant',       'Fabricant'),
        ('distributeur',    'Distributeur'),
        ('importateur',     'Importateur'),
        ('acheteur_pro',    'Acheteur professionnel'),
    ]
    STATUT_CHOICES = [
        ('en_attente', 'En attente de vérification'),
        ('verifie',    'Vérifié ✅'),
        ('suspendu',   'Suspendu'),
    ]
 
    utilisateur     = models.OneToOneField('apps_core.Utilisateur', on_delete=models.CASCADE,
                                            related_name='profil_b2b')
    type_entreprise = models.CharField(max_length=20, choices=TYPE_CHOICES)
    nom_entreprise  = models.CharField(max_length=200)
    registre_commerce = models.CharField(max_length=100)
    numero_tva      = models.CharField(max_length=50, blank=True)
    secteur_activite = models.CharField(max_length=100)
    chiffre_affaires_annuel = models.DecimalField(max_digits=15, decimal_places=2,
                                                   null=True, blank=True)
    nb_employes     = models.PositiveIntegerField(null=True, blank=True)
 
    statut          = models.CharField(max_length=15, choices=STATUT_CHOICES, default='en_attente')
    limite_credit   = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                           help_text="Limite de crédit B2B accordée")
    conditions_paiement = models.CharField(max_length=50, default='immediate',
                                            choices=[
                                                ('immediate',   'Paiement immédiat'),
                                                ('30_jours',    '30 jours'),
                                                ('60_jours',    '60 jours'),
                                                ('90_jours',    '90 jours'),
                                            ])
    date_creation   = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        verbose_name = "Profil B2B"
        db_table = 'b2b_profil'
 
    def __str__(self):
        return f"{self.nom_entreprise} ({self.get_type_entreprise_display()})"
 
 
class AppelOffreB2B(models.Model):
    """Appel d'offres B2B — entreprises cherchent fournisseurs"""
    STATUT_CHOICES = [
        ('publie',   'Publié'),
        ('ferme',    'Fermé'),
        ('adjuge',   'Adjugé'),
        ('annule',   'Annulé'),
    ]
 
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    acheteur        = models.ForeignKey(ProfilB2B, on_delete=models.CASCADE,
                                         related_name='appels_offre')
    titre           = models.CharField(max_length=200)
    description     = models.TextField()
    categorie       = models.ForeignKey('apps_core.Categorie', on_delete=models.CASCADE)
    budget_estime   = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    quantite        = models.PositiveIntegerField()
    unite           = models.CharField(max_length=50, help_text="Ex: cartons, kg, pièces")
    specifications  = models.JSONField(default=dict)
    conditions_livraison = models.TextField(blank=True)
    criteres_selection = models.TextField(blank=True)
 
    statut          = models.CharField(max_length=10, choices=STATUT_CHOICES, default='publie')
    date_limite     = models.DateTimeField()
    soumission_gagnante = models.ForeignKey('SoumissionB2B', null=True, blank=True,
                                             on_delete=models.SET_NULL,
                                             related_name='appels_gagnes')
    date_creation   = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        verbose_name = "Appel d'offre B2B"
        ordering = ['-date_creation']
        db_table = 'b2b_appel_offre'
 
    def __str__(self):
        return f"AO B2B: {self.titre}"
 
 
class SoumissionB2B(models.Model):
    """Soumission d'un fournisseur à un appel d'offre B2B"""
    STATUT_CHOICES = [
        ('soumise',     'Soumise'),
        ('en_etude',    'En étude'),
        ('retenue',     'Retenue'),
        ('rejetee',     'Rejetée'),
        ('gagnante',    'Gagnante ✅'),
    ]
 
    appel_offre     = models.ForeignKey(AppelOffreB2B, on_delete=models.CASCADE,
                                         related_name='soumissions')
    fournisseur     = models.ForeignKey(ProfilB2B, on_delete=models.CASCADE,
                                         related_name='soumissions')
    prix_unitaire   = models.DecimalField(max_digits=12, decimal_places=2)
    prix_total      = models.DecimalField(max_digits=15, decimal_places=2)
    delai_livraison = models.PositiveIntegerField(help_text="Jours")
    description_offre = models.TextField()
    documents       = models.FileField(upload_to='b2b/soumissions/', null=True, blank=True)
    statut          = models.CharField(max_length=15, choices=STATUT_CHOICES, default='soumise')
    date_soumission = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        unique_together = ['appel_offre', 'fournisseur']
        ordering = ['prix_total']
        db_table = 'b2b_soumission'
 
    def __str__(self):
        return f"{self.fournisseur.nom_entreprise} → {self.appel_offre.titre}: {self.prix_total} XAF"
 
 
class ContratB2B(models.Model):
    """Contrat signé entre acheteur et fournisseur B2B"""
    STATUT_CHOICES = [
        ('brouillon',   'Brouillon'),
        ('envoye',      'Envoyé pour signature'),
        ('signe',       'Signé'),
        ('actif',       'Actif'),
        ('termine',     'Terminé'),
        ('resilie',     'Résilié'),
    ]
 
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    appel_offre     = models.OneToOneField(AppelOffreB2B, on_delete=models.CASCADE,
                                            related_name='contrat', null=True, blank=True)
    acheteur        = models.ForeignKey(ProfilB2B, on_delete=models.CASCADE,
                                         related_name='contrats_acheteur')
    fournisseur     = models.ForeignKey(ProfilB2B, on_delete=models.CASCADE,
                                         related_name='contrats_fournisseur')
    montant_total   = models.DecimalField(max_digits=15, decimal_places=2)
    termes          = models.TextField()
    fichier_contrat = models.FileField(upload_to='b2b/contrats/', null=True, blank=True)
    statut          = models.CharField(max_length=15, choices=STATUT_CHOICES, default='brouillon')
    date_debut      = models.DateField(null=True, blank=True)
    date_fin        = models.DateField(null=True, blank=True)
    date_signature  = models.DateTimeField(null=True, blank=True)
    date_creation   = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        db_table = 'b2b_contrat'
 
    def __str__(self):
        return f"Contrat B2B: {self.acheteur.nom_entreprise} ↔ {self.fournisseur.nom_entreprise}"


# ===========================================================================
# app_publicite/models.py
# Application : Réseau Publicitaire YopiAds
# ===========================================================================
 
class Publicite(models.Model):
    TYPE_CHOICES = [
        ('banniere',            'Bannière'),
        ('popup',               'Pop-up'),
        ('barre_laterale',      'Barre latérale'),
        ('page_produit',        'Page produit'),
        ('resultats_recherche', 'Résultats de recherche'),
        ('video_pre_roll',      'Vidéo pre-roll'),
        ('sponsored_produit',   'Produit sponsorisé'),
        ('native',              'Contenu natif'),
    ]
    STATUT_CHOICES = [
        ('brouillon',   'Brouillon'),
        ('en_revision', 'En révision'),
        ('active',      'Active'),
        ('en_pause',    'En pause'),
        ('expiree',     'Expirée'),
        ('rejetee',     'Rejetée'),
    ]
    OBJECTIF_CHOICES = [
        ('trafic',      'Trafic'),
        ('ventes',      'Ventes'),
        ('notoriete',   'Notoriété'),
        ('leads',       'Génération de leads'),
    ]
 
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    titre           = models.CharField(max_length=200)
    annonceur       = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                         related_name='publicites')
    boutique        = models.ForeignKey('apps_marketplace.Boutique', null=True, blank=True,
                                         on_delete=models.SET_NULL, related_name='publicites')
    type_pub        = models.CharField(max_length=25, choices=TYPE_CHOICES)
    objectif        = models.CharField(max_length=15, choices=OBJECTIF_CHOICES, default='ventes')
 
    # Contenu
    image           = models.ImageField(upload_to='publicites/')
    video_url       = models.URLField(blank=True, null=True)
    titre_pub       = models.CharField(max_length=100)
    description_pub = models.TextField(max_length=300)
    texte_bouton    = models.CharField(max_length=50, default='En savoir plus')
    lien_url        = models.URLField()
 
    # Budget
    budget_total    = models.DecimalField(max_digits=12, decimal_places=2)
    budget_journalier = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cout_par_clic   = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    cout_par_impression = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    cout_par_conversion = models.DecimalField(max_digits=8, decimal_places=2, default=0)
 
    # Ciblage
    categories_ciblees  = models.ManyToManyField('apps_core.Categorie', blank=True)
    villes_ciblees      = models.ManyToManyField('apps_core.Ville', blank=True)
    age_min             = models.PositiveIntegerField(null=True, blank=True)
    age_max             = models.PositiveIntegerField(null=True, blank=True)
    niveau_gamification = models.CharField(max_length=20, blank=True,
                                            help_text="Cibler un niveau ex: or, platine")
    mots_cles           = models.CharField(max_length=500, blank=True)
 
    # Dates
    date_debut      = models.DateTimeField()
    date_fin        = models.DateTimeField()
    statut          = models.CharField(max_length=15, choices=STATUT_CHOICES, default='brouillon')
    priorite        = models.PositiveIntegerField(default=0)
 
    # Statistiques
    impressions     = models.PositiveIntegerField(default=0)
    clics           = models.PositiveIntegerField(default=0)
    conversions     = models.PositiveIntegerField(default=0)
    total_depense   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
 
    date_creation   = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        verbose_name = "Publicité"
        ordering = ['-priorite', '-date_creation']
        db_table = 'publicite_publicite'
 
    def __str__(self):
        return f"📢 {self.titre} — {self.annonceur.username}"
 
    def taux_clic(self):
        if self.impressions == 0:
            return 0
        return round(self.clics / self.impressions * 100, 2)
 
    def roi(self):
        if self.total_depense == 0:
            return 0
        return round((self.conversions * self.cout_par_conversion - self.total_depense)
                     / self.total_depense * 100, 2)
 
 
class InteractionPublicite(models.Model):
    TYPE_CHOICES = [
        ('impression',  'Impression'),
        ('clic',        'Clic'),
        ('conversion',  'Conversion'),
        ('rejet',       'Rejet / Skip'),
    ]
 
    publicite       = models.ForeignKey(Publicite, on_delete=models.CASCADE,
                                         related_name='interactions')
    utilisateur     = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                         null=True, blank=True)
    type_interaction = models.CharField(max_length=15, choices=TYPE_CHOICES)
    adresse_ip      = models.GenericIPAddressField()
    user_agent      = models.TextField()
    cout_genere     = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    date_creation   = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        db_table = 'publicite_interaction'
 
    def __str__(self):
        return f"{self.get_type_interaction_display()} — {self.publicite.titre}"
 


# ===========================================================================
# app_pos/models.py
# Application : Point de Vente Physique (ERP intégré)
# ===========================================================================
 
class CaissePos(models.Model):
    """Caisse enregistreuse d'un magasin physique"""
    boutique        = models.ForeignKey('apps_marketplace.Boutique', on_delete=models.CASCADE,
                                         related_name='caisses')
    nom             = models.CharField(max_length=100)
    numero_serie    = models.CharField(max_length=100, blank=True)
    est_active      = models.BooleanField(default=True)
    caissier_actuel = models.ForeignKey('apps_core.Utilisateur', null=True, blank=True,
                                         on_delete=models.SET_NULL, related_name='caisses_assignees')
    solde_debut_journee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    date_creation   = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        db_table = 'pos_caisse'
 
    def __str__(self):
        return f"Caisse {self.nom} — {self.boutique.nom}"
 
 
class VentePos(models.Model):
    """Vente réalisée en magasin physique"""
    STATUT_CHOICES = [
        ('complete',  'Complète'),
        ('annulee',   'Annulée'),
        ('remboursee', 'Remboursée'),
    ]
    PAIEMENT_CHOICES = [
        ('especes',         'Espèces'),
        ('orange_money',    'Orange Money'),
        ('mtn_momo',        'MTN MoMo'),
        ('carte',           'Carte bancaire'),
        ('cheque',          'Chèque'),
        ('mixte',           'Mixte'),
    ]
 
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    caisse          = models.ForeignKey(CaissePos, on_delete=models.CASCADE, related_name='ventes')
    caissier        = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE,
                                         related_name='ventes_pos')
    client          = models.ForeignKey('apps_core.Utilisateur', null=True, blank=True,
                                         on_delete=models.SET_NULL, related_name='achats_pos')
    numero_ticket   = models.CharField(max_length=50, unique=True)
    montant_total   = models.DecimalField(max_digits=12, decimal_places=2)
    montant_paye    = models.DecimalField(max_digits=12, decimal_places=2)
    monnaie_rendue  = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    methode_paiement = models.CharField(max_length=15, choices=PAIEMENT_CHOICES)
    statut          = models.CharField(max_length=15, choices=STATUT_CHOICES, default='complete')
    commande_online = models.ForeignKey('apps_marketplace.Commande', null=True, blank=True,
                                         on_delete=models.SET_NULL,
                                         help_text="Si vente liée à une commande YopiShop")
    date_vente      = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        ordering = ['-date_vente']
        db_table = 'pos_vente'
 
    def __str__(self):
        return f"Ticket {self.numero_ticket} — {self.montant_total} XAF"
 
 
class ArticleVentePos(models.Model):
    vente           = models.ForeignKey(VentePos, on_delete=models.CASCADE, related_name='articles')
    produit         = models.ForeignKey('apps_core.Produit', on_delete=models.CASCADE)
    quantite        = models.PositiveIntegerField()
    prix_unitaire   = models.DecimalField(max_digits=12, decimal_places=2)
    prix_total      = models.DecimalField(max_digits=12, decimal_places=2)
    remise          = models.DecimalField(max_digits=10, decimal_places=2, default=0)
 
    class Meta:
        db_table = 'pos_article_vente'
 
    def __str__(self):
        return f"{self.produit.titre} x{self.quantite}"
 
    def save(self, *args, **kwargs):
        self.prix_total = (self.prix_unitaire * self.quantite) - self.remise
        super().save(*args, **kwargs)
 
 
class SessionCaisse(models.Model):
    """Ouverture/fermeture de session de caisse"""
    caisse          = models.ForeignKey(CaissePos, on_delete=models.CASCADE, related_name='sessions')
    caissier        = models.ForeignKey('apps_core.Utilisateur', on_delete=models.CASCADE)
    fond_caisse_ouverture = models.DecimalField(max_digits=10, decimal_places=2)
    fond_caisse_fermeture = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    montant_especes_compte = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    ecart_caisse    = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    nb_transactions = models.PositiveIntegerField(default=0)
    chiffre_affaires_session = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    date_ouverture  = models.DateTimeField(auto_now_add=True)
    date_fermeture  = models.DateTimeField(null=True, blank=True)
    notes           = models.TextField(blank=True)
 
    class Meta:
        db_table = 'pos_session_caisse'
 
    def __str__(self):
        return f"Session {self.caissier.username} — {self.caisse.nom}"
 
 
 
 
 