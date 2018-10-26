import os
import glob
import logging
import argparse
import numpy as np

from model import load_model
from util import load_image, init_session

from PIL import Image


def image_paths(path):
    jpgs = glob.glob(os.path.join(path, '*.jpg'), recursive=True)
    pngs = glob.glob(os.path.join(path, '*.png'), recursive=True)
    return jpgs + pngs


def resolved_name(path):
    head, tail = os.path.split(path)
    name, ext = os.path.splitext(tail)
    return f'{name}-sr{ext}'


def resolve(model, lr):
    sr = model.predict(np.expand_dims(lr, axis=0))[0]
    sr = np.clip(sr, 0, 255)
    sr = sr.astype('uint8')
    return Image.fromarray(sr)


def main(args):
    """
    Super-resolve all *.jpg and *.png images in a user-defined directory.
    """

    logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.INFO)
    os.makedirs(args.outdir, exist_ok=True)

    model = load_model(args.model)

    for path in image_paths(args.indir):
        logging.info('Super-resolve image %s', path)
        lr = load_image(path)
        sr = resolve(model, lr)
        sr.save(os.path.join(args.outdir, resolved_name(path)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='DIV2K benchmark')

    parser.add_argument('-i', '--indir', type=str, default='./demo',
                        help='path to LR images directory')
    parser.add_argument('-o', '--outdir', type=str, default='./output',
                        help='output JSON file')
    parser.add_argument('-m', '--model', default=2,
                        help='model file')
    parser.add_argument('--gpu-memory-fraction', type=float, default=0.8,
                        help='fraction of GPU memory to allocate')

    args = parser.parse_args()

    init_session(args.gpu_memory_fraction)
    main(args)
