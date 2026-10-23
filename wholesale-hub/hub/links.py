"""Build store search links from a template such as https://site.com/search?q={q}."""
from urllib.parse import quote, quote_plus


def search_url(template, query):
    if not template:
        return ""
    encoded = quote_plus(query) if "?" in template else quote(query)
    return template.replace("{q}", encoded)
