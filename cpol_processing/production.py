"""
CPOL Level 1b main production line.

@title: CPOL_PROD_1b
@author: Valentin Louf <valentin.louf@monash.edu>
@institution: Bureau of Meteorology

.. autosummary::
    :toctree: generated/

    process_and_save
    plot_quicklook
    production_line
"""
# Python Standard Library
import gc
import os
import time
import logging
import datetime
import traceback

# Other Libraries -- Matplotlib must be imported before pyart.
import netCDF4
import numpy as np
import matplotlib
matplotlib.use('Agg')  # <- Reason why matplotlib is imported first.
import matplotlib.colors as colors
import matplotlib.pyplot as pl
import pyart

# Custom modules.
from .processing_codes import radar_codes
from .processing_codes import atten_codes
from .processing_codes import gridding_codes
from .processing_codes import hydro_codes


# Get logger.
logger = logging.getLogger()


def process_and_save(radar_file_name, outpath, outpath_grid, figure_path, sound_dir, is_seapol=False):
    """
    Call processing function and write data.

    Parameters:
    ===========
        radar_file_name: str
            Name of the input radar file.
        outpath: str
            Path for saving output data.
        outpath_grid: str
            Path for saving gridded data.
        figure_path: str
            Path for saving figures.
        sound_dir: str
            Path to radiosoundings directory.
    """
    def correct_output_filename(outfilename):
        """
        Some level 0 and/or level 1a treatment did not generate the right file names.
        Correcting these here.

        Parameter:
        ==========
        outfilename: str
            Output file name.

        Returns:
        ========
        outfilename: str
            Corrected output file name.
        """
        outfilename = outfilename.replace("level1a", "level1b")

        # Correct occasional missing suffix.
        if "level1b" not in outfilename:
            outfilename = outfilename.replace(".nc", "_level1b.nc")
        # Correct an occasional mislabelling from RadX.
        if "SURV" in outfilename:
            outfilename = outfilename.replace("SURV", "PPI")
        if "SUR" in outfilename:
            outfilename = outfilename.replace("SUR", "PPI")

        return outfilename

    tick = time.time()
    radar = production_line(radar_file_name, sound_dir, figure_path, is_seapol)

    radar_start_date = netCDF4.num2date(radar.time['data'][0], radar.time['units'].replace("since", "since "))

    # Generate output file name.
    outfilename = os.path.basename(radar_file_name)
    if "cfrad" in outfilename:
        outfilename = correct_output_filename(outfilename)
    else:
        outfilename = "cfrad." + radar_start_date.strftime("%Y%m%d_%H%M%S") + ".nc"

    outfilename = os.path.join(outpath, outfilename)

    # Check if output file already exists.
    if os.path.isfile(outfilename):
        logger.error('Output file already exists for: %s.', outfilename)
        return None

    # Write results
    pyart.io.write_cfradial(outfilename, radar, format='NETCDF4')

    # Deleting all unwanted keys for gridded product.
    logger.info("Gridding started.")
    unwanted_keys = []
    goodkeys = ['corrected_differential_reflectivity', 'cross_correlation_ratio',
                'temperature', 'giangrande_differential_phase', 'giangrande_specific_differential_phase',
                'radar_echo_classification', 'radar_estimated_rain_rate', 'D0',
                'NW', 'corrected_reflectivity', 'velocity', 'region_dealias_velocity']
    for mykey in radar.fields.keys():
        if mykey not in goodkeys:
            unwanted_keys.append(mykey)
    for mykey in unwanted_keys:
        radar.fields.pop(mykey)

    try:
        # Gridding (and saving)
        gridding_codes.gridding_radar_150km(radar, radar_start_date, outpath=outpath_grid)
        gridding_codes.gridding_radar_70km(radar, radar_start_date, outpath=outpath_grid)
        logger.info('Gridding done.')
    except Exception:
        logging.error('Problem while gridding.')
        raise

    # Processing finished!
    logger.info('%s processed in  %0.2f s.', os.path.basename(radar_file_name), (time.time() - tick))

    return None


