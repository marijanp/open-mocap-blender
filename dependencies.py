import importlib.util
import os

import bpy


# -------------------------------------------------------------
# HELPER FUNCTIONS
# -------------------------------------------------------------
# Modules the add-on imports, mapped to the package that provides them.
REQUIRED_PACKAGES = {
    "mediapipe": "mediapipe",
    "cv2": "opencv-python",
    "cvzone": "cvzone",
}

# Directory holding the MediaPipe .task models cvzone loads. The Nix package
# points this at the store; otherwise cvzone downloads them into its working
# directory on first use.
MODEL_DIR_ENV = "CVZONE_MODEL_DIR"

MODEL_FILES = ("pose_landmarker.task", "hand_landmarker.task")


def is_installed(module_name):
    """Check if a Python module is importable in Blender."""
    return importlib.util.find_spec(module_name) is not None


def missing_packages():
    """Return the packages this add-on needs but cannot import."""
    return [package for module, package in REQUIRED_PACKAGES.items() if not is_installed(module)]


def missing_models():
    """Return the MediaPipe models that are not present in the model directory."""
    model_dir = os.environ.get(MODEL_DIR_ENV)
    if not model_dir:
        # cvzone will download these itself into its working directory.
        return []
    return [name for name in MODEL_FILES if not os.path.exists(os.path.join(model_dir, name))]


# -------------------------------------------------------------
# OPERATORS
# -------------------------------------------------------------
class DependencyStatusOperator(bpy.types.Operator):
    """Report the state of the add-on's Python dependencies"""
    bl_idname = "addon.dependency_status"
    bl_label = "Check Dependencies"
    bl_description = "Report which Python dependencies and models are available."

    def execute(self, context):
        missing = missing_packages()
        if missing:
            self.report({'ERROR'}, f"Missing Python packages: {', '.join(missing)}")
            return {'CANCELLED'}

        models = missing_models()
        if models:
            self.report({'WARNING'}, f"Missing MediaPipe models: {', '.join(models)}")
            return {'CANCELLED'}

        self.report({'INFO'}, "All dependencies are available.")
        return {'FINISHED'}


classes = [DependencyStatusOperator]