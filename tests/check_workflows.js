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
console.log('7 workflow structures, JS syntax, stable casting, private/kids upload: passed');
