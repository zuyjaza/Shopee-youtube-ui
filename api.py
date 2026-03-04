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
job_queue: deque = deque()          # Hàng đợi chờ xử lý: [{"job_id", "url", "sub_id"}]
job_results: dict = {}              # Kết quả: {job_id: {"status", "youtube_link", "error"}}
emulator_commands: deque = deque()  # Hàng đợi lệnh cho Emulator: ["RELOAD", ...]

# --- THAY ĐỔI LINK CỦA BẠN TẠI ĐÂY ---
ZALO_LINK = "https://zalo.me/g/svkgoi169"
YOUTUBE_LINK = "https://youtube.com/shopcollection/SCUCRmBaJUNvFvMmbln7TBzmH7gk5YXlO3wJA?si=4_mkvFsa9v0KPjHt"

# --- Thống kê ---
global_stats = {
    "total_requests": 0,
    "completed_jobs": 0,
    "errors": 0,
    "start_time": time.time()
}


class LinkRequest(BaseModel):
    url: str
    sub_id: str = ""

class YoutubeResponse(BaseModel):
    job_id: str
    yt_link: str
    error: str | None = None


@app.post("/request-conversion")
async def request_conversion(req: LinkRequest):
    """Streamlit gọi để yêu cầu convert 1 link. Trả về job_id."""
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
        "shopee_url": req.url,
        "detailed_status": "",
        "created_at": time.time()
    }
    return {"job_id": job_id, "status": "pending"}


@app.get("/get-pending-link")
async def get_pending_link():
    """Extension polling để lấy job tiếp theo trong queue."""
    try:
        now = time.time()

        # Dọn job cũ quá TTL
        while job_queue and (now - job_queue[0]["created_at"] > JOB_TTL):
            old = job_queue.popleft()
            if job_results.get(old["job_id"], {}).get("status") in ("pending", "processing"):
                job_results[old["job_id"]] = {"status": "error", "youtube_link": None, "error": "Hết thời gian chờ", "created_at": old["created_at"]}

        # --- KIỂM TRA XỬ LÝ TUẦN TỰ ---
        for job in job_queue:
            if job_results.get(job["job_id"], {}).get("status") == "processing":
                # Kiểm tra xem job này có bị stuck không (quá 90s)
                elapsed = now - job.get("picked_at", now)
                if elapsed > 90:
                    print(f"⚠️ Job {job['job_id']} bị stuck, reset về pending.")
                    if job["job_id"] in job_results:
                        job_results[job["job_id"]]["status"] = "pending"
                    job.pop("picked_at", None)
                else:
                    return {"has_link": False, "status": "processing"}

        # Tìm job đầu tiên "pending" để cấp cho bot
        for job in job_queue:
            job_id = job["job_id"]
            if job_results.get(job_id, {}).get("status") == "pending":
                job_results[job_id]["status"] = "processing"
                job["picked_at"] = now
                return {
                    "has_link": True,
                    "job_id": job_id,
                    "shopee_url": job["url"],
                    "sub_id": job.get("sub_id", "")
                }

        return {"has_link": False}
    except Exception as e:
        print(f"🔥 LỖI SERVER TRONG get_pending_link: {str(e)}")
        return {"has_link": False, "error": str(e)}


@app.post("/submit-youtube-link")
async def submit_youtube_link(res: YoutubeResponse):
    """Extension trả kết quả về kèm job_id."""
    job_id = res.job_id
    if job_id not in job_results:
        raise HTTPException(status_code=404, detail="Job not found")

    # Xoá job khỏi queue
    for i, job in enumerate(job_queue):
        if job["job_id"] == job_id:
            del job_queue[i]
            break

    yt_link = res.yt_link
    if yt_link.startswith("ERROR:"):
        error_msg = yt_link.replace("ERROR:", "").strip()
        job_results[job_id].update({
            "status": "error", 
            "youtube_link": None, 
            "error": error_msg, 
            "shopee_url": job_results[job_id].get("shopee_url")
        })
    else:
        # Nếu yt_link là "SUCCESS" hoặc link thật, coi là Complete
        job_results[job_id].update({
            "status": "complete", 
            "youtube_link": yt_link, 
            "error": None
        })
        global_stats["completed_jobs"] += 1

    return {"message": "Result received"}


