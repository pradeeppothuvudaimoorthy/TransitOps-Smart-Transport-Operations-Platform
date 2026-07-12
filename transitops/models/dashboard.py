# -*- coding: utf-8 -*-
"""
TransitOps - Dashboard Model
=============================
Transient/wizard-style model that aggregates KPIs for the
backend dashboard action. All methods are @api.model returning
plain dicts for JSON serialization in the JS widget.

Also contains the license-alert scheduled action logic.
"""

from odoo import api, fields, models, _
from datetime import date, timedelta
import logging

_logger = logging.getLogger(__name__)


class TransitDashboard(models.Model):
    """
    Virtual model used exclusively by the backend dashboard controller.

    Not persisted to the database (_auto = False removed since we need
    the model class for ACL; instead we use it as a container for
    @api.model methods).
    """
    _name = 'transit.dashboard'
    _description = 'TransitOps Dashboard'

    name = fields.Char(default='Dashboard')

    # ------------------------------------------------------------------
    # KPI Data Methods
    # ------------------------------------------------------------------
    @api.model
    def get_fleet_kpis(self):
        """
        Return a comprehensive dict of fleet KPIs for the dashboard widget.

        Returns
        -------
        dict with keys:
            active_vehicles, available_vehicles, vehicles_in_maintenance,
            retired_vehicles, drivers_available, trips_today, active_trips,
            pending_trips, fleet_utilization, total_fuel_cost,
            total_maintenance_cost, total_revenue, total_operational_cost,
            fleet_health_score
        """
        Vehicle = self.env['transit.vehicle']
        Driver = self.env['transit.driver']
        Trip = self.env['transit.trip']
        Expense = self.env['transit.expense']

        # --- Vehicle Stats ---
        all_vehicles = Vehicle.search([])
        active_vehicles = all_vehicles.filtered(
            lambda v: v.status != 'retired'
        )
        available_vehicles = all_vehicles.filtered(lambda v: v.status == 'available')
        on_trip_vehicles = all_vehicles.filtered(lambda v: v.status == 'on_trip')
        in_shop_vehicles = all_vehicles.filtered(lambda v: v.status == 'in_shop')
        retired_vehicles = all_vehicles.filtered(lambda v: v.status == 'retired')

        # --- Driver Stats ---
        all_drivers = Driver.search([])
        available_drivers = all_drivers.filtered(
            lambda d: d.status == 'available' and d.license_valid
        )

        # --- Trip Stats ---
        today = date.today()
        trips_today = Trip.search([
            ('dispatch_date', '>=', fields.Datetime.to_string(
                fields.Datetime.start_of(fields.Datetime.now(), 'day')
            )),
            ('dispatch_date', '<', fields.Datetime.to_string(
                fields.Datetime.end_of(fields.Datetime.now(), 'day')
            )),
        ])
        active_trips = Trip.search([('status', '=', 'dispatched')])
        pending_trips = Trip.search([('status', '=', 'draft')])

        # --- Fleet Utilization ---
        total_active = len(active_vehicles)
        fleet_utilization = (
            (len(on_trip_vehicles) / total_active * 100) if total_active else 0.0
        )

        # --- Financial Stats ---
        all_expenses = Expense.search([])
        fuel_expenses = all_expenses.filtered(lambda e: e.expense_type == 'fuel')
        maintenance_expenses = all_expenses.filtered(
            lambda e: e.expense_type == 'maintenance'
        )
        total_fuel_cost = sum(fuel_expenses.mapped('amount'))
        total_maintenance_cost = sum(maintenance_expenses.mapped('amount'))
        total_operational_cost = sum(all_expenses.mapped('amount'))

        completed_trips = Trip.search([('status', '=', 'completed')])
        total_revenue = sum(completed_trips.mapped('revenue'))

        # --- Fleet Health Score ---
        # Formula: weighted average of available %, license validity %
        license_valid_count = sum(1 for d in all_drivers if d.license_valid)
        license_score = (
            (license_valid_count / len(all_drivers) * 100) if all_drivers else 100.0
        )
        availability_score = (
            (len(available_vehicles) / total_active * 100) if total_active else 100.0
        )
        fleet_health_score = round(
            (availability_score * 0.6 + license_score * 0.4), 1
        )

        return {
            # Vehicles
            'active_vehicles': len(active_vehicles),
            'available_vehicles': len(available_vehicles),
            'on_trip_vehicles': len(on_trip_vehicles),
            'vehicles_in_maintenance': len(in_shop_vehicles),
            'retired_vehicles': len(retired_vehicles),
            # Drivers
            'total_drivers': len(all_drivers),
            'drivers_available': len(available_drivers),
            # Trips
            'trips_today': len(trips_today),
            'active_trips': len(active_trips),
            'pending_trips': len(pending_trips),
            'total_completed_trips': len(completed_trips),
            # Utilization
            'fleet_utilization': round(fleet_utilization, 1),
            # Financials
            'total_fuel_cost': total_fuel_cost,
            'total_maintenance_cost': total_maintenance_cost,
            'total_operational_cost': total_operational_cost,
            'total_revenue': total_revenue,
            'net_profit': total_revenue - total_operational_cost,
            # Health
            'fleet_health_score': fleet_health_score,
        }

    # ------------------------------------------------------------------
    # Report Calculation Methods
    # ------------------------------------------------------------------
    @api.model
    def get_report_data(self, date_from=None, date_to=None):
        """
        Return aggregated analytics for the report views.

        Returns
        -------
        dict with:
            fleet_utilization, avg_fuel_efficiency, vehicle_roi_list,
            total_operational_cost, driver_performance_list,
            avg_trip_distance, monthly_trips, monthly_fuel_cost
        """
        Trip = self.env['transit.trip']
        FuelLog = self.env['transit.fuel.log']
        Vehicle = self.env['transit.vehicle']
        Driver = self.env['transit.driver']

        domain = [('status', '=', 'completed')]
        if date_from:
            domain.append(('completion_date', '>=', date_from))
        if date_to:
            domain.append(('completion_date', '<=', date_to))

        completed_trips = Trip.search(domain)

        # Average trip distance
        distances = completed_trips.mapped('actual_distance')
        avg_trip_distance = sum(distances) / len(distances) if distances else 0.0

        # Fuel efficiency (all fuel logs)
        fuel_domain = []
        if date_from:
            fuel_domain.append(('date', '>=', date_from))
        if date_to:
            fuel_domain.append(('date', '<=', date_to))
        fuel_logs = FuelLog.search(fuel_domain)
        total_fuel_liters = sum(fuel_logs.mapped('fuel_liters'))
        total_fuel_distance = sum(fuel_logs.mapped('distance'))
        avg_fuel_efficiency = (
            total_fuel_distance / total_fuel_liters if total_fuel_liters else 0.0
        )

        # Vehicle ROI list
        vehicle_roi_list = []
        for v in Vehicle.search([]):
            vehicle_roi_list.append({
                'vehicle': v.name,
                'registration': v.registration_number,
                'revenue': v.total_revenue,
                'fuel_cost': v.total_fuel_cost,
                'maintenance_cost': v.total_maintenance_cost,
                'total_operational_cost': v.total_operational_cost,
                'acquisition_cost': v.acquisition_cost,
                'roi': round(v.roi * 100, 2),
            })

        # Driver performance list
        driver_perf = []
        for d in Driver.search([]):
            trips = d.trip_ids.filtered(lambda t: t.status == 'completed')
            driver_perf.append({
                'driver': d.name,
                'license': d.license_number,
                'trips_completed': d.total_trips_completed,
                'total_distance': d.total_distance_driven,
                'safety_score': d.safety_score,
                'avg_distance': (
                    d.total_distance_driven / d.total_trips_completed
                    if d.total_trips_completed else 0.0
                ),
            })

        return {
            'avg_trip_distance': round(avg_trip_distance, 2),
            'avg_fuel_efficiency': round(avg_fuel_efficiency, 2),
            'vehicle_roi_list': vehicle_roi_list,
            'driver_performance_list': driver_perf,
        }

    # ------------------------------------------------------------------
    # Scheduled Action: License Expiry Alert (Step 18)
    # ------------------------------------------------------------------
    @api.model
    def action_check_license_expiry(self):
        """
        Scheduled action that runs daily.

        For every driver whose license expires within 30 days:
        1. Creates a mail.activity on the driver record.
        2. Sends an optional email reminder if the driver has a linked user.

        Called by: data/scheduled_actions.xml (cron job).
        """
        Driver = self.env['transit.driver']
        today = date.today()
        alert_threshold = today + timedelta(days=30)

        expiring_drivers = Driver.search([
            ('license_expiry_date', '>=', fields.Date.to_string(today)),
            ('license_expiry_date', '<=', fields.Date.to_string(alert_threshold)),
            ('status', '!=', 'suspended'),
        ])

        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)

        for driver in expiring_drivers:
            days_left = (driver.license_expiry_date - today).days

            # Avoid duplicate activities
            existing = self.env['mail.activity'].search([
                ('res_model', '=', 'transit.driver'),
                ('res_id', '=', driver.id),
                ('activity_type_id', '=', activity_type.id if activity_type else False),
                ('summary', 'ilike', 'License Expiry'),
            ])
            if existing:
                continue

            note = _(
                'Driver <b>%(name)s</b> license (%(number)s) expires in '
                '<b>%(days)s day(s)</b> on %(date)s. '
                'Please arrange renewal immediately.',
                name=driver.name,
                number=driver.license_number,
                days=days_left,
                date=driver.license_expiry_date,
            )

            if activity_type:
                driver.activity_schedule(
                    activity_type_id=activity_type.id,
                    summary=_('License Expiry Alert — %s days left') % days_left,
                    note=note,
                    user_id=self.env.user.id,
                )

            # Post to chatter for audit trail
            driver.message_post(
                body=note,
                message_type='comment',
                subtype_xmlid='mail.mt_note',
            )

            _logger.warning(
                'LICENSE EXPIRY ALERT: Driver [%s] license expires in %d day(s) on %s.',
                driver.name, days_left, driver.license_expiry_date,
            )

        # Also flag already-expired drivers
        expired_drivers = Driver.search([
            ('license_expiry_date', '<', fields.Date.to_string(today)),
            ('license_valid', '=', True),  # Hasn't been updated yet
        ])
        for driver in expired_drivers:
            # Force recompute
            driver._compute_license_valid()
            _logger.warning(
                'EXPIRED LICENSE: Driver [%s] license expired on %s.',
                driver.name, driver.license_expiry_date,
            )

        _logger.info(
            'License expiry check complete. Expiring: %d, Already expired: %d.',
            len(expiring_drivers), len(expired_drivers),
        )
