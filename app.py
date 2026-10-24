from pathlib import Path
import datetime as dt,json,hashlib
import streamlit as st
import engine
st.set_page_config(page_title='Developer Tool Reliability Monitor',page_icon='🔎',layout='wide')
st.markdown('''<style>.block-container{max-width:1120px;padding-top:2.4rem}h1{font-size:2.6rem!important;letter-spacing:-.06rem}div[data-testid="stMetric"]{border:1px solid #dbe4e3;padding:14px;border-radius:10px;background:#f5f8f6}div[data-testid="stCaptionContainer"]{line-height:1.5}footer{visibility:hidden}</style>''',unsafe_allow_html=True)
st.caption('DEVELOPER TOOL RELIABILITY MONITOR · REVIEW WORKSPACE')
st.title('Which reports need a closer look?')
st.write('Turn reports about Python, Node.js and VS Code into a source-linked review packet for your next planning meeting.')
st.caption('The model suggests what to review. You decide what belongs in the team’s work queue.')
@st.cache_resource
def ready():return engine.resources()
try:_,saved,_=ready()
except Exception:
 st.error('The saved model could not be loaded. Please try again later or contact the app owner.');st.stop()
mode=st.radio('1. Add your reports',['Use the saved collection','Upload a collection','Enter one report'],horizontal=True)
records=[];uploaded=[];manual={}
if mode=='Use the saved collection':
 st.info('Try the tool without preparing a file. This is the saved October 1, 2026 collection—not a live feed.')
 sources=st.multiselect('Repositories to include',list(engine.SOURCES),default=list(engine.SOURCES))
 limit=st.selectbox('How many reports?', [3,12,50,100],index=0)
 records=[r for r in saved if r['source'] in sources]
 if limit==3:
  wanted=['microsoft/vscode#318366','python/cpython#158583','nodejs/node#66388'];records=[r for rid in wanted for r in records if r['record_id']==rid]
 else:records=records[:limit]
 st.caption(f'{len(records)} reports selected. The 3-report example includes one source from each selected repository.')
elif mode=='Upload a collection':
 st.caption('Add CSV or JSON files from the three supported repositories. Up to 100 reports total; 2 MB per file. Public issue text only—do not upload secrets or private reports.')
 uploaded=st.file_uploader('Collection files',type=['csv','json'],accept_multiple_files=True,max_upload_size=2)
 with st.expander('What fields does my file need?'):
  st.write('Required: title, excerpt, source, source_url and published_date (YYYY-MM-DD). Source must be CPython, VS Code or Node.js; the link must point to an issue in the matching repository. Optional: record_id, repository, issue_state and collected_at_utc.')
  sample=[{k:saved[0][k] for k in ['record_id','title','excerpt','source','source_url','published_date','repository']}]
  st.download_button('Download a sample input file',json.dumps(sample,indent=2),file_name='sample_issues.json',mime='application/json')
else:
 st.caption('Paste a public GitHub issue report. The app analyzes the text you provide; it does not fetch the link.')
 a,b=st.columns(2)
 with a:
  source=st.selectbox('Source repository',list(engine.SOURCES));title=st.text_input('Report title');url=st.text_input('Original GitHub issue link',placeholder='https://github.com/python/cpython/issues/123')
 with b:
  date=st.date_input('Publication date',value=None);excerpt=st.text_area('Report description',height=130,placeholder='Paste the issue description, including what happened and what was expected.')
 manual={'source':source,'title':title,'source_url':url,'published_date':date.isoformat() if date else '', 'excerpt':excerpt}
# A changed input invalidates old results so they cannot be mistaken for a new run.
fingerprint=hashlib.sha256(json.dumps({'mode':mode,'records':records,'manual':manual,'files':[(x.name,hashlib.sha256(x.getvalue()).hexdigest()) for x in uploaded]},sort_keys=True).encode()).hexdigest()
if st.session_state.get('input_signature')!=fingerprint:
 for key in ['results','rejected','input_error']:
  st.session_state.pop(key,None)
 st.session_state['input_signature']=fingerprint
