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

# Magento
MAGENTO_URL = os.getenv('MAGENTO_URL', 'https://reflexmania.it')
MAGENTO_TOKEN = os.getenv('MAGENTO_TOKEN', '9f58bc0d4s7mutmz816i85evfooq2jfp')

# InvoiceX DB
INVOICEX_CONFIG = {
    'user': os.getenv('INVOICEX_USER', 'ilblogdi_inv2021'),
    'password': os.getenv('INVOICEX_PASS', 'pWTrEKV}=fF-'),
    'host': os.getenv('INVOICEX_HOST', 'nl1-ts3.a2hosting.com'),
    'database': os.getenv('INVOICEX_DB', 'ilblogdi_invoicex2021'),
}

# InvoiceX API (esterne)
INVOICEX_API_URL = os.getenv('INVOICEX_API_URL', 'https://api.reflexmania.it/')
INVOICEX_API_KEY = os.getenv('INVOICEX_API_KEY', '52bf3c1f206dae8e45bf647cda396172')

# ============================================================================
# ANASTASIA DATABASE (MySQL A2Hosting)
# ============================================================================
ANASTASIA_DB_CONFIG = {
    'host': os.getenv('ANASTASIA_HOST', 'nl1-ts3.a2hosting.com'),
    'port': int(os.getenv('ANASTASIA_PORT', 3306)),
    'database': os.getenv('ANASTASIA_DB', 'ilblogdi_anastasia'),
    'user': os.getenv('ANASTASIA_USER', 'ilblogdi_anastasia'),
    'password': os.getenv('ANASTASIA_PASS', 'cd9g!1g4yvq_'),
    'connect_timeout': 10,
    'autocommit': True
}

# URL sistema Anastasia
ANASTASIA_URL = os.getenv('ANASTASIA_URL', 'https://anastasia.reflexmania.com')

# Flask
SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

# Logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# Database (per sistema ordini locale - opzionale)
DATABASE_URI = os.getenv(
    'DATABASE_URL',
    'postgresql://postgres:postgres@localhost:5432/reflexmania'
)