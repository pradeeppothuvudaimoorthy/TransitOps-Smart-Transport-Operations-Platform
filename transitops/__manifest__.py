# -*- coding: utf-8 -*-
# TransitOps - Smart Transport Operations Platform
# Manifest File

{
    'name': 'TransitOps - Smart Transport Operations Platform',
    'version': '18.0.1.0.0',
    'category': 'Transport/Fleet',
    'summary': 'Complete digitized transport operations platform covering fleet, '
               'drivers, dispatching, maintenance, fuel and expense management.',
    'description': """
        TransitOps Smart Transport Operations Platform
        ==============================================

        A production-quality ERP module for transport companies to manage:

        * Vehicle Fleet Management
        * Driver Management & License Tracking
        * Trip Dispatching & Completion Workflow
        * Preventive & Reactive Maintenance
        * Fuel Logging & Efficiency Tracking
        * Expense Management
        * Analytics & ROI Reporting
        * Dashboard KPIs
        * Automated License Expiry Alerts
        * Role-Based Access Control
    """,
    'author': 'TransitOps Team',
    'website': 'https://www.transitops.io',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'web',
    ],
    'data': [
        # Security (load first)
        'security/ir.model.access.csv',
        'security/security.xml',

        # Data (load before views)
        'data/sequences.xml',
        'data/scheduled_actions.xml',
        'data/expense_types.xml',

        # Views
        'views/vehicle_views.xml',
        'views/driver_views.xml',
        'views/trip_views.xml',
        'views/maintenance_views.xml',
        'views/fuel_log_views.xml',
        'views/expense_views.xml',
        'views/dashboard_views.xml',
        'views/report_views.xml',
        'views/menus.xml',

        # Reports
        'reports/trip_report.xml',
        'reports/vehicle_report.xml',

        # Wizards
        'wizard/trip_cancel_wizard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # Google Fonts — Poppins (preloaded for zero FOUT)
            'https://fonts.gstatic.com',
            'https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700;800;900&display=swap',
            # TransitOps Design System v2
            'transitops/static/src/css/transitops.css',
            'transitops/static/src/js/firebase_service.js',
            'transitops/static/src/js/dashboard.js',
        ],
    },
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'images': ['static/description/banner.png'],
}
