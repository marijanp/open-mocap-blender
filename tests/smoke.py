"""
Headless smoke test for the Open Mocap add-on.

Runs synthetic motion data through the add-on in `blender -b`, so it covers
registration, animation, combining and baking code paths without a camera, a
display or real footage. It does not verify tracking quality: where detection is
involved the landmark data is fabricated, and verifying detection quality needs
footage this test deliberately does not have.

Run it from the development shell, which supplies the add-on and its
dependencies:

    blender --background --factory-startup --python-exit-code 1 --python tests/smoke.py
"""

import bpy
import importlib
import math
import os
import sys
import tempfile
import traceback

import numpy as np

MODULE = "bl_ext.user_default.open_mocap"

failures = []


def check(name, condition, detail=""):
    print(f"[smoke] {'ok' if condition else 'FAIL'}: {name}{f' ({detail})' if detail else ''}", flush=True)
    if not condition:
        failures.append(name)


def section(title):
    print(f"[smoke] --- {title}", flush=True)


def fcurve_count(obj):
    """F-curves on an object's action.

    Blender 5 replaced Action.fcurves with slotted actions, where the curves live
    in a channel bag inside the action's layers.
    """
    action = obj.animation_data.action if obj.animation_data else None
    if action is None:
        return 0
    return sum(
        len(strip.channelbag(obj.animation_data.action_slot).fcurves)
        for layer in action.layers
        for strip in layer.strips
    )


def bake(**kwargs):
    """Call the bake operator, mapping a reported error to CANCELLED.

    An operator that reports {'ERROR'} and returns CANCELLED makes bpy.ops raise,
    so both outcomes are folded into the returned set here.
    """
    try:
        return set(bpy.ops.object.bake_motion(**kwargs))
    except RuntimeError:
        return {"CANCELLED"}


def keyed_bones(obj, frame_start, frame_end):
    """Bones with keyframe points inside a frame range."""
    action = obj.animation_data.action if obj.animation_data else None
    if action is None:
        return set()
    names = set()
    for layer in action.layers:
        for strip in layer.strips:
            for fcurve in strip.channelbag(obj.animation_data.action_slot).fcurves:
                if not any(frame_start <= kp.co[0] <= frame_end for kp in fcurve.keyframe_points):
                    continue
                names.add(fcurve.data_path.split('"')[1])
    return names


def make_rig(name, bone_names):
    armature = bpy.data.armatures.new(name)
    rig = bpy.data.objects.new(name, armature)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    previous = None
    for index, bone_name in enumerate(bone_names):
        bone = armature.edit_bones.new(bone_name)
        bone.head = (0, 0, index)
        bone.tail = (0, 0, index + 1)
        bone.parent = previous
        previous = bone
    bpy.ops.object.mode_set(mode="OBJECT")
    return rig


section("dependencies")
for module in ("numpy", "cv2", "mediapipe", "cvzone"):
    try:
        __import__(module)
        check(f"import {module}", True)
    except Exception as exc:  # noqa: BLE001 - any failure to import is a failure
        check(f"import {module}", False, f"{type(exc).__name__}: {exc}")

section("registration")
# The extension must be linked into BLENDER_USER_EXTENSIONS for this to be
# discoverable; the development shell does that. Enable it the way Blender would.
import addon_utils  # noqa: E402

check(
    "extension is discoverable",
    any(m.__name__ == MODULE for m in addon_utils.modules(refresh=True)),
)
addon_utils.enable(MODULE, default_set=True, persistent=True)
check("enabled as an extension", MODULE in bpy.context.preferences.addons)

addon = importlib.import_module(MODULE)
gvar = importlib.import_module(f"{MODULE}.globalVariables")
operators = importlib.import_module(f"{MODULE}.operators")
utils = importlib.import_module(f"{MODULE}.utils")
CombineMotionData = operators.CombineMotionData

check("scene properties registered", hasattr(bpy.context.scene, "bake_frame_start"))

section("dependency status reporting")
from bl_ext.user_default.open_mocap import dependencies as depmod  # noqa: E402

