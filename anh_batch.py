import hashlib
import json
import os
import sys
import threading
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import uuid
import base64

from flask import abort, jsonify, render_template, request, send_from_directory

CONTENT = os.path.expanduser("~/content")
DEFAULT_TOPIC = "12-truyen-xua-nhan-qua__chuyen-que-xua"
STATE = ".batch.json"
EP = re.compile(r"^\d{2}-")
NAME = re.compile(r"^[\w.\-]+$")
IMG = re.compile(r"^\d+\.jpg$")
LIST_ROW = re.compile(r"\|\s*\*\*(\d+)\*\*\s*\|\s*`(\d+\.jpg)`")


def _topics():
    out = []
    for t in sorted(os.listdir(CONTENT)):
        p = os.path.join(CONTENT, t)
        if not os.path.isdir(p) or not re.match(r"^\d+-", t):
            continue
        if any(EP.match(e) and os.path.exists(os.path.join(p, e, "bg-prompts.json"))
               for e in os.listdir(p)):
            out.append(t)
    return out


def _dir(topic, tap):
    if not (NAME.match(topic or "") and NAME.match(tap or "")):
        abort(400)
    d = os.path.realpath(os.path.join(CONTENT, topic, tap))
    if not d.startswith(os.path.realpath(CONTENT) + os.sep) or not os.path.isdir(d):
        abort(404)
    return d


def _files(d):
    md = os.path.join(d, "danh-sach-anh-tinh-gon.md")
    if os.path.exists(md):
        ten = [m.group(2) for m in LIST_ROW.finditer(open(md, encoding="utf-8").read())]
        if ten:
            return ten
    bg = os.path.join(d, "bg-prompts.json")
    n = len(json.load(open(bg, encoding="utf-8"))) if os.path.exists(bg) else 0
    return [f"{i:02d}.jpg" for i in range(1, n + 1)]


def _state(d):
    p = os.path.join(d, STATE)
    if not os.path.exists(p):
        return None
    try:
        st = json.load(open(p, encoding="utf-8"))
    except Exception:
        return None
    return st if st.get("batch_id") else None


def _row(topic, d):
    files = _files(d)
    have = [f for f in files if os.path.exists(os.path.join(d, f))]
    st = _state(d)
    cu = os.path.exists(os.path.join(d, STATE)) and not st
    return {"topic": topic, "tap": os.path.basename(d), "total": len(files), "have": len(have), "cu": cu,
            "batch": ({"id": st.get("batch_id"), "gui_luc": st.get("gui_luc"),
                       "model": st.get("model"), "quality": st.get("quality"),
                       "count": len(st.get("files") or [])} if st else None)}


def _api(path, key):
    req = urllib.request.Request("https://api.openai.com/v1" + path,
                                 headers={"Authorization": "Bearer " + key})
    try:
        return urllib.request.urlopen(req, timeout=180).read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:200]}")
    except Exception as e:
        raise RuntimeError(str(e))


def _status(key, st):
    b = json.loads(_api("/batches/" + st["batch_id"], key))
    rc = b.get("request_counts") or {}
    return b, {"status": b.get("status"), "completed": rc.get("completed", 0),
               "fail_n": rc.get("failed", 0), "total": rc.get("total", 0)}


_SENDING = set()
_SEND_LOCK = threading.Lock()


def _gen():
    sc = os.path.join(CONTENT, "scripts")
    if sc not in sys.path:
        sys.path.insert(0, sc)
    import gen_anh
    return gen_anh


def _prompts(d):
    bg = os.path.join(d, "bg-prompts.json")
    if not os.path.exists(bg):
        return []
    theo = {p["shot"]: p["prompt"] for p in json.load(open(bg, encoding="utf-8"))}
    md = os.path.join(d, "danh-sach-anh-tinh-gon.md")
    if os.path.exists(md):
        ra = [(m.group(2), theo[m.group(3)]) for m in re.finditer(
            r"\|\s*\*\*(\d+)\*\*\s*\|\s*`(\d+\.jpg)`\s*\|\s*(\d+\.\d+)\s*\|",
            open(md, encoding="utf-8").read()) if m.group(3) in theo]
        if ra:
            return ra
    return [(f"{i:02d}.jpg", p["prompt"]) for i, p in
            enumerate(json.load(open(bg, encoding="utf-8")), 1)]


