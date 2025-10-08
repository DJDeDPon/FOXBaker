import sys

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import subprocess
import threading
import os
from pathlib import Path
import re
import time
from PIL import Image, ImageTk
import tempfile
import json
import glob

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


class LocalizationManager:
    def __init__(self, lang_dir='lang', default_lang='ru'):
        self.locales = {}
        self.lang_dir = lang_dir
        self.language_map = {}
        self.load_languages()
        self.current_lang = default_lang
        if default_lang not in self.locales:
            self.current_lang = next(iter(self.locales))

    def load_languages(self):
        lang_files = glob.glob(os.path.join(self.lang_dir, '*.json'))
        for file in lang_files:
            lang_code = Path(file).stem
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.locales[lang_code] = data
                    self.language_map[data.get('language_name', lang_code)] = lang_code
            except Exception as e:
                print(f"Error loading language file {file}: {e}")

    def get(self, key):
        return self.locales.get(self.current_lang, {}).get(key, key)

    def get_available_languages(self):
        return {code: data.get('language_name', code) for code, data in self.locales.items()}

    def set_language(self, lang_name):
        lang_code = self.language_map.get(lang_name)
        if lang_code and lang_code in self.locales:
            self.current_lang = lang_code
            return True
        return False


class FOXBaker:
    def __init__(self):
        # Используем новую функцию для поиска папки lang
        lang_path = resource_path('lang')
        self.loc = LocalizationManager(lang_dir=lang_path, default_lang='en')

        ctk.set_appearance_mode("dark")
        self.root = ctk.CTk()
        self.root.title(self.loc.get("window_title"))
        self.root.geometry("700x780")
        self.root.minsize(600, 650)
        self.root.configure(fg_color="#211A16")

        self.video_path = tk.StringVar()
        self.subtitle_path = tk.StringVar()
        self.output_name = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.quality_mode = tk.StringVar()
        self.output_format = tk.StringVar(value="mp4")
        self.hw_accel_enabled = tk.BooleanVar(value=False)
        self.hw_accel_type = tk.StringVar(value="AMD")
        self.is_processing = False
        self.process = None
        self.fox_animation = None
        self.log_visible = False
        self.hw_accel_menu_visible = False
        self.fox_idle_frames = []
        self.fox_run_frames = []
        self.fox_run_frames_flipped = []
        self.current_fox_frame = 0
        self.fox_position = 0
        self.fox_direction = 1
        self.progress_canvas = None
        self.progress_window = None
        self.fox_image_id = None
        self.fox_text_id = None
        self.start_time = 0
        self.total_duration = 0
        self.current_progress = 0

        self.load_fox_sprites()
        self.setup_ui()
        self.start_fox_idle_animation()
        self.root.bind("<Configure>", self.on_window_resize)
        self.update_ui_text()

    def load_fox_sprites(self):
        try:
            for i in range(1, 10):
                # Используем resource_path для поиска спрайтов
                img_path = resource_path(os.path.join('idle', f'foxidle{i}.png'))
                img = Image.open(img_path).convert("RGBA")
                img = img.resize((24, 20), Image.Resampling.NEAREST)
                self.fox_idle_frames.append(ImageTk.PhotoImage(img))
            for i in range(1, 9):
                # Используем resource_path для поиска спрайтов
                img_path = resource_path(os.path.join('run', f'foxrun{i}.png'))
                img = Image.open(img_path).convert("RGBA")
                img = img.resize((24, 20), Image.Resampling.NEAREST)
                self.fox_run_frames.append(ImageTk.PhotoImage(img))
                img_flipped = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                self.fox_run_frames_flipped.append(ImageTk.PhotoImage(img_flipped))
        except Exception as e:
            print(f"Sprite loading error: {e}")

    def setup_ui(self):
        top_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        top_frame.pack(fill="x", padx=20, pady=(10, 0))

        self.title_label = ctk.CTkLabel(top_frame, font=ctk.CTkFont(size=48, weight="bold"), text_color="#D95B14")
        self.title_label.pack(fill="x")  # Этот виджет теперь заполняет всю ширину и центрирует текст

        lang_values = list(self.loc.get_available_languages().values())
        self.lang_menu = ctk.CTkOptionMenu(top_frame, values=lang_values, command=self.change_language,
                                           width=120, fg_color="#423A36", button_color="#423A36",
                                           button_hover_color="#574F4A", text_color="#F0E6DD")
        # Используем place для точного позиционирования справа, не влияя на заголовок
        self.lang_menu.place(relx=1.0, rely=0.5, x=-5, anchor="e")
        self.lang_menu.set(self.loc.get_available_languages().get(self.loc.current_lang))

        self.main_frame = ctk.CTkScrollableFrame(self.root, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # --- Все остальные виджеты остаются как были, до кнопок логов ---

        video_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        video_frame.pack(fill="x", padx=10, pady=5)
        self.video_label = ctk.CTkLabel(video_frame, font=ctk.CTkFont(size=14, weight="bold"), text_color="#F0E6DD")
        self.video_label.pack(anchor="w")
        video_input_frame = ctk.CTkFrame(video_frame, fg_color="transparent")
        video_input_frame.pack(fill="x")
        self.video_entry = ctk.CTkEntry(video_input_frame, textvariable=self.video_path, height=35,
                                        font=ctk.CTkFont(size=12), fg_color="#3D3530", border_width=0,
                                        text_color="#F0E6DD")
        self.video_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.video_browse_button = ctk.CTkButton(video_input_frame, command=self.browse_video, width=80, height=35,
                                                 fg_color="#423A36", hover_color="#574F4A", text_color="#F0E6DD")
        self.video_browse_button.pack(side="right")

        sub_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        sub_frame.pack(fill="x", padx=10, pady=5)
        self.sub_label = ctk.CTkLabel(sub_frame, font=ctk.CTkFont(size=14, weight="bold"), text_color="#F0E6DD")
        self.sub_label.pack(anchor="w")
        sub_input_frame = ctk.CTkFrame(sub_frame, fg_color="transparent")
        sub_input_frame.pack(fill="x")
        self.sub_entry = ctk.CTkEntry(sub_input_frame, textvariable=self.subtitle_path, height=35,
                                      font=ctk.CTkFont(size=12), fg_color="#3D3530", border_width=0,
                                      text_color="#F0E6DD")
        self.sub_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.sub_browse_button = ctk.CTkButton(sub_input_frame, command=self.browse_subtitles, width=80, height=35,
                                               fg_color="#423A36", hover_color="#574F4A", text_color="#F0E6DD")
        self.sub_browse_button.pack(side="right")

        name_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        name_frame.pack(fill="x", padx=10, pady=5)
        self.name_label = ctk.CTkLabel(name_frame, font=ctk.CTkFont(size=14, weight="bold"), text_color="#F0E6DD")
        self.name_label.pack(anchor="w")
        name_input_frame = ctk.CTkFrame(name_frame, fg_color="transparent")
        name_input_frame.pack(fill="x")
        self.name_entry = ctk.CTkEntry(name_input_frame, textvariable=self.output_name, height=35,
                                       font=ctk.CTkFont(size=12), fg_color="#3D3530", border_width=0,
                                       text_color="#F0E6DD")
        self.name_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.format_menu = ctk.CTkOptionMenu(name_input_frame, variable=self.output_format,
                                             values=["mp4", "mkv", "avi", "mov", "webm"], width=80, height=35,
                                             fg_color="#423A36", button_color="#423A36", button_hover_color="#574F4A",
                                             text_color="#F0E6DD")
        self.format_menu.pack(side="right")

        output_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        output_frame.pack(fill="x", padx=10, pady=5)
        self.output_dir_label = ctk.CTkLabel(output_frame, font=ctk.CTkFont(size=14, weight="bold"),
                                             text_color="#F0E6DD")
        self.output_dir_label.pack(anchor="w")
        output_input_frame = ctk.CTkFrame(output_frame, fg_color="transparent")
        output_input_frame.pack(fill="x")
        self.output_entry = ctk.CTkEntry(output_input_frame, textvariable=self.output_dir, height=35,
                                         font=ctk.CTkFont(size=12), fg_color="#3D3530", border_width=0,
                                         text_color="#F0E6DD")
        self.output_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.output_dir_browse_button = ctk.CTkButton(output_input_frame, command=self.browse_output_dir, width=80,
                                                      height=35, fg_color="#423A36", hover_color="#574F4A",
                                                      text_color="#F0E6DD")
        self.output_dir_browse_button.pack(side="right")

        button_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        button_frame.pack(fill="x", padx=10, pady=10)
        self.start_button = ctk.CTkButton(button_frame, command=self.start_processing, height=45,
                                          font=ctk.CTkFont(size=16, weight="bold"), fg_color="#D95B14",
                                          hover_color="#F26E21", text_color="#F0E6DD")
        self.start_button.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.quality_menu = ctk.CTkOptionMenu(button_frame, variable=self.quality_mode, width=120, height=45,
                                              fg_color="#423A36", button_color="#423A36", button_hover_color="#574F4A",
                                              font=ctk.CTkFont(size=14), text_color="#F0E6DD")
        self.quality_menu.pack(side="right")

        hw_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        hw_frame.pack(fill="x", padx=10, pady=5)
        self.hw_accel_checkbox = ctk.CTkCheckBox(hw_frame, variable=self.hw_accel_enabled,
                                                 command=self.toggle_hw_accel_menu, font=ctk.CTkFont(size=13),
                                                 fg_color="#D95B14", text_color="#F0E6DD")
        self.hw_accel_checkbox.pack(anchor="w")
        self.hw_accel_frame = ctk.CTkFrame(hw_frame, fg_color="#3D3530")
        self.hw_accel_type_label = ctk.CTkLabel(self.hw_accel_frame, font=ctk.CTkFont(size=12), text_color="#F0E6DD")
        self.hw_accel_type_label.pack(anchor="w", padx=10, pady=(10, 5))
        self.hw_amd_radio = ctk.CTkRadioButton(self.hw_accel_frame, text="AMD (h24_amf)", variable=self.hw_accel_type,
                                               value="AMD", font=ctk.CTkFont(size=11), fg_color="#D95B14",
                                               text_color="#F0E6DD")
        self.hw_amd_radio.pack(anchor="w", padx=20, pady=2)
        self.hw_nvidia_radio = ctk.CTkRadioButton(self.hw_accel_frame, text="NVIDIA (h264_nvenc)",
                                                  variable=self.hw_accel_type, value="NVIDIA",
                                                  font=ctk.CTkFont(size=11), fg_color="#D95B14", text_color="#F0E6DD")
        self.hw_nvidia_radio.pack(anchor="w", padx=20, pady=(2, 10))

        self.status_label = ctk.CTkLabel(self.main_frame, font=ctk.CTkFont(size=14), text_color="#F0E6DD")
        self.status_label.pack(pady=(10, 10))
        progress_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        progress_frame.pack(fill="x", padx=10, pady=5)
        self.progress_canvas = tk.Canvas(progress_frame, height=44, bg="#211A16", bd=0, highlightthickness=0)
        self.progress_canvas.pack(fill="x")
        self.progress_bar = ctk.CTkProgressBar(self.progress_canvas, height=20, progress_color="#D95B14",
                                               fg_color="#3D3530")
        self.progress_bar.set(0)
        self.progress_window = self.progress_canvas.create_window(0, 22, anchor="nw", window=self.progress_bar,
                                                                  width=self.progress_canvas.winfo_width())
        self.progress_canvas.bind("<Configure>", self._on_progress_canvas_resize)
        initial_frame = self.fox_idle_frames[0] if self.fox_idle_frames else None
        if initial_frame:
            self.fox_image_id = self.progress_canvas.create_image(5, 4, anchor="nw", image=initial_frame)

        info_frame = ctk.CTkFrame(progress_frame, fg_color="transparent")
        info_frame.pack(fill="x", pady=(5, 0))
        self.progress_percent_label = ctk.CTkLabel(info_frame, text="0%", font=ctk.CTkFont(size=12),
                                                   text_color="#F0E6DD")
        self.progress_percent_label.pack(side="left")
        self.time_remaining_label = ctk.CTkLabel(info_frame, font=ctk.CTkFont(size=12), text_color="#F0E6DD")
        self.time_remaining_label.pack(side="right")
        self.cancel_button = ctk.CTkButton(self.main_frame, command=self.cancel_processing, height=35,
                                           fg_color="#A93F3F", hover_color="#C85F5F")
        self.cancel_button.pack(pady=5, padx=10)

        # --- Изменения здесь ---
        # Кнопки логов теперь пакуются отдельно для идеального центрирования
        self.log_toggle_button = ctk.CTkButton(self.main_frame, command=self.toggle_log, height=30,
                                               fg_color="transparent", hover_color="#423A36", text_color="#F0E6DD")
        self.log_toggle_button.pack(pady=(5, 0), padx=10)

        self.copy_logs_button = ctk.CTkButton(self.main_frame, command=self.copy_logs, height=30, fg_color="#423A36",
                                              hover_color="#574F4A")
        self.copy_logs_button.pack(pady=(5, 10), padx=10)
        # --- Конец изменений ---

        self.log_text = ctk.CTkTextbox(self.main_frame, height=150, font=ctk.CTkFont(family="Consolas", size=10),
                                       fg_color="#1C1C1C", text_color="#F0E6DD")

        self.video_path.trace("w", self.update_output_defaults)

    def change_language(self, lang_name):
        if self.loc.set_language(lang_name):
            self.update_ui_text()

    def update_ui_text(self):
        self.root.title(self.loc.get("window_title"))
        self.title_label.configure(text=self.loc.get("main_title"))
        self.video_label.configure(text=self.loc.get("video_file_label"))
        self.video_browse_button.configure(text=self.loc.get("browse_button"))
        self.sub_label.configure(text=self.loc.get("subtitle_file_label"))
        self.sub_browse_button.configure(text=self.loc.get("browse_button"))
        self.name_label.configure(text=self.loc.get("output_name_label"))
        self.output_dir_label.configure(text=self.loc.get("output_dir_label"))
        self.output_dir_browse_button.configure(text=self.loc.get("browse_button"))
        self.start_button.configure(text=self.loc.get("start_button"))

        quality_menu_values = self.loc.get("quality_menu_values")
        self.quality_mode.set(quality_menu_values[0])
        self.quality_menu.configure(values=quality_menu_values)

        self.hw_accel_checkbox.configure(text=self.loc.get("hw_accel_checkbox"))
        self.hw_accel_type_label.configure(text=self.loc.get("hw_accel_type_label"))
        self.status_label.configure(text=self.loc.get("status_ready"))
        self.cancel_button.configure(text=self.loc.get("cancel_button"))
        self.log_toggle_button.configure(
            text=self.loc.get("show_logs_button") if not self.log_visible else self.loc.get("hide_logs_button"))
        self.copy_logs_button.configure(text=self.loc.get("copy_logs_button"))

        # --- ВОТ ИСПРАВЛЕНИЕ ---
        self.time_remaining_label.configure(text="")  # Добавлена эта строка
    def toggle_log(self):
        self.log_visible = not self.log_visible
        if self.log_visible:
            self.log_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
            self.log_toggle_button.configure(text=self.loc.get("hide_logs_button"))
            self.update_ui_layout()
        else:
            self.log_text.pack_forget()
            self.log_toggle_button.configure(text=self.loc.get("show_logs_button"))

    def validate_inputs(self):
        if not self.video_path.get() or not os.path.exists(self.video_path.get()):
            messagebox.showerror(self.loc.get("error_msg_title"), self.loc.get("invalid_video_file_msg"))
            return False
        if not self.subtitle_path.get() or not os.path.exists(self.subtitle_path.get()):
            messagebox.showerror(self.loc.get("error_msg_title"), self.loc.get("invalid_subtitle_file_msg"))
            return False
        if not self.output_name.get().strip():
            messagebox.showerror(self.loc.get("error_msg_title"), self.loc.get("invalid_output_name_msg"))
            return False
        if not self.output_dir.get() or not os.path.exists(self.output_dir.get()):
            messagebox.showerror(self.loc.get("error_msg_title"), self.loc.get("invalid_output_dir_msg"))
            return False
        return True

    def update_progress_info(self, progress):
        pct = int(progress * 100)
        self.progress_bar.set(progress)
        self.progress_percent_label.configure(text=f"{pct}%")
        if progress > 0.01:
            elapsed = time.time() - self.start_time
            estimated_total = elapsed / progress
            remaining = estimated_total - elapsed
            if remaining > 0:
                rm = int(remaining // 60)
                rs = int(remaining % 60)
                self.time_remaining_label.configure(
                    text=f"{self.loc.get('time_remaining_label_prefix')}{rm:02d}:{rs:02d}")
            else:
                self.time_remaining_label.configure(text=self.loc.get("time_remaining_label_finishing"))
        else:
            self.time_remaining_label.configure(text=self.loc.get("time_remaining_label_calc"))

    def run_ffmpeg(self):
        temp_sub_copy = None
        try:
            video_path = self.video_path.get()
            subtitle_path = self.subtitle_path.get()
            out_name = self.output_name.get().strip()
            out_dir = self.output_dir.get()
            output_format = self.output_format.get()
            output_path = os.path.join(out_dir, f"{out_name}.{output_format}")

            temp_sub_copy = self._ensure_ass_utf8(subtitle_path)
            escaped_sub_path = Path(temp_sub_copy).as_posix().replace(":", r"\:")
            vf = f"subtitles='{escaped_sub_path}'"

            quality = self.loc.get("quality_menu_values").index(self.quality_mode.get())
            hw_enabled = self.hw_accel_enabled.get()
            hw_type = self.hw_accel_type.get()

            cmd = ["ffmpeg", "-i", video_path]

            if quality == 2:
                vf += ",scale=1280:720"

            cmd.extend(["-vf", vf])

            if hw_enabled:
                cmd.extend(["-c:v", "h264_amf" if hw_type == "AMD" else "h264_nvenc"])
            else:
                cmd.extend(["-c:v", "libx264"])

            cmd.extend(["-c:a", "copy"])

            bitrate_options = {0: 0, 1: 1200000, 2: 600000}
            target_bitrate = bitrate_options.get(quality, 0)

            if target_bitrate > 0:
                cmd.extend(["-b:v", str(target_bitrate), "-maxrate", str(int(target_bitrate * 1.2)), "-bufsize",
                            str(target_bitrate * 2)])
            else:
                original_bitrate = self.get_video_bitrate(video_path)
                if original_bitrate:
                    target_bitrate = max(int(original_bitrate * 0.9), 1000000)
                    cmd.extend(["-b:v", str(target_bitrate), "-maxrate", str(int(target_bitrate * 1.2)), "-bufsize",
                                str(target_bitrate * 2)])
                else:
                    if hw_enabled:
                        cmd.extend(["-rc", "cqp", "-qp_i", "20", "-qp_p", "22", "-qp_b", "24"])
                    else:
                        cmd.extend(["-crf", "20"])

            if hw_enabled:
                cmd.extend(["-quality", "speed"])
            else:
                cmd.extend(["-preset", "medium"])

            cmd.extend(["-progress", "pipe:1", "-y", output_path])

            self.log_message("Command: " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
            self.update_status("status_processing_video")

            self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                            encoding="utf-8", errors="replace",
                                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)

            for line in iter(self.process.stdout.readline, ''):
                self.log_message(line.strip())
                self.parse_ffmpeg_progress(line)

            rc = self.process.wait()
            if rc == 0:
                self.update_status("status_processing_done")
                self.root.after(0, lambda: self.update_progress_info(1.0))
                try:
                    original_size = os.path.getsize(video_path) / (1024 * 1024)
                    output_size = os.path.getsize(output_path) / (1024 * 1024)
                    compression_ratio = (
                                (original_size - output_size) / original_size * 100) if original_size > 0 else 0
                    size_info = f"\nOriginal size: {original_size:.1f} MB\nOutput size: {output_size:.1f} MB\nCompression: {compression_ratio:.1f}%"
                    messagebox.showinfo(self.loc.get("success_msg_title"),
                                        self.loc.get("processing_success_with_stats_msg").format(stats=size_info,
                                                                                                 path=output_path))
                except:
                    messagebox.showinfo(self.loc.get("success_msg_title"),
                                        self.loc.get("processing_success_msg").format(path=output_path))
            else:
                self.update_status("status_processing_error")
                messagebox.showerror(self.loc.get("error_msg_title"), self.loc.get("processing_failed_msg"))
        except FileNotFoundError:
            self.update_status("status_ffmpeg_not_found")
            messagebox.showerror(self.loc.get("error_msg_title"), self.loc.get("ffmpeg_not_found_msg"))
        except Exception as e:
            self.update_status("status_error_occurred")
            messagebox.showerror(self.loc.get("error_msg_title"),
                                 self.loc.get("generic_error_msg").format(error=str(e)))
            self.log_message(f"Error: {str(e)}")
        finally:
            if temp_sub_copy and os.path.exists(temp_sub_copy):
                os.remove(temp_sub_copy)
            self.stop_processing()

    def start_processing(self):
        if not self.validate_inputs(): return
        self.is_processing = True
        self.start_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.update_status("status_processing_start")
        self.total_duration = self.get_video_duration(self.video_path.get())
        self.start_time = time.time()
        self.progress_bar.set(0)
        self.update_progress_info(0)
        self.stop_fox_idle_animation()
        self.start_fox_run_animation()
        threading.Thread(target=self.run_ffmpeg, daemon=True).start()

    def cancel_processing(self):
        if self.process:
            self.process.terminate()
            self.log_message("Process cancelled by user.")
            self.update_status("status_processing_cancelled")
        self.stop_processing()

    def stop_processing(self):
        self.is_processing = False
        self.process = None
        self.root.after(0, lambda: self.start_button.configure(state="normal"))
        self.root.after(0, lambda: self.cancel_button.configure(state="disabled"))
        self.stop_fox_run_animation()
        self.start_fox_idle_animation()

    def update_status(self, status_key):
        self.root.after(0, lambda: self.status_label.configure(text=self.loc.get(status_key)))

    def copy_logs(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.log_text.get("1.0", "end-1c"))
        messagebox.showinfo(self.loc.get("info_msg_title"), self.loc.get("logs_copied_msg"))

    # All other helper/utility methods remain the same
    def get_video_duration(self, video_path):
        try:
            cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of",
                   "default=noprint_wrappers=1:nokey=1", video_path]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            return float(result.stdout.strip() or 0)
        except:
            return 0

    def get_video_bitrate(self, video_path):
        try:
            cmd = ["ffprobe", "-v", "quiet", "-select_streams", "v:0", "-show_entries", "stream=bit_rate", "-of",
                   "default=noprint_wrappers=1:nokey=1", video_path]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if result.stdout.strip() and result.stdout.strip() != "N/A": return int(result.stdout.strip())
            cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=bit_rate", "-of",
                   "default=noprint_wrappers=1:nokey=1", video_path]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if result.stdout.strip() and result.stdout.strip() != "N/A": return int(result.stdout.strip())
        except:
            return None
        return None

    def _ensure_ass_utf8(self, orig_path):
        encodings = ["utf-8", "cp1251", "cp866", "latin1"]
        data = None
        for enc in encodings:
            try:
                with open(orig_path, "r", encoding=enc) as f:
                    data = f.read()
                break
            except:
                continue
        if data is None:
            with open(orig_path, "r", encoding="utf-8", errors="replace") as f: data = f.read()

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=Path(orig_path).suffix, prefix="sub_",
                                          dir=tempfile.gettempdir())
        with open(tmp.name, "w", encoding="utf-8") as f:
            f.write(data)
        return tmp.name

    def browse_video(self):
        fn = filedialog.askopenfilename(filetypes=[("Video files", "*.mp4 *.avi *.mov *.mkv *.webm")])
        if fn: self.video_path.set(fn)

    def browse_subtitles(self):
        fn = filedialog.askopenfilename(filetypes=[("Subtitle files", "*.ass *.srt"), ("All files", "*.*")])
        if fn: self.subtitle_path.set(fn)

    def browse_output_dir(self):
        fn = filedialog.askdirectory()
        if fn: self.output_dir.set(fn)

    def update_output_defaults(self, *args):
        v = self.video_path.get()
        if v and os.path.exists(v):
            self.output_name.set(Path(v).stem + "s")
            if not self.output_dir.get(): self.output_dir.set(str(Path(v).parent))

    def on_window_resize(self, event):
        if event.widget == self.root: self.update_ui_layout()

    def update_ui_layout(self):
        if self.log_visible:
            available_height = self.root.winfo_height() - 600
            self.log_text.configure(height=max(100, min(200, available_height)))

    def _on_progress_canvas_resize(self, event):
        self.progress_canvas.itemconfig(self.progress_window, width=event.width)
        max_pos = max(0, event.width - 30)
        if self.fox_position > max_pos:
            self.fox_position = max_pos
            if self.fox_image_id: self.progress_canvas.coords(self.fox_image_id, self.fox_position, 4)

    def toggle_hw_accel_menu(self):
        self.hw_accel_menu_visible = not self.hw_accel_menu_visible
        if self.hw_accel_enabled.get():
            self.hw_accel_frame.pack(fill="x", padx=20, pady=5)
        else:
            self.hw_accel_frame.pack_forget()

    def parse_ffmpeg_progress(self, line):
        try:
            if "out_time_ms=" in line:
                current_time = int(line.split("out_time_ms=")[-1].strip()) / 1000000.0
            elif "time=" in line and (m := re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)):
                h, mn, s = m.groups()
                current_time = int(h) * 3600 + int(mn) * 60 + float(s)
            else:
                return

            if self.total_duration > 0:
                prog = min(current_time / self.total_duration, 1.0)
                self.root.after(0, lambda: self.update_progress_info(prog))
        except:
            pass

    def animate_fox_idle(self):
        if not self.is_processing and self.fox_idle_frames:
            frame = self.fox_idle_frames[self.current_fox_frame]
            if self.fox_image_id: self.progress_canvas.itemconfigure(self.fox_image_id, image=frame)
            self.current_fox_frame = (self.current_fox_frame + 1) % len(self.fox_idle_frames)
            self.fox_animation = self.root.after(150, self.animate_fox_idle)

    def animate_fox_run(self):
        if self.is_processing and self.fox_run_frames:
            frames = self.fox_run_frames if self.fox_direction == 1 else self.fox_run_frames_flipped
            frame = frames[self.current_fox_frame]
            if self.fox_image_id: self.progress_canvas.itemconfigure(self.fox_image_id, image=frame)

            progress_width = self.progress_canvas.winfo_width()
            if progress_width > 30:
                max_position = progress_width - 30
                self.fox_position += self.fox_direction * 3
                if self.fox_position >= max_position:
                    self.fox_direction = -1
                elif self.fox_position <= 0:
                    self.fox_direction = 1
                self.progress_canvas.coords(self.fox_image_id, self.fox_position, 4)

            self.current_fox_frame = (self.current_fox_frame + 1) % len(frames)
            self.fox_animation = self.root.after(100, self.animate_fox_run)

    def stop_fox_idle_animation(self):
        if self.fox_animation: self.root.after_cancel(self.fox_animation)
        self.fox_animation = None

    def stop_fox_run_animation(self):
        if self.fox_animation: self.root.after_cancel(self.fox_animation)
        self.fox_animation = None

    def start_fox_idle_animation(self):
        if not self.is_processing:
            self.fox_position = 5;
            self.current_fox_frame = 0
            self.animate_fox_idle()

    def start_fox_run_animation(self):
        if self.is_processing:
            self.fox_position = 5;
            self.current_fox_frame = 0;
            self.fox_direction = 1
            self.animate_fox_run()

    def log_message(self, message):
        self.root.after(0, lambda: self.log_text.insert("end", message + "\n"))
        self.root.after(0, lambda: self.log_text.see("end"))

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = FOXBaker()
    app.run()