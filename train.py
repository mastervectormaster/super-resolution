import os
import logging
import pickle
import datetime
import itertools
import numpy as np
import tensorflow as tf

from args import parser, set_profile
from data import cropped_sequence, fullsize_sequence
from model import edsr, wdsr, copy_weights
from optimizer import weightnorm as wn
from util import init_session

from keras import backend as K
from keras.callbacks import LearningRateScheduler, ModelCheckpoint, TensorBoard
from keras.losses import mean_absolute_error
from keras.models import load_model
from keras.optimizers import Adam


def create_train_workspace(path):
    train_dir = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    train_dir = os.path.join(path, train_dir)
    models_dir = os.path.join(train_dir, 'models')
    os.makedirs(train_dir, exist_ok=True)
    os.mkdir(models_dir)
    return train_dir, models_dir


def write_args(path, args):
    with open(os.path.join(path, 'args.txt'), 'w') as f:
        for k, v in sorted(args.__dict__.items()):
            f.write(f'{k}={v}\n')


def write_history(path, history):
    with open(os.path.join(path, 'history.pkl'), 'wb') as f:
        f.write(pickle.dumps(history))


def model_weightnorm_init(model, generator, num_batches):
    lr_batches = [lr_batch for lr_batch, _ in itertools.islice(generator, num_batches)]
    wn.data_based_init(model, np.concatenate(lr_batches, axis=0))


def model_checkpoint_callback(path, monitor, save_best_only):
    pattern = os.path.join(path, 'epoch-{epoch:03d}-psnr-{' + monitor + ':.4f}.h5')
    return ModelCheckpoint(filepath=pattern, monitor=monitor, save_best_only=save_best_only, mode='max')


def tensor_board_callback(path):
    return TensorBoard(log_dir=os.path.join(path, 'log'), write_graph=False)


def learning_rate_callback(step_size, decay, verbose=1):
    def schedule(epoch, lr):
        if epoch > 0 and epoch % step_size == 0:
            return lr * decay
        else:
            return lr

    return LearningRateScheduler(schedule, verbose=verbose)


def mae(hr, sr):
    hr, sr = _crop_hr_in_training(hr, sr)
    return mean_absolute_error(hr, sr)


def psnr(hr, sr):
    hr, sr = _crop_hr_in_training(hr, sr)
    return tf.image.psnr(hr, sr, max_val=255)


def _crop_hr_in_training(hr, sr):
    """
    Remove margin of size scale*2 from hr in training phase.

    The margin is computed from size difference of hr and sr
    so that no explicit scale parameter is needed. This is only
    needed for WDSR models.
    """

    margin = (tf.shape(hr)[1] - tf.shape(sr)[1]) // 2
    hr = K.in_train_phase(hr[:, margin:-margin, margin:-margin, :], hr)
    hr.uses_learning_phase = True
    return hr, sr


def _load_model(path):
    return load_model(path, custom_objects={'tf': tf,
                                            'AdamWithWeightnorm': wn.AdamWithWeightnorm,
                                            'mae_scale_2': mae, # backwards-compatibility
                                            'mae_scale_3': mae, # backwards-compatibility
                                            'mae_scale_4': mae, # backwards-compatibility
                                            'psnr_scale_2': psnr, # backwards-compatibility
                                            'psnr_scale_3': psnr, # backwards-compatibility
                                            'psnr_scale_4': psnr, # backwards-compatibility
                                            'mae': mae,
                                            'psnr': psnr})


def main(args):
    train_dir, models_dir = create_train_workspace(args.outdir)
    write_args(train_dir, args)
    logging.info('Training workspace is %s', train_dir)

    training_generator = cropped_sequence(args.dataset, scale=args.scale, subset='train', downgrade=args.downgrade,
                                          image_ids=args.training_images, batch_size=args.batch_size)

    if args.benchmark:
        logging.info('Validation with DIV2K benchmark')
        validation_steps = len(args.validation_images)
        validation_generator = fullsize_sequence(args.dataset, scale=args.scale, subset='valid', downgrade=args.downgrade,
                                                 image_ids=args.validation_images)
    else:
        logging.info('Validation with randomly cropped images from DIV2K validation set')
        validation_steps = args.validation_steps
        validation_generator = cropped_sequence(args.dataset, scale=args.scale, subset='valid', downgrade=args.downgrade,
                                                image_ids=args.validation_images, batch_size=args.batch_size)

    if args.model == "edsr":
        loss = mean_absolute_error
        model = edsr.edsr(scale=args.scale,
                          num_filters=args.num_filters,
                          num_res_blocks=args.num_res_blocks,
                          res_block_scaling=args.res_scaling)
    else:
        loss = mae
        model_fn = wdsr.wdsr_b if args.model == 'wdsr_b' else wdsr.wdsr_a
        model = model_fn(scale=args.scale,
                         num_filters=args.num_filters,
                         num_res_blocks=args.num_res_blocks,
                         res_block_expansion = args.res_expansion,
                         res_block_scaling=args.res_scaling)

    if args.weightnorm:
        model.compile(optimizer=wn.AdamWithWeightnorm(lr=args.learning_rate), loss=loss, metrics=[psnr])
        if args.num_init_batches > 0:
            logging.info('Data-based initialization of weights with %d batches', args.num_init_batches)
            model_weightnorm_init(model, training_generator, args.num_init_batches)
    else:
        model.compile(optimizer=Adam(lr=args.learning_rate), loss=loss, metrics=[psnr])

    if args.pretrained_model:
        logging.info('Initialization with weights from pre-trained model %s', args.pretrained_model)
        copy_weights(from_model=_load_model(args.pretrained_model), to_model=model)

    if args.print_model_summary:
        model.summary()

    callbacks = [
        tensor_board_callback(train_dir),
        learning_rate_callback(step_size=args.learning_rate_step_size,
                               decay=args.learning_rate_decay),
        model_checkpoint_callback(models_dir,
                                  monitor='val_psnr',
                                  save_best_only=args.save_best_models_only or args.benchmark)]

    history = model.fit_generator(training_generator,
                                  epochs=args.epochs,
                                  steps_per_epoch=args.steps_per_epoch,
                                  validation_data=validation_generator,
                                  validation_steps=validation_steps,
                                  use_multiprocessing=True,
                                  max_queue_size=args.max_queue_size,
                                  workers=args.num_workers,
                                  callbacks=callbacks)

    write_history(train_dir, history.history)


if __name__ == '__main__':
    logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.INFO)

    args = parser.parse_args()
    set_profile(args)

    init_session(args.gpu_memory_fraction)
    main(args)
