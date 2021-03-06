# -*- coding: utf-8 -*-

"""
a-Al2O3.py

script for wg_disp, my adaptation of MPB waveguide dispersion code written
by Ryan Hamerly.

models amorphous alumina waveguide dispersion as a function of wavelength and
several geometric parameters

@author: dodd
"""


import numpy as np
from wg_disp import collect_wgparams_sweep, data_dir, n_proc_def
from instrumental import u


params = {'w_top_list': np.linspace(300,1500,9) * u.nm,
         'λ_list': np.linspace(0.32,1.8,20)*u.um,
         'λ_factor_list': np.array([1,0.95,1.05]),
         'θ_list': np.array([0,20]), # sidewall internal angle at top of core, degrees
         't_core_list': np.array([200,400,600,800,1000]) * u.nm,  # core thickness
         't_etch': 200 * u.nm,  # partial (or complete) etch depth
         'mat_core': 'Alumina',
         'mat_clad': 'SiO2',
         'mat_subs': None,
         'Xgrid': 4, # x lattice vector
         'Ygrid': 4, # y lattice vector
         'n_points': 32, # number of k-points simulated
         'n_bands': 4, # number of bands simulated
         'res': 64, # real-space resolution
         'edge_gap': 0.5, # μm, gap between non-background objects that would normally extend to infinity in x or y and unit-cell edge, to avoid finding modes in substrates, slabs, etc.
 }

# collect_wgparams_sweep(params,
#                         sweep_name='Al2O3_SiO2',
#                         n_proc=n_proc_def,
#                         data_dir=data_dir,
#                         verbose=True,
#                         return_data=False,
                        # )

# params_air = params.copy()
# params_air['mat_clad'] = 'Air'
#
# restart_sweep_dir = '/homes/dodd/data/wgparams_sweep_Al2O3_Air_2020_03_04_01_48_15'
#
# collect_wgparams_sweep(params_air,
#                         sweep_name='Al2O3_Air',
#                         n_proc=n_proc_def,
#                         sweep_dir=restart_sweep_dir,
#                         data_dir=data_dir,
#                         verbose=True,
#                         return_data=False,
#                         )
#
# params_mgf2 = params.copy()
# params_mgf2['mat_clad'] = 'MgF2'
#
#
# collect_wgparams_sweep(params_mgf2,
#                         sweep_name='Al2O3_MgF2',
#                         n_proc=n_proc_def,
#                         data_dir=data_dir,
#                         verbose=True,
#                         return_data=False,
#                         )

# params_sio2_subs = params.copy()
# params_sio2_subs['mat_clad'] = 'Air'
# params_sio2_subs['mat_subs'] = 'SiO2'
# # params_sio2_subs['Xgrid'] = 6
# # params_sio2_subs['Ygrid'] = 6

# # restart_sweep_dir = None
# restart_sweep_dir = '/homes/dodd/data/wg_disp/wgparams_sweep_Al2O3_SubsSiO2_2020_03_10_14_03_08'

# collect_wgparams_sweep(params_sio2_subs,
#                         sweep_name='Al2O3_SubsSiO2',
#                         n_proc=n_proc_def,
#                         sweep_dir=restart_sweep_dir,
#                         data_dir=data_dir,
#                         verbose=True,
#                         return_data=False,
#                         )

params_mgf2_subs = params.copy()
params_mgf2_subs['mat_clad'] = 'Air'
params_mgf2_subs['mat_subs'] = 'MgF2'
# params_mgf2_subs['Xgrid'] = 6
# params_mgf2_subs['Ygrid'] = 6
restart_sweep_dir = '/homes/dodd/data/wg_disp/wgparams_sweep_Al2O3_SubsMgF2_2020_03_11_15_01_45'
collect_wgparams_sweep(params_mgf2_subs,
                        sweep_name='Al2O3_SubsMgF2',
                        n_proc=n_proc_def,
                        sweep_dir=restart_sweep_dir,
                        data_dir=data_dir,
                        verbose=True,
                        return_data=False,
                        )
