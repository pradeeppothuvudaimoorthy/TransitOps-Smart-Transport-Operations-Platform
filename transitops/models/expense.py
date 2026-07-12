# -*- coding: utf-8 -*-
"""
TransitOps - Expense Model
============================
General expense tracking for the fleet. Expenses may be created
manually or automatically by fuel log / maintenance creation.

Types: fuel, maintenance, toll, insurance, repair, other.
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class TransitExpense(models.Model):
    """
    Financial expense record for a vehicle / trip.

    Auto-creation Sources
    ---------------------
    * transit.fuel.log.create()       → type='fuel'
    * transit.maintenance.create()    → type='maintenance'

    Manual creation is also allowed for toll, insurance, repair, other types.
    """
    _name = 'transit.expense'
    _description = 'Transit Expense'
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
        domain="[('vehicle_id', '=', vehicle_id)]",
        ondelete='set null',
        help='Link this expense to a specific trip (optional).',
    )
    expense_type = fields.Selection(
        selection=[
            ('fuel', 'Fuel'),
            ('maintenance', 'Maintenance'),
            ('toll', 'Toll'),
            ('insurance', 'Insurance'),
            ('repair', 'Repair'),
            ('other', 'Other'),
        ],
        string='Expense Type',
        required=True,
        tracking=True,
        default='other',
    )
    amount = fields.Float(
        string='Amount',
        required=True,
        digits=(10, 2),
        tracking=True,
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    description = fields.Text(
        string='Description / Notes',
        tracking=True,
    )

    # ------------------------------------------------------------------
    # SQL Constraints
    # ------------------------------------------------------------------
    _sql_constraints = [
        (
            'non_negative_amount',
            'CHECK(amount >= 0)',
            'Expense amount cannot be negative.',
        ),
    ]

    # ------------------------------------------------------------------
    # Python Constraints
    # ------------------------------------------------------------------
    @api.constrains('amount')
    def _check_amount(self):
        for expense in self:
            if expense.amount < 0:
                raise ValidationError(
                    _('Expense amount cannot be negative for record %s.') % expense.reference
                )

    # ------------------------------------------------------------------
    # ORM Override
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        """Assign sequence reference on creation."""
        for vals in vals_list:
            if vals.get('reference', _('New')) == _('New'):
                vals['reference'] = self.env['ir.sequence'].next_by_code(
                    'transit.expense.sequence'
                ) or _('New')
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Reporting Helpers
    # ------------------------------------------------------------------
    @api.model
    def get_expenses_by_type(self, vehicle_id=None, date_from=None, date_to=None):
        """
        Return a dict of {expense_type: total_amount} for reporting.

        Args:
            vehicle_id (int, optional): Filter to a specific vehicle.
            date_from (date, optional): Start date filter.
            date_to (date, optional): End date filter.

        Returns:
            dict: Mapping of expense type label → total amount.
        """
        domain = []
        if vehicle_id:
            domain.append(('vehicle_id', '=', vehicle_id))
        if date_from:
            domain.append(('date', '>=', date_from))
        if date_to:
            domain.append(('date', '<=', date_to))

        expenses = self.search(domain)
        result = {}
        type_labels = dict(self._fields['expense_type'].selection)
        for expense in expenses:
            label = type_labels.get(expense.expense_type, expense.expense_type)
            result[label] = result.get(label, 0.0) + expense.amount
        return result
