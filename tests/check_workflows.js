const fs=require('fs');
const path=require('path');
const assert=require('assert');
const dir=path.join(__dirname,'../n8n/workflows');
for(const f of fs.readdirSync(dir).filter(x=>x.endsWith('.json'))){
 const w=JSON.parse(fs.readFileSync(path.join(dir,f),'utf8'));
 assert.strictEqual(w.active,false);
 const names=new Set(w.nodes.map(n=>n.name));
 for(const n of w.nodes){
  if(n.type==='n8n-nodes-base.code') new Function('$','$input',n.parameters.jsCode);
  assert(!n.credentials,'Export must never embed credential IDs or tokens');
 }
 for(const routes of Object.values(w.connections)) for(const output of routes.main) for(const edge of output) assert(names.has(edge.node));
 const upload=w.nodes.find(n=>n.type==='n8n-nodes-base.youTube');
 if(upload){assert.strictEqual(upload.parameters.options.privacyStatus,'private');assert.strictEqual(upload.parameters.options.selfDeclaredMadeForKids,true);assert.strictEqual(upload.retryOnFail,false);}
}
const intake=JSON.parse(fs.readFileSync(path.join(dir,'01-story-intake.json'),'utf8'));
const source=intake.nodes.find(n=>n.name==='Validate and Choose Characters').parameters.jsCode;
const form={'Story title':'A little star','Story / poem / rhyme':'Two friends rescue a bird.','Language':'Hindi','Video format':'9:16 vertical','Target duration':'30 seconds','Consistency':'Text descriptions (less consistent)'};
const registry={};for(let i=1;i<=10;i++){const n=String(i).padStart(2,'0');registry[`character_${n}_name`]='Friend '+i;registry[`character_${n}_face_prompt`]='kind eyes';registry[`character_${n}_body_prompt`]='red coat';}
const $=name=>({first:()=>({json:name==='Story Submission Form'?form:registry})});
const input={first:()=>({json:{creditCostPerClip:'1',maxCreditsPerJob:'20'}})};
const fn=new Function('$','$input',source);
const a=fn($,input)[0].json,b=fn($,input)[0].json;
assert.deepStrictEqual(a.selectedCharacters,b.selectedCharacters,'Retry casting must remain stable');
assert([2,3].includes(a.selectedCharacters.length));assert.strictEqual(a.uploadVisibility,'private');
assert.strictEqual(a.model,'veo-lite');assert.strictEqual(a.language,'Hindi');
const bank=JSON.parse(fs.readFileSync(path.join(dir,'08-story-bank.json'),'utf8'));
const bankForm={...form,'Story bank (title on first line; separate stories with ---)':'A star\nTwo friends help a bird.\n---\nA moon\nTwo friends find a lost toy.'};
const bankLookup=name=>({first:()=>({json:name==='Story Submission Form'?bankForm:registry})});
const batch=new Function('$','$input',bank.nodes.find(n=>n.name==='Validate and Choose Characters').parameters.jsCode)(bankLookup,input)[0].json;
assert.strictEqual(batch.stories.length,2);assert.strictEqual(batch.stories[0].title,'A star');
console.log('11 workflow structures, JS syntax, stable casting, private/kids upload: passed');
