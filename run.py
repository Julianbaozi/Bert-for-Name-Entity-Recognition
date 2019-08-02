#!/usr/bin/env python

import torch
import torch.nn as nn
import pickle as pk
from sklearn.model_selection import KFold
from config import config
from function import *

if __name__ == "__main__":

    import warnings
    warnings.filterwarnings('once')

    words, sentences, labels, tags_vals, tag2idx = read_data(config, "data/dataset.csv") #data_path = "data/dataset.csv"
    config['num_labels'] = len(tag2idx)
    data_fold = vectorization(config, sentences, labels, tags_vals, tag2idx)

    config['device'] = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    n_gpu = torch.cuda.device_count()
    print('The device is ' + torch.cuda.get_device_name(0)) 
    print('The number of device is ', n_gpu) 

    if_cross_val = config['if_cross_val']
    if if_cross_val:
        print('Cross Validation')
        fold_num = config['fold_num']
        kfold = KFold(fold_num, shuffle=True, random_state=None)
        # enumerate splits
        f = 1
        eval_accuracy_fold = [] 
        f1_fold = []
        for train_index, test_index in kfold.split(data_fold[0]):
            dataloader, count = myDataLoader(config, data_fold, train_index, test_index)

#             weight = torch.tensor(np.log(max(count)/count)+config['mu'])
            weight = None
            print('')
            print('Fold {}:'.format(f))
            model = None
            model = BuildModel(config, weight)
            _, eval_accuracy, f1 = train(config, model, dataloader, if_plot=False, fold_id=f)
            eval_accuracy_fold.append(eval_accuracy)
            f1_fold.append(f1)
            f+=1
        print('accuracy of folds: {}'.format(eval_accuracy_fold))
        print('average accuracy: {}'.format(sum(eval_accuracy_fold)/fold_num))
        print('f1 of folds: {}'.format(f1_fold))
        print('average f1: {}'.format(sum(f1_fold)/fold_num))

    else:
        dataloader, count = myDataLoader(config, data_fold)
        weight = np.log(max(count)/count)+config['mu']
        weight = torch.tensor(weight)
        #     weight = None
        model = BuildModel(config, weight)
        model, max_acc, max_f1 = train(config, model, dataloader, if_plot=True)
        
        with open('results/model_weighted.pkl','wb') as fp: #output_path = "results"
            pk.dump(model,fp) 
        if config['test_size']:
            predictions, true_labels, eval_loss, eval_accuracy, f1 = test(config, model, dataloader[1], validation = False, tags_vals=tags_vals)


