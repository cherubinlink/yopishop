# Dans apps_social/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import AbonnementSocial
from apps_core.views import creer_notification

@receiver(post_save, sender=AbonnementSocial)
def notifier_nouvel_abonnement(sender, instance, created, **kwargs):
    if not created:
        return
    creer_notification(
        utilisateur=instance.suivi,
        type_notification='social',
        titre=f"@{instance.abonne.username} vous suit !",
        message=f"{instance.abonne.username} s'est abonné à votre profil.",
        lien=f"/social/@{instance.abonne.username}/",
    )