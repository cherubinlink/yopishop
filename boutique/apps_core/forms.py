
# ===========================================================================
# apps_core/forms.py
# Formulaires — Section 1 : Gestion Utilisateurs
# Couvre : Inscription, Connexion, Profil, Wallet, Mot de passe
# ===========================================================================
 
from django import forms
from django.forms import inlineformset_factory
from django.contrib.auth.forms import (
    AuthenticationForm,PasswordChangeForm,
    PasswordResetForm,SetPasswordForm,
)
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from apps_core.models import (
    Utilisateur, ProfilUtilisateur, DemandeRechargeWallet,  Produit,
    ImageProduit,VarianteProduit,AttributProduit,
    Categorie,Marque,Promotion
)



# =============================================================================
# HELPER : qui peut voir/définir le badge YopiShop officiel
# =============================================================================
 
def utilisateur_peut_definir_yopishop(user):
    """
    True si l'utilisateur peut cocher/décocher 'Produit YopiShop Officiel'.
      - Administrateurs et super administrateurs Django (is_staff/is_superuser)
      - Utilisateurs avec type_vendeur == 'yopishop'
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    return getattr(user, 'type_vendeur', None) == 'yopishop'


# =============================================================================
# INSCRIPTION
# =============================================================================
 
class InscriptionForm(forms.ModelForm):
    """Formulaire d'inscription complet."""
 
    password1 = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Minimum 8 caractères',
            'autocomplete': 'new-password',
        }),
        min_length=8,
    )
    password2 = forms.CharField(
        label="Confirmer le mot de passe",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Répétez votre mot de passe',
            'autocomplete': 'new-password',
        }),
    )
    accepter_cgu = forms.BooleanField(
        required=True,
        label="J'accepte les conditions générales d'utilisation",
        error_messages={'required': "Vous devez accepter les CGU pour créer un compte."},
    )
 
    class Meta:
        model  = Utilisateur
        fields = ('username', 'email', 'first_name', 'last_name', 'telephone')
        widgets = {
            'username':   forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Nom d'utilisateur"}),
            'email':      forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@exemple.com'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Prénom'}),
            'last_name':  forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom'}),
            'telephone':  forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+237 6XX XXX XXX'}),
        }
        labels = {
            'username':   "Nom d'utilisateur",
            'email':      'Adresse email',
            'first_name': 'Prénom',
            'last_name':  'Nom',
            'telephone':  'Téléphone',
        }
 
    def clean_email(self):
        email = self.cleaned_data.get('email', '').lower().strip()
        if Utilisateur.objects.filter(email=email).exists():
            raise ValidationError("Cette adresse email est déjà utilisée.")
        return email
 
    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if Utilisateur.objects.filter(username__iexact=username).exists():
            raise ValidationError("Ce nom d'utilisateur est déjà pris.")
        if len(username) < 3:
            raise ValidationError("Le nom d'utilisateur doit contenir au moins 3 caractères.")
        return username
 
    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password1')
        p2 = cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', "Les mots de passe ne correspondent pas.")
        return cleaned_data
 
    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        user.email = self.cleaned_data['email'].lower()
        if commit:
            user.save()
            # Créer le profil automatiquement
            ProfilUtilisateur.objects.get_or_create(utilisateur=user)
        return user
 
 
# =============================================================================
# CONNEXION
# =============================================================================
 
class ConnexionForm(AuthenticationForm):
    """Formulaire de connexion avec champs stylisés."""
 
    username = forms.CharField(
        label="Email ou nom d'utilisateur",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': "Email ou nom d'utilisateur",
            'autofocus': True,
            'autocomplete': 'username',
        }),
    )
    password = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Votre mot de passe',
            'autocomplete': 'current-password',
        }),
    )
    se_souvenir = forms.BooleanField(
        required=False,
        label="Se souvenir de moi",
        initial=False,
    )
 
    error_messages = {
        'invalid_login': "Email/nom d'utilisateur ou mot de passe incorrect.",
        'inactive': "Ce compte est désactivé. Contactez le support.",
    }


# =============================================================================
# PROFIL UTILISATEUR
# =============================================================================
 
