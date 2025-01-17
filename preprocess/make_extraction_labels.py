"""produce the dataset with (psudo) extraction label"""
import os
import json
import shutil
import numpy as np
from collections import defaultdict
from sklearn.model_selection import train_test_split
from cytoolz import compose
from tqdm import tqdm
import sys
sys.path.insert(0,'..')
from NLP_Project import metric
from numba import jit

def _split_words(texts):
    return map(lambda t: t.split(), texts)

@jit
def get_extract_label_jit(art_sents, abs_sents):
    """ greedily match summary sentences to article sentences"""
    extracted = np.empty(0)
    scores = np.empty(0)
    indices = np.array(list(range(len(art_sents))))
    for abst in abs_sents:
        # for each sentence in the abstract, compute the rouge 
        # with all the sentences in the article:
        rouges = np.array(list(map(metric.compute_rouge_l_jit(reference=abst, mode='f'),
                          art_sents)))
        # Take the index of the article sentence maximizing the score:
        temp = np.zeros(rouges.size) - 1
        for id in indices:
            temp[id] = rouges[id]
        ext = np.argmax(temp)
        indices = indices[indices != ext]
        extracted = np.append(extracted, ext)
        scores = np.append(scores, np.take(rouges, ext))
        if indices.size == 0:
            break
    extracted = extracted.astype(int)
    return extracted.tolist(), scores.tolist()

def get_extract_label_original(art_sents, abs_sents):
    """ greedily match summary sentences to article sentences"""
    extracted = []
    scores = []
    indices = list(range(len(art_sents)))
    for abst in abs_sents:
        # for each sentence in the abstract, compute the rouge 
        # with all the sentences in the article:
        rouges = list(map(metric.compute_rouge_l(reference=abst, mode='f'),
                          art_sents))
        # Take the index of the article sentence maximizing the score:
        ext = max(indices, key=lambda i: rouges[i])
        indices.remove(ext)
        extracted.append(ext)
        scores.append(rouges[ext])
        if not indices:
            break
    return extracted, scores

def get_extract_label(art_sents, abs_sents, jit=True):
    if jit:
        return get_extract_label_jit(art_sents, abs_sents)
    else:
        return get_extract_label_original(art_sents, abs_sents)

def label(DATASET_PATH, split, jit=True, task=None):
    data = {}
    path_reports = os.path.join(DATASET_PATH, 'preprocess', split, 'annual_reports')
    path_summaries = os.path.join(DATASET_PATH, 'preprocess', split, 'gold_summaries')
    split = _rename_split_folder(split, task)
    path_labels = os.path.join(DATASET_PATH, 'preprocess', 'labels', split)
    if not os.path.exists(path_labels):
        os.makedirs(path_labels)
        
    for file_name in tqdm(os.listdir(path_reports)):
        with open(os.path.join(path_reports, file_name)) as fr:
            article = fr.readlines()
        if len(article) > 0:
            abstract = _get_abstract(path_summaries, file_name.split('.')[0], len(article), task)
            if abstract is not None:
                data['abstract'] = abstract
                tokenize = compose(list, _split_words)
                art_sents = tokenize(article)
                abs_sents = tokenize(data['abstract'])
                data['article'] = article
                extracted, scores = get_extract_label(art_sents, abs_sents, jit)
                data['extracted'] = extracted
                data['score'] = scores
                with open(os.path.join(path_labels, '{}.json'.format(file_name.split('.')[0])), 'w') as f:
                    json.dump(data, f, indent=4)
    return split, len(os.listdir(path_labels))

def split_data(DATASET_PATH):
    val_labels = os.path.join(DATASET_PATH, 'val')
    if not os.path.exists(val_labels):
        os.makedirs(val_labels)
    file_names = os.listdir(os.path.join(DATASET_PATH, 'train'))
    _, X_val, _, _ = train_test_split(file_names, file_names, test_size=0.2, random_state=42)
    for file_name in X_val:
        shutil.move(os.path.join(DATASET_PATH, 'train', file_name), val_labels)

def _get_abstract(path_summaries, file_name, article_len, task=None):
    if task == 'Headline Generation':
        abs_names = ['{}_1.txt'.format(file_name)]
    elif task == 'Summarization':
        abs_names = ['{}_2.txt'.format(file_name)]
    else:
        abs_names = [s for s in os.listdir(path_summaries) if s.split('_')[0] == file_name]
        abs_names.sort()
    for abs_name in abs_names:
        with open(os.path.join(path_summaries, abs_name)) as fr:
            abstract = fr.readlines()
        if len(abstract) < article_len and len(abstract) > 0:
            return abstract
    return None

def _rename_split_folder(split, task=None):
    if split == 'training':
        return 'train'
    elif split == 'validation':
        if task is not None:
            return 'val'
        else:
            return 'test'
    return split

