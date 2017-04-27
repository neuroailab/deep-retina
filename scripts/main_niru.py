"""
Niru main script
"""

from __future__ import absolute_import
from deepretina.models import functional, sequential, convnet, ln, generalizedconvnet, bn_cnn
from deepretina.core import train
from deepretina.experiments import Experiment, _loadexpt_h5
from deepretina.io import KerasMonitor, Monitor, main_wrapper
from deepretina.glms import GLM
from deepretina.utils import cutout_indices
import numpy as np
from keras.optimizers import RMSprop
from pyret import filtertools as ft


@main_wrapper
def fit_cutout(cell, train_stimuli, exptdate, filtersize, l2=1e-3, load_fraction=1.0, readme=None):
    """Fits a LN model on a cutout stimulus using keras"""

    history = 40
    batchsize = 5000

    # load experiment data
    test_stimuli = ['whitenoise', 'naturalscene']
    data = Experiment(exptdate, [cell], train_stimuli, test_stimuli, history, batchsize, nskip=6000)

    # subselect
    data.subselect(load_fraction)

    # get the spatial center of the STA, and the cutout indices
    cellname = 'cell{:02d}'.format(cell + 1)
    sta = np.array(_loadexpt_h5(exptdate, 'whitenoise')['stas'][cellname])
    sta_center = ft.get_ellipse(ft.decompose(sta)[0])[0]
    xi, yi = cutout_indices(sta_center, size=filtersize)

    # cutout the experiment
    data.cutout(xi, yi)
    xdim, ydim = data._train_data[train_stimuli[0]].X.shape[2:]

    # get the layers
    layers = ln((history, xdim, ydim), 1, weight_init='glorot_uniform', l2_reg=l2)

    # compile it
    model = sequential(layers, RMSprop(lr=1e-4), loss='poisson')

    # create a monitor
    monitor = KerasMonitor('ln_cutout', model, data, readme, save_every=20)

    # train
    train(model, data, monitor, num_epochs=25)

    return model


@main_wrapper
def fit_ln(cells, train_stimuli, exptdate, l2=1e-3, readme=None):
    """Fits an LN model using keras"""
    stim_shape = (40, 50, 50)
    ncells = len(cells)
    batchsize = 5000

    # get the layers
    layers = ln(stim_shape, ncells, weight_init='normal', l2_reg=l2)

    # compile it
    model = sequential(layers, RMSprop(lr=1e-4), loss='poisson')

    # load the STAs
    # stas = []
    # h5file = _loadexpt_h5(exptdate, train_stimuli[0])
    # for ci in cells:
    #     key = 'cell{:02}'.format(ci + 1)
    #     stas.append(np.array(h5file['stas'][key]).ravel())

    # specify the initial weights using the STAs
    # W = np.vstack(stas).T
    # b = np.zeros(W.shape[1])
    # model.layers[1].set_weights([W, b])

    # load experiment data
    test_stimuli = ['whitenoise', 'naturalscene']
    data = Experiment(exptdate, cells, train_stimuli, test_stimuli, stim_shape[0], batchsize, nskip=6000)

    # create a monitor
    monitor = KerasMonitor('ln', model, data, readme, save_every=20)

    # train
    train(model, data, monitor, num_epochs=30)

    return model


@main_wrapper
def fit_bncnn(cells, train_stimuli, exptdate, l2_reg=0.0, readme=None):
    stim_shape = (40, 50, 50)
    ncells = len(cells)
    bs = 5000

    model = functional(*bn_cnn(stim_shape, ncells, l2_reg=l2_reg), 'adam', loss='poisson')

    test_stimuli = ['whitenoise', 'naturalscene']
    data = Experiment(exptdate, cells, train_stimuli, test_stimuli, stim_shape[0], bs)

    # create a monitor to track progress
    monitor = KerasMonitor('bn_cnn', model, data, readme, save_every=25)
    # monitor = None

    # train
    train(model, data, monitor, num_epochs=75)
    return model


@main_wrapper
def fit_convnet(cells, train_stimuli, exptdate, nclip=0, readme=None):
    """Main script for fitting a convnet

    author: Niru Maheswaranathan
    """

    stim_shape = (40, 50, 50)
    ncells = len(cells)
    batchsize = 5000

    # get the convnet layers
    layers = convnet(stim_shape, ncells, num_filters=(8, 16),
                     filter_size=(15, 7), weight_init='normal',
                     l2_reg_weights=(0.01, 0.01, 0.01),
                     l1_reg_activity=(0.0, 0.0, 0.001),
                     dropout=(0.1, 0.0))

    # compile the keras model
    model = sequential(layers, 'adam', loss='poisson')

    # load experiment data
    test_stimuli = ['whitenoise', 'naturalscene']
    data = Experiment(exptdate, cells, train_stimuli, test_stimuli, stim_shape[0], batchsize, nskip=nclip)

    # create a monitor to track progress
    # monitor = KerasMonitor('convnet', model, data, readme, save_every=20)
    monitor = None

    # train
    train(model, data, monitor, num_epochs=50)

    return model


