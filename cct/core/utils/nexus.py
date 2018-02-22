import h5py
import datetime
import dateutil.parser
import pkg_resources
import numpy as np
from typing import Any

def newdataset(group:h5py.Group, name:str, data:Any, **attributes) -> h5py.Dataset:
    dataset=group.create_dataset(name, data=data)
    for a in attributes:
        dataset.attrs[a] = attributes[a]
    return dataset

def newgroup(group:h5py.Group, name:str, nxclass:str, **attributes) -> h5py.Group:
    grp = group.create_group(name)
    grp.attrs['NX_class'] = nxclass
    for a in attributes:
        grp.attrs[a] = attributes[a]
    return grp

def write_nexus(group:h5py.Group, param:dict, mask:np.ndarray, intensity:np.ndarray, error:np.ndarray):
    entry = group.create_group('entry')
    entry.attrs['NX_class'] = 'NXentry'
    entry.attrs['default'] = 'data'
    st=dateutil.parser.parse(param['exposure']['startdate'])
    et=dateutil.parser.parse(param['exposure']['enddate'])
    entry.create_dataset('start_time', data=st.isoformat())
    entry.create_dataset('end_time', data=et.isoformat())
    entry.create_dataset('title', data=param['sample']['title'])
    entry.create_dataset('definition', 'NXsas')
    entry.create_dataset('duration', (et-st).total_seconds())
    entry['duration'].attrs['units'] = 's'
    entry.create_dataset('collection_time', data=param['exposure']['exptime'])
    entry['collection_time'].attrs['units'] = 's'
    entry['definition'].attrs['URL'] = 'http://download/nexusformat.org/doc/html/classes/applications/NXsas.html'
    newdataset(entry, 'collection_identifier', param['accounting']['projectid'])
    newdataset(entry, 'collection_description', param['accounting']['projectname'])
    newdataset(entry, 'program_name', 'cct', version=pkg_resources.get_distribution('cct').version)
    user = newgroup(group, 'operator', 'NXuser')
    newdataset(user, 'name', param['accounting']['operator'])
    newdataset(user, 'role', 'operator')
    user = newgroup(group, 'principal_investigator', 'NXuser')
    newdataset(user, 'name', param['accounting']['proposer'])
    newdataset(user, 'role', 'principal_investigator')
    user = newgroup(group, 'sample_preparator', 'NXuser')
    newdataset(user, 'name', param['sample']['preparedby'])
    newdataset(user, 'role', 'sample_preparator')
    sample = newgroup(group, 'sample', 'NXsample')
    newdataset(sample, 'name', param['sample']['title'])
    newdataset(sample, 'type', param['sample']['category'])
    newdataset(sample, 'situation', param['sample']['situation'])
    newdataset(sample, 'description', param['sample']['description'])
    newdataset(sample, 'thickness', param['sample']['thickness.val'], uncertainties=param['sample']['thickness.err'], units='cm')
    newdataset(sample, 'distance', param['geometry']['truedistance'], uncertainties=param['geometry']['truedistance.err'], units='mm')
    newdataset(sample, 'preparation_date', dateutil.parser.parse(param['sample']['preparetime']).isoformat())
    newdataset(sample, 'transmission', param['sample']['transmission.val'], uncertainties = param['sample']['transmission.err']) # non-standard!
    newdataset(sample, 'position_x', param['sample']['positionx.val'], uncertainties = param['sample']['positionx.err'], units='mm') # non-standard!
    newdataset(sample, 'position_y', param['sample']['positiony.val'], uncertainties = param['sample']['positiony.err'], units='mm') # non-standard!
    newdataset(sample, 'distance_decrease', param['sample']['distminus.val'], uncertainties = param['sample']['distminus.err'], units='mm') # non-standard!

    instrument = newgroup(group, 'instrument', 'NXinstrument')
    newdataset(instrument, 'name','Creative Research Equipment for DiffractiOn', short_name='CREDO')
    geom = param['geometry']
    for i, distance in [(1, -geom['dist_ph3_sample']-geom['dist_ph2_ph3']-geom['dist_ph1_ph2']),
                        (2, -geom['dist_ph3_sample']-geom['dist_ph2_ph3']),
                        (3, -geom['dist_ph3_sample'])]:
        ph=newgroup(instrument, 'pinhole_{}'.format(i), 'NXpinhole')
        newdataset(ph, 'material', 'PtIr')
        newdataset(ph, 'description','Pinhole #{}'.format(i))
        geo=newgroup(ph, 'geometry', 'NXgeometry')
        newdataset(geo,'component_index', -i)
        newdataset(ph, 'diameter', geom['pinhole_{}'.format(i)]*0.001, units='mm')
        translation = newgroup(geo, 'translation', 'NXtranslation')
        newdataset(translation, 'distances', np.array([0,0,distance]), units='mm')
    bs=newgroup(instrument, 'beam_stop', 'NXbeam_stop')
    newdataset(bs, 'description', 'circular')
    newdataset(bs, 'size', geom['beamstop'], units='mm')
    newdataset(bs, 'distance_to_detector', geom['dist_det_beamstop'], units='mm')
    newdataset(bs, 'status', 'in') # Only an assumption!
    detector=newgroup(instrument, 'detector', 'NXdetector')
    newdataset(detector, 'distance', geom['truedistance'])
    newdataset(detector, 'description', param['devices']['pilatus']['cameraname'])
    newdataset(detector, 'serial_number', param['devices']['pilatus']['cameraSN'])
    newdataset(detector, 'type', 'CMOS')
    newdataset(detector, 'beam_center_x', geom['beamposy'], units='pixel', uncertainties=geom['beamposy.err'])
    newdataset(detector, 'beam_center_y', geom['beamposx'], units='pixel', uncertainties=geom['beamposx.err'])
    newdataset(detector, 'pixel_mask', ((mask==0)*256).astype(np.int32))
    newdataset(detector, 'countrate_correction_applied', True)
    newdataset(detector, 'bit_depth_readout', 20)
    newdataset(detector, 'detector_readout_time',0.0023, units='s')
    newdataset(detector, 'sensor_material', 'Si')
    newdataset(detector, 'sensor_thickness', 0.450, units='mm')
    newdataset(detector, 'threshold_energy', param['devices']['pilatus']['threshold'], units='eV')
    newdataset(detector, 'x_pixel_size', geom['pixelsize']*0.001, uncertainties=geom['pixelsize.err']*0.001, units='mm')
    newdataset(detector, 'y_pixel_size', geom['pixelsize']*0.001, uncertainties=geom['pixelsize.err']*0.001, units='mm')
    newdataset(detector, 'dead_time', param['devices']['pilatus']['tau'], units='s')
    newdataset(detector, 'gain_setting', param['devices']['pilatus']['gain'])
    newdataset(detector, 'saturation_value', param['devices']['pilatus']['cutoff'])
    newdataset(detector, 'layout', 'area')
    newdataset(detector, 'angular_calibration_applied', False)
    newdataset(detector, 'flatfield_applied', True)
    newdataset(detector, 'frame_time', param['devices']['pilatus']['expperiod'])
    newdataset(detector, 'data', intensity, uncertainties='data_error')
    newdataset(detector, 'data_error', error)
    for motname, devname, idx in [('BeamStop_X', 'tmcm351b',0),
                              ('BeamStop_Y', 'tmcm351b',1),
                              ('PH1X', 'tmcm6110',0),
                              ('PH1Y', 'tmcm6110',1),
                              ('PH2X', 'tmcm6110',2),
                              ('PH2Y', 'tmcm6110',3),
                              ('PH3X', 'tmcm6110',4),
                              ('PH3Y', 'tmcm6110',5),
                              ('Sample_X', 'tmcm351a', 1),
                              ('Sample_Y', 'tmcm351a', 2),
                              ('Unknown1', 'tmcm351a', 0),
                              ('Unknown2', 'tmcm351b', 2),
                              ]:
        dev = param['devices'][devname]
        mot = newgroup(instrument, 'motname', 'NXpositioner')
        newdataset(mot, 'name', motname)
        newdataset(mot, 'value', dev['actualposition${}'.format(idx)], units='mm')
        newdataset(mot, 'raw_value', dev['actualpositionraw${}'.format(idx)], units='microsteps')
        newdataset(mot, 'target_value', dev['targetposition${}'.format(idx)], units='mm')
        newdataset(mot, 'soft_limit_min', dev['softleft${}'.format(idx)], units='mm')
        newdataset(mot, 'soft_limit_max', dev['softright${}'.format(idx)], units='mm')
        newdataset(mot, 'velocity', dev['maxspeed${}'.format(idx)], units='mm/s')
        newdataset(mot, 'raw_velocity', dev['maxspeedraw${}'.format(idx)])
        newdataset(mot, 'acceleration_time', dev['maxspeed${}'.format(idx)]/dev['maxacceleration${}'.format(idx)], units='s')
        newdataset(mot, 'left_limit_hit', dev['leftswitchstatus${}'.format(idx)]) # non-standard!
        newdataset(mot, 'right_limit_hit', dev['rightswitchstatus${}'.format(idx)]) # non-standard!
        newdataset(mot, 'left_limit_switch_enabled', dev['leftswitchenable${}'.format(idx)]) # non-standard!
        newdataset(mot, 'right_limit_switch_enabled', dev['rightswitchenable${}'.format(idx)]) # non-standard!
        newdataset(mot, 'standbycurrent', dev['standbycurrent${}'.format(idx)], units='A') # non-standard!
        newdataset(mot, 'drivecurrent', dev['maxcurrent${}'.format(idx)], units='A') # non-standard!

    source=newgroup(instrument, 'source','NXsource')
    genix = param['devices']['genix']
    newdataset(source, 'distance', -geom['dist_ph3_sample']-geom['dist_ph2_ph3']-geom['dist_ph1_ph2']-geom['dist_source_ph1'], units='mm')
    newdataset(source, 'name', 'GeniX3D Cu ULD', short_name='genix')
    newdataset(source, 'type', 'Fixed Tube X-ray')
    newdataset(source, 'probe', 'x-ray')
    newdataset(source, 'power', genix['power'], units='W')
    newdataset(source, 'energy', genix['ht'], units='kV')
    newdataset(source, 'current', genix['current'], units='mA')
    #newdataset(source, 'flux', None) # ToDo
    newdataset(source, 'voltage', genix['ht'], units='kV')
    newdataset(source, 'target_material', 'Cu')
    d1 = geom['pinhole_1']*0.001
    d2 = geom['pinhole_2']*0.001
    l1= geom['dist_ph1_ph2']
    l2= geom['dist_ph2_ph3']
    ls=geom['dist_ph3_sample']

    beamsizeatsample = (d1+d2)/(l1+l2)*(l1+l2+ls)-d1
    flux = param['datareduction']['flux']/(np.pi*beamsizeatsample**2)
    dflux = param['datareduction']['flux.err']/(np.pi*beamsizeatsample**2)
    newdataset(source, 'flux', flux, units='s-1 cm-2', uncertainties=dflux)

    mono = newgroup(instrument, 'monochromator', 'NXmonochromator')
    newdataset(mono, 'wavelength', geom['wavelength'], units='nm', uncertainties=geom['wavelength.err'])
    newdataset(mono, 'wavelength_spread', geom['wavelength.err']/geom['wavelength'])
    monitor = newgroup(group, 'control', 'NXmonitor')
    newdataset(monitor, 'mode', 'timer')
    newdataset(monitor, 'preset', param['exposure']['exptime'],units='s')
    newdataset(monitor, 'integral', param['exposure']['exptime'],units='s')
    collimator = newgroup(instrument, 'collimator', 'NXcollimator')
    cgeo = newgroup(collimator, 'geometry', 'NXgeometry')
    cshape = newgroup(cgeo, 'shape', 'NXshape')
    newdataset(cshape, 'shape', 'nxcylinder')
    newdataset(cshape, 'size', beamsizeatsample)

    data = newgroup(group, 'data', 'NXdata', signal='intensity')
    data.intensity = h5py.SoftLink('../instrument/detector/data')
    data.data_error = h5py.SoftLink('../instrument/detector/data_error')

    return group



