from django import template

register = template.Library()

@register.filter
def split(value, arg):
    """Divise une chaîne par le séparateur donné."""
    return value.split(arg)

@register.filter
def split(value, separator=','):
    """
    Découpe une chaîne en liste.
    Exemple :
    {{ "a,b,c"|split:"," }}
    """
    if value:
        return value.split(separator)
    return []


@register.filter
def sub(value, arg):
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0