check(
    "all packaged dependencies are visible",
    depmod.missing_packages() == [],
    ", ".join(depmod.missing_packages()),
)
check("MediaPipe models are visible", depmod.missing_models() == [], ", ".join(depmod.missing_models()))

section("synthetic pose capture data")
frames = []
for frame in range(5):
    points = []
    for i in range(40):
        points += [
            math.sin((frame + i) * 0.3) * 50,
            math.cos(frame * 0.2) * 30,
            0.1 * i,
        ]
    frames.append(points)

gvar.positionList = frames
gvar.fps = 30

section("animate pose")
try:
    result = bpy.ops.object.animate_obj()
    check("animate operator finished", "FINISHED" in result, str(result))
    check("40 pose empties created", len(gvar.object_list) == 40, str(len(gvar.object_list)))
    check("18 skeleton bones created", len(gvar.bones_list) == 18, str(len(gvar.bones_list)))
    animated = gvar.object_list[0]
    check(
        "keyframes written",
        animated.animation_data is not None and animated.animation_data.action is not None,
    )
except Exception:  # noqa: BLE001
    traceback.print_exc()
    check("animate operator", False)

section("combine motion data")
front = [[0.0] * (40 * 3) for _ in range(5)]
side = [[0.0] * (40 * 3) for _ in range(5)]
front[0][0] = 1.0
side[0][0] = 4.0
combined = CombineMotionData.combine_lists(None, front, side, 40)
check("frame count is the shorter list", len(combined) == 5, str(len(combined)))
check("z comes from the side view x", combined[0][2] == -4.0, str(combined[0][:3]))
check("front view data is preserved", combined[0][0] == 1.0, str(combined[0][:3]))

section("pose landmarks are read from the frame just submitted")
# cvzone can run inference on a background thread, in which case findPosition
# returns the previous frame's landmarks. The add-on requests synchronous
# inference, so a landmark set written for frame N must come back from frame N.


class SameFrameDetector:
    """Stands in for cvzone's PoseDetector.

    findPosition returns whatever the last findPose wrote. With synchronous
    inference that is the current frame; with cvzone's background thread it is
    the previous one, or nothing at the start.
    """

    def __init__(self):
        self.pending = None
        self.detected = []

    def findPose(self, img):
        self.detected.append(len(self.detected))
        self.pending = 100 + len(self.detected)
        return img

    def findPosition(self, img):
        current, self.pending = self.pending, None
        landmarks = [[float(current)] * 3 for _ in range(33)]
        return landmarks, {"bbox": (0, 0, 1, 1), "center": (0, 0)}


# Install the stub as the constructor would install the real detector, so the
# keyword arguments the add-on passes are captured too. Pre-setting
# tracker.detector would bypass the constructor and pass even with
# useThread=False removed from the add-on.
recorded_kwargs = {}
real_pose_detector = utils.PoseDetector


def recording_pose_detector(*args, **kwargs):
    recorded_kwargs.update(kwargs)
    return SameFrameDetector()


utils.PoseDetector = recording_pose_detector
try:
    tracker = utils.PoseTracking.__new__(utils.PoseTracking)
    tracker.detector = None
    tracker.mode = "front_pose"
    tracker.running = False
    gvar.positionList = []
    gvar.zlist = []
    img = np.zeros((480, 640, 3), np.uint8)
    for _ in range(3):
        tracker.detect_pose(img)
finally:
    utils.PoseDetector = real_pose_detector

check(
    "add-on asks for synchronous inference",
    recorded_kwargs == {"useThread": False},
    str(recorded_kwargs),
)
check("one sample captured per submitted frame", len(gvar.positionList) == 3, str(len(gvar.positionList)))
if len(gvar.positionList) == 3:
    # The fake detector tags each frame with a distinct x. Landmarks are
    # normalized as (x - width/2)/100, so the decoded x still tells which frame's
    # detection each sample came from: strictly increasing means each sample
    # carries its own frame rather than the previous one.
    decoded = [utils.MathUtility.cv2blender_coordinates(frame[0:3])[0] for frame in gvar.positionList]
    check(
        "each sample carries its own frame's landmarks",
        decoded == sorted(set(decoded)) and len(set(decoded)) == 3,
        str(decoded),
    )