class ProfilBaseForm(forms.ModelForm):
    """Informations de base de l'utilisateur."""
 
    class Meta:
        model  = Utilisateur
        fields = (
            'first_name', 'last_name', 'email',
            'telephone', 'date_naissance', 'bio',
            'avatar',
        )
        widgets = {
            'first_name':    forms.TextInput(attrs={'class': 'form-control'}),
            'last_name':     forms.TextInput(attrs={'class': 'form-control'}),
            'email':         forms.EmailInput(attrs={'class': 'form-control'}),
            'telephone':     forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+237 6XX XXX XXX'}),
            'date_naissance': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'bio':           forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'maxlength': 500, 'placeholder': 'Parlez de vous en quelques mots...'}),
            'avatar':        forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }
        labels = {
            'first_name': 'Prénom',
            'last_name':  'Nom',
            'email':      'Adresse email',
            'bio':        'Biographie',
        }
 
    def clean_email(self):
        email = self.cleaned_data.get('email', '').lower().strip()
        qs = Utilisateur.objects.filter(email=email).exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Cette adresse email est déjà utilisée par un autre compte.")
        return email
 
 
class ProfilAdresseForm(forms.ModelForm):
    """Adresse et localisation."""
 
    class Meta:
        model  = Utilisateur
        fields = ('adresse', 'ville', 'pays', 'code_postal')
        widgets = {
            'adresse':     forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'ville':       forms.Select(attrs={'class': 'form-select'}),
            'pays':        forms.Select(attrs={'class': 'form-select'}),
            'code_postal': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Code postal'}),
        }
 
 
class ProfilPreferencesForm(forms.ModelForm):
    """Préférences utilisateur (notifications, langue, devise)."""
 
    class Meta:
        model  = ProfilUtilisateur
        fields = (
            'langue_preference', 'devise_preference',
            'notifications_email', 'notifications_sms', 'notifications_push',
        )
        widgets = {
            'langue_preference':  forms.Select(
                choices=[('fr', 'Français'), ('en', 'English')],
                attrs={'class': 'form-select'}
            ),
            'devise_preference': forms.Select(
                choices=[('XAF', 'FCFA — Franc CFA'), ('USD', 'USD — Dollar'), ('EUR', 'EUR — Euro')],
                attrs={'class': 'form-select'}
            ),
        }


class SousDomaineBoutiqueForm(forms.ModelForm):
    """Choisir ou modifier le sous-domaine boutique."""
 
    class Meta:
        model  = Utilisateur
        fields = ('sous_domaine',)
        widgets = {
            'sous_domaine': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'mon-shop',
                'pattern': '^[a-z0-9-]{3,50}$',
            }),
        }
        labels = {'sous_domaine': 'Sous-domaine boutique'}
        help_texts = {
            'sous_domaine': 'Lettres minuscules, chiffres et tirets uniquement. Ex: mon-shop → mon-shop.yopishop.com',
        }
 
    def clean_sous_domaine(self):
        val = self.cleaned_data.get('sous_domaine', '').lower().strip()
        import re
        if not re.match(r'^[a-z0-9-]{3,50}$', val):
            raise ValidationError("Seuls les lettres minuscules, chiffres et tirets sont autorisés (3–50 caractères).")
        qs = Utilisateur.objects.filter(sous_domaine=val).exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Ce sous-domaine est déjà utilisé.")
        reserved = ['www', 'api', 'admin', 'shop', 'app', 'mail', 'ftp', 'yopishop']
        if val in reserved:
            raise ValidationError(f"Le sous-domaine '{val}' est réservé.")
        return val



# =============================================================================
# MOT DE PASSE
# =============================================================================
 
class ChangementMotDePasseForm(PasswordChangeForm):
    """Changement de mot de passe avec champs stylisés."""
 
    old_password = forms.CharField(
        label="Mot de passe actuel",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'current-password'}),
    )
    new_password1 = forms.CharField(
        label="Nouveau mot de passe",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
        min_length=8,
    )
    new_password2 = forms.CharField(
        label="Confirmer le nouveau mot de passe",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
    )
 
 
