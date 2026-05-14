import customtkinter as ctk
from tkinter import filedialog, messagebox
import google.generativeai as genai
import threading
import time
import os

# UI Setup (Dark Mode)
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class ShortsAIApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("ShortsAI Pro - Viral Caption Generator")
        self.geometry("1100x750")
        self.resizable(False, False)

        # Variables
        self.video_paths = [None] * 5
        self.api_key_1 = ctk.StringVar()
        self.api_key_2 = ctk.StringVar()
        self.video_topic = ctk.StringVar()
        self.video_type = ctk.StringVar(value="Ranking Video (Top 5 to 1)")

        self.setup_ui()

    def setup_ui(self):
        # --- Left Panel (Video Inputs) ---
        self.left_frame = ctk.CTkFrame(self, width=300, corner_radius=10)
        self.left_frame.pack(side="left", fill="y", padx=20, pady=20)

        ctk.CTkLabel(self.left_frame, text="Upload Clips (Max 5)", font=("Arial", 18, "bold")).pack(pady=15)

        self.video_buttons = []
        for i in range(5):
            btn = ctk.CTkButton(self.left_frame, text=f"+ Select Clip {i+1}", height=60, 
                                fg_color="#2b2b2b", hover_color="#3b3b3b", border_width=1,
                                command=lambda idx=i: self.select_video(idx))
            btn.pack(pady=10, padx=20, fill="x")
            self.video_buttons.append(btn)

        # --- Right Panel (Outputs) ---
        self.right_frame = ctk.CTkFrame(self, corner_radius=10)
        self.right_frame.pack(side="right", fill="both", expand=True, padx=(0, 20), pady=20)

        ctk.CTkLabel(self.right_frame, text="AI Generated Captions", font=("Arial", 18, "bold")).pack(pady=15)

        self.output_boxes = []
        self.copy_buttons = []
        
        # Create 5 output areas
        for i in range(5):
            frame = ctk.CTkFrame(self.right_frame, fg_color="transparent")
            frame.pack(fill="x", padx=20, pady=5)
            
            lbl = ctk.CTkLabel(frame, text=f"Clip {i+1}:", font=("Arial", 14, "bold"))
            lbl.pack(side="left", padx=5)
            
            textbox = ctk.CTkTextbox(frame, height=60, wrap="word")
            textbox.pack(side="left", fill="x", expand=True, padx=5)
            self.output_boxes.append(textbox)
            
            copy_btn = ctk.CTkButton(frame, text="Copy English", width=100, 
                                     command=lambda idx=i: self.copy_english_only(idx))
            copy_btn.pack(side="right", padx=5)
            self.copy_buttons.append(copy_btn)

        # --- Bottom Panel (Settings & Generate) ---
        self.bottom_frame = ctk.CTkFrame(self.right_frame, height=150, corner_radius=10)
        self.bottom_frame.pack(side="bottom", fill="x", padx=20, pady=20)

        # Settings Row 1
        row1 = ctk.CTkFrame(self.bottom_frame, fg_color="transparent")
        row1.pack(fill="x", pady=10, padx=10)
        
        ctk.CTkLabel(row1, text="Primary Gemini Key:").pack(side="left", padx=5)
        ctk.CTkEntry(row1, textvariable=self.api_key_1, width=200, show="*").pack(side="left", padx=5)
        
        ctk.CTkLabel(row1, text="Backup Key (Optional):").pack(side="left", padx=10)
        ctk.CTkEntry(row1, textvariable=self.api_key_2, width=200, show="*").pack(side="left", padx=5)

        # Settings Row 2
        row2 = ctk.CTkFrame(self.bottom_frame, fg_color="transparent")
        row2.pack(fill="x", pady=5, padx=10)

        ctk.CTkLabel(row2, text="Video Topic:").pack(side="left", padx=5)
        ctk.CTkEntry(row2, textvariable=self.video_topic, width=200, placeholder_text="e.g. Top 5 Angry Cats").pack(side="left", padx=5)

        ctk.CTkLabel(row2, text="Type:").pack(side="left", padx=10)
        ctk.CTkOptionMenu(row2, variable=self.video_type, values=["Ranking Video (Top 5 to 1)", "Normal Compilation"]).pack(side="left", padx=5)

        # Generate Button
        self.generate_btn = ctk.CTkButton(self.bottom_frame, text="🚀 GENERATE CAPTIONS", 
                                          font=("Arial", 16, "bold"), height=40, fg_color="#00aa00", hover_color="#008800",
                                          command=self.start_generation)
        self.generate_btn.pack(pady=15)

        self.status_label = ctk.CTkLabel(self.bottom_frame, text="Ready.", text_color="gray")
        self.status_label.pack()

    def select_video(self, idx):
        filepath = filedialog.askopenfilename(title="Select Video", filetypes=[("Video Files", "*.mp4 *.mov *.avi")])
        if filepath:
            self.video_paths[idx] = filepath
            filename = os.path.basename(filepath)
            self.video_buttons[idx].configure(text=f"✅ {filename[:15]}...", fg_color="#1f538d")

    def copy_english_only(self, idx):
        text = self.output_boxes[idx].get("1.0", "end-1c")
        # Extract only English parts (assuming format: 1. English | Sinhala)
        english_lines = []
        for line in text.split('\n'):
            if '|' in line:
                english_lines.append(line.split('|')[0].strip())
        
        if english_lines:
            self.clipboard_clear()
            self.clipboard_append('\n'.join(english_lines))
            messagebox.showinfo("Copied", "English captions copied to clipboard! Ready for CapCut.")

    def start_generation(self):
        if not self.api_key_1.get():
            messagebox.showerror("Error", "Please enter your Primary Gemini API Key!")
            return
        if not any(self.video_paths):
            messagebox.showerror("Error", "Please select at least one video clip!")
            return

        self.generate_btn.configure(state="disabled", text="Processing...")
        threading.Thread(target=self.process_videos, daemon=True).start()

    def process_videos(self):
        current_key = self.api_key_1.get()
        genai.configure(api_key=current_key)
        
        topic = self.video_topic.get() or "General Video"
        v_type = self.video_type.get()

        for i, path in enumerate(self.video_paths):
            if not path:
                continue

            self.status_label.configure(text=f"Uploading Clip {i+1} to AI...")
            self.output_boxes[i].delete("1.0", "end")
            self.output_boxes[i].insert("end", "Processing...\n")

            try:
                # Upload video to Gemini
                video_file = genai.upload_file(path=path)
                
                # Wait for processing
                while video_file.state.name == "PROCESSING":
                    time.sleep(2)
                    video_file = genai.get_file(video_file.name)

                self.status_label.configure(text=f"Analyzing Clip {i+1}...")

                # Prompt Engineering
                rank_context = f"This is clip number {5-i} in a Top 5 countdown. Make it hype!" if "Ranking" in v_type else "This is a standalone funny/viral clip."
                prompt = f"""
                You are an expert YouTube Shorts creator targeting Tier 1 countries.
                Video Topic: {topic}. {rank_context}
                Watch the video and listen to the audio carefully.
                Give me 3 short, punchy, viral English text overlays (max 2-4 words each) with a matching emoji. Use modern internet slang.
                Also provide a brief Sinhala meaning for each.
                Strictly use this format:
                1. [English Caption] | [Sinhala Meaning]
                2. [English Caption] | [Sinhala Meaning]
                3. [English Caption] | [Sinhala Meaning]
                """

                model = genai.GenerativeModel(model_name="gemini-2.0-flash")
                response = model.generate_content([prompt, video_file])

                self.output_boxes[i].delete("1.0", "end")
                self.output_boxes[i].insert("end", response.text)

                # Smart Delay to avoid Rate Limits (15 seconds)
                if i < 4 and any(self.video_paths[i+1:]):
                    self.status_label.configure(text=f"Smart Delay: Waiting 15s to prevent API limits...")
                    time.sleep(15)

            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "quota" in error_msg.lower():
                    # Rate Limit Hit!
                    if self.api_key_2.get() and current_key == self.api_key_1.get():
                        self.status_label.configure(text="Limit hit! Switching to Backup Key...")
                        current_key = self.api_key_2.get()
                        genai.configure(api_key=current_key)
                        time.sleep(5) # Short pause before retry
                        # Retry logic can be added here, for now we just show error to manual retry
                        self.output_boxes[i].insert("end", "\n[Switched to Backup Key. Click Generate again for this clip]")
                    else:
                        self.status_label.configure(text="Limit hit! Auto-Pausing for 65 seconds...")
                        self.output_boxes[i].insert("end", "\n[Rate Limit Hit. Waiting 65s...]")
                        time.sleep(65)
                else:
                    self.output_boxes[i].insert("end", f"\nError: {error_msg}")

        self.status_label.configure(text="All clips processed successfully!")
        self.generate_btn.configure(state="normal", text="🚀 GENERATE CAPTIONS")

if __name__ == "__main__":
    app = ShortsAIApp()
    app.mainloop()
