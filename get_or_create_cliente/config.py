#!/usr/bin/env python3
"""
Configurazioni per il sistema ReflexMania
"""
import os

# BackMarket
BACKMARKET_TOKEN = os.getenv('BACKMARKET_TOKEN', 'NDNjYzQzMDRmNGU2NTUzYzkzYjAwYjpCTVQtOTJhZjQ0MjU5YTlhMmYzMGRhMzA3YWJhZWMwZGI5YzUwMjAxMTdhYQ==')
BACKMARKET_BASE_URL = "https://www.backmarket.fr"

# Refurbed
REFURBED_TOKEN = os.getenv('REFURBED_TOKEN', '277931ea-1ede-4a14-8aaa-41b2222d2aba')
REFURBED_BASE_URL = "https://api.refurbed.com"

# CDiscount (Octopia)
OCTOPIA_CLIENT_ID = os.getenv('OCTOPIA_CLIENT_ID', 'reflexmania')
OCTOPIA_CLIENT_SECRET = os.getenv('OCTOPIA_CLIENT_SECRET', 'qTpoc2gd40Huhzi64FIKY6f9NoKac0C6')
OCTOPIA_SELLER_ID = os.getenv('OCTOPIA_SELLER_ID', '405765')

# InvoiceX DB
INVOICEX_CONFIG = {
    'user': os.getenv('INVOICEX_USER', 'ilblogdi_inv2021'),
    'password': os.getenv('INVOICEX_PASS', 'pWTrEKV}=fF-'),
    'host': os.getenv('INVOICEX_HOST', 'nl1-ts3.a2hosting.com'),
    'database': os.getenv('INVOICEX_DB', 'ilblogdi_invoicex2021'),
}
