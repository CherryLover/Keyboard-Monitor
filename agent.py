from pynput import keyboard
from pynput.keyboard import Key

import concurrent.futures
import logging
import os
import queue
import sys
import time
import sqlite3
from datetime import datetime

MODIFIERS = {
    Key.shift, Key.shift_l, Key.shift_r,
    Key.alt, Key.alt_l, Key.alt_r, Key.alt_gr,
    Key.ctrl, Key.ctrl_l, Key.ctrl_r,
    Key.cmd, Key.cmd_l, Key.cmd_r,
}

DATABASE_PATH = os.path.join(os.path.dirname(__file__), "keyboard_monitor.db")

# Create table in SQLite database
def create_table():
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS keyboard_monitor (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hits TEXT NULL,
                ts TIMESTAMP NOT NULL
            )
        """)
        conn.commit()

if __name__ == '__main__':
    create_table()  # Call create_table outside of the threads

    log = logging.getLogger("agent")
    log.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(funcName)s %(message)s')
    file_handler = logging.FileHandler(f'agent-{time.time_ns()}.log', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.setFormatter(formatter)
    log.addHandler(file_handler)
    log.addHandler(stdout_handler)

    current_modifiers = set()
    pending_hits = queue.Queue()
    cancel_signal = queue.Queue()

    def on_press(key):
        if key in MODIFIERS:
            current_modifiers.add(key)
        else:
            hits = sorted([str(key) for key in current_modifiers]) + [str(key)]
            hits = '+'.join(hits)
            pending_hits.put(hits)
        log.debug(f'{key} pressed, current_modifiers: {current_modifiers}')

    def on_release(key):
        if key in MODIFIERS:
            try:
                current_modifiers.remove(key)
            except KeyError:
                log.warning(f'Key {key} not in current_modifiers {current_modifiers}')
        log.debug(f'{key} released, current_modifiers: {current_modifiers}')

    def sender_thread():
        while True:
            hits = pending_hits.get()
            if hits is None:
                log.info("Exiting sender thread...")
                break

            # Each thread must create its own SQLite connection
            with sqlite3.connect(DATABASE_PATH) as conn:
                cursor = conn.cursor()
                try:
                    log.debug(f'sending: {hits}')
                    cursor.execute("INSERT INTO keyboard_monitor (hits, ts) VALUES (?, ?)", (hits, datetime.now()))
                    conn.commit()
                    log.info(f'sent: {hits}')
                except sqlite3.OperationalError as e:
                    log.error(f'Operational error: {e}')
                    pending_hits.put(hits)

    def listener_thread():
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            log.info("Listening...")
            cancel_signal.get()
            pending_hits.put(None)
            log.info("Exiting listener thread...")

    with concurrent.futures.ThreadPoolExecutor() as executor:
        sender = executor.submit(sender_thread)
        listener = executor.submit(listener_thread)
        try:
            f = concurrent.futures.wait([sender, listener], return_when=concurrent.futures.FIRST_EXCEPTION)
            for fut in f.done:
                error = fut.exception(timeout=0)
                if error:
                    log.error(f'Unhandled exception for futures: {error}')
        except KeyboardInterrupt as e:
            log.info("KeyboardInterrupt. Exiting...")
        except Exception as e:
            log.error(f'Unhandled exception: {e}')
        finally:
            cancel_signal.put(True)
