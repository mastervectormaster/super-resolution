import data
import numpy as np

from PIL import Image
from . import ARR_PATH


def fullsize_sequence():
    return data.fullsize_sequence(ARR_PATH, scale=2, subset='train', downgrade='bicubic', image_ids=range(1, 5))


def cropped_sequence(batch_size=2):
    return data.cropped_sequence(ARR_PATH, scale=2, subset='train', downgrade='bicubic', image_ids=range(1, 5), batch_size=batch_size)


def test_batch_size(conversion):
    sequence = cropped_sequence(batch_size=3)
    assert len(sequence) == 2

    lr_batch, hr_batch = sequence[0]
    assert lr_batch.shape == (3, 48, 48, 3)
    assert hr_batch.shape == (3, 96, 96, 3)

    lr_batch, hr_batch = sequence[1]
    assert lr_batch.shape == (1, 48, 48, 3)
    assert hr_batch.shape == (1, 96, 96, 3)


def test_full_image_size(conversion):
    sequence = fullsize_sequence()
    lr_batch, hr_batch = sequence[0]
    assert lr_batch.shape == (1, 702, 1020, 3)
    assert hr_batch.shape == (1, 1404, 2040, 3)


def test_cropped_image_size(conversion):
    sequence = cropped_sequence()
    lr_batch, hr_batch = sequence[0]
    assert lr_batch.shape == (2, 48, 48, 3)
    assert hr_batch.shape == (2, 96, 96, 3)


def test_bicubic_downscale_fullsize(conversion):
    assert_bicubic_downscale(fullsize_sequence())


def test_bicubic_downscale_cropped(conversion):
    assert_bicubic_downscale(cropped_sequence())


def assert_bicubic_downscale(sequence, bound=12):
    for i in range(len(sequence)):
        lr_batch, hr_batch = sequence[i]
        for lr, hr in zip(lr_batch, hr_batch):
            assert_bicubic_downscale_1(lr, hr, bound)


def assert_bicubic_downscale_1(lr, hr, bound):
    """
    Assert that the pixel-wise value difference between an lr
    image and a bicubic downscaled hr image is within bound.
    """

    hr_img = Image.fromarray(hr)
    ds_img = hr_img.resize((lr.shape[1], lr.shape[0]), resample=Image.BICUBIC)

    lr = lr.astype('int16')
    ds = np.array(ds_img, dtype='int16')

    assert np.max(lr - ds) <= bound