section("hand landmarks and routing")
# Two failures to cover, both introduced by cvzone 2.0.0:
#  * it hardcoded handType "Unknown" although the Tasks API reports handedness
#    next to the landmarks, so both hands landed in the left list;
#  * it emitted [x, y, 0], dropping the landmark depth the add-on reads as Z.
#
# The stub hands are given distinct, exactly-representable landmark values so the
# expected normalization can be stated rather than approximated. cvzone converts
# with int(landmark * size); the add-on normalizes as
# ((x - width/2)/100, (y - height)/100, z/40) on a 640x480 frame. With
# landmark.x = i/64 and landmark.z = i/64 that yields x = 10*i and z = 10*i, so
# normalized Z is exactly 0.25*i (right hand) and 0.5*i (left hand).
from cvzone.HandTrackingModule import HandDetector  # noqa: E402

HAND_DEPTH_STEP = {"Right": 1.0 / 64, "Left": 2.0 / 64}


class FakeCategory:
    def __init__(self, name):
        self.category_name = name


class FakeLandmark:
    def __init__(self, index, depth_step):
        self.x = index * (1.0 / 64)
        self.y = 0.5
        self.z = index * depth_step


class FakeHandResult:
    """A detection carrying one landmark set per handedness label."""

    def __init__(self, labels):
        self.hand_landmarks = [
            [FakeLandmark(i, HAND_DEPTH_STEP[label]) for i in range(21)]
            for label in labels
        ]
        self.handedness = [[FakeCategory(label)] for label in labels]


hand_detector = HandDetector.__new__(HandDetector)
hand_detector.num_hands = 2
hand_detector.mode = "front_hand"
hand_detector.timestamp = 0
hand_detector.detector = type(
    "FakeHandLandmarker",
    (),
    {"detect_for_video": lambda _self, _img, _ts: FakeHandResult(["Right", "Left"])},
)()

gvar.R_hand_positionList = []
gvar.R_hand_zlist = []
gvar.L_hand_positionList = []
gvar.L_hand_zlist = []
hand_tracker = utils.HandTracking.__new__(utils.HandTracking)
hand_tracker.detector = hand_detector
hand_tracker.num_hands = 2
hand_tracker.mode = "front_hand"
hand_tracker.running = False
hand_tracker.detect_hand(img)


def hand_axis(sample, axis):
    return [sample[i * 3 + axis] for i in range(21)]


def captured_axis(samples, axis):
    return hand_axis(samples[0], axis) if samples else []


for label, samples in (
    ("Right", gvar.R_hand_positionList),
    ("Left", gvar.L_hand_positionList),
):
    step = HAND_DEPTH_STEP[label]
    expected_z = [i * step * 640 / 40 for i in range(21)]
    check(
        f"{label} hand captured with x,y,z triples",
        len(samples) == 1 and len(samples[0]) == 21 * 3,
        f"{len(samples)} samples, {len(samples[0]) if samples else 0} values",
    )
    check(
        f"{label} hand depth is preserved, not flattened",
        samples and all(value != 0.0 for value in captured_axis(samples, 2)[1:]),
        str(captured_axis(samples, 2)[:4]) if samples else "no data",
    )
    check(
        f"{label} hand depth matches landmark.z * width / 40",
        samples and captured_axis(samples, 2) == expected_z,
        f"expected {expected_z[:4]}, got {captured_axis(samples, 2)[:4]}" if samples else "no data",
    )
    expected_x = [(10 * i - 640 / 2) / 100 for i in range(21)]
    check(
        f"{label} hand x is normalized from the pixel conversion",
        samples and all(abs(a - b) < 1e-9 for a, b in zip(captured_axis(samples, 0), expected_x)),
        f"expected {expected_x[:3]}, got {captured_axis(samples, 0)[:3]}" if samples else "no data",
    )

check(
    "handedness routes hands to separate lists",
    len(gvar.R_hand_positionList) == 1 and len(gvar.L_hand_positionList) == 1,
    f"right={len(gvar.R_hand_positionList)} left={len(gvar.L_hand_positionList)}",
)

