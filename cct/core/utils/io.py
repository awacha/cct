import logging
import os

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def write_legacy_paramfile(paramfilename, params):
    """Saves the parameter dictionary to a legacy paramfile.
    """
    params['filename'] = os.path.abspath(paramfilename)

    with open(paramfilename, 'wt') as f:
        logger.debug(
            'Writing param file for new exposure to %s' % paramfilename)

        f.write('FSN:\t%d\n' % params['exposure']['fsn'])
        if 'sample' in params:
            f.write('Sample name:\t%s\n' % params['sample']['title'])
        f.write('Sample-to-detector distance (mm):\t%.18f\n' %
                params['geometry']['truedistance'])
        if 'sample' in params:
            f.write('Sample thickness (cm):\t%.18f\n' % params['sample']['thickness.val'])
            f.write('Sample position (cm):\t%.18f\n' % params['sample']['positiony.val'])
            f.write('Sample transmission:\t%.18f\n' % params['sample']['transmission.val'])
        f.write('Measurement time (sec): %f\n' % params['exposure']['exptime'])
        f.write('Beam x y for integration:\t%.18f %.18f\n' % (
            params['geometry']['beamposx'] + 1, params['geometry']['beamposy'] + 1))
        f.write('Pixel size of 2D detector (mm):\t%f\n' %
                params['geometry']['pixelsize'])
        f.write('Primary intensity at monitor (counts/sec):\t%f\n' %
                params['exposure']['exptime'])
        f.write('Date:\t%s\n' % params['exposure']['date'])
        if 'datareduction' in params:
            if 'absintrefFSN' in params['datareduction']:
                f.write('Glassy carbon FSN:\t%d\n' % params['datareduction']['absintrefFSN'])
            if 'absintfactor' in params['datareduction']:
                f.write('Normalisation factor (to absolute units):\t%.18f\n' % params['datareduction']['absintfactor'])
            if 'absintfactor.err' in params['datareduction']:
                f.write('NormFactorError:\t%.18f\n' % params['datareduction']['absintfactor.err'])
            if 'emptybeamFSN' in params['datareduction']:
                f.write('Empty beam FSN:\t%.18f\n' % params['datareduction']['emptybeamFSN'])

        if 'sample' in params:
            f.write('Preparedby:\t%s\n' % params['sample']['preparedby'])
            f.write('Preparetime:\t%s\n' % str(params['sample']['preparetime']))
            f.write('Transmission:\t%.18f\n' % params['sample']['transmission.err'])
            f.write('ThicknessError:\t%.18f\n' % params['sample']['thickness.err'])
            f.write('PosSampleError:\t%.18f\n' % params['sample']['positiony.err'])
            f.write('PosSampleX:\t%.18f\n' % params['sample']['positionx.val'])
            f.write('PosSampleXError:\t%.18f\n' % params['sample']['positionx.err'])
            f.write('DistMinus:\t%.18f\n' % params['sample']['distminus.val'])
            f.write('DistMinusErr:\t%.18f\n' % params['sample']['distminus.err'])
            f.write('TransmError:\t%.18f\n' % params['sample']['transmission.err'])
            f.write('PosSampleError:\t%.18f\n' % params['sample']['positiony.err'])
            f.write('SampleDescription:\t%s\n' % params['sample']['description'])
            f.write('SampleSituation:\t%s\n' % params['sample']['situation'])
            f.write('SampleCategory:\t%s\n' % params['sample']['category'])

        if 'temperature_setpoint' in params['environment']:
            f.write('TemperatureSetpoint:\t%.18f\n' % params['environment']['temperature_setpoint'])
        if 'temperature' in params['environment']:
            f.write('Temperature:\t%.18f\n' % params['environment']['temperature'])
        if 'vacuum_pressure' in params['environment']:
            f.write('Vacuum:\t%.18f\n' % params['environment']['vacuum_pressure'])

        f.write('EndDate:\t%s\n' % params['exposure']['date'])
        f.write('SetupDescription:\t%s\n' %
                params['geometry']['description'])
        f.write('DistError:\t%.18f\n' % params['geometry']['dist_sample_det.err'])
        f.write('Calibrated sample-to-detector distance (mm):\t%.18f\n' % params['geometry']['truedistance'])
        f.write('DistCalibratedError:\t%.18f\n' % params['geometry']['truedistance.err'])
        f.write('XPixel:\t%.18f\n' % params['geometry']['pixelsize'])
        f.write('YPixel:\t%.18f\n' % params['geometry']['pixelsize'])
        f.write('Owner:\t%s\n' % params['accounting']['operator'])
        f.write('__Origin__:\tCCT\n')
        f.write('MonitorError:\t0\n')
        f.write('Wavelength:\t%.18f\n' %
                params['geometry']['wavelength'])
        f.write('WavelengthError:\t%.18f\n' %
                params['geometry']['wavelength.err'])
        f.write('__particle__:\tphoton\n')
        f.write('Project:\t%s\n' % params['accounting']['projectname'])
        f.write('maskid:\t%s\n' %
                params['geometry']['mask'].rsplit('.', 1)[0])
        f.write('StartDate:\t%s\n' % params['exposure']['startdate'])
        f.write('__Origin__:\tCCT\n')

        for m in sorted(params['motors']):
            f.write('motor.%s:\t%f\n' %
                    (m, params['motors'][m]))
        for d in sorted(params['devices']):
            for v in sorted(params['devices'][d]):
                f.write(
                    'devices.%s.%s:\t%s\n' % (d, v, params['devices'][d][v]))
        for k in params['geometry']:
            f.write('geometry.%s:\t%s\n' % (k, params['geometry'][k]))
        for k in params['accounting']:
            f.write('accounting.%s:\t%s\n' %
                    (k, params['accounting'][k]))
        for k in params['exposure']:
            f.write('exposure.%s\t%s\n' %
                    (k, params['exposure'][k]))
        if 'datareduction' in params:
            for k in params["datareduction"]:
                f.write('datareduction.%s\t%s\n'%
                        (k,params['datareduction'][k]))
