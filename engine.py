"""A4 learned model and routing, called directly without a paid API or n8n server."""
import csv,datetime as dt,html,io,json,re
from functools import lru_cache
from urllib.parse import urlsplit
from model import load
SOURCES={'CPython':'python/cpython','VS Code':'microsoft/vscode','Node.js':'nodejs/node'}
ROUTES={'human_review':'Needs a closer look','investigation_queue':'Suggested investigation','planning_queue':'Suggested planning'}
REASONS={'weak model score':'The model has weak support for this classification.','limited familiar vocabulary':'Many words are unfamiliar to this model.','short source excerpt':'The description has fewer than 15 words.','weak similarity to training examples':'No close training example supports this report.','nearest labeled example disagrees':'The closest labeled example points to a different classification.','sensitive terms in source require a person to review':'The source mentions a sensitive topic that needs a person to check it.'}
@lru_cache(maxsize=1)
def resources():return load()
def normalize(raw):
 if not isinstance(raw,dict):raise ValueError('Each report must be a record with named fields.')
 r={k:v for k,v in raw.items() if isinstance(k,str)}
 for key,label in [('title','title'),('excerpt','description'),('source','source'),('source_url','original GitHub issue link'),('published_date','publication date')]:
  if not isinstance(r.get(key),str) or not r[key].strip():raise ValueError('Add the '+label+'.')
  r[key]=r[key].strip()
 if r['source'] not in SOURCES:raise ValueError('Choose CPython, VS Code or Node.js as the source.')
 if len(r['title'])>1000 or len(r['excerpt'])>12000:raise ValueError('Keep the title under 1,000 characters and the description under 12,000 characters.')
 try:dt.date.fromisoformat(r['published_date'])
 except ValueError:raise ValueError('Use a real publication date in YYYY-MM-DD format.')
 u=urlsplit(r['source_url']); repo=SOURCES[r['source']]
 match=re.fullmatch('/'+re.escape(repo)+r'/issues/([1-9][0-9]*)/?',u.path)
 if u.scheme!='https' or u.netloc!='github.com' or not match or u.query or u.fragment:raise ValueError('Use the original HTTPS issue link from '+repo+', such as https://github.com/'+repo+'/issues/123. Remove extra query text.')
 rid=repo+'#'+match.group(1)
 if r.get('record_id') and r['record_id']!=rid:raise ValueError('The report ID does not match the original issue link.')
 if r.get('repository') and r['repository']!=repo:raise ValueError('The repository does not match the selected source.')
 if r.get('record_type') and r['record_type']!='public_software_issue':raise ValueError('Use issue reports, not pull requests.')
 r.update(record_id=rid,repository=repo,source_url='https://github.com/'+repo+'/issues/'+match.group(1))
 r.setdefault('issue_state','not supplied');r.setdefault('collected_at_utc','not supplied')
 return r

def read_files(files):
 records=[];errors=[]
 if not files:raise ValueError('Choose at least one CSV or JSON file, or use the saved collection.')
 for name,raw in files:
  if len(raw)>2_000_000:raise ValueError('Each file must be smaller than 2 MB. Split the collection into smaller files.')
  try:
   text=raw.decode('utf-8-sig')
   if name.lower().endswith('.csv'):items=list(csv.DictReader(io.StringIO(text)))
   elif name.lower().endswith('.json'):
    items=json.loads(text)
    if isinstance(items,dict):items=items.get('records')
   else:raise ValueError('Choose a .csv or .json file.')
  except (UnicodeDecodeError,json.JSONDecodeError,csv.Error):raise ValueError('Could not read '+name+'. Save a UTF-8 CSV or JSON file and try again.')
  if not isinstance(items,list):raise ValueError(name+' must contain a list of records, or a JSON object with a records list.')
  records.extend(items)
  if len(records)>100:raise ValueError('Use at most 100 reports per run. Split a larger collection and try again.')
 if not records:raise ValueError('The file has no reports. Add at least one record or use the saved collection.')
 return records