class ReinitMotDePasseForm(PasswordResetForm):
    email = forms.EmailField(
        label="Adresse email",
        max_length=254,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Votre adresse email',
            'autocomplete': 'email',
        }),
    )
 
 
class NouveauMotDePasseForm(SetPasswordForm):
    new_password1 = forms.CharField(
        label="Nouveau mot de passe",
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        min_length=8,
    )
    new_password2 = forms.CharField(
        label="Confirmer le mot de passe",
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
    )




# =============================================================================
# WALLET YOPIPAY
# =============================================================================
 
class CreditWalletForm(forms.Form):
    """Formulaire de crédit manuel du wallet (pour admins ou tests)."""
 
    montant = forms.DecimalField(
        label="Montant (XAF)",
        min_value=100,
        max_value=10_000_000,
        decimal_places=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ex: 5000',
            'step': '100',
        }),
    )
    description = forms.CharField(
        label="Motif",
        max_length=500,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Remboursement commande #123'}),
    )


# =============================================================================
# FORMULAIRE : RechargeWalletForm (à ajouter dans forms.py)
# =============================================================================
 
class RechargeWalletForm(forms.ModelForm):
    """Formulaire de demande de recharge soumise par l'utilisateur."""
 
    montant = forms.DecimalField(
        label="Montant (XAF)",
        min_value=500,
        max_value=10_000_000,
        decimal_places=0,
        widget=forms.NumberInput(attrs={
            'class':       'form-control',
            'placeholder': 'Ex: 5000',
            'step':        '100',
            'min':         '500',
        }),
    )
    methode = forms.ChoiceField(
        label="Méthode de paiement",
        choices=DemandeRechargeWallet.METHODE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    numero_expediteur = forms.CharField(
        label="Numéro expéditeur",
        required=False,
        max_length=30,
        widget=forms.TextInput(attrs={
            'class':       'form-control',
            'placeholder': '+237 6XX XXX XXX',
        }),
    )
    preuve_paiement = forms.ImageField(
        label="Capture d'écran du paiement",
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*,.pdf'}),
    )
 
    class Meta:
        model  = DemandeRechargeWallet
        fields = ['montant', 'methode', 'numero_expediteur', 'preuve_paiement']
 
    def clean_montant(self):
        montant = self.cleaned_data.get('montant')
        if montant and montant < 500:
            raise forms.ValidationError("Le montant minimum est de 500 XAF.")
        return montant
 
 
 
class DemandeVendeurForm(forms.Form):
    """
    Formulaire de candidature pour devenir vendeur pro.
    Utilisé dans la vue devenir_vendeur.
    """
    motivation = forms.CharField(
        label="Pourquoi souhaitez-vous vendre sur YopiShop ?",
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Décrivez vos motivations...'}),
        min_length=50,
    )
    experience_commerce = forms.CharField(
        label="Avez-vous déjà vendu en ligne ?",
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Décrivez votre expérience...'}),
        required=False,
    )
    types_produits = forms.CharField(
        label="Quels types de produits souhaitez-vous vendre ?",
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        min_length=20,
    )
    volume_estime = forms.ChoiceField(
        label="Volume estimé de produits",
        choices=[
            ('', '-- Sélectionnez --'),
            ('1-10',   '1 à 10 produits'),
            ('11-50',  '11 à 50 produits'),
            ('51-100', '51 à 100 produits'),
            ('100+',   'Plus de 100 produits'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    a_entreprise = forms.BooleanField(
        label="J'ai une entreprise enregistrée",
        required=False,
    )
    nom_entreprise = forms.CharField(
        label="Nom de l'entreprise",
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optionnel'}),
    )


# =============================================================================
# FORMULAIRE PRODUIT (création / édition)
# =============================================================================
 
class ProduitForm(forms.ModelForm):
    """
    Formulaire principal de création/édition d'un produit.
 
    Le champ `est_produit_yopishop` est retiré dynamiquement dans __init__
    si l'utilisateur n'a pas les droits nécessaires (cf.
    utilisateur_peut_definir_yopishop).
    """
 
    class Meta:
        model = Produit
        fields = [
            'titre', 'description', 'description_courte',
            'type_produit', 'categorie', 'marque',
            'prix', 'prix_achat', 'devise',
            'quantite_stock', 'alerte_stock_min', 'sku',
            'etat', 'poids', 'dimensions',
            'ville', 'quartier', 'adresse_complete',
            'est_actif', 'est_vedette',
            'autorise_enchere', 'autorise_vente_directe', 'autorise_achat_groupe',
            'est_b2b', 'quantite_min_commande',
            'est_produit_yopishop',   # retiré dynamiquement si non autorisé
            'livraison_disponible', 'livraison_locale_uniquement', 'retrait_sur_place',
            'modele_3d_url',
            'titre_meta', 'description_meta',
        ]
        widgets = {
            'titre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex : iPhone 13 Pro Max 256Go',
                'maxlength': 200,
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 6,
                'placeholder': 'Description détaillée du produit...',
            }),
            'description_courte': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2, 'maxlength': 500,
                'placeholder': 'Résumé court affiché dans les listes de produits (max 500 caractères)',
            }),
            'type_produit': forms.Select(attrs={'class': 'form-select'}),
            'categorie':    forms.Select(attrs={'class': 'form-select'}),
            'marque':       forms.Select(attrs={'class': 'form-select'}),
 
            'prix':       forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'placeholder': 'Ex : 25000'}),
            'prix_achat': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'placeholder': 'Prix d\'achat (optionnel)'}),
            'devise':     forms.Select(choices=[('XAF', 'FCFA — Franc CFA'), ('USD', 'USD'), ('EUR', 'EUR')],
                                        attrs={'class': 'form-select'}),
 
            'quantite_stock':   forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'alerte_stock_min': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'sku': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Référence interne (optionnel)'}),
 
            'etat':       forms.Select(attrs={'class': 'form-select'}),
            'poids':      forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Poids en kg'}),
            'dimensions': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex : 30x20x10 cm'}),
 
            'ville':    forms.Select(attrs={'class': 'form-select'}),
            'quartier': forms.Select(attrs={'class': 'form-select'}),
            'adresse_complete': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Adresse de retrait / expédition'}),
 
            'quantite_min_commande': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
 
            'est_actif':              forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'est_vedette':            forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'autorise_enchere':       forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'autorise_vente_directe': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'autorise_achat_groupe':  forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'est_b2b':                forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'est_produit_yopishop':   forms.CheckboxInput(attrs={'class': 'form-check-input'}),
 
            'livraison_disponible':        forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'livraison_locale_uniquement':  forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'retrait_sur_place':            forms.CheckboxInput(attrs={'class': 'form-check-input'}),
 
            'modele_3d_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://... (modèle 3D / AR, optionnel)'}),
 
            'titre_meta':       forms.TextInput(attrs={'class': 'form-control', 'maxlength': 200}),
            'description_meta': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'maxlength': 300}),
        }
        labels = {
            'titre':                  'Titre du produit',
            'description':            'Description complète',
            'description_courte':     'Description courte',
            'type_produit':           'Type de produit',
            'categorie':              'Catégorie',
            'marque':                 'Marque',
            'prix':                   'Prix de vente',
            'prix_achat':             'Prix d\'achat',
            'quantite_stock':         'Quantité en stock',
            'alerte_stock_min':       'Seuil d\'alerte stock',
            'sku':                    'SKU / Référence',
            'etat':                   'État du produit',
            'poids':                  'Poids (kg)',
            'dimensions':             'Dimensions',
            'ville':                  'Ville',
            'quartier':               'Quartier',
            'adresse_complete':       'Adresse complète',
            'est_actif':              'Produit actif (visible sur la plateforme)',
            'est_vedette':            'Mettre en vedette',
            'autorise_enchere':       'Autoriser les enchères sur ce produit',
            'autorise_vente_directe': 'Autoriser la vente directe',
            'autorise_achat_groupe':  'Autoriser l\'achat groupé',
            'est_b2b':                'Produit B2B (vente en gros)',
            'quantite_min_commande':  'Quantité minimum par commande',
            'est_produit_yopishop':   '✅ Produit YopiShop Officiel',
            'livraison_disponible':            'Livraison disponible',
            'livraison_locale_uniquement':     'Livraison locale uniquement',
            'retrait_sur_place':                'Retrait sur place possible',
            'modele_3d_url':          'URL modèle 3D / Réalité augmentée',
            'titre_meta':             'Titre SEO',
            'description_meta':       'Description SEO',
        }
        help_texts = {
            'est_produit_yopishop': "Affiche le badge ✅ YopiShop Officiel dans les listings. "
                                     "Réservé aux administrateurs et au compte YopiShop.",
            'sku': "Code interne pour votre gestion de stock (facultatif).",
            'quantite_min_commande': "Pour les produits B2B, quantité minimum exigée par commande.",
        }
 
    def __init__(self, *args, **kwargs):
        # L'utilisateur courant est passé explicitement par la vue
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
 
        # ── Catégories : uniquement actives ──────────────────────────────────
        self.fields['categorie'].queryset = Categorie.objects.filter(est_active=True).order_by('ordre', 'nom')
        self.fields['marque'].queryset = Marque.objects.filter(est_active=True).order_by('nom')
        self.fields['marque'].required = False
        self.fields['marque'].empty_label = "— Aucune marque —"
 
        # ── Champs optionnels ─────────────────────────────────────────────────
        for champ_optionnel in ('prix_achat', 'sku', 'poids', 'dimensions',
                                  'quartier', 'adresse_complete', 'modele_3d_url',
                                  'titre_meta', 'description_meta', 'marque'):
            self.fields[champ_optionnel].required = False
 
        # ── RÈGLE MÉTIER : retirer le champ est_produit_yopishop si non autorisé ──
        if not utilisateur_peut_definir_yopishop(self.user):
            self.fields.pop('est_produit_yopishop', None)
 
        # ── Ville obligatoire pour produits physiques avec livraison ────────
        self.fields['ville'].required = False
 
    def clean(self):
        cleaned_data = super().clean()
 
        type_produit = cleaned_data.get('type_produit')
        ville        = cleaned_data.get('ville')
        livraison    = cleaned_data.get('livraison_disponible')
 
        # Un produit physique avec livraison doit avoir une ville
        if type_produit == 'physique' and livraison and not ville:
            self.add_error('ville', "La ville est requise pour un produit physique livrable.")
 
        # Vérification cohérence prix
        prix       = cleaned_data.get('prix')
        prix_achat = cleaned_data.get('prix_achat')
        if prix is not None and prix_achat is not None and prix_achat > prix:
            self.add_error('prix_achat', "Le prix d'achat ne peut pas être supérieur au prix de vente.")
 
        # Quantité min commande cohérente pour B2B
        est_b2b = cleaned_data.get('est_b2b')
        qte_min = cleaned_data.get('quantite_min_commande') or 1
        if est_b2b and qte_min < 2:
            self.add_error('quantite_min_commande',
                            "Un produit B2B doit avoir une quantité minimum de commande d'au moins 2.")
 
        return cleaned_data
 
    def save(self, commit=True):
        produit = super().save(commit=False)
 
        # Sécurité supplémentaire : si le champ n'était pas dans le form
        # (utilisateur non autorisé), on s'assure qu'il garde sa valeur
        # existante (édition) ou reste False (création) — jamais modifiable
        # par un payload POST forgé.
        if 'est_produit_yopishop' not in self.fields:
            if self.instance.pk:
                # Édition : conserver la valeur existante en base
                ancien = Produit.objects.filter(pk=self.instance.pk).values_list(
                    'est_produit_yopishop', flat=True
                ).first()
                produit.est_produit_yopishop = bool(ancien)
            else:
                produit.est_produit_yopishop = False
 
        if commit:
            produit.save()
        return produit


