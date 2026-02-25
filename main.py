import json
import traceback
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Dict, Optional
import uvicorn
import os
from api_agent import run_agent, db_manager, memory, reload_agent_config, CONFIG_FILE

app_root_path = os.getenv("ROOT_PATH", "/admin/db-config")

app = FastAPI(root_path=app_root_path)

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

class ChatRequest(BaseModel):
    message: str
    session_id: str
    history: Optional[List[Dict[str, str]]] = []
    language: str = "Default English"

@app.get("/")
async def get_home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    user_query = req.message
    session_id = req.session_id
    try:
        print(f"Received query: {user_query} (Session: {session_id}, Language: {req.language})")
        result = run_agent(user_query, session_id=session_id, history=req.history, language=req.language)
        return result
    except Exception as e:
        print(f"Error processing query: {e}")
        return {"response": f"An error occurred: {str(e)}"}

@app.post("/history")
async def history_endpoint(req: ChatRequest):
    try:
        print(f"Fetching history for session: {req.session_id}")
        session_id = req.session_id

        raw_data = memory.get_all(user_id=session_id)
        
        if isinstance(raw_data, dict):
            history_list = raw_data.get("results", [])
        elif isinstance(raw_data, list):
            history_list = raw_data
        else:
            history_list = []
            
        clean_history = []
        for item in history_list:
            if isinstance(item, dict):
                clean_history.append(item.get('memory', ''))
            elif isinstance(item, str):
                clean_history.append(item)
        
        print(f"Successfully retrieved {len(clean_history)} messages.")
        return {"history": clean_history}

    except Exception as e:
        print("CRITICAL ERROR IN HISTORY ENDPOINT:")
        traceback.print_exc()
        return {"history": [], "error": str(e)}

@app.post("/refresh")
async def refresh_endpoint():
    try:
        status_msg = db_manager.refresh_data()
        return {"status": status_msg}
    except Exception as e:
        return {"status": f"Error refreshing data: {str(e)}"}

@app.get("/config")
async def get_config_page(request: Request):
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                config_data = json.load(f)
        else:
            config_data = []
        
        return templates.TemplateResponse("config.html", {
            "request": request, 
            "config_json": json.dumps(config_data)
        })
    except Exception as e:
        return templates.TemplateResponse("config.html", {
            "request": request, 
            "config_json": "[]",
            "error": str(e)
        })

@app.post("/api/config")
async def save_config(request: Request):
    try:
        new_config = await request.json()
        
        with open(CONFIG_FILE, "w") as f:
            json.dump(new_config, f, indent=2)
            
        reload_agent_config()
        
        return {"status": "success"}
    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8005, reload=True)