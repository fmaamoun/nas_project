import json
import customtkinter as ctk
from pydantic import ValidationError
from config import MPLSConfig
from CTkMessagebox import CTkMessagebox
from pathlib import Path
from tkinter import filedialog
from gns3_project import Gns3Project


class ConfigGeneratorApp:
    def __init__(self, root):
        """
        Initialize the Config Generator application.
        """
        self.json_file_path = None
        self.project_path = None
        self.root = root
        self.root.title("Config Generator")
        self.root.geometry("350x300")

        # Frame for JSON File Selection
        self.json_frame = ctk.CTkFrame(self.root)
        self.json_frame.pack(pady=10, padx=20, fill="x")

        self.select_json_button = ctk.CTkButton(
            self.json_frame, text="Select JSON File", command=self.select_json_file
        )
        self.select_json_button.pack(pady=5)

        self.json_file_label = ctk.CTkLabel(self.json_frame, text="No JSON file selected", wraplength=400)
        self.json_file_label.pack(pady=5)

        # Frame for Project Path Selection
        self.project_frame = ctk.CTkFrame(self.root)
        self.project_frame.pack(pady=10, padx=20, fill="x")

        self.select_project_button = ctk.CTkButton(
            self.project_frame, text="Select GNS3 Project Path", command=self.select_project_path
        )
        self.select_project_button.pack(pady=5)

        self.project_path_label = ctk.CTkLabel(self.project_frame, text="No project path selected", wraplength=400)
        self.project_path_label.pack(pady=5)

        # Button to generate config files, disabled initially
        self.generate_button = ctk.CTkButton(
            self.root, text="Generate Configs", state="disabled", command=self.generate_configs
        )
        self.generate_button.pack(pady=20)

        self.intent_file = None  # Placeholder for validated network data
        self.router_configs = {}  # Placeholder for router configurations from GNS3 project

    def reset(self):
        """
        Reset the UI and internal state.
        """
        self.json_file_label.configure(text="No JSON file selected")
        self.project_path_label.configure(text="No project path selected")
        self.generate_button.configure(state="disabled")
        self.json_file_path = None
        self.project_path = None
        self.intent_file = None
        self.router_configs = {}

    def select_json_file(self):
        """
        Open a file dialog to select a JSON file and update the UI.
        """
        file_path = filedialog.askopenfilename(
            title="Select JSON File",
            filetypes=[("JSON Files", "*.json")],
            initialdir=str(Path.home())
        )
        if file_path:
            self.json_file_label.configure(text=f"{file_path}")
            self.json_file_path = file_path
            self.check_ready_to_generate()
        else:
            self.reset()

    def select_project_path(self):
        """
        Open a directory dialog to select a GNS3 project path and update the UI.
        """
        path = filedialog.askdirectory(
            title="Select GNS3 Project Directory",
            initialdir=str(Path.home())
        )
        if path:
            self.project_path_label.configure(text=f"{path}")
            self.project_path = path
            self.check_ready_to_generate()
        else:
            self.reset()

    def check_ready_to_generate(self):
        """
        Enable the generate button only if both JSON file and project path are selected.
        """
        if self.json_file_path and self.project_path:
            self.generate_button.configure(state="normal")
        else:
            self.generate_button.configure(state="disabled")

    def generate_configs(self):
        """
        Validate the selected JSON and generate configuration files.
        """
        try:
            # Load and validate JSON data
            with open(self.json_file_path, 'r') as file:
                json_data = json.load(file)

            print(json_data)
            self.intent_file = json_data

            # Init GNS3 project
            project = Gns3Project(self.project_path)

            # Generate configuration files using the validated network data and router configs
            config = MPLSConfig(self.intent_file)
            project.write_router_config(config.generate_all_configs())

            # Show success message
            CTkMessagebox(
                title="Success",
                message="Config files generated successfully!",
                icon="check",
                option_1="OK"
            )
        except ValidationError as e:
            error_message = "; ".join([err["msg"] for err in e.errors()])
            CTkMessagebox(
                title="Validation Error",
                message=error_message,
                icon="cancel",
                option_1="OK"
            )
        except ValueError as ve:
            CTkMessagebox(
                title="Value Error",
                message=str(ve),
                icon="cancel",
                option_1="OK"
            )
        except IOError as ioe:
            CTkMessagebox(
                title="IO Error",
                message=str(ioe),
                icon="cancel",
                option_1="OK"
            )
        except Exception as e:
            CTkMessagebox(
                title="Error",
                message=f"An error occurred: {str(e)}",
                icon="cancel",
                option_1="OK"
            )
        finally:
            self.reset()


if __name__ == "__main__":
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    app = ConfigGeneratorApp(root)
    root.mainloop()