@main_wrapper
def fit_convconv(cells, train_stimuli, exptdate, readme=None):
    """Main script for fitting a multilayered convnet

    author: Niru Maheswaranathan
    """
    stim_shape = (40, 50, 50)
    ncells = len(cells)
    batchsize = 5000
    noise_sigma = 0.1

    # specify convolutional layers (nfilters, filtersize)
    # and regularization (l1, l2)
    convlayers = [(8, 15), (16, 7)]
    W_reg = [(0., 1e-3), (0., 1e-3)]
    act_reg = [(0., 0.), (0., 0.)]

    # get the convnet layers
    layers = multiconv(stim_shape, ncells, noise_sigma, convlayers, W_reg, act_reg)

    # compile the keras model
    model = sequential(layers, 'adam', loss='poisson')

    # load experiment data
    test_stimuli = ['whitenoise', 'naturalscene']
    data = Experiment(exptdate, cells, train_stimuli, test_stimuli, stim_shape[0], batchsize, nskip=6000)

    # create a monitor to track progress
    monitor = KerasMonitor('multilayered_convnet', model, data, readme, save_every=20)

    # train
    train(model, data, monitor, num_epochs=50)

    return model


@main_wrapper
def fit_genconv(cells, train_stimuli, exptdate, load_fraction=1.0, readme=None):
    """Fits a generalized convnet (based off of Lane's function)"""

    stim_shape = (40, 50, 50)
    ncells = len(cells)
    batchsize = 6000

    # get the convnet layers
    layers = generalizedconvnet(stim_shape, ncells,
                                architecture=('conv', 'noise', 'relu', 'conv', 'noise', 'relu', 'flatten', 'affine'),
                                num_filters=[8, -1, -1, 16], filter_sizes=[15, -1, -1, 7], weight_init='normal',
                                l2_reg=0.01, dropout=0.25, sigma=2.0)

    # compile the keras model
    model = sequential(layers, 'adam', loss='poisson')

    # load experiment data
    test_stimuli = ['whitenoise', 'naturalscene']
    data = Experiment(exptdate, cells, train_stimuli, test_stimuli, stim_shape[0], batchsize, nskip=6000)
    data.subselect(load_fraction)

    # create a monitor to track progress
    monitor = KerasMonitor('convnet', model, data, readme, save_every=20)

    # train
    train(model, data, monitor, num_epochs=100)

    return model


@main_wrapper
def fit_glm(cell, train_stimuli, exptdate, filtersize, l2, load_fraction=1.0, readme=None):
    """Main script for fitting a GLM

    author: Niru Maheswaranathan
    """
    batchsize = 5000
    history = 40

    # load experimental data
    test_stimuli = ['whitenoise', 'naturalscene']
    data = Experiment(exptdate, [cell], train_stimuli, test_stimuli, history, batchsize, nskip=6000)
    data.subselect(load_fraction)

    # get the spatial center of the STA, and the cutout indices
    cellname = 'cell{:02d}'.format(cell + 1)
    sta = np.array(_loadexpt_h5(exptdate, 'whitenoise')['stas'][cellname])
    try:
        sta_center = ft.get_ellipse(ft.decompose(sta)[0])[0]
        xi, yi = cutout_indices(sta_center, size=filtersize)
    except:
        return None

    # cutout the experiment
    data.cutout(xi, yi)
    xdim, ydim = data._train_data[train_stimuli[0]].X.shape[2:]

    # dimensions
    stim_shape = (history, xdim, ydim)
    coupling_history = 20

    # build the GLM
    model = GLM(stim_shape, coupling_history, 1, lr=1e-4, l2={'filter': l2[0], 'history': l2[1]})

    # create a monitor to track progress
    monitor = Monitor('GLM', model, data, readme, save_every=20)

    # train
    train(model, data, monitor, num_epochs=25)

    return model

if __name__ == '__main__':
    # 15-10-07
    # mdl = fit_bncnn([0, 1, 2, 3, 4], ['naturalscene'], '15-10-07')

    # 15-11-21a
    gc_151121a = [6, 10, 12, 13]
    # mdl = fit_convnet(gc_151121a, ['whitenoise'], '15-11-21a', nclip=6000)
    # mdl = fit_bncnn(gc_151121a, ['naturalscene'], '15-11-21a', description='naturalscene bn_cnn with l2reg')
    mdl = fit_bncnn(gc_151121a, ['whitenoise'], '15-11-21a', l2_reg=0.1, description='whitenoise bn_cnn with l2reg=0.1')
    mdl = fit_bncnn(gc_151121a, ['whitenoise'], '15-11-21a', l2_reg=0.5, description='whitenoise bn_cnn with l2reg=0.5')
    mdl = fit_bncnn(gc_151121a, ['whitenoise'], '15-11-21a', l2_reg=0.02, description='whitenoise bn_cnn with l2reg=0.02')

    # 15-11-21b
    # gc_151121b = [0, 1, 3, 4, 5, 8, 9, 13, 14, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25]
    # mdl = fit_convnet(gc_151121b, ['naturalscene'], '15-11-21b', nclip=6000)

    # 16-01-07
    # gc_160107 = [0, 2, 7, 10, 11, 12, 31]
    # mdl = fit_convnet(gc_160107, ['naturalscene'], '16-01-07', nclip=6000, description='16-10-07 naturalscene model (goodcells)')

    # 16-01-08
    # gc_160108 = [0, 3, 7, 9, 11]
    # mdl = fit_convnet(gc_160108, ['naturalscene'], '16-01-08', nclip=6000, description='16-10-08 naturalscene model (goodcells)')
