"""Build credential-free, importable n8n workflows. Never run live generations here."""
import json
from pathlib import Path
import uuid

ROOT = Path(__file__).resolve().parents[1] / 'n8n' / 'workflows'
BASE = 'http://127.0.0.1:8099'


def node(name, kind, params, x, version=1, **extra):
    return dict(id=str(uuid.uuid5(uuid.NAMESPACE_URL, name)), name=name,
                type=f'n8n-nodes-base.{kind}', typeVersion=version,
                position=[x, 0], parameters=params, **extra)


def code(name, source, x):
    return node(name, 'code', {'jsCode': source}, x, 2)


def fields_node(name, fields, x):
    return node(name, 'set', {'assignments': {'assignments': [
        {'id': k, 'name': k, 'value': v, 'type': 'string'} for k, v in fields.items()
    ]}, 'includeOtherFields': True, 'options': {}}, x, 3.4)


def http(name, url, x, method='GET', body=None, download=False, google=False):
    params = {'url': url, 'method': method, 'authentication': 'predefinedCredentialType' if google else 'genericCredentialType',
              'options': {'timeout': 30000}}
    params['nodeCredentialType' if google else 'genericAuthType'] = 'youTubeOAuth2Api' if google else 'httpHeaderAuth'
    if body is not None:
        params.update(sendBody=True, contentType='json', specifyBody='json', jsonBody=body)
    if download:
        params['options']['response'] = {'response': {'responseFormat': 'file', 'outputPropertyName': 'data'}}
        params['options']['timeout'] = 120000
    if url.endswith('/v1/setup') or url.endswith('/v1/preflight'):
        params['options']['timeout'] = 120000
    return node(name, 'httpRequest', params, x, 4.2, retryOnFail=False)


def field(label, choices=None, required=False, kind='text'):
    item = {'fieldLabel': label, 'fieldType': 'dropdown' if choices else kind, 'requiredField': required}
    if choices:
        item['fieldOptions'] = {'values': [{'option': x} for x in choices]}
    return item


def form(name, title, path, fields):
    return node(name, 'formTrigger', {'path': path, 'formTitle': title,
        'formDescription': 'Use n8n execution results to see status and errors. All uploads remain Private.',
        'formFields': {'values': fields}, 'responseMode': 'lastNode', 'options': {}}, 0, 2.2,
        webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, path)))


def save(name, filename, nodes):
    for index, item in enumerate(nodes):
        item['position'] = [index * 240, 0]
    wf = {'name': name, 'nodes': nodes, 'connections': {}, 'active': False,
          'settings': {'executionOrder': 'v1'}, 'tags': []}
    for left, right in zip(nodes, nodes[1:]):
        wf['connections'][left['name']] = {'main': [[{'node': right['name'], 'type': 'main', 'index': 0}]]}
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT/filename).write_text(json.dumps(wf, ensure_ascii=False, indent=2)+'\n')


story_form = form('Story Submission Form', 'Create a WonderTales video', 'wondertales-story', [
    field('Story title', required=True), field('Story / poem / rhyme', required=True, kind='textarea'),
    field('Language', ['English', 'Hindi'], True), field('Video format', ['9:16 vertical', '16:9 landscape'], True),
    field('Target duration', ['30 seconds', '1 minute', '90 seconds', '2 minutes'], True),
    field('Flow account alias (blank uses flow-main)'), field('YouTube destination alias (blank uses channel-main)'),
    field('Consistency', ['Reference images', 'Text descriptions (less consistent)'], True),
    field('Editor (blank uses built-in)', ['Built-in FFmpeg', 'MoneyPrinterTurbo']),
    field('Subtitle style (MoneyPrinterTurbo only)', ['clean', 'kids']),
    field('Licensed music path (optional; MoneyPrinterTurbo only)'),
    field('Learning goal (optional)'), field('Rights / licence notes (optional)', kind='textarea'),
    field('Variant label (optional; change only for an intentional new version)')])