# =============================================================================
# FORMSETS : Images, Variantes, Attributs (édition inline)
# =============================================================================
 
ImageProduitFormSet = inlineformset_factory(
    Produit, ImageProduit,
    fields=['image', 'texte_alternatif', 'est_principale', 'ordre'],
    extra=3,
    max_num=10,
    can_delete=True,
    widgets={
        'image':            forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        'texte_alternatif': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Texte alternatif (SEO)'}),
        'est_principale':   forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        'ordre':            forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'style': 'width:80px'}),
    },
)
 
 
VarianteProduitFormSet = inlineformset_factory(
    Produit, VarianteProduit,
    fields=['nom', 'valeur', 'prix_supplementaire', 'stock', 'sku_variante', 'image', 'est_active'],
    extra=2,
    max_num=30,
    can_delete=True,
    widgets={
        'nom':                 forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex : Couleur'}),
        'valeur':              forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex : Rouge'}),
        'prix_supplementaire': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
        'stock':               forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
        'sku_variante':        forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'SKU variante (optionnel)'}),
        'image':               forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        'est_active':          forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    },
)
 
 
AttributProduitFormSet = inlineformset_factory(
    Produit, AttributProduit,
    fields=['nom', 'valeur', 'unite', 'ordre'],
    extra=3,
    max_num=20,
    can_delete=True,
    widgets={
        'nom':    forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex : RAM'}),
        'valeur': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex : 8'}),
        'unite':  forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex : Go', 'style': 'width:90px'}),
        'ordre':  forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'style': 'width:80px'}),
    },
)