@app.get("/check-status")
async def check_status(job_id: str):
    """Streamlit kiểm tra tiến độ theo job_id."""
    if job_id not in job_results:
        raise HTTPException(status_code=404, detail="Job not found")
    
    result = job_results[job_id]
    now = time.time()
    created_at = result.get("created_at", now)

    # --- KIỂM TRA TIMEOUT 30 GIÂY ---
    if result["status"] in ("pending", "processing") and (now - created_at) > 30:
        result["status"] = "error"
        result["error"] = "Lỗi gắn mã, vui lòng thử lại"
        # Xoá khỏi queue nếu còn
        for i, job in enumerate(job_queue):
            if job["job_id"] == job_id:
                del job_queue[i]
                break
    # Tính vị trí trong hàng đợi
    queue_pos = 0
    if result["status"] == "pending":
        for i, q_job in enumerate(job_queue):
            if q_job["job_id"] == job_id:
                queue_pos = i + 1
                break
    
    return {
        "status": result["status"],
        "youtube_link": result["youtube_link"],
        "error": result["error"],
        "shopee_url": result.get("shopee_url"),
        "detailed_status": result.get("detailed_status", ""),
        "queue_position": queue_pos
    }

@app.post("/submit-detailed-status")
async def submit_detailed_status(data: dict):
    job_id = data.get("job_id")
    message = data.get("message")
    if job_id in job_results:
        job_results[job_id]["detailed_status"] = message
        return {"ok": True}
    return {"ok": False, "error": "Job not found"}

@app.get("/get-tagged-job")
async def get_tagged_job():
    """Emulator polling để lấy job đã được gắn thẻ thành công."""
    for job_id, res in job_results.items():
        if res["status"] == "tagged":
            # Chuyển sang extracting để tránh job khác lấy trùng
            res["status"] = "extracting"
            return {
                "has_job": True,
                "job_id": job_id,
                "shopee_url": res.get("shopee_url")
            }
    return {"has_job": False}

@app.post("/submit-final-link")
async def submit_final_link(res: YoutubeResponse):
    """Emulator trả kết quả link affiliate cuối cùng."""
    job_id = res.job_id
    if job_id not in job_results:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if res.error:
        job_results[job_id].update({"status": "error", "error": res.error})
        global_stats["errors"] += 1
    else:
        job_results[job_id].update({"status": "complete", "youtube_link": res.yt_link, "error": None})
        global_stats["completed_jobs"] += 1
    
    return {"message": "Final result received"}


@app.post("/submit-cleanup-done")
async def submit_cleanup_done(data: dict):
    """Extension gọi sau khi Dọn dẹp xong để báo Emulator chuẩn bị."""
    job_id = data.get("job_id")
    print(f"🧹 Cleanup DONE for job {job_id}. Queueing RELOAD for Emulator.")
    emulator_commands.append("RELOAD_YOUTUBE")
    return {"message": "Cleanup signal received"}

@app.get("/get-emulator-command")
async def get_emulator_command():
    """Emulator polling để lấy lệnh đặc biệt (như RELOAD)."""
    if emulator_commands:
        cmd = emulator_commands.popleft()
        return {"has_command": True, "command": cmd}
    return {"has_command": False}


@app.get("/stats")
async def get_stats():
    """Xem thống kê lượt nhập link."""
    uptime_sec = time.time() - global_stats["start_time"]
    uptime_min = round(uptime_sec / 60, 1)
    return {
        "tong_luot_nhap_link": global_stats["total_requests"],
        "so_link_thanh_cong": global_stats["completed_jobs"],
        "so_link_bi_loi": global_stats["errors"],
        "thoi_gian_server_chay_phut": uptime_min,
        "ghi_chu": "Du lieu se reset khi Server Render khoi dong lai."
    }


@app.get("/debug")
async def debug_state():
    """Xem trạng thái bộ nhớ hiện tại (debug)."""
    return {
        "job_queue_len": len(job_queue),
        "job_queue": list(job_queue),
        "job_results": job_results
    }

@app.get("/reset-all")
async def reset_all():
    """Reset sạch sẽ hàng đợi và kết quả."""
    job_queue.clear()
    job_results.clear()
    return {"message": "Đã reset sạch sẽ hệ thống."}