story_form['parameters']['formDescription'] += ' Give the story an engaging opening, a clear problem and a satisfying ending. Use original or licensed characters/stories. Music paths point to the worker imports folder. Narration is spoken, not sung.'
registry = {}
for i in range(1, 11):
    for suffix in ('name', 'face_prompt', 'body_prompt', 'reference_image'):
        registry[f'character_{i:02}_{suffix}'] = ''
registry_node = fields_node('Character Registry (edit in n8n)', registry, 240)
config = fields_node('Credit Settings (configure in n8n)', {'creditCostPerClip': '', 'maxCreditsPerJob': ''}, 480)
prepare = code('Validate and Choose Characters', r'''
const form = $('Story Submission Form').first().json;
const registry = $('Character Registry (edit in n8n)').first().json;
const config = $input.first().json;
const title = String(form['Story title'] || '').trim();
const story = String(form['Story / poem / rhyme'] || '').trim();
const language = form.Language;
if (!['9:16 vertical','16:9 landscape'].includes(form['Video format'])) throw new Error('Choose a supported video format.');
if (!['Reference images','Text descriptions (less consistent)'].includes(form.Consistency)) throw new Error('Choose an explicit consistency mode.');
const aspectRatio = form['Video format'] === '9:16 vertical' ? '9:16' : '16:9';
const durationSeconds = {'30 seconds':30, '1 minute':60, '90 seconds':90, '2 minutes':120}[form['Target duration']];
if (!title || !story || !durationSeconds || !['English','Hindi'].includes(language)) throw new Error('Check the story, language, and duration.');
const pool = Array.from({length:10}, (_,i) => {
  const slot = String(i+1).padStart(2,'0');
  const read = suffix => String(registry[`character_${slot}_${suffix}`] || '').trim();
  return {name:read('name'), facePrompt:read('face_prompt'), bodyPrompt:read('body_prompt'), referenceImage:read('reference_image')};
}).filter(c => c.name && c.facePrompt && c.bodyPrompt);
if (pool.length < 2) throw new Error('Fill in at least two character names, faces, and clothing descriptions in Character Registry.');
if (new Set(pool.map(c=>c.name)).size !== pool.length) throw new Error('Use unique character names.');
const variant = String(form['Variant label (optional; change only for an intentional new version)'] || '').trim();
// Stable pseudorandom casting: a retried identical submission must not create a new paid job.
let seed = 2166136261;
for (const ch of JSON.stringify([title, story, language, aspectRatio, durationSeconds, variant])) seed = Math.imul(seed ^ ch.charCodeAt(0), 16777619) >>> 0;
const random = () => { seed = (Math.imul(seed,1664525) + 1013904223) >>> 0; return seed / 4294967296; };
for (let i=pool.length-1; i>0; i--) { const j=Math.floor(random()*(i+1)); [pool[i],pool[j]]=[pool[j],pool[i]]; }
const count = Math.min(pool.length, random()<0.5 ? 2 : 3);
const creditCostPerClip = Number(config.creditCostPerClip);
const maxCreditsPerJob = Number(config.maxCreditsPerJob);
if (!Number.isFinite(creditCostPerClip) || !Number.isFinite(maxCreditsPerJob) || !(creditCostPerClip>0) || !(maxCreditsPerJob>0)) throw new Error('Set the displayed Flow cost per clip and your per-job credit cap in Credit Settings.');
return [{json:{title, story, language, aspectRatio, durationSeconds, variant,
 flowAccount:String(form['Flow account alias (blank uses flow-main)'] || 'flow-main').trim(),
 youtubeDestination:String(form['YouTube destination alias (blank uses channel-main)'] || 'channel-main').trim(),
 selectedCharacters:pool.slice(0,count), creditCostPerClip, maxCreditsPerJob,
 editor:form['Editor (blank uses built-in)'] === 'MoneyPrinterTurbo' ? 'moneyprinterturbo' : 'builtin',
 subtitleStyle:form['Subtitle style (MoneyPrinterTurbo only)'] || 'clean',
 musicFile:String(form['Licensed music path (optional; MoneyPrinterTurbo only)'] || '').trim(),
 learningGoal:String(form['Learning goal (optional)'] || '').trim(),
 rightsNote:String(form['Rights / licence notes (optional)'] || '').trim(),
 consistencyMode:form.Consistency === 'Reference images' ? 'reference' : 'text',
 model:'veo-lite', uploadVisibility:'private', madeForKids:true}}];
'''.strip(), 720)
queue = http('Queue Local Video Job', BASE+'/v1/jobs', 960, 'POST', '={{ $json }}')
save('WonderTales — Story Intake', '01-story-intake.json', [story_form, registry_node, config, prepare, queue])
# Identical settings/registry can be copied from production before this zero-video-credit check.
check_nodes = json.loads(json.dumps([story_form, registry_node, config, prepare, queue]))
check_nodes[0]['parameters']['path'] = 'wondertales-preflight'
check_nodes[0]['parameters']['formTitle'] = 'WonderTales connection and credit preflight'
check_nodes[0]['webhookId'] = str(uuid.uuid5(uuid.NAMESPACE_URL, 'wondertales-preflight'))
check_nodes[-1]['parameters']['url'] = BASE+'/v1/preflight'
check_nodes[-1]['name'] = 'Check Flow Without Generating'
save('WonderTales — Preflight (no video credits)', '02-preflight.json', check_nodes)

