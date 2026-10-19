"""Generate three inactive n8n exports; configure one Header Auth credential on import."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def http(ident, name, method, path, x, body=None):
    p = {"method": method, "url": "http://127.0.0.1:8099" + path,
         "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
         "options": {"timeout": 240000}}
    if body is not None:
        p.update(sendBody=True, specifyBody="json", jsonBody=body)
    return {"id": ident, "name": name, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [x, 0], "parameters": p}


def write(name, nodes):
    workflow = {"name": name, "active": False, "nodes": nodes, "connections": {},
                "settings": {"executionOrder": "v1", "timezone": "Asia/Kolkata"}}
    for a, b in zip(nodes, nodes[1:]):
        workflow["connections"][a["name"]] = {"main": [[{"node": b["name"], "type": "main", "index": 0}]]}
    (ROOT / "n8n/workflows" / (name.split(" ")[0] + ".json")).write_text(json.dumps(workflow, indent=2) + "\n")


form = {"id": "story", "name": "Your story", "type": "n8n-nodes-base.formTrigger", "typeVersion": 2,
        "position": [0, 0], "webhookId": "wondertales-v2-story",
        "parameters": {"path": "wondertales-v2-story", "responseMode": "lastNode", "formTitle": "WonderTales · New story",
            "formDescription": "Create a scene plan without spending Flow credits. Review and approve it in the local studio.",
            "formFields": {"values": [
                {"fieldLabel": "Title", "requiredField": True},
                {"fieldLabel": "Story", "fieldType": "textarea", "requiredField": True},
                {"fieldLabel": "Language", "fieldType": "dropdown", "fieldOptions": {"values": [{"option": "English"}, {"option": "Hindi"}]}, "requiredField": True},
                {"fieldLabel": "Format", "fieldType": "dropdown", "fieldOptions": {"values": [{"option": "9:16"}, {"option": "16:9"}]}, "requiredField": True},
                {"fieldLabel": "Seconds", "fieldType": "dropdown", "fieldOptions": {"values": [{"option": str(n)} for n in (16, 32, 64, 120)]}, "requiredField": True}]},
            "options": {"respondWithOptions": {"values": {"respondWith": "text", "formSubmittedText": "Your plan was saved. Open the WonderTales studio to review it and approve a credit cap."}}}}}
write("01-story-plan", [form, http("plan", "Save scene plan", "POST", "/api/plan", 280,
    '={{ JSON.stringify({title:$json.Title,story:$json.Story,language:$json.Language,aspect:$json.Format,duration:Number($json.Seconds)}) }}')])
write("02-job-status", [{"id": "manual", "name": "Check progress", "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "position": [0, 0], "parameters": {}},
    http("status", "List videos and guidance", "GET", "/api/jobs", 280)])
write("03-queue-monitor", [{"id": "schedule", "name": "Every hour", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [0, 0], "parameters": {"rule": {"interval": [{"field": "hours", "hoursInterval": 1}]}}},
    http("tick", "Check approved queue", "POST", "/api/tick", 280, "={}"),
    http("jobs", "Progress report", "GET", "/api/jobs", 560)])
