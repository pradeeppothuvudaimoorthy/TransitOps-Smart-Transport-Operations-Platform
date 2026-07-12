# -*- coding: utf-8 -*-
"""
TransitOps - Maintenance Model
================================
Tracks vehicle maintenance / repair events. Creating a maintenance record
automatically sets the vehicle to "In Shop". Closing it restores to "Available"
(unless the vehicle has been retired).

Automatically creates an expense record on creation.
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class TransitMaintenance(models.Model):
    """
    Preventive and reactive maintenance records linked to a vehicle.

    Workflow
    --------
    active → closed

    Side-effects
    ------------
    * On create  → vehicle.status = 'in_shop'
    * On close   → vehicle.status = 'available' (if not retired)
    * On create  → transit.expense created automatically
    """
    _name = 'transit.maintenance'
    _description = 'Transit Maintenance'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'start_date desc, id desc'
    _rec_name = 'reference'

    # ------------------------------------------------------------------
    # Identification
    # ------------------------------------------------------------------
    reference = fields.Char(
        string='Reference',
        readonly=True,
        copy=False,
        default=lambda self: _('New'),
        help='Auto-generated maintenance reference number.',
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
    issue = fields.Text(
        string='Issue / Description',
        required=True,
        tracking=True,
        help='Detailed description of the maintenance issue or scheduled service.',
    )
    workshop = fields.Char(
        string='Workshop / Service Center',
        tracking=True,
        help='Name of the garage or service center handling this maintenance.',
    )
    cost = fields.Float(
        string='Maintenance Cost',
        digits=(10, 2),
        tracking=True,
        help='Total cost of this maintenance job.',
    )
    start_date = fields.Date(
        string='Start Date',
        required=True,
        tracking=True,
        default=fields.Date.today,
    )
    end_date = fields.Date(
        string='End Date',
        tracking=True,
        help='Date the vehicle was returned from maintenance.',
    )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    status = fields.Selection(
        selection=[
            ('active', 'Active'),
            ('closed', 'Closed'),
        ],
        string='Status',
        default='active',
        required=True,
        tracking=True,
        index=True,
    )

    # ------------------------------------------------------------------
    # Linked Expense (auto-created)
    # ------------------------------------------------------------------
    expense_id = fields.Many2one(
        comodel_name='transit.expense',
        string='Related Expense',
        readonly=True,
        copy=False,
        help='Expense record automatically created when this maintenance is saved.',
    )

    # ------------------------------------------------------------------
    # SQL Constraints
    # ------------------------------------------------------------------
    _sql_constraints = [
        (
            'non_negative_cost',
            'CHECK(cost >= 0)',
            'Maintenance cost cannot be negative.',
        ),
    ]

    # ------------------------------------------------------------------
    # Python Constraints
    # ------------------------------------------------------------------
    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for record in self:
            if record.end_date and record.start_date and record.end_date < record.start_date:
                raise ValidationError(
                    _('End date cannot be earlier than start date for maintenance record %s.')
                    % record.reference
                )

    # ------------------------------------------------------------------
    # ORM Overrides
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        """
        On creation:
        1. Assign sequence reference.
        2. Set vehicle status → 'in_shop'.
        3. Auto-create expense.
        """
        for vals in vals_list:
            if vals.get('reference', _('New')) == _('New'):
                vals['reference'] = self.env['ir.sequence'].next_by_code(
                    'transit.maintenance.sequence'
                ) or _('New')

        records = super().create(vals_list)

        for record in records:
            # Vehicle → In Shop
            if record.vehicle_id.status not in ('in_shop', 'retired'):
                record.vehicle_id._set_status(
                    'in_shop',
                    reason=f'Maintenance {record.reference} created.',
                )
            elif record.vehicle_id.status == 'in_shop':
                _logger.info(
                    'Vehicle [%s] already in shop; multiple maintenance records active.',
                    record.vehicle_id.registration_number,
                )

            # Auto-create expense
            record._create_expense()

        return records

    def write(self, vals):
        """When cost changes on an active record, update linked expense."""
        result = super().write(vals)
        if 'cost' in vals:
            for record in self:
                if record.expense_id:
                    record.expense_id.amount = record.cost
        return result

    # ------------------------------------------------------------------
    # Expense Auto-Creation
    # ------------------------------------------------------------------
    def _create_expense(self):
        """
        Automatically create a transit.expense record tied to this
        maintenance job. Called on record creation.
        """
        self.ensure_one()
        if self.expense_id:
            return  # Already has a linked expense
        expense = self.env['transit.expense'].create({
            'vehicle_id': self.vehicle_id.id,
            'expense_type': 'maintenance',
            'amount': self.cost,
            'date': self.start_date or fields.Date.today(),
            'description': f'Auto-generated: Maintenance {self.reference} — {self.issue[:100]}',
        })
        self.expense_id = expense.id
        _logger.info('Auto-created expense [%d] for maintenance [%s]', expense.id, self.reference)

    # ------------------------------------------------------------------
    # Workflow Action
    # ------------------------------------------------------------------
    def action_close_maintenance(self):
        """
        CLOSE: active → closed
        ----------------------
        * Sets end_date if not already set.
        * Restores vehicle to Available (unless retired).
        * Posts chatter message.
        """
        for record in self:
            if record.status == 'closed':
                raise ValidationError(
                    _('Maintenance record %s is already closed.') % record.reference
                )

            if not record.end_date:
                record.end_date = fields.Date.today()

            record.status = 'closed'

            # Restore vehicle unless retired or still in another active maintenance
            other_active = self.search([
                ('vehicle_id', '=', record.vehicle_id.id),
                ('status', '=', 'active'),
                ('id', '!=', record.id),
            ])
            if not other_active and record.vehicle_id.status != 'retired':
                record.vehicle_id._set_status(
                    'available',
                    reason=f'Maintenance {record.reference} closed.',
                )
            elif record.vehicle_id.status == 'retired':
                _logger.info(
                    'Vehicle [%s] is Retired; not restoring to Available after maintenance close.',
                    record.vehicle_id.registration_number,
                )

            record.message_post(
                body=_(
                    '<b>Maintenance Closed ✅</b><br/>'
                    'Workshop: %(ws)s<br/>'
                    'Cost: %(cost)s<br/>'
                    'End Date: %(end)s',
                    ws=record.workshop or _('N/A'),
                    cost=record.cost,
                    end=record.end_date,
                )
            )