def plot_quicklook(radar, gatefilter, radar_date, figure_path):
    """
    Plot figure of old/new radar parameters for checking purpose.

    Parameters:
    ===========
        radar:
            Py-ART radar structure.
        gatefilter:
            The Gate filter.
        radar_date: datetime
            Datetime stucture of the radar data.
    """
    if figure_path is None:
        logger.error("No figure plotted.")
        return None
    # Extracting year and date.
    year = str(radar_date.year)
    datestr = radar_date.strftime("%Y%m%d")
    # Path for saving Figures.
    outfile_path = os.path.join(figure_path, year, datestr)

    # Checking if output directory exists. Creating them otherwise.
    if not os.path.isdir(os.path.join(figure_path, year)):
        try:
            os.mkdir(os.path.join(figure_path, year))
        except FileExistsError:
            pass
    if not os.path.isdir(outfile_path):
        try:
            os.mkdir(outfile_path)
        except FileExistsError:
            pass

    # Checking if figure already exists.
    outfile = radar_date.strftime("%Y%m%d_%H%M") + ".png"
    outfile = os.path.join(outfile_path, outfile)

    # Initializing figure.
    with pl.style.context('seaborn-paper'):
        gr = pyart.graph.RadarDisplay(radar)
        fig, the_ax = pl.subplots(5, 3, figsize=(12, 17), sharex=True, sharey=True)
        the_ax = the_ax.flatten()
        # Plotting reflectivity
        gr.plot_ppi('total_power', ax=the_ax[0])
        gr.plot_ppi('corrected_reflectivity', ax=the_ax[1], gatefilter=gatefilter)
        gr.plot_ppi('radar_echo_classification', ax=the_ax[2], gatefilter=gatefilter)

        gr.plot_ppi('differential_reflectivity', ax=the_ax[3])
        gr.plot_ppi('corrected_differential_reflectivity', ax=the_ax[4], gatefilter=gatefilter)
        # Seasons 0910: No RHOHV available.
        try:
            gr.plot_ppi('cross_correlation_ratio', ax=the_ax[5], norm=colors.LogNorm(vmin=0.5, vmax=1.05))
        except KeyError:
            pass

        gr.plot_ppi('differential_phase', ax=the_ax[6], vmin=-180, vmax=180, cmap='pyart_Wild25')
        gr.plot_ppi('corrected_differential_phase', ax=the_ax[7], vmin=-180, vmax=180, cmap='pyart_Wild25')
        gr.plot_ppi('giangrande_differential_phase', ax=the_ax[8], vmin=-180, vmax=180, cmap='pyart_Wild25')

        gr.plot_ppi('giangrande_specific_differential_phase', ax=the_ax[9], vmin=-2, vmax=5, cmap='pyart_Theodore16')
        try:
            gr.plot_ppi('velocity', ax=the_ax[10], cmap=pyart.graph.cm.NWSVel, vmin=-30, vmax=30)
            gr.plot_ppi('region_dealias_velocity', ax=the_ax[11], gatefilter=gatefilter,
                        cmap=pyart.graph.cm.NWSVel, vmin=-30, vmax=30)
        except KeyError:
            try:
                gr.plot_ppi('VRADH', ax=the_ax[10], cmap=pyart.graph.cm.NWSVel, vmin=-30, vmax=30)
                gr.plot_ppi('WRADH', ax=the_ax[11], gatefilter=gatefilter,
                            cmap=pyart.graph.cm.NWSVel, vmin=-30, vmax=30)
            except Exception:
                pass

        gr.plot_ppi('D0', ax=the_ax[12], gatefilter=gatefilter, cmap='GnBu', vmin=0, vmax=2)
        gr.plot_ppi('NW', ax=the_ax[13], gatefilter=gatefilter, cmap='cubehelix', vmin=0, vmax=8)
        gr.plot_ppi('radar_estimated_rain_rate', ax=the_ax[14], gatefilter=gatefilter)

        for ax_sl in the_ax:
            gr.plot_range_rings([50, 100, 150], ax=ax_sl)
            ax_sl.set_aspect(1)
            ax_sl.set_xlim(-150, 150)
            ax_sl.set_ylim(-150, 150)

        pl.tight_layout()
        pl.savefig(outfile)  # Saving figure.
        fig.clf()  # Clear figure
        pl.close()  # Release memory
    del gr  # Releasing memory

    return None


