# -*- coding: utf-8 -*-

"""
wg_disp.py

Code for modeling waveguide dispersion using MPB,
adapted from code written by Ryan Hamerly.

@author: dodd
"""

from pathlib import Path
from multiprocessing import Pool
import socket
import pickle
from datetime import datetime
from time import time
from os import path, makedirs, chmod
import os
import psutil
import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
import meep as mp
import meep.materials as mats
from meep import mpb
import meeputils as mu
from wurlitzer import pipes, STDOUT
from io import StringIO
# from instrumental import u
u = mu.u


###
home = str( Path.home() )
hostname = socket.gethostname()
if hostname=='dodd-laptop':
    data_dir = home+'/data/wg_disp/'
    n_proc_def = 12
    nice_level_def = 19 # Unix, lowest priority is 19
elif hostname=='hogwarts4':
    data_dir = home+'/data/wg_disp/'
    n_proc_def = 32
    nice_level_def = 19 # Unix, lowest priority is 19
else: # assume I'm on a MTL server or something
    data_dir = home+'/data/wg_disp/'
    n_proc_def = 32
    nice_level_def = 19 # Unix, lowest priority is 19

###

# set to lowest priority, this is windows only, on Unix use ps.nice(19)
def limit_cpu():
    """
    Initializer for Pool worker processes to make sure they get out of the way
    when other users of shared machines start new processes.
    Based on:
    https://stackoverflow.com/questions/42103367/limit-total-cpu-usage-in-python-multiprocessing
    """
    "is called at every process start"
    p = psutil.Process(os.getpid())
    # p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS) # windows
    p.nice(nice_level_def) # Unix, lowest priority is 19

def get_intersect(a1, a2, b1, b2):
    """
    Returns the point of intersection of the lines passing through a2,a1 and b2,b1.
    a1: [x, y] a point on the first line
    a2: [x, y] another point on the first line
    b1: [x, y] a point on the second line
    b2: [x, y] another point on the second line
    """
    s = np.vstack([a1,a2,b1,b2])        # s for stacked
    h = np.hstack((s, np.ones((4, 1)))) # h for homogeneous
    l1 = np.cross(h[0], h[1])           # get first line
    l2 = np.cross(h[2], h[3])           # get second line
    x, y, z = np.cross(l1, l2)          # point of intersection
    if z == 0:                          # lines are parallel
        return (float('inf'), float('inf'))
    return (x/z, y/z)

def conformal_verts(obj,t):
    """
    Returns a list of vertices for a "conformal" meep Prism object around the meep/mpb geometry
    object obj with thickness t

    inputs:
    obj:  meep/mpb geometry object
    t:    conformal layer thickness in um (float)

    outputs:
    conformal_vertices:  list of meep.Vector3 vector objects
    """
    verts = obj.vertices
    for vind, vv in enumerate(verts):
        verts[vind] = mp.Vector3(vv[0],vv[1],0.0)
    edges = [verts[ind+1]-verts[ind] for ind in range(len(verts)-1)] + [verts[0]-verts[-1],]
    edge_centers = [verts[ind]+edges[ind]/2. for ind in range(len(verts))]
    edge_normals = [ mp.Vector3(0,0,1).cross(e).unit() for e in edges ]
    ts = [t for v in verts] # * np.ones(len(verts))
    for ind in range(len(verts)):
        # if mp.is_point_in_object(edge_centers[ind] + edge_normals[ind]*0.001, obj):
            # print(f'reversing edge normal {ind}')
#             edge_normals[ind] = edge_normals[ind] * -1
        if edge_normals[ind][1] < 0:
            ts[ind] = 0.
    vrts = [(verts[ind]+ts[ind]*edge_normals[ind],verts[ind+1]+ts[ind]*edge_normals[ind]) for ind in range(len(verts)-1)] + [( verts[-1]+ts[-1]*edge_normals[-1], verts[0]+ts[-1]*edge_normals[-1] ),]
    conformal_verts_init = [ get_intersect((vrts[ind][0][0],vrts[ind][0][1]),
                                      (vrts[ind][1][0],vrts[ind][1][1]),
                                      (vrts[ind+1][0][0],vrts[ind+1][0][1]),
                                      (vrts[ind+1][1][0],vrts[ind+1][1][1])) for ind in range(len(verts)-1)]
    conformal_verts_init += [ get_intersect((vrts[-1][0][0],vrts[-1][0][1]),
                                      (vrts[-1][1][0],vrts[-1][1][1]),
                                      (vrts[0][0][0],vrts[0][0][1]),
                                      (vrts[0][1][0],vrts[0][1][1])), ]
    conformal_verts_final = [mp.Vector3(v[0],v[1],0.) for v in conformal_verts_init]
    return conformal_verts_final

