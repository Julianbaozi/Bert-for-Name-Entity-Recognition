import pandas as pd
import numpy as np
from tqdm import tqdm, trange
import pickle as pk

#add pname at the beginning of the sentence
def add_pname(data, cve_cpe_pnames):
    def add(pname):
        if len(pname)==0:
            return [], []
        add_sent = ['Product','name','is']
        add_label = ['O','O','O']
        #only consider pname without '_'
        pname = [i for i in pname if '_' not in i]

        for i in range(len(pname)):
            spl_name = pname[i].split()
            add_sent.extend(spl_name)
            add_label.extend(['pn']*len(spl_name))

            if i!=len(pname)-1:
                add_sent.append(',')
            else:
                add_sent.append('.')
            add_label.append('O')
        return add_sent, add_label

    def agg_func(s):
        add_sent, add_label = add(cve_cpe_pnames[s.name[0]])
        new_sent = add_sent + s["token"].values.tolist()
        new_tag = add_label + s["label"].values.tolist()
        return [(w, t) for w, t in zip(new_sent, new_tag)]


    grouped = data.groupby(['sent_ind','cve_sent_ind']).apply(agg_func)
    words = [w for w in grouped]
    return words

def read_data(config, path):
    data = pd.read_csv(path, encoding="latin1").fillna(method="ffill")
    count_label = data.groupby('label')['sent_ind'].count()
    # sentence id
    i=0
    cve_sent_ind = 0
    sent_ind = data.loc[0]['sent_ind']
    while i<len(data):
        d = data.loc[i]
        if d['sent_ind']==sent_ind:
            data.loc[i, 'cve_sent_ind']=cve_sent_ind
            if d['token']=='.':
                cve_sent_ind=cve_sent_ind+1
            i+=1
        else:
            sent_ind = d['sent_ind']
            cve_sent_ind = 0
            
    with open('data/cpe.pkl','rb') as f:
        cve_cpe_pnames,cve_cpe_vendors = pk.load(f)
    words = add_pname(data, cve_cpe_pnames)
    sentences = [" ".join([s[0] for s in sent]) for sent in words]
    labels = [[s[1] for s in sent] for sent in words]
    substitue = config['substitue']
    tags_vals = list(set(data["label"].values)) + [substitue]
    tag2idx = {t: i for i, t in enumerate(tags_vals)}
    return words, sentences, labels, tags_vals, tag2idx

from pytorch_pretrained_bert import BertTokenizer, BertConfig, BertModel
from keras.preprocessing.sequence import pad_sequences
from torch.utils.data import TensorDataset, DataLoader, RandomSampler, SequentialSampler

def vectorization(config, sentences, labels, tags_vals, tag2idx):
    #use bert tokenization and substitute label
    #vectorize and pad dataset
    tokenizer = BertTokenizer.from_pretrained(config['name'], do_lower_case=config['do_lower_case'])

    mytexts = []
    mylabels = []
    for sent, tags in zip(sentences,labels):
        BERT_texts = []
        BERT_labels = np.array([])
        for word, tag in zip(sent.split(),tags):
            sub_words = tokenizer.tokenize(word)
            n_underscore = sub_words.count('_') 
            for i in range(n_underscore):
                sub_words.remove('_')
            tags = np.array([tag for x in sub_words])
            tags[1:] = config['substitue']
            BERT_texts += sub_words
            BERT_labels = np.append(BERT_labels,tags)
        mytexts.append(BERT_texts)
        mylabels.append(BERT_labels)

    l = 0
    for w in mytexts:
        if len(w)>l:
            l = len(w)
    print('The longest sentence has {} tokens.'.format(l))

    MAX_LEN = config['MAX_LEN']
    #padding data
    input_ids = pad_sequences([tokenizer.convert_tokens_to_ids(txt) for txt in mytexts],
                              maxlen=MAX_LEN, dtype="long", truncating="post", padding="post")
    tags = pad_sequences([[tag2idx.get(l) for l in lab] for lab in mylabels],
                         maxlen=MAX_LEN, value=tag2idx["O"], padding="post",
                         dtype="long", truncating="post")
    attention_masks = np.array([[float(i>0) for i in ii] for ii in input_ids])
    data_fold = (input_ids, tags, attention_masks)
    return data_fold

from sklearn.model_selection import train_test_split

import torch
import torch.nn as nn