def production_line(radar_file_name, sound_dir, figure_path=None, is_seapol=False):
    """
    Production line for correcting and estimating CPOL data radar parameters.
    The naming convention for these parameters is assumed to be DBZ, ZDR, VEL,
    PHIDP, KDP, SNR, RHOHV, and NCP. KDP, NCP, and SNR are optional and can be
    recalculated.

    Parameters:
    ===========
        radar_file_name: str
            Name of the input radar file.
        sound_dir: str
            Path to radiosounding directory.
        figure_path: str
            Path for saving figures.

    Returns:
    ========
        radar: Object
            Py-ART radar structure.

    PLAN:
    =====
        02/ Generate output file name. Check if output file already exists.
        03/ Read input radar file.
        04/ Check if radar file OK (no problem with azimuth and reflectivity).
        05/ Get radar date.
        06/ Check if NCP field exists (creating a fake one if it doesn't)
        07/ Check if RHOHV field exists (creating a fake one if it doesn't)
        08/ Compute SNR and temperature using radiosoundings.
        09/ Correct RHOHV using Ryzhkov algorithm.
        10/ Create gatefilter (remove noise and incorrect data).
        11/ Correct ZDR using Ryzhkov algorithm.
        12/ Process and unfold raw PHIDP using wradlib and Vulpiani algorithm.
        13/ Compute Giangrande's PHIDP using pyart.
        14/ Unfold velocity using pyart.
        15/ Compute attenuation for ZH
        16/ Compute attenuation for ZDR
        17/ Estimate Hydrometeors classification using csu toolbox.
        18/ Estimate Rainfall rate using csu toolbox.
        19/ Estimate DSD retrieval using csu toolbox.
        20/ Removing fake/temporary fieds.
        21/ Rename fields to pyart standard names.
        22/ Plotting figure quicklooks.
        23/ Hardcoding gatefilter.
    """
    # Start chronometer.
    start_time = time.time()

    # !!! READING THE RADAR !!!
    radar = radar_codes.read_radar(radar_file_name)

    # Correct SEAPOL PHIDP
    if is_seapol:
        phi = radar.fields['PHIDP']['data']
        radar.add_field_like("PHIDP", "PHIDP", -phi, replace_existing=True)
        print("SEAPOL PHIDP corrected.")

    # Check if radar reflecitivity field is correct.
    if not radar_codes.check_reflectivity(radar):
        logger.error("MAJOR ERROR: %s reflectivity field is empty.", radar_file_name)
        return None

    if not radar_codes.check_azimuth(radar):
        logger.error("MAJOR ERROR: %s azimuth field is empty.", radar_file_name)
        return None

    # Getting radar's date and time.
    radar_start_date = netCDF4.num2date(radar.time['data'][0], radar.time['units'].replace("since", "since "))
    datestr = radar_start_date.strftime("%Y%m%d_%H%M")
    logger.info("%s read.", radar_file_name)
    radar.time['units'] = radar.time['units'].replace("since", "since ")

    # Correct Doppler velocity units.
    try:
        radar.fields['VEL']['units'] = "m/s"
        radar.fields['VEL']['standard_name'] = "radial_velocity"
        vel_missing = False
    except KeyError:
        vel_missing = True
        pass

    # Looking for RHOHV field
    # For CPOL, season 09/10, there are no RHOHV fields before March!!!!
    try:
        radar.fields['RHOHV']
        fake_rhohv = False  # Don't need to delete this field cause it's legit.
    except KeyError:
        # Creating a fake RHOHV field.
        rho = pyart.config.get_metadata('cross_correlation_ratio')
        rho['data'] = np.ones_like(radar.fields['DBZ']['data'])
        rho['description'] = "THIS FIELD IS FAKE. SHOULD BE REMOVED!"
        radar.add_field('RHOHV', rho)
        radar.add_field('RHOHV_CORR', rho)
        fake_rhohv = True  # We delete this fake field later.

    if fake_rhohv:
        radar.metadata['debug_info'] = 'RHOHV field does not exist in RAW data. I had to use a fake RHOHV.'
        logger.critical("RHOHV field not found, creating a fake RHOHV")

    # Compute SNR and extract radiosounding temperature.
    try:
        height, temperature, snr = radar_codes.snr_and_sounding(radar, radar_start_date, sound_dir)
        radar.add_field('temperature', temperature, replace_existing=True)
        radar.add_field('height', height, replace_existing=True)
    except ValueError:
        traceback.print_exc()
        logger.error("Impossible to compute SNR")
        return None

    # Looking for SNR
    try:
        radar.fields['SNR']
        logger.info('SNR already exists.')
    except KeyError:
        radar.add_field('SNR', snr, replace_existing=True)
        logger.info('SNR calculated.')

    # Correct RHOHV
    if not fake_rhohv:
        rho_corr = radar_codes.correct_rhohv(radar)
        radar.add_field_like('RHOHV', 'RHOHV_CORR', rho_corr, replace_existing=True)
        logger.info('RHOHV corrected.')

    # Looking for NCP field
    try:
        radar.fields['NCP']
        fake_ncp = False
    except KeyError:
        # Creating a fake NCP field.
        ncp = pyart.config.get_metadata('normalized_coherent_power')
        emr2 = radar_codes._mask_rhohv(radar, "RHOHV_CORR", tight=True)
        ncp['data'] = emr2
        ncp['description'] = "THIS FIELD IS FAKE. SHOULD BE REMOVED!"
        radar.add_field('NCP', ncp)
        fake_ncp = True

    # Correct ZDR
    corr_zdr = radar_codes.correct_zdr(radar)
    radar.add_field_like('ZDR', 'ZDR_CORR', corr_zdr, replace_existing=True)

    # Get filter
    if fake_rhohv or vel_missing:
        gatefilter = radar_codes.do_gatefilter(radar, rhohv_name='RHOHV_CORR', is_rhohv_fake=fake_rhohv)
    else:
        gatefilter = radar_codes.do_wrd_gatefilter(radar)
    logger.info('Filter initialized.')

    # Unfold PHIDP:
    phi_unfold = radar_codes.unfold_raw_phidp(radar, gatefilter)
    radar.add_field_like("PHIDP", "PHI_UNF", phi_unfold, replace_existing=True)
    logger.info('Raw PHIDP unfolded.')

    # Bringi unfolding.
    phimeta, kdpmeta = radar_codes.phidp_bringi(radar, gatefilter, unfold_phidp_name="PHI_UNF")
    radar.add_field('PHIDP_BRINGI', phimeta, replace_existing=True)
    radar.add_field('KDP_BRINGI', kdpmeta, replace_existing=True)
    radar.fields['PHIDP_BRINGI']['long_name'] = "bringi_corrected_differential_phase"
    radar.fields['KDP_BRINGI']['long_name'] = "bringi_corrected_specific_differential_phase"
    logger.info('KDP/PHIDP Bringi estimated.')

    # Correct spider webs on phidp.
    phidp = radar_codes.fix_phidp_from_kdp(radar, gatefilter)
    radar.add_field_like("PHIDP", "PHI_CORR", phidp, replace_existing=True)
    logger.info('PHIDP spider webs removed.')

    # Giangrande PHIDP/KDP
    phidp_gg, kdp_gg = radar_codes.phidp_giangrande(radar, gatefilter, phidp_field='PHI_CORR')
    radar.add_field('PHIDP_GG', phidp_gg, replace_existing=True)
    radar.add_field('KDP_GG', kdp_gg, replace_existing=True)
    radar.fields['PHIDP_GG']['long_name'] = "corrected_differential_phase"
    radar.fields['KDP_GG']['long_name'] = "corrected_specific_differential_phase"
    logger.info('KDP/PHIDP Giangrande estimated.')

    # Unfold VELOCITY
    # This function will check if a 'VEL_CORR' field exists anyway.
    try:
        radar.fields['VEL']
        vdop_unfold = radar_codes.unfold_velocity(radar, gatefilter, bobby_params=False, vel_name='VEL')
        radar.add_field('VEL_UNFOLDED', vdop_unfold, replace_existing=True)
        logger.info('Doppler velocity unfolded.')
    except KeyError:
        logger.info("No velocity field found.")
        pass
    except TypeError:
        print("Problem with velocity.")
        pass

    # Correct Attenuation ZH
    atten_spec, zh_corr = atten_codes.correct_attenuation_zh(radar)
    radar.add_field('DBZ_CORR', zh_corr, replace_existing=True)
    radar.add_field('specific_attenuation_reflectivity', atten_spec, replace_existing=True)
    logger.info('Attenuation on reflectivity corrected.')

    # Correct Attenuation ZDR
    atten_spec_zdr, zdr_corr = atten_codes.correct_attenuation_zdr(radar)
    radar.add_field_like('ZDR', 'ZDR_CORR', zdr_corr, replace_existing=True)
    radar.add_field('specific_attenuation_differential_reflectivity', atten_spec_zdr,
                    replace_existing=True)
    logger.info('Attenuation on ZDR corrected.')

    # Hydrometeors classification
    hydro_class = hydro_codes.hydrometeor_classification(radar)
    radar.add_field('radar_echo_classification', hydro_class, replace_existing=True)
    logger.info('Hydrometeors classification estimated.')

    # Rainfall rate
    rainfall = hydro_codes.rainfall_rate(radar)
    radar.add_field("radar_estimated_rain_rate", rainfall)
    logger.info('Rainfall rate estimated.')

    # DSD retrieval
    nw_dict, d0_dict = hydro_codes.dsd_retrieval(radar)
    radar.add_field("D0", d0_dict)
    radar.add_field("NW", nw_dict)
    logger.info('DSD estimated.')

    # Removing fake and useless fields.
    if fake_ncp:
        radar.fields.pop('NCP')

    if fake_rhohv:
        radar.fields.pop("RHOHV")
        radar.fields.pop("RHOHV_CORR")

    # Rename fields to pyart defaults.
    radar = radar_codes.rename_radar_fields(radar)

    # Remove obsolete fields:
    try:
        radar.fields['Refl']
        radar.fields.pop('Refl')
        logger.info('Obsolete field Refl removed.')
    except KeyError:
        pass

    # Treatment is finished!
    end_time = time.time()
    logger.info("Treatment for %s done in %0.2f seconds.", os.path.basename(radar_file_name),
                (end_time - start_time))

    # Plot check figure.
    logger.info('Plotting figure')
    try:
        plot_quicklook(radar, gatefilter, radar_start_date, figure_path)
    except Exception:
        logger.exception("Problem while trying to plot figure.")
    figure_time = time.time()
    logger.info('Figure saved in %0.2fs.', (figure_time - end_time))

    # Hardcode mask
    for mykey in radar.fields:
        if mykey in ['temperature', 'height', 'signal_to_noise_ratio', "differential_reflectivity",
                     'normalized_coherent_power', 'spectrum_width', 'total_power', "velocity",
                     'corrected_differential_phase', 'corrected_specific_differential_phase',
                     "differential_phase", "raw_unfolded_differential_phase", "bringi_differential_phase",
                     "giangrande_differential_phase", "specific_differential_phase", "bringi_specific_differential_phase",
                     "giangrande_specific_differential_phase", "VRADH", "VRADV", "WRADH", "WRADV"]:
            # Virgin fields that are left untouch.
            continue
        else:
            try:
                radar.fields[mykey]['data'] = radar_codes.filter_hardcoding(radar.fields[mykey]['data'], gatefilter)
            except KeyError:
                continue
    logger.info('Hardcoding gatefilter to Fields done.')

    return radar
