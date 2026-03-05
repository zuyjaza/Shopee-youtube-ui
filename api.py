from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uuid
import time
from collections import deque

app = FastAPI(title="YouTube Shopping Extension API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Hàng đợi và kết quả theo job_id ---
JOB_TTL = 180                       # Thời gian chờ tối đa (giây)
job_queue: deque = deque()          # Hàng đợi chờ xử lý
job_results: dict = {}              # Kết quả: {job_id: {"status", "youtube_link", "error"}}

# --- Thống kê ---
global_stats = {
    "total_requests": 0,
    "completed_jobs": 0,
    "errors": 0,
    "start_time": time.time(),
    "last_bot_heartbeat": 0  # Theo dõi lần cuối bot (Extension/Phone) kết nối
}

class LinkRequest(BaseModel):
    url: str
    sub_id: str = ""

class YoutubeResponse(BaseModel):
    job_id: str
    yt_link: str | None = None
    error: str | None = None

@app.post("/request-conversion")
async def request_conversion(req: LinkRequest):
    # Kiểm tra xem hệ thống có đang hoạt động không (Bot có online trong 30s qua không)
    if time.time() - global_stats["last_bot_heartbeat"] > 30:
        return {"job_id": None, "status": "maintenance", "error": "Hệ thống đang bảo trì"}
    
    job_id = str(uuid.uuid4())
    job_queue.append({
        "job_id": job_id,
        "url": req.url,
        "sub_id": req.sub_id,
        "created_at": time.time()
    })
    global_stats["total_requests"] += 1
    job_results[job_id] = {
        "status": "pending", 
        "youtube_link": None, 
        "error": None,
        "created_at": time.time()
    }
    return {"job_id": job_id, "status": "pending"}

@app.get("/get-pending-link")
async def get_pending_link():
    now = time.time()
    global_stats["last_bot_heartbeat"] = now  # Cập nhật heartbeat khi có bot kết nối
    # Tìm job đầu tiên "pending"
    for job in job_queue:
        job_id = job["job_id"]
        if job_results.get(job_id, {}).get("status") == "pending":
            job_results[job_id]["status"] = "processing"
            return job
    return {}  # Trả về dict rỗng thay vì None để bot cũ không bị lỗi NoneType

@app.post("/submit-youtube-link")
async def submit_youtube_link(res: YoutubeResponse):
    job_id = res.job_id
    if job_id not in job_results:
        return {"ok": False, "error": "Job not found"}
    
    if res.error:
        job_results[job_id].update({"status": "error", "error": res.error})
        global_stats["errors"] += 1
    else:
        job_results[job_id].update({"status": "complete", "youtube_link": res.yt_link, "error": None})
        global_stats["completed_jobs"] += 1
    
    # Xoá khỏi queue sau khi xong
    global job_queue
    job_queue = deque([j for j in job_queue if j["job_id"] != job_id])
    
    return {"ok": True}

@app.get("/get-job-status/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in job_results:
        return {"status": "not_found"}
    return job_results[job_id]

@app.get("/stats")
async def get_stats():
    uptime_min = round((time.time() - global_stats["start_time"]) / 60, 1)
    return {
        "total": global_stats["total_requests"],
        "completed": global_stats["completed_jobs"],
        "errors": global_stats["errors"],
        "uptime_min": uptime_min,
        "queue_size": len(job_queue)
    }

@app.get("/", response_class=HTMLResponse)
async def get_ui():
    # Kiểm tra trạng thái hệ thống ngay khi load trang
    is_maintenance = time.time() - global_stats["last_bot_heartbeat"] > 30
    status_msg = "⚠️ Đang Bảo Trì Hệ Thống. Vui lòng quay lại sau!" if is_maintenance else ""
    status_type = "error"
    display_style = "block" if is_maintenance else "none"

    return f"""
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mã YouTube Shopee</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #f0f2f5;
            color: #31333f;
            margin: 0;
            padding: 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }}
        .container {{
            max-width: 600px;
            width: 100%;
        }}
        .header-title {{
            color: #212121;
            text-align: center;
            font-weight: 900;
            font-size: 2.5rem;
            margin: 20px 0;
            display: flex;
            flex-direction: row;
            align-items: center;
            justify-content: center;
            gap: 15px;
            width: 100%;
            white-space: nowrap;
        }}
        .btn-zalo {{
            background-color: #0068ff;
            color: white;
            padding: 12px;
            border-radius: 8px;
            text-align: center;
            font-weight: 700;
            margin-bottom: 20px;
            text-decoration: none;
            display: block;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .input-group {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        label {{
            display: block;
            font-size: 0.9rem;
            margin-bottom: 8px;
            font-weight: 500;
        }}
        input {{
            width: 100%;
            padding: 12px;
            border: 2px solid #ff0000;
            border-radius: 6px;
            box-sizing: border-box;
            font-size: 1rem;
            margin-bottom: 15px;
            background-color: #f8f9fa;
        }}
        button#convert-btn {{
            background-color: #ff0000;
            color: white;
            border: none;
            padding: 12px 25px;
            border-radius: 6px;
            font-weight: 700;
            cursor: pointer;
            font-size: 1rem;
            width: 100%;
            transition: background 0.2s;
        }}
        button#convert-btn:disabled {{
            background-color: #ccc;
        }}
        .status-box {{
            padding: 15px;
            border-radius: 8px;
            margin-top: 20px;
            display: {display_style};
        }}
        .status-pending {{ background-color: #fff3cd; color: #856404; border: 1px solid #ffeeba; }}
        .status-success {{ background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; }}
        .status-error {{ background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }}
        .result-area {{
            margin-top: 15px;
            display: none;
        }}
        .result-link {{
            word-break: break-all;
            background: #eee;
            padding: 10px;
            border-radius: 4px;
            font-family: monospace;
            margin-bottom: 10px;
        }}
        .action-btns {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }}
        .btn-action {{
            padding: 10px;
            border-radius: 6px;
            text-align: center;
            text-decoration: none;
            font-weight: 600;
            font-size: 0.9rem;
        }}
        .btn-copy {{ background: #28a745; color: white; border: none; cursor: pointer; }}
        .btn-open {{ background: #ff0000; color: white; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header-title">
            <svg viewBox="0 0 24 24" width="48" height="48" fill="#ff0000"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>
            <span>Mã YouTube Shopee</span>
        </div>

        <a href="https://zalo.me/g/svkgoi169" target="_blank" class="btn-zalo">💬 THAM GIA NHÓM ZALO HỖ TRỢ</a>

        <div class="input-group">
            <label>Dán Link sản phẩm cần lấy mã vào đây 👇</label>
            <input type="text" id="shopee-url" placeholder="https://vn.shp.ee/..." {"disabled" if is_maintenance else ""}>
            <button id="convert-btn" onclick="startConversion()" {"disabled" if is_maintenance else ""}>⚡ Gắn Mã</button>
        </div>

        <div id="status-box" class="status-box status-{status_type}">{status_msg}</div>

        <div id="result-area" class="result-area">
            <div id="result-link" class="result-link"></div>
            <div class="action-btns">
                <a id="open-link" href="#" target="_blank" class="btn-action btn-open">🌍 Mở Link</a>
                <button class="btn-action btn-copy" onclick="copyLink()">📋 Copy Link</button>
            </div>
        </div>
    </div>

    <script>
        let currentJobId = null;
        let pollInterval = null;

        async function startConversion() {{
            const urlInput = document.getElementById('shopee-url');
            const url = urlInput.value.trim();
            if (!url) return alert('Vui lòng nhập link Shopee!');

            const btn = document.getElementById('convert-btn');
            btn.disabled = true;
            btn.innerText = '⌛ ĐANG XỬ LÝ...';

            showStatus('⌛ Đang chờ xử lý... từ 10-20s', 'pending');
            document.getElementById('result-area').style.display = 'none';

            try {{
                const response = await fetch('/request-conversion', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ url: url }})
                }});
                const data = await response.json();
                
                if (data.status === 'maintenance') {{
                    showStatus('⚠️ Đang Bảo Trì Hệ Thống. Vui lòng quay lại sau!', 'error');
                    resetButton();
                    return;
                }}
                
                currentJobId = data.job_id;
                
                if (pollInterval) clearInterval(pollInterval);
                pollInterval = setInterval(checkStatus, 2000);
            }} catch (err) {{
                showStatus('❌ Lỗi kết nối Server!', 'error');
                resetButton();
            }}
        }}

        async function checkStatus() {{
            if (!currentJobId) return;

            try {{
                const response = await fetch('/get-job-status/' + currentJobId);
                const data = await response.json();
                
                if (data.status === 'complete') {{
                    clearInterval(pollInterval);
                    showStatus('✅ GẮN MÃ THÀNH CÔNG!', 'success');
                    showResult(data.youtube_link);
                    resetButton();
                }} else if (data.status === 'error') {{
                    clearInterval(pollInterval);
                    showStatus('❌ LỖI: ' + data.error, 'error');
                    resetButton();
                }}
                // Nếu đang xử lý (pending/processing), hàm showStatus đã được gọi ở startConversion() với text 'Đang chờ xử lý...'
            }} catch (err) {{
                console.error('Polling error:', err);
            }}
        }}

        function showStatus(msg, type) {{
            const box = document.getElementById('status-box');
            box.style.display = 'block';
            box.innerText = msg;
            box.className = 'status-box status-' + type;
        }}

        function showResult(link) {{
            const area = document.getElementById('result-area');
            area.style.display = 'block';
            document.getElementById('result-link').innerText = link;
            document.getElementById('open-link').href = link;
        }}

        function resetButton() {{
            const btn = document.getElementById('convert-btn');
            btn.disabled = false;
            btn.innerText = '⚡ Gắn Mã';
        }}

        function copyLink() {{
            const link = document.getElementById('result-link').innerText;
            navigator.clipboard.writeText(link).then(() => {{
                alert('Đã chép mã thành công!');
            }});
        }}
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    import uvicorn
    # Production: chạy trên 0.0.0.0 để Render expose ra internet
    print("🚀 API Server đang chạy ở chế độ PRODUCTION (Render).")
    uvicorn.run(app, host="0.0.0.0", port=8002)
