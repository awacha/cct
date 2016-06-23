"""Periodically create and update a state file viewable over a HTTP server"""
import datetime
import os
import shutil
import string
from xml.dom.minidom import parse

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
    webstate_timeout = 30

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._timeouthandler = None

    def start(self):
        self._timeouthandler = GLib.timeout_add(self.webstate_timeout * 1000, self.write_statusfile)

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
            status = self.instrument.devices[d].get_variable('_status')
            if self.instrument.devices[d]._get_connected():
                bg = 'green'
            else:
                bg = 'red'
            dhtc += '  <td style="background:%s">' % bg + str(status) + '</td>\n'
        dhtc += '</tr>\n<tr>\n  <th>Verbose status</th>\n'
        for d in sorted(self.instrument.devices):
            status = self.instrument.devices[d].get_variable('_auxstatus')
            dhtc += "  <td>" + str(status) + '</td>\n'
        dhtc += '</tr>\n<tr>\n  <th>Last send time</th>\n'
        for d in sorted(self.instrument.devices):
            lastsend = self.instrument._telemetries[d]['last_send']
            if lastsend > 5:
                bg = 'red'
            else:
                bg = 'green'
            dhtc += '  <td style="background:%s">%.2f</td>\n' % (bg, lastsend)
        dhtc += '</tr>\n<tr>\n  <th>Last recv time</th>\n'
        for d in sorted(self.instrument.devices):
            lastrecv = self.instrument._telemetries[d]['last_recv']
            if lastrecv > 5:
                bg = 'red'
            else:
                bg = 'green'
            dhtc += '  <td style="background:%s">%.2f</td>\n' % (bg, lastrecv)

        dhtc += '</tr>\n<tr>\n  <th>Background process restarts</h>\n'
        for d in sorted(self.instrument.devices):
            restarts = self.instrument.devices[d]._background_startup_count
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
                <td>%s</td>
                <td><b>%.3f</b></td>
                <td>%.3f</td>
                <td>%.3f</td>
                <td style="background:%s;text-align:center">%s</td>
                <td style="background:%s;text-align:center">%s</td>
                <td>%s</td>
            </tr>
            """ % (m, mot.where(), mot.get_variable('softleft'),
                   mot.get_variable('softright'), endswitch_color(mot.leftlimitswitch()),
                   endswitch_text(mot.leftlimitswitch()), endswitch_color(mot.rightlimitswitch()),
                   endswitch_text(mot.rightlimitswitch()), ', '.join(mot.decode_error_flags()))
        return mst

    def format_faultvalue(self, name):
        value = self.instrument.xray_source.get_variable(name + '_fault')
        if value:
            bg = 'red'
        else:
            bg = 'green'
        return bg, name.replace('_', ' ').capitalize()

    def create_xraysource_status(self):
        # make X-ray source status

        # noinspection PyStringFormat
        xray = """
        <tr>
            <td>HV: %.2f V</td>
            <td>Current: %.2f mA</td>
            <td>Power: %.2f W</td>
            <td>Shutter: %s</td>
        </tr>
        <tr>
            <td style="background-color:%s">%s</td>
            <td style="background-color:%s">%s</td>
            <td style="background-color:%s">%s</td>
            <td style="background-color:%s">%s</td>
        </tr>
        <tr>
            <td style="background-color:%s">%s</td>
            <td style="background-color:%s">%s</td>
            <td style="background-color:%s">%s</td>
            <td style="background-color:%s">%s</td>
        </tr>
        <tr>
            <td style="background-color:%s">%s</td>
            <td style="background-color:%s">%s</td>
            <td style="background-color:%s">%s</td>
            <td style="background-color:%s">%s</td>
        </tr>
        """ % (self.instrument.xray_source.get_variable('ht'),
               self.instrument.xray_source.get_variable('current'),
               self.instrument.xray_source.get_variable('power'),
               ['Closed', 'Open'][self.instrument.xray_source.get_variable('shutter')],
               *self.format_faultvalue('xray_light'),
               *self.format_faultvalue('shutter_light'),
               *self.format_faultvalue('sensor1'),
               *self.format_faultvalue('sensor2'),
               *self.format_faultvalue('tube_position'),
               *self.format_faultvalue('vacuum'),
               *self.format_faultvalue('waterflow'),
               *self.format_faultvalue('safety_shutter'),
               *self.format_faultvalue('temperature'),
               *self.format_faultvalue('relay_interlock'),
               *self.format_faultvalue('door'),
               *self.format_faultvalue('filament'),
               )
        return xray

    def create_detector_status(self):
        # detector status
        detstat = self.instrument.detector.get_all_variables()
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

        detector = """
        <tr>
            <td>Exposure time:</td><td>%(exptime).2f sec</td>
            <td>Exposure period:</td><td>%(expperiod).2f sec</td>
        <tr>
            <td>Number of images:</td><td>%(nimages).2f sec</td>
            <td>Threshold:</td><td>%(threshold).0f eV (%(gain)s gain)</td>
        </tr>
        <tr>
            <td>Power board temperature:</td><td style="background-color:%(temperature0_bg)s">%(temperature0).1f °C</td>
            <td>Power board humidity:</td><td style="background-color:%(humidity0_bg)s">%(humidity0).1f %%</td>
        </tr>
        <tr>
            <td>Base plate temperature:</td><td style="background-color:%(temperature1_bg)s">%(temperature1).1f °C</td>
            <td>Base plate humidity:</td><td style="background-color:%(humidity1_bg)s">%(humidity1).1f %%</td>
        </tr>
        <tr>
            <td>Sensor temperature:</td><td style="background-color:%(temperature2_bg)s">%(temperature2).1f °C</td>
            <td>Sensor humidity:</td><td style="background-color:%(humidity2_bg)s">%(humidity2).1f %%</td>
        </tr>
        """ % detstat
        return detector

    def create_fsnlist_data(self):
        fl = "<tr>\n    <th>Prefix:</th>\n"
        for p in sorted(self.instrument.filesequence.get_prefixes()):
            fl += "    <td>%s</td>\n" % p
        fl += '    <td>Scan</td>\n</tr>\n<tr>\n    <th>Last FSN:</th>\n'
        for p in sorted(self.instrument.filesequence.get_prefixes()):
            fl += "    <td>%d</td>\n" % self.instrument.filesequence.get_lastfsn(p)
        fl += '    <td>%d</td>\n' % self.instrument.filesequence.get_lastscan()
        fl += '</tr>\n<tr>\n    <th>Next FSN:</th>\n'
        for p in sorted(self.instrument.filesequence.get_prefixes()):
            fl += '    <td>%d</td>\n' % self.instrument.filesequence.get_nextfreefsn(p, False)
        fl += '    <td>%d</td>\n' % self.instrument.filesequence.get_nextfreescan(False)
        fl += '</tr>'
        return fl

    def create_accountingdata(self):
        # user, project ID, project title, proposer
        ad = """
        <tr>
            <td>Operator:</td>
            <td>%(operator)s</td>
            <td>Privilege level:</td>
            <td>%(privilegelevel)s</td>
        </tr>
        <tr>
            <td>Project ID:</td>
            <td>%(project)s</td>
            <td>Principal investigator:</td>
            <td>%(proposer)s</td>
        </tr>
        <tr>
        """ % {'operator': self.instrument.accounting.get_user().username,
               'privilegelevel': self.instrument.accounting.get_privilegelevel().name,
               'project': self.instrument.accounting.get_project().projectid,
               'proposer': self.instrument.accounting.get_project().proposer,
               }
        return ad

    def write_statusfile(self):
        """This method writes a status file: a HTML file and other auxiliary
        files (e.g. images to include), which can be published over the net.
        """
        self.reload_statusfile_template()
        uptime = (datetime.datetime.now() - self.instrument._starttime).total_seconds()
        uptime_hour = uptime // 3600
        uptime = uptime - uptime_hour * 3600
        uptime_min = uptime // 60
        uptime_sec = uptime - uptime_min * 60
        subs = {'timestamp': str(datetime.datetime.now()),
                'uptime': '%d:%d:%.2f' % (uptime_hour, uptime_min, uptime_sec),
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
        shutter = self.instrument.xray_source.get_variable('shutter')
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
        for x in get_svg_object_by_id(dom, 'hv'):
            x.firstChild.firstChild.data = '%.2f kV' % self.instrument.xray_source.get_variable('ht')
        for x in get_svg_object_by_id(dom, 'current'):
            x.firstChild.firstChild.data = '%.2f mA' % self.instrument.xray_source.get_variable('current')
        for x in get_svg_object_by_id(dom, 'detector_state'):
            x.firstChild.firstChild.data = '%s' % self.instrument.detector.get_variable('_status')
        for x in get_svg_object_by_id(dom, 'vacuum'):
            x.firstChild.firstChild.data = '%.3f mbar' % self.instrument.devices['tpg201'].get_variable('pressure')
        for x in get_svg_object_by_id(dom, 'samplename'):
            x.firstChild.firstChild.data = str(self.instrument.samplestore.get_active_name())
        for x in get_svg_object_by_id(dom, 'temperature'):
            try:
                temperature = self.instrument.devices['haakephoenix'].get_variable('temperature_internal')
                temperature = '%.2f °C' % temperature
                if not self.instrument.devices['haakephoenix']._get_connected():
                    temperature = 'Uncontrolled'
            except KeyError:
                temperature = 'Uncontrolled'
            x.firstChild.firstChild.data = temperature
        for m in self.instrument.motors:
            for x in get_svg_object_by_id(dom, m):
                x.firstChild.firstChild.data = '%.3f' % (self.instrument.motors[m].where())
        with open(os.path.join(self.instrument.config['path']['directories']['status'], 'scheme.svg'), 'wt',
                  encoding='utf-8') as f:
            dom.writexml(f)