status_form = form('Status Form', 'WonderTales jobs and setup', 'wondertales-status', [field('Job ID (blank lists recent jobs)')])
status_http = http('Get Job Status', "={{ '"+BASE+"/v1/jobs' + ($json['Job ID (blank lists recent jobs)'] ? '/' + encodeURIComponent($json['Job ID (blank lists recent jobs)'].trim()) : '') }}", 240)
status = code('Readable Status', "const data=$input.first().json; return (data.jobs || [data]).map(j=>({json:{jobId:j.id,title:j.body.title,state:j.state,progress:j.progress,detail:j.detail,flowAccount:j.body.flowAccount,destination:j.body.youtubeDestination,editor:j.body.editor || 'builtin',creditReport:j.creditReport,quality:j.report,nextAction:j.nextAction,privateYouTubeLink:j.youtubeUrl,scenes:j.scenes}}));", 480)
save('WonderTales — Job Status', '03-job-status.json', [status_form,status_http,status])

manage_form = form('Manage Job Form', 'Recover or resume WonderTales jobs', 'wondertales-manage', [
    field('Job ID', required=True), field('Action', ['Resume safe steps', 'Recover an existing scene clip', 'Record an existing YouTube video ID', 'Rebuild narration and captions', 'Confirm a scene was never submitted', 'Archive this job'], True),
    field('Scene index (starts at 0)'), field('Type NOT_SUBMITTED only after checking Flow'), field('Recovered clip path (inside imports folder)'), field('YouTube video ID')])
manage_code = code('Prepare Recovery Action', r'''
const f=$input.first().json; const id=String(f['Job ID']||'').trim();
if (!/^[a-f0-9]{32}$/.test(id)) throw new Error('Copy a valid Job ID from Job Status.');
const action={'Resume safe steps':'resume','Recover an existing scene clip':'recover','Record an existing YouTube video ID':'reconcile-upload','Rebuild narration and captions':'reset-narration','Confirm a scene was never submitted':'confirm-unsubmitted','Archive this job':'archive'}[f.Action];
if(!action) throw new Error('Choose an action.');
return [{json:{id,action,body:{confirmation:String(f['Type NOT_SUBMITTED only after checking Flow']||'').trim(),sceneIndex:Number(f['Scene index (starts at 0)']),filePath:String(f['Recovered clip path (inside imports folder)']||''),youtubeId:String(f['YouTube video ID']||'').trim()}}}];
'''.strip(), 240)
manage_http=http('Apply Recovery Action', "={{ '"+BASE+"/v1/jobs/' + $json.id + '/' + $json.action }}",480,'POST','={{ $json.body }}')
save('WonderTales — Job Recovery', '04-job-recovery.json', [manage_form,manage_code,manage_http])