# --- Trang Giao diện Siêu nhẹ (Zalo Compatible) ---
@app.get("/", response_class=HTMLResponse)
async def get_ui():
    html_content = f"""
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
            font-size: 3rem;
            margin: 20px 0;
            display: flex;
            flex-direction: row;
            align-items: center;
            justify-content: center;
            gap: 15px;
            width: 100%;
            white-space: nowrap;
        }}
        @media (max-width: 480px) {{
            .header-title {{ font-size: 1.8rem; gap: 8px; }}
        }}
        .btn-zalo {{
            background-color: #0068ff;
            color: white;
            padding: 12px;
            border-radius: 8px;
            text-align: center;
            font-weight: 700;
            margin-bottom: 12px;
            text-decoration: none;
            display: block;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .btn-yt {{
            background-color: #ff0000;
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
            display: none;
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
            <svg class="yt-icon" viewBox="0 0 2859 2000" style="width: 45px; height: 45px; flex-shrink: 0;">
                <path fill="#FF0000" d="M2790.8 311.2c-32.3-121.1-127.1-216-248.2-248.2C2323.9 0 1429.5 0 1429.5 0S535 0 316.4 63C195.3 95.2 100.5 190.1 68.2 311.2 0 529.8 0 985 0 985s0 455.2 68.2 673.8c32.3 121.1 127.1 216 248.2 248.2 218.6 63 1113.1 63 1113.1 63s894.4 0 1113.1-63c121.1-32.3 216-127.1 248.2-248.2 68.2-218.6 68.2-673.8 68.2-673.8s0-455.2-68.2-673.8"/>
                <path fill="#FFF" d="M1142.4 1416.3l742.8-431.3-742.8-431.3z"/>
            </svg>
            <span>Mã YouTube Shopee</span>
        </div>

        <a href="{ZALO_LINK}" target="_blank" class="btn-zalo">💬 THAM GIA NHÓM ZALO</a>

        <div class="input-group">
            <label>Dán link Shopee vào đây:</label>
            <input type="text" id="shopee-url" placeholder="https://vn.shp.ee/...">
            <button id="convert-btn" onclick="startConversion()">⚡ Gắn Mã</button>
        </div>

        <div id="status-box" class="status-box"></div>

        <div id="result-area" class="result-area">
            <div id="result-link" class="result-link"></div>
            <div class="action-btns">
                <a id="open-link" href="#" target="_blank" class="btn-action btn-open">🌍 Mở Link Lấy Mã</a>
                <button class="btn-action btn-copy" onclick="copyLink()">📋 Copy Link</button>
            </div>
        </div>
    </div>

    <script>
        let currentJobId = null;
        let pollInterval = null;
        let startTime = null;

        async function startConversion() {{
            const urlInput = document.getElementById('shopee-url');
            const url = urlInput.value.trim();
            if (!url) return alert('Vui lòng nhập link Shopee!');

            // Link Validation
            const isVideo = url.includes('?smtt=0');
            const isValidFormat = url.toLowerCase().includes('vn.shp.ee') || url.toLowerCase().includes('s.shopee.vn');

            if (isVideo) {{
                showStatus('⚠️ Vui lòng nhập link sản phẩm, đây là Link video.', 'error');
                return;
            }}
            if (!isValidFormat) {{
                showStatus('❌ vui lòng nhập đúng link sản phẩm shopee', 'error');
                return;
            }}

            const btn = document.getElementById('convert-btn');
            btn.disabled = true;
            btn.innerText = '⌛ ĐANG XỬ LÝ...';

            showStatus('⌛ Đã gửi yêu cầu, đang chờ xử lý...', 'pending');
            document.getElementById('result-area').style.display = 'none';

            try {{
                const response = await fetch('/request-conversion', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ url: url }})
                }});
                const data = await response.json();
                currentJobId = data.job_id;
                startTime = Date.now(); // Bắt đầu đếm ngược 30s
                
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
                const response = await fetch(`/check-status?job_id=${{currentJobId}}`);
                const data = await response.json();

                // Kiểm tra Timeout ở phía Client (30 giây)
                const elapsed = (Date.now() - startTime) / 1000;
                
                if (data.status === 'complete') {{
                    clearInterval(pollInterval);
                    showStatus('✅ GẮN MÃ THÀNH CÔNG!', 'success');
                    showResult(data.youtube_link);
                    resetButton();
                }} else if (data.status === 'error' || elapsed > 30) {{
                    clearInterval(pollInterval);
                    const errorMsg = elapsed > 30 ? 'Lỗi gắn mã, vui lòng thử lại' : data.error;
                    showStatus('❌ LỖI: ' + errorMsg, 'error');
                    resetButton();
                }} else {{
                    // Chỉ hiển thị hàng đợi, ẩn chi tiết
                    let msg = '⏳ Đang chờ xử lý...';
                    if (data.queue_position > 0) msg = `⏳ Bạn đang ở vị trí thứ ${{data.queue_position}} trong hàng đợi.`;
                    showStatus(msg, 'pending');
                }}
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
    return html_content

if __name__ == "__main__":
    import uvicorn
    # Chạy trên 0.0.0.0 để Chrome Extension dễ kết nối
    uvicorn.run(app, host="0.0.0.0", port=8002)
