# ===========================================================================
# app_marketplace/forms.py
# Formulaires — App Marketplace
# Couvre : Boutique, DocumentKYC, EmployeBoutique, AvisVendeur, DemandeVendeur
# ===========================================================================

from django import forms
from django.core.exceptions import ValidationError
from django.utils.text import slugify
import re


from apps_marketplace.models import (
    Boutique, DocumentKYC, EmployeBoutique,
    AvisVendeur, DemandeVendeur,CodePromo
)


# =============================================================================
# BOUTIQUE
# =============================================================================

class BoutiqueCreerForm(forms.ModelForm):
    """Création d'une boutique professionnelle."""

    class Meta:
        model  = Boutique
        fields = [
            'nom', 'sous_domaine', 'description',
            'logo', 'banniere', 'couleur_primaire', 'couleur_secondaire',
            'email', 'telephone', 'adresse', 'ville',
            'site_web', 'facebook', 'instagram', 'tiktok', 'whatsapp',
            'delai_traitement', 'politique_retour', 'conditions_vente',
        ]
        widgets = {
            'nom':         forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom de votre boutique'}),
            'sous_domaine': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'mon-shop → mon-shop.yopishop.com',
                'pattern': '^[a-z0-9-]{3,50}$',
            }),
            'description':  forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Décrivez votre boutique...'}),
            'logo':         forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'banniere':     forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'couleur_primaire':   forms.TextInput(attrs={'class': 'form-control form-control-color', 'type': 'color'}),
            'couleur_secondaire': forms.TextInput(attrs={'class': 'form-control form-control-color', 'type': 'color'}),
            'email':        forms.EmailInput(attrs={'class': 'form-control'}),
            'telephone':    forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+237 6XX XXX XXX'}),
            'adresse':      forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'ville':        forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Douala, Yaoundé...'}),
            'site_web':     forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://...'}),
            'facebook':     forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'URL ou @nom'}),
            'instagram':    forms.TextInput(attrs={'class': 'form-control', 'placeholder': '@nom'}),
            'tiktok':       forms.TextInput(attrs={'class': 'form-control', 'placeholder': '@nom'}),
            'whatsapp':     forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+237 6XX XXX XXX'}),
            'delai_traitement': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '30'}),
            'politique_retour': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'conditions_vente': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in ('logo', 'banniere', 'site_web', 'facebook', 'instagram',
                   'tiktok', 'whatsapp', 'telephone', 'adresse', 'ville',
                   'politique_retour', 'conditions_vente'):
            self.fields[f].required = False

    def clean_sous_domaine(self):
        sd = self.cleaned_data.get('sous_domaine', '').lower().strip()
        if not re.match(r'^[a-z0-9-]{3,50}$', sd):
            raise ValidationError("Uniquement lettres minuscules, chiffres et tirets (3–50 caractères).")
        reserved = ['www', 'api', 'admin', 'app', 'mail', 'ftp', 'yopishop', 'shop']
        if sd in reserved:
            raise ValidationError(f"'{sd}' est un sous-domaine réservé.")
        qs = Boutique.objects.filter(sous_domaine=sd)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Ce sous-domaine est déjà pris.")
        return sd

    def clean_nom(self):
        nom = self.cleaned_data.get('nom', '').strip()
        qs  = Boutique.objects.filter(nom__iexact=nom)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Une boutique avec ce nom existe déjà.")
        return nom


class BoutiqueEditerForm(BoutiqueCreerForm):
    """Édition boutique — sous_domaine non modifiable après création."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['sous_domaine'].widget.attrs['readonly'] = True
            self.fields['sous_domaine'].help_text = "Le sous-domaine ne peut plus être modifié."


# =============================================================================
# DOCUMENT KYC
# =============================================================================

class DocumentKYCForm(forms.ModelForm):
    class Meta:
        model  = DocumentKYC
        fields = ['type_document', 'fichier', 'description']
        widgets = {
            'type_document': forms.Select(attrs={'class': 'form-select'}),
            'fichier':       forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*,.pdf',
            }),
            'description':   forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Description optionnelle',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['description'].required = False

    def clean_fichier(self):
        fichier = self.cleaned_data.get('fichier')
        if fichier:
            if fichier.size > 5 * 1024 * 1024:
                raise ValidationError("Le fichier ne peut pas dépasser 5 Mo.")
            ext = fichier.name.rsplit('.', 1)[-1].lower()
            if ext not in ('jpg', 'jpeg', 'png', 'pdf'):
                raise ValidationError("Formats acceptés : JPG, PNG, PDF.")
        return fichier


# =============================================================================
# EMPLOYÉ BOUTIQUE
# =============================================================================

class EmployeBoutiqueForm(forms.ModelForm):
    email_employe = forms.EmailField(
        label="Email de l'employé",
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@exemple.com'}),
    )

    class Meta:
        model  = EmployeBoutique
        fields = ['role', 'est_actif']
        widgets = {
            'role':      forms.Select(attrs={'class': 'form-select'}),
            'est_actif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_email_employe(self):
        from apps_core.models import Utilisateur
        email = self.cleaned_data['email_employe'].lower()
        try:
            self.employe_user = Utilisateur.objects.get(email=email, is_active=True)
        except Utilisateur.DoesNotExist:
            raise ValidationError("Aucun compte actif trouvé avec cet email.")
        return email


# =============================================================================
# AVIS VENDEUR
# =============================================================================

class AvisVendeurForm(forms.ModelForm):
    class Meta:
        model  = AvisVendeur
        fields = [
            'note', 'commentaire',
            'note_communication', 'note_expedition', 'note_emballage',
        ]
        widgets = {
            'note':              forms.HiddenInput(),
            'commentaire':       forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Votre expérience avec ce vendeur...'}),
            'note_communication': forms.HiddenInput(),
            'note_expedition':   forms.HiddenInput(),
            'note_emballage':    forms.HiddenInput(),
        }

    def clean_note(self):
        n = self.cleaned_data.get('note')
        if n is None or not (1 <= n <= 5):
            raise ValidationError("La note doit être entre 1 et 5 étoiles.")
        return n


class ReponseVendeurForm(forms.ModelForm):
    """Réponse d'un vendeur à un avis."""
    class Meta:
        model  = AvisVendeur
        fields = ['reponse_vendeur']
        widgets = {
            'reponse_vendeur': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'Votre réponse publique à cet avis...',
            }),
        }
        labels = {'reponse_vendeur': 'Votre réponse'}