schedule=node('Check Ready Jobs', 'scheduleTrigger', {'rule':{'interval':[{'field':'minutes','minutesInterval':1}]}},0,1.2)
dest=fields_node('YouTube Destination (configure)', {'destination':'channel-main','expectedChannelId':''},240)
channel=http('Verify Connected YouTube Account', 'https://www.googleapis.com/youtube/v3/channels?part=id&mine=true',480,google=True)
verify=code('Guard Channel Identity', "const c=$('YouTube Destination (configure)').first().json; if(!c.expectedChannelId || !$input.first().json.items?.some(x=>x.id===c.expectedChannelId)) throw new Error('Set the expected YouTube channel ID and connect the matching OAuth credential on BOTH Google nodes.'); return [{json:$('Pick One Job for This Channel').first().json}];",720)
list_jobs=http('List Ready Jobs', BASE+'/v1/jobs',960)
select=code('Pick One Job for This Channel', "const destination=$('YouTube Destination (configure)').first().json.destination; const j=$input.first().json.jobs.find(j=>j.state==='ready' && j.canClaimUpload===true && j.body.youtubeDestination===destination); return j ? [{json:j}] : [];",1200)
claim=http('Claim Upload', "={{ '"+BASE+"/v1/jobs/' + $json.id + '/claim-upload' }}",1440,'POST',"={{ {destination: $json.body.youtubeDestination} }}")
download=http('Download Verified Video', "={{ '"+BASE+"/v1/jobs/' + $json.id + '/video' }}",1680,download=True)
upload=node('Upload Private to YouTube', 'youTube', {'resource':'video','operation':'upload',
    'title':"={{ $('Claim Upload').first().json.body.title }}", 'regionCode':'IN','categoryId':'1','binaryProperty':'data',
    'options':{'privacyStatus':'private','selfDeclaredMadeForKids':True,'notifySubscribers':False,
               'defaultLanguage':"={{ $('Claim Upload').first().json.body.language === 'Hindi' ? 'hi' : 'en' }}",
               'description':'Children’s story created with AI-assisted animation. Uploaded privately for creator review.'}},1920,1,retryOnFail=False)
complete=code('Validate Upload Result', "const id=$input.first().json.uploadId || $input.first().json.id; if(!/^[A-Za-z0-9_-]{11}$/.test(String(id||''))) throw new Error('Upload result is uncertain. Check YouTube and record its video ID in Job Recovery. Do not retry this upload.'); const j=$('Claim Upload').first().json; return [{json:{jobId:j.id,youtubeId:id,uploadClaim:j.uploadClaim}}];",2160)
record=http('Record Private Upload', "={{ '"+BASE+"/v1/jobs/' + $json.jobId + '/complete-upload' }}",2400,'POST',"={{ {youtubeId:$json.youtubeId, uploadClaim:$json.uploadClaim} }}")
save('WonderTales — Private Upload (one destination)', '05-private-youtube-upload.json', [schedule,dest,list_jobs,select,channel,verify,claim,download,upload,complete,record])
setup=node('Check Setup', 'manualTrigger', {},0)
save('WonderTales — Setup Diagnostics', '06-setup-diagnostics.json',[setup,http('Check Local Tools and Account Aliases',BASE+'/v1/setup',240)])

account_form = form('Account Aliases Form', 'Register dedicated account aliases', 'wondertales-accounts', [
    field('Flow alias (optional)'), field('Dedicated Chrome profile name'), field('Existing Flow project ID (optional)'),
    field('YouTube destination alias (optional)')])
