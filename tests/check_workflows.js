const fs=require('fs'),vm=require('vm'),assert=require('assert');
const files=fs.readdirSync('n8n/workflows').filter(f=>f.endsWith('.json'));
assert.equal(files.length,3);
for(const f of files){const w=JSON.parse(fs.readFileSync('n8n/workflows/'+f));assert.strictEqual(w.active,false);const names=new Set(w.nodes.map(n=>n.name));for(const n of w.nodes){if(n.type.endsWith('httpRequest')){assert.equal(n.parameters.genericAuthType,'httpHeaderAuth');assert.ok(!n.credentials);if(n.parameters.jsonBody?.startsWith('={{'))new vm.Script(n.parameters.jsonBody.slice(3,-2));}}for(const [name,c] of Object.entries(w.connections)){assert.ok(names.has(name));for(const targets of c.main)for(const t of targets)assert.ok(names.has(t.node));}}
const html=fs.readFileSync('wondertales/index.html','utf8');new vm.Script(html.match(/<script>([\s\S]*)<\/script>/)[1]);
console.log('Three inactive workflow exports and studio JavaScript validated.');