class DateTimeLocalInput(forms.DateTimeInput): 
    input_type = 'datetime-local'



class CodePromoForm(forms.ModelForm): 
    
    class Meta: 
        model = CodePromo 
        fields = [ 'code', 'nom', 'description', 'type_reduction', 'valeur_reduction', 'montant_max_reduction', 'montant_min_commande', 'type_cible', 'utilisateurs_cibles', 'categories_ciblees', 'produits_cibles', 'limite_utilisation_globale', 'limite_par_utilisateur', 'date_debut', 'date_fin', 'statut', 'cumulable', ]
        widgets = { 'code': forms.TextInput(attrs={ 'class': 'form-control', 'placeholder': 'Ex: YOPI20' }), 
            'nom': forms.TextInput(attrs={ 'class': 'form-control', 'placeholder': 'Nom du code promo' }), 
            'description': forms.Textarea(attrs={ 'class': 'form-control', 'rows': 4, 'placeholder': 'Description du code promo' }), 
            'type_reduction': forms.Select(attrs={ 'class': 'form-select' }), 
            'valeur_reduction': forms.NumberInput(attrs={ 'class': 'form-control', 'step': '0.01' }), 
            'montant_max_reduction': forms.NumberInput(attrs={ 'class': 'form-control', 'step': '0.01' }), 
            'montant_min_commande': forms.NumberInput(attrs={ 'class': 'form-control', 'step': '0.01' }), 
            'type_cible': forms.Select(attrs={ 'class': 'form-select' }), 
            'utilisateurs_cibles': forms.SelectMultiple(attrs={ 'class': 'form-select' }), 
            'categories_ciblees': forms.SelectMultiple(attrs={ 'class': 'form-select' }), 
            'produits_cibles': forms.SelectMultiple(attrs={ 'class': 'form-select' }), 
            'limite_utilisation_globale': forms.NumberInput(attrs={ 'class': 'form-control' }), 
            'limite_par_utilisateur': forms.NumberInput(attrs={ 'class': 'form-control' }), 
            'date_debut': DateTimeLocalInput(attrs={ 'class': 'form-control' }), 
            'date_fin': DateTimeLocalInput(attrs={ 'class': 'form-control' }), 
            'statut': forms.Select(attrs={ 'class': 'form-select' }), 
            'cumulable': forms.CheckboxInput(attrs={ 'class': 'form-check-input' }), 
        } 
    def __init__(self, *args, **kwargs): 
        self.user = kwargs.pop('user', None) 
        super().__init__(*args, **kwargs) 
        self.fields['code'].help_text = "Code saisi par le client." 
        self.fields['valeur_reduction'].help_text = "Pourcentage ou montant." 
        self.fields['montant_max_reduction'].help_text = "Optionnel." 
        self.fields['montant_min_commande'].help_text = "Montant minimum requis." 
        self.fields['limite_utilisation_globale'].help_text = "Laisser vide pour illimité." 
        if self.user and not self.user.is_staff: 
            self.fields['utilisateurs_cibles'].queryset = ( self.fields['utilisateurs_cibles'].queryset ) 
    def clean_code(self): 
        code = self.cleaned_data['code'].upper().strip() 
        qs = CodePromo.objects.filter(code=code) 
        if self.instance.pk: 
            qs = qs.exclude(pk=self.instance.pk) 
        if qs.exists(): 
            raise forms.ValidationError( "Ce code promo existe déjà." ) 
            return code 
    def clean(self): 
        cleaned_data = super().clean() 
        date_debut = cleaned_data.get('date_debut') 
        date_fin = cleaned_data.get('date_fin') 
        if date_debut and date_fin: 
            if date_fin <= date_debut: 
                self.add_error( 'date_fin', "La date de fin doit être supérieure à la date de début." ) 
                valeur_reduction = cleaned_data.get('valeur_reduction') 
                type_reduction = cleaned_data.get('type_reduction') 
                if ( type_reduction == 'pourcentage' and valeur_reduction and valeur_reduction > 100 ): 
                    self.add_error( 'valeur_reduction', "Le pourcentage ne peut pas dépasser 100%." ) 
                    return cleaned_data