account_code = code('Prepare Account Mapping', "const f=$input.first().json; return [{json:{flowAlias:String(f['Flow alias (optional)']||'').trim(),profile:String(f['Dedicated Chrome profile name']||'').trim(),project:String(f['Existing Flow project ID (optional)']||'').trim(),destination:String(f['YouTube destination alias (optional)']||'').trim()}}];",240)
account_http = http('Save Private Account Mapping',BASE+'/v1/setup/accounts',480,'POST','={{ $json }}')
save('WonderTales — Manage Account Aliases', '07-account-aliases.json',[account_form,account_code,account_http])

# Batch intake reuses the same validation/casting logic as single-story intake.
bank_nodes = json.loads(json.dumps([story_form,registry_node,config,prepare,queue]))
bank_form = bank_nodes[0]
bank_form['parameters']['path'] = 'wondertales-story-bank'
bank_form['parameters']['formTitle'] = 'WonderTales story bank — submit several stories'
bank_form['webhookId'] = str(uuid.uuid5(uuid.NAMESPACE_URL,'wondertales-story-bank'))
bank_fields = bank_form['parameters']['formFields']['values']
bank_fields[:] = [f for f in bank_fields if f['fieldLabel'] not in ('Story title','Story / poem / rhyme')]
bank_fields.insert(0,field('Story bank (title on first line; separate stories with ---)',required=True,kind='textarea'))
source = prepare['parameters']['jsCode']
source = source.replace("const form = $('Story Submission Form').first().json;", '')
bank_nodes[3]['parameters']['jsCode'] = r'''
const input = $('Story Submission Form').first().json;
const raw = String(input['Story bank (title on first line; separate stories with ---)'] || '').trim();
const blocks = raw.split(/\r?\n\s*---\s*\r?\n/).map(s=>s.trim()).filter(Boolean);
if (!blocks.length || blocks.length>30) throw new Error('Submit between 1 and 30 stories. Separate blocks with a line containing ---');
const stories = blocks.map(block=>{
 const lines=block.split(/\r?\n/); const bankTitle=lines.shift().trim(); const bankStory=lines.join('\n').trim();
 if(!bankTitle || !bankStory) throw new Error('Every block needs a title on its first line, then story text below it.');
 const form={...input,'Story title':bankTitle,'Story / poem / rhyme':bankStory};
''' + source + '\n}).map(result=>result[0].json); return [{json:{stories}}];'
bank_nodes[-1]['name'] = 'Save Story Bank'
bank_nodes[-1]['parameters']['url'] = BASE+'/v1/stories'
save('WonderTales — Story Bank', '08-story-bank.json', bank_nodes)

queue_schedule=node('Daily Queue Tick', 'scheduleTrigger', {'rule':{'interval':[{'field':'minutes','minutesInterval':5}]}},0,1.2)
queue_tick=http('Check Daily Queue',BASE+'/v1/queue/tick',240,'POST','={{ {} }}')
queue_summary=http('Show Queue Result',BASE+'/v1/queue/summary',480)
save('WonderTales — Rule-Based Daily Queue', '09-daily-queue-manager.json',[queue_schedule,queue_tick,queue_summary])
control_form=form('Queue Controls Form','WonderTales queue controls','wondertales-queue-controls',[
 field('Action',['Pause everything','Resume everything','Check queue now','Show daily summary'],True)])
control_code=code('Prepare Queue Command',"const action={'Pause everything':'pause','Resume everything':'resume','Check queue now':'tick','Show daily summary':'summary'}[$input.first().json.Action]; if(!action) throw new Error('Choose a queue action.'); return [{json:{action}}];",240)
control_http=http('Apply Queue Command',BASE+'/v1/queue/command',480,'POST','={{ $json }}')
save('WonderTales — Pause Resume and Summary', '10-queue-controls.json',[control_form,control_code,control_http])
summary_schedule=node('Daily Summary at 8 PM', 'scheduleTrigger', {'rule':{'interval':[{'field':'cronExpression','expression':'0 20 * * *'}]}},0,1.2)
save('WonderTales — Daily Summary (in n8n)', '11-daily-summary.json',[summary_schedule,http('Daily Summary',BASE+'/v1/queue/summary',240)])
for filename in ('09-daily-queue-manager.json','11-daily-summary.json'):
 path=ROOT/filename
 data=json.loads(path.read_text()); data['settings']['timezone']='Asia/Kolkata'
 path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