# =============================================================================
# FORMULAIRE RECHERCHE / FILTRES CATALOGUE
# =============================================================================
 
class FiltreCatalogueForm(forms.Form):
    """Formulaire de filtres pour la page catalogue (GET)."""
 
    q = forms.CharField(
        required=False,
        label="Recherche",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Rechercher un produit...'}),
    )
    categorie = forms.ModelChoiceField(
        queryset=Categorie.objects.filter(est_active=True),
        required=False,
        label="Catégorie",
        widget=forms.Select(attrs={'class': 'form-select'}),
        to_field_name='slug',
    )
    marque = forms.ModelChoiceField(
        queryset=Marque.objects.filter(est_active=True),
        required=False,
        label="Marque",
        widget=forms.Select(attrs={'class': 'form-select'}),
        to_field_name='slug',
    )
    prix_min = forms.DecimalField(
        required=False, min_value=0,
        label="Prix min",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Min'}),
    )
    prix_max = forms.DecimalField(
        required=False, min_value=0,
        label="Prix max",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Max'}),
    )
    etat = forms.ChoiceField(
        choices=[('', 'Tous les états')] + Produit.ETAT_CHOICES,
        required=False,
        label="État",
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    type_produit = forms.ChoiceField(
        choices=[('', 'Tous les types')] + Produit.TYPE_PRODUIT_CHOICES,
        required=False,
        label="Type",
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    en_stock = forms.BooleanField(
        required=False,
        label="En stock uniquement",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
    vedette = forms.BooleanField(
        required=False,
        label="Produits vedettes",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
    yopishop = forms.BooleanField(
        required=False,
        label="Produits YopiShop Officiel",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
    tri = forms.ChoiceField(
        choices=[
            ('recent',     'Plus récents'),
            ('prix_asc',   'Prix croissant'),
            ('prix_desc',  'Prix décroissant'),
            ('populaire',  'Plus populaires'),
            ('note',       'Meilleures notes'),
        ],
        required=False,
        initial='recent',
        label="Trier par",
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
 
    def clean(self):
        cleaned_data = super().clean()
        pmin = cleaned_data.get('prix_min')
        pmax = cleaned_data.get('prix_max')
        if pmin is not None and pmax is not None and pmin > pmax:
            self.add_error('prix_max', "Le prix max doit être supérieur au prix min.")
        return cleaned_data


# =============================================================================
# FORMULAIRE CATÉGORIE (admin / vendeurs pro avec droits)
# =============================================================================
 
class CategorieForm(forms.ModelForm):
    class Meta:
        model = Categorie
        fields = ['nom', 'slug', 'description', 'image', 'parent', 'est_active', 'ordre']
        widgets = {
            'nom':         forms.TextInput(attrs={'class': 'form-control'}),
            'slug':        forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Laisser vide pour générer automatiquement'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'image':       forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'parent':      forms.Select(attrs={'class': 'form-select'}),
            'est_active':  forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'ordre':       forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
        }
 
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['slug'].required = False
        self.fields['parent'].required = False
        self.fields['parent'].queryset = Categorie.objects.filter(est_active=True)
        if self.instance.pk:
            # Empêcher une catégorie d'être son propre parent
            self.fields['parent'].queryset = self.fields['parent'].queryset.exclude(pk=self.instance.pk)



# =============================================================================
# FORMULAIRE MARQUE
# =============================================================================
 
class MarqueForm(forms.ModelForm):
    class Meta:
        model = Marque
        fields = ['nom', 'slug', 'description', 'logo', 'est_active']
        widgets = {
            'nom':         forms.TextInput(attrs={'class': 'form-control'}),
            'slug':        forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Laisser vide pour générer automatiquement'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'logo':        forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'est_active':  forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
 
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['slug'].required = False
        self.fields['description'].required = False
        self.fields['logo'].required = False
 
    def clean_slug(self):
        slug = self.cleaned_data.get('slug', '').strip()
        if not slug:
            from django.utils.text import slugify
            slug = slugify(self.cleaned_data.get('nom', ''))
        qs = Marque.objects.filter(slug=slug).exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Ce slug est déjà utilisé par une autre marque.")
        return slug
 
 
# =============================================================================
# FORMULAIRE AVIS PRODUIT
# =============================================================================
 
# =============================================================================
# WIDGET MULTIPLE FILES
# =============================================================================

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


# =============================================================================
# FIELD MULTIPLE FILES
# =============================================================================

class MultipleFileField(forms.FileField):

    widget = MultipleFileInput

    def clean(self, data, initial=None):
        single_file_clean = super().clean

        if isinstance(data, (list, tuple)):
            return [
                single_file_clean(d, initial)
                for d in data
            ]

        return single_file_clean(data, initial)


# =============================================================================
# FORMULAIRE AVIS PRODUIT
# =============================================================================

class AvisProduitForm(forms.Form):

    note = forms.IntegerField(
        label="Note",
        min_value=1,
        max_value=5,
        widget=forms.HiddenInput()
    )

    titre = forms.CharField(
        label="Titre de votre avis",
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Résumez votre expérience'
        })
    )

    commentaire = forms.CharField(
        label="Votre commentaire",
        min_length=10,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Décrivez votre expérience avec ce produit...'
        })
    )

    images = MultipleFileField(
        required=False,
        widget=MultipleFileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*',
            'multiple': True,
        })
    )

    def clean_images(self):

        files = self.cleaned_data.get('images')

        if not files:
            return []

        if not isinstance(files, (list, tuple)):
            files = [files]

        MAX_IMAGES = 5
        MAX_SIZE = 5 * 1024 * 1024  # 5 Mo

        if len(files) > MAX_IMAGES:
            raise forms.ValidationError(
                f"Maximum {MAX_IMAGES} images autorisées."
            )

        for f in files:

            if f.size > MAX_SIZE:
                raise forms.ValidationError(
                    f"Le fichier '{f.name}' dépasse 5 Mo."
                )

            if not f.content_type.startswith('image/'):
                raise forms.ValidationError(
                    f"'{f.name}' n'est pas une image valide."
                )

        return files


 
class PromotionForm(forms.ModelForm):
    """Formulaire création/édition promotion — réservé admins et vendeurs pro."""
 
    class Meta:
        model  = Promotion
        fields = [
            'nom', 'description', 'code',
            'type_promotion', 'valeur_reduction',
            'montant_min_achat', 'montant_max_reduction',
            'limite_utilisation', 'limite_par_utilisateur',
            'date_debut', 'date_fin',
            'categories', 'produits',
            'statut', 'priorite',
        ]
        widgets = {
            'nom':         forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom de la promotion'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'code':        forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'CODE-PROMO (optionnel — laisser vide pour promo automatique)',
                'style': 'text-transform:uppercase',
            }),
            'type_promotion':        forms.Select(attrs={'class': 'form-select'}),
            'valeur_reduction':      forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'placeholder': 'Ex: 20 pour 20% ou 2000 FCFA'}),
            'montant_min_achat':     forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'placeholder': 'Optionnel'}),
            'montant_max_reduction': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'placeholder': 'Optionnel'}),
            'limite_utilisation':    forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'placeholder': 'Laisser vide = illimité'}),
            'limite_par_utilisateur': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'date_debut': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'date_fin':   forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'categories': forms.CheckboxSelectMultiple(),
            'produits':   forms.CheckboxSelectMultiple(),
            'statut':     forms.Select(attrs={'class': 'form-select'}),
            'priorite':   forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
        }
        labels = {
            'nom':                   'Nom de la promotion',
            'description':           'Description',
            'code':                  'Code promo',
            'type_promotion':        'Type de réduction',
            'valeur_reduction':      'Valeur de la réduction',
            'montant_min_achat':     'Montant minimum d\'achat',
            'montant_max_reduction': 'Réduction maximale',
            'limite_utilisation':    'Limite totale d\'utilisation',
            'limite_par_utilisateur':'Limite par utilisateur',
            'date_debut':            'Date de début',
            'date_fin':              'Date de fin',
            'categories':            'Catégories ciblées',
            'produits':              'Produits ciblés',
            'statut':                'Statut',
            'priorite':              'Priorité (plus élevé = appliqué en premier)',
        }
 
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
 
        self.fields['code'].required               = False
        self.fields['montant_min_achat'].required   = False
        self.fields['montant_max_reduction'].required = False
        self.fields['limite_utilisation'].required  = False
 
        # Limiter les produits au vendeur si pas admin
        if self.user and not self.user.is_staff:
            self.fields['produits'].queryset = Produit.objects.filter(
                vendeur=self.user, est_actif=True
            ).select_related('categorie')
            # Les non-admins ne peuvent pas changer le statut directement
            self.fields['statut'].choices = [
                ('brouillon', 'Brouillon'),
                ('active',    'Active'),
                ('en_pause',  'En pause'),
            ]
        else:
            self.fields['produits'].queryset = Produit.objects.filter(
                est_actif=True
            ).select_related('categorie', 'vendeur')
 
        self.fields['categories'].queryset = Categorie.objects.filter(
            est_active=True
        ).order_by('ordre', 'nom')
 
        # Retirer le champ 'utilisateurs' (géré séparément)
        if 'utilisateurs' in self.fields:
            del self.fields['utilisateurs']
 
    def clean_code(self):
        code = self.cleaned_data.get('code') or ''  # ← None → '' sans planter
        code = code.strip().upper()

        if not code:
            return None  # Champ optionnel vide → on retourne None, pas d'erreur

        qs = Promotion.objects.filter(code=code)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Ce code promo est déjà utilisé.")

        if len(code) < 3:
            raise ValidationError("Le code promo doit contenir au moins 3 caractères.")

        import re
        if not re.match(r'^[A-Z0-9_-]+$', code):
            raise ValidationError("Le code ne peut contenir que des lettres, chiffres, tirets et underscores.")

        return code
 
    def clean(self):
        cleaned = super().clean()
        debut = cleaned.get('date_debut')
        fin   = cleaned.get('date_fin')
        if debut and fin and fin <= debut:
            self.add_error('date_fin', "La date de fin doit être postérieure à la date de début.")
 
        type_promo = cleaned.get('type_promotion')
        valeur     = cleaned.get('valeur_reduction')
        if type_promo == 'pourcentage' and valeur is not None:
            if valeur <= 0 or valeur > 100:
                self.add_error('valeur_reduction', "Le pourcentage doit être entre 0.01 et 100.")
 
        return cleaned
 
 
class CodePromoForm(forms.Form):
    """Formulaire public d'application d'un code promo (panier)."""
    code = forms.CharField(
        label="Code promo",
        max_length=50,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Entrez votre code promo',
            'style': 'text-transform:uppercase',
        }),
    )
 
    def clean_code(self):
        code = self.cleaned_data['code'].strip().upper()
        now  = timezone.now()
        try:
            promo = Promotion.objects.get(
                code=code,
                statut='active',
                date_debut__lte=now,
                date_fin__gte=now,
            )
        except Promotion.DoesNotExist:
            raise ValidationError("Ce code promo est invalide, expiré ou inactif.")
        self.promo = promo
        return code