section("model directory handling")
# The packaged cvzone resolves models through CVZONE_MODEL_DIR at import time, so
# the module has to be reloaded for the variable to take effect. With it set, a
# missing model must fail rather than attempt a download into the store.
import cvzone.PoseModule as pose_module  # noqa: E402
import cvzone.HandTrackingModule as hand_module  # noqa: E402

missing_dir = os.path.join(tempfile.mkdtemp(), "no-models-here")
saved = os.environ.get("CVZONE_MODEL_DIR")
try:
    os.environ["CVZONE_MODEL_DIR"] = missing_dir
    importlib.reload(pose_module)
    importlib.reload(hand_module)
    check(
        "model path is taken from CVZONE_MODEL_DIR",
        pose_module.PoseDetector.MODEL_NAME == os.path.join(missing_dir, "pose_landmarker.task"),
        pose_module.PoseDetector.MODEL_NAME,
    )
    try:
        pose_module.PoseDetector()
        check("missing packaged model raises instead of downloading", False)
    except FileNotFoundError as exc:
        check("missing packaged model raises instead of downloading", True, str(exc))
    except Exception as exc:  # noqa: BLE001
        check("missing packaged model raises instead of downloading", False, f"{type(exc).__name__}: {exc}")
finally:
    if saved is None:
        os.environ.pop("CVZONE_MODEL_DIR", None)
    else:
        os.environ["CVZONE_MODEL_DIR"] = saved
    importlib.reload(pose_module)
    importlib.reload(hand_module)

section("bake motion")
try:
    rig = make_rig("RIG", ["spine", "chest", "head"])
    rig.pose.bones["spine"].constraints.new("COPY_ROTATION").target = gvar.bones_list[0]

    # Bake every bone when selection is not the filter.
    result = bpy.ops.object.bake_motion(
        target_rig="RIG", frame_start=1, frame_end=5, only_selected_bones=False
    )
    check("bake operator finished", "FINISHED" in result, str(result))
    check("bake produced fcurves", fcurve_count(rig) > 0, f"{fcurve_count(rig)} fcurves")

    # Blender 5 selects pose bones through PoseBone.select; the pre-5
    # PoseBone.bone.select this add-on used no longer exists.
    bpy.ops.object.mode_set(mode="POSE")
    rig.pose.bones["head"].select = True
    check(
        "PoseBone.select reaches context.selected_pose_bones",
        [b.name for b in bpy.context.selected_pose_bones] == ["head"],
    )
    bpy.ops.object.mode_set(mode="OBJECT")

    # Only the selected bone may be baked. The f-curves already exist from the
    # bake above, so the check is which bone gained keys in the new frame range.
    bpy.ops.object.mode_set(mode="POSE")
    rig.pose.bones["head"].select = False
    rig.pose.bones["chest"].select = True
    result = bake(target_rig="RIG", frame_start=6, frame_end=10, only_selected_bones=True)
    check("selected-bones bake finished", result == {"FINISHED"}, str(result))
    keyed = keyed_bones(rig, 6, 10)
    check("only the selected bone gained keys", keyed == {"chest"}, str(sorted(keyed)))
    check(
        "selection is restored after baking",
        [b.name for b in rig.pose.bones if b.select] == ["chest"],
        str([b.name for b in rig.pose.bones if b.select]),
    )

    # With nothing selected the bake must cancel rather than widen to every bone.
    bpy.ops.object.mode_set(mode="POSE")
    for bone in rig.pose.bones:
        bone.select = False
    before = fcurve_count(rig)
    result = bake(target_rig="RIG", frame_start=11, frame_end=15, only_selected_bones=True)
    check("zero-selection bake cancels", result == {"CANCELLED"}, str(result))
    check("zero-selection bake wrote nothing", fcurve_count(rig) == before)
    check("zero-selection bake left no bone selected", not any(b.select for b in rig.pose.bones))

    # Baking a rig that is not the active one, while another rig holds pose mode,
    # must leave the scene on the requested rig.
    make_rig("RIG_OTHER", ["other_root"])
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.mode_set(mode="POSE")
    result = bake(target_rig="RIG", frame_start=16, frame_end=18, only_selected_bones=False)
    check("baking a non-active rig finishes", result == {"FINISHED"}, str(result))
    check(
        "the requested rig became active",
        bpy.context.view_layer.objects.active.name == "RIG",
        bpy.context.view_layer.objects.active.name,
    )

    for frame_start, frame_end in ((5, 1), (0, 3)):
        before = fcurve_count(rig)
        result = bake(
            target_rig="RIG",
            frame_start=frame_start,
            frame_end=frame_end,
            only_selected_bones=False,
        )
        check(
            f"invalid frame range ({frame_start},{frame_end}) cancels",
            result == {"CANCELLED"},
            str(result),
        )
        check(
            f"invalid frame range ({frame_start},{frame_end}) wrote nothing",
            fcurve_count(rig) == before,
        )

    bpy.ops.object.mode_set(mode="OBJECT")
