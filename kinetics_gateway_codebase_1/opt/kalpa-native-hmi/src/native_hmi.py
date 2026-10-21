#!/usr/bin/env python3
"""Kalpa Local HMI: native GTK3/Wayland frontend for the *existing* gateway REST APIs.

Read-only by construction. The only HTTP POST used is /api/auth/login.
Credentials and bearer token stay in RAM; no browser, disk cache, telemetry replay,
or fieldbus access. Python GUI uses the Yocto *system* interpreter with PyGObject.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys
from threading import Thread

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gdk, GLib, Gtk, Pango

from api_client import APIError, GatewayClient
import viewmodels as vm

CSS = r'''
window { background-color: #0c141d; color: #ecf4ff; font-family: "DejaVu Sans", sans-serif; }
label { color: #e9f2ff; }
.sidebar { background-color: #101c2a; border-right: 1px solid #304158; }
.brand { font-weight: 900; font-size: 20px; color: #ff826c; }
.section { color: #91bdd5; font-size: 11px; font-weight: bold; }
.heading { font-weight: 800; font-size: 23px; color: #ffffff; }
.title-card { color: #ffffff; font-size: 14px; font-weight: 800; }
.note { color: #a8bfce; font-size: 11px; }
.value { color: #ffffff; font-weight: 900; font-size: 22px; }
.value-sm { color: #ffffff; font-weight: 700; font-size: 15px; }
.panel { background-color: #192738; border: 1px solid #304158; border-radius: 11px; }
.separator { background-color: #304158; }
button { border-radius: 8px; background-color: #203249; color: #eff6ff; border: 1px solid #31465f; padding: 10px 14px; }
button:hover { background-color: #334b65; }
button.active { background-color: #304967; color: #ffffff; font-weight: bold; }
button.accent { background-color: #ff8068; color: #08111c; font-weight: 800; border: none; }
button.accent:hover { background-color: #ff9a83; }
entry { background-color: #0c1723; border: 1px solid #405570; border-radius: 6px; color: white; padding: 10px; }
.pill { color: #76f0ce; font-size: 12px; font-weight: 900; }
.warn { color: #ff9d86; font-size: 12px; }
.smallcaps { color: #97d5fc; font-size: 11px; font-weight: 800; }
.socbar trough { background-color: #32455d; min-height: 7px; border: none; border-radius: 4px; }
.socbar progress { background-color: #61ccb3; min-height: 7px; border-radius: 4px; }
treeview { color: #e9f2ff; background-color: #192738; font-size: 11px; }
treeview:selected { background-color: #315777; color: white; }
treeview header button { font-size: 10px; padding: 6px; }
scrolledwindow { background-color: transparent; }
'''


def cls(widget, name):
    widget.get_style_context().add_class(name)
    return widget


def label(value='', style=None, wrap=False):
    widget = Gtk.Label(label=str(value))
    widget.set_xalign(0.0)
    if wrap:
        widget.set_line_wrap(True)
        widget.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    if style:
        cls(widget, style)
    return widget


def vbox(spacing=8):
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)


def hbox(spacing=8):
    return Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=spacing)


def pad(widget, amount=16):
    widget.set_margin_top(amount)
    widget.set_margin_bottom(amount)
    widget.set_margin_start(amount)
    widget.set_margin_end(amount)
    return widget


def panel(contents=None, margin=0):
    ev = Gtk.EventBox()
    cls(ev, 'panel')
    box = vbox(8)
    pad(box, 14)
    if contents is not None:
        box.pack_start(contents, True, True, 0)
    ev.add(box)
    if margin:
        ev.set_margin_bottom(margin)
    return ev, box


class NativeHMI:
    TABS = (
        ('overview', 'Overview'),
        ('battery', 'Battery / BMS'),
        ('pcs', 'PCS / Power'),
        ('alarms', 'Alarms & events'),
        ('gateway', 'Gateway health'),
    )

    def __init__(self, api_url: str, fullscreen=True):
        self.api = GatewayClient(api_url)
        self.fullscreen_mode = fullscreen
        self.tab = 'overview'
        self.payload = None
        self.request_running = False
        self.login_running = False
        self.auth_epoch = 0
        self.last_error = ''

        display = Gdk.Screen.get_default()
        if display is None:
            raise RuntimeError('No active GTK display: Weston/Wayland socket may be unavailable')
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS.encode('utf-8'))
        Gtk.StyleContext.add_provider_for_screen(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.win = Gtk.Window(title='ORNATE EMS — Kalpa Local HMI')
        self.win.set_default_size(1280, 720)
        self.win.set_size_request(800, 520)
        self.win.connect('destroy', Gtk.main_quit)
        self.win.connect('key-press-event', self.handle_key)
        self.root = Gtk.Stack()
        self.root.set_transition_type(Gtk.StackTransitionType.NONE)
        self.win.add(self.root)
        self._make_login()
        self._make_dashboard()
        self.root.set_visible_child_name('login')
        self.win.show_all()
        if self.fullscreen_mode:
            self.win.fullscreen()
        GLib.timeout_add_seconds(5, self._refresh_tick)
        GLib.timeout_add_seconds(15, self._clock_tick)

    def handle_key(self, widget, event):
        if event.keyval == Gdk.KEY_F11:
            if self.fullscreen_mode:
                self.win.unfullscreen()
            else:
                self.win.fullscreen()
            self.fullscreen_mode = not self.fullscreen_mode
            return True
        return False

    def _make_login(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.set_valign(Gtk.Align.CENTER)
        outer.set_halign(Gtk.Align.CENTER)
        outer.set_size_request(440, -1)
        frame, box = panel()
        box.set_spacing(16)
        box.pack_start(label('◆  ORNATE EMS', 'brand'), False, False, 3)
        box.pack_start(label('Kalpa local monitoring', 'heading'), False, False, 4)
        box.pack_start(label('Native HDMI interface · Read-only · Existing gateway account', 'note', True), False, False, 0)
        box.pack_start(label('Username', 'smallcaps'), False, False, 0)
        self.username = Gtk.Entry()
        self.username.set_text('customer')
        box.pack_start(self.username, False, False, 0)
        box.pack_start(label('Password', 'smallcaps'), False, False, 0)
        self.password = Gtk.Entry()
        self.password.set_visibility(False)
        self.password.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        self.password.connect('activate', self._submit_login)
        box.pack_start(self.password, False, False, 0)
        self.login_btn = Gtk.Button(label='Open dashboard')
        cls(self.login_btn, 'accent')
        self.login_btn.connect('clicked', self._submit_login)
        box.pack_start(self.login_btn, False, False, 0)
        self.login_message = label('No passwords are saved to disk.', 'note', True)
        box.pack_start(self.login_message, False, False, 0)
        outer.pack_start(frame, False, False, 0)
        self.root.add_named(outer, 'login')

    def _make_dashboard(self):
        shell = hbox(0)
        sidebar = vbox(13)
        cls(sidebar, 'sidebar')
        sidebar.set_size_request(190, -1)
        pad(sidebar, 14)
        sidebar.pack_start(label('◆ ORNATE EMS', 'brand'), False, False, 3)
        sidebar.pack_start(label('SITE MONITORING', 'section'), False, False, 15)
        self.nav_buttons = {}
        for key, name in self.TABS:
            btn = Gtk.Button(label=name)
            btn.connect('clicked', self._switch_tab, key)
            btn.set_hexpand(True)
            sidebar.pack_start(btn, False, False, 0)
            self.nav_buttons[key] = btn
        sidebar.pack_start(Gtk.Box(), True, True, 0)
        self.role_label = label('VIEW ONLY', 'note')
        sidebar.pack_start(self.role_label, False, False, 0)
        logout = Gtk.Button(label='Sign out')
        logout.connect('clicked', self._logout)
        sidebar.pack_start(logout, False, False, 0)
        shell.pack_start(sidebar, False, False, 0)

        right = vbox(8)
        pad(right, 16)
        top = hbox(18)
        tit = vbox(3)
        tit.pack_start(label('LOCAL ENERGY MANAGEMENT SYSTEM', 'section'), False, False, 0)
        self.page_title = label('Site overview', 'heading')
        tit.pack_start(self.page_title, False, False, 0)
        top.pack_start(tit, True, True, 0)
        mode = label('SIL / MOCK DATA', 'warn')
        top.pack_start(mode, False, False, 12)
        self.status = label('CONNECTING', 'pill')
        top.pack_start(self.status, False, False, 10)
        self.clock = label('', 'value-sm')
        top.pack_start(self.clock, False, False, 4)
        right.pack_start(top, False, False, 6)
        self.warning = label('', 'warn', True)
        right.pack_start(self.warning, False, False, 1)
        self.warning.set_no_show_all(True)
        self.warning.hide()
        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.content = vbox(13)
        self.content.set_margin_bottom(24)
        self.scroll.add(self.content)
        right.pack_start(self.scroll, True, True, 0)
        self.bottom_label = label('Waiting for first authenticated snapshot…', 'note')
        right.pack_start(self.bottom_label, False, False, 0)
        shell.pack_start(right, True, True, 0)
        self.root.add_named(shell, 'dashboard')
        self._clock_tick()
        self._set_active()

    def _clock_tick(self):
        self.clock.set_text(datetime.now().strftime('%I:%M %p'))
        return True

    def _set_active(self):
        for name, button in self.nav_buttons.items():
            ctx = button.get_style_context()
            if name == self.tab:
                ctx.add_class('active')
            else:
                ctx.remove_class('active')

    def _switch_tab(self, unused_button, tab):
        self.tab = tab
        self.scroll.get_vadjustment().set_value(0)
        self._set_active()
        self.page_title.set_text(dict(self.TABS)[tab].replace('Overview', 'Site overview'))
        self._draw()

    def _submit_login(self, *_):
        if self.login_running:
            return
        username, password = self.username.get_text().strip(), self.password.get_text()
        self.password.set_text('')
        if not username or not password:
            self.login_message.set_text('Enter both username and password.')
            return
        self.login_running = True
        self.login_btn.set_sensitive(False)
        self.login_message.set_text('Authenticating against 127.0.0.1…')
        self.auth_epoch += 1
        epoch = self.auth_epoch
        def work():
            try:
                role = self.api.login(username, password)
                GLib.idle_add(self._login_success, epoch, role)
            except Exception as exc:
                GLib.idle_add(self._login_failure, epoch, str(exc))
        Thread(target=work, name='kalpa-hmi-login', daemon=True).start()

    def _login_success(self, epoch, role):
        if epoch != self.auth_epoch:
            return False
        self.login_running = False
        self.login_btn.set_sensitive(True)
        self.login_message.set_text('')
        self.role_label.set_text('%s · VIEW ONLY' % role.upper())
        self.root.set_visible_child_name('dashboard')
        self._refresh_tick()
        return False

    def _login_failure(self, epoch, message):
        if epoch != self.auth_epoch:
            return False
        self.login_running = False
        self.login_btn.set_sensitive(True)
        self.login_message.set_text(message)
        return False

    def _logout(self, *_):
        self.auth_epoch += 1
        self.api.logout()
        self.payload = None
        self.request_running = False
        self.root.set_visible_child_name('login')
        self.login_message.set_text('Signed out. Credentials are not stored.')

    def _refresh_tick(self):
        if not self.api.token or self.request_running:
            return True
        epoch = self.auth_epoch
        self.request_running = True
        def work():
            try:
                results = self.api.poll()
                GLib.idle_add(self._refresh_ok, epoch, results)
            except APIError as err:
                GLib.idle_add(self._refresh_failed, epoch, str(err), err.status)
            except Exception as err:
                GLib.idle_add(self._refresh_failed, epoch, str(err), None)
        Thread(target=work, name='kalpa-hmi-poll', daemon=True).start()
        return True

    def _refresh_ok(self, epoch, payload):
        if epoch != self.auth_epoch:
            return False
        self.request_running = False
        self.payload = payload
        snapshot, health, alarms, ctrl = payload
        name, desc = vm.telemetry_freshness(snapshot, health)
        self.status.set_text(name)
        if desc:
            self.warning.set_text(desc + ' — values may be outdated')
            self.warning.show()
        else:
            self.warning.hide()
        self.bottom_label.set_text('Snapshot: %s   •   Refreshed: %s   •   Read-only' %
                                   (vm.txt(snapshot.get('timestamp')), datetime.now().strftime('%H:%M:%S')))
        self._draw()
        return False

    def _refresh_failed(self, epoch, error, status):
        if epoch != self.auth_epoch:
            return False
        self.request_running = False
        if status == 401:
            self._logout()
            self.login_message.set_text('Session expired. Sign in again.')
        else:
            self.status.set_text('CONNECTION LOST')
            self.warning.set_text('Gateway API unavailable: ' + error + ' — displayed data is stale')
            self.warning.show()
        return False

    def _add_title(self, name):
        w = label(name, 'title-card')
        w.set_margin_top(8)
        self.content.pack_start(w, False, False, 0)

    def _metric(self, box, key, value, large=False):
        piece = vbox(3)
        piece.pack_start(label(key, 'note'), False, False, 0)
        piece.pack_start(label(vm.txt(value, 150), 'value' if large else 'value-sm', True), False, False, 0)
        box.pack_start(piece, True, True, 0)

    def _stat_cards(self, data):
        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        grid.set_column_homogeneous(True)
        for i, (name, value) in enumerate(data):
            frame, content = panel()
            self._metric(content, name, value, True)
            grid.attach(frame, i, 0, 1, 1)
        self.content.pack_start(grid, False, False, 0)

    def _metric_panel(self, name, pairs, columns=3):
        ev, body = panel()
        body.pack_start(label(name, 'title-card'), False, False, 5)
        grid = Gtk.Grid(column_spacing=18, row_spacing=16)
        grid.set_column_homogeneous(True)
        for i, (k, value) in enumerate(pairs):
            col = vbox(3)
            col.pack_start(label(k, 'note'), False, False, 0)
            col.pack_start(label(vm.txt(value, 130), 'value-sm', True), False, False, 0)
            grid.attach(col, i % columns, i // columns, 1, 1)
        body.pack_start(grid, False, False, 0)
        self.content.pack_start(ev, False, False, 0)

    def _table(self, columns, rows, min_height=200):
        frame, body = panel()
        store = Gtk.ListStore(*([str] * len(columns)))
        for row in rows:
            store.append([vm.txt(v, 160) for v in row])
        tree = Gtk.TreeView(model=store)
        tree.set_headers_visible(True)
        tree.set_enable_search(False)
        tree.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
        for i, name in enumerate(columns):
            renderer = Gtk.CellRendererText()
            renderer.set_property('xpad', 7)
            renderer.set_property('ypad', 5)
            if name in ('Signal / alarm', 'Gateway ID'):
                renderer.set_property('ellipsize', Pango.EllipsizeMode.END)
            c = Gtk.TreeViewColumn(name, renderer, text=i)
            c.set_resizable(True)
            c.set_min_width(70)
            tree.append_column(c)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller.set_min_content_height(min_height)
        scroller.add(tree)
        body.pack_start(scroller, True, True, 0)
        self.content.pack_start(frame, True, True, 0)

    def _overview(self, model, health, alarms, ctrl):
        self._stat_cards(vm.overview_stats(model, health, alarms))
        self._add_title('Battery / PCS pairs')
        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        grid.set_column_homogeneous(True)
        enabled = [p for p in vm.pairs(model) if p.get('enabled') is not False]
        for i, p in enumerate(enabled):
            frame, content = panel()
            name = vm.txt(p.get('pair_id', 'Pair')).replace('_', ' ').upper()
            content.pack_start(label(name + '  ·  ' + vm.onoff(p.get('online')), 'title-card'), False, False, 2)
            soc = (p.get('battery') or {}).get('soc_percent')
            content.pack_start(label('SOC   ' + vm.fmt(soc, 1, '%'), 'value-sm'), False, False, 0)
            bar = Gtk.ProgressBar()
            cls(bar, 'socbar')
            try:
                bar.set_fraction(max(0.0, min(1.0, float(soc) / 100)))
            except (ValueError, TypeError):
                bar.set_fraction(0.0)
            content.pack_start(bar, False, False, 3)
            bat, pcs = p.get('battery') or {}, p.get('pcs') or {}
            for name2, value in (
                ('Actual power', vm.fmt(pcs.get('active_power_kw'), 1, ' kW')),
                ('Rack voltage', vm.fmt(bat.get('voltage_v'), 0, ' V')),
                ('SOH', vm.fmt(bat.get('soh_percent'), 1, '%')),
            ):
                content.pack_start(label('%s: %s' % (name2, value), 'note'), False, False, 0)
            grid.attach(frame, i % 4, i // 4, 1, 1)
        self.content.pack_start(grid, False, False, 0)
        battery = model.get('battery_system') or {}
        self._metric_panel('Battery system', [
            ('Voltage', vm.fmt(battery.get('voltage_v'), 1, ' V')),
            ('Current', vm.fmt(battery.get('current_a'), 1, ' A')),
            ('SOH', vm.fmt(battery.get('soh_percent'), 1, '%')),
            ('Charge limit', vm.fmt(battery.get('max_charge_power_kw'), 1, ' kW')),
            ('Discharge limit', vm.fmt(battery.get('max_discharge_power_kw'), 1, ' kW')),
            ('BMS state', vm.txt(battery.get('state'))),
        ])
        self._metric_panel('Connectivity', [
            ('Gateway', health.get('status') or '—'),
            ('Modbus assets', '%s / %s' % (health.get('assets_online', '—'), health.get('assets_total', '—'))),
            ('Field interface', (health.get('network') or {}).get('field_interface') or '—'),
            ('EMS mode', health.get('mode') or '—'),
            ('Local storage', (health.get('storage') or {}).get('storage_mode') or '—'),
            ('Internet', 'Not required for local HMI'),
        ])

    def _battery(self, model):
        self._add_title('Lineage BMS · Rack status')
        self._table(['Rack', 'Link', 'SOC', 'SOH', 'Voltage', 'Current', 'State', 'Charge limit', 'Discharge limit', 'Contactors'],
                    vm.battery_rows(model), 180)
        b = model.get('battery_system') or {}
        self._metric_panel('System battery readings', [
            ('System SOC', vm.fmt(b.get('soc_percent'), 1, '%')),
            ('System SOH', vm.fmt(b.get('soh_percent'), 1, '%')),
            ('Battery voltage', vm.fmt(b.get('voltage_v'), 1, ' V')),
            ('Battery current', vm.fmt(b.get('current_a'), 1, ' A')),
            ('Maximum cell voltage', vm.voltage_cell(b.get('max_cell_voltage_v'))),
            ('Minimum cell voltage', vm.voltage_cell(b.get('min_cell_voltage_v'))),
            ('Max cell temperature', vm.fmt(b.get('max_cell_temperature_c'), 1, ' °C')),
            ('Min cell temperature', vm.fmt(b.get('min_cell_temperature_c'), 1, ' °C')),
            ('BMS state', vm.txt(b.get('state'))),
            ('Charge limit', vm.fmt(b.get('max_charge_power_kw'), 1, ' kW')),
            ('Discharge limit', vm.fmt(b.get('max_discharge_power_kw'), 1, ' kW')),
            ('Online', vm.onoff(b.get('online'))),
        ])

    def _pcs(self, model):
        self._add_title('Elecod PCS · Operating status')
        self._table(['PCS', 'Link', 'Operating', 'Direction', 'Active power', 'Reactive power', 'DC voltage', 'DC current', 'Grid frequency', 'Fault'],
                    vm.pcs_rows(model), 200)
        self._add_title('Grid and DC measurements')
        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        grid.set_column_homogeneous(True)
        for i, p in enumerate(vm.pcss(model)):
            frame, body = panel()
            body.pack_start(label(vm.txt(p.get('asset_id')).upper(), 'title-card'), False, False, 4)
            metrics = vbox(4)
            for key, value in (
                ('Grid V AB', vm.fmt(p.get('grid_voltage_ab_v'), 0, ' V')),
                ('Grid V BC', vm.fmt(p.get('grid_voltage_bc_v'), 0, ' V')),
                ('Grid V CA', vm.fmt(p.get('grid_voltage_ca_v'), 0, ' V')),
                ('DC bus', vm.fmt(p.get('dc_bus_voltage_v'), 1, ' V')),
                ('DC power', vm.fmt(p.get('dc_power_kw'), 1, ' kW')),
                ('Power factor', vm.fmt(p.get('power_factor'), 3)),
            ):
                metrics.pack_start(label('%s: %s' % (key, value), 'note'), False, False, 0)
            body.pack_start(metrics, False, False, 0)
            grid.attach(frame, i % 4, i // 4, 1, 1)
        self.content.pack_start(grid, False, False, 0)

    def _alarms(self, data):
        self._add_title('Active faults and warnings · up to 100 shown')
        rows = vm.alarm_rows(data)
        self._table(['Severity', 'Asset', 'Signal / alarm', 'Status', 'First seen'], rows, 460)
        self.content.pack_start(label('Mock mode can generate simulated alarms; do not treat them as physical rack faults.', 'note'), False, False, 0)

    def _gateway(self, health, ctrl):
        storage = health.get('storage') or {}
        network = health.get('network') or {}
        startup = health.get('startup') or {}
        self._metric_panel('Local gateway / network status', [
            ('Gateway ID', health.get('gateway_id') or '—'),
            ('Health', health.get('status') or '—'),
            ('Mode', health.get('mode') or '—'),
            ('Connected assets', '%s / %s' % (health.get('assets_online', '—'), health.get('assets_total', '—'))),
            ('Last poll error', health.get('last_poll_error') or 'None reported'),
            ('Startup initialized', 'Yes' if startup.get('ready') is True else 'No'),
            ('Field interface', network.get('field_interface') or '—'),
            ('Wi-Fi interface', network.get('wifi_interface') or '—'),
            ('Storage mode', storage.get('storage_mode') or '—'),
            ('Storage DB', storage.get('database') or '—'),
            ('Control enabled', 'YES' if (health.get('control_sequence') or {}).get('enabled') is True else 'No'),
            ('Internet', 'Not needed for local view'),
        ])
        self._add_title('Control application status · Read-only')
        self._table(['Pair', 'Stage', 'Run status', 'Direction', 'Requested', 'Commanded', 'PCS actual', 'Blocked'],
                    vm.control_rows(ctrl), 175)

    def _draw(self):
        if self.payload is None:
            return
        adjustment = self.scroll.get_vadjustment()
        old_position = adjustment.get_value()
        for child in self.content.get_children():
            self.content.remove(child)
        model, health, alarms, ctrl = self.payload
        if self.tab == 'overview':
            self._overview(model, health, alarms, ctrl)
        elif self.tab == 'battery':
            self._battery(model)
        elif self.tab == 'pcs':
            self._pcs(model)
        elif self.tab == 'alarms':
            self._alarms(alarms)
        elif self.tab == 'gateway':
            self._gateway(health, ctrl)
        self.content.show_all()
        def restore_position():
            adjustment.set_value(min(old_position, max(0, adjustment.get_upper() - adjustment.get_page_size())))
            return False
        GLib.idle_add(restore_position)


def main():
    parser = argparse.ArgumentParser(description='Read-only Kalpa Native HDMI HMI')
    parser.add_argument('--api-url', default='http://127.0.0.1:8000', help='loopback-only gateway API address')
    parser.add_argument('--fullscreen', action='store_true', help='start in fullscreen')
    parser.add_argument('--windowed', action='store_true', help='start windowed')
    args = parser.parse_args()
    try:
        NativeHMI(args.api_url, fullscreen=not args.windowed)
        Gtk.main()
    except Exception as error:
        print('Kalpa GTK HMI startup failed: ' + str(error), file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == '__main__':
    main()