# Daily read-only analytics. Separate OAuth credentials, explicit channel ID, no revenue scopes.
analytics_schedule=node('Refresh Analytics Daily', 'scheduleTrigger', {'rule':{'interval':[{'field':'cronExpression','expression':'0 9 * * *'}]}},0,1.2)
analytics_config=fields_node('Analytics Destination (configure)', {'destination':'channel-main','expectedChannelId':''},240)
analytics_identity=http('Verify Analytics Channel', 'https://www.googleapis.com/youtube/v3/channels?part=id,statistics&mine=true',480,google=True)
analytics_guard=code('Guard Analytics Identity', r'''
const c=$('Analytics Destination (configure)').first().json;
if(!/^UC[A-Za-z0-9_-]{22}$/.test(c.expectedChannelId || '')) throw new Error('Configure the expected YouTube channel ID.');
const ch=($input.first().json.items || []).find(x=>x.id===c.expectedChannelId);
if(!ch) throw new Error('YouTube OAuth channel does not match this destination.');
const s=ch.statistics || {};
const subscriberCount=s.hiddenSubscriberCount || s.subscriberCount===undefined ? null : Number(s.subscriberCount);
const end=new Date(); end.setUTCDate(end.getUTCDate()-2);
const start=new Date(end); start.setUTCDate(start.getUTCDate()-27);
return [{json:{destination:c.destination,channelId:c.expectedChannelId,subscriberCount,
 startDate:start.toISOString().slice(0,10),endDate:end.toISOString().slice(0,10)}}];
'''.strip(),720)
analytics_local=http('List Managed Uploads',BASE+'/v1/analytics/jobs',960)
analytics_ids=code('Select Latest 50 Uploads', r'''
const c=$('Guard Analytics Identity').first().json;
const ids=[...new Set(($input.first().json.jobs || []).filter(j=>j.destination===c.destination && j.youtubeId).map(j=>j.youtubeId))].slice(0,50);
// A new channel with no managed uploads can still be checked using its channel statistics.
return [{json:{...c,ids,videoStatusUrl:ids.length ? 'https://www.googleapis.com/youtube/v3/videos?part=id,status,snippet&id='+encodeURIComponent(ids.join(',')) : 'https://www.googleapis.com/youtube/v3/videos?part=id,status,snippet&id=00000000000'}}];
'''.strip(),1200)
analytics_status=http('Read Publication Status', '={{ $json.videoStatusUrl }}',1440,google=True)
analytics_url=code('Build Read Only Analytics Query', r'''
const c=$('Select Latest 50 Uploads').first().json;
const videos=($input.first().json.items || []).map(v=>({id:v.id,channelId:v.snippet?.channelId,privacyStatus:v.status?.privacyStatus}));
if(videos.some(v=>v.channelId!==c.channelId)) throw new Error('A managed video belongs to a different channel.');
const query={ids:'channel=='+c.channelId,startDate:c.startDate,endDate:c.endDate,dimensions:'video',metrics:'views,estimatedMinutesWatched,averageViewPercentage,subscribersGained',sort:'-estimatedMinutesWatched',maxResults:'200'};
const url='https://youtubeanalytics.googleapis.com/v2/reports?'+Object.entries(query).map(([k,v])=>encodeURIComponent(k)+'='+encodeURIComponent(v)).join('&');
return [{json:{...c,videos,url}}];
'''.strip(),1680)
analytics_fetch=http('Read YouTube Analytics (read-only OAuth)', '={{ $json.url }}',1920)
analytics_fetch['parameters']['genericAuthType']='oAuth2Api'
analytics_parse=code('Normalize Analytics Snapshot',r'''
const c=$('Build Read Only Analytics Query').first().json;
const report=$input.first().json;
if(report.error || !Array.isArray(report.columnHeaders)) throw new Error('YouTube Analytics returned an invalid report; previous snapshot is preserved.');
const names=report.columnHeaders.map(h=>h.name);
const required=['video','views','estimatedMinutesWatched','averageViewPercentage','subscribersGained'];
if(required.some(k=>!names.includes(k))) throw new Error('Analytics columns changed. Update the integration before saving.');
const rows=(report.rows || []).map(row=>Object.fromEntries(required.map(k=>[k,row[names.indexOf(k)]])));
return [{json:{destination:c.destination,channelId:c.channelId,subscriberCount:c.subscriberCount,startDate:c.startDate,endDate:c.endDate,videos:c.videos,rows}}];
'''.strip(),2160)
analytics_save=http('Save Private Analytics Snapshot',BASE+'/v1/analytics/snapshot',2400,'POST','={{ $json }}')
save('WonderTales — Daily YouTube Analytics', '12-youtube-analytics.json', [analytics_schedule,analytics_config,analytics_identity,analytics_guard,analytics_local,analytics_ids,analytics_status,analytics_url,analytics_fetch,analytics_parse,analytics_save])
weekly=node('Weekly Review Monday 10 AM', 'scheduleTrigger', {'rule':{'interval':[{'field':'cronExpression','expression':'0 10 * * 1'}]}},0,1.2)
manual_review=node('Review Performance Now', 'manualTrigger', {},0)
review_http=http('Performance Credits Rights and Publication Report',BASE+'/v1/growth/report',240)
save('WonderTales — Weekly Growth Review', '13-weekly-growth-review.json',[weekly,review_http])
# Manual and scheduled triggers converge on the same report; never connect triggers together.
path=ROOT/'13-weekly-growth-review.json'; data=json.loads(path.read_text())
manual_review['position']=[0,220]; data['nodes'].append(manual_review)
data['connections'][manual_review['name']]={'main':[[{'node':review_http['name'],'type':'main','index':0}]]}
path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
review_nodes=json.loads(json.dumps([story_form,registry_node,config,prepare,queue]))
review_nodes[0]['parameters']['path']='wondertales-story-review'
review_nodes[0]['parameters']['formTitle']='WonderTales story similarity and rights notes — no generation'
review_nodes[0]['webhookId']=str(uuid.uuid5(uuid.NAMESPACE_URL,'wondertales-story-review'))
review_nodes[-1]['name']='Check Story Without Generating'
review_nodes[-1]['parameters']['url']=BASE+'/v1/stories/check'
save('WonderTales — Story Review (no credits)', '14-story-review.json',review_nodes)
thumb_form=form('Thumbnail Preview Form','Preview a video frame for its thumbnail','wondertales-thumbnail',[
 field('Job ID',required=True),field('Frame',['1','2','3'],True)])
thumb_code=code('Choose Saved Thumbnail',"const f=$input.first().json; const id=String(f['Job ID']||'').trim(); if(!/^[a-f0-9]{32}$/.test(id) || !['1','2','3'].includes(f.Frame)) throw new Error('Enter a valid Job ID and choose a frame.'); return [{json:{id,frame:f.Frame}}];",240)
thumb_http=http('Download Thumbnail Candidate',"={{ '"+BASE+"/v1/jobs/' + $json.id + '/thumbnail-' + $json.frame }}",480,download=True)
save('WonderTales — Thumbnail Preview', '15-thumbnail-preview.json',[thumb_form,thumb_code,thumb_http])
for filename in ('12-youtube-analytics.json','13-weekly-growth-review.json'):
 path=ROOT/filename; data=json.loads(path.read_text()); data['settings']['timezone']='Asia/Kolkata'
 path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