except Exception:  # noqa: BLE001
    traceback.print_exc()
    check("bake operator", False)

section("pose tracking over a video file")
# A stick figure is not a person, so this asserts only that the capture loop runs:
# the models load, the video decodes, detection runs and the loop stops cleanly.
# Detection quality is not asserted, and real footage is not used.


def write_test_video(path, frames=6):
    import cv2

    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 30, (640, 480))
    for frame in range(frames):
        image = np.zeros((480, 640, 3), np.uint8)
        cx = 320 + int(math.sin(frame * 0.4) * 40)
        cv2.circle(image, (cx, 120), 34, (200, 200, 200), -1)
        cv2.line(image, (cx, 154), (cx, 300), (220, 220, 220), 28)
        cv2.line(image, (cx, 180), (cx - 70, 240), (220, 220, 220), 20)
        cv2.line(image, (cx, 180), (cx + 70, 240), (220, 220, 220), 20)
        cv2.line(image, (cx, 300), (cx - 30, 420), (220, 220, 220), 24)
        cv2.line(image, (cx, 300), (cx + 30, 420), (220, 220, 220), 24)
        writer.write(image)
    writer.release()
    return path


with tempfile.TemporaryDirectory() as tmp:
    video = write_test_video(os.path.join(tmp, "synthetic.mp4"))
    gvar.positionList = []
    gvar.zlist = []
    gvar.front_video_path = video

    probe = utils.PoseTracking("front_pose")
    check("video opened for tracking", probe.running, video)
    # The detector is built on first detection, so count frames at detect_pose
    # rather than on a detector that may not exist yet.
    submitted = {"count": 0}
    original_detect_pose = probe.detect_pose

    def counting_detect_pose(frame_image):
        submitted["count"] += 1
        return original_detect_pose(frame_image)

    probe.detect_pose = counting_detect_pose

    steps = 0
    try:
        while probe.running and steps < 50:
            if probe.update_frame() is None:
                break
            steps += 1
        check("capture loop reached the end of the video", not probe.running, f"{steps} steps")
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        check("capture loop", False)
    finally:
        probe.stop()

    check(
        "every video frame reached the detector",
        submitted["count"] == 6,
        f"{submitted['count']} frames detected in {steps} steps",
    )
    check("detector was constructed from the packaged models", probe.detector is not None)
    # The packaged OpenCV has no GUI backend; the preview window must degrade to a
    # no-op instead of raising, which is what lets the loop above finish.
    check("preview window degrades without a GUI backend", utils.PreviewWindow.available is False)
    gvar.front_video_path = ""

section("unregistration")
try:
    addon.unregister()
    check("unregistered cleanly", not hasattr(bpy.context.scene, "bake_frame_start"))
    addon.register()
    check("re-registered cleanly", hasattr(bpy.context.scene, "bake_frame_start"))
except Exception:  # noqa: BLE001
    traceback.print_exc()
    check("unregister/register cycle", False)

section("result")
if failures:
    print(f"[smoke] FAILED {len(failures)} check(s): {failures}", flush=True)
    sys.exit(1)
print("[smoke] all checks passed", flush=True)