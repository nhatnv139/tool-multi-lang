# -*- coding: utf-8 -*-
"""Tien trinh con cua film.make_scene: sinh khung Ken Burns (raw BGR) ra stdout,
stdout noi thang vao stdin cua lenh ffmpeg cuoi (phu de + grade + x264).

Vi sao tach tien trinh: make_scene chay nhieu canh song song bang THREAD; vong sinh
khung (warpAffine + hat bay + tobytes) giu GIL nen cac canh cho nhau -> thuc te chi
~1 nhan. Moi canh 1 tien trinh rieng -> song song that tren nhieu nhan.

    python kb_worker.py <file .pkl: {parts, subs} cho film._kb_stream>
"""
import os
import pickle
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    with open(sys.argv[1], "rb") as f:
        payload = pickle.load(f)          # {"parts": [...tham so _kb_frames], "subs": [...]}
    import cv2
    # nhieu canh chay song song (FILM_JOBS) + x264 moi canh da an het nhan: de cv2 mo
    # 16 luong/worker thi cac tien trinh tranh nhau CPU, cham hon ca chay 1 luong.
    # do 20/10 (3 canh song song): 1 luong 31.3s, 4 luong 27.8s
    cv2.setNumThreads(int(os.environ.get("FILM_CV_THREADS") or max(1, (os.cpu_count() or 4) // 4)))
    import film
    out = sys.stdout.buffer
    try:
        for fr in film._kb_stream(payload["parts"], payload.get("subs") or ()):
            out.write(memoryview(fr).cast("B"))     # khong copy nhu tobytes (~1.3ms/khung)
        out.flush()
    except (BrokenPipeError, OSError):
        pass        # ffmpeg da du khung (-t) hoac bi dung -> thoat em


if __name__ == "__main__":
    main()
