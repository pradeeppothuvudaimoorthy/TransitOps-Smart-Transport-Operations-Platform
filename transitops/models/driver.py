# -*- coding: utf-8 -*-
"""
TransitOps - Driver Model
=========================
Manages driver records including license lifecycle, safety scoring,
status tracking, and automatic license-validity computation.
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from datetime import date
import logging

_logger = logging.getLogger(__name__)


class TransitDriver(models.Model):
    """
    Represents a professional driver in the TransitOps fleet.

    Business Rules
    --------------
    * License Number is unique per driver (SQL constraint).
    * license_valid is automatically False once expiry date has passed.
    * Only drivers with status='available' and valid licenses can be assigned to trips.
    * Status transitions are logged to the chatter for audit purposes.
    """
    _name = 'transit.driver'
    _description = 'Transit Driver'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name asc'
    _rec_name = 'name'

    # ------------------------------------------------------------------
    # Personal Information
    # ------------------------------------------------------------------
    name = fields.Char(
        string='Full Name',
        required=True,
        tracking=True,
    )
    contact_number = fields.Char(
        string='Contact Number',
        tracking=True,
        help='Primary mobile or landline number for the driver.',
    )
    photo = fields.Image(
        string='Photo',
        max_width=256,
        max_height=256,
    )

    # ------------------------------------------------------------------
    # License Information
    # ------------------------------------------------------------------
    license_number = fields.Char(
        string='License Number',
        required=True,
        copy=False,
        tracking=True,
        help='Government-issued driving license identification number.',
    )
    license_category = fields.Selection(
        selection=[
            ('A', 'Class A – Heavy Trucks'),
            ('B', 'Class B – Light Trucks'),
            ('C', 'Class C – Public Service'),
            ('D', 'Class D – Dangerous Goods'),
            ('E', 'Class E – Trailers/Articulated'),
        ],
        string='License Category',
        required=True,
        tracking=True,
        help='License class determines the types of vehicles the driver may operate.',
    )
    license_expiry_date = fields.Date(
        string='License Expiry Date',
        required=True,
        tracking=True,
        help='Date after which the license is no longer legally valid.',
    )
    license_valid = fields.Boolean(
        string='License Valid',
        compute='_compute_license_valid',
        store=True,
        tracking=True,
        help='Automatically set to False when the license expiry date has passed.',
    )
    days_to_expiry = fields.Integer(
        string='Days to Expiry',
        compute='_compute_license_valid',
        store=True,
        help='Number of days remaining until license expiry. Negative = already expired.',
    )

    # ------------------------------------------------------------------
    # Safety & Performance
    # ------------------------------------------------------------------
    safety_score = fields.Float(
        string='Safety Score',
        digits=(5, 2),
        default=100.0,
        tracking=True,
        help='Safety score out of 100. Decremented on violations or incidents.',
    )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    status = fields.Selection(
        selection=[
            ('available', 'Available'),
            ('on_trip', 'On Trip'),
            ('off_duty', 'Off Duty'),
            ('suspended', 'Suspended'),
        ],
        string='Status',
        default='available',
        required=True,
        tracking=True,
        index=True,
        help='Current operational availability status of the driver.',
    )

    # ------------------------------------------------------------------
    # Relations
    # ------------------------------------------------------------------
    trip_ids = fields.One2many(
        comodel_name='transit.trip',
        inverse_name='driver_id',
        string='Trip History',
        readonly=True,
    )
    trip_count = fields.Integer(
        string='Trips',
        compute='_compute_trip_count',
        store=False,
    )
    total_trips_completed = fields.Integer(
        string='Trips Completed',
        compute='_compute_performance_stats',
        store=True,
        help='Total number of successfully completed trips.',
    )
    total_distance_driven = fields.Float(
        string='Total Distance (km)',
        compute='_compute_performance_stats',
        store=True,
        digits=(10, 2),
        help='Cumulative actual distance driven across all completed trips.',
    )

    # ------------------------------------------------------------------
    # SQL Constraints
    # ------------------------------------------------------------------
    _sql_constraints = [
        (
            'unique_license_number',
            'UNIQUE(license_number)',
            'A driver with this License Number already exists. '
            'Each driver must have a unique license number.',
        ),
        (
            'valid_safety_score',
            'CHECK(safety_score >= 0 AND safety_score <= 100)',
            'Safety score must be between 0 and 100.',
        ),
    ]

    # ------------------------------------------------------------------
    # Compute Methods
    # ------------------------------------------------------------------
    @api.depends('license_expiry_date')
    def _compute_license_valid(self):
        """
        Determines license validity and remaining days.
        Runs on expiry date change; also triggered daily by scheduled action.

        NOTE: date.today() is evaluated inside the loop so that long-running
        batch recomputes (e.g. nightly cron spanning midnight) use the correct
        date for every record rather than the stale value captured at loop start.
        """
        for driver in self:
            today = date.today()  # Re-evaluated per record — safe for batch jobs
            if driver.license_expiry_date:
                delta = (driver.license_expiry_date - today).days
                driver.days_to_expiry = delta
                driver.license_valid = delta >= 0
            else:
                driver.days_to_expiry = 0
                driver.license_valid = False

    @api.depends('trip_ids')
    def _compute_trip_count(self):
        """Recomputes whenever trip_ids changes (trips added or removed)."""
        for driver in self:
            driver.trip_count = len(driver.trip_ids)

    @api.depends('trip_ids', 'trip_ids.status', 'trip_ids.actual_distance')
    def _compute_performance_stats(self):
        """Aggregate completed trip stats for this driver."""
        for driver in self:
            completed = driver.trip_ids.filtered(lambda t: t.status == 'completed')
            driver.total_trips_completed = len(completed)
            driver.total_distance_driven = sum(completed.mapped('actual_distance'))

    # ------------------------------------------------------------------
    # Python Constraints
    # ------------------------------------------------------------------
    @api.constrains('license_expiry_date')
    def _check_license_expiry(self):
        """Warn if a newly created driver already has an expired license."""
        for driver in self:
            if driver.license_expiry_date and driver.license_expiry_date < date.today():
                _logger.warning(
                    'Driver [%s] has an already-expired license (%s).',
                    driver.name, driver.license_expiry_date,
                )

    @api.constrains('safety_score')
    def _check_safety_score(self):
        for driver in self:
            if not (0.0 <= driver.safety_score <= 100.0):
                raise ValidationError(
                    _('Safety score for driver "%s" must be between 0 and 100.') % driver.name
                )

    # ------------------------------------------------------------------
    # Status Transition Helper
    # ------------------------------------------------------------------
    def _set_status(self, new_status, reason=''):
        """
        Internal status transition helper with chatter logging.
        Called by trip model during dispatch / completion / cancellation.
        """
        self.ensure_one()
        old_label = dict(self._fields['status'].selection).get(self.status, self.status)
        new_label = dict(self._fields['status'].selection).get(new_status, new_status)
        self.status = new_status
        msg = _(
            'Driver status changed: <b>%(old)s</b> → <b>%(new)s</b>%(reason)s',
            old=old_label,
            new=new_label,
            reason=f'. {reason}' if reason else '',
        )
        self.message_post(body=msg)
        _logger.info('Driver [%s] status: %s → %s', self.name, old_label, new_status)

    # ------------------------------------------------------------------
    # Manual Status Actions (UI Buttons)
    # ------------------------------------------------------------------
    def action_set_off_duty(self):
        for driver in self:
            if driver.status == 'on_trip':
                raise ValidationError(
                    _('Driver "%s" is currently On Trip and cannot be set Off Duty.') % driver.name
                )
            driver._set_status('off_duty', reason='Manually set to Off Duty.')

    def action_set_available(self):
        for driver in self:
            if driver.status == 'suspended':
                raise ValidationError(
                    _('Suspended driver "%s" must be reviewed before being set Available.') % driver.name
                )
            driver._set_status('available', reason='Manually set to Available.')

    def action_suspend(self):
        for driver in self:
            if driver.status == 'on_trip':
                raise ValidationError(
                    _('Driver "%s" is currently On Trip. Complete or cancel the trip first.') % driver.name
                )
            driver._set_status('suspended', reason='Suspended by Fleet Manager.')

    def action_view_trips(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Trips for %s') % self.name,
            'res_model': 'transit.trip',
            'view_mode': 'list,form',
            'domain': [('driver_id', '=', self.id)],
            'context': {'default_driver_id': self.id},
        }

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    @api.model
    def _name_search(self, name='', domain=None, operator='ilike', limit=100, order=None):
        """Allow searching by name or license number."""
        if domain is None:
            domain = []
        if name:
            domain = [
                '|',
                ('name', operator, name),
                ('license_number', operator, name),
            ] + domain
        return self._search(domain, limit=limit, order=order)
