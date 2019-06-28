#!/usr/bin/env python
import logging
import os

import h5py
import numpy as np
import click

from os import path
from sys import stdout
from argparse import Namespace

from sklearn.manifold import TSNE
from sklearn.cluster import k_means

from .core import spectral_clustering, spectral_embedding
from .visualize import spray_visualize

logger = logging.getLogger(__name__)

def csints(arg):
    return [int(s) for s in arg.split(',')]

@click.group(chain=True)
@click.argument('data', type=click.Path())
@click.option('--overwrite/--no-overwrite', default=False)
@click.option('--modify/--no-modify', default=False)
@click.option('--log', type=click.File(), default=stdout)
@click.option('-v', '--verbose', count=True)
@click.pass_context
def main(ctx, data, overwrite, modify, log, verbose):
    logger.addHandler(logging.StreamHandler(log))
    logger.setLevel(logging.DEBUG if verbose > 0 else logging.INFO)

    defaults = {
        'data': data,
        'modify': modify,
        'overwrite': overwrite,
    }
    ctx.default_map = dict(zip(('embed', 'cluster', 'tsne'), (defaults,)*3))
    ctx.ensure_object(Namespace)

@main.command()
@click.argument('attribution', type=click.Path())
@click.option('--data', type=click.Path())
@click.option('--overwrite/--no-overwrite', default=False)
@click.option('--modify/--no-modify', default=False)
@click.option('--eigvals', type=int, default=32)
@click.option('--knn', type=int, default=10)
@click.pass_context
def embed(ctx, attribution, data, overwrite, modify, eigvals, knn):
    fout = data

    if not path.exists(fout) or modify:
        logger.info('Computing embedding: {}'.format(fout))
        with h5py.File(attribution, 'r') as fd:
            attr  = fd['attribution'][:]
            label = fd['label'][:]

        #attr  = attr.mean(1)
        shape = attr.shape
        attr = attr.reshape(shape[0], np.prod(shape[1:]))

        os.makedirs(path.dirname(fout), exist_ok=True)

        ew, ev = spectral_embedding(attr, knn, eigvals, precomputed=False)
        with h5py.File(fout, 'a') as fd:
            for key, val in zip(('eigenvalue', 'eigenvector'), (ew, ev)):
                if key in fd and overwrite:
                    del fd[key]
                fd[key] = val.astype('float32')
        ctx.obj.ev = ev
    else:
        logger.info('File exists, not overwriting embedding: {}'.format(fout))

@main.command()
@click.option('--data', type=click.Path())
@click.option('--output', type=click.Path())
@click.option('--overwrite/--no-overwrite', default=False)
@click.option('--modify/--no-modify', default=False)
@click.option('--computed/--loaded', default=True)
@click.option('--eigvals', type=int, default=8)
@click.option('--clusters', type=csints, default='2,3,4,5')
@click.pass_context
def cluster(ctx, data, output, overwrite, modify, computed, eigvals, clusters):
    fout = data if output is None else output

    if not path.exists(fout) or modify:
        logger.info('Computing clustering: {}'.format(fout))
        if computed and ('ev' in ctx.obj):
            ev = ctx.obj.ev
        else:
            try:
                with h5py.File(data, 'r') as fd:
                    ev = fd['eigenvector'][:]
            except KeyError:
                logger.error('Embedding must be either computed or already exist in data.')
                return

        llabels = []
        for k in clusters:
            _, lab, _ = k_means(ev[:, -eigvals:], k)
            llabels.append(lab.astype('uint8'))

        with h5py.File(fout, 'a') as fd:
            fdl = fd.require_group('cluster')
            for kval, lab in zip(clusters, llabels):
                key = 'kmeans-%d'%kval
                if key in fdl:
                    if overwrite:
                        del fdl[key]
                    else:
                        logger.error('Key already exists and overwrite is disabled: %s'%key)
                        continue
                fdl[key] = lab
                fdl[key].attrs.create('k', kval, dtype=np.uint8)
                fdl[key].attrs.create('eigenvector', range(ev.shape[1] - eigvals, ev.shape[1]), dtype=np.uint32)
    else:
        logger.info('File exists, not overwriting clustering: {}'.format(fout))

@main.command()
@click.option('--data', type=click.Path())
@click.option('--output', type=click.Path())
@click.option('--overwrite/--no-overwrite', default=False)
@click.option('--modify/--no-modify', default=False)
@click.option('--computed/--loaded', default=True)
@click.option('--eigvals', type=int, default=8)
@click.pass_context
def tsne(ctx, data, output, overwrite, modify, computed, eigvals):
    fout = data if output is None else output

    if not path.exists(fout) or modify:
        logger.info('Computing TSNE: {}'.format(fout))
        if computed and ('ev' in ctx.obj):
            ev = ctx.obj.ev
        else:
            try:
                with h5py.File(data, 'r') as fd:
                    ev = fd['eigenvector'][:]
            except KeyError:
                logger.error('Embedding must be either computed or already exist in data.')
                return

        tsne = TSNE().fit_transform(ev[:, -eigvals:])

        with h5py.File(fout, 'a') as fd:
            fdl = fd.require_group('visualization')
            key = 'tsne'
            if key in fdl:
                if overwrite:
                    del fdl[key]
                else:
                    logger.error('Key already exists and overwrite is disabled: %s'%key)
                    return
            fdl[key] = tsne.astype(np.float32)
            fdl[key].attrs.create('eigenvector', range(ev.shape[1] - eigvals, ev.shape[1]), dtype=np.uint32)
    else:
        logger.info('File exists, not overwriting TSNE: {}'.format(fout))

if __name__ == '__main__':
    main()
