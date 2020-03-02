# -*- coding: utf-8 -*-
# Part of Cnmx. See LICENSE file for full copyright and licensing details.

{
    'name': 'UTM Trackers',
    'category': 'Hidden',
    'description': """
Enable management of UTM trackers: campaign, medium, source.
""",
    'version': '1.0',
    'depends': ['base', 'web'],
    'data': [
        'data/utm_data.xml',
        'views/assets.xml',
        'views/utm_campaign_views.xml',
        'views/utm_views.xml',
        'security/ir.model.access.csv',
    ],
    'demo': [],
    'auto_install': False,
}
