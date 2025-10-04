#!/usr/bin/env python3
"""
Services package
"""
from .order_service import (
    get_pending_orders, 
    normalize_order, 
    disable_product_on_channels,
    create_ddt_invoicex,  # Questa rimane in order_service.py
    get_or_create_cliente  # Questa rimane in order_service.py
)

# Il nuovo DDTService è importato direttamente dove serve
# from services.ddt_service import DDTService

__all__ = [
    'create_ddt_invoicex',
    'get_or_create_cliente', 
    'get_pending_orders',
    'normalize_order',
    'disable_product_on_channels'
]