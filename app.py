# -*- coding: utf-8 -*-
"""Mac 远控 · Tailscale —— 输入 Mac 的 Tailscale 地址即可远程控制家里 Mac"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import base64
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

APP_NAME = "Mac 远控"
APP_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
TS_EXE = r"C:\Program Files\Tailscale\tailscale.exe"
DEFAULT_PORT = "5900"

CFG_CANDIDATES = [os.path.join(APP_DIR, "config.json")]
if not os.access(APP_DIR, os.W_OK):
    CFG_CANDIDATES.append(os.path.join(os.environ.get("APPDATA", APP_DIR), "MacRemote", "config.json"))
CFG_PATH = CFG_CANDIDATES[0]

BG = "#F4F6F9"
CARD = "#FFFFFF"
FG = "#1B2430"
MUTED = "#6B7785"
ACCENT = "#1677FF"
ACCENT_DARK = "#0F5FD9"
GREEN = "#12893F"
ORANGE = "#C77700"
RED = "#C4342B"
LINE = "#E3E8EF"


# ---------------------------------------------------------------- 配置
def load_cfg():
    data = {"host": "", "port": DEFAULT_PORT, "quality": "均衡", "fullscreen": True, "viewonly": False, "password": ""}
    for p in CFG_CANDIDATES:
        try:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    data.update(json.load(f))
                break
        except Exception:
            pass
    return data


def save_cfg(data):
    for p in CFG_CANDIDATES:
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return p
        except Exception:
            continue
    return None


def obfuscate(s):
    if not s:
        return ""
    key = b"MacRemoteTailscale"
    raw = s.encode("utf-8")
    out = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
    return base64.b64encode(out).decode("ascii")


def deobfuscate(s):
    if not s:
        return ""
    try:
        key = b"MacRemoteTailscale"
        raw = base64.b64decode(s.encode("ascii"))
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(raw)).decode("utf-8")
    except Exception:
        return ""


# ---------------------------------------------------------------- Tailscale
def tailscale_json():
    exe = TS_EXE if os.path.exists(TS_EXE) else (shutil.which("tailscale") or "")
    if not exe:
        return None, "本机没找到 tailscale 命令"
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        p = subprocess.run([exe, "status", "--json"], capture_output=True, text=True,
                           timeout=15, startupinfo=si, encoding="utf-8", errors="replace")
        if not p.stdout.strip():
            return None, "Tailscale 未登录或未运行"
        return json.loads(p.stdout), None
    except Exception as e:
        return None, "读取 Tailscale 状态失败：%s" % e


def list_peers():
    """返回 [(label, ip, is_mac, online)]"""
    data, err = tailscale_json()
    if not data:
        return [], err
    peers = []
    me = data.get("Self") or {}
    for v in (data.get("Peer") or {}).values():
        ip = ""
        for a in (v.get("TailscaleIPs") or []):
            if a.count(".") == 3:
                ip = a
                break
        if not ip:
            continue
        host = (v.get("HostName") or v.get("DNSName") or "?").split(".")[0]
        osname = (v.get("OS") or "").lower()
        online = bool(v.get("Online"))
        is_mac = osname in ("macos", "darwin", "ios") and osname != "ios"
        label = "%s  ·  %s" % (host, ip)
        peers.append({"label": label, "ip": ip, "host": host, "os": osname,
                      "is_mac": is_mac, "online": online})
    peers.sort(key=lambda x: (not x["is_mac"], not x["online"], x["host"].lower()))
    return peers, None


# ---------------------------------------------------------------- VNC 探测
RFB_NAMES = {
    1: "无需密码", 2: "VNC 密码", 5: "RA2", 6: "RA2ne", 16: "Tight", 18: "TLS",
    19: "VeNCrypt", 30: "Apple 认证-1", 31: "Apple 认证-2", 32: "Apple 认证-3",
    33: "Apple 认证-4", 35: "Apple 认证-5", 36: "Apple 认证-6",
}


def _recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise EOFError("连接被关闭")
        buf += chunk
    return buf


def probe_vnc(host, port, timeout=6.0):
    """返回 (状态, 说明)；状态 in {'ok','nopass','appleonly','refused','noport'}"""
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
    except socket.timeout:
        return "noport", "连接超时：%s:%s 没有响应" % (host, port)
    except OSError as e:
        return "noport", "无法连接 %s:%s（%s）" % (host, port, e.strerror or e)
    try:
        sock.settimeout(timeout)
        ver = _recv_exact(sock, 12)
        if not ver.startswith(b"RFB"):
            return "noport", "端口开了，但不是 VNC 服务（收到 %r）" % ver[:8]
        sock.sendall(b"RFB 003.008\n")
        n = _recv_exact(sock, 1)[0]
        if n == 0:
            ln = int.from_bytes(_recv_exact(sock, 4), "big")
            reason = _recv_exact(sock, ln).decode("utf-8", "replace")
            return "refused", "服务端拒绝：%s" % reason
        types = [_recv_exact(sock, 1)[0] for _ in range(n)]
        names = ", ".join(RFB_NAMES.get(t, "类型%s" % t) for t in types)
        ver_s = ver[4:11].decode("ascii", "replace").strip()
        if 2 in types:
            return "ok", "屏幕共享已开启（RFB %s），可用 VNC 密码登录" % ver_s
        if 1 in types:
            return "nopass", "屏幕共享已开启，但未设置密码（%s）" % names
        return "appleonly", "只接受 Apple 账号认证（%s）——需要在 Mac 上勾选“VNC 显示程序可以使用密码控制屏幕”" % names
    except EOFError:
        return "refused", "服务端提前断开连接"
    except Exception as e:
        return "refused", "握手失败：%s" % e
    finally:
        try:
            sock.close()
        except Exception:
            pass


# ---------------------------------------------------------------- 找 VNC 客户端
VIEWER_CANDIDATES = [
    (os.path.join(APP_DIR, "bin", "TigerVNC", "vncviewer.exe"), "tiger"),
    (os.path.join(APP_DIR, "bin", "vncviewer.exe"), "tiger"),
    (r"C:\Program Files\TigerVNC\vncviewer.exe", "tiger"),
    (r"C:\Program Files (x86)\TigerVNC\vncviewer.exe", "tiger"),
    (r"C:\Program Files\uvnc bvba\UltraVNC\vncviewer.exe", "ultra"),
    (r"C:\Program Files\UltraVNC\vncviewer.exe", "ultra"),
    (r"C:\Program Files (x86)\UltraVNC\vncviewer.exe", "ultra"),
    (r"C:\Program Files\TightVNC\tvnviewer.exe", "tight"),
    (r"C:\Program Files (x86)\TightVNC\tvnviewer.exe", "tight"),
    (r"C:\Program Files\RealVNC\VNC Viewer\vncviewer.exe", "real"),
]


def find_viewer():
    for path, kind in VIEWER_CANDIDATES:
        if os.path.exists(path):
            return path, kind
    return None, None


QUALITY_MAP = {
    "高速（局域网）": ["-CompressLevel=1", "-QualityLevel=9"],
    "均衡": ["-CompressLevel=6", "-QualityLevel=8"],
    "省流量": ["-CompressLevel=9", "-QualityLevel=6"],
}


# ---------------------------------------------------------------- 界面
class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_cfg()
        self.peers = []
        self.pending_probe = None
        self.last_status = None
        self.viewer, self.viewer_kind = find_viewer()
        self._build()
        self._refresh_peers(auto=True)

    # ---------- 布局
    def _build(self):
        r = self.root
        r.title("Mac 远控 · Tailscale")
        r.geometry("620x700")
        r.minsize(620, 700)
        r.configure(bg=BG)
        try:
            r.iconbitmap(os.path.join(APP_DIR, "app.ico"))
        except Exception:
            pass

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("TLabel", background=BG, foreground=FG, font=("Microsoft YaHei UI", 10))
        style.configure("Card.TLabel", background=CARD, foreground=FG, font=("Microsoft YaHei UI", 10))
        style.configure("Muted.TLabel", background=CARD, foreground=MUTED, font=("Microsoft YaHei UI", 9))
        style.configure("Title.TLabel", background=BG, foreground=FG, font=("Microsoft YaHei UI", 18, "bold"))
        style.configure("Sub.TLabel", background=BG, foreground=MUTED, font=("Microsoft YaHei UI", 10))
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(10, 6))
        style.configure("Accent.TButton", font=("Microsoft YaHei UI", 11, "bold"), padding=(14, 10),
                        background=ACCENT, foreground="#FFFFFF", borderwidth=0, focusthickness=0)
        style.map("Accent.TButton", background=[("active", ACCENT_DARK), ("disabled", "#9AB8E8")])
        style.configure("TEntry", padding=6, fieldbackground="#FFFFFF")
        style.configure("TCombobox", padding=5)
        style.configure("TCheckbutton", background=CARD, foreground=FG, font=("Microsoft YaHei UI", 9))
        style.map("TCheckbutton", background=[("active", CARD)])
        style.configure("TSeparator", background=LINE)

        outer = ttk.Frame(r, padding=22)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Mac 远程控制", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="通过 Tailscale 私有网络直连家里的 Mac，输入地址即可开始",
                  style="Sub.TLabel").pack(anchor="w", pady=(4, 16))

        # 卡片
        card = tk.Frame(outer, bg=CARD, highlightbackground=LINE, highlightthickness=1, bd=0)
        card.pack(fill="x")
        inner = ttk.Frame(card, style="Card.TFrame", padding=16)
        inner.pack(fill="x")

        ttk.Label(inner, text="① Tailscale 设备", style="Card.TLabel",
                  font=("Microsoft YaHei UI", 10, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        self.dev_cb = ttk.Combobox(inner, state="readonly", font=("Microsoft YaHei UI", 10))
        self.dev_cb.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 2))
        self.dev_cb.bind("<<ComboboxSelected>>", self.on_pick)
        ttk.Button(inner, text="刷新", width=6, command=self._refresh_peers).grid(row=1, column=2, padx=(8, 0), pady=(6, 2))

        ttk.Label(inner, text="② 地址与端口（可手动填写）", style="Card.TLabel",
                  font=("Microsoft YaHei UI", 10, "bold")).grid(row=2, column=0, columnspan=3, sticky="w", pady=(14, 0))
        self.host_var = tk.StringVar(value=self.cfg.get("host", ""))
        self.port_var = tk.StringVar(value=str(self.cfg.get("port", DEFAULT_PORT)))
        hf = ttk.Frame(inner, style="Card.TFrame")
        hf.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(6, 2))
        self.host_entry = ttk.Entry(hf, textvariable=self.host_var, font=("Consolas", 11))
        self.host_entry.pack(side="left", fill="x", expand=True)
        self.host_entry.bind("<Return>", lambda e: self.connect())
        ttk.Label(hf, text=" : ", style="Card.TLabel").pack(side="left")
        ttk.Entry(hf, textvariable=self.port_var, width=6, font=("Consolas", 11)).pack(side="left")

        self.status_lbl = tk.Label(inner, text="尚未检测", bg=CARD, fg=MUTED,
                                   font=("Microsoft YaHei UI", 9), anchor="w", justify="left", wraplength=545)
        self.status_lbl.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(8, 0))

        inner.columnconfigure(0, weight=1)

        # 按钮行
        btn_row = ttk.Frame(outer)
        btn_row.pack(fill="x", pady=(16, 0))
        ttk.Button(btn_row, text="检测连通", command=self.test).pack(side="left")
        self.connect_btn = ttk.Button(btn_row, text="开始远程控制", style="Accent.TButton", command=self.connect)
        self.connect_btn.pack(side="left", padx=(10, 0), fill="x", expand=True)
        ttk.Button(btn_row, text="复制地址", command=self.copy_addr).pack(side="left", padx=(10, 0))

        # 选项卡片
        opt = tk.Frame(outer, bg=CARD, highlightbackground=LINE, highlightthickness=1, bd=0)
        opt.pack(fill="x", pady=(14, 0))
        oin = ttk.Frame(opt, style="Card.TFrame", padding=16)
        oin.pack(fill="x")

        row1 = ttk.Frame(oin, style="Card.TFrame")
        row1.pack(fill="x")
        ttk.Label(row1, text="画质", style="Card.TLabel").pack(side="left")
        self.q_cb = ttk.Combobox(row1, state="readonly", width=14, values=list(QUALITY_MAP.keys()),
                                 font=("Microsoft YaHei UI", 9))
        self.q_cb.set(self.cfg.get("quality", "均衡") if self.cfg.get("quality") in QUALITY_MAP else "均衡")
        self.q_cb.pack(side="left", padx=(8, 16))

        self.fs_var = tk.BooleanVar(value=bool(self.cfg.get("fullscreen", True)))
        self.vo_var = tk.BooleanVar(value=bool(self.cfg.get("viewonly", False)))
        ttk.Checkbutton(row1, text="全屏打开", variable=self.fs_var).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(row1, text="只观看（不控制鼠标键盘）", variable=self.vo_var).pack(side="left")

        row2 = ttk.Frame(oin, style="Card.TFrame")
        row2.pack(fill="x", pady=(10, 0))
        ttk.Label(row2, text="认证方式", style="Card.TLabel").pack(side="left")
        self.auth_cb = ttk.Combobox(row2, state="readonly", width=11, font=("Microsoft YaHei UI", 9),
                                    values=["VNC 密码", "Mac 账号"])
        self.auth_cb.set("Mac 账号" if self.cfg.get("auth") == "account" else "VNC 密码")
        self.auth_cb.pack(side="left", padx=(8, 12))

        ttk.Label(row2, text="密码", style="Card.TLabel").pack(side="left")
        self.pw_var = tk.StringVar(value=deobfuscate(self.cfg.get("password", "")))
        self.pw_entry = ttk.Entry(row2, textvariable=self.pw_var, show="•", width=18, font=("Microsoft YaHei UI", 9))
        self.pw_entry.pack(side="left", padx=(8, 6))
        self.remember_var = tk.BooleanVar(value=bool(self.cfg.get("password")))
        ttk.Checkbutton(row2, text="记住", variable=self.remember_var).pack(side="left")
        ttk.Label(row2, text="（留空则连上后弹框输入）", style="Muted.TLabel").pack(side="left", padx=(6, 0))

        hint = ttk.Label(oin, style="Muted.TLabel", wraplength=520, justify="left",
                         text="VNC 密码＝Mac「屏幕共享 → 电脑设置…」里单独设的那个；"
                              "Mac 账号＝Mac 用户名 + 登录密码（会多要一个用户名输入框）。")
        hint.pack(anchor="w", pady=(8, 0))

        # 底部工具
        foot = ttk.Frame(outer)
        foot.pack(fill="x", pady=(14, 0))
        ttk.Button(foot, text="打开 Mac 共享文件夹", command=self.open_share).pack(side="left")
        ttk.Button(foot, text="Mac 端设置说明", command=self.open_guide).pack(side="left", padx=(8, 0))
        self.fix_btn = ttk.Button(foot, text="准备 VNC 客户端", command=self.fix_viewer)
        self.fix_btn.pack(side="right")

        self.foot_lbl = tk.Label(outer, text="", bg=BG, fg=MUTED, font=("Microsoft YaHei UI", 8), anchor="w")
        self.foot_lbl.pack(fill="x", pady=(10, 0))

        self._update_footer()

    # ---------- 提示
    def _update_footer(self):
        if self.viewer:
            txt = "VNC 客户端：%s" % self.viewer
            self.fix_btn.configure(text="更换 VNC 客户端")
        else:
            txt = "未找到 VNC 客户端，点右侧「准备 VNC 客户端」一键获取"
            self.fix_btn.configure(text="准备 VNC 客户端")
        self.foot_lbl.configure(text=txt)

    def set_status(self, text, color=MUTED):
        self.last_status = (text, color)
        self.status_lbl.configure(text=text, fg=color)

    # ---------- Tailscale 设备
    def _refresh_peers(self, auto=False):
        def work():
            peers, err = list_peers()
            self.root.after(0, lambda: self._apply_peers(peers, err, auto))
        threading.Thread(target=work, daemon=True).start()

    def _apply_peers(self, peers, err, auto):
        self.peers = peers
        labels = [p["label"] + ("" if p["online"] else "  (离线)") for p in peers]
        self.dev_cb["values"] = labels
        if err:
            self.set_status("Tailscale 状态读取失败：%s（仍可手动填 IP）" % err, ORANGE)
        if not peers:
            return
        cur = self.host_var.get().strip()
        idx = next((i for i, p in enumerate(peers) if p["ip"] == cur), None)
        if idx is None:
            idx = next((i for i, p in enumerate(peers) if p["is_mac"]), 0)
        self.dev_cb.current(idx)
        if not cur or auto:
            self.host_var.set(peers[idx]["ip"])
        if auto:
            self.root.after(600, self.test)

    def on_pick(self, _=None):
        i = self.dev_cb.current()
        if 0 <= i < len(self.peers):
            self.host_var.set(self.peers[i]["ip"])
            self.set_status("已选择 %s，点「检测连通」确认能否连" % self.peers[i]["host"], MUTED)

    # ---------- 检测
    def test(self):
        host = self.host_var.get().strip()
        port = self.port_var.get().strip()
        if not host:
            self.set_status("先填 Mac 的 Tailscale 地址（或在上面的设备列表里选一台）", ORANGE)
            return
        try:
            port_n = int(port)
        except ValueError:
            self.set_status("端口必须是数字，默认 5900", ORANGE)
            return
        self.set_status("正在检测 %s:%s …" % (host, port_n), MUTED)
        gen = time.time()
        self.pending_probe = gen

        def work():
            state, msg = probe_vnc(host, port_n)
            self.root.after(0, lambda: self._show_probe(gen, state, msg))
        threading.Thread(target=work, daemon=True).start()

    def _show_probe(self, gen, state, msg):
        if self.pending_probe != gen:
            return
        who = next((p for p in self.peers if p["ip"] == self.host_var.get().strip()), None)
        prefix = ""
        if who and not who["online"]:
            prefix = "Tailscale 显示这台设备离线；"
        if state in ("ok",):
            self.set_status("✓ 可以连接 —— " + prefix + msg, GREEN)
        elif state == "nopass":
            self.set_status("✓ 可以连接（无密码）—— " + msg, GREEN)
        elif state == "appleonly":
            self.set_status("端口通了，但认证方式不匹配 —— " + msg, ORANGE)
        elif state == "refused":
            self.set_status("端口通了，但服务拒绝了 —— " + msg, RED)
        else:
            self.set_status("连不上 —— " + prefix + msg + "\n检查：Mac 是否开机唤醒、Tailscale 是否在线、屏幕共享是否开启", RED)

    # ---------- 连接
    def connect(self):
        host = self.host_var.get().strip()
        if not host:
            messagebox.showinfo(APP_NAME, "先填 Mac 的 Tailscale 地址，或从设备列表里选一台。")
            return
        port = self.port_var.get().strip() or DEFAULT_PORT
        viewer, kind = find_viewer()
        if not viewer:
            if messagebox.askyesno(APP_NAME, "这台电脑还没有 VNC 客户端，需要先准备一个。\n\n现在就自动准备吗？（内置 TigerVNC，约 10 MB）"):
                self.fix_viewer()
            return
        self.viewer, self.viewer_kind = viewer, kind
        self._save()

        args = [viewer]
        target = "%s::%s" % (host, port) if kind in ("tiger", "ultra") else "%s:%s" % (host, port)
        use_vnc_pw = self.auth_cb.get() != "Mac 账号"
        if kind in ("tiger", "ultra"):
            for a in QUALITY_MAP.get(self.q_cb.get(), []):
                args.append(a)
            if self.fs_var.get():
                args.append("-FullScreen=1")
            if self.vo_var.get():
                args.append("-ViewOnly=1")
            if use_vnc_pw:
                # 只用标准 VNC 密码认证，免得弹框里还要用户名
                args.append("-SecurityTypes=VncAuth")
        else:
            if self.vo_var.get():
                args.append("/viewonly")
            if self.fs_var.get():
                args.append("/fullscreen")
        args.append(target)

        errlog = os.path.join(APP_DIR, "vnc_last.log")
        child_env = dict(os.environ)
        pw = self.pw_var.get()
        if pw and (kind not in ("tiger", "ultra") or use_vnc_pw):
            # TigerVNC 支持用 VNC_PASSWORD 环境变量预置密码；-PasswordFile 要的是
            # DES 混淆过的二进制格式，明文会被当成错的密码，所以不走文件。
            child_env["VNC_PASSWORD"] = pw
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 1
            ef = open(errlog, "w", encoding="utf-8", errors="replace")
            proc = subprocess.Popen(args, cwd=os.path.dirname(viewer), startupinfo=si, env=child_env,
                                    stdout=subprocess.DEVNULL, stderr=ef, close_fds=True)
        except Exception as e:
            messagebox.showerror(APP_NAME, "启动 VNC 客户端失败：\n%s" % e)
            return
        self.set_status("已启动 VNC 客户端，正在连接 %s …\n若弹出密码框，输入 Mac 系统设置里设的那个 VNC 密码。" % target, GREEN)

        def watch():
            time.sleep(4)
            if proc.poll() is None:
                return
            try:
                ef.close()
            except Exception:
                pass
            try:
                txt = open(errlog, encoding="utf-8", errors="replace").read().strip()
            except Exception:
                txt = ""
            bad_lines = [t for t in txt.splitlines()
                         if ("Unrecognized" in t) or ("Could not" in t) or ("failed" in t.lower())]
            detail = "\n".join(bad_lines) if bad_lines else (txt.splitlines()[-1] if txt.strip() else "（没有输出）")
            self.root.after(0, lambda: self._launch_failed(detail))

        threading.Thread(target=watch, daemon=True).start()

    def _launch_failed(self, detail):
        self.set_status("VNC 客户端启动后立刻退出了，原因：\n%s" % detail, RED)
        messagebox.showerror(APP_NAME, "VNC 客户端启动失败，退出原因：\n\n%s\n\n完整日志：%s"
                             % (detail, os.path.join(APP_DIR, "vnc_last.log")))

    def copy_addr(self):
        host = self.host_var.get().strip()
        if not host:
            return
        txt = "%s:%s" % (host, self.port_var.get().strip() or DEFAULT_PORT)
        self.root.clipboard_clear()
        self.root.clipboard_append(txt)
        self.set_status("地址已复制：%s" % txt, MUTED)

    # ---------- 共享文件夹
    def open_share(self):
        host = self.host_var.get().strip()
        if not host:
            messagebox.showinfo(APP_NAME, "先填 Mac 的地址。")
            return
        try:
            subprocess.Popen(["explorer.exe", r"\\%s" % host])
            self.set_status(r"已在资源管理器打开 \\%s —— 首次访问输入 Mac 的共享账号密码" % host, MUTED)
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e))

    def open_guide(self):
        p = os.path.join(APP_DIR, "Mac 端设置.txt")
        if os.path.exists(p):
            os.startfile(p)
        else:
            messagebox.showinfo(APP_NAME, "同目录下没有找到《Mac 端设置.txt》。")

    # ---------- 准备客户端
    def fix_viewer(self):
        viewer, _ = find_viewer()
        if viewer:
            messagebox.showinfo(APP_NAME, "已经有可用的 VNC 客户端：\n%s\n\n如果想换，可以把 vncviewer.exe 放进程序目录的 bin 文件夹。" % viewer)
            self._update_footer()
            return
        msg = ("程序目录里没有找到 VNC 客户端。两种方式：\n\n"
               "· 自动：点「是」，我用系统自带的 winget 安装 TigerVNC（官方源，约 10 MB）\n"
               "· 手动：下载后把 vncviewer.exe 及其 dll 放进 bin 文件夹\n\n"
               "现在自动安装吗？")
        if not messagebox.askyesno(APP_NAME, msg):
            return
        self.set_status("正在通过 winget 安装 TigerVNC，请稍候…", MUTED)

        def work():
            try:
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                p = subprocess.run(["winget", "install", "--id", "TigerVNC.TigerVNC", "--exact",
                                    "--silent", "--accept-package-agreements", "--accept-source-agreements"],
                                   capture_output=True, text=True, timeout=600, startupinfo=si,
                                   encoding="utf-8", errors="replace")
                ok = p.returncode == 0
                tail = (p.stdout or "")[-400:]
            except Exception as e:
                ok, tail = False, str(e)
            self.root.after(0, lambda: self._after_install(ok, tail))
        threading.Thread(target=work, daemon=True).start()

    def _after_install(self, ok, tail):
        self.viewer, self.viewer_kind = find_viewer()
        self._update_footer()
        if self.viewer:
            self.set_status("TigerVNC 已就绪：%s" % self.viewer, GREEN)
        else:
            self.set_status("自动安装没成功，请手动下载 TigerVNC 后把 vncviewer.exe 放进 bin 目录。\n%s" % tail, RED)

    # ---------- 保存
    def _save(self):
        self.cfg["host"] = self.host_var.get().strip()
        self.cfg["port"] = self.port_var.get().strip() or DEFAULT_PORT
        self.cfg["quality"] = self.q_cb.get()
        self.cfg["auth"] = "account" if self.auth_cb.get() == "Mac 账号" else "vnc"
        self.cfg["fullscreen"] = bool(self.fs_var.get())
        self.cfg["viewonly"] = bool(self.vo_var.get())
        self.cfg["password"] = obfuscate(self.pw_var.get()) if self.remember_var.get() else ""
        save_cfg(self.cfg)

    def on_close(self):
        self._save()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