def myDataLoader(config, data_fold, train_index=None, test_index=None):
    bs = config['bs']
    test_size = config['test_size']
    if_cross_val = config['if_cross_val']
    input_ids, tags, attention_masks = data_fold
    
    if if_cross_val:
        tr_inputs, val_inputs = input_ids[train_index], input_ids[test_index]
        tr_tags, val_tags = tags[train_index], tags[test_index]
        tr_masks, val_masks = attention_masks[train_index], attention_masks[test_index]
    
    else:
        tr_inputs, val_inputs, tr_tags, val_tags = train_test_split(input_ids, tags, 
                                                                random_state=1, test_size=test_size)
        tr_masks, val_masks, _, _ = train_test_split(attention_masks, input_ids,
                                             random_state=1, test_size=test_size)
    
    tr_inputs = torch.tensor(tr_inputs)
    val_inputs = torch.tensor(val_inputs)
    tr_tags = torch.tensor(tr_tags)
    val_tags = torch.tensor(val_tags)
    tr_masks = torch.tensor(tr_masks)
    val_masks = torch.tensor(val_masks)
    
    train_data = TensorDataset(tr_inputs, tr_masks, tr_tags)
    train_sampler = RandomSampler(train_data)
    train_dataloader = DataLoader(train_data, sampler=train_sampler, batch_size=bs, drop_last=False)

    valid_data = TensorDataset(val_inputs, val_masks, val_tags)
    valid_sampler = SequentialSampler(valid_data)
    valid_dataloader = DataLoader(valid_data, sampler=valid_sampler, batch_size=bs, drop_last=False)
    dataloader = (train_dataloader, valid_dataloader)
    
    count = np.unique(tr_tags, return_counts=True)[1]
    return dataloader, count

from pytorch_pretrained_bert import BertForTokenClassification, BertAdam

def BuildModel(config, weight=None):
    # change the forward method: do not consider 'X' when computing loss
    def new_forward(self, input_ids, token_type_ids=None, attention_mask=None, labels=None, weight=weight):
        sequence_output, _ = self.bert(input_ids, token_type_ids, attention_mask, output_all_encoded_layers=False)
        
        sequence_output = self.dropout(sequence_output)
        logits = self.classifier(sequence_output)

        if labels is not None:
            if weight is not None:
                weight = weight.to(torch.float).to(config['device'])
            loss_fct = nn.CrossEntropyLoss(weight=weight, ignore_index=self.num_labels-1)
            # Only keep active parts of the loss
            if attention_mask is not None:
                active_loss = (attention_mask.view(-1) == 1) #* (labels.view(-1) != self.num_labels-1)
                active_logits = logits.view(-1, self.num_labels)[active_loss]
                active_labels = labels.view(-1)[active_loss]
                loss = loss_fct(active_logits, active_labels)
            else:
                loss = loss_fct(logits.view(-1, self.num_labels), labels.view(-1))
            return loss
        else:
            return logits
    BertForTokenClassification.forward = new_forward
    model = BertForTokenClassification.from_pretrained(config['name'], num_labels=config['num_labels'])
    model.to(config['device'])
    
    return model

from sklearn.metrics import confusion_matrix ,f1_score, accuracy_score, classification_report

def test(config, model, dataloader, validation = False, tags_vals = None):
    #dataloader is only validation data or test data
    model.eval()
    eval_loss, eval_accuracy = 0, 0
    nb_eval_steps, nb_eval_examples = 0, 0
    predictions , true_labels = [], []
    for batch in dataloader:
        batch = tuple(t.to(config['device']) for t in batch)
        b_input_ids, b_input_mask, b_labels = batch
        with torch.no_grad():
            tmp_eval_loss = model(b_input_ids, token_type_ids=None, attention_mask=b_input_mask, labels=b_labels)
            logits = model(b_input_ids, token_type_ids=None, attention_mask=b_input_mask)
        
        active = ((b_input_mask.view(-1) == 1) * (b_labels.view(-1) != config['num_labels']-1))
        active_logits = logits.view(-1, config['num_labels'])[active].cpu().numpy()
        active_labels = b_labels.view(-1)[active].cpu().numpy()
        pred_labels = np.argmax(active_logits, axis=1)
#         label_ids = b_labels.to('cpu').numpy()
#         logits = logits.detach().cpu().numpy()
        predictions.append(pred_labels)
        true_labels.append(active_labels)
        
#         tmp_eval_accuracy = np.sum(pred_labels == active_labels) / len(active_labels)
        
        eval_loss += tmp_eval_loss.mean().item()
#         eval_accuracy += tmp_eval_accuracy
        
        nb_eval_examples += b_input_ids.size(0)
        nb_eval_steps += 1
    eval_loss = eval_loss/nb_eval_steps
#     eval_accuracy = eval_accuracy/nb_eval_steps
    predictions = np.concatenate(predictions)
    true_labels = np.concatenate(true_labels)
    
    eval_accuracy = accuracy_score(true_labels, predictions, normalize=True, sample_weight=None)
    f1 = f1_score(true_labels, predictions, average='macro')
    if validation==True:
        return eval_loss, eval_accuracy, f1
    else:
        print("Test loss: {}".format(eval_loss))
        print("Test Accuracy: {}".format(eval_accuracy))
        print("micro F1-Score: {}".format(f1_score(true_labels, predictions, average='micro',)))
        print("macro F1-Score: {}".format(f1))
        print("weighted F1-Score: {}".format(f1_score(true_labels, predictions, average='weighted')))
        
        pred_tags = [tags_vals[p] for p in predictions]
        valid_tags = [tags_vals[l] for l in true_labels]
        counts = [valid_tags.count(tag) for tag in tags_vals]
        cfs_mat = confusion_matrix(valid_tags, pred_tags,tags_vals)
        cfs_with_index = pd.DataFrame(cfs_mat, index = tags_vals,
                      columns = tags_vals)
        cfs_mat_norm = cfs_mat/cfs_mat.sum(axis=1, keepdims = True)
        cfs_with_index_norm = pd.DataFrame(cfs_mat_norm, index = tags_vals,
                      columns = tags_vals)
        print('')
        print('test counts:')
        print(pd.DataFrame(tags_vals,counts))
        print('')
        print(classification_report(valid_tags, pred_tags))
        print('')
        print('Confusion matrix:')
        print(cfs_with_index)
        sn.heatmap(cfs_with_index_norm)
        print('')
        return predictions, true_labels, eval_loss, eval_accuracy, f1
    