def _post_api(path, key, data=None, raw=None, ctype="application/json"):
    req = urllib.request.Request("https://api.openai.com/v1" + path,
                                 data=raw if raw is not None else json.dumps(data).encode(),
                                 method="POST",
                                 headers={"Authorization": "Bearer " + key, "Content-Type": ctype})
    try:
        return urllib.request.urlopen(req, timeout=180).read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:200]}")
    except Exception as e:
        raise RuntimeError(str(e))


def _norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def _title_of(d):
    p = os.path.join(d, "content.md")
    if not os.path.exists(p):
        return ""
    with open(p, encoding="utf-8") as f:
        for _, line in zip(range(60), f):
            if line.startswith("@title"):
                return _norm(line[6:])
    return ""


def _title_index():
    out = []
    for t in _topics():
        base = os.path.join(CONTENT, t)
        for e in sorted(os.listdir(base)):
            d = os.path.join(base, e)
            if EP.match(e) and os.path.isdir(d):
                ti = _title_of(d)
                if ti:
                    out.append((ti, t, e))
    return out


def _save_jpg(b64, dest):
    tmp = dest + ".png"
    with open(tmp, "wb") as f:
        f.write(base64.b64decode(b64))
    try:
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", tmp, "-q:v", "3", dest],
                       check=True, capture_output=True)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def register(app, up_dir, load_key, batches_path):
    def load_reg():
        try:
            with open(batches_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_reg(reg):
        tmp = batches_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(reg, f, ensure_ascii=False, indent=1)
        os.replace(tmp, batches_path)

    @app.route("/anh-batch/api/registry")
    def anh_batch_registry():
        idx = _title_index()
        items = []
        for bid, v in load_reg().items():
            ti = _norm(v.get("title"))
            hit = next(((t, e) for full, t, e in idx if ti and full.startswith(ti)), None)
            items.append({"id": bid, "n": v.get("n"), "model": v.get("model"), "quality": v.get("quality"),
                          "sent": v.get("sent"), "status": v.get("status"), "title": v.get("title"),
                          "lay_ve": v.get("lay_ve"),
                          "suggest": {"topic": hit[0], "tap": hit[1]} if hit else None})
        items.sort(key=lambda x: x.get("sent") or "", reverse=True)
        return jsonify(items=items)

    @app.route("/anh-batch/api/reg_check", methods=["POST"])
    def anh_batch_reg_check():
        bid = (request.get_json(force=True) or {}).get("id")
        reg = load_reg()
        if bid not in reg:
            return jsonify(error="Không thấy batch này trong danh sách."), 404
        key = load_key()
        if not key:
            return jsonify(error="Chưa có key OpenAI (openai_config.json)."), 400
        try:
            _, s = _status(key, {"batch_id": bid})
        except RuntimeError as e:
            return jsonify(error=str(e)), 502
        reg[bid]["status"] = s["status"]
        save_reg(reg)
        return jsonify(s)

    @app.route("/anh-batch/api/reg_fetch", methods=["POST"])
    def anh_batch_reg_fetch():
        j = request.get_json(force=True) or {}
        bid = j.get("id")
        reg = load_reg()
        if bid not in reg:
            return jsonify(error="Không thấy batch này trong danh sách."), 404
        d = _dir(j.get("topic"), j.get("tap"))
        ti, et = _norm(reg[bid].get("title")), _title_of(d)
        if ti and et and not et.startswith(ti) and not j.get("ep"):
            return jsonify(mismatch=True,
                           error=f"Batch này là phim “{ti[:46]}…” nhưng tập {j.get('tap','')[:2]} là “{et[:46]}…”."), 409
        key = load_key()
        if not key:
            return jsonify(error="Chưa có key OpenAI (openai_config.json)."), 400
        try:
            b, s = _status(key, {"batch_id": bid})
            reg[bid]["status"] = s["status"]
            if s["status"] in ("validating", "in_progress", "finalizing", "cancelling"):
                save_reg(reg)
                return jsonify(**s, saved=0, pending=True)
            if not b.get("output_file_id"):
                save_reg(reg)
                return jsonify(error=f"Batch {s['status']}, không có file kết quả.", **s), 409
            out = _api("/files/" + b["output_file_id"] + "/content", key).decode("utf-8")
        except RuntimeError as e:
            return jsonify(error=str(e)), 502
        ghi_de = bool(j.get("ghi_de"))
        saved, skipped, failed = [], [], []
        for line in out.splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            m = re.match(r"^scene_(\d+)$", r.get("custom_id") or "")
            if not m:
                continue
            ten = f"{int(m.group(1)) + 1:02d}.jpg"
            resp = r.get("response") or {}
            if resp.get("status_code") != 200:
                failed.append({"file": ten, "why": str(resp.get("body"))[:140]})
                continue
            dest = os.path.join(d, ten)
            if os.path.exists(dest) and not ghi_de:
                skipped.append(ten)
                continue
            _save_jpg(resp["body"]["data"][0]["b64_json"], dest)
            saved.append(ten)
        reg[bid]["lay_ve"] = {"topic": j.get("topic"), "tap": j.get("tap"),
                              "luc": time.strftime("%Y-%m-%d %H:%M"), "saved": len(saved) + len(skipped)}
        save_reg(reg)
        return jsonify(**s, saved=len(saved), skipped=len(skipped), failed=failed,
                       row=_row(j.get("topic"), d))

    @app.route("/anh-batch")
    def anh_batch_page():
        return render_template("anh_batch.html", default_topic=DEFAULT_TOPIC)

    @app.route("/anh-batch/api/list")
    def anh_batch_list():
        topics = _topics()
        topic = request.args.get("topic") or (DEFAULT_TOPIC if DEFAULT_TOPIC in topics else (topics[0] if topics else ""))
        rows = []
        if topic:
            base = os.path.join(CONTENT, topic)
            seen = {}
            for e in sorted(os.listdir(base)):
                d = os.path.join(base, e)
                if EP.match(e) and os.path.isdir(d) and os.path.exists(os.path.join(d, "bg-prompts.json")):
                    r = _row(topic, d)
                    f0 = next((f for f in _files(d) if os.path.exists(os.path.join(d, f))), None)
                    r["sig"] = hashlib.md5(open(os.path.join(d, f0), "rb").read()).hexdigest() if f0 else None
                    rows.append(r)
                    if r["sig"]:
                        seen.setdefault(r["sig"], []).append(e[:2])
            for r in rows:
                r["dup"] = [t for t in seen.get(r["sig"], []) if t != r["tap"][:2]] if r.get("sig") else []
        return jsonify(topics=topics, topic=topic, rows=rows)

    def plan(topic, tap, reg, idx_force):
        d = _dir(topic, tap)
        ds = _prompts(d)
        can = [(t, pr) for t, pr in ds if not os.path.exists(os.path.join(d, t))]
        why = None
        if not ds:
            why = "không có bg-prompts.json"
        elif not can:
            why = "đã đủ ảnh"
        elif _state(d):
            why = "đã gửi batch, chờ lấy về"
        else:
            et = _title_of(d)
            for bid, v in reg.items():
                ti = _norm(v.get("title"))
                if ti and et.startswith(ti) and not idx_force:
                    why = f"đã gửi từ trang Film (batch {bid[-8:]}, {v.get('sent')})"
                    break
        return d, can, why

    @app.route("/anh-batch/api/estimate", methods=["POST"])
    def anh_batch_estimate():
        j = request.get_json(force=True) or {}
        G = _gen()
        model, quality = j.get("model") or "gpt-image-1-mini", j.get("quality") or "medium"
        if model not in G.GIA_OUT or quality not in ("low", "medium", "high"):
            return jsonify(error="Model hoặc mức nét không hợp lệ."), 400
        reg, out, tot = load_reg(), [], 0
        for tap in j.get("taps") or []:
            d, can, why = plan(j.get("topic"), tap, reg, bool(j.get("force")))
            n = 0 if why else len(can)
            tot += n
            out.append({"tap": tap, "n": n, "skip": why})
        gia = G.uoc_tinh(tot, model, quality, "1536x1024") / 2
        return jsonify(items=out, total=tot, usd=round(gia, 2))

    @app.route("/anh-batch/api/send", methods=["POST"])
    def anh_batch_send():
        j = request.get_json(force=True) or {}
        G = _gen()
        model, quality = j.get("model") or "gpt-image-1-mini", j.get("quality") or "medium"
        if model not in G.GIA_OUT or quality not in ("low", "medium", "high"):
            return jsonify(error="Model hoặc mức nét không hợp lệ."), 400
        key = load_key()
        if not key:
            return jsonify(error="Chưa có key OpenAI (openai_config.json)."), 400
        reg, results = load_reg(), []
        for tap in j.get("taps") or []:
            with _SEND_LOCK:
                if tap in _SENDING:
                    results.append({"tap": tap, "ok": False, "why": "đang gửi"})
                    continue
                _SENDING.add(tap)
            try:
                d, can, why = plan(j.get("topic"), tap, reg, bool(j.get("force")))
                if why:
                    results.append({"tap": tap, "ok": False, "why": why})
                    continue
                dong = [json.dumps({"custom_id": t, "method": "POST", "url": "/v1/images/generations",
                                    "body": {"model": model, "prompt": pr, "size": "1536x1024",
                                             "quality": quality, "n": 1}}, ensure_ascii=False)
                        for t, pr in can]
                jsonl = ("\n".join(dong) + "\n").encode("utf-8")
                ranh = "----anh_batch_" + str(int(time.time() * 1000))
                body = (f"--{ranh}\r\nContent-Disposition: form-data; name=\"purpose\"\r\n\r\nbatch\r\n"
                        f"--{ranh}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"anh.jsonl\"\r\n"
                        f"Content-Type: application/jsonl\r\n\r\n").encode() + jsonl + f"\r\n--{ranh}--\r\n".encode()
                try:
                    f = json.loads(_post_api("/files", key, raw=body, ctype=f"multipart/form-data; boundary={ranh}"))
                    b = json.loads(_post_api("/batches", key, data={"input_file_id": f["id"],
                                                                    "endpoint": "/v1/images/generations",
                                                                    "completion_window": "24h"}))
                except RuntimeError as e:
                    results.append({"tap": tap, "ok": False, "why": str(e)})
                    continue
                sp = os.path.join(d, STATE)
                if os.path.exists(sp):
                    os.replace(sp, os.path.join(d, ".batch.cu.json"))
                with open(sp, "w", encoding="utf-8") as fh:
                    json.dump({"batch_id": b["id"], "file_id": f["id"], "model": model, "quality": quality,
                               "files": [t for t, _ in can], "gui_luc": time.strftime("%Y-%m-%d %H:%M")},
                              fh, ensure_ascii=False, indent=1)
                results.append({"tap": tap, "ok": True, "batch_id": b["id"], "n": len(can)})
            finally:
                with _SEND_LOCK:
                    _SENDING.discard(tap)
        return jsonify(results=results)

    @app.route("/anh-batch/api/check", methods=["POST"])
    def anh_batch_check():
        j = request.get_json(force=True) or {}
        d = _dir(j.get("topic"), j.get("tap"))
        st = _state(d)
        if not st:
            return jsonify(error="Tập này chưa gửi batch (không có .batch.json)."), 404
        key = load_key()
        if not key:
            return jsonify(error="Chưa có key OpenAI (openai_config.json)."), 400
        try:
            _, s = _status(key, st)
        except RuntimeError as e:
            return jsonify(error=str(e)), 502
        return jsonify(s)

    @app.route("/anh-batch/api/fetch", methods=["POST"])
    def anh_batch_fetch():
        j = request.get_json(force=True) or {}
        d = _dir(j.get("topic"), j.get("tap"))
        ghi_de = bool(j.get("ghi_de"))
        st = _state(d)
        if not st:
            return jsonify(error="Tập này chưa gửi batch (không có .batch.json)."), 404
        key = load_key()
        if not key:
            return jsonify(error="Chưa có key OpenAI (openai_config.json)."), 400
        try:
            b, s = _status(key, st)
            if s["status"] in ("validating", "in_progress", "finalizing", "cancelling"):
                return jsonify(**s, saved=0, pending=True)
            if not b.get("output_file_id"):
                return jsonify(error=f"Batch {s['status']}, không có file kết quả.", **s), 409
            out = _api("/files/" + b["output_file_id"] + "/content", key).decode("utf-8")
        except RuntimeError as e:
            return jsonify(error=str(e)), 502
        saved, skipped, failed = [], [], []
        for line in out.splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            ten = r.get("custom_id") or ""
            resp = r.get("response") or {}
            if not IMG.match(ten):
                continue
            if resp.get("status_code") != 200:
                failed.append({"file": ten, "why": str(resp.get("body"))[:140]})
                continue
            dich = os.path.join(d, ten)
            if os.path.exists(dich) and not ghi_de:
                skipped.append(ten)
                continue
            png = base64.b64decode(resp["body"]["data"][0]["b64_json"])
            tmp = dich + ".png"
            with open(tmp, "wb") as f:
                f.write(png)
            try:
                subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", tmp, "-q:v", "3", dich],
                               check=True, capture_output=True)
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
            saved.append(ten)
        du = all(os.path.exists(os.path.join(d, f)) for f in (st.get("files") or []))
        if du:
            os.remove(os.path.join(d, STATE))
        return jsonify(**s, saved=len(saved), skipped=len(skipped), failed=failed,
                       du=du, row=_row(j.get("topic"), d))

    @app.route("/anh-batch/api/open", methods=["POST"])
    def anh_batch_open():
        j = request.get_json(force=True) or {}
        d = _dir(j.get("topic"), j.get("tap"))
        subprocess.Popen(["open", d])
        return jsonify(ok=True)

    @app.route("/anh-batch/api/images")
    def anh_batch_images():
        d = _dir(request.args.get("topic"), request.args.get("tap"))
        files = [f for f in _files(d) if os.path.exists(os.path.join(d, f))]
        return jsonify(files=files)

    @app.route("/anh-batch/img/<topic>/<tap>/<fn>")
    def anh_batch_img(topic, tap, fn):
        d = _dir(topic, tap)
        if not IMG.match(fn):
            abort(400)
        return send_from_directory(d, fn, as_attachment=False)

    @app.route("/anh-batch/api/import", methods=["POST"])
    def anh_batch_import():
        j = request.get_json(force=True) or {}
        d = _dir(j.get("topic"), j.get("tap"))
        files = [f for f in _files(d) if os.path.exists(os.path.join(d, f))]
        if not files:
            return jsonify(error="Tập này chưa có ảnh nào trong thư mục."), 404
        os.makedirs(up_dir, exist_ok=True)
        items = []
        stamp = int(time.time() * 1000)
        for i, f in enumerate(files):
            name = f"filmclip_{stamp}_{i:03d}_{uuid.uuid4().hex[:6]}.jpg"
            shutil.copyfile(os.path.join(d, f), os.path.join(up_dir, name))
            items.append({"path": os.path.join(up_dir, name), "name": f, "url": "/filmimg/" + name})
        return jsonify(items=items)