def analyze(record):
 classifier,_,_=resources();p=classifier.predict(record);reasons=[]
 if p['model_score']<.8:reasons.append('weak model score')
 if p['vocabulary_coverage']<.3:reasons.append('limited familiar vocabulary')
 if len(record['excerpt'].split())<15:reasons.append('short source excerpt')
 n=p['neighbors'][0] if p['neighbors'] else None
 if not n or n['similarity']<.12:reasons.append('weak similarity to training examples')
 elif n['label']!=p['predicted_label']:reasons.append('nearest labeled example disagrees')
 flags=[x for x in ['uninitialized memory','uninitialised','use-after-free','buffer overflow','permission','sandbox','content exclusion'] if x in (record['title']+' '+record['excerpt']).lower()]
 if flags:reasons.append('sensitive terms in source require a person to review')
 route='human_review' if reasons else 'investigation_queue' if p['predicted_label']=='reported_problem' else 'planning_queue'
 step={'human_review':'Open the original issue and verify the proposed classification before choosing work for the team.','investigation_queue':'Check the current issue status, then try to reproduce the reported behavior in an isolated environment. Record the relevant versions and what you observe.','planning_queue':'Check the current issue status and requested scope, then decide whether the team needs design, documentation, testing or implementation work.'}[route]
 return {'record':record,'analysis':{**p,'route':route,'reasons':[REASONS[x] for x in reasons],'flags':flags,'next_step':step},'status':'ok'}

def run_batch(records):
 if not records:raise ValueError('Add at least one report before creating a review packet.')
 if len(records)>100:raise ValueError('Use at most 100 reports per run.')
 seen=set();results=[];rejected=[]
 for i,raw in enumerate(records,1):
  try:
   r=normalize(raw)
   if r['record_id'] in seen:raise ValueError('This issue is already in the collection. Keep one copy.')
   seen.add(r['record_id'])
  except ValueError as e:rejected.append({'row':i,'reason':str(e)});continue
  try:results.append(analyze(r))
  except Exception:results.append({'record':r,'status':'error','analysis':{'predicted_label':'unavailable','route':'human_review','reasons':['The local analysis did not finish. Review this report manually.'],'flags':[],'next_step':'Open the original issue and review it manually. No model decision was substituted.','neighbors':[],'model_score':None,'vocabulary_coverage':None}})
 if not results:raise ValueError('No reports could be used. '+rejected[0]['reason']+' Check the fields and try again.')
 return results,rejected

def csv_bytes(results,rejected=None):
 f=io.StringIO();w=csv.writer(f);w.writerow(['record_id','title','source','source_url','route','suggestion','review_reasons','next_step'])
 def safe(v):
  v=str(v);return "'"+v if v.lstrip().startswith(('=','+','-','@','\t','\r')) else v
 for x in results:
  r=x['record'];a=x['analysis'];w.writerow([safe(v) for v in [r['record_id'],r['title'],r['source'],r['source_url'],ROUTES[a['route']],a['predicted_label'],'; '.join(a['reasons']),a['next_step']]])
 return f.getvalue().encode('utf-8-sig')
def report_html(results,rejected):
 e=lambda v:html.escape(str(v));parts=[]
 for x in results:
  r=x['record'];a=x['analysis'];parts.append(f'<article><p class="tag">{e(ROUTES[a["route"]])}</p><h2>{e(r["title"])}</h2><p>{e(r["record_id"])} | Published {e(r["published_date"])} | Saved state: {e(r["issue_state"])}</p><p><a href="{e(r["source_url"])}">Open original issue</a></p><h3>What to check next</h3><p>{e(a["next_step"])}</p><ul>'+''.join('<li>'+e(v)+'</li>' for v in a['reasons'])+f'</ul><h3>Saved source description</h3><blockquote>{e(r["excerpt"])}</blockquote></article>')
 notes=''.join(f'<li>Row {x["row"]}: {e(x["reason"])}</li>' for x in rejected)
 return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Developer Tool Review Packet</title><style>body{font:17px/1.6 system-ui;color:#1b3440;background:#f6f7f3;max-width:960px;margin:40px auto;padding:24px}article{background:white;padding:28px;margin:22px 0;border:1px solid #ccd7d8;border-radius:12px}h1,h2{line-height:1.2}.tag{color:#276b65;font-weight:700}blockquote{white-space:pre-wrap;border-left:3px solid #c3d2d2;padding-left:18px}a{color:#17656d}</style><h1>Developer Tool Review Packet</h1><p>'+str(len(results))+' reports. Suggestions require verification. Saved descriptions and issue states may be out of date; check the original source before acting. A4 model agreement was 21/30 against draft labels, equal to the baseline.</p>'+''.join(parts)+('<h2>Rows not used</h2><ul>'+notes+'</ul>' if rejected else '')+'</html>').encode()
