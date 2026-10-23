"""Turns the providers section of the settings into provider objects."""
from .csv_import import CsvImportProvider
from .demo import DemoProvider
from .ebay import EbayProvider


def build(cfg):
    pc = cfg["providers"]
    out = []
    if pc["demo"]["enabled"]:
        out.append(DemoProvider(pc["demo"], cfg))
    if pc["csv_import"]["enabled"]:
        out.append(CsvImportProvider(pc["csv_import"], cfg))
    if pc["ebay"]["enabled"]:
        out.append(EbayProvider(pc["ebay"], cfg))
    return out
