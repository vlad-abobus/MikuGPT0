# -*- coding: utf-8 -*-
"""Отдельный процесс: окно 3D-панды на pywebview (WebView2/Edge).

Запускается из main.py и общается с основным процессом по localhost TCP.
Формат команд (по одной на строку): ``state:<name>``, ``speak:<ms>``, ``stop``, ``quit``.
"""
import argparse
import logging
import socket
import sys
import threading

logger = logging.getLogger(__name__)


def _eval_js(holder, code: str) -> None:
    win = holder.get("win")
    if win is None:
        return
    try:
        win.evaluate_js(code)
    except Exception as e:
        logger.debug("panda viewer: evaluate_js failed: %s", e)


def _dispatch(cmd: str, holder: dict) -> None:
    if cmd.startswith("state:"):
        state = cmd.split(":", 1)[1].strip().replace("'", "")
        _eval_js(holder, f"window.setPandaState && window.setPandaState('{state}');")
    elif cmd.startswith("speak:"):
        raw = cmd.split(":", 1)[1].strip()
        try:
            ms = max(600, int(raw))
        except ValueError:
            ms = 1800
        _eval_js(holder, f"window.pandaSpeak && window.pandaSpeak({ms});")
    elif cmd == "stop":
        _eval_js(holder, "window.pandaStop && window.pandaStop();")
    elif cmd == "quit":
        holder["stop"] = True
        win = holder.get("win")
        if win is not None:
            try:
                win.destroy()
            except Exception:
                pass


def _serve(port: int, holder: dict) -> None:
    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", port))
        srv.listen(1)
    except OSError as e:
        logger.error("panda viewer: не удалось занять порт %s: %s", port, e)
        return

    try:
        while not holder.get("stop"):
            try:
                conn, _ = srv.accept()
            except OSError:
                break
            conn.settimeout(1.0)
            buf = b""
            try:
                while not holder.get("stop"):
                    try:
                        data = conn.recv(4096)
                    except socket.timeout:
                        continue
                    if not data:
                        break
                    buf += data
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        cmd = line.decode("utf-8", "ignore").strip()
                        if cmd:
                            _dispatch(cmd, holder)
            except OSError:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass
            if holder.get("stop"):
                break
    finally:
        try:
            srv.close()
        except OSError:
            pass


def run_viewer(html: str, port: int, width: int, height: int, x: int, y: int) -> int:
    try:
        import webview
    except Exception as e:
        logger.error("pywebview недоступен: %s", e)
        return 1

    holder: dict = {}
    threading.Thread(target=_serve, args=(port, holder), daemon=True).start()

    try:
        window = webview.create_window(
            "Panda",
            url=html,
            width=int(width),
            height=int(height),
            x=int(x),
            y=int(y),
            frameless=True,
            easy_drag=True,
            on_top=True,
            resizable=False,
            background_color="#050505",
        )
    except Exception as e:
        logger.error("panda viewer: create_window failed: %s", e)
        return 1

    holder["win"] = window

    def _on_start() -> None:
        if holder.get("stop"):
            return
        _eval_js(holder, "window.setPandaState && window.setPandaState('idle');")

    try:
        webview.start(_on_start, gui="edgechromium", http_server=True)
    except Exception as e:
        logger.error("panda viewer: start failed: %s", e)
        try:
            webview.start(_on_start, http_server=True)
        except Exception as e2:
            logger.error("panda viewer: fallback start failed: %s", e2)
            return 1
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Panda 3D viewer (pywebview)")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--html", required=True)
    parser.add_argument("--width", type=int, default=300)
    parser.add_argument("--height", type=int, default=380)
    parser.add_argument("--x", type=int, default=100)
    parser.add_argument("--y", type=int, default=100)
    args = parser.parse_args(argv)
    return run_viewer(args.html, args.port, args.width, args.height, args.x, args.y)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    sys.exit(main())
