import json
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from pydantic import ValidationError
from CTkMessagebox import CTkMessagebox

from network_config_generator import NetworkConfigGenerator
from gns3_manager import Gns3Manager

class MainApp:
    def __init__(self, root):
        # Initialize main window
        self.root = root
        self.root.title("Config Generator")
        self.root.geometry("400x320")

        self.json_file_path = None
        self.project_path = None
        self.intent_file = None

        self.setup_ui()

    def setup_ui(self):
        # Build the main UI layout
        for label, command in [
            ("Select JSON File", self.select_json_file),
            ("Select GNS3 Project Path", self.select_project_path)
        ]:
            self.create_selection_frame(label, command)

        self.generate_button = ctk.CTkButton(
            self.root,
            text="Generate Configs",
            state="disabled",
            command=self.generate_configs
        )
        self.generate_button.pack(pady=20)

    def create_selection_frame(self, button_text, command):
        # Create a frame with a button and status label
        frame = ctk.CTkFrame(self.root)
        frame.pack(pady=10, padx=20, fill="x")

        button = ctk.CTkButton(frame, text=button_text, command=command)
        button.pack(pady=5)

        # Determine initial label text
        if "JSON" in button_text:
            label_text = "No file selected"
        else:
            label_text = "No project path selected"

        label = ctk.CTkLabel(frame, text=label_text, wraplength=400)
        label.pack(pady=5)

        # Store reference for later updates
        if "JSON" in button_text:
            self.json_label = label
        else:
            self.project_label = label

    def reset(self):
        # Reset UI controls and internal state
        self.json_file_path = None
        self.project_path = None
        self.intent_file = None

        self.json_label.configure(text="No file selected")
        self.project_label.configure(text="No project path selected")
        self.generate_button.configure(state="disabled")

    def select_json_file(self):
        # Prompt user to pick a JSON file
        file = filedialog.askopenfilename(
            title="Select JSON File",
            filetypes=[("JSON Files", "*.json")],
            initialdir=str(Path.home())
        )
        if file:
            self.json_file_path = file
            self.json_label.configure(text=file)
            self.check_ready_to_generate()
        else:
            self.reset()

    def select_project_path(self):
        # Prompt user to pick a GNS3 project folder
        path = filedialog.askdirectory(
            title="Select GNS3 Project Directory",
            initialdir=str(Path.home())
        )
        if path:
            self.project_path = path
            self.project_label.configure(text=path)
            self.check_ready_to_generate()
        else:
            self.reset()

    def check_ready_to_generate(self):
        # Enable generate button if both file and path are set
        if self.json_file_path and self.project_path:
            self.generate_button.configure(state="normal")
        else:
            self.generate_button.configure(state="disabled")

    def generate_configs(self):
        # Load JSON, generate configs, write to GNS3, and show recap
        with open(self.json_file_path, "r") as f:
            self.intent_file = json.load(f)

        generator = NetworkConfigGenerator(self.intent_file)
        project   = Gns3Manager(self.project_path)
        configs   = generator.generate_all_configs()
        project.write_router_config(configs)

        self.show_network_recap(generator)
        self.show_message("Success", "Config files generated successfully!", icon="check")

    def show_network_recap(self, generator):
        # Open a window displaying the network recap
        recap_window = ctk.CTkToplevel(self.root)
        recap_window.title("Network Recap")
        recap_window.geometry("640x500")

        recap_text = ctk.CTkTextbox(recap_window, width=620, height=460)
        recap_text.pack(padx=10, pady=10)

        try:
            recap = generator.generate_network_recap()
        except Exception as e:
            recap = f"Failed to generate network recap.\n\n{e}"

        recap_text.insert("1.0", recap)
        recap_text.configure(state="disabled")

    def show_message(self, title, message, icon="cancel"):
        # Display a message box
        CTkMessagebox(
            title=title,
            message=message,
            icon=icon,
            option_1="OK"
        )

if __name__ == "__main__":
    # Set UI theme and launch application
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    app  = MainApp(root)
    root.mainloop()
