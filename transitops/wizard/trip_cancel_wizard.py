# -*- coding: utf-8 -*-
"""
TransitOps - Trip Cancellation Wizard
======================================
Provides a confirmation dialog with cancellation reason when a Fleet Manager
wants to cancel a trip. Records the reason in the chatter.
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class TripCancelWizard(models.TransientModel):
    """
    Transient wizard model for trip cancellation.
    Allows Fleet Managers to provide a reason before cancelling.
    """
    _name = 'transit.trip.cancel.wizard'
    _description = 'Trip Cancellation Wizard'

    trip_id = fields.Many2one(
        comodel_name='transit.trip',
        string='Trip',
        required=True,
        readonly=True,
        default=lambda self: self._context.get('active_id'),
    )
    trip_number = fields.Char(
        related='trip_id.trip_number',
        string='Trip Number',
        readonly=True,
    )
    current_status = fields.Selection(
        related='trip_id.status',
        string='Current Status',
        readonly=True,
    )
    cancellation_reason = fields.Text(
        string='Cancellation Reason',
        required=True,
        help='Provide a clear reason for cancelling this trip.',
    )

    # ------------------------------------------------------------------
    # Confirm Action
    # ------------------------------------------------------------------
    def action_confirm_cancel(self):
        """
        Execute trip cancellation with the supplied reason.
        Posts the reason to the chatter of the trip, vehicle and driver.
        """
        self.ensure_one()
        trip = self.trip_id

        if trip.status == 'completed':
            raise ValidationError(
                _('Completed trip "%s" cannot be cancelled.') % trip.trip_number
            )
        if trip.status == 'cancelled':
            raise ValidationError(
                _('Trip "%s" is already cancelled.') % trip.trip_number
            )

        was_dispatched = trip.status == 'dispatched'
        trip.status = 'cancelled'

        if was_dispatched:
            if trip.vehicle_id.status == 'on_trip':
                trip.vehicle_id._set_status(
                    'available',
                    reason=f'Trip {trip.trip_number} cancelled: {self.cancellation_reason[:80]}',
                )
            if trip.driver_id.status == 'on_trip':
                trip.driver_id._set_status(
                    'available',
                    reason=f'Trip {trip.trip_number} cancelled: {self.cancellation_reason[:80]}',
                )

        trip.message_post(
            body=_(
                '<b>Trip Cancelled ❌</b><br/>'
                'Cancelled by: <b>%(user)s</b><br/>'
                'Reason: %(reason)s',
                user=self.env.user.name,
                reason=self.cancellation_reason,
            )
        )

        return {'type': 'ir.actions.act_window_close'}