from torch.optim import Adam
import matplotlib.pyplot as plt
import seaborn as sn
from copy import deepcopy

def train(config, model, dataloader, if_plot=True, fold_id=None):
    #the dataloader is the combination of training data and validation data
    epochs = config['epochs']
    max_grad_norm = config['max_grad_norm']
    period = config['period']
    FULL_FINETUNING = config['FULL_FINETUNING']
    
    if FULL_FINETUNING:
        
        param_optimizer = list(model.named_parameters())
        no_decay = ['bias', 'gamma', 'beta']
        optimizer_grouped_parameters = [
            {'params': [p for n, p in param_optimizer if not any(nd in n for nd in no_decay)],
             'weight_decay_rate': config['decay']},
            {'params': [p for n, p in param_optimizer if any(nd in n for nd in no_decay)],
             'weight_decay_rate': 0.0}
        ]
    else:
        param_optimizer = list(model.classifier.named_parameters()) 
        optimizer_grouped_parameters = [{"params": [p for n, p in param_optimizer]}]
    
    optimizer = Adam(optimizer_grouped_parameters, lr=config['lr'])
    
    tr_loss_list = []
    eval_loss_list = []
    eval_acc_list = []
    f1_list = []
    max_acc = 0
    max_f1 = 0
    
    train_dataloader, valid_dataloader = dataloader
    
    if config['test_size']:
        eval_loss, eval_accuracy, f1 = test(config, model, dataloader=valid_dataloader, validation=True)
        # print train loss per epoch
        print('Epoch: {}'.format(0))
        # VALIDATION on validation set
        print("Validation loss: {}".format(eval_loss))
        print("Validation Accuracy: {}".format(eval_accuracy))
        print("Macro F1-Score: {}".format(f1))
        print('')
    
    for epoch in range(1, epochs+1):
        # TRAIN loop
        model.train()
        tr_loss = 0
        nb_tr_examples, nb_tr_steps = 0, 0

        for step, batch in enumerate(train_dataloader):
            # add batch to gpu
            batch = tuple(t.to(config['device']) for t in batch)
            b_input_ids, b_input_mask, b_labels = batch
            # forward pass
            loss = model(b_input_ids, token_type_ids=None,
                         attention_mask=b_input_mask, labels=b_labels)
            # backward pass
            loss.backward()
            # track train loss
            tr_loss += loss.item()
            nb_tr_examples += b_input_ids.size(0)
            nb_tr_steps += 1
            # gradient clipping
            torch.nn.utils.clip_grad_norm_(parameters=model.parameters(), max_norm=max_grad_norm)
            # update parameters
            optimizer.step()
            model.zero_grad()
        tr_loss = tr_loss/nb_tr_steps
        print('Epoch: {}'.format(epoch))
        print("Train loss: {}".format(tr_loss))
        
        if config['test_size']:
            eval_loss, eval_accuracy, f1 = test(config, model, valid_dataloader, validation = True)

            if eval_accuracy>max_acc:
                max_acc = eval_accuracy
                max_f1 = f1
                best_model = deepcopy(model)

            tr_loss_list.append(tr_loss)
            eval_loss_list.append(eval_loss)
            eval_acc_list.append(eval_accuracy)
            f1_list.append(f1)

            if epoch % period == 0:
                # print train loss per epoch
                # VALIDATION on validation set
                print("Validation loss: {}".format(eval_loss))
                print("Validation Accuracy: {}".format(eval_accuracy))
                print("Macro F1-Score: {}".format(f1))
                print('')

    if if_plot:
#     pk.dump((tr_loss_list, eval_loss_list, eval_acc_list, f1_list), open("results/train_result.pkl",'wb'))
    
        ax1=plt.subplot(1, 3, 1)
        ax2=plt.subplot(1, 3, 2)
        ax3=plt.subplot(1, 3, 3)

        ax1.plot(tr_loss_list)
        ax1.plot(eval_loss_list)

        ax2.plot(eval_acc_list)

        ax3.plot(f1_list)
        plt.show()
        plt.savefig('results/train_img{}.png'.format(fold_id))
        
    if config['test_size']:    
        print('The best result: ')
        print('Validation Accuracy: {}, Macro F1-Score: {}'.format(max_acc, max_f1))
        return best_model, max_acc, max_f1
    else:
        return model, None, None
    
        