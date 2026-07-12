# -*- coding: utf-8 -*-
"""
TransitOps - Vehicle Model
==========================
Manages the entire vehicle fleet lifecycle including status tracking,
odometer management, cost analytics and relational aggregations.
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class TransitVehicle(models.Model):
    """
    Core vehicle entity for the TransitOps platform.

    Business Rules
    --------------
    * Registration Number is globally unique (SQL constraint).
    * Status drives availability for trip assignment and maintenance.
    * Analytics fields are stored computed to allow efficient SQL queries.
    """
    _name = 'transit.vehicle'
    _description = 'Transit Vehicle'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name asc'
    _rec_name = 'name'

    # ------------------------------------------------------------------
    # Basic Information
    # ------------------------------------------------------------------
    name = fields.Char(
        string='Vehicle Name',
        required=True,
        tracking=True,
        help='Friendly name or alias for the vehicle (e.g. "Truck Alpha").',
    )
    registration_number = fields.Char(
        string='Registration Number',
        required=True,
        tracking=True,
        copy=False,
        help='Official government registration plate. Must be unique across the fleet.',
    )
    vehicle_type = fields.Selection(
        selection=[
            ('truck', 'Truck'),
            ('van', 'Van'),
            ('pickup', 'Pickup'),
            ('tanker', 'Tanker'),
            ('trailer', 'Trailer'),
            ('bus', 'Bus'),
            ('motorcycle', 'Motorcycle'),
            ('other', 'Other'),
        ],
        string='Vehicle Type',
        required=True,
        default='truck',
        tracking=True,
    )
    region = fields.Char(
        string='Region / Zone',
        tracking=True,
        help='Operational region or depot zone this vehicle is based in.',
    )

    # ------------------------------------------------------------------
    # Capacity & Engine
    # ------------------------------------------------------------------
    max_load_capacity = fields.Float(
        string='Max Load Capacity (kg)',
        required=True,
        digits=(10, 2),
        tracking=True,
        help='Maximum payload the vehicle can legally carry in kilograms.',
    )
    fuel_type = fields.Selection(
        selection=[
            ('diesel', 'Diesel'),
            ('petrol', 'Petrol'),
            ('cng', 'CNG'),
            ('electric', 'Electric'),
            ('hybrid', 'Hybrid'),
            ('lpg', 'LPG'),
        ],
        string='Fuel Type',
        required=True,
        default='diesel',
        tracking=True,
    )

    # ------------------------------------------------------------------
    # Odometer & Cost
    # ------------------------------------------------------------------
    current_odometer = fields.Float(
        string='Current Odometer (km)',
        digits=(10, 2),
        tracking=True,
        help='Running total of kilometres driven. Updated on trip completion.',
    )
    acquisition_cost = fields.Float(
        string='Acquisition Cost',
        digits=(10, 2),
        tracking=True,
        help='Original purchase / acquisition cost of the vehicle.',
    )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    status = fields.Selection(
        selection=[
            ('available', 'Available'),
            ('on_trip', 'On Trip'),
            ('in_shop', 'In Shop'),
            ('retired', 'Retired'),
        ],
        string='Status',
        default='available',
        required=True,
        tracking=True,
        index=True,
        help='Current operational status of the vehicle.',
    )

    # ------------------------------------------------------------------
    # One-to-Many Relations
    # ------------------------------------------------------------------
    trip_ids = fields.One2many(
        comodel_name='transit.trip',
        inverse_name='vehicle_id',
        string='Trips',
        readonly=True,
    )
    maintenance_ids = fields.One2many(
        comodel_name='transit.maintenance',
        inverse_name='vehicle_id',
        string='Maintenance Records',
        readonly=True,
    )
    fuel_log_ids = fields.One2many(
        comodel_name='transit.fuel.log',
        inverse_name='vehicle_id',
        string='Fuel Logs',
        readonly=True,
    )
    expense_ids = fields.One2many(
        comodel_name='transit.expense',
        inverse_name='vehicle_id',
        string='Expenses',
        readonly=True,
    )

    # ------------------------------------------------------------------
    # Stat-Button Counts
    # ------------------------------------------------------------------
    trip_count = fields.Integer(
        string='Trips',
        compute='_compute_trip_count',
        store=False,
    )
    maintenance_count = fields.Integer(
        string='Maintenance',
        compute='_compute_maintenance_count',
        store=False,
    )
    fuel_log_count = fields.Integer(
        string='Fuel Logs',
        compute='_compute_fuel_log_count',
        store=False,
    )
    expense_count = fields.Integer(
        string='Expenses',
        compute='_compute_expense_count',
        store=False,
    )

    # ------------------------------------------------------------------
    # Analytics (Stored Computed — for dashboard SQL efficiency)
    # ------------------------------------------------------------------
    total_fuel_cost = fields.Float(
        string='Total Fuel Cost',
        compute='_compute_analytics',
        store=True,
        digits=(10, 2),
        help='Sum of all fuel expenses for this vehicle.',
    )
    total_maintenance_cost = fields.Float(
        string='Total Maintenance Cost',
        compute='_compute_analytics',
        store=True,
        digits=(10, 2),
        help='Sum of all maintenance expenses for this vehicle.',
    )
    total_operational_cost = fields.Float(
        string='Total Operational Cost',
        compute='_compute_analytics',
        store=True,
        digits=(10, 2),
        help='Sum of all expenses (fuel + maintenance + other).',
    )
    total_revenue = fields.Float(
        string='Total Revenue',
        compute='_compute_analytics',
        store=True,
        digits=(10, 2),
        help='Sum of revenue from all completed trips.',
    )
    roi = fields.Float(
        string='ROI',
        compute='_compute_roi',
        store=True,
        digits=(6, 4),
        help='Return on Investment = (Revenue - Fuel - Maintenance) / Acquisition Cost.',
    )

    # ------------------------------------------------------------------
    # SQL Constraints
    # ------------------------------------------------------------------
    _sql_constraints = [
        (
            'unique_registration_number',
            'UNIQUE(registration_number)',
            'A vehicle with this Registration Number already exists. '
            'Each vehicle must have a unique registration plate.',
        ),
        (
            'positive_max_load',
            'CHECK(max_load_capacity > 0)',
            'Maximum load capacity must be a positive value.',
        ),
        (
            'non_negative_odometer',
            'CHECK(current_odometer >= 0)',
            'Odometer reading cannot be negative.',
        ),
        (
            'non_negative_acquisition_cost',
            'CHECK(acquisition_cost >= 0)',
            'Acquisition cost cannot be negative.',
        ),
    ]

    # ------------------------------------------------------------------
    # Compute Methods
    # ------------------------------------------------------------------
    def _compute_trip_count(self):
        for vehicle in self:
            vehicle.trip_count = len(vehicle.trip_ids)

    def _compute_maintenance_count(self):
        for vehicle in self:
            vehicle.maintenance_count = len(vehicle.maintenance_ids)

    def _compute_fuel_log_count(self):
        for vehicle in self:
            vehicle.fuel_log_count = len(vehicle.fuel_log_ids)

    def _compute_expense_count(self):
        for vehicle in self:
            vehicle.expense_count = len(vehicle.expense_ids)

    @api.depends(
        'expense_ids', 'expense_ids.amount', 'expense_ids.expense_type',
        'trip_ids', 'trip_ids.revenue', 'trip_ids.status',
    )
    def _compute_analytics(self):
        """
        Aggregate financial data from related expense and trip records.
        Uses mapped() for efficient in-memory summation without extra queries.
        """
        for vehicle in self:
            fuel_expenses = vehicle.expense_ids.filtered(
                lambda e: e.expense_type == 'fuel'
            )
            maintenance_expenses = vehicle.expense_ids.filtered(
                lambda e: e.expense_type == 'maintenance'
            )
            completed_trips = vehicle.trip_ids.filtered(
                lambda t: t.status == 'completed'
            )

            vehicle.total_fuel_cost = sum(fuel_expenses.mapped('amount'))
            vehicle.total_maintenance_cost = sum(maintenance_expenses.mapped('amount'))
            vehicle.total_operational_cost = sum(vehicle.expense_ids.mapped('amount'))
            vehicle.total_revenue = sum(completed_trips.mapped('revenue'))

    @api.depends('total_revenue', 'total_fuel_cost', 'total_maintenance_cost', 'acquisition_cost')
    def _compute_roi(self):
        """
        ROI = (Revenue - Fuel Cost - Maintenance Cost) / Acquisition Cost
        Returns 0 if acquisition cost is zero to avoid division by zero.
        """
        for vehicle in self:
            if vehicle.acquisition_cost:
                net = (
                    vehicle.total_revenue
                    - vehicle.total_fuel_cost
                    - vehicle.total_maintenance_cost
                )
                vehicle.roi = net / vehicle.acquisition_cost
            else:
                vehicle.roi = 0.0

    # ------------------------------------------------------------------
    # Python Constraints
    # ------------------------------------------------------------------
    @api.constrains('registration_number')
    def _check_registration_number(self):
        """Ensure registration number is not blank or whitespace-only."""
        for vehicle in self:
            if not vehicle.registration_number or not vehicle.registration_number.strip():
                raise ValidationError(
                    _('Registration Number cannot be empty or contain only spaces.')
                )

    # ------------------------------------------------------------------
    # Status Transition Helpers
    # ------------------------------------------------------------------
    def _set_status(self, new_status, reason=''):
        """
        Internal helper to change vehicle status with chatter logging.
        Called by trip/maintenance models.
        """
        self.ensure_one()
        old_status = dict(self._fields['status'].selection).get(self.status, self.status)
        new_label = dict(self._fields['status'].selection).get(new_status, new_status)
        self.status = new_status
        msg = _(
            'Vehicle status changed: <b>%(old)s</b> → <b>%(new)s</b>%(reason)s',
            old=old_status,
            new=new_label,
            reason=f'. {reason}' if reason else '',
        )
        self.message_post(body=msg)
        _logger.info('Vehicle [%s] status: %s → %s', self.registration_number, old_status, new_status)

    # ------------------------------------------------------------------
    # Action Methods (Stat Buttons)
    # ------------------------------------------------------------------
    def action_view_trips(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Trips for %s') % self.name,
            'res_model': 'transit.trip',
            'view_mode': 'list,form',
            'domain': [('vehicle_id', '=', self.id)],
            'context': {'default_vehicle_id': self.id},
        }

    def action_view_maintenance(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Maintenance for %s') % self.name,
            'res_model': 'transit.maintenance',
            'view_mode': 'list,form',
            'domain': [('vehicle_id', '=', self.id)],
            'context': {'default_vehicle_id': self.id},
        }

    def action_view_fuel_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Fuel Logs for %s') % self.name,
            'res_model': 'transit.fuel.log',
            'view_mode': 'list,form',
            'domain': [('vehicle_id', '=', self.id)],
            'context': {'default_vehicle_id': self.id},
        }

    def action_view_expenses(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Expenses for %s') % self.name,
            'res_model': 'transit.expense',
            'view_mode': 'list,form',
            'domain': [('vehicle_id', '=', self.id)],
            'context': {'default_vehicle_id': self.id},
        }

    def action_retire_vehicle(self):
        """Retire the vehicle. Cannot be undone without Fleet Manager rights."""
        for vehicle in self:
            if vehicle.status == 'on_trip':
                raise ValidationError(
                    _('Cannot retire vehicle "%s" while it is On Trip.') % vehicle.name
                )
            if vehicle.status == 'in_shop':
                raise ValidationError(
                    _('Cannot retire vehicle "%s" while it is In Shop. '
                      'Close the maintenance record first.') % vehicle.name
                )
            vehicle._set_status('retired', reason='Vehicle retired from fleet.')

    # ------------------------------------------------------------------
    # Search / Name Search
    # ------------------------------------------------------------------
    @api.model
    def _name_search(self, name='', domain=None, operator='ilike', limit=100, order=None):
        """
        Allow searching by both vehicle name and registration number
        so dispatchers can quickly locate a vehicle by plate.
        """
        if domain is None:
            domain = []
        if name:
            domain = [
                '|',
                ('name', operator, name),
                ('registration_number', operator, name),
            ] + domain
        return self._search(domain, limit=limit, order=order)
