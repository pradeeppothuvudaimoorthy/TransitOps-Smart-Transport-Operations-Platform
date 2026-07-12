# -*- coding: utf-8 -*-
"""
TransitOps - Trip Model
========================
The central workflow model. Manages the complete lifecycle of a transport
trip from draft creation through dispatch to completion or cancellation.

Workflow
--------
  Draft → Dispatched → Completed
                     → Cancelled
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from datetime import date
import logging

_logger = logging.getLogger(__name__)


class TransitTrip(models.Model):
    """
    Represents a single transport trip.

    Business Rules (enforced in Python)
    ------------------------------------
    * Vehicle must be 'available' before dispatch.
    * Driver must be 'available' and have a valid license before dispatch.
    * Cargo weight must not exceed vehicle max_load_capacity.
    * A vehicle / driver cannot be assigned to two active trips simultaneously.
    * Final odometer must be ≥ start odometer on completion.
    * Cancellation restores vehicle/driver status only if not already completed.
    """
    _name = 'transit.trip'
    _description = 'Transit Trip'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'dispatch_date desc, id desc'
    _rec_name = 'trip_number'

    # ------------------------------------------------------------------
    # Identification
    # ------------------------------------------------------------------
    trip_number = fields.Char(
        string='Trip Number',
        readonly=True,
        copy=False,
        default=lambda self: _('New'),
        help='Auto-generated unique trip reference.',
    )

    # ------------------------------------------------------------------
    # Core Fields
    # ------------------------------------------------------------------
    vehicle_id = fields.Many2one(
        comodel_name='transit.vehicle',
        string='Vehicle',
        required=True,
        tracking=True,
        domain="[('status', '=', 'available')]",
        help='Only Available vehicles are selectable.',
    )
    driver_id = fields.Many2one(
        comodel_name='transit.driver',
        string='Driver',
        required=True,
        tracking=True,
        domain="[('status', '=', 'available'), ('license_valid', '=', True)]",
        help='Only Available drivers with a valid license are selectable.',
    )
    source = fields.Char(
        string='Source / Origin',
        required=True,
        tracking=True,
    )
    destination = fields.Char(
        string='Destination',
        required=True,
        tracking=True,
    )
    cargo_weight = fields.Float(
        string='Cargo Weight (kg)',
        required=True,
        digits=(10, 2),
        tracking=True,
        help='Weight of cargo to be transported. Must not exceed vehicle capacity.',
    )
    planned_distance = fields.Float(
        string='Planned Distance (km)',
        digits=(10, 2),
        tracking=True,
    )
    actual_distance = fields.Float(
        string='Actual Distance (km)',
        compute='_compute_actual_distance',
        store=True,
        digits=(10, 2),
        help='Computed as Final Odometer − Start Odometer.',
    )
    start_odometer = fields.Float(
        string='Start Odometer (km)',
        digits=(10, 2),
        tracking=True,
        help='Vehicle odometer reading at trip start (auto-filled from vehicle on dispatch).',
    )
    final_odometer = fields.Float(
        string='Final Odometer (km)',
        digits=(10, 2),
        tracking=True,
        help='Vehicle odometer reading at trip end. Required to complete the trip.',
    )
    fuel_used = fields.Float(
        string='Fuel Used (L)',
        digits=(10, 2),
        tracking=True,
        help='Total fuel consumed during this trip. Required to complete the trip.',
    )
    revenue = fields.Float(
        string='Revenue',
        digits=(10, 2),
        tracking=True,
        help='Income generated from this trip.',
    )

    # ------------------------------------------------------------------
    # Dates
    # ------------------------------------------------------------------
    dispatch_date = fields.Datetime(
        string='Dispatch Date & Time',
        tracking=True,
        help='Timestamp when the trip was officially dispatched.',
    )
    completion_date = fields.Datetime(
        string='Completion Date & Time',
        tracking=True,
        help='Timestamp when the trip was completed.',
    )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    status = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('dispatched', 'Dispatched'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        index=True,
        copy=False,
    )

    # ------------------------------------------------------------------
    # Relations
    # ------------------------------------------------------------------
    fuel_log_ids = fields.One2many(
        comodel_name='transit.fuel.log',
        inverse_name='trip_id',
        string='Fuel Logs',
    )
    expense_ids = fields.One2many(
        comodel_name='transit.expense',
        inverse_name='trip_id',
        string='Expenses',
    )

    # Convenience fields for UI display
    vehicle_capacity = fields.Float(
        related='vehicle_id.max_load_capacity',
        string='Vehicle Capacity (kg)',
        readonly=True,
        store=False,
    )
    driver_license_valid = fields.Boolean(
        related='driver_id.license_valid',
        string='License Valid',
        readonly=True,
        store=False,
    )

    # ------------------------------------------------------------------
    # SQL Constraints
    # ------------------------------------------------------------------
    _sql_constraints = [
        (
            'positive_cargo_weight',
            'CHECK(cargo_weight > 0)',
            'Cargo weight must be a positive value.',
        ),
        (
            'positive_revenue',
            'CHECK(revenue >= 0)',
            'Revenue cannot be negative.',
        ),
    ]

    # ------------------------------------------------------------------
    # Compute Methods
    # ------------------------------------------------------------------
    @api.depends('final_odometer', 'start_odometer')
    def _compute_actual_distance(self):
        for trip in self:
            if trip.final_odometer and trip.start_odometer:
                trip.actual_distance = max(0.0, trip.final_odometer - trip.start_odometer)
            else:
                trip.actual_distance = 0.0

    # ------------------------------------------------------------------
    # ORM Overrides
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        """Auto-generate trip numbers using the ir.sequence."""
        for vals in vals_list:
            if vals.get('trip_number', _('New')) == _('New'):
                vals['trip_number'] = self.env['ir.sequence'].next_by_code(
                    'transit.trip.sequence'
                ) or _('New')
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Business Validations (shared between dispatch and constraint)
    # ------------------------------------------------------------------
    def _validate_for_dispatch(self):
        """
        Central validation method called before dispatch.
        Raises ValidationError with user-friendly messages on any failure.
        """
        self.ensure_one()

        # 1. Vehicle must be selected and available
        if not self.vehicle_id:
            raise ValidationError(_('No vehicle selected for trip %s.') % self.trip_number)
        if self.vehicle_id.status != 'available':
            raise ValidationError(
                _('Vehicle "%(vehicle)s" is currently %(status)s and cannot be dispatched. '
                  'Only Available vehicles can be assigned to trips.',
                  vehicle=self.vehicle_id.name,
                  status=dict(self.vehicle_id._fields['status'].selection).get(
                      self.vehicle_id.status, self.vehicle_id.status
                  ))
            )

        # 2. Driver must be selected, available, and have a valid license
        if not self.driver_id:
            raise ValidationError(_('No driver selected for trip %s.') % self.trip_number)
        if self.driver_id.status != 'available':
            raise ValidationError(
                _('Driver "%(driver)s" is currently %(status)s and cannot be dispatched.',
                  driver=self.driver_id.name,
                  status=dict(self.driver_id._fields['status'].selection).get(
                      self.driver_id.status, self.driver_id.status
                  ))
            )
        if not self.driver_id.license_valid:
            raise ValidationError(
                _('Driver "%(driver)s" has an expired or invalid license (expired: %(date)s). '
                  'Renew the license before dispatching.',
                  driver=self.driver_id.name,
                  date=self.driver_id.license_expiry_date)
            )

        # 3. Cargo weight must not exceed vehicle capacity
        if self.cargo_weight > self.vehicle_id.max_load_capacity:
            raise ValidationError(
                _('Cargo weight %(cargo)s kg exceeds vehicle "%(vehicle)s" max capacity of %(cap)s kg.',
                  cargo=self.cargo_weight,
                  vehicle=self.vehicle_id.name,
                  cap=self.vehicle_id.max_load_capacity)
            )

        # 4. Vehicle not already on another active trip
        active_vehicle_trips = self.search([
            ('vehicle_id', '=', self.vehicle_id.id),
            ('status', '=', 'dispatched'),
            ('id', '!=', self.id),
        ])
        if active_vehicle_trips:
            raise ValidationError(
                _('Vehicle "%(vehicle)s" is already assigned to active trip %(trip)s.',
                  vehicle=self.vehicle_id.name,
                  trip=active_vehicle_trips[0].trip_number)
            )

        # 5. Driver not already on another active trip
        active_driver_trips = self.search([
            ('driver_id', '=', self.driver_id.id),
            ('status', '=', 'dispatched'),
            ('id', '!=', self.id),
        ])
        if active_driver_trips:
            raise ValidationError(
                _('Driver "%(driver)s" is already assigned to active trip %(trip)s.',
                  driver=self.driver_id.name,
                  trip=active_driver_trips[0].trip_number)
            )

    # ------------------------------------------------------------------
    # Python Constraints (model-level, runs on save)
    # ------------------------------------------------------------------
    @api.constrains('cargo_weight', 'vehicle_id')
    def _check_cargo_weight(self):
        """Prevent saving a trip where cargo exceeds vehicle capacity."""
        for trip in self:
            if trip.vehicle_id and trip.cargo_weight > trip.vehicle_id.max_load_capacity:
                raise ValidationError(
                    _('Cargo weight %(cargo)s kg exceeds vehicle capacity of %(cap)s kg '
                      'for vehicle "%(vehicle)s".',
                      cargo=trip.cargo_weight,
                      cap=trip.vehicle_id.max_load_capacity,
                      vehicle=trip.vehicle_id.name)
                )

    # ------------------------------------------------------------------
    # Workflow Button Actions
    # ------------------------------------------------------------------
    def action_dispatch(self):
        """
        DISPATCH: Draft → Dispatched
        ----------------------------
        1. Run all validations.
        2. Capture start odometer from vehicle.
        3. Set vehicle status → On Trip.
        4. Set driver status → On Trip.
        5. Record dispatch timestamp.
        6. Post chatter message.
        """
        for trip in self:
            if trip.status != 'draft':
                raise ValidationError(
                    _('Only Draft trips can be dispatched. Trip %s is already %s.')
                    % (trip.trip_number, trip.status)
                )

            trip._validate_for_dispatch()

            # Capture odometer at dispatch time
            trip.start_odometer = trip.vehicle_id.current_odometer
            trip.dispatch_date = fields.Datetime.now()

            # Update related records
            trip.vehicle_id._set_status('on_trip', reason=f'Dispatched on trip {trip.trip_number}')
            trip.driver_id._set_status('on_trip', reason=f'Assigned to trip {trip.trip_number}')

            # Transition trip state
            trip.status = 'dispatched'

            # Chatter
            trip.message_post(
                body=_(
                    '<b>Trip Dispatched ✅</b><br/>'
                    'Vehicle: <b>%(vehicle)s</b><br/>'
                    'Driver: <b>%(driver)s</b><br/>'
                    'Route: %(src)s → %(dst)s<br/>'
                    'Start Odometer: %(odo)s km',
                    vehicle=trip.vehicle_id.name,
                    driver=trip.driver_id.name,
                    src=trip.source,
                    dst=trip.destination,
                    odo=trip.start_odometer,
                )
            )
            _logger.info('Trip [%s] dispatched. Vehicle: %s, Driver: %s',
                         trip.trip_number, trip.vehicle_id.registration_number,
                         trip.driver_id.name)

    def action_complete(self):
        """
        COMPLETE: Dispatched → Completed
        ---------------------------------
        1. Require final_odometer, fuel_used, completion_date.
        2. Compute actual_distance.
        3. Update vehicle odometer.
        4. Restore vehicle/driver to Available.
        5. Auto-create fuel log entry.
        """
        for trip in self:
            if trip.status != 'dispatched':
                raise ValidationError(
                    _('Only Dispatched trips can be completed. Trip %s is %s.')
                    % (trip.trip_number, trip.status)
                )

            # Required fields for completion
            if not trip.final_odometer:
                raise ValidationError(
                    _('Final Odometer is required to complete trip %s.') % trip.trip_number
                )
            if trip.final_odometer < trip.start_odometer:
                raise ValidationError(
                    _('Final Odometer (%s km) cannot be less than Start Odometer (%s km) '
                      'for trip %s.')
                    % (trip.final_odometer, trip.start_odometer, trip.trip_number)
                )
            if not trip.fuel_used or trip.fuel_used <= 0:
                raise ValidationError(
                    _('Fuel Used (liters) is required to complete trip %s.') % trip.trip_number
                )

            trip.completion_date = fields.Datetime.now()

            # Update vehicle odometer
            trip.vehicle_id.current_odometer = trip.final_odometer

            # Restore statuses
            trip.vehicle_id._set_status('available', reason=f'Trip {trip.trip_number} completed.')
            trip.driver_id._set_status('available', reason=f'Trip {trip.trip_number} completed.')

            # Transition trip state
            trip.status = 'completed'

            # Auto-create Fuel Log (Step 12 + 14 integration)
            self.env['transit.fuel.log'].create({
                'vehicle_id': trip.vehicle_id.id,
                'trip_id': trip.id,
                'date': fields.Date.today(),
                'fuel_liters': trip.fuel_used,
                'fuel_cost': 0.0,   # Financial analyst fills cost
                'distance': trip.actual_distance,
            })

            # Chatter
            trip.message_post(
                body=_(
                    '<b>Trip Completed ✅</b><br/>'
                    'Final Odometer: <b>%(odo)s km</b><br/>'
                    'Actual Distance: <b>%(dist)s km</b><br/>'
                    'Fuel Used: <b>%(fuel)s L</b><br/>'
                    'Revenue: <b>%(rev)s</b>',
                    odo=trip.final_odometer,
                    dist=trip.actual_distance,
                    fuel=trip.fuel_used,
                    rev=trip.revenue,
                )
            )

    def action_cancel(self):
        """
        CANCEL: Draft/Dispatched → Cancelled
        -------------------------------------
        Restores vehicle/driver status to Available
        only if trip was Dispatched (not already Completed).
        """
        for trip in self:
            if trip.status == 'completed':
                raise ValidationError(
                    _('Completed trip %s cannot be cancelled.') % trip.trip_number
                )
            if trip.status == 'cancelled':
                raise ValidationError(
                    _('Trip %s is already cancelled.') % trip.trip_number
                )

            was_dispatched = trip.status == 'dispatched'
            trip.status = 'cancelled'

            if was_dispatched:
                # Restore vehicle and driver only if they are still "on_trip"
                if trip.vehicle_id.status == 'on_trip':
                    trip.vehicle_id._set_status(
                        'available', reason=f'Trip {trip.trip_number} cancelled.'
                    )
                if trip.driver_id.status == 'on_trip':
                    trip.driver_id._set_status(
                        'available', reason=f'Trip {trip.trip_number} cancelled.'
                    )

            trip.message_post(
                body=_('<b>Trip Cancelled ❌</b><br/>Cancellation recorded by %(user)s.',
                       user=self.env.user.name)
            )

    # ------------------------------------------------------------------
    # Onchange
    # ------------------------------------------------------------------
    @api.onchange('vehicle_id')
    def _onchange_vehicle_id(self):
        """Pre-fill start odometer from vehicle when vehicle is selected."""
        if self.vehicle_id:
            self.start_odometer = self.vehicle_id.current_odometer

    @api.onchange('vehicle_id', 'cargo_weight')
    def _onchange_check_capacity(self):
        """Warn user if cargo weight already exceeds capacity before saving."""
        if self.vehicle_id and self.cargo_weight:
            if self.cargo_weight > self.vehicle_id.max_load_capacity:
                return {
                    'warning': {
                        'title': _('Capacity Exceeded'),
                        'message': _(
                            'Cargo weight (%(cargo)s kg) exceeds the vehicle '
                            'max load capacity (%(cap)s kg). This trip cannot be dispatched.',
                            cargo=self.cargo_weight,
                            cap=self.vehicle_id.max_load_capacity,
                        ),
                    }
                }
