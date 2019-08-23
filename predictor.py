from __future__ import print_function

import os
import sys
import time
import json
import pickle
import logging
import argparse

import torch
import numpy as np

import util
import evaluation
import data_provider as data
from common import *
from model import get_model
from bigfile import BigFile
from generic_utils import Progbar


def parse_args():
    parser = argparse.ArgumentParser('W2VVPP predictor')
    parser.add_argument('--rootpath', type=str, default=ROOT_PATH,
                        help='path to datasets. (default: %s)'%ROOT_PATH)
    parser.add_argument('testCollection', type=str,
                        help='test collection')
    parser.add_argument('--overwrite', type=int, default=0, choices=[0,1],
                        help='overwrite existed vocabulary file. (default: 0)')
    parser.add_argument('--text_sets', type=str, nargs='+', default=['tv16.avs.txt'],
                        help='validation collection set (tv16.avs.txt, tv17.avs.txt, tv18.avs.txt).')
    parser.add_argument('--batch_size', default=128, type=int,
                        help='size of a predicting mini-batch.')
    parser.add_argument('--num_workers', default=2, type=int,
                        help='Number of data loader workers.')
    parser.add_argument('--logger_path', default='runs_0',
                        help='Path to load the model.')
    parser.add_argument('--checkpoint', default='model_best.pth.tar', type=str,
                        help='path to latest checkpoint (default: model_best.pth.tar)')

    args = parser.parse_args()
    return args


def main():
    opt = parse_args()
    print(json.dumps(vars(opt), indent=2))

    rootpath = opt.rootpath
    testCollection = opt.testCollection

    resume_file = os.path.join(opt.logger_path, opt.checkpoint)
    if not os.path.exists(resume_file):
        logging.info(resume_file + ' not exists.')
        sys.exit(0)

    # Load checkpoint
    logger.info('loading model...')
    checkpoint = torch.load(resume_file)
    epoch = checkpoint['epoch']
    best_perf = checkpoint['best_perf']
    config = checkpoint['config']

    # Construct the model
    model = get_model('w2vvpp')(config)
    print(model.vis_net, '\n', model.txt_net)
    model.load_state_dict(checkpoint['model'])
    print("=> loaded checkpoint '{}' (epoch {}, best_perf {})"
         .format(resume_file, epoch, best_perf))

    vis_feat_file = BigFile(os.path.join(rootpath, testCollection, 'FeatureData', config.vid_feat))
    vis_loader = data.vis_provider({'vis_feat': vis_feat_file, 'pin_memory': True,
                                    'batch_size': opt.batch_size, 'num_workers': opt.num_workers})

    logger.info('Encoding videos')
    vis_embs, vis_ids = evaluation.encode_vis(model, vis_loader)

    for text_set in opt.text_sets:
        output_dir = os.path.join(rootpath, testCollection, 'w2vvpp_test', text_set, *opt.logger_path.split('/')[-5:])
        pred_result_file = os.path.join(output_dir, 'id.sent.score.txt')

        if util.checkToSkip(pred_result_file, opt.overwrite):
            sys.exit(0)
        util.makedirs(output_dir)

        capfile = os.path.join(rootpath, testCollection, 'TextData', text_set)
        # load text data
        txt_loader = data.txt_provider({'capfile': capfile, 'pin_memory': True,
                                    'batch_size': opt.batch_size, 'num_workers': opt.num_workers})

        logger.info('Encoding %s captions' % text_set)
        txt_embs, txt_ids = evaluation.encode_txt(model, txt_loader)

        t2i_matrix = evaluation.compute_sim(txt_embs, vis_embs, measure=config.measure)
        inds = np.argsort(t2i_matrix, axis=1)

        
        start = time.time()
        with open(pred_result_file, 'w') as fout:
            for index in range(inds.shape[0]):
                ind = inds[index][::-1]

                fout.write(txt_ids[index]+' '+' '.join([vis_ids[i]+' %s'%t2i_matrix[index][i]
                    for i in ind])+'\n')
        print('writing result into file time: %.3f\n' % (time.time()-start))


if __name__ == '__main__':
    main()