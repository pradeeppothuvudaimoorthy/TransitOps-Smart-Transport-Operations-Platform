# -*- coding: utf-8 -*-
"""
TransitOps - Fuel Log Model
============================
Records fuel consumption events per vehicle / trip.
Computes fuel efficiency (km/L) and automatically creates
an expense record on save.
"""

from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)


class TransitFuelLog(models.Model):
    """
    Single fuel fill-up or consumption event.

    Auto-creates a transit.expense (type='fuel') on creation.
    """
    _name = 'transit.fuel.log'
    _description = 'Transit Fuel Log'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'
    _rec_name = 'reference'

    # ------------------------------------------------------------------
    # Identification
    # ------------------------------------------------------------------
    reference = fields.Char(
        string='Reference',
        readonly=True,
        copy=False,
        default=lambda self: _('New'),
    )

    # ------------------------------------------------------------------
    # Core Fields
    # ------------------------------------------------------------------
    vehicle_id = fields.Many2one(
        comodel_name='transit.vehicle',
        string='Vehicle',
        required=True,
        tracking=True,
        ondelete='restrict',
    )
    trip_id = fields.Many2one(
        comodel_name='transit.trip',
        string='Trip',
        tracking=True,
        # Domain evaluated at runtime: only trips belonging to the selected vehicle.
        # A lambda is required here because string domains cannot reference
        # sibling field values in a Python model field definition.
        domain=lambda self: [('vehicle_id', '=', self.vehicle_id.id)] if self.vehicle_id else [],
        ondelete='set null',
        help='Associated trip. Leave blank for depot fill-ups.',
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    fuel_liters = fields.Float(
        string='Fuel (Liters)',
        required=True,
        digits=(10, 2),
        tracking=True,
    )
    fuel_cost = fields.Float(
        string='Fuel Cost',
        digits=(10, 2),
        tracking=True,
        help='Total cost of fuel for this fill-up event.',
    )
    distance = fields.Float(
        string='Distance Covered (km)',
        digits=(10, 2),
        tracking=True,
        help='Distance driven on this fuel load.',
    )

    # ------------------------------------------------------------------
    # Computed
    # ------------------------------------------------------------------
    fuel_efficiency = fields.Float(
        string='Fuel Efficiency (km/L)',
        compute='_compute_fuel_efficiency',
        store=True,
        digits=(6, 2),
        help='Distance per liter. Higher is more efficient.',
    )

    # ------------------------------------------------------------------
    # Linked Expense
    # ------------------------------------------------------------------
    expense_id = fields.Many2one(
        comodel_name='transit.expense',
        string='Related Expense',
        readonly=True,
        copy=False,
    )

    # ------------------------------------------------------------------
    # SQL Constraints
    # ------------------------------------------------------------------
    _sql_constraints = [
        (
            'positive_fuel_liters',
            'CHECK(fuel_liters > 0)',
            'Fuel liters must be a positive value.',
        ),
        (
            'non_negative_fuel_cost',
            'CHECK(fuel_cost >= 0)',
            'Fuel cost cannot be negative.',
        ),
        (
            'non_negative_distance',
            'CHECK(distance >= 0)',
            'Distance cannot be negative.',
        ),
    ]

    # ------------------------------------------------------------------
    # Compute Methods
    # ------------------------------------------------------------------
    @api.depends('distance', 'fuel_liters')
    def _compute_fuel_efficiency(self):
        """
        Fuel Efficiency = Distance / Fuel Liters
        Returns 0 if either value is zero.
        """
        for log in self:
            if log.fuel_liters and log.distance:
                log.fuel_efficiency = log.distance / log.fuel_liters
            else:
                log.fuel_efficiency = 0.0

    # ------------------------------------------------------------------
    # ORM Overrides
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        """Assign sequence and auto-create expense on fuel log creation."""
        for vals in vals_list:
            if vals.get('reference', _('New')) == _('New'):
                vals['reference'] = self.env['ir.sequence'].next_by_code(
                    'transit.fuel.log.sequence'
                ) or _('New')

        records = super().create(vals_list)

        for record in records:
            record._create_fuel_expense()

        return records

    def write(self, vals):
        """Keep linked expense amount in sync with fuel_cost changes."""
        result = super().write(vals)
        if 'fuel_cost' in vals:
            for record in self:
                if record.expense_id:
                    record.expense_id.amount = record.fuel_cost
        return result

    # ------------------------------------------------------------------
    # Expense Auto-Creation
    # ------------------------------------------------------------------
    def _create_fuel_expense(self):
        """
        Automatically create a transit.expense (type='fuel') when
        a fuel log is created. Prevents duplicate manual entries.
        """
        self.ensure_one()
        if self.expense_id:
            return
        expense = self.env['transit.expense'].create({
            'vehicle_id': self.vehicle_id.id,
            'trip_id': self.trip_id.id if self.trip_id else False,
            'expense_type': 'fuel',
            'amount': self.fuel_cost,
            'date': self.date,
            'description': (
                f'Auto-generated: Fuel Log {self.reference} — '
                f'{self.fuel_liters} L on {self.date}'
            ),
        })
        self.expense_id = expense.id
        _logger.info(
            'Auto-created fuel expense [%d] for fuel log [%s]',
            expense.id, self.reference,
        )
