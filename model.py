"""Small, inspectable local text classifier. Python standard library only."""
import collections
import hashlib
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_ROOT = ROOT / "data" if (ROOT / "data").is_dir() else ROOT
STOP = set('a an the and or but to of in on for is are was were be been being it its this that these those with as by at from not no can could should would will have has had do does did if then than so we i you my our your their they them he she there here when where which what how also into any all only some each same about after before using used use issue bug report description version steps reproduce expected actual behavior type linked prs python node vscode github com https http main code'.split())
CLASSES = ('reported_problem', 'planned_work')
DISPLAY = {'reported_problem': 'Reported problem', 'planned_work': 'Planned work'}
VERSION = 'local-nb-v1'

def tokens(record):
    # Exclude source/repository, tracker labels, URLs, IDs, and fenced code.
    text = record['title'] + ' ' + record['title'] + ' ' + record['excerpt'][:2400]
    text = re.sub(r'https?://\S+', ' ', text)
    text = re.sub(r'```.*?```', ' ', text, flags=re.S)
    words = [w for w in re.findall(r'[a-z][a-z_]{2,30}', text.lower()) if w not in STOP]
    return words + [a + ':' + b for a, b in zip(words, words[1:])]

def fit(records, labels):
    train = [r for r in records if labels[r['record_id']]['split'] == 'train']
    df = collections.Counter()
    for r in train:
        df.update(set(tokens(r)))
    vocab = sorted(w for w, n in df.items() if n >= 2)
    counts = {c: collections.Counter() for c in CLASSES}
    docs = collections.Counter()
    for r in train:
        c = labels[r['record_id']]['label']
        docs[c] += 1
        counts[c].update({w: min(n, 3) for w, n in collections.Counter(tokens(r)).items() if w in vocab})
    model = {'version': VERSION, 'classes': list(CLASSES), 'vocabulary': vocab,
             'train_ids': [r['record_id'] for r in train], 'document_counts': dict(docs),
             'log_prior': {}, 'log_likelihood': {}, 'idf': {w: math.log((1 + len(train)) / (1 + df[w])) + 1 for w in vocab}}
    for c in CLASSES:
        model['log_prior'][c] = math.log(docs[c] / len(train))
        denom = sum(counts[c].values()) + len(vocab)
        model['log_likelihood'][c] = {w: math.log((counts[c][w] + 1) / denom) for w in vocab}
    model['training_sha256'] = hashlib.sha256(json.dumps(train, sort_keys=True).encode()).hexdigest()
    return model

class Classifier:
    def __init__(self, model, records, labels):
        self.model, self.labels = model, labels
        self.vocab = set(model['vocabulary'])
        self.train = [r for r in records if r['record_id'] in model['train_ids']]
        self.vectors = {r['record_id']: self.vector(r) for r in self.train}

    def vector(self, record):
        counts = collections.Counter(tokens(record))
        vec = {w: (1 + math.log(n)) * self.model['idf'][w] for w, n in counts.items() if w in self.vocab}
        norm = math.sqrt(sum(v*v for v in vec.values())) or 1
        return {w: v / norm for w, v in vec.items()}

    def predict(self, record):
        raw = tokens(record)
        known = collections.Counter({w: min(n, 3) for w, n in collections.Counter(raw).items() if w in self.vocab})
        scores = {}
        for c in CLASSES:
            scores[c] = self.model['log_prior'][c] + sum(n * self.model['log_likelihood'][c][w] for w, n in known.items())
        winner = max(scores, key=scores.get)
        # A normalized strength measure, explicitly NOT calibrated probability.
        margin = abs(scores[CLASSES[0]] - scores[CLASSES[1]]) / max(1, sum(known.values()))
        strength = 1 / (1 + math.exp(-8 * margin))
        contributions = []
        other = next(c for c in CLASSES if c != winner)
        for w,n in known.items():
            diff = n * (self.model['log_likelihood'][winner][w] - self.model['log_likelihood'][other][w])
            if diff > 0:
                contributions.append((diff, w))
        vec = self.vector(record)
        neighbors = []
        for r in self.train:
            if r['record_id'] == record['record_id']:
                continue
            sim = sum(v * self.vectors[r['record_id']].get(w, 0) for w,v in vec.items())
            neighbors.append({'record_id': r['record_id'], 'title': r['title'], 'source_url': r['source_url'],
                              'label': self.labels[r['record_id']]['label'], 'similarity': round(sim, 4)})
        neighbors.sort(key=lambda x: x['similarity'], reverse=True)
        return {'predicted_label': winner, 'model_score': round(strength,4),
                'vocabulary_coverage': round(sum(known.values()) / max(1,len(raw)),4),
                'text_tokens': len(raw), 'learned_signals': [w for _,w in sorted(contributions, reverse=True)[:6]],
                'neighbors': neighbors[:2], 'split': self.labels.get(record['record_id'],{}).get('split','new')}

def evaluate(classifier, records, labels):
    test = [r for r in records if labels[r['record_id']]['split'] == 'test']
    rows, matrix = [], {a: {b: 0 for b in CLASSES} for a in CLASSES}
    for r in test:
        pred = classifier.predict(r)
        truth = labels[r['record_id']]['label']
        matrix[truth][pred['predicted_label']] += 1
        rows.append({'record_id': r['record_id'], 'source':r['source'], 'title': r['title'],
                     'reference_label': truth, **pred, 'correct': truth == pred['predicted_label']})
    majority = max(classifier.model['document_counts'], key=classifier.model['document_counts'].get)
    n_correct = sum(x['correct'] for x in rows)
    baseline = sum(labels[r['record_id']]['label'] == majority for r in test)
    return {'model_version': VERSION, 'train_count':len(classifier.train), 'test_count':len(test),
            'excluded_count':sum(v['split']=='excluded' for v in labels.values()),
            'correct':n_correct, 'accuracy': n_correct / len(test), 'majority_baseline_accuracy':baseline / len(test),
            'confusion_matrix':matrix, 'predictions':rows,
            'label_provenance':'Reference labels were drafted by an AI assistant from the saved title and excerpt; not independently adjudicated by the student or maintainers.',
            'limitations':'Small single-day snapshot; group-aware held-out test; uncalibrated model scores; no confirmed severity, root cause, fix, or production reliability claims.'}

def load():
    records = json.loads((DATA_ROOT/'a3_snapshot.json').read_text())
    labels = {x['record_id']: x for x in json.loads((DATA_ROOT/'reference_labels.json').read_text())}
    model = json.loads((DATA_ROOT/'model.json').read_text())
    return Classifier(model,records,labels), records, labels

if __name__ == '__main__':
    records=json.loads((DATA_ROOT/'a3_snapshot.json').read_text())
    labels={x['record_id']:x for x in json.loads((DATA_ROOT/'reference_labels.json').read_text())}
    model=fit(records,labels)
    (DATA_ROOT/'model.json').write_text(json.dumps(model,indent=2))
    result=evaluate(Classifier(model,records,labels),records,labels)
    (ROOT/'evidence/model_evaluation.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='predictions'},indent=2))
