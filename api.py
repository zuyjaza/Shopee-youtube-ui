from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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
job_queue: deque = deque()          # Hàng đợi chờ xử lý: [{"job_id", "url", "sub_id"}]
job_results: dict = {}              # Kết quả: {job_id: {"status", "youtube_link", "error"}}
emulator_commands: deque = deque()  # Hàng đợi lệnh cho Emulator: ["RELOAD", ...]
JOB_TTL = 300                       # Giữ kết quả tối đa 5 phút
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
        "detailed_status": ""
    }
    return {"job_id": job_id, "status": "pending"}


@app.get("/get-pending-link")
async def get_pending_link():
    """Extension polling để lấy job tiếp theo trong queue."""
    now = time.time()

    # Dọn job cũ quá TTL
    while job_queue and now - job_queue[0]["created_at"] > JOB_TTL:
        old = job_queue.popleft()
        if job_results.get(old["job_id"], {}).get("status") in ("pending", "processing"):
            job_results[old["job_id"]] = {"status": "error", "youtube_link": None, "error": "Hết thời gian chờ"}

    # Tìm job đầu tiên có status "pending" trong queue
    # (bỏ qua job đang "processing" để tránh bị block)
    for job in job_queue:
        job_id = job["job_id"]
        status = job_results.get(job_id, {}).get("status")

        # Reset job bị stuck quá 90s ở processing → cho thử lại
        if status == "processing":
            elapsed = now - job.get("picked_at", now)
            if elapsed > 90:
                job_results[job_id]["status"] = "pending"
                job.pop("picked_at", None)
                status = "pending"

        if status == "pending":
            job_results[job_id]["status"] = "processing"
            job["picked_at"] = now
            return {
                "has_link": True,
                "job_id": job_id,
                "shopee_url": job["url"],
                "sub_id": job.get("sub_id", "")
            }

    return {"has_link": False}


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

if __name__ == "__main__":
    import uvicorn
    # Chạy trên 0.0.0.0 để Chrome Extension dễ kết nối
    uvicorn.run(app, host="0.0.0.0", port=8002)
