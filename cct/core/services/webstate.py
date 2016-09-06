"""Periodically create and update a state file viewable over a HTTP server"""
import datetime
import os
import shutil
import string
import time
from xml.dom.minidom import parse

import numpy as np
import pkg_resources
from gi.repository import GLib

from .service import Service


def get_svg_object_by_id(dom, idname):
    results = []
    for d in dom.childNodes:
        results.extend(get_svg_object_by_id(d, idname))
    try:
        if dom.getAttribute('id') == idname:
            results.append(dom)
    except AttributeError:
        pass
    return results


class WebStateFileWriter(Service):
    name = 'webstate'

    state = {'interval': 30}

    def __init__(self, *args, **kwargs):
        self._timeouthandler = None
        self._statusfile_template = None
        super().__init__(*args, **kwargs)

    def start(self):
        super().start()
        if self.instrument.online:
            self._timeouthandler = GLib.timeout_add(self.state['interval'] * 1000, self.write_statusfile)

    def stop(self):
        if self._timeouthandler is not None:
            GLib.source_remove(self._timeouthandler)
            self._timeouthandler = None
        super().stop()

    def reload_statusfile_template(self):
        # if not hasattr(self,'_statusfile_template'):
        if True:
            with open(pkg_resources.resource_filename(
                    'cct', 'resource/cct_status/credo_status.html'),
                    'rt', encoding='utf-8') as f:
                self._statusfile_template = string.Template(f.read())

    def create_devicehealth_data(self):
        # create contents of devicehealth table.
        dhtc = ''
        # First row: device names
        dhtc += '<tr>\n  <th>Device</th>\n'
        for d in sorted(self.instrument.devices):
            dhtc += '  <td>' + d.capitalize() + '</td>\n'
        dhtc += '</tr>\n<tr>\n  <th>Status</th>\n'
        for d in sorted(self.instrument.devices):
            try:
                status = self.instrument.devices[d].get_variable('_status')
            except KeyError:
                status = 'Disconnected'
                bg = 'red'
            else:
                if self.instrument.devices[d].get_connected():
                    bg = 'green'
                else:
                    bg = 'gray'
            dhtc += '  <td style="background:{}">'.format(bg) + str(status) + '</td>\n'
        dhtc += '</tr>\n<tr>\n  <th>Verbose status</th>\n'
        for d in sorted(self.instrument.devices):
            try:
                status = self.instrument.devices[d].get_variable('_auxstatus')
            except KeyError:
                status = 'Missing'
            dhtc += "  <td>" + str(status) + '</td>\n'
        dhtc += '</tr>\n<tr>\n  <th>Last send time</th>\n'
        for d in sorted(self.instrument.devices):
            try:
                lastsend = self.instrument.services['telemetrymanager'][d].last_send
            except KeyError:
                lastsend = np.nan
                bg = 'red'
            else:
                if lastsend > 5:
                    bg = 'red'
                else:
                    bg = 'green'
            dhtc += '  <td style="background:{}">{:.2f}</td>\n'.format(bg, lastsend)
        dhtc += '</tr>\n<tr>\n  <th>Last recv time</th>\n'
        for d in sorted(self.instrument.devices):
            try:
                lastrecv = self.instrument.services['telemetrymanager'][d].last_recv
            except KeyError:
                lastrecv = np.nan
                bg = 'red'
            else:
                if lastrecv > 5:
                    bg = 'red'
                else:
                    bg = 'green'
            dhtc += '  <td style="background:{}">{:.2f}</td>\n'.format(bg, lastrecv)

        dhtc += '</tr>\n<tr>\n  <th>Background process restarts</h>\n'
        for d in sorted(self.instrument.devices):
            restarts = self.instrument.devices[d].background_startup_count
            dhtc += '  <td>' + str(restarts - 1) + '</td>\n'
        dhtc += '</tr>\n'
        return dhtc

    def create_motorstatus_data(self):
        # Make motor status table
        mst = """
        <tr>
            <th>Motor</th>
            <th>Position</th>
            <th>Left limit</th>
            <th>Right limit</th>
            <th>Left switch</th>
            <th>Right switch</th>
            <th>Status flags</th>
        </tr>\n"""

        def endswitch_text(state):
            if state:
                return 'Active'
            else:
                return ''

        def endswitch_color(state):
            if state:
                return 'red'
            else:
                return 'green'

        for m in sorted(self.instrument.motors):
            mot = self.instrument.motors[m]
            mst += """
            <tr>
                <td>{}</td>
                <td><b>{:.3f}</b></td>
                <td>{:.3f}</td>
                <td>{:.3f}</td>
                <td style="background:{};text-align:center">{}</td>
                <td style="background:{};text-align:center">{}</td>
                <td>{}</td>
            </tr>
            """.format(m, mot.where(), mot.get_variable('softleft'),
                       mot.get_variable('softright'), endswitch_color(mot.leftlimitswitch()),
                       endswitch_text(mot.leftlimitswitch()), endswitch_color(mot.rightlimitswitch()),
                       endswitch_text(mot.rightlimitswitch()), ', '.join(mot.decode_error_flags()))
        return mst

    def format_genix_faultvalue(self, name):
        try:
            value = self.instrument.get_device('xray_source').get_variable(name + '_fault')
        except KeyError:
            value = np.nan
            bg = 'red'
        else:
            if value:
                bg = 'red'
            else:
                bg = 'green'
        return bg, name.replace('_', ' ').capitalize()

    def create_xraysource_status(self):
        # make X-ray source status

        # noinspection PyStringFormat
        variables = {}
        for var in ['ht', 'current', 'power', 'shutter']:
            try:
                variables[var] = self.instrument.get_device('xray_source').get_variable(var)
            except (KeyError, AttributeError):
                variables[var] = np.nan
        if isinstance(variables['shutter'], bool):
            variables['shutter'] = ['Closed', 'Open'][variables['shutter']]
        xray = """
        <tr>
            <td>HV: {ht:.2f} V</td>
            <td>Current: {current:.2f} mA</td>
            <td>Power: {power:.2f} W</td>
            <td>Shutter: {shutter}</td>
        </tr>
        """.format(**variables)
        for i, fault in enumerate(
                ['xray_light', 'shutter_light', 'sensor1', 'sensor2', 'tube_position', 'vacuum', 'waterflow',
                 'safety_shutter', 'temperature', 'relay_interlock', 'door', 'filament']):
            if i % 4 == 0:
                xray += "<tr>\n"
            xray += '<td style="background-color:{}">{}</td>\n'.format(*self.format_genix_faultvalue(fault))
            if i % 4 == 3:
                xray += '</tr>\n'
        return xray

    def create_detector_status(self):
        # detector status
        try:
            detstat = self.instrument.get_device('detector').get_all_variables()
        except KeyError:
            return ""
        if detstat['temperature0'] < 15 or detstat['temperature0'] > 55:
            detstat['temperature0_bg'] = 'red'
        elif detstat['temperature0'] < 20 or detstat['temperature0'] > 37:
            detstat['temperature0_bg'] = 'orange'
        else:
            detstat['temperature0_bg'] = 'green'
        if detstat['temperature1'] < 15 or detstat['temperature1'] > 35:
            detstat['temperature1_bg'] = 'red'
        elif detstat['temperature1'] < 20 or detstat['temperature1'] > 33:
            detstat['temperature1_bg'] = 'orange'
        else:
            detstat['temperature1_bg'] = 'green'
        if detstat['temperature2'] < 15 or detstat['temperature2'] > 45:
            detstat['temperature2_bg'] = 'red'
        elif detstat['temperature2'] < 20 or detstat['temperature2'] > 35:
            detstat['temperature2_bg'] = 'orange'
        else:
            detstat['temperature2_bg'] = 'green'
        if detstat['humidity0'] > 80:
            detstat['humidity0_bg'] = 'red'
        elif detstat['humidity0'] > 45:
            detstat['humidity0_bg'] = 'orange'
        else:
            detstat['humidity0_bg'] = 'green'
        if detstat['humidity1'] > 80:
            detstat['humidity1_bg'] = 'red'
        elif detstat['humidity1'] > 45:
            detstat['humidity1_bg'] = 'orange'
        else:
            detstat['humidity1_bg'] = 'green'
        if detstat['humidity2'] > 30:
            detstat['humidity2_bg'] = 'red'
        elif detstat['humidity2'] > 10:
            detstat['humidity2_bg'] = 'orange'
        else:
            detstat['humidity2_bg'] = 'green'

        return """
        <tr>
            <td>Exposure time:</td><td>{exptime:.2f} sec</td>
            <td>Exposure period:</td><td>{expperiod:.2f} sec</td>
        <tr>
            <td>Number of images:</td><td>{nimages:.2f} sec</td>
            <td>Threshold:</td><td>{threshold:.0f} eV ({gain} gain)</td>
        </tr>
        <tr>
            <td>Power board temperature:</td><td style="background-color:{temperature0_bg}">{temperature0:.1f} °C</td>
            <td>Power board humidity:</td><td style="background-color:{humidity0_bg}">{humidity0:.1f} %</td>
        </tr>
        <tr>
            <td>Base plate temperature:</td><td style="background-color:{temperature1_bg}">{temperature1:.1f} °C</td>
            <td>Base plate humidity:</td><td style="background-color:{humidity1_bg}">{humidity1:.1f} %</td>
        </tr>
        <tr>
            <td>Sensor temperature:</td><td style="background-color:{temperature2_bg}">{temperature2:.1f} °C</td>
            <td>Sensor humidity:</td><td style="background-color:{humidity2_bg}">{humidity2:.1f} %</td>
        </tr>
        """.format(**detstat)

    def create_fsnlist_data(self):
        fl = "<tr>\n    <th>Prefix:</th>\n"
        for p in sorted(self.instrument.services['filesequence'].get_prefixes()):
            fl += "    <td>{}</td>\n".format(p)
        fl += '    <td>Scan</td>\n</tr>\n<tr>\n    <th>Last FSN:</th>\n'
        for p in sorted(self.instrument.services['filesequence'].get_prefixes()):
            fl += "    <td>{:d}</td>\n".format(self.instrument.services['filesequence'].get_lastfsn(p))
        fl += '    <td>{:d}</td>\n'.format(self.instrument.services['filesequence'].get_lastscan())
        fl += '</tr>\n<tr>\n    <th>Next FSN:</th>\n'
        for p in sorted(self.instrument.services['filesequence'].get_prefixes()):
            fl += '    <td>{:d}</td>\n'.format(self.instrument.services['filesequence'].get_nextfreefsn(p, False))
        fl += '    <td>{:d}</td>\n'.format(self.instrument.services['filesequence'].get_nextfreescan(False))
        fl += '</tr>'
        return fl

    def create_accountingdata(self):
        # user, project ID, project title, proposer
        ad = """
        <tr>
            <td>Operator:</td>
            <td>{operator}</td>
            <td>Privilege level:</td>
            <td>{privilegelevel}</td>
        </tr>
        <tr>
            <td>Project ID:</td>
            <td>{project}</td>
            <td>Principal investigator:</td>
            <td>{proposer}</td>
        </tr>
        <tr>
        """.format(operator=self.instrument.services['accounting'].get_user().username,
                   privilegelevel=self.instrument.services['accounting'].get_privilegelevel().name,
                   project=self.instrument.services['accounting'].get_project().projectid,
                   proposer=self.instrument.services['accounting'].get_project().proposer)
        return ad

    def write_statusfile(self):
        """This method writes a status file: a HTML file and other auxiliary
        files (e.g. images to include), which can be published over the net.
        """
        self.reload_statusfile_template()
        uptime = time.monotonic() - self.instrument.starttime
        uptime_hour = uptime // 3600
        uptime -= uptime_hour * 3600
        uptime_min = uptime // 60
        uptime_sec = uptime - uptime_min * 60
        subs = {'timestamp': str(datetime.datetime.now()),
                'uptime': '{:02.0f}:{:02.0f}:{:05.2f}'.format(uptime_hour, uptime_min, uptime_sec),
                'devicehealth_tablecontents': self.create_devicehealth_data(),
                'motorpositions_tablecontents': self.create_motorstatus_data(),
                'xraysource_status': self.create_xraysource_status(),
                'detector_status': self.create_detector_status(),
                'filesequence_data': self.create_fsnlist_data(),
                'accounting_data': self.create_accountingdata(),
                }
        shutil.copy2(pkg_resources.resource_filename('cct', 'resource/cct_status/credo_status.css'),
                     os.path.join(self.instrument.config['path']['directories']['status'], 'credo_status.css'))
        self.adjust_svg()
        with open(os.path.join(self.instrument.config['path']['directories']['status'], 'index.html'), 'wt',
                  encoding='utf-8') as f:
            f.write(self._statusfile_template.safe_substitute(**subs))
        return True

    def adjust_svg(self):
        dom = parse(pkg_resources.resource_filename('cct', 'resource/cct_status/scheme_interactive.svg'))
        try:
            shutter = self.instrument.get_device('xray_source').get_variable('shutter')
        except KeyError:
            shutter = False
        beamstop = self.instrument.get_beamstop_state()
        for x in get_svg_object_by_id(dom, 'xray'):
            if shutter:
                x.setAttribute('visibility', 'visible')
            else:
                x.setAttribute('visibility', 'hidden')
        for x in get_svg_object_by_id(dom, 'hitting_xray'):
            if shutter and (beamstop != 'in'):
                x.setAttribute('visibility', 'visible')
            else:
                x.setAttribute('visibility', 'hidden')
        for x in get_svg_object_by_id(dom, 'beamstop_in'):
            if beamstop == 'out':
                x.setAttribute('visibility', 'hidden')
            else:
                x.setAttribute('visibility', 'visible')
        for x in get_svg_object_by_id(dom, 'beamstop_out'):
            if beamstop == 'in':
                x.setAttribute('visibility', 'hidden')
            else:
                x.setAttribute('visibility', 'visible')
        try:
            ht = '{:.2f} kV'.format(self.instrument.get_device('xray_source').get_variable('ht'))
        except KeyError:
            ht = '??? kV'
        for x in get_svg_object_by_id(dom, 'hv'):
            x.firstChild.firstChild.data = ht
        try:
            current = '{:.2f} mA'.format(self.instrument.get_device('xray_source').get_variable('current'))
        except KeyError:
            current = '??? mA'
        for x in get_svg_object_by_id(dom, 'current'):
            x.firstChild.firstChild.data = current
        for x in get_svg_object_by_id(dom, 'detector_state'):
            try:
                x.firstChild.firstChild.data = self.instrument.get_device('detector').get_variable('_status')
            except KeyError:
                x.firstChild.firstChild.data = 'Disconnected'
        for x in get_svg_object_by_id(dom, 'vacuum'):
            try:
                x.firstChild.firstChild.data = '{:.3f} mbar'.format(
                    self.instrument.devices['tpg201'].get_variable('pressure'))
            except KeyError:
                x.firstChild.firstChild.data = 'Vacuum gauge disconnected'
        for x in get_svg_object_by_id(dom, 'samplename'):
            x.firstChild.firstChild.data = str(self.instrument.services['samplestore'].get_active_name())
        for x in get_svg_object_by_id(dom, 'temperature'):
            try:
                temperature = self.instrument.devices['haakephoenix'].get_variable('temperature_internal')
                temperature = '{:.2f} °C'.format(temperature)
                if not self.instrument.devices['haakephoenix'].get_connected():
                    temperature = 'Uncontrolled'
            except KeyError:
                temperature = 'Uncontrolled'
            x.firstChild.firstChild.data = temperature
        for m in self.instrument.motors:
            for x in get_svg_object_by_id(dom, m):
                x.firstChild.firstChild.data = '{:.3f}'.format(self.instrument.motors[m].where())
        with open(os.path.join(self.instrument.config['path']['directories']['status'], 'scheme.svg'), 'wt',
                  encoding='utf-8') as f:
            dom.writexml(f)
