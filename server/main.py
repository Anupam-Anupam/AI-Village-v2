"""
FastAPI Server for AI Village
Provides REST API for task management, agent coordination, and live feed
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import pymongo
import httpx

app = FastAPI(title="AI Village API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connections
POSTGRES_URL = os.getenv("POSTGRES_URL", "postgresql://hub:hubpassword@postgres:5432/hub")
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://admin:password@mongodb:27017/serverdb?authSource=admin")

def get_postgres_conn():
    """Get PostgreSQL connection"""
    return psycopg2.connect(POSTGRES_URL)

def get_mongo_client():
    """Get MongoDB client"""
    return pymongo.MongoClient(MONGODB_URL)

# Pydantic models
class TaskCreate(BaseModel):
    text: str
    timestamp: Optional[str] = None

class TaskResponse(BaseModel):
    task_id: int
    text: str
    status: str
    created_at: str

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "ok", "message": "AI Village API is running"}

@app.post("/task")
async def create_task(task: TaskCreate):
    """Create a new task for agents to execute"""
    try:
        conn = get_postgres_conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Insert task into database
        # Note: agent_id is set to NULL initially, agents will claim tasks when they pick them up
        cur.execute(
            """
            INSERT INTO tasks (title, status, agent_id, created_at, updated_at)
            VALUES (%s, %s, NULL, NOW(), NOW())
            RETURNING id, title, status, created_at
            """,
            (task.text, "pending")
        )
        
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        return {
            "task_id": result["id"],
            "text": result["title"],
            "status": result["status"],
            "created_at": result["created_at"].isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/agents/live")
async def get_live_feed(limit_per_agent: int = 3):
    """Get live feed of agent activity with screenshots and progress"""
    try:
        # Get MongoDB data
        mongo_client = get_mongo_client()
        db = mongo_client.get_database()
        
        # VNC URLs for each agent (can be configured per agent)
        vnc_urls = {
            "agent1": os.getenv("AGENT1_VNC_URL", "https://m-linux-aqnzbmas97.containers.cloud.trycua.com/vnc.html?autoconnect=true&password=479e9bdb455b566d"),
            "agent2": os.getenv("AGENT2_VNC_URL", "https://m-linux-aqnzbmas97.containers.cloud.trycua.com/vnc.html?autoconnect=true&password=479e9bdb455b566d"),
            "agent3": os.getenv("AGENT3_VNC_URL", "https://m-linux-aqnzbmas97.containers.cloud.trycua.com/vnc.html?autoconnect=true&password=479e9bdb455b566d"),
        }
        
        # Get latest progress updates per agent
        agents_data = []
        for agent_id in ["agent1", "agent2", "agent3"]:
            # Get latest progress updates
            progress_updates = list(
                db.progress_updates.find(
                    {"agent_id": agent_id}
                ).sort("timestamp", -1).limit(limit_per_agent)
            )
            
            # Get latest screenshots
            screenshots = list(
                db.screenshots.find(
                    {"agent_id": agent_id}
                ).sort("uploaded_at", -1).limit(limit_per_agent)
            )
            
            # Format data
            latest_progress = progress_updates[0] if progress_updates else None
            
            agents_data.append({
                "agent_id": agent_id,
                "vnc_url": vnc_urls.get(agent_id),
                "latest_progress": {
                    "message": latest_progress.get("message", "") if latest_progress else "",
                    "progress_percent": latest_progress.get("progress_percent", 0) if latest_progress else 0,
                    "timestamp": latest_progress.get("timestamp").isoformat() if latest_progress and latest_progress.get("timestamp") else None
                } if latest_progress else None,
                "progress_updates": [
                    {
                        "message": p.get("message", ""),
                        "progress_percent": p.get("progress_percent", 0),
                        "timestamp": p.get("timestamp").isoformat() if p.get("timestamp") else None,
                        "task_id": p.get("task_id")
                    }
                    for p in progress_updates
                ],
                "screenshots": [
                    {
                        "url": f"/screenshots/{s.get('filename', '')}",
                        "uploaded_at": s.get("uploaded_at").isoformat() if s.get("uploaded_at") else None,
                        "task_id": s.get("task_id")
                    }
                    for s in screenshots
                ]
            })
        
        mongo_client.close()
        
        return {
            "agents": agents_data,
            "generated_at": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/chat/agent-responses")
async def get_agent_responses(limit: int = 60):
    """Get recent agent progress updates for chat display"""
    try:
        mongo_client = get_mongo_client()
        db = mongo_client.get_database()
        
        # Get recent progress updates from all agents
        messages = list(
            db.progress_updates.find().sort("timestamp", -1).limit(limit)
        )
        
        # Format for chat display
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({
                "id": str(msg.get("_id")),
                "agent_id": msg.get("agent_id", "unknown"),
                "message": msg.get("message", ""),
                "progress_percent": msg.get("progress_percent", 0),
                "timestamp": msg.get("timestamp").isoformat() if msg.get("timestamp") else None,
                "task_id": msg.get("task_id"),
                "task": {
                    "title": msg.get("task_title", ""),
                    "status": msg.get("task_status", "")
                } if msg.get("task_title") else None
            })
        
        mongo_client.close()
        
        return {"messages": formatted_messages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/tasks")
async def list_tasks(status: Optional[str] = None, limit: int = 50):
    """List tasks with optional status filter"""
    try:
        conn = get_postgres_conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        if status:
            cur.execute(
                """
                SELECT id, title, status, created_at, updated_at
                FROM tasks
                WHERE status = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (status, limit)
            )
        else:
            cur.execute(
                """
                SELECT id, title, status, created_at, updated_at
                FROM tasks
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,)
            )
        
        tasks = cur.fetchall()
        cur.close()
        conn.close()
        
        return {"tasks": tasks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/vnc-proxy/{agent_id}/{path:path}")
async def vnc_proxy(agent_id: str, path: str, request: Request):
    """
    Proxy VNC requests to strip X-Frame-Options header
    This allows embedding VNC in iframes
    """
    # Get VNC URL for the agent
    vnc_urls = {
        "agent1": os.getenv("AGENT1_VNC_URL", "https://m-linux-aqnzbmas97.containers.cloud.trycua.com"),
        "agent2": os.getenv("AGENT2_VNC_URL", "https://m-linux-aqnzbmas97.containers.cloud.trycua.com"),
        "agent3": os.getenv("AGENT3_VNC_URL", "https://m-linux-aqnzbmas97.containers.cloud.trycua.com"),
    }
    
    base_url = vnc_urls.get(agent_id)
    if not base_url:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    # Build target URL
    target_url = f"{base_url}/{path}"
    if request.url.query:
        target_url = f"{target_url}?{request.url.query}"
    
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            # Forward the request
            response = await client.get(
                target_url,
                headers={k: v for k, v in request.headers.items() if k.lower() not in ['host', 'connection']}
            )
            
            # Strip security headers that prevent iframe embedding
            headers = dict(response.headers)
            headers.pop('x-frame-options', None)
            headers.pop('content-security-policy', None)
            headers.pop('x-content-type-options', None)
            
            # Return response with modified headers
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=headers,
                media_type=response.headers.get('content-type')
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Proxy error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