def get_wgparams(w_top,θ,t_core,t_etch,lam,mat_core,mat_clad,Xgrid,Ygrid,n_points,mat_subs=None,n_bands=4,res=32,edge_gap=1,do_func=None,):
    """
    Solves for mode, n_eff and ng_eff at some wavelength lam for a set of
    geometry and material parameters.
    """
    # convert all input parameters with length units to μm
    w_top = w_top.to(u.um).m
    t_core = t_core.to(u.um).m
    t_etch = t_etch.to(u.um).m
    lam = lam.to(u.um).m

    # get phase and group indices for these materials at this wavelength
    n_core = mu.get_index(mat_core, lam); ng_core = mu.get_ng(mat_core, lam)
    n_clad = mu.get_index(mat_clad, lam); ng_clad = mu.get_ng(mat_clad, lam)
    med_core = mp.Medium(index=n_core); med_clad = mp.Medium(index=n_clad)

    # Set up geometry.
    k_points = mp.interpolate(n_points, [mp.Vector3(0.05, 0, 0), mp.Vector3(0.05*n_points, 0, 0)])
    lat = mp.Lattice(size=mp.Vector3(Xgrid, Ygrid,0))
    dx_base = np.tan(np.deg2rad(θ)) * t_etch
    ### hardcode conformal layer temporarily! ###
    any_conformal = True
    t_ald = 0.5
    mat_ald = 'SiO2'
    n_ald = mu.get_index(mat_ald, lam); ng_ald = mu.get_ng(mat_ald, lam)
    med_ald = mp.Medium(index=n_ald)
    ################################################
    verts_core = [  mp.Vector3(-w_top/2., t_etch/2,  0,  ),
                mp.Vector3( w_top/2., t_etch/2,  0, ),
                mp.Vector3(w_top/2+dx_base, -t_etch/2,  0,  ),
                mp.Vector3( -w_top/2-dx_base, -t_etch/2,  0, ),
             ]

    core = mp.Prism(verts_core,
                axis = mp.Vector3(0,0,1),
                height=mp.inf,
                center=mp.Vector3(),
                material=med_core,
               )

    if any_conformal:
        ald_core = mp.Prism(conformal_verts(core,t_ald), height=mp.inf, material=med_ald)
        ald_slab = mp.Block(size=mp.Vector3(Xgrid-edge_gap, t_ald , mp.inf), center=mp.Vector3(0, (-t_etch/2+t_ald/2), 0), material=med_ald)

    if t_etch<t_core:   # partial etch
        slab = mp.Block(size=mp.Vector3(Xgrid-edge_gap,
                                        t_core-t_etch,
                                        mp.inf,),
                        center=mp.Vector3(0,
                                          -t_core/2,
                                          0,),
                        material=med_core,
                       )
        if any_conformal:
            geom = [ald_core,
                    ald_slab,
                    core,
                    slab,
                    ]
        else:
            geom = [core,
                    slab,
                    ]
    # print('adding slab block')
    else:
        if any_conformal:
            geom = [ald_core,
                    ald_slab,
                    core,
                    ]
        else:
            geom = [core,]
    if mat_subs:
        n_subs = mu.get_index(mat_subs, lam)
        ng_subs = mu.get_ng(mat_subs, lam)
        med_subs = mp.Medium(index=n_subs)
        t_subs = Ygrid/2 - edge_gap/2 -t_core+t_etch/2
        subs = mp.Block(size=mp.Vector3(Xgrid-edge_gap, t_subs , mp.inf), center=mp.Vector3(0, -t_core+t_etch/2-t_subs/2., 0),material=med_subs)
        geom += [subs,]
        n_guess = n_core #(n_subs+n_core)/2.
        n_min = n_clad # n_subs
    else:
        n_guess = n_core #(n_clad+n_core)/2.
        n_min = n_clad
    # verts_core = [mp.Vector3(-w_top/2.,t_core),
    #         mp.Vector3(w_top/2.,t_core),
    #         mp.Vector3(w_top/2+dx_base,t_core-t_etch),
    #         mp.Vector3(-w_top/2-dx_base,t_core-t_etch),
    #        ]
    # core = mp.Prism(verts_core, height=mp.inf, material=med_core)
    # if t_etch<t_core:   # partial etch
    #     slab = mp.Block(size=mp.Vector3(Xgrid-edge_gap, t_core-t_etch , mp.inf), center=mp.Vector3(0, (t_core-t_etch), 0),material=med_core)
    #     geom = [core,
    #             slab,
    #             ]
    #     # print('adding slab block')
    # else:
    #     geom = [core,]
    # if mat_subs:
    #     n_subs = mu.get_index(mat_subs, lam)
    #     ng_subs = mu.get_ng(mat_subs, lam)
    #     med_subs = mp.Medium(index=n_subs)
    #     subs = mp.Block(size=mp.Vector3(Xgrid-edge_gap, (Ygrid-edge_gap)/2. , mp.inf), center=mp.Vector3(0, -(Ygrid-edge_gap)/4., 0),material=med_subs)
    #     geom += [subs,]
    #     n_guess = (n_subs+n_core)/2.
    #     n_min = n_clad # n_subs
    # else:
    #     n_guess = (n_clad+n_core)/2.
    #     n_min = n_clad

    ms = mpb.ModeSolver(geometry_lattice=lat,
                        geometry=[],
                        k_points=k_points,
                        resolution=res,
                        num_bands=n_bands,
                        default_material=med_clad)

    ms.geometry = geom
    ms.default_material = med_clad

    blackhole = StringIO()
    with pipes(stdout=blackhole, stderr=STDOUT):
        ms.init_params(mp.NO_PARITY, False)
        eps = np.array(ms.get_epsilon())
    # mat_core_mask = (eps - n_clad ** 2) / (n_core ** 2 - n_clad ** 2)
    mat_core_mask = (np.abs(np.sqrt(eps) - n_core ) / n_core) < 0.01
    if mat_subs:
        mat_subs_mask = (np.abs(np.sqrt(eps) - n_subs ) / n_subs) < 0.01

    out = {}

    def get_fieldprops(ms, band):
        if (out != {}):
            return
        e = np.array(ms.get_efield(band))
        eps_ei2 = eps.reshape(eps.shape+(1,)) * np.abs(e[:, :, 0, :]**2)
        ei_pwr = eps_ei2.sum(axis=(0, 1))
        if (ei_pwr[0] > ei_pwr[1]):
            print ("TE mode!\n")
            # Calculate eps |E|^2.  Then get power in the core material, and distribution along x.
            # Get n_g.  Adjust by material disperision factor (n_{g,mat}/n_{mat}), weighted by eps |E|^2 above.
            epwr = eps_ei2.sum(-1) / eps_ei2.sum()
            p_mat_core_x = (epwr * mat_core_mask).sum(-1)
            p_mat_core = p_mat_core_x.sum()
            p_x = epwr.sum(-1)
            p_y = epwr.sum(0)
            ng_geom = 1 / ms.compute_one_group_velocity_component(mp.Vector3(0, 0, 1), band)
            if mat_subs:
                p_mat_subs = (epwr * mat_subs_mask).sum()
                ng = ng_geom * ( p_mat_core * (ng_core / n_core) + p_mat_subs * (ng_subs / n_subs) + (1 - p_mat_core - p_mat_subs) * (ng_clad / n_clad))
            else:
                ng = ng_geom * (p_mat_core * (ng_core / n_core) + (1 - p_mat_core) * (ng_clad / n_clad))

            # Output various stuff.
            out['band'] = band
            out['ng'] = ng
            out['ng_geom'] = ng_geom
            out['p_mat_core'] = p_mat_core
            out['p_mat_core_x'] = p_mat_core_x
            out['p_x'] = p_x
            out['p_y'] = p_y

            if (do_func != None):
                do_func(out, ms, band)

    with pipes(stdout=blackhole, stderr=STDOUT):
        k = ms.find_k(mp.NO_PARITY,             # parity (meep parity object)
                      1/lam,                    # ω at which to solve for k
                      1,                        # band_min (find k(ω) for bands
                      n_bands,                        # band_max  band_min:band_max)
                      mp.Vector3(0, 0, 1),      # k direction to search
                      1e-4,                     # fractional k error tolerance
                      n_guess/lam,              # kmag_guess, |k| estimate
                      n_min/lam,                # kmag_min (find k in range
                      n_core/lam,               # kmag_max  kmag_min:kmag_max)
                      get_fieldprops,           # band_func to be run on soln.
                      )

    if (out == {}):
        print ("TE mode not found.")
        return out

    out['neff'] = k[out['band']-1] / (1 / lam)

    print ("lam = {:.2f}, w_top = {:.2f}, θ = {:.2f}, t_core = {:.2f}, t_etch = {:.2f}, neff = {:.3f}, ng = {:.3f}, "
           "p_mat_core = {:.2f}".format(lam, w_top, θ, t_core, t_etch, out['neff'], out['ng'], out['p_mat_core'],))
    return out

def get_wgparams_parallel(p):
    # check to see if this simulation has already been run and load old result
    # if so. this allows large sweeps that crash in the middle to be restarted
    # without changing the code and without re-running completed sims.
    fpath = path.normpath(path.join(p['sweep_dir'],p['fname']))
    if path.exists(fpath):
        with open(fpath,'rb') as f:
            out = pickle.load(f)
    else:
        try:
            out = get_wgparams(p['w_top'],
                                p['θ'],
                                p['t_core'],
                                p['t_etch'],
                                p['λ'],
                                p['mat_core'],
                                p['mat_clad'],
                                p['Xgrid'],
                                p['Ygrid'],
                                p['n_points'],
                                p['mat_subs'],
                                p['n_bands'],
                                p['res'],
                                p['edge_gap'],
                                )
        except:
            print('MPB error')
            out = {}
        out.update(p)
        with open(fpath,'wb') as f:
                pickle.dump(out,f)
    return out

def collect_wgparams_sweep(params,sweep_name='test',n_proc=n_proc_def,data_dir=data_dir,sweep_dir=False,verbose=True,return_data=False):
    """
    Find waveguide dispersion using mpb
    """
    if not sweep_dir:
        timestamp_str = datetime.strftime(datetime.now(),'%Y_%m_%d_%H_%M_%S')
        sweep_dir_name = 'wgparams_sweep_' + sweep_name + '_' + timestamp_str
        sweep_dir = path.normpath(path.join(data_dir,sweep_dir_name))
        makedirs(sweep_dir)
    sweep_data_fname = 'data.npy'
    sweep_data_fpath = path.join(sweep_dir,sweep_data_fname)
    mfname = 'metadata.dat'
    mfpath = path.join(sweep_dir,mfname)
    # add a couple other things to kwargs and save as a metadata dict
    metadata = params.copy()
    nλ = len(params['λ_list'])
    metadata['nλ'] = nλ
    nw = len(params['w_top_list'])
    metadata['nw'] = nw
    nfact = len(params['λ_factor_list'])
    metadata['nfact'] = nfact
    nt_core = len(params['t_core_list'])
    metadata['nt_core'] = nt_core
    nθ = len(params['θ_list'])
    metadata['nθ'] = nθ

    metadata['sweep_dir'] = sweep_dir
    t_start = time()
    start_timestamp_str = datetime.strftime(datetime.now(),'%Y_%m_%d_%H_%M_%S')
    metadata['t_start'] = start_timestamp_str
    # print(metadata)
    with open(mfpath, 'wb') as f:
        pickle.dump(metadata,f)
    params_list = []
    for (m, λ_factor) in enumerate(params['λ_factor_list']):
        for (i, λ0) in enumerate(params['λ_list']):
            for (j, ww) in enumerate(params['w_top_list']):
                for (k, ttc) in enumerate(params['t_core_list']):
                    for (l, θθ) in enumerate(params['θ_list']):
                        p = metadata.copy()
                        p['fname'] = f'{m}_{i}_{j}_{k}_{l}.dat'
                        p['m'] = m
                        p['j'] = j
                        p['i'] = i
                        p['k'] = k
                        p['l'] = l
                        p['λ'] = λ0 * λ_factor
                        p['w_top'] = ww
                        p['t_core'] = ttc
                        p['t_etch'] = ttc
                        p['θ'] = θθ
                        params_list += [p,]
    with Pool(n_proc,limit_cpu) as pool:
        out_list = pool.map(get_wgparams_parallel,params_list)
    # record stop time
    stop_timestamp_str = datetime.strftime(datetime.now(),'%Y_%m_%d_%H_%M_%S')
    t_elapsed_sec = time()-t_start
    if verbose:
        print('wgparams sweep finished at ' + stop_timestamp_str)
    metadata['t_stop'] = stop_timestamp_str
    metadata['t_elapsed_sec'] = t_elapsed_sec
    with open(mfpath, 'wb') as f:
        pickle.dump(metadata,f)

    # compile output dataset
    px_len = params['Xgrid'] * params['res']
    py_len = params['Ygrid'] * params['res']
    neff_list = np.zeros([nfact, nλ, nw, nt_core, nθ], dtype=np.float)
    ng_list   = np.zeros([nfact, nλ, nw, nt_core, nθ], dtype=np.float)
    ng_geom_list   = np.zeros([nfact, nλ, nw, nt_core, nθ], dtype=np.float)
    p_mat_core_list  = np.zeros([nfact, nλ, nw, nt_core, nθ], dtype=np.float)
    p_mat_core_x_list  = np.zeros([nfact, nλ, nw, nt_core, nθ, px_len], dtype=np.float)
    p_x_list  = np.zeros([nfact, nλ, nw, nt_core, nθ, px_len], dtype=np.float)
    p_y_list  = np.zeros([nfact, nλ, nw, nt_core, nθ, py_len], dtype=np.float)

    for out_ind in range(len(out_list)):
        out = out_list[out_ind]
        m = out['m']
        i = out['i']
        j = out['j']
        k = out['k']
        l = out['l']
        inds = m,i,j,k,l
        if 'neff' in out.keys():
            neff_list[inds] = out['neff']
            ng_list[inds] = out['ng']
            ng_geom_list[inds] = out['ng_geom']
            p_mat_core_list[inds] = out['p_mat_core']
            p_mat_core_x_list[inds] = out['p_mat_core_x']
            p_x_list[inds] = out['p_x']
            p_y_list[inds] = out['p_y']
        else:
            neff_list[inds] = np.nan
            ng_list[inds] = np.nan
            ng_geom_list[inds] = np.nan
            p_mat_core_list[inds] = np.nan
            # p_mat_core_x_list[inds] = np.nan
            # p_x_list[inds] = np.nan
            # p_y_list[inds] = np.nan


    np.save(sweep_data_fpath,
            {"neff": neff_list,
             "ng": ng_list,
             "ng_geom": ng_geom_list,
             "p_mat_core": p_mat_core_list,
             "p_mat_core_x": p_mat_core_x_list,
             "p_x": p_x_list,
             "p_y": p_y_list,
             }
            )

def _multivalued_params(params,verbose=True):
        multivalued_params = OrderedDict([])
        for k,v in params.items():
            if not isinstance(v,(list,str,dict,OrderedDict,bool)):
                if isinstance(Q_(v).m,np.ndarray):
                    multivalued_params[k]=v
                    if verbose:
                        l = len(Q_(v).m)
                        print('detected {:}-valued parameter: '.format(l) + k + ':')
                        print(v)
        return multivalued_params

def _param_index_combinations(multivalued_params):
    mvp = multivalued_params
    param_indices = [range(len(Q_(v).m)) for k,v in mvp.items()]
    param_index_combinations = list(itertools.product(*param_indices))
    return param_index_combinations

def _param_set_list(params,multivalued_params,param_index_combinations):
    mvp = multivalued_params
    pics = param_index_combinations
    param_set_list = [deepcopy(params) for pic in pics]
    for jj,pic in enumerate(pics):
        for ii,(key,val_list) in enumerate(mvp.items()):
            param_set_list[jj][key] = val_list[pic[ii]]
    return param_set_list