def analyze_documents_total(DATASET_PATH, split='training'):
    data = {}
    path_reports = os.path.join(DATASET_PATH, 'preprocess', 'distribution', split, 'annual_reports')
    path_summaries = os.path.join(DATASET_PATH, 'preprocess', 'distribution', split, 'gold_summaries')
    path_analysis = os.path.join(DATASET_PATH, 'preprocess', 'distribution', 'analysis_total')
    if not os.path.exists(path_analysis):
        os.makedirs(path_analysis)
    
    for file_name in tqdm(os.listdir(path_reports)):
        with open(os.path.join(path_reports, file_name)) as fr:
            article = fr.readlines()
        if len(article) > 0:
            abstract = _get_abstract(path_summaries, file_name.split('.')[0], len(article))
            if abstract is not None:
                tokenize = compose(list, _split_words)
                art_sents = tokenize(article)
                abs_sents = tokenize(abstract)
                scores = get_scores_total(art_sents, abs_sents)
                data['score'] = scores
                with open(os.path.join(path_analysis, '{}.json'.format(file_name.split('.')[0])), 'w') as f:
                    json.dump(data, f, indent=4)
            
@jit
def get_scores_total(art_sents, abs_sents):
    indices = np.array(list(range(len(art_sents))))
    scores = np.zeros((len(abs_sents), indices.size))
    for j, abst in enumerate(abs_sents):
        rouges = np.array(list(map(metric.compute_rouge_l_jit(reference=abst, mode='f'), art_sents)))
        scores[j] = rouges
        if j == len(abs_sents) - 1:
            return scores.tolist()

def analyze_documents_final(DATASET_PATH, split='training', top_M=None):
    data = {}
    total_len = 0
    rows_distribution = np.empty(0)
    percentage_distribution = np.zeros(100)
    weighted_percentage_distribution = np.zeros(100)
    path_analysis_tot = os.path.join(DATASET_PATH, 'preprocess', 'distribution', 'analysis_total')
    path_analysis = os.path.join(DATASET_PATH, 'preprocess', 'distribution', 'analysis')
    if not os.path.exists(path_analysis):
        os.makedirs(path_analysis)
    
    for file_name in tqdm(os.listdir(path_analysis_tot)):
        with open(os.path.join(path_analysis_tot, file_name)) as fr:
            scores_lists = json.load(fr)
        
        scores, rows_distribution = get_scores_final(scores_lists["score"], rows_distribution, top_M)
        bucket_scores, percentage_distribution, weighted_percentage_distribution = get_bucket_scores(scores, percentage_distribution, weighted_percentage_distribution)
        len_scores = len(scores)
        total_len += len_scores
        data['score'] = scores
        data['bucket'] = bucket_scores
        data['length'] = len_scores
        with open(os.path.join(path_analysis, '{}.json'.format(file_name.split('.')[0])), 'w') as f:
            json.dump(data, f, indent=4)
    
    weighted_percentage_distribution = weighted_percentage_distribution / total_len

    distribution = {'rows': rows_distribution.tolist(),
                    'percentage': percentage_distribution.tolist(),
                    'weighted_percentage': weighted_percentage_distribution.tolist(),
                    'total_len': total_len}

    with open(os.path.join(path_analysis, 'distribution.json'), 'w') as f:
        json.dump(distribution, f, indent=4)
            
@jit
def get_scores_final(scores_lists, rows_distribution, top_M):
    indices = np.array(list(range(len(scores_lists[0]))))
    scores = np.zeros(indices.size)
    for j, scores_list in enumerate(scores_lists):
        rouges = np.array(scores_list)
        if top_M is not None and len(rouges) > top_M:
            sorted_rouges = np.sort(rouges)
            top_M_lower = sorted_rouges[-top_M]
        else:
            top_M_lower = -1
        for i in indices:
            if rouges[i] >= top_M_lower:
                scores[i] += rouges[i]
                if i < len(rows_distribution):
                    rows_distribution[i] += rouges[i]
                else:
                    rows_distribution = np.append(rows_distribution, rouges[i])
        if j == len(scores_lists) - 1:
            return scores.tolist(), rows_distribution

@jit
def get_bucket_scores(scores, percentage_distribution, weighted_percentage_distribution):
    scores = np.array(scores)
    indices = np.array(list(range(len(scores))))
    bucket_scores = np.zeros(100)
    buckets = np.array_split(indices, 100)
    for p, bucket in enumerate(buckets):
        if len(bucket) > 0:
            for i in bucket:
                bucket_scores[p] += scores[i]
            bucket_scores[p] = bucket_scores[p]/len(bucket)
            percentage_distribution[p] += bucket_scores[p]
            weighted_percentage_distribution[p] += bucket_scores[p] * len(scores)
        else:
            bucket_scores[p] = 0
        if p == len(buckets) - 1:
            return bucket_scores.tolist(), percentage_distribution, weighted_percentage_distribution
