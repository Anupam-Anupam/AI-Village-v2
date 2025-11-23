"""
Lean trajectory processor - watches CUA trajectory files and stores in MongoDB.
"""
import json
import base64
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Import db_adapters - try absolute first (for direct execution), then relative (for package import)
try:
    from db_adapters import MongoClientWrapper
except ImportError:
    try:
        from .db_adapters import MongoClientWrapper
    except ImportError:
        # Last resort: add current directory to path
        import sys
        from pathlib import Path
        current_dir = Path(__file__).parent
        if str(current_dir) not in sys.path:
            sys.path.insert(0, str(current_dir))
        from db_adapters import MongoClientWrapper


class TrajectoryProcessor(FileSystemEventHandler):
    """Processes CUA trajectory files in real-time and stores in MongoDB."""
    
    def __init__(self, trajectory_dir: Path, mongo_client: MongoClientWrapper, task_id: Optional[int] = None):
        self.trajectory_dir = Path(trajectory_dir)
        self.mongo = mongo_client
        self.task_id = task_id
        self.processed_files = set()
        
        # Ensure directory exists
        self.trajectory_dir.mkdir(parents=True, exist_ok=True)
        
        # Process existing files
        self._process_existing()
    
    def _extract_messages_from_json(self, data: Dict[str, Any]) -> List[str]:
        """Extract all meaningful messages/results from JSON data using multiple schema patterns."""
        messages = []
        
        if not isinstance(data, dict):
            return messages
        
        # Schema 1: response.output structure
        if "response" in data:
            response = data["response"]
            if isinstance(response, dict) and "output" in response:
                output = response["output"]
                if isinstance(output, list):
                    for item in output:
                        if isinstance(item, dict) and item.get("type") == "message":
                            content = item.get("content", [])
                            if isinstance(content, list):
                                for content_item in content:
                                    if isinstance(content_item, dict):
                                        # Try output_text type
                                        if content_item.get("type") == "output_text":
                                            text = content_item.get("text")
                                            if isinstance(text, str) and text.strip():
                                                messages.append(text.strip())
                                        # Try direct text field
                                        elif "text" in content_item:
                                            text = content_item.get("text")
                                            if isinstance(text, str) and text.strip():
                                                messages.append(text.strip())
        
        # Schema 2: direct output structure
        if "output" in data:
            output = data["output"]
            if isinstance(output, list):
                for item in output:
                    if isinstance(item, dict) and item.get("type") == "message":
                        content = item.get("content", [])
                        if isinstance(content, list):
                            for content_item in content:
                                if isinstance(content_item, dict):
                                    # Try output_text type
                                    if content_item.get("type") == "output_text":
                                        text = content_item.get("text")
                                        if isinstance(text, str) and text.strip():
                                            messages.append(text.strip())
                                    # Try direct text field
                                    elif "text" in content_item:
                                        text = content_item.get("text")
                                        if isinstance(text, str) and text.strip():
                                            messages.append(text.strip())
                        # Also check if content is a string directly
                        elif isinstance(content, str) and content.strip():
                            messages.append(content.strip())
        
        # Schema 3: role-based messages (assistant role)
        if data.get("role") == "assistant":
            if "content" in data:
                content = data["content"]
                if isinstance(content, str) and content.strip():
                    messages.append(content.strip())
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and "text" in item:
                            text = item.get("text")
                            if isinstance(text, str) and text.strip():
                                messages.append(text.strip())
                        elif isinstance(item, str) and item.strip():
                            messages.append(item.strip())
        
        # Schema 4: direct text/result fields
        for field in ["text", "result", "message", "content", "response_text"]:
            if field in data:
                value = data[field]
                if isinstance(value, str) and value.strip():
                    messages.append(value.strip())
                elif isinstance(value, dict) and "text" in value:
                    text = value.get("text")
                    if isinstance(text, str) and text.strip():
                        messages.append(text.strip())
        
        # Schema 5: nested result/response structures
        if "result" in data and isinstance(data["result"], dict):
            result = data["result"]
            if "text" in result:
                text = result.get("text")
                if isinstance(text, str) and text.strip():
                    messages.append(text.strip())
            if "output" in result:
                output = result["output"]
                if isinstance(output, str) and output.strip():
                    messages.append(output.strip())
        
        return messages
    
    def _process_existing(self):
        """Process any existing trajectory files."""
        if not self.trajectory_dir.exists():
            return
        
        for file_path in self.trajectory_dir.rglob("*.json"):
            if str(file_path) not in self.processed_files:
                self._process_file(file_path)
    
    def _process_file(self, file_path: Path):
        """Process a single trajectory file."""
        if str(file_path) in self.processed_files:
            return
        
        try:
            print(f"[TrajectoryProcessor] Processing file: {file_path}")
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.processed_files.add(str(file_path))
            print(f"[TrajectoryProcessor] File loaded, keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
            
            # Extract meaningful messages/results from JSON
            extracted_messages = []
            if isinstance(data, dict):
                extracted_messages = self._extract_messages_from_json(data)
                
                # Log each extracted message
                for msg in extracted_messages:
                    if msg:  # Only log non-empty messages
                        print(f"[TrajectoryProcessor] Extracted message: {msg[:100]}...")
                        self.mongo.write_log(
                            task_id=self.task_id,
                            level="info",
                            message=msg,
                            meta={"type": "agent_response", "source": "trajectory", "file": file_path.name}
                        )
                
                # Extract agent responses from output (legacy support)
                if "output" in data:
                    for item in data.get("output", []):
                        if item.get("type") == "message":
                            content = item.get("content", [])
                            for cp in content:
                                if isinstance(cp, dict):
                                    # Check for image in content
                                    image_url = cp.get("image_url") or cp.get("image")
                                    if image_url and isinstance(image_url, str):
                                        print(f"[TrajectoryProcessor] Found image in content: {image_url[:50]}...")
                                        if image_url.startswith("data:image"):
                                            self._store_screenshot_base64(image_url)
                                        elif Path(image_url).exists():
                                            self._store_screenshot(image_url)
                
                # Extract screenshots from computer_call_output
                if "type" in data and data.get("type") == "computer_call_output":
                    screenshot_path = data.get("screenshot_path") or data.get("image_path")
                    if screenshot_path:
                        print(f"[TrajectoryProcessor] Found screenshot_path: {screenshot_path}")
                        self._store_screenshot(screenshot_path)
                    
                    image_data = data.get("image") or data.get("screenshot")
                    if image_data and isinstance(image_data, str) and image_data.startswith("data:image"):
                        print(f"[TrajectoryProcessor] Found base64 image in computer_call_output")
                        self._store_screenshot_base64(image_data)
                
                # Check for nested trajectory data
                if "trajectory" in data:
                    self._process_trajectory_data(data["trajectory"])
            
            # Store a summary log entry (only if no messages were extracted, to avoid duplicate logs)
            if not extracted_messages:
                self.mongo.write_log(
                    task_id=self.task_id,
                    level="debug",
                    message=f"Trajectory processed: {file_path.name}",
                    meta={"trajectory_file": str(file_path), "data": data}
                )
            else:
                # Store a brief summary log with count of messages extracted
                self.mongo.write_log(
                    task_id=self.task_id,
                    level="debug",
                    message=f"Trajectory processed: {file_path.name} ({len(extracted_messages)} messages extracted)",
                    meta={"trajectory_file": str(file_path), "messages_count": len(extracted_messages)}
                )
            
        except Exception as e:
            print(f"Error processing trajectory {file_path}: {e}")
    
    def _store_screenshot(self, image_path: str):
        """Store screenshot from file path."""
        try:
            path = Path(image_path)
            if not path.exists():
                # Try relative to trajectory_dir
                path = self.trajectory_dir / image_path
                if not path.exists():
                    return
            
            with open(path, "rb") as f:
                image_data = f.read()
            
            screenshot_id = self.mongo.store_screenshot(
                task_id=self.task_id,
                image_data=image_data,
                filename=path.name
            )
            print(f"[TrajectoryProcessor] ✅ Stored screenshot: {screenshot_id} ({len(image_data)} bytes)")
        except Exception as e:
            print(f"Error storing screenshot {image_path}: {e}")
    
    def _store_screenshot_base64(self, base64_data: str):
        """Store screenshot from base64 data URL."""
        try:
            # Extract base64 part from data URL
            if "," in base64_data:
                base64_part = base64_data.split(",", 1)[1]
            else:
                base64_part = base64_data
            
            image_data = base64.b64decode(base64_part)
            
            screenshot_id = self.mongo.store_screenshot(
                task_id=self.task_id,
                image_data=image_data,
                filename=f"screenshot_{datetime.utcnow().isoformat()}.png"
            )
            print(f"[TrajectoryProcessor] ✅ Stored base64 screenshot: {screenshot_id} ({len(image_data)} bytes)")
        except Exception as e:
            print(f"Error storing base64 screenshot: {e}")
    
    def _process_trajectory_data(self, trajectory_data: Any):
        """Recursively process nested trajectory data."""
        if isinstance(trajectory_data, dict):
            # Check for screenshots
            for key in ["screenshot", "image", "screenshot_path", "image_path"]:
                if key in trajectory_data:
                    value = trajectory_data[key]
                    if isinstance(value, str):
                        if value.startswith("data:image"):
                            self._store_screenshot_base64(value)
                        elif Path(value).exists():
                            self._store_screenshot(value)
            
            # Recursively process nested dicts
            for value in trajectory_data.values():
                if isinstance(value, (dict, list)):
                    self._process_trajectory_data(value)
        elif isinstance(trajectory_data, list):
            for item in trajectory_data:
                if isinstance(item, (dict, list)):
                    self._process_trajectory_data(item)
    
    def on_created(self, event):
        """Handle new file creation."""
        if event.is_directory:
            return
        
        if event.src_path.endswith('.json'):
            self._process_file(Path(event.src_path))
    
    def on_modified(self, event):
        """Handle file modification."""
        if event.is_directory:
            return
        
        if event.src_path.endswith('.json'):
            self._process_file(Path(event.src_path))


def start_processor(trajectory_dir: Path, mongo_client: MongoClientWrapper, task_id: Optional[int] = None) -> Observer:
    """Start watching trajectory directory."""
    processor = TrajectoryProcessor(trajectory_dir, mongo_client, task_id)
    observer = Observer()
    observer.schedule(processor, str(trajectory_dir), recursive=True)
    observer.start()
    return observer