if st.button('2. Create review packet',type='primary'):
 st.session_state.pop('results',None);st.session_state.pop('rejected',None);st.session_state.pop('input_error',None)
 try:
  batch=engine.read_files([(x.name,x.getvalue()) for x in uploaded]) if mode=='Upload a collection' else [manual] if mode=='Enter one report' else records
  with st.spinner('Checking reports and preparing your review packet…'):results,rejected=engine.run_batch(batch)
  st.session_state['results']=results;st.session_state['rejected']=rejected
 except ValueError as e:st.session_state['input_error']=str(e)
 except Exception:st.session_state['input_error']='The review packet could not be created. Try the saved collection or check your input and try again.'
if st.session_state.get('input_error'):st.error(st.session_state['input_error'])
results=st.session_state.get('results')
if not results:
 st.divider();st.subheader('Your review packet will appear here')
 st.write('Choose the saved example, upload a collection or enter a report, then select “Create review packet.” You’ll get suggested next steps, reasons to check uncertain reports, and files you can share.')
else:
 rejected=st.session_state.get('rejected',[])
 st.divider();st.subheader('Your review packet')
 a,b,c=st.columns(3)
 for col,route in zip([a,b,c],engine.ROUTES):col.metric(engine.ROUTES[route],sum(x['analysis']['route']==route for x in results))
 st.caption(f'{len(results)} reports included · {len(rejected)} rows not used · Suggestions are not approved work. Check current status at the original source.')
 if rejected:
  with st.expander(f'Check {len(rejected)} rows that could not be used'):
   for x in rejected:st.write(f'Row {x["row"]}: {x["reason"]}')
 a,b=st.columns(2)
 a.download_button('Download readable report',engine.report_html(results,rejected),file_name='developer_tool_review.html',mime='text/html')
 b.download_button('Download work queue (CSV)',engine.csv_bytes(results),file_name='developer_tool_work_queue.csv',mime='text/csv')
 a,b=st.columns([2,1])
 search=a.text_input('Find a report',placeholder='Search by title, source or issue ID');route=b.selectbox('Show reports',['All reports']+list(engine.ROUTES.values()))
 shown=[x for x in results if search.lower() in (x['record']['title']+' '+x['record']['source']+' '+x['record']['record_id']).lower() and (route=='All reports' or engine.ROUTES[x['analysis']['route']]==route)]
 if not shown:st.info('No reports match. Clear the search or choose “All reports.”')
 else:
  selected=st.selectbox('Choose a report to inspect',list(range(len(shown))),format_func=lambda i:shown[i]['record']['title'])
  x=shown[selected];r=x['record'];an=x['analysis']
  with st.container(border=True):
   st.caption(engine.ROUTES[an['route']].upper());st.subheader(r['title']);st.caption(f'{r["record_id"]} · Published {r["published_date"]} · Saved state: {r["issue_state"]}')
   st.link_button('Open original GitHub issue',r['source_url'])
   st.markdown('#### What to check next');st.write(an['next_step'])
   st.markdown('#### Why this route?')
   if an['reasons']:
    for reason in an['reasons']:st.write('• '+reason)
   else:st.write('The report passed the model’s basic support checks. Verify the source before acting.')
   st.markdown('#### Saved source description');st.text(r['excerpt'])
   with st.expander('Model support and similar examples'):
    st.caption('The model score is not a probability. Similar wording does not mean the reports have the same cause.')
    if an['model_score'] is not None:st.write(f'Model score: {an["model_score"]:.3f} · Familiar-word coverage: {an["vocabulary_coverage"]:.0%}')
    for n in an['neighbors']:st.markdown(f'[{n["record_id"]}]({n["source_url"]}) — similarity {n["similarity"]:.3f}')
with st.expander('About the data, model and privacy'):
 st.write('This uses the same local Naive Bayes model and review gates as Assignment 4. Its agreement was 21/30 against AI-assisted draft labels, equal to the majority baseline. It does not confirm defects, severity, causes or fixes. The saved collection includes 41 CPython, 42 VS Code and 17 Node.js reports. Model evaluation uses a held-out split, not every displayed record.')
 st.write('No paid AI API is called. Inputs and results stay in the current app session; the app does not intentionally write uploads to storage or send them to a model provider. A public host processes the session, so use public issue text only. Refreshing or closing the session may clear your packet; download files you want to keep